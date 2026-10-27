#!/usr/bin/env python3
"""NAS Traffic Lens client. Authentication is held in memory only."""
import argparse
import datetime
import getpass
import http.cookiejar
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import warnings


class ClientError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Even same-origin redirects can point to a non-whitelisted path, so reject all.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ClientError('Redirect refused; use the direct service URL.')


def base_url(raw):
    try:
        parts = urllib.parse.urlsplit(raw or '')
        if (parts.scheme not in ('http', 'https') or not parts.hostname or
                parts.username is not None or parts.password is not None or
                parts.query or parts.fragment or parts.path not in ('', '/') or
                any(c.isspace() or ord(c) < 32 for c in raw)):
            raise ValueError
        _ = parts.port  # validate the port before making a request
    except ValueError:
        raise ClientError('URL must be an http(s) origin without credentials, path, query or fragment.')
    return raw.rstrip('/')


def nonnegative(raw):
    try:
        value = int(raw)
        if value < 0:
            raise ValueError
        return value
    except ValueError:
        raise argparse.ArgumentTypeError('must be a non-negative integer')


def positive(raw):
    value = nonnegative(raw)
    if value == 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return value


def calendar_date(raw):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            raise ValueError
        datetime.date.fromisoformat(raw)
    except ValueError:
        raise argparse.ArgumentTypeError('must be a valid date in YYYY-MM-DD format')
    return raw


def container_id(raw):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', raw):
        raise argparse.ArgumentTypeError('must be a Docker container ID from the containers response')
    return raw


def revision_hash(raw):
    if not re.fullmatch(r'[0-9a-f]{64}', raw):
        raise argparse.ArgumentTypeError('must be a 64-character lowercase revision hash')
    return raw


def valid_rule_id(raw):
    if not (isinstance(raw, str) and 0 < len(raw) <= 64 and raw == raw.strip() and
            not any(unicodedata.category(char) == 'Cc' for char in raw)):
        return False
    try:
        raw.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def rule_id(raw):
    if not valid_rule_id(raw):
        raise argparse.ArgumentTypeError('must be a nonempty rule ID of at most 64 characters without outer whitespace or controls')
    return raw


def restart_id(raw):
    if not re.fullmatch(r'[0-9a-f]{12,64}', raw):
        raise argparse.ArgumentTypeError('must be a 12–64 character lowercase hexadecimal container ID')
    return raw


def parser():
    p = argparse.ArgumentParser(description='Query or explicitly operate NAS Traffic Lens; output JSON.')
    p.add_argument('--url', default=os.environ.get('NTL_URL'), help='service origin, e.g. http://nas:8088; or set NTL_URL')
    p.add_argument('--password-stdin', action='store_true', help='read password from a non-interactive stdin pipe without echo')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('health', 'system', 'containers', 'tools'):
        sub.add_parser(name)
    p_overview = sub.add_parser('overview')
    p_overview.add_argument('--interfaces', choices=['physical', 'all'])
    p_history = sub.add_parser('history')
    p_history.add_argument('--period', choices=['day', 'week', 'month', 'year'])
    p_process = sub.add_parser('processes')
    p_process.add_argument('--period', choices=['30s', 'today', '1d', '3d', '7d', '30d', 'custom'])
    p_process.add_argument('--limit', type=positive)
    p_process.add_argument('--start', type=nonnegative)
    p_process.add_argument('--end', type=nonnegative)
    p_conn = sub.add_parser('connections')
    for name, choices in [('mode', ['capture', 'conntrack']), ('interfaces', ['physical', 'all']),
                          ('scope', ['all', 'wan', 'lan']), ('proto', ['all', 'tcp', 'udp']),
                          ('direction', ['all', 'rx', 'tx'])]:
        p_conn.add_argument('--' + name, choices=choices)
    for name in ('iface', 'owner', 'source', 'dest'):
        p_conn.add_argument('--' + name)
    for name in ('min-bytes', 'min-duration', 'offset'):
        p_conn.add_argument('--' + name, type=nonnegative)
    p_conn.add_argument('--limit', type=positive)
    p_stats = sub.add_parser('container-stats')
    p_stats.add_argument('container_id', type=container_id)
    p_alert = sub.add_parser('alerts')
    p_alert.add_argument('--start', type=nonnegative)
    p_alert.add_argument('--end', type=nonnegative)
    p_alert.add_argument('--limit', type=positive)
    p_upload = sub.add_parser('upload-diagnostics')
    p_upload.add_argument('--date', required=True, type=calendar_date)
    p_rules = sub.add_parser('rules')
    p_rules.add_argument('--kind', required=True, choices=['monitor', 'protection'])
    p_put = sub.add_parser('rule-put')
    p_put.add_argument('--kind', required=True, choices=['monitor', 'protection'])
    p_put.add_argument('--revision', required=True, type=revision_hash)
    p_put.add_argument('--rule-json', required=True, help='JSON rule without credentials')
    p_put.add_argument('--apply', action='store_true', help='execute the requested rule change')
    p_delete = sub.add_parser('rule-delete')
    p_delete.add_argument('--kind', required=True, choices=['monitor', 'protection'])
    p_delete.add_argument('--revision', required=True, type=revision_hash)
    p_delete.add_argument('--id', required=True, type=rule_id)
    p_delete.add_argument('--apply', action='store_true', help='execute the requested rule deletion')
    p_restart = sub.add_parser('container-restart')
    p_restart.add_argument('container_id', type=restart_id)
    p_restart.add_argument('--apply', action='store_true', help='execute the requested restart')
    return p


