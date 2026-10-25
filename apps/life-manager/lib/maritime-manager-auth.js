"use strict";

const { createWebAuthClient, createWebCsrfToken, ensureWebUser, publicOrigin,
  csrfSecret, hasVerifiedGoogleIdentity } = require("./web-auth.js");
const SIGNUP_PATH = "/auth/maritime/email";
const CONFIRM_PATH = "/auth/maritime/confirm";
function enabled(options) {
  return (options.env || process.env).LM_MARITIME_MANAGER_EMAIL_ENABLED === "1";
}
function send(res, status, body, extra = {}) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store",
    "referrer-policy": "no-referrer", "x-content-type-options": "nosniff", ...extra });
  res.end(body == null ? "" : JSON.stringify(body));
}
function clientFor(req, res, options) {
  return (options.createClient || createWebAuthClient)(req, res, options);
}
async function resolveMaritimeManagerUser(req, res, options = {}) {
  if (!enabled(options)) return null;
  try {
    const client = clientFor(req, res, options);
    const result = await client.auth.getUser();
    const user = result?.data?.user;
    if (result?.error || !user || !user.email || !Number.isFinite(Date.parse(user.email_confirmed_at))
      || !hasVerifiedGoogleIdentity(user)) return null;
    const uid = await (options.ensureWebUserImpl || ensureWebUser)(user.id, options);
    return { uid, subject: user.id, email: user.email,
      csrf: createWebCsrfToken(uid, csrfSecret(options)) };
  } catch { return null; }
}
async function readMaritimeBody(req) {
  const mime = String(req.headers?.["content-type"] || "").split(";")[0].trim().toLowerCase();
  if (!["application/json", "application/x-www-form-urlencoded"].includes(mime)) throw new Error("invalid_body");
  let text = "";
  for await (const chunk of req) {
    text += chunk.toString("utf8");
    if (Buffer.byteLength(text) > 4096) throw new Error("invalid_body");
  }
  let body;
  if (mime === "application/json") body = JSON.parse(text);
  else {
    const params = new URLSearchParams(text);
    if ([...new Set(params.keys())].some(key => params.getAll(key).length !== 1)) throw new Error("invalid_body");
    body = Object.fromEntries(params);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("invalid_body");
  return body;
}
async function handleMaritimeManagerAuth(req, res) {
  const url = new URL(req.url || "/", "http://localhost");
  if (![SIGNUP_PATH, CONFIRM_PATH].includes(url.pathname)) return false;
  send(res, 410, { error: "google_sign_in_required" });
  return true;
}
async function managerReady(row, options) {
  if (row?.status !== "active" || row.paused_at || !row.agent_id) return false;
  const job = require("./maritime-manager-runtime.js").buildMaritimeManagerProvisionJob({
    tenantId: row.uid, releaseSha: row.release_sha, phase: "configure",
  });
  const receipt = await (options.readCommonReceipt || require("./runtime-job-store.js").readCommonReceipt)({
    tenantId: row.uid, jobId: job.job_id, attempt: 1,
  }, options.storeOptions || {});
  const ref = `maritime-agent://${row.agent_id}`;
  return Boolean(receipt && ["verified", "reconciled"].includes(receipt.outcome) && receipt.provider === "maritime"
    && receipt.loop_id === "maritime.manager" && receipt.external_ref === ref && receipt.evidence_refs?.includes(ref));
}
async function handleMaritimeManagerActivate(req, res, options = {}) {
  const path = new URL(req.url || "/", "http://localhost").pathname;
  if (path !== "/maritime/activate") return false;
  if (!enabled(options)) { send(res, 503, { error: "manager_unavailable" }); return true; }
  if (req.method !== "POST") { send(res, 405, { error: "method_not_allowed" }, { allow: "POST" }); return true; }
  let origin;
  try { origin = publicOrigin(req, options); }
  catch { send(res, 503, { error: "manager_unavailable" }); return true; }
  if (req.headers?.origin !== origin) { send(res, 403, { error: "origin_rejected" }); return true; }
  const user = await resolveMaritimeManagerUser(req, res, options);
  if (!user) { send(res, 401, { error: "authentication_required" }); return true; }
  const supplied = Buffer.from(String(req.headers?.["x-lm-web-csrf"] || ""));
  const expected = Buffer.from(user.csrf);
  if (supplied.length !== expected.length || !require("node:crypto").timingSafeEqual(supplied, expected)) {
    send(res, 403, { error: "csrf_rejected" }); return true;
  }
  const { MANAGER_CONSENT_VERSION, normalizeMaritimeSource, createMaritimeDistributionStore } = require("./maritime-distribution.js");
  let body;
  try {
    body = await readMaritimeBody(req);
    if (Object.keys(body).some(key => !["consentVersion", "source", "timezone", "attribution"].includes(key))
      || body.consentVersion !== MANAGER_CONSENT_VERSION || (body.source != null && typeof body.source !== "string")
      || (body.timezone != null && typeof body.timezone !== "string")
      || (body.attribution != null && (typeof body.attribution !== "object" || Array.isArray(body.attribution)))) throw new Error("invalid_activation");
    new Intl.DateTimeFormat("en", { timeZone: body.timezone || "UTC" });
  } catch { send(res, 400, { error: "invalid_activation" }); return true; }
  const env = options.env || process.env;
  const releaseSha = options.releaseSha || env.LM_MARITIME_MANAGER_IMAGE_RELEASE_SHA;
  if (!/^[0-9a-f]{40}$/.test(String(releaseSha || ""))) { send(res, 503, { error: "release_unavailable" }); return true; }
  try {
    const lock = options.withControlLock || ((uid, operation) => require("./runtime-job-store.js").withRuntimeTenantControlLock({ tenantId: uid }, operation, options.storeOptions || {}));
    await lock(user.uid, async () => {
    const store = options.managerStore || require("./maritime-manager-store.js").createMaritimeManagerStore({ env });
    const existing = await store.read(user.uid);
    if (existing?.status === "paused" || existing?.paused_at) { send(res, 409, { error: "manager_paused" }); return true; }
    if (existing?.status === "effect_unknown") { send(res, 409, { error: "manager_reconciling" }); return true; }
    if (existing?.status === "active") {
      const ready = await managerReady(existing, options); send(res, ready ? 200 : 202, { status: ready ? "active" : "pending" }); return true;
    }
    const source = normalizeMaritimeSource(body.source || "direct");
    const distribution = options.distributionStore || createMaritimeDistributionStore({ env });
    const consent = await distribution.accept(user.uid, source);
    if (!consent?.ok) { send(res, consent?.status === "capacity_full" ? 429 : 503, { error: consent?.status === "capacity_full" ? "capacity_full" : "consent_unavailable" }); return true; }
    const row = await store.enroll({ uid: user.uid, authSubject: user.subject, email: user.email,
      timezone: body.timezone || "UTC", source, consentVersion: MANAGER_CONSENT_VERSION, releaseSha });
    if (row.status === "paused" || row.paused_at) { send(res, 409, { error: "manager_paused" }); return true; }
    if (row.status === "effect_unknown") { send(res, 409, { error: "manager_reconciling" }); return true; }
    const attribution = require("./web-attribution.js").sanitizeWebAttribution(body.attribution);
    if (Object.keys(attribution).length) {
      try { await (options.storeFirstTouch || require("./web-auth.js").storeWebFirstTouch)(user.uid, attribution, { ...options, env }); }
      catch { /* Acquisition telemetry cannot authorize or duplicate business work. */ }
    }
    const job = require("./maritime-manager-runtime.js").buildMaritimeManagerProvisionJob({ tenantId: user.uid, releaseSha: row.release_sha });
    const queued = await (options.enqueueJob || require("./runtime-job-store.js").enqueueJob)(job);
    if (!queued || typeof queued.created !== "boolean" || queued.job?.job_id !== job.job_id
      || queued.job?.tenant_id !== user.uid) throw new Error("enqueue_receipt_invalid");
    if (queued.job.status === "dead_letter") { send(res, 503, { error: "provision_failed" }); return true; }
    if (queued.job.status === "reconciling") { send(res, 409, { error: "manager_reconciling" }); return true; }
    if (queued.job.status === "completed") {
      const latest = await store.read(user.uid);
      if (latest?.status === "active" && latest.agent_id && !latest.paused_at) {
        const ready = await managerReady(latest, options); send(res, ready ? 200 : 202, { status: ready ? "active" : "pending" });
      }
      else send(res, 409, { error: "provision_state_unconfirmed" });
      return true;
    }
    if (!["queued", "running"].includes(queued.job.status)) throw new Error("enqueue_state_invalid");
    send(res, 202, { status: "pending", jobCreated: queued.created });
    });
  } catch { send(res, 503, { error: "activation_unavailable" }); }
  return true;
}
async function handleMaritimeManagerStop(req, res, options = {}) {
  if (new URL(req.url || "/", "http://localhost").pathname !== "/maritime/stop") return false;
  if (!enabled(options)) { send(res, 503, { error: "manager_unavailable" }); return true; }
  if (req.method !== "POST") { send(res, 405, { error: "method_not_allowed" }, { allow: "POST" }); return true; }
  let origin;
  try { origin = publicOrigin(req, options); } catch { send(res, 503, { error: "manager_unavailable" }); return true; }
  if (req.headers?.origin !== origin) { send(res, 403, { error: "origin_rejected" }); return true; }
  const user = await resolveMaritimeManagerUser(req, res, options);
  if (!user) { send(res, 401, { error: "authentication_required" }); return true; }
  const supplied = Buffer.from(String(req.headers?.["x-lm-web-csrf"] || "")), expected = Buffer.from(user.csrf);
  if (supplied.length !== expected.length || !require("node:crypto").timingSafeEqual(supplied, expected)) {
    send(res, 403, { error: "csrf_rejected" }); return true;
  }
  try { if (Object.keys(await readMaritimeBody(req)).length) throw new Error(); }
  catch { send(res, 400, { error: "invalid_stop" }); return true; }
  let paused = false;
  try {
    const store = options.managerStore || require("./maritime-manager-store.js").createMaritimeManagerStore({ env: options.env || process.env });
    const existing = await store.read(user.uid);
    if (!existing) { send(res, 404, { error: "manager_not_found" }); return true; }
    const row = await store.pause(user.uid);
    if (!row || row.uid !== user.uid || row.status !== "paused" || !row.paused_at) throw new Error();
    paused = true;
    const job = require("./maritime-manager-runtime.js").buildMaritimeManagerProvisionJob({ tenantId: user.uid, releaseSha: row.release_sha, phase: "pause" });
    const queued = await (options.enqueueJob || require("./runtime-job-store.js").enqueueJob)(job, options.storeOptions || {});
    if (!queued?.job || queued.job.job_id !== job.job_id || queued.job.tenant_id !== user.uid) throw new Error();
    const pending = queued.job.status !== "completed";
    send(res, pending ? 202 : 200, { status: "paused", cleanupPending: pending });
  } catch { send(res, 503, { ...(paused ? { status: "paused", cleanupPending: true } : {}), error: "stop_cleanup_unconfirmed" }); }
  return true;
}
async function handleMaritimeManagerPage(req, res, options = {}) {
  const url = new URL(req.url || "/", "http://localhost");
  if (url.pathname !== "/maritime") return false;
  if (!enabled(options)) { send(res, 503, { error: "manager_unavailable" }); return true; }
  if (req.method !== "GET") { send(res, 405, { error: "method_not_allowed" }, { allow: "GET" }); return true; }
  const { normalizeMaritimeSource, createMaritimeDistributionStore, renderMaritimeLanding } = require("./maritime-distribution.js");
  const source = normalizeMaritimeSource(url.searchParams.get("source") || "direct");
  const language = String(url.searchParams.get("lang") || "").toLowerCase().startsWith("ja") ? "ja" : "en";
  try {
    const user = await resolveMaritimeManagerUser(req, res, options);
    let state = null, workbench = null, workbenchUnavailable = false;
    if (user) {
      const store = options.managerStore || require("./maritime-manager-store.js").createMaritimeManagerStore({ env: options.env || process.env });
      const row = await store.read(user.uid);
      state = row?.status || null;
      if (state === "active" && !await managerReady(row, options)) state = "provisioning";
      if (state === "active") {
        try { workbench = await require("./maritime-manager-workbench.js").readMaritimeManagerWorkbench({ uid: user.uid }, options); }
        catch { workbenchUnavailable = true; }
      }
      void require("./maritime-manager-usage.js").observeMaritimeUsage("returned", user.uid, signal => (options.recordReturn || require("./maritime-manager-usage.js").recordMaritimeManagerReturn)(user.uid, { ...options, signal, request: req, managerStore: store }), options);
    }
    const distribution = options.distributionStore || createMaritimeDistributionStore({ env: options.env || process.env });
    void Promise.resolve(distribution.recordAnonymousEvent("maritime_landing_view", source)).catch(() => {});
    res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "vary": "Cookie",
      "referrer-policy": "no-referrer", "x-content-type-options": "nosniff",
      "content-security-policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" });
    res.end(renderMaritimeLanding({ source, language, user, state, workbench, workbenchUnavailable,
      telegramAvailable: options.telegramAvailable === true,
      authError: url.searchParams.get("auth_error") === "connection" ? "connection" : null }));
  } catch { send(res, 503, { error: "manager_unavailable" }); }
  return true;
}
module.exports = { handleMaritimeManagerAuth, resolveMaritimeManagerUser, handleMaritimeManagerActivate, handleMaritimeManagerPage, handleMaritimeManagerStop };
