"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  acquireExclusiveLock,
  appendLedgerEntry,
  defaultStateDir,
  runDailyPass,
  summarizeSevenDays,
} = require("./daily-dev-loop");

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "lm-daily-dev-"));
}

function writeExecutable(file, source) {
  fs.writeFileSync(file, source, { mode: 0o700 });
}

test("the default state dir lives beneath the Life Manager data root, never a legacy root", () => {
  assert.equal(
    defaultStateDir({ HOME: "/srv/operator-home" }),
    "/srv/operator-home/.local/state/life-manager/state/life-manager-dev",
  );
  assert.equal(
    defaultStateDir({ LM_DATA_DIR: "/var/lib/life-manager" }),
    "/var/lib/life-manager/state/life-manager-dev",
  );
  const legacyToken = "." + "open" + "claw";
  assert.ok(!defaultStateDir({ HOME: "/srv/operator-home" }).includes(legacyToken));
});

test("appendLedgerEntry writes one closed-schema JSONL record without arbitrary fields", () => {
  const dir = tempDir();
  const ledger = path.join(dir, "daily-ledger.jsonl");
  const written = appendLedgerEntry(ledger, {
    run_id: "20260724T181500-123",
    day: "2026-07-24",
    started_at: "2026-07-24T09:15:00.000Z",
    finished_at: "2026-07-24T09:15:01.000Z",
    outcome: "no_op",
    reason: "no_unattempted_open_issue",
    issue_number: null,
    pr_url: null,
    duration_ms: 1000,
    recovered_stale_lock: false,
    raw_provider_error: "must not persist",
  });

  assert.deepEqual(Object.keys(written).sort(), [
    "day",
    "duration_ms",
    "finished_at",
    "issue_number",
    "outcome",
    "pr_url",
    "reason",
    "recovered_stale_lock",
    "run_id",
    "schema_version",
    "started_at",
  ]);
  assert.equal(fs.statSync(ledger).mode & 0o077, 0);
  assert.deepEqual(JSON.parse(fs.readFileSync(ledger, "utf8")), written);
});

test("acquireExclusiveLock recovers a dead stale owner but never steals a live lock", () => {
  const dir = tempDir();
  const lock = path.join(dir, "daily.lock");
  fs.writeFileSync(lock, JSON.stringify({ pid: 999999, started_ms: 1 }), { mode: 0o600 });

  const recovered = acquireExclusiveLock(lock, {
    nowMs: 100_000,
    staleMs: 10_000,
    isPidAlive: () => false,
    pid: 321,
  });
  assert.equal(recovered.acquired, true);
  assert.equal(recovered.recoveredStale, true);
  recovered.release();

  fs.writeFileSync(lock, JSON.stringify({ pid: 777, started_ms: 90_000 }), { mode: 0o600 });
  const busy = acquireExclusiveLock(lock, {
    nowMs: 100_000,
    staleMs: 10_000,
    isPidAlive: () => true,
    pid: 321,
  });
  assert.deepEqual(busy, { acquired: false, recoveredStale: false, reason: "active_lock" });
});

test("runDailyPass records a bounded no-op with the D0 machine result", async () => {
  const dir = tempDir();
  const child = path.join(dir, "no-op.sh");
  writeExecutable(child, `#!/bin/bash
printf '%s\n' '{"status":"no_op","reason":"no_unattempted_open_issue","issue_number":null,"pr_url":null}' > "$LM_DEV_RESULT_PATH"
`);

  const result = await runDailyPass({
    command: child,
    stateDir: dir,
    timeoutMs: 2_000,
    now: () => new Date("2026-07-24T09:15:00.000Z"),
  });

  assert.equal(result.outcome, "no_op");
  assert.equal(result.reason, "no_unattempted_open_issue");
  const rows = fs.readFileSync(path.join(dir, "daily-ledger.jsonl"), "utf8").trim().split("\n");
  assert.equal(rows.length, 1);
  assert.deepEqual(
    JSON.parse(fs.readFileSync(path.join(dir, "seven-day-status.json"), "utf8")),
    {
      schema_version: 1,
      ready: false,
      consecutive_days: 1,
      evaluated_at: "2026-07-24T09:15:00.000Z",
    },
  );
});

test("runDailyPass kills a hung child at the hard timeout and records timeout recovery", async () => {
  const dir = tempDir();
  const child = path.join(dir, "hang.sh");
  writeExecutable(child, "#!/bin/bash\nsleep 60\n");

  const result = await runDailyPass({
    command: child,
    stateDir: dir,
    timeoutMs: 50,
    killGraceMs: 20,
  });

  assert.equal(result.outcome, "timed_out");
  assert.equal(result.reason, "hard_timeout");
  assert.equal(fs.existsSync(path.join(dir, "daily.lock")), false);
});

