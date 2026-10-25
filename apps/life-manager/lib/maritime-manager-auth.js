"use strict";

const { createWebAuthClient, createWebCsrfToken, ensureWebUser, publicOrigin,
  hasPkceVerifier, csrfSecret, captureWebFirstTouchCookie, readWebFirstTouchCookie } = require("./web-auth.js");
const SIGNUP_PATH = "/auth/maritime/email";
const CONFIRM_PATH = "/auth/maritime/confirm";
const CAPAFY_CONNECT_PATH = "/maritime/capafy/connect/start";
const CAPAFY_VERIFY_PATH = "/maritime/capafy/connect/verify";
const CAPAFY_DISCONNECT_PATH = "/maritime/capafy/connect/disconnect";
function enabled(options) {
  return (options.env || process.env).LM_MARITIME_MANAGER_EMAIL_ENABLED === "1";
}
function send(res, status, body, extra = {}) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store",
    "referrer-policy": "no-referrer", "x-content-type-options": "nosniff", ...extra });
  res.end(body == null ? "" : JSON.stringify(body));
}
function redirect(res, location) { send(res, 302, null, { location }); }
function clientFor(req, res, options) {
  return (options.createClient || createWebAuthClient)(req, res, options);
}
async function resolveMaritimeManagerUser(req, res, options = {}) {
  if (!enabled(options)) return null;
  try {
    const client = clientFor(req, res, options);
    const result = await client.auth.getUser();
    const user = result?.data?.user;
    if (result?.error || !user || !user.email || !Number.isFinite(Date.parse(user.email_confirmed_at))) return null;
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
async function signupBody(req) {
  const body = await readMaritimeBody(req);
  if (Object.keys(body).some(key => !["email", "attribution"].includes(key)) || typeof body.email !== "string") throw new Error("invalid_body");
  const email = body.email.trim().toLowerCase();
  if (email.length > 320 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error("invalid_body");
  return { email, attribution: require("./web-attribution.js").sanitizeWebAttribution(body.attribution) };
}
async function handleMaritimeManagerAuth(req, res, options = {}) {
  const url = new URL(req.url || "/", "http://localhost");
  if (![SIGNUP_PATH, CONFIRM_PATH].includes(url.pathname)) return false;
  if (!enabled(options)) { send(res, 503, { error: "manager_email_unavailable" }); return true; }
  const expectedMethod = url.pathname === SIGNUP_PATH ? "POST" : "GET";
  if (req.method !== expectedMethod) { send(res, 405, { error: "method_not_allowed" }, { allow: expectedMethod }); return true; }
  if (url.pathname === SIGNUP_PATH) {
    let origin;
    try { origin = publicOrigin(req, options); }
    catch { send(res, 503, { error: "manager_email_unavailable" }); return true; }
    if (req.headers?.origin !== origin) { send(res, 403, { error: "origin_rejected" }); return true; }
    let email, attribution;
    try { ({email, attribution} = await signupBody(req)); }
    catch { send(res, 400, { error: "invalid_email_request" }); return true; }
    try {
      captureWebFirstTouchCookie(req, res, attribution, options);
      const client = clientFor(req, res, options);
      const result = await client.auth.signInWithOtp({ email,
        options: { shouldCreateUser: true, emailRedirectTo: `${origin}${CONFIRM_PATH}` } });
      if (result?.error) {
        send(res, result.error.status === 429 ? 429 : 503, { error: "email_request_unavailable" });
      } else send(res, 202, { status: "check_email" });
    } catch { send(res, 503, { error: "email_request_unavailable" }); }
    return true;
  }
  // Mail link scanners can authenticate; only the later CSRF-protected POST activates work.
  let client;
  let sessionEstablished = false;
  try {
    for (const key of ["token_hash", "code", "type"]) {
      if (url.searchParams.getAll(key).length > 1) throw new Error("invalid_confirmation");
    }
    const code = url.searchParams.get("code");
    // Only exchange the PKCE code for the browser that initiated signup.
    // A bearer token_hash callback could otherwise replace somebody else's session.
    if (url.searchParams.has("token_hash") || !code || code.length > 2048 || !hasPkceVerifier(req, options)) {
      throw new Error("invalid_confirmation");
    }
    client = clientFor(req, res, options);
    const result = await client.auth.exchangeCodeForSession(code);
    if (result?.error || !result?.data?.session) throw new Error("invalid_confirmation");
    sessionEstablished = true;
    const user = await resolveMaritimeManagerUser(req, res, { ...options, createClient: () => client });
    if (!user) throw new Error("invalid_confirmation");
    const attribution = readWebFirstTouchCookie(req, options);
    void require("./maritime-manager-usage.js").observeMaritimeUsage("email_verified", user.uid, async signal => {
      if (Object.keys(attribution).length) {
        const fetchImpl = options.fetchImpl || globalThis.fetch;
        const fetch = (url, init = {}) => fetchImpl(url, { ...init, signal: init.signal ? AbortSignal.any([signal, init.signal]) : signal });
        if (!await (options.storeFirstTouch || require("./web-auth.js").storeWebFirstTouch)(user.uid, attribution, { ...options, fetch })) return false;
      }
      return (options.recordEmailVerified || require("./maritime-manager-usage.js").recordMaritimeEmailVerified)(user.uid, { ...options, attribution, signal });
    }, options);
    redirect(res, "/maritime?verified=1");
  } catch {
    if (client && sessionEstablished) { try { await client.auth.signOut({ scope: "local" }); } catch {} }
    redirect(res, "/maritime?auth_error=connection");
  }
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

function maritimeCsrfMatches(user, req) {
  const supplied = Buffer.from(String(req.headers?.["x-lm-web-csrf"] || ""));
  const expected = Buffer.from(user.csrf);
  return supplied.length === expected.length && require("node:crypto").timingSafeEqual(supplied, expected);
}

function maritimeManagerActiveForCapafy(row, user) {
  return Boolean(row && row.uid === user.uid && String(row.auth_subject || "").toLowerCase() === user.subject.toLowerCase()
    && row.status === "active" && !row.paused_at);
}

function capafyBindingStore(options) {
  if (options.capafyBindingStore) return options.capafyBindingStore;
  const env = options.env || process.env;
  return require("./maritime-manager-capafy-binding.js").createMaritimeCapafyBindingStore({
    query: options.query,
    encryptionKey: env.LM_MARITIME_CAPAFY_ENCRYPTION_KEY,
    now: options.now,
  });
}

async function handleMaritimeManagerCapafyConnection(req, res, options = {}) {
  const pathname = new URL(req.url || "/", "http://localhost").pathname;
  if (![CAPAFY_CONNECT_PATH, CAPAFY_VERIFY_PATH, CAPAFY_DISCONNECT_PATH].includes(pathname)) return false;
  if (!enabled(options)) { send(res, 503, { error: "manager_unavailable" }); return true; }
  if (pathname !== CAPAFY_DISCONNECT_PATH && options.capafyConnectionEnabled !== true
    && (options.env || process.env).LM_MARITIME_CAPAFY_CONNECTION_ENABLED !== "1") {
    send(res, 503, { error: "capafy_connection_unavailable" }); return true;
  }
  if (req.method !== "POST") { send(res, 405, { error: "method_not_allowed" }, { allow: "POST" }); return true; }
  let origin;
  try { origin = publicOrigin(req, options); }
  catch { send(res, 503, { error: "manager_unavailable" }); return true; }
  if (req.headers?.origin !== origin) { send(res, 403, { error: "origin_rejected" }); return true; }
  const user = await resolveMaritimeManagerUser(req, res, options);
  if (!user) { send(res, 401, { error: "authentication_required" }); return true; }
  if (!maritimeCsrfMatches(user, req)) { send(res, 403, { error: "csrf_rejected" }); return true; }
  const managerStore = options.managerStore || require("./maritime-manager-store.js").createMaritimeManagerStore({ env: options.env || process.env });
  let enrollment;
  try { enrollment = await managerStore.read(user.uid); }
  catch { send(res, 503, { error: "manager_unavailable" }); return true; }
  if (!enrollment || enrollment.auth_subject?.toLowerCase() !== user.subject.toLowerCase()) {
    send(res, 409, { error: "manager_setup_required" }); return true;
  }
  if (pathname !== CAPAFY_DISCONNECT_PATH && !maritimeManagerActiveForCapafy(enrollment, user)) {
    send(res, enrollment.status === "paused" || enrollment.paused_at ? 409 : 202,
      { error: enrollment.status === "paused" || enrollment.paused_at ? "manager_paused" : "manager_not_ready" });
    return true;
  }
  let body;
  try { body = await readMaritimeBody(req); }
  catch { send(res, 400, { error: "invalid_request" }); return true; }
  const env = options.env || process.env;
  const bindingStore = (() => { try { return capafyBindingStore(options); } catch { return null; } })();
  if (!bindingStore) { send(res, 503, { error: "capafy_connection_unavailable" }); return true; }
  if (pathname === CAPAFY_CONNECT_PATH) {
    if (Object.keys(body).some(key => !["email", "termsAccepted", "privacyAccepted"].includes(key))
      || typeof body.email !== "string") {
      send(res, 400, { error: "invalid_request" }); return true;
    }
    if (body.termsAccepted !== true || body.privacyAccepted !== true) {
      send(res, 400, { error: "capafy_policy_consent_required" }); return true;
    }
    try {
      bindingStore.assertConfigured?.();
      const { CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION, CAPAFY_TERMS_URL, CAPAFY_PRIVACY_URL } = require("./maritime-manager-capafy-binding.js");
      const acceptedAt = options.now?.() || new Date().toISOString();
      const connector = options.capafyConnector || require("./maritime-manager-capafy-binding.js").createCapafyAccountConnector({ fetchImpl: options.fetchImpl });
      const challenge = await connector.startLogin(body.email);
      const challengeRef = require("./maritime-manager-capafy-binding.js").sealChallenge({
        tenantId: user.uid, authSubject: user.subject, challengeId: challenge.challengeId,
        expiresInSec: challenge.expiresInSec, now: acceptedAt,
        policyConsentVersion: CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION, termsAcceptedAt: acceptedAt,
        termsUrl: CAPAFY_TERMS_URL, privacyUrl: CAPAFY_PRIVACY_URL,
      }, require("./web-auth.js").csrfSecret(options));
      send(res, 202, { status: "check_email", challengeRef, expiresInSec: challenge.expiresInSec });
    } catch (error) {
      send(res, error?.message === "maritime_capafy_email_invalid" ? 400 : 503,
        { error: error?.message === "maritime_capafy_email_invalid" ? "invalid_email" : "capafy_login_unavailable" });
    }
    return true;
  }
  if (pathname === CAPAFY_VERIFY_PATH) {
    if (Object.keys(body).some(key => !["challengeRef", "code", "autonomyConsentVersion"].includes(key))
      || typeof body.challengeRef !== "string" || typeof body.code !== "string"
      || body.autonomyConsentVersion !== require("./maritime-manager-capafy-binding.js").CAPAFY_AUTONOMY_CONSENT_VERSION) {
      send(res, 400, { error: "invalid_request" }); return true;
    }
    let challenge;
    try {
      challenge = require("./maritime-manager-capafy-binding.js").openChallenge(body.challengeRef, {
        tenantId: user.uid, authSubject: user.subject,
        secret: require("./web-auth.js").csrfSecret(options), now: options.now?.() || new Date().toISOString(),
      });
    } catch (error) {
      send(res, 400, { error: error?.message === "maritime_capafy_challenge_expired" ? "challenge_expired" : "challenge_invalid" });
      return true;
    }
    try {
      const connector = options.capafyConnector || require("./maritime-manager-capafy-binding.js").createCapafyAccountConnector({ fetchImpl: options.fetchImpl });
      const identity = await connector.verifyLogin({ challengeId: challenge.challengeId, code: body.code });
      const saved = await bindingStore.save({ tenantId: user.uid, authSubject: user.subject,
        providerSubject: identity.providerSubject, accessToken: identity.accessToken,
        autonomyConsentVersion: body.autonomyConsentVersion,
        policyConsentVersion: challenge.policyConsentVersion, termsAcceptedAt: challenge.termsAcceptedAt,
        termsUrl: challenge.termsUrl, privacyUrl: challenge.privacyUrl });
      send(res, 200, { status: "connected", provider: saved.provider, accountRef: saved.accountRef,
        developerVerified: true, autonomyConsentVersion: saved.autonomyConsentVersion });
    } catch (error) {
      const code = String(error?.message || "");
      const errorCode = code === "maritime_capafy_developer_verification_required" ? "developer_verification_required"
        : code === "maritime_capafy_subject_mismatch" ? "account_identity_mismatch"
          : code === "maritime_capafy_binding_rejected" ? "account_already_connected"
            : "capafy_verification_unavailable";
      send(res, ["developer_verification_required", "account_identity_mismatch", "account_already_connected"].includes(errorCode) ? 409 : 503,
        { error: errorCode });
    }
    return true;
  }
  if (Object.keys(body).length) { send(res, 400, { error: "invalid_request" }); return true; }
  try {
    const disconnected = await bindingStore.disconnect({ tenantId: user.uid, authSubject: user.subject });
    send(res, 200, { status: "disconnected", disconnected });
  } catch { send(res, 503, { error: "capafy_disconnect_unavailable" }); }
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
    let state = null, capafyStatus = null;
    if (user) {
      const store = options.managerStore || require("./maritime-manager-store.js").createMaritimeManagerStore({ env: options.env || process.env });
      const row = await store.read(user.uid);
      state = row?.status || null;
      if (state === "active" && !await managerReady(row, options)) state = "provisioning";
      if (row?.uid === user.uid && row.auth_subject?.toLowerCase() === user.subject.toLowerCase()) {
        const capafyEnabled = options.capafyConnectionEnabled === true
          || (options.env || process.env).LM_MARITIME_CAPAFY_CONNECTION_ENABLED === "1";
        try {
          const bindingStore = options.capafyBindingStore || (typeof options.query === "function" ? capafyBindingStore(options) : null);
          const connection = await bindingStore?.readStatus?.({ tenantId: user.uid, authSubject: user.subject });
          capafyStatus = connection?.connected === true ? (capafyEnabled ? "connected" : "connected_disabled")
            : connection?.connected === false ? (capafyEnabled ? "not_connected" : "disabled") : "unavailable";
        } catch { capafyStatus = "unavailable"; }
      }
      void require("./maritime-manager-usage.js").observeMaritimeUsage("returned", user.uid, signal => (options.recordReturn || require("./maritime-manager-usage.js").recordMaritimeManagerReturn)(user.uid, { ...options, signal, request: req, managerStore: store }), options);
    }
    const distribution = options.distributionStore || createMaritimeDistributionStore({ env: options.env || process.env });
    void Promise.resolve(distribution.recordAnonymousEvent("maritime_landing_view", source)).catch(() => {});
    res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "vary": "Cookie",
      "referrer-policy": "no-referrer", "x-content-type-options": "nosniff",
      "content-security-policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" });
    res.end(renderMaritimeLanding({ source, language, user, state, capafyStatus,
      telegramAvailable: options.telegramAvailable === true }));
  } catch { send(res, 503, { error: "manager_unavailable" }); }
  return true;
}
module.exports = { handleMaritimeManagerAuth, resolveMaritimeManagerUser, handleMaritimeManagerActivate,
  handleMaritimeManagerPage, handleMaritimeManagerStop, handleMaritimeManagerCapafyConnection };
