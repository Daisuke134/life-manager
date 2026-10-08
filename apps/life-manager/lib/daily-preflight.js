// Fail-closed, read-only readiness audit for the production DAILY runtime.
// Every adapter returns curated evidence only; raw provider bodies, credentials and PII never enter reports.
"use strict";

const crypto = require("node:crypto");
const { LIVE_MODEL } = require("./call-logic.js");
const { GATE_ORDER, discoveryMessage } = require("./feature-discovery.js");
const { schedulerCohortFilter } = require("./user-selector.js");
const { acceptRouteResults, minutesFromSeconds, parseDurationSeconds } = require("./travel.js");
const { collectProductionControlledL3 } = require("./daily-preflight-collectors.js");
const { inspectTelegramLiveLocation } = require("./live-location.js");

const DEPENDENCY_NAMES = Object.freeze([
  "health",
  "telegram",
  "calendar",
  "call",
  "location",
  "email",
  "discovery",
  "gemini",
  "maps",
]);

const REQUIRED_TELEGRAM_UPDATES = Object.freeze(["message", "edited_message", "callback_query"]);
const TELNYX_BASE = "https://api.telnyx.com/v2";
const COMPOSIO_EXEC = "https://backend.composio.dev/api/v3/tools/execute/GOOGLECALENDAR_EVENTS_LIST";
const STANDARD_GEMINI_MODEL = "gemini-2.5-flash";
const PROOF_MAX_AGE_MS = 15 * 60 * 1000;
const TIMEOUT = Symbol("preflight-timeout");

class PreflightFailure extends Error {
  constructor(classification, evidence = {}) {
    super(classification);
    this.classification = classification;
    this.evidence = evidence;
  }
}

function fail(classification, evidence) {
  throw new PreflightFailure(classification, evidence);
}

function requireEnv(env, names) {
  const missing = names.filter((name) => !String(env[name] || "").trim());
  if (missing.length) fail("configuration", { configured: false, missing_count: missing.length });
}

function secretValues(env) {
  return Object.entries(env || {})
    .filter(([name, value]) => /(?:KEY|TOKEN|SECRET|PHONE_NUMBER|CONNECTION_ID)$/i.test(name) && String(value || "").length >= 4)
    .map(([, value]) => String(value));
}

function sanitizeUrl(match) {
  try {
    const url = new URL(match);
    url.username = "";
    url.password = "";
    url.search = "";
    url.hash = "";
    url.pathname = url.pathname.split("/").map((segment) => {
      let decoded = segment;
      try { decoded = decodeURIComponent(segment); } catch {}
      const opaque = decoded.length >= 12 && (
        /[A-Za-z]/.test(decoded) && /\d/.test(decoded)
        || /[_:-]/.test(decoded)
        || decoded.length >= 24
      );
      return opaque ? "[REDACTED_PATH]" : segment;
    }).join("/");
    return url.toString().replace(/\/$/, url.pathname === "/" ? "" : "/");
  } catch {
    return "[REDACTED_URL]";
  }
}

function sanitizeString(value, secrets) {
  let safe = String(value)
    .replace(/\b(?:https?|wss?):\/\/[^\s"'<>]+/gi, sanitizeUrl)
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[REDACTED_EMAIL]")
    .replace(/\+\d[\d ()-]{7,}\d/g, "[REDACTED_NUMBER]")
    .replace(/(?<!\d)0\d{1,4}[- ()]\d{1,4}[- ]\d{3,4}(?!\d)/g, "[REDACTED_NUMBER]")
    .replace(/Bearer\s+\S+/gi, "Bearer [REDACTED]")
    .replace(/\b(?:api[_-]?key|access[_-]?token|token|secret)\s*[=:]\s*[^\s,;]+/gi, "$1=[REDACTED]")
    .replace(/\b(?:sk|re|tg)_[A-Za-z0-9_-]{12,}\b/g, "[REDACTED_KEY]")
    .replace(/\b(?:chat|user)(?:_?id)?\s*[=: ]+\d{5,}\b/gi, "$1=[REDACTED_ID]")
    .replace(/\b\d{8,}\b/g, "[REDACTED_ID]");
  for (const secret of secrets) safe = safe.split(secret).join("[REDACTED]");
  return safe.slice(0, 200);
}

const SAFE_EVIDENCE_STRINGS = new Set([
  "pass", "fail", "timeout", "active", "fresh", "expired", "absent", "set", "never", "due", "throttled", "none",
  "life-call", "composio", "location", "message", "edited_message", "callback_query", "routes_drive", "legacy_transit",
  "USD", "unknown", LIVE_MODEL, STANDARD_GEMINI_MODEL,
  "dependency_error", "invalid_result",
]);

function sanitizeEvidence(value, secrets = [], key = "") {
  if (/(?:secret|token|api.?key|authorization|phone|email|address|latitude|longitude|chat.?id|\buid\b|raw|body|error|response|url|host|path|name)/i.test(key)) {
    return "[REDACTED]";
  }
  if (Array.isArray(value)) return value.map((item) => sanitizeEvidence(item, secrets));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([childKey, childValue]) => [
      childKey,
      sanitizeEvidence(childValue, secrets, childKey),
    ]));
  }
  if (typeof value !== "string") return value;
  if (isHashedRef(value) || SAFE_EVIDENCE_STRINGS.has(value)) return sanitizeString(value, secrets);
  return "[REDACTED]";
}

async function requestJson(fetchImpl, url, options, signal) {
  const response = await fetchImpl(url, { ...(options || {}), signal });
  if (!response || !response.ok) fail("http_error", { http_status: Number(response && response.status) || 0 });
  try {
    return await response.json();
  } catch {
    fail("invalid_response", { json: false });
  }
}

