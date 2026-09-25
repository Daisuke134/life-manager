"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const SHA = /^sha256:[0-9a-f]{64}$/;
const SAFE = /^[A-Za-z0-9:._-]{1,160}$/;
const SAFE_BRANCH = /^[A-Za-z0-9][A-Za-z0-9/._-]{0,159}$/;

function invalid() {
  throw new Error("Connector Healer shadow invalid");
}

function readJsonl(file, limit = 1_000_000) {
  let source = "";
  try {
    const stat = fs.statSync(file);
    if (stat.size > limit) invalid();
    source = fs.readFileSync(file, "utf8");
  } catch (error) {
    if (!error || error.code !== "ENOENT") throw error;
  }
  return source.split(/\r?\n/).filter(Boolean).map((line) => {
    try { return JSON.parse(line); } catch { invalid(); }
  });
}

function validateIncident(value) {
  if (
    !value || typeof value !== "object" || Array.isArray(value)
    || value.schema_version !== 1 || !SHA.test(String(value.fingerprint || ""))
    || !SAFE.test(String(value.wake_id || "")) || !SAFE.test(String(value.run_id || ""))
    || !SAFE.test(String(value.stage || "")) || !SAFE.test(String(value.safe_action || ""))
    || !SAFE.test(String(value.expected_effect || "")) || !SAFE.test(String(value.observed_effect || ""))
    || !SAFE.test(String(value.incident_class || "")) || value.incident_class === "none"
    || !SAFE.test(String(value.code_commit || "")) || !SAFE.test(String(value.cursor || ""))
    || !Number.isFinite(Date.parse(String(value.observed_at || "")))
  ) invalid();
  return value;
}

function defaultExecute(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    env: options.env,
    input: options.input,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
    maxBuffer: 16 * 1024 * 1024,
    timeout: Number(options.timeoutMs || 45 * 60 * 1000),
    killSignal: "SIGTERM",
  });
  return {
    status: result.status,
    signal: result.signal || null,
    errorCode: result.error && result.error.code || null,
    stdout: String(result.stdout || ""),
    stderr: String(result.stderr || ""),
  };
}

function healerEnvironment(env = process.env) {
  const clean = {};
  for (const key of ["PATH", "HOME", "CODEX_HOME", "TMPDIR", "LANG", "LC_ALL"]) {
    if (env[key]) clean[key] = String(env[key]);
  }
  clean.LM_CONNECTOR_HEALER_SHADOW = "1";
  clean.LM_CONNECTOR_EXTERNAL_EFFECTS = "disabled";
  return clean;
}

function healerPrompt(incident) {
  return [
    "You are the Connector shadow Healer. Work only in this isolated worktree.",
    "Use Superpowers systematic-debugging phases 1-4. Form exactly one root-cause hypothesis.",
    "Use Superpowers test-driven-development: observe one focused RED, implement the smallest GREEN, then run fresh verification.",
    "external event submit is forbidden. Browser, Calendar, Gmail, Telegram, payment, launchd, and production deployment are forbidden.",
    "Do not read secrets, PII, raw logs, runtime profiles, CloakBrowser state, Gig state, or port 9223.",
    "Do not commit, push, merge, or deploy. Parent Healer owns commit and push after your turn.",
    `Privacy-safe incident: ${JSON.stringify({
      fingerprint: incident.fingerprint,
      stage: incident.stage,
      safe_action: incident.safe_action,
      expected_effect: incident.expected_effect,
      observed_effect: incident.observed_effect,
      incident_class: incident.incident_class,
      code_commit: incident.code_commit,
      cursor: incident.cursor,
    })}`,
  ].join("\n");
}

function appendRevision(file, input) {
  const row = {
    schema_version: 1,
    fingerprint: input.fingerprint,
    revision: input.revision,
    status: input.status,
    branch: input.branch,
    commit: input.commit || "none",
    observed_at: input.observed_at,
  };
  if (
    !SHA.test(String(row.fingerprint || ""))
    || !Number.isInteger(row.revision) || row.revision < 1 || row.revision > 3
    || !["revision_created", "revision_failed", "revision_timeout", "worktree_failed"].includes(row.status)
    || !SAFE_BRANCH.test(String(row.branch || "")) || !SAFE.test(String(row.commit || ""))
    || new Date(Date.parse(String(row.observed_at || ""))).toISOString() !== row.observed_at
  ) invalid();
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  fs.appendFileSync(file, `${JSON.stringify(row)}\n`, { encoding: "utf8", mode: 0o600 });
  return row;
}

