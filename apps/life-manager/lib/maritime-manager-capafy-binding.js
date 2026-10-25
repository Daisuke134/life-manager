"use strict";

const { createCipheriv, createDecipheriv, createHmac, hkdfSync, randomBytes, timingSafeEqual } = require("node:crypto");

const API_ORIGIN = "https://api.capafy.ai";
const CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION = "capafy-publisher-terms-privacy-v1";
const CAPAFY_TERMS_URL = `${API_ORIGIN}/terms-of-service`;
const CAPAFY_PRIVACY_URL = `${API_ORIGIN}/privacy-policy`;
const CAPAFY_AUTONOMY_CONSENT_VERSION = "maritime-capafy-autonomy-v1";
const UID = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SUBJECT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ACCESS_TOKEN = /^am_sk_[A-Za-z0-9_-]{16,480}$/;

function fail(code) { throw new Error(code); }
function validTenant(value) { if (typeof value !== "string" || !UID.test(value)) fail("maritime_capafy_identity_invalid"); return value; }
function validSubject(value) { if (typeof value !== "string" || !SUBJECT.test(value)) fail("maritime_capafy_identity_invalid"); return value.toLowerCase(); }
function nowIso(value) {
  const date = value instanceof Date ? value : new Date(String(value));
  if (!Number.isFinite(date.getTime())) fail("maritime_capafy_time_invalid");
  return date.toISOString();
}

function sealChallenge({ tenantId, authSubject, challengeId, expiresInSec, now = new Date().toISOString(),
  policyConsentVersion, termsAcceptedAt, termsUrl, privacyUrl } = {}, secret) {
  const uid = validTenant(tenantId), subject = validSubject(authSubject);
  if (typeof secret !== "string" || secret.length < 16
    || typeof challengeId !== "string" || !/^[A-Za-z0-9_-]{8,512}$/.test(challengeId)
    || !Number.isInteger(expiresInSec) || expiresInSec < 1 || expiresInSec > 600) fail("maritime_capafy_challenge_invalid");
  const issuedAt = nowIso(now);
  const acceptedAt = nowIso(termsAcceptedAt);
  if (policyConsentVersion !== CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION
    || acceptedAt !== issuedAt || termsUrl !== CAPAFY_TERMS_URL || privacyUrl !== CAPAFY_PRIVACY_URL) {
    fail("maritime_capafy_policy_consent_required");
  }
  const issued = Date.parse(issuedAt);
  const payload = Buffer.from(JSON.stringify({ v: 1, uid, subject,
    challengeId, expiresAt: new Date(issued + expiresInSec * 1000).toISOString(),
    policyConsentVersion, termsAcceptedAt: acceptedAt, termsUrl, privacyUrl })).toString("base64url");
  const signature = createHmac("sha256", secret).update(`maritime-capafy-otp:v1\0${payload}`).digest("base64url");
  return `${payload}.${signature}`;
}

function openChallenge(value, { tenantId, authSubject, secret, now = new Date().toISOString() } = {}) {
  try {
    const uid = validTenant(tenantId), subject = validSubject(authSubject);
    if (typeof secret !== "string" || secret.length < 16 || typeof value !== "string" || value.length > 2048) fail("invalid");
    const parts = value.split(".");
    if (parts.length !== 2 || parts.some(part => !/^[A-Za-z0-9_-]+$/.test(part))) fail("invalid");
    const expected = createHmac("sha256", secret).update(`maritime-capafy-otp:v1\0${parts[0]}`).digest();
    const supplied = Buffer.from(parts[1], "base64url");
    if (supplied.length !== expected.length || !timingSafeEqual(expected, supplied)) fail("invalid");
    const payload = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
    if (!payload || payload.v !== 1 || payload.uid !== uid || payload.subject !== subject
      || !/^[A-Za-z0-9_-]{8,512}$/.test(payload.challengeId || "")
      || payload.policyConsentVersion !== CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION
      || nowIso(payload.termsAcceptedAt) !== payload.termsAcceptedAt
      || payload.termsUrl !== CAPAFY_TERMS_URL || payload.privacyUrl !== CAPAFY_PRIVACY_URL
      || Object.keys(payload).sort().join(",") !== "challengeId,expiresAt,policyConsentVersion,privacyUrl,subject,termsAcceptedAt,termsUrl,uid,v") fail("invalid");
    const expiresAt = nowIso(payload.expiresAt);
    const current = Date.parse(nowIso(now));
    if (current >= Date.parse(expiresAt)) fail("maritime_capafy_challenge_expired");
    if (Date.parse(payload.termsAcceptedAt) > current) fail("invalid");
    return Object.freeze({ challengeId: payload.challengeId, expiresAt,
      policyConsentVersion: payload.policyConsentVersion, termsAcceptedAt: payload.termsAcceptedAt,
      termsUrl: payload.termsUrl, privacyUrl: payload.privacyUrl });
  } catch (error) {
    if (error?.message === "maritime_capafy_challenge_expired") throw error;
    fail("maritime_capafy_challenge_invalid");
  }
}

