"use strict";

const { createHash } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const EVENT_REF = /^connpass-event:\/\/event\/[1-9][0-9]*$/;
const URL = /^https:\/\/(?:[a-z0-9-]+\.)?connpass\.com\/event\/[1-9][0-9]*\/$/i;
const SLOT = new Set(["available", "waitlist", "closed"]);
const TALK = new Set(["unknown", "not_offered", "open", "submitted", "provider_verified", "closed"]);
const PRIORITY = new Set(["yc_hackathon", "open_talk", "ai", "crypto", "startup", "other"]);
const CREDENTIAL_VALUE = /(?:password|cookie|api[ _-]?key|secret|(?:access|auth|refresh)[ _-]?token)\s*[:=]\s*\S{8,}|\bbearer\s+\S{16,}/i;
const HASH = /^[a-f0-9]{64}$/;
const POSITIVE_PROVIDER_ID = /^[1-9][0-9]*$/;
const UNCERTAIN_REASONS = new Set(["delivery_unknown", "missing_message_id", "provider_rejection", "transport"]);
const CLAIM_KEYS = "candidate_snapshot_sha256,claimed_at,schema_version,wake_id";
const DELIVERY_KEYS = "candidate_snapshot_sha256,observed_at,schema_version,telegram_provider_id,wake_id";
const UNCERTAIN_KEYS = "candidate_snapshot_sha256,quarantined_at,reason,schema_version,wake_id";
const QUESTIONNAIRE_KEYS = "candidate_snapshot_sha256,observed_at,questions,schema_version,telegram_provider_id,wake_id";
const CLAIM_DIR_NAME = "connpass-action-boundary-claims";
const NO_FOLLOW = fs.constants.O_NOFOLLOW || 0;

