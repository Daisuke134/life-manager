#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const os = require("node:os");
const crypto = require("node:crypto");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const {
  evaluatePromotion,
  decideDeploymentOutcome,
} = require("../lib/dev-auto-promote.js");


const REPO = "Daisuke134/life-manager";
const RAILWAY_PROJECT = "f9c524cb-ba4a-43bb-9639-ff736afd9ec1";
const RAILWAY_SERVICE = "life-call";
const RAILWAY_ENVIRONMENT = "production";
const HEALTH_URL = "https://life-call-production.up.railway.app/health";
const APP_DIR = path.resolve(__dirname, "..");
const REPO_DIR = path.resolve(APP_DIR, "../..");
const RUN_AGENT = process.env.LM_DEV_RUN_AGENT
  || path.join(process.env.HOME, "anicca/skills/earn/marketing-engine/run_agent.sh");
const REVIEW_SCHEMA = path.join(__dirname, "dev-auto-promote-review.schema.json");
const TERMINAL_FAILURES = new Set(["FAILED", "CRASHED", "REMOVED"]);


function run(file, args, options = {}) {
  return String(execFileSync(file, args, {
    cwd: options.cwd || REPO_DIR,
    encoding: "utf8",
    input: options.input,
    stdio: options.inherit ? "inherit" : ["pipe", "pipe", "pipe"],
    timeout: options.timeout || 20 * 60 * 1000,
    maxBuffer: 20 * 1024 * 1024,
    env: options.env || process.env,
  }) || "").trim();
}


function parseArgs(argv) {
  const result = { evaluateOnly: false };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--pr") result.pr = Number(argv[++index]);
    else if (argv[index] === "--issue") result.issue = Number(argv[++index]);
    else if (argv[index] === "--evaluate-only") result.evaluateOnly = true;
    else throw new Error("auto_promote_argument_invalid");
  }
  if (!Number.isInteger(result.pr) || result.pr < 1
      || !Number.isInteger(result.issue) || result.issue < 1) {
    throw new Error("auto_promote_argument_invalid");
  }
  return result;
}


function ghJson(args) {
  return JSON.parse(run("gh", [...args, "-R", REPO]) || "null");
}


function currentTreeDigest() {
  const diff = execFileSync("git", ["diff", "--binary", "origin/main...HEAD"], {
    cwd: REPO_DIR,
    encoding: null,
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 30000,
    maxBuffer: 20 * 1024 * 1024,
  });
  return crypto.createHash("sha256").update(diff).digest("hex");
}


function candidateAddedLines(diff) {
  const lines = [];
  let current = "";
  for (const line of String(diff || "").split("\n")) {
    const match = line.match(/^diff --git a\/(.+) b\/(.+)$/);
    if (match) {
      current = match[2];
      continue;
    }
    const candidateCode = /^apps\/life-manager\/(?:lib|test|scripts)\//.test(current);
    if (candidateCode && line.startsWith("+") && !line.startsWith("+++")) {
      lines.push({ path: current, line: line.slice(1) });
    }
  }
  return lines;
}