function deriveEncryptionKey(value) {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/i.test(value)) fail("maritime_capafy_encryption_unavailable");
  return Buffer.from(hkdfSync("sha256", Buffer.from(value, "hex"), Buffer.from("life-manager-maritime-capafy"),
    Buffer.from("provider-access-token:v1"), 32));
}

function associatedData({ tenantId, authSubject, providerSubject }) {
  return Buffer.from(`life-manager-maritime-capafy:v1\0${validTenant(tenantId)}\0${validSubject(authSubject)}\0${validSubject(providerSubject)}`);
}

function encryptToken(input, encryptionKey) {
  if (typeof input.accessToken !== "string" || !ACCESS_TOKEN.test(input.accessToken)) fail("maritime_capafy_token_invalid");
  const iv = randomBytes(12), cipher = createCipheriv("aes-256-gcm", deriveEncryptionKey(encryptionKey), iv);
  cipher.setAAD(associatedData(input));
  const ciphertext = Buffer.concat([cipher.update(input.accessToken, "utf8"), cipher.final()]);
  return { ciphertext, iv, tag: cipher.getAuthTag() };
}

function decryptToken(row, encryptionKey) {
  try {
    const iv = Buffer.from(row.iv), tag = Buffer.from(row.tag), ciphertext = Buffer.from(row.ciphertext);
    if (iv.length !== 12 || tag.length !== 16 || ciphertext.length < 1 || ciphertext.length > 1024) fail("invalid");
    const decipher = createDecipheriv("aes-256-gcm", deriveEncryptionKey(encryptionKey), iv);
    decipher.setAAD(associatedData({ tenantId: row.uid, authSubject: row.auth_subject,
      providerSubject: row.provider_subject }));
    decipher.setAuthTag(tag);
    const token = Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
    if (!ACCESS_TOKEN.test(token)) fail("invalid");
    return token;
  } catch { fail("maritime_capafy_binding_invalid"); }
}

