"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createMaritimeCapafyBindingStore, createCapafyAccountConnector, createMaritimeCapafyAccountBinding, sealChallenge, openChallenge,
  CAPAFY_AUTONOMY_CONSENT_VERSION } = require("./maritime-manager-capafy-binding.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const SUBJECT = "11111111-1111-4111-8111-111111111111";
const CAPAFY_SUBJECT = "019d3c7f-fe51-7c57-aa2e-8e1055bb36a5";
const KEY = "a".repeat(64);
const TOKEN = "am_sk_" + "x".repeat(32);
const NOW = "2026-10-25T12:00:00.000Z";

test("Capafy OTP challenge is signed, time limited, and bound to the authenticated Life Manager identity", () => {
  const challenge = sealChallenge({ tenantId: UID, authSubject: SUBJECT, challengeId: "challenge-1",
    expiresInSec: 300, now: NOW, policyConsentVersion: "capafy-publisher-terms-privacy-v1",
    termsAcceptedAt: NOW, termsUrl: "https://api.capafy.ai/terms-of-service",
    privacyUrl: "https://api.capafy.ai/privacy-policy" }, "csrf-secret-longer");
  assert.deepEqual(openChallenge(challenge, { tenantId: UID, authSubject: SUBJECT,
    secret: "csrf-secret-longer", now: NOW }), { challengeId: "challenge-1", expiresAt: "2026-10-25T12:05:00.000Z",
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: NOW,
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy" });
  assert.throws(() => openChallenge(challenge, { tenantId: "lm_22222222-2222-4222-8222-222222222222",
    authSubject: SUBJECT, secret: "csrf-secret-longer", now: NOW }), /invalid/i);
  assert.throws(() => openChallenge(challenge, { tenantId: UID, authSubject: "22222222-2222-4222-8222-222222222222",
    secret: "csrf-secret", now: NOW }), /invalid/i);
  assert.throws(() => openChallenge(challenge, { tenantId: UID, authSubject: SUBJECT,
    secret: "csrf-secret-longer", now: "2026-10-25T12:05:01.000Z" }), /expired/i);
  assert.throws(() => openChallenge(`${challenge.slice(0, -1)}x`, { tenantId: UID, authSubject: SUBJECT,
    secret: "csrf-secret-longer", now: NOW }), /invalid/i);
});

test("Capafy login sends OTP only to requested account and binds verified API subject to the challenge account", async () => {
  const requests = [];
  const connector = createCapafyAccountConnector({ now: () => NOW, fetchImpl: async (url, options) => {
    requests.push({ url: new URL(url), options });
    const path = new URL(url).pathname;
    const payload = path === "/auth/login" ? { code: 0, data: { challengeId: "challenge-1", expiresInSec: 300 } }
      : path === "/auth/login/verify" ? { code: 0, data: { accessToken: TOKEN, userId: CAPAFY_SUBJECT,
        email: "seller@example.com", status: "active" } }
        : path === "/agent/account" ? { code: 0, data: { email: "seller@example.com", role: "developer", developerVerified: true } }
          : { code: 0, data: { userId: CAPAFY_SUBJECT, profile: null } };
    return new Response(JSON.stringify(payload), { status: 200 });
  } });
  const started = await connector.startLogin("seller@example.com");
  assert.deepEqual(started, { challengeId: "challenge-1", expiresInSec: 300 });
  const identity = await connector.verifyLogin({ challengeId: started.challengeId, code: "004219" });
  assert.deepEqual(identity, { provider: "capafy", providerSubject: CAPAFY_SUBJECT,
    accountEmail: "seller@example.com", developerVerified: true, accessToken: TOKEN });
  assert.equal(requests[0].url.origin, "https://api.capafy.ai");
  assert.deepEqual(JSON.parse(requests[0].options.body), { loginMethod: "email", email: "seller@example.com" });
  assert.deepEqual(JSON.parse(requests[1].options.body), { challengeId: "challenge-1", code: "004219", source: "agent" });
  assert.equal(requests[2].options.headers.authorization, `Bearer ${TOKEN}`);
  assert.equal(requests[3].options.headers.authorization, `Bearer ${TOKEN}`);
  await assert.rejects(connector.verifyLogin({ challengeId: "bad", code: "123456" }), /invalid/i);
});

test("Capafy connector rejects consumer, unverified, or subject-mismatched accounts", async () => {
  for (const account of [
    { code: 0, data: { email: "seller@example.com", role: "consumer", developerVerified: true } },
    { code: 0, data: { email: "seller@example.com", role: "developer", developerVerified: false } },
  ]) {
    let accountRead = 0;
    const connector = createCapafyAccountConnector({ fetchImpl: async url => {
      const path = new URL(url).pathname;
      const data = path === "/auth/login/verify" ? { code: 0, data: { accessToken: TOKEN,
        userId: CAPAFY_SUBJECT, email: "seller@example.com", status: "active" } }
        : path === "/agent/account" ? (accountRead++, account)
          : { code: 0, data: { userId: CAPAFY_SUBJECT, profile: null } };
      return new Response(JSON.stringify(data), { status: 200 });
    } });
    await assert.rejects(connector.verifyLogin({ challengeId: "challenge-1", code: "004219" }), /developer/i);
  }
  const mismatch = createCapafyAccountConnector({ fetchImpl: async url => {
    const path = new URL(url).pathname;
    const data = path === "/auth/login/verify" ? { code: 0, data: { accessToken: TOKEN,
      userId: CAPAFY_SUBJECT, email: "seller@example.com", status: "active" } }
      : path === "/agent/account" ? { code: 0, data: { email: "seller@example.com", role: "developer", developerVerified: true } }
        : { code: 0, data: { userId: "019d3c7f-fe51-7c57-aa2e-8e1055bb36a6", profile: null } };
    return new Response(JSON.stringify(data), { status: 200 });
  } });
  await assert.rejects(mismatch.verifyLogin({ challengeId: "challenge-1", code: "004219" }), /subject/i);
});

test("Capafy access tokens are encrypted at rest with tenant and owner authenticated data and never returned in public binding", async () => {
  const queries = [];
  const row = { uid: UID, auth_subject: SUBJECT, provider_subject: CAPAFY_SUBJECT,
    account_ref: `account://capafy/${UID}/${CAPAFY_SUBJECT}`, ciphertext: null, iv: null, tag: null,
    autonomy_consent_version: CAPAFY_AUTONOMY_CONSENT_VERSION,
    policy_consent_version: "capafy-publisher-terms-privacy-v1", terms_accepted_at: NOW,
    terms_url: "https://api.capafy.ai/terms-of-service", privacy_url: "https://api.capafy.ai/privacy-policy" };
  const store = createMaritimeCapafyBindingStore({ query: async (sql, values) => {
    queries.push({ sql, values });
    if (/INSERT INTO private\.lm_maritime_manager_capafy_bindings/i.test(sql)) {
      const [uid, subject, providerSubject, accountRef, ciphertext, iv, tag, consent,
        policyVersion, termsAcceptedAt, termsUrl, privacyUrl] = values;
      Object.assign(row, { uid, auth_subject: subject, provider_subject: providerSubject, account_ref: accountRef,
        ciphertext: Buffer.from(ciphertext), iv: Buffer.from(iv), tag: Buffer.from(tag), autonomy_consent_version: consent,
        policy_consent_version: policyVersion, terms_accepted_at: termsAcceptedAt,
        terms_url: termsUrl, privacy_url: privacyUrl });
      return { rows: [{ uid, auth_subject: subject, provider_subject: providerSubject, account_ref: accountRef,
        autonomy_consent_version: consent, policy_consent_version: policyVersion,
        terms_accepted_at: termsAcceptedAt, terms_url: termsUrl, privacy_url: privacyUrl }] };
    }
    if (/SELECT uid,auth_subject,provider_subject,account_ref,ciphertext,iv,tag,autonomy_consent_version,\s*policy_consent_version,\s*terms_accepted_at,\s*terms_url,\s*privacy_url/i.test(sql)) {
      return row.uid === values[0] && row.auth_subject === values[1] ? { rows: [{ ...row }] } : { rows: [] };
    }
    if (/SELECT uid,auth_subject,provider_subject,account_ref,autonomy_consent_version/i.test(sql)) {
      const { uid, auth_subject, provider_subject, account_ref, autonomy_consent_version,
        policy_consent_version, terms_accepted_at, terms_url, privacy_url } = row;
      return row.uid === values[0] && row.auth_subject === values[1]
        ? { rows: [{ uid, auth_subject, provider_subject, account_ref, autonomy_consent_version,
          policy_consent_version, terms_accepted_at, terms_url, privacy_url }] } : { rows: [] };
    }
    throw new Error("unexpected query");
  }, encryptionKey: KEY });
  const saved = await store.save({ tenantId: UID, authSubject: SUBJECT, providerSubject: CAPAFY_SUBJECT,
    accessToken: TOKEN, autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION,
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: NOW,
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy" });
  assert.equal(saved.accountRef, row.account_ref);
  assert.equal(saved.provider, "capafy");
  assert.equal(JSON.stringify(row).includes(TOKEN), false);
  assert.equal(row.ciphertext.toString("utf8").includes(TOKEN), false);
  const loaded = await store.read({ tenantId: UID, authSubject: SUBJECT });
  assert.equal(loaded.accessToken, TOKEN);
  assert.equal(loaded.providerSubject, CAPAFY_SUBJECT);
  assert.deepEqual({ policyConsentVersion: loaded.policyConsentVersion, termsAcceptedAt: loaded.termsAcceptedAt,
    termsUrl: loaded.termsUrl, privacyUrl: loaded.privacyUrl }, { policyConsentVersion: "capafy-publisher-terms-privacy-v1",
    termsAcceptedAt: NOW, termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy" });
  const status = await store.readStatus({ tenantId: UID, authSubject: SUBJECT });
  assert.deepEqual(status, { connected: true, provider: "capafy", tenantId: UID,
    accountRef: row.account_ref, autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION,
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: NOW,
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy" });
  assert.equal(JSON.stringify(status).includes(TOKEN), false);
  await assert.rejects(store.read({ tenantId: UID, authSubject: "22222222-2222-4222-8222-222222222222" }), /unavailable/i);
  assert.match(queries[0].sql, /WHERE private\.lm_maritime_manager_capafy_bindings\.auth_subject=EXCLUDED\.auth_subject/);
  assert.equal(queries[0].values[0], UID);
  assert.equal(queries[0].values[1], SUBJECT);
});

test("Capafy binding refuses missing autonomy consent and tampered encrypted identity", async () => {
  const store = createMaritimeCapafyBindingStore({ query: async () => ({ rows: [] }), encryptionKey: KEY });
  await assert.rejects(store.save({ tenantId: UID, authSubject: SUBJECT, providerSubject: CAPAFY_SUBJECT,
    accessToken: TOKEN }), /consent/i);
  await assert.rejects(store.save({ tenantId: UID, authSubject: SUBJECT, providerSubject: CAPAFY_SUBJECT,
    accessToken: TOKEN, autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION }), /policy_consent/i);
  const challenge = sealChallenge({ tenantId: UID, authSubject: SUBJECT, challengeId: "challenge-1", expiresInSec: 300,
    now: NOW, policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: NOW,
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy" }, "secret-long-enough");
  assert.throws(() => openChallenge(challenge, { tenantId: UID, authSubject: SUBJECT, secret: "other", now: NOW }), /invalid/i);
});

test("private binding migration denies public roles and keys credentials to the enrollment owner", () => {
  const migration = fs.readFileSync(path.join(__dirname, "../migrations/20261025134600_maritime_manager_capafy_bindings.sql"), "utf8");
  assert.match(migration, /private\.lm_maritime_manager_capafy_bindings/i);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/i);
  assert.match(migration, /CREATE POLICY lm_maritime_manager_capafy_bindings_service_role_access\s+ON private\.lm_maritime_manager_capafy_bindings FOR ALL TO service_role\s+USING \(true\) WITH CHECK \(true\)/i);
  assert.match(migration, /REVOKE ALL ON TABLE private\.lm_maritime_manager_capafy_bindings FROM PUBLIC, anon, authenticated/i);
  assert.match(migration, /FOREIGN KEY \(uid, auth_subject\)[\s\S]*REFERENCES public\.lm_maritime_manager_enrollments\(uid, auth_subject\)/i);
  assert.match(migration, /CREATE UNIQUE INDEX IF NOT EXISTS lm_maritime_manager_enrollments_uid_auth_subject\s+ON public\.lm_maritime_manager_enrollments \(uid, auth_subject\)/i);
  assert.match(migration, /autonomy_consent_version = 'maritime-capafy-autonomy-v1'/i);
  assert.match(migration, /policy_consent_version = 'capafy-publisher-terms-privacy-v1'/i);
  assert.match(migration, /terms_accepted_at IS NOT NULL/i);
  assert.match(migration, /CREATE TABLE IF NOT EXISTS private\.lm_maritime_manager_capafy_recovery_cursor/i);
  assert.match(migration, /CREATE POLICY lm_maritime_manager_capafy_recovery_cursor_service_role_access\s+ON private\.lm_maritime_manager_capafy_recovery_cursor FOR ALL TO service_role\s+USING \(true\) WITH CHECK \(true\)/i);
  assert.match(migration, /REVOKE ALL ON TABLE private\.lm_maritime_manager_capafy_recovery_cursor FROM PUBLIC, anon, authenticated/i);
  assert.match(migration, /GRANT SELECT, UPDATE ON TABLE private\.lm_maritime_manager_capafy_recovery_cursor TO service_role/i);
});

test("Capafy unlink remains available when encryption-key configuration is unavailable", async () => {
  let deleted = false;
  const store = createMaritimeCapafyBindingStore({ query: async (sql, values) => {
    assert.match(sql, /^DELETE FROM private\.lm_maritime_manager_capafy_bindings/i);
    assert.deepEqual(values, [UID, SUBJECT]);
    deleted = true;
    return { rows: [{ uid: UID, auth_subject: SUBJECT }] };
  } });
  assert.equal(await store.disconnect({ tenantId: UID, authSubject: SUBJECT }), true);
  assert.equal(deleted, true);
  assert.throws(() => store.assertConfigured(), /encryption/i);
});

test("host account binding checks the live official subject, tenant enrollment, account ref, and consent before exposing a credential", async () => {
  let tenantId = UID, authSubject = SUBJECT, accountRef = `account://capafy/${UID}/${CAPAFY_SUBJECT}`;
  let officialSubject = CAPAFY_SUBJECT, tokenReads = 0, callbackToken = null;
  const binding = createMaritimeCapafyAccountBinding({
    managerStore: { read: async uid => uid === tenantId ? { uid, auth_subject: authSubject, status: "active", paused_at: null } : null },
    bindingStore: { read: async input => {
      if (input.tenantId !== UID || input.authSubject !== SUBJECT) throw new Error("binding unavailable");
      tokenReads++;
      return { provider: "capafy", tenantId: UID, authSubject: SUBJECT, providerSubject: CAPAFY_SUBJECT,
        accountRef, autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION, accessToken: TOKEN };
    } },
    connector: { readAccount: async token => {
      assert.equal(token, TOKEN);
      return { provider: "capafy", providerSubject: officialSubject, accountEmail: "seller@example.com", developerVerified: true };
    } },
  });
  assert.deepEqual(await binding.readAccountBinding({ tenantId: UID, accountRef }), {
    provider: "capafy", tenantId: UID, accountRef, providerSubject: CAPAFY_SUBJECT,
    autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION,
  });
  assert.equal(JSON.stringify(await binding.readAccountBinding({ tenantId: UID, accountRef })).includes(TOKEN), false);
  const readsBeforeAccess = tokenReads;
  await binding.withAccessToken({ tenantId: UID, accountRef }, async token => { callbackToken = token; return true; });
  assert.equal(callbackToken, TOKEN);
  assert.equal(tokenReads, readsBeforeAccess + 1);
  await assert.rejects(binding.readAccountBinding({ tenantId: UID, accountRef: "account://capafy/foreign" }), /invalid/i);
  officialSubject = "019d3c7f-fe51-7c57-aa2e-8e1055bb36a6";
  await assert.rejects(binding.readAccountBinding({ tenantId: UID, accountRef }), /subject/i);
  officialSubject = CAPAFY_SUBJECT;
  tenantId = "lm_22222222-2222-4222-8222-222222222222";
  await assert.rejects(binding.readAccountBinding({ tenantId, accountRef }), /unavailable/i);
  tenantId = UID;
  authSubject = "22222222-2222-4222-8222-222222222222";
  await assert.rejects(binding.readAccountBinding({ tenantId: UID, accountRef }), /unavailable/i);
});

test("paused tenant can use its bound token for provider readback while action admission stays elsewhere", async () => {
  const accountRef = `account://capafy/${UID}/${CAPAFY_SUBJECT}`;
  let connectorReads = 0;
  const binding = createMaritimeCapafyAccountBinding({
    managerStore: { read: async uid => ({ uid, auth_subject: SUBJECT, status: "paused",
      paused_at: "2026-10-25T11:00:00.000Z" }) },
    bindingStore: { read: async input => {
      assert.deepEqual(input, { tenantId: UID, authSubject: SUBJECT });
      return { provider: "capafy", tenantId: UID, authSubject: SUBJECT, providerSubject: CAPAFY_SUBJECT,
        accountRef, autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION, accessToken: TOKEN };
    } },
    connector: { readAccount: async token => {
      connectorReads++;
      assert.equal(token, TOKEN);
      return { provider: "capafy", providerSubject: CAPAFY_SUBJECT, developerVerified: true };
    } },
  });
  let callbackToken, actionCalls = 0;
  await assert.rejects(binding.withAccessToken({ tenantId: UID, accountRef }, async () => { actionCalls++; }), /inactive/i);
  assert.equal(actionCalls, 0);
  await binding.withAccessToken({ tenantId: UID, accountRef }, async token => { callbackToken = token; }, { mode: "readback" });
  assert.equal(callbackToken, TOKEN);
  assert.equal(connectorReads, 1);
});
