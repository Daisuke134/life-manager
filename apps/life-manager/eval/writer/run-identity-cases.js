"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { loadDataset, loadReferenceSet } = require("./join-labels.js");

const MIN_PER_CLASS = 20;
const MAX_OUTPUT_BYTES = 1_000_000;
const MAX_FREEZE_BYTES = 65_536;
const SHA256 = /^[a-f0-9]{64}$/u;
const REPO_ROOT = path.resolve(__dirname, "../../../../");
const WRITER_ROOT = path.join(REPO_ROOT, "skills/writer-agent");
const DEFAULT_MODEL_RUNNER = path.join(WRITER_ROOT, "runtime/model-runner.sh");
const FROZEN_ARTIFACT_PATHS = {
  run_identity_cases: __filename,
  join_labels: path.join(__dirname, "join-labels.js"),
  judge_metrics: path.join(__dirname, "judge-metrics.js"),
  receipt_grader: path.join(__dirname, "receipt-grader.js"),
  identity_gate: path.join(WRITER_ROOT, "scripts/identity-gate.sh"),
  writer_runtime_env: path.join(WRITER_ROOT, "scripts/writer-runtime-env.sh"),
  shared_model_runner: path.join(WRITER_ROOT, "runtime/shared-model-runner.py"),
};
const NO_EFFECT_ERRORS = new Set([
  "nested_sandbox_execution",
  "writer_runtime_env_failed",
  "judge_spawn_failed",
  "eval_freeze_missing",
  "eval_freeze_invalid",
  "eval_freeze_mismatch",
]);
const ISOLATED_GATE_COMMAND = [
  'ARTICLE_ROOT="$8" ARTICLE_SKILL_DIR="$8" LIFE_MANAGER_REPO="$9"; export ARTICLE_ROOT ARTICLE_SKILL_DIR LIFE_MANAGER_REPO',
  'if [ "${ARTICLE_NESTED_SANDBOX:-}" = "1" ] || [ "${ARTICLE_JUDGE_BROKER_SERVER:-}" = "1" ]; then exit 86; fi',
  'source "$ARTICLE_ROOT/scripts/writer-runtime-env.sh" >/dev/null 2>&1 || exit 70',
  'if [ "${ARTICLE_NESTED_SANDBOX:-}" = "1" ] || [ "${ARTICLE_JUDGE_BROKER_SERVER:-}" = "1" ]; then exit 86; fi',
  'export ARTICLE_ROOT="$8" ARTICLE_SKILL_DIR="$8" LIFE_MANAGER_REPO="$9"',
  'export ARTICLE_PROVIDER="${18}" ARTICLE_MODEL_RUNNER="${13}" AGENT_RUNNER_BIN="${14}" AGENT_RUNNER_CONFIG="${15}" ARTICLE_MODEL_ROLE="${16}" LIFE_MANAGER_PYTHON="${17}" WRITER_BROWSER_PYTHON="${17}"',
  'export ARTICLE_RUN_DIR="$2" WRITER_STATE_DIR="$3" ARTICLE_STATE_DIR="$3" STATE_DIR="$3" WRITER_LOG_DIR="$4"',
  'export ARTICLE_GATES_LOG="$4/article-gates.log" ARTICLE_MODEL_ROOT="$8" ARTICLE_MODEL_STATE_ROOT="$5" ARTICLE_MODEL_LOG="$6" ARTICLE_PROVIDER_HEALTH="$5/provider-health.json"',
  'export WRITER_SHARED_RUNNER_STATE="$7" ARTICLE_MODEL_ROLE=terra',
  'export ANICCA_USAGE_LEDGER="${12}"',
  'export LIFE_MANAGER_RUN_ID="${10}" LIFE_MANAGER_LOOP_ID=writer-a8-identity-eval LIFE_MANAGER_OCCURRENCE_ID="${10}-${11}" WRITER_EVAL_RUN_ID="${10}" WRITER_EVAL_CASE_ID="${11}"',
  'unset ARTICLE_CODEX_EVENTS_FILE ARTICLE_CODEX_LAST_MESSAGE_FILE ARTICLE_CODEX_RESUME_SESSION_ID ARTICLE_SOL_TRIGGER_RECEIPT ARTICLE_CODEX_BIN ARTICLE_CLAUDE_BIN',
  'export LIFE_MANAGER_ENV_FILE=/dev/null',
  'exec "$8/scripts/identity-gate.sh" "$1" --lang en',
].join("; ");

