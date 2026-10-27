"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { assertCapafyPublisherActionAllowed } = require("./maritime-manager-capafy-action-gate.js");

const TENANT = "lm_11111111-1111-4111-8111-111111111111";
const SUBJECT = "11111111-1111-4111-8111-111111111111";
const SKILL_ID = "agent-1";
const DISCLOSURE_SHA256 = "a".repeat(64);
const NOW = "2026-10-27T00:55:00.000Z";

function consent(patch = {}) {
  return { tenantId: TENANT, authSubject: SUBJECT, agreementVersion: "v1.2", effectiveDate: "2026-09-28",
    publisherType: "individual", legalName: "Private Name", jurisdiction: "Japan",
    verifiedContactEmail: "private@example.test", publicSupportEmail: "support@example.test",
    ageOfMajorityAttested: true, entityAuthorityAttested: false, supportedRegionAttested: true,
    sanctionsEligibilityAttested: true, identityContactAccurateAttested: true,
    singlePublisherAccountAttested: true, certificationFeeNonRefundableAcknowledged: true,
    dataDisclosuresAccepted: true, supportObligationsAccepted: true, agreementAccepted: true,
    acceptedAt: NOW, withdrawnAt: null, ...patch };
}

function disclosure(patch = {}) {
  return { tenantId: TENANT, authSubject: SUBJECT, agreementVersion: "v1.2", skillId: SKILL_ID,
    disclosureSha256: DISCLOSURE_SHA256, acceptedAt: NOW, withdrawnAt: null, ...patch };
}

function ready(overrides = {}) {
  return assertCapafyPublisherActionAllowed({ tenantId: TENANT, authSubject: SUBJECT, skillId: SKILL_ID,
    disclosureSha256: DISCLOSURE_SHA256, consent: consent(), skillDisclosure: disclosure(), ...overrides });
}

test("Capafy action gate names every missing eligibility, identity, support, and Skill disclosure gate", () => {
  const cases = [
    [{ consent: null }, "maritime_capafy_publisher_agreement_consent_required"],
    [{ consent: consent({ agreementVersion: "v1.1" }) }, "maritime_capafy_agreement_version_stale"],
    [{ consent: consent({ ageOfMajorityAttested: false }) }, "maritime_capafy_age_of_majority_required"],
    [{ consent: consent({ supportedRegionAttested: false }) }, "maritime_capafy_supported_region_required"],
    [{ consent: consent({ sanctionsEligibilityAttested: false }) }, "maritime_capafy_sanctions_eligibility_required"],
    [{ consent: consent({ identityContactAccurateAttested: false }) }, "maritime_capafy_identity_contact_facts_required"],
    [{ consent: consent({ legalName: "" }) }, "maritime_capafy_identity_contact_facts_required"],
    [{ consent: consent({ verifiedContactEmail: "" }) }, "maritime_capafy_identity_contact_facts_required"],
    [{ consent: consent({ publicSupportEmail: "" }) }, "maritime_capafy_public_support_email_required"],
    [{ consent: consent({ singlePublisherAccountAttested: false }) }, "maritime_capafy_single_publisher_account_required"],
    [{ consent: consent({ certificationFeeNonRefundableAcknowledged: false }) }, "maritime_capafy_certification_fee_acknowledgement_required"],
    [{ consent: consent({ dataDisclosuresAccepted: false }) }, "maritime_capafy_data_disclosure_required"],
    [{ consent: consent({ supportObligationsAccepted: false }) }, "maritime_capafy_support_obligations_required"],
    [{ skillId: null }, "maritime_capafy_skill_id_required"],
    [{ skillDisclosure: null }, "maritime_capafy_skill_data_disclosure_required"],
    [{ skillDisclosure: disclosure({ tenantId: "lm_22222222-2222-4222-8222-222222222222" }) }, "maritime_capafy_skill_data_disclosure_required"],
    [{ skillDisclosure: disclosure({ disclosureSha256: "b".repeat(64) }) }, "maritime_capafy_skill_data_disclosure_required"],
    [{ skillDisclosure: disclosure({ withdrawnAt: NOW }) }, "maritime_capafy_skill_data_disclosure_required"],
  ];
  for (const [overrides, code] of cases) {
    assert.throws(() => ready(overrides), error => error.message === code, code);
  }
});

test("eligible action reports payout and tax as unverified-deferrable without returning private facts", () => {
  const result = ready();
  assert.deepEqual(result, { allowed: true, skillId: SKILL_ID, disclosureSha256: DISCLOSURE_SHA256,
    payoutTaxStatus: "unverified_deferrable", revenueLabelAllowed: false });
  assert.doesNotMatch(JSON.stringify(result), /Private Name|private@example\.test|support@example\.test|am_sk_/i);
});