test("summarizeSevenDays requires seven real consecutive day keys and preserves no-op reasons", () => {
  const rows = Array.from({ length: 7 }, (_, index) => ({
    day: `2026-07-${String(18 + index).padStart(2, "0")}`,
    outcome: index === 2 ? "no_op" : "pr_open",
    reason: index === 2 ? "no_unattempted_open_issue" : "pr_created",
    issue_number: index === 2 ? null : 100 + index,
    pr_url: index === 2 ? null : `https://github.com/Daisuke134/life-manager/pull/${200 + index}`,
  }));
  assert.equal(summarizeSevenDays(rows).ready, true);

  const missingDay = rows.filter((row) => row.day !== "2026-07-21");
  assert.equal(summarizeSevenDays(missingDay).ready, false);
});

// F2b: never silently start with empty dev-loop state while unmigrated legacy
// state (done.jsonl dedup history) still exists — fail loudly and name the
// migration script. All paths here are temp dirs; the real HOME is untouched.

const {
  assertLegacyDevStateMigrated,
  defaultLegacyDevStateDir,
} = require("./daily-dev-loop");

test("the default legacy dev state dir points at the legacy store, overridable by env", () => {
  const legacyStore = "." + "open" + "claw";
  assert.equal(
    defaultLegacyDevStateDir({ HOME: "/srv/operator-home" }),
    `/srv/operator-home/${legacyStore}/state/life-manager-dev`,
  );
  assert.equal(
    defaultLegacyDevStateDir({ HOME: "/srv/operator-home", LM_LEGACY_STATE_ROOT: "/srv/legacy/state" }),
    "/srv/legacy/state/life-manager-dev",
  );
});

test("an empty new state dir with populated legacy state fails loudly naming the migration script", () => {
  const legacy = tempDir();
  fs.writeFileSync(path.join(legacy, "done.jsonl"), '{"issue":41}\n');
  const fresh = path.join(tempDir(), "state", "life-manager-dev");
  assert.throws(
    () => assertLegacyDevStateMigrated(fresh, legacy),
    /migrate-legacy-state\.sh/,
  );
  // An existing-but-empty new state dir is equally unmigrated.
  fs.mkdirSync(fresh, { recursive: true });
  assert.throws(
    () => assertLegacyDevStateMigrated(fresh, legacy),
    /migrate-legacy-state\.sh/,
  );
});

test("the guard passes when legacy state is absent or the new state dir is populated", () => {
  const legacyEmpty = tempDir();
  const fresh = path.join(tempDir(), "state", "life-manager-dev");
  assertLegacyDevStateMigrated(fresh, legacyEmpty);
  assertLegacyDevStateMigrated(fresh, path.join(legacyEmpty, "never-created"));

  const legacy = tempDir();
  fs.writeFileSync(path.join(legacy, "done.jsonl"), '{"issue":41}\n');
  const migrated = tempDir();
  fs.writeFileSync(path.join(migrated, "done.jsonl"), '{"issue":41}\n');
  assertLegacyDevStateMigrated(migrated, legacy);
});

test("runDailyPass refuses to run while unmigrated legacy state exists", async () => {
  const legacy = tempDir();
  fs.writeFileSync(path.join(legacy, "done.jsonl"), '{"issue":41}\n');
  const fresh = path.join(tempDir(), "state", "life-manager-dev");
  const child = path.join(tempDir(), "never-run.sh");
  writeExecutable(child, "#!/bin/bash\nexit 0\n");

  await assert.rejects(
    runDailyPass({ command: child, stateDir: fresh, legacyStateDir: legacy }),
    /migrate-legacy-state\.sh/,
  );
  assert.equal(fs.existsSync(fresh), false, "the guard must fire before state creation");
});

test("appendLedgerEntry keeps every failure reason the D0 script writes", () => {
  const d0 = fs.readFileSync(path.join(__dirname, "../scripts/life-manager-dev-d0.sh"), "utf8");
  const written = [...d0.matchAll(/write_result "[a-z_]+" "([a-z0-9_]+)"/g)].map((m) => m[1]);
  assert.ok(written.includes("recovery_class_unresolved") && written.includes("candidate_preflight_red"));
  const dir = tempDir();
  for (const reason of new Set(written)) {
    const row = appendLedgerEntry(path.join(dir, "daily-ledger.jsonl"), {
      run_id: "20260927T000000-1", day: "2026-09-27",
      started_at: "2026-09-27T00:00:00.000Z", finished_at: "2026-09-27T00:00:01.000Z",
      outcome: "failed", reason, issue_number: 1, pr_url: null,
      duration_ms: 1000, recovered_stale_lock: false,
    });
    assert.equal(row.reason, reason, `${reason} was masked as ${row.reason}`);
  }
});
