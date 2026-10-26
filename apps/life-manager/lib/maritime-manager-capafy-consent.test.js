"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createMaritimeCapafyPublisherConsentStore } = require("./maritime-manager-capafy-consent.js");

const TENANT = "lm_11111111-1111-4111-8111-111111111111";
const SUBJECT = "11111111-1111-4111-8111-111111111111";
const NOW = "2026-10-27T00:55:00.000Z";
const consent = () => ({
  agreementVersion: "v1.2",
  publisherType: "individual",
  legalName: "Test Publisher",
  jurisdiction: "Japan",
  publicSupportEmail: "support@example.test",
  ageOfMajorityAttested: true,
  entityAuthorityAttested: false,
  supportedRegionAttested: true,
  sanctionsEligibilityAttested: true,
  identityContactAccurateAttested: true,
  singlePublisherAccountAttested: true,
  certificationFeeNonRefundableAcknowledged: true,
  dataDisclosuresAccepted: true,
  supportObligationsAccepted: true,
  agreementAccepted: true,
});

test("publisher consent stores the exact agreement and tenant facts but returns no identity or email", async () => {
  const writes = [];
  const store = createMaritimeCapafyPublisherConsentStore({
    now: () => NOW,
    query: async (sql, values) => {
      writes.push({ sql, values });
      return { rows: [{ uid: TENANT, auth_subject: SUBJECT, agreement_version: "v1.2",
        effective_date: "2026-09-28", agreement_url: "https://capafy.ai/publisher-agreement/",
        certification_fee_usd: "0.99", accepted_at: NOW, consent_digest: values.at(-1) }] };
    },
  });

  const receipt = await store.record({ tenantId: TENANT, authSubject: SUBJECT,
    verifiedContactEmail: "verified@example.test", consent: consent() });

  assert.deepEqual(receipt, { tenantId: TENANT, authSubject: SUBJECT, agreementVersion: "v1.2",
    effectiveDate: "2026-09-28", agreementUrl: "https://capafy.ai/publisher-agreement/", certificationFeeUsd: "0.99",
    acceptedAt: NOW });
  assert.match(writes[0].sql, /private\.lm_maritime_manager_capafy_publisher_consents/i);
  assert.deepEqual(writes[0].values.slice(0, 7), [TENANT, SUBJECT, "v1.2", "2026-09-28",
    "https://capafy.ai/publisher-agreement/", "individual", "Test Publisher"]);
  assert.ok(writes[0].values.includes("verified@example.test"));
  assert.ok(writes[0].values.includes("support@example.test"));
  assert.ok(writes[0].values.includes("0.99"));
  assert.doesNotMatch(JSON.stringify(receipt), /Test Publisher|verified@example\.test|support@example\.test|am_sk_/i);
});

test("stale Publisher Agreement versions and incomplete attestations are rejected before persistence", async () => {
  let writes = 0;
  const store = createMaritimeCapafyPublisherConsentStore({ query: async () => { writes++; return { rows: [] }; } });
  await assert.rejects(store.record({ tenantId: TENANT, authSubject: SUBJECT,
    verifiedContactEmail: "verified@example.test", consent: { ...consent(), agreementVersion: "v1.1" } }),
  /agreement_version/i);
  await assert.rejects(store.record({ tenantId: TENANT, authSubject: SUBJECT,
    verifiedContactEmail: "verified@example.test", consent: { ...consent(), publicSupportEmail: "" } }),
  /consent_invalid/i);
  await assert.rejects(store.record({ tenantId: TENANT, authSubject: SUBJECT,
    verifiedContactEmail: "verified@example.test", consent: { ...consent(), dataDisclosuresAccepted: false } }),
  /consent_required/i);
  assert.equal(writes, 0);
});