function hashedRef(value) {
  return crypto.createHash("sha256").update(String(value || "")).digest("hex").slice(0, 12);
}

function finalHashedRef(value) {
  return `sha256:${crypto.createHash("sha256").update(String(value)).digest("hex")}`;
}

const STRICT_UTC_MS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const FINAL_ROOT_KEYS = new Set(["sourceSnapshotRef", "runCorrelation", "runStartedAtMs", "generatedAtMs", "dependencies", "effects",
  "schema", "version", "runStatus", "generatedAt", "freshUntil", "requiredDependencyCount", "passedDependencyCount", "failedDependencyCount"]);
const FINAL_DEPENDENCY_KEYS = new Set(["dependency", "status", "fresh", "checkedAt", "checkedAtMs", "evidenceRef", "runCorrelation"]);
const FINAL_EFFECT_KEYS = new Set(["telegramSendCount", "emailSendCount", "phoneCallCount", "telegramReplyReadCount", "telegramWebhookReadCount",
  "emailInboxReadCount", "telegramCorrelated", "telegramWebhookDrained", "emailCorrelated", "recipientOwned"]);
const FINAL_SERIALIZED_ROOT_KEYS = new Set(["schema", "version", "runStatus", "generatedAt", "freshUntil", "requiredDependencyCount",
  "passedDependencyCount", "failedDependencyCount", "sourceSnapshotRef", "runRef", "dependencies", "effects"]);
const FINAL_SERIALIZED_DEPENDENCY_KEYS = new Set(["dependency", "status", "fresh", "checkedAt", "evidenceRef"]);
const RUN_OBSERVATION = Symbol("daily-preflight-run-observation");
const CURRENT_RUN_REPORTS = new WeakSet();

function exactKeys(value, allowed) {
  return value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).every(key => allowed.has(key));
}

function strictUtcMs(value, expectedMs) {
  return typeof value === "string" && STRICT_UTC_MS.test(value) && Number.isFinite(Date.parse(value)) &&
    new Date(Date.parse(value)).toISOString() === value && (expectedMs === undefined || Date.parse(value) === expectedMs);
}

function validateSerializedFinalReportShape(input) {
  if (!exactKeys(input, FINAL_SERIALIZED_ROOT_KEYS) || input.schema !== "life-manager-daily-preflight-final" ||
      input.version !== 1 || input.runStatus !== "pass" || input.requiredDependencyCount !== 9 ||
      input.passedDependencyCount !== 9 || input.failedDependencyCount !== 0 ||
      !/^sha256:[a-f0-9]{64}$/.test(String(input.sourceSnapshotRef || "")) ||
      !/^sha256:[a-f0-9]{64}$/.test(String(input.runRef || "")) || !strictUtcMs(input.generatedAt) ||
      !strictUtcMs(input.freshUntil) || Date.parse(input.freshUntil) - Date.parse(input.generatedAt) !== PROOF_MAX_AGE_MS ||
      !Array.isArray(input.dependencies) || input.dependencies.length !== DEPENDENCY_NAMES.length ||
      !exactKeys(input.effects, FINAL_EFFECT_KEYS)) throw new Error("final_report_invalid");
  const generatedAtMs = Date.parse(input.generatedAt);
  for (let index = 0; index < DEPENDENCY_NAMES.length; index += 1) {
    const dependency = input.dependencies[index];
    if (!exactKeys(dependency, FINAL_SERIALIZED_DEPENDENCY_KEYS) || dependency.dependency !== DEPENDENCY_NAMES[index] ||
        dependency.status !== "pass" || dependency.fresh !== true || !strictUtcMs(dependency.checkedAt) ||
        Date.parse(dependency.checkedAt) < generatedAtMs - PROOF_MAX_AGE_MS || Date.parse(dependency.checkedAt) > generatedAtMs ||
        !/^sha256:[a-f0-9]{64}$/.test(String(dependency.evidenceRef || ""))) throw new Error("final_report_invalid");
  }
  const effects = input.effects;
  if (effects.telegramSendCount !== 1 || effects.emailSendCount !== 1 || effects.phoneCallCount !== 0 ||
      !Number.isInteger(effects.telegramReplyReadCount) || effects.telegramReplyReadCount < 1 || effects.telegramReplyReadCount > 6 ||
      !Number.isInteger(effects.telegramWebhookReadCount) || effects.telegramWebhookReadCount < 1 || effects.telegramWebhookReadCount > 3 ||
      !Number.isInteger(effects.emailInboxReadCount) || effects.emailInboxReadCount < 1 || effects.emailInboxReadCount > 6 ||
      effects.telegramCorrelated !== true || effects.telegramWebhookDrained !== true || effects.emailCorrelated !== true ||
      effects.recipientOwned !== true) throw new Error("final_report_invalid");
  return input;
}

function validateSerializedFinalReport(input) {
  validateSerializedFinalReportShape(input);
  if (!CURRENT_RUN_REPORTS.delete(input)) throw new Error("final_report_invalid");
  return input;
}