function rejectInput(errorClass) {
  const error = new Error("Writer identity evaluation rejected input");
  error.code = errorClass;
  throw error;
}

function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const keys = [...expected].sort();
  return actual.length === keys.length && actual.every((key, index) => key === keys[index]);
}

function resolveManifestPath(value) {
  if (typeof value !== "string" || !value.trim()) rejectInput("eval_freeze_invalid");
  if (value.startsWith("~/")) return path.resolve(os.homedir(), value.slice(2));
  return path.isAbsolute(value) ? path.resolve(value) : path.resolve(REPO_ROOT, value);
}

function sha256File(filePath) {
  try {
    return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
  } catch {
    rejectInput("eval_freeze_invalid");
  }
}

function executablePath(value) {
  if (typeof value !== "string" || !value.trim()) rejectInput("eval_freeze_invalid");
  const expanded = value.startsWith("~/") ? path.join(os.homedir(), value.slice(2)) : value;
  if (path.isAbsolute(expanded) || expanded.includes(path.sep)) return path.resolve(expanded);
  for (const directory of (process.env.PATH || "").split(path.delimiter)) {
    if (!directory) continue;
    const candidate = path.join(directory, expanded);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return path.resolve(candidate);
    } catch {
      // Search PATH without exposing candidate paths in the error record.
    }
  }
  rejectInput("eval_freeze_invalid");
}

function executableVersion(executable) {
  const result = spawnSync(executable, ["--version"], {
    encoding: "utf8",
    timeout: 5000,
    maxBuffer: 4096,
  });
  if (result.error || result.status !== 0) rejectInput("eval_freeze_mismatch");
  const version = `${result.stdout || ""}${result.stderr || ""}`.trim().split(/\r?\n/u)[0];
  if (!version) rejectInput("eval_freeze_mismatch");
  return version;
}

