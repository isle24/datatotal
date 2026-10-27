"""Black-box tests for the NAS skill CLI (no external services)."""
import json
import importlib.util
import getpass
import warnings
from argparse import Namespace
from unittest.mock import patch
import os
import subprocess
import sys
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

CLI = Path(__file__).resolve().parents[1] / '.agents/skills/nas-traffic-lens/scripts/ntl.py'


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, data, headers=None):
        body = json.dumps(data).encode()
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.server.requests.append(('GET', self.path, self.headers.get('Cookie')))
        if self.path == '/api/auth/status':
            self.respond(200, {'enabled': self.server.auth, 'authenticated': not self.server.auth})
        elif self.server.redirect:
            self.respond(302, {}, {'Location': self.server.redirect})
        elif self.server.fail:
            self.respond(503, {'detail': 'service unavailable'})
        elif self.server.auth and self.headers.get('Cookie') != 'session=ok':
            self.respond(401, {'detail': 'unauthorized'})
        else:
            path = urlsplit(self.path).path
            payload = {'path': path, 'query': parse_qs(urlsplit(self.path).query)}
            if path == '/api/history':
                payload.update(period='day', buckets=[])
            elif path == '/api/docker/containers':
                payload.update(enabled=True, containers=[])
            elif path in ('/api/agent/rules/monitor', '/api/agent/rules/protection'):
                payload = {'rules': [{'id': 'one', 'name': 'rule'}], 'revision': 'a' * 64}
            self.respond(200, self.server.data_override if self.server.data_override is not None else payload)

    def do_POST(self):
        self.server.requests.append(('POST', self.path, None))
        n = int(self.headers.get('Content-Length', '0'))
        data = json.loads(self.rfile.read(n))
        if self.path == '/api/auth/login' and data.get('password') == 'test-secret':
            self.respond(200, {'ok': True}, {'Set-Cookie': 'session=ok; Path=/; HttpOnly'})
        elif self.path.startswith('/api/agent/'):
            self.server.posted.append((self.path, data))
            if self.server.mutation_redirect:
                self.respond(302, {}, {'Location': self.server.mutation_redirect})
            elif self.server.mutation_status != 200:
                self.respond(self.server.mutation_status, {'detail': 'sensitive-response-secret'})
            else:
                self.respond(200, self.server.mutation_response)
        else:
            self.respond(401, {'detail': 'invalid password'})