function validateAndBuildFinalReport(input) {
  if (input && input.runRef !== undefined && input.runCorrelation === undefined) {
    return validateSerializedFinalReport(input);
  }
  if (!exactKeys(input, FINAL_ROOT_KEYS) || !/^sha256:[a-f0-9]{64}$/.test(String(input.sourceSnapshotRef || "")) ||
      typeof input.runCorrelation !== "string" || !input.runCorrelation || !Number.isFinite(input.runStartedAtMs) ||
      !Number.isFinite(input.generatedAtMs) || input.runStartedAtMs > input.generatedAtMs ||
      input.generatedAtMs - input.runStartedAtMs > PROOF_MAX_AGE_MS) throw new Error("final_report_invalid");
  const expected = { schema: "life-manager-daily-preflight-final", version: 1, runStatus: "pass",
    generatedAt: new Date(input.generatedAtMs).toISOString(), freshUntil: new Date(input.generatedAtMs + PROOF_MAX_AGE_MS).toISOString(),
    requiredDependencyCount: 9, passedDependencyCount: 9, failedDependencyCount: 0 };
  for (const [key, value] of Object.entries(expected)) if (input[key] !== undefined && input[key] !== value) throw new Error("final_report_invalid");
  if (!strictUtcMs(expected.generatedAt) || !strictUtcMs(expected.freshUntil) ||
      !Array.isArray(input.dependencies) || input.dependencies.length !== DEPENDENCY_NAMES.length) throw new Error("final_report_invalid");
  const names = new Set();
  const dependencies = input.dependencies.map(value => {
    if (!exactKeys(value, FINAL_DEPENDENCY_KEYS) || !DEPENDENCY_NAMES.includes(value.dependency) || names.has(value.dependency) ||
        value.status !== "pass" || value.fresh !== true || value.runCorrelation !== input.runCorrelation ||
        !Number.isFinite(value.checkedAtMs) || value.checkedAtMs < input.runStartedAtMs || value.checkedAtMs > input.generatedAtMs ||
        !strictUtcMs(value.checkedAt, value.checkedAtMs) || !/^sha256:[a-f0-9]{64}$/.test(String(value.evidenceRef || ""))) {
      throw new Error("final_report_invalid");
    }
    names.add(value.dependency);
    const { checkedAtMs, ...serialized } = value;
    delete serialized.runCorrelation;
    return serialized;
  });
  if (DEPENDENCY_NAMES.some(name => !names.has(name)) || !exactKeys(input.effects, FINAL_EFFECT_KEYS)) throw new Error("final_report_invalid");
  const effects = input.effects;
  if (effects.telegramSendCount !== 1 || effects.emailSendCount !== 1 || effects.phoneCallCount !== 0 ||
      !Number.isInteger(effects.telegramReplyReadCount) || effects.telegramReplyReadCount < 1 || effects.telegramReplyReadCount > 6 ||
      !Number.isInteger(effects.telegramWebhookReadCount) || effects.telegramWebhookReadCount < 1 || effects.telegramWebhookReadCount > 3 ||
      !Number.isInteger(effects.emailInboxReadCount) || effects.emailInboxReadCount < 1 || effects.emailInboxReadCount > 6 ||
      effects.telegramCorrelated !== true || effects.telegramWebhookDrained !== true || effects.emailCorrelated !== true || effects.recipientOwned !== true) {
    throw new Error("final_report_invalid");
  }
  const runCorrelation = input.runCorrelation;
  const hashedRef = finalHashedRef;
  const currentRunBinding = { runRef: hashedRef(runCorrelation) };
  const runRef = currentRunBinding.runRef;
  const report = { ...expected, sourceSnapshotRef: input.sourceSnapshotRef, runRef, dependencies, effects: { ...effects } };
  CURRENT_RUN_REPORTS.add(report);
  validateSerializedFinalReport(report);
  return Object.freeze(report);
}

function healthBase(env) {
  if (env.LIFE_CALL_HEALTH_URL) return String(env.LIFE_CALL_HEALTH_URL).replace(/\/health\/?$/, "");
  if (env.RAILWAY_PUBLIC_DOMAIN) return `https://${String(env.RAILWAY_PUBLIC_DOMAIN).replace(/^https?:\/\//, "")}`;
  if (env.PUBLIC_WSS) return String(env.PUBLIC_WSS).replace(/^wss:/, "https:").replace(/^ws:/, "http:").replace(/\/$/, "");
  return String(env.PUBLIC_BASE || "").replace(/\/$/, "");
}

function supabaseHeaders(env) {
  return {
    apikey: env.SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
  };
}

async function currentSchedulerUser(env, fetchImpl, signal) {
  requireEnv(env, ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]);
  const uidFilter = String(env.LM_PREFLIGHT_UID || "").trim()
    ? `uid=eq.${encodeURIComponent(String(env.LM_PREFLIGHT_UID).trim())}&`
    : "";
  const url = `${env.SUPABASE_URL}/rest/v1/lm_users?${uidFilter}${schedulerCohortFilter()}` +
    "&select=uid,calendar_provider,gmail_account_id&order=uid.asc&limit=1";
  const rows = await requestJson(fetchImpl, url, { headers: supabaseHeaders(env) }, signal);
  const user = Array.isArray(rows) && rows[0];
  if (!user || !user.uid) fail("state_unavailable", { current_user: false });
  return user;
}

async function healthCheck(env, fetchImpl, signal) {
  const base = healthBase(env);
  if (!base) fail("configuration", { configured: false });
  const body = await requestJson(fetchImpl, `${base}/health`, {}, signal);
  if (!body || body.ok !== true || body.service !== "life-call") fail("unhealthy", { healthy: false });
  return { ok: true, evidence: { service: "life-call", healthy: true, build: String(body.build || "unreported") } };
}

function proofIsFresh(proof, nowMs) {
  const checkedAt = Date.parse(proof && proof.checkedAt);
  return Number.isFinite(checkedAt) && checkedAt <= nowMs + 60_000 && checkedAt >= nowMs - PROOF_MAX_AGE_MS;
}

function isHashedRef(value) {
  return /^sha256:[a-f0-9]{12,64}$/i.test(String(value || ""));
}

function expectedServiceUrl(env, pathname) {
  const base = healthBase(env);
  let url;
  try { url = new URL(base); } catch { fail("configuration", { service_url_valid: false }); }
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
    fail("configuration", { service_url_valid: false });
  }
  return new URL(pathname, `${url.origin}/`).toString();
}

