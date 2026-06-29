from collections import defaultdict
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import server.main as main


def make_collector():
    collector = main.TrafficCollector.__new__(main.TrafficCollector)
    collector.lock = main.threading.RLock()
    collector.capture_interfaces = ["eth0"]
    collector.go_collector_available = False
    collector.conntrack_summary = {"available": False, "source": "capture", "total": 0, "wan": 0, "lan": 0, "rawTotal": 0, "mode": "active"}
    collector.socket_map = {}
    collector.conn_totals = {}
    collector.stage_started_at = None
    collector.stage_totals = defaultdict(lambda: defaultdict(main.Counter))
    collector.calibrated_stage_totals = defaultdict(lambda: defaultdict(main.Counter))
    collector.alerts = main.deque(maxlen=20)
    collector.alert_settings = main.AlertSettings()
    collector.container_protection_rules = []
    collector.container_protection_states = {}
    collector.container_status = {"enabled": False, "count": 0, "lastRefresh": None}
    collector.container_rows = []
    collector.container_rows_by_id = {}
    collector.container_ports = {}
    collector.docker_overrides = main.empty_docker_overrides()
    collector.docker_web_probe_cache = {}
    collector.last_container_refresh = main.now()
    collector.container_refresh_lock = main.threading.Lock()
    collector.notification_channels = [{"id": "webhook", "name": "Webhook", "enabled": True, "type": "webhook"}]
    collector.last_rates = {
        "eth0": {
            "systemRxBps": 128,
            "systemTxBps": 64,
            "scopes": {},
        }
    }
    return collector


def test_go_snapshot_empty_interfaces_falls_back_to_local_interfaces():
    collector = make_collector()
    local_interfaces = {
        "eth0": {
            "detail": {
                "name": "eth0",
                "isUp": True,
                "captured": True,
                "virtual": False,
                "defaultRoute": True,
            },
            "scopes": {},
            "system": {
                "rxBytes": 1234,
                "txBytes": 5678,
                "rxPackets": 10,
                "txPackets": 20,
            },
        }
    }

    with patch.object(collector, "snapshot_interfaces", return_value=local_interfaces):
        result = collector._merge_go_snapshot(
            {
                "interfaces": {},
                "rates": {},
                "connectionSummary": {"total": 0, "wan": 0, "lan": 0},
            },
            "physical",
        )

    assert "eth0" in result["interfaces"]
    assert result["interfaces"]["eth0"]["system"]["rxBytes"] == 1234
    assert result["rates"]["eth0"]["systemRxBps"] == 128


def test_go_snapshot_prefers_conntrack_summary_for_router_like_connection_counts():
    collector = make_collector()
    go_interfaces = {
        "eth0": {
            "detail": {
                "name": "eth0",
                "isUp": True,
                "captured": True,
                "virtual": False,
                "defaultRoute": True,
            },
            "scopes": {},
            "system": {
                "rxBytes": 1234,
                "txBytes": 5678,
                "rxPackets": 10,
                "txPackets": 20,
            },
        }
    }

    result = collector._merge_go_snapshot(
        {
            "interfaces": go_interfaces,
            "rates": {},
            "connectionSummary": {"total": 1800, "wan": 1200, "lan": 600},
            "conntrackSummary": {
                "available": True,
                "source": "conntrack",
                "total": 8,
                "wan": 3,
                "lan": 5,
                "rawTotal": 80,
                "mode": "active",
            },
        },
        "physical",
    )

    assert result["connectionSummary"]["source"] == "conntrack"
    assert result["connectionSummary"]["total"] == 8
    assert result["connectionSummary"]["wan"] == 3
    assert result["connectionSummary"]["lan"] == 5
    assert result["connectionSummary"]["rawTotal"] == 80


