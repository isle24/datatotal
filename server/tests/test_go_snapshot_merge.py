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
    collector.conntrack_summary = {"available": False, "source": "capture", "total": 0, "wan": 0, "lan": 0, "rawTotal": 0, "mode": "active"}
    collector.socket_map = {}
    collector.conn_totals = {}
    collector.stage_started_at = None
    collector.stage_totals = defaultdict(lambda: defaultdict(main.Counter))
    collector.calibrated_stage_totals = defaultdict(lambda: defaultdict(main.Counter))
    collector.alerts = main.deque(maxlen=20)
    collector.alert_settings = main.AlertSettings()
    collector.container_status = {"enabled": False, "count": 0, "lastRefresh": None}
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


if __name__ == "__main__":
    test_go_snapshot_empty_interfaces_falls_back_to_local_interfaces()
    test_go_snapshot_prefers_conntrack_summary_for_router_like_connection_counts()
    test_go_snapshot_uses_socket_summary_when_go_conntrack_is_unavailable()
    test_go_processes_empty_list_falls_back_to_local_rank()
    test_go_connections_empty_list_falls_back_to_local_connections()
    print("go snapshot merge tests passed")