function prepareWorktreeDependencies(repoRoot, worktree) {
  const target = path.join(repoRoot, "apps/life-manager/node_modules");
  const link = path.join(worktree, "apps/life-manager/node_modules");
  let targetStat;
  try { targetStat = fs.lstatSync(target); } catch { invalid(); }
  if (!targetStat.isDirectory() && !targetStat.isSymbolicLink()) invalid();
  let resolvedTarget;
  try {
    resolvedTarget = fs.realpathSync(target);
    if (!fs.statSync(resolvedTarget).isDirectory()) invalid();
  } catch {
    invalid();
  }
  if (targetStat.isSymbolicLink()) {
    const bundleRoot = path.resolve(fs.realpathSync(repoRoot), "../..", "dependency-bundles");
    const relative = path.relative(bundleRoot, resolvedTarget);
    const parts = relative.split(path.sep);
    if (
      parts.length !== 2
      || !/^npm-[A-Za-z0-9._-]{1,160}$/.test(parts[0])
      || parts[1] !== "node_modules"
      || !fs.statSync(path.join(bundleRoot, parts[0], ".complete"), { throwIfNoEntry: false })?.isFile()
      || !fs.statSync(path.join(resolvedTarget, ".package-lock.json"), { throwIfNoEntry: false })?.isFile()
    ) invalid();
  }
  fs.mkdirSync(path.dirname(link), { recursive: true, mode: 0o700 });
  try {
    const linkStat = fs.lstatSync(link);
    if (!linkStat.isSymbolicLink() || fs.realpathSync(link) !== resolvedTarget) invalid();
  } catch (error) {
    if (!error || error.code !== "ENOENT") throw error;
    fs.symlinkSync(target, link, "dir");
  }
}

function cleanWorktreeStatus(repoRoot, worktree, source) {
  const target = path.join(repoRoot, "apps/life-manager/node_modules");
  const link = path.join(worktree, "apps/life-manager/node_modules");
  let safeLink = false;
  try {
    safeLink = fs.lstatSync(link).isSymbolicLink()
      && fs.realpathSync(link) === fs.realpathSync(target);
  } catch { safeLink = false; }
  return String(source || "").split(/\r?\n/).filter(Boolean).filter((line) => (
    !(safeLink && line === "?? apps/life-manager/node_modules")
  ));
}

