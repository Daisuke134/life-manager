"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  evaluatePromotion,
  decideDeploymentOutcome,
} = require("./dev-auto-promote.js");


function validCandidate(patch = {}) {
  return {
    issueNumber: 1088,
    closingIssueNumbers: [1088],
    openPrsForIssue: 1,
    issueIsPrivacySafeError: true,
    baseRefName: "main",
    headOid: "a".repeat(40),
    localHeadOid: "a".repeat(40),
    mergeable: "MERGEABLE",
    changedFiles: [
      "apps/life-manager/lib/calendar-provider-retry.js",
      "apps/life-manager/lib/calendar-provider-retry.test.js",
    ],
    addedLines: [
      "const retryLimit = 2;",
      "module.exports = { retryLimit };",
    ],
    gates: {
      tests: true,
      evals: true,
      privacy: true,
      adversary: true,
      cleanWorktree: true,
    },
    ...patch,
  };
}


test("one privacy-safe error PR inside every guard is promotable", () => {
  assert.deepEqual(evaluatePromotion(validCandidate()), {
    allowed: true,
    reasons: [],
    blockedActions: [],
  });
});


test("one issue and one PR, exact head, mergeability, and every fresh gate are mandatory", () => {
  const cases = [
    [{ closingIssueNumbers: [1088, 1089] }, "issue_count"],
    [{ openPrsForIssue: 2 }, "pr_count"],
    [{ issueIsPrivacySafeError: false }, "issue_contract"],
    [{ baseRefName: "dev" }, "base_branch"],
    [{ localHeadOid: "b".repeat(40) }, "head_drift"],
    [{ mergeable: "CONFLICTING" }, "mergeable"],
    [{ gates: { ...validCandidate().gates, adversary: false } }, "adversary"],
    [{ gates: { ...validCandidate().gates, tests: false } }, "tests"],
  ];
  for (const [patch, reason] of cases) {
    const result = evaluatePromotion(validCandidate(patch));
    assert.equal(result.allowed, false);
    assert.equal(result.reasons.includes(reason), true);
  }
});


test("paths and actions outside the closed production guard are refused", () => {
  const result = evaluatePromotion(validCandidate({
    changedFiles: [
      "apps/life-manager/lib/calendar-provider-retry.js",
      ".github/workflows/bypass.yml",
      "apps/life-manager/migrations/unsafe.sql",
    ],
    addedLines: [
      "railway variable set API_KEY=value",
      "wallet.sendTransaction({ to, value })",
      "sendUnsolicitedEmail(target)",
    ],
  }));
  assert.equal(result.allowed, false);
  assert.equal(result.reasons.includes("path_allowlist"), true);
  assert.deepEqual(result.blockedActions, [
    "migration",
    "outreach_send",
    "secret_change",
    "wallet_transfer",
  ]);
});


test("capability paths and indirect privileged execution are blocked without relying on action names", () => {
  const result = evaluatePromotion(validCandidate({
    changedFiles: ["apps/life-manager/lib/late-notice.js"],
    addedLines: [{
      path: "apps/life-manager/lib/late-notice.js",
      line: 'const capability = process.mainModule.require("node:" + "child_process");',
    }],
  }));
  assert.equal(result.allowed, false);
  assert.deepEqual(result.blockedActions, ["outreach_send", "privileged_execution"]);
});


test("routine additions cannot access inherited secrets, filesystem, or direct network", () => {
  const result = evaluatePromotion(validCandidate({
    changedFiles: ["apps/life-manager/lib/calendar-provider-retry.js"],
    addedLines: [
      {
        path: "apps/life-manager/lib/calendar-provider-retry.js",
        line: "const token = process.env.PROVIDER_TOKEN;",
      },
      {
        path: "apps/life-manager/lib/calendar-provider-retry.js",
        line: 'const fs = require("node:fs");',
      },
      {
        path: "apps/life-manager/lib/calendar-provider-retry.js",
        line: 'await fetch("https:" + "//provider.invalid");',
      },
    ],
  }));
  assert.equal(result.allowed, false);
  assert.deepEqual(result.blockedActions, [
    "filesystem_access",
    "network_execution",
    "secret_access",
  ]);
});


