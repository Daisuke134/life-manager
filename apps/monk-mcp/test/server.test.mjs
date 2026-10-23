import test from 'node:test';
import assert from 'node:assert/strict';
import { handle } from '../src/server.mjs';
const call = async (body) => (await handle(new Request('https://x/mcp', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }))).json();
test('initialize + tools/list', async () => {
  assert.equal((await call({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18' } })).result.serverInfo.name, 'anicca-monk-db');
  const names = (await call({ jsonrpc: '2.0', id: 2, method: 'tools/list' })).result.tools.map((t) => t.name);
  assert.deepEqual(names, ['search_teachings', 'get_teaching', 'daily_dhamma']);
});
test('search finds anger verses with source', async () => {
  const r = (await call({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'search_teachings', arguments: { query: 'anger', limit: 3 } } })).result.structuredContent;
  assert.ok(r.total > 0); assert.match(r.results[0].source_url, /^https:\/\/suttacentral\.net\//);
});
test('get_teaching dhp1 and not found', async () => {
  const ok = (await call({ jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'get_teaching', arguments: { id: 'dhp1' } } })).result;
  assert.match(ok.structuredContent.text, /Intention is the leader/);
  const nf = (await call({ jsonrpc: '2.0', id: 5, method: 'tools/call', params: { name: 'get_teaching', arguments: { id: 'zzz' } } })).result;
  assert.equal(nf.isError, true);
});
test('daily_dhamma is deterministic', async () => {
  const a = (await call({ jsonrpc: '2.0', id: 6, method: 'tools/call', params: { name: 'daily_dhamma', arguments: { date: '2026-10-24' } } })).result.structuredContent;
  const b = (await call({ jsonrpc: '2.0', id: 7, method: 'tools/call', params: { name: 'daily_dhamma', arguments: { date: '2026-10-24' } } })).result.structuredContent;
  assert.equal(a.teaching.id, b.teaching.id);
});
test('GET /mcp is 405, notification is 202', async () => {
  assert.equal((await handle(new Request('https://x/mcp'))).status, 405);
  assert.equal((await handle(new Request('https://x/mcp', { method: 'POST', body: '{"jsonrpc":"2.0","method":"notifications/initialized"}' }))).status, 202);
});
