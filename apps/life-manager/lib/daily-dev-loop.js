"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { resolveDataRoot } = require("./runtime-paths");

const OUTCOMES = new Set(["pr_open", "no_op", "failed", "timed_out"]);
const REASONS = new Set([
  "pr_created",
  "no_unattempted_open_issue",
  "overlapping_d0",
  "worktree_mismatch",
  "agent_failed",
  "test_red",
  "no_diff",
  "pr_failed",
  "hard_timeout",
  "child_exit_without_result",
  "invalid_machine_result",
  "recovery_class_unresolved",
  "candidate_preflight_red",
]);

function isPidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function acquireExclusiveLock(lockPath, options = {}) {
  const nowMs = options.nowMs ?? Date.now();
  const staleMs = options.staleMs ?? 30 * 60 * 1000;
  const pid = options.pid ?? process.pid;
  const pidAlive = options.isPidAlive ?? isPidAlive;
  let recoveredStale = false;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const fd = fs.openSync(lockPath, "wx", 0o600);
      fs.writeFileSync(fd, JSON.stringify({ pid, started_ms: nowMs }));
      fs.closeSync(fd);
      let released = false;
      return {
        acquired: true,
        recoveredStale,
        release() {
          if (released) return;
          released = true;
          try {
            const owner = JSON.parse(fs.readFileSync(lockPath, "utf8"));
            if (owner.pid === pid) fs.unlinkSync(lockPath);
          } catch {
            // A missing/replaced lock is not ours to remove.
          }
        },
      };
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      let owner = null;
      try {
        owner = JSON.parse(fs.readFileSync(lockPath, "utf8"));
      } catch {
        owner = {};
      }
      const age = nowMs - Number(owner.started_ms || 0);
      if (attempt === 0 && age > staleMs && !pidAlive(Number(owner.pid))) {
        fs.unlinkSync(lockPath);
        recoveredStale = true;
        continue;
      }
      return { acquired: false, recoveredStale: false, reason: "active_lock" };
    }
  }
  return { acquired: false, recoveredStale: false, reason: "active_lock" };
}

function closedLedgerEntry(input) {
  const outcome = OUTCOMES.has(input.outcome) ? input.outcome : "failed";
  const reason = REASONS.has(input.reason) ? input.reason : "invalid_machine_result";
  const issue = Number(input.issue_number);
  const prUrl = typeof input.pr_url === "string"
    && /^https:\/\/github\.com\/Daisuke134\/life-manager\/pull\/\d+$/.test(input.pr_url)
    ? input.pr_url
    : null;
  return {
    schema_version: 1,
    run_id: String(input.run_id),
    day: String(input.day),
    started_at: String(input.started_at),
    finished_at: String(input.finished_at),
    outcome,
    reason,
    issue_number: Number.isInteger(issue) && issue > 0 ? issue : null,
    pr_url: prUrl,
    duration_ms: Math.max(0, Math.round(Number(input.duration_ms) || 0)),
    recovered_stale_lock: input.recovered_stale_lock === true,
  };
}

function appendLedgerEntry(ledgerPath, input) {
  const entry = closedLedgerEntry(input);
  fs.mkdirSync(path.dirname(ledgerPath), { recursive: true, mode: 0o700 });
  fs.appendFileSync(ledgerPath, `${JSON.stringify(entry)}\n`, { mode: 0o600 });
  fs.chmodSync(ledgerPath, 0o600);
  return entry;
}

function tokyoDay(date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function safeMachineResult(result, childCode) {
  if (!result || typeof result !== "object") {
    return {
      outcome: "failed",
      reason: "child_exit_without_result",
      issue_number: null,
      pr_url: null,
    };
  }
  const outcome = result.status;
  if (!OUTCOMES.has(outcome) || !REASONS.has(result.reason)) {
    return {
      outcome: "failed",
      reason: "invalid_machine_result",
      issue_number: null,
      pr_url: null,
    };
  }
  if (childCode !== 0 && outcome !== "failed") {
    return {
      outcome: "failed",
      reason: "invalid_machine_result",
      issue_number: null,
      pr_url: null,
    };
  }
  return {
    outcome,
    reason: result.reason,
    issue_number: result.issue_number,
    pr_url: result.pr_url,
  };
}

function waitForChild(command, env, timeoutMs, killGraceMs) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, [], {
      detached: process.platform !== "win32",
      env,
      stdio: "inherit",
    });
    let timedOut = false;
    let forceTimer = null;
    const timer = setTimeout(() => {
      timedOut = true;
      try {
        if (process.platform !== "win32") process.kill(-child.pid, "SIGTERM");
        else child.kill("SIGTERM");
      } catch {}
      forceTimer = setTimeout(() => {
        try {
          if (process.platform !== "win32") process.kill(-child.pid, "SIGKILL");
          else child.kill("SIGKILL");
        } catch {}
      }, killGraceMs);
      forceTimer.unref();
    }, timeoutMs);
    timer.unref();

    child.once("error", (error) => {
      clearTimeout(timer);
      if (forceTimer) clearTimeout(forceTimer);
      reject(error);
    });
    child.once("close", (code, signal) => {
      clearTimeout(timer);
      if (forceTimer) clearTimeout(forceTimer);
      resolve({ code, signal, timedOut });
    });
  });
}

// Default dev-loop state lives beneath the portable Life Manager data root,
// matching the directory install-life-manager-dev-launchd.sh creates.
function defaultStateDir(env = process.env) {
  return path.join(resolveDataRoot(env), "state", "life-manager-dev");
}

