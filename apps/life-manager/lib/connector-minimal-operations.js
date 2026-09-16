"use strict";

const fs = require("node:fs");
const path = require("node:path");

const { sendMessage: sendTelegramMessage } = require("./telegram.js");

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9:._-]{2,159}$/;
const SAFE_REASON = /^[a-z0-9][a-z0-9_:-]{1,99}$/;
const SAFE_METHOD = /^[a-z][a-z0-9_]{1,63}$/;
const SAFE_PROVIDER = /^[a-z][a-z0-9_-]{1,31}$/;
// Bounded, non-sensitive: a JS class/constructor name only (see
// connector-minimal-runner.js's safeErrorClass), never a message, stack,
// URL, or env value.
const ERROR_CLASS = /^[A-Za-z][A-Za-z0-9]{0,63}$/;
const PURPOSE = /^(?:navigate|observe|fill|submit|readback)$/;
const RESULT = /^(?:success|failed)$/;
const ACTION_KEYS = "duration_ms,method,purpose,result,timestamp";
const ACTION_FAILURE_CONTEXT_KEYS = "duration_ms,method,provider,purpose,result,safe_reason,timestamp";
const ACTION_FAILURE_CONTEXT_WITH_CLASS_KEYS = "duration_ms,error_class,method,provider,purpose,result,safe_reason,timestamp";
const REPORT_KEYS = "consecutive_failure_count,created_at,safe_reason,schema_version,status,wake_id";
const DELIVERY_KEYS = "delivered_at,schema_version,telegram_provider_id,wake_id";
const CLAIM_KEYS = "claimed_at,schema_version,wake_id";
const UNCERTAIN_KEYS = "quarantined_at,reason,schema_version,wake_id";
const POSITIVE_PROVIDER_ID = /^[1-9][0-9]*$/;
const UNCERTAIN_REASONS = new Set(["delivery_unknown", "missing_message_id", "provider_rejection", "transport"]);
const STATUSES = new Set(["applied_bundle", "completed_no_effect", "circuit_open"]);
// Ceiling for observed/normalized/window/free_open/calendar_free counts: matches the
// `rows.length > 5_000` per-page guard in connector-connpass-workflow.js, the real limit
// on how many rows discovery can ever observe (measured live: connpass can legitimately
// observe 767 Tokyo events in-window, so 500 rejected a genuine result).
const DISCOVERY_AUDIT_COUNT_CEILING = 5_000;
// Ceiling for discovered/within_window/eligible/calendar_free/selected counts: matches
// the highest per-page listing guard among this validator's callers (kokuchpro's
// `rows.length > 800` in connector-kokuchpro-workflow.js; eventbrite=500, techplay=50
// are already within the old 500 bound). Raised for the same reason as above.
const DOORKEEPER_DISCOVERY_AUDIT_COUNT_CEILING = 800;

function invalid() {
  throw new Error("Connector minimal operations invalid");
}

function exactInstant(value) {
  const instant = value instanceof Date ? value.toISOString() : String(value || "");
  if (!Number.isFinite(Date.parse(instant)) || new Date(Date.parse(instant)).toISOString() !== instant) invalid();
  return instant;
}

function privateDirectory(value) {
  const directory = path.resolve(String(value || ""));
  if (!path.isAbsolute(directory) || directory === path.parse(directory).root) invalid();
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  fs.chmodSync(directory, 0o700);
  // A retry must not mistake an unflushed ancestor from an earlier failed
  // attempt for a durable directory. Sync every parent entry up to the root.
  for (let child = directory, parent = path.dirname(child); parent !== child;
    child = parent, parent = path.dirname(child)) {
    const parentFd = fs.openSync(parent, "r");
    try { fs.fsyncSync(parentFd); } finally { fs.closeSync(parentFd); }
  }
  return directory;
}

function readRows(file) {
  let source = "";
  try {
    const stat = fs.statSync(file);
    if (!stat.isFile() || stat.size > 5_000_000) invalid();
    source = fs.readFileSync(file, "utf8");
  } catch (error) {
    if (!error || error.code !== "ENOENT") throw error;
  }
  return source.split(/\r?\n/).filter(Boolean).map((line) => {
    try { return JSON.parse(line); } catch { invalid(); }
  });
}

function append(file, value) {
  fs.appendFileSync(file, `${JSON.stringify(value)}\n`, { encoding: "utf8", mode: 0o600 });
  fs.chmodSync(file, 0o600);
}

