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

test("publisher consent can be viewed and withdrawn by its tenant without replacing the v1.2 record", async () => {
  let row = null;
  const store = createMaritimeCapafyPublisherConsentStore({ now: () => NOW, query: async (sql, values) => {
    if (/^INSERT INTO/i.test(sql)) {
      if (!row) {
        row = { uid: values[0], auth_subject: values[1], agreement_version: values[2],
          effective_date: values[3], agreement_url: values[4], publisher_type: values[5], legal_name: values[6],
          jurisdiction: values[7], verified_contact_email: values[8], public_support_email: values[9],
          age_of_majority_attested: values[10], entity_authority_attested: values[11],
          supported_region_attested: values[12], sanctions_eligibility_attested: values[13],
          identity_contact_accurate_attested: values[14], single_publisher_account_attested: values[15],
          certification_fee_usd: values[16], certification_fee_non_refundable_acknowledged: values[17],
          data_disclosures_accepted: values[18], data_disclosure_sections: values[19],
          support_obligations_accepted: values[20], support_obligation_sections: values[21],
          agreement_accepted: values[22], accepted_at: values[23], consent_digest: values[24], withdrawn_at: null };
        return { rows: [row] };
      }
      return { rows: [] };
    }
    if (/^UPDATE/i.test(sql)) {
      if (!row || row.uid !== values[0] || row.auth_subject !== values[1]) return { rows: [] };
      row.withdrawn_at ||= values[3];
      return { rows: [row] };
    }
    if (/^SELECT/i.test(sql)) {
      if (!row || row.uid !== values[0] || row.auth_subject !== values[1]
        || row.agreement_version !== values[2] || (/withdrawn_at IS NULL/i.test(sql) && row.withdrawn_at)) return { rows: [] };
      return { rows: [{ ...row }] };
    }
    throw new Error("unexpected_query");
  } });
  const input = { tenantId: TENANT, authSubject: SUBJECT, verifiedContactEmail: "verified@example.test", consent: consent() };
  const receipt = await store.record(input);
  assert.equal(receipt.agreementVersion, "v1.2");
  const visible = await store.readForTenant({ tenantId: TENANT, authSubject: SUBJECT });
  assert.equal(visible.legalName, "Test Publisher");
  assert.equal(visible.verifiedContactEmail, "verified@example.test");
  assert.equal(visible.publicSupportEmail, "support@example.test");
  assert.equal(visible.withdrawnAt, null);
  const withdrawal = await store.withdraw({ tenantId: TENANT, authSubject: SUBJECT });
  assert.deepEqual(withdrawal, { tenantId: TENANT, authSubject: SUBJECT, agreementVersion: "v1.2",
    effectiveDate: "2026-09-28", agreementUrl: "https://capafy.ai/publisher-agreement/",
    certificationFeeUsd: "0.99", acceptedAt: NOW, withdrawnAt: NOW });
  assert.equal(await store.readCurrent({ tenantId: TENANT, authSubject: SUBJECT }), null);
  assert.equal((await store.readForTenant({ tenantId: TENANT, authSubject: SUBJECT })).withdrawnAt, NOW);
  assert.doesNotMatch(JSON.stringify(receipt) + JSON.stringify(withdrawal),
    /Test Publisher|verified@example\.test|support@example\.test|am_sk_/i);
  await assert.rejects(store.record(input), /consent_withdrawn/i);
  assert.equal((await store.readForTenant({ tenantId: TENANT, authSubject: SUBJECT })).withdrawnAt, NOW);
  assert.equal(row.uid, TENANT);
  assert.equal(row.auth_subject, SUBJECT);
});

test("tenant consent readback is tenant-bound and the withdrawal migration is service-role only", async () => {
  let queryInput;
  const store = createMaritimeCapafyPublisherConsentStore({ query: async (sql, values) => {
    queryInput = { sql, values };
    return { rows: [{ uid: TENANT, auth_subject: SUBJECT, agreement_version: "v1.2",
      effective_date: "2026-09-28", agreement_url: "https://capafy.ai/publisher-agreement/",
      certification_fee_usd: "0.99", publisher_type: "individual", legal_name: "Test Publisher",
      jurisdiction: "Japan", verified_contact_email: "verified@example.test", public_support_email: "support@example.test",
      age_of_majority_attested: true, entity_authority_attested: false, supported_region_attested: true,
      sanctions_eligibility_attested: true, identity_contact_accurate_attested: true,
      single_publisher_account_attested: true, certification_fee_non_refundable_acknowledged: true,
      data_disclosures_accepted: true, data_disclosure_sections: "v1.2:3.4,3.5,8.1-8.7",
      support_obligations_accepted: true, support_obligation_sections: "v1.2:3.2,4.2-4.3,8.5",
      agreement_accepted: true, accepted_at: NOW, withdrawn_at: null }] };
  } });
  const visible = await store.readForTenant({ tenantId: TENANT, authSubject: SUBJECT });
  assert.deepEqual(queryInput.values, [TENANT, SUBJECT, "v1.2"]);
  assert.match(queryInput.sql, /WHERE uid=\$1 AND auth_subject=\$2 AND agreement_version=\$3/i);
  assert.equal(visible.publisherType, "individual");
  assert.equal(visible.dataDisclosureSections, "v1.2:3.4,3.5,8.1-8.7");
  assert.equal(visible.supportObligationSections, "v1.2:3.2,4.2-4.3,8.5");
});

