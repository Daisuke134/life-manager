'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { createMaritimeManagerServer } = require('./server.js');
const UID = 'lm_11111111-1111-4111-8111-111111111111';
const SHA = 'a'.repeat(40);
const config = { tenantId: UID, releaseSha: SHA, modelReady: true };
async function listening(t, deps) {
  const server = createMaritimeManagerServer(deps);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  return `http://127.0.0.1:${server.address().port}`;
}

test('health is pure and chat acknowledges a queued wake without waiting for factory work', async t => {
  const calls = [];
  const base = await listening(t, { config, relayWake: async input => { calls.push(input); return { accepted: true }; } });
  const health = await fetch(base + '/health');
  assert.equal(health.status, 200);
  assert.deepEqual(await health.json(), { ok: true, releaseSha: SHA });
  assert.equal(calls.length, 0);
  const response = await fetch(base + '/chat', { method: 'POST', body: JSON.stringify({ message: 'lm:cycle', source: 'scheduled' }) });
  assert.equal(response.status, 202);
  assert.deepEqual(await response.json(), { response: '処理を受け付けました。結果は日次レポートでお知らせします。' });
  assert.deepEqual(calls, [{ tenantId: UID, releaseSha: SHA, kind: 'cycle' }]);
});

test('ordinary chat and arbitrary commands never become scheduled work', async t => {
  let calls = 0;
  const base = await listening(t, { config, relayWake: async () => { calls++; return { accepted: true }; } });
  for (const body of [
    { message: 'lm:cycle', source: 'front_door' },
    { message: 'run shell command', source: 'scheduled', tenantId: 'other' },
    ...['__proto__', 'constructor', 'toString'].map(message => ({ message, source: 'scheduled' })),
    { message: JSON.stringify({ kind: 'cycle', tenantId: 'other' }), source: 'scheduled' },
  ]) {
    const response = await fetch(base + '/chat', { method: 'POST', body: JSON.stringify(body) });
    assert.equal(response.status, 200);
  }
  assert.equal(calls, 0);
});

test('report wake is bound to configured tenant and release and ignores caller fields', async t => {
  const calls = [];
  const base = await listening(t, { config, relayWake: async input => { calls.push(input); return { accepted: true }; } });
  await fetch(base + '/chat', { method: 'POST', body: JSON.stringify({ source: 'scheduled', message: 'lm:report', tenantId: 'other', releaseSha: 'b'.repeat(40), shell: 'unsafe' }) });
  assert.deepEqual(calls, [{ tenantId: UID, releaseSha: SHA, kind: 'report' }]);
});

test('missing model readiness and missing relay do not claim a working manager', async t => {
  const base = await listening(t, { config: { ...config, modelReady: false } });
  const response = await fetch(base + '/health');
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { ok: false, releaseSha: SHA, errorClass: 'cloud_model_config_missing' });
  const chat = await fetch(base + '/chat', { method: 'POST', body: JSON.stringify({ source: 'scheduled', message: 'lm:cycle' }) });
  assert.equal(chat.status, 503);
});

test('relay refusal and provider exceptions never echo credentials or claim acceptance', async t => {
  for (const relayWake of [async () => ({ accepted: false }), async () => { throw new Error('private-token'); }]) {
    const base = await listening(t, { config, relayWake });
    const response = await fetch(base + '/chat', { method: 'POST', body: JSON.stringify({ source: 'scheduled', message: 'lm:cycle' }) });
    assert.equal(response.status, 503);
    assert.equal((await response.text()).includes('private-token'), false);
  }
});

test('malformed and oversized bodies fail without a relay and unknown routes are closed', async t => {
  let calls = 0;
  const base = await listening(t, { config, relayWake: async () => { calls++; } });
  for (const [body, status] of [['{', 400], ['x'.repeat(8193), 413], ['null', 400], ['{"message":1}', 400]]) {
    assert.equal((await fetch(base + '/chat', { method: 'POST', body })).status, status);
  }
  assert.equal((await fetch(base + '/anything')).status, 404);
  assert.equal((await fetch(base + '/health', { method: 'POST' })).status, 404);
  assert.equal(calls, 0);
});

test('invalid tenant or release is rejected before opening a server', () => {
  assert.throws(() => createMaritimeManagerServer({ config: { ...config, tenantId: '../other' } }), /invalid/);
  assert.throws(() => createMaritimeManagerServer({ config: { ...config, releaseSha: 'main' } }), /invalid/);
});

test('a stalled relay has a bounded response and receives cancellation', async t => {
  let signal;
  const base = await listening(t, { config, relayTimeoutMs: 20, relayWake: async (_input, opts) => {
    signal = opts.signal; return new Promise(() => {});
  } });
  const response = await fetch(base + '/chat', { method: 'POST', body: JSON.stringify({ source: 'scheduled', message: 'lm:cycle' }) });
  assert.equal(response.status, 503);
  assert.equal(signal.aborted, true);
});

test('startup binds the injected port and sends only fixed wake data through the private relay token', async t => {
  const { startMaritimeManagerServer } = require('./server.js');
  const net = require('node:net');
  const reservation = net.createServer().listen(0, '127.0.0.1');
  await once(reservation, 'listening');
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  const calls = [];
  const env = { PORT: String(port), LM_WAKE_RELAY_URL: 'https://manager.example/api/internal/maritime/wake', LM_WAKE_RELAY_TOKEN: 'private-relay-fixture' };
  const server = startMaritimeManagerServer({ env, prepareRuntime: () => ({ config }), fetchImpl: async (...input) => {
    calls.push(input); return { ok: true, json: async () => ({ accepted: true }) };
  } });
  await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  assert.equal(server.address().address, '0.0.0.0');
  const response = await fetch(`http://127.0.0.1:${port}/chat`, { method: 'POST', body: JSON.stringify({ source: 'scheduled', message: 'lm:cycle' }) });
  assert.equal(response.status, 202);
  assert.equal((await response.text()).includes(env.LM_WAKE_RELAY_TOKEN), false);
  assert.equal(calls[0][0], env.LM_WAKE_RELAY_URL);
  assert.equal(calls[0][1].headers.Authorization, `Bearer ${env.LM_WAKE_RELAY_TOKEN}`);
  assert.deepEqual(JSON.parse(calls[0][1].body), { tenantId: UID, releaseSha: SHA, kind: 'cycle' });
  assert.equal(calls[0][1].redirect, 'error');
});
test('startup rejects unsafe relay configuration and never invents a default port', () => {
  const { startMaritimeManagerServer } = require('./server.js');
  for (const env of [{}, { PORT: '0' }, { PORT: 'NaN' },
    { PORT: '8080', LM_WAKE_RELAY_URL: 'http://manager.example/api/internal/maritime/wake', LM_WAKE_RELAY_TOKEN: 'fixture' },
    { PORT: '8080', LM_WAKE_RELAY_URL: 'https://manager.example/other', LM_WAKE_RELAY_TOKEN: 'fixture' }]) {
    assert.throws(() => startMaritimeManagerServer({ env, prepareRuntime: () => ({ config }) }), /invalid/);
  }
});