function appendDurable(file, value) {
  const bytes = Buffer.from(`${JSON.stringify(value)}\n`, "utf8");
  const fd = fs.openSync(file, "a", 0o600);
  try {
    let offset = 0;
    while (offset < bytes.length) offset += fs.writeSync(fd, bytes, offset, bytes.length - offset, null);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  fs.chmodSync(file, 0o600);
  const directoryFd = fs.openSync(path.dirname(file), "r");
  try { fs.fsyncSync(directoryFd); } finally { fs.closeSync(directoryFd); }
}

function safeAction(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) invalid();
  const keys = Object.keys(input).sort().join(",");
  const hasErrorClass = keys === ACTION_FAILURE_CONTEXT_WITH_CLASS_KEYS;
  const hasFailureContext = keys === ACTION_FAILURE_CONTEXT_KEYS || hasErrorClass;
  if (
    (keys !== ACTION_KEYS && !hasFailureContext)
    || !PURPOSE.test(String(input.purpose || ""))
    || !SAFE_METHOD.test(String(input.method || ""))
    || !RESULT.test(String(input.result || ""))
    || !Number.isInteger(input.duration_ms) || input.duration_ms < 0 || input.duration_ms > 600_000
    || (hasFailureContext && (
      input.result !== "failed"
      || !SAFE_PROVIDER.test(String(input.provider || ""))
      || !SAFE_REASON.test(String(input.safe_reason || ""))
    ))
    || (hasErrorClass && !ERROR_CLASS.test(String(input.error_class || "")))
  ) invalid();
  return Object.freeze({
    purpose: input.purpose,
    method: input.method,
    timestamp: exactInstant(input.timestamp),
    result: input.result,
    duration_ms: input.duration_ms,
    ...(hasFailureContext ? { provider: input.provider, safe_reason: input.safe_reason } : {}),
    ...(hasErrorClass ? { error_class: input.error_class } : {}),
  });
}

function safeReport(input, wakeId, createdAt) {
  if (
    !input || typeof input !== "object" || Array.isArray(input)
    || !STATUSES.has(String(input.status || ""))
    || !SAFE_REASON.test(String(input.safe_reason || ""))
    || !Number.isInteger(input.consecutive_failure_count)
    || input.consecutive_failure_count < 0 || input.consecutive_failure_count > 3
  ) invalid();
  return Object.freeze({
    schema_version: 1,
    wake_id: wakeId,
    status: input.status,
    safe_reason: input.safe_reason,
    consecutive_failure_count: input.consecutive_failure_count,
    created_at: createdAt,
  });
}

function safeDelivery(input) {
  if (
    !input || typeof input !== "object" || Array.isArray(input)
    || Object.keys(input).sort().join(",") !== DELIVERY_KEYS
    || input.schema_version !== 1
    || typeof input.wake_id !== "string" || !SAFE_ID.test(input.wake_id)
    || typeof input.telegram_provider_id !== "string" || !POSITIVE_PROVIDER_ID.test(input.telegram_provider_id)
    || !Number.isSafeInteger(Number(input.telegram_provider_id))
    || typeof input.delivered_at !== "string" || exactInstant(input.delivered_at) !== input.delivered_at
  ) invalid();
  return Object.freeze({ ...input });
}

function safeClaim(input) {
  if (
    !input || typeof input !== "object" || Array.isArray(input)
    || Object.keys(input).sort().join(",") !== CLAIM_KEYS
    || input.schema_version !== 1
    || typeof input.wake_id !== "string" || !SAFE_ID.test(input.wake_id)
    || typeof input.claimed_at !== "string" || exactInstant(input.claimed_at) !== input.claimed_at
  ) invalid();
  return Object.freeze({ ...input });
}

function safeUncertain(input) {
  if (
    !input || typeof input !== "object" || Array.isArray(input)
    || Object.keys(input).sort().join(",") !== UNCERTAIN_KEYS
    || input.schema_version !== 1
    || typeof input.wake_id !== "string" || !SAFE_ID.test(input.wake_id)
    || typeof input.reason !== "string" || !UNCERTAIN_REASONS.has(input.reason)
    || typeof input.quarantined_at !== "string" || exactInstant(input.quarantined_at) !== input.quarantined_at
  ) invalid();
  return Object.freeze({ ...input });
}

