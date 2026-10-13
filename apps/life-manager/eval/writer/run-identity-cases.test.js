"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const CLI = path.join(__dirname, "run-identity-cases.js");
const JOINER_CLI = path.join(__dirname, "join-labels.js");
const METRICS_CLI = path.join(__dirname, "judge-metrics.js");
const REPO_ROOT = path.resolve(__dirname, "../../../../");
const WRITER_ROOT = path.join(REPO_ROOT, "skills/writer-agent");
const VERSION = "writer-edd-a8-v3";
const DATASET_SHA256 = "355729f17728c1ef8638cde71f8deca44a37619854f1be6995efdd11df3c1f39";
const REFERENCE_VERSION = "writer-edd-a8-reference-v1";
const REFERENCE_SOURCE = "synthetic_policy_reference_v1";

function referenceRows() {
  const fixture = path.join(__dirname, "fixtures/a8-category-c-reference-v1.jsonl");
  return fs.readFileSync(fixture, "utf8").trim().split(/\r?\n/u).map((line) => {
    const row = JSON.parse(line);
    return { ...row, reference_rationale: `PRIVATE_RATIONALE_MARKER_${row.case_id}` };
  });
}

function executableOnPath(name) {
  for (const directory of (process.env.PATH || "").split(path.delimiter)) {
    if (!directory) continue;
    const candidate = path.join(directory, name);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return path.resolve(candidate);
    } catch {
      // Keep searching PATH.
    }
  }
  throw new Error(`required test executable is unavailable: ${name}`);
}