function loadFreezeManifest(filePath, dataset, referenceSet) {
  let bytes;
  try {
    bytes = fs.readFileSync(filePath);
  } catch {
    rejectInput("eval_freeze_missing");
  }
  if (bytes.length > MAX_FREEZE_BYTES) rejectInput("eval_freeze_invalid");

  let freeze;
  try {
    freeze = JSON.parse(bytes.toString("utf8"));
  } catch {
    rejectInput("eval_freeze_invalid");
  }
  const keys = [
    "schema_version", "record_type", "status", "freeze_id",
    "dataset_version", "dataset_sha256", "reference_set_version", "reference_set_sha256",
    "artifact_hashes", "model_runner_path", "agent_runner_path", "agent_runner_config_path",
    "split_manifest_path", "python_executable_path", "python_version", "codex_executable_path",
    "codex_version", "task_class", "provider", "model_id", "effort", "profile_alias",
    "model_role", "node_version",
  ];
  if (!exactKeys(freeze, keys)) rejectInput("eval_freeze_invalid");
  if (freeze.schema_version !== 1 || freeze.record_type !== "writer_judge_freeze") {
    rejectInput("eval_freeze_invalid");
  }
  if (freeze.status !== "frozen" || typeof freeze.freeze_id !== "string" || !freeze.freeze_id.trim()) {
    rejectInput("eval_freeze_missing");
  }
  if (freeze.dataset_version !== dataset.version || freeze.dataset_sha256 !== dataset.sha256
    || freeze.reference_set_version !== referenceSet.version || freeze.reference_set_sha256 !== referenceSet.sha256
    || freeze.node_version !== process.version) rejectInput("eval_freeze_mismatch");
  if (freeze.task_class !== "composition-agent" || freeze.provider !== "codex"
    || freeze.model_id !== "gpt-5.6-terra" || freeze.effort !== "medium"
    || freeze.profile_alias !== "acct1" || freeze.model_role !== "terra") rejectInput("eval_freeze_invalid");

  const modelRunnerPath = resolveManifestPath(freeze.model_runner_path);
  const configuredModelRunner = path.resolve(process.env.ARTICLE_MODEL_RUNNER || DEFAULT_MODEL_RUNNER);
  const agentRunnerPath = resolveManifestPath(freeze.agent_runner_path);
  const agentRunnerConfigPath = resolveManifestPath(freeze.agent_runner_config_path);
  const splitManifestPath = resolveManifestPath(freeze.split_manifest_path);
  const pythonExecutablePath = resolveManifestPath(freeze.python_executable_path);
  if (modelRunnerPath !== configuredModelRunner) rejectInput("eval_freeze_mismatch");
  for (const executable of [modelRunnerPath, pythonExecutablePath]) {
    try {
      fs.accessSync(executable, fs.constants.X_OK);
    } catch {
      rejectInput("eval_freeze_mismatch");
    }
  }
  try {
    fs.accessSync(agentRunnerPath, fs.constants.R_OK);
  } catch {
    rejectInput("eval_freeze_mismatch");
  }

  const artifactPaths = {
    ...FROZEN_ARTIFACT_PATHS,
    model_runner: modelRunnerPath,
    agent_runner: agentRunnerPath,
    agent_runner_config: agentRunnerConfigPath,
    split_manifest: splitManifestPath,
  };
  if (!exactKeys(freeze.artifact_hashes, Object.keys(artifactPaths))) rejectInput("eval_freeze_invalid");
  for (const [name, artifactPath] of Object.entries(artifactPaths)) {
    const expected = freeze.artifact_hashes[name];
    if (typeof expected !== "string" || !SHA256.test(expected) || sha256File(artifactPath) !== expected) {
      rejectInput("eval_freeze_mismatch");
    }
  }

  let runnerConfig;
  try {
    runnerConfig = JSON.parse(fs.readFileSync(agentRunnerConfigPath, "utf8"));
  } catch {
    rejectInput("eval_freeze_invalid");
  }
  const task = runnerConfig?.task_classes?.[freeze.task_class];
  const candidates = task?.candidates;
  const candidate = Array.isArray(candidates) && candidates.length === 1 ? candidates[0] : null;
  const codex = runnerConfig?.providers?.codex;
  const profile = codex?.profiles?.[freeze.profile_alias];
  if (!candidate || candidate.provider !== freeze.provider || candidate.model !== freeze.model_id
    || candidate.effort !== freeze.effort || candidate.profile_alias !== freeze.profile_alias
    || !Array.isArray(codex.account_profile_order) || codex.account_profile_order.length !== 1
    || codex.account_profile_order[0] !== freeze.profile_alias
    || !Array.isArray(codex.executable_fallbacks) || codex.executable_fallbacks.length !== 0
    || !profile?.automation_home || !profile?.auth_file || codex.cost_tier !== "subscription") {
    rejectInput("eval_freeze_mismatch");
  }

  const codexExecutablePath = executablePath(codex.executable);
  if (codexExecutablePath !== resolveManifestPath(freeze.codex_executable_path)
    || executableVersion(codexExecutablePath) !== freeze.codex_version
    || executableVersion(pythonExecutablePath) !== freeze.python_version) rejectInput("eval_freeze_mismatch");

  return {
    ...freeze,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    resolved: {
      model_runner_path: modelRunnerPath,
      agent_runner_path: agentRunnerPath,
      agent_runner_config_path: agentRunnerConfigPath,
      split_manifest_path: splitManifestPath,
      python_executable_path: pythonExecutablePath,
      codex_executable_path: codexExecutablePath,
    },
  };
}

function parseArgs(args) {
  const preflightOnly = args.length === 5 && args[4] === "--preflight-only";
  if ((!preflightOnly && args.length !== 4) || args[0] !== "--reference-labels" || !args[1]
    || args[2] !== "--freeze-manifest" || !args[3]) {
    rejectInput("invalid_arguments");
  }
  return { referenceLabelsPath: args[1], freezeManifestPath: args[3], preflightOnly };
}

