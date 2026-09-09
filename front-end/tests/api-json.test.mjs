import test from 'node:test';
import assert from 'node:assert/strict';
import { readApiJson } from '../src/api/json.js';
import { navigationRepository } from '../src/api/navigation.js';
test('HTML fallback and text 500 errors never escape as JSON parse errors', async () => {
  await assert.rejects(readApiJson(new Response('<!doctype html><html>index</html>')), e => e.code === 'NON_JSON_RESPONSE' && !e.message.includes('<html>'));
  await assert.rejects(readApiJson(new Response('Internal Server Error', { status: 500 })), /500/);
});
test('old NAS navigation is reported as a missing capability', async () => {
  const repository = navigationRepository(() => readApiJson(new Response('<html>old NAS</html>')), {});
  await assert.rejects(repository.list(), e => e.code === 'NAVIGATION_UNAVAILABLE' && e.message.includes('2026.09.09-2'));
});
test('authentication and structured validation errors preserve their meaning', async () => {
  let expired = false;
  await assert.rejects(readApiJson(new Response('{}', {status:401}), () => { expired = true; }), /重新登录/);
  assert.equal(expired,true);
  await assert.rejects(readApiJson(new Response('{"detail":[{"msg":"invalid"}]}', {status:422})), e=> e.status===422 && Array.isArray(e.detail));
});
