"use strict";

// One daily self-build pass (spec §10 row 10f, §9.3 DEV loop).
//
// 10e built the merge guard: a PR goes in, an 8-stage pipeline decides, and a hash-chained row is
// appended to $LM_DEV_GUARD_LEDGER. What 10e deliberately did NOT build is the thing that decides
// WHICH PR to hand it, once a day, with nobody watching. That is this file.
//
// One pass, in order:
//
//   1. list the open error-fix PRs the loop itself produced — its own branch prefix AND its own
//      body marker, so a human's PR is never touched by unattended machinery;
//   2. run the guard's OWN eligibility check over them, dry — no merge, no deploy, no writes —
//      and pick the OLDEST that passes (oldest first, so a PR can never be starved by newer work);
//   3. run the merge guard end to end on that one PR, under a wall-clock budget;
//   4. append exactly one day row to $LM_SELFBUILD_LEDGER.
//
// A day with nothing to do still writes a row. So does a day that could not read the backlog at
// all. The spec's done condition is "各日 issue/PR/no-op 理由" — seven distinct days each carrying
// an honest outcome — so a silent day is indistinguishable from a dead loop, and a loop that skips
// its ledger on quiet days can claim any streak it likes.
//
// WHAT THIS FILE MAY NOT DECIDE. It picks the candidate; it never decides the outcome. Every gate
// (review, blocked actions, tests, merge, deploy, rollback) lives in the guard, and the guard's own
// files are refused at eligibility, so a loop-authored PR cannot weaken them. This orchestrator and
// the reviewer it spawns are handed to the guard as `protectedPaths` for the same reason: a PR that
// rewrote the picker could point `--review-cmd` at a rubber stamp, and the guard would then dutifully
// protect the rubber stamp instead. SELF_BUILD_PROTECTED_PATHS closes that door — those three files
// change only through a human-merged PR.
//
// HOW THAT CLAIM IS ACTUALLY MADE TRUE, since a comment is not a mechanism: the paths are passed
// to `deps.runGuard`, which puts them on the guard CLI's argv as repeated `--protect <path>`, and
// the CLI unions them with the paths it resolves from `--review-cmd`. Until 2026-07-27 they were
// accepted here and silently dropped by the spawn, so this paragraph described nothing.
//
// TWO MORE THINGS THIS FILE PROMISES, both of them mechanisms rather than intentions:
//   * TOCTOU. The head oid the precheck judged travels to the guard as `--expect-head`, and the
//     guard refuses at stage one if the branch has been force-pushed since. Everything decided
//     here was decided about one specific commit.
//   * The budget never interrupts a merge. When the wall clock runs out, the guard's progress file
//     is consulted: pre-merge stages are killed, and a guard that has entered `merge` is waited
//     on to completion. A kill landing mid-merge would leave main changed, unrecorded and
//     un-rolled-back, which is worse than any overrun.
//
// This file contains no schedule wiring. Enabling launchd is an explicit operator step
// (scripts/enable-self-build-launchd.sh), never something the loop does to itself.

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  GUARD_LOCK_STALE_MS,
  appendGuardRun,
  evaluateEligibility,
  guardLedgerPath,
  guardLockPath,
  readGuardProgress,
  readLedgerRows,
} = require("./dev-merge-guard.js");


// The three files that, between them, choose the PR and choose the judge. Handed to the guard as
// protected paths on every run. They are NOT in GUARD_SELF_PATHS (which is 10e's static list) —
// they are supplied dynamically, exactly like the resolved --review-cmd, and land on the same
// `deny:guard-self` rule.
const SELF_BUILD_PROTECTED_PATHS = Object.freeze([
  "apps/life-manager/lib/self-build-daily.js",
  "apps/life-manager/scripts/self-build-daily.js",
  "apps/life-manager/scripts/dev-adversary-review.js",
]);

