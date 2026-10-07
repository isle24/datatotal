import unittest
from unittest.mock import Mock

import server.main as main
from server.tests import test_audit_protection as existing


class UnlimitedRestartTests(unittest.TestCase):
    def test_restart_never_turns_into_stop_or_count_lock(self):
        c = existing.ProtectionTests().make_collector()
        for timestamp in range(100, 110):
            c.evaluate_container_protection(timestamp)
        self.assertEqual([call.args[1] for call in c.docker_container_action.call_args_list], ["restart"] * 10)
        self.assertEqual(c.container_protection_states["r"]["count"], 10)
        self.assertFalse(c.container_protection_states["r"]["locked"])

    def test_old_limit_stop_lock_is_released_on_load_without_erasing_history(self):
        c = existing.ProtectionTests().make_collector()
        c.db.set_setting("container_protection_rules", {"rules": c.container_protection_rules})
        c.db.set_setting("container_protection_states", {"r": {"count": 3, "locked": True, "pending": False,
            "lastAction": "stop", "containerId": "demo", "reason": "stop completed: CPU threshold"}})
        c.load_saved_settings()
        state = c.container_protection_states["r"]
        self.assertFalse(state["locked"])
        self.assertEqual(state["count"], 3)
        c.evaluate_container_protection(100)
        c.docker_container_action.assert_called_once_with("demo", "restart")
        self.assertEqual(state["count"], 4)

    def test_nested_legacy_limit_locks_are_released_for_restart_rules(self):
        c = existing.ProtectionTests().make_collector()
        c.db.set_setting("container_protection_rules", {"rules": c.container_protection_rules})
        c.db.set_setting("container_protection_states", {"r": {"containers": {"name:alpha": {
            "count": 3, "locked": True, "lastAction": "stop", "pending": False}}}})
        c.load_saved_settings()
        self.assertFalse(c.container_protection_states["r"]["containers"]["name:alpha"]["locked"])

    def test_uncertain_pending_action_stays_locked(self):
        c = existing.ProtectionTests().make_collector()
        c.db.set_setting("container_protection_rules", {"rules": c.container_protection_rules})
        c.db.set_setting("container_protection_states", {"r": {"count": 3, "locked": True,
            "pending": True, "lastAction": "stop"}})
        c.load_saved_settings()
        self.assertTrue(c.container_protection_states["r"]["locked"])

    def test_explicit_stop_rule_keeps_its_completed_lock(self):
        c = existing.ProtectionTests().make_collector("stop")
        c.db.set_setting("container_protection_rules", {"rules": c.container_protection_rules})
        c.db.set_setting("container_protection_states", {"r": {"count": 0, "locked": True,
            "pending": False, "lastAction": "stop"}})
        c.load_saved_settings()
        self.assertTrue(c.container_protection_states["r"]["locked"])

    def test_restart_still_obeys_cooldown(self):
        c = existing.ProtectionTests().make_collector()
        c.container_protection_rules[0]["cooldownSeconds"] = 60
        c.evaluate_container_protection(100)
        c.evaluate_container_protection(130)
        c.evaluate_container_protection(161)
        self.assertEqual(c.docker_container_action.call_count, 2)


if __name__ == "__main__":
    unittest.main()