async function runHealerShadow(options = {}) {
  const repoRoot = path.resolve(String(options.repoRoot || ""));
  const stateDir = path.resolve(String(options.stateDir || ""));
  const worktreeRoot = path.resolve(String(options.worktreeRoot || path.join(stateDir, "healer-worktrees")));
  if (
    !path.isAbsolute(repoRoot) || repoRoot === path.parse(repoRoot).root
    || !path.isAbsolute(stateDir) || stateDir === path.parse(stateDir).root
    || !path.isAbsolute(worktreeRoot) || worktreeRoot === path.parse(worktreeRoot).root
  ) invalid();
  const incidents = readJsonl(path.join(stateDir, "observer-incidents.jsonl")).map(validateIncident);
  const revisionsFile = path.join(stateDir, "healer-revisions.jsonl");
  const revisions = readJsonl(revisionsFile);
  const incident = [...incidents].reverse().find((row) => {
    const attempts = revisions.filter((revision) => revision.fingerprint === row.fingerprint);
    return !attempts.some((revision) => revision.status === "revision_created") && attempts.length < 3;
  });
  if (!incident) return Object.freeze({ status: "duplicate" });

  const now = typeof options.now === "function" ? options.now() : new Date();
  const observedAt = now.toISOString();
  const recent = revisions.filter((row) => Date.parse(row.observed_at) >= now.getTime() - 24 * 60 * 60 * 1000);
  if (recent.length >= 3) return Object.freeze({ status: "revision_cap" });
  const execute = options.execute || defaultExecute;
  let baseCommit = incident.code_commit;
  if (baseCommit === "unknown") {
    const resolved = await execute("git", ["-C", repoRoot, "rev-parse", "HEAD"], {
      cwd: repoRoot, env: healerEnvironment(options.env),
    });
    baseCommit = String(resolved && resolved.stdout || "").trim();
    if (!resolved || resolved.status !== 0 || !/^[0-9a-f]{40}$/.test(baseCommit)) invalid();
  }
  const short = incident.fingerprint.slice("sha256:".length, "sha256:".length + 12);
  const revision = recent.length + 1;
  let branch = `healer/connector-${short}-r${revision}`;
  let worktree = path.join(worktreeRoot, `${short}-r${revision}`);
  fs.mkdirSync(worktreeRoot, { recursive: true, mode: 0o700 });

  let result = await execute("git", ["-C", repoRoot, "worktree", "add", "-b", branch, worktree, baseCommit], {
    cwd: repoRoot, env: healerEnvironment(options.env),
  });
  const collision = result && result.status !== 0
    && /(?:branch|worktree|path).*(?:already exists|already checked out|already registered)/i
      .test(String(result.stderr || ""));
  if (collision) {
    branch = `${branch}-recovery1`;
    worktree = `${worktree}-recovery1`;
    result = await execute("git", ["-C", repoRoot, "worktree", "add", "-b", branch, worktree, baseCommit], {
      cwd: repoRoot, env: healerEnvironment(options.env),
    });
  }
  if (!result || result.status !== 0) {
    appendRevision(revisionsFile, {
      fingerprint: incident.fingerprint, revision, status: "worktree_failed",
      branch, observed_at: observedAt,
    });
    return Object.freeze({ status: "worktree_failed", branch, worktree });
  }
  prepareWorktreeDependencies(repoRoot, worktree);
  result = await execute("codex", [
    "exec", "--json", "--model", "gpt-5.6-terra",
    "--sandbox", "workspace-write", "-C", worktree, "-",
  ], {
    cwd: worktree,
    env: healerEnvironment(options.env),
    input: healerPrompt({ ...incident, code_commit: baseCommit }),
    timeoutMs: Number(options.codexTimeoutMs || 45 * 60 * 1000),
  });
  const timedOut = result && (result.errorCode === "ETIMEDOUT" || result.signal === "SIGTERM");
  if (!result || result.status !== 0 || !String(result.stdout || "").includes("thread.started")) {
    appendRevision(revisionsFile, {
      fingerprint: incident.fingerprint, revision, status: timedOut ? "revision_timeout" : "revision_failed",
      branch, observed_at: observedAt,
    });
    return Object.freeze({ status: timedOut ? "revision_timeout" : "revision_failed", branch, worktree });
  }
  let preCommitStatus = await execute("git", ["-C", worktree, "status", "--porcelain"], {
    cwd: worktree, env: healerEnvironment(options.env),
  });
  let candidateRows = preCommitStatus && preCommitStatus.status === 0
    ? cleanWorktreeStatus(repoRoot, worktree, preCommitStatus.stdout) : ["status_failed"];
  if (candidateRows.length > 0) {
    const staged = await execute("git", [
      "-C", worktree, "add", "-A", "--", ".", ":(exclude)apps/life-manager/node_modules",
    ], { cwd: worktree, env: healerEnvironment(options.env) });
    const committed = staged && staged.status === 0
      ? await execute("git", [
        "-C", worktree, "commit", "-m", `fix(connector): heal ${short}`,
      ], { cwd: worktree, env: healerEnvironment(options.env) }) : null;
    const pushed = committed && committed.status === 0
      ? await execute("git", ["-C", worktree, "push", "-u", "origin", branch], {
        cwd: worktree, env: healerEnvironment(options.env),
      }) : null;
    if (!pushed || pushed.status !== 0) {
      appendRevision(revisionsFile, {
        fingerprint: incident.fingerprint, revision, status: "revision_failed",
        branch, observed_at: observedAt,
      });
      return Object.freeze({ status: "revision_failed", branch, worktree });
    }
  }
  const commit = await execute("git", ["-C", worktree, "rev-parse", "HEAD"], {
    cwd: worktree, env: healerEnvironment(options.env),
  });
  const commitId = String(commit && commit.stdout || "").trim();
  const status = await execute("git", ["-C", worktree, "status", "--porcelain"], {
    cwd: worktree, env: healerEnvironment(options.env),
  });
  const secrets = await execute("gitleaks", [
    "git", worktree,
    "--config", path.join(repoRoot, ".gitleaks.toml"),
    "--no-banner", "--redact", "--log-opts", `${baseCommit}..${commitId}`,
  ], { cwd: worktree, env: healerEnvironment(options.env), timeoutMs: 5 * 60 * 1000 });
  const pii = await execute("python3", [
    path.join(repoRoot, "scripts/security/pii_shape_scan.py"),
    "--allowlist", path.join(repoRoot, ".pii-shape-allowlist"),
    worktree,
  ], { cwd: worktree, env: healerEnvironment(options.env), timeoutMs: 5 * 60 * 1000 });
  const remote = await execute("git", ["-C", worktree, "ls-remote", "--heads", "origin", branch], {
    cwd: worktree, env: healerEnvironment(options.env),
  });
  const remoteLine = String(remote && remote.stdout || "").trim();
  const dirtyRows = status && status.status === 0
    ? cleanWorktreeStatus(repoRoot, worktree, status.stdout) : ["status_failed"];
  const verified = commit && commit.status === 0
    && /^[0-9a-f]{40}$/.test(commitId)
    && commitId !== baseCommit
    && dirtyRows.length === 0
    && secrets && secrets.status === 0
    && pii && pii.status === 0
    && remote && remote.status === 0
    && remoteLine === `${commitId}\trefs/heads/${branch}`;
  if (!verified) {
    appendRevision(revisionsFile, {
      fingerprint: incident.fingerprint, revision, status: "revision_failed",
      branch, observed_at: observedAt,
    });
    return Object.freeze({ status: "revision_failed", branch, worktree });
  }
  const row = appendRevision(revisionsFile, {
    fingerprint: incident.fingerprint,
    revision,
    status: "revision_created",
    branch,
    commit: commitId,
    observed_at: observedAt,
  });
  return Object.freeze({ status: row.status, branch, commit: commitId, worktree });
}

module.exports = { runHealerShadow };