function positiveTelegramProviderId(response) {
  if (!response || typeof response !== "object" || Array.isArray(response)
    || response.ok !== true || !response.result || typeof response.result !== "object"
    || Array.isArray(response.result)) throw new Error("Telegram delivery needs a positive message ID");
  const raw = response.result.message_id;
  if (!Number.isSafeInteger(raw) || raw <= 0) throw new Error("Telegram delivery needs a positive message ID");
  return String(raw);
}

function safeStoredReport(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)
    || Object.keys(input).sort().join(",") !== REPORT_KEYS
    || input.schema_version !== 1
    || typeof input.wake_id !== "string" || !SAFE_ID.test(input.wake_id)
    || typeof input.created_at !== "string") invalid();
  return safeReport(input, input.wake_id, exactInstant(input.created_at));
}

function uniqueByWake(rows) {
  const seen = new Set();
  return rows.map((row) => {
    if (seen.has(row.wake_id)) invalid();
    seen.add(row.wake_id);
    return row;
  });
}

function safeDiscoveryAudit(input, wakeId, recordedAt) {
  const keys = [
    "calendar_free_count", "free_open_count", "normalized_count", "observed_count", "window_count",
  ];
  if (
    !input || typeof input !== "object" || Array.isArray(input)
    || Object.keys(input).sort().join(",") !== keys.join(",")
    || keys.some((key) => !Number.isInteger(input[key]) || input[key] < 0 || input[key] > DISCOVERY_AUDIT_COUNT_CEILING)
    || input.normalized_count > input.observed_count
    || input.window_count > input.normalized_count
    || input.free_open_count > input.window_count
    || input.calendar_free_count > input.free_open_count
  ) invalid();
  return Object.freeze({
    schema_version: 1,
    wake_id: wakeId,
    ...input,
    recorded_at: recordedAt,
  });
}

function safeRankingAudit(input, wakeId, recordedAt) {
  const keys = [
    "bisect_count", "elapsed_ms", "max_request_ms", "request_count", "retry_count",
    "schema_version", "total_request_ms",
  ];
  const counts = ["request_count", "retry_count", "bisect_count"];
  const timings = ["total_request_ms", "max_request_ms", "elapsed_ms"];
  if (
    !input || typeof input !== "object" || Array.isArray(input)
    || Object.keys(input).sort().join(",") !== keys.join(",")
    || input.schema_version !== 1
    || counts.some((key) => !Number.isInteger(input[key]) || input[key] < 0 || input[key] > 10_000)
    || timings.some((key) => !Number.isInteger(input[key]) || input[key] < 0 || input[key] > 3_600_000)
    || input.retry_count > input.request_count || input.bisect_count > input.request_count
    || input.max_request_ms > input.total_request_ms || input.max_request_ms > input.elapsed_ms
  ) invalid();
  return Object.freeze({ ...input, wake_id: wakeId, recorded_at: recordedAt });
}

function safeDoorkeeperDiscoveryAudit(input, wakeId, recordedAt) {
  const keys = [
    "calendar_free_count", "discovered_count", "eligible_count", "selected_count", "within_window_count",
  ];
  if (
    !input || typeof input !== "object" || Array.isArray(input)
    || Object.keys(input).sort().join(",") !== keys.join(",")
    || keys.some((key) => !Number.isInteger(input[key]) || input[key] < 0 || input[key] > DOORKEEPER_DISCOVERY_AUDIT_COUNT_CEILING)
    || input.selected_count > input.calendar_free_count
    || input.calendar_free_count > input.eligible_count
    || input.eligible_count > input.within_window_count
    || input.within_window_count > input.discovered_count
  ) invalid();
  return Object.freeze({
    schema_version: 1,
    wake_id: wakeId,
    ...input,
    recorded_at: recordedAt,
  });
}

function safeTechPlayDiscoveryAudit(input, wakeId, recordedAt) {
  const countKeys = [
    "calendar_free_count", "discovered_count", "eligible_count", "pending_count",
    "processed_count", "rss_count", "saturated_count", "selected_count", "within_window_count",
  ];
  if (!input || typeof input !== "object" || Array.isArray(input)
    || Object.keys(input).sort().join(",") !== countKeys.join(",")
    || !Number.isInteger(input.processed_count) || !Number.isInteger(input.pending_count)
    || !Number.isInteger(input.rss_count)
    || !Number.isInteger(input.saturated_count)
    || input.processed_count < 0 || input.pending_count < 0
    || input.saturated_count < 0 || input.saturated_count > 1
    || input.saturated_count > input.pending_count
    || input.rss_count < 0 || input.rss_count > input.discovered_count
    || input.processed_count > input.discovered_count
    || input.pending_count > input.discovered_count
    || input.within_window_count > input.processed_count) invalid();
  const base = Object.fromEntries(countKeys.filter((key) => !["processed_count", "pending_count", "rss_count", "saturated_count"].includes(key))
    .map((key) => [key, input[key]]));
  return Object.freeze({ ...safeDoorkeeperDiscoveryAudit(base, wakeId, recordedAt),
    processed_count: input.processed_count, pending_count: input.pending_count,
    rss_count: input.rss_count, saturated_count: input.saturated_count });
}

