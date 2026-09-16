/**
 * harness-health-snapshot.mjs — Impure: CLI, the ONLY caller of computeHarnessHealth against real
 * disk state.
 *
 * anicca-harness-tooluse-health R7: reads $ANICCA_HOME/state/ledger.jsonl via the EXISTING
 * readLedgerLines, computes R4's computeHarnessHealth, and OVERWRITES (never appends — a derived
 * VIEW, not an event log) $ANICCA_HOME/state/harness-health.json with the result. A missing/
 * unreadable ledger.jsonl produces the R4 empty-ledger shape, never crashes. The same run writes a
 * derived `harness-recovery.json` containing only the latest typed recovery intent per owner/slot;
 * raw failure detail never enters that file.
 *
 * Scheduling (launchd/cron cadence) is explicitly deferred, same precedent
 * skills/self/healthcheck-runtime-loop.sh's own header comment already states for itself.
 *
 * Run via: node runtime/loop/harness-health-snapshot.mjs
 * Optional test-injection env var (same idiom as ANICCA_BALANCE_OVERRIDE/CLAUDE_BIN elsewhere in
 * this codebase): HARNESS_HEALTH_NOW — epoch-ms override for generatedAt, so a test can pin the
 * exact instant this script's output is compared against a direct computeHarnessHealth() call.
 * HARNESS_HEALTH_STREAK_THRESHOLD is read by harness-health.mjs itself (DEFAULT_STREAK_THRESHOLD).
 */

import { promises as fs } from 'node:fs';
import path from 'node:path';

import { readLedgerLines } from './ledger.mjs';
import { computeHarnessHealth, projectRecoveryIntents } from './harness-health.mjs';

const ANICCA_HOME = process.env.ANICCA_HOME;
if (!ANICCA_HOME) {
  process.stderr.write('[harness-health-snapshot] FATAL: ANICCA_HOME is not set.\n');
  process.exit(1);
}

const LEDGER_PATH = path.join(ANICCA_HOME, 'state', 'ledger.jsonl');
const FAILURES_PATH = path.join(ANICCA_HOME, 'state', 'harness-failures.jsonl');
const SNAPSHOT_PATH = path.join(ANICCA_HOME, 'state', 'harness-health.json');
const RECOVERY_PATH = path.join(ANICCA_HOME, 'state', 'harness-recovery.json');

async function main() {
  let records = [];
  try {
    records = await readLedgerLines(LEDGER_PATH);
  } catch (err) {
    // readLedgerLines already returns [] on ENOENT; any other read error still must not crash this
    // CLI (R7: "A missing/unreadable ledger.jsonl SHALL produce the R4 empty-ledger shape, never crash").
    process.stderr.write(`[harness-health-snapshot] WARNING: could not read ${LEDGER_PATH} (${err.message}); writing empty-ledger shape\n`);
    records = [];
  }

  const nowOverride = process.env.HARNESS_HEALTH_NOW;
  const now = nowOverride != null && nowOverride !== '' ? Number(nowOverride) : Date.now();

  const report = computeHarnessHealth(records, { now });
  let failureRecords = [];
  try {
    failureRecords = await readLedgerLines(FAILURES_PATH);
  } catch (err) {
    // Recovery is a derived diagnostic view; an unreadable side channel must not prevent the
    // ordinary health snapshot from being refreshed.
    process.stderr.write(`[harness-health-snapshot] WARNING: could not read ${FAILURES_PATH} (${err.message}); writing empty recovery projection\n`);
    failureRecords = [];
  }
  const recovery = projectRecoveryIntents(failureRecords);

  await fs.mkdir(path.dirname(SNAPSHOT_PATH), { recursive: true });
  await fs.writeFile(SNAPSHOT_PATH, JSON.stringify(report, null, 2) + '\n');
  await fs.writeFile(RECOVERY_PATH, JSON.stringify(recovery, null, 2) + '\n');
}

try {
  await main();
} catch (err) {
  process.stderr.write(`[harness-health-snapshot] FATAL: ${err.message}\n`);
  process.exit(1);
}
