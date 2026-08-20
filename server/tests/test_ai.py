from pathlib import Path
import sys
import threading
from collections import deque
import json
import asyncio
import sqlite3
import tempfile
from unittest.mock import patch

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.services.ai import (  # noqa: E402
    build_ai_request,
    chat_completion_stream,
    default_ai_settings,
    list_models,
    normalize_model_list,
    normalize_ai_settings,
    public_ai_settings,
)
import server.main as main  # noqa: E402


class ConfigurationSettingsDB:
    def __init__(self):
        self.settings = {}
        self.audit = []

    def get_setting(self, key):
        return self.settings.get(key)

    def set_setting(self, key, value):
        self.settings[key] = value
        return {"ok": True}

    def set_settings_atomic(self, values, audit_changes=None, source="ai"):
        self.settings.update(values or {})
        self.audit.append(audit_changes or [])
        return {"ok": True}

    def add_configuration_audit(self, changes, source="ai"):
        self.audit.append({"source": source, "changes": changes})
        return {"ok": True}


def make_configuration_collector(db=None):
    collector = main.TrafficCollector.__new__(main.TrafficCollector)
    collector.db = db or ConfigurationSettingsDB()
    collector.ai_settings = normalize_ai_settings({"enabled": True, "apiKey": "configured-key"})
    collector.monitor_rules = []
    collector.notification_channels = []
    collector.container_protection_rules = []
    collector.docker_overrides = {"containers": {}}
    collector.get_settings = lambda: {
        "runtime": {"sampleSeconds": main.SAMPLE_SECONDS},
        "monitor": {"rules": collector.monitor_rules, "channels": collector.notification_channels, "containerRules": collector.container_protection_rules},
        "containerProtection": {"rules": collector.container_protection_rules},
        "notifications": {"channels": collector.notification_channels},
        "docker": {"containers": collector.docker_overrides.get("containers", {})},
        "ai": {"enabled": True, "provider": "openai", "baseUrl": "https://example.test/v1", "model": "test", "timeoutSeconds": 60, "maxTokens": 1200, "systemPrompt": ""},
    }
    return collector


def test_ai_settings_are_normalized_and_api_key_is_masked():
    settings = normalize_ai_settings(
        {
            "enabled": True,
            "baseUrl": "https://example.test/v1/",
            "apiKey": "secret-token",
            "model": "local-model",
            "timeoutSeconds": 45,
            "maxTokens": 5000,
            "systemPrompt": "分析 NAS 流量",
        }
    )

    assert settings["baseUrl"] == "https://example.test/v1"
    assert settings["apiKey"] == "secret-token"
    assert settings["timeoutSeconds"] == 45
    assert settings["maxTokens"] == 5000
    assert settings["provider"] == "openai"
    assert public_ai_settings(settings) == {
        "enabled": True,
        "provider": "openai",
        "baseUrl": "https://example.test/v1",
        "model": "local-model",
        "timeoutSeconds": 45,
        "maxTokens": 5000,
        "systemPrompt": "分析 NAS 流量",
        "keyConfigured": True,
        "apiKeyMasked": "sec...ken",
    }


def test_configuration_schema_excludes_secrets_and_host_controls():
    from server.services.config_assistant import configuration_schema

    paths = {item["path"] for item in configuration_schema()["fields"]}
    assert "runtime.sampleSeconds" in paths
    assert "ai.apiKey" not in paths
    assert "runtime.dbPath" not in paths
    forbidden_segments = {"apikey", "password", "token", "secret"}
    assert all(not (set(path.lower().split(".")) & forbidden_segments) for path in paths)


def test_configuration_response_requires_bounded_json_change_list():
    from server.services.config_assistant import parse_configuration_response

    response = parse_configuration_response(
        '{"changes":[{"path":"runtime.sampleSeconds","value":2,"summary":"采样间隔 2 秒","risk":"低"}]}'
    )
    assert response[0]["path"] == "runtime.sampleSeconds"
    try:
        parse_configuration_response("not json")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid AI configuration JSON should be rejected")