function versionOf(executable) {
  const result = spawnSync(executable, ["--version"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  return `${result.stdout || ""}${result.stderr || ""}`.trim().split(/\r?\n/u)[0];
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function makeHarness(references = referenceRows()) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "writer-identity-eval-"));
  const modelRunner = path.join(directory, "fake-model-runner.js");
  const promptsDirectory = path.join(directory, "prompts");
  const contextsDirectory = path.join(directory, "contexts");
  const stateDirectory = path.join(directory, "state");
  const logDirectory = path.join(directory, "logs");
  const envFile = path.join(directory, "empty.env");
  const referencePath = path.join(directory, "reference-labels.jsonl");
  const freezePath = path.join(directory, "freeze.json");
  const agentRunnerConfigPath = path.join(directory, "agent-runner-config.json");
  const splitManifestPath = path.join(directory, "splits.json");
  const codexExecutablePath = path.join(directory, "fake-codex");
  const pythonExecutablePath = process.env.LIFE_MANAGER_PYTHON && fs.existsSync(process.env.LIFE_MANAGER_PYTHON)
    ? path.resolve(process.env.LIFE_MANAGER_PYTHON)
    : process.env.WRITER_BROWSER_PYTHON && fs.existsSync(process.env.WRITER_BROWSER_PYTHON)
      ? path.resolve(process.env.WRITER_BROWSER_PYTHON)
      : executableOnPath("python3");

  fs.writeFileSync(modelRunner, `#!/usr/bin/env node
"use strict";
const fs = require("node:fs");
const path = require("node:path");
if (process.argv.slice(2).join(" ") !== "judge --prompt-file -") process.exit(64);
let prompt = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { prompt += chunk; });
process.stdin.on("end", () => {
  fs.mkdirSync(process.env.CAPTURE_DIR, { recursive: true });
  fs.writeFileSync(path.join(process.env.CAPTURE_DIR, process.env.WRITER_EVAL_CASE_ID + ".txt"), prompt);
  fs.mkdirSync(process.env.CONTEXT_DIR, { recursive: true });
  fs.writeFileSync(path.join(process.env.CONTEXT_DIR, process.env.WRITER_EVAL_CASE_ID + ".json"), JSON.stringify({
    ARTICLE_RUN_DIR: process.env.ARTICLE_RUN_DIR,
    ARTICLE_MODEL_STATE_ROOT: process.env.ARTICLE_MODEL_STATE_ROOT,
    ARTICLE_MODEL_LOG: process.env.ARTICLE_MODEL_LOG,
    ANICCA_USAGE_LEDGER: process.env.ANICCA_USAGE_LEDGER,
    WRITER_SHARED_RUNNER_STATE: process.env.WRITER_SHARED_RUNNER_STATE,
    ARTICLE_CODEX_EVENTS_FILE: process.env.ARTICLE_CODEX_EVENTS_FILE || null,
    ARTICLE_CODEX_LAST_MESSAGE_FILE: process.env.ARTICLE_CODEX_LAST_MESSAGE_FILE || null,
    ARTICLE_CODEX_RESUME_SESSION_ID: process.env.ARTICLE_CODEX_RESUME_SESSION_ID || null,
    ARTICLE_SOL_TRIGGER_RECEIPT: process.env.ARTICLE_SOL_TRIGGER_RECEIPT || null,
    ARTICLE_CODEX_BIN: process.env.ARTICLE_CODEX_BIN || null,
    ARTICLE_CLAUDE_BIN: process.env.ARTICLE_CLAUDE_BIN || null,
    ARTICLE_PROVIDER: process.env.ARTICLE_PROVIDER || null,
    ARTICLE_MODEL_RUNNER: process.env.ARTICLE_MODEL_RUNNER || null,
    ARTICLE_MODEL_ROLE: process.env.ARTICLE_MODEL_ROLE || null,
    AGENT_RUNNER_BIN: process.env.AGENT_RUNNER_BIN || null,
    AGENT_RUNNER_CONFIG: process.env.AGENT_RUNNER_CONFIG || null,
    LIFE_MANAGER_PYTHON: process.env.LIFE_MANAGER_PYTHON || null,
    WRITER_STATE_DIR: process.env.WRITER_STATE_DIR,
    WRITER_LOG_DIR: process.env.WRITER_LOG_DIR,
  }));
  const caseId = process.env.WRITER_EVAL_CASE_ID;
  const output = caseId === "W-C-001"
    ? { verdict: "FAIL", violations: ["B: non-target-only failure"] }
    : caseId === "W-C-002"
      ? { verdict: "FAIL", violations: ["C: private internal spec"] }
      : caseId === "W-C-003"
        ? null
        : { verdict: "PASS", violations: [] };
  process.stdout.write(output ? JSON.stringify(output) + "\\n" : "malformed judge output\\n");
});
`);
  fs.chmodSync(modelRunner, 0o755);
  fs.writeFileSync(codexExecutablePath, "#!/bin/sh\n[ \"$1\" = \"--version\" ] || exit 64\nprintf '%s\\n' 'codex-cli test-1'\n");
  fs.chmodSync(codexExecutablePath, 0o755);
  fs.writeFileSync(envFile, "");
  const referenceBytes = `${references.map((row) => JSON.stringify(row)).join("\n")}\n`;
  fs.writeFileSync(referencePath, referenceBytes);
  const referenceSha256 = crypto.createHash("sha256").update(referenceBytes).digest("hex");

  const runnerConfig = {
    providers: {
      codex: {
        executable: codexExecutablePath,
        executable_fallbacks: [],
        cost_tier: "subscription",
        profiles: {
          acct1: { automation_home: path.join(directory, "codex-home"), auth_file: path.join(directory, "auth.json") },
        },
        account_profile_order: ["acct1"],
      },
    },
    task_classes: {
      "composition-agent": {
        candidates: [{ provider: "codex", model: "gpt-5.6-terra", effort: "medium", profile_alias: "acct1" }],
      },
    },
  };
  fs.writeFileSync(agentRunnerConfigPath, `${JSON.stringify(runnerConfig, null, 2)}\n`);
  fs.writeFileSync(splitManifestPath, `${JSON.stringify({
    schema_version: 1,
    record_type: "writer_eval_splits",
    dataset_version: VERSION,
    dataset_sha256: DATASET_SHA256,
    dev_case_ids: references.map((row) => row.case_id),
  }, null, 2)}\n`);
  const agentRunnerPath = path.join(REPO_ROOT, "runtime/agent-runner/agent_runner.py");
  const artifactPaths = {
    run_identity_cases: CLI,
    join_labels: JOINER_CLI,
    judge_metrics: METRICS_CLI,
    receipt_grader: path.join(__dirname, "receipt-grader.js"),
    identity_gate: path.join(WRITER_ROOT, "scripts/identity-gate.sh"),
    writer_runtime_env: path.join(WRITER_ROOT, "scripts/writer-runtime-env.sh"),
    shared_model_runner: path.join(WRITER_ROOT, "runtime/shared-model-runner.py"),
    model_runner: modelRunner,
    agent_runner: agentRunnerPath,
    agent_runner_config: agentRunnerConfigPath,
    split_manifest: splitManifestPath,
  };
  const freeze = {
    schema_version: 1,
    record_type: "writer_judge_freeze",
    status: "frozen",
    freeze_id: "writer-edd-a9-test-freeze-v1",
    dataset_version: VERSION,
    dataset_sha256: DATASET_SHA256,
    reference_set_version: REFERENCE_VERSION,
    reference_set_sha256: referenceSha256,
    artifact_hashes: Object.fromEntries(Object.entries(artifactPaths)
      .map(([name, filePath]) => [name, sha256File(filePath)])),
    model_runner_path: modelRunner,
    agent_runner_path: agentRunnerPath,
    agent_runner_config_path: agentRunnerConfigPath,
    split_manifest_path: splitManifestPath,
    python_executable_path: pythonExecutablePath,
    python_version: versionOf(pythonExecutablePath),
    codex_executable_path: codexExecutablePath,
    codex_version: "codex-cli test-1",
    task_class: "composition-agent",
    provider: "codex",
    model_id: "gpt-5.6-terra",
    effort: "medium",
    profile_alias: "acct1",
    model_role: "terra",
    node_version: process.version,
  };
  fs.writeFileSync(freezePath, `${JSON.stringify(freeze, null, 2)}\n`);

  const env = {
    ...process.env,
    ARTICLE_ROOT: WRITER_ROOT,
    ARTICLE_SKILL_DIR: WRITER_ROOT,
    LIFE_MANAGER_REPO: REPO_ROOT,
    LIFE_MANAGER_ENV_FILE: envFile,
    WRITER_STATE_DIR: stateDirectory,
    ARTICLE_STATE_DIR: stateDirectory,
    WRITER_LOG_DIR: logDirectory,
    ARTICLE_GATES_LOG: path.join(logDirectory, "article-gates.log"),
    ARTICLE_MODEL_RUNNER: modelRunner,
    CAPTURE_DIR: promptsDirectory,
    CONTEXT_DIR: contextsDirectory,
    ARTICLE_CODEX_EVENTS_FILE: path.join(directory, "must-not-write.events.jsonl"),
    ARTICLE_CODEX_LAST_MESSAGE_FILE: path.join(directory, "must-not-write.last-message.txt"),
    ARTICLE_CODEX_RESUME_SESSION_ID: "previous-session-must-not-resume",
    ARTICLE_SOL_TRIGGER_RECEIPT: path.join(directory, "sol-receipt-must-not-claim.json"),
    ARTICLE_CODEX_BIN: path.join(directory, "must-not-use-codex-binary"),
    ARTICLE_CLAUDE_BIN: path.join(directory, "must-not-use-claude-binary"),
    ARTICLE_MODEL_ROLE: "sol-audit",
    WRITER_SHARED_RUNNER_STATE: path.join(directory, "shared-runner-state-must-not-write"),
    ANICCA_USAGE_LEDGER: path.join(directory, "must-not-use-global-usage-ledger.jsonl"),
  };
  delete env.ARTICLE_RUN_DIR;
  delete env.LIFE_MANAGER_RUN_ID;
  delete env.LIFE_MANAGER_LOOP_ID;
  delete env.LIFE_MANAGER_OCCURRENCE_ID;

  const freezeSha256 = sha256File(freezePath);
  return {
    directory, referencePath, referenceSha256, freezePath, freezeSha256,
    agentRunnerConfigPath, codexExecutablePath, pythonExecutablePath,
    promptsDirectory, contextsDirectory, env,
  };
}

