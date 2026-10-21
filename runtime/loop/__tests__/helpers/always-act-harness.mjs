// always-act-harness.mjs — shared, non-test helper module for
// franklin-alwaysact-skill-router's Phase 2a integration tests.
//
// NOT a *.test.mjs file on purpose: runtime/loop/package.json's `test`/`test:unit`/`test:integration`
// scripts (and this feature's own additions to them) enumerate test files EXPLICITLY by name, so a
// helper module without the `.test.` infix is never accidentally picked up as its own test file, and
// `node --test` (glob-based CI runs) would also skip it since it does not match `*.test.mjs`.
//
// Mirrors the existing integration pattern (test Codex runner + loopback decision server + tmp
// ANICCA_HOME + waitForLines) — extended with Codex prompt capture (for PROP-504b's bounded menu
// assertion) and Solana identity fixtures (REQ-501's own identity-match guard idiom,
// mirroring runtime/loop/__tests__/wallet-address-solana.test.mjs).
//
// Test-Money Safety Rule (behavioral-spec.md sec5 / verification-architecture.md): every wallet used
// here is a FRESH, randomly generated, unfunded keypair (Keypair.generate()) — never Franklin's real
// production secret at /home/life-manager/.blockrun, never any real network/RPC/x402 call. Skill execution
// is always a mock script under a temporary skills root, never a real skills/*/run.sh.

import { promises as fsp } from 'node:fs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { mockCodexRunnerEnv } from './mock-codex-runner-env.mjs';
import { Keypair } from '@solana/web3.js';
import bs58 from 'bs58';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const LOOP_ENTRY = path.resolve(__dirname, '../../index.mjs');
export const REPO_ROOT = path.resolve(__dirname, '../../../..');

// ── Tmp-home / fixture-file helpers ─────────────────────────────────────────