def test_configuration_changes_reject_sensitive_and_unknown_paths():
    from server.services.config_assistant import validate_configuration_changes

    current = {"runtime": {"sampleSeconds": 1}}
    for change, expected in (
        ({"path": "ai.apiKey", "value": "secret"}, "不允许"),
        ({"path": "runtime.execute", "value": "rm -rf /"}, "未知"),
    ):
        try:
            validate_configuration_changes([change], current)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("unsafe configuration change should be rejected")


def test_proposal_store_is_single_use_and_expires():
    from server.services.config_assistant import ProposalStore

    store = ProposalStore(ttl_seconds=1)
    proposal_id = store.put({"changes": []}, now_value=100)
    assert store.take(proposal_id, now_value=100)["changes"] == []
    assert store.take(proposal_id, now_value=100) is None
    expired = store.put({"changes": []}, now_value=100)
    assert store.take(expired, now_value=102) is None


def test_ai_configuration_proposal_does_not_persist_until_apply():
    collector = make_configuration_collector()
    response = '{"changes":[{"path":"runtime.sampleSeconds","value":2,"summary":"采样间隔 2 秒","risk":"低"}]}'
    with patch.object(main, "chat_completion", return_value={"answer": response}):
        result = collector.create_ai_configuration_proposal("把采样间隔改为 2 秒")
    assert result["requiresConfirmation"] is True
    assert collector.db.get_setting("runtime_settings") is None
    applied = collector.apply_ai_configuration_proposal(result["proposal"]["id"])
    assert applied["runtime"]["sampleSeconds"] == 2
    assert collector.db.get_setting("runtime_settings")["sampleSeconds"] == 2
    assert collector.apply_ai_configuration_proposal(result["proposal"]["id"])["ok"] is False


def test_ai_configuration_proposal_rejects_sensitive_changes():
    collector = make_configuration_collector()
    response = '{"changes":[{"path":"ai.apiKey","value":"secret","summary":"set key","risk":"high"}]}'
    with patch.object(main, "chat_completion", return_value={"answer": response}):
        result = collector.create_ai_configuration_proposal("设置 API Key 为 secret")
    assert result["ok"] is False
    assert "不允许" in result["detail"] or "敏感" in result["detail"]


def test_ai_configuration_applies_multiple_non_secret_setting_roots_and_preserves_key():
    collector = make_configuration_collector()
    response = json.dumps(
        {
            "changes": [
                {"path": "monitor.rules", "value": [{"id": "upload", "name": "upload", "metric": "wan_tx_bps", "threshold": 100, "durationSeconds": 0}], "summary": "增加上传规则", "risk": "低"},
                {"path": "ai.model", "value": "new-model", "summary": "切换模型", "risk": "低"},
                {"path": "docker.containers", "value": {"qb": {"containerId": "abcdef123456", "containerName": "qb", "iconKey": "qbittorrent", "ports": []}}, "summary": "设置容器图标", "risk": "低"},
            ]
        },
        ensure_ascii=False,
    )
    with patch.object(main, "chat_completion", return_value={"answer": response}):
        proposal = collector.create_ai_configuration_proposal("增加规则并设置容器图标")
    applied = collector.apply_ai_configuration_proposal(proposal["proposal"]["id"])
    assert applied["ok"] is True
    assert collector.monitor_rules[0]["id"] == "upload"
    assert collector.ai_settings["model"] == "new-model"
    assert collector.ai_settings["apiKey"] == "configured-key"
    assert collector.docker_overrides["containers"]["abcdef123456"]["iconKey"] == "qbittorrent"
    assert any(item for item in collector.db.audit if isinstance(item, list) and item)


def test_ai_settings_reject_invalid_endpoint_and_preserve_existing_key():
    existing = normalize_ai_settings({"apiKey": "old-secret"})
    settings = normalize_ai_settings(
        {"baseUrl": "file:///etc/passwd", "apiKey": "sec...cret"},
        existing=existing,
    )

    assert settings["baseUrl"] == default_ai_settings()["baseUrl"]
    assert settings["apiKey"] == "old-secret"


def test_ai_base_url_rejects_credentials_queries_fragments_and_sensitive_urls():
    existing = normalize_ai_settings({"apiKey": "old-secret", "baseUrl": "https://example.test/v1"})
    for value in (
        "https://user:pass@example.test/v1",
        "https://example.test/v1?token=secret",
        "https://example.test/v1#token",
        "https://token.example.test/v1",
    ):
        settings = normalize_ai_settings({"baseUrl": value}, existing=existing)
        assert settings["baseUrl"] == "https://example.test/v1"


