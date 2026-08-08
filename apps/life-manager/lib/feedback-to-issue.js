"use strict";

const { execFileSync } = require("node:child_process");


const ISSUE_REPO = "Daisuke134/life-manager";
const DEV_LOOP_LABEL = "lm:type:self-heal";
const SOURCE_REF = /^(tg|err):sha256:[a-f0-9]{32}$/;
const PRODUCT_LEARNING_FIELDS = Object.freeze([
  "source_event_id",
  "user_segment",
  "opportunity",
  "desired_outcome",
  "evidence",
  "proposed_assumption_test",
  "success_metric",
]);
const PRODUCT_LEARNING_FORMATS = Object.freeze({
  source_event_id: /^[a-z0-9][a-z0-9._:-]{0,159}$/,
  user_segment: /^[a-z0-9][a-z0-9_-]{0,63}$/,
  desired_outcome: /^[a-z0-9][a-z0-9_,-]{0,159}$/,
  evidence: /^[a-z0-9][a-z0-9._/-]{0,499}$/,
});


function normalizeRow(row) {
  const value = row || {};
  const id = String(value.id || "");
  const sourceRef = String(value.source_ref || "");
  const summary = String(value.summary || "");
  const labels = Array.isArray(value.labels) ? value.labels.map(String) : [];
  if (!/^[1-9][0-9]*$/.test(id)) throw new Error("feedback_issue_row_invalid");
  const sourceMatch = sourceRef.match(SOURCE_REF);
  if (!sourceMatch) throw new Error("feedback_issue_row_invalid");
  if (!summary || summary.length > 500) throw new Error("feedback_issue_row_invalid");
  if (
    labels[0] !== (sourceMatch[1] === "tg" ? "feedback" : "error")
    || labels.length > 8
    || labels.some((label) => !/^[a-z-]+$/.test(label))
  ) {
    throw new Error("feedback_issue_row_invalid");
  }
  const productLearning = {};
  for (const field of PRODUCT_LEARNING_FIELDS) {
    if (value[field] == null) continue;
    const fieldValue = String(value[field]).trim();
    if (!fieldValue || fieldValue.length > 500 || /[\r\n]/.test(fieldValue)) {
      throw new Error("feedback_issue_row_invalid");
    }
    productLearning[field] = fieldValue;
  }
  if (Object.keys(productLearning).length && Object.keys(productLearning).length !== PRODUCT_LEARNING_FIELDS.length) {
    throw new Error("feedback_issue_row_invalid");
  }
  for (const [field, pattern] of Object.entries(PRODUCT_LEARNING_FORMATS)) {
    if (productLearning[field] && !pattern.test(productLearning[field])) {
      throw new Error("feedback_issue_row_invalid");
    }
  }
  return Object.freeze({
    id,
    source_ref: sourceRef,
    summary,
    labels: Object.freeze(labels),
    ...productLearning,
  });
}


function markerFor(row) {
  return row.source_ref.startsWith("tg:")
    ? `lm-feedback:${row.source_ref}`
    : `lm-intake:${row.source_ref}`;
}


function buildFeedbackIssue(input) {
  const row = normalizeRow(input);
  const title = `[${row.labels[0]}] ${row.summary}`.slice(0, 220);
  const heading = row.labels[0] === "feedback"
    ? "## Privacy-safe feedback"
    : "## Privacy-safe production error";
  const body = [
    heading,
    "",
    row.summary,
    "",
    "## Acceptance",
    "",
    "- Add a regression test that reproduces the reported behavior.",
    "- Keep all existing tests and evals green.",
    "- Do not add raw identity, contact, message, or secret data.",
    "",
    ...(row.source_event_id ? [
      "## Product learning",
      "",
      ...PRODUCT_LEARNING_FIELDS.map((field) => `${field}: ${row[field]}`),
      "",
    ] : []),
    `<!-- ${markerFor(row)} -->`,
  ].join("\n");
  return Object.freeze({
    title,
    body,
    labels: Object.freeze([DEV_LOOP_LABEL]),
  });
}