// Closed sets. An outcome that is not in one of these is a bug being loud, not a day being green.
const GUARD_VERDICTS = Object.freeze([
  "merged_deployed",
  "merged_unverified",
  "rolled_back",
  "rollback_failed",
  "stopped",
  "errored",
  "locked",
]);

const SELF_BUILD_VERDICTS = Object.freeze([
  ...GUARD_VERDICTS,
  "no_op",
  "timeout",
  "unrecognized_guard_verdict",
]);

const NO_OP_REASONS = Object.freeze([
  "no_open_error_fix_pr",
  "no_eligible_pr",
  "guard_lock_held",
  // `gh pr list` failed. Distinct from "no PRs", because a day with an unreadable backlog proved
  // nothing about the backlog, and a loop that files the two under one reason is claiming to have
  // looked when it could not.
  "pr_list_unavailable",
  // Not a reason: a sentinel for a reason nobody declared. See close().
  "unrecognized_no_op_reason",
]);

const SEVEN_DAYS = 7;

// 45 minutes, and the arithmetic is the whole point. The guard's own post-merge bounds are a 10 min
// health poll AND a 15 min deploy-freshness poll — 25 minutes AFTER the merge, before which sit
// review (12 min budget) and the full test suite. The previous 20 minutes was therefore not a
// generous bound but an impossible one: every successfully merging day would have been killed
// mid-deploy and filed as a timeout, and the loop's only good outcome was the one it could never
// reach. 45 leaves the guard's worst case room and still refuses to hold the lock into the next
// day's pass. It is also NOT the merge safety mechanism — that is the merge-aware kill below.
const DEFAULT_BUDGET_MS = 45 * 60 * 1000;

// Once the guard announces this stage it has begun doing irreversible things, and the budget stops
// being allowed to end it.
const POINT_OF_NO_RETURN_STAGE = "merge";


function selfBuildLedgerPath(env = process.env) {
  if (env.LM_SELFBUILD_LEDGER) return env.LM_SELFBUILD_LEDGER;
  const home = env.HOME || os.homedir();
  return path.join(home, ".life-manager/state/self-build-days.jsonl");
}


function tokyoDay(date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}


