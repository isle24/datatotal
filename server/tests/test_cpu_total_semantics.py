"""Container CPU percentages must be whole-machine totals, not per-core values.

Docker's historical convention reports 100% for one fully busy core, so an
18-core host can show up to 1800% for a container. The container-protection
thresholds are meant as percent of the WHOLE machine (100% = every core busy):
a Docker-style 68.44% on 18 cores is only 3.80% of the machine and must not
trip a rule configured with threshold 5.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import server.main as main
from server.tests import test_audit_protection as existing

CPU_BASE = 100_000_000
SYSTEM_BASE = 1_000_000_000


def raw_stats(cpu_delta, system_delta, online_cpus, percpu_cores=None):
    """A Docker /stats?stream=false payload with the requested CPU deltas."""
    cpu_usage = {"total_usage": CPU_BASE + cpu_delta}
    if percpu_cores:
        cpu_usage["percpu_usage"] = [cpu_delta] * percpu_cores
    return {
        "cpu_stats": {
            "online_cpus": online_cpus,
            "system_cpu_usage": SYSTEM_BASE + system_delta,
            "cpu_usage": cpu_usage,
        },
        "precpu_stats": {
            "system_cpu_usage": SYSTEM_BASE,
            "cpu_usage": {"total_usage": CPU_BASE},
        },
        "memory_stats": {
            "usage": 300_000_000,
            "limit": 8_000_000_000,
            "stats": {"inactive_file": 50_000_000},
        },
        "networks": {"eth0": {"rx_bytes": 1234, "tx_bytes": 5678}},
        "blkio_stats": {
            "io_service_bytes_recursive": [
                {"op": "read", "value": 4096},
                {"op": "write", "value": 8192},
            ]
        },
    }


# Deliberately the live NAS shape: 18 logical cores; 3422/90000 busy CPU time
# equals Docker's 68.44% single-core reading and 3.80% of the whole machine.
RAW_18_CORES_3_80 = raw_stats(cpu_delta=3422, system_delta=90000, online_cpus=18)
RAW_18_CORES_6_00 = raw_stats(cpu_delta=5400, system_delta=90000, online_cpus=18)


def module_stats(raw):
    with patch.object(main, "docker_api_get", return_value=raw):
        return main.docker_container_stats("flaresolverr")


def make_protection_collector(threshold=5):
    """A real collector whose protection evaluation reads Docker through the API."""
    collector = existing.ProtectionTests().make_collector()
    # Drop the mocked stats reader so evaluation flows through the real pipeline:
    # collector.docker_container_stats -> main.docker_container_stats -> docker_api_get.
    del collector.docker_container_stats
    row = {"id": "flaresolverr", "name": "flaresolverr", "state": "running"}
    collector.refresh_container_ports = Mock()
    collector.container_rows = [row]
    collector.container_rows_by_id = {"flaresolverr": row}
    collector.container_protection_rules = [{
        "id": "r",
        "containerId": "flaresolverr",
        "containerName": "flaresolverr",
        "enabled": True,
        "logic": "and",
        "action": "restart",
        "maxActions": 2,
        "cooldownSeconds": 0,
        "conditions": [{
            "metric": "cpuPercent",
            "operator": "gte",
            "threshold": threshold,
            "durationSeconds": 0,
        }],
    }]
    collector.resolve_container_protection_target = lambda rule: {
        "id": "flaresolverr", "name": "flaresolverr"}
    return collector


# --- (a) formula math -------------------------------------------------------


def test_cpu_percent_is_whole_machine_total():
    # 100 CPU ticks of usage over 400 ticks of wall time on 4 cores: one core
    # fully busy = 100% of the Docker scale but 25% of the whole machine.
    stats = module_stats(raw_stats(cpu_delta=100, system_delta=400, online_cpus=4))
    assert stats["cpuPercent"] == 25.0
    assert stats["cpuPercentSingleCore"] == 100.0
    assert stats["cpuCount"] == 4


def test_cpu_count_falls_back_to_percpu_usage():
    stats = module_stats(raw_stats(cpu_delta=80, system_delta=800, online_cpus=0, percpu_cores=8))
    assert stats["cpuCount"] == 8
    assert stats["cpuPercent"] == 10.0
    assert stats["cpuPercentSingleCore"] == 80.0


def test_zero_deltas_report_zero_on_both_scales():
    stats = module_stats(raw_stats(cpu_delta=0, system_delta=0, online_cpus=18))
    assert stats["cpuPercent"] == 0.0
    assert stats["cpuPercentSingleCore"] == 0.0
    assert stats["cpuCount"] == 18


def test_other_stats_fields_keep_their_previous_values():
    stats = module_stats(raw_stats(cpu_delta=100, system_delta=400, online_cpus=4))
    assert stats["memoryUsedBytes"] == 250_000_000
    assert stats["memoryUsageBytes"] == 300_000_000
    assert stats["memoryLimitBytes"] == 8_000_000_000
    assert stats["memoryPercent"] == 3.12
    assert stats["netRxBytes"] == 1234
    assert stats["netTxBytes"] == 5678
    assert stats["blkReadBytes"] == 4096
    assert stats["blkWriteBytes"] == 8192


def test_normalize_container_stats_passes_compatibility_fields_through():
    collector = main.TrafficCollector.__new__(main.TrafficCollector)
    normalized = collector.normalize_container_stats({
        "cpuPercent": 3.8,
        "cpuPercentSingleCore": 68.44,
        "cpuCount": 18,
        "memoryUsedBytes": 100,
        "memoryLimitBytes": 1000,
    })
    assert normalized["cpuPercent"] == 3.8
    assert normalized["cpuPercentSingleCore"] == 68.44
    assert normalized["cpuCount"] == 18

    without_compatibility = collector.normalize_container_stats({"cpuPercent": 5.0})
    assert "cpuPercentSingleCore" not in without_compatibility
    assert "cpuCount" not in without_compatibility


def test_docker_stats_fields_include_the_compatibility_fields():
    # These fields must be filtered from container summaries/details like the
    # other live stats fields, so the new keys belong in DOCKER_STATS_FIELDS.
    assert {"cpuPercentSingleCore", "cpuCount"} <= main.DOCKER_STATS_FIELDS


# --- (b) 18-core live fixture -----------------------------------------------


def test_18_core_docker_style_68_44_percent_is_3_80_percent_of_the_machine():
    stats = module_stats(RAW_18_CORES_3_80)
    # Previous Docker-style reading (100 = one core) preserved for compatibility.
    assert stats["cpuPercentSingleCore"] == 68.44
    # Whole-machine total compared against the protection threshold.
    assert stats["cpuPercent"] == 3.8


# --- (c) protection integration ---------------------------------------------


def test_protection_ignores_3_8_percent_of_18_cores_against_threshold_5():
    collector = make_protection_collector(threshold=5)
    with patch.object(main, "docker_api_get", return_value=RAW_18_CORES_3_80):
        actions = collector.evaluate_container_protection(100.0)
    collector.docker_container_action.assert_not_called()
    collector.record_alert.assert_not_called()
    assert actions == []
    state = collector.container_protection_states["r"]
    assert state["monitorStatus"] == "healthy"
    assert state["metricDetails"][0]["value"] == 3.8
    assert state["metricDetails"][0]["threshold"] == 5


def test_protection_stays_idle_across_samples_spaced_beyond_the_stats_cache_ttl():
    collector = make_protection_collector(threshold=5)
    clock = [1000.0]
    with patch.object(main, "now", side_effect=lambda: clock[0]), \
            patch.object(main, "docker_api_get", return_value=RAW_18_CORES_3_80) as api:
        collector.evaluate_container_protection(1000.0)
        clock[0] += 30.0  # well beyond max(10s, DOCKER_STATS_CACHE_SECONDS * 2)
        collector.evaluate_container_protection(1030.0)
    assert api.call_count == 2
    collector.docker_container_action.assert_not_called()
    state = collector.container_protection_states["r"]
    assert state["monitorStatus"] == "healthy"
    assert state["metricDetails"][0]["value"] == 3.8


def test_protection_restarts_container_at_6_percent_of_18_cores_against_threshold_5():
    collector = make_protection_collector(threshold=5)
    with patch.object(main, "docker_api_get", return_value=RAW_18_CORES_6_00):
        actions = collector.evaluate_container_protection(100.0)
    collector.docker_container_action.assert_called_once_with("flaresolverr", "restart")
    collector.record_alert.assert_called_once()
    assert actions and actions[0]["matchedMetrics"] == ["cpuPercent"]
    state = collector.container_protection_states["r"]
    assert state["monitorStatus"] == "exceeded"
    assert state["metricDetails"][0]["value"] == 6.0