test("Publisher consent requires age or entity authority and valid tenant identity inputs", async () => {
  let writes = 0;
  const store = createMaritimeCapafyPublisherConsentStore({ query: async () => { writes++; return { rows: [] }; } });
  await assert.rejects(store.record({ tenantId: "not-a-tenant", authSubject: SUBJECT,
    verifiedContactEmail: "verified@example.test", consent: consent() }), /identity_invalid/i);
  await assert.rejects(store.record({ tenantId: TENANT, authSubject: SUBJECT,
    verifiedContactEmail: "verified@example.test", consent: { ...consent(), entityAuthorityAttested: true } }),
  /consent_required/i);
  await assert.rejects(store.record({ tenantId: TENANT, authSubject: SUBJECT,
    verifiedContactEmail: "verified@example.test", consent: { ...consent(), ageOfMajorityAttested: false } }),
  /consent_required/i);
  assert.equal(writes, 0);
});

test("current-consent readback rejects an old agreement row and reveals no stored contact facts", async () => {
  let row = { uid: TENANT, auth_subject: SUBJECT, agreement_version: "v1.1",
    effective_date: "2026-09-28", agreement_url: "https://capafy.ai/publisher-agreement/",
    certification_fee_usd: "0.99", accepted_at: NOW };
  const store = createMaritimeCapafyPublisherConsentStore({ now: () => NOW, query: async () => ({ rows: [row] }) });
  assert.equal(await store.readCurrent({ tenantId: TENANT, authSubject: SUBJECT }), null);
  row = { ...row, agreement_version: "v1.2" };
  const current = await store.readCurrent({ tenantId: TENANT, authSubject: SUBJECT });
  assert.deepEqual(current, { tenantId: TENANT, authSubject: SUBJECT, agreementVersion: "v1.2",
    effectiveDate: "2026-09-28", agreementUrl: "https://capafy.ai/publisher-agreement/",
    certificationFeeUsd: "0.99", acceptedAt: NOW });
  assert.doesNotMatch(JSON.stringify(current), /legalName|supportEmail|verifiedContactEmail|am_sk_/i);
});

test("one-time consent retries are idempotent but cannot replace same-version identity or support facts", async () => {
  let row = null;
  const store = createMaritimeCapafyPublisherConsentStore({ now: () => NOW, query: async (sql, values) => {
    if (/^INSERT INTO/i.test(sql)) {
      if (row) return { rows: [] };
      row = { uid: values[0], auth_subject: values[1], agreement_version: values[2],
        effective_date: values[3], agreement_url: values[4], certification_fee_usd: values[16],
        public_support_email: values[9], accepted_at: values[23], consent_digest: values[24] };
      return { rows: [row] };
    }
    return { rows: [row] };
  } });
  const input = { tenantId: TENANT, authSubject: SUBJECT, verifiedContactEmail: "verified@example.test", consent: consent() };
  const first = await store.record(input);
  assert.deepEqual(await store.record(input), first);
  await assert.rejects(store.record({ ...input, consent: { ...consent(), publicSupportEmail: "new@example.test" } }),
    /consent_already_recorded/i);
  assert.equal(row.public_support_email, "support@example.test");
});

test("consent migration keeps legal facts tenant-bound and inaccessible to public roles", () => {
  const migration = fs.readFileSync(path.join(__dirname,
    "../migrations/20261027005500_maritime_manager_capafy_publisher_consent.sql"), "utf8");
  assert.match(migration, /PRIMARY KEY \(uid, auth_subject, agreement_version\)/i);
  assert.match(migration, /FOREIGN KEY \(uid, auth_subject\)[\s\S]*REFERENCES public\.lm_maritime_manager_enrollments\(uid, auth_subject\)/i);
  assert.match(migration, /agreement_version = 'v1\.2'/i);
  assert.match(migration, /effective_date = DATE '2026-09-28'/i);
  assert.match(migration, /certification_fee_usd numeric\(4,2\) NOT NULL CHECK \(certification_fee_usd = 0\.99\)/i);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/i);
  assert.match(migration, /REVOKE ALL ON TABLE private\.lm_maritime_manager_capafy_publisher_consents FROM PUBLIC, anon, authenticated/i);
  assert.match(migration, /GRANT SELECT, INSERT ON TABLE private\.lm_maritime_manager_capafy_publisher_consents TO service_role/i);
});
