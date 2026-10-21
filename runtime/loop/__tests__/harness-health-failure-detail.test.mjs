/**
 * harness-health-failure-detail.test.mjs — RED (Phase 2a, feature anicca-harness-tooluse-health).
 * R6 (behavioral-spec.md + verification-architecture.md proof table).
 *
 * Extends index.mjs's existing temp-$ANICCA_HOME integration-test convention (integration.test.mjs):
 * spawns the real loop against a test-only Codex runner, a loopback decision fixture, and mock skills,
 * then inspects the real harness-failures.jsonl file.
 *
 * The test-only Codex runner deliberately discards non-2xx response bodies and returns only a bounded
 * status error class. `capFailureDetail` still proves the shared 4000-character bound directly; tool
 * output length is verified end-to-end below.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { capFailureDetail } from '../harness-health.mjs';
import { mockCodexRunnerEnv, stopTestLoop } from './helpers/mock-codex-runner-env.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LOOP_ENTRY = path.resolve(__dirname, '../index.mjs');

function makeToolCallResponse(slot = 'earn', args = { slot: 'earn' }) {
  return JSON.stringify({
    id: 'chatcmpl-test',
    object: 'chat.completion',
    choices: [{
      index: 0,
      message: {
        role: 'assistant',
        content: null,
        tool_calls: [{
          id: 'call_test',
          type: 'function',
          function: { name: 'run_skill', arguments: JSON.stringify({ slot, ...args }) },
        }],
      },
      finish_reason: 'tool_calls',
    }],
    usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
  });
}

function startMockServer(responseFactory) {
  return new Promise((resolve) => {
    let count = 0;
    const server = http.createServer((req, res) => {
      if (req.method === 'POST' && req.url.includes('/chat/completions')) {
        let body = '';
        req.on('data', (d) => { body += d; });
        req.on('end', () => {
          const resp = responseFactory(count++, body);
          res.writeHead(resp.status || 200, { 'Content-Type': 'application/json' });
          res.end(resp.body);
        });
      } else {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ object: 'list', data: [] }));
      }
    });
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({ server, port, url: `http://127.0.0.1:${port}/v1` });
    });
  });
}

function makeTmpHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anicca-harness-health-test-'));
  fs.mkdirSync(path.join(home, 'identity'), { recursive: true });
  fs.writeFileSync(path.join(home, 'identity', 'genesis.md'), '# Anicca\nTest agent.\n');
  return home;
}

function spawnLoop(env) {
  const codexFixtureEnv = mockCodexRunnerEnv({ home: env.ANICCA_HOME, baseUrl: env.OPENAI_BASE_URL });
  return spawn(process.execPath, [LOOP_ENTRY], {
    env: { ...process.env, ...env, ...codexFixtureEnv },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

function readJsonl(p) {
  if (!fs.existsSync(p)) return [];
  return fs.readFileSync(p, 'utf8')
    .split('\n')
    .filter((l) => l.trim().length > 0)
    .map((l) => { try { return JSON.parse(l); } catch { return null; } })
    .filter(Boolean);
}

function waitFor(fn, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const interval = setInterval(() => {
      const result = fn();
      if (result) { clearInterval(interval); resolve(result); }
      else if (Date.now() - start > timeoutMs) { clearInterval(interval); reject(new Error('waitFor timeout')); }
    }, 50);
  });
}

// ── R6 unit-level: capFailureDetail is the shared cap applied identically to BOTH branches ──

test('R6: capFailureDetail caps at EXACTLY 4000 chars (tool_logic-branch fixture, 6000-char input)', () => {
  const raw = 'x'.repeat(6000);
  const detail = capFailureDetail(raw);
  assert.equal(detail.length, 4000);
});

test('R6: capFailureDetail caps at EXACTLY 4000 chars (brain_transport-branch fixture, 6000-char input) -- resolves FIND-009', () => {
  const raw = 'proxy_down: ' + 'y'.repeat(6000);
  const detail = capFailureDetail(raw);
  assert.equal(detail.length, 4000);
});

test('R6: capFailureDetail whitespace-collapses before capping (same idiom as the existing 900-char `result` cap)', () => {
  const raw = 'a\n\n\tb   c';
  assert.equal(capFailureDetail(raw), 'a b c');
});

// ── R6 integration: brain_transport branch (THINK throws) ───────────────────

test('R6: wake_error wake -> exactly one harness-failures.jsonl line, no slot key, layer:brain_transport', async () => {
  const home = makeTmpHome();
  const failuresPath = path.join(home, 'state', 'harness-failures.jsonl');
  const ledgerPath = path.join(home, 'state', 'ledger.jsonl');
  const recoveryIntentsPath = path.join(home, 'state', 'recovery-intents.jsonl');

  const { server, url } = await startMockServer(() => ({ status: 500, body: JSON.stringify({ error: 'boom' }) }));

  const proc = spawnLoop({
    ANICCA_HOME: home,
    LIFE_MANAGER_LOOP_ID: 'test-loop',
    LIFE_MANAGER_RELEASE_SHA: 'a'.repeat(40),
    LIFE_MANAGER_RECOVERY_INTENTS_PATH: recoveryIntentsPath,
    OPENAI_BASE_URL: url,
    ANICCA_BALANCE_OVERRIDE: '0',
    SLEEP_BASE_S: '0',
    SLEEP_ERROR_S: '0',
    SKILL_TIMEOUT_S: '5',
    LOOP_DETECT_WINDOW: '100',
  });

  try {
    await waitFor(() => readJsonl(ledgerPath).some((l) => l.kind === 'wake_error') || null);
    await waitFor(() => readJsonl(failuresPath).length > 0 || null);
    await waitFor(() => readJsonl(recoveryIntentsPath).length > 0 || null);
    await stopTestLoop(proc);
    await new Promise((r) => setTimeout(r, 300));

    const lines = readJsonl(failuresPath);
    assert.equal(lines.length, 1, 'exactly one harness-failures.jsonl line for the one wake_error wake');
    const line = lines[0];
    assert.equal('slot' in line, false, 'brain_transport failures never carry a slot key');
    assert.equal(line.layer, 'brain_transport');
    assert.equal(line.kind, 'wake_error');
    assert.ok(line.detail.length <= 4000);
    assert.ok('ts' in line && 'wake_id' in line && 'exit_code' in line);
    assert.equal(line.recovery_intent.loop_id, 'test-loop');
    assert.equal(line.recovery_intent.action, 'reconcile_owner');
    assert.equal(line.recovery_intent.mutates_external_effect, false);
    const queued = readJsonl(recoveryIntentsPath);
    assert.equal(queued.length, 1);
    assert.equal(queued[0].record_type, 'recovery_intent');
    assert.equal(queued[0].intent_id, line.recovery_intent.intent_id);
    assert.equal(fs.statSync(recoveryIntentsPath).mode & 0o777, 0o600);
  } finally {
    server.close();
    await stopTestLoop(proc);
    fs.rmSync(home, { recursive: true, force: true });
  }
});

test('R6: Codex transport failure never imports a provider response body containing a private key', async () => {
  const home = makeTmpHome();
  const failuresPath = path.join(home, 'state', 'harness-failures.jsonl');
  const privKey = '0x' + 'a'.repeat(64);

  // The fake Codex runner receives this response only on loopback and must not forward its body.
  const { server, url } = await startMockServer(() => ({
    status: 500,
    body: JSON.stringify({ error: `leaked key ${privKey} in response` }),
  }));

  const proc = spawnLoop({
    ANICCA_HOME: home,
    OPENAI_BASE_URL: url,
    ANICCA_BALANCE_OVERRIDE: '0',
    SLEEP_BASE_S: '0',
    SLEEP_ERROR_S: '0',
    SKILL_TIMEOUT_S: '5',
    LOOP_DETECT_WINDOW: '100',
  });

  try {
    await waitFor(() => readJsonl(failuresPath).length > 0 || null);
    await stopTestLoop(proc);
    await new Promise((r) => setTimeout(r, 300));

    const lines = readJsonl(failuresPath);
    const line = lines[0];
    assert.ok(!line.detail.includes(privKey), 'raw private key must never appear in detail');
    assert.equal(line.detail, 'codex_brain_failed:fixture_http_500');
  } finally {
    server.close();
    await stopTestLoop(proc);
    fs.rmSync(home, { recursive: true, force: true });
  }
});

// ── R6 integration: tool_logic branch (skill_error, exit 1) ─────────────────

test('R6: skill_error wake with >2000-char stdout -> detail LONGER than 900 chars, ledger result STILL capped at 900 (they genuinely diverge)', async () => {
  const home = makeTmpHome();
  const failuresPath = path.join(home, 'state', 'harness-failures.jsonl');
  const ledgerPath = path.join(home, 'state', 'ledger.jsonl');

  const longOutput = 'z'.repeat(2500);
  const mockSkillPath = path.join(os.tmpdir(), `mock-r6-long-${Date.now()}.sh`);
  fs.writeFileSync(mockSkillPath, `#!/bin/sh\nprintf '%s' '${longOutput}'\nexit 1\n`);
  fs.chmodSync(mockSkillPath, 0o755);

  const { server, url } = await startMockServer(() => ({ status: 200, body: makeToolCallResponse('earn', { slot: 'earn' }) }));

  const proc = spawnLoop({
    ANICCA_HOME: home,
    OPENAI_BASE_URL: url,
    ANICCA_BALANCE_OVERRIDE: '0',
    SLEEP_BASE_S: '0',
    SLEEP_ERROR_S: '0',
    SKILL_TIMEOUT_S: '10',
    LOOP_DETECT_WINDOW: '100',
    ANICCA_EARN_SKILL: mockSkillPath,
  });

  try {
    await waitFor(() => readJsonl(ledgerPath).some((l) => l.kind === 'skill_error') || null);
    await waitFor(() => readJsonl(failuresPath).length > 0 || null);
    await stopTestLoop(proc);
    await new Promise((r) => setTimeout(r, 300));

    const failureLines = readJsonl(failuresPath);
    const failLine = failureLines.find((l) => l.layer === 'tool_logic');
    assert.ok(failLine, 'expected a tool_logic harness-failures.jsonl line');
    assert.ok(failLine.detail.length > 900, `detail must exceed the 900-char result cap, got ${failLine.detail.length}`);
    assert.equal(failLine.slot, 'earn');
    assert.ok('exit_code' in failLine);

    const ledgerLines = readJsonl(ledgerPath);
    const skillErrorLine = ledgerLines.find((l) => l.kind === 'skill_error');
    assert.ok(skillErrorLine, 'expected a skill_error ledger line');
    assert.ok(skillErrorLine.result.length <= 900, `ledger result must stay capped at 900, got ${skillErrorLine.result.length}`);
    assert.notEqual(skillErrorLine.result.length, failLine.detail.length, 'result and detail must genuinely diverge in length on this fixture');
  } finally {
    server.close();
    await stopTestLoop(proc);
    fs.rmSync(home, { recursive: true, force: true });
    fs.rmSync(mockSkillPath, { force: true });
  }
});

test('R6: skill_error wake with >4000-char stdout -> detail length EXACTLY 4000 (resolves FIND-008)', async () => {
  const home = makeTmpHome();
  const failuresPath = path.join(home, 'state', 'harness-failures.jsonl');

  const hugeOutput = 'q'.repeat(6000);
  const mockSkillPath = path.join(os.tmpdir(), `mock-r6-huge-${Date.now()}.sh`);
  fs.writeFileSync(mockSkillPath, `#!/bin/sh\nprintf '%s' '${hugeOutput}'\nexit 1\n`);
  fs.chmodSync(mockSkillPath, 0o755);

  const { server, url } = await startMockServer(() => ({ status: 200, body: makeToolCallResponse('earn', { slot: 'earn' }) }));

  const proc = spawnLoop({
    ANICCA_HOME: home,
    OPENAI_BASE_URL: url,
    ANICCA_BALANCE_OVERRIDE: '0',
    SLEEP_BASE_S: '0',
    SLEEP_ERROR_S: '0',
    SKILL_TIMEOUT_S: '10',
    LOOP_DETECT_WINDOW: '100',
    ANICCA_EARN_SKILL: mockSkillPath,
  });

  try {
    await waitFor(() => readJsonl(failuresPath).length > 0 || null);
    await stopTestLoop(proc);
    await new Promise((r) => setTimeout(r, 300));

    const failLine = readJsonl(failuresPath).find((l) => l.layer === 'tool_logic');
    assert.ok(failLine);
    assert.equal(failLine.detail.length, 4000, 'detail must be capped at EXACTLY 4000, neither uncapped nor wrongly capped');
  } finally {
    server.close();
    await stopTestLoop(proc);
    fs.rmSync(home, { recursive: true, force: true });
    fs.rmSync(mockSkillPath, { force: true });
  }
});

// ── R6 regression guard: clean wake appends NOTHING, result cap unchanged (INV-NO-PROMPT-REGRESSION) ──

test('R6: clean wake -> ZERO lines appended to harness-failures.jsonl; ledger result stays <=900 (INV-NO-PROMPT-REGRESSION)', async () => {
  const home = makeTmpHome();
  const failuresPath = path.join(home, 'state', 'harness-failures.jsonl');
  const ledgerPath = path.join(home, 'state', 'ledger.jsonl');

  const mockSkillPath = path.join(os.tmpdir(), `mock-r6-clean-${Date.now()}.sh`);
  fs.writeFileSync(mockSkillPath, '#!/bin/sh\necho "[earn] discover wake=test"\nexit 0\n');
  fs.chmodSync(mockSkillPath, 0o755);

  const { server, url } = await startMockServer((count) => {
    if (count >= 3) return { status: 200, body: JSON.stringify({ id: 'x', choices: [{ index: 0, message: { role: 'assistant', content: 'done' }, finish_reason: 'stop' }], usage: {} }) };
    return { status: 200, body: makeToolCallResponse('earn', { slot: 'earn' }) };
  });

  const proc = spawnLoop({
    ANICCA_HOME: home,
    OPENAI_BASE_URL: url,
    ANICCA_BALANCE_OVERRIDE: '0',
    SLEEP_BASE_S: '0',
    SLEEP_ERROR_S: '0',
    SKILL_TIMEOUT_S: '5',
    LOOP_DETECT_WINDOW: '100',
    ANICCA_EARN_SKILL: mockSkillPath,
  });

  try {
    await waitFor(() => (readJsonl(ledgerPath).filter((l) => l.kind === 'wake').length >= 3 ? true : null));
    await stopTestLoop(proc);
    await new Promise((r) => setTimeout(r, 300));

    const failureLines = readJsonl(failuresPath);
    assert.equal(failureLines.length, 0, 'clean wakes must append nothing to harness-failures.jsonl');

    const wakeLines = readJsonl(ledgerPath).filter((l) => l.kind === 'wake');
    assert.ok(wakeLines.length > 0);
    for (const wl of wakeLines) {
      if (wl.result != null) {
        assert.ok(wl.result.length <= 900, `pre-existing result cap (task #119) must stay at 900, got ${wl.result.length}`);
      }
    }
  } finally {
    server.close();
    await stopTestLoop(proc);
    fs.rmSync(home, { recursive: true, force: true });
    fs.rmSync(mockSkillPath, { force: true });
  }
});