export function makeTmpHome(prefix = 'always-act-test-') {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

export function writeGenesis(home, text = '# Anicca\nYou are Franklin, an autonomous earning agent.\n') {
  fs.mkdirSync(path.join(home, 'identity'), { recursive: true });
  fs.writeFileSync(path.join(home, 'identity', 'genesis.md'), text);
}

/**
 * Write an executable mock skill script at $home/skills/<slot>/run.sh.
 * `slot` may contain a single '/' (e.g. 'economy/gig', 'earn/sol-trade') — mirrors
 * run-skill.mjs::resolveSkillPath's `slot.replace('/', path.sep)` join.
 *
 * @param {string} home - tmp ANICCA_HOME
 * @param {string} slot
 * @param {string} scriptBody - shell script body (no shebang; this helper adds one)
 */
export function writeMockSkill(home, slot, scriptBody) {
  const skillDir = path.join(home, 'skills', ...slot.split('/'));
  fs.mkdirSync(skillDir, { recursive: true });
  const runPath = path.join(skillDir, 'run.sh');
  fs.writeFileSync(runPath, `#!/bin/sh\n${scriptBody}\n`);
  fs.chmodSync(runPath, 0o755);
  return runPath;
}

/**
 * A mock skill that, when WAKE_ID matches `realizeForWakeId`, appends a matching earn-ledger line
 * (a "realized economic result" per REQ-506/earn-detect.mjs's classifyEarnResult contract: a line
 * with `wake === WAKE_ID`). When it does NOT match (or `realizeForWakeId` is null), it exits 0 with
 * no ledger write — REQ-506's "no realized action" / neutral-signal-WAIT case.
 *
 * The written line's shape matches skills/_shared/lib/ledger.mjs::isProfitable's REAL, unmodified
 * contract (net_usdc>0 AND a real confirmation receipt AND external===true AND source not a swap) —
 * not merely a decorative `profitable` field — so `profitable:true` fixtures actually classify as
 * profitable through the SAME classifyEarnResult/isProfitable this feature reuses unmodified
 * (REQ-506), exactly as a real Solana-settled earn action would (sig + confirmed:true; a fake but
 * well-formed signature string, never a real on-chain signature).
 */
export function writeMockEarnSkill(home, slot, { realizeForWakeId = null, profitable = true } = {}) {
  const ledgerPath = path.join(home, 'skills', 'earn', 'state', 'earn-ledger.jsonl');
  fs.mkdirSync(path.dirname(ledgerPath), { recursive: true });
  const realismFields = profitable
    ? ',"net_usdc":0.01,"external":true,"sig":"mockAlwaysActFixtureSig1111111111111111111111111111111111111111","confirmed":true'
    : ',"net_usdc":0';
  const wakeGuard = realizeForWakeId === '*'
    ? '[ -n "$WAKE_ID" ]'
    : `[ "$WAKE_ID" = "${realizeForWakeId}" ]`;
  const body = realizeForWakeId
    ? `if ${wakeGuard}; then\n` +
      `  printf '%s\\n' '{"wake":"'"$WAKE_ID"'","slot":"${slot}","profitable":${profitable ? 'true' : 'false'},"earn_usdc":${profitable ? '0.01' : '0'}${realismFields}}' >> "${ledgerPath}"\n` +
      `fi\n` +
      `echo "[${slot}] mock earn skill ran wake=$WAKE_ID"\nexit 0`
    : `echo "[${slot}] mock earn skill ran wake=$WAKE_ID (no-op, no ledger line)"\nexit 0`;
  return writeMockSkill(home, slot, body);
}

/** A guard-blocked mock skill (mirrors sol-trade/run.sh's kill-switch `action:"skip"` trace — exits 0,
 * writes NOTHING to earn-ledger.jsonl, so classifyEarnResult sees earnLine===null every time.) */
export function writeMockGuardBlockedSkill(home, slot, reason = 'kill-switch') {
  return writeMockSkill(home, slot, `echo '{"action":"skip","reason":"${reason}"}'\nexit 0`);
}

/**
 * Writes a well-formed, zero-live-slot `registry.json` fixture (`{"slots":{}}`) under `home` and
 * returns its absolute path — pair with `ALWAYS_ACT_REGISTRY_PATH_OVERRIDE` (index.mjs's test-only
 * env seam, same idiom as `ANICCA_BALANCE_OVERRIDE`) to drive REQ-502's empty-menu terminal case
 * through a REAL spawned wake (PROP-502d), rather than only the pure `assembleAlwaysActMenu` unit
 * test. `liveSlotNames`/`assembleAlwaysActMenu` both resolve `{"slots":{}}` to `[]` cleanly (no
 * parse-error fallback path involved) — a genuine, coherent "zero live earn-action slots" registry,
 * not a malformed-JSON crash.
 */
export function writeEmptyRegistry(home) {
  const dir = path.join(home, 'fixtures');
  fs.mkdirSync(dir, { recursive: true });
  const registryPath = path.join(dir, 'empty-registry.json');
  fs.writeFileSync(registryPath, JSON.stringify({ slots: {} }, null, 2));
  return registryPath;
}

/**
 * Writes a registry.json fixture whose live slots are EXACTLY the given `{name: riskTag}` set (pair
 * with `ALWAYS_ACT_REGISTRY_PATH_OVERRIDE`, the same test-only seam `writeEmptyRegistry` uses) — lets
 * PROP-506f construct a REAL, reachable always-act menu where every OTHER live slot besides the
 * just-picked one is `risk:"capital"` (the risk-free-filtered reroute set is genuinely empty, driven
 * through a real spawned wake — not merely a pure `assembleAlwaysActMenu` return-value stand-in).
 *
 * @param {string} home
 * @param {Record<string, string>} slotsWithRisk - e.g. `{ 'earn/sol-trade': 'capital', hl_trade: 'capital' }`
 * @returns {string} absolute path to the written registry.json fixture
 */
export function writeRiskTaggedRegistry(home, slotsWithRisk) {
  const dir = path.join(home, 'fixtures');
  fs.mkdirSync(dir, { recursive: true });
  const registryPath = path.join(dir, 'risk-tagged-registry.json');
  const slots = {};
  for (const [name, risk] of Object.entries(slotsWithRisk || {})) {
    slots[name] = { status: 'live', risk };
  }
  fs.writeFileSync(registryPath, JSON.stringify({ slots }, null, 2));
  return registryPath;
}

// ── Solana identity fixtures (REQ-501) ──────────────────────────────────────
// Fresh, randomly generated, UNFUNDED keypairs only — never Franklin's real production secret.

export function generateSolanaKeypair() {
  const kp = Keypair.generate();
  return { secretBase58: bs58.encode(kp.secretKey), address: kp.publicKey.toBase58() };
}

/** Writes $legacyHome/.blockrun/.solana-session — the ONLY path resolve-identity.mjs::resolveSolanaSecret
 * honors, and ONLY when the caller's ANICCA_HOME === path.join(legacyHome, '.blockrun') exactly. */
export function writeBlockrunSession(legacyHome, secretBase58) {
  const dir = path.join(legacyHome, '.blockrun');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, '.solana-session'), secretBase58);
  return dir; // === the ANICCA_HOME value a caller must use for this to resolve
}

