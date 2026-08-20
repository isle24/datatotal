from pathlib import Path
import sys
import threading
from collections import deque
import json
import asyncio
from unittest.mock import patch

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.services.ai import (  # noqa: E402
    build_ai_request,
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
    assert settings["timeoutSeconds"] == 30
    assert settings["maxTokens"] == 4096
    assert settings["provider"] == "openai"
    assert public_ai_settings(settings) == {
        "enabled": True,
        "provider": "openai",
        "baseUrl": "https://example.test/v1",
        "model": "local-model",
        "timeoutSeconds": 30,
        "maxTokens": 4096,
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
    assert deepseek["baseUrl"] == "https://api.deepseek.com/v1"
    assert deepseek["model"] == "deepseek-chat"
    deepseek_from_api_payload = normalize_ai_settings(
        {"provider": "deepseek", "baseUrl": "https://api.openai.com/v1", "model": "gpt-4o-mini"}
    )
    assert deepseek_from_api_payload["baseUrl"] == "https://api.deepseek.com/v1"
    assert deepseek_from_api_payload["model"] == "deepseek-chat"
    assert normalize_ai_settings({"provider": "anthropic"})["provider"] == "claude"


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
    assert body["max_tokens"] == 1200


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


if __name__ == "__main__":
    test_ai_settings_are_normalized_and_api_key_is_masked()
    test_ai_settings_reject_invalid_endpoint_and_preserve_existing_key()
    test_provider_defaults_and_legacy_settings_are_compatible()
    test_model_payload_is_bounded_and_supports_openai_and_anthropic_shapes()
    test_claude_request_uses_native_headers_and_message_shape()
    test_model_discovery_uses_short_bounded_cache()
    test_model_discovery_caches_safe_error_without_repeating_request()
    test_models_route_returns_structured_provider_error_without_500()
    test_ai_context_uses_docker_summary_port_count()
    test_ai_request_models_reject_oversized_or_privileged_input()
    print("ai tests passed")