def test_configuration_audit_is_atomic_and_does_not_store_string_values():
    with tempfile.TemporaryDirectory() as directory:
        db = main.TrafficDB(Path(directory) / "traffic.db")
        db.start()
        db.set_settings_atomic(
            {"runtime_settings": {"sampleSeconds": 2}},
            [{"path": "ai.model", "old": "old-model", "new": "new-model"}],
            source="test",
        )
        assert db.get_setting("runtime_settings")["sampleSeconds"] == 2
        audits = db.query_configuration_audit()
        assert audits[0]["source"] == "test"
        assert audits[0]["changes"][0]["new"] == {"type": "string", "length": len("new-model")}
        assert "new-model" not in json.dumps(audits, ensure_ascii=False)

        db.conn.execute(
            "CREATE TRIGGER fail_configuration_audit BEFORE INSERT ON configuration_audit "
            "BEGIN SELECT RAISE(ABORT, 'test rollback'); END;"
        )
        try:
            db.set_settings_atomic(
                {"runtime_settings": {"sampleSeconds": 3}},
                [{"path": "runtime.sampleSeconds", "old": 2, "new": 3}],
                source="test",
            )
        except sqlite3.DatabaseError:
            pass
        else:
            raise AssertionError("audit failure should roll back settings")
        assert db.get_setting("runtime_settings")["sampleSeconds"] == 2
        assert len(db.query_configuration_audit()) == 1
        db.conn.close()


def test_provider_defaults_and_legacy_settings_are_compatible():
    assert default_ai_settings()["provider"] == "openai"
    assert normalize_ai_settings({"baseUrl": "https://api.openai.com/v1"})["provider"] == "openai"
    deepseek = normalize_ai_settings({"provider": "deepseek"})
    assert deepseek["baseUrl"] == "https://api.deepseek.com"
    assert deepseek["model"] == "deepseek-v4-flash"
    assert deepseek["maxTokens"] == 393216
    deepseek_from_api_payload = normalize_ai_settings(
        {"provider": "deepseek", "baseUrl": "https://api.openai.com/v1", "model": "gpt-4o-mini"}
    )
    assert deepseek_from_api_payload["baseUrl"] == "https://api.deepseek.com"
    assert deepseek_from_api_payload["model"] == "deepseek-v4-flash"
    assert normalize_ai_settings({"provider": "anthropic"})["provider"] == "claude"


def test_ai_output_token_limit_preserves_valid_values_and_bounds_large_values():
    assert normalize_ai_settings({"maxTokens": 32768})["maxTokens"] == 32768
    assert normalize_ai_settings({"maxTokens": 999999})["maxTokens"] == 393216


def test_model_payload_is_bounded_and_supports_openai_and_anthropic_shapes():
    assert normalize_model_list({"data": [{"id": "gpt-a"}, {"id": "", "name": "ignored"}]}) == [
        {"id": "gpt-a", "name": "gpt-a"}
    ]
    assert normalize_model_list({"data": [{"id": "claude-a", "display_name": "Claude A"}]}) == [
        {"id": "claude-a", "name": "Claude A"}
    ]


def test_claude_request_uses_native_headers_and_message_shape():
    settings = normalize_ai_settings(
        {"provider": "claude", "apiKey": "secret", "model": "claude-test", "enabled": True}
    )
    request = build_ai_request(
        settings,
        [{"role": "system", "content": "rules"}, {"role": "user", "content": "hello"}],
    )
    assert request.full_url.endswith("/messages")
    assert request.get_header("X-api-key") == "secret"
    assert request.get_header("Anthropic-version") == "2023-06-01"
    assert request.get_header("Authorization") is None
    body = json.loads(request.data)
    assert body["system"] == "rules"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["max_tokens"] == 4096


def test_stream_request_enables_streaming_for_openai_compatible_provider():
    settings = normalize_ai_settings({"provider": "deepseek", "apiKey": "secret", "enabled": True})
    request = build_ai_request(settings, [{"role": "user", "content": "hello"}], stream=True)
    body = json.loads(request.data)
    assert body["stream"] is True
    assert request.full_url.endswith("/chat/completions")


