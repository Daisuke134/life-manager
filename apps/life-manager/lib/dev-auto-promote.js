"use strict";


const ROUTINE_ALLOWED_PATHS = Object.freeze([
  /^apps\/life-manager\/(?:lib|test)\/(?!dev-auto-promote)[A-Za-z0-9_./-]+\.(?:js|cjs|mjs|json)$/,
]);

const BOOTSTRAP_PATHS = Object.freeze(new Set([
  "apps/life-manager/lib/dev-auto-promote.js",
  "apps/life-manager/lib/dev-auto-promote.test.js",
  "apps/life-manager/lib/dev-auto-promote-runtime.test.js",
  "apps/life-manager/scripts/dev-auto-promote.js",
  "apps/life-manager/scripts/dev-auto-promote-review.schema.json",
  "apps/life-manager/package.json",
  "docs/evidence/10e-auto-merge-deploy.md",
  "docs/superpowers/specs/2026-07-19-anicca-one-repo-consolidation-spec.md",
  "execution-notes.md",
]));

const CAPABILITY_PATHS = Object.freeze({
  outreach_send: /(?:late-notice|call-bridge|transport\/mail|marketing|distribution|postiz|telegram-send)/i,
  provider_account_mutation: /(?:panel-api|panel-control-center|oauth|connected-account)/i,
  secret_change: /(?:^|\/)(?:scripts|config|\.github)(?:\/|$)|(?:secret|credential)/i,
  wallet_transfer: /(?:wallet|finance|financial|money-send|transfer)/i,
});

const ALLOWED_PATHS = Object.freeze([
  ...ROUTINE_ALLOWED_PATHS,
  /^docs\/evidence\/10e-[A-Za-z0-9_.-]+\.md$/,
  /^docs\/superpowers\/specs\/2026-07-19-anicca-one-repo-consolidation-spec\.md$/,
  /^execution-notes\.md$/,
]);