ROUTES = {
    'health': '/api/health', 'overview': '/api/overview', 'history': '/api/history',
    'processes': '/api/processes', 'connections': '/api/connections',
    'system': '/api/system', 'containers': '/api/docker/containers',
    'alerts': '/api/alerts', 'upload-diagnostics': '/api/diagnostics/upload',
    'tools': '/api/agent/tools',
}


def read_json(opener, url, data=None, mutation=False):
    headers = {'Accept': 'application/json'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST' if data is not None else 'GET')
    try:
        with opener.open(req, timeout=45 if mutation else 15) as response:
            return json.load(response)
    except ClientError:
        if mutation:
            raise ClientError('Mutation outcome unknown; check current state before retrying.') from None
        raise
    except urllib.error.HTTPError as exc:
        if mutation and exc.code >= 500:
            raise ClientError('Mutation outcome unknown; check current state before retrying.') from None
        raise ClientError('Server returned HTTP %d.' % exc.code) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        if mutation:
            raise ClientError('Mutation outcome unknown; check current state before retrying.') from None
        raise ClientError('Network request failed; check the service URL and connection.') from None
    except (ValueError, UnicodeError):
        if mutation:
            raise ClientError('Mutation outcome unknown; check current state before retrying.') from None
        raise ClientError('Server returned invalid JSON.') from None


MONITOR_FIELDS = {'id', 'name', 'metric', 'operator', 'threshold', 'durationSeconds',
                  'scope', 'direction', 'window', 'enabled', 'channelIds', 'channelMode'}
TARGET_FIELDS = {'containerId', 'containerName', 'composeProject', 'composeService', 'composeContainerNumber'}
CONDITION_FIELDS = {'metric', 'operator', 'threshold', 'durationSeconds'}
PROTECTION_FIELDS = {'id', 'name', 'targetMode', 'containers', 'enabled', 'channelIds', 'channelMode',
                     'logic', 'action', 'maxActions', 'cooldownSeconds', 'conditions'} | TARGET_FIELDS


def valid_rule(rule, kind):
    allowed = MONITOR_FIELDS if kind == 'monitor' else PROTECTION_FIELDS
    if not isinstance(rule, dict) or set(rule) - allowed:
        return False
    if not valid_rule_id(rule.get('id')):
        return False
    string_fields = {'id', 'name', 'metric', 'operator', 'scope', 'direction', 'window', 'channelMode',
                     'targetMode', 'logic', 'action'} | TARGET_FIELDS
    integer_fields = {'threshold', 'durationSeconds', 'maxActions', 'cooldownSeconds'}
    if any(key in rule and not isinstance(rule[key], str) for key in string_fields):
        return False
    if any(key in rule and (type(rule[key]) is not int or rule[key] < 0) for key in integer_fields):
        return False
    if 'enabled' in rule and type(rule['enabled']) is not bool:
        return False
    if 'channelIds' in rule and (not isinstance(rule['channelIds'], list) or
                                 not all(isinstance(value, str) for value in rule['channelIds'])):
        return False
    if kind == 'protection':
        for key, fields in [('containers', TARGET_FIELDS), ('conditions', CONDITION_FIELDS)]:
            if key in rule and (not isinstance(rule[key], list) or
                                not all(isinstance(item, dict) and not set(item) - fields for item in rule[key])):
                return False
        if any(not all(isinstance(value, str) for value in item.values()) for item in rule.get('containers', [])):
            return False
        for item in rule.get('conditions', []):
            if any(key in item and not isinstance(item[key], str) for key in ('metric', 'operator')):
                return False
            if any(key in item and (type(item[key]) is not int or item[key] < 0) for key in ('threshold', 'durationSeconds')):
                return False
    return True


def run(args):
    origin = base_url(args.url)
    values = vars(args).copy()
    command = values.pop('command')
    values.pop('url')
    use_stdin = values.pop('password_stdin')
    identifier = values.pop('container_id', None)
    kind = values.pop('kind', None)
    mutation = command in ('rule-put', 'rule-delete', 'container-restart')
    data = None
    if mutation and not values.pop('apply', False):
        raise ClientError('--apply is required for mutations.')
    if command == 'rule-put':
        raw_rule = values.pop('rule_json')
        try:
            if len(raw_rule) > 65536:
                raise ValueError
            rule = json.loads(raw_rule)
        except (ValueError, TypeError):
            raise ClientError('Invalid rule JSON.') from None
        if not valid_rule(rule, kind):
            raise ClientError('Invalid rule JSON.')
        data = {'expectedRevision': values.pop('revision'), 'operation': 'put', 'rule': rule, 'ruleId': None}
    elif command == 'rule-delete':
        data = {'expectedRevision': values.pop('revision'), 'operation': 'delete',
                'rule': None, 'ruleId': values.pop('id')}
    elif command == 'container-restart':
        data = {}
    start, end = values.get('start'), values.get('end')
    if start is not None and end is not None and start >= end:
        raise ClientError('--start must be earlier than --end.')
    if command == 'processes' and ((start is None) != (end is None)):
        raise ClientError('processes requires --start and --end together.')
    if command == 'processes' and values.get('period') == 'custom' and values.get('start') is None:
        raise ClientError('custom period requires --start and --end Unix timestamps.')
    if command == 'container-stats':
        path = '/api/docker/containers/%s/stats' % urllib.parse.quote(identifier, safe='')
    elif command == 'container-restart':
        path = '/api/agent/containers/%s/restart' % identifier
    elif command in ('rules', 'rule-put', 'rule-delete'):
        path = '/api/agent/rules/' + kind
    else:
        path = ROUTES[command]
    params = {k: v for k, v in values.items() if v is not None}
    query = '?' + urllib.parse.urlencode(params) if params else ''
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                         urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    status = read_json(opener, origin + '/api/auth/status')
    if not isinstance(status, dict) or not isinstance(status.get('enabled'), bool) or not isinstance(status.get('authenticated'), bool):
        raise ClientError('Invalid authentication status from server.')
    if status['enabled'] and not status['authenticated']:
        if use_stdin:
            if sys.stdin.isatty():
                raise ClientError('--password-stdin requires a pipe or redirected standard input.')
            password = sys.stdin.readline().rstrip('\r\n')
        elif sys.stdin.isatty():
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', getpass.GetPassWarning)
                    password = getpass.getpass('NAS password: ')
            except getpass.GetPassWarning:
                raise ClientError('Cannot disable terminal echo; password entry cancelled.') from None
        else:
            raise ClientError('Authentication required: use an interactive terminal or --password-stdin.')
        if not password:
            raise ClientError('Empty password is not allowed.')
        login = read_json(opener, origin + '/api/auth/login', {'password': password})
        del password
        if not isinstance(login, dict) or login.get('ok') is not True:
            raise ClientError('Authentication failed.')
    result = read_json(opener, origin + path + query, data, mutation=mutation) if mutation else read_json(opener, origin + path + query)
    if mutation:
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise ClientError('Mutation outcome unknown; check current state before retrying.')
        if command == 'container-restart':
            return {'ok': True, 'action': 'restart', 'containerId': identifier}
        new_revision = result.get('revision')
        if not isinstance(new_revision, str) or not re.fullmatch(r'[0-9a-f]{64}', new_revision):
            raise ClientError('Mutation outcome unknown; check current state before retrying.')
        return {'ok': True, 'revision': new_revision, 'ruleId': data['rule']['id'] if data['rule'] else data['ruleId']}
    if command == 'rules':
        if (not isinstance(result, dict) or not isinstance(result.get('revision'), str) or
                not re.fullmatch(r'[0-9a-f]{64}', result['revision']) or not isinstance(result.get('rules'), list) or
                not all(valid_rule(rule, kind) for rule in result['rules'])):
            raise ClientError('Invalid rules response from server.')
        return {'rules': result['rules'], 'revision': result['revision']}
    if command == 'history' and (not isinstance(result, dict) or
                                 not isinstance(result.get('period'), str) or
                                 not isinstance(result.get('buckets'), list)):
        raise ClientError('Invalid history response from server.')
    if command == 'containers' and (not isinstance(result, dict) or
                                    not isinstance(result.get('containers'), list)):
        raise ClientError('Invalid containers response from server.')
    return result


def main():
    args = parser().parse_args()
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ClientError, EOFError, KeyboardInterrupt) as exc:
        print('ntl: ' + (str(exc) or 'Cancelled.'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