/** Writes $home/.automaton/solana.json — a DIFFERENT (non-.blockrun) instance's own resolvable secret,
 * for constructing an identity-MISMATCH fixture (a real, resolvable, but DIFFERENT wallet). */
export function writeAutomatonSolanaJson(home, secretBase58, address) {
  const dir = path.join(home, '.automaton');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'solana.json'), JSON.stringify({ address, secretKey: secretBase58 }, null, 2));
}

// ── Mock brain HTTP server (captures parsed request bodies) ────────────────

export function makeToolCallResponse(slot, args = {}) {
  return JSON.stringify({
    id: 'chatcmpl-test', object: 'chat.completion',
    choices: [{
      index: 0,
      message: {
        role: 'assistant', content: null,
        tool_calls: [{
          id: 'call_test', type: 'function',
          function: { name: 'run_skill', arguments: JSON.stringify({ slot, args }) },
        }],
      },
      finish_reason: 'tool_calls',
    }],
    usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
  });
}

export function makeNarrateResponse(text = 'I am thinking.') {
  return JSON.stringify({
    id: 'chatcmpl-test', object: 'chat.completion',
    choices: [{ index: 0, message: { role: 'assistant', content: text, tool_calls: undefined }, finish_reason: 'stop' }],
    usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
  });
}

/**
 * Start a loopback-only decision fixture for the test Codex runner. `responseFactory` receives the
 * actual prompt sent by the loop; exact slot menus are captured separately from that prompt.
 *
 * @param {(count: number, parsedBody: object) => string} responseFactory
 * @returns {Promise<{server, port, url, requests: object[]}>}
 */
export function startMockBrainServer(responseFactory) {
  const requests = [];
  return new Promise((resolve) => {
    let count = 0;
    const server = http.createServer((req, res) => {
      if (req.method === 'POST' && req.url.includes('/chat/completions')) {
        let raw = '';
        req.on('data', (d) => { raw += d; });
        req.on('end', () => {
          let parsed = null;
          try { parsed = JSON.parse(raw); } catch { /* leave null */ }
          requests.push(parsed);
          const resp = responseFactory(count++, parsed);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(resp);
        });
      } else {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ object: 'list', data: [] }));
      }
    });
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({ server, port, url: `http://127.0.0.1:${port}/v1`, requests });
    });
  });
}

// ── Spawn / ledger helpers (mirrors integration.test.mjs verbatim) ─────────

