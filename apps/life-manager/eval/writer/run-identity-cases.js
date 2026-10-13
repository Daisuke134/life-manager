"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { joinLabels, loadDataset, readJsonl } = require("./join-labels.js");

const MIN_PER_CLASS = 20;
const MAX_OUTPUT_BYTES = 1_000_000;
const REPO_ROOT = path.resolve(__dirname, "../../../../");
const WRITER_ROOT = path.join(REPO_ROOT, "skills/writer-agent");
const NO_EFFECT_ERRORS = new Set([
  "nested_sandbox_execution",
  "writer_runtime_env_failed",
  "judge_spawn_failed",
]);
const ISOLATED_GATE_COMMAND = [
  'ARTICLE_ROOT="$8" ARTICLE_SKILL_DIR="$8" LIFE_MANAGER_REPO="$9"; export ARTICLE_ROOT ARTICLE_SKILL_DIR LIFE_MANAGER_REPO',
  'if [ "${ARTICLE_NESTED_SANDBOX:-}" = "1" ] || [ "${ARTICLE_JUDGE_BROKER_SERVER:-}" = "1" ]; then exit 86; fi',
  'source "$ARTICLE_ROOT/scripts/writer-runtime-env.sh" >/dev/null 2>&1 || exit 70',
  'if [ "${ARTICLE_NESTED_SANDBOX:-}" = "1" ] || [ "${ARTICLE_JUDGE_BROKER_SERVER:-}" = "1" ]; then exit 86; fi',
  'export ARTICLE_ROOT="$8" ARTICLE_SKILL_DIR="$8" LIFE_MANAGER_REPO="$9"',
  'export ARTICLE_RUN_DIR="$2" WRITER_STATE_DIR="$3" ARTICLE_STATE_DIR="$3" STATE_DIR="$3" WRITER_LOG_DIR="$4"',
  'export ARTICLE_GATES_LOG="$4/article-gates.log" ARTICLE_MODEL_ROOT="$8" ARTICLE_MODEL_STATE_ROOT="$5" ARTICLE_MODEL_LOG="$6" ARTICLE_PROVIDER_HEALTH="$5/provider-health.json"',
  'export WRITER_SHARED_RUNNER_STATE="$7" ARTICLE_MODEL_ROLE=terra',
  'export ANICCA_USAGE_LEDGER="${12}"',
  'export LIFE_MANAGER_RUN_ID="${10}" LIFE_MANAGER_LOOP_ID=writer-a8-identity-eval LIFE_MANAGER_OCCURRENCE_ID="${10}-${11}" WRITER_EVAL_RUN_ID="${10}" WRITER_EVAL_CASE_ID="${11}"',
  'unset ARTICLE_CODEX_EVENTS_FILE ARTICLE_CODEX_LAST_MESSAGE_FILE ARTICLE_CODEX_RESUME_SESSION_ID ARTICLE_SOL_TRIGGER_RECEIPT',
  'export LIFE_MANAGER_ENV_FILE=/dev/null',
  'exec "$8/scripts/identity-gate.sh" "$1" --lang en',
].join("; ");

function rejectInput(errorClass) {
  const error = new Error("Writer identity evaluation rejected input");
  error.code = errorClass;
  throw error;
}