async function claimNextFeedback(query) {
  const result = await query(
    `WITH candidate AS (
       SELECT id
       FROM public.lm_feedback_intake
       WHERE status = 'queued'
          OR (
            status = 'issued'
            AND issue_url IS NULL
            AND updated_at < now() - interval '15 minutes'
          )
       ORDER BY created_at, id
       FOR UPDATE SKIP LOCKED
       LIMIT 1
     )
     UPDATE public.lm_feedback_intake AS feedback
     SET status = 'issued', updated_at = now()
     FROM candidate
     WHERE feedback.id = candidate.id
     RETURNING feedback.id, feedback.source_ref, feedback.summary, feedback.labels,
       feedback.source_event_id, feedback.user_segment, feedback.opportunity,
       feedback.desired_outcome, feedback.evidence,
       feedback.proposed_assumption_test, feedback.success_metric`,
    [],
  );
  const row = result && Array.isArray(result.rows) ? result.rows[0] : null;
  return row ? normalizeRow(row) : null;
}


async function recordIssue(query, rowId, issueUrl) {
  const result = await query(
    `UPDATE public.lm_feedback_intake
     SET issue_url = $2, updated_at = now()
     WHERE id = $1 AND status = 'issued' AND issue_url IS NULL`,
    [String(rowId), String(issueUrl)],
  );
  if (!result || result.rowCount !== 1) throw new Error("feedback_issue_record_conflict");
}


async function releaseClaim(query, rowId) {
  await query(
    `UPDATE public.lm_feedback_intake
     SET status = 'queued', updated_at = now()
     WHERE id = $1 AND status = 'issued' AND issue_url IS NULL`,
    [String(rowId)],
  );
}


async function processNextFeedback({ query, claim, issueClient }) {
  if (typeof query !== "function" || !issueClient) throw new Error("feedback_issue_dependencies_required");
  const row = await (claim || (() => claimNextFeedback(query)))();
  if (!row) return { status: "no-op" };
  const normalized = normalizeRow(row);
  const issue = buildFeedbackIssue(normalized);
  try {
    await issueClient.ensureLabel(DEV_LOOP_LABEL);
    const existing = await issueClient.findByMarker(markerFor(normalized));
    const resolved = existing || await issueClient.create(issue);
    if (!resolved || !/^https:\/\/github\.com\/Daisuke134\/life-manager\/issues\/[1-9][0-9]*$/.test(resolved.url || "")) {
      throw new Error("feedback_issue_url_invalid");
    }
    await recordIssue(query, normalized.id, resolved.url);
    return {
      status: "issued",
      rowId: normalized.id,
      issueUrl: resolved.url,
      created: !existing,
    };
  } catch (error) {
    await releaseClaim(query, normalized.id);
    throw error;
  }
}


function createGhIssueClient(options = {}) {
  const repo = options.repo || ISSUE_REPO;
  const exec = options.execFileSync || execFileSync;
  const run = (args) => String(exec("gh", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }) || "").trim();
  return {
    ensureLabel(label) {
      run([
        "label", "create", label,
        "-R", repo,
        "--color", "B60205",
        "--description", "Privacy-safe input for the unattended Life Manager dev loop",
        "--force",
      ]);
    },
    findByMarker(marker) {
      const raw = run([
        "issue", "list",
        "-R", repo,
        "--state", "all",
        "--limit", "100",
        "--json", "url,body",
      ]);
      const issues = JSON.parse(raw || "[]");
      return issues.find((issue) => String(issue.body || "").includes(`<!-- ${marker} -->`)) || null;
    },
    create(issue) {
      const url = run([
        "issue", "create",
        "-R", repo,
        "--title", issue.title,
        "--body", issue.body,
        "--label", issue.labels[0],
      ]);
      return { url };
    },
  };
}


module.exports = {
  ISSUE_REPO,
  DEV_LOOP_LABEL,
  PRODUCT_LEARNING_FIELDS,
  buildFeedbackIssue,
  claimNextFeedback,
  processNextFeedback,
  createGhIssueClient,
};
