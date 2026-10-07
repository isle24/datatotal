import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import server.main as main


class DailyUploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = main.TrafficDB(Path(self.directory.name) / "traffic.db")
        self.db.start()
        self.c = main.TrafficCollector()
        self.c.db = self.db
        self.c.record_alert = Mock()
        self.day = datetime(2026, 10, 7)
        self.timestamp = self.day.replace(hour=12).timestamp()
        self.c.monitor_rules = [main.sanitize_monitor_rule(main.MonitorRule(
            id="upload", name="upload", metric="daily_wan_tx_bytes", threshold=100))]

    def tearDown(self):
        self.db.conn.close()
        self.directory.cleanup()

    def add_traffic(self, day, amount, scope="wan"):
        self.db.add_minute(int(day.replace(hour=10).timestamp()), [{"iface": "eth0", "scope": scope,
                            "txBytes": amount, "rxBytes": 0, "rxPackets": 0, "txPackets": 0}])

    def test_only_today_wan_counts_toward_daily_limit(self):
        self.add_traffic(self.day - timedelta(days=1), 10000)
        self.add_traffic(self.day, 99)
        self.add_traffic(self.day, 10000, "lan")
        self.c.evaluate_daily_alert(self.timestamp)
        self.c.record_alert.assert_not_called()
        self.add_traffic(self.day, 2)
        self.c.evaluate_daily_alert(self.timestamp + 60)
        self.assertEqual(self.c.record_alert.call_args.args[3], 101)

    def test_daily_rules_trigger_independently(self):
        self.c.monitor_rules.append({**self.c.monitor_rules[0], "id": "higher", "threshold": 200})
        self.add_traffic(self.day, 150)
        self.c.evaluate_daily_alert(self.timestamp)
        self.add_traffic(self.day, 100)
        self.c.evaluate_daily_alert(self.timestamp + 60)
        self.assertEqual([call.args[0] for call in self.c.record_alert.call_args_list], ["upload", "higher"])

    def test_new_day_resets_each_rule_even_if_first_sample_exceeds_limit(self):
        self.add_traffic(self.day, 150)
        self.c.evaluate_daily_alert(self.timestamp)
        self.add_traffic(self.day + timedelta(days=1), 150)
        self.c.evaluate_daily_alert(self.timestamp + 86400)
        self.assertEqual(self.c.record_alert.call_count, 2)

    def test_today_notification_marker_survives_service_restart(self):
        self.db.set_setting("monitor_rules", {"rules": self.c.monitor_rules})
        self.add_traffic(self.day, 150)
        self.c.evaluate_daily_alert(self.timestamp)
        restored = main.TrafficCollector()
        restored.db = self.db
        restored.record_alert = Mock()
        restored.load_saved_settings()
        restored.evaluate_daily_alert(self.timestamp + 60)
        restored.record_alert.assert_not_called()

    def test_metric_canonicalizes_daily_window(self):
        self.assertEqual(self.c.monitor_rules[0]["window"], "day")


if __name__ == "__main__":
    unittest.main()
