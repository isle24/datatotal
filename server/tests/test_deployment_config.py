import os
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import server.main as main


ROOT = Path(__file__).resolve().parents[2]


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