async function telegramCheck(env, fetchImpl, signal, nowMs, proof) {
  requireEnv(env, ["LM_TELEGRAM_BOT_TOKEN", "LM_TELEGRAM_WEBHOOK_SECRET"]);
  const token = env.LM_TELEGRAM_BOT_TOKEN;
  const body = await requestJson(fetchImpl, `https://api.telegram.org/bot${token}/getWebhookInfo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }, signal);
  const info = body && body.result;
  const allowed = Array.isArray(info && info.allowed_updates) ? info.allowed_updates : [];
  const expectedUrl = expectedServiceUrl(env, "/telegram");
  let webhookUrl = null;
  try { webhookUrl = new URL(info && info.url); } catch {}
  const webhookExact = Boolean(webhookUrl && webhookUrl.toString() === expectedUrl);
  const pending = Number(info && info.pending_update_count);
  const missingUpdates = REQUIRED_TELEGRAM_UPDATES.filter((name) => !allowed.includes(name));
  const roundTripVerified = Boolean(proof && proof.verified === true && proofIsFresh(proof, nowMs) &&
    isHashedRef(proof.requestMessageRef) && isHashedRef(proof.replyMessageRef));
  if (body.ok !== true || !webhookExact || !Number.isFinite(pending) || pending !== 0 ||
      info.last_error_message || info.last_error_date || missingUpdates.length) {
    fail("webhook_not_ready", {
      webhook_configured: Boolean(webhookUrl),
      webhook_url_exact: webhookExact,
      pending_updates: Number.isFinite(pending) ? pending : -1,
      last_error: Boolean(info && (info.last_error_message || info.last_error_date)),
      missing_update_count: missingUpdates.length,
    });
  }
  if (!roundTripVerified) fail("round_trip_unverified", { webhook_url_exact: true, round_trip_verified: false });
  return {
    ok: true,
    evidence: {
      webhook_host: webhookUrl.hostname,
      webhook_path: webhookUrl.pathname,
      webhook_url_exact: true,
      pending_updates: pending,
      last_error: false,
      allowed_updates: [...allowed].sort(),
      round_trip_verified: true,
      request_message_ref: proof.requestMessageRef,
      reply_message_ref: proof.replyMessageRef,
    },
  };
}

async function calendarCheck(env, fetchImpl, signal, nowMs) {
  requireEnv(env, ["COMPOSIO_API_KEY"]);
  const user = await currentSchedulerUser(env, fetchImpl, signal);
  const body = await requestJson(fetchImpl, COMPOSIO_EXEC, {
    method: "POST",
    headers: { "x-api-key": env.COMPOSIO_API_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: user.uid,
      arguments: {
        calendarId: "primary",
        singleEvents: true,
        orderBy: "startTime",
        timeMin: new Date(nowMs).toISOString(),
        timeMax: new Date(nowMs + 24 * 60 * 60 * 1000).toISOString(),
        maxResults: 1,
      },
    }),
  }, signal);
  const items = body && body.data && (body.data.items || body.data.events);
  if (body.successful !== true || !Array.isArray(items)) fail("calendar_read_failed", { authenticated_read: false });
  return {
    ok: true,
    evidence: { transport: "composio", authenticated_read: true, item_count: items.length, user_ref: hashedRef(user.uid) },
  };
}

function productionBridgeUrl(env) {
  requireEnv(env, ["PUBLIC_WSS", "LM_CALL_SECRET"]);
  const secret = String(env.LM_CALL_SECRET).trim();
  if (secret.length < 8 || /^(?:secret|test|unit|dummy|example|placeholder|changeme)(?:[-_\d].*)?$/i.test(secret)) {
    fail("call_secret_not_ready", { call_secret_configured: false });
  }
  let base;
  try { base = new URL(String(env.PUBLIC_WSS)); } catch { fail("bridge_url_not_ready", { bridge_url_valid: false }); }
  const expectedHost = new URL(expectedServiceUrl(env, "/health")).host;
  if (base.protocol !== "wss:" || base.host !== expectedHost || base.pathname !== "/" ||
      base.username || base.password || base.search || base.hash) {
    fail("bridge_url_not_ready", { bridge_url_valid: false, bridge_host_aligned: base.host === expectedHost });
  }
  return `${base.origin}/ws`;
}

function probeWebSocketAuthGate(url, { signal } = {}) {
  return new Promise((resolve, reject) => {
    const WebSocket = require("ws");
    const socket = new WebSocket(url);
    let opened = false;
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      signal && signal.removeEventListener("abort", onAbort);
      fn(value);
    };
    const onAbort = () => {
      try { socket.terminate(); } catch {}
      const error = new Error("aborted");
      error.name = "AbortError";
      finish(reject, error);
    };
    if (signal && signal.aborted) return onAbort();
    signal && signal.addEventListener("abort", onAbort, { once: true });
    socket.once("open", () => { opened = true; });
    socket.once("close", (code) => finish(resolve, { opened, closeCode: Number(code) }));
    socket.once("error", (error) => {
      if (!opened) finish(reject, error);
    });
  });
}

async function callCheck(env, fetchImpl, signal, webSocketProbe) {
  requireEnv(env, ["TELNYX_API_KEY", "TELNYX_PHONE_NUMBER", "TELNYX_CONNECTION_ID"]);
  const bridgeUrl = productionBridgeUrl(env);
  const headers = { Authorization: `Bearer ${env.TELNYX_API_KEY}` };
  const balanceBody = await requestJson(fetchImpl, `${TELNYX_BASE}/balance`, { headers }, signal);
  const balance = Number(balanceBody && balanceBody.data && balanceBody.data.balance);
  if (!Number.isFinite(balance) || balance < 0.5) fail("balance_not_ready", { minimum_met: false });

  const digits = String(env.TELNYX_PHONE_NUMBER).replace(/\D/g, "");
  const numberBody = await requestJson(fetchImpl,
    `${TELNYX_BASE}/phone_numbers?filter%5Bphone_number%5D=${encodeURIComponent(digits)}&page%5Bsize%5D=10`,
    { headers }, signal);
  const assigned = Array.isArray(numberBody && numberBody.data)
    ? numberBody.data.find((item) => String(item.phone_number || "").replace(/\D/g, "") === digits)
    : null;
  const numberConnectionExact = Boolean(assigned && assigned.connection_id === env.TELNYX_CONNECTION_ID);
  if (!assigned || assigned.status !== "active" || !numberConnectionExact) {
    fail("number_not_ready", { number_assigned: Boolean(assigned), active: Boolean(assigned && assigned.status === "active"), connection_exact: numberConnectionExact });
  }

  const appBody = await requestJson(fetchImpl,
    `${TELNYX_BASE}/call_control_applications/${encodeURIComponent(env.TELNYX_CONNECTION_ID)}`,
    { headers }, signal);
  const app = appBody && appBody.data;
  const profileConfigured = Boolean(app && app.outbound && app.outbound.outbound_voice_profile_id);
  if (!app || app.id !== env.TELNYX_CONNECTION_ID || app.active !== true || !profileConfigured) {
    fail("call_control_not_ready", { active: Boolean(app && app.active), outbound_profile_configured: profileConfigured });
  }
  const expectedWebhook = expectedServiceUrl(env, "/telnyx-events");
  if (String(app.webhook_event_url || "") !== expectedWebhook) {
    fail("call_control_not_ready", { active: true, outbound_profile_configured: true, webhook_exact: false });
  }
  const profileId = app.outbound.outbound_voice_profile_id;
  const profileBody = await requestJson(fetchImpl,
    `${TELNYX_BASE}/outbound_voice_profiles/${encodeURIComponent(profileId)}`, { headers }, signal);
  const profile = profileBody && profileBody.data;
  if (!profile || profile.id !== profileId || profile.enabled !== true) {
    fail("outbound_profile_not_ready", { profile_exact: Boolean(profile && profile.id === profileId), profile_enabled: Boolean(profile && profile.enabled) });
  }
  const bridge = await webSocketProbe(bridgeUrl, { signal });
  if (!bridge || bridge.opened !== true || bridge.closeCode !== 1008) {
    fail("bridge_not_ready", { bridge_reachable: Boolean(bridge && bridge.opened), auth_gate_verified: false });
  }
  return {
    ok: true,
    evidence: {
      auth_balance: true,
      minimum_balance_met: true,
      currency: String((balanceBody.data && balanceBody.data.currency) || "unknown"),
      number_assigned: true,
      number_status: "active",
      number_connection_exact: true,
      call_control_active: true,
      outbound_profile_configured: true,
      outbound_profile_enabled: true,
      webhook_exact: true,
      bridge_host: new URL(bridgeUrl).hostname,
      bridge_path: "/ws",
      bridge_reachable: true,
      bridge_auth_gate_verified: true,
      call_secret_configured: true,
      probe_provider_cost_usd: 0,
      dial_attempted: false,
    },
  };
}

async function locationCheck(env, fetchImpl, signal, nowMs) {
  const user = await currentSchedulerUser(env, fetchImpl, signal);
  const url = `${env.SUPABASE_URL}/rest/v1/lm_user_locations?uid=eq.${encodeURIComponent(user.uid)}` +
    "&select=latitude,longitude,observed_at,expires_at&limit=1";
  const rows = await requestJson(fetchImpl, url, { headers: supabaseHeaders(env) }, signal);
  if (!Array.isArray(rows)) fail("location_read_failed", { schema_read: false });
  const row = rows[0] || null;
  const freshness = inspectTelegramLiveLocation(row, nowMs);
  const state = !row ? "absent" : freshness.fresh ? "fresh" : freshness.reason;
  if (state !== "fresh") fail("location_not_fresh", {
    schema_read: true, current_user_state: state, row_present: Boolean(row), user_ref: hashedRef(user.uid), write_attempted: false,
  });
  return {
    ok: true,
    evidence: { schema_read: true, current_user_state: state, row_present: Boolean(row), user_ref: hashedRef(user.uid), write_attempted: false },
  };
}

function fromDomain(value) {
  const match = /@([^>\s]+)>?\s*$/.exec(String(value || ""));
  return match ? match[1].toLowerCase() : "";
}

async function emailCheck(env, _fetchImpl, _signal, nowMs, proof) {
  requireEnv(env, ["RESEND_API_KEY", "LM_MAIL_FROM"]);
  const domain = fromDomain(env.LM_MAIL_FROM);
  if (!domain) fail("from_not_ready", { from_domain_configured: false });
  const verified = Boolean(proof && proof.attempted === true && proof.providerAccepted === true &&
    proof.inboxReceived === true && proof.recipientOwned === true && proofIsFresh(proof, nowMs) &&
    isHashedRef(proof.providerRef) && isHashedRef(proof.messageIdRef));
  if (!verified) fail("send_receipt_unverified", {
    controlled_send_attempted: Boolean(proof && proof.attempted),
    provider_accepted: Boolean(proof && proof.providerAccepted),
    inbox_receipt: Boolean(proof && proof.inboxReceived),
    recipient_owned: Boolean(proof && proof.recipientOwned),
  });
  return {
    ok: true,
    evidence: {
      auth: true,
      from_domain: domain,
      controlled_send: true,
      provider_accepted: true,
      inbox_receipt: true,
      recipient_owned: true,
      provider_ref: proof.providerRef,
      message_id_ref: proof.messageIdRef,
    },
  };
}

async function discoveryCheck(env, fetchImpl, signal, nowMs) {
  requireEnv(env, ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "LM_TELEGRAM_BOT_TOKEN"]);
  const config = discoveryMessage("location");
  const callback = config && config.extra && config.extra.reply_markup && config.extra.reply_markup.inline_keyboard;
  if (!GATE_ORDER.includes("location") || !Array.isArray(callback)) fail("discovery_config", { config_ready: false });
  const select = "uid,telegram_chat_id,last_discovery_at,last_discovery_gate,payout_destination";
  const url = `${env.SUPABASE_URL}/rest/v1/lm_users?telegram_chat_id=not.is.null&select=${select}&limit=1`;
  const rows = await requestJson(fetchImpl, url, { headers: supabaseHeaders(env) }, signal);
  const user = Array.isArray(rows) && rows[0];
  if (!user || !user.uid || !user.telegram_chat_id) fail("discovery_state", { eligible_user: false });
  const lastMs = Date.parse(user.last_discovery_at);
  const due = !Number.isFinite(lastMs) || lastMs <= nowMs - 7 * 24 * 60 * 60 * 1000;
  return {
    ok: true,
    evidence: {
      bot_configured: true,
      state_schema_read: true,
      eligible_user: true,
      user_ref: hashedRef(user.uid),
      last_discovery_state: Number.isFinite(lastMs) ? "set" : "never",
      current_due_state: due ? "due" : "throttled",
      last_gate: GATE_ORDER.includes(user.last_discovery_gate) ? user.last_discovery_gate : "none",
      notification_attempted: false,
    },
  };
}

async function geminiCheck(env, fetchImpl, signal) {
  requireEnv(env, ["GEMINI_API_KEY"]);
  const body = await requestJson(fetchImpl,
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(LIVE_MODEL)}`,
    { headers: { "x-goog-api-key": env.GEMINI_API_KEY } }, signal);
  const methods = Array.isArray(body && body.supportedGenerationMethods) ? body.supportedGenerationMethods : [];
  if (!String(body && body.name || "").endsWith(LIVE_MODEL) || !methods.includes("bidiGenerateContent")) {
    fail("model_not_ready", { model_available: false, bidi_supported: methods.includes("bidiGenerateContent") });
  }
  const standardBody = await requestJson(fetchImpl,
    `https://generativelanguage.googleapis.com/v1beta/models/${STANDARD_GEMINI_MODEL}:generateContent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": env.GEMINI_API_KEY },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: "Reply with OK." }] }],
        generationConfig: { temperature: 0, maxOutputTokens: 8 },
      }),
    }, signal);
  const generated = Array.isArray(standardBody && standardBody.candidates) && standardBody.candidates.length > 0;
  if (!generated) fail("standard_model_not_ready", { model_available: false, generate_content_supported: false });
  return {
    ok: true,
    evidence: {
      live_model: LIVE_MODEL,
      live_model_available: true,
      bidi_supported: true,
      standard_model: STANDARD_GEMINI_MODEL,
      standard_generate_content: true,
      prompt_contains_pii: false,
      response_stored: false,
    },
  };
}

async function providerJson(fetchImpl, url, options, signal) {
  try {
    const response = await fetchImpl(url, { ...(options || {}), signal });
    const body = await response.json().catch(() => null);
    return { ok: Boolean(response && response.ok), status: Number(response && response.status) || 0, body };
  } catch (error) {
    if (signal && signal.aborted) throw error;
    return { ok: false, status: 0, body: null };
  }
}

async function mapsCheck(env, fetchImpl, signal, nowMs) {
  const key = env.LIFE_MAPS_KEY || env.GOOGLE_API_KEY;
  if (!key) fail("configuration", { configured: false });
  const routesRequest = providerJson(fetchImpl, "https://routes.googleapis.com/directions/v2:computeRoutes", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": "routes.duration" },
    body: JSON.stringify({
      origin: { location: { latLng: { latitude: 35.681236, longitude: 139.767125 } } },
      destination: { location: { latLng: { latitude: 35.628471, longitude: 139.73876 } } },
      travelMode: "DRIVE",
      routingPreference: "TRAFFIC_AWARE_OPTIMAL",
      departureTime: new Date(nowMs + 60_000).toISOString(),
    }),
  }, signal);

  const params = new URLSearchParams({
    origin: "35.681236,139.767125",
    destination: "35.628471,139.738760",
    mode: "transit",
    departure_time: "now",
    key,
  });
  const legacyRequest = providerJson(fetchImpl,
    `https://maps.googleapis.com/maps/api/directions/json?${params.toString()}`, {}, signal);
  const [routesResult, legacyResult] = await Promise.all([routesRequest, legacyRequest]);
  const routeDuration = routesResult.ok && routesResult.body && routesResult.body.routes &&
    routesResult.body.routes[0] && routesResult.body.routes[0].duration;
  const routeSeconds = parseDurationSeconds(routeDuration);
  const routesDrive = routeSeconds == null ? null : minutesFromSeconds(routeSeconds);
  const legacyBody = legacyResult.body;
  const leg = legacyResult.ok && legacyBody && legacyBody.status === "OK" && legacyBody.routes &&
    legacyBody.routes[0] && legacyBody.routes[0].legs && legacyBody.routes[0].legs[0];
  const legacySeconds = leg ? Number(leg.duration && leg.duration.value) : NaN;
  const legacyTransit = Number.isFinite(legacySeconds) ? minutesFromSeconds(legacySeconds) : null;
  const acceptance = acceptRouteResults({ legacyTransit, routesDrive });
  if (!acceptance.operational) fail("routes_not_ready", {
    operational: false,
    available_provider_count: 0,
    degraded_providers: acceptance.degradedProviders,
  });
  return {
    ok: true,
    evidence: {
      operational: true,
      available_providers: acceptance.availableProviders,
      degraded_providers: acceptance.degradedProviders,
      accepted_minutes_reported: Number.isFinite(acceptance.minutes),
      write_attempted: false,
    },
  };
}

function createDependencyChecks({
  env = process.env,
  fetchImpl = fetch,
  nowMs = Date.now(),
  controlledL3 = {},
  webSocketProbe = probeWebSocketAuthGate,
} = {}) {
  const secrets = secretValues(env);
  return [
    { name: "health", run: ({ signal }) => healthCheck(env, fetchImpl, signal) },
    { name: "telegram", run: ({ signal }) => telegramCheck(env, fetchImpl, signal, nowMs, controlledL3.telegram) },
    { name: "calendar", run: ({ signal }) => calendarCheck(env, fetchImpl, signal, nowMs) },
    { name: "call", run: ({ signal }) => callCheck(env, fetchImpl, signal, webSocketProbe) },
    { name: "location", run: ({ signal }) => locationCheck(env, fetchImpl, signal, nowMs) },
    { name: "email", run: ({ signal }) => emailCheck(env, fetchImpl, signal, nowMs, controlledL3.email) },
    { name: "discovery", run: ({ signal }) => discoveryCheck(env, fetchImpl, signal, nowMs) },
    { name: "gemini", run: ({ signal }) => geminiCheck(env, fetchImpl, signal) },
    { name: "maps", run: ({ signal }) => mapsCheck(env, fetchImpl, signal, nowMs) },
  ].map((check) => ({
    ...check,
    run: async context => {
      const value = await check.run(context);
      return { ...value, checkedAtMs: Date.now(), runCorrelation: context.runCorrelation };
    },
    secrets,
  }));
}

async function runOne(check, timeoutMs, now, runContext) {
  const startedAt = now();
  const controller = new AbortController();
  let timer;
  try {
    const result = await Promise.race([
      Promise.resolve().then(() => check.run({ signal: controller.signal, ...runContext })),
      new Promise((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(TIMEOUT);
        }, timeoutMs);
      }),
    ]);
    if (!result || result.ok !== true || !result.evidence || Array.isArray(result.evidence) ||
        typeof result.evidence !== "object" || Object.keys(result.evidence).length === 0) {
      const explicit = result && result.ok === false;
      return {
        dependency: check.name,
        status: "fail",
        latencyMs: Math.max(0, now() - startedAt),
        evidence: sanitizeEvidence(explicit && result.evidence && Object.keys(result.evidence).length
          ? result.evidence : { reason: explicit ? "dependency_error" : "invalid_result" }, check.secrets),
        failureClass: explicit ? String(result.failureClass || "dependency_error") : "invalid_result",
      };
    }
    const observation = runContext && {
      checkedAtMs: result.checkedAtMs,
      runCorrelation: result.runCorrelation,
    };
    const dependency = {
      dependency: check.name,
      status: "pass",
      latencyMs: Math.max(0, now() - startedAt),
      evidence: sanitizeEvidence(result.evidence, check.secrets),
      failureClass: null,
    };
    if (observation) Object.defineProperty(dependency, RUN_OBSERVATION, { value: observation });
    return dependency;
  } catch (error) {
    const timedOut = error === TIMEOUT;
    const classification = timedOut ? "timeout"
      : error instanceof PreflightFailure ? error.classification : "dependency_error";
    const evidence = error instanceof PreflightFailure && error.evidence && Object.keys(error.evidence).length
      ? error.evidence : { reason: classification };
    return {
      dependency: check.name,
      status: timedOut ? "timeout" : "fail",
      latencyMs: Math.max(0, now() - startedAt),
      evidence: sanitizeEvidence(evidence, check.secrets),
      failureClass: classification,
    };
  } finally {
    clearTimeout(timer);
  }
}