function loadCandidate(prNumber, issueNumber, gates) {
  const pr = ghJson([
    "pr", "view", String(prNumber),
    "--json", "number,state,baseRefName,headRefOid,mergeable,files,closingIssuesReferences,url",
  ]);
  const issue = ghJson([
    "issue", "view", String(issueNumber),
    "--json", "number,state,title,body,labels,url",
  ]);
  const openPrs = ghJson([
    "pr", "list", "--state", "open", "--limit", "100",
    "--json", "number,body",
  ]);
  const diff = run("gh", ["pr", "diff", String(prNumber), "-R", REPO, "--patch"]);
  const localHeadOid = run("git", ["rev-parse", "HEAD"]);
  const treeDigest = currentTreeDigest();
  const exactFix = new RegExp(`(^|\\n)Fixes #${issueNumber}\\.(\\n|$)`);
  const matchingPrs = openPrs.filter((value) => exactFix.test(String(value.body || "")));
  return {
    prNumber: Number(pr.number),
    issueNumber,
    closingIssueNumbers: (pr.closingIssuesReferences || []).map((value) => Number(value.number)),
    openPrsForIssue: matchingPrs.length,
    issueIsPrivacySafeError:
      issue.state === "OPEN"
      && /^\[error\]\s/.test(String(issue.title || ""))
      && /<!-- lm-intake:err:sha256:[a-f0-9]{32} -->/.test(String(issue.body || ""))
      && (issue.labels || []).some((label) => label.name === "lm:type:self-heal"),
    baseRefName: pr.baseRefName,
    headOid: pr.headRefOid,
    localHeadOid,
    mergeable: pr.mergeable,
    changedFiles: (pr.files || []).map((value) => value.path),
    addedLines: candidateAddedLines(diff),
    treeDigest,
    bootstrapReviewBound: gates.bootstrapReviewBound === true,
    gates,
    pr,
    issue,
  };
}


function safeGateEnvironment(baseEnvironment, temporaryHome) {
  return {
    PATH: String(baseEnvironment.PATH || "/usr/bin:/bin"),
    TMPDIR: String(baseEnvironment.TMPDIR || os.tmpdir()),
    HOME: temporaryHome,
    CI: "1",
    NODE_ENV: "test",
  };
}


function runFullGates() {
  const temporaryHome = fs.mkdtempSync(path.join(os.tmpdir(), "lm-promote-gate-"));
  fs.chmodSync(temporaryHome, 0o700);
  const env = safeGateEnvironment(process.env, temporaryHome);
  try {
    run("npm", ["test"], { cwd: APP_DIR, inherit: true, env });
    run("npm", ["run", "eval"], { cwd: APP_DIR, inherit: true, env });
    run("npm", ["run", "eval:panel-privacy"], { cwd: APP_DIR, inherit: true, env });
  } finally {
    fs.rmSync(temporaryHome, { recursive: true, force: true });
  }
}


function runFreshAdversary(prNumber, issueNumber, headOid, treeDigest, changedFiles) {
  const evidenceDir = path.join(
    process.env.HOME,
    ".openclaw/state/agent-runner-evidence",
    `life-manager-promote-${prNumber}`,
    `${Math.floor(Date.now() / 1000)}-${process.pid}`,
  );
  fs.mkdirSync(evidenceDir, { recursive: true, mode: 0o700 });
  const prompt = [
    "You are a fresh-context, artifact-only adversarial release reviewer.",
    `Review Life Manager PR #${prNumber} for privacy-safe error issue #${issueNumber}.`,
    `The exact candidate head is ${headOid}.`,
    `The exact origin/main...HEAD binary diff SHA-256 is ${treeDigest}.`,
    `Changed paths: ${changedFiles.join(", ")}`,
    "Read origin/main...HEAD and relevant tests/spec only. Do not edit, commit, push, merge, deploy,",
    "contact providers, or expose secrets/PII. Find concrete correctness, privacy, path-scope,",
    "test weakness, rollback, or production-safety blockers. PASS only when blocking_findings is empty.",
    `Return reviewed_head exactly as ${headOid}.`,
    `Return reviewed_tree_sha256 exactly as ${treeDigest} after independently checking the diff.`,
  ].join("\n");
  const output = run(RUN_AGENT, [
    "--task-class", "high-value-agent",
    "--evidence-dir", evidenceDir,
    "--task-label", `life-manager-promote-${prNumber}`,
    "--loop", "life-manager-dev-promote",
    "--schema", REVIEW_SCHEMA,
    "--workdir", REPO_DIR,
    "--print-result",
  ], { input: `${prompt}\n` });
  const result = JSON.parse(output);
  return {
    passed: reviewPasses(result, headOid, treeDigest),
    evidenceDir,
    result,
  };
}


