from pathlib import Path
import sys
import threading
from collections import deque
from unittest.mock import patch

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.services.ai import (  # noqa: E402
    default_ai_settings,
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
    assert public_ai_settings(settings) == {
        "enabled": True,
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


if __name__ == "__main__":
    test_ai_settings_are_normalized_and_api_key_is_masked()
    test_ai_settings_reject_invalid_endpoint_and_preserve_existing_key()
    test_ai_context_uses_docker_summary_port_count()
    test_ai_request_models_reject_oversized_or_privileged_input()
    print("ai tests passed")
