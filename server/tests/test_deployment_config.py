import os
import io
from collections import deque
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
import tempfile
from unittest.mock import patch
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import server.main as main
from server.services.notifications import (
    DEFAULT_NOTIFY_BODY_TEMPLATE,
    LEGACY_NOTIFY_BODY_TEMPLATE,
    notification_context,
    safe_notification_detail,
)


ROOT = Path(__file__).resolve().parents[2]


def test_builtin_docker_icons_match_names_images_and_compose_aliases():
    from server.services.docker_icons import match_docker_icon

    assert match_docker_icon(name="qbittorrent-nox")["key"] == "qbittorrent"
    assert match_docker_icon(image="redis:7-alpine")["key"] == "redis"
    assert match_docker_icon(compose_service="moviepolite")["key"] == "moviepilot"
    assert match_docker_icon(name="postgres")["key"] == "postgresql"


def test_builtin_docker_icon_list_is_bounded_and_local():
    from server.services.docker_icons import list_docker_icons

    icons = list_docker_icons()
    assert len(icons) >= 5
    assert all(item["dataUrl"].startswith("data:image/svg+xml,") for item in icons)
    assert all(len(item["dataUrl"]) < 65536 for item in icons)


def test_unknown_docker_service_does_not_receive_a_guess():
    from server.services.docker_icons import match_docker_icon

    assert match_docker_icon(name="totally-unrelated-service") == {}


def test_docker_discovery_adds_builtin_icon_and_manual_icon_wins():
    original = main.ENABLE_DOCKER_DISCOVERY
    main.ENABLE_DOCKER_DISCOVERY = True
    container = {
        "Id": "abcdef1234567890",
        "Names": ["/qbittorrent-nox"],
        "Image": "linuxserver/qbittorrent:latest",
        "Labels": {},
        "State": "running",
        "Status": "Up",
        "Created": 1,
        "HostConfig": {"NetworkMode": "bridge"},
        "Ports": [],
    }
    try:
        with patch("server.main.docker_api_get", return_value=[container]):
            _ports, rows = main.discover_containers({}, main.empty_docker_overrides())
        assert rows[0]["iconKey"] == "qbittorrent"
        assert rows[0]["iconSource"] == "builtin"

        custom_icon = "data:image/png;base64," + "a" * 32
        overrides = {
            "containers": {
                "abcdef123456": {
                    "containerId": "abcdef123456",
                    "containerName": "qbittorrent-nox",
                    "icon": custom_icon,
                }
            }
        }
        with patch("server.main.docker_api_get", return_value=[container]):
            _ports, rows = main.discover_containers({}, overrides)
        assert rows[0]["iconSource"] == "custom"
        assert rows[0]["containerIcon"] == custom_icon
    finally:
        main.ENABLE_DOCKER_DISCOVERY = original


class MemorySettingsDB:
    def __init__(self):
        self.settings = {}

    def get_setting(self, key):
        return self.settings.get(key)

    def set_setting(self, key, value):
        self.settings[key] = value
        return value


def test_compose_files_only_expose_bootstrap_environment():
    for name in ("docker-compose.yml", "docker-compose.nas.yml"):
        service = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))["services"]["nas-traffic-lens"]

        assert service["environment"] == {
            "APP_PORT": "8088",
            "DASHBOARD_PASSWORD": "123456",
        }
        assert "./data:/data" in service["volumes"]
        assert "./logs:/logs" in service["volumes"]
        assert "/var/run/docker.sock:/var/run/docker.sock:ro" in service["volumes"]


def test_docker_discovery_defaults_on_and_can_be_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert main.env_bool("ENABLE_DOCKER_DISCOVERY", True) is True
    with patch.dict(os.environ, {"ENABLE_DOCKER_DISCOVERY": "false"}, clear=True):
        assert main.env_bool("ENABLE_DOCKER_DISCOVERY", True) is False
    assert main.RuntimeSettingsPayload().dockerDiscovery is True


def test_first_start_seeds_runtime_defaults_in_sqlite():
    collector = main.TrafficCollector.__new__(main.TrafficCollector)
    collector.db = MemorySettingsDB()
    collector.monitor_rules = main.default_monitor_rules()
    collector.notification_channels = main.default_notification_channels()
    collector.container_protection_rules = main.default_container_protection_rules()
    collector.docker_overrides = main.empty_docker_overrides()

    collector.load_saved_settings()

    saved = collector.db.settings["runtime_settings"]
    assert saved["sampleSeconds"] == main.DEFAULT_SAMPLE_SECONDS
    assert saved["historyRetentionDays"] == main.DEFAULT_HISTORY_RETENTION_DAYS
    assert saved["dockerDiscovery"] is True