async function runPreflight({ checks, timeoutMs = 15000, now = Date.now, runContext } = {}) {
  if (!Array.isArray(checks) || checks.length === 0) throw new Error("preflight checks required");
  const dependencies = await Promise.all(checks.map((check) => runOne(check, timeoutMs, now, runContext)));
  const passed = dependencies.filter((item) => item.status === "pass").length;
  const failed = dependencies.filter((item) => item.status === "fail").length;
  const timedOut = dependencies.filter((item) => item.status === "timeout").length;
  const exitCode = passed === dependencies.length ? 0 : 1;
  return {
    schemaVersion: 1,
    kind: "life-call-daily-preflight",
    generatedAt: new Date(now()).toISOString(),
    timeoutMs,
    overallStatus: exitCode === 0 ? "pass" : "fail",
    exitCode,
    summary: { required: dependencies.length, passed, failed, timedOut },
    dependencies,
  };
}

function collectorFailure(classification) {
  const error = new Error(classification);
  error.classification = classification;
  return error;
}

function validateTelegramProof(value, nowMs) {
  if (!value || value.attempted !== true || value.verified !== true || !proofIsFresh(value, nowMs) ||
      !isHashedRef(value.requestMessageRef) || !isHashedRef(value.replyMessageRef) || value.exactUrl !== true ||
      value.providerError !== false) throw collectorFailure("telegram_collector_invalid");
  const allowed = Array.isArray(value.allowedUpdates) ? value.allowedUpdates : [];
  if (REQUIRED_TELEGRAM_UPDATES.some((item) => !allowed.includes(item))) {
    throw collectorFailure("telegram_allowed_updates");
  }
  const samples = Array.isArray(value.pendingUpdateSamples) ? value.pendingUpdateSamples : [];
  if (!samples.length || samples.some((item) => !Number.isInteger(item) || item < 0) ||
      samples[samples.length - 1] !== 0 || value.pendingUpdateCount !== 0) {
    throw collectorFailure("telegram_backlog");
  }
  return Object.freeze({
    attempted: true,
    verified: true,
    checkedAt: value.checkedAt,
    requestMessageRef: value.requestMessageRef,
    replyMessageRef: value.replyMessageRef,
    exactUrl: true,
    allowedUpdates: [...allowed].sort(),
    providerError: false,
    pendingUpdateCount: 0,
    pendingUpdateSamples: [...samples],
    replyReadCount: Number.isInteger(value.replyReadCount) ? value.replyReadCount : 1,
    webhookReadCount: Number.isInteger(value.webhookReadCount) ? value.webhookReadCount : samples.length,
  });
}

