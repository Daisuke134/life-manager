#!/usr/bin/env node
"use strict";

// CLI entry for one daily self-build pass (spec §10 row 10f).
//
//   node scripts/self-build-daily.js                 # one real pass
//   node scripts/self-build-daily.js --dry-run       # pick + precheck only, guard never runs
//   node scripts/self-build-daily.js --status        # read the ledger, print the 7-day readout
//
// Prints ONE JSON object on stdout: the day row plus the seven-day readout. The launchd entrypoint
// (skills/life-manager/self-build-daily.sh) reads that object and reports it to Telegram verbatim.
//
// The guard runs as a CHILD PROCESS, not in-process, for one reason: the wall-clock budget has to
// be enforceable. An in-process guard stuck in a network read cannot be interrupted; a detached
// child can have its whole process group killed. The child is `scripts/dev-merge-guard.js`.
//
// That kill is MERGE-AWARE. The guard announces every stage it begins into a progress file, and a
// guard that has entered the merge stage is never signalled — it is waited on. See lib/.
//
// This file installs no schedule. See scripts/enable-self-build-launchd.sh.

const os = require("node:os");
const path = require("node:path");
const { execFileSync, spawn } = require("node:child_process");

const {
  createGuardDeps,
  guardLedgerPath,
  guardLockPath,
  readLedgerRows,
} = require("../lib/dev-merge-guard.js");
const {
  DEFAULT_BUDGET_MS,
  SELF_BUILD_PROTECTED_PATHS,
  readSelfBuildDays,
  readMetricFocus,
  runSelfBuildDay,
  selfBuildLedgerPath,
  selfBuildStreak,
} = require("../lib/self-build-daily.js");

const APP_DIR = path.resolve(__dirname, "..");
const REPO_DIR = path.resolve(APP_DIR, "../..");
const REPO = "Daisuke134/life-manager";
const GUARD_CLI = path.join(APP_DIR, "scripts/dev-merge-guard.js");
const REVIEW_CLI = path.join(APP_DIR, "scripts/dev-adversary-review.js");

// Only branches the loop itself produces. A hand-written branch is a human's PR and a human merges
// it; the unattended path never touches work it did not create.
//
// MEASURED, not guessed: scripts/life-manager-dev-d0.sh line ~110 is
// `BRANCH="${LM_DEV_BRANCH:-feature/lm-dev-$NUM}"`, and that is the only branch the producer ever
// creates. The old pattern also accepted `fix/<anything>`, which is every hand-shaped branch a
// human has ever pushed to this repo — the unattended merger was one `fix/typo` away from merging
// somebody's work in their sleep. The guard's own BRANCH_PATTERNS still allow `fix/…` because a
// human may hand the guard such a PR deliberately; this picker, which chooses with nobody
// watching, may not.
const LOOP_BRANCH = /^feature\/lm-dev-[1-9][0-9]*$/;
const LOOP_AUTHORS = new Set(["Daisuke134"]);

// A branch name is a convention, not authorship: anyone with push access can create
// `feature/lm-dev-9999`, and the author login is the same human either way, since the loop pushes
// as Dais. So the producer stamps this marker into every PR body it opens, and nothing without it
// is treated as loop-authored. Changing it means changing BOTH files, which is the point.
const LOOP_PR_MARKER = "[lm-dev-loop]";


function parseArgs(argv) {
  const options = { dryRun: false, status: false };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--dry-run") options.dryRun = true;
    else if (flag === "--status") options.status = true;
    else if (flag === "--ledger") options.ledger = String(argv[++index] || "");
    else if (flag === "--budget-ms") options.budgetMs = Number(argv[++index]);
    else throw new Error(`self_build_daily_argument_invalid: ${flag}`);
  }
  return options;
}


function exec(file, args, execOptions = {}) {
  return execFileSync(file, args, {
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    stdio: ["pipe", "pipe", "pipe"],
    ...execOptions,
  });
}


// One detached guard child, killable as a group. Resolves with the guard's own stdout JSON, or with
// null when the run was aborted/unparseable — the caller then reads the guard ledger for the truth.
//
// Every argument below used to be dropped here. `options` arrived from runSelfBuildDay carrying
// protectedPaths and went nowhere, so the library header's claim that the picker and the judge were
// handed to the guard was simply untrue. They are on the argv now, and so is the head the picker
// judged and the progress file the merge-aware kill reads.
function spawnGuard({
  prNumber,
  signal,
  reviewCommand,
  protectedPaths = [],
  expectHead = null,
  progressFile = null,
  guardCli = GUARD_CLI,
}) {
  return new Promise((resolve, reject) => {
    const args = [guardCli, "--pr", String(prNumber), "--review-cmd", reviewCommand];
    for (const protectedPath of protectedPaths) args.push("--protect", String(protectedPath));
    if (expectHead) args.push("--expect-head", String(expectHead));
    if (progressFile) args.push("--progress-file", String(progressFile));

    const child = spawn(process.execPath, args, {
      cwd: APP_DIR,
      detached: process.platform !== "win32",
      env: process.env,
      stdio: ["ignore", "pipe", "inherit"],
    });

    let stdout = "";
    child.stdout.on("data", (chunk) => { stdout += String(chunk); });

    const killGroup = (sig) => {
      try {
        if (process.platform !== "win32") process.kill(-child.pid, sig);
        else child.kill(sig);
      } catch {
        // already gone
      }
    };
    const onAbort = () => {
      killGroup("SIGTERM");
      setTimeout(() => killGroup("SIGKILL"), 5_000).unref();
    };
    signal?.addEventListener("abort", onAbort, { once: true });

    child.once("error", (error) => {
      signal?.removeEventListener("abort", onAbort);
      reject(error);
    });
    child.once("close", () => {
      signal?.removeEventListener("abort", onAbort);
      let parsed = null;
      try { parsed = JSON.parse(stdout.trim().split("\n").at(-1) || "null"); } catch { parsed = null; }
      resolve(parsed ? { runId: parsed.run_id ?? null, verdict: parsed.verdict ?? null, raw: parsed } : null);
    });
  });
}


