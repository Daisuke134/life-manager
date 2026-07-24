"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  reviewPasses,
  safeGateEnvironment,
  mergePullRequest,
  waitForExactDeployment,
} = require("../scripts/dev-auto-promote.js");


test("fresh adversary PASS is bound to the exact reviewed head", () => {
  const head = "a".repeat(40);
  const tree = "c".repeat(64);
  assert.equal(reviewPasses({
    status: "pass",
    reviewed_head: head,
    reviewed_tree_sha256: tree,
    blocking_findings: [],
    evidence: ["reviewed exact diff"],
  }, head, tree), true);
  assert.equal(reviewPasses({
    status: "pass",
    reviewed_head: "b".repeat(40),
    reviewed_tree_sha256: tree,
    blocking_findings: [],
    evidence: ["reviewed stale diff"],
  }, head, tree), false);
  assert.equal(reviewPasses({
    status: "pass",
    reviewed_head: head,
    reviewed_tree_sha256: "d".repeat(64),
    blocking_findings: [],
    evidence: ["reviewed different tree"],
  }, head, tree), false);
});


test("candidate gates receive a minimal environment with no inherited credentials", () => {
  const environment = safeGateEnvironment({
    PATH: "/usr/bin:/bin",
    TMPDIR: "/tmp",
    GH_TOKEN: "fixture-github-token",
    RAILWAY_TOKEN: "fixture-railway-token",
    COMPOSIO_API_KEY: "fixture-provider-key",
  }, "/tmp/lm-gate-home");
  assert.deepEqual(environment, {
    PATH: "/usr/bin:/bin",
    TMPDIR: "/tmp",
    HOME: "/tmp/lm-gate-home",
    CI: "1",
    NODE_ENV: "test",
  });
});


test("merge command is atomically pinned to the reviewed PR head", () => {
  const calls = [];
  mergePullRequest(1092, "a".repeat(40), {
    runImpl: (file, args) => calls.push({ file, args }),
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].file, "gh");
  assert.deepEqual(calls[0].args.slice(0, 5), [
    "pr", "merge", "1092", "-R", "Daisuke134/life-manager",
  ]);
  assert.equal(calls[0].args.includes("--match-head-commit"), true);
  assert.equal(calls[0].args.includes("a".repeat(40)), true);
});


test("rollback readback ignores the old deployment and requires a new post-rollback exact commit", async () => {
  const timestamp = (hour, second) => ["2026", "07", `24T${hour}:00:${second}.000Z`].join("-");
  const old = {
    id: "old-deployment",
    status: "SUCCESS",
    createdAt: timestamp("08", "00"),
    meta: { commitHash: "a".repeat(40) },
  };
  const restored = {
    id: "restored-deployment",
    status: "SUCCESS",
    createdAt: timestamp("09", "01"),
    meta: { commitHash: "a".repeat(40) },
  };
  const result = await waitForExactDeployment("a".repeat(40), {
    createdAfterMs: Date.parse(timestamp("09", "00")),
    excludeDeploymentIds: ["old-deployment"],
    timeoutMs: 50,
    listImpl: () => [{ id: old.id }, { id: restored.id }],
    detailImpl: (id) => id === old.id ? old : restored,
    sleepImpl: async () => {},
  });
  assert.deepEqual(result, restored);
});
