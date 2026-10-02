#!/usr/bin/env node
"use strict";

// CLI entry for the unattended merge guard (spec §10 row 10e).
//
//   node scripts/dev-merge-guard.js --pr 1094 --review-cmd "my-fresh-reviewer"
//   node scripts/dev-merge-guard.js --pr 1094 --review-cmd "..." --dry-run
//   node scripts/dev-merge-guard.js --pr 1094 --review-cmd "..." \
//     --protect apps/life-manager/lib/self-build-daily.js \
//     --expect-head <40-hex> --progress-file /path/progress.json
//
// --protect       repeatable; unioned with the paths resolved from --review-cmd and refused at
//                 eligibility, so a caller can protect the machinery that chose this PR.
// --expect-head   the head oid the CALLER decided about. A head that moved since is refused
//                 (`head_moved`) rather than reviewed and merged unseen.
// --progress-file where each stage BEGINNING is announced, so a parent enforcing a wall-clock
//                 budget can tell a killable pre-merge stall from a merge it must not interrupt.
//
// --review-cmd receives the PR diff on stdin and must answer on stdout with
// {"verdict":"pass"|"fail","findings":[...]}. Anything else counts as FAIL. In production this
// command spawns a fresh-context reviewer; the guard only cares about the JSON contract.
//
// This atomic deliberately installs no schedule. Re-enabling the daily run belongs to 10f.

const { execFileSync } = require("node:child_process");
const {
  createGuardDeps,
  createReviewCommandHook,
  guardLedgerPath,
  resolveReviewCommandPaths,
  runMergeGuard,
} = require("../lib/dev-merge-guard.js");


function parseArgs(argv) {
  const options = { dryRun: false, protect: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--pr") options.pr = Number(argv[++index]);
    else if (flag === "--review-cmd") options.reviewCmd = String(argv[++index] || "");
    else if (flag === "--ledger") options.ledger = String(argv[++index] || "");
    // Repeatable. The caller knows things the guard cannot infer: which files, in ITS opinion,
    // decide who gets reviewed and by whom. resolveReviewCommandPaths finds the judge; --protect
    // is how a caller adds the picker that chose the defendant.
    else if (flag === "--protect") options.protect.push(String(argv[++index] || ""));
    else if (flag === "--expect-head") options.expectHead = String(argv[++index] || "");
    else if (flag === "--progress-file") options.progressFile = String(argv[++index] || "");
    else if (flag === "--dry-run") options.dryRun = true;
    else throw new Error(`dev_merge_guard_argument_invalid: ${flag}`);
  }
  options.protect = options.protect.filter(Boolean);
  if (!Number.isInteger(options.pr) || options.pr < 1) {
    throw new Error("dev_merge_guard_pr_required");
  }
  if (!options.reviewCmd) {
    // A guard with no fresh adversary is not a guard. Refuse rather than silently pass stage 3.
    throw new Error("dev_merge_guard_review_required");
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


async function main() {
  const options = parseArgs(process.argv.slice(2));
  const deps = createGuardDeps({
    exec,
    fetch: globalThis.fetch,
    config: process.env.LM_SELFBUILD_SOURCE_REPO
      ? { repoDir: process.env.LM_SELFBUILD_SOURCE_REPO }
      : undefined,
    ledgerPath: options.ledger || guardLedgerPath(),
  });
  deps.review = createReviewCommandHook(options.reviewCmd, { exec });

  if (options.dryRun) {
    // Everything up to (not including) the merge, so a guard change can be exercised without
    // promoting anything.
    deps.merge = async () => ({ ok: false, reason: "dry_run" });
  }

  // The reviewer is part of the guard. Whatever file `--review-cmd` actually runs is resolved by
  // realpath here and refused at eligibility, so a PR cannot rewrite its own judge — the first
  // half of the two-PR takeover chain dies before the second half is ever written.
  //
  // The union with `--protect` is what makes the daily pass's claim true: the orchestrator that
  // CHOOSES the PR is as load-bearing as the reviewer that judges it, and only the orchestrator
  // knows its own filenames. Union, not replacement — a caller can add protection, never remove it.
  const protectedPaths = [...new Set([
    ...resolveReviewCommandPaths(options.reviewCmd),
    ...options.protect,
  ])];

  const result = await runMergeGuard({
    prNumber: options.pr,
    deps,
    options: {
      protectedPaths,
      expectHead: options.expectHead || null,
      progressFile: options.progressFile || null,
    },
  });
  process.stdout.write(`${JSON.stringify({
    verdict: result.verdict,
    pr: options.pr,
    stopped_at_stage: result.stoppedAtStage,
    stop_reason: result.stopReason,
    stages_passed: result.stagesPassed,
    stages_failed: result.stagesFailed,
    merge_sha: result.mergeSha,
    deploy_id: result.deployId,
    health: result.health,
    rollback: result.rollback,
    post_merge_error: result.postMergeError ?? null,
    ledger_check_ok: result.ledgerCheck?.ok ?? null,
    protected_paths: protectedPaths,
    expected_head: options.expectHead || null,
    run_id: result.runId,
    ledger: deps.ledgerPath,
  })}\n`);
  if (result.verdict !== "merged_deployed") process.exitCode = 3;
}


if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`dev-merge-guard failed: ${error.message}\n`);
    process.exitCode = 1;
  });
}


module.exports = { parseArgs };