function createMaritimeCapafyBindingStore({ query, encryptionKey, now = () => new Date().toISOString() } = {}) {
  if (typeof query !== "function") fail("maritime_capafy_store_unavailable");
  function assertConfigured() {
    deriveEncryptionKey(encryptionKey);
    return true;
  }
  async function save({ tenantId, authSubject, providerSubject, accessToken, autonomyConsentVersion,
    policyConsentVersion, termsAcceptedAt, termsUrl, privacyUrl } = {}) {
    const uid = validTenant(tenantId), subject = validSubject(authSubject), external = validSubject(providerSubject);
    if (autonomyConsentVersion !== CAPAFY_AUTONOMY_CONSENT_VERSION) fail("maritime_capafy_autonomy_consent_required");
    if (policyConsentVersion !== CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION
      || termsUrl !== CAPAFY_TERMS_URL || privacyUrl !== CAPAFY_PRIVACY_URL) {
      fail("maritime_capafy_policy_consent_required");
    }
    const acceptedAt = nowIso(termsAcceptedAt);
    if (acceptedAt > nowIso(now())) fail("maritime_capafy_policy_consent_required");
    const accountRef = `account://capafy/${uid}/${external}`;
    const sealed = encryptToken({ tenantId: uid, authSubject: subject, providerSubject: external, accessToken }, encryptionKey);
    const rows = (await query(`
      INSERT INTO private.lm_maritime_manager_capafy_bindings
        (uid,auth_subject,provider_subject,account_ref,ciphertext,iv,tag,autonomy_consent_version,
         policy_consent_version,terms_accepted_at,terms_url,privacy_url,connected_at)
      VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::timestamptz,$11,$12,$13::timestamptz)
      ON CONFLICT (uid) DO UPDATE SET
        ciphertext=EXCLUDED.ciphertext,iv=EXCLUDED.iv,tag=EXCLUDED.tag,
        policy_consent_version=EXCLUDED.policy_consent_version,terms_accepted_at=EXCLUDED.terms_accepted_at,
        terms_url=EXCLUDED.terms_url,privacy_url=EXCLUDED.privacy_url,connected_at=EXCLUDED.connected_at
      WHERE private.lm_maritime_manager_capafy_bindings.auth_subject=EXCLUDED.auth_subject
        AND private.lm_maritime_manager_capafy_bindings.provider_subject=EXCLUDED.provider_subject
        AND private.lm_maritime_manager_capafy_bindings.account_ref=EXCLUDED.account_ref
        AND private.lm_maritime_manager_capafy_bindings.autonomy_consent_version=EXCLUDED.autonomy_consent_version
      RETURNING uid,auth_subject,provider_subject,account_ref,autonomy_consent_version,
        policy_consent_version,terms_accepted_at,terms_url,privacy_url
    `, [uid, subject, external, accountRef, sealed.ciphertext, sealed.iv, sealed.tag,
      CAPAFY_AUTONOMY_CONSENT_VERSION, policyConsentVersion, acceptedAt, termsUrl, privacyUrl, nowIso(now())])).rows;
    if (!Array.isArray(rows) || rows.length !== 1 || rows[0].uid !== uid || rows[0].auth_subject !== subject
      || rows[0].provider_subject !== external || rows[0].account_ref !== accountRef
      || rows[0].autonomy_consent_version !== CAPAFY_AUTONOMY_CONSENT_VERSION
      || rows[0].policy_consent_version !== policyConsentVersion || nowIso(rows[0].terms_accepted_at) !== acceptedAt
      || rows[0].terms_url !== termsUrl || rows[0].privacy_url !== privacyUrl) fail("maritime_capafy_binding_rejected");
    return Object.freeze({ provider: "capafy", tenantId: uid, providerSubject: external, accountRef,
      autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION, policyConsentVersion,
      termsAcceptedAt: acceptedAt, termsUrl, privacyUrl });
  }
  async function read({ tenantId, authSubject } = {}) {
    const uid = validTenant(tenantId), subject = validSubject(authSubject);
    const rows = (await query(`
      SELECT uid,auth_subject,provider_subject,account_ref,ciphertext,iv,tag,autonomy_consent_version,
        policy_consent_version,terms_accepted_at,terms_url,privacy_url
      FROM private.lm_maritime_manager_capafy_bindings WHERE uid=$1 AND auth_subject=$2 LIMIT 2
    `, [uid, subject])).rows;
    if (!Array.isArray(rows) || rows.length !== 1) fail("maritime_capafy_binding_unavailable");
    const row = rows[0];
    if (row.uid !== uid || row.auth_subject !== subject || row.autonomy_consent_version !== CAPAFY_AUTONOMY_CONSENT_VERSION
      || row.policy_consent_version !== CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION
      || row.terms_url !== CAPAFY_TERMS_URL || row.privacy_url !== CAPAFY_PRIVACY_URL
      || row.account_ref !== `account://capafy/${uid}/${row.provider_subject}`) fail("maritime_capafy_binding_invalid");
    return Object.freeze({ provider: "capafy", tenantId: uid, authSubject: subject,
      providerSubject: validSubject(row.provider_subject), accountRef: row.account_ref,
      autonomyConsentVersion: row.autonomy_consent_version,
      policyConsentVersion: row.policy_consent_version, termsAcceptedAt: nowIso(row.terms_accepted_at),
      termsUrl: row.terms_url, privacyUrl: row.privacy_url, accessToken: decryptToken(row, encryptionKey) });
  }
  async function readStatus({ tenantId, authSubject } = {}) {
    const uid = validTenant(tenantId), subject = validSubject(authSubject);
    const rows = (await query(`
      SELECT uid,auth_subject,provider_subject,account_ref,autonomy_consent_version,
        policy_consent_version,terms_accepted_at,terms_url,privacy_url
      FROM private.lm_maritime_manager_capafy_bindings WHERE uid=$1 AND auth_subject=$2 LIMIT 2
    `, [uid, subject])).rows;
    if (!Array.isArray(rows) || rows.length > 1) fail("maritime_capafy_binding_invalid");
    if (!rows.length) return Object.freeze({ connected: false });
    const row = rows[0];
    if (row.uid !== uid || row.auth_subject !== subject || row.autonomy_consent_version !== CAPAFY_AUTONOMY_CONSENT_VERSION
      || row.policy_consent_version !== CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION
      || row.terms_url !== CAPAFY_TERMS_URL || row.privacy_url !== CAPAFY_PRIVACY_URL
      || row.account_ref !== `account://capafy/${uid}/${validSubject(row.provider_subject)}`) fail("maritime_capafy_binding_invalid");
    return Object.freeze({ connected: true, provider: "capafy", tenantId: uid,
      accountRef: row.account_ref, autonomyConsentVersion: row.autonomy_consent_version,
      policyConsentVersion: row.policy_consent_version, termsAcceptedAt: nowIso(row.terms_accepted_at),
      termsUrl: row.terms_url, privacyUrl: row.privacy_url });
  }
  async function disconnect({ tenantId, authSubject } = {}) {
    const uid = validTenant(tenantId), subject = validSubject(authSubject);
    const rows = (await query(`DELETE FROM private.lm_maritime_manager_capafy_bindings
      WHERE uid=$1 AND auth_subject=$2 RETURNING uid,auth_subject`, [uid, subject])).rows;
    if (!Array.isArray(rows) || rows.length > 1 || rows.some(row => row.uid !== uid || row.auth_subject !== subject)) {
      fail("maritime_capafy_binding_invalid");
    }
    return rows.length === 1;
  }
  return Object.freeze({ save, read, readStatus, disconnect, assertConfigured });
}

