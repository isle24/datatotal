import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

import server.main as main


class NotificationSelectionTests(unittest.TestCase):
    def make_collector(self):
        c = main.TrafficCollector()
        c.notification_channels = [{"id": "a", "enabled": True}, {"id": "b", "enabled": True}]
        c.save_notification_result = Mock()
        return c

    def test_no_notification_policy_never_dispatches_enabled_channels(self):
        c = self.make_collector()
        with patch.object(main.threading, "Thread") as thread:
            c.notify_alert({"id": "alert", "channelMode": "none", "channelIds": []})
        thread.assert_not_called()
        self.assertTrue(c.save_notification_result.call_args.args[1].get("skipped"))

    def test_explicit_empty_selection_never_becomes_all_channels(self):
        c = self.make_collector()
        with patch.object(main.threading, "Thread") as thread:
            c.notify_alert({"id": "alert", "channelMode": "selected", "channelIds": []})
        thread.assert_not_called()

    def test_legacy_rules_keep_existing_all_or_selected_meaning(self):
        for ids, expected in (([], "all"), (["b"], "selected")):
            rule = main.sanitize_monitor_rule(main.MonitorRule(id="r", name="r", metric="wan_tx_bps", channelIds=ids))
            self.assertEqual(rule["channelMode"], expected)

    def test_rule_loader_preserves_explicit_no_notification(self):
        rules, skipped = main.load_saved_monitor_rules({"rules": [{"id": "r", "name": "r", "metric": "wan_tx_bps", "channelMode": "none"}]})
        self.assertEqual(skipped, 0)
        self.assertEqual(rules[0]["channelMode"], "none")

    def test_all_enabled_channels_are_delivered_without_a_hidden_twenty_channel_cutoff(self):
        c = self.make_collector()
        channels = [{"id": f"c{i}", "enabled": True} for i in range(21)]
        with patch.object(main, "dispatch_notification_alert", return_value={"ok": True}):
            c.deliver_alert_notifications({"id": "a"}, channels)
        self.assertEqual(c.save_notification_result.call_count, 21)

    def test_saved_selected_channels_are_not_silently_truncated_on_restart(self):
        ids = [f"c{i}" for i in range(51)]
        rules, skipped = main.load_saved_monitor_rules({"rules": [{"id": "r", "name": "r", "metric": "wan_tx_bps", "channelMode": "selected", "channelIds": ids}]})
        self.assertEqual(skipped, 0)
        self.assertEqual(rules[0]["channelIds"], ids)

    def test_skipped_notification_receipt_survives_database_read(self):
        with tempfile.TemporaryDirectory() as directory:
            db = main.TrafficDB(Path(directory) / "qa.db")
            db.start()
            db.add_alert_evidence("a", {})
            db.add_alert_notification_result("a", {"channelId": "", "ok": True, "skipped": True})
            row = db.conn.execute("SELECT notifications FROM alert_evidence WHERE alert_id='a'").fetchone()
            self.assertTrue(json.loads(row[0])[0].get("skipped"))
            db.conn.close()

    def test_every_delivery_receipt_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            db = main.TrafficDB(Path(directory) / "qa.db")
            db.start()
            db.add_alert_evidence("a", {})
            for i in range(21):
                db.add_alert_notification_result("a", {"channelId": f"c{i}", "ok": True})
            row = db.conn.execute("SELECT notifications FROM alert_evidence WHERE alert_id='a'").fetchone()
            self.assertEqual(len(json.loads(row[0])), 21)
            db.conn.close()

    def test_manual_container_refresh_bypasses_list_cache(self):
        c = main.TrafficCollector()
        c.refresh_container_ports = Mock()
        c.docker_containers(refresh=True)
        c.refresh_container_ports.assert_called_once_with(force=True)


if __name__ == "__main__":
    unittest.main()