const BLOCKED_ACTION_PATTERNS = Object.freeze({
  outreach_send: /\b(?:sendUnsolicitedEmail|sendMail|makeCall|postToSocial|telegramSend)\b/i,
  provider_account_mutation: /connected_accounts[^\n]*(?:PATCH|DELETE)|\bdisconnectProvider\b/i,
  secret_change: /\brailway\s+variable\s+set\b|\b(?:api|secret|token)[_-]?key\s*=/i,
  wallet_transfer: /\b(?:sendTransaction|eth_sendRawTransaction|wallet\.transfer)\b/i,
  privileged_execution: /\b(?:process\.mainModule|module\.constructor|child_process|execFile(?:Sync)?|spawn(?:Sync)?|process\.binding|node:vm)\b|\beval\s*\(|\bnew\s+Function\b|require\s*\(\s*[^"'`]/i,
  secret_access: /\b(?:process|Deno|Bun)\.env\b/i,
  filesystem_access: /\bnode:fs\b|require\s*\(\s*["']fs["']\s*\)|\b(?:readFile|readdir|createReadStream)\b/i,
  network_execution: /\bfetch\s*\(|\b(?:node:https|node:http)\b|\b(?:https|http)\.request\s*\(|\bWebSocket\s*\(/i,
});


function uniqueSorted(values) {
  return [...new Set(values)].sort();
}


function evaluatePromotion(candidate = {}) {
  const reasons = [];
  const closing = Array.isArray(candidate.closingIssueNumbers)
    ? candidate.closingIssueNumbers.map(Number)
    : [];
  if (closing.length !== 1 || closing[0] !== Number(candidate.issueNumber)) reasons.push("issue_count");
  if (candidate.openPrsForIssue !== 1) reasons.push("pr_count");
  if (candidate.issueIsPrivacySafeError !== true) reasons.push("issue_contract");
  if (candidate.baseRefName !== "main") reasons.push("base_branch");
  if (!/^[a-f0-9]{40}$/.test(String(candidate.headOid || ""))
      || candidate.localHeadOid !== candidate.headOid) reasons.push("head_drift");
  if (candidate.mergeable !== "MERGEABLE") reasons.push("mergeable");

  const bootstrap = Number(candidate.prNumber) === 1092 && Number(candidate.issueNumber) === 1088;
  const paths = Array.isArray(candidate.changedFiles) ? candidate.changedFiles : [];
  const pathAllowed = (file) => ROUTINE_ALLOWED_PATHS.some((pattern) => pattern.test(file))
    || (bootstrap && BOOTSTRAP_PATHS.has(file));
  if (!paths.length || paths.some((file) => !pathAllowed(file))) {
    reasons.push("path_allowlist");
  }
  if (bootstrap && candidate.bootstrapReviewBound !== true) reasons.push("bootstrap_review");
  const blockedActions = [];
  if (paths.some((file) => /(^|\/)migrations?\//i.test(file))) blockedActions.push("migration");
  const routineProductionPaths = paths.filter((file) =>
    !BOOTSTRAP_PATHS.has(file)
    && !/\.test\.[cm]?js$/.test(file)
  );
  for (const [name, pattern] of Object.entries(CAPABILITY_PATHS)) {
    if (routineProductionPaths.some((file) => pattern.test(file))) blockedActions.push(name);
  }
  const entries = (Array.isArray(candidate.addedLines) ? candidate.addedLines : [])
    .map((entry) => typeof entry === "string" ? { path: "", line: entry } : entry)
    .filter((entry) => !(
      entry
      && entry.path === "apps/life-manager/lib/dev-auto-promote.js"
      && /^\s*(?:outreach_send|provider_account_mutation|secret_change|wallet_transfer|privileged_execution|secret_access|filesystem_access|network_execution):\s*\//.test(entry.line)
    ));
  const added = entries
    .filter((entry) => !(bootstrap && entry && BOOTSTRAP_PATHS.has(entry.path)))
    .map((entry) => String(entry && entry.line || ""))
    .join("\n");
  for (const [name, pattern] of Object.entries(BLOCKED_ACTION_PATTERNS)) {
    if (pattern.test(added)) blockedActions.push(name);
  }
  if (bootstrap) {
    const bootstrapText = entries
      .filter((entry) =>
        entry
        && BOOTSTRAP_PATHS.has(entry.path)
        && !/\.test\.[cm]?js$/.test(entry.path)
      )
      .map((entry) => String(entry.line || ""))
      .join("\n");
    const allowedBootstrapCapabilities = new Set([
      "filesystem_access",
      "network_execution",
      "privileged_execution",
      "secret_access",
    ]);
    for (const [name, pattern] of Object.entries(BLOCKED_ACTION_PATTERNS)) {
      if (pattern.test(bootstrapText) && !allowedBootstrapCapabilities.has(name)) {
        reasons.push("bootstrap_capability");
      }
    }
  }
  if (blockedActions.length) reasons.push("blocked_actions");

  const gates = candidate.gates || {};
  for (const gate of ["tests", "evals", "privacy", "adversary", "cleanWorktree"]) {
    if (gates[gate] !== true) reasons.push(gate);
  }
  return Object.freeze({
    allowed: reasons.length === 0,
    reasons: Object.freeze(uniqueSorted(reasons)),
    blockedActions: Object.freeze(uniqueSorted(blockedActions)),
  });
}


function decideDeploymentOutcome({
  exactCommit,
  deploymentStatus,
  healthOk,
  previousDeploymentHealthy,
} = {}) {
  if (!exactCommit) return { action: "wait" };
  if (deploymentStatus === "SUCCESS" && healthOk === true) return { action: "complete" };
  if (previousDeploymentHealthy !== true) return { action: "stop" };
  if (deploymentStatus === "FAILED" || (deploymentStatus === "SUCCESS" && healthOk === false)) {
    return { action: "rollback" };
  }
  return { action: "wait" };
}


module.exports = {
  ALLOWED_PATHS,
  ROUTINE_ALLOWED_PATHS,
  BOOTSTRAP_PATHS,
  CAPABILITY_PATHS,
  BLOCKED_ACTION_PATTERNS,
  evaluatePromotion,
  decideDeploymentOutcome,
};