def test_go_snapshot_uses_socket_summary_when_go_conntrack_is_unavailable():
    collector = make_collector()
    collector.socket_map = {
        ("tcp", "192.168.3.56", "8.8.8.8", 50000, 443): {"pid": 1, "name": "wan"},
        ("tcp", "192.168.3.56", "192.168.3.1", 50001, 80): {"pid": 2, "name": "lan"},
    }
    go_interfaces = {
        "eth0": {
            "detail": {
                "name": "eth0",
                "isUp": True,
                "captured": True,
                "virtual": False,
                "defaultRoute": True,
            },
            "scopes": {},
            "system": {
                "rxBytes": 1234,
                "txBytes": 5678,
                "rxPackets": 10,
                "txPackets": 20,
            },
        }
    }

    result = collector._merge_go_snapshot(
        {
            "interfaces": go_interfaces,
            "rates": {},
            "connectionSummary": {"total": 1800, "wan": 1200, "lan": 600},
            "conntrackSummary": {"available": False, "source": "capture", "total": 0, "wan": 0, "lan": 0},
        },
        "physical",
    )

    assert result["connectionSummary"]["source"] == "socket"
    assert result["connectionSummary"]["total"] == 2
    assert result["connectionSummary"]["wan"] == 1
    assert result["connectionSummary"]["lan"] == 1


def test_go_processes_empty_list_falls_back_to_local_rank():
    collector = make_collector()
    collector.go_collector_available = True
    bucket = int(main.now())
    collector.process_recent = {bucket: {"qbittorrent": main.Counter(rx_bytes=100, tx_bytes=200)}}

    with patch.object(main, "go_processes", return_value={"period": "30s", "processes": []}):
        result = collector.process_rank("30s", 10)

    assert result["source"] == "memory"
    assert len(result["processes"]) == 1
    assert result["processes"][0]["name"] == "qbittorrent"


def test_go_connections_empty_list_falls_back_to_local_connections():
    collector = make_collector()
    collector.go_collector_available = True
    collector.conn_totals = {
        "eth0|wan|tcp|192.168.3.56:50000|8.8.8.8:443|1|qbittorrent|": main.Counter(
            rx_bytes=100,
            tx_bytes=200,
        )
    }
    local_interfaces = {
        "eth0": {
            "detail": {
                "name": "eth0",
                "isUp": True,
                "captured": True,
                "virtual": False,
                "defaultRoute": True,
            },
            "scopes": {},
            "system": {
                "rxBytes": 1234,
                "txBytes": 5678,
                "rxPackets": 10,
                "txPackets": 20,
            },
        }
    }

    with patch.object(main, "go_connections", return_value={"connections": [], "summary": {"total": 0}, "pagination": {"total": 0}}):
        with patch.object(collector, "snapshot_interfaces", return_value=local_interfaces):
            result = collector.connection_detail(mode="capture", interface_view="physical")

    assert result["source"] == "capture"
    assert len(result["connections"]) == 1
    assert result["summary"]["total"] == 1


def test_history_persist_prefers_go_snapshot_when_available_and_ignores_empty_local_snapshot():
    collector = make_collector()
    collector.go_collector_available = True
    collector.last_persist_totals = None

    go_interfaces = {
        "eth1": {
            "detail": {
                "name": "eth1",
                "isUp": True,
                "captured": True,
                "virtual": False,
                "defaultRoute": True,
            },
            "scopes": {
                "wan": {
                    "rxBytes": 1000,
                    "txBytes": 2000,
                    "rxPackets": 10,
                    "txPackets": 20,
                    "totalBytes": 3000,
                    "firstSeen": 1,
                    "lastSeen": 2,
                    "durationSeconds": 1,
                }
            },
            "system": {
                "rxBytes": 4000,
                "txBytes": 5000,
                "rxPackets": 30,
                "txPackets": 40,
            },
        }
    }

    with patch.object(main, "go_snapshot", return_value={"interfaces": go_interfaces}):
        persist_interfaces = collector.history_persist_interfaces({})

    assert persist_interfaces == go_interfaces

    collector.persist_minute(persist_interfaces, 12345)
    assert collector.last_persist_totals["eth1"]["wan"]["rxBytes"] == 1000

    with patch.object(main, "go_snapshot", return_value={"interfaces": {}}):
        empty_result = collector.history_persist_interfaces({})

    assert empty_result == {}
    collector.persist_minute(empty_result, 12346)
    assert collector.last_persist_totals["eth1"]["wan"]["rxBytes"] == 1000