def test_saved_docker_discovery_setting_updates_runtime_status():
    collector = main.TrafficCollector.__new__(main.TrafficCollector)
    collector.db = MemorySettingsDB()
    collector.db.settings["runtime_settings"] = {"dockerDiscovery": False}
    collector.monitor_rules = main.default_monitor_rules()
    collector.notification_channels = main.default_notification_channels()
    collector.container_protection_rules = main.default_container_protection_rules()
    collector.docker_overrides = main.empty_docker_overrides()
    collector.container_status = {"enabled": True, "count": 0, "lastRefresh": None}

    try:
        collector.load_saved_settings()
        assert main.ENABLE_DOCKER_DISCOVERY is False
        assert collector.container_status["enabled"] is False
    finally:
        main.apply_runtime_settings(main.RuntimeSettingsPayload())


def make_settings_collector(db):
    collector = main.TrafficCollector.__new__(main.TrafficCollector)
    collector.db = db
    collector.monitor_rules = main.default_monitor_rules()
    collector.notification_channels = main.default_notification_channels()
    collector.container_protection_rules = main.default_container_protection_rules()
    collector.docker_overrides = main.empty_docker_overrides()
    collector.container_status = {"enabled": True, "count": 0, "lastRefresh": None}
    return collector


def test_runtime_migration_preserves_forward_fields():
    db = MemorySettingsDB()
    db.settings["runtime_settings"] = {
        "sampleSeconds": 2,
        "futureSetting": {"enabled": True},
    }
    collector = make_settings_collector(db)

    collector.load_saved_settings()

    saved = db.settings["runtime_settings"]
    assert saved["sampleSeconds"] == 2
    assert saved["dockerDiscovery"] is True
    assert saved["futureSetting"] == {"enabled": True}


def test_invalid_saved_runtime_is_not_overwritten():
    db = MemorySettingsDB()
    original = {"sampleSeconds": "not-a-number", "futureSetting": "keep"}
    db.settings["runtime_settings"] = dict(original)
    collector = make_settings_collector(db)

    with redirect_stdout(io.StringIO()):
        collector.load_saved_settings()

    assert db.settings["runtime_settings"] == original


def test_existing_monitor_rules_are_not_rewritten_on_startup():
    db = MemorySettingsDB()
    original = {
        "rules": [{
            "id": "future-rule",
            "name": "future rule",
            "metric": "wan_tx_bps",
            "futureField": "keep",
        }]
    }
    db.settings["monitor_rules"] = original
    collector = make_settings_collector(db)

    collector.load_saved_settings()

    assert db.settings["monitor_rules"] == original