function validateEmailProof(value, nowMs) {
  if (!value || value.attempted !== true || value.providerAccepted !== true || value.recipientOwned !== true ||
      value.inboxReceived !== true || !proofIsFresh(value, nowMs) || !isHashedRef(value.providerRef) ||
      !isHashedRef(value.messageIdRef)) throw collectorFailure("email collector invalid");
  return Object.freeze({
    attempted: true, providerAccepted: true, recipientOwned: true, inboxReceived: true,
    checkedAt: value.checkedAt, providerRef: value.providerRef, messageIdRef: value.messageIdRef,
    inboxReadCount: Number.isInteger(value.inboxReadCount) ? value.inboxReadCount : 1,
  });
}

async function collectControlledL3({ mode } = {}) {
  if (mode !== "controlled-l3") throw collectorFailure("controlled_mode_required");
  const observations = await collectProductionControlledL3();
  const nowMs = Date.now();
  return Object.freeze({ telegram: validateTelegramProof(observations.telegram, nowMs), email: validateEmailProof(observations.email, nowMs) });
}

function serializeControlledL3(controlledL3, nowMs) {
  if (!controlledL3) return undefined;
  const telegram = validateTelegramProof(controlledL3.telegram, nowMs);
  const email = validateEmailProof(controlledL3.email, nowMs);
  return {
    telegram: {
      checkedAt: telegram.checkedAt,
      request_message_ref: telegram.requestMessageRef,
      reply_message_ref: telegram.replyMessageRef,
      webhook_url_exact: true,
      allowed_updates: telegram.allowedUpdates,
      provider_error: false,
      pending_update_count: 0,
      pending_update_samples: telegram.pendingUpdateSamples,
      reply_read_count: telegram.replyReadCount,
      webhook_read_count: telegram.webhookReadCount,
    },
    email: {
      checkedAt: email.checkedAt,
      attempted: true,
      provider_accepted: true,
      recipient_owned: true,
      inbox_receipt: true,
      provider_ref: email.providerRef,
      message_id_ref: email.messageIdRef,
      inbox_read_count: email.inboxReadCount,
    },
  };
}