test("Skill data disclosure is explicit, tenant-bound, versioned, and idempotent", async () => {
  const disclosureSha256 = "a".repeat(64);
  let disclosureRow = null, inserts = 0;
  const store = createMaritimeCapafyPublisherConsentStore({ now: () => NOW, query: async (sql, values) => {
    if (/FROM private\.lm_maritime_manager_capafy_publisher_consents/i.test(sql)) return { rows: [{
      uid: TENANT, auth_subject: SUBJECT, agreement_version: "v1.2", effective_date: "2026-09-28",
      agreement_url: "https://capafy.ai/publisher-agreement/", certification_fee_usd: "0.99", accepted_at: NOW,
    }] };
    if (/INSERT INTO private\.lm_maritime_manager_capafy_skill_disclosures/i.test(sql)) {
      inserts++;
      if (disclosureRow) return { rows: [] };
      disclosureRow = { uid: values[0], auth_subject: values[1], agreement_version: values[2],
        skill_id: values[3], disclosure_sha256: values[4], accepted_at: values[5], withdrawn_at: null };
      return { rows: [{ ...disclosureRow }] };
    }
    if (/FROM private\.lm_maritime_manager_capafy_skill_disclosures/i.test(sql)) {
      return disclosureRow && disclosureRow.uid === values[0] && disclosureRow.auth_subject === values[1]
        && disclosureRow.agreement_version === values[2] && disclosureRow.skill_id === values[3]
        && disclosureRow.disclosure_sha256 === values[4] && !disclosureRow.withdrawn_at
        ? { rows: [{ ...disclosureRow }] } : { rows: [] };
    }
    throw new Error("unexpected query");
  } });
  const input = { tenantId: TENANT, authSubject: SUBJECT, skillId: "agent-1", disclosureSha256,
    accepted: true };
  const receipt = await store.recordSkillDisclosure(input);
  const repeated = await store.recordSkillDisclosure(input);
  assert.deepEqual(receipt, { skillId: "agent-1", disclosureSha256, agreementVersion: "v1.2", acceptedAt: NOW });
  assert.deepEqual(repeated, receipt);
  assert.equal(inserts, 2);
  assert.deepEqual(await store.readSkillDisclosure(input), { tenantId: TENANT, authSubject: SUBJECT,
    skillId: "agent-1", disclosureSha256, agreementVersion: "v1.2", acceptedAt: NOW, withdrawnAt: null });
  assert.doesNotMatch(JSON.stringify([receipt, disclosureRow]), /Private Name|verified@example\.test|support@example\.test|am_sk_/i);
  await assert.rejects(store.recordSkillDisclosure({ ...input, accepted: false }), /skill_data_disclosure_required/i);
});

test("a Skill disclosure cannot be recorded without current tenant Publisher consent", async () => {
  let inserts = 0;
  const store = createMaritimeCapafyPublisherConsentStore({ query: async sql => {
    if (/FROM private\.lm_maritime_manager_capafy_publisher_consents/i.test(sql)) return { rows: [] };
    if (/INSERT INTO private\.lm_maritime_manager_capafy_skill_disclosures/i.test(sql)) inserts++;
    return { rows: [] };
  } });
  await assert.rejects(store.recordSkillDisclosure({ tenantId: TENANT, authSubject: SUBJECT,
    skillId: "agent-1", disclosureSha256: "a".repeat(64), accepted: true }), /publisher_agreement_consent_required/i);
  assert.equal(inserts, 0);
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
  assert.match(migration, /withdrawn_at timestamptz/i);
  assert.match(migration, /GRANT SELECT, INSERT, UPDATE ON TABLE private\.lm_maritime_manager_capafy_publisher_consents TO service_role/i);
  assert.match(migration, /CREATE TABLE IF NOT EXISTS private\.lm_maritime_manager_capafy_skill_disclosures/i);
  assert.match(migration, /PRIMARY KEY \(uid, auth_subject, agreement_version, skill_id, disclosure_sha256\)/i);
  assert.match(migration, /GRANT SELECT, INSERT ON TABLE private\.lm_maritime_manager_capafy_skill_disclosures TO service_role/i);
});