def test_stream_completion_parses_openai_sse_and_emits_done_event():
    class StreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self, _limit):
            if self.lines:
                return self.lines.pop(0)
            return b""

        def close(self):
            pass

        lines = [
            b"data: {\"choices\":[{\"delta\":{\"content\":\"hello\"}}]}\n",
            b"data: {\"choices\":[{\"delta\":{\"content\":\" world\"}}]}\n",
            b"data: [DONE]\n",
            b"\n",
        ]

    settings = normalize_ai_settings({"provider": "deepseek", "apiKey": "secret", "enabled": True})
    with patch("server.services.ai.urllib.request.urlopen", return_value=StreamResponse()):
        events = list(chat_completion_stream(settings, [{"role": "user", "content": "hello"}]))
    assert events == [
        {"type": "delta", "content": "hello"},
        {"type": "delta", "content": " world"},
        {
            "type": "done",
            "answer": "hello world",
            "model": "deepseek-v4-flash",
            "usage": {},
            "finishReason": "stop",
            "truncated": False,
        },
    ]


def test_stream_completion_parses_anthropic_sse_and_usage():
    class StreamResponse:
        def __init__(self):
            self.lines = [
                b'event: content_block_delta\n',
                b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hello"}}\n',
                b'event: message_delta\n',
                b'data: {"type":"message_delta","usage":{"output_tokens":7}}\n',
                b'event: message_stop\n',
                b'data: {"type":"message_stop"}\n',
                b'\n',
            ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self, _limit):
            return self.lines.pop(0) if self.lines else b""

    settings = normalize_ai_settings(
        {"provider": "claude", "apiKey": "secret", "model": "claude-test", "enabled": True}
    )
    with patch("server.services.ai.urllib.request.urlopen", return_value=StreamResponse()):
        events = list(chat_completion_stream(settings, [{"role": "user", "content": "hello"}]))
    assert events == [
        {"type": "delta", "content": "hello"},
        {
            "type": "done",
            "answer": "hello",
            "model": "claude-test",
            "usage": {"output_tokens": 7},
            "finishReason": "stop",
            "truncated": False,
        },
    ]


def test_stream_completion_uses_configured_limit_instead_of_fixed_20000_chars():
    content = "x" * 21000

    class StreamResponse:
        lines = [
            (f'data: {{"choices":[{{"delta":{{"content":{json.dumps(content)}}}}}]}}\n').encode(),
            b"data: [DONE]\n",
        ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self, _limit):
            return self.lines.pop(0) if self.lines else b""

    settings = normalize_ai_settings({"provider": "deepseek", "apiKey": "secret", "enabled": True})
    with patch("server.services.ai.urllib.request.urlopen", return_value=StreamResponse()):
        events = list(chat_completion_stream(settings, [{"role": "user", "content": "hello"}]))
    assert events[-1]["answer"] == content
    assert events[-1]["truncated"] is False


def test_stream_completion_marks_provider_length_as_truncated():
    class StreamResponse:
        lines = [
            b'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":"length"}]}\n',
            b"data: [DONE]\n",
        ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self, _limit):
            return self.lines.pop(0) if self.lines else b""

    settings = normalize_ai_settings({"provider": "deepseek", "apiKey": "secret", "enabled": True})
    with patch("server.services.ai.urllib.request.urlopen", return_value=StreamResponse()):
        events = list(chat_completion_stream(settings, [{"role": "user", "content": "hello"}]))
    assert events[-1]["finishReason"] == "length"
    assert events[-1]["truncated"] is True


def test_stream_completion_marks_eof_without_provider_marker():
    class StreamResponse:
        lines = [b'data: {"choices":[{"delta":{"content":"partial"}}]}\n']

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self, _limit):
            return self.lines.pop(0) if self.lines else b""

    settings = normalize_ai_settings({"provider": "deepseek", "apiKey": "secret", "enabled": True})
    with patch("server.services.ai.urllib.request.urlopen", return_value=StreamResponse()):
        events = list(chat_completion_stream(settings, [{"role": "user", "content": "hello"}]))
    assert events[-1]["finishReason"] == "connection_closed"
    assert events[-1]["truncated"] is True


