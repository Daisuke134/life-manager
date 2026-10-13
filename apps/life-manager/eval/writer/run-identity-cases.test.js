"use strict";

const assert = require("node:assert/strict");
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
const VERSION = "writer-edd-a8-v2";
const DATASET_SHA256 = "7168b3f762f0b72d9dd8259aad09779a305d3a101a3c1bd4f844b9db78cf9e8d";

function humanRows(passCount) {
  return Array.from({ length: 40 }, (_, index) => ({
    case_id: `W-C-${String(index + 1).padStart(3, "0")}`,
    dataset_version: VERSION,
    dataset_sha256: DATASET_SHA256,
    human_label: index < passCount ? "PASS" : "FAIL",
    human_rationale: `PRIVATE_RATIONALE_MARKER_${index + 1}`,
  }));
}

function makeHarness(labels) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "writer-identity-eval-"));
  const modelRunner = path.join(directory, "fake-model-runner.js");
  const promptsDirectory = path.join(directory, "prompts");
  const contextsDirectory = path.join(directory, "contexts");
  const stateDirectory = path.join(directory, "state");
  const logDirectory = path.join(directory, "logs");
  const envFile = path.join(directory, "empty.env");
  const labelsPath = path.join(directory, "human-labels.jsonl");

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
    WRITER_SHARED_RUNNER_STATE: process.env.WRITER_SHARED_RUNNER_STATE,
    ARTICLE_CODEX_EVENTS_FILE: process.env.ARTICLE_CODEX_EVENTS_FILE || null,
    ARTICLE_CODEX_LAST_MESSAGE_FILE: process.env.ARTICLE_CODEX_LAST_MESSAGE_FILE || null,
    ARTICLE_CODEX_RESUME_SESSION_ID: process.env.ARTICLE_CODEX_RESUME_SESSION_ID || null,
    ARTICLE_SOL_TRIGGER_RECEIPT: process.env.ARTICLE_SOL_TRIGGER_RECEIPT || null,
    ARTICLE_MODEL_ROLE: process.env.ARTICLE_MODEL_ROLE || null,
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
  fs.writeFileSync(envFile, "");
  fs.writeFileSync(labelsPath, `${labels.map((row) => JSON.stringify(row)).join("\n")}\n`);

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
    ARTICLE_MODEL_ROLE: "sol-audit",
    WRITER_SHARED_RUNNER_STATE: path.join(directory, "shared-runner-state-must-not-write"),
  };
  delete env.ARTICLE_RUN_DIR;
  delete env.LIFE_MANAGER_RUN_ID;
  delete env.LIFE_MANAGER_LOOP_ID;
  delete env.LIFE_MANAGER_OCCURRENCE_ID;

  return { directory, labelsPath, promptsDirectory, contextsDirectory, env };
}

function invoke(harness) {
  return spawnSync(process.execPath, [CLI, "--human-labels", harness.labelsPath], {
    cwd: REPO_ROOT,
    encoding: "utf8",
    env: harness.env,
  });
}

test("refuses to call the judge before human PASS and FAIL each reach 20", () => {
  const harness = makeHarness(humanRows(19));
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(fs.existsSync(harness.promptsDirectory), false);
    assert.doesNotMatch(result.stderr, /PRIVATE_RATIONALE_MARKER/u);
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});

