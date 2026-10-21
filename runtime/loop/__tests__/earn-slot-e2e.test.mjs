// NO-MOCK E2E (REQ-6): the REAL loop process picks a per-method earn slot (earn/_probe), spawns its REAL
// run.sh, which receives EARN_LEDGER+WAKE_ID (GAP-B) and writes the earn-ledger line the classify gate reads
// (GAP-A). Only the BRAIN is the standard mock-server (the slot wiring is what's under test, not the model).
// Run: node --test runtime/loop/__tests__/earn-slot-e2e.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mockCodexRunnerEnv, stopTestLoop } from './helpers/mock-codex-runner-env.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LOOP_ENTRY = path.resolve(__dirname, '../index.mjs');
const STUB_SRC = path.resolve(__dirname, '../../../skills/earn/_probe/run.sh');

function toolCall(slot) {
  return JSON.stringify({ id: 'c', object: 'chat.completion', choices: [{ index: 0, message: { role: 'assistant', content: null, tool_calls: [{ id: 'call', type: 'function', function: { name: 'run_skill', arguments: JSON.stringify({ slot }) } }] }, finish_reason: 'tool_calls' }], usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 } });
}
function narrate() {
  return JSON.stringify({ id: 'c', object: 'chat.completion', choices: [{ index: 0, message: { role: 'assistant', content: 'idle', tool_calls: undefined }, finish_reason: 'stop' }], usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 } });
}
function startMock() {
  return new Promise((resolve) => {
    let count = 0;
    const server = http.createServer((req, res) => {
      if (req.method === 'POST' && req.url.includes('/chat/completions')) {
        let b = ''; req.on('data', d => b += d); req.on('end', () => {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(count++ === 0 ? toolCall('earn/_probe') : narrate());
        });
      } else { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end('{"object":"list","data":[]}'); }
    });
    server.listen(0, '127.0.0.1', () => resolve({ server, url: `http://127.0.0.1:${server.address().port}/v1` }));
  });
}
const readJsonl = (p) => fs.existsSync(p) ? fs.readFileSync(p, 'utf8').split('\n').filter(l => l.trim()).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean) : [];
function waitFor(pred, timeoutMs = 15000) {
  return new Promise((resolve, reject) => { const t0 = Date.now(); const iv = setInterval(() => { if (pred()) { clearInterval(iv); resolve(true); } else if (Date.now() - t0 > timeoutMs) { clearInterval(iv); reject(new Error('timeout')); } }, 50); });
}

test('E2E: real loop picks earn/_probe → stub gets EARN_LEDGER+WAKE_ID → earn-ledger line → wake ledger slot=earn/_probe', { timeout: 30000 }, async () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anicca-earnslot-'));
  fs.mkdirSync(path.join(home, 'identity'), { recursive: true });
  fs.writeFileSync(path.join(home, 'identity', 'genesis.md'), '# Anicca\nautonomous agent.\n');
  fs.mkdirSync(path.join(home, 'skills', 'earn', '_probe'), { recursive: true });
  fs.copyFileSync(STUB_SRC, path.join(home, 'skills', 'earn', '_probe', 'run.sh'));
  fs.chmodSync(path.join(home, 'skills', 'earn', '_probe', 'run.sh'), 0o755);
  const earnLedger = path.join(home, 'earn-ledger.jsonl');
  const wakeLedger = path.join(home, 'state', 'ledger.jsonl');

  const { server, url } = await startMock();
  const proc = spawn(process.execPath, [LOOP_ENTRY], {
    env: { ...process.env, ANICCA_HOME: home, OPENAI_BASE_URL: url,
      ...mockCodexRunnerEnv({ home, baseUrl: url }), ANICCA_BALANCE_OVERRIDE: '0',
      SLEEP_BASE_S: '0', SLEEP_ERROR_S: '0', SLEEP_LOOP_DETECT_S: '0', SKILL_TIMEOUT_S: '10',
      LOOP_DETECT_WINDOW: '100', EARN_LEDGER: earnLedger },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  try {
    await waitFor(() => readJsonl(wakeLedger).some(l => l.slot === 'earn/_probe'));
    const wakeLine = readJsonl(wakeLedger).find(l => l.slot === 'earn/_probe');
    assert.ok(wakeLine, 'wake ledger has a slot=earn/_probe line');
    // GAP-B proof: the stub only writes the earn-ledger line if it received EARN_LEDGER + WAKE_ID
    const earnLines = readJsonl(earnLedger);
    assert.ok(earnLines.length >= 1, 'stub wrote an earn-ledger line (⇒ it received EARN_LEDGER)');
    const el = earnLines[0];
    assert.equal(el.source, '_probe');
    assert.equal(el.strategy, '_probe', 'EARN_STRATEGY=_probe reached the child (earnStrategyFor)');
    assert.equal(el.wake, wakeLine.wake_id, 'earn-ledger correlates by wake===WAKE_ID (GAP-A classify path)');
    assert.equal(el.earn_usdc, 0.01);
  } finally {
    await stopTestLoop(proc);
    server.close();
  }
});

test('E2E: forced earn/<sub> with NO run.sh → skill_missing (not crash) (REQ-6)', { timeout: 30000 }, async () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anicca-earnmiss-'));
  fs.mkdirSync(path.join(home, 'identity'), { recursive: true });
  fs.writeFileSync(path.join(home, 'identity', 'genesis.md'), '# Anicca\nautonomous agent.\n');
  // NOTE: deliberately do NOT create skills/earn/_gone/run.sh
  const wakeLedger = path.join(home, 'state', 'ledger.jsonl');
  const { server, url } = await (async () => {
    let count = 0;
    const s = http.createServer((req, res) => {
      if (req.method === 'POST' && req.url.includes('/chat/completions')) { let b = ''; req.on('data', d => b += d); req.on('end', () => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(count++ === 0 ? toolCall('earn/_gone') : narrate()); }); }
      else { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end('{"object":"list","data":[]}'); }
    });
    return new Promise(r => s.listen(0, '127.0.0.1', () => r({ server: s, url: `http://127.0.0.1:${s.address().port}/v1` })));
  })();
  const proc = spawn(process.execPath, [LOOP_ENTRY], { env: { ...process.env, ANICCA_HOME: home, OPENAI_BASE_URL: url,
    ...mockCodexRunnerEnv({ home, baseUrl: url }), ANICCA_BALANCE_OVERRIDE: '0', SLEEP_BASE_S: '0', SLEEP_ERROR_S: '0',
    SLEEP_LOOP_DETECT_S: '0', SKILL_TIMEOUT_S: '10', LOOP_DETECT_WINDOW: '100' }, stdio: ['ignore', 'pipe', 'pipe'] });
  try {
    await waitFor(() => readJsonl(wakeLedger).some(l => l.slot === 'earn/_gone'));
    const line = readJsonl(wakeLedger).find(l => l.slot === 'earn/_gone');
    assert.equal(line.kind, 'skill_missing', 'missing earn/<sub> run.sh → skill_missing, not a crash');
  } finally { await stopTestLoop(proc); server.close(); }
});