function createSelfBuildDeps(io = {}) {
  const guardIo = createGuardDeps({ exec: io.exec || exec, fetch: globalThis.fetch });
  const reviewCommand = io.reviewCommand || `${process.execPath} ${REVIEW_CLI}`;
  const gh = io.gh || ((args) => exec("gh", args));

  return {
    reviewCommand,
    listErrorFixPrs: async () => {
      const raw = gh([
        "pr", "list", "-R", REPO, "--state", "open", "--base", "main", "--limit", "100",
        "--json", "number,createdAt,headRefName,author,body",
      ]);
      const list = JSON.parse(String(raw || "[]"));
      return list
        .filter((pr) => LOOP_BRANCH.test(String(pr?.headRefName || "")))
        .filter((pr) => LOOP_AUTHORS.has(String(pr?.author?.login || "")))
        // Three independent signals, all required. Branch and author are conventions a human can
        // satisfy by accident; the marker is written by the producer and nothing else.
        .filter((pr) => String(pr?.body || "").includes(LOOP_PR_MARKER))
        .map((pr) => ({
          number: Number(pr.number),
          createdAt: String(pr.createdAt),
          title: String(pr.title || ""),
          body: String(pr.body || ""),
        }));
    },
    getPullRequest: guardIo.getPullRequest,
    listChangedFiles: guardIo.listChangedFiles,
    alert: guardIo.alert,
    readGuardLedger: () => readLedgerRows(guardLedgerPath()),
    // Only ever called after a pre-merge kill. `git worktree prune` deregisters worktrees whose
    // directories the group kill left behind; it never removes a live one, so it is safe to run
    // unconditionally on that path.
    pruneWorktrees: io.pruneWorktrees || (async () => {
      exec("git", ["-C", REPO_DIR, "worktree", "prune"]);
      return { ok: true };
    }),
    runGuard: io.runGuard
      || (({ prNumber, signal, options }) => spawnGuard({
        prNumber,
        signal,
        reviewCommand,
        protectedPaths: options?.protectedPaths ?? [],
        expectHead: options?.expectHead ?? null,
        progressFile: options?.progressFile ?? null,
      })),
  };
}


async function main() {
  const options = parseArgs(process.argv.slice(2));
  const ledgerPath = options.ledger || selfBuildLedgerPath();

  if (options.status) {
    process.stdout.write(`${JSON.stringify({
      ledger: ledgerPath,
      streak: selfBuildStreak(readSelfBuildDays(ledgerPath)),
    })}\n`);
    return;
  }

  const deps = createSelfBuildDeps();
  const metricFocus = readMetricFocus();
  if (options.dryRun) {
    // Everything up to (not including) the guard, so the picker can be exercised without promoting
    // anything. Matches `scripts/dev-merge-guard.js --dry-run` in spirit.
    deps.runGuard = async () => ({ runId: null, verdict: "stopped", raw: { dry_run: true } });
  }

  const row = await runSelfBuildDay({
    deps,
    options: {
      ledgerPath,
      guardLedgerPath: guardLedgerPath(),
      guardLockPath: guardLockPath(guardLedgerPath()),
      budgetMs: Number.isFinite(options.budgetMs) ? options.budgetMs : DEFAULT_BUDGET_MS,
      protectedPaths: [...SELF_BUILD_PROTECTED_PATHS],
      metricFocus,
      // Per-run, so a previous day's abandoned file can never be mistaken for today's merge.
      progressFile: path.join(os.tmpdir(), `lm-self-build-progress-${process.pid}.json`),
    },
  });

  process.stdout.write(`${JSON.stringify({
    ...row,
    dry_run: options.dryRun,
    ledger: ledgerPath,
    streak: selfBuildStreak(readSelfBuildDays(ledgerPath)),
  })}\n`);

  // Exit code carries the honest shape of the day: 0 = the pass completed (including a legitimate
  // no-op), 3 = the day ran but did not merge, 1 = the pass itself broke.
  if (row.verdict === "errored") process.exitCode = 1;
  else if (!["merged_deployed", "no_op"].includes(row.verdict)) process.exitCode = 3;
}


if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`self-build-daily failed: ${error?.message || error}\n`);
    process.exitCode = 1;
  });
}


module.exports = { LOOP_BRANCH, LOOP_PR_MARKER, createSelfBuildDeps, parseArgs, spawnGuard };