def test_pyyaml_is_a_direct_dependency():
    requirements = (ROOT / "server" / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "pyyaml==" in requirements


def test_legacy_byte_threshold_is_formatted_as_readable_gibibytes():
    assert main.format_threshold(53687091200, "daily_wan_tx_bytes") == {
        "value": 50,
        "unit": "GB",
        "bytes": 53687091200,
        "label": "50 GB",
    }
    assert main.format_threshold(103386068478, "daily_wan_tx_bytes")["label"] == "96.29 GB"
    assert main.threshold_to_bytes(10, "MB/s") == 10 * 1024 * 1024


def test_zero_duration_monitor_rule_triggers_immediately():
    collector = main.TrafficCollector.__new__(main.TrafficCollector)
    collector.monitor_rules = [{
        "id": "daily",
        "name": "daily upload",
        "metric": "daily_wan_tx_bytes",
        "operator": "gte",
        "threshold": 1024,
        "durationSeconds": 0,
        "enabled": True,
        "channelIds": [],
    }]
    collector.rule_states = {}
    triggered = []
    collector.record_alert = lambda *args, **kwargs: triggered.append((args, kwargs))

    assert collector.evaluate_monitor_rule("daily_wan_tx_bytes", 1024, 100.0) is True
    assert len(triggered) == 1


def test_alert_evidence_and_notification_results_are_persisted_and_pruned():
    with tempfile.TemporaryDirectory() as directory:
        db = main.TrafficDB(Path(directory) / "traffic.db")
        db.start()
        alert = {
            "id": "daily-1",
            "timestamp": 1785945600,
            "type": "daily_wan_upload",
            "severity": "warning",
            "message": "daily upload",
            "value": 60 * 1024**3,
            "threshold": 50 * 1024**3,
        }
        db.add_alert(alert)
        db.add_alert_evidence(alert["id"], {
            "reason": "Public upload reached 60 GB, above 50 GB",
            "topProcesses": [{"name": "xunlei", "txBytes": 40 * 1024**3}],
        })
        db.add_alert_notification_result(alert["id"], {
            "channelId": "meow",
            "channelName": "Meow",
            "channelType": "meow",
            "ok": False,
            "detail": "timeout",
            "timestamp": 1785945601,
        })

        rows = db.query_alerts(1785940000, 1785950000, 10)
        assert rows[0]["evidence"]["topProcesses"][0]["name"] == "xunlei"
        assert rows[0]["notifications"][0]["ok"] is False
        assert rows[0]["notifications"][0]["detail"] == "timeout"

        db.prune_old(1785945601)
        assert db.query_alerts(0, 2000000000, 10) == []


def test_upload_diagnostic_returns_bounded_daily_totals_processes_interfaces_and_alerts():
    with tempfile.TemporaryDirectory() as directory:
        db = main.TrafficDB(Path(directory) / "traffic.db")
        db.start()
        start = int(datetime(2026, 8, 6).timestamp())
        db.add_minute(start + 60, [{
            "iface": "eth0", "scope": "wan", "rxBytes": 1024,
            "txBytes": 60 * 1024**3, "rxPackets": 1, "txPackets": 2,
        }])
        db.add_process_minute(start + 60, [{
            "processKey": main.process_key_for({"pid": 321, "name": "xunlei", "cmdline": "/usr/bin/xunlei"}),
            "rxBytes": 100, "txBytes": 40 * 1024**3,
            "rxPackets": 1, "txPackets": 2,
        }])
        db.add_alert({
            "id": "daily-1", "timestamp": start + 120,
            "type": "daily_wan_upload", "severity": "warning",
            "message": "daily upload", "value": 60 * 1024**3,
            "threshold": 50 * 1024**3,
        })

        diagnostic = db.query_upload_diagnostic("2026-08-06", limit=10)

        assert diagnostic["date"] == "2026-08-06"
        assert diagnostic["totals"]["txBytes"] == 60 * 1024**3
        assert diagnostic["topProcesses"][0]["name"] == "xunlei"
        assert diagnostic["topInterfaces"][0]["iface"] == "eth0"
        assert diagnostic["alerts"][0]["id"] == "daily-1"


def test_notification_context_exposes_human_readable_transfer_values():
    context = notification_context(
        {
            "id": "daily-1",
            "type": "daily_wan_upload",
            "value": 103386068478,
            "threshold": 53687091200,
            "evidence": {
                "actual": {"label": "96.3 GB"},
                "threshold": {"label": "50 GB"},
            },
        },
        {"id": "meow", "name": "Meow", "type": "meow"},
        "NAS Traffic Lens",
        "test",
    )

    assert context["value_human"] == "96.3 GB"
    assert context["threshold_human"] == "50 GB"


def test_notification_errors_redact_target_and_token_and_old_default_template_migrates():
    channel = {
        "url": "https://notify.example/secret-token.send",
        "token": "secret-token",
    }
    detail = safe_notification_detail(
        "request https://notify.example/secret-token.send failed for secret-token",
        channel,
    )
    assert "secret-token" not in detail
    assert "notify.example" not in detail
    sanitized = main.sanitize_notification_channel(main.NotificationChannel(
        id="meow",
        name="Meow",
        type="meow",
        bodyTemplate=LEGACY_NOTIFY_BODY_TEMPLATE,
    ))
    assert sanitized["bodyTemplate"] == DEFAULT_NOTIFY_BODY_TEMPLATE


def test_record_alert_captures_active_wan_process_and_missing_channel_result():
    with tempfile.TemporaryDirectory() as directory:
        db = main.TrafficDB(Path(directory) / "traffic.db")
        db.start()
        collector = main.TrafficCollector.__new__(main.TrafficCollector)
        collector.db = db
        collector.lock = main.threading.RLock()
        collector.alerts = deque(maxlen=20)
        collector.notification_channels = []
        process_key = main.process_key_for({
            "pid": 88,
            "name": "xunlei",
            "cmdline": "/usr/bin/xunlei",
            "container": {"id": "abc123", "name": "xunlei"},
        }, include_container_detail=True)
        collector.conn_totals = {
            f"eth0|wan|tcp|192.168.3.56:50000|8.8.8.8:443|{process_key}": main.Counter(tx_bytes=2048),
        }

        collector.record_alert(
            "daily_wan_upload",
            "warning",
            "daily upload",
            60 * 1024**3,
            50 * 1024**3,
            {"id": "daily", "metric": "daily_wan_tx_bytes", "channelIds": ["meow"], "window": "day"},
        )

        rows = db.query_alerts(0, int(main.now() + 10), 10)
        assert rows[0]["evidence"]["topProcesses"][0]["name"] == "xunlei"
        assert rows[0]["evidence"]["topProcesses"][0]["container"]["name"] == "xunlei"
        assert rows[0]["notifications"][0]["ok"] is False
        assert "no enabled notification channel" in rows[0]["notifications"][0]["detail"]


if __name__ == "__main__":
    test_compose_files_only_expose_bootstrap_environment()
    test_docker_discovery_defaults_on_and_can_be_disabled()
    test_first_start_seeds_runtime_defaults_in_sqlite()
    test_saved_docker_discovery_setting_updates_runtime_status()
    test_runtime_migration_preserves_forward_fields()
    test_invalid_saved_runtime_is_not_overwritten()
    test_existing_monitor_rules_are_not_rewritten_on_startup()
    test_pyyaml_is_a_direct_dependency()
    print("deployment config tests passed")
