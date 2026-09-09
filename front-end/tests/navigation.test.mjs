import test from 'node:test';
import assert from 'node:assert/strict';
import { dockerBookmark, serviceUrl, safeNavigationUrl } from '../src/utils/navigation.js';

test('Docker import uses selected NAS, IPv6 and actual web port', () => {
  const port = { accessMode: 'web', hostPort: 8080, containerPort: 80, scheme: 'https', path: '/ui', proto: 'tcp', label: '控制台' };
  const entry = dockerBookmark({ name: 'qb', containerIcon: '' }, port, '2001:db8::1');
  assert.equal(entry.url, 'https://[2001:db8::1]:8080/ui');
  assert.equal(entry.sourceKey, dockerBookmark({ name: 'qb', id: 'changed' }, port, '2001:db8::1').sourceKey);
  assert.throws(() => dockerBookmark({ name: 'redis' }, { accessMode: 'native', hostPort: 6379 }, 'nas'));
  assert.equal(serviceUrl({ hostPort: 80, path: '//evil.test' }, 'nas'), 'http://nas//evil.test');
});

test('navigation blocks executable URLs and embedded credentials', () => {
  for (const url of ['javascript:alert(1)', 'file:///etc/passwd', 'https://name:pw@nas', '//nas']) assert.equal(safeNavigationUrl(url), '');
  assert.equal(safeNavigationUrl(' http://nas:8088/ui '), 'http://nas:8088/ui');
});