function targetVerdict(result) {
  if (result.error) return { verdict: "UNKNOWN", errorClass: "judge_spawn_failed", retryable: true };
  if (result.status === 86) {
    return { verdict: "UNKNOWN", errorClass: "nested_sandbox_execution", retryable: false };
  }
  if (result.status === 70) {
    return { verdict: "UNKNOWN", errorClass: "writer_runtime_env_failed", retryable: false };
  }
  const lines = String(result.stdout || "").split(/\r?\n/u).filter((line) => line.trim() !== "");
  let output;
  try {
    output = JSON.parse(lines.at(-1));
  } catch {
    return { verdict: "UNKNOWN", errorClass: "malformed_judge_output", retryable: true };
  }
  if (!output || !Array.isArray(output.violations)
    || !output.violations.every((violation) => typeof violation === "string")) {
    return { verdict: "UNKNOWN", errorClass: "malformed_judge_output", retryable: true };
  }
  if (result.status === 0 && output.verdict === "PASS" && output.violations.length === 0) {
    return { verdict: "PASS", errorClass: null, retryable: false };
  }
  if (result.status === 1 && output.verdict === "FAIL") {
    if (output.violations.some((violation) => /^C:\s/u.test(violation))) {
      return { verdict: "FAIL", errorClass: null, retryable: false };
    }
    return { verdict: "UNKNOWN", errorClass: "non_target_failure_category", retryable: false };
  }
  return { verdict: "UNKNOWN", errorClass: "unexpected_gate_result", retryable: true };
}

function eventRecord({ runId, caseId, exitCode, verdict, errorClass, retryable, referenceSet = null, freeze = null,
  ownerId = "writer-a8-identity-eval", nextActionOverride = null, preflightOnly = false }) {
  const preflight = caseId === null || NO_EFFECT_ERRORS.has(errorClass);
  return {
    run_id: runId,
    owner_id: ownerId,
    occurrence_id: caseId === null ? `${runId}:preflight` : `${runId}:${caseId}`,
    case_id: caseId,
    release_sha: process.env.LIFE_MANAGER_RELEASE_SHA || null,
    loaded_argv: caseId === null
      ? ["node", "run-identity-cases.js", "--reference-labels", "<provided>", "--freeze-manifest", "<provided>",
        ...(preflightOnly ? ["--preflight-only"] : [])]
      : ["bash", "-c", "<isolated-gate-wrapper>", "<isolated>/article.md"],
    loaded_env: {
      ARTICLE_ROOT: "skills/writer-agent",
      ARTICLE_MODEL_RUNNER: process.env.ARTICLE_MODEL_RUNNER || "skills/writer-agent/runtime/model-runner.sh",
      WRITER_EVAL_FREEZE_ID: freeze?.freeze_id || null,
      ARTICLE_MODEL_STATE_ROOT: "<isolated-temp>",
      ARTICLE_MODEL_LOG: "<isolated-temp>",
      ARTICLE_PROVIDER_HEALTH: "<isolated-temp>",
      WRITER_SHARED_RUNNER_STATE: "<isolated-temp>",
      ANICCA_USAGE_LEDGER: "<isolated-temp>",
      ARTICLE_MODEL_ROLE: "terra",
      ARTICLE_CODEX_EVENTS_FILE: "cleared",
      ARTICLE_CODEX_LAST_MESSAGE_FILE: "cleared",
      ARTICLE_CODEX_RESUME_SESSION_ID: "cleared",
      ARTICLE_SOL_TRIGGER_RECEIPT: "cleared",
      ARTICLE_CODEX_BIN: "cleared",
      ARTICLE_CLAUDE_BIN: "cleared",
      LIFE_MANAGER_ENV_FILE: process.env.LIFE_MANAGER_ENV_FILE || "<default>",
      WRITER_STATE_DIR: "<isolated-temp>",
      WRITER_LOG_DIR: "<isolated-temp>",
    },
    phase: preflight ? "preflight" : "identity_judge",
    command: caseId === null ? "run-identity-cases.js" : "isolated-gate-wrapper",
    exit_code: exitCode,
    effect: preflight ? "none" : "judge_model_inference",
    readback: {
      judge_verdict: verdict,
      reference_set_version: referenceSet?.version || null,
      reference_set_sha256: referenceSet?.sha256 || null,
      freeze_id: freeze?.freeze_id || null,
      freeze_sha256: freeze?.sha256 || null,
      provider: freeze?.provider || null,
      model_id: freeze?.model_id || null,
      effort: freeze?.effort || null,
    },
    provider_receipt_id: null,
    evidence_refs: [
      "docs/evals/writer-edd-a8-label-set.md",
      "apps/life-manager/eval/writer/fixtures/a8-category-c-reference-v1.jsonl",
      ...(freeze ? [`freeze_id:${freeze.freeze_id}`, `freeze_sha256:${freeze.sha256}`] : []),
      ...(caseId ? [`case_id:${caseId}`] : []),
    ],
    error_class: errorClass,
    retryable,
    next_action: nextActionOverride || nextAction(errorClass),
  };
}

