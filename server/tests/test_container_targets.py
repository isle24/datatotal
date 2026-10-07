import copy
import threading
import unittest
from unittest.mock import Mock, patch

import server.main as main
from server.services.protection_state import durable_states, restore_states
from server.services.container_targets import row_protection_state
from server.tests import test_audit_protection as existing


class ContainerTargetTests(unittest.TestCase):
    def make_collector(self, mode="selected", duration=0):
        c = existing.ProtectionTests().make_collector(duration=duration)
        c.container_protection_rules[0].update(targetMode=mode, containers=[
            {"containerId": "aaa", "containerName": "alpha"},
            {"containerId": "bbb", "containerName": "beta"},
        ])
        c.container_rows = [{"id": "aaa", "name": "alpha", "state": "running"},
                            {"id": "bbb", "name": "beta", "state": "running"}]
        c.refresh_container_ports = Mock()
        return c

    def test_cgroup_v2_cpu_uses_nested_online_cpus(self):
        raw = {"cpu_stats": {"online_cpus": 4, "system_cpu_usage": 500,
                             "cpu_usage": {"total_usage": 200}},
               "precpu_stats": {"system_cpu_usage": 100, "cpu_usage": {"total_usage": 100}}}
        with patch.object(main, "docker_api_get", return_value=raw):
            self.assertEqual(main.docker_container_stats("demo")["cpuPercent"], 100)

    def test_selected_containers_act_independently(self):
        c = self.make_collector()
        c.docker_container_stats.side_effect = lambda cid: {"ok": True, "stats": {"cpuPercent": 95 if cid == "aaa" else 10}}
        c.evaluate_container_protection(100)
        c.docker_container_action.assert_called_once_with("aaa", "restart")

    def test_all_containers_includes_new_running_targets(self):
        c = self.make_collector("all")
        c.container_rows.append({"id": "ccc", "name": "gamma", "state": "running"})
        c.container_rows.append({"id": "ddd", "name": "stopped", "state": "exited"})
        c.evaluate_container_protection(100)
        self.assertEqual({call.args[0] for call in c.docker_container_action.call_args_list}, {"aaa", "bbb", "ccc"})

    def test_multiselect_follows_recreated_container_name(self):
        c = self.make_collector()
        c.container_rows[0]["id"] = "new-alpha"
        c.evaluate_container_protection(100)
        self.assertEqual({call.args[0] for call in c.docker_container_action.call_args_list}, {"new-alpha", "bbb"})

    def test_one_stats_error_does_not_skip_other_container(self):
        c = self.make_collector()
        def stats(cid):
            if cid == "aaa":
                raise RuntimeError("unavailable")
            return {"ok": True, "stats": {"cpuPercent": 95}}
        c.docker_container_stats.side_effect = stats
        c.evaluate_container_protection(100)
        c.docker_container_action.assert_called_once_with("bbb", "restart")

    def test_samples_are_parallel_and_shared_between_rules(self):
        c = self.make_collector()
        c.container_protection_rules.append({**copy.deepcopy(c.container_protection_rules[0]), "id": "second"})
        rendezvous = threading.Barrier(2)
        def stats(cid):
            rendezvous.wait(timeout=2)
            return {"ok": True, "stats": {"cpuPercent": 10}}
        c.docker_container_stats.side_effect = stats
        c.evaluate_container_protection(100)
        self.assertEqual(c.docker_container_stats.call_count, 2)
        self.assertEqual(c.container_protection_states["r"]["containers"]["name:alpha"]["monitorStatus"], "healthy")

    def test_repeated_unavailable_samples_break_duration_and_show_error(self):
        c = self.make_collector(duration=10)
        for timestamp, ok in ((100, True), (105, False), (110, True)):
            c.docker_container_stats.return_value = {"ok": ok, "detail": "timeout", "stats": {"cpuPercent": 95}}
            c.evaluate_container_protection(timestamp)
        c.docker_container_action.assert_not_called()
        c.docker_container_stats.return_value = {"ok": False, "detail": "timeout"}
        c.evaluate_container_protection(115)
        state = c.container_protection_states["r"]["containers"]["name:alpha"]
        self.assertEqual(state["monitorStatus"], "unavailable")
        self.assertIn("timeout", state["monitorReason"])

    def test_multitarget_counts_survive_restart_and_reset_together(self):
        c = self.make_collector()
        c.evaluate_container_protection(100)
        restored = self.make_collector()
        restored.db = c.db
        restored.load_saved_settings()
        restored.evaluate_container_protection(101)
        self.assertEqual({s["count"] for s in restored.container_protection_states["r"]["containers"].values()}, {2})
        restored.get_settings = Mock(return_value={})
        restored.reset_container_protection("r")
        self.assertNotIn("r", restored.container_protection_states)

    def test_nested_pending_actions_lock_after_restart_without_sample_windows(self):
        states = {"r": {"containers": {"name:alpha": {"pending": True, "count": 1,
                                                      "metrics": {"cpu": {}}, "lastStatsAt": 50}}}}
        saved = durable_states(states, {"r"})
        restored = restore_states(saved, {"r"})["r"]["containers"]["name:alpha"]
        self.assertTrue(restored["locked"])
        self.assertEqual(restored["metrics"], {})
        self.assertNotIn("lastStatsAt", saved["r"]["containers"]["name:alpha"])

    def test_selected_rule_roundtrips_without_losing_targets(self):
        c = self.make_collector()
        row = c.container_protection_rules[0]
        loaded, skipped = main.load_saved_container_protection_rules({"rules": [row]})
        self.assertEqual(skipped, 0)
        self.assertEqual(loaded[0]["targetMode"], "selected")
        self.assertEqual([r["containerName"] for r in loaded[0]["containers"]], ["alpha", "beta"])

    def test_docker_actions_wait_for_graceful_stop(self):
        c = self.make_collector()
        with patch.object(main, "docker_api_request", return_value={"ok": True}) as request:
            main.TrafficCollector.docker_container_action(c, "aaa", "restart")
        self.assertGreaterEqual(request.call_args.kwargs.get("timeout", 2), 20)

    def test_selected_replica_does_not_select_whole_compose_service(self):
        c = self.make_collector()
        c.container_protection_rules[0]["containers"] = [{"containerId": "aaa", "containerName": "alpha",
            "composeProject": "project", "composeService": "worker"}]
        for row in c.container_rows:
            row.update(composeProject="project", composeService="worker")
        c.evaluate_container_protection(100)
        c.docker_container_action.assert_called_once_with("aaa", "restart")

    def test_notification_error_does_not_restart_same_container_twice_in_one_cycle(self):
        c = self.make_collector()
        c.container_protection_rules.append({**copy.deepcopy(c.container_protection_rules[0]), "id": "second"})
        c.record_alert.side_effect = RuntimeError("evidence unavailable")
        c.evaluate_container_protection(100)
        self.assertEqual(c.docker_container_action.call_count, 2)

    def test_compose_recreation_preserves_per_container_count(self):
        c = self.make_collector()
        c.container_protection_rules[0]["containers"][0].update(composeProject="project", composeService="worker", composeContainerNumber="1")
        c.container_rows[0].update(composeProject="project", composeService="worker", composeContainerNumber="1")
        c.evaluate_container_protection(100)
        c.container_rows[0].update(id="new-alpha", name="renamed-alpha")
        c.evaluate_container_protection(101)
        c.evaluate_container_protection(102)
        self.assertEqual([call.args[1] for call in c.docker_container_action.call_args_list if call.args[0] == "new-alpha"], ["restart", "restart"])
        self.assertEqual(c.container_protection_states["r"]["containers"]["name:alpha"]["count"], 3)

    def test_saving_rule_changes_restarts_duration_window(self):
        c = self.make_collector(duration=10)
        c.get_settings = Mock(return_value={})
        c.evaluate_container_protection(100)
        row = {**c.container_protection_rules[0], "name": "edited"}
        c.update_container_protection_rules(main.ContainerProtectionRulesPayload(rules=[row]))
        c.evaluate_container_protection(110)
        c.docker_container_action.assert_not_called()

    def test_missing_sample_payload_is_not_a_healthy_zero_reading(self):
        with patch.object(main, "docker_api_get", return_value={}):
            self.assertEqual(main.docker_container_stats("demo"), {})

    def test_switch_all_to_single_preserves_target_count_instead_of_group_count(self):
        c = self.make_collector("all")
        c.get_settings = Mock(return_value={})
        c.evaluate_container_protection(100)
        row = {**c.container_protection_rules[0], "name": "scope switch", "targetMode": "single", "containerId": "aaa", "containerName": "alpha"}
        c.update_container_protection_rules(main.ContainerProtectionRulesPayload(rules=[row]))
        c.resolve_container_protection_target = lambda rule: {"id": "aaa", "name": "alpha"}
        c.evaluate_container_protection(101)
        self.assertEqual(c.docker_container_action.call_args.args, ("aaa", "restart"))

    def test_switch_single_to_selected_keeps_target_restart_history(self):
        c = self.make_collector("single")
        c.get_settings = Mock(return_value={})
        c.resolve_container_protection_target = lambda rule: {"id": "aaa", "name": "alpha"}
        c.evaluate_container_protection(100)
        row = {**c.container_protection_rules[0], "name": "scope switch", "targetMode": "selected"}
        c.update_container_protection_rules(main.ContainerProtectionRulesPayload(rules=[row]))
        c.evaluate_container_protection(101)
        c.evaluate_container_protection(102)
        self.assertEqual(c.docker_container_action.call_args_list[-2].args, ("aaa", "restart"))
        self.assertEqual(c.container_protection_states["r"]["containers"]["name:alpha"]["count"], 3)

    def test_missing_replica_never_adopts_unselected_survivor(self):
        c = self.make_collector()
        c.container_protection_rules[0]["containers"] = [{"containerId": "aaa", "containerName": "alpha", "composeProject": "p", "composeService": "worker", "composeContainerNumber": "1"}]
        c.container_rows = [{"id": "bbb", "name": "beta", "state": "running", "composeProject": "p", "composeService": "worker", "composeContainerNumber": "2"}]
        c.evaluate_container_protection(100)
        c.docker_container_action.assert_not_called()

    def test_replica_state_lookup_prefers_exact_identity(self):
        rule = {"id": "r", "targetMode": "all"}
        states = {"r": {"containers": {"name:alpha": {"containerId": "aaa", "containerName": "alpha", "composeProject": "p", "composeService": "worker", "count": 2}, "name:beta": {"containerId": "bbb", "containerName": "beta", "composeProject": "p", "composeService": "worker", "count": 1}}}}
        row = {"id": "bbb", "name": "beta", "composeProject": "p", "composeService": "worker"}
        self.assertEqual(row_protection_state(rule, states, row)["count"], 1)

    def test_late_target_refreshes_stats_after_slow_first_action(self):
        c = self.make_collector()
        clock = [0]
        def stats(cid, refresh=False):
            return {"ok": True, "cachedAt": 100 + clock[0], "stats": {"cpuPercent": 10 if refresh else 95}}
        def action(cid, action):
            clock[0] += 30
            return {"ok": True}
        c.docker_container_stats.side_effect = stats
        c.docker_container_action.side_effect = action
        with patch.object(main.time, "monotonic", side_effect=lambda: clock[0]):
            c.evaluate_container_protection(100)
        c.docker_container_action.assert_called_once_with("aaa", "restart")

    def test_switch_locked_single_to_empty_all_keeps_lock_when_container_returns(self):
        c = self.make_collector("all")
        c.container_protection_states["r"] = {"count": 2, "locked": True, "containerId": "aaa", "containerName": "alpha", "metrics": {}}
        c.container_rows = []
        c.evaluate_container_protection(100)
        c.container_rows = [{"id": "aaa", "name": "alpha", "state": "running"}]
        c.evaluate_container_protection(101)
        c.docker_container_action.assert_not_called()

    def test_compose_only_replica_identities_have_separate_action_counts(self):
        c = self.make_collector()
        c.container_protection_rules[0].update(maxActions=1, containers=[
            {"composeProject": "p", "composeService": "worker", "composeContainerNumber": "1"},
            {"composeProject": "p", "composeService": "worker", "composeContainerNumber": "2"}])
        for number, row in enumerate(c.container_rows, 1):
            row.update(composeProject="p", composeService="worker", composeContainerNumber=str(number))
        c.evaluate_container_protection(100)
        self.assertEqual([call.args[1] for call in c.docker_container_action.call_args_list], ["restart", "restart"])


if __name__ == "__main__":
    unittest.main()