function reviewPasses(result, expectedHead, expectedTreeDigest) {
  return Boolean(
    result
    && result.status === "pass"
    && result.reviewed_head === expectedHead
    && result.reviewed_tree_sha256 === expectedTreeDigest
    && Array.isArray(result.blocking_findings)
    && result.blocking_findings.length === 0
    && Array.isArray(result.evidence)
    && result.evidence.length > 0
  );
}


function deploymentDetail(id) {
  const query = "query($id:String!){deployment(id:$id){id status createdAt canRollback meta}}";
  const response = JSON.parse(run("railway", [
    "api", query,
    "--variables", JSON.stringify({ id }),
  ]));
  return response.data.deployment;
}


function listDeployments() {
  return JSON.parse(run("railway", [
    "deployment", "list",
    "-p", RAILWAY_PROJECT,
    "-s", RAILWAY_SERVICE,
    "-e", RAILWAY_ENVIRONMENT,
    "--limit", "20",
    "--json",
  ]));
}


function currentSuccessfulDeployment() {
  for (const item of listDeployments()) {
    const detail = deploymentDetail(item.id);
    if (detail.status === "SUCCESS" && detail.meta && detail.meta.commitHash) return detail;
  }
  throw new Error("auto_promote_previous_deployment_missing");
}


async function readHealth() {
  try {
    const response = await fetch(HEALTH_URL, {
      headers: { "user-agent": "life-manager-auto-promote/1" },
      signal: AbortSignal.timeout(15000),
    });
    const body = await response.json();
    return response.ok && body && body.ok === true && body.service === "life-call";
  } catch {
    return false;
  }
}


async function waitForExactDeployment(commitHash, options = {}) {
  const timeoutMs = options.timeoutMs || 15 * 60 * 1000;
  const createdAfterMs = Number(options.createdAfterMs || 0);
  const excluded = new Set(options.excludeDeploymentIds || []);
  const listImpl = options.listImpl || listDeployments;
  const detailImpl = options.detailImpl || deploymentDetail;
  const sleepImpl = options.sleepImpl
    || ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const item of listImpl()) {
      const detail = detailImpl(item.id);
      const createdMs = Date.parse(detail.createdAt);
      if (
        !excluded.has(detail.id)
        && Number.isFinite(createdMs)
        && createdMs > createdAfterMs
        && detail.meta
        && detail.meta.commitHash === commitHash
      ) {
        if (detail.status === "SUCCESS" || TERMINAL_FAILURES.has(detail.status)) return detail;
      }
    }
    await sleepImpl(10000);
  }
  throw new Error("auto_promote_deployment_timeout");
}


function mergePullRequest(prNumber, headOid, options = {}) {
  const runImpl = options.runImpl || run;
  runImpl("gh", [
    "pr", "merge", String(prNumber),
    "-R", REPO,
    "--squash", "--admin", "--delete-branch",
    "--match-head-commit", headOid,
  ]);
}


function deploymentRollback(id) {
  const mutation = "mutation($id:String!){deploymentRollback(id:$id)}";
  const response = JSON.parse(run("railway", [
    "api", mutation,
    "--variables", JSON.stringify({ id }),
  ]));
  if (!response.data || response.data.deploymentRollback !== true) {
    throw new Error("auto_promote_rollback_failed");
  }
}


