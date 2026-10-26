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
const SKILL_ID = "agent-1";
const DISCLOSURE_SHA256 = "a".repeat(64);
const currentPublisherConsent = tenantId => {
  const record = { tenantId, authSubject: SUBJECT, agreementVersion: "v1.2", effectiveDate: "2026-09-28",
    publisherType: "individual", legalName: "Test Publisher", jurisdiction: "Japan",
    verifiedContactEmail: "verified@example.test", publicSupportEmail: "support@example.test",
    ageOfMajorityAttested: true, entityAuthorityAttested: false, supportedRegionAttested: true,
    sanctionsEligibilityAttested: true, identityContactAccurateAttested: true,
    singlePublisherAccountAttested: true, certificationFeeNonRefundableAcknowledged: true,
    dataDisclosuresAccepted: true, supportObligationsAccepted: true, agreementAccepted: true,
    acceptedAt: NOW, withdrawnAt: null };
  return {
    readCurrent: async ({ tenantId: requested, authSubject }) => requested === tenantId && authSubject === SUBJECT
      ? { tenantId, authSubject: SUBJECT, agreementVersion: "v1.2", effectiveDate: "2026-09-28", acceptedAt: NOW } : null,
    readForTenant: async ({ tenantId: requested, authSubject }) => requested === tenantId && authSubject === SUBJECT ? record : null,
    readSkillDisclosure: async ({ tenantId: requested, authSubject, skillId, disclosureSha256 }) =>
      requested === tenantId && authSubject === SUBJECT && skillId === SKILL_ID && disclosureSha256 === DISCLOSURE_SHA256
        ? { tenantId, authSubject: SUBJECT, agreementVersion: "v1.2", skillId,
          disclosureSha256, acceptedAt: NOW, withdrawnAt: null } : null,
  };
};

test("Capafy OTP challenge is signed, time limited, and bound to the authenticated Life Manager identity", () => {
  const challenge = sealChallenge({ tenantId: UID, authSubject: SUBJECT, challengeId: "challenge-1",
    expiresInSec: 300, now: NOW, policyConsentVersion: "capafy-publisher-terms-privacy-v1",
    termsAcceptedAt: NOW, termsUrl: "https://api.capafy.ai/terms-of-service",
    privacyUrl: "https://api.capafy.ai/privacy-policy" }, "csrf-secret-longer");
  assert.deepEqual(openChallenge(challenge, { tenantId: UID, authSubject: SUBJECT,
    secret: "csrf-secret-longer", now: NOW }), { challengeId: "challenge-1", expiresAt: "2026-10-25T12:05:00.000Z",
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: NOW,
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy",
    mailboxVerification: false });
  assert.throws(() => openChallenge(challenge, { tenantId: "lm_22222222-2222-4222-8222-222222222222",
    authSubject: SUBJECT, secret: "csrf-secret-longer", now: NOW }), /invalid/i);
  assert.throws(() => openChallenge(challenge, { tenantId: UID, authSubject: "22222222-2222-4222-8222-222222222222",
    secret: "csrf-secret", now: NOW }), /invalid/i);
  assert.throws(() => openChallenge(challenge, { tenantId: UID, authSubject: SUBJECT,
    secret: "csrf-secret-longer", now: "2026-10-25T12:05:01.000Z" }), /expired/i);
  assert.throws(() => openChallenge(`${challenge.slice(0, -1)}x`, { tenantId: UID, authSubject: SUBJECT,
    secret: "csrf-secret-longer", now: NOW }), /invalid/i);
});