function apiPayload(response) {
  if (!response || response.ok !== true) fail("maritime_capafy_api_unavailable");
  return response.json().then(payload => {
    if (!payload || typeof payload !== "object" || payload.code !== 0 || !payload.data || typeof payload.data !== "object") {
      fail("maritime_capafy_api_rejected");
    }
    return payload.data;
  }).catch(error => {
    if (/^maritime_capafy_api_/.test(error?.message || "")) throw error;
    fail("maritime_capafy_api_invalid");
  });
}

function createCapafyAccountConnector({ fetchImpl = globalThis.fetch, baseUrl = API_ORIGIN } = {}) {
  let origin;
  try { const url = new URL(baseUrl); if (url.protocol !== "https:" || url.origin !== API_ORIGIN) fail("invalid"); origin = url.origin; }
  catch { fail("maritime_capafy_api_origin_invalid"); }
  if (typeof fetchImpl !== "function") fail("maritime_capafy_api_unavailable");
  async function request(method, pathname, { body, accessToken } = {}) {
    try {
      const response = await fetchImpl(`${origin}${pathname}`, { method, redirect: "error", signal: AbortSignal.timeout(15_000),
        headers: { accept: "application/json", ...(body === undefined ? {} : { "content-type": "application/json" }),
          ...(accessToken === undefined ? {} : { authorization: `Bearer ${accessToken}` }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      return await apiPayload(response);
    } catch (error) {
      if (/^maritime_capafy_api_/.test(error?.message || "")) throw error;
      fail("maritime_capafy_api_unavailable");
    }
  }
  async function startLogin(emailValue) {
    const email = typeof emailValue === "string" ? emailValue.trim().toLowerCase() : "";
    if (email.length > 320 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) fail("maritime_capafy_email_invalid");
    const data = await request("POST", "/auth/login", { body: { loginMethod: "email", email } });
    if (typeof data.challengeId !== "string" || !/^[A-Za-z0-9_-]{8,512}$/.test(data.challengeId)
      || !Number.isInteger(data.expiresInSec) || data.expiresInSec < 1 || data.expiresInSec > 600) fail("maritime_capafy_challenge_invalid");
    return Object.freeze({ challengeId: data.challengeId, expiresInSec: data.expiresInSec });
  }
  async function verifyLogin({ challengeId, code } = {}) {
    if (typeof challengeId !== "string" || !/^[A-Za-z0-9_-]{8,512}$/.test(challengeId)
      || typeof code !== "string" || !/^\d{4,8}$/.test(code)) fail("maritime_capafy_otp_invalid");
    const login = await request("POST", "/auth/login/verify", { body: { challengeId, code, source: "agent" } });
    if (typeof login.accessToken !== "string" || !ACCESS_TOKEN.test(login.accessToken)
      || typeof login.status !== "string" || login.status !== "active") fail("maritime_capafy_account_unverified");
    const providerSubject = validSubject(login.userId);
    const loginEmail = typeof login.email === "string" ? login.email.trim().toLowerCase() : "";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(loginEmail)) fail("maritime_capafy_account_unverified");
    const [account, profile] = await Promise.all([
      request("GET", "/agent/account", { accessToken: login.accessToken }),
      request("GET", "/agent/account/profile", { accessToken: login.accessToken }),
    ]);
    if (typeof account.email !== "string" || account.email.trim().toLowerCase() !== loginEmail
      || account.role !== "developer" || account.developerVerified !== true) fail("maritime_capafy_developer_verification_required");
    if (profile.userId !== providerSubject) fail("maritime_capafy_subject_mismatch");
    return Object.freeze({ provider: "capafy", providerSubject, accountEmail: loginEmail,
      developerVerified: true, accessToken: login.accessToken });
  }
  async function readAccount(accessToken) {
    if (typeof accessToken !== "string" || !ACCESS_TOKEN.test(accessToken)) fail("maritime_capafy_token_invalid");
    const [account, profile] = await Promise.all([
      request("GET", "/agent/account", { accessToken }),
      request("GET", "/agent/account/profile", { accessToken }),
    ]);
    const providerSubject = validSubject(profile.userId);
    if (account.role !== "developer" || account.developerVerified !== true || typeof account.email !== "string"
      || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(account.email.trim())) fail("maritime_capafy_developer_verification_required");
    return Object.freeze({ provider: "capafy", providerSubject,
      accountEmail: account.email.trim().toLowerCase(), developerVerified: true });
  }
  return Object.freeze({ startLogin, verifyLogin, readAccount });
}

function createMaritimeCapafyAccountBinding({ bindingStore, managerStore, connector } = {}) {
  if (!bindingStore || typeof bindingStore.read !== "function" || !managerStore || typeof managerStore.read !== "function"
    || !connector || typeof connector.readAccount !== "function") fail("maritime_capafy_binding_unavailable");
  async function resolveBinding({ tenantId, accountRef, mode = "readback" } = {}) {
    const uid = validTenant(tenantId);
    const enrollment = await managerStore.read(uid);
    if (!enrollment || enrollment.uid !== uid || !SUBJECT.test(String(enrollment.auth_subject || ""))
      || !["active", "paused", "effect_unknown"].includes(enrollment.status)) fail("maritime_capafy_tenant_inactive");
    if (!new Set(["action", "readback"]).has(mode)) fail("maritime_capafy_access_mode_invalid");
    if (mode === "action" && (enrollment.status !== "active" || enrollment.paused_at)) {
      fail("maritime_capafy_tenant_inactive");
    }
    const binding = await bindingStore.read({ tenantId: uid, authSubject: enrollment.auth_subject });
    if (binding.provider !== "capafy" || binding.tenantId !== uid
      || binding.autonomyConsentVersion !== CAPAFY_AUTONOMY_CONSENT_VERSION
      || (accountRef != null && binding.accountRef !== accountRef)) fail("maritime_capafy_binding_invalid");
    const official = await connector.readAccount(binding.accessToken);
    if (official.provider !== "capafy" || official.providerSubject !== binding.providerSubject
      || official.developerVerified !== true) fail("maritime_capafy_subject_mismatch");
    return Object.freeze({ accessToken: binding.accessToken,
      identity: Object.freeze({ provider: "capafy", tenantId: uid, accountRef: binding.accountRef,
        providerSubject: binding.providerSubject, autonomyConsentVersion: binding.autonomyConsentVersion }) });
  }
  async function resolve(identity) { return (await resolveBinding({ ...identity, mode: "readback" })).identity; }
  async function withAccessToken(identity, operation, options = {}) {
    if (typeof operation !== "function") fail("maritime_capafy_operation_invalid");
    const mode = options?.mode || "action";
    const verified = await resolveBinding({ tenantId: validTenant(identity?.tenantId), accountRef: identity?.accountRef, mode });
    return operation(verified.accessToken, verified.identity);
  }
  return Object.freeze({ readAccountBinding: resolve, withAccessToken });
}

module.exports = { CAPAFY_AUTONOMY_CONSENT_VERSION, CAPAFY_PUBLISHER_POLICY_CONSENT_VERSION,
  CAPAFY_TERMS_URL, CAPAFY_PRIVACY_URL, createMaritimeCapafyBindingStore,
  createCapafyAccountConnector, createMaritimeCapafyAccountBinding, sealChallenge, openChallenge };
