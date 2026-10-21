/**
 * config-drift.test.mjs — Phase 2a (RED) tests for config-delivery-verification.
 *
 * Imports the PURE core + one thin effectful reader from `../config-drift.mjs`, which DOES NOT EXIST
 * YET (Phase 2b writes it). This whole file is expected to fail to even load until then — that is the
 * intended RED signal.
 *
 * Contract this file pins down (per specs/verification-architecture.md's Purity Boundary Map):
 *   - diffDeclaredVsActual(declaredMap, actualMap) -> [{key, declared, actual}]        (REQ-006, PROP-001/002)
 *   - classifyObservability(rawObservation) -> "OBSERVED" | "UNOBSERVABLE"              (REQ-004)
 *   - resolveExpectedValue(declaredConfig, key, codeDefault) -> {value, declaredExplicitly}  (REQ-001 edge, REQ-003)
 *   - flattenRegistrySlotStatus(registry) -> {slotName: status}                          (REQ-002)
 *   - parsePlistEnvironmentVariables(plutilJsonText) -> {key: value}                      (plist parse, pure)
 *   - parseAllowedEnvFromCommandLine(commandLine, allowedKeys) -> {key: value|undefined}  (NFR-Security, FIND-002 homework)
 *   - parseIndexLoopProcesses(psOutputLines) -> [{pid, aniccaHome, xpcServiceName}]        (REQ-010, PROP-019)
 *   - detectBrainDrift(instance, declaredConfig, observedEnvOrNull, key?, codeDefault?) -> DriftEntry[]  (REQ-001/003/004)
 *   - detectRegistryStatusDrift(canonicalRegistry, copies) -> DriftEntry[]                 (REQ-002/004)
 *   - readRegistryFile(filePath) -> Promise<object|null>                                    (effectful, thin — REQ-004/REQ-005)
 *
 * NOTE on PROP-008/013/020 (grep-for-hardcoded-branching/severity-keywords structural checks):
 * verification-architecture.md itself marks these as "コードレビュー時に機械実行、CIではなく実装
 * レビューのチェックリスト項目" (manual adversary-review checklist items, not CI unit tests) — a
 * literal-substring grep against a file full of explanatory prose comments (this codebase's own style,
 * see brain.mjs/index.mjs) would be fragile and is not requested by this session's task. Left as a
 * Phase 3 adversary review checklist item, not a Phase 2a test, consistent with the spec's own tooling
 * column. PROP-011 (kill/bootout/bootstrap/writeFile absence) IS included below since its Tier/Tool row
 * carries no such "not CI" caveat and a total-absence check is not fragile against prose.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  diffDeclaredVsActual,
  classifyObservability,
  resolveExpectedValue,
  flattenRegistrySlotStatus,
  parsePlistEnvironmentVariables,
  parseAllowedEnvFromCommandLine,
  parseIndexLoopProcesses,
  detectBrainDrift,
  detectRegistryStatusDrift,
  readRegistryFile,
} from '../config-drift.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SOURCE_PATH = path.resolve(__dirname, '../config-drift.mjs');

// ── REQ-006 / PROP-001 / PROP-002 — diffDeclaredVsActual is a pure, deterministic, non-mutating diff ──

test('PROP-001: diffDeclaredVsActual returns bit-for-bit identical result across 10 consecutive calls (deterministic)', () => {
  const declared = { ANICCA_BRAIN: 'claude-p' };
  const actual = { ANICCA_BRAIN: 'proxy' };
  const results = [];
  for (let i = 0; i < 10; i++) results.push(diffDeclaredVsActual(declared, actual));
  const first = JSON.stringify(results[0]);
  for (const r of results) assert.equal(JSON.stringify(r), first, 'every call must return an identical diff list');
});

test('PROP-002: diffDeclaredVsActual does not mutate its input objects (frozen inputs must not throw)', () => {
  const declared = Object.freeze({ ANICCA_BRAIN: 'claude-p', hl_trade: 'dormant' });
  const actual = Object.freeze({ ANICCA_BRAIN: 'proxy', hl_trade: 'dormant' });
  assert.doesNotThrow(() => diffDeclaredVsActual(declared, actual));
});

test('diffDeclaredVsActual: mismatching key produces exactly one {key, declared, actual} entry', () => {
  const diffs = diffDeclaredVsActual({ ANICCA_BRAIN: 'claude-p' }, { ANICCA_BRAIN: 'proxy' });
  assert.deepEqual(diffs, [{ key: 'ANICCA_BRAIN', declared: 'claude-p', actual: 'proxy' }]);
});

test('diffDeclaredVsActual: matching key produces zero entries (PASS)', () => {
  const diffs = diffDeclaredVsActual({ ANICCA_BRAIN: 'proxy' }, { ANICCA_BRAIN: 'proxy' });
  assert.deepEqual(diffs, []);
});

// ── REQ-001 / PROP-003 / PROP-004 — ANICCA_BRAIN declared-vs-runtime drift (the real Bug 1) ──────────

test('PROP-003: real bug-1 fixture (declared=claude-p, actual=proxy, instance=ai.anicca.agent-economy-loop) -> exactly 1 drift entry', () => {
  const drift = detectBrainDrift(
    'ai.anicca.agent-economy-loop',
    { ANICCA_BRAIN: 'claude-p' },
    { ANICCA_BRAIN: 'proxy' },
  );
  assert.equal(drift.length, 1);
  assert.deepEqual(drift[0], {
    key: 'ANICCA_BRAIN',
    instance: 'ai.anicca.agent-economy-loop',
    declared: 'claude-p',
    actual: 'proxy',
  });
});

test('PROP-004: declared === actual (both "proxy") -> zero drift entries (PASS)', () => {
  const drift = detectBrainDrift(
    'ai.anicca.franklin-loop',
    { ANICCA_BRAIN: 'proxy' },
    { ANICCA_BRAIN: 'proxy' },
  );
  assert.deepEqual(drift, []);
});

test('REQ-001 edge case: plist declares no ANICCA_BRAIN key at all -> inherits Codex code default', () => {
  // declaredConfig has no ANICCA_BRAIN key (plist omitted it entirely).
  const drift = detectBrainDrift('some-instance', {}, { ANICCA_BRAIN: 'claude-p' });
  // actual (claude-p) differs from the inherited default (codex) -> must be reported, not swallowed.
  assert.equal(drift.length, 1);
  assert.equal(drift[0].declared, 'codex');
  assert.equal(drift[0].actual, 'claude-p');
});

// ── FIND-003 (adversary iteration-1, major->blocking): declaredConfig===null (plist UNREADABLE) must
// be distinguished from declaredConfig==={} (plist WAS read, key just absent) — the former is a
// fail-closed FAIL, never a silent fall-through to codeDefault that could look like a PASS. ────────────

test('FIND-003: declaredConfig=null (plist could not be read at all) -> FAIL (reason: unobservable), NEVER a silent codeDefault-based PASS', () => {
  const drift = detectBrainDrift('ai.anicca.agent-economy-loop', null, { ANICCA_BRAIN: 'proxy' });
  assert.equal(drift.length, 1);
  assert.equal(drift[0].reason, 'unobservable');
  assert.equal(drift[0].declared, null);
  assert.equal(drift[0].actual, null);
});

test('FIND-003: declaredConfig={} resolves via Codex code default and flags an explicit proxy runtime value', () => {
  const drift = detectBrainDrift('some-instance', {}, { ANICCA_BRAIN: 'proxy' });
  assert.deepEqual(drift, [{
    key: 'ANICCA_BRAIN', declared: 'codex', actual: 'proxy', instance: 'some-instance',
  }]);
});

test('FIND-003: an unreadable declaredConfig takes priority even when the actual side WOULD have matched the codeDefault — unobservable is reported regardless of what the (unusable) codeDefault comparison would have said', () => {
  const drift = detectBrainDrift('ai.anicca.agent-economy-loop', undefined, { ANICCA_BRAIN: 'proxy' });
  assert.equal(drift.length, 1);
  assert.equal(drift[0].reason, 'unobservable');
});

// ── Live-run correctness fix (found running the real detector against the production fleet,
// com.anicca.daemon 2026-07-12): `ps` can only show ANICCA_BRAIN if it was EXPLICITLY set in the
// process's env -- it can't see brain.mjs's own in-process `config.ANICCA_BRAIN || 'proxy'` default. An
// OBSERVED env object (not null -- the process WAS read successfully) that simply lacks the key must
// inherit codeDefault the SAME way the declared side already does, or every instance that never
// explicitly overrides ANICCA_BRAIN reports a spurious drift that isn't real. ──────────────────────────

test('real-fleet fix: neither side explicitly sets ANICCA_BRAIN (both observed AND declared omit the key) -> both resolve to the SAME inherited codeDefault -> PASS, not a spurious declared="proxy"/actual=undefined drift', () => {
  const drift = detectBrainDrift('com.anicca.daemon', { ANICCA_HOME: '/home/life-manager/.anicca' }, { ANICCA_HOME: '/home/life-manager/.anicca' });
  assert.deepEqual(drift, [], 'neither side named ANICCA_BRAIN at all -> both inherit the identical codeDefault -> no real drift');
});

test('real-fleet fix: observed env IS successfully read (not null) but happens to omit the key, while declared EXPLICITLY sets a non-default value -> still reports a real drift (this fix must not become a new silent-PASS hole)', () => {
  const drift = detectBrainDrift('ai.anicca.agent-economy-loop', { ANICCA_BRAIN: 'claude-p' }, { ANICCA_HOME: '/home/life-manager/.anicca-founder' });
  assert.equal(drift.length, 1);
  assert.equal(drift[0].declared, 'claude-p');
  assert.equal(drift[0].actual, 'codex', 'the observed side with the key absent inherits the Codex code default, which differs from the explicit declared claude-p');
});

test('resolveExpectedValue: key present in declaredConfig is returned verbatim with declaredExplicitly=true', () => {
  const resolved = resolveExpectedValue({ ANICCA_BRAIN: 'claude-p' }, 'ANICCA_BRAIN', 'proxy');
  assert.deepEqual(resolved, { value: 'claude-p', declaredExplicitly: true });
});

test('resolveExpectedValue: key absent from declaredConfig falls back to codeDefault with declaredExplicitly=false', () => {
  const resolved = resolveExpectedValue({}, 'ANICCA_BRAIN', 'proxy');
  assert.deepEqual(resolved, { value: 'proxy', declaredExplicitly: false });
});

// ── REQ-003 / PROP-007 — same function, per-instance declared values, no global hardcoded expectation ─

test('PROP-007: Franklin fixture (declared=proxy, actual=proxy) PASSes and claude-p fixture (declared=claude-p, actual=proxy) FAILs through the SAME detectBrainDrift function — only the declared input differs', () => {
  const franklinDrift = detectBrainDrift('ai.anicca.franklin-loop', { ANICCA_BRAIN: 'proxy' }, { ANICCA_BRAIN: 'proxy' });
  const claudePDrift = detectBrainDrift('ai.anicca.agent-economy-loop', { ANICCA_BRAIN: 'claude-p' }, { ANICCA_BRAIN: 'proxy' });
  assert.deepEqual(franklinDrift, [], 'Franklin (self-funded, proxy is correct) must PASS');
  assert.equal(claudePDrift.length, 1, 'claude-p instance (human-funded, claude-p is correct) must FAIL — same function, different declared input only');
});

// ── REQ-002 / PROP-005 / PROP-006 — registry.json slot status drift (the real Bug 2) ─────────────────

test('flattenRegistrySlotStatus: extracts a flat {slotName: status} map from a registry object', () => {
  const registry = { slots: { hl_trade: { status: 'dormant' }, yield: { status: 'live' } } };
  assert.deepEqual(flattenRegistrySlotStatus(registry), { hl_trade: 'dormant', yield: 'live' });
});

test('PROP-005: real bug-2 fixture (canonical hl_trade=dormant, copy hl_trade=live) -> exactly 1 drift entry for hl_trade.status', () => {
  const canonical = { slots: { hl_trade: { status: 'dormant', dormantReason: 'unfunded' } } };
  const copies = [{ copyPath: '~/.anicca-founder/skills/registry.json', registryOrNull: { slots: { hl_trade: { status: 'live' } } } }];
  const drift = detectRegistryStatusDrift(canonical, copies);
  assert.equal(drift.length, 1);
  assert.deepEqual(drift[0], {
    key: 'hl_trade.status',
    copyPath: '~/.anicca-founder/skills/registry.json',
    declared: 'dormant',
    actual: 'live',
  });
});

test('registry status: canonical and copy fully identical -> zero drift entries (PASS)', () => {
  const canonical = { slots: { hl_trade: { status: 'dormant' } } };
  const copies = [{ copyPath: '/x/registry.json', registryOrNull: { slots: { hl_trade: { status: 'dormant' } } } }];
  assert.deepEqual(detectRegistryStatusDrift(canonical, copies), []);
});

test('PROP-006: multiple copies are reported INDEPENDENTLY — one matching copy must not swallow another copy\'s drift', () => {
  const canonical = { slots: { hl_trade: { status: 'dormant' } } };
  const copies = [
    { copyPath: '/a/registry.json', registryOrNull: { slots: { hl_trade: { status: 'dormant' } } } }, // matches
    { copyPath: '/b/registry.json', registryOrNull: { slots: { hl_trade: { status: 'live' } } } },     // drifts
    { copyPath: '/c/registry.json', registryOrNull: { slots: { hl_trade: { status: 'live' } } } },     // drifts too
  ];
  const drift = detectRegistryStatusDrift(canonical, copies);
  const drifted = drift.map((d) => d.copyPath).sort();
  assert.deepEqual(drifted, ['/b/registry.json', '/c/registry.json'], 'exactly the 2 drifting copies must be reported, the matching one must not appear');
});

test('registry status edge case: a slot present only in the runtime copy (not in canonical) is still reported as drift, never silently ignored', () => {
  const canonical = { slots: {} };
  const copies = [{ copyPath: '/x/registry.json', registryOrNull: { slots: { ghost_slot: { status: 'live' } } } }];
  const drift = detectRegistryStatusDrift(canonical, copies);
  assert.equal(drift.length, 1);
  assert.equal(drift[0].key, 'ghost_slot.status');
});

// ── FIND-005 (adversary iteration-2, minor): detectRegistryStatusDrift itself (the REQ-006 pure core,
// not just the composed runConfigDriftDetector wrapper) must fail closed when canonicalRegistry itself
// is unobservable (null/undefined) — an unreadable canonical means there is nothing to diff every copy
// against, so every copy reports unobservable, never an empty (PASS) array. ─────────────────────────────

test('FIND-005: detectRegistryStatusDrift(null, copies) fails EVERY copy closed at the pure-function level itself, not just via an external wrapper check', () => {
  const copies = [
    { copyPath: '/a/registry.json', registryOrNull: { slots: { hl_trade: { status: 'dormant' } } } },
    { copyPath: '/b/registry.json', registryOrNull: null },
  ];
  const drift = detectRegistryStatusDrift(null, copies);
  assert.equal(drift.length, 2, 'both copies must report unobservable -- an unreadable canonical rescues nothing');
  assert.ok(drift.every((d) => d.reason === 'unobservable' && d.declared === null && d.actual === null));
  assert.deepEqual(drift.map((d) => d.copyPath).sort(), ['/a/registry.json', '/b/registry.json']);
});

test('FIND-005: detectRegistryStatusDrift(undefined, copies) behaves identically to null (both classify as UNOBSERVABLE)', () => {
  const copies = [{ copyPath: '/x/registry.json', registryOrNull: { slots: {} } }];
  const drift = detectRegistryStatusDrift(undefined, copies);
  assert.equal(drift.length, 1);
  assert.equal(drift[0].reason, 'unobservable');
});

test('FIND-005: detectRegistryStatusDrift(null, []) with zero copies returns an empty array (nothing to report, not an error)', () => {
  assert.deepEqual(detectRegistryStatusDrift(null, []), []);
});

// ── REQ-004 / PROP-009 / PROP-010 — fail-closed on unobservable runtime state ─────────────────────────

test('classifyObservability: null/undefined raw observation classifies as UNOBSERVABLE', () => {
  assert.equal(classifyObservability(null), 'UNOBSERVABLE');
  assert.equal(classifyObservability(undefined), 'UNOBSERVABLE');
});

test('classifyObservability: a real object classifies as OBSERVED', () => {
  assert.equal(classifyObservability({ ANICCA_BRAIN: 'proxy' }), 'OBSERVED');
});

test('PROP-009: detectBrainDrift with observedEnvOrNull=null (process not found / ps failed) returns a FAIL, NOT an empty PASS array', () => {
  const drift = detectBrainDrift('ai.anicca.agent-economy-loop', { ANICCA_BRAIN: 'claude-p' }, null);
  assert.equal(drift.length, 1);
  assert.equal(drift[0].reason, 'unobservable');
  assert.equal(drift[0].actual, null);
  assert.notDeepEqual(drift, [], 'unobservable must never be reported as an empty (PASS) array');
});

test('PROP-009: detectRegistryStatusDrift with a null copy (missing file / parse failure) returns a FAIL, NOT an empty PASS array', () => {
  const canonical = { slots: { hl_trade: { status: 'dormant' } } };
  const copies = [{ copyPath: '/missing/registry.json', registryOrNull: null }];
  const drift = detectRegistryStatusDrift(canonical, copies);
  assert.equal(drift.length >= 1, true);
  assert.ok(drift.every((d) => d.reason === 'unobservable' && d.actual === null));
});

test('PROP-010: unobservable-copy entries are never merged/collapsed into an empty array even when OTHER copies match perfectly', () => {
  const canonical = { slots: { hl_trade: { status: 'dormant' } } };
  const copies = [
    { copyPath: '/ok/registry.json', registryOrNull: { slots: { hl_trade: { status: 'dormant' } } } }, // matches -> no entry
    { copyPath: '/missing/registry.json', registryOrNull: null }, // unobservable -> must still surface
  ];
  const drift = detectRegistryStatusDrift(canonical, copies);
  assert.equal(drift.length, 1, 'the matching copy contributes 0 entries, but the unobservable copy MUST still contribute 1 — never both collapsing to 0');
  assert.equal(drift[0].reason, 'unobservable');
  assert.equal(drift[0].copyPath, '/missing/registry.json');
});

// ── plist parse (pure) — fixture is an already-converted JSON string (what `plutil -convert json -o -`
// produces), injected as a literal string. No plutil/ps subprocess is ever spawned in this test file. ──

test('parsePlistEnvironmentVariables: extracts EnvironmentVariables dict from a plutil-json-shaped string', () => {
  const jsonText = JSON.stringify({
    Label: 'ai.anicca.agent-economy-loop',
    EnvironmentVariables: { ANICCA_BRAIN: 'claude-p', ANICCA_HOME: '/home/life-manager/.anicca-founder' },
  });
  assert.deepEqual(parsePlistEnvironmentVariables(jsonText), {
    ANICCA_BRAIN: 'claude-p',
    ANICCA_HOME: '/home/life-manager/.anicca-founder',
  });
});

test('parsePlistEnvironmentVariables: plist with no EnvironmentVariables dict at all returns {} (not a throw)', () => {
  const jsonText = JSON.stringify({ Label: 'ai.anicca.franklin-loop' });
  assert.deepEqual(parsePlistEnvironmentVariables(jsonText), {});
});

// ── NFR-Security / FIND-002 adversary homework — secrets must never leak through the allow-list filter ─

test('NFR-Security/FIND-002: parseAllowedEnvFromCommandLine extracts ONLY the allow-listed key, secret value never appears in the returned object', () => {
  const commandLine = 'node index.mjs ANTHROPIC_API_KEY=sk-test-secret-value ANICCA_BRAIN=proxy ANICCA_SOLANA_PRIVATE_KEY=abc123secretkey XPC_SERVICE_NAME=ai.anicca.agent-economy-loop';
  const result = parseAllowedEnvFromCommandLine(commandLine, ['ANICCA_BRAIN']);
  assert.deepEqual(result, { ANICCA_BRAIN: 'proxy' });
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes('sk-test-secret-value'), 'secret ANTHROPIC_API_KEY value must never appear in the returned object');
  assert.ok(!serialized.includes('abc123secretkey'), 'secret private-key value must never appear in the returned object');
});

test('NFR-Security/FIND-002: even when the allow-list itself is empty, no key at all (secret or not) leaks through', () => {
  const commandLine = 'node index.mjs ANTHROPIC_API_KEY=sk-test-secret-value ANICCA_WALLET_PRIVATE_KEY=alsosecret';
  const result = parseAllowedEnvFromCommandLine(commandLine, []);
  assert.deepEqual(result, {});
});

test('NFR-Security/FIND-002: a malformed/empty command line must not throw with a secret-containing message — error path (if any) is also secret-free', () => {
  const commandLine = ''; // degenerate input
  let thrown = null;
  try {
    parseAllowedEnvFromCommandLine(commandLine, ['ANICCA_BRAIN']);
  } catch (err) {
    thrown = err;
  }
  if (thrown) {
    assert.ok(!String(thrown.message).includes('sk-test-secret-value'));
  }
});

test('NFR-Security/FIND-002 end-to-end: detectBrainDrift built on top of the allow-list extractor never leaks a secret present elsewhere on the same command line, including inside a thrown error', () => {
  const commandLine = 'node index.mjs ANTHROPIC_API_KEY=sk-test-secret-value ANICCA_BRAIN=proxy';
  const observedEnv = parseAllowedEnvFromCommandLine(commandLine, ['ANICCA_BRAIN']);
  let drift;
  let thrownMessage = '';
  try {
    drift = detectBrainDrift('ai.anicca.agent-economy-loop', { ANICCA_BRAIN: 'claude-p' }, observedEnv);
  } catch (err) {
    thrownMessage = String(err && err.message);
    throw err;
  }
  const serialized = JSON.stringify(drift);
  assert.ok(!serialized.includes('sk-test-secret-value'), 'detector output must never contain the secret');
  assert.ok(!thrownMessage.includes('sk-test-secret-value'), 'a thrown error (if any) must never contain the secret either');
});

// ── REQ-010 / PROP-019 — discovery by live-process enumeration, not a static instance-name list ───────

test('PROP-019: parseIndexLoopProcesses extracts {pid, aniccaHome, xpcServiceName} from 3 ps-fixture lines containing runtime/loop/index.mjs', () => {
  const psLines = [
    '94249 /usr/local/bin/node __REPO_ROOT__/runtime/loop/index.mjs ANICCA_HOME=/home/life-manager/.anicca-founder XPC_SERVICE_NAME=ai.anicca.agent-economy-loop',
    '79192 /usr/local/bin/node __REPO_ROOT__/runtime/loop/index.mjs ANICCA_HOME=/home/life-manager/.blockrun XPC_SERVICE_NAME=ai.anicca.franklin-loop',
    '86698 /usr/local/bin/node __REPO_ROOT__/runtime/loop/index.mjs ANICCA_HOME=/home/life-manager/.franklin2-home/.blockrun XPC_SERVICE_NAME=ai.anicca.franklin2-loop',
    '12345 /usr/local/bin/node __REPO_ROOT__/runtime/dashboard/index.mjs SOME_OTHER=1', // must be filtered out (not index-loop)
  ];
  const found = parseIndexLoopProcesses(psLines);
  assert.equal(found.length, 3, 'only the 3 lines whose command contains runtime/loop/index.mjs must be returned');
  const byPid = Object.fromEntries(found.map((f) => [f.pid, f]));
  assert.deepEqual(byPid[94249], { pid: 94249, aniccaHome: '/home/life-manager/.anicca-founder', xpcServiceName: 'ai.anicca.agent-economy-loop' });
  assert.deepEqual(byPid[86698], { pid: 86698, aniccaHome: '/home/life-manager/.franklin2-home/.blockrun', xpcServiceName: 'ai.anicca.franklin2-loop' });
});

test('PROP-019: adding a 4th index.mjs line to the SAME fixture yields 4 results with NO code change (no static list to update)', () => {
  const psLines = [
    '94249 node __REPO_ROOT__/runtime/loop/index.mjs ANICCA_HOME=/a XPC_SERVICE_NAME=ai.anicca.a',
    '79192 node __REPO_ROOT__/runtime/loop/index.mjs ANICCA_HOME=/b XPC_SERVICE_NAME=ai.anicca.b',
    '86698 node __REPO_ROOT__/runtime/loop/index.mjs ANICCA_HOME=/c XPC_SERVICE_NAME=ai.anicca.c',
    '99999 node __REPO_ROOT__/runtime/loop/index.mjs ANICCA_HOME=/d XPC_SERVICE_NAME=ai.anicca.d',
  ];
  const found = parseIndexLoopProcesses(psLines);
  assert.equal(found.length, 4, 'a 4th never-before-seen instance must be discovered purely by enumeration, not a maintained list');
});

test('REQ-010 edge case: an index.mjs process line missing ANICCA_HOME or XPC_SERVICE_NAME reports null for that field rather than being silently dropped from the result set', () => {
  const psLines = [
    '55555 node __REPO_ROOT__/runtime/loop/index.mjs XPC_SERVICE_NAME=ai.anicca.orphan', // no ANICCA_HOME
  ];
  const found = parseIndexLoopProcesses(psLines);
  assert.equal(found.length, 1, 'the process must still be discovered (not dropped), even though ANICCA_HOME is missing');
  assert.equal(found[0].pid, 55555);
  assert.equal(found[0].aniccaHome, null);
  assert.equal(found[0].xpcServiceName, 'ai.anicca.orphan');
});

test('REQ-010 edge case: zero index.mjs lines in the ps fixture returns an empty array (an explicit "no targets", never mistaken for PASS by the caller)', () => {
  const psLines = ['1 /sbin/launchd', '222 /usr/bin/some-other-process'];
  assert.deepEqual(parseIndexLoopProcesses(psLines), []);
});

// ── REQ-005 / PROP-011 — detector source never contains a kill/restart/write call ───────────────────

test('PROP-011: config-drift.mjs source contains none of kickstart/bootout/bootstrap/kill(/SIGKILL/SIGTERM/writeFile', async () => {
  const src = await fs.readFile(SOURCE_PATH, 'utf8');
  for (const forbidden of ['kickstart', 'bootout', 'bootstrap', 'kill(', 'SIGKILL', 'SIGTERM', 'writeFile']) {
    assert.ok(!src.includes(forbidden), `config-drift.mjs must never contain '${forbidden}' — detector is read-only (REQ-005)`);
  }
});

// ── REQ-005 / PROP-012 — readRegistryFile is a read-only effectful adapter; never touches file mtime ──

test('PROP-012: readRegistryFile reads a fixture file repeatedly without changing its mtime (read-only, REQ-005)', async () => {
  const tmpPath = path.join(os.tmpdir(), `config-drift-mtime-fixture-${Date.now()}.json`);
  await fs.writeFile(tmpPath, JSON.stringify({ slots: { hl_trade: { status: 'dormant' } } }));
  try {
    const before = (await fs.stat(tmpPath)).mtimeMs;
    for (let i = 0; i < 3; i++) {
      const parsed = await readRegistryFile(tmpPath);
      assert.deepEqual(parsed, { slots: { hl_trade: { status: 'dormant' } } });
    }
    const after = (await fs.stat(tmpPath)).mtimeMs;
    assert.equal(after, before, 'reading the registry file repeatedly must never change its mtime');
  } finally {
    await fs.rm(tmpPath, { force: true });
  }
});

test('readRegistryFile: missing file returns null (fail-closed input for REQ-004), never throws', async () => {
  const result = await readRegistryFile(path.join(os.tmpdir(), `does-not-exist-${Date.now()}.json`));
  assert.equal(result, null);
});

test('readRegistryFile: malformed JSON returns null (fail-closed input for REQ-004), never throws', async () => {
  const tmpPath = path.join(os.tmpdir(), `config-drift-malformed-${Date.now()}.json`);
  await fs.writeFile(tmpPath, 'not valid json {{{');
  try {
    const result = await readRegistryFile(tmpPath);
    assert.equal(result, null);
  } finally {
    await fs.rm(tmpPath, { force: true });
  }
});
