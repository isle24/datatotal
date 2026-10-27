"""CLI-to-FastAPI integration against a loopback-only, isolated instance."""
import copy
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import uvicorn

import server.main as main


CLI = Path(__file__).resolve().parents[1] / '.agents/skills/nas-traffic-lens/scripts/ntl.py'
FAKE_PASSWORD = 'local-integration-test-only'
FULL_CONTAINER_ID = 'abcdef123456' + 'a' * 52


class AgentCLIIntegrationTests(unittest.TestCase):
    def test_rule_update_conflict_and_container_restart(self):
        docker_calls = []

        def docker_request(method, path, **kwargs):
            docker_calls.append((method, path))
            if method == 'GET':
                return {'ok': True, 'status': 200, 'json': [{'Id': FULL_CONTAINER_ID}]}
            return {'ok': True, 'status': 204}

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            collector = main.TrafficCollector()
            collector.db = main.TrafficDB(Path(tmp) / 'isolated.db')
            collector.db.start()
            stack.callback(collector.db.conn.close)
            collector.monitor_rules = [
                main.sanitize_monitor_rule(main.MonitorRule(id='first', name='First', metric='wan_tx_bps', threshold=10)),
                main.sanitize_monitor_rule(main.MonitorRule(id='second', name='Second', metric='daily_wan_tx_bytes', threshold=20)),
            ]
            before_rules = copy.deepcopy(collector.monitor_rules)
            stack.enter_context(patch.object(main, 'collector', collector))
            stack.enter_context(patch.object(main, 'DASHBOARD_PASSWORD', FAKE_PASSWORD))
            stack.enter_context(patch.object(main, 'docker_api_request', side_effect=docker_request))
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            stack.callback(sock.close)
            sock.bind(('127.0.0.1', 0))
            sock.listen(64)
            url = 'http://127.0.0.1:%d' % sock.getsockname()[1]
            # Lifespan is disabled so the real collector startup never opens any
            # capture interface, host Docker socket or production database.
            server = uvicorn.Server(uvicorn.Config(main.app, lifespan='off', log_level='critical', access_log=False))
            thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
            thread.start()

            def stop_server():
                server.should_exit = True
                thread.join(5)
            stack.callback(stop_server)
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(server.started, 'loopback test server did not start')

            def cli(*args):
                env = dict(os.environ)
                env.pop('NTL_URL', None)
                result = subprocess.run(
                    [sys.executable, str(CLI), '--url', url, '--password-stdin', *args],
                    input=FAKE_PASSWORD + '\n', text=True, capture_output=True, env=env, timeout=10,
                )
                self.assertNotIn(FAKE_PASSWORD, result.stdout + result.stderr)
                return result

            listed = cli('rules', '--kind', 'monitor')
            self.assertEqual(listed.returncode, 0, listed.stderr)
            snapshot = json.loads(listed.stdout)
            self.assertEqual(snapshot['rules'], before_rules)
            changed = dict(snapshot['rules'][0], threshold=42)
            put = cli('rule-put', '--kind', 'monitor', '--revision', snapshot['revision'],
                      '--rule-json', json.dumps(changed), '--apply')
            self.assertEqual(put.returncode, 0, put.stderr)
            self.assertTrue(json.loads(put.stdout)['ok'])
            stored = collector.db.get_setting('monitor_rules')['rules']
            self.assertEqual(stored[0]['threshold'], 42)
            self.assertEqual(stored[1], before_rules[1])
            listed_after = cli('rules', '--kind', 'monitor')
            self.assertEqual(listed_after.returncode, 0, listed_after.stderr)
            snapshot_after = json.loads(listed_after.stdout)
            self.assertEqual(snapshot_after['rules'], stored)
            self.assertNotEqual(snapshot_after['revision'], snapshot['revision'])

            stale = cli('rule-put', '--kind', 'monitor', '--revision', snapshot['revision'],
                        '--rule-json', json.dumps(dict(changed, threshold=99)), '--apply')
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn('HTTP 409', stale.stderr)
            self.assertEqual(collector.db.get_setting('monitor_rules')['rules'], stored)

            restart = cli('container-restart', FULL_CONTAINER_ID[:12], '--apply')
            self.assertEqual(restart.returncode, 0, restart.stderr)
            self.assertEqual(json.loads(restart.stdout)['action'], 'restart')
            self.assertEqual(docker_calls, [
                ('GET', '/containers/json?all=1'),
                ('POST', '/containers/' + FULL_CONTAINER_ID + '/restart?t=10'),
            ])


if __name__ == '__main__':
    unittest.main()