test("Capafy challenge records whether verification may use the tenant-owned mailbox", () => {
  const challenge = sealChallenge({ tenantId: UID, authSubject: SUBJECT, challengeId: "challenge-1",
    expiresInSec: 300, now: NOW, policyConsentVersion: "capafy-publisher-terms-privacy-v1",
    termsAcceptedAt: NOW, termsUrl: "https://api.capafy.ai/terms-of-service",
    privacyUrl: "https://api.capafy.ai/privacy-policy", mailboxVerification: true }, "csrf-secret-longer");
  assert.equal(openChallenge(challenge, { tenantId: UID, authSubject: SUBJECT,
    secret: "csrf-secret-longer", now: NOW }).mailboxVerification, true);
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
  let claimRow = null;
  const row = { uid: UID, auth_subject: SUBJECT, provider_subject: CAPAFY_SUBJECT,
    account_ref: `account://capafy/${UID}/${CAPAFY_SUBJECT}`, ciphertext: null, iv: null, tag: null,
    autonomy_consent_version: CAPAFY_AUTONOMY_CONSENT_VERSION,
    policy_consent_version: "capafy-publisher-terms-privacy-v1", terms_accepted_at: NOW,
    terms_url: "https://api.capafy.ai/terms-of-service", privacy_url: "https://api.capafy.ai/privacy-policy" };
  const store = createMaritimeCapafyBindingStore({ query: async (sql, values) => {
    queries.push({ sql, values });
    if (/INSERT INTO private\.lm_maritime_manager_capafy_publisher_account_claims/i.test(sql)) {
      claimRow = { uid: values[0], auth_subject: values[1], provider_subject: values[2], account_ref: values[3] };
      return { rows: [{ ...claimRow }] };
    }
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
    publisherAgreementVersion: "v1.2",
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
  const bindingInsert = queries.find(item => /INSERT INTO private\.lm_maritime_manager_capafy_bindings/i.test(item.sql));
  assert.match(bindingInsert.sql, /WHERE private\.lm_maritime_manager_capafy_bindings\.auth_subject=EXCLUDED\.auth_subject/);
  assert.equal(bindingInsert.values[0], UID);
  assert.equal(bindingInsert.values[1], SUBJECT);
  assert.deepEqual(claimRow, { uid: UID, auth_subject: SUBJECT, provider_subject: CAPAFY_SUBJECT,
    account_ref: row.account_ref });
});

test("Capafy binding refuses missing autonomy consent and tampered encrypted identity", async () => {
  const store = createMaritimeCapafyBindingStore({ query: async () => ({ rows: [] }), encryptionKey: KEY });
  await assert.rejects(store.save({ tenantId: UID, authSubject: SUBJECT, providerSubject: CAPAFY_SUBJECT,
    accessToken: TOKEN }), /consent/i);
  await assert.rejects(store.save({ tenantId: UID, authSubject: SUBJECT, providerSubject: CAPAFY_SUBJECT,
    accessToken: TOKEN, autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION,
    publisherAgreementVersion: "v1.2" }), /policy_consent/i);
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
  assert.match(migration, /CREATE TABLE IF NOT EXISTS private\.lm_maritime_manager_capafy_publisher_account_claims/i);
  assert.match(migration, /provider_subject uuid NOT NULL UNIQUE/i);
  assert.match(migration, /CREATE POLICY lm_maritime_manager_capafy_publisher_account_claims_service_role_access\s+ON private\.lm_maritime_manager_capafy_publisher_account_claims FOR ALL TO service_role/i);
  assert.match(migration, /GRANT SELECT, INSERT ON TABLE private\.lm_maritime_manager_capafy_publisher_account_claims TO service_role/i);
  assert.doesNotMatch(migration, /GRANT (?:SELECT, INSERT, UPDATE|ALL PRIVILEGES) ON TABLE private\.lm_maritime_manager_capafy_publisher_account_claims/i);
  assert.match(migration, /REVOKE ALL ON TABLE private\.lm_maritime_manager_capafy_publisher_account_claims FROM PUBLIC, anon, authenticated/i);
  assert.match(migration, /FROM private\.lm_maritime_manager_capafy_bindings\s+ON CONFLICT \(uid\) DO NOTHING/i);
  assert.match(migration, /CREATE TABLE IF NOT EXISTS private\.lm_maritime_manager_capafy_recovery_cursor/i);
  assert.match(migration, /CREATE POLICY lm_maritime_manager_capafy_recovery_cursor_service_role_access\s+ON private\.lm_maritime_manager_capafy_recovery_cursor FOR ALL TO service_role\s+USING \(true\) WITH CHECK \(true\)/i);
  assert.match(migration, /REVOKE ALL ON TABLE private\.lm_maritime_manager_capafy_recovery_cursor FROM PUBLIC, anon, authenticated/i);
  assert.match(migration, /GRANT SELECT, UPDATE ON TABLE private\.lm_maritime_manager_capafy_recovery_cursor TO service_role/i);
});

test("Capafy Postgres integration test streams service_role assertions into psql", () => {
  const integration = fs.readFileSync(path.join(__dirname, "../test/postgres/maritime-capafy-bindings.integration.sh"), "utf8");
  assert.match(integration, /docker exec -i "\$DOCKER_NAME" psql[^\n]*<<'SQL'\nSET ROLE service_role;/);
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

test("concurrent verified account binds claim one Publisher identity per tenant and preserve it after unlink", async () => {
  let claim = null, binding = null, claimWrites = 0;
  const query = async (sql, values) => {
    if (/INSERT INTO private\.lm_maritime_manager_capafy_publisher_account_claims/i.test(sql)) {
      claimWrites++;
      if (!claim) {
        claim = { uid: values[0], auth_subject: values[1], provider_subject: values[2], account_ref: values[3] };
        return { rows: [{ ...claim }] };
      }
      return { rows: [] };
    }
    if (/SELECT uid,auth_subject,provider_subject,account_ref\s+FROM private\.lm_maritime_manager_capafy_publisher_account_claims/i.test(sql)) {
      assert.deepEqual(values, [UID]);
      return claim?.uid === values[0] ? { rows: [{ ...claim }] } : { rows: [] };
    }
    if (/INSERT INTO private\.lm_maritime_manager_capafy_bindings/i.test(sql)) {
      const [uid, subject, providerSubject, accountRef] = values;
      if (binding && (binding.uid !== uid || binding.provider_subject !== providerSubject)) return { rows: [] };
      binding ||= { uid, auth_subject: subject, provider_subject: providerSubject, account_ref: accountRef };
      return { rows: [{ ...binding, autonomy_consent_version: CAPAFY_AUTONOMY_CONSENT_VERSION,
        policy_consent_version: "capafy-publisher-terms-privacy-v1", terms_accepted_at: NOW,
        terms_url: "https://api.capafy.ai/terms-of-service", privacy_url: "https://api.capafy.ai/privacy-policy" }] };
    }
    if (/DELETE FROM private\.lm_maritime_manager_capafy_bindings/i.test(sql)) {
      const existed = binding?.uid === values[0] && binding?.auth_subject === values[1];
      if (existed) binding = null;
      return { rows: existed ? [{ uid: values[0], auth_subject: values[1] }] : [] };
    }
    throw new Error("unexpected query");
  };
  const store = createMaritimeCapafyBindingStore({ query, encryptionKey: KEY, now: () => NOW });
  const common = { tenantId: UID, authSubject: SUBJECT, accessToken: TOKEN,
    autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION,
    publisherAgreementVersion: "v1.2", policyConsentVersion: "capafy-publisher-terms-privacy-v1",
    termsAcceptedAt: NOW, termsUrl: "https://api.capafy.ai/terms-of-service",
    privacyUrl: "https://api.capafy.ai/privacy-policy" };
  const subjects = [CAPAFY_SUBJECT, "019d3c7f-fe51-7c57-aa2e-8e1055bb36a6"];
  const writes = await Promise.allSettled(subjects.map(providerSubject => store.save({ ...common, providerSubject })));
  assert.equal(writes.filter(result => result.status === "fulfilled").length, 1);
  assert.equal(writes.filter(result => result.status === "rejected").length, 1);
  assert.equal(claimWrites, 2);
  const winner = claim.provider_subject;
  assert.deepEqual(claim, { uid: UID, auth_subject: SUBJECT, provider_subject: winner,
    account_ref: `account://capafy/${UID}/${winner}` });
  const reused = await store.save({ ...common, providerSubject: winner });
  assert.equal(reused.providerSubject, winner);
  assert.equal(JSON.stringify(reused).includes(TOKEN), false);
  assert.equal(await store.disconnect({ tenantId: UID, authSubject: SUBJECT }), true);
  const reconnected = await store.save({ ...common, providerSubject: winner });
  assert.equal(reconnected.providerSubject, winner);
  await assert.rejects(store.save({ ...common, providerSubject: subjects.find(subject => subject !== winner) }), /account_already_claimed/i);
  assert.equal(claim.provider_subject, winner);
});

test("Publisher claim distinguishes database uniqueness conflicts from outages without leaking details", async () => {
  const common = { tenantId: UID, authSubject: SUBJECT, providerSubject: CAPAFY_SUBJECT, accessToken: TOKEN,
    autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION, publisherAgreementVersion: "v1.2",
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: NOW,
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy" };
  const outcomes = [];
  for (const [code, expected] of [["23505", "maritime_capafy_account_already_claimed"],
    ["08006", "maritime_capafy_account_claim_unavailable"]]) {
    const store = createMaritimeCapafyBindingStore({ encryptionKey: KEY, now: () => NOW,
      query: async () => { const error = new Error(`database detail ${TOKEN}`); error.code = code; throw error; } });
    await assert.rejects(store.save(common), error => { outcomes.push(error.message); return error.message === expected; });
  }
  assert.doesNotMatch(JSON.stringify(outcomes), /database detail|am_sk_/);
});

test("host account binding checks the live official subject, tenant enrollment, account ref, and consent before exposing a credential", async () => {
  let tenantId = UID, authSubject = SUBJECT, accountRef = `account://capafy/${UID}/${CAPAFY_SUBJECT}`;
  let officialSubject = CAPAFY_SUBJECT, tokenReads = 0, callbackToken = null;
  const binding = createMaritimeCapafyAccountBinding({
    publisherConsentStore: currentPublisherConsent(UID),
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
    autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION, publisherAgreementVersion: "v1.2",
  });
  assert.equal(JSON.stringify(await binding.readAccountBinding({ tenantId: UID, accountRef })).includes(TOKEN), false);
  const readsBeforeAccess = tokenReads;
  await binding.withAccessToken({ tenantId: UID, accountRef }, async token => { callbackToken = token; return true; },
    { skillId: SKILL_ID, disclosureSha256: DISCLOSURE_SHA256 });
  assert.equal(callbackToken, TOKEN);
  assert.equal(tokenReads, readsBeforeAccess + 1);
  await assert.rejects(binding.readAccountBinding({ tenantId: UID, accountRef: "account://capafy/foreign" }), /invalid/i);
  officialSubject = "019d3c7f-fe51-7c57-aa2e-8e1055bb36a6";
  await assert.rejects(binding.readAccountBinding({ tenantId: UID, accountRef }), /subject/i);
  officialSubject = CAPAFY_SUBJECT;
  tenantId = "lm_22222222-2222-4222-8222-222222222222";
  await assert.rejects(binding.readAccountBinding({ tenantId, accountRef }), /publisher_agreement_consent_required/i);
  tenantId = UID;
  authSubject = "22222222-2222-4222-8222-222222222222";
  await assert.rejects(binding.readAccountBinding({ tenantId: UID, accountRef }), /publisher_agreement_consent_required/i);
});

test("paused tenant can use its bound token for provider readback while action admission stays elsewhere", async () => {
  const accountRef = `account://capafy/${UID}/${CAPAFY_SUBJECT}`;
  let connectorReads = 0;
  const binding = createMaritimeCapafyAccountBinding({
    publisherConsentStore: currentPublisherConsent(UID),
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

test("Capafy token access stops before binding or provider reads when agreement consent is missing or stale", async () => {
  for (const current of [null, { tenantId: UID, authSubject: SUBJECT,
    agreementVersion: "v1.1", effectiveDate: "2026-09-28", acceptedAt: NOW }]) {
    let bindingReads = 0, officialReads = 0, actionCalls = 0;
    const binding = createMaritimeCapafyAccountBinding({
      publisherConsentStore: { readCurrent: async () => current, readForTenant: async () => null,
        readSkillDisclosure: async () => null },
      managerStore: { read: async uid => ({ uid, auth_subject: SUBJECT, status: "active", paused_at: null }) },
      bindingStore: { read: async () => { bindingReads++; return { provider: "capafy", tenantId: UID,
        providerSubject: CAPAFY_SUBJECT, accountRef: `account://capafy/${UID}/${CAPAFY_SUBJECT}`,
        autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION, accessToken: TOKEN }; } },
      connector: { readAccount: async () => { officialReads++; return { provider: "capafy",
        providerSubject: CAPAFY_SUBJECT, developerVerified: true }; } },
    });
    await assert.rejects(binding.withAccessToken({ tenantId: UID, accountRef: `account://capafy/${UID}/${CAPAFY_SUBJECT}` },
      async () => { actionCalls++; }), /publisher_agreement_consent_required/i);
    assert.deepEqual({ bindingReads, officialReads, actionCalls }, { bindingReads: 0, officialReads: 0, actionCalls: 0 });
  }
});

test("withdrawing the current Publisher consent closes the Capafy token action gate", async () => {
  let withdrawn = false, bindingReads = 0, officialReads = 0, actionCalls = 0;
  const validConsent = currentPublisherConsent(UID), current = validConsent.readCurrent;
  const publisherConsentStore = {
    readForTenant: validConsent.readForTenant,
    readSkillDisclosure: validConsent.readSkillDisclosure,
    readCurrent: async input => withdrawn ? null : current(input),
    withdraw: async input => { assert.deepEqual(input, { tenantId: UID, authSubject: SUBJECT }); withdrawn = true; return true; },
  };
  const accountRef = `account://capafy/${UID}/${CAPAFY_SUBJECT}`;
  const binding = createMaritimeCapafyAccountBinding({ publisherConsentStore,
    managerStore: { read: async uid => ({ uid, auth_subject: SUBJECT, status: "active", paused_at: null }) },
    bindingStore: { read: async () => { bindingReads++; return { provider: "capafy", tenantId: UID,
      providerSubject: CAPAFY_SUBJECT, accountRef, autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION,
      accessToken: TOKEN }; } },
    connector: { readAccount: async () => { officialReads++; return { provider: "capafy",
      providerSubject: CAPAFY_SUBJECT, developerVerified: true }; } },
  });
  await publisherConsentStore.withdraw({ tenantId: UID, authSubject: SUBJECT });
  await assert.rejects(binding.withAccessToken({ tenantId: UID, accountRef }, async () => { actionCalls++; }),
    /publisher_agreement_consent_required/i);
  assert.deepEqual({ bindingReads, officialReads, actionCalls }, { bindingReads: 0, officialReads: 0, actionCalls: 0 });
});

test("Capafy action stops at a missing Skill-specific disclosure before token or provider access", async () => {
  let bindingReads = 0, officialReads = 0, actionCalls = 0;
  const consent = currentPublisherConsent(UID);
  const publisherConsentStore = { ...consent, readSkillDisclosure: async () => null };
  const accountRef = `account://capafy/${UID}/${CAPAFY_SUBJECT}`;
  const binding = createMaritimeCapafyAccountBinding({ publisherConsentStore,
    managerStore: { read: async uid => ({ uid, auth_subject: SUBJECT, status: "active", paused_at: null }) },
    bindingStore: { read: async () => { bindingReads++; return { provider: "capafy", tenantId: UID,
      providerSubject: CAPAFY_SUBJECT, accountRef, autonomyConsentVersion: CAPAFY_AUTONOMY_CONSENT_VERSION,
      accessToken: TOKEN }; } },
    connector: { readAccount: async () => { officialReads++; return { provider: "capafy",
      providerSubject: CAPAFY_SUBJECT, developerVerified: true }; } },
  });
  await assert.rejects(binding.withAccessToken({ tenantId: UID, accountRef }, async () => { actionCalls++; },
    { skillId: SKILL_ID, disclosureSha256: DISCLOSURE_SHA256 }), /skill_data_disclosure_required/i);
  assert.deepEqual({ bindingReads, officialReads, actionCalls }, { bindingReads: 0, officialReads: 0, actionCalls: 0 });
});
