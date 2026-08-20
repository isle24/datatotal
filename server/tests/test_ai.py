from pathlib import Path
import sys
import threading
from collections import deque
import json
import asyncio
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


def test_ai_settings_reject_invalid_endpoint_and_preserve_existing_key():
    existing = normalize_ai_settings({"apiKey": "old-secret"})
    settings = normalize_ai_settings(
        {"baseUrl": "file:///etc/passwd", "apiKey": "sec...cret"},
        existing=existing,
    )

    assert settings["baseUrl"] == default_ai_settings()["baseUrl"]
    assert settings["apiKey"] == "old-secret"


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