function invoke(harness, extraArgs = []) {
  return spawnSync(process.execPath, [
    CLI,
    "--reference-labels", harness.referencePath,
    "--freeze-manifest", harness.freezePath,
    ...extraArgs,
  ], {
    cwd: REPO_ROOT,
    encoding: "utf8",
    env: harness.env,
  });
}

test("validates a frozen manifest without starting a provider in preflight-only mode", () => {
  const harness = makeHarness();
  const home = path.join(harness.directory, "preflight-home");
  const localBin = path.join(home, ".local/bin");
  fs.mkdirSync(localBin, { recursive: true });
  fs.symlinkSync(harness.codexExecutablePath, path.join(localBin, "codex"));
  fs.symlinkSync(harness.pythonExecutablePath, path.join(localBin, "python3"));
  const config = JSON.parse(fs.readFileSync(harness.agentRunnerConfigPath, "utf8"));
  config.providers.codex.executable = "~/.local/bin/codex";
  fs.writeFileSync(harness.agentRunnerConfigPath, `${JSON.stringify(config, null, 2)}\n`);
  const freeze = JSON.parse(fs.readFileSync(harness.freezePath, "utf8"));
  freeze.codex_executable_path = "~/.local/bin/codex";
  freeze.python_executable_path = "~/.local/bin/python3";
  freeze.artifact_hashes.agent_runner_config = sha256File(harness.agentRunnerConfigPath);
  fs.writeFileSync(harness.freezePath, `${JSON.stringify(freeze, null, 2)}\n`);
  harness.freezeSha256 = sha256File(harness.freezePath);
  harness.env.HOME = home;
  harness.env.ARTICLE_NESTED_SANDBOX = "1";
  try {
    const result = invoke(harness, ["--preflight-only"]);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    const [event] = result.stderr.trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(event.owner_id, "writer-a9-freeze-preflight");
    assert.equal(event.phase, "preflight");
    assert.equal(event.effect, "none");
    assert.equal(event.error_class, null);
    assert.equal(event.readback.freeze_id, "writer-edd-a9-test-freeze-v1");
    assert.equal(event.readback.freeze_sha256, harness.freezeSha256);
    assert.equal(event.readback.judge_verdict, "UNKNOWN");
    assert.equal(event.next_action, "run_frozen_identity_cases");
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("refuses any judge inference when the A9 freeze manifest is absent", () => {
  const harness = makeHarness();
  fs.rmSync(harness.freezePath);
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    assert.equal(JSON.parse(result.stderr.trim()).error_class, "eval_freeze_missing");
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("refuses inference when a frozen evaluator artifact hash has drifted", () => {
  const harness = makeHarness();
  const freeze = JSON.parse(fs.readFileSync(harness.freezePath, "utf8"));
  freeze.artifact_hashes.run_identity_cases = "0".repeat(64);
  fs.writeFileSync(harness.freezePath, `${JSON.stringify(freeze, null, 2)}\n`);
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    assert.equal(JSON.parse(result.stderr.trim()).error_class, "eval_freeze_mismatch");
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("refuses provider fallback even when the drifted config hash is refreshed", () => {
  const harness = makeHarness();
  const freeze = JSON.parse(fs.readFileSync(harness.freezePath, "utf8"));
  const config = JSON.parse(fs.readFileSync(freeze.agent_runner_config_path, "utf8"));
  config.task_classes["composition-agent"].candidates.push({
    provider: "claude-direct",
    model: "claude-sonnet-5",
  });
  fs.writeFileSync(freeze.agent_runner_config_path, `${JSON.stringify(config, null, 2)}\n`);
  freeze.artifact_hashes.agent_runner_config = sha256File(freeze.agent_runner_config_path);
  fs.writeFileSync(harness.freezePath, `${JSON.stringify(freeze, null, 2)}\n`);
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    assert.equal(JSON.parse(result.stderr.trim()).error_class, "eval_freeze_mismatch");
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("refuses an unrecorded Codex runtime version before invoking the judge", () => {
  const harness = makeHarness();
  const freeze = JSON.parse(fs.readFileSync(harness.freezePath, "utf8"));
  freeze.codex_version = "codex-cli changed";
  fs.writeFileSync(harness.freezePath, `${JSON.stringify(freeze, null, 2)}\n`);
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    assert.equal(JSON.parse(result.stderr.trim()).error_class, "eval_freeze_mismatch");
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("refuses to call the judge unless synthetic PASS and FAIL references each reach 20", () => {
  const references = referenceRows();
  references[0] = { ...references[0], reference_label: "FAIL" };
  const harness = makeHarness(references);
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    assert.equal(JSON.parse(result.stderr.trim()).error_class, "insufficient_reference_labels");
    assert.doesNotMatch(result.stderr, /PRIVATE_RATIONALE_MARKER/u);
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("refuses nested sandbox execution before creating any judge prompt", () => {
  const harness = makeHarness();
  harness.env.ARTICLE_NESTED_SANDBOX = "1";
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    const event = JSON.parse(result.stderr.trim());
    assert.equal(event.error_class, "nested_sandbox_execution");
    assert.equal(event.effect, "none");
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("preserves inherited broker refusal when dotenv blanks the broker marker", () => {
  const harness = makeHarness();
  harness.env.ARTICLE_JUDGE_BROKER_SERVER = "1";
  fs.writeFileSync(harness.env.LIFE_MANAGER_ENV_FILE, "ARTICLE_JUDGE_BROKER_SERVER=\n");
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    const event = JSON.parse(result.stderr.trim());
    assert.equal(event.error_class, "nested_sandbox_execution");
    assert.equal(event.effect, "none");
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("refuses a broker marker loaded from dotenv before invoking the judge", () => {
  const harness = makeHarness();
  delete harness.env.ARTICLE_JUDGE_BROKER_SERVER;
  delete harness.env.ARTICLE_NESTED_SANDBOX;
  fs.writeFileSync(harness.env.LIFE_MANAGER_ENV_FILE, "ARTICLE_JUDGE_BROKER_SERVER=1\n");
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    const event = JSON.parse(result.stderr.trim());
    assert.equal(event.error_class, "nested_sandbox_execution");
    assert.equal(event.effect, "none");
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("runs isolated cases from the synthetic reference set and emits predictions without labels", () => {
  const harness = makeHarness();
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 0, result.stderr);
    const predictions = result.stdout.trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(predictions.length, 40);
    assert.deepEqual(predictions.slice(0, 4), [
      { case_id: "W-C-001", dataset_version: VERSION, dataset_sha256: DATASET_SHA256, reference_set_version: REFERENCE_VERSION, reference_set_sha256: harness.referenceSha256, freeze_id: "writer-edd-a9-test-freeze-v1", freeze_sha256: harness.freezeSha256, provider: "codex", model_id: "gpt-5.6-terra", effort: "medium", judge_verdict: "UNKNOWN" },
      { case_id: "W-C-002", dataset_version: VERSION, dataset_sha256: DATASET_SHA256, reference_set_version: REFERENCE_VERSION, reference_set_sha256: harness.referenceSha256, freeze_id: "writer-edd-a9-test-freeze-v1", freeze_sha256: harness.freezeSha256, provider: "codex", model_id: "gpt-5.6-terra", effort: "medium", judge_verdict: "FAIL" },
      { case_id: "W-C-003", dataset_version: VERSION, dataset_sha256: DATASET_SHA256, reference_set_version: REFERENCE_VERSION, reference_set_sha256: harness.referenceSha256, freeze_id: "writer-edd-a9-test-freeze-v1", freeze_sha256: harness.freezeSha256, provider: "codex", model_id: "gpt-5.6-terra", effort: "medium", judge_verdict: "UNKNOWN" },
      { case_id: "W-C-004", dataset_version: VERSION, dataset_sha256: DATASET_SHA256, reference_set_version: REFERENCE_VERSION, reference_set_sha256: harness.referenceSha256, freeze_id: "writer-edd-a9-test-freeze-v1", freeze_sha256: harness.freezeSha256, provider: "codex", model_id: "gpt-5.6-terra", effort: "medium", judge_verdict: "PASS" },
    ]);
    assert.equal(fs.readdirSync(harness.promptsDirectory).length, 40);
    assert.equal(fs.readdirSync(harness.contextsDirectory).length, 40);
    const callContext = JSON.parse(fs.readFileSync(path.join(harness.contextsDirectory, "W-C-002.json"), "utf8"));
    assert.equal(callContext.ARTICLE_MODEL_STATE_ROOT, path.join(callContext.ARTICLE_RUN_DIR, "model-state"));
    assert.equal(callContext.ARTICLE_MODEL_LOG, path.join(callContext.WRITER_LOG_DIR, "model-runner.log"));
    assert.equal(callContext.ANICCA_USAGE_LEDGER, path.join(callContext.ARTICLE_RUN_DIR, "usage-ledger.jsonl"));
    assert.equal(callContext.WRITER_SHARED_RUNNER_STATE, path.join(callContext.ARTICLE_RUN_DIR, "shared-runner-evidence"));
    assert.equal(callContext.ARTICLE_CODEX_EVENTS_FILE, null);
    assert.equal(callContext.ARTICLE_CODEX_LAST_MESSAGE_FILE, null);
    assert.equal(callContext.ARTICLE_CODEX_RESUME_SESSION_ID, null);
    assert.equal(callContext.ARTICLE_SOL_TRIGGER_RECEIPT, null);
    assert.equal(callContext.ARTICLE_CODEX_BIN, null);
    assert.equal(callContext.ARTICLE_CLAUDE_BIN, null);
    assert.equal(callContext.ARTICLE_MODEL_ROLE, "terra");
    assert.equal(callContext.ARTICLE_PROVIDER, "codex");
    assert.equal(callContext.ARTICLE_MODEL_RUNNER, path.join(harness.directory, "fake-model-runner.js"));
    assert.equal(callContext.AGENT_RUNNER_BIN, path.join(REPO_ROOT, "runtime/agent-runner/agent_runner.py"));
    assert.equal(callContext.AGENT_RUNNER_CONFIG, path.join(harness.directory, "agent-runner-config.json"));
    assert.equal(callContext.WRITER_STATE_DIR, path.join(callContext.ARTICLE_RUN_DIR, "state"));
    assert.equal(callContext.WRITER_LOG_DIR, path.join(callContext.ARTICLE_RUN_DIR, "logs"));

    const targetPrompt = fs.readFileSync(path.join(harness.promptsDirectory, "W-C-002.txt"), "utf8");
    assert.match(targetPrompt, /identity-review-v7\.md/u);
    assert.doesNotMatch(targetPrompt, /PRIVATE_RATIONALE_MARKER|reference_label|reference_rationale/u);
    assert.doesNotMatch(result.stdout, /PRIVATE_RATIONALE_MARKER|reference_label|reference_rationale/u);

    const predictionsPath = path.join(harness.directory, "judge-predictions.jsonl");
    fs.writeFileSync(predictionsPath, result.stdout);
    const joined = spawnSync(process.execPath, [
      JOINER_CLI,
      "--reference-labels", harness.referencePath,
      "--judge-predictions", predictionsPath,
    ], { encoding: "utf8" });
    assert.equal(joined.status, 0, joined.stderr);
    const joinedRows = joined.stdout.trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(joinedRows.length, 40);
    assert.deepEqual(joinedRows.slice(0, 2), [
      { case_id: "W-C-001", reference_label: "PASS", reference_source: REFERENCE_SOURCE, reference_set_version: REFERENCE_VERSION, reference_set_sha256: harness.referenceSha256, freeze_id: "writer-edd-a9-test-freeze-v1", freeze_sha256: harness.freezeSha256, provider: "codex", model_id: "gpt-5.6-terra", effort: "medium", judge_verdict: "UNKNOWN" },
      { case_id: "W-C-002", reference_label: "FAIL", reference_source: REFERENCE_SOURCE, reference_set_version: REFERENCE_VERSION, reference_set_sha256: harness.referenceSha256, freeze_id: "writer-edd-a9-test-freeze-v1", freeze_sha256: harness.freezeSha256, provider: "codex", model_id: "gpt-5.6-terra", effort: "medium", judge_verdict: "FAIL" },
    ]);
    const metrics = spawnSync(process.execPath, [METRICS_CLI], {
      input: joined.stdout,
      encoding: "utf8",
    });
    assert.equal(metrics.status, 0, metrics.stderr);
    const summary = JSON.parse(metrics.stdout);
    assert.equal(summary.status, "incomplete_predictions");
    assert.equal(summary.scope, "synthetic_reference_agreement");
    assert.equal(summary.freeze_id, "writer-edd-a9-test-freeze-v1");
    assert.equal(summary.freeze_sha256, harness.freezeSha256);
    assert.equal(summary.provider, "codex");
    assert.equal(summary.model_id, "gpt-5.6-terra");
    assert.equal(summary.effort, "medium");
    assert.equal(summary.human_validation, "not_performed");
    assert.deepEqual(summary.rates, {
      reference_tpr: null,
      reference_tnr: null,
      reference_false_pass_rate: null,
      reference_false_fail_rate: null,
    });

    const events = result.stderr.trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(events.length, 40);
    assert.deepEqual(events.filter((event) => event.error_class)
      .map((event) => [event.case_id, event.error_class]), [
      ["W-C-001", "non_target_failure_category"],
      ["W-C-003", "malformed_judge_output"],
    ]);
    assert.ok(events.every((event) => event.run_id && event.owner_id && event.occurrence_id
      && event.phase === "identity_judge" && event.command && "exit_code" in event
      && "effect" in event && "readback" in event && "provider_receipt_id" in event
      && Array.isArray(event.evidence_refs) && "retryable" in event && event.next_action));
    const caseEvent = events.find((event) => event.case_id === "W-C-002");
    assert.equal(caseEvent.readback.reference_set_version, REFERENCE_VERSION);
    assert.equal(caseEvent.readback.reference_set_sha256, harness.referenceSha256);
    assert.equal(caseEvent.readback.freeze_id, "writer-edd-a9-test-freeze-v1");
    assert.equal(caseEvent.readback.freeze_sha256, harness.freezeSha256);
    assert.doesNotMatch(JSON.stringify(caseEvent), /reference_label|reference_rationale/u);
    assert.doesNotMatch(result.stderr, /PRIVATE_RATIONALE_MARKER|reference_label|reference_rationale|identity-review-v7\.md/u);
    assert.equal(fs.existsSync(harness.env.ARTICLE_CODEX_EVENTS_FILE), false);
    assert.equal(fs.existsSync(harness.env.ARTICLE_CODEX_LAST_MESSAGE_FILE), false);
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});