def test_stream_completion_preserves_length_reason_without_done_marker():
    class StreamResponse:
        lines = [
            b'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":"length"}]}\n',
        ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self, _limit):
            return self.lines.pop(0) if self.lines else b""

    settings = normalize_ai_settings({"provider": "deepseek", "apiKey": "secret", "enabled": True})
    with patch("server.services.ai.urllib.request.urlopen", return_value=StreamResponse()):
        events = list(chat_completion_stream(settings, [{"role": "user", "content": "hello"}]))
    assert events[-1]["finishReason"] == "length"
    assert events[-1]["truncated"] is True


def test_ai_history_is_persisted_and_can_be_cleared():
    with tempfile.TemporaryDirectory() as directory:
        db = main.TrafficDB(Path(directory) / "traffic.db")
        db.start()
        db.append_ai_messages(
            [
                {"role": "user", "content": "问题", "source": "chat"},
                {"role": "assistant", "content": "回答", "source": "chat", "truncated": True},
            ]
        )
        assert db.get_ai_messages() == [
            {"id": 1, "role": "user", "content": "问题", "source": "chat", "truncated": False},
            {"id": 2, "role": "assistant", "content": "回答", "source": "chat", "truncated": True},
        ]
        db.clear_ai_messages()
        assert db.get_ai_messages() == []


def test_model_discovery_uses_short_bounded_cache():
    class ResponseStub:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({"data": [{"id": "model-a"}]}).encode()

    settings = normalize_ai_settings({"apiKey": "secret", "enabled": False})
    with patch("server.services.ai.urllib.request.urlopen", return_value=ResponseStub()) as opener:
        first = list_models(settings, refresh=True)
        second = list_models(settings)
    assert first["models"] == [{"id": "model-a", "name": "model-a"}]
    assert first["cached"] is False
    assert second["cached"] is True
    assert opener.call_count == 1


def test_model_discovery_caches_safe_error_without_repeating_request():
    class ResponseStub:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b"{}"

    settings = normalize_ai_settings({"apiKey": "another-secret", "enabled": True})
    with patch("server.services.ai.urllib.request.urlopen", return_value=ResponseStub()) as opener:
        for _ in range(2):
            try:
                list_models(settings, refresh=False)
            except Exception as exc:
                assert "手动填写" in str(exc)
            else:
                raise AssertionError("model discovery should fail for an empty model list")
    assert opener.call_count == 1


def test_provider_error_detail_redacts_api_key():
    from server.services.ai import _safe_error_detail

    assert "secret-token" not in _safe_error_detail("provider echoed secret-token", "secret-token")
    assert "[redacted]" in _safe_error_detail("provider echoed secret-token", "secret-token")


def test_models_route_returns_structured_provider_error_without_500():
    original = main.collector.ai_settings
    main.collector.ai_settings = normalize_ai_settings({"provider": "qwen", "enabled": True})
    try:
        result = asyncio.run(main.ai_models())
    finally:
        main.collector.ai_settings = original
    assert result["ok"] is False
    assert result["provider"] == "qwen"
    assert result["models"] == []
    assert "API Key" in result["detail"]


def test_analyze_route_streams_sse_when_requested():
    payload = main.AIAnalyzePayload(scope="overview", question="check traffic")

    async def collect_response():
        with patch.object(
            main.collector,
            "ai_analyze_stream",
            return_value=iter(
                [
                    {"type": "delta", "content": "hello"},
                    {"type": "done", "answer": "hello", "model": "test", "usage": {}},
                ]
            ),
        ):
            response = await main.ai_analyze(payload, stream=True)
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
            return response, "".join(chunks)

    response, body = asyncio.run(collect_response())
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert 'data: {"type":"delta","content":"hello"}' in body
    assert 'data: {"type":"done","answer":"hello"' in body


class HistoryStub:
    def query_history(self, period):
        return {"period": period, "totals": {}, "buckets": []}

    def query_alerts(self, start, end, limit):
        return [{
            "id": "daily-1",
            "message": "daily upload",
            "evidence": {"reason": "Public upload exceeded 50 GB"},
            "notifications": [{"channelId": "meow", "ok": False, "detail": "timeout"}],
        }]

    def query_upload_diagnostic(self, date_value, limit=20):
        return {"date": date_value, "totals": {"txBytes": 60 * 1024**3}, "topProcesses": [{"name": "xunlei"}]}