function emitEvent(event) {
  process.stderr.write(`${JSON.stringify(event)}\n`);
}

function nextAction(errorClass) {
  if (!errorClass) return "join_predictions_to_synthetic_reference";
  if (errorClass === "insufficient_reference_labels") return "restore_at_least_20_synthetic_reference_pass_and_fail_cases";
  if (errorClass === "eval_freeze_missing") return "create_and_record_A9_freeze_before_provider_start";
  if (errorClass === "eval_freeze_invalid") return "repair_A9_freeze_manifest_schema_before_provider_start";
  if (errorClass === "eval_freeze_mismatch") return "reconcile_frozen_hashes_and_runtime_identity_before_provider_start";
  if (errorClass === "invalid_arguments") return "invoke_with_synthetic_reference_jsonl_path";
  if (errorClass === "invalid_reference_labels") return "check_reference_version_hash_source_and_case_ids";
  if (errorClass === "unknown_case") return "reconcile_case_ids_with_canonical_dataset";
  if (errorClass === "nested_sandbox_execution") return "run_from_owner_controlled_outer_shell_not_nested_agent";
  if (errorClass === "writer_runtime_env_failed") return "repair_writer_runtime_environment_before_retry";
  if (errorClass === "non_target_failure_category") return "keep_prediction_unknown_and_review_target_category";
  if (errorClass === "judge_spawn_failed") return "verify_model_runner_availability_before_retry";
  return "inspect_identity_gate_and_model_runner_diagnostics_before_retry";
}

function invokeIdentityGate({ caseData, caseDir, runId, dataset, referenceSet, freeze }) {
  fs.mkdirSync(caseDir, { recursive: true });
  const articlePath = path.join(caseDir, "article.md");
  fs.writeFileSync(articlePath, `${caseData.excerpt}\n`);
  const stateDir = path.join(caseDir, "state");
  const logDir = path.join(caseDir, "logs");
  const modelStateDir = path.join(caseDir, "model-state");
  const modelLogPath = path.join(logDir, "model-runner.log");
  const sharedRunnerStateDir = path.join(caseDir, "shared-runner-evidence");
  const usageLedgerPath = path.join(caseDir, "usage-ledger.jsonl");
  const env = {
    ...process.env,
    ARTICLE_ROOT: WRITER_ROOT,
    ARTICLE_SKILL_DIR: WRITER_ROOT,
    LIFE_MANAGER_REPO: REPO_ROOT,
    WRITER_STATE_DIR: stateDir,
    ARTICLE_STATE_DIR: stateDir,
    WRITER_LOG_DIR: logDir,
    ARTICLE_GATES_LOG: path.join(logDir, "article-gates.log"),
    ARTICLE_MODEL_STATE_ROOT: modelStateDir,
    ARTICLE_MODEL_LOG: modelLogPath,
    ARTICLE_PROVIDER_HEALTH: path.join(modelStateDir, "provider-health.json"),
    WRITER_SHARED_RUNNER_STATE: sharedRunnerStateDir,
    ANICCA_USAGE_LEDGER: usageLedgerPath,
    ARTICLE_RUN_DIR: caseDir,
    LIFE_MANAGER_RUN_ID: runId,
    LIFE_MANAGER_LOOP_ID: "writer-a8-identity-eval",
    LIFE_MANAGER_OCCURRENCE_ID: `${runId}-${caseData.case_id}`,
    WRITER_EVAL_RUN_ID: runId,
    WRITER_EVAL_CASE_ID: caseData.case_id,
    WRITER_EVAL_FREEZE_ID: freeze.freeze_id,
    WRITER_EVAL_FREEZE_SHA256: freeze.sha256,
  };
  const result = spawnSync("bash", [
    "-c", ISOLATED_GATE_COMMAND, "writer-a8-identity-eval", articlePath,
    caseDir, stateDir, logDir, modelStateDir, modelLogPath, sharedRunnerStateDir,
    WRITER_ROOT, REPO_ROOT, runId, caseData.case_id,
    usageLedgerPath,
    freeze.resolved.model_runner_path,
    freeze.resolved.agent_runner_path,
    freeze.resolved.agent_runner_config_path,
    freeze.model_role,
    freeze.resolved.python_executable_path,
    freeze.provider,
  ], {
    encoding: "utf8",
    env,
    maxBuffer: MAX_OUTPUT_BYTES,
  });
  const classified = targetVerdict(result);
  emitEvent(eventRecord({
    runId,
    caseId: caseData.case_id,
    exitCode: result.status ?? null,
    verdict: classified.verdict,
    errorClass: classified.errorClass,
    retryable: classified.retryable,
    referenceSet,
    freeze,
  }));
  if (NO_EFFECT_ERRORS.has(classified.errorClass)) {
    const error = new Error("Writer evaluation could not establish its isolated runtime context");
    error.code = classified.errorClass;
    error.eventEmitted = true;
    throw error;
  }
  return {
    case_id: caseData.case_id,
    dataset_version: dataset.version,
    dataset_sha256: dataset.sha256,
    reference_set_version: referenceSet.version,
    reference_set_sha256: referenceSet.sha256,
    freeze_id: freeze.freeze_id,
    freeze_sha256: freeze.sha256,
    provider: freeze.provider,
    model_id: freeze.model_id,
    effort: freeze.effort,
    judge_verdict: classified.verdict,
  };
}

