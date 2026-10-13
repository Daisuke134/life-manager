"use strict";

const crypto = require("node:crypto");
const { TextDecoder } = require("node:util");

const MAX_INPUT_BYTES = 1_500_000;
const MAX_ARTIFACT_BYTES = 1_000_000;
const HASH = /^[a-f0-9]{64}$/u;
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const EDITORIAL_FORMS = new Set([
  "explainer", "how-to", "case-study", "comparison", "field-note", "opinion", "report",
]);
const ACTIONS = new Set([
  "ready_to_freeze", "reroute", "block_freeze", "evaluate_reroute", "force_publish_advisory",
]);
const LANGUAGES = ["en", "ja"];
const PUBLICATION_STAGES = new Set([
  "draft",
  "blocked-before-publication",
  "published",
  "unknown",
]);

function invalid(label) {
  throw new Error(`Writer eval ${label} invalid`);
}

function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid("input");
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) invalid("input");
}

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function publicationCheck(observed, expected) {
  if (observed === "unknown" || expected === "unknown") return "unknown";
  return observed === expected ? "pass" : "fail";
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isHashOrNull(value) {
  return value === null || (typeof value === "string" && HASH.test(value));
}

function canonicalJson(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) throw new Error("unsupported receipt number");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (!isObject(value)) throw new Error("unsupported receipt value");
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

function qualityLanguageValid(value, lang) {
  const fields = [
    "lang", "article_sha256", "editorial", "identity", "reader",
    "editorial_current", "identity_current", "reader_current",
    "evaluation_current", "ready", "reasons",
  ];
  try {
    exactKeys(value, fields);
  } catch {
    return false;
  }
  return value.lang === lang
    && typeof value.article_sha256 === "string" && HASH.test(value.article_sha256)
    && ["PASS", "FAIL"].includes(value.editorial)
    && ["PASS", "FAIL"].includes(value.identity)
    && ["PASS", "FAIL"].includes(value.reader)
    && ["editorial_current", "identity_current", "reader_current", "evaluation_current", "ready"]
      .every((field) => typeof value[field] === "boolean")
    && Array.isArray(value.reasons)
    && value.reasons.every((reason) => typeof reason === "string");
}

function receiptSchemaValid(receipt, expectedRunId) {
  if (!isObject(receipt)
    || receipt.version !== 2
    || receipt.run_id !== expectedRunId
    || !Number.isSafeInteger(receipt.attempt) || receipt.attempt < 1
    || !ACTIONS.has(receipt.action)
    || typeof receipt.fingerprint !== "string" || !HASH.test(receipt.fingerprint)
    || typeof receipt.editorial_form !== "string" || !EDITORIAL_FORMS.has(receipt.editorial_form)
    || !Array.isArray(receipt.failed_languages)
    || receipt.failed_languages.some((lang) => !LANGUAGES.includes(lang))
    || new Set(receipt.failed_languages).size !== receipt.failed_languages.length
    || !Number.isSafeInteger(receipt.reroutes_used) || receipt.reroutes_used < 0
    || !isObject(receipt.quality)
    || Object.keys(receipt.quality).length !== LANGUAGES.length
    || !LANGUAGES.every((lang) => qualityLanguageValid(receipt.quality[lang], lang))
    || !["strict", "continuous"].includes(receipt.publication_policy)
    || !isHashOrNull(receipt.feedback_invocation_sha256)
    || !isHashOrNull(receipt.feedback_plan_sha256)
    || !isHashOrNull(receipt.feedback_iteration_plan_sha256)
    || !isHashOrNull(receipt.quality_feedback_consumption_sha256)
    || !isObject(receipt.receipt_snapshots)
    || Object.keys(receipt.receipt_snapshots).length !== LANGUAGES.length
    || !LANGUAGES.every((lang) => {
      const snapshots = receipt.receipt_snapshots[lang];
      return isObject(snapshots)
        && Object.keys(snapshots).length === 3
        && ["editorial", "reader", "identity"].every(
          (name) => typeof snapshots[name] === "string" && HASH.test(snapshots[name]),
        );
    })
    || !isHashOrNull(receipt.previous_receipt_sha256)
    || typeof receipt.receipt_sha256 !== "string" || !HASH.test(receipt.receipt_sha256)) {
    return false;
  }

  const allowed = new Set([
    "version", "run_id", "attempt", "action", "fingerprint", "editorial_form",
    "failed_languages", "reroutes_used", "quality", "publication_policy",
    "feedback_invocation_sha256", "feedback_plan_sha256", "feedback_iteration_plan_sha256",
    "quality_feedback_consumption_sha256", "receipt_snapshots", "previous_receipt_sha256",
    "receipt_sha256", "force_publish_after_iterations", "quality_advisory", "reason",
    "forbidden_editorial_form", "required_changes", "required_evaluations",
    "quality_feedback_reason",
  ]);
  if (Object.keys(receipt).some((key) => !allowed.has(key))) return false;

  if (receipt.action === "force_publish_advisory"
    && (receipt.force_publish_after_iterations !== 1
      || receipt.quality_advisory !== true
      || receipt.reason !== "quality_iteration_limit_reached")) return false;
  if (receipt.action === "reroute"
    && (!EDITORIAL_FORMS.has(receipt.forbidden_editorial_form)
      || JSON.stringify(receipt.required_changes) !== JSON.stringify(["editorial_form", "outline"]))) {
    return false;
  }
  if (receipt.action === "evaluate_reroute"
    && (!Array.isArray(receipt.required_evaluations)
      || !["editorial", "identity", "reader"].every((item) => receipt.required_evaluations.includes(item)))) {
    return false;
  }
  return true;
}

function receiptHashValid(receipt) {
  try {
    const { receipt_sha256: unused, ...unsigned } = receipt;
    void unused;
    return sha256(Buffer.from(canonicalJson(unsigned), "utf8")) === receipt.receipt_sha256;
  } catch {
    return false;
  }
}

function gradeWriterReceipt(value) {
  exactKeys(value, [
    "schema_version",
    "case_id",
    "run_id",
    "artifact_base64",
    "expected_artifact_sha256",
    "prior_receipt_sha256",
    "publication_status",
    "expected_publication_status",
  ]);
  if (value.schema_version !== 1) invalid("schema version");
  if (typeof value.case_id !== "string" || !ID.test(value.case_id)) invalid("case id");
  if (typeof value.run_id !== "string" || !ID.test(value.run_id)) invalid("run id");
  if (typeof value.artifact_base64 !== "string"
    || value.artifact_base64.length > Math.ceil(MAX_ARTIFACT_BYTES / 3) * 4) {
    invalid("artifact size");
  }
  if (value.expected_artifact_sha256 !== null
    && (typeof value.expected_artifact_sha256 !== "string" || !HASH.test(value.expected_artifact_sha256))) {
    invalid("artifact hash");
  }
  if (!Array.isArray(value.prior_receipt_sha256) || value.prior_receipt_sha256.length > 100
    || value.prior_receipt_sha256.some((item) => typeof item !== "string" || !HASH.test(item))) {
    invalid("receipt history");
  }
  if (!PUBLICATION_STAGES.has(value.publication_status)
    || !PUBLICATION_STAGES.has(value.expected_publication_status)) invalid("publication stage");

  const artifact = Buffer.from(value.artifact_base64, "base64");
  if (artifact.toString("base64") !== value.artifact_base64
    || artifact.length > MAX_ARTIFACT_BYTES) invalid("artifact encoding");
  const artifactHash = sha256(artifact);
  const artifactHashCheck = value.expected_artifact_sha256 === null
    ? "unknown"
    : artifactHash === value.expected_artifact_sha256 ? "pass" : "fail";

  let receipt = null;
  let parseability = "fail";
  let parseSucceeded = false;
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(artifact);
    receipt = JSON.parse(text);
    parseability = "pass";
    parseSucceeded = true;
  } catch {
    receipt = null;
  }

  const receiptSchema = !parseSucceeded
    ? "unknown"
    : receiptSchemaValid(receipt, value.run_id) ? "pass" : "fail";
  const receiptId = !parseSucceeded
    ? "unknown"
    : receiptSchema === "pass" && receiptHashValid(receipt) ? "pass" : "fail";
  const priorHashes = value.prior_receipt_sha256;
  const priorHasDuplicates = new Set(priorHashes).size !== priorHashes.length;
  const chainMatches = receipt !== null && receiptSchema === "pass"
    && (receipt.attempt === 1
      ? priorHashes.length === 0 && receipt.previous_receipt_sha256 === null
      : priorHashes.length === receipt.attempt - 1
        && priorHashes.at(-1) === receipt.previous_receipt_sha256);
  const duplicateReceipt = receiptId !== "pass"
    ? "unknown"
    : priorHasDuplicates || priorHashes.includes(receipt.receipt_sha256) || !chainMatches
      ? "fail" : "pass";

  const publicationStatus = publicationCheck(
    value.publication_status,
    value.expected_publication_status,
  );
  const reasonCodes = [];
  if (artifactHashCheck === "fail") reasonCodes.push("artifact_sha256_mismatch");
  if (parseability === "fail") reasonCodes.push("quality_self_heal_record_unparseable");
  if (receiptSchema === "fail") reasonCodes.push("quality_self_heal_record_schema_invalid");
  if (receiptId === "fail") reasonCodes.push("quality_self_heal_receipt_hash_mismatch");
  if (duplicateReceipt === "fail") reasonCodes.push("duplicate_quality_self_heal_receipt");
  if (publicationStatus === "fail") reasonCodes.push("publication_status_mismatch");

  return Object.freeze({
    schema_version: 1,
    record_type: "writer_code_grade",
    case_id: value.case_id,
    run_id: value.run_id,
    checks: Object.freeze({
      artifact_hash: artifactHashCheck,
      receipt_parseability: parseability,
      receipt_schema: receiptSchema,
      receipt_id: receiptId,
      duplicate_receipt: duplicateReceipt,
      publication_status: publicationStatus,
    }),
    dimensions: Object.freeze({
      task_completion: "unknown",
      quality: "unknown",
      effect_integrity: "unknown",
      settled_net_minor: null,
    }),
    reason_codes: Object.freeze(reasonCodes),
  });
}

async function readStdin() {
  const chunks = [];
  let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > MAX_INPUT_BYTES) invalid("stdin size");
    chunks.push(chunk);
  }
  return new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks));
}

async function main() {
  if (process.argv.length !== 2) invalid("arguments");
  const input = JSON.parse(await readStdin());
  process.stdout.write(`${JSON.stringify(gradeWriterReceipt(input))}\n`);
}

if (require.main === module) {
  main().catch(() => {
    process.stderr.write("Writer eval rejected input\n");
    process.exitCode = 2;
  });
}

module.exports = { gradeWriterReceipt };