test("refuses nested sandbox execution before creating any judge prompt", () => {
  const harness = makeHarness(humanRows(20));
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

test("runs isolated cases without labels, filters non-Category-C failures, and emits safe prediction rows", () => {
  const harness = makeHarness(humanRows(20));
  try {
    const result = invoke(harness);

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 0, result.stderr);
    const predictions = result.stdout.trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(predictions.length, 40);
    assert.deepEqual(predictions.slice(0, 4), [
      { case_id: "W-C-001", dataset_version: VERSION, dataset_sha256: DATASET_SHA256, judge_verdict: "UNKNOWN" },
      { case_id: "W-C-002", dataset_version: VERSION, dataset_sha256: DATASET_SHA256, judge_verdict: "FAIL" },
      { case_id: "W-C-003", dataset_version: VERSION, dataset_sha256: DATASET_SHA256, judge_verdict: "UNKNOWN" },
      { case_id: "W-C-004", dataset_version: VERSION, dataset_sha256: DATASET_SHA256, judge_verdict: "PASS" },
    ]);
    assert.equal(fs.readdirSync(harness.promptsDirectory).length, 40);
    assert.equal(fs.readdirSync(harness.contextsDirectory).length, 40);
    const callContext = JSON.parse(fs.readFileSync(path.join(harness.contextsDirectory, "W-C-002.json"), "utf8"));
    assert.equal(callContext.ARTICLE_MODEL_STATE_ROOT, path.join(callContext.ARTICLE_RUN_DIR, "model-state"));
    assert.equal(callContext.ARTICLE_MODEL_LOG, path.join(callContext.WRITER_LOG_DIR, "model-runner.log"));
    assert.equal(callContext.WRITER_SHARED_RUNNER_STATE, path.join(callContext.ARTICLE_RUN_DIR, "shared-runner-evidence"));
    assert.equal(callContext.ARTICLE_CODEX_EVENTS_FILE, null);
    assert.equal(callContext.ARTICLE_CODEX_LAST_MESSAGE_FILE, null);
    assert.equal(callContext.ARTICLE_CODEX_RESUME_SESSION_ID, null);
    assert.equal(callContext.ARTICLE_SOL_TRIGGER_RECEIPT, null);
    assert.equal(callContext.ARTICLE_MODEL_ROLE, "terra");
    assert.equal(callContext.WRITER_STATE_DIR, path.join(callContext.ARTICLE_RUN_DIR, "state"));
    assert.equal(callContext.WRITER_LOG_DIR, path.join(callContext.ARTICLE_RUN_DIR, "logs"));

    const targetPrompt = fs.readFileSync(path.join(harness.promptsDirectory, "W-C-002.txt"), "utf8");
    assert.match(targetPrompt, /identity-review-v7\.md/u);
    assert.doesNotMatch(targetPrompt, /PRIVATE_RATIONALE_MARKER|human_label/u);
    assert.doesNotMatch(result.stdout, /PRIVATE_RATIONALE_MARKER|human_rationale/u);

    const predictionsPath = path.join(harness.directory, "judge-predictions.jsonl");
    fs.writeFileSync(predictionsPath, result.stdout);
    const joined = spawnSync(process.execPath, [
      JOINER_CLI,
      "--human-labels", harness.labelsPath,
      "--judge-predictions", predictionsPath,
    ], { encoding: "utf8" });
    assert.equal(joined.status, 0, joined.stderr);
    const joinedRows = joined.stdout.trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(joinedRows.length, 40);
    assert.deepEqual(joinedRows.slice(0, 2), [
      { case_id: "W-C-001", human_label: "PASS", judge_verdict: "UNKNOWN" },
      { case_id: "W-C-002", human_label: "PASS", judge_verdict: "FAIL" },
    ]);
    const metrics = spawnSync(process.execPath, [METRICS_CLI], {
      input: joined.stdout,
      encoding: "utf8",
    });
    assert.equal(metrics.status, 0, metrics.stderr);
    const summary = JSON.parse(metrics.stdout);
    assert.equal(summary.status, "incomplete_predictions");
    assert.deepEqual(summary.rates, { tpr: null, tnr: null, false_pass_rate: null, false_fail_rate: null });

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
    assert.doesNotMatch(result.stderr, /PRIVATE_RATIONALE_MARKER|identity-review-v7\.md/u);
    assert.equal(fs.existsSync(harness.env.ARTICLE_CODEX_EVENTS_FILE), false);
    assert.equal(fs.existsSync(harness.env.ARTICLE_CODEX_LAST_MESSAGE_FILE), false);
  } finally {
    fs.rmSync(harness.directory, { recursive: true, force: true });
  }
});
