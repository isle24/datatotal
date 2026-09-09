import copy
import tempfile
import unittest
from pathlib import Path

import server.main as main
from server.services.config_assistant import validate_configuration_changes
from server.tests.test_ai import make_configuration_collector


class SettingsSafetyTests(unittest.TestCase):
    def test_ai_rename_preserves_rules_outside_snapshot(self):
        c = make_configuration_collector()
        c.monitor_rules = [main.sanitize_monitor_rule(main.MonitorRule(id=f"r{i}", name=f"Rule {i}", metric="wan_tx_bps", threshold=100)) for i in range(101)]
        current = c._ai_configuration_snapshot()
        row = copy.deepcopy(current["monitor"]["rules"][0])
        row["name"] = "Renamed"
        changes = validate_configuration_changes([{"path": "monitor.rules", "value": [row]}], current)
        c._apply_ai_configuration_changes(changes, current)
        self.assertEqual(len(c.monitor_rules), 101)
        self.assertEqual(c.monitor_rules[0]["name"], "Renamed")

    def test_ai_removal_is_explicit_and_only_removes_named_ids(self):
        c = make_configuration_collector()
        c.monitor_rules = [main.sanitize_monitor_rule(main.MonitorRule(id=name, name=name, metric="wan_tx_bps")) for name in ("a", "b")]
        current = c._ai_configuration_snapshot()
        changes = validate_configuration_changes([{"path": "monitor.rules", "value": [], "removeIds": ["a"]}], current)
        self.assertEqual(changes[0]["removeIds"], ["a"])
        c._apply_ai_configuration_changes(changes, current)
        self.assertEqual([row["id"] for row in c.monitor_rules], ["b"])

    def test_ai_docker_update_preserves_unseen_containers(self):
        c = make_configuration_collector()
        c.docker_overrides = {"containers": {f"demo{i}": {"key": f"demo{i}", "containerName": f"demo{i}", "ports": []} for i in range(501)}}
        current = c._ai_configuration_snapshot()
        key = next(iter(current["docker"]["containers"]))
        row = copy.deepcopy(current["docker"]["containers"][key])
        row["iconKey"] = "redis"
        changes = validate_configuration_changes([{"path": "docker.containers", "value": {key: row}}], current)
        c._apply_ai_configuration_changes(changes, current)
        self.assertEqual(len(c.docker_overrides["containers"]), 501)
        self.assertEqual(c.docker_overrides["containers"][key]["iconKey"], "redis")

    def test_history_cleanup_keeps_configuration_labels_and_alerts(self):
        with tempfile.TemporaryDirectory() as directory:
            db = main.TrafficDB(Path(directory) / "traffic.db")
            db.start()
            db.set_setting("notification_channels", {"channels": [{"id": "demo"}]})
            db.set_label("demo", "A label")
            db.add_alert({"id": "a", "timestamp": 60, "type": "test", "severity": "warning", "message": "reason", "value": 100, "threshold": 50})
            db.add_alert_evidence("a", {"reason": "reason", "topProcesses": [{"name": "demo"}]})
            db.conn.execute("INSERT INTO minute_stats (bucket, iface, scope, tx_bytes) VALUES (60, 'eth0', 'wan', 100)")
            db.conn.execute("INSERT INTO process_minute_stats (bucket, process_key, tx_bytes) VALUES (60, 'demo', 100)")
            db.conn.commit()
            db.clear_traffic_history()
            self.assertEqual(db.conn.execute("SELECT count(*) FROM minute_stats").fetchone()[0], 0)
            self.assertEqual(db.conn.execute("SELECT count(*) FROM process_minute_stats").fetchone()[0], 0)
            self.assertEqual(db.get_setting("notification_channels"), {"channels": [{"id": "demo"}]})
            self.assertEqual(db.get_labels(), {"demo": "A label"})
            self.assertEqual(db.conn.execute("SELECT count(*) FROM alerts").fetchone()[0], 1)
            self.assertEqual(db.conn.execute("SELECT count(*) FROM alert_evidence").fetchone()[0], 1)
            db.conn.close()


if __name__ == "__main__":
    unittest.main()
