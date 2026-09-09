import test from 'node:test';
import assert from 'node:assert/strict';
import { updateController } from '../src/desktop/update-controller.js';

test('checks do not overlap and old update resources are released', async () => {
  const state = { phase: 'idle' }; let resolve, closed = 0, checks = 0;
  const api = updateController(state, () => { checks++; return new Promise(r => { resolve = r; }); });
  const pending = api.check(); await api.check(); assert.equal(checks, 1);
  resolve({ version: '1.0.0', close: async () => { closed++; } }); await pending;
  assert.equal(state.version, '1.0.0');
  const next = api.check(); await new Promise(r => setImmediate(r)); resolve(null); await next;
  assert.equal(closed, 1); assert.equal(state.phase, 'current');
});

test('failed download can retry, installation waits for verified download', async () => {
  const state = { phase: 'idle' }; let attempts = 0, installed = 0;
  const api = updateController(state, async () => ({ version: '1.0.0', close: async () => {}, download: async cb => { if (++attempts === 1) throw Error('timeout'); cb({event:'Started',data:{contentLength:5}}); cb({event:'Progress',data:{chunkLength:5}}); }, install: async () => { installed++; } }));
  await api.check(); await api.install(); assert.equal(installed, 0); assert.equal(state.phase, 'available');
  await api.install(); assert.equal(installed, 1); assert.equal(state.phase, 'installed'); assert.equal(state.downloaded, 5);
});