def test_container_protection_and_rule_fires_only_after_duration():
    collector = make_collector()
    collector.container_protection_rules = [{
        "id": "rule-1",
        "name": "qb cpu",
        "containerId": "abc123",
        "containerName": "qb",
        "enabled": True,
        "channelIds": ["webhook"],
        "logic": "and",
        "action": "restart",
        "maxActions": 3,
        "conditions": [
            {"metric": "cpuPercent", "operator": "gte", "threshold": 80, "durationSeconds": 10},
            {"metric": "memoryPercent", "operator": "gte", "threshold": 70, "durationSeconds": 10},
        ],
    }]
    collector.docker_container_stats = lambda container_id, refresh=False: {
        "ok": True,
        "stats": {"cpuPercent": 85, "memoryPercent": 75, "memoryUsedBytes": 1536, "memoryLimitBytes": 2048},
    }
    collector.docker_container_action = lambda container_id, action: {"ok": True, "action": action}
    alerts = []
    collector.record_alert = lambda alert_type, severity, message, value, threshold, rule=None: alerts.append((alert_type, severity, message, value, threshold, rule))

    assert collector.evaluate_container_protection(100.0) == []
    assert alerts == []
    collector.evaluate_container_protection(105.0)

    assert alerts == []
    collector.evaluate_container_protection(111.0)

    assert len(alerts) == 1
    assert alerts[0][0] == "container_protection"


def test_container_protection_or_fires_when_any_metric_matches():
    collector = make_collector()
    collector.container_protection_rules = [{
        "id": "rule-2",
        "name": "qb io",
        "enabled": True,
        "channelIds": ["webhook"],
        "containerId": "abc123",
        "containerName": "qb",
        "logic": "or",
        "action": "restart",
        "maxActions": 3,
        "conditions": [
            {"metric": "cpuPercent", "operator": "gte", "threshold": 90, "durationSeconds": 0},
            {"metric": "blkReadBps", "operator": "gte", "threshold": 100, "durationSeconds": 0},
        ],
    }]
    collector.docker_container_stats = lambda container_id, refresh=False: {"ok": True, "stats": {"cpuPercent": 10, "blkReadBps": 200}}
    collector.docker_container_action = lambda container_id, action: {"ok": True, "action": action}
    calls = []
    collector.record_alert = lambda alert_type, severity, message, value, threshold, rule=None: calls.append(rule)

    collector.evaluate_container_protection(200.0)

    assert len(calls) == 1
    assert calls[0]["logic"] == "or"


def test_container_protection_max_actions_forces_stop():
    collector = make_collector()
    collector.container_protection_rules = [{
        "id": "rule-3",
        "name": "qb runaway",
        "enabled": True,
        "channelIds": ["webhook"],
        "containerId": "abc123",
        "containerName": "qb",
        "action": "restart",
        "maxActions": 2,
        "logic": "or",
        "conditions": [
            {"metric": "cpuPercent", "operator": "gte", "threshold": 90, "durationSeconds": 0},
        ],
    }]
    actions = []
    collector.docker_container_stats = lambda container_id, refresh=False: {"ok": True, "stats": {"cpuPercent": 95}}
    collector.docker_container_action = lambda container_id, action: actions.append(action) or {"ok": True, "action": action}
    collector.record_alert = lambda *args, **kwargs: None

    collector.evaluate_container_protection(10.0)
    collector.evaluate_container_protection(11.0)
    collector.evaluate_container_protection(12.0)

    assert actions == ["restart", "restart", "stop"]
    assert collector.container_protection_states["rule-3"]["lastAction"] == "stop"