function parseArgs(args) {
  if (args.length !== 2 || args[0] !== "--human-labels" || !args[1]) {
    rejectInput("invalid_arguments");
  }
  return { humanLabelsPath: args[1] };
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

function eventRecord({ runId, caseId, exitCode, verdict, errorClass, retryable }) {
  const preflight = caseId === null || NO_EFFECT_ERRORS.has(errorClass);
  return {
    run_id: runId,
    owner_id: "writer-a8-identity-eval",
    occurrence_id: caseId === null ? `${runId}:preflight` : `${runId}:${caseId}`,
    case_id: caseId,
    release_sha: process.env.LIFE_MANAGER_RELEASE_SHA || null,
    loaded_argv: caseId === null
      ? ["node", "run-identity-cases.js", "--human-labels", "<provided>"]
      : ["bash", "-c", "<isolated-gate-wrapper>", "<isolated>/article.md"],
    loaded_env: {
      ARTICLE_ROOT: "skills/writer-agent",
      ARTICLE_MODEL_RUNNER: process.env.ARTICLE_MODEL_RUNNER || "skills/writer-agent/runtime/model-runner.sh",
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
      LIFE_MANAGER_ENV_FILE: process.env.LIFE_MANAGER_ENV_FILE || "<default>",
      WRITER_STATE_DIR: "<isolated-temp>",
      WRITER_LOG_DIR: "<isolated-temp>",
    },
    phase: preflight ? "preflight" : "identity_judge",
    command: caseId === null ? "run-identity-cases.js" : "isolated-gate-wrapper",
    exit_code: exitCode,
    effect: preflight ? "none" : "judge_model_inference",
    readback: { judge_verdict: verdict },
    provider_receipt_id: null,
    evidence_refs: [
      "docs/evals/writer-edd-a8-label-set.md",
      ...(caseId ? [`case_id:${caseId}`] : []),
    ],
    error_class: errorClass,
    retryable,
    next_action: nextAction(errorClass),
  };
}

function emitEvent(event) {
  process.stderr.write(`${JSON.stringify(event)}\n`);
}

function nextAction(errorClass) {
  if (!errorClass) return "join_predictions_to_human_labels";
  if (errorClass === "insufficient_labels") return "collect_at_least_20_human_pass_and_20_human_fail_labels";
  if (errorClass === "invalid_arguments") return "invoke_with_human_labels_jsonl_path";
  if (errorClass === "invalid_human_labels") return "reexport_and_check_canonical_dataset_version_and_hash";
  if (errorClass === "unknown_case") return "reconcile_case_ids_with_canonical_dataset";
  if (errorClass === "nested_sandbox_execution") return "run_from_owner_controlled_outer_shell_not_nested_agent";
  if (errorClass === "writer_runtime_env_failed") return "repair_writer_runtime_environment_before_retry";
  if (errorClass === "non_target_failure_category") return "keep_prediction_unknown_and_review_target_category";
  if (errorClass === "judge_spawn_failed") return "verify_model_runner_availability_before_retry";
  return "inspect_identity_gate_and_model_runner_diagnostics_before_retry";
}

function invokeIdentityGate({ caseData, caseDir, runId, dataset }) {
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
  };
  const result = spawnSync("bash", [
    "-c", ISOLATED_GATE_COMMAND, "writer-a8-identity-eval", articlePath,
    caseDir, stateDir, logDir, modelStateDir, modelLogPath, sharedRunnerStateDir,
    WRITER_ROOT, REPO_ROOT, runId, caseData.case_id,
    usageLedgerPath,
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
    judge_verdict: classified.verdict,
  };
}

function main() {
  const runId = `writer-a8-${crypto.randomUUID()}`;
  let tempDir;
  try {
    const { humanLabelsPath } = parseArgs(process.argv.slice(2));
    const dataset = loadDataset();
    const labeledRows = joinLabels(readJsonl(humanLabelsPath), [], dataset);
    const counts = { PASS: 0, FAIL: 0 };
    for (const row of labeledRows) {
      if (row.human_label === "PASS" || row.human_label === "FAIL") counts[row.human_label] += 1;
    }
    if (counts.PASS < MIN_PER_CLASS || counts.FAIL < MIN_PER_CLASS) {
      rejectInput("insufficient_labels");
    }
    if (process.env.ARTICLE_NESTED_SANDBOX === "1" || process.env.ARTICLE_JUDGE_BROKER_SERVER === "1") {
      rejectInput("nested_sandbox_execution");
    }

    const casesById = new Map(dataset.cases.map((item) => [item.case_id, item]));
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "writer-a8-identity-"));
    for (const row of labeledRows) {
      const caseData = casesById.get(row.case_id);
      if (!caseData) rejectInput("unknown_case");
      const prediction = invokeIdentityGate({
        caseData,
        caseDir: path.join(tempDir, caseData.case_id),
        runId,
        dataset,
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
        errorClass: error.code || "invalid_human_labels",
        retryable: false,
      }));
    }
    process.exitCode = 2;
  } finally {
    if (tempDir) fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

if (require.main === module) main();