test("the guard policy source is not mistaken for an executed blocked action", () => {
  const policySource = fs.readFileSync(path.join(__dirname, "dev-auto-promote.js"), "utf8");
  const result = evaluatePromotion(validCandidate({
    prNumber: 1092,
    bootstrapReviewBound: true,
    changedFiles: ["apps/life-manager/lib/dev-auto-promote.js"],
    addedLines: policySource.split("\n").map((line) => ({
      path: "apps/life-manager/lib/dev-auto-promote.js",
      line,
    })),
  }));
  assert.equal(result.allowed, true);
  assert.deepEqual(result.blockedActions, []);
});


test("review-bound bootstrap test fixtures do not grant production capabilities", () => {
  const result = evaluatePromotion(validCandidate({
    prNumber: 1092,
    bootstrapReviewBound: true,
    changedFiles: ["apps/life-manager/lib/dev-auto-promote.test.js"],
    addedLines: [{
      path: "apps/life-manager/lib/dev-auto-promote.test.js",
      line: "sendUnsolicitedEmail(target); wallet.sendTransaction(value);",
    }],
  }));
  assert.equal(result.allowed, true);
  assert.deepEqual(result.blockedActions, []);
});


test("deployment completes only for the exact healthy merge and otherwise rolls back once", () => {
  assert.deepEqual(decideDeploymentOutcome({
    exactCommit: true,
    deploymentStatus: "SUCCESS",
    healthOk: true,
    previousDeploymentHealthy: true,
  }), { action: "complete" });
  assert.deepEqual(decideDeploymentOutcome({
    exactCommit: true,
    deploymentStatus: "FAILED",
    healthOk: false,
    previousDeploymentHealthy: true,
  }), { action: "rollback" });
  assert.deepEqual(decideDeploymentOutcome({
    exactCommit: true,
    deploymentStatus: "SUCCESS",
    healthOk: false,
    previousDeploymentHealthy: true,
  }), { action: "rollback" });
  assert.deepEqual(decideDeploymentOutcome({
    exactCommit: false,
    deploymentStatus: "SUCCESS",
    healthOk: true,
    previousDeploymentHealthy: true,
  }), { action: "wait" });
  assert.deepEqual(decideDeploymentOutcome({
    exactCommit: true,
    deploymentStatus: "FAILED",
    healthOk: false,
    previousDeploymentHealthy: false,
  }), { action: "stop" });
});


test("runtime orders full gates and fresh adversary before merge, then exact deploy health before rollback", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../scripts/dev-auto-promote.js"),
    "utf8",
  );
  const fullGates = source.slice(
    source.indexOf("function runFullGates"),
    source.indexOf("function runFreshAdversary"),
  );
  const testGate = fullGates.indexOf("npm\", [\"test\"]");
  const evalGate = fullGates.indexOf("npm\", [\"run\", \"eval\"]");
  assert.equal(testGate > 0, true);
  assert.equal(evalGate > testGate, true);
  assert.match(fullGates, /eval:panel-privacy/);

  const main = source.slice(source.indexOf("async function main"));
  const fullGateCall = main.indexOf("runFullGates()");
  const adversary = main.indexOf("runFreshAdversary");
  const merge = main.indexOf("mergePullRequest");
  const exactDeploy = main.indexOf("waitForExactDeployment", merge);
  const health = main.indexOf("readHealth", exactDeploy);
  const rollback = main.indexOf("deploymentRollback", health);
  const receipt = main.indexOf("\"pr\", \"comment\"", health);
  assert.equal(adversary < fullGateCall, true);
  assert.equal(merge > adversary, true);
  assert.equal(exactDeploy > merge, true);
  assert.equal(health > exactDeploy, true);
  assert.equal(rollback > health, true);
  assert.equal(receipt > health, true);
  assert.match(source, /--evaluate-only/);
  assert.doesNotMatch(source, /(?:GH_TOKEN|RAILWAY_TOKEN|DATABASE_URL)\s*=/);
});