def test_container_protection_resolves_recreated_container_by_compose_identity():
    collector = make_collector()
    collector.container_rows = [{
        "id": "newcontainer",
        "name": "qbittorrent",
        "composeProject": "media",
        "composeService": "qbittorrent",
    }]
    collector.container_rows_by_id = {
        "newcontainer": collector.container_rows[0],
        "qbittorrent": collector.container_rows[0],
    }
    collector.container_protection_rules = [{
        "id": "rule-4",
        "name": "qb recreated",
        "enabled": True,
        "channelIds": ["webhook"],
        "containerId": "oldcontain",
        "containerName": "qbittorrent",
        "composeProject": "media",
        "composeService": "qbittorrent",
        "action": "restart",
        "maxActions": 3,
        "logic": "or",
        "conditions": [
            {"metric": "cpuPercent", "operator": "gte", "threshold": 90, "durationSeconds": 0},
        ],
    }]
    seen = []
    collector.refresh_container_ports = lambda force=False: None
    collector.docker_container_stats = lambda container_id, refresh=False: {"ok": True, "stats": {"cpuPercent": 95}}
    collector.docker_container_action = lambda container_id, action: seen.append((container_id, action)) or {"ok": True, "action": action}
    collector.record_alert = lambda *args, **kwargs: None

    collector.evaluate_container_protection(300.0)

    assert seen == [("newcontainer", "restart")]
    assert collector.container_protection_rules[0]["containerId"] == "newcontainer"
    assert collector.container_protection_states["rule-4"]["containerId"] == "newcontainer"


def test_discover_containers_exposes_compose_identity_and_matches_rule():
    labels = {}
    containers = [{
        "Id": "abc1234567890",
        "Names": ["/qbittorrent"],
        "Image": "linuxserver/qbittorrent:latest",
        "State": "running",
        "Status": "Up 1 hour",
        "Created": 100,
        "HostConfig": {"NetworkMode": "bridge"},
        "Labels": {
            "com.docker.compose.project": "media",
            "com.docker.compose.service": "qbittorrent",
        },
        "Ports": [{"PrivatePort": 8080, "PublicPort": 18080, "Type": "tcp"}],
    }]
    rules = [{
        "id": "rule-5",
        "enabled": True,
        "containerId": "oldid",
        "containerName": "",
        "composeProject": "media",
        "composeService": "qbittorrent",
    }]

    with patch.object(main, "ENABLE_DOCKER_DISCOVERY", True), patch.object(main, "docker_api_get", return_value=containers):
        _ports, rows = main.discover_containers(labels, protection_rules=rules, protection_states={"rule-5": {"active": True}})

    assert rows[0]["composeProject"] == "media"
    assert rows[0]["composeService"] == "qbittorrent"
    assert rows[0]["protection"]["enabled"] is True
    assert rows[0]["protection"]["state"]["active"] is True


def test_docker_container_action_restart_and_stop():
    collector = make_collector()
    with patch.object(main, "docker_api_request", return_value={"ok": True, "status": 204, "json": None, "body": "", "detail": ""}) as request:
        assert collector.docker_container_action("abc123", "restart")["ok"] is True
        assert request.call_args.args[0] == "POST"
        assert "/containers/abc123/restart" in request.call_args.args[1]

    with patch.object(main, "docker_api_request", return_value={"ok": True, "status": 204, "json": None, "body": "", "detail": ""}) as request:
        assert collector.docker_container_action("abc123", "stop")["ok"] is True
        assert "/containers/abc123/stop" in request.call_args.args[1]


if __name__ == "__main__":
    test_go_snapshot_empty_interfaces_falls_back_to_local_interfaces()
    test_go_snapshot_prefers_conntrack_summary_for_router_like_connection_counts()
    test_go_snapshot_uses_socket_summary_when_go_conntrack_is_unavailable()
    test_go_processes_empty_list_falls_back_to_local_rank()
    test_go_connections_empty_list_falls_back_to_local_connections()
    test_history_persist_prefers_go_snapshot_when_available_and_ignores_empty_local_snapshot()
    print("go snapshot merge tests passed")