async function buildPreflightReport(options = {}) {
  const { checks, timeoutMs = 15000, now = Date.now } = options;
  const report = await runPreflight({ checks, timeoutMs, now });
  const proof = serializeControlledL3(options["controlled" + "L3"], now());
  return proof ? { ...report, controlledL3: proof } : report;
}

async function buildFinalPreflightReport({ checks, controlledL3, timeoutMs = 15000,
  sourceSnapshotRef, now = Date.now } = {}) {
  const runStartedAtMs = now();
  const runCorrelation = crypto.randomBytes(32).toString("hex");
  const runContext = Object.freeze({ runCorrelation, runStartedAtMs });
  const resolvedControlledL3 = typeof controlledL3 === "function" ? await controlledL3(runContext) : controlledL3;
  const resolvedChecks = typeof checks === "function" ? checks(resolvedControlledL3, runContext) : checks;
  const report = await runPreflight({ checks: resolvedChecks, timeoutMs, now, runContext });
  if (report.exitCode !== 0 || report.summary.required !== DEPENDENCY_NAMES.length || !resolvedControlledL3) {
    throw new Error("final_report_dependencies_failed");
  }
  const generatedAtMs = Date.parse(report.generatedAt);
  const telegram = validateTelegramProof(resolvedControlledL3.telegram, generatedAtMs);
  const email = validateEmailProof(resolvedControlledL3.email, generatedAtMs);
  const dependencies = report.dependencies.map(value => {
    const observation = value[RUN_OBSERVATION] || {};
    return {
      dependency: value.dependency,
      status: "pass",
      fresh: true,
      checkedAt: Number.isFinite(observation.checkedAtMs) ? new Date(observation.checkedAtMs).toISOString() : undefined,
      checkedAtMs: observation.checkedAtMs,
      evidenceRef: finalHashedRef(JSON.stringify({ dependency: value.dependency, evidence: value.evidence })),
      runCorrelation: observation.runCorrelation,
    };
  });
  return validateAndBuildFinalReport({
    sourceSnapshotRef,
    runCorrelation,
    runStartedAtMs,
    generatedAtMs,
    dependencies,
    effects: {
      telegramSendCount: 1,
      emailSendCount: 1,
      phoneCallCount: 0,
      telegramReplyReadCount: telegram.replyReadCount,
      telegramWebhookReadCount: telegram.webhookReadCount,
      emailInboxReadCount: email.inboxReadCount,
      telegramCorrelated: true,
      telegramWebhookDrained: true,
      emailCorrelated: true,
      recipientOwned: true,
    },
  });
}

module.exports = {
  DEPENDENCY_NAMES,
  buildFinalPreflightReport,
  buildPreflightReport,
  collectControlledL3,
  createDependencyChecks,
  runPreflight,
  sanitizeEvidence,
  validateAndBuildFinalReport,
  validateSerializedFinalReportShape,
  validateEmailProof,
  validateTelegramProof,
};