function main() {
  const runId = `writer-a8-${crypto.randomUUID()}`;
  let tempDir;
  let referenceSet = null;
  let freeze = null;
  try {
    const { referenceLabelsPath, freezeManifestPath, preflightOnly } = parseArgs(process.argv.slice(2));
    const dataset = loadDataset();
    referenceSet = loadReferenceSet(referenceLabelsPath, dataset);
    const counts = { PASS: 0, FAIL: 0 };
    for (const row of referenceSet.rows) {
      if (row.reference_label === "PASS" || row.reference_label === "FAIL") counts[row.reference_label] += 1;
    }
    if (counts.PASS < MIN_PER_CLASS || counts.FAIL < MIN_PER_CLASS) {
      rejectInput("insufficient_reference_labels");
    }
    if (!preflightOnly && (process.env.ARTICLE_NESTED_SANDBOX === "1"
      || process.env.ARTICLE_JUDGE_BROKER_SERVER === "1")) {
      rejectInput("nested_sandbox_execution");
    }
    freeze = loadFreezeManifest(freezeManifestPath, dataset, referenceSet);
    if (preflightOnly) {
      emitEvent(eventRecord({
        runId: `writer-a9-preflight-${crypto.randomUUID()}`,
        caseId: null,
        exitCode: 0,
        verdict: "UNKNOWN",
        errorClass: null,
        retryable: false,
        referenceSet,
        freeze,
        ownerId: "writer-a9-freeze-preflight",
        nextActionOverride: "run_frozen_identity_cases",
        preflightOnly: true,
      }));
      return;
    }

    const casesById = new Map(dataset.cases.map((item) => [item.case_id, item]));
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "writer-a8-identity-"));
    for (const row of referenceSet.rows) {
      const caseData = casesById.get(row.case_id);
      if (!caseData) rejectInput("unknown_case");
      const prediction = invokeIdentityGate({
        caseData,
        caseDir: path.join(tempDir, caseData.case_id),
        runId,
        dataset,
        referenceSet,
        freeze,
      });
      process.stdout.write(`${JSON.stringify(prediction)}\n`);
    }
  } catch (error) {
    if (!error.eventEmitted) {
      emitEvent(eventRecord({
        runId,
        caseId: null,
        exitCode: 2,
        verdict: "UNKNOWN",
        errorClass: error.code || "invalid_reference_labels",
        retryable: false,
        referenceSet,
        freeze,
      }));
    }
    process.exitCode = 2;
  } finally {
    if (tempDir) fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

if (require.main === module) main();
