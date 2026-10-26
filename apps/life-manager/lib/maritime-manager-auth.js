"use strict";

const { createWebAuthClient, createWebCsrfToken, ensureWebUser, publicOrigin,
  csrfSecret, hasVerifiedGoogleIdentity } = require("./web-auth.js");
const SIGNUP_PATH = "/auth/maritime/email";
const CONFIRM_PATH = "/auth/maritime/confirm";
const CAPAFY_CONNECT_PATH = "/maritime/capafy/connect/start";
const CAPAFY_VERIFY_PATH = "/maritime/capafy/connect/verify";
const CAPAFY_DISCONNECT_PATH = "/maritime/capafy/connect/disconnect";
const CAPAFY_PUBLISHER_CONSENT_PATH = "/maritime/capafy/publisher-consent";
const CAPAFY_PUBLISHER_CONSENT_WITHDRAW_PATH = "/maritime/capafy/publisher-consent/withdraw";
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
  const { MANAGER_CONSENT_VERSION } = require("./maritime-distribution.js");
  if (row?.status !== "active" || row.paused_at || !row.agent_id || row.consent_version !== MANAGER_CONSENT_VERSION) return false;
  const ref = `maritime-agent://${row.agent_id}`;
  const runtime = require("./maritime-manager-runtime.js");
  const jobs = [runtime.buildMaritimeManagerProvisionJob({ tenantId: row.uid, releaseSha: row.release_sha, phase: "configure" })];
  if (typeof row.consent_v2_at === "string" && Number.isFinite(Date.parse(row.consent_v2_at))) {
    jobs.push(runtime.buildMaritimeManagerProvisionJob({ tenantId: row.uid, releaseSha: row.release_sha,
      phase: "configure", resumeAt: new Date(row.consent_v2_at).toISOString() }));
  }
  const readReceipt = options.readCommonReceipt || require("./runtime-job-store.js").readCommonReceipt;
  for (const job of jobs) {
    const receipt = await readReceipt({ tenantId: row.uid, jobId: job.job_id, attempt: 1 }, options.storeOptions || {});
    if (receipt && ["verified", "reconciled"].includes(receipt.outcome) && receipt.provider === "maritime"
      && receipt.loop_id === "maritime.manager" && receipt.external_ref === ref && receipt.evidence_refs?.includes(ref)) return true;
  }
  return false;
}
async function enqueueMaritimeProvisionRecovery(row, phase, options) {
  const build = require("./maritime-manager-runtime.js").buildMaritimeManagerProvisionJob;
  const base = build({ tenantId: row.uid, releaseSha: row.release_sha, phase });
  const readState = options.readProvisionJobState || require("./runtime-job-store.js").readRuntimeJobState;
  const read = async job => readState({ tenantId: row.uid, job }, options.storeOptions || {});
  let job = base;
  let state = await read(base);
  if (state && (state.job_id !== job.job_id || state.tenant_id !== row.uid
    || !["queued", "running", "reconciling", "completed", "dead_letter"].includes(state.status))) {
    throw new Error("provision_state_invalid");
  }
  if (state?.status === "dead_letter" && state.last_error_code === "MARITIME_PROVISION_CONSENT_REQUIRED"
    && state.attempt === 1 && typeof row.consent_v2_at === "string" && Number.isFinite(Date.parse(row.consent_v2_at))) {
    const resumeAt = new Date(row.consent_v2_at).toISOString();
    job = build({ tenantId: row.uid, releaseSha: row.release_sha, phase, resumeAt });
    state = await read(job);
    if (state && (state.job_id !== job.job_id || state.tenant_id !== row.uid
      || !["queued", "running", "reconciling", "completed", "dead_letter"].includes(state.status))) {
      throw new Error("provision_state_invalid");
    }
  }
  if (state) return { created: false, job: { ...job, status: state.status } };
  const enqueue = options.enqueueJob || require("./runtime-job-store.js").enqueueJob;
  const queued = await enqueue(job, options.storeOptions || {});
  if (!queued || typeof queued.created !== "boolean" || queued.job?.job_id !== job.job_id
    || queued.job?.tenant_id !== row.uid
    || !["queued", "running", "reconciling", "completed", "dead_letter"].includes(queued.job.status)) {
    throw new Error("provision_enqueue_receipt_invalid");
  }
  return queued;
}
async function enqueueMaritimeReconsentJobs(row, options) {
  const plans = require("./maritime-manager-wake.js").buildMaritimeReconsentJobs(row);
  const enqueue = options.enqueueJobAt || require("./runtime-job-store.js").enqueueJobAt;
  for (const plan of [plans.report, plans.cycle]) {
    const queued = await enqueue(plan.job, plan.availableAt, options.storeOptions || {});
    let availableAt = null;
    try { availableAt = new Date(queued?.job?.available_at).toISOString(); } catch { /* validated below */ }
    if (!queued || typeof queued.created !== "boolean" || queued.job?.job_id !== plan.job.job_id
      || queued.job?.tenant_id !== row.uid || availableAt !== plan.availableAt
      || !["queued", "running", "completed", "dead_letter", "reconciling"].includes(queued.job.status)) {
      throw new Error("reconsent_job_receipt_invalid");
    }
    if (queued.job.status === "dead_letter" || queued.job.status === "reconciling") {
      throw new Error("reconsent_job_not_ready");
    }
  }
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
    let existing = await store.read(user.uid);
    let retentionAccepted = false;
    if (existing?.status === "paused" || existing?.paused_at) { send(res, 409, { error: "manager_paused" }); return true; }
    if (existing?.status === "effect_unknown") { send(res, 409, { error: "manager_reconciling" }); return true; }
    if (["pending", "provisioning"].includes(existing?.status) && existing.consent_version !== MANAGER_CONSENT_VERSION) {
      const distribution = options.distributionStore || createMaritimeDistributionStore({ env });
      const consent = await distribution.accept(user.uid, normalizeMaritimeSource(existing.source || body.source || "direct"));
      if (!consent?.ok) { send(res, consent?.status === "capacity_full" ? 429 : 503,
        { error: consent?.status === "capacity_full" ? "capacity_full" : "consent_unavailable" }); return true; }
      const reconsent = options.reconsentManagerImpl || store.reconsent;
      if (typeof reconsent !== "function") throw new Error("manager_reconsent_unavailable");
      const updated = await reconsent.call(store, { uid: user.uid, authSubject: user.subject,
        consentVersion: MANAGER_CONSENT_VERSION });
      if (!updated || updated.uid !== user.uid || updated.auth_subject !== user.subject
        || !["pending", "provisioning"].includes(updated.status) || updated.paused_at || updated.agent_id
        || updated.release_sha !== existing.release_sha || updated.consent_version !== MANAGER_CONSENT_VERSION) {
        throw new Error("manager_reconsent_unconfirmed");
      }
      existing = updated;
      retentionAccepted = true;
    }
    if (existing?.status === "active") {
      if (existing.consent_version !== MANAGER_CONSENT_VERSION) {
        const distribution = options.distributionStore || createMaritimeDistributionStore({ env });
        const consent = await distribution.accept(user.uid, normalizeMaritimeSource(existing.source || body.source || "direct"));
        if (!consent?.ok) { send(res, consent?.status === "capacity_full" ? 429 : 503,
          { error: consent?.status === "capacity_full" ? "capacity_full" : "consent_unavailable" }); return true; }
        const reconsent = options.reconsentManagerImpl || store.reconsent;
        if (typeof reconsent !== "function") throw new Error("manager_reconsent_unavailable");
        const updated = await reconsent.call(store, { uid: user.uid, authSubject: user.subject,
          consentVersion: MANAGER_CONSENT_VERSION });
        if (!updated || updated.uid !== user.uid || updated.auth_subject !== user.subject
          || updated.status !== "active" || updated.paused_at || updated.consent_version !== MANAGER_CONSENT_VERSION) {
          throw new Error("manager_reconsent_unconfirmed");
        }
        const ready = await managerReady(updated, options);
        if (ready) {
          await enqueueMaritimeReconsentJobs(updated, options);
          send(res, 200, { status: "active", consentUpdated: true });
          return true;
        }
        const provision = await enqueueMaritimeProvisionRecovery(updated, "configure", options);
        if (provision.job.status === "reconciling") { send(res, 409, { error: "manager_reconciling" }); return true; }
        if (provision.job.status === "dead_letter") { send(res, 503, { error: "provision_failed" }); return true; }
        if (provision.job.status === "completed") {
          const latest = await store.read(user.uid);
          if (await managerReady(latest, options)) {
            await enqueueMaritimeReconsentJobs(latest, options);
            send(res, 200, { status: "active", consentUpdated: true });
          } else send(res, 409, { error: "provision_state_unconfirmed" });
          return true;
        }
        send(res, 202, { status: "pending", consentUpdated: true });
        return true;
      }
      const ready = await managerReady(existing, options);
      if (!ready && existing.consent_v2_at) {
        const provision = await enqueueMaritimeProvisionRecovery(existing, "configure", options);
        if (provision.job.status === "reconciling") { send(res, 409, { error: "manager_reconciling" }); return true; }
        if (provision.job.status === "dead_letter") { send(res, 503, { error: "provision_failed" }); return true; }
        if (provision.job.status === "completed") {
          const latest = await store.read(user.uid);
          if (await managerReady(latest, options)) {
            await enqueueMaritimeReconsentJobs(latest, options);
            send(res, 200, { status: "active" });
          } else send(res, 409, { error: "provision_state_unconfirmed" });
          return true;
        }
        send(res, 202, { status: "pending" });
        return true;
      }
      if (ready && existing.consent_v2_at) await enqueueMaritimeReconsentJobs(existing, options);
      send(res, ready ? 200 : 202, { status: ready ? "active" : "pending" }); return true;
    }
    const source = normalizeMaritimeSource(existing?.source || body.source || "direct");
    const distribution = options.distributionStore || createMaritimeDistributionStore({ env });
    const consent = retentionAccepted ? { ok: true, status: "consented" } : await distribution.accept(user.uid, source);
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
    const queued = retentionAccepted
      ? await enqueueMaritimeProvisionRecovery(row, "create", options)
      : await (options.enqueueJob || require("./runtime-job-store.js").enqueueJob)(job);
    if (!queued || typeof queued.created !== "boolean" || (!retentionAccepted && queued.job?.job_id !== job.job_id)
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
function capafyPublisherConsentStore(options) {
  if (options.capafyPublisherConsentStore) return options.capafyPublisherConsentStore;
  return require("./maritime-manager-capafy-consent.js").createMaritimeCapafyPublisherConsentStore({
    query: options.query,
    now: options.now,
  });
}

async function handleMaritimeManagerCapafyConnection(req, res, options = {}) {
  const pathname = new URL(req.url || "/", "http://localhost").pathname;
  if (![CAPAFY_CONNECT_PATH, CAPAFY_VERIFY_PATH, CAPAFY_DISCONNECT_PATH, CAPAFY_PUBLISHER_CONSENT_PATH,
    CAPAFY_PUBLISHER_CONSENT_WITHDRAW_PATH].includes(pathname)) return false;
  if (!enabled(options)) { send(res, 503, { error: "manager_unavailable" }); return true; }
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
  const consentLifecyclePath = [CAPAFY_PUBLISHER_CONSENT_PATH, CAPAFY_PUBLISHER_CONSENT_WITHDRAW_PATH].includes(pathname);
  if (pathname !== CAPAFY_DISCONNECT_PATH && !consentLifecyclePath && !maritimeManagerActiveForCapafy(enrollment, user)) {
    send(res, enrollment.status === "paused" || enrollment.paused_at ? 409 : 202,
      { error: enrollment.status === "paused" || enrollment.paused_at ? "manager_paused" : "manager_not_ready" });
    return true;
  }
  let body;
  try { body = await readMaritimeBody(req); }
  catch { send(res, 400, { error: "invalid_request" }); return true; }
  const env = options.env || process.env;
  if (pathname === CAPAFY_PUBLISHER_CONSENT_PATH) {
    try {
      const consentStore = capafyPublisherConsentStore(options);
      const record = await consentStore.record({ tenantId: user.uid, authSubject: user.subject,
        verifiedContactEmail: enrollment.email, consent: body });
      send(res, 201, { status: "recorded", agreementVersion: record.agreementVersion,
        effectiveDate: record.effectiveDate, acceptedAt: record.acceptedAt });
    } catch (error) {
      const reason = String(error?.message || "");
      const stale = reason === "maritime_capafy_agreement_version_stale";
      const invalid = /^maritime_capafy_consent_(?:invalid|identity_invalid|required)$/.test(reason);
      const conflict = reason === "maritime_capafy_consent_already_recorded";
      const withdrawn = reason === "maritime_capafy_consent_withdrawn";
      send(res, stale || invalid ? 400 : conflict || withdrawn ? 409 : 503,
        { error: stale ? "publisher_agreement_version_stale" : invalid ? "publisher_consent_invalid"
          : withdrawn ? "publisher_consent_withdrawn" : conflict ? "publisher_consent_already_recorded" : "publisher_consent_unavailable" });
    }
    return true;
  }
  if (pathname === CAPAFY_PUBLISHER_CONSENT_WITHDRAW_PATH) {
    if (Object.keys(body).length) { send(res, 400, { error: "invalid_request" }); return true; }
    try {
      const withdrawn = await capafyPublisherConsentStore(options).withdraw({ tenantId: user.uid, authSubject: user.subject });
      if (!withdrawn) { send(res, 409, { error: "publisher_consent_not_found" }); return true; }
      send(res, 200, { status: "withdrawn", agreementVersion: withdrawn.agreementVersion,
        effectiveDate: withdrawn.effectiveDate, withdrawnAt: withdrawn.withdrawnAt });
    } catch { send(res, 503, { error: "publisher_consent_unavailable" }); }
    return true;
  }
  if (pathname !== CAPAFY_DISCONNECT_PATH && options.capafyConnectionEnabled !== true
    && env.LM_MARITIME_CAPAFY_CONNECTION_ENABLED !== "1") {
    send(res, 503, { error: "capafy_connection_unavailable" }); return true;
  }
  let publisherAgreementVersion = null;
  if (pathname !== CAPAFY_DISCONNECT_PATH) {
    let currentConsent;
    try {
      const consentStore = capafyPublisherConsentStore(options);
      currentConsent = await consentStore.readCurrent({ tenantId: user.uid, authSubject: user.subject });
    } catch {
      send(res, 503, { error: "publisher_consent_unavailable" }); return true;
    }
    const currentAgreement = require("./maritime-manager-capafy-consent.js");
    if (currentConsent?.tenantId !== user.uid || currentConsent.authSubject !== user.subject.toLowerCase()
      || currentConsent.agreementVersion !== currentAgreement.CAPAFY_PUBLISHER_AGREEMENT_VERSION
      || currentConsent.effectiveDate !== currentAgreement.CAPAFY_PUBLISHER_AGREEMENT_EFFECTIVE_DATE) {
      send(res, 409, { error: "capafy_publisher_agreement_consent_required" }); return true;
    }
    publisherAgreementVersion = currentConsent.agreementVersion;
  }
  const bindingStore = (() => { try { return capafyBindingStore(options); } catch { return null; } })();
  if (!bindingStore) { send(res, 503, { error: "capafy_connection_unavailable" }); return true; }
  if (pathname === CAPAFY_CONNECT_PATH) {
    const useTenantMailbox = body.useTenantMailbox === true;
    if (Object.keys(body).some(key => !["termsAccepted", "privacyAccepted", "useTenantMailbox", "tenantMailboxConsent"].includes(key))
      || (body.useTenantMailbox !== undefined && typeof body.useTenantMailbox !== "boolean")
      || (body.tenantMailboxConsent !== undefined && typeof body.tenantMailboxConsent !== "boolean")
      || (!useTenantMailbox && body.tenantMailboxConsent === true)) {
      send(res, 400, { error: "invalid_request" }); return true;
    }
    if (body.termsAccepted !== true || body.privacyAccepted !== true) {
      send(res, 400, { error: "capafy_policy_consent_required" }); return true;
    }
    if (useTenantMailbox && body.tenantMailboxConsent !== true) {
      send(res, 400, { error: "tenant_mailbox_consent_required" }); return true;
    }
    try {
      if (typeof bindingStore.readStatus !== "function") throw new Error("maritime_capafy_binding_unavailable");
      const existing = await bindingStore.readStatus({ tenantId: user.uid, authSubject: user.subject });
      if (existing?.connected === true) {
        const accountRef = existing.accountRef;
        const expectedPrefix = `account://capafy/${user.uid}/`;
        if (existing.provider !== "capafy" || existing.tenantId !== user.uid
          || typeof accountRef !== "string" || !accountRef.startsWith(expectedPrefix)
          || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(accountRef.slice(expectedPrefix.length))) {
          throw new Error("maritime_capafy_binding_invalid");
        }
        send(res, 200, { status: "connected", provider: "capafy", accountRef,
          autonomyConsentVersion: require("./maritime-manager-capafy-binding.js").CAPAFY_AUTONOMY_CONSENT_VERSION });
        return true;
      }
      if (existing?.connected !== false) throw new Error("maritime_capafy_binding_invalid");
      bindingStore.assertConfigured?.();
      const { CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION, CAPAFY_TERMS_URL, CAPAFY_PRIVACY_URL } = require("./maritime-manager-capafy-binding.js");
      const acceptedAt = options.now?.() || new Date().toISOString();
      const mailbox = useTenantMailbox
        ? await options.managerMailboxStore?.ensure({ tenantId: user.uid, authSubject: user.subject })
        : null;
      const email = useTenantMailbox ? mailbox?.email : enrollment.email;
      if (typeof email !== "string" || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        throw new Error("maritime_capafy_email_invalid");
      }
      if (useTenantMailbox && !/^[^\s@]+@agentmail\.to$/i.test(email)) {
        throw new Error("maritime_mailbox_unavailable");
      }
      const attemptId = useTenantMailbox ? require("node:crypto").randomUUID() : null;
      const startedAt = new Date(acceptedAt).toISOString();
      if (useTenantMailbox) {
        const leaseExpiresAt = new Date(Date.parse(startedAt) + 600_000).toISOString();
        const reserved = await options.managerMailboxStore?.reserveCapafyChallenge({ tenantId: user.uid,
          authSubject: user.subject, attemptId, startedAt, leaseExpiresAt });
        if (reserved !== true) {
          send(res, 409, { error: "capafy_challenge_in_progress" });
          return true;
        }
      }
      const connector = options.capafyConnector || require("./maritime-manager-capafy-binding.js").createCapafyAccountConnector({ fetchImpl: options.fetchImpl });
      const challenge = await connector.startLogin(email);
      if (useTenantMailbox) {
        const expiresAt = new Date(Date.parse(startedAt) + challenge.expiresInSec * 1000).toISOString();
        const bound = await options.managerMailboxStore?.bindCapafyChallenge({ tenantId: user.uid,
          authSubject: user.subject, attemptId, challengeId: challenge.challengeId, expiresAt });
        if (bound !== true) throw new Error("maritime_mailbox_challenge_bind_unconfirmed");
      }
      const challengeRef = require("./maritime-manager-capafy-binding.js").sealChallenge({
        tenantId: user.uid, authSubject: user.subject, challengeId: challenge.challengeId,
        expiresInSec: challenge.expiresInSec, now: startedAt,
        policyConsentVersion: CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION, termsAcceptedAt: startedAt,
        termsUrl: CAPAFY_TERMS_URL, privacyUrl: CAPAFY_PRIVACY_URL, mailboxVerification: useTenantMailbox,
      }, require("./web-auth.js").csrfSecret(options));
      send(res, 202, { status: "check_email", challengeRef, expiresInSec: challenge.expiresInSec,
        ...(useTenantMailbox ? { mailboxEmail: email } : {}) });
    } catch (error) {
      send(res, error?.message === "maritime_capafy_email_invalid" ? 400 : 503,
        { error: error?.message === "maritime_capafy_email_invalid" ? "invalid_email" : "capafy_login_unavailable" });
    }
    return true;
  }
  if (pathname === CAPAFY_VERIFY_PATH) {
    if (Object.keys(body).some(key => !["challengeRef", "code", "autonomyConsentVersion"].includes(key))
      || typeof body.challengeRef !== "string" || (body.code !== undefined && typeof body.code !== "string")
      || (body.code !== undefined && !/^\d{4,8}$/.test(body.code))
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
    if (challenge.mailboxVerification === true) {
      let claimed = false;
      try {
        claimed = await options.managerMailboxStore?.claimCapafyChallengeVerification({ tenantId: user.uid,
          authSubject: user.subject, challengeId: challenge.challengeId, now: options.now?.() || new Date().toISOString() });
      } catch {
        send(res, 503, { error: "capafy_verification_unavailable" }); return true;
      }
      if (claimed !== true) { send(res, 409, { error: "capafy_challenge_in_progress" }); return true; }
    }
    const releaseMailboxChallenge = async () => {
      if (challenge.mailboxVerification !== true) return true;
      try {
        return await options.managerMailboxStore?.releaseCapafyChallengeVerification({ tenantId: user.uid,
          authSubject: user.subject, challengeId: challenge.challengeId }) === true;
      } catch { return false; }
    };
    let code = body.code;
    if (code === undefined) {
      if (challenge.mailboxVerification !== true) {
        send(res, 400, { error: "verification_code_required" }); return true;
      }
      let result;
      try {
        result = await options.managerMailboxStore?.readCapafyVerificationCode({ tenantId: user.uid,
          authSubject: user.subject, afterMs: Date.parse(challenge.termsAcceptedAt) });
      } catch {
        await releaseMailboxChallenge();
        send(res, 503, { error: "capafy_verification_unavailable" }); return true;
      }
      if (result?.status === "not_found") {
        await releaseMailboxChallenge();
        send(res, 202, { status: "waiting_for_email" }); return true;
      }
      if (result?.status !== "code" || typeof result.code !== "string" || !/^\d{4,8}$/.test(result.code)) {
        await releaseMailboxChallenge();
        send(res, 503, { error: "capafy_verification_unavailable" }); return true;
      }
      code = result.code;
    }
    if (!/^\d{4,8}$/.test(code)) {
      await releaseMailboxChallenge();
      send(res, 400, { error: "invalid_request" }); return true;
    }
    if (challenge.mailboxVerification === true) {
      const now = options.now?.() || new Date().toISOString();
      let renewed = false;
      try {
        renewed = await options.managerMailboxStore?.renewCapafyChallengeVerification({ tenantId: user.uid,
          authSubject: user.subject, challengeId: challenge.challengeId, now,
          leaseExpiresAt: new Date(Date.parse(now) + 120_000).toISOString() });
      } catch {
        send(res, 503, { error: "capafy_verification_unavailable" }); return true;
      }
      if (renewed !== true) { send(res, 409, { error: "capafy_challenge_in_progress" }); return true; }
    }
    try {
      const connector = options.capafyConnector || require("./maritime-manager-capafy-binding.js").createCapafyAccountConnector({ fetchImpl: options.fetchImpl });
      const identity = await connector.verifyLogin({ challengeId: challenge.challengeId, code });
      const saved = await bindingStore.save({ tenantId: user.uid, authSubject: user.subject,
        providerSubject: identity.providerSubject, accessToken: identity.accessToken,
        publisherAgreementVersion,
        autonomyConsentVersion: body.autonomyConsentVersion,
        policyConsentVersion: challenge.policyConsentVersion, termsAcceptedAt: challenge.termsAcceptedAt,
        termsUrl: challenge.termsUrl, privacyUrl: challenge.privacyUrl });
      if (challenge.mailboxVerification === true) {
        const completed = await options.managerMailboxStore?.completeCapafyChallenge({ tenantId: user.uid,
          authSubject: user.subject, challengeId: challenge.challengeId });
        if (completed !== true) throw new Error("maritime_mailbox_challenge_completion_unconfirmed");
      }
      send(res, 200, { status: "connected", provider: saved.provider, accountRef: saved.accountRef,
        developerVerified: true, autonomyConsentVersion: saved.autonomyConsentVersion });
    } catch (error) {
      const code = String(error?.message || "");
      const errorCode = code === "maritime_capafy_developer_verification_required" ? "developer_verification_required"
        : code === "maritime_capafy_subject_mismatch" ? "account_identity_mismatch"
          : ["maritime_capafy_binding_rejected", "maritime_capafy_account_already_claimed"].includes(code) ? "account_already_connected"
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
  const { MANAGER_CONSENT_VERSION, normalizeMaritimeSource, createMaritimeDistributionStore, renderMaritimeLanding } = require("./maritime-distribution.js");
  const source = normalizeMaritimeSource(url.searchParams.get("source") || "direct");
  const language = String(url.searchParams.get("lang") || "").toLowerCase().startsWith("ja") ? "ja" : "en";
  try {
    const user = await resolveMaritimeManagerUser(req, res, options);
    let state = null, workbench = null, workbenchUnavailable = false, publisherConsent = null;
    let publisherConsentAvailable = false;
    if (user) {
      const store = options.managerStore || require("./maritime-manager-store.js").createMaritimeManagerStore({ env: options.env || process.env });
      const row = await store.read(user.uid);
      if (row?.uid === user.uid && String(row.auth_subject || "").toLowerCase() === user.subject.toLowerCase()) {
        const consentStore = options.capafyPublisherConsentStore
          || (typeof options.query === "function" ? capafyPublisherConsentStore(options) : null);
        if (typeof consentStore?.readForTenant === "function") {
          publisherConsent = await consentStore.readForTenant({ tenantId: user.uid, authSubject: user.subject });
          publisherConsentAvailable = true;
        }
      }
      state = row?.status || null;
      if (["pending", "provisioning", "active"].includes(state) && row.consent_version !== MANAGER_CONSENT_VERSION) state = "consent_required";
      else if (state === "active" && !await managerReady(row, options)) state = "provisioning";
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
      publisherConsent, publisherConsentAvailable,
      telegramAvailable: options.telegramAvailable === true,
      authError: url.searchParams.get("auth_error") === "connection" ? "connection" : null }));
  } catch { send(res, 503, { error: "manager_unavailable" }); }
  return true;
}
module.exports = { handleMaritimeManagerAuth, resolveMaritimeManagerUser, handleMaritimeManagerActivate,
  handleMaritimeManagerPage, handleMaritimeManagerStop, handleMaritimeManagerCapafyConnection };
