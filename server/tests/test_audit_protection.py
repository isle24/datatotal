import unittest
from unittest.mock import Mock

import server.main as main
from server.tests.test_ai import ConfigurationSettingsDB


class ProtectionTests(unittest.TestCase):
    def make_collector(self, action="restart", duration=0, db=None):
        c = main.TrafficCollector()
        c.db = db or ConfigurationSettingsDB()
        c.container_protection_rules = [{
            "id": "r", "containerId": "demo", "enabled": True, "logic": "and",
            "action": action, "maxActions": 2, "cooldownSeconds": 0,
            "conditions": [{"metric": "cpuPercent", "threshold": 80, "durationSeconds": duration}],
        }]
        c.resolve_container_protection_target = lambda rule: {"id": "demo", "name": "demo"}
        c.docker_container_stats = Mock(return_value={"ok": True, "stats": {"cpuPercent": 95}})
        c.docker_container_action = Mock(return_value={"ok": True})
        c.record_alert = Mock()
        return c

    def test_stop_waits_for_full_duration(self):
        c = self.make_collector("stop", 300)
        c.evaluate_container_protection(100)
        c.docker_container_action.assert_not_called()
        c.evaluate_container_protection(400)
        c.docker_container_action.assert_called_once_with("demo", "stop")

    def test_recovery_does_not_clear_restart_limit(self):
        c = self.make_collector()
        for timestamp, cpu in enumerate([95, 0, 95, 0, 95], 100):
            c.docker_container_stats.return_value = {"ok": True, "stats": {"cpuPercent": cpu}}
            c.evaluate_container_protection(timestamp)
        self.assertEqual([call.args[1] for call in c.docker_container_action.call_args_list], ["restart", "restart", "stop"])

    def test_stop_lock_and_counts_survive_application_restart(self):
        c = self.make_collector()
        for timestamp in (100, 101, 102):
            c.evaluate_container_protection(timestamp)
        restored = self.make_collector(db=c.db)
        restored.load_saved_settings()
        restored.evaluate_container_protection(300)
        restored.docker_container_action.assert_not_called()
        self.assertTrue(restored.container_protection_states["r"]["locked"])

    def test_each_restart_requires_a_new_duration_window(self):
        c = self.make_collector(duration=10)
        for timestamp in (100, 110, 111):
            c.evaluate_container_protection(timestamp)
        self.assertEqual(c.docker_container_action.call_count, 1)

    def test_failed_stop_has_bounded_retries_and_records_failure(self):
        c = self.make_collector("stop")
        c.docker_container_action.return_value = {"ok": False, "detail": "Docker unavailable"}
        for timestamp in range(100, 700, 60):
            c.evaluate_container_protection(timestamp)
        self.assertEqual(c.docker_container_action.call_count, 3)
        self.assertIn("failed", c.container_protection_states["r"]["reason"])

    def test_disk_rates_are_computed_from_counter_deltas(self):
        c = self.make_collector()
        state = {}
        first = c.normalize_container_stats({"blkReadBytes": 1000})
        second = c.normalize_container_stats({"blkReadBytes": 1600})
        c.container_protection_metric_value(state, first, "blkReadBps", 100)
        self.assertEqual(c.container_protection_metric_value(state, second, "blkReadBps", 102), 300)

    def test_cannot_act_without_durable_state(self):
        c = self.make_collector()
        c.db.set_setting = Mock(return_value={"ok": False})
        c.evaluate_container_protection(100)
        c.docker_container_action.assert_not_called()

    def test_cached_disk_sample_does_not_interrupt_duration(self):
        c = self.make_collector("stop", 10)
        c.container_protection_rules[0]["conditions"][0].update(metric="blkReadBps", threshold=80)
        for timestamp, sampled_at, total in ((100, 100, 1000), (105, 105, 1500), (107, 105, 1500), (110, 110, 2000), (115, 115, 2500)):
            c.docker_container_stats.return_value = {"ok": True, "cachedAt": sampled_at, "stats": {"blkReadBytes": total}}
            c.evaluate_container_protection(timestamp)
        c.docker_container_action.assert_called_once_with("demo", "stop")

    def test_stale_sample_cannot_trigger_action(self):
        c = self.make_collector("stop", 10)
        c.docker_container_stats.return_value = {"ok": True, "cachedAt": 100, "stats": {"cpuPercent": 95}}
        for timestamp in (100, 110, 200):
            c.evaluate_container_protection(timestamp)
        c.docker_container_action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
