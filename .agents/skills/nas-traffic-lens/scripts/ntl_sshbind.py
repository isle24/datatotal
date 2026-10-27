#!/usr/bin/env python3
"""Query a bound NAS without saving or displaying its dashboard password."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


class HelperError(Exception):
    pass


IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
MUTATION_COMMANDS = {'rule-put', 'rule-delete', 'container-restart'}
UNKNOWN_MUTATION = 'Mutation outcome unknown; check current state before retrying.'
CHILD_ERRORS = {
    'ntl: Server returned HTTP 409.\n': 'Version conflict; fetch current rules before retrying.',
    'ntl: Mutation outcome unknown; check current state before retrying.\n': UNKNOWN_MUTATION,
    'ntl: Action failed.\n': 'Action failed.',
    'ntl: --apply is required for mutations.\n': '--apply is required for mutations.',
}


def parse_args(argv):
    parser = argparse.ArgumentParser(description='Query NAS Traffic Lens via a usable sshbind server; output JSON.')
    parser.add_argument('--config', help='JSON file containing only alias, container, and url')
    parser.add_argument('--alias', help='sshbind alias')
    parser.add_argument('--container', help='NAS Traffic Lens Docker container name or ID')
    parser.add_argument('--url', help='NAS Traffic Lens origin, with the same host as the sshbind server')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='query command and options for ntl.py')
    return parser.parse_args(argv)


def configuration(args):
    config = {}
    if args.config:
        try:
            with open(args.config, encoding='utf-8') as source:
                config = json.load(source)
            if not isinstance(config, dict) or set(config) - {'alias', 'container', 'url'}:
                raise ValueError
        except (OSError, UnicodeError, ValueError):
            raise HelperError('Invalid configuration file; only alias, container and url are allowed.') from None
    values = {key: getattr(args, key) if getattr(args, key) is not None else config.get(key)
              for key in ('alias', 'container', 'url')}
    for key in ('alias', 'container'):
        if not isinstance(values[key], str) or not IDENTIFIER.fullmatch(values[key]):
            raise HelperError('A valid --%s is required.' % key)
    url = values['url']
    try:
        if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
            raise ValueError
        parts = urlsplit(url)
        if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username is not None or
                parts.password is not None or parts.path not in ('', '/') or parts.query or parts.fragment):
            raise ValueError
        _ = parts.port
    except ValueError:
        raise HelperError('A valid --url origin without credentials or path is required.') from None
    command = list(args.command)
    if command and command[0] == '--':
        command.pop(0)
    if not command:
        raise HelperError('A query command is required.')
    if any(value == '--password-stdin' or value.startswith('--password-stdin=') or value == '--url' or value.startswith('--url=') for value in command):
        raise HelperError('Specify --url before the query command; password options are managed by this helper.')
    return values, parts.hostname.casefold(), command


def invoke(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        raise HelperError('Unable to run sshbind.') from None
    if result.returncode:
        raise HelperError('sshbind command failed; check connectivity and Docker access.')
    try:
        return json.loads(result.stdout)
    except (TypeError, ValueError):
        raise HelperError('sshbind returned invalid structured output.') from None


def fetch_password(values, host):
    listing = invoke(['sshbind', 'list', '--json'])
    servers = listing.get('servers') if isinstance(listing, dict) else None
    if not isinstance(servers, list):
        raise HelperError('sshbind returned an invalid server list.')
    matches = [server for server in servers if isinstance(server, dict) and server.get('name') == values['alias']]
    if len(matches) != 1 or matches[0].get('usable') is not True:
        raise HelperError('sshbind alias is not available and usable.')
    server_host = matches[0].get('host')
    if not isinstance(server_host, str) or server_host.casefold().strip('[]') != host:
        raise HelperError('Service URL host must match the sshbind server host.')
    response = invoke(['sshbind', 'exec', '--json', values['alias'], 'docker inspect ' + values['container']])
    if not isinstance(response, dict) or response.get('exit_code') != 0 or not isinstance(response.get('stdout'), str):
        raise HelperError('Unable to inspect the configured Docker container.')
    try:
        inspection = json.loads(response['stdout'])
        if not isinstance(inspection, list) or len(inspection) != 1:
            raise ValueError
        env = inspection[0]['Config']['Env'] or []
        if not isinstance(env, list) or not all(isinstance(item, str) for item in env):
            raise ValueError
        passwords = [item.partition('=')[2] for item in env if item.startswith('DASHBOARD_PASSWORD=')]
        if len(passwords) > 1:
            raise ValueError
        password = passwords[0] if passwords else ''
        if '\n' in password or '\r' in password:
            raise ValueError
        return password
    except (ValueError, TypeError, KeyError, IndexError):
        raise HelperError('Container configuration is invalid or unsupported.') from None


def main(argv=None):
    args = parse_args(argv)
    try:
        values, host, command = configuration(args)
        password = fetch_password(values, host)
        invocation = [sys.executable, str(Path(__file__).resolve().with_name('ntl.py')), '--url', values['url']]
        # Authentication can take two 15-second requests before a 45-second write.
        kwargs = {'capture_output': True, 'text': True, 'timeout': 90}
        if password:
            invocation.append('--password-stdin')
            kwargs['input'] = password + '\n'
        else:
            kwargs['stdin'] = subprocess.DEVNULL
        invocation.extend(command)
        try:
            result = subprocess.run(invocation, **kwargs)
        except subprocess.SubprocessError:
            if command[0] in MUTATION_COMMANDS:
                raise HelperError(UNKNOWN_MUTATION) from None
            raise HelperError('Unable to run the query client.') from None
        except OSError:
            raise HelperError('Unable to run the query client.') from None
        if result.returncode:
            if result.returncode == 2:
                raise HelperError('Invalid command or arguments.')
            if (result.returncode == 1 and command[0] == 'container-restart' and
                    result.stderr == 'ntl: Server returned HTTP 409.\n'):
                raise HelperError('Container ID is ambiguous; use its full ID.')
            if result.returncode == 1 and result.stderr in CHILD_ERRORS:
                raise HelperError(CHILD_ERRORS[result.stderr])
            if command[0] in MUTATION_COMMANDS:
                raise HelperError(UNKNOWN_MUTATION)
            raise HelperError('Query failed; check authentication, service availability and query arguments.')
        # Only pass through well-formed query JSON, not arbitrary subprocess output.
        try:
            json.loads(result.stdout)
        except (TypeError, ValueError):
            if command[0] in MUTATION_COMMANDS:
                raise HelperError(UNKNOWN_MUTATION) from None
            raise HelperError('Query returned invalid JSON.') from None
        sys.stdout.write(result.stdout)
        return 0
    except HelperError as exc:
        print('ntl-sshbind: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
