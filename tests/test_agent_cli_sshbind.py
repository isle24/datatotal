import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / '.agents/skills/nas-traffic-lens/scripts/ntl_sshbind.py'


def completed(stdout='', stderr='', code=0):
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)


def listing(host='192.0.2.10', usable=True):
    return completed(json.dumps({'servers': [{'name': 'example-nas', 'host': host, 'usable': usable}]}))


def inspection(password='secret-example'):
    env = [] if password is None else ['DASHBOARD_PASSWORD=' + password]
    return completed(json.dumps({'exit_code': 0, 'stdout': json.dumps([{'Config': {'Env': env}}]), 'stderr': ''}))


class SshbindClientTests(unittest.TestCase):
    def setUp(self):
        if not SCRIPT.is_file():
            self.fail('sshbind helper has not yet been implemented')
        spec = importlib.util.spec_from_file_location('ntl_sshbind_test', SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def invoke(self, calls, argv=None):
        out, err = io.StringIO(), io.StringIO()
        args = argv or ['--alias', 'example-nas', '--container', 'nas-traffic-lens', '--url', 'http://192.0.2.10:8088', 'history', '--period', 'day']
        with patch.object(self.mod.subprocess, 'run', side_effect=calls) as run, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = self.mod.main(args)
        return status, out.getvalue(), err.getvalue(), run

    def test_passes_secret_only_via_stdin_and_propagates_json(self):
        status, out, err, run = self.invoke([listing(), inspection(), completed('{"ok":true}\n')])
        self.assertEqual((status, out, err), (0, '{"ok":true}\n', ''))
        self.assertEqual(run.call_args_list[0].args[0], ['sshbind', 'list', '--json'])
        inspect = run.call_args_list[1].args[0]
        self.assertEqual(inspect, ['sshbind', 'exec', '--json', 'example-nas', 'docker inspect nas-traffic-lens'])
        cmd = run.call_args_list[2].args[0]
        self.assertEqual(cmd[-4:], ['--password-stdin', 'history', '--period', 'day'])
        self.assertNotIn('secret-example', repr(cmd))
        self.assertEqual(run.call_args_list[2].kwargs['input'], 'secret-example\n')

    def test_symlinked_command_locates_query_script_next_to_real_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'ntl-query'
            link.symlink_to(SCRIPT)
            with patch.object(self.mod, '__file__', str(link)):
                status, _, _, run = self.invoke([listing(), inspection(None), completed('{}')])
        self.assertEqual(status, 0)
        self.assertEqual(run.call_args_list[2].args[0][1], str(SCRIPT.resolve().with_name('ntl.py')))

    def test_no_password_does_not_send_stdin_password_flag(self):
        status, _, _, run = self.invoke([listing(), inspection(None), completed('{"ok":true}')])
        self.assertEqual(status, 0)
        self.assertNotIn('--password-stdin', run.call_args_list[2].args[0])
        self.assertNotIn('input', run.call_args_list[2].kwargs)

    def test_unsafe_identifier_rejected_before_execution(self):
        status, _, _, run = self.invoke([], ['--alias', 'example-nas;id', '--container', 'good', '--url', 'http://192.0.2.10:8088', 'health'])
        self.assertNotEqual(status, 0)
        self.assertEqual(run.call_count, 0)

    def test_unusable_and_mismatched_host_stop_before_inspect(self):
        for server in (listing(usable=False), listing(host='elsewhere')):
            with self.subTest(server=server):
                status, _, _, run = self.invoke([server])
                self.assertNotEqual(status, 0)
                self.assertEqual(run.call_count, 1)

    def test_case_insensitive_host_matching(self):
        args = ['--alias', 'example-nas', '--container', 'app', '--url', 'http://NAS.EXAMPLE:8088', 'health']
        status, _, _, _ = self.invoke([listing('nas.example'), inspection(), completed('{}')], args)
        self.assertEqual(status, 0)

    def test_bad_url_and_credentials_rejected_before_inspection(self):
        for url in ('ftp://192.0.2.10', 'http://user:pass@192.0.2.10', 'http://192.0.2.10/path'):
            with self.subTest(url=url):
                status, _, _, run = self.invoke([], ['--alias', 'example-nas', '--container', 'app', '--url', url, 'health'])
                self.assertNotEqual(status, 0)
                self.assertEqual(run.call_count, 0)

    def test_inspection_failure_hides_sensitive_stdout_and_stderr(self):
        for result in (completed('secret-example', 'secret-example', 1), completed(json.dumps({'exit_code': 2, 'stdout': 'secret-example', 'stderr': 'secret-example'}))):
            with self.subTest(result=result):
                status, out, err, run = self.invoke([listing(), result])
                self.assertNotEqual(status, 0)
                self.assertNotIn('secret-example', out + err)
                self.assertEqual(run.call_count, 2)

    def test_child_failure_does_not_echo_secret_in_diagnostics(self):
        status, out, err, _ = self.invoke([listing(), inspection(), completed('secret-example', 'secret-example', 1)])
        self.assertNotEqual(status, 0)
        self.assertNotIn('secret-example', out + err)

    def test_known_child_failures_are_distinguished_without_forwarding_output(self):
        cases = [
            (1, 'ntl: Server returned HTTP 409.\n', 'Version conflict; fetch current rules before retrying.'),
            (1, 'ntl: Mutation outcome unknown; check current state before retrying.\n', 'Mutation outcome unknown; check current state before retrying.'),
            (1, 'ntl: Action failed.\n', 'Action failed.'),
            (1, 'ntl: --apply is required for mutations.\n', '--apply is required for mutations.'),
            (2, 'arbitrary invalid argument secret-example\n', 'Invalid command or arguments.'),
        ]
        for code, child_stderr, expected in cases:
            with self.subTest(child_stderr=child_stderr):
                status, out, err, run = self.invoke([listing(), inspection(), completed('secret-example', child_stderr, code)])
                self.assertNotEqual(status, 0)
                self.assertEqual(out, '')
                self.assertEqual(err, 'ntl-sshbind: ' + expected + '\n')
                self.assertNotIn('secret-example', err)
                self.assertEqual(run.call_count, 3)

    def test_spoofed_or_extra_child_error_text_is_not_forwarded(self):
        err_text = 'ntl: Server returned HTTP 409.\nsecret-example\n'
        status, out, err, _ = self.invoke([listing(), inspection(), completed('secret-example', err_text, 1)])
        self.assertNotEqual(status, 0)
        self.assertEqual(out, '')
        self.assertNotIn('secret-example', err)
        self.assertNotIn('Version conflict', err)

    def test_mutation_subprocess_timeout_reports_unknown_and_does_not_retry(self):
        for command in ('rule-put', 'rule-delete', 'container-restart'):
            with self.subTest(command=command):
                args = ['--alias', 'example-nas', '--container', 'nas-traffic-lens', '--url', 'http://192.0.2.10:8088', command]
                timeout = subprocess.TimeoutExpired('ignored', 60, output='secret-example', stderr='secret-example')
                status, out, err, run = self.invoke([listing(), inspection(), timeout], args)
                self.assertNotEqual(status, 0)
                self.assertEqual(out, '')
                self.assertEqual(err, 'ntl-sshbind: Mutation outcome unknown; check current state before retrying.\n')
                self.assertNotIn('secret-example', err)
                self.assertEqual(run.call_count, 3)
                self.assertEqual(run.call_args_list[2].kwargs['timeout'], 90)

    def test_restart_conflict_reports_ambiguous_id_not_rule_version(self):
        args = ['--alias', 'example-nas', '--container', 'nas-traffic-lens', '--url', 'http://192.0.2.10:8088', 'container-restart', 'abcdef123456', '--apply']
        status, out, err, run = self.invoke([listing(), inspection(), completed('', 'ntl: Server returned HTTP 409.\n', 1)], args)
        self.assertNotEqual(status, 0)
        self.assertEqual(out, '')
        self.assertEqual(err, 'ntl-sshbind: Container ID is ambiguous; use its full ID.\n')
        self.assertEqual(run.call_count, 3)

    def test_unexpected_mutation_result_is_unknown_and_never_echoes_data(self):
        args = ['--alias', 'example-nas', '--container', 'nas-traffic-lens', '--url', 'http://192.0.2.10:8088', 'container-restart']
        for child in (completed('secret-example', 'secret-example', 1), completed('secret-example', '', 0)):
            with self.subTest(code=child.returncode):
                status, out, err, run = self.invoke([listing(), inspection(), child], args)
                self.assertNotEqual(status, 0)
                self.assertEqual(out, '')
                self.assertEqual(err, 'ntl-sshbind: Mutation outcome unknown; check current state before retrying.\n')
                self.assertNotIn('secret-example', err)
                self.assertEqual(run.call_count, 3)

    def test_newline_in_password_is_rejected(self):
        status, out, err, run = self.invoke([listing(), inspection('secret\nnext')])
        self.assertNotEqual(status, 0)
        self.assertNotIn('secret', out + err)
        self.assertEqual(run.call_count, 2)

    def test_config_file_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text(json.dumps({'alias': 'wrong', 'container': 'app', 'url': 'http://192.0.2.10:8088'}))
            status, _, _, run = self.invoke([listing(), inspection(None), completed('{}')], ['--config', str(path), '--alias', 'example-nas', 'health'])
        self.assertEqual(status, 0)
        self.assertEqual(run.call_args_list[1].args[0][-1], 'docker inspect app')

    def test_config_rejects_password_or_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text(json.dumps({'alias': 'example-nas', 'container': 'app', 'url': 'http://192.0.2.10:8088', 'password': 'secret-example'}))
            status, out, err, run = self.invoke([], ['--config', str(path), 'health'])
        self.assertNotEqual(status, 0)
        self.assertNotIn('secret-example', out + err)
        self.assertEqual(run.call_count, 0)


if __name__ == '__main__':
    unittest.main()