function readMetricFocus(options = {}) {
  const home = options.home || process.env.HOME || os.homedir();
  const file = options.statePath
    || process.env.LM_MONEY_STATE
    || path.join(home, ".local/state/life-manager/state/STATE.md");
  let raw;
  try { raw = fs.readFileSync(file, "utf8"); } catch { return null; }
  const values = {};
  for (const line of raw.split("\n")) {
    const match = line.match(/^([a-z_]+):\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (match) values[match[1]] = Number(match[2]);
  }
  const stages = [
    ["calendar", values.funnel_users, values.funnel_calendar_connected],
    ["phone", values.funnel_calendar_connected, values.funnel_phone_saved],
    ["call", values.funnel_phone_saved, values.funnel_call_opt_in],
    ["paid", values.funnel_call_opt_in, values.funnel_paid],
  ];
  const drops = stages
    .filter(([, from, to]) => Number.isFinite(from) && Number.isFinite(to))
    .map(([focus, from, to]) => ({ focus, drop: Math.max(0, from - to) }));
  if (!drops.length) return null;
  drops.sort((left, right) => right.drop - left.drop || left.focus.localeCompare(right.focus));
  return { focus: drops[0].focus, values, statePath: file };
}


// Read-only. The guard's acquireGuardLock is what actually steals a stale lock; this only tells the
// day row WHY the takeover happened, and stops the pass from starting a second guard while a live
// one is mid-merge.
//
// Staleness is AGE ALONE, because that is exactly what acquireGuardLock uses, and the two must
// agree. The old pidAlive veto made them disagree in the worst possible direction: a PID number
// recycled by any unrelated process would make this function call a 3-hour-old lock "live" and
// refuse the day, while the guard — had it been asked — would have stolen the lock and run. An
// unattended loop wedged indefinitely by a coincidence of PID numbers is a worse failure than a
// slow guard being displaced, and the guard's own O_EXCL claim is what actually decides the race.
function inspectGuardLock(lockPath, options = {}) {
  const nowMs = (options.now ? options.now() : new Date()).getTime();
  const staleMs = options.staleMs ?? GUARD_LOCK_STALE_MS;

  let raw;
  try {
    raw = fs.readFileSync(lockPath, "utf8");
  } catch {
    return { held: false, stale: false, ageMs: null, holder: null };
  }

  let holder = null;
  try { holder = JSON.parse(raw); } catch { holder = null; }
  const heldSinceMs = Number(holder?.acquired_at_ms);
  // An unreadable/undated lock has no age we can trust; infinitely old is the honest reading, and
  // it is what acquireGuardLock assumes too.
  const ageMs = Number.isFinite(heldSinceMs) ? nowMs - heldSinceMs : Infinity;
  return {
    held: true,
    stale: ageMs >= staleMs,
    ageMs: Number.isFinite(ageMs) ? ageMs : null,
    holder,
  };
}


// Oldest first. `createdAt` is the authority; the PR number is only the tie-break, because numbers
// are shared with issues and a reopened PR can carry a low number with a recent creation date.
function orderCandidates(list, options = {}) {
  const metricFocus = String(options.metricFocus?.focus || options.metricFocus || "").trim();
  const marker = metricFocus ? `[lm-metric-focus:${metricFocus}]` : "";
  return [...(Array.isArray(list) ? list : [])]
    .filter((entry) => Number.isInteger(Number(entry?.number)) && Number(entry.number) > 0)
    .map((entry) => ({
      ...entry,
      number: Number(entry.number),
      createdAt: String(entry.createdAt || ""),
      metricMatch: Boolean(marker && String(entry.body || "").includes(marker)),
    }))
    .sort((left, right) => {
      if (left.metricMatch !== right.metricMatch) return left.metricMatch ? -1 : 1;
      const a = Date.parse(left.createdAt);
      const b = Date.parse(right.createdAt);
      if (Number.isFinite(a) && Number.isFinite(b) && a !== b) return a - b;
      return left.number - right.number;
    });
}


// The guard's OWN eligibility function, run dry. Two reasons it is this one and not a private copy:
// a second implementation would drift, and a PR the precheck accepts but the guard refuses burns a
// whole day on a run that was never going to merge.
async function pickEligiblePr({ deps, options = {} }) {
  const protectedPaths = options.protectedPaths || [...SELF_BUILD_PROTECTED_PATHS];
  let listed;
  try {
    listed = await deps.listErrorFixPrs();
  } catch (error) {
    // `gh pr list` failing is not "no PRs". A day that could not read the backlog proved nothing
    // about the backlog, and letting the throw escape meant the day wrote NO ledger row at all —
    // a broken gh looking exactly like a loop that never ran, which is the one thing the ledger
    // exists to make impossible.
    return {
      prNumber: null,
      pr: null,
      eligibility: null,
      skipped: [],
      candidates: 0,
      listError: String(error?.message || error),
    };
  }
  const candidates = orderCandidates(listed, { metricFocus: options.metricFocus });
  const skipped = [];

  for (const candidate of candidates) {
    let pr = null;
    let changedFiles = null;
    try {
      pr = await deps.getPullRequest(candidate.number);
      const listed = await deps.listChangedFiles({
        base: pr?.baseRefName ?? "main",
        headOid: pr?.headRefOid,
        headRefName: pr?.headRefName,
      });
      changedFiles = Array.isArray(listed) ? listed.map(String) : null;
    } catch (error) {
      skipped.push({ pr: candidate.number, reasons: [`precheck_failed:${error.message}`] });
      continue;
    }

    const eligibility = evaluateEligibility(pr, {
      allowedAuthors: options.allowedAuthors,
      protectedPaths,
      changedFiles,
    });
    // An unreadable file list is not an empty one — the guard says so at stage one and so does this.
    if (eligibility.ok && changedFiles !== null) {
      return {
        prNumber: candidate.number,
        pr,
        eligibility,
        skipped,
        candidates: candidates.length,
        // The head THIS precheck judged. It travels to the guard so the guard can refuse a branch
        // that was force-pushed in between: everything decided above was decided about this commit.
        headOid: String(pr?.headRefOid || "") || null,
        listError: null,
      };
    }
    const reasons = [...eligibility.reasons];
    if (changedFiles === null) reasons.push("changed_files_unreadable");
    skipped.push({ pr: candidate.number, reasons });
  }

  return {
    prNumber: null,
    pr: null,
    eligibility: null,
    skipped,
    candidates: candidates.length,
    headOid: null,
    listError: null,
  };
}


// The chained append (prev = sha256 of the previous row's record_hash) is the guard's, on purpose:
// it lives in a file the loop is forbidden to modify, so the code that makes the ledger
// tamper-EVIDENT cannot itself be edited by an unattended merge. Same honest limit as 10e's ledger —
// evident, not proof; a local attacker with write access can recompute the whole chain.
function appendSelfBuildDay(ledgerPath, row) {
  return appendGuardRun(ledgerPath, row);
}


function readSelfBuildDays(ledgerPath) {
  return readLedgerRows(ledgerPath).filter((row) => row && row.__unparseable === undefined);
}


// The 10f done condition, read out rather than asserted. `distinctDays` is what the spec counts
// (seven distinct real days); `consecutiveDays` is reported alongside so a gap is visible instead of
// silently inflating the streak. Two runs on one day are ONE day — otherwise a loop could be kicked
// seven times in an afternoon and claim a week.
function selfBuildStreak(source) {
  const rows = Array.isArray(source) ? source : readSelfBuildDays(source);
  const days = new Set();
  for (const row of rows) {
    const day = String(row?.day ?? "");
    if (/^\d{4}-\d{2}-\d{2}$/.test(day)) days.add(day);
  }
  const sorted = [...days].sort();

  let consecutiveDays = sorted.length > 0 ? 1 : 0;
  for (let index = sorted.length - 1; index > 0; index -= 1) {
    const previous = Date.parse(`${sorted[index - 1]}T00:00:00Z`);
    const current = Date.parse(`${sorted[index]}T00:00:00Z`);
    if (current - previous !== 86_400_000) break;
    consecutiveDays += 1;
  }

  return {
    days: sorted,
    distinctDays: sorted.length,
    consecutiveDays,
    lastDay: sorted.at(-1) ?? null,
    ready: sorted.length >= SEVEN_DAYS,
    remaining: Math.max(0, SEVEN_DAYS - sorted.length),
    required: SEVEN_DAYS,
  };
}


// After a killed run, the guard may or may not have got as far as writing its own row. If it did,
// that row is the truth about how far the run got and the day row points at it; if it did not, the
// day row says so rather than inventing a stage.
function findPartialGuardRow(rows, prNumber, startedAtMs) {
  const match = (Array.isArray(rows) ? rows : []).filter((row) => {
    if (Number(row?.pr) !== Number(prNumber)) return false;
    const started = Date.parse(String(row?.started_at || ""));
    // 60s of slack: the guard stamps started_at a moment after this pass does.
    return !Number.isFinite(started) || started >= startedAtMs - 60_000;
  });
  return match.at(-1) ?? null;
}


async function runSelfBuildDay({ deps, options = {} }) {
  if (!deps || typeof deps.listErrorFixPrs !== "function" || typeof deps.runGuard !== "function") {
    throw new Error("self_build_daily_deps_required");
  }
  const now = deps.now || (() => new Date());
  const started = now();
  const startedAtMs = started.getTime();
  const runId = `${started.toISOString().replace(/\D/g, "").slice(0, 14)}-selfbuild-${crypto.randomBytes(4).toString("hex")}`;

  const ledgerPath = options.ledgerPath || selfBuildLedgerPath();
  const guardLedger = options.guardLedgerPath || guardLedgerPath();
  const lockPath = options.guardLockPath || guardLockPath(guardLedger);
  const budgetMs = options.budgetMs ?? DEFAULT_BUDGET_MS;
  const protectedPaths = options.protectedPaths || [...SELF_BUILD_PROTECTED_PATHS];
  const readGuardLedger = deps.readGuardLedger || (() => readLedgerRows(guardLedger));
  const progressFile = options.progressFile ?? null;
  const readProgress = deps.readGuardProgress || (() => readGuardProgress(progressFile));

  const day = {
    schema_version: 1,
    kind: "self_build_day",
    run_id: runId,
    day: options.day || tokyoDay(started),
    started_at: started.toISOString(),
    finished_at: started.toISOString(),
    duration_ms: 0,
    pr: null,
    verdict: "no_op",
    guard_verdict: null,
    guard_run_ref: null,
    no_op_reason: null,
    no_op_reason_raw: null,
    recovered_stale_lock: false,
    stolen_lock_holder: null,
    budget_exceeded: false,
    merge_in_flight: false,
    cleanup_ran: false,
    candidates_considered: 0,
    skipped: [],
    error: null,
    metric_focus: options.metricFocus?.focus || options.metricFocus || null,
  };

  const close = () => {
    const finished = now();
    day.finished_at = finished.toISOString();
    day.duration_ms = Math.max(0, finished.getTime() - startedAtMs);
    if (!SELF_BUILD_VERDICTS.includes(day.verdict)) day.verdict = "unrecognized_guard_verdict";
    // A reason nobody declared is a BUG in this file, and the old code rewrote it to
    // "no_eligible_pr" — the ledger quietly laundering a defect into the most ordinary-looking
    // day there is. The sentinel cannot be mistaken for a real reason, and the raw value is kept
    // beside it so whoever reads the row can see what the code actually tried to say.
    if (day.no_op_reason !== null && !NO_OP_REASONS.includes(day.no_op_reason)) {
      day.no_op_reason_raw = day.no_op_reason;
      day.no_op_reason = "unrecognized_no_op_reason";
    }
    return appendSelfBuildDay(ledgerPath, day);
  };

  if (options.forceNoOpReason) {
    // Test seam only: the normaliser above has to be exercisable without a fabricated bug.
    day.no_op_reason = String(options.forceNoOpReason);
    return close();
  }

  const lock = inspectGuardLock(lockPath, { now, staleMs: options.lockStaleMs });
  day.recovered_stale_lock = lock.held && lock.stale;
  if (day.recovered_stale_lock) day.stolen_lock_holder = lock.holder ?? null;
  if (lock.held && !lock.stale) {
    // Somebody else's guard is mid-run. Starting a second one would race a merge, so the day is
    // recorded as locked — a real, honest day, not a skipped one.
    day.verdict = "locked";
    day.no_op_reason = "guard_lock_held";
    return close();
  }

  const picked = await pickEligiblePr({ deps, options: { ...options, protectedPaths } });
  day.candidates_considered = picked.candidates;
  day.skipped = picked.skipped;
  if (picked.listError) {
    day.verdict = "no_op";
    day.no_op_reason = "pr_list_unavailable";
    day.error = picked.listError;
    return close();
  }
  if (picked.prNumber === null) {
    day.verdict = "no_op";
    day.no_op_reason = picked.candidates === 0 ? "no_open_error_fix_pr" : "no_eligible_pr";
    return close();
  }
  day.pr = picked.prNumber;

  // ---------------------------------------------------------------------------------------------
  // The merge-aware kill.
  //
  // The budget exists so a wedged guard cannot hold the lock into tomorrow's pass. But the guard
  // is killed by process GROUP, and a SIGTERM that lands between `git merge` and the guard's own
  // ledger append leaves main merged, the day unrecorded, and no rollback attempted — the loop
  // having changed production and lost the note saying so. So the budget expiring is a QUESTION,
  // not a verdict: ask the guard's progress file which stage it is in.
  //   * pre-merge  -> kill. Nothing irreversible has happened; the day is an honest timeout.
  //   * merge, or anything after it -> do NOT signal. Wait, however long it takes, and report the
  //     guard's real verdict. An overrun is recorded on the row (budget_exceeded) so a run that
  //     took 90 minutes never looks like one that took 9.
  // An unreadable progress file reads as pre-merge, which is the safe default: the guard writes it
  // BEFORE touching git, so "no file" cannot mean "already merging".
  // ---------------------------------------------------------------------------------------------
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    day.budget_exceeded = true;
    const progress = readProgress(progressFile);
    const stagesBegun = progress?.stagesBegun ?? [];
    if (stagesBegun.includes(POINT_OF_NO_RETURN_STAGE)) {
      day.merge_in_flight = true;
      return;
    }
    timedOut = true;
    controller.abort(new Error("self_build_budget_exceeded"));
  }, budgetMs);
  if (typeof timer.unref === "function") timer.unref();

  let guardResult = null;
  let guardError = null;
  try {
    guardResult = await deps.runGuard({
      prNumber: picked.prNumber,
      signal: controller.signal,
      // The header's claim, finally made true: these really do reach the guard's argv now.
      // expectHead makes the picker's decision falsifiable — the guard refuses a head that moved.
      options: { protectedPaths, expectHead: picked.headOid, progressFile },
    });
  } catch (error) {
    guardError = error;
  } finally {
    clearTimeout(timer);
  }

  if (timedOut) {
    // The group kill reaps whatever the guard had spawned, including the `git worktree add` it
    // uses to run the suite. A half-created worktree left registered would make tomorrow's pass
    // fail at a stage that has nothing to do with tomorrow's PR, so it is pruned and said so.
    try {
      await deps.pruneWorktrees?.();
      day.cleanup_ran = true;
    } catch (error) {
      day.error = `worktree_prune_failed: ${String(error?.message || error)}`;
    }
    const partial = findPartialGuardRow(readGuardLedger(), picked.prNumber, startedAtMs);
    day.verdict = "timeout";
    day.guard_run_ref = partial?.run_id ?? guardResult?.runId ?? null;
    day.guard_verdict = partial ? String(partial.verdict ?? null) : null;
    if (partial && day.guard_verdict === "null") day.guard_verdict = null;
    return close();
  }

  if (guardError) {
    day.verdict = "errored";
    day.error = String(guardError?.message || guardError);
    day.guard_run_ref = guardResult?.runId ?? null;
    try { await deps.alert?.(`self-build day ${day.day}: the guard threw — ${day.error}`); } catch {}
    return close();
  }

  const verdict = String(guardResult?.verdict ?? "");
  day.guard_verdict = verdict || null;
  day.guard_run_ref = guardResult?.runId ?? null;
  day.verdict = GUARD_VERDICTS.includes(verdict) ? verdict : "unrecognized_guard_verdict";
  if (day.verdict === "unrecognized_guard_verdict") {
    try {
      await deps.alert?.(
        `self-build day ${day.day}: the guard answered an unknown verdict "${verdict}" for PR`
        + ` #${picked.prNumber}. Treat the day as unproven until a human reads the guard ledger.`,
      );
    } catch {}
  }
  return close();
}


module.exports = {
  DEFAULT_BUDGET_MS,
  GUARD_VERDICTS,
  NO_OP_REASONS,
  POINT_OF_NO_RETURN_STAGE,
  SELF_BUILD_PROTECTED_PATHS,
  SELF_BUILD_VERDICTS,
  SEVEN_DAYS,
  appendSelfBuildDay,
  inspectGuardLock,
  orderCandidates,
  readMetricFocus,
  pickEligiblePr,
  readSelfBuildDays,
  runSelfBuildDay,
  selfBuildLedgerPath,
  selfBuildStreak,
  tokyoDay,
};