function invalid() { throw new Error("Connpass action Telegram invalid"); }
function stageError(code) {
  const error = new Error(code);
  error.code = code;
  return error;
}
function safe(value, max) {
  const text = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
  if (!text || text.length > max || /[\x00-\x1f\x7f]|\{\{|\}\}/.test(text) || CREDENTIAL_VALUE.test(text)) invalid();
  return text;
}
function publicText(value, max) {
  const text = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
  if (!text || text.length > max || /[\x00-\x1f\x7f]|\{\{|\}\}/.test(text)) invalid();
  return text;
}
function integer(value) { return Number.isSafeInteger(value) && value >= 0 ? value : null; }
function normalize(candidate) {
  if (!candidate || candidate.provider !== "connpass" || !EVENT_REF.test(String(candidate.event_ref || ""))
    || !URL.test(String(candidate.canonical_url || "")) || !SLOT.has(candidate.participation_slot_status)
    || !TALK.has(candidate.lightning_talk_status) || !PRIORITY.has(candidate.priority_class)) invalid();
  const deadline = candidate.application_deadline_at == null ? null : String(candidate.application_deadline_at);
  if (deadline != null && (!Number.isFinite(Date.parse(deadline)) || new Date(Date.parse(deadline)).toISOString() !== deadline)) invalid();
  return Object.freeze({
    event_ref: candidate.event_ref,
    canonical_url: candidate.canonical_url,
    title: publicText(candidate.title, 500).slice(0, 160),
    participation_slot_status: candidate.participation_slot_status,
    lightning_talk_status: candidate.lightning_talk_status,
    participant_limit: integer(candidate.participant_limit),
    accepted_count: integer(candidate.accepted_count),
    waiting_count: integer(candidate.waiting_count),
    application_deadline_at: deadline,
    priority_class: candidate.priority_class,
    preference_reason: publicText(candidate.preference_reason, 500),
  });
}
function normalizeQuestionnaire(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) invalid();
  const candidate = normalize(input.candidate);
  if (!Array.isArray(input.questions) || input.questions.length < 1 || input.questions.length > 20) invalid();
  const questions = input.questions.map((question) => publicText(question, 300));
  return Object.freeze({ candidate, questions: Object.freeze(questions) });
}
function digest(value) { return createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex"); }
function escapeHtml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function exactInstant(value) { const date = value instanceof Date ? value : new Date(value); if (!Number.isFinite(date.getTime())) invalid(); return date.toISOString(); }
function positiveProviderId(receipt) {
  if (!receipt || typeof receipt !== "object" || Array.isArray(receipt)
    || Object.keys(receipt).sort().join(",") !== "messageId") invalid();
  const raw = receipt.messageId;
  if (typeof raw === "number") {
    if (!Number.isSafeInteger(raw) || raw <= 0) invalid();
    return String(raw);
  }
  if (typeof raw !== "string" || !POSITIVE_PROVIDER_ID.test(raw) || !Number.isSafeInteger(Number(raw))) invalid();
  return raw;
}
function ledgerIdentity(row) { return `${row.wake_id}\u0000${row.candidate_snapshot_sha256}`; }
function validateLedger(row, kind) {
  if (!row || typeof row !== "object" || Array.isArray(row)
    || typeof row.wake_id !== "string" || !row.wake_id || row.wake_id.length > 160
    || /[\x00-\x1f\x7f]/.test(row.wake_id)
    || typeof row.candidate_snapshot_sha256 !== "string" || !HASH.test(row.candidate_snapshot_sha256)) invalid();
  if (safe(row.wake_id, 160) !== row.wake_id) invalid();
  if (row.schema_version !== 1) invalid();
  if (kind === "delivery" && (typeof row.telegram_provider_id !== "string"
    || !POSITIVE_PROVIDER_ID.test(row.telegram_provider_id) || !Number.isSafeInteger(Number(row.telegram_provider_id)))) invalid();
  if (kind === "questionnaire" && (typeof row.telegram_provider_id !== "string"
    || !POSITIVE_PROVIDER_ID.test(row.telegram_provider_id) || !Number.isSafeInteger(Number(row.telegram_provider_id))
    || !Array.isArray(row.questions) || row.questions.length < 1 || row.questions.length > 20)) invalid();
  if (kind === "questionnaire") row.questions.forEach((question) => publicText(question, 300));
  if (kind === "uncertain" && (typeof row.reason !== "string" || !UNCERTAIN_REASONS.has(row.reason))) invalid();
  const timestamp = kind === "claim" ? row.claimed_at
    : ["delivery", "questionnaire"].includes(kind) ? row.observed_at : row.quarantined_at;
  if (typeof timestamp !== "string" || exactInstant(timestamp) !== timestamp) invalid();
}
function readLedger(file, keys, kind) {
  let source = "";
  let descriptor;
  let expected = null;
  try { expected = fs.lstatSync(file); }
  catch (error) {
    if (!error || error.code !== "ENOENT") throw error;
  }
  if (expected && (!expected.isFile() || (expected.mode & 0o777) !== 0o600 || expected.size > 5_000_000)) invalid();
  try {
    descriptor = fs.openSync(file, fs.constants.O_RDONLY | NO_FOLLOW);
    const stat = fs.fstatSync(descriptor);
    if (!stat.isFile() || (stat.mode & 0o777) !== 0o600 || stat.size > 5_000_000
      || (expected && (stat.dev !== expected.dev || stat.ino !== expected.ino))) invalid();
    source = fs.readFileSync(descriptor, "utf8");
  } catch (error) {
    if (!expected && error && error.code === "ENOENT") return [];
    throw error;
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
  const seen = new Set();
  return source.split(/\r?\n/).filter(Boolean).map((line) => {
    let row;
    try { row = JSON.parse(line); } catch { invalid(); }
    if (!row || typeof row !== "object" || Array.isArray(row)
      || Object.keys(row).sort().join(",") !== keys) invalid();
    validateLedger(row, kind);
    const identity = ledgerIdentity(row);
    if (seen.has(identity)) invalid();
    seen.add(identity);
    return Object.freeze(row);
  });
}
function appendDurable(file, value) {
  const bytes = Buffer.from(`${JSON.stringify(value)}\n`, "utf8");
  let existing;
  try { existing = fs.lstatSync(file); } catch (error) { if (!error || error.code !== "ENOENT") throw error; }
  if (existing && (!existing.isFile() || (existing.mode & 0o777) !== 0o600)) invalid();
  const descriptor = fs.openSync(file, fs.constants.O_WRONLY | fs.constants.O_APPEND | fs.constants.O_CREAT | NO_FOLLOW, 0o600);
  try {
    const opened = fs.fstatSync(descriptor);
    if (!opened.isFile() || (opened.mode & 0o777) !== 0o600) invalid();
    fs.fchmodSync(descriptor, 0o600);
    let offset = 0;
    while (offset < bytes.length) offset += fs.writeSync(descriptor, bytes, offset, bytes.length - offset, null);
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  if (!existing) syncDirectory(path.dirname(file));
}
function ensurePrivateDirectory(directory) {
  let existed = true;
  try { fs.lstatSync(directory); } catch (error) {
    if (!error || error.code !== "ENOENT") invalid();
    existed = false;
  }
  try { fs.mkdirSync(directory, { recursive: true, mode: 0o700 }); } catch { invalid(); }
  let stat;
  try { stat = fs.lstatSync(directory); } catch { invalid(); }
  if (!stat.isDirectory() || (stat.mode & 0o777) !== 0o700) invalid();
  if (!existed) syncDirectory(path.dirname(directory));
}
function syncDirectory(directory, expectedMode) {
  let descriptor;
  try {
    descriptor = fs.openSync(directory, fs.constants.O_RDONLY | NO_FOLLOW);
    const stat = fs.fstatSync(descriptor);
    if (!stat.isDirectory() || (expectedMode != null && (stat.mode & 0o777) !== expectedMode)) invalid();
    fs.fsyncSync(descriptor);
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
}
function claimMarkerPath(stateDir, wakeId, snapshot) {
  return path.join(stateDir, CLAIM_DIR_NAME, `${digest({ wake_id: wakeId, candidate_snapshot_sha256: snapshot })}.claim`);
}
function acquireClaimMarker(stateDir, wakeId, snapshot) {
  const directory = path.join(stateDir, CLAIM_DIR_NAME);
  ensurePrivateDirectory(directory);
  const marker = claimMarkerPath(stateDir, wakeId, snapshot);
  let descriptor;
  try {
    descriptor = fs.openSync(marker, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | NO_FOLLOW, 0o600);
  } catch (error) {
    if (error && error.code === "EEXIST") return false;
    throw error;
  }
  try {
    const value = Buffer.from(`${JSON.stringify({ schema_version: 1, wake_id: wakeId, candidate_snapshot_sha256: snapshot })}\n`, "utf8");
    fs.fchmodSync(descriptor, 0o600);
    let offset = 0;
    while (offset < value.length) offset += fs.writeSync(descriptor, value, offset, value.length - offset, null);
    fs.fsyncSync(descriptor);
    syncDirectory(directory, 0o700);
  } catch (error) {
    error.markerCreated = true;
    throw error;
  } finally { fs.closeSync(descriptor); }
  return true;
}
function removeClaimMarker(stateDir, wakeId, snapshot) {
  const directory = path.join(stateDir, CLAIM_DIR_NAME);
  ensurePrivateDirectory(directory);
  const marker = claimMarkerPath(stateDir, wakeId, snapshot);
  let stat;
  try { stat = fs.lstatSync(marker); } catch (error) {
    if (error && error.code === "ENOENT") throw new Error("claim marker disappeared");
    throw error;
  }
  if (!stat.isFile() || (stat.mode & 0o777) !== 0o600) invalid();
  fs.unlinkSync(marker);
  try {
    syncDirectory(directory, 0o700);
    try { fs.lstatSync(marker); throw new Error("claim marker remained"); }
    catch (error) { if (!error || error.code !== "ENOENT") throw error; }
  } catch (error) {
    // Recreate the marker best-effort before surfacing uncertainty. If the
    // directory fsync failed, an in-process replay fence still remains.
    try { acquireClaimMarker(stateDir, wakeId, snapshot); } catch { /* uncertainty is recorded by the caller */ }
    throw error;
  }
}
function quarantine(file, wakeId, snapshot, reason, now) {
  appendDurable(file, Object.freeze({
    schema_version: 1,
    wake_id: wakeId,
    candidate_snapshot_sha256: snapshot,
    reason,
    quarantined_at: exactInstant(now()),
  }));
}
function createConnpassActionTelegram(options = {}) {
  const stateDir = path.resolve(String(options.stateDir || ""));
  const wakeId = safe(options.wakeId, 160);
  const telegramTarget = safe(options.telegramTarget, 200);
  const now = options.now || (() => new Date());
  const send = options.send;
  if (!path.isAbsolute(stateDir) || stateDir === path.parse(stateDir).root || typeof now !== "function" || typeof send !== "function") invalid();
  const file = path.join(stateDir, "connpass-action-boundary-deliveries.jsonl");
  const questionnaireFile = path.join(stateDir, "connpass-questionnaire-requests.jsonl");
  const claimFile = path.join(stateDir, "connpass-action-boundary-send-claims.jsonl");
  const uncertainFile = path.join(stateDir, "connpass-action-boundary-uncertain.jsonl");
  return Object.freeze({
    async reportQuestionnaire(input = {}) {
      let normalized;
      try { normalized = normalizeQuestionnaire(input); }
      catch { throw stageError("CONNPASS_QUESTIONNAIRE_CANDIDATE_FAILED"); }
      const snapshot = digest({
        event_ref: normalized.candidate.event_ref,
        questions: normalized.questions,
      });
      try { ensurePrivateDirectory(stateDir); }
      catch { throw stageError("CONNPASS_QUESTIONNAIRE_LEDGER_FAILED"); }
      let rows;
      try { rows = readLedger(questionnaireFile, QUESTIONNAIRE_KEYS, "questionnaire"); }
      catch { throw stageError("CONNPASS_QUESTIONNAIRE_LEDGER_FAILED"); }
      const existing = rows.find((row) => row.candidate_snapshot_sha256 === snapshot);
      if (existing) {
        return Object.freeze({ telegram_provider_id: existing.telegram_provider_id, completion_disposition: "reused" });
      }
      let claimed;
      try { claimed = acquireClaimMarker(stateDir, "questionnaire", snapshot); }
      catch { throw stageError("CONNPASS_QUESTIONNAIRE_REPORT_UNCERTAIN"); }
      if (!claimed) throw stageError("CONNPASS_QUESTIONNAIRE_REPORT_UNCERTAIN");
      const lines = [
        "Connector::: Connpass質問が未解決のため / 自動申込: 0件",
        `${normalized.candidate.title}`,
        normalized.candidate.canonical_url,
        "",
        ...normalized.questions.map((question, index) => `${index + 1}. ${question}`),
        "",
        "回答を保存後、private profileへ反映して次の自然wakeで再開します。推測回答は行いません。",
      ];
      let response;
      try {
        response = await send(escapeHtml(lines.join("\n")), {
          telegramTarget,
          idempotencyKey: `connpass-questionnaire:${snapshot}`,
        });
      } catch {
        try { quarantine(uncertainFile, wakeId, snapshot, "transport", now); } catch { /* preserve stable stage */ }
        throw stageError("CONNPASS_QUESTIONNAIRE_REPORT_FAILED");
      }
      let providerId;
      try { providerId = positiveProviderId(response); }
      catch {
        try { quarantine(uncertainFile, wakeId, snapshot, "missing_message_id", now); } catch { /* preserve stable stage */ }
        throw stageError("CONNPASS_QUESTIONNAIRE_REPORT_FAILED");
      }
      try {
        appendDurable(questionnaireFile, Object.freeze({
          schema_version: 1,
          wake_id: wakeId,
          candidate_snapshot_sha256: snapshot,
          questions: normalized.questions,
          telegram_provider_id: providerId,
          observed_at: exactInstant(now()),
        }));
      } catch {
        try { quarantine(uncertainFile, wakeId, snapshot, "delivery_unknown", now); } catch { /* preserve stable stage */ }
        throw stageError("CONNPASS_QUESTIONNAIRE_REPORT_UNCERTAIN");
      }
      return Object.freeze({ telegram_provider_id: providerId, completion_disposition: "created" });
    },
    async report(input = {}) {
      if (!Array.isArray(input.candidates) || input.candidates.length < 1 || input.candidates.length > 10_000) {
        throw stageError("CONNPASS_ACTION_BOUNDARY_INPUT_FAILED");
      }
      let normalized;
      try { normalized = input.candidates.slice(0, 5).map(normalize); }
      catch { throw stageError("CONNPASS_ACTION_BOUNDARY_CANDIDATE_FAILED"); }
      const lines = ["Connector::: connpass候補（手動action boundary）", "自動申込: 0件", ""];
      const candidates = [];
      for (const row of normalized) {
        const index = candidates.length;
        const block = [
          `${index + 1}. ${row.title}`,
          `優先度: ${row.priority_class}`,
          `理由: ${row.preference_reason}`,
          `参加枠: ${row.participation_slot_status} / 参加 ${row.accepted_count ?? "不明"}人 / 定員 ${row.participant_limit ?? "不明"}人`,
          `LT: ${row.lightning_talk_status} / 補欠: ${row.waiting_count ?? "不明"}人`,
          `締切: ${row.application_deadline_at ?? "provider未提供"}`,
          row.canonical_url,
          "",
        ];
        if ([...lines, ...block].join("\n").trim().length > 4_096) break;
        candidates.push(row);
        lines.push(...block);
      }
      if (candidates.length < 1) invalid();
      const snapshot = digest(candidates);
      try { ensurePrivateDirectory(stateDir); } catch { throw stageError("CONNPASS_ACTION_BOUNDARY_LEDGER_FAILED"); }
      let deliveries;
      let claims;
      let uncertain;
      try {
        deliveries = readLedger(file, DELIVERY_KEYS, "delivery");
        claims = readLedger(claimFile, CLAIM_KEYS, "claim");
        uncertain = readLedger(uncertainFile, UNCERTAIN_KEYS, "uncertain");
      } catch {
        throw stageError("CONNPASS_ACTION_BOUNDARY_LEDGER_FAILED");
      }
      const identity = `${wakeId}\u0000${snapshot}`;
      const existing = deliveries.find((row) => ledgerIdentity(row) === identity);
      if (existing) {
        return Object.freeze({ telegram_provider_id: existing.telegram_provider_id, completion_disposition: "reused" });
      }
      if (uncertain.some((row) => ledgerIdentity(row) === identity) || claims.some((row) => ledgerIdentity(row) === identity)) {
        throw stageError("CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
      }
      const claim = Object.freeze({
        schema_version: 1,
        wake_id: wakeId,
        candidate_snapshot_sha256: snapshot,
        claimed_at: exactInstant(now()),
      });
      let claimed;
      try { claimed = acquireClaimMarker(stateDir, wakeId, snapshot); }
      catch (error) {
        throw stageError(error && error.markerCreated
          ? "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN" : "CONNPASS_ACTION_BOUNDARY_CLAIM_FAILED");
      }
      if (!claimed) throw stageError("CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
      try {
        appendDurable(claimFile, claim);
      } catch {
        try { removeClaimMarker(stateDir, wakeId, snapshot); }
        catch {
          try { quarantine(uncertainFile, wakeId, snapshot, "delivery_unknown", now); } catch { /* preserve the stable stage boundary below */ }
          throw stageError("CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
        }
        throw stageError("CONNPASS_ACTION_BOUNDARY_CLAIM_FAILED");
      }
      const message = escapeHtml(lines.join("\n").trim());
      let response;
      try {
        response = await send(message, { telegramTarget, idempotencyKey: `connpass-action-boundary:${wakeId}:${snapshot}` });
      } catch (error) {
        const reason = error && UNCERTAIN_REASONS.has(error.safeReason) ? error.safeReason : "transport";
        try { quarantine(uncertainFile, wakeId, snapshot, reason, now); } catch { /* preserve the stable stage boundary below */ }
        throw stageError(reason === "transport"
          ? "CONNPASS_ACTION_BOUNDARY_SEND_FAILED" : "CONNPASS_ACTION_BOUNDARY_PROVIDER_ID_FAILED");
      }
      let providerId;
      let reason = null;
      if (response && response.delivery_unknown === true) reason = "delivery_unknown";
      else if (response && response.ok === false) reason = "provider_rejection";
      if (!reason) {
        try { providerId = positiveProviderId(response); }
        catch { reason = "missing_message_id"; }
      }
      if (reason) {
        try { quarantine(uncertainFile, wakeId, snapshot, reason, now); } catch { /* preserve the stable stage boundary below */ }
        throw stageError("CONNPASS_ACTION_BOUNDARY_PROVIDER_ID_FAILED");
      }
      try {
        appendDurable(file, Object.freeze({
          schema_version: 1,
          wake_id: wakeId,
          candidate_snapshot_sha256: snapshot,
          telegram_provider_id: providerId,
          observed_at: exactInstant(now()),
        }));
      } catch {
        try { quarantine(uncertainFile, wakeId, snapshot, "delivery_unknown", now); } catch { /* preserve the stable stage boundary below */ }
        throw stageError("CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
      }
      return Object.freeze({ telegram_provider_id: providerId, completion_disposition: "created" });
    },
  });
}

module.exports = { createConnpassActionTelegram };