def test_ai_context_uses_docker_summary_port_count():
    collector = main.TrafficCollector.__new__(main.TrafficCollector)
    collector.db = HistoryStub()
    collector.lock = threading.RLock()
    collector.alerts = deque(maxlen=20)
    collector.monitor_rules = []
    collector.api_overview = lambda _view: {}
    collector.process_rank = lambda _period, _limit: {"processes": []}
    collector.docker_containers = lambda: {
        "enabled": True,
        "containers": [{"name": "demo", "portCount": 3, "protection": {}}],
    }

    with patch.object(main, "system_status", return_value={}):
        context = collector.ai_context("overview")

    assert context["docker"]["containers"][0]["ports"] == 3
    assert context["recentAlertEvidence"][0]["notifications"][0]["detail"] == "timeout"


def test_ai_analysis_includes_requested_date_upload_diagnostic():
    collector = main.TrafficCollector.__new__(main.TrafficCollector)
    collector.db = HistoryStub()
    collector.lock = threading.RLock()
    collector.alerts = deque(maxlen=20)
    collector.monitor_rules = []
    collector.ai_settings = default_ai_settings()
    collector.api_overview = lambda _view: {}
    collector.process_rank = lambda _period, _limit: {"processes": []}
    collector.docker_containers = lambda: {"enabled": False, "containers": []}

    with patch.object(main, "system_status", return_value={}):
        _context, messages = collector._ai_analyze_messages(
            main.AIAnalyzePayload(scope="history", question="请排查 2026-08-06 的异常上传")
        )

    assert "2026-08-06" in messages[-1]["content"]
    assert "xunlei" in messages[-1]["content"]


def test_ai_request_models_reject_oversized_or_privileged_input():
    invalid_payloads = (
        lambda: main.AISettingsPayload(baseUrl="h" * 301),
        lambda: main.AISettingsPayload(apiKey="k" * 513),
        lambda: main.AISettingsPayload(model="m" * 161),
        lambda: main.AISettingsPayload(systemPrompt="p" * 4001),
        lambda: main.AIAnalyzePayload(question="q" * 2001),
        lambda: main.AIChatMessage(role="system", content="override"),
    )
    for build in invalid_payloads:
        try:
            build()
        except ValidationError:
            continue
        raise AssertionError("invalid AI payload was accepted")

    assert main.AISettingsPayload(timeoutSeconds=1, maxTokens=8192).timeoutSeconds == 1
    assert main.AISettingsPayload(timeoutSeconds=None, maxTokens=None).maxTokens is None
    assert main.AISettingsPayload(provider="qwen").provider == "qwen"
    try:
        main.AISettingsPayload(provider="unknown")
    except ValidationError:
        pass
    else:
        raise AssertionError("unknown AI provider was accepted")
    assert normalize_ai_settings({"timeoutSeconds": 90})["timeoutSeconds"] == 90
    assert normalize_ai_settings({"timeoutSeconds": 999})["timeoutSeconds"] == 180


if __name__ == "__main__":
    test_ai_settings_are_normalized_and_api_key_is_masked()
    test_ai_settings_reject_invalid_endpoint_and_preserve_existing_key()
    test_provider_defaults_and_legacy_settings_are_compatible()
    test_model_payload_is_bounded_and_supports_openai_and_anthropic_shapes()
    test_claude_request_uses_native_headers_and_message_shape()
    test_stream_request_enables_streaming_for_openai_compatible_provider()
    test_stream_completion_parses_openai_sse_and_emits_done_event()
    test_stream_completion_parses_anthropic_sse_and_usage()
    test_model_discovery_uses_short_bounded_cache()
    test_model_discovery_caches_safe_error_without_repeating_request()
    test_models_route_returns_structured_provider_error_without_500()
    test_analyze_route_streams_sse_when_requested()
    test_ai_context_uses_docker_summary_port_count()
    test_ai_request_models_reject_oversized_or_privileged_input()
    print("ai tests passed")