export function spawnLoop(env) {
  const codexFixtureEnv = mockCodexRunnerEnv({
    home: env.ANICCA_HOME,
    baseUrl: env.OPENAI_BASE_URL,
    capturePromptPath: env.CODEX_TEST_PROMPT_CAPTURE
      || path.join(env.ANICCA_HOME, 'state', 'codex-prompts.jsonl'),
  });
  const fixtureSkills = env.LIFE_MANAGER_SKILLS_ROOT
    || (env.ANICCA_HOME ? path.join(env.ANICCA_HOME, 'skills') : undefined);
  const fixtureLedger = env.EARN_LEDGER
    || (env.ANICCA_HOME ? path.join(env.ANICCA_HOME, 'skills', 'earn', 'state', 'earn-ledger.jsonl') : undefined);
  const registryPath = env.ALWAYS_ACT_REGISTRY_PATH_OVERRIDE
    || path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..', '..', '..', 'skills', 'registry.json');
  if (fixtureSkills) {
    const ledgerSource = path.join(REPO_ROOT, 'skills', '_shared', 'lib', 'ledger.mjs');
    const ledgerShim = path.join(fixtureSkills, '_shared', 'lib', 'ledger.mjs');
    fs.mkdirSync(path.dirname(ledgerShim), { recursive: true });
    if (!fs.existsSync(ledgerShim)) fs.symlinkSync(ledgerSource, ledgerShim);
  }
  return spawn(process.execPath, [LOOP_ENTRY], {
    env: {
      ...process.env,
      ...env,
      ...codexFixtureEnv,
      ...(fixtureSkills ? { LIFE_MANAGER_SKILLS_ROOT: fixtureSkills } : {}),
      ...(fixtureLedger ? { EARN_LEDGER: fixtureLedger } : {}),
      ALWAYS_ACT_REGISTRY_PATH_OVERRIDE: registryPath,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

export function readLedger(ledgerPath) {
  if (!fs.existsSync(ledgerPath)) return [];
  return fs.readFileSync(ledgerPath, 'utf8')
    .split('\n')
    .filter((l) => l.trim().length > 0)
    .map((l) => { try { return JSON.parse(l); } catch { return null; } })
    .filter(Boolean);
}

export function waitForLines(ledgerPath, n, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const interval = setInterval(() => {
      const lines = readLedger(ledgerPath);
      if (lines.length >= n) { clearInterval(interval); resolve(lines); }
      if (Date.now() - start > timeoutMs) { clearInterval(interval); reject(new Error(`Timeout waiting for ${n} ledger lines; got ${lines.length}`)); }
    }, 50);
  });
}

export function waitForCondition(fn, timeoutMs = 15000, intervalMs = 50) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const interval = setInterval(() => {
      let ok = false;
      try { ok = fn(); } catch { /* keep polling */ }
      if (ok) { clearInterval(interval); resolve(); }
      if (Date.now() - start > timeoutMs) { clearInterval(interval); reject(new Error('Timeout waiting for condition')); }
    }, intervalMs);
  });
}

/** Base env every always-act spawn test starts from — fast, deterministic, no real sleep/RPC. */
export function baseSpawnEnv(extra = {}) {
  return {
    ANICCA_BALANCE_OVERRIDE: '50', // >= BOOTSTRAP_RESERVE_USDC(20) default so capital-risking slots
                                    // are menu-visible via REQ-503's reserve gate, letting REQ-506's
                                    // risk-free reroute filter be the ONLY thing under test.
    SLEEP_BASE_S: '1', // give the test process time to observe one terminal wake before the next decision
    SLEEP_ERROR_S: '0',
    SLEEP_LOOP_DETECT_S: '0',
    SKILL_TIMEOUT_S: '5',
    LOOP_DETECT_WINDOW: '100', // disable unrelated loop-detect diversification for these tests
    ...extra,
  };
}

export async function cleanupHome(home) {
  try { await fsp.rm(home, { recursive: true, force: true }); } catch { /* best-effort */ }
}
