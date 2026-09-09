import copy
import unittest
from unittest.mock import Mock, patch

import server.main as main


class GoIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.c = main.TrafficCollector()
        self.c.go_collector_available = True
        self.c.db = Mock()

    def test_rate_sample_uses_go_rates_for_alerts(self):
        data = {"interfaces": {"eth0": {"scopes": {}}}, "rates": {"eth0": {"scopes": {"wan": {"txBps": 10000000}}}}, "stage": {"active": True, "interfaces": {"eth0": {"wan": {"txBytes": 200}}}}}
        with patch.object(main, "go_snapshot", return_value=data):
            sample = self.c.collect_traffic_sample(None, 100)
        self.assertEqual(sample["rates"], data["rates"])
        self.assertEqual(self.c.last_go_sample["stage"], data["stage"])
        self.c.monitor_rules = [main.sanitize_monitor_rule(main.MonitorRule(id="upload", name="upload", metric="wan_tx_bps", threshold=100, durationSeconds=0))]
        self.c.record_alert = Mock()
        self.c.evaluate_alerts(sample["rates"], 100)
        self.c.record_alert.assert_called_once()
        self.assertEqual(self.c.record_alert.call_args.args[3], 10000000)

    def test_connection_alert_counts_share_go_overview_source(self):
        self.c.last_go_sample = {"connectionSummary": {"total": 500, "wan": 300, "lan": 200}, "conntrackSummary": {"available": True, "total": 25, "wan": 5, "lan": 20}}
        self.assertEqual(self.c.connection_counts()["wan"], 5)

    def test_unavailable_go_does_not_become_zero_traffic(self):
        with patch.object(main, "go_snapshot", return_value=None):
            self.assertIsNone(self.c.collect_traffic_sample(None, 100))
            with self.assertRaises(main.HTTPException) as error:
                self.c.api_overview()
            self.assertEqual(error.exception.status_code, 503)

    def test_process_totals_persist_all_deltas_and_handle_counter_reset(self):
        data = {"instanceId": "boot1", "totals": {"1|demo|": {"txBytes": 100, "firstSeen": 10}}}
        with patch.object(main, "go_process_totals", return_value=copy.deepcopy(data), create=True):
            self.c.persist_process_minute(100)
        data["totals"]["1|demo|"]["txBytes"] = 300
        with patch.object(main, "go_process_totals", return_value=copy.deepcopy(data), create=True):
            self.c.persist_process_minute(160)
        self.assertEqual(self.c.db.add_process_minute.call_args.args[1][0]["txBytes"], 200)
        data["instanceId"] = "boot2"
        data["totals"]["1|demo|"].update(txBytes=20, firstSeen=20)
        with patch.object(main, "go_process_totals", return_value=data, create=True):
            self.c.persist_process_minute(220)
        self.assertEqual(self.c.db.add_process_minute.call_args.args[1][0]["txBytes"], 20)

    def test_go_alert_evidence_reads_go_connections(self):
        row = {"iface": "eth0", "scope": "wan", "txBytes": 100, "process": {"name": "demo", "pid": 1}}
        with patch.object(main, "go_connections", return_value={"connections": [row]}):
            self.assertEqual(self.c.wan_connection_evidence()["topProcesses"][0]["name"], "demo")

    def test_empty_go_results_are_valid_and_failures_are_explicit(self):
        for method, upstream, empty in ((self.c.process_rank, "go_processes", {"processes": []}), (self.c.connection_detail, "go_connections", {"connections": []})):
            with patch.object(main, upstream, return_value=empty):
                self.assertEqual(method(), empty)
            with patch.object(main, upstream, return_value=None):
                with self.assertRaises(main.HTTPException) as error:
                    method()
                self.assertEqual(error.exception.status_code, 503)

    def test_interface_counter_reset_preserves_new_bytes(self):
        self.c.persist_minute({"eth0": {"scopes": {"wan": {"txBytes": 1000}}}}, 100)
        self.c.persist_minute({"eth0": {"scopes": {"wan": {"txBytes": 50}}}}, 160)
        self.assertEqual(self.c.db.add_minute.call_args.args[1][0]["txBytes"], 50)

    def test_new_collector_instance_counts_all_new_interface_bytes(self):
        self.c.last_go_sample = {"instanceId": "old"}
        self.c.persist_minute({"eth0": {"scopes": {"wan": {"txBytes": 1000}}}}, 100)
        self.c.last_go_sample = {"instanceId": "new"}
        self.c.persist_minute({"eth0": {"scopes": {"wan": {"txBytes": 1500}}}}, 160)
        self.assertEqual(self.c.db.add_minute.call_args.args[1][0]["txBytes"], 1500)


if __name__ == "__main__":
    unittest.main()
