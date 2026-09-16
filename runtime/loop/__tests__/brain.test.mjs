/**
 * brain.test.mjs — thinkProxy/httpPost must not swallow HTTP-level error responses.
 *
 * Root cause (agent-economy #F1, 2026-07-06; confirmed still live in brain.mjs 2026-07-07):
 * Franklin's free-model brain (`franklin proxy` -> sol.blockrun.ai) intermittently
 * 403/429s ("NVIDIA API error: 403 Forbidden Authorization failed" / rate-limit) —
 * confirmed live and TRANSIENT. brain.mjs already has a retry loop (3 attempts, 2s
 * back-off) built for exactly this, but httpPost() previously resolved on ANY
 * response regardless of status code — so a non-2xx error body got JSON.parse'd and
 * returned as if it were a valid completion, and the retry loop never fired because
 * no exception was thrown. Live symptom: every masked failure surfaced as a harmless
 * "narrate" wake instead of wake_error, hiding the real failure rate entirely.
 *
 * Contract: httpPost must reject on non-2xx so thinkProxy's existing retry loop
 * actually engages; think() must eventually surface a real completion if a later
 * attempt succeeds, and must throw (not return a garbage "completion") if every
 * attempt keeps failing.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { think, runCodexAgentWithTimeout } from '../brain.mjs';

const baseCtx = (over) => ({
  wakeId: 'W1', walletAddress: '0xabc', balanceUsdc: 1.23, tier: 'lean',
  model: 'nvidia/llama-4-maverick', positionsSummary: '', recentSlots: [],
  recentLedgerLines: [], activeSkillSlots: [], skillCatalog: {}, ...over,
});

// Starts a server whose response sequence is driven by `statuses` (one entry
// consumed per request; the last entry repeats if more requests arrive than
// entries). Non-2xx entries return the real BlockRun/NVIDIA passthrough shape
// captured live; 200 entries return a minimal valid chat/completions body.
function startMockProxy(statuses) {
  let i = 0;
  const server = http.createServer((req, res) => {
    const status = statuses[Math.min(i, statuses.length - 1)];
    i += 1;
    res.writeHead(status, { 'Content-Type': 'application/json' });
    if (status >= 200 && status < 300) {
      res.end(JSON.stringify({
        id: 'msg_test', choices: [{ message: { role: 'assistant', content: 'ok' } }],
      }));
    } else {
      res.end(JSON.stringify({
        type: 'error',
        error: { type: 'api_error', message: 'NVIDIA API error: 403 {"status":403,"title":"Forbidden","detail":"Authorization failed"}' },
      }));
    }
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({ server, requestCount: () => i }));
  });
}

test('think(): all attempts 403 -> throws instead of returning the error body as a completion', async () => {
  const { server } = await startMockProxy([403, 403, 403]);
  try {
    const { port } = server.address();
    await assert.rejects(
      () => think(baseCtx(), { ANICCA_BRAIN: 'proxy', OPENAI_BASE_URL: `http://127.0.0.1:${port}/v1` }),
    );
  } finally {
    server.close();
  }
});

test('think(): transient 403s then 200 -> retry loop recovers a real completion', async () => {
  const { server, requestCount } = await startMockProxy([403, 403, 200]);
  try {
    const { port } = server.address();
    const result = await think(baseCtx(), { ANICCA_BRAIN: 'proxy', OPENAI_BASE_URL: `http://127.0.0.1:${port}/v1` });
    assert.equal(result.choices[0].message.content, 'ok');
    assert.equal(requestCount(), 3); // proves it actually retried past the two 403s
  } finally {
    server.close();
  }
});

test('think(): all attempts 429 (rate-limit) -> throws instead of masking as a narrate-able empty completion', async () => {
  const { server } = await startMockProxy([429, 429, 429]);
  try {
    const { port } = server.address();
    await assert.rejects(
      () => think(baseCtx(), { ANICCA_BRAIN: 'proxy', OPENAI_BASE_URL: `http://127.0.0.1:${port}/v1` }),
    );
  } finally {
    server.close();
  }
});

// --- claude-p never falls back to the proxy (2026-07-13, Dais) --------------------------------
// claude-p is human-funded: the subscription brain is already paid for, and its crypto wallet is
// for TRADING, not for buying inference. The old fallback silently handed money decisions to a
// free model that could not even issue the tool call ("run_skill skill not found"). A wake that
// fails loudly and retries beats a wake decided by the wrong brain.
test('ANICCA_BRAIN=claude-p throws instead of falling back to the proxy', async () => {
  const config = {
    ANICCA_BRAIN: 'claude-p',
    CLAUDE_BIN: '/nonexistent/claude-binary-that-cannot-exist',
    // A proxy that would answer if we ever fell through to it — we must NEVER reach it.
    OPENAI_BASE_URL: 'http://127.0.0.1:1/v1',
  };

  await assert.rejects(
    () => think(baseCtx(), config),
    (err) => /claude_not_found|claude_exit|claude_p_timeout|claude_empty|claude_invalid/.test(err.message),
    'claude-p failure must surface as a claude-p error, never as a silent proxy answer',
  );
});

test('Codex brain runner enforces its timeout and returns bounded process output', async () => {
  const result = await runCodexAgentWithTimeout(
    process.execPath,
    ['-e', 'process.stdin.resume(); process.stdin.on("end", () => process.stdout.write("ok"));'],
    { env: process.env, cwd: '/tmp', input: 'prompt', timeoutMs: 5_000 },
  );
  assert.equal(result.code, 0);
  assert.equal(result.stdout, 'ok');
  await assert.rejects(
    () => runCodexAgentWithTimeout(
      process.execPath,
      ['-e', 'setTimeout(() => {}, 60_000)'],
      { env: process.env, cwd: '/tmp', input: '', timeoutMs: 25 },
    ),
    /codex_brain_timeout/,
  );
});
