import copy
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import server.main as main


class AgentOperationsTests(unittest.TestCase):
    def setUp(self):
        self.collector = main.TrafficCollector()
        self.collector.monitor_rules = [main.sanitize_monitor_rule(main.MonitorRule(id='old', name='Old', metric='wan_tx_bps', threshold=20))]
        self.collector.container_protection_rules = [main.sanitize_container_protection_rule(main.ContainerProtectionRule(id='p1', name='Protection', conditions=[main.ContainerProtectionCondition(metric='cpuPercent', threshold=80)]))]
        self.collector.container_protection_states = {'p1': {'count': 9}}
        self.collector.db = Mock()
        self.collector.db.set_setting.return_value = {'ok': True}
        self.collector.db.set_settings_atomic.return_value = {'ok': True}
        self.collector.db.get_labels.return_value = {}
        self.full_id = 'abcdef123456' + 'a' * 52
        self.docker = patch.object(main, 'docker_api_request')
        self.docker_mock = self.docker.start()
        self.docker_mock.side_effect = lambda method, path, **kwargs: (
            {'ok': True, 'status': 200, 'json': [{'Id': self.full_id}]} if method == 'GET' else {'ok': True, 'status': 204})
        self.saved = patch.object(main, 'collector', self.collector)
        self.saved.start()
        self.password = patch.object(main, 'DASHBOARD_PASSWORD', 'unit-test-password')
        self.password.start()
        self.client = TestClient(main.app)
        self.client.cookies.set(main.AUTH_COOKIE_NAME, main.create_session_token())

    def tearDown(self):
        self.client.close()
        self.docker.stop()
        self.saved.stop()
        self.password.stop()

    def snapshot(self, kind):
        response = self.client.get('/api/agent/rules/' + kind)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def put(self, kind, revision, rule):
        return self.client.post('/api/agent/rules/' + kind, json={'expectedRevision': revision, 'operation': 'put', 'rule': rule})

    def test_get_and_put_preserve_other_rule_and_exclude_secrets(self):
        before = self.snapshot('monitor')
        self.assertEqual(set(before), {'rules', 'revision'})
        response = self.put('monitor', before['revision'], {'id': 'new', 'name': 'Daily', 'metric': 'daily_wan_tx_bytes', 'threshold': 123})
        self.assertEqual(response.status_code, 200, response.text)
        after = response.json()
        self.assertEqual([x['id'] for x in after['rules']], ['old', 'new'])
        self.assertEqual(after['rules'][1]['window'], 'day')
        self.assertNotEqual(before['revision'], after['revision'])
        self.assertEqual(set(after), {'ok', 'rules', 'revision'})
        self.assertIs(after['ok'], True)

    def test_stale_and_concurrent_writes_never_lose_updates(self):
        revision = self.snapshot('monitor')['revision']
        gate = threading.Barrier(2)
        def update(i):
            gate.wait()
            return self.put('monitor', revision, {'id': str(i), 'name': str(i), 'metric': 'wan_tx_bps', 'threshold': 10}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(update, range(2)))
        self.assertEqual(sorted(codes), [200, 409])
        self.assertEqual(len(self.snapshot('monitor')['rules']), 2)

    def test_dashboard_revision_conflicts_with_agent_changes_without_breaking_legacy(self):
        for kind, collection, endpoint, revision_field in [
            ('monitor', 'rules', '/api/settings/monitor', 'rulesRevision'),
            ('protection', 'containerRules', '/api/settings/container-protection', 'containerRulesRevision'),
        ]:
            with self.subTest(kind=kind):
                settings = self.client.get('/api/settings').json()['monitor']
                original = copy.deepcopy(settings[collection])
                self.assertEqual(settings[revision_field], self.snapshot(kind)['revision'])
                if kind == 'monitor':
                    new = {'id': 'ui-race', 'name': 'Agent rule', 'metric': 'wan_tx_bps', 'threshold': 50}
                else:
                    new = {'id': 'ui-race', 'name': 'Agent rule', 'targetMode': 'all', 'conditions': [{'metric': 'cpuPercent', 'threshold': 80}]}
                saved = self.put(kind, settings[revision_field], new)
                self.assertEqual(saved.status_code, 200, saved.text)
                stale = self.client.post(endpoint, json={'rules': original, 'expectedRevision': settings[revision_field]})
                self.assertEqual(stale.status_code, 409, stale.text)
                self.assertIn('ui-race', [item['id'] for item in self.snapshot(kind)['rules']])
                legacy = self.client.post(endpoint, json={'rules': original})
                self.assertEqual(legacy.status_code, 200, legacy.text)
                self.assertNotIn('ui-race', [item['id'] for item in self.snapshot(kind)['rules']])

    def test_existing_rule_cannot_be_replaced_with_incomplete_object(self):
        snapshot = self.snapshot('monitor')
        incomplete = {'id': 'old', 'name': 'Changed', 'metric': 'wan_tx_bps'}
        result = self.put('monitor', snapshot['revision'], incomplete)
        self.assertEqual(result.status_code, 422)
        self.collector.db.set_setting.assert_not_called()
        complete = dict(snapshot['rules'][0], threshold=4321)
        result = self.put('monitor', snapshot['revision'], complete)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['rules'][0]['threshold'], 4321)

    def test_existing_international_and_spaced_rule_id_can_be_changed_and_deleted(self):
        self.collector.monitor_rules[0]['id'] = '公网 每日 上传'
        snapshot = self.snapshot('monitor')
        updated = dict(snapshot['rules'][0], threshold=40)
        result = self.put('monitor', snapshot['revision'], updated)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['rules'][0]['id'], '公网 每日 上传')
        deleted = self.client.post('/api/agent/rules/monitor', json={'expectedRevision': result.json()['revision'], 'operation': 'delete', 'ruleId': '公网 每日 上传'})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()['rules'], [])

    def test_id_rejects_control_characters_outer_whitespace_and_overlong_values(self):
        snapshot = self.snapshot('monitor')
        for invalid in (' bad', 'bad ', 'bad\nname', 'bad\x00name', 'a' * 65, ''):
            with self.subTest(invalid=invalid):
                rule = {'id': invalid, 'name': 'Invalid', 'metric': 'wan_tx_bps', 'threshold': 5}
                self.assertEqual(self.put('monitor', snapshot['revision'], rule).status_code, 422)
                result = self.client.post('/api/agent/rules/monitor', json={'expectedRevision': snapshot['revision'], 'operation': 'delete', 'ruleId': invalid})
                self.assertEqual(result.status_code, 422)

    def test_id_rejects_unencodable_utf8_surrogates(self):
        self.assertFalse(main.valid_agent_rule_id('\ud800'))

    def test_delete_and_protection_history_preserved_for_other_rules(self):
        before = self.snapshot('protection')
        response = self.put('protection', before['revision'], {'id': 'p2', 'name': 'Second', 'targetMode': 'all', 'conditions': [{'metric': 'cpuPercent', 'threshold': 80}]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.collector.container_protection_states['p1']['count'], 9)
        revision = response.json()['revision']
        delete = self.client.post('/api/agent/rules/protection', json={'expectedRevision': revision, 'operation': 'delete', 'ruleId': 'p2'})
        self.assertEqual(delete.status_code, 200, delete.text)
        self.assertEqual([r['id'] for r in delete.json()['rules']], ['p1'])
        self.assertEqual(self.collector.container_protection_states['p1']['count'], 9)
        missing = self.client.post('/api/agent/rules/protection', json={'expectedRevision': delete.json()['revision'], 'operation': 'delete', 'ruleId': 'p2'})
        self.assertEqual(missing.status_code, 404)

    def test_invalid_rule_unknown_fields_and_duplicate_existing_ids_rejected(self):
        revision = self.snapshot('monitor')['revision']
        for rule in ({'id': '', 'name': 'bad', 'metric': 'wan_tx_bps'}, {'id': 'r', 'name': 'bad', 'metric': 'bogus'}, {'id': 'r', 'name': 'bad', 'metric': 'wan_tx_bps', 'unexpected': True}, {'id': 'r', 'name': 'bad', 'metric': 'wan_tx_bps', 'threshold': -1}):
            with self.subTest(rule=rule):
                response = self.put('monitor', revision, rule)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.collector.db.set_setting.call_count, 0)
        self.collector.monitor_rules.append(copy.deepcopy(self.collector.monitor_rules[0]))
        revision = self.snapshot('monitor')['revision']
        self.assertEqual(self.put('monitor', revision, {'id': 'old', 'name': 'Change', 'metric': 'wan_tx_bps'}).status_code, 409)

    def test_storage_failure_preserves_memory(self):
        revision = self.snapshot('monitor')['revision']
        old = copy.deepcopy(self.collector.monitor_rules)
        self.collector.db.set_setting.return_value = {'ok': False}
        self.collector.db.set_settings_atomic.return_value = {'ok': False}
        response = self.put('monitor', revision, {'id': 'new', 'name': 'New', 'metric': 'wan_tx_bps', 'threshold': 10})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.collector.monitor_rules, old)

        revision = self.snapshot('protection')['revision']
        original_rules = copy.deepcopy(self.collector.container_protection_rules)
        original_states = copy.deepcopy(self.collector.container_protection_states)
        response = self.put('protection', revision, {'id': 'p2', 'name': 'New', 'targetMode': 'all', 'conditions': [{'metric': 'cpuPercent', 'threshold': 80}]})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.collector.container_protection_rules, original_rules)
        self.assertEqual(self.collector.container_protection_states, original_states)

    def test_delete_recreate_does_not_restore_old_durable_state(self):
        with tempfile.TemporaryDirectory() as path:
            db = main.TrafficDB(Path(path) / 'traffic.db')
            db.start()
            self.collector.db = db
            try:
                self.collector.container_protection_rules[0]['targetMode'] = 'all'
                other = {**self.collector.container_protection_rules[0], 'id': 'other'}
                self.collector.container_protection_rules.append(other)
                self.collector.container_protection_states = {'p1': {'count': 9, 'pending': True, 'locked': True}, 'other': {'count': 7}}
                db.set_setting('container_protection_rules', {'rules': self.collector.container_protection_rules})
                db.set_setting('container_protection_states', self.collector.container_protection_states)
                snapshot = self.snapshot('protection')
                old = snapshot['rules'][0]
                delete = self.client.post('/api/agent/rules/protection', json={'expectedRevision': snapshot['revision'], 'operation': 'delete', 'ruleId': 'p1'})
                self.assertEqual(delete.status_code, 200, delete.text)
                self.assertNotIn('p1', db.get_setting('container_protection_states'))
                self.assertEqual(db.get_setting('container_protection_states')['other']['count'], 7)
                recreate = self.put('protection', delete.json()['revision'], old)
                self.assertEqual(recreate.status_code, 200, recreate.text)
                restored = main.TrafficCollector()
                restored.db = db
                restored.load_saved_settings()
                self.assertNotIn('p1', restored.container_protection_states)
                self.assertEqual(restored.container_protection_states['other']['count'], 7)
            finally:
                db.conn.close()

    def test_rule_threshold_change_rearms_realtime_without_clearing_daily_dedupe(self):
        c = self.collector
        c.record_alert = Mock()
        c.monitor_rules[0]['threshold'] = 20
        c.daily_alert_dates['other-daily'] = '2026-10-27'
        self.assertTrue(c.evaluate_monitor_rule('wan_tx_bps', 30, 100))
        snapshot = self.snapshot('monitor')
        same = self.put('monitor', snapshot['revision'], snapshot['rules'][0])
        self.assertEqual(same.status_code, 200)
        self.assertTrue(c.rule_states['old']['active'])
        changed = dict(same.json()['rules'][0], threshold=10)
        response = self.put('monitor', same.json()['revision'], changed)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(c.evaluate_monitor_rule('wan_tx_bps', 30, 101))
        self.assertEqual(c.record_alert.call_count, 2)
        self.assertEqual(c.daily_alert_dates['other-daily'], '2026-10-27')

    def test_monitor_evaluation_shares_settings_lock(self):
        c = self.collector
        c.monitor_rules[0]['threshold'] = 20
        c.record_alert = Mock()
        started = threading.Event()
        finished = threading.Event()
        def evaluate():
            started.set()
            c.evaluate_monitor_rule('wan_tx_bps', 30, 100)
            finished.set()
        with c.settings_lock:
            thread = threading.Thread(target=evaluate)
            thread.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(finished.wait(0.1))
        thread.join(1)
        self.assertTrue(finished.is_set())

    def test_nested_unknown_or_invalid_conditions_never_silently_change(self):
        revision = self.snapshot('protection')['revision']
        for extra in ({'conditions': [{'metric': 'not-real', 'threshold': 1}]},
                      {'conditions': [{'metric': 'cpuPercent', 'threshold': 1, 'mystery': True}]},
                      {'conditions': [{'metric': 'cpuPercent', 'threshold': -1}]},
                      {'conditions': [{'metric': 'cpuPercent', 'threshold': 1}], 'containers': [{'containerId': 'a', 'unexpected': 1}]}):
            rule = {'id': 'p2', 'name': 'New', 'targetMode': 'all'}
            rule.update(extra)
            with self.subTest(extra=extra):
                self.assertEqual(self.put('protection', revision, rule).status_code, 422)
        self.collector.db.set_setting.assert_not_called()

    def test_enabled_rules_require_positive_thresholds_but_disabled_can_keep_zero(self):
        monitor_revision = self.snapshot('monitor')['revision']
        rule = {'id': 'zero', 'name': 'Zero', 'metric': 'wan_tx_bps', 'threshold': 0}
        self.assertEqual(self.put('monitor', monitor_revision, rule).status_code, 422)
        rule['enabled'] = False
        self.assertEqual(self.put('monitor', monitor_revision, rule).status_code, 200)
        protection_revision = self.snapshot('protection')['revision']
        rule = {'id': 'zero', 'name': 'Zero', 'targetMode': 'all', 'conditions': [
            {'metric': 'cpuPercent', 'threshold': 80}, {'metric': 'memoryPercent', 'threshold': 0}]}
        self.assertEqual(self.put('protection', protection_revision, rule).status_code, 422)
        rule['enabled'] = False
        self.assertEqual(self.put('protection', protection_revision, rule).status_code, 200)

    def test_rejects_protection_rule_conditions_that_startup_would_truncate(self):
        revision = self.snapshot('protection')['revision']
        condition = {'metric': 'cpuPercent', 'threshold': 80}
        rule = {'id': 'many', 'name': 'Many', 'targetMode': 'all', 'logic': 'and', 'conditions': [condition.copy() for _ in range(21)]}
        self.assertEqual(self.put('protection', revision, rule).status_code, 422)
        rule['conditions'].pop()
        response = self.put('protection', revision, rule)
        self.assertEqual(response.status_code, 200, response.text)
        persisted = response.json()['rules'][-1]
        loaded, skipped = main.load_saved_container_protection_rules({'rules': [persisted]})
        self.assertEqual(skipped, 0)
        self.assertEqual(loaded[0], persisted)

    def test_rejects_rule_integers_that_lose_precision_when_reloaded(self):
        huge = 2**53 + 1
        monitor_revision = self.snapshot('monitor')['revision']
        for field in ('threshold', 'durationSeconds'):
            rule = {'id': 'large', 'name': 'Large', 'metric': 'wan_tx_bps', 'threshold': 80}
            rule[field] = huge
            self.assertEqual(self.put('monitor', monitor_revision, rule).status_code, 422)
        protection_revision = self.snapshot('protection')['revision']
        for field in ('threshold', 'durationSeconds'):
            rule = {'id': 'large', 'name': 'Large', 'targetMode': 'all', 'conditions': [{'metric': 'cpuPercent', 'threshold': 80, field: huge}]}
            self.assertEqual(self.put('protection', protection_revision, rule).status_code, 422)
        for field in ('cooldownSeconds', 'maxActions'):
            rule = {'id': 'large', 'name': 'Large', 'targetMode': 'all', 'conditions': [{'metric': 'cpuPercent', 'threshold': 80}], field: huge}
            self.assertEqual(self.put('protection', protection_revision, rule).status_code, 422)

    def test_single_container_restart_requires_full_safe_id_and_hides_details(self):
        for bad in ['not-container', 'abc', 'zzzzzzzzzzzz', 'aaaaaaaaaaa_']:
            response = self.client.post('/api/agent/containers/' + bad + '/restart')
            self.assertEqual(response.status_code, 422)
        self.docker_mock.assert_not_called()
        response = self.client.post('/api/agent/containers/abcdef123456/restart')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(any(args.args[0] == 'POST' and self.full_id in args.args[1] for args in self.docker_mock.call_args_list))
        self.docker_mock.side_effect = lambda method, path, **kwargs: (
            {'ok': True, 'status': 200, 'json': [{'Id': self.full_id}]} if method == 'GET' else {'ok': False, 'detail': 'secret docker detail'})
        response = self.client.post('/api/agent/containers/abcdef123456/restart')
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('secret', response.text)

    def test_container_ids_must_resolve_uniquely(self):
        self.docker_mock.return_value = None
        self.docker_mock.side_effect = lambda *args, **kwargs: {'ok': True, 'json': [{'Id': self.full_id}, {'Id': 'abcdef123456' + 'b' * 52}]}
        response = self.client.post('/api/agent/containers/abcdef123456/restart')
        self.assertEqual(response.status_code, 409)
        self.assertEqual([x.args[0] for x in self.docker_mock.call_args_list], ['GET'])
        self.docker_mock.reset_mock()
        response = self.client.post('/api/agent/containers/' + ('abcdef123456' + 'c' * 52) + '/restart')
        self.assertEqual(response.status_code, 404)

    def test_manual_restart_shares_protection_lock_without_altering_rule_state(self):
        started = threading.Event()
        finished = threading.Event()
        states = copy.deepcopy(self.collector.container_protection_states)
        def restart():
            started.set()
            self.assertEqual(self.client.post('/api/agent/containers/abcdef123456/restart').status_code, 200)
            finished.set()
        with self.collector.protection_lock:
            thread = threading.Thread(target=restart)
            thread.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(finished.wait(0.1))
            self.docker_mock.assert_not_called()
        thread.join(1)
        self.assertTrue(finished.is_set())
        self.assertEqual(self.collector.container_protection_states, states)

    def test_mutation_requires_configured_password_session_and_same_origin(self):
        revision = self.snapshot('monitor')['revision']
        payload = {'expectedRevision': revision, 'operation': 'delete', 'ruleId': 'old'}
        with patch.object(main, 'DASHBOARD_PASSWORD', ''):
            self.assertEqual(self.client.post('/api/agent/rules/monitor', json=payload).status_code, 403)
            self.assertEqual(self.client.post('/api/agent/containers/abcdef123456/restart').status_code, 403)
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/agent/rules/monitor', json=payload).status_code, 401)
        self.client.cookies.set(main.AUTH_COOKIE_NAME, main.create_session_token())
        self.assertEqual(self.client.post('/api/agent/rules/monitor', json=payload, headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/agent/containers/abcdef123456/restart', headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/agent/rules/monitor', json=payload, headers={'Origin': 'http://testserver'}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
