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
const IDENTITY_GATE = path.join(WRITER_ROOT, "scripts/identity-gate.sh");

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
  const preflight = caseId === null;
  return {
    run_id: runId,
    owner_id: "writer-a8-identity-eval",
    occurrence_id: preflight ? `${runId}:preflight` : `${runId}:${caseId}`,
    case_id: caseId,
    release_sha: process.env.LIFE_MANAGER_RELEASE_SHA || null,
    loaded_argv: preflight
      ? ["node", "run-identity-cases.js", "--human-labels", "<provided>"]
      : ["bash", "identity-gate.sh", "<isolated>/article.md", "--lang", "en"],
    loaded_env: {
      ARTICLE_ROOT: "skills/writer-agent",
      ARTICLE_MODEL_RUNNER: process.env.ARTICLE_MODEL_RUNNER || "skills/writer-agent/runtime/model-runner.sh",
      ARTICLE_MODEL_STATE_ROOT: "<isolated-temp>",
      ARTICLE_MODEL_LOG: "<isolated-temp>",
      LIFE_MANAGER_ENV_FILE: process.env.LIFE_MANAGER_ENV_FILE || "<default>",
      WRITER_STATE_DIR: "<isolated-temp>",
      WRITER_LOG_DIR: "<isolated-temp>",
    },
    phase: preflight ? "preflight" : "identity_judge",
    command: preflight ? "run-identity-cases.js" : "identity-gate.sh",
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
    ARTICLE_RUN_DIR: caseDir,
    LIFE_MANAGER_RUN_ID: runId,
    LIFE_MANAGER_LOOP_ID: "writer-a8-identity-eval",
    LIFE_MANAGER_OCCURRENCE_ID: `${runId}-${caseData.case_id}`,
    WRITER_EVAL_RUN_ID: runId,
    WRITER_EVAL_CASE_ID: caseData.case_id,
  };
  const result = spawnSync("bash", [IDENTITY_GATE, articlePath, "--lang", "en"], {
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
    emitEvent(eventRecord({
      runId,
      caseId: null,
      exitCode: 2,
      verdict: "UNKNOWN",
      errorClass: error.code || "invalid_human_labels",
      retryable: false,
    }));
    process.exitCode = 2;
  } finally {
    if (tempDir) fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

if (require.main === module) main();