function reportMessage(row) {
  const label = row.status === "applied_bundle" ? "申込と証拠保存が完了"
    : row.status === "circuit_open" ? "安全停止" : "今回の新規申込なし";
  return [
    `Connector::: ${label}`,
    `status: ${row.status}`,
    `safe reason: ${row.safe_reason}`,
    `consecutive failures: ${row.consecutive_failure_count}`,
  ].join("\n");
}

function createMinimalProductionOperations(options = {}) {
  const stateDir = privateDirectory(options.stateDir);
  const wakeId = String(options.wakeId || "");
  const occurrenceId = String(options.occurrenceId || "");
  const telegramTarget = String(options.telegramTarget || "").trim();
  const now = options.now || (() => new Date());
  const telegramToken = String(options.telegramToken || "").trim();
  const sendMessage = options.sendMessage || (telegramToken
    ? (message, deliveryOptions) => sendTelegramMessage(telegramToken, deliveryOptions.telegramTarget, message)
    : null);
  if (
    !SAFE_ID.test(wakeId) || !telegramTarget || telegramTarget.length > 200
    || (occurrenceId && (!/^life-manager-connector-native:[A-Za-z0-9._:-]{1,90}$/.test(occurrenceId)
      || occurrenceId.length > 128))
    || typeof now !== "function" || typeof sendMessage !== "function"
  ) invalid();
  const historyFile = path.join(stateDir, "action-history.jsonl");
  const effectIntentFile = path.join(stateDir, "effect-intents.jsonl");
  const reportFile = path.join(stateDir, "wake-reports.jsonl");
  const deliveryFile = path.join(stateDir, "wake-report-deliveries.jsonl");
  const claimFile = path.join(stateDir, "wake-report-send-claims.jsonl");
  const uncertainFile = path.join(stateDir, "wake-report-uncertain.jsonl");
  const discoveryAuditFile = path.join(stateDir, "luma-discovery-audits.jsonl");
  const connpassDiscoveryAuditFile = path.join(stateDir, "connpass-discovery-audits.jsonl");
  const rankingAuditFile = path.join(stateDir, "ranking-audits.jsonl");
  const peatixDiscoveryAuditFile = path.join(stateDir, "peatix-discovery-audits.jsonl");
  const meetupDiscoveryAuditFile = path.join(stateDir, "meetup-discovery-audits.jsonl");
  const doorkeeperDiscoveryAuditFile = path.join(stateDir, "doorkeeper-discovery-audits.jsonl");
  const eventbriteDiscoveryAuditFile = path.join(stateDir, "eventbrite-discovery-audits.jsonl");
  const techPlayDiscoveryAuditFile = path.join(stateDir, "techplay-discovery-audits.jsonl");
  const kokuchproDiscoveryAuditFile = path.join(stateDir, "kokuchpro-discovery-audits.jsonl");

  async function recordAction(input) {
    const action = safeAction(input);
    append(historyFile, Object.freeze({ schema_version: 1, wake_id: wakeId, ...action }));
  }

  function normalizeEffectIntent(input, id, wake, recordedAt) {
    if (!input || typeof input !== "object" || Array.isArray(input)
      || Object.keys(input).sort().join(",") !== "candidate,effect_kind,effect_url") invalid();
    const candidate = input.candidate;
    const provider = String(candidate && candidate.provider || "");
    const eventRef = String(candidate && candidate.event_ref || "");
    const canonicalUrl = String(candidate && candidate.canonical_url || "");
    const effectKind = String(input.effect_kind || "");
    const effectUrl = String(input.effect_url || "");
    let parsed, effectTarget;
    try { parsed = new URL(canonicalUrl); effectTarget = new URL(effectUrl); } catch { invalid(); }
    if (!/^life-manager-connector-native:[A-Za-z0-9._:-]{1,90}$/.test(String(id || ""))
      || String(id).length > 128 || !SAFE_ID.test(String(wake || ""))
      || !SAFE_PROVIDER.test(provider)
      || !eventRef.startsWith(`${provider}-event://event/`)
      || eventRef.length > 200 || /[\x00-\x1f\x7f]/.test(eventRef)
      || canonicalUrl.length > 2_000 || parsed.protocol !== "https:"
      || parsed.username || parsed.password
      || !["registration", "talk_application", "manual_boundary_notice"].includes(effectKind)
      || effectUrl.length > 2_000 || effectTarget.protocol !== "https:"
      || effectTarget.username || effectTarget.password) invalid();
    const readbackCandidate = { provider, event_ref: eventRef, canonical_url: canonicalUrl };
    for (const [key, limit] of [
      ["title", 500], ["ticket_id", 128], ["registration_status", 40],
      ["ticket_price_status", 40], ["venue_name", 2_000], ["venue_address", 2_000],
    ]) {
      if (candidate[key] == null) continue;
      if (typeof candidate[key] !== "string" || !candidate[key]
        || candidate[key].length > limit || /[\x00-\x1f\x7f]/.test(candidate[key])) invalid();
      readbackCandidate[key] = candidate[key];
    }
    for (const key of ["starts_at", "ends_at"]) {
      if (candidate[key] != null) readbackCandidate[key] = exactInstant(candidate[key]);
    }
    if (candidate.ticket_price_minor != null) {
      if (!Number.isInteger(candidate.ticket_price_minor) || candidate.ticket_price_minor < 0) invalid();
      readbackCandidate.ticket_price_minor = candidate.ticket_price_minor;
    }
    return Object.freeze({ schema_version: 1, occurrence_id: id,
      wake_id: wake, provider, event_ref: eventRef, canonical_url: canonicalUrl,
      effect_kind: effectKind, effect_url: effectUrl,
      readback_candidate: Object.freeze(readbackCandidate),
      recorded_at: exactInstant(recordedAt) });
  }

  async function recordEffectIntent(input) {
    const row = normalizeEffectIntent(input, occurrenceId, wakeId, now());
    appendDurable(effectIntentFile, row);
    return row;
  }

  async function listEffectIntents(requestedOccurrenceId) {
    if (!/^life-manager-connector-native:[A-Za-z0-9._:-]{1,90}$/.test(String(requestedOccurrenceId || ""))
      || String(requestedOccurrenceId).length > 128) invalid();
    const rows = readRows(effectIntentFile).map((row) => {
      if (!row || typeof row !== "object" || Array.isArray(row)
        || Object.keys(row).sort().join(",") !== "canonical_url,effect_kind,effect_url,event_ref,occurrence_id,provider,readback_candidate,recorded_at,schema_version,wake_id"
        || row.schema_version !== 1) invalid();
      const canonical = normalizeEffectIntent({ candidate: row.readback_candidate,
        effect_kind: row.effect_kind, effect_url: row.effect_url },
      row.occurrence_id, row.wake_id, row.recorded_at);
      if (JSON.stringify(canonical) !== JSON.stringify(row)) invalid();
      return Object.freeze(row);
    });
    return Object.freeze(rows.filter((row) => row.occurrence_id === requestedOccurrenceId));
  }

  async function recordDiscoveryAudit(input) {
    append(discoveryAuditFile, safeDiscoveryAudit(input, wakeId, exactInstant(now())));
  }

  async function recordConnpassDiscoveryAudit(input) {
    append(connpassDiscoveryAuditFile, safeDiscoveryAudit(input, wakeId, exactInstant(now())));
  }

  async function recordRankingAudit(input) {
    append(rankingAuditFile, safeRankingAudit(input, wakeId, exactInstant(now())));
  }

  async function recordPeatixDiscoveryAudit(input) {
    append(peatixDiscoveryAuditFile, safeDiscoveryAudit(input, wakeId, exactInstant(now())));
  }

  async function recordMeetupDiscoveryAudit(input) {
    append(meetupDiscoveryAuditFile, safeDiscoveryAudit(input, wakeId, exactInstant(now())));
  }

  async function recordDoorkeeperDiscoveryAudit(input) {
    append(doorkeeperDiscoveryAuditFile, safeDoorkeeperDiscoveryAudit(input, wakeId, exactInstant(now())));
  }
  async function recordEventbriteDiscoveryAudit(input) {
    append(eventbriteDiscoveryAuditFile, safeDoorkeeperDiscoveryAudit(input, wakeId, exactInstant(now())));
  }
  async function recordTechPlayDiscoveryAudit(input) {
    append(techPlayDiscoveryAuditFile, safeTechPlayDiscoveryAudit(input, wakeId, exactInstant(now())));
  }
  async function recordKokuchProDiscoveryAudit(input) {
    append(kokuchproDiscoveryAuditFile, safeDoorkeeperDiscoveryAudit(input, wakeId, exactInstant(now())));
  }

  async function reportWake(input) {
    let report = safeReport(input, wakeId, exactInstant(now()));
    const reports = uniqueByWake(readRows(reportFile).map(safeStoredReport));
    const existing = reports.find((row) => row && row.wake_id === wakeId);
    if (existing) {
      const createdAt = exactInstant(existing.created_at);
      const canonical = safeReport(input, wakeId, createdAt);
      if (Object.keys(existing).sort().join(",") !== REPORT_KEYS
        || REPORT_KEYS.split(",").some((key) => existing[key] !== canonical[key])) invalid();
      report = canonical;
    }
    const deliveries = uniqueByWake(readRows(deliveryFile).map(safeDelivery));
    const byWake = new Map(deliveries.map((delivery) => [delivery.wake_id, delivery]));
    const claims = uniqueByWake(readRows(claimFile).map(safeClaim));
    const claimedByWake = new Map(claims.map((claim) => [claim.wake_id, claim]));
    const uncertain = uniqueByWake(readRows(uncertainFile).map(safeUncertain));
    const uncertainByWake = new Map(uncertain.map((quarantine) => [quarantine.wake_id, quarantine]));
    if (!existing) {
      append(reportFile, report);
      reports.push(report);
    }
    async function deliver(current) {
      if (!current || !SAFE_ID.test(String(current.wake_id || ""))) invalid();
      if (uncertainByWake.has(current.wake_id)) throw new Error("Telegram report delivery uncertain");
      let response;
      let reason;
      try {
        response = await sendMessage(reportMessage(current), { telegramTarget, idempotencyKey: current.wake_id });
      } catch {
        reason = "transport";
      }
      if (!reason && response && response.ok === false) {
        reason = response.delivery_unknown === true ? "delivery_unknown" : "provider_rejection";
      }
      let providerId;
      if (!reason) {
        try { providerId = positiveTelegramProviderId(response); }
        catch { reason = "missing_message_id"; }
      }
      if (reason) {
        const quarantine = safeUncertain({
          schema_version: 1,
          wake_id: current.wake_id,
          reason,
          quarantined_at: exactInstant(now()),
        });
        append(uncertainFile, quarantine);
        uncertainByWake.set(current.wake_id, quarantine);
        throw new Error("Telegram report delivery uncertain");
      }
      const delivery = safeDelivery({
        schema_version: 1,
        wake_id: current.wake_id,
        telegram_provider_id: providerId,
        delivered_at: exactInstant(now()),
      });
      append(deliveryFile, delivery);
      byWake.set(current.wake_id, delivery);
    }
    const current = reports.find((row) => row && row.wake_id === wakeId);
    if (!current) invalid();
    // A later wake reports only itself; replaying an older unknown effect can duplicate a visible report.
    if (uncertainByWake.has(wakeId)) throw new Error("Telegram report delivery uncertain");
    if (!byWake.has(wakeId)) {
      if (claimedByWake.has(wakeId)) throw new Error("Telegram report delivery uncertain");
      const claim = safeClaim({ schema_version: 1, wake_id: wakeId, claimed_at: exactInstant(now()) });
      appendDurable(claimFile, claim);
      claimedByWake.set(wakeId, claim);
      await deliver(current);
    }
    const currentDelivery = byWake.get(wakeId);
    if (!currentDelivery) invalid();
    return Object.freeze({ telegram_provider_id: currentDelivery.telegram_provider_id });
  }

  return Object.freeze({
    recordAction, recordEffectIntent, listEffectIntents,
    recordDiscoveryAudit, recordConnpassDiscoveryAudit,
    recordRankingAudit, recordPeatixDiscoveryAudit,
    recordMeetupDiscoveryAudit, recordDoorkeeperDiscoveryAudit, recordEventbriteDiscoveryAudit, reportWake,
    recordTechPlayDiscoveryAudit, recordKokuchProDiscoveryAudit,
  });
}

module.exports = { createMinimalProductionOperations };