// Named ONLY to detect unmigrated state and refuse to run (fail-loud guard);
// the dev loop never reads the legacy store. LEGACY_DEV_STORE = ".openclaw".
const LEGACY_DEV_STORE = ".openclaw";
function defaultLegacyDevStateDir(env = process.env) {
  const legacyStateRoot = String(env.LM_LEGACY_STATE_ROOT || "").trim()
    || path.join(String(env.HOME || "").trim() || os.homedir(), LEGACY_DEV_STORE, "state");
  return path.join(legacyStateRoot, "life-manager-dev");
}

function hasEntries(dir) {
  try {
    return fs.readdirSync(dir).length > 0;
  } catch {
    return false;
  }
}

// F2b: silently starting with an empty state dir while the legacy dev-loop
// state (done.jsonl dedup history) still exists would re-select completed
// issues. Fail loudly and name the migration script instead.
function assertLegacyDevStateMigrated(stateDir, legacyStateDir) {
  if (!hasEntries(legacyStateDir)) return;
  if (hasEntries(stateDir)) return;
  throw new Error(
    `daily-dev-loop: state dir ${stateDir} is empty but unmigrated legacy dev-loop state exists at `
    + `${legacyStateDir}; run apps/life-manager/scripts/migrate-legacy-state.sh `
    + "(copy-only, the legacy store stays intact) before this loop",
  );
}

async function runDailyPass(options = {}) {
  const stateDir = options.stateDir || defaultStateDir(process.env);
  // Guard the default path always; an explicit stateDir is guarded only when
  // the caller also names the legacy dir (tests use temp dirs, never real HOME).
  const legacyStateDir = options.legacyStateDir
    ?? (options.stateDir ? null : defaultLegacyDevStateDir(process.env));
  if (legacyStateDir) assertLegacyDevStateMigrated(stateDir, legacyStateDir);
  const command = options.command
    || path.join(__dirname, "../scripts/life-manager-dev-d0.sh");
  const timeoutMs = options.timeoutMs ?? 25 * 60 * 1000;
  const killGraceMs = options.killGraceMs ?? 5_000;
  const now = options.now ?? (() => new Date());
  fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });

  const started = now();
  const runId = `${started.toISOString().replace(/\D/g, "").slice(0, 14)}-${process.pid}`;
  const lock = acquireExclusiveLock(path.join(stateDir, "daily.lock"), {
    staleMs: timeoutMs + killGraceMs + 60_000,
  });
  if (!lock.acquired) return { outcome: "no_op", reason: "active_lock" };

  const resultPath = path.join(stateDir, `.result-${runId}.json`);
  let machine;
  try {
    const child = await waitForChild(command, {
      ...process.env,
      LM_DEV_STATE_DIR: stateDir,
      LM_DEV_RESULT_PATH: resultPath,
    }, timeoutMs, killGraceMs);
    if (child.timedOut) {
      machine = {
        outcome: "timed_out",
        reason: "hard_timeout",
        issue_number: null,
        pr_url: null,
      };
    } else {
      let parsed = null;
      try {
        parsed = JSON.parse(fs.readFileSync(resultPath, "utf8"));
      } catch {}
      machine = safeMachineResult(parsed, child.code);
    }
  } catch {
    machine = {
      outcome: "failed",
      reason: "child_exit_without_result",
      issue_number: null,
      pr_url: null,
    };
  }

  const finished = now();
  try {
    const ledgerPath = path.join(stateDir, "daily-ledger.jsonl");
    const entry = appendLedgerEntry(ledgerPath, {
      run_id: runId,
      day: tokyoDay(started),
      started_at: started.toISOString(),
      finished_at: finished.toISOString(),
      duration_ms: finished.getTime() - started.getTime(),
      recovered_stale_lock: lock.recoveredStale,
      ...machine,
    });
    const entries = fs.readFileSync(ledgerPath, "utf8")
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line));
    const summary = summarizeSevenDays(entries);
    const status = {
      schema_version: 1,
      ready: summary.ready,
      consecutive_days: summary.consecutiveDays,
      evaluated_at: finished.toISOString(),
    };
    const statusPath = path.join(stateDir, "seven-day-status.json");
    const tempStatusPath = `${statusPath}.${process.pid}.tmp`;
    fs.writeFileSync(tempStatusPath, JSON.stringify(status), { mode: 0o600 });
    fs.renameSync(tempStatusPath, statusPath);
    return { ...entry, seven_day_ready: status.ready };
  } finally {
    try { fs.unlinkSync(resultPath); } catch {}
    lock.release();
  }
}

function summarizeSevenDays(entries) {
  const byDay = new Map();
  for (const entry of entries) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(String(entry.day))) {
      byDay.set(entry.day, entry);
    }
  }
  const allDays = [...byDay.keys()].sort();
  let consecutiveDays = allDays.length > 0 ? 1 : 0;
  for (let index = allDays.length - 1; index > 0; index -= 1) {
    const previous = Date.parse(`${allDays[index - 1]}T00:00:00Z`);
    const current = Date.parse(`${allDays[index]}T00:00:00Z`);
    if (current - previous !== 86_400_000) break;
    consecutiveDays += 1;
  }
  const days = allDays.slice(-Math.min(7, consecutiveDays));
  return {
    ready: consecutiveDays >= 7,
    consecutiveDays,
    days,
    entries: days.map((day) => byDay.get(day)),
  };
}

module.exports = {
  acquireExclusiveLock,
  appendLedgerEntry,
  assertLegacyDevStateMigrated,
  defaultLegacyDevStateDir,
  defaultStateDir,
  runDailyPass,
  summarizeSevenDays,
};