async function main() {
  const options = parseArgs(process.argv.slice(2));
  const optimisticGates = {
    tests: true,
    evals: true,
    privacy: true,
    adversary: true,
    cleanWorktree: true,
    bootstrapReviewBound: true,
  };
  let candidate = loadCandidate(options.pr, options.issue, optimisticGates);
  let guard = evaluatePromotion(candidate);
  if (!guard.allowed || options.evaluateOnly) {
    process.stdout.write(`${JSON.stringify({
      status: guard.allowed ? "eligible" : "refused",
      pr: options.pr,
      issue: options.issue,
      guard,
    })}\n`);
    if (!guard.allowed) process.exitCode = 3;
    return;
  }

  const review = runFreshAdversary(
    options.pr,
    options.issue,
    candidate.headOid,
    candidate.treeDigest,
    candidate.changedFiles,
  );
  if (!review.passed) throw new Error("auto_promote_guard_refused:adversary");
  runFullGates();
  const cleanWorktree = run("git", ["status", "--porcelain"]) === "";
  const reviewedHead = candidate.headOid;
  const reviewedTreeDigest = candidate.treeDigest;
  candidate = loadCandidate(options.pr, options.issue, {
    tests: true,
    evals: true,
    privacy: true,
    adversary: review.passed,
    cleanWorktree,
    bootstrapReviewBound: review.passed,
  });
  if (candidate.headOid !== reviewedHead || candidate.treeDigest !== reviewedTreeDigest) {
    throw new Error("auto_promote_review_binding_changed");
  }
  guard = evaluatePromotion(candidate);
  if (!guard.allowed) throw new Error(`auto_promote_guard_refused:${guard.reasons.join(",")}`);

  const previous = currentSuccessfulDeployment();
  const previousDeploymentHealthy = await readHealth();
  if (!previousDeploymentHealthy) throw new Error("auto_promote_previous_health_red");

  mergePullRequest(options.pr, candidate.headOid);
  const merged = ghJson([
    "pr", "view", String(options.pr),
    "--json", "state,mergeCommit,url",
  ]);
  if (merged.state !== "MERGED" || !merged.mergeCommit || !merged.mergeCommit.oid) {
    throw new Error("auto_promote_merge_readback_failed");
  }

  const deployment = await waitForExactDeployment(merged.mergeCommit.oid);
  const healthOk = deployment.status === "SUCCESS" && await readHealth();
  const outcome = decideDeploymentOutcome({
    exactCommit: deployment.meta && deployment.meta.commitHash === merged.mergeCommit.oid,
    deploymentStatus: deployment.status,
    healthOk,
    previousDeploymentHealthy,
  });
  if (outcome.action === "rollback") {
    if (!previous.canRollback) throw new Error("auto_promote_rollback_unavailable");
    const rollbackStartedMs = Date.now();
    deploymentRollback(previous.id);
    const restored = await waitForExactDeployment(previous.meta.commitHash, {
      createdAfterMs: rollbackStartedMs,
      excludeDeploymentIds: [previous.id, deployment.id],
    });
    if (restored.status !== "SUCCESS" || !(await readHealth())) {
      throw new Error("auto_promote_rollback_health_red");
    }
    throw new Error("auto_promote_deployment_rolled_back");
  }
  if (outcome.action !== "complete") throw new Error(`auto_promote_deployment_${outcome.action}`);

  const issue = ghJson([
    "issue", "view", String(options.issue),
    "--json", "state,url",
  ]);
  if (issue.state !== "CLOSED") throw new Error("auto_promote_issue_not_closed");
  run("gh", [
    "pr", "comment", String(options.pr),
    "-R", REPO,
    "--body", [
      "## Automated production postflight",
      "",
      `- Error issue: #${options.issue} (closed)`,
      `- Merge commit: \`${merged.mergeCommit.oid}\``,
      `- Railway deployment: \`${deployment.id}\``,
      `- Deployment commit: \`${deployment.meta.commitHash}\``,
      "- Production health: `ok`",
      "- Fresh adversary: `PASS` (blocking findings: `0`)",
      "- Guard: path allowlist PASS, blocked actions `0`, one issue / one PR PASS",
    ].join("\n"),
  ]);
  process.stdout.write(`${JSON.stringify({
    status: "deployed",
    issue: issue.url,
    pr: merged.url,
    mergeCommit: merged.mergeCommit.oid,
    deploymentId: deployment.id,
    deploymentCommit: deployment.meta.commitHash,
    health: "ok",
    adversaryEvidenceDir: review.evidenceDir,
  })}\n`);
}


if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`dev-auto-promote failed: ${error.message}\n`);
    process.exitCode = 1;
  });
}


module.exports = {
  reviewPasses,
  safeGateEnvironment,
  mergePullRequest,
  waitForExactDeployment,
};
