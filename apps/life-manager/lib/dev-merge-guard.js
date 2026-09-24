"use strict";

// Unattended merge guard for the DEV self-build loop (spec §10 row 10e, §9.3).
//
// The loop already produces fix PRs (lib/daily-dev-loop.js -> scripts/life-manager-dev-d0.sh,
// fed by lib/error-intake.js and lib/feedback-to-issue.js). This module is the gate that stands
// between such a PR and production. It is deliberately paranoid: every stage must sign off, in
// order, and the FIRST failure is a hard stop with an honest verdict. Nothing merges on a maybe.
//
// WHAT THIS GUARD DOES NOT DO — read this before trusting it.
//
// The `tests` stage runs `npm test` and `npm run eval` on the PR's own code, on this machine, with
// this machine's environment and credentials. That is arbitrary code execution by construction: a
// test file IS code, and running the suite is the only way to know the suite is green. Three things
// bound the blast radius, and none of them is a sandbox:
//
//   1. review-first — the fresh adversary and the blocked-actions tripwire run BEFORE the suite, so
//      code no reviewer has read never executes. (Before this ordering existed, an attacker's code
//      ran first and the review was a post-mortem.)
//   2. the path allowlist — a PR may only touch lib/, test/ and scripts/ under apps/life-manager,
//      and package.json only additively, so it cannot rewrite the workflow, the spec or a migration.
//   3. self-deny — the guard's own files, and whatever file `--review-cmd` resolves to, are refused
//      at eligibility, so no PR can weaken the thing judging it and no two-PR takeover chain
//      (PR 1 edits the reviewer, PR 2 is waved through by it) can start.
//
// `npm ci --ignore-scripts` removes install-time hooks from the picture, but the suite itself still
// runs PR code. REAL isolation — a container or VM with no network, no credentials and no write
// access to this repo — is NOT implemented here and is future work. Until it exists, this guard is
// honest about being a review gate with a hardened blast radius, not a sandbox.
//
// This file contains no schedule wiring on purpose — re-enabling launchd is 10f's job.

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");


const REPO = "Daisuke134/life-manager";
const RAILWAY_PROJECT = "f9c524cb-ba4a-43bb-9639-ff736afd9ec1";
const RAILWAY_SERVICE = "life-call";
const RAILWAY_ENVIRONMENT = "production";
const HEALTH_URL = "https://life-call-production.up.railway.app/health";
const APP_DIR = path.resolve(__dirname, "..");
const REPO_DIR = path.resolve(APP_DIR, "../..");

// Verified against railway CLI 5.28.0 and the live public GraphQL schema on 2026-07-27:
//   * `railway redeploy` accepts only -s/-e/-p/-y/--json/--from-source. There is NO way to point
//     it at an older deployment id, so "redeploy the previous deployment" is not a CLI feature.
//   * `railway deployment` exposes only list/up/redeploy — again no rollback subcommand.
//   * `Mutation.deploymentRollback(id: String!): Boolean!` ("Rolls back to a deployment.") and
//     `Deployment.canRollback: Boolean!` DO exist, reachable through `railway api`.
// So: rollback runs through `railway api`, gated on canRollback, and falls back to an automatic
// revert PR + alert when Railway says the old deployment is no longer rollback-able.
const ROLLBACK_MUTATION = "mutation($id:String!){deploymentRollback(id:$id)}";
const DEPLOYMENT_DETAIL_QUERY =
  "query($id:String!){deployment(id:$id){id status createdAt canRollback meta}}";

// Order matters, and this is the order: nothing that has not been read by the fresh adversary and
// cleared by the blocked-actions tripwire is ever executed. `tests` runs PR code (see header), so
// it sits AFTER review, not before it.
const GUARD_STAGES = Object.freeze([
  "eligibility",
  "review",
  "blocked_actions",
  "tests",
  "merge",
  "deploy_health",
]);

const DEFAULT_AUTHORS = Object.freeze(["Daisuke134"]);
const RECOVERY_PR_MARKER = "[lm-recovery-self-heal]";

// The loop names its branches `feature/lm-dev-<issue>` (real: PR #1094 -> feature/lm-dev-1090,
// PR #1095 -> feature/lm-dev-1089). `fix/...` is accepted for hand-shaped error fixes.
const BRANCH_PATTERNS = Object.freeze([
  /^feature\/lm-dev-[1-9][0-9]*$/,
  /^fix\/[A-Za-z0-9][A-Za-z0-9._/-]*$/,
]);

const ALLOWED_DIRECTORIES = Object.freeze([
  ["apps/life-manager/lib/", "allow:lib"],
  ["apps/life-manager/test/", "allow:test"],
  ["apps/life-manager/scripts/", "allow:scripts"],
  ["runtime/loop/", "allow:runtime-loop"],
]);

// The guard may not be modified by the machinery it guards. Without this, the takeover is two
// ordinary PRs long: PR 1 (paths all inside the allowlist, tests green, reviewer bribed by nothing
// more than a plausible diff) weakens the allowlist or the tripwire; PR 2 then walks through the
// hole. Both files and both directories are refused at eligibility, which is stage one, so such a
// PR never reaches review, never reaches the suite, and never runs a line of its own code.
// Consequence, stated plainly: changes to the guard require a human-merged PR. That is the price.
const GUARD_SELF_PATHS = Object.freeze([
  /^apps\/life-manager\/lib\/dev-merge-guard/,
  /^apps\/life-manager\/scripts\/dev-merge-guard/,
  /^apps\/life-manager\/lib\/self-build-daily/,
  /^apps\/life-manager\/scripts\/self-build-daily/,
  /^apps\/life-manager\/lib\/recovery-self-build-bridge/,
  /^apps\/life-manager\/scripts\/recovery-self-build-bridge/,
  /^apps\/life-manager\/scripts\/life-manager-dev-d0\.sh$/,
  /^apps\/life-manager\/lib\/product-onboarding/,
  /^apps\/life-manager\/scripts\/local-foundation-gate/,
  /^runtime\/loop\/lm_loop\.py$/,
  /^runtime\/loop\/lm_loop_run\.py$/,
  /^runtime\/loop\/runtime_event\.py$/,
  /^runtime\/loop\/recovery-/,
]);

const CONDITIONAL_MANIFEST = "apps/life-manager/package.json";

// package.json script keys the loop may touch: it must be able to register a new regression test.
const MUTABLE_SCRIPTS = Object.freeze(["test", "pretest"]);

