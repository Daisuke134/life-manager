"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { classifyChangedPath, repairScopeForOwner } = require("./dev-merge-guard.js");

const DEV_LOOP_LABEL = "lm:type:self-heal";
const OUT_OF_SCOPE_OUTCOME = "escalate_owner_out_of_scope";
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const RELEASE_SHA = /^[0-9a-f]{40}$/;
const SAFE_REF = /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._:/-]{1,512}$/;
const TERMINAL_REPAIR_FAILURES = new Set(["blocked", "escalated"]);
const DEFAULT_MAX_BYTES = 2 * 1024 * 1024;

function safeId(value, field) {
  const text = String(value || "");
  if (!SAFE_ID.test(text)) throw new Error(`recovery_self_build_${field}_invalid`);
  return text;
}

function normalizeRecoveryOutcome(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || value.schema_version !== 1 || value.record_type !== "recovery_outcome"
      || !TERMINAL_REPAIR_FAILURES.has(value.state)) {
    throw new Error("recovery_self_build_outcome_invalid");
  }
  const loopId = safeId(value.loop_id, "loop_id");
  const ownerId = safeId(value.owner_id, "owner_id");
  const occurrenceId = safeId(value.occurrence_id, "occurrence_id");
  if (ownerId !== loopId || !occurrenceId.startsWith(`${loopId}:`)) {
    throw new Error("recovery_self_build_identity_invalid");
  }
  const releaseSha = String(value.release_sha || "");
  if (!RELEASE_SHA.test(releaseSha)) throw new Error("recovery_self_build_release_invalid");
  const evidenceRefs = Array.isArray(value.evidence_refs)
    ? value.evidence_refs.filter((ref) => typeof ref === "string" && SAFE_REF.test(ref)).slice(0, 32)
    : [];
  return Object.freeze({
    intent_id: safeId(value.intent_id, "intent_id"),
    loop_id: loopId,
    owner_id: ownerId,
    occurrence_id: occurrenceId,
    release_sha: releaseSha,
    action: safeId(value.action, "action"),
    failure_layer: safeId(value.failure_layer || "unknown", "failure_layer"),
    intent_reason: value.intent_reason == null
      ? null : safeId(value.intent_reason, "intent_reason"),
    state: value.state,
    result: safeId(value.result || value.state, "result"),
    attempt: Number.isSafeInteger(value.attempt) && value.attempt >= 0 ? value.attempt : 0,
    before_event_id: value.before_event_id == null
      ? null : safeId(value.before_event_id, "before_event_id"),
    after_event_id: value.after_event_id == null
      ? null : safeId(value.after_event_id, "after_event_id"),
    command_exit_code: Number.isInteger(value.command_exit_code) ? value.command_exit_code : null,
    next_action: safeId(value.next_action || "escalate_owner", "next_action"),
    outcome_reason: value.reason == null ? null : safeId(value.reason, "reason"),
    evidence_refs: Object.freeze(evidenceRefs),
  });
}

// Reuses the exact file-scope decision the merge guard itself applies to a recovery PR
// (dev-merge-guard.js classifyChangedPath + repairScopeForOwner) rather than re-deriving it: an
// owner whose entrypoint the dev agent cannot touch (outside apps/life-manager, runtime/loop, or a
// registry-granted deterministic/effect-none scope) must never receive an `lm:type:self-heal`
// code-repair issue, because no merge the dev agent could open would ever be eligible to fix it.
// Returns null (unknown, never treated as in-scope) when the registry is missing or the owner has
// no entrypoint on record.
function ownerRepairScopeEligible(registry, ownerId) {
  if (!registry || typeof registry !== "object" || !registry.loops) return null;
  const entry = registry.loops[ownerId];
  const entrypoint = typeof entry?.entrypoint === "string" ? entry.entrypoint : "";
  if (!entrypoint) return null;
  const repairScope = repairScopeForOwner(registry, ownerId);
  return classifyChangedPath(entrypoint, { repairScope }).allowed === true;
}

function markerForRecoveryOutcome(value) {
  const outcome = normalizeRecoveryOutcome(value);
  return `lm-recovery:${outcome.intent_id}`;
}

