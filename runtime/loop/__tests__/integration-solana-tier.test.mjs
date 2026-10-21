// PROP-006, REQ-003 — wake-level integration: currentTier reflects Franklin's REAL fetched Solana
// balance (franklin-loop-revival). Mirrors integration.test.mjs / earn-slot-e2e.test.mjs's existing
// "spawn the real loop + mock the HTTP boundary" convention — the mock here covers BOTH the THINK
// endpoint (OPENAI_BASE_URL, as today) AND the Solana RPC endpoint (SOLANA_RPC_URL, new for this
// feature) so no real network call is made, yet the loop's ACTUAL balance-fetch + tier-select code
// path runs unmodified end-to-end.
//
// RED PHASE: today, index.mjs's `fetchUsdcBalance(walletAddress, config)` throws
// "invalid wallet address" for ANY base58 Solana address (balance.mjs has no Solana branch yet),
// so the catch-block at index.mjs:242-244 keeps `currentTier` at its initial
// `{tier:'broke', model: config.ANICCA_FREE_MODEL}` — the ledger's `model` field on the resulting
// `narrate` wake will show the FREE-tier marker, never the FUNDED-tier marker asserted below.
// Deliberately does NOT set ANICCA_BALANCE_OVERRIDE — that test-only escape hatch bypasses address
// validation entirely and would make this assertion pass WITHOUT REQ-001/REQ-002 actually working,
// which is exactly the "tier gamed without real balance" loophole REQ-003 forbids (see
// behavioral-spec.md REQ-003 edge case on ANICCA_BALANCE_OVERRIDE).
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

// Franklin's real, live Solana wallet address (behavioral-spec.md Context) — used only as an
// address SHAPE here; the RPC response is fully mocked below, no real network call is made.
const SOLANA_ADDR = '8FpqdcCHqjqkVXR58eVJa53neXbJf9emXhvHhgeUPCV9';
const REAL_BALANCE_USDC = 11.63; // matches behavioral-spec.md's "~$11.63" real balance at spec time

function narrateResponse() {
  return JSON.stringify({
    id: 'chatcmpl-test',
    object: 'chat.completion',
    choices: [{ index: 0, message: { role: 'assistant', content: 'idle', tool_calls: undefined }, finish_reason: 'stop' }],
    usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
  });
}

function startChatMock() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      if (req.method === 'POST' && req.url.includes('/chat/completions')) {
        let body = '';
        req.on('data', (d) => { body += d; });
        req.on('end', () => {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(narrateResponse());
        });
      } else {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ object: 'list', data: [] }));
      }
    });
    server.listen(0, '127.0.0.1', () => resolve({ server, url: `http://127.0.0.1:${server.address().port}/v1` }));
  });
}

// Fake Solana JSON-RPC endpoint: getTokenAccountsByOwner -> one ATA holding REAL_BALANCE_USDC.
function startSolanaRpcMock() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let body = '';
      req.on('data', (d) => { body += d; });
      req.on('end', () => {
        let parsed;
        try { parsed = JSON.parse(body); } catch { parsed = {}; }
        let result;
        if (parsed.method === 'getTokenAccountsByOwner') {
          result = {
            value: [{
              account: {
                data: {
                  parsed: {
                    info: {
                      tokenAmount: {
                        amount: String(Math.round(REAL_BALANCE_USDC * 1e6)),
                        decimals: 6,
                        uiAmount: REAL_BALANCE_USDC,
                        uiAmountString: String(REAL_BALANCE_USDC),
                      },
                    },
                  },
                },
              },
            }],
          };
        } else {
          result = null;
        }
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ jsonrpc: '2.0', id: parsed.id ?? 1, result }));
      });
    });
    server.listen(0, '127.0.0.1', () => resolve({ server, url: `http://127.0.0.1:${server.address().port}` }));
  });
}

function readJsonl(p) {
  if (!fs.existsSync(p)) return [];
  return fs.readFileSync(p, 'utf8').split('\n').filter((l) => l.trim())
    .map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
}

function waitFor(pred, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    const iv = setInterval(() => {
      if (pred()) { clearInterval(iv); resolve(true); }
      else if (Date.now() - t0 > timeoutMs) { clearInterval(iv); reject(new Error('timeout waiting for ledger line')); }
    }, 50);
  });
}

test('PROP-006/REQ-003: a real (mocked) Solana balance selects funded context while the brain remains Codex', { timeout: 30000 }, async () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anicca-sol-tier-'));
  fs.mkdirSync(path.join(home, 'identity'), { recursive: true });
  fs.writeFileSync(path.join(home, 'identity', 'genesis.md'), '# Anicca\nautonomous agent.\n');
  const wakeLedger = path.join(home, 'state', 'ledger.jsonl');
  const promptCapture = path.join(home, 'codex-prompt.txt');

  const { server: chatServer, url: chatUrl } = await startChatMock();
  const { server: rpcServer, url: rpcUrl } = await startSolanaRpcMock();

  const proc = spawn(process.execPath, [LOOP_ENTRY], {
    env: {
      ...process.env,
      ANICCA_HOME: home,
      ANICCA_INSTANCE: 'franklin',
      ANICCA_WALLET_ADDRESS: SOLANA_ADDR,
      OPENAI_BASE_URL: chatUrl,
      SOLANA_RPC_URL: rpcUrl,
      // Deliberately ABSENT: ANICCA_BALANCE_OVERRIDE (see file header comment — this is the point).
      LEAN_TIER_THRESHOLD: '1.00',
      SLEEP_BASE_S: '0',
      SLEEP_ERROR_S: '0',
      SLEEP_LOOP_DETECT_S: '0',
      SKILL_TIMEOUT_S: '10',
      LOOP_DETECT_WINDOW: '100',
      ...mockCodexRunnerEnv({ home, baseUrl: chatUrl, capturePromptPath: promptCapture }),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let stderr = '';
  proc.stderr.on('data', (d) => { stderr += d; });

  try {
    await waitFor(() => readJsonl(wakeLedger).some((l) => l.kind === 'narrate'));
    const line = readJsonl(wakeLedger).find((l) => l.kind === 'narrate');
    assert.ok(line, 'expected at least one Codex no-action decision');
    assert.equal(line.model, 'gpt-5.6-terra', `brain must stay Codex (stderr: ${stderr})`);
    assert.match(await fs.promises.readFile(promptCapture, 'utf8'), /Tier: funded/,
      `balance $${REAL_BALANCE_USDC} should select funded context without changing provider`);
  } finally {
    await stopTestLoop(proc);
    chatServer.close();
    rpcServer.close();
  }
});