// Named function shapes that must never enter production through an unattended merge.
// Grep-based on purpose: this is a last-resort tripwire, not a type system. It runs over ADDED
// diff lines only, so pre-existing calls elsewhere in the repo are not the guard's business.
const BLOCKED_ACTIONS = Object.freeze([
  Object.freeze({
    action: "outreach_send",
    // §9.5: the agent contacts third parties on Dais's behalf. A bad unattended merge that gains
    // an outreach call can mail or ring strangers before anyone reads the diff — irreversible
    // reputational damage, and the one class of side effect Dais cannot undo.
    rationale: "New third-party outreach (mail/call/post) must never ship without a human read.",
    pattern: /\b(?:outreach_send|sendOutreach|sendOutreachEmail|sendMail|sendEmail|makeCall|placeCall|dialOut|postToSocial|telegramSend)\s*\(/,
  }),
  Object.freeze({
    action: "payment",
    // Money leaving or entering a real card/account is irreversible and legally consequential;
    // the billing surface (lib/billing.js) changes only under review.
    rationale: "New charge/refund/payout calls move real money and are irreversible once sent.",
    pattern: /\b(?:paymentIntents|charges|payouts|subscriptions)\.(?:create|update|cancel|del)\s*\(|\b(?:chargeCard|capturePayment|createCharge|issueRefund)\s*\(/,
  }),
  Object.freeze({
    action: "wallet_transfer",
    // §9.8: the agent wallet is the FINANCIAL organ's identity. An on-chain transfer cannot be
    // rolled back by any deploy, so it can never be introduced by machinery that self-merges.
    rationale: "On-chain transfers cannot be reverted by a redeploy, so they never self-merge.",
    pattern: /\b(?:wallet\.transfer|sendTransaction|sendRawTransaction|eth_sendRawTransaction|signTransaction|transferFrom|sendUserOperation)\s*\(/,
  }),
  Object.freeze({
    action: "direct_main_promotion",
    rationale: "A candidate may push only its feature branch and must never merge or update main around the guard.",
    pattern: /(?:\bgit\s+push\b[^\n]*\bmain\b|["'`]git["'`][^\n]*["'`]push["'`][^\n]*["'`]origin["'`][^\n]*["'`]main["'`]|\bgh\s+pr\s+merge\b|["'`]gh["'`][^\n]*["'`]pr["'`][^\n]*["'`]merge["'`])/,
  }),
  Object.freeze({
    action: "direct_deploy",
    rationale: "A candidate may not deploy itself; only the guarded promotion stage owns deployment and rollback.",
    pattern: /(?:\brailway\s+(?:up|redeploy|deploy)\b|["'`]railway["'`][^\n]*["'`](?:up|redeploy|deploy)["'`])/,
  }),
]);

// A blocklist declaration can mention the very names it hunts for, so the guard's OWN declaration
// lines are exempt — but narrowly:
//   * the path must be exactly the guard's source (by realpath), not merely end with its name. A
//     file called `vendor/lib/dev-merge-guard.js` is not this guard, and a suffix test handed any
//     attacker a free exemption for the cost of a filename.
//   * the line must contain NOTHING but the declaration. `pattern: /x/, boot: await sendMail(u),`
//     starts like a declaration and ends like an exfiltration; the anchored form below refuses it.
// This is belt-and-braces now that GUARD_SELF_PATHS refuses such a diff at eligibility.
const GUARD_SOURCE_RELATIVE = (() => {
  try {
    return path.relative(fs.realpathSync(REPO_DIR), fs.realpathSync(__filename)).split(path.sep).join("/");
  } catch {
    return "apps/life-manager/lib/dev-merge-guard.js";
  }
})();
const GUARD_DECLARATION_LINE = /^\s*pattern:\s*\/.*\/[dgimsuvy]*,?\s*$/;


function stableStringify(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
}


function sha256(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}


function classifyChangedPath(file, options = {}) {
  const value = String(file || "");
  const basename = value.split("/").pop() || "";
  const protectedPaths = Array.isArray(options.protectedPaths) ? options.protectedPaths : [];
  // Self-deny first: it must not be possible to reach an allow rule by any spelling.
  if (GUARD_SELF_PATHS.some((pattern) => pattern.test(value))) {
    return { allowed: false, rule: "deny:guard-self" };
  }
  if (protectedPaths.includes(value)) return { allowed: false, rule: "deny:guard-self" };
  if (/^\.github\//.test(value)) return { allowed: false, rule: "deny:workflow" };
  if (/(^|\/)migrations?(\/|$)/i.test(value)) return { allowed: false, rule: "deny:migration" };
  if (/^\.env($|\.)/.test(basename)) return { allowed: false, rule: "deny:env" };
  if (/^docs\/superpowers\/specs\//.test(value)) return { allowed: false, rule: "deny:spec" };
  if (/^skills\//.test(value)) return { allowed: false, rule: "deny:skill" };
  if (value === CONDITIONAL_MANIFEST) {
    return { allowed: false, conditional: true, rule: "conditional:package-json" };
  }
  for (const [prefix, rule] of ALLOWED_DIRECTORIES) {
    if (value.startsWith(prefix)) return { allowed: true, rule };
  }
  return { allowed: false, rule: "deny:not-allowlisted" };
}


// `--review-cmd` is a shell string, and the file it actually runs is only knowable at runtime. So:
// resolve every token of it (relative to the repo, then along PATH) to a real file, keep the ones
// whose REALPATH lands inside the repo, and hand those to the eligibility gate as protected paths.
// Realpath rather than string matching, because a symlink is a rename with extra steps.
function resolveReviewCommandPaths(command, io = {}) {
  const repoDir = io.repoDir || REPO_DIR;
  const realpathSync = io.realpathSync || fs.realpathSync;
  const statSync = io.statSync || fs.statSync;
  const env = io.env || process.env;

  let repoRoot;
  try { repoRoot = realpathSync(repoDir); } catch { repoRoot = path.resolve(repoDir); }

  const tokens = String(command || "")
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => token.replace(/^["']|["']$/g, ""))
    .filter((token) => token && !token.startsWith("-"));

  const candidates = [];
  for (const token of tokens) {
    candidates.push(path.resolve(repoDir, token));
    if (!token.includes("/")) {
      for (const dir of String(env.PATH || "").split(path.delimiter).filter(Boolean)) {
        candidates.push(path.join(dir, token));
      }
    }
  }

  const found = new Set();
  for (const candidate of candidates) {
    let real;
    try {
      if (!statSync(candidate).isFile()) continue;
      real = realpathSync(candidate);
    } catch {
      continue;
    }
    if (!real.startsWith(`${repoRoot}${path.sep}`)) continue;
    found.add(path.relative(repoRoot, real).split(path.sep).join("/"));
  }
  return [...found];
}


// `git diff --name-status -M` answers `M<TAB>path`, `A<TAB>path`, `R097<TAB>old<TAB>new`. A rename
// is TWO paths and both are judged: moving an allowlisted file into skills/ is still a skills edit,
// and moving a workflow into lib/ is still a workflow edit.
function parseNameStatus(raw) {
  const files = [];
  for (const line of String(raw || "").split("\n")) {
    if (!line.trim()) continue;
    const [status, ...paths] = line.split("\t");
    if (!status || paths.length === 0) continue;
    for (const value of paths) {
      const file = value.trim();
      if (file && !files.includes(file)) files.push(file);
    }
  }
  return files;
}


function isAdditiveOnly(before = {}, after = {}) {
  for (const [name, version] of Object.entries(before)) {
    if (after[name] !== version) return false;
  }
  return true;
}


// A dependency change ships new third-party code straight into production, so it is refused
// outright. Adding a devDependency, or appending a test file to the `test`/`pretest` line, is the
// one manifest edit the loop legitimately needs to register a regression test.
function evaluatePackageJsonChange(before, after) {
  const reasons = [];
  const left = before && typeof before === "object" ? before : {};
  const right = after && typeof after === "object" ? after : {};

  if (stableStringify(left.dependencies ?? {}) !== stableStringify(right.dependencies ?? {})) {
    reasons.push("dependencies_changed");
  }
  if (!isAdditiveOnly(left.devDependencies ?? {}, right.devDependencies ?? {})) {
    reasons.push("devdependencies_not_additive");
  }

  const leftScripts = { ...(left.scripts ?? {}) };
  const rightScripts = { ...(right.scripts ?? {}) };
  for (const key of MUTABLE_SCRIPTS) {
    delete leftScripts[key];
    delete rightScripts[key];
  }
  if (stableStringify(leftScripts) !== stableStringify(rightScripts)) {
    reasons.push("scripts_changed_outside_test");
  }

  const ignored = new Set(["dependencies", "devDependencies", "scripts"]);
  const otherKeys = [...new Set([...Object.keys(left), ...Object.keys(right)])]
    .filter((key) => !ignored.has(key));
  for (const key of otherKeys) {
    if (stableStringify(left[key]) !== stableStringify(right[key])) {
      reasons.push("other_fields_changed");
      break;
    }
  }
  return { allowed: reasons.length === 0, reasons };
}

function isRetainedRegressionFixture(file) {
  const value = String(file || "");
  return /^runtime\/loop\/tests\/test_[^/]+\.py$/.test(value)
    || /^runtime\/loop\/__tests__\/[^/]+\.test\.mjs$/.test(value)
    || /^apps\/life-manager\/test\/[^/]+\.test\.js$/.test(value)
    || /^apps\/life-manager\/(?:lib|scripts)\/[^/]+\.test\.js$/.test(value);
}


function evaluateEligibility(pr, options = {}) {
  const authors = options.allowedAuthors || DEFAULT_AUTHORS;
  const reasons = [];
  const value = pr || {};

  if (value.state !== "OPEN") reasons.push("pr_not_open");
  if (value.baseRefName !== "main") reasons.push("base_branch");
  if (!BRANCH_PATTERNS.some((pattern) => pattern.test(String(value.headRefName || "")))) {
    reasons.push("branch_name");
  }
  if (!authors.includes(String(value.author?.login || ""))) reasons.push("author_not_allowlisted");
  if (!/^[a-f0-9]{40}$/.test(String(value.headRefOid || ""))) reasons.push("head_oid_missing");
  if (value.mergeable !== "MERGEABLE") reasons.push("not_mergeable");

  // TOCTOU. Whoever picked this PR read its head, judged its file list, and only then handed the
  // number over. Between those two moments the branch can be force-pushed, and the guard would
  // then review, test and merge a head nobody ever prechecked. `--expect-head` closes the window:
  // the caller says which commit it decided about, and a different one is refused outright rather
  // than silently accepted as "the same PR".
  if (options.expectHead && String(value.headRefOid || "") !== String(options.expectHead)) {
    reasons.push("head_moved");
  }

  // `gh pr view --json files` caps at 100 entries and reports a rename as its new path only. Both
  // are silent holes: file 101 is never classified, and `git mv skills/x lib/x` looks like a plain
  // lib/ addition. So the authoritative list is git's own name-status at the head commit, and gh's
  // list is kept only as a cross-check recorded in the evidence.
  const ghFiles = Array.isArray(value.files) ? value.files.map((entry) => entry.path) : [];
  const gitFiles = Array.isArray(options.changedFiles) ? options.changedFiles.map(String) : null;
  const files = gitFiles ?? ghFiles;
  if (files.length === 0) reasons.push("no_changed_files");
  if (String(value.body || "").includes(RECOVERY_PR_MARKER)) {
    if (!files.some(isRetainedRegressionFixture)) reasons.push("regression_fixture_missing");
    // runtime/loop repairs cannot inherit the app guard's Railway-only deploy check. Task 7
    // supplies an immutable release canary and exact owner health readback before this option is
    // enabled. Until then the issue/PR pipeline may prepare a candidate, but never merge it.
    if (options.recoveryPromotionEnabled !== true) reasons.push("recovery_promotion_not_enabled");
  }

  const crossCheck = {
    gh_count: ghFiles.length,
    git_count: gitFiles ? gitFiles.length : null,
    gh_only: gitFiles ? ghFiles.filter((file) => !gitFiles.includes(file)) : [],
    git_only: gitFiles ? gitFiles.filter((file) => !ghFiles.includes(file)) : [],
    authoritative: gitFiles ? "git" : "gh",
  };

  const deniedPaths = [];
  const conditionalPaths = [];
  for (const file of files) {
    const verdict = classifyChangedPath(file, { protectedPaths: options.protectedPaths });
    if (verdict.allowed) continue;
    if (verdict.conditional) conditionalPaths.push(file);
    else deniedPaths.push({ path: file, rule: verdict.rule });
  }
  if (deniedPaths.length > 0) reasons.push("path_allowlist");

  return {
    ok: reasons.length === 0,
    reasons,
    changedPaths: files,
    deniedPaths,
    conditionalPaths,
    crossCheck,
  };
}


function parseAddedLines(diff) {
  const added = [];
  let current = "";
  for (const line of String(diff || "").split("\n")) {
    const header = line.match(/^diff --git a\/(.+?) b\/(.+)$/);
    if (header) {
      current = header[2];
      continue;
    }
    const target = line.match(/^\+\+\+ b\/(.+)$/);
    if (target) {
      current = target[1];
      continue;
    }
    if (line.startsWith("+++") || line.startsWith("---")) continue;
    if (line.startsWith("+")) added.push({ path: current, line: line.slice(1) });
  }
  return added;
}


function detectBlockedActions(addedLines, options = {}) {
  const guardSource = options.guardSourcePath || GUARD_SOURCE_RELATIVE;
  const hits = [];
  for (const entry of Array.isArray(addedLines) ? addedLines : []) {
    const file = String(entry?.path || "");
    const line = String(entry?.line || "");
    if (file === guardSource && GUARD_DECLARATION_LINE.test(line)) continue;
    for (const blocked of BLOCKED_ACTIONS) {
      if (blocked.pattern.test(line)) {
        hits.push({ action: blocked.action, path: file, line, rationale: blocked.rationale });
      }
    }
  }
  return hits;
}


function chainSeed(runId) {
  return sha256(`dev-merge-guard:v1:${runId}`);
}


function signStageChain(runId, records) {
  let prev = chainSeed(runId);
  return records.map((record) => {
    const body = { ...record, prev };
    const signature = sha256(stableStringify(body));
    prev = signature;
    return { ...body, signature };
  });
}


function verifyStageChain(runId, records) {
  let prev = chainSeed(runId);
  for (const record of Array.isArray(records) ? records : []) {
    if (!record || record.prev !== prev) return false;
    const { signature, ...body } = record;
    if (sha256(stableStringify(body)) !== signature) return false;
    prev = signature;
  }
  return true;
}


function guardLedgerPath(env = process.env) {
  if (env.LM_DEV_GUARD_LEDGER) return env.LM_DEV_GUARD_LEDGER;
  const home = env.HOME || os.homedir();
  return path.join(home, ".life-manager/state/dev-guard-runs.jsonl");
}


// ---------------------------------------------------------------------------------------------
// The run ledger — 10f's Day-N evidence, and therefore worth lying about.
//
// Rows are chained: every row carries `record_hash` = sha256 of its own body, and `prev` = sha256
// of the PREVIOUS row's record_hash (a fixed genesis for the first row). Editing a row, deleting a
// row, or reordering rows all break the chain and are detected by verifyLedgerTail.
//
// Honest limit: the hash function is public and the file is writable by whoever runs the guard, so
// a determined local attacker can recompute the whole chain after editing it. This is
// tamper-EVIDENT against casual editing and truncation, NOT tamper-PROOF. The upgrade that would
// make it tamper-proof is an HMAC (or an ed25519 signature) whose key lives OFF the runner — e.g.
// `record_hash = HMAC-SHA256(key, body)` with the key held by the alerting service, so the runner
// can append but not forge history. Not implemented here; it needs a key store this atomic does
// not own.
// ---------------------------------------------------------------------------------------------
const LEDGER_GENESIS = sha256("dev-merge-guard:ledger:v1:genesis");


function ledgerRecordHash(row) {
  const { record_hash: _ignored, ...body } = row || {};
  return sha256(stableStringify(body));
}


function readLedgerRows(ledgerPath, limit = 0) {
  let raw;
  try { raw = fs.readFileSync(ledgerPath, "utf8"); } catch { return []; }
  const rows = [];
  for (const line of raw.split("\n")) {
    if (!line.trim()) continue;
    try { rows.push(JSON.parse(line)); } catch { rows.push({ __unparseable: line.slice(0, 200) }); }
  }
  return limit > 0 ? rows.slice(-limit) : rows;
}


// Verifies both chains at once: the row-to-row chain, and each row's internal stage chain. Rows
// written before the chain existed carry no record_hash and are reported as `legacy`, not as fraud.
function verifyLedgerTail(ledgerPath, options = {}) {
  const limit = options.limit ?? 0;
  const rows = readLedgerRows(ledgerPath, limit);
  const problems = [];
  let expectedPrev = limit > 0 && rows.length === limit ? null : LEDGER_GENESIS;

  for (const [index, row] of rows.entries()) {
    if (row?.__unparseable !== undefined) {
      problems.push({ index, problem: "unparseable_row" });
      expectedPrev = null;
      continue;
    }
    if (typeof row?.record_hash !== "string") {
      problems.push({ index, run_id: row?.run_id ?? null, problem: "legacy_unchained_row" });
      expectedPrev = null;
      continue;
    }
    if (ledgerRecordHash(row) !== row.record_hash) {
      problems.push({ index, run_id: row.run_id ?? null, problem: "record_hash_mismatch" });
    }
    if (expectedPrev !== null && row.prev !== expectedPrev) {
      problems.push({ index, run_id: row.run_id ?? null, problem: "chain_broken" });
    }
    if (Array.isArray(row.stages) && !verifyStageChain(row.run_id, row.stages)) {
      problems.push({ index, run_id: row.run_id ?? null, problem: "stage_chain_broken" });
    }
    expectedPrev = sha256(row.record_hash);
  }

  const fatal = problems.filter((entry) => entry.problem !== "legacy_unchained_row");
  return { ok: fatal.length === 0, rows: rows.length, problems };
}


function appendGuardRun(ledgerPath, row) {
  fs.mkdirSync(path.dirname(ledgerPath), { recursive: true, mode: 0o700 });
  const previous = readLedgerRows(ledgerPath).at(-1);
  const prev = typeof previous?.record_hash === "string"
    ? sha256(previous.record_hash)
    : LEDGER_GENESIS;
  const chained = { ...row, prev };
  chained.record_hash = ledgerRecordHash(chained);
  fs.appendFileSync(ledgerPath, `${JSON.stringify(chained)}\n`, { mode: 0o600 });
  fs.chmodSync(ledgerPath, 0o600);
  return chained;
}


// ---------------------------------------------------------------------------------------------
// Run lock. Two guards on one PR would double-merge, double-deploy, and interleave their appends
// into the chained ledger. O_EXCL creation is the flock the filesystem already gives us; a lock
// older than 30 minutes belonged to a process that died mid-run and is taken over rather than
// left to wedge the loop forever.
// ---------------------------------------------------------------------------------------------
const GUARD_LOCK_STALE_MS = 30 * 60 * 1000;


function guardLockPath(ledgerPath) {
  return `${String(ledgerPath)}.lock`;
}


// ---------------------------------------------------------------------------------------------
// Stage progress. The guard runs as a detached child of the daily self-build pass, and that parent
// enforces a wall-clock budget by killing the whole process group. A blind kill can land BETWEEN
// `git merge` and the ledger append: main is merged, nothing is recorded, and no rollback is even
// attempted. The parent therefore has to know which stage the child is in, and the only process
// that knows is the child. So: one small file, rewritten whenever a stage BEGINS.
//
// Written rather than returned, because the parent cannot read the child's memory; BEGUN rather
// than finished, because the dangerous window opens the moment the merge is attempted, not when it
// succeeds. Best effort in both directions — a progress file that cannot be written must never
// stop a real run, and one that cannot be read is reported as `null`, which the parent treats as
// "pre-merge", i.e. killable. That default can waste a run; it can never orphan a merge, because a
// guard that has truly begun merging has already written the file before touching git.
// ---------------------------------------------------------------------------------------------
function readGuardProgress(progressFile) {
  if (!progressFile) return null;
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(progressFile, "utf8"));
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  return {
    runId: parsed.run_id ?? null,
    stage: parsed.stage ? String(parsed.stage) : null,
    stagesBegun: Array.isArray(parsed.stages_begun) ? parsed.stages_begun.map(String) : [],
    updatedAt: parsed.updated_at ?? null,
  };
}


function writeGuardProgress(progressFile, { runId, stage } = {}) {
  if (!progressFile || !stage) return null;
  const previous = readGuardProgress(progressFile);
  const stagesBegun = [...(previous?.stagesBegun ?? [])];
  if (!stagesBegun.includes(String(stage))) stagesBegun.push(String(stage));
  const payload = {
    run_id: runId ?? previous?.runId ?? null,
    stage: String(stage),
    stages_begun: stagesBegun,
    updated_at: new Date().toISOString(),
  };
  try {
    fs.mkdirSync(path.dirname(progressFile), { recursive: true, mode: 0o700 });
    // Rename, not truncate-and-write: the parent may read this file at any instant, and a
    // half-written progress file parses as null, which would read as "pre-merge" mid-merge.
    const temporary = `${progressFile}.${process.pid}.tmp`;
    fs.writeFileSync(temporary, `${JSON.stringify(payload)}\n`, { mode: 0o600 });
    fs.renameSync(temporary, progressFile);
    fs.chmodSync(progressFile, 0o600);
  } catch {
    // A run that cannot describe itself still has to run. The ledger row is the real record.
  }
  return payload;
}


function acquireGuardLock(lockPath, options = {}) {
  const nowMs = (options.now ? options.now() : new Date()).getTime();
  const pid = options.pid ?? process.pid;
  const staleMs = options.staleMs ?? GUARD_LOCK_STALE_MS;
  const claim = () => {
    const fd = fs.openSync(lockPath, "wx", 0o600);
    try {
      fs.writeFileSync(fd, JSON.stringify({
        pid, acquired_at: new Date(nowMs).toISOString(), acquired_at_ms: nowMs,
      }));
    } finally {
      fs.closeSync(fd);
    }
  };

  fs.mkdirSync(path.dirname(lockPath), { recursive: true, mode: 0o700 });
  try {
    claim();
    return { ok: true, pid, stolen: null };
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
  }

  let holder = null;
  try { holder = JSON.parse(fs.readFileSync(lockPath, "utf8")); } catch { holder = null; }
  const heldSinceMs = Number(holder?.acquired_at_ms);
  const ageMs = Number.isFinite(heldSinceMs) ? nowMs - heldSinceMs : Infinity;
  if (ageMs < staleMs) return { ok: false, holder, ageMs };

  try { fs.unlinkSync(lockPath); } catch {}
  try {
    claim();
    return { ok: true, pid, stolen: holder };
  } catch {
    return { ok: false, holder, ageMs };
  }
}


function releaseGuardLock(lockPath, options = {}) {
  const pid = options.pid ?? process.pid;
  try {
    const holder = JSON.parse(fs.readFileSync(lockPath, "utf8"));
    if (holder && holder.pid !== pid) return false;
  } catch {
    // An unreadable or already-removed lock is not ours to defend.
  }
  try { fs.unlinkSync(lockPath); return true; } catch { return false; }
}


function tail(text, limit = 4000) {
  const value = String(text || "");
  return value.length <= limit ? value : value.slice(-limit);
}


function normalizeReview(answer) {
  const verdict = answer && typeof answer === "object" ? String(answer.verdict || "") : "";
  const findings = answer && Array.isArray(answer.findings)
    ? answer.findings.map((finding) => String(finding))
    : [];
  if (verdict !== "pass" && verdict !== "fail") {
    return {
      ok: false,
      verdict: verdict || null,
      findings: findings.length ? findings : ["reviewer returned no usable verdict"],
    };
  }
  return { ok: verdict === "pass", verdict, findings };
}


function createReviewCommandHook(command, options = {}) {
  const exec = options.exec;
  if (typeof exec !== "function") throw new Error("dev_merge_guard_review_exec_required");
  return async (diff) => {
    try {
      const output = exec("/bin/sh", ["-c", String(command)], {
        input: String(diff || ""),
        encoding: "utf8",
        timeout: options.timeoutMs || 30 * 60 * 1000,
        maxBuffer: 64 * 1024 * 1024,
      });
      const parsed = JSON.parse(String(output || ""));
      const verdict = parsed && parsed.verdict === "pass" ? "pass" : "fail";
      const findings = Array.isArray(parsed?.findings) ? parsed.findings.map(String) : [];
      if (verdict === "fail" && findings.length === 0) {
        findings.push("reviewer returned a non-pass verdict without findings");
      }
      return { verdict, findings };
    } catch (error) {
      return {
        verdict: "fail",
        findings: [`review command did not return JSON: ${error.message}`],
      };
    }
  };
}


async function pollUntil(probe, { now, sleep, timeoutMs, intervalMs }) {
  const deadline = now().getTime() + timeoutMs;
  for (;;) {
    const value = await probe();
    if (value) return value;
    if (now().getTime() >= deadline) return null;
    await sleep(intervalMs);
  }
}


function createGuardDeps(io = {}) {
  const execImpl = io.exec;
  if (typeof execImpl !== "function") throw new Error("dev_merge_guard_exec_required");
  const fetchImpl = io.fetch || globalThis.fetch;
  const ghImpl = io.gh || ((args, options) => execImpl("gh", args, options));
  const env = io.env || process.env;
  const tgSend = io.sendMessage || ((token, chatId, text) =>
    require("./telegram.js").sendMessage(token, chatId, text));
  const config = io.config || {};
  const repo = config.repo || REPO;
  const repoDir = config.repoDir || REPO_DIR;
  const appSubdir = config.appSubdir || "apps/life-manager";
  const healthUrl = config.healthUrl || HEALTH_URL;
  const railwayArgs = [
    "-p", config.project || RAILWAY_PROJECT,
    "-s", config.service || RAILWAY_SERVICE,
    "-e", config.environment || RAILWAY_ENVIRONMENT,
  ];

  const gh = (args) => String(ghImpl([...args], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }) || "");
  const ghJson = (args) => JSON.parse(gh(args) || "null");
  const railway = (args, options) => String(execImpl("railway", args, {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
    ...options,
  }) || "");

  const git = (args, options) => String(execImpl("git", args, {
    cwd: repoDir,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    ...options,
  }) || "");

  // Everything the guard judges — the file list AND the diff — must come from ONE immutable commit.
  // `gh pr diff` renders whatever the branch points at right now, so an author who pushes between
  // the review and the merge gets a merge of code no one reviewed. Fetching the head oid into
  // remote-tracking refs pins it; `--match-head-commit` at merge time closes the loop.
  const fetched = new Set();
  const ensureFetched = (base, headRefName) => {
    const key = `${base} ${headRefName}`;
    if (fetched.has(key)) return;
    git(["fetch", "--no-tags", "origin",
      `+refs/heads/${base}:refs/remotes/origin/${base}`,
      `+refs/heads/${headRefName}:refs/remotes/origin/${headRefName}`,
    ]);
    fetched.add(key);
  };

  const sleep = io.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  // GitHub computes mergeability lazily: the first read of a PR that has not been checked since
  // its last push answers UNKNOWN, and asking is what schedules the computation. Measured on real
  // PR #1094 on 2026-07-27 — the guard refused a perfectly mergeable PR on the first query and saw
  // MERGEABLE on the next. Retry rather than turn GitHub's laziness into a false refusal.
  const mergeabilityAttempts = config.mergeabilityAttempts ?? 6;
  const mergeabilityIntervalMs = config.mergeabilityIntervalMs ?? 3000;

  return {
    now: io.now || (() => new Date()),
    sleep,
    ledgerPath: io.ledgerPath || guardLedgerPath(),

    async getPullRequest(prNumber) {
      let pr = null;
      for (let attempt = 0; attempt < mergeabilityAttempts; attempt += 1) {
        if (attempt > 0) await sleep(mergeabilityIntervalMs);
        pr = ghJson([
          "pr", "view", String(prNumber), "-R", repo,
          "--json", "number,state,baseRefName,headRefName,headRefOid,author,mergeable,files,url,body",
        ]);
        if (pr?.mergeable !== "UNKNOWN") return pr;
      }
      return pr;
    },

    // The reviewed diff is `git diff <base>...<headOid>` at the pinned head commit, NOT
    // `gh pr diff`, which follows a branch the author can move after the reviewer has spoken.
    async getDiff({ base, headOid, headRefName }) {
      ensureFetched(String(base), String(headRefName));
      return git(["diff", `refs/remotes/origin/${base}...${headOid}`]);
    },

    // Same single source of truth as getDiff, and the reason gh's `files` array is only a
    // cross-check: it truncates at 100 entries and collapses a rename to its new path.
    async listChangedFiles({ base, headOid, headRefName }) {
      ensureFetched(String(base), String(headRefName));
      return parseNameStatus(git([
        "diff", "--name-status", "-M", `refs/remotes/origin/${base}...${headOid}`,
      ]));
    },

    async readFileAtRef({ ref, path: filePath }) {
      try {
        const encoded = gh([
          "api", `repos/${repo}/contents/${filePath}?ref=${encodeURIComponent(ref)}`,
          "--jq", ".content",
        ]).trim();
        return Buffer.from(encoded, "base64").toString("utf8");
      } catch {
        return null;
      }
    },

    // Full suite + evals against a throwaway checkout of the PR head, so nothing in the
    // operator's working tree can make a red PR look green.
    //
    // This DOES execute the PR's own code — see the file header. `--ignore-scripts` removes the
    // easiest path (an added `postinstall` running before a single assertion does), and running
    // last, after review and the tripwire, means the code being executed has been read. Neither is
    // a sandbox; real isolation is future work.
    async runTests({ headOid, headRefName }) {
      const worktree = fs.mkdtempSync(path.join(os.tmpdir(), "lm-guard-worktree-"));
      const appDir = path.join(worktree, appSubdir);
      const output = [];
      const run = (file, args, cwd) => {
        output.push(`$ ${file} ${args.join(" ")}`);
        output.push(String(execImpl(file, args, {
          cwd,
          encoding: "utf8",
          maxBuffer: 64 * 1024 * 1024,
          timeout: 60 * 60 * 1000,
        }) || ""));
      };
      try {
        run("git", ["fetch", "origin", String(headRefName)], repoDir);
        run("git", ["worktree", "add", "--detach", worktree, String(headOid)], repoDir);
        run("npm", ["ci", "--silent", "--ignore-scripts"], appDir);
        run("npm", ["test"], appDir);
        run("npm", ["run", "eval"], appDir);
        return { ok: true, exitCode: 0, output: output.join("\n") };
      } catch (error) {
        output.push(String(error.stdout || ""));
        output.push(String(error.stderr || error.message || ""));
        return { ok: false, exitCode: Number.isInteger(error.status) ? error.status : 1, output: output.join("\n") };
      } finally {
        try { execImpl("git", ["worktree", "remove", "--force", worktree], { cwd: repoDir, encoding: "utf8" }); } catch {}
        try { fs.rmSync(worktree, { recursive: true, force: true }); } catch {}
      }
    },

    async merge({ prNumber, headOid }) {
      try {
        gh([
          "pr", "merge", String(prNumber), "-R", repo,
          "--squash", "--delete-branch", "--match-head-commit", String(headOid),
        ]);
      } catch (error) {
        return { ok: false, reason: `merge_command_failed: ${error.message}` };
      }
      const readback = ghJson(["pr", "view", String(prNumber), "-R", repo, "--json", "state,mergeCommit"]);
      const mergeSha = readback?.mergeCommit?.oid || null;
      if (readback?.state !== "MERGED" || !/^[a-f0-9]{40}$/.test(String(mergeSha))) {
        return { ok: false, reason: "merge_readback_failed" };
      }
      return { ok: true, mergeSha };
    },

    async listDeployments() {
      const raw = railway(["deployment", "list", ...railwayArgs, "--limit", "20", "--json"]);
      const parsed = JSON.parse(raw || "[]");
      return Array.isArray(parsed) ? parsed : [];
    },

    async getPreviousSuccessfulDeployment() {
      const raw = railway(["deployment", "list", ...railwayArgs, "--limit", "20", "--json"]);
      const list = JSON.parse(raw || "[]");
      for (const item of Array.isArray(list) ? list : []) {
        if (item.status !== "SUCCESS" || !item.meta?.commitHash) continue;
        const detail = JSON.parse(railway([
          "api", DEPLOYMENT_DETAIL_QUERY, "--variables", JSON.stringify({ id: item.id }),
        ]) || "null");
        const deployment = detail?.data?.deployment;
        if (!deployment) continue;
        return {
          id: deployment.id,
          status: deployment.status,
          canRollback: deployment.canRollback === true,
          commitHash: deployment.meta?.commitHash || item.meta.commitHash,
        };
      }
      return null;
    },

    async triggerRedeploy() {
      try {
        return { ok: true, raw: railway(["redeploy", ...railwayArgs, "--yes", "--json"]) };
      } catch (error) {
        return { ok: false, raw: String(error.message || "") };
      }
    },

    async checkHealth() {
      try {
        const response = await fetchImpl(healthUrl, {
          headers: { "user-agent": "life-manager-dev-merge-guard/1" },
          signal: AbortSignal.timeout(15000),
        });
        if (!response.ok) return false;
        const body = await response.json();
        return body?.ok === true;
      } catch {
        return false;
      }
    },

    // `railway redeploy` cannot target a deployment id (verified above), so rollback is the
    // GraphQL mutation the CLI proxies through `railway api`.
    async rollback({ deploymentId }) {
      try {
        const raw = railway([
          "api", ROLLBACK_MUTATION, "--variables", JSON.stringify({ id: String(deploymentId) }),
        ]);
        const parsed = JSON.parse(raw || "null");
        return { ok: parsed?.data?.deploymentRollback === true, raw };
      } catch (error) {
        return { ok: false, raw: String(error.message || "") };
      }
    },

    async openRevertPr({ mergeSha, prNumber, reason }) {
      const branch = `revert/lm-dev-${prNumber}-${String(mergeSha).slice(0, 12)}`;
      const worktree = fs.mkdtempSync(path.join(os.tmpdir(), "lm-guard-revert-"));
      try {
        execImpl("git", ["fetch", "origin", "main"], { cwd: repoDir, encoding: "utf8" });
        execImpl("git", ["worktree", "add", "-b", branch, worktree, "origin/main"], { cwd: repoDir, encoding: "utf8" });
        execImpl("git", ["revert", "--no-edit", "-m", "1", String(mergeSha)], { cwd: worktree, encoding: "utf8" });
        execImpl("git", ["push", "-u", "origin", branch], { cwd: worktree, encoding: "utf8" });
        const url = gh([
          "pr", "create", "-R", repo, "--base", "main", "--head", branch,
          "--title", `revert: roll back PR #${prNumber} after a red production health check`,
          "--body", [
            `Automatic revert of \`${mergeSha}\` (merged from #${prNumber}).`,
            "",
            "Production health did not come back after the deploy, and the platform rollback was",
            `not available: ${reason || "the previous Railway deployment reported canRollback: false"}.`,
            "",
            "This PR is the rollback. Production is still on the merged commit until it lands.",
          ].join("\n"),
        ]).trim();
        return { url };
      } catch (error) {
        return { url: null, error: String(error.message || "") };
      } finally {
        try { execImpl("git", ["worktree", "remove", "--force", worktree], { cwd: repoDir, encoding: "utf8" }); } catch {}
        try { fs.rmSync(worktree, { recursive: true, force: true }); } catch {}
      }
    },

    // An alert nobody reads is not an alert. This guard runs unattended, so stderr on a launchd
    // runner is functionally /dev/null — the cases that reach here (production red, a revert PR
    // waiting for a human, a broken ledger chain) all need Dais's phone to buzz. Telegram first,
    // stderr only when the bot is not configured or the send fails.
    async alert(message) {
      const token = env.LM_TELEGRAM_BOT_TOKEN;
      const chatId = env.LM_ADMIN_TELEGRAM_CHAT_ID;
      const text = `⚠️ dev-merge-guard: ${message}`;
      if (token && chatId) {
        try {
          const answer = await tgSend(token, chatId, text);
          if (answer?.ok !== false) return { delivered: true, channel: "telegram" };
        } catch {
          // fall through to stderr rather than losing the alert entirely
        }
      }
      process.stderr.write(`dev-merge-guard ALERT: ${message}\n`);
      return { delivered: false, channel: "stderr" };
    },
  };
}


async function runMergeGuard({ prNumber, deps, options = {} }) {
  if (!deps
    || typeof deps.getPullRequest !== "function"
    || typeof deps.listChangedFiles !== "function") {
    throw new Error("dev_merge_guard_deps_required");
  }
  const now = deps.now || (() => new Date());
  const sleep = deps.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));

  const started = now();
  const runId = `${started.toISOString().replace(/\D/g, "").slice(0, 14)}-pr${prNumber}-${crypto.randomBytes(4).toString("hex")}`;

  // One guard at a time. Two concurrent runs would double-merge the same PR, race each other's
  // deploys, and interleave appends into a chained ledger that only makes sense written serially.
  const ledgerPath = deps.ledgerPath || guardLedgerPath();
  const lockPath = deps.lockPath || guardLockPath(ledgerPath);
  const lockPid = options.lockPid ?? process.pid;
  const lock = acquireGuardLock(lockPath, {
    now, pid: lockPid, staleMs: options.lockStaleMs,
  });
  if (!lock.ok) {
    // Deliberately no ledger row: a run that never held the lock must not append to the chain
    // while the holder is mid-write.
    return {
      runId,
      verdict: "locked",
      stoppedAtStage: null,
      stopReason: "another_guard_run_holds_the_lock",
      mergeSha: null,
      deployId: null,
      health: "skipped",
      rollback: null,
      stages: [],
      stagesPassed: [],
      stagesFailed: [],
      lock: { path: lockPath, held_by: lock.holder ?? null, age_ms: lock.ageMs ?? null },
      ledgerRow: null,
    };
  }

  try {
    return await runMergeGuardLocked({ prNumber, deps, options, now, sleep, started, runId, ledgerPath });
  } finally {
    releaseGuardLock(lockPath, { pid: lockPid });
  }
}


async function runMergeGuardLocked({ prNumber, deps, options, now, sleep, started, runId, ledgerPath }) {
  const healthTimeoutMs = options.healthTimeoutMs ?? 10 * 60 * 1000;
  const healthIntervalMs = options.healthIntervalMs ?? 10_000;
  const freshTimeoutMs = options.freshTimeoutMs ?? 15 * 60 * 1000;
  const freshIntervalMs = options.freshIntervalMs ?? 10_000;

  // Read the existing chain before writing to it. A ledger that stopped verifying between runs is
  // the single loudest signal this machinery can produce, so it is checked every time and alerted
  // on immediately — not left for whoever eventually reads the file.
  const ledgerCheck = verifyLedgerTail(ledgerPath, { limit: options.ledgerTailLimit ?? 200 });
  if (!ledgerCheck.ok) {
    await deps.alert(
      `the run ledger at ${ledgerPath} no longer verifies (${JSON.stringify(ledgerCheck.problems)}).`
      + " Treat every Day-N claim built on it as unproven until a human looks.",
    );
  }

  const records = [];
  const state = {
    stoppedAtStage: null,
    stopReason: null,
    mergeSha: null,
    deployId: null,
    health: "skipped",
    rollback: null,
  };

  const record = (stage, ok, reason, evidence) => {
    // A reason only ever describes a failure; a passing stage carries none.
    records.push({ stage, ok, reason: ok ? null : (reason || stage), evidence: evidence || {} });
    if (!ok && GUARD_STAGES.includes(stage) && state.stoppedAtStage === null) {
      state.stoppedAtStage = stage;
      state.stopReason = reason || stage;
    }
    return ok;
  };

  let diff = null;
  let diffContext = null;
  const loadDiff = async () => {
    if (diff === null) diff = String(await deps.getDiff(diffContext) || "");
    return diff;
  };

  let verdict = "stopped";
  let postMergeError = null;

  // Announced to the parent BEFORE the stage does anything, so a kill that races the announcement
  // can only ever be too early (safe) and never too late (a merge nobody knows about).
  const beginStage = (stage) => writeGuardProgress(options.progressFile, { runId, stage });

  try {
    run: {
      // 1. Eligibility.
      beginStage("eligibility");
      const pr = await deps.getPullRequest(prNumber);
      diffContext = {
        prNumber,
        base: pr?.baseRefName ?? "main",
        headOid: pr?.headRefOid ?? null,
        headRefName: pr?.headRefName ?? null,
      };

      // The file list git reports at the head commit, not the (truncated, rename-blind) one gh
      // reports for a branch. If it cannot be read the guard refuses: an unknown file list is not
      // an empty one.
      let changedFiles = null;
      let changedFilesError = null;
      try {
        const listed = await deps.listChangedFiles({
          base: diffContext.base, headOid: pr?.headRefOid, headRefName: pr?.headRefName,
        });
        changedFiles = Array.isArray(listed) ? listed.map(String) : null;
      } catch (error) {
        changedFilesError = String(error?.message || error);
      }

      const eligibility = evaluateEligibility(pr, {
        allowedAuthors: options.allowedAuthors,
        protectedPaths: options.protectedPaths,
        expectHead: options.expectHead,
        changedFiles,
        recoveryPromotionEnabled: options.recoveryPromotionEnabled,
      });
      const reasons = [...eligibility.reasons];
      if (changedFiles === null) reasons.push("changed_files_unreadable");

      const manifest = {};
      if (eligibility.conditionalPaths.includes(CONDITIONAL_MANIFEST)) {
        const before = await deps.readFileAtRef({ ref: pr.baseRefName, path: CONDITIONAL_MANIFEST });
        const after = await deps.readFileAtRef({ ref: pr.headRefOid, path: CONDITIONAL_MANIFEST });
        let evaluated;
        if (before === null || before === undefined || after === null || after === undefined) {
          // A manifest we could not read at BOTH refs is unknown, and unknown is not empty. The
          // old code JSON.parse'd a null into a null, compared {} with {}, and waved through
          // whatever the PR had actually done to package.json whenever gh hiccuped.
          evaluated = { allowed: false, reasons: ["unreadable"] };
        } else {
          try {
            evaluated = evaluatePackageJsonChange(JSON.parse(before), JSON.parse(after));
          } catch {
            evaluated = { allowed: false, reasons: ["unreadable"] };
          }
        }
        manifest.package_json = evaluated;
        for (const reason of evaluated.reasons) reasons.push(`package_json:${reason}`);
      }
      if (!record("eligibility", reasons.length === 0, reasons.join(","), {
        pr: pr?.number ?? prNumber,
        branch: pr?.headRefName ?? null,
        author: pr?.author?.login ?? null,
        head_oid: pr?.headRefOid ?? null,
        changed_paths: eligibility.changedPaths,
        denied_paths: eligibility.deniedPaths,
        conditional_paths: eligibility.conditionalPaths,
        files_cross_check: eligibility.crossCheck,
        changed_files_error: changedFilesError,
        protected_paths: options.protectedPaths ?? [],
        expected_head: options.expectHead ?? null,
        ...manifest,
      })) break run;

      // 2. Fresh adversary — BEFORE the suite, because the suite executes the PR's code.
      beginStage("review");
      const review = normalizeReview(await deps.review(await loadDiff(), {
        prNumber,
        headOid: pr.headRefOid,
      }));
      if (!record("review", review.ok, "adversary_fail", {
        verdict: review.verdict,
        findings: review.findings,
      })) break run;

      // 3. BlockedActions tripwire — also before the suite, same reason.
      beginStage("blocked_actions");
      const hits = detectBlockedActions(parseAddedLines(await loadDiff()));
      if (!record("blocked_actions", hits.length === 0, "blocked_actions_present", { hits })) break run;

      // 4. Tests + evals, in an isolated worktree of the PR head commit.
      beginStage("tests");
      const tests = await deps.runTests({ headOid: pr.headRefOid, headRefName: pr.headRefName });
      if (!record("tests", tests?.ok === true && tests.exitCode === 0, "test_suite_red", {
        exit_code: tests?.exitCode ?? null,
        output_tail: tail(tests?.output),
      })) break run;

      // 5. Merge. The rollback target is read BEFORE the merge, while it is still the live one.
      //
      // The progress announcement goes out FIRST, before a single irreversible call. From this
      // line on the parent's wall-clock budget stops being allowed to kill this process: a merge
      // interrupted between `git merge` and the ledger append leaves main changed, unrecorded and
      // un-rolled-back, which is strictly worse than a run that simply took too long.
      beginStage("merge");
      const previous = await deps.getPreviousSuccessfulDeployment();
      const merged = await deps.merge({ prNumber, headOid: pr.headRefOid });
      const mergeOk = merged?.ok === true && /^[a-f0-9]{40}$/.test(String(merged.mergeSha || ""));
      if (mergeOk) state.mergeSha = merged.mergeSha;
      if (!record("merge", mergeOk, merged?.reason || "merge_failed", {
        merge_sha: state.mergeSha,
        previous_deployment_id: previous?.id ?? null,
        previous_deployment_can_rollback: previous?.canRollback ?? null,
      })) break run;

      // 6. Deploy + health + deploy freshness.
      //
      // From here on the merge HAS HAPPENED. Anything that throws past this point — a railway CLI
      // that dies, a network that vanishes, a deps stub that blows up — must still leave a ledger
      // row saying so, or 10f's Day-N evidence silently loses the one run that mattered: the one
      // that put code into production and then stopped being able to describe it.
      beginStage("deploy_health");
      try {
        const redeploy = await deps.triggerRedeploy();
        const healthy = await pollUntil(() => deps.checkHealth(), {
          now, sleep, timeoutMs: healthTimeoutMs, intervalMs: healthIntervalMs,
        });
        if (!healthy) {
          state.health = "failed";
          record("deploy_health", false, "health_red_after_merge", {
            redeploy_ok: redeploy?.ok ?? null,
            health: "failed",
          });
          state.rollback = await performRollback({
            deps, previous, mergeSha: state.mergeSha, prNumber, records,
            now, sleep, healthTimeoutMs, healthIntervalMs,
          });
          // The verdict is whatever the rollback ACTUALLY achieved. Announcing "rolled_back"
          // before the mutation had even answered was the guard lying in its own evidence file.
          verdict = state.rollback?.ok === true ? "rolled_back" : "rollback_failed";
          break run;
        }
        state.health = "ok";

        const fresh = await pollUntil(async () => {
          const deployments = await deps.listDeployments();
          return (Array.isArray(deployments) ? deployments : []).find((deployment) =>
            deployment
            && deployment.id !== previous?.id
            && deployment.status === "SUCCESS"
            && deployment.meta?.commitHash === state.mergeSha) || null;
        }, { now, sleep, timeoutMs: freshTimeoutMs, intervalMs: freshIntervalMs });

        if (!fresh) {
          record("deploy_health", false, "deploy_freshness_unverified", {
            redeploy_ok: redeploy?.ok ?? null,
            health: "ok",
            merge_sha: state.mergeSha,
          });
          await deps.alert(
            `PR #${prNumber} merged as ${state.mergeSha} and /health is ok, but no Railway deployment`
            + " reported that exact commit. Production may still be serving the old build.",
          );
          break run;
        }
        state.deployId = fresh.id;
        record("deploy_health", true, null, {
          redeploy_ok: redeploy?.ok ?? null,
          health: "ok",
          deploy_id: fresh.id,
          deploy_commit: fresh.meta?.commitHash ?? null,
        });
        verdict = "merged_deployed";
      } catch (error) {
        postMergeError = String(error?.stack || error?.message || error);
        verdict = "merged_unverified";
        record("deploy_health", false, "post_merge_error", {
          merge_sha: state.mergeSha,
          error: postMergeError,
        });
        try {
          await deps.alert(
            `PR #${prNumber} merged as ${state.mergeSha}, then the deploy/verify path threw:`
            + ` ${postMergeError}. Production state is UNKNOWN and no rollback was attempted.`,
          );
        } catch {
          // An alert that fails must not be the reason the run goes unrecorded.
        }
        break run;
      }
    }
  } catch (error) {
    // A throw before the merge is a bug in the guard, not in the PR — record it rather than
    // vanishing without a row.
    postMergeError = String(error?.stack || error?.message || error);
    verdict = state.mergeSha ? "merged_unverified" : "errored";
    if (state.stopReason === null) state.stopReason = "guard_threw";
    record("guard_error", false, "guard_threw", { error: postMergeError });
    try { await deps.alert(`the guard itself threw on PR #${prNumber}: ${postMergeError}`); } catch {}
  }

  const finished = now();
  const stages = signStageChain(runId, records);
  const gateRecords = stages.filter((entry) => GUARD_STAGES.includes(entry.stage));
  const row = appendGuardRun(ledgerPath, {
    // v2 adds prev/record_hash (the row chain), post_merge_error and ledger_check.
    schema_version: 2,
    run_id: runId,
    pr: Number(prNumber),
    started_at: started.toISOString(),
    finished_at: finished.toISOString(),
    duration_ms: Math.max(0, finished.getTime() - started.getTime()),
    verdict,
    stopped_at_stage: state.stoppedAtStage,
    stop_reason: state.stopReason,
    stages_passed: gateRecords.filter((entry) => entry.ok).map((entry) => entry.stage),
    stages_failed: gateRecords.filter((entry) => !entry.ok).map((entry) => entry.stage),
    stages,
    merge_sha: state.mergeSha,
    deploy_id: state.deployId,
    health: state.health,
    rollback: state.rollback,
    post_merge_error: postMergeError,
    ledger_check: { ok: ledgerCheck.ok, rows: ledgerCheck.rows, problems: ledgerCheck.problems },
  });

  return {
    runId,
    verdict,
    stoppedAtStage: state.stoppedAtStage,
    stopReason: state.stopReason,
    mergeSha: state.mergeSha,
    deployId: state.deployId,
    health: state.health,
    rollback: state.rollback,
    postMergeError,
    ledgerCheck,
    stages,
    stagesPassed: row.stages_passed,
    stagesFailed: row.stages_failed,
    ledgerRow: row,
  };
}


// Returns what the rollback ACTUALLY achieved — the caller turns that into the verdict. Two things
// this must never do: report `ok: true` because a rollback was attempted, and stop after the
// platform mutation answered `false`. A refused mutation leaves production on the bad commit just
// as surely as `canRollback: false` does, so both fall through to the same remedy: a revert PR.
async function performRollback({
  deps, previous, mergeSha, prNumber, records, now, sleep, healthTimeoutMs, healthIntervalMs,
}) {
  let railwayRollbackOk = null;
  let healthAfter = null;
  let fallbackReason = "the previous Railway deployment reported `canRollback: false`";

  if (previous && previous.canRollback === true) {
    const result = await deps.rollback({ deploymentId: previous.id });
    railwayRollbackOk = result?.ok === true;
    healthAfter = await pollUntil(() => deps.checkHealth(), {
      now, sleep, timeoutMs: healthTimeoutMs, intervalMs: healthIntervalMs,
    }) ? "ok" : "failed";

    if (railwayRollbackOk) {
      const rollback = {
        attempted: true,
        method: "railway_api_deployment_rollback",
        target_deployment_id: previous.id,
        ok: true,
        railway_rollback_ok: true,
        revert_pr_url: null,
        health_after: healthAfter,
      };
      records.push({ stage: "rollback", ok: true, reason: null, evidence: rollback });
      await deps.alert(
        `PR #${prNumber} merged as ${mergeSha} but production health stayed red. Rolled back to`
        + ` deployment ${previous.id} (health_after=${healthAfter}).`,
      );
      return rollback;
    }

    fallbackReason = `deploymentRollback(${previous.id}) answered false`;
    records.push({
      stage: "rollback_attempt",
      ok: false,
      reason: "rollback_mutation_failed",
      evidence: {
        method: "railway_api_deployment_rollback",
        target_deployment_id: previous.id,
        ok: false,
        health_after: healthAfter,
      },
    });
    await deps.alert(
      `PR #${prNumber} merged as ${mergeSha}, production health is red, and Railway REFUSED the`
      + ` rollback of deployment ${previous.id}. Falling back to a revert PR.`,
    );
  }

  const revert = await deps.openRevertPr({ mergeSha, prNumber, reason: fallbackReason });
  const rollback = {
    attempted: true,
    // No platform rollback is available, so the only honest remedy is a revert PR — which a human
    // still has to merge. Production stays on the bad commit until then, and the alert says so.
    method: "revert_pr",
    target_deployment_id: previous?.id ?? null,
    ok: Boolean(revert?.url),
    railway_rollback_ok: railwayRollbackOk,
    revert_pr_url: revert?.url ?? null,
    revert_pr_error: revert?.error ?? null,
    health_after: healthAfter ?? "failed",
    production_still_on_bad_commit: true,
  };
  records.push({
    stage: "rollback",
    ok: rollback.ok,
    reason: rollback.ok ? null : "revert_pr_failed",
    evidence: rollback,
  });
  await deps.alert(
    rollback.ok
      ? `PR #${prNumber} merged as ${mergeSha}, production health is red, and no platform rollback`
        + ` was possible (${fallbackReason}). Opened revert PR ${rollback.revert_pr_url} — it needs`
        + " a HUMAN to merge it. Production stays on the bad commit until then."
      : `PR #${prNumber} merged as ${mergeSha}, production health is red, the platform rollback was`
        + ` not possible (${fallbackReason}), AND the revert PR could not be opened`
        + ` (${rollback.revert_pr_error || "unknown error"}). Production is broken and unattended`
        + " machinery has run out of remedies. A human must intervene now.",
  );
  return rollback;
}


module.exports = {
  REPO,
  HEALTH_URL,
  GUARD_STAGES,
  BLOCKED_ACTIONS,
  RECOVERY_PR_MARKER,
  BRANCH_PATTERNS,
  ROLLBACK_MUTATION,
  GUARD_SELF_PATHS,
  GUARD_SOURCE_RELATIVE,
  LEDGER_GENESIS,
  GUARD_LOCK_STALE_MS,
  classifyChangedPath,
  evaluatePackageJsonChange,
  evaluateEligibility,
  isRetainedRegressionFixture,
  parseAddedLines,
  parseNameStatus,
  detectBlockedActions,
  resolveReviewCommandPaths,
  signStageChain,
  verifyStageChain,
  guardLedgerPath,
  guardLockPath,
  readGuardProgress,
  writeGuardProgress,
  acquireGuardLock,
  releaseGuardLock,
  appendGuardRun,
  readLedgerRows,
  verifyLedgerTail,
  createReviewCommandHook,
  createGuardDeps,
  runMergeGuard,
};