function buildRecoverySelfBuildIssue(value) {
  const outcome = normalizeRecoveryOutcome(value);
  const marker = markerForRecoveryOutcome(value);
  const evidence = outcome.evidence_refs.length
    ? outcome.evidence_refs.map((ref) => `- ${ref}`)
    : ["- none"];
  return Object.freeze({
    title: `[self-heal] ${outcome.loop_id} exhausted bounded recovery`.slice(0, 220),
    body: [
      "## Sanitized recovery outcome",
      "",
      `owner_id: ${outcome.owner_id}`,
      `occurrence_id: ${outcome.occurrence_id}`,
      `release_sha: ${outcome.release_sha}`,
      `failure_layer: ${outcome.failure_layer}`,
      `intent_reason: ${outcome.intent_reason || "none"}`,
      `action: ${outcome.action}`,
      `result: ${outcome.result}`,
      `attempt: ${outcome.attempt}`,
      `before_event_id: ${outcome.before_event_id || "none"}`,
      `after_event_id: ${outcome.after_event_id || "none"}`,
      `command_exit_code: ${outcome.command_exit_code ?? "none"}`,
      `outcome_reason: ${outcome.outcome_reason || "none"}`,
      `next_action: ${outcome.next_action}`,
      "",
      "## Evidence refs",
      "",
      ...evidence,
      "",
      "## Acceptance",
      "",
      "- Add a retained regression fixture that reproduces this failure before the fix.",
      "- Keep focused tests and existing safety/evaluation gates green.",
      "- Do not edit the recovery control plane, evaluator, merge guard, policy or external-effect owners.",
      "- Preserve immutable release binding and prove the repaired owner with authoritative status readback.",
      "",
      `<!-- ${marker} -->`,
    ].join("\n"),
    labels: Object.freeze([DEV_LOOP_LABEL]),
  });
}

function readJsonLinesTail(file, maxBytes = DEFAULT_MAX_BYTES) {
  let descriptor;
  try { descriptor = fs.openSync(file, "r"); } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
  try {
    const size = fs.fstatSync(descriptor).size;
    const length = Math.min(size, maxBytes);
    const start = size - length;
    const buffer = Buffer.alloc(length);
    fs.readSync(descriptor, buffer, 0, length, start);
    let text = buffer.toString("utf8");
    if (start > 0) text = text.slice(Math.max(0, text.indexOf("\n") + 1));
    return text.split("\n").filter(Boolean).map((line) => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean);
  } finally {
    fs.closeSync(descriptor);
  }
}

function issuedIntentIds(cursorPath) {
  return new Set(readJsonLinesTail(cursorPath).map((row) => String(row?.intent_id || "")).filter(Boolean));
}

function appendIssued(cursorPath, value) {
  fs.mkdirSync(path.dirname(cursorPath), { recursive: true, mode: 0o700 });
  const descriptor = fs.openSync(cursorPath, "a", 0o600);
  try {
    fs.fchmodSync(descriptor, 0o600);
    fs.writeSync(descriptor, `${JSON.stringify(value)}\n`);
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
}

async function processRecoveryOutcomeJournal({
  journalPath, cursorPath, issueClient, maxBytes, registry,
} = {}) {
  if (!journalPath || !cursorPath || !issueClient
      || typeof issueClient.ensureLabel !== "function"
      || typeof issueClient.findByMarker !== "function"
      || typeof issueClient.create !== "function") {
    throw new Error("recovery_self_build_dependencies_required");
  }
  const issued = issuedIntentIds(cursorPath);
  const seen = new Set();
  let selected = null;
  for (const row of readJsonLinesTail(journalPath, maxBytes)) {
    let normalized;
    try { normalized = normalizeRecoveryOutcome(row); } catch { continue; }
    if (seen.has(normalized.intent_id) || issued.has(normalized.intent_id)) continue;
    seen.add(normalized.intent_id);
    selected = row;
    break;
  }
  if (!selected) return { status: "no-op", reason: "no_unissued_terminal_outcome" };

  const normalized = normalizeRecoveryOutcome(selected);

  if (registry !== undefined && ownerRepairScopeEligible(registry, normalized.owner_id) === false) {
    appendIssued(cursorPath, {
      schema_version: 1,
      intent_id: normalized.intent_id,
      issue_url: null,
      created: false,
      outcome: OUT_OF_SCOPE_OUTCOME,
    });
    return {
      status: "skipped_out_of_scope",
      intent_id: normalized.intent_id,
      outcome: OUT_OF_SCOPE_OUTCOME,
    };
  }

  const marker = markerForRecoveryOutcome(selected);
  const issue = buildRecoverySelfBuildIssue(selected);
  await issueClient.ensureLabel(DEV_LOOP_LABEL);
  const existing = await issueClient.findByMarker(marker);
  const resolved = existing || await issueClient.create(issue);
  const url = String(resolved?.url || "");
  if (!/^https:\/\/github\.com\/Daisuke134\/life-manager\/issues\/[1-9][0-9]*$/.test(url)) {
    throw new Error("recovery_self_build_issue_url_invalid");
  }
  appendIssued(cursorPath, {
    schema_version: 1,
    intent_id: normalized.intent_id,
    issue_url: url,
    created: !existing,
  });
  return {
    status: "issued",
    intent_id: normalized.intent_id,
    issue_url: url,
    created: !existing,
  };
}

module.exports = {
  DEV_LOOP_LABEL,
  OUT_OF_SCOPE_OUTCOME,
  buildRecoverySelfBuildIssue,
  markerForRecoveryOutcome,
  normalizeRecoveryOutcome,
  ownerRepairScopeEligible,
  processRecoveryOutcomeJournal,
  readJsonLinesTail,
};