class CLITest(unittest.TestCase):
    def test_rule_id_rejects_unencodable_utf8_surrogate(self):
        spec = importlib.util.spec_from_file_location('ntl_utf8_test', CLI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertFalse(module.valid_rule_id('\ud800'))

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:%s' % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.auth = False
        self.server.redirect = None
        self.server.fail = False
        self.server.data_override = None
        self.server.requests = []
        self.server.posted = []
        self.server.mutation_status = 200
        self.server.mutation_redirect = None
        self.server.mutation_response = {'ok': True, 'revision': 'b' * 64, 'ruleId': 'one', 'secret': 'sensitive-response-secret'}

    def run_cli(self, *args, env=None, url=True, input_text=None):
        child_env = os.environ.copy()
        child_env.pop('NTL_URL', None)
        child_env.update(env or {})
        return subprocess.run([sys.executable, str(CLI)] + (['--url', self.url] if url else []) + list(args),
                              capture_output=True, text=True, env=child_env, timeout=5, input=input_text)

    def test_health_uses_status_then_read_only_get(self):
        result = self.run_cli('health')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['path'], '/api/health')
        self.assertEqual([r[:2] for r in self.server.requests], [('GET', '/api/auth/status'), ('GET', '/api/health')])

    def test_password_stdin_logs_in_and_uses_cookie_without_outputting_secret(self):
        self.server.auth = True
        result = self.run_cli('--password-stdin', 'system', input_text='test-secret\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['path'], '/api/system')
        self.assertEqual([r[0] for r in self.server.requests], ['GET', 'POST', 'GET'])
        self.assertEqual(self.server.requests[-1][2], 'session=ok')
        self.assertNotIn('test-secret', result.stdout + result.stderr)

    def test_missing_password_in_noninteractive_mode_fails_without_login(self):
        self.server.auth = True
        result = self.run_cli('health')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--password-stdin', result.stderr)
        self.assertEqual(len(self.server.requests), 1)

    def test_query_parameters_and_escaping(self):
        result = self.run_cli('connections', '--scope', 'wan', '--direction', 'tx', '--owner', 'q & b', '--limit', '12')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['query'], {'scope': ['wan'], 'direction': ['tx'], 'owner': ['q & b'], 'limit': ['12']})

    def test_url_from_environment_and_escaped_container_id(self):
        result = self.run_cli('container-stats', 'demo_1', env={'NTL_URL': self.url}, url=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['path'], '/api/docker/containers/demo_1/stats')

    def test_invalid_parameters_rejected_before_network(self):
        for command in [('history', '--period', 'forever'), ('container-stats', '../settings'), ('upload-diagnostics', '--date', '2026-13-99'), ('processes', '--limit', '-1')]:
            with self.subTest(command=command):
                result = self.run_cli(*command)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.server.requests)

    def test_http_error_is_nonzero_and_not_valid_data(self):
        self.server.fail = True
        result = self.run_cli('overview')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('503', result.stderr)

    def test_cross_origin_redirect_is_not_followed(self):
        self.server.redirect = 'http://127.0.0.1:1/stolen'
        result = self.run_cli('overview')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('redirect', result.stderr.lower())

    def test_single_alert_time_bound_is_supported(self):
        result = self.run_cli('alerts', '--start', '1700000000')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['query'], {'start': ['1700000000']})

    def test_endpoints_follow_the_allowed_mapping(self):
        cases = [(['overview'], '/api/overview'), (['history'], '/api/history'),
                 (['processes'], '/api/processes'), (['containers'], '/api/docker/containers'),
                 (['upload-diagnostics', '--date', '2026-10-27'], '/api/diagnostics/upload'),
                 (['tools'], '/api/agent/tools')]
        for command, expected in cases:
            with self.subTest(command=command):
                result = self.run_cli(*command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['path'], expected)

    def test_wrong_password_does_not_disclose_credential_or_response(self):
        self.server.auth = True
        result = self.run_cli('--password-stdin', 'health', input_text='wrong-secret\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('wrong-secret', result.stdout + result.stderr)
        self.assertNotIn('invalid password', result.stdout + result.stderr)
        self.assertEqual([item[0] for item in self.server.requests], ['GET', 'POST'])

    def test_interactive_password_aborts_if_echo_cannot_be_disabled(self):
        spec = importlib.util.spec_from_file_location('ntl_test', CLI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = Namespace(url=self.url, password_stdin=False, command='health')
        def unsafe_getpass(_):
            warnings.warn('cannot turn echo off', getpass.GetPassWarning)
            self.fail('password input continued with echo enabled')
        with patch.object(module, 'read_json', return_value={'enabled': True, 'authenticated': False}), \
             patch.object(module.sys.stdin, 'isatty', return_value=True), \
             patch.object(module.getpass, 'getpass', side_effect=unsafe_getpass):
            with self.assertRaises(module.ClientError):
                module.run(args)

    def test_invalid_history_and_container_structures_fail(self):
        for command in ('history', 'containers'):
            with self.subTest(command=command):
                self.server.data_override = {'detail': 'unexpected response'}
                result = self.run_cli(command)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertIn('invalid', result.stderr.lower())

    def test_url_credentials_are_refused(self):
        result = self.run_cli('--url', 'http://user:password@127.0.0.1:1', 'health', url=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('password@', result.stderr)
        self.assertFalse(self.server.requests)

    def test_rule_listing_uses_kind_endpoint_and_checks_revision(self):
        for kind in ('monitor', 'protection'):
            result = self.run_cli('rules', '--kind', kind)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['revision'], 'a' * 64)
            self.assertEqual(self.server.requests[-1][1], '/api/agent/rules/' + kind)
        self.server.data_override = {'rules': [], 'revision': 'bad'}
        self.assertNotEqual(self.run_cli('rules', '--kind', 'monitor').returncode, 0)

    def test_mutations_require_apply_and_valid_input_before_network(self):
        cases = [
            ('container-restart', 'a' * 12),
            ('container-restart', 'bad', '--apply'),
            ('rule-put', '--kind', 'monitor', '--revision', 'a' * 64, '--rule-json', '{"id":"one"}'),
            ('rule-delete', '--kind', 'monitor', '--revision', 'bad', '--id', 'one', '--apply'),
            ('rule-put', '--kind', 'monitor', '--revision', 'a' * 64, '--rule-json', '{bad', '--apply'),
            ('rule-put', '--kind', 'monitor', '--revision', 'a' * 64, '--rule-json', '{"id":"one","token":"do-not-leak"}', '--apply'),
            ('rule-put', '--kind', 'monitor', '--revision', 'a' * 64, '--rule-json', '{"id":"one","name":{"token":"do-not-leak"}}', '--apply'),
            ('rule-put', '--kind', 'monitor', '--revision', 'a' * 64, '--rule-json', '{"id":"one","threshold":-1}', '--apply'),
        ]
        for command in cases:
            with self.subTest(command=command):
                self.server.requests = []
                result = self.run_cli(*command)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('do-not-leak', result.stderr + result.stdout)
                self.assertEqual(self.server.requests, [])

    def test_rule_put_and_delete_post_expected_revision_and_filter_response(self):
        revision = 'a' * 64
        result = self.run_cli('rule-put', '--kind', 'monitor', '--revision', revision,
                              '--rule-json', '{"id":"one","name":"rule","metric":"daily_wan_tx_bytes"}', '--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.server.posted[-1], ('/api/agent/rules/monitor',
                         {'expectedRevision': revision, 'operation': 'put',
                          'rule': {'id': 'one', 'name': 'rule', 'metric': 'daily_wan_tx_bytes'}, 'ruleId': None}))
        self.assertNotIn('sensitive-response-secret', result.stdout + result.stderr)
        result = self.run_cli('rule-delete', '--kind', 'protection', '--revision', revision, '--id', 'one', '--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.server.posted[-1], ('/api/agent/rules/protection',
                         {'expectedRevision': revision, 'operation': 'delete', 'rule': None, 'ruleId': 'one'}))

    def test_restart_once_conflict_and_unsuccessful_payload_fail(self):
        self.server.mutation_response = {'ok': True, 'containerId': 'a' * 12, 'action': 'restart', 'secret': 'sensitive-response-secret'}
        result = self.run_cli('container-restart', 'a' * 12, '--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.server.posted, [('/api/agent/containers/' + 'a' * 12 + '/restart', {})])
        self.assertNotIn('sensitive-response-secret', result.stdout + result.stderr)
        self.server.mutation_status = 409
        self.server.posted = []
        result = self.run_cli('rule-delete', '--kind', 'monitor', '--revision', 'a' * 64, '--id', 'one', '--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('409', result.stderr)
        self.assertEqual(len(self.server.posted), 1)
        self.assertNotIn('sensitive-response-secret', result.stdout + result.stderr)
        self.server.mutation_status = 200
        self.server.mutation_response = {'ok': False, 'detail': 'sensitive-response-secret'}
        result = self.run_cli('container-restart', 'a' * 12, '--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('sensitive-response-secret', result.stdout + result.stderr)

    def test_mutation_timeout_is_unknown_and_not_retried(self):
        spec = importlib.util.spec_from_file_location('ntl_timeout_test', CLI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        class Opener:
            calls = 0
            def open(self, request, timeout):
                self.calls += 1
                raise urllib.error.URLError(TimeoutError('sensitive-response-secret'))
        opener = Opener()
        with self.assertRaises(module.ClientError) as error:
            module.read_json(opener, self.url + '/api/agent/rules/monitor', {}, mutation=True)
        self.assertEqual(str(error.exception), 'Mutation outcome unknown; check current state before retrying.')
        self.assertEqual(opener.calls, 1)

    def test_unusable_mutation_success_response_is_unknown_not_retryable(self):
        for response in ({}, {'ok': 'true'}, {'ok': False}, []):
            with self.subTest(response=response):
                self.server.posted = []
                self.server.mutation_response = response
                result = self.run_cli('container-restart', 'a' * 12, '--apply')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Mutation outcome unknown', result.stderr)
                self.assertEqual(len(self.server.posted), 1)

    def test_mutation_redirect_is_not_followed_and_outcome_is_unknown(self):
        self.server.mutation_redirect = 'http://127.0.0.1:1/unexpected'
        result = self.run_cli('container-restart', 'a' * 12, '--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Mutation outcome unknown', result.stderr)
        self.assertEqual(len(self.server.posted), 1)

    def test_mutation_timeout_allows_docker_graceful_restart(self):
        spec = importlib.util.spec_from_file_location('ntl_wait_test', CLI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{"ok":true}'
        class Opener:
            timeouts = []
            def open(self, request, timeout):
                self.timeouts.append(timeout)
                return Response()
        opener = Opener()
        module.read_json(opener, self.url + '/api/health')
        module.read_json(opener, self.url + '/api/agent/containers/aaaaaaaaaaaa/restart', {}, mutation=True)
        self.assertEqual(opener.timeouts, [15, 45])

    def test_rule_ids_allow_colon_in_inputs_and_rule_listing(self):
        self.server.data_override = {'rules': [{'id': 'team:one', 'name': 'rule'}], 'revision': 'a' * 64}
        result = self.run_cli('rules', '--kind', 'monitor')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['rules'][0]['id'], 'team:one')
        result = self.run_cli('rule-delete', '--kind', 'monitor', '--revision', 'a' * 64, '--id', 'team:one', '--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.server.posted[-1][1]['ruleId'], 'team:one')

    def test_rule_ids_allow_unicode_and_internal_spaces(self):
        name = '通知 规则一'
        self.server.data_override = {'rules': [{'id': name, 'name': 'rule'}], 'revision': 'a' * 64}
        result = self.run_cli('rules', '--kind', 'monitor')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['rules'][0]['id'], name)
        result = self.run_cli('rule-delete', '--kind', 'monitor', '--revision', 'a' * 64, '--id', name, '--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.server.posted[-1][1]['ruleId'], name)
        result = self.run_cli('rule-put', '--kind', 'monitor', '--revision', 'a' * 64,
                              '--rule-json', json.dumps({'id': name, 'name': 'rule', 'metric': 'wan_tx_bps'}, ensure_ascii=False), '--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.server.posted[-1][1]['rule']['id'], name)

    def test_rule_ids_reject_outer_space_and_control_characters(self):
        for name in ('', ' 规则', '规则 ', '规则\n一', '规则\x7f一', '规则\x85一', 'a' * 65):
            with self.subTest(name=repr(name)):
                self.server.requests = []
                result = self.run_cli('rule-delete', '--kind', 'monitor', '--revision', 'a' * 64, '--id', name, '--apply')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.server.requests, [])


if __name__ == '__main__':
    unittest.main()
