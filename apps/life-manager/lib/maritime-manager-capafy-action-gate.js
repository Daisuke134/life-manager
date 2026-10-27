"use strict";

const { CAPAFY_PUBLISHER_AGREEMENT_VERSION, CAPAFY_PUBLISHER_AGREEMENT_EFFECTIVE_DATE } =
  require("./maritime-manager-capafy-consent.js");

const TENANT = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SUBJECT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SKILL_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function fail(code) { throw new Error(code); }
function nonempty(value, max = 200) {
  return typeof value === "string" && value.trim().length > 0 && value.trim().length <= max
    && !/[\u0000-\u001f\u007f]/.test(value);
}

function assertCapafyPublisherActionAllowed({ tenantId, authSubject, skillId, disclosureSha256,
  consent, skillDisclosure } = {}) {
  const subject = typeof authSubject === "string" ? authSubject.toLowerCase() : "";
  if (typeof tenantId !== "string" || !TENANT.test(tenantId) || !SUBJECT.test(subject)) {
    fail("maritime_capafy_action_identity_invalid");
  }
  if (!consent || consent.tenantId !== tenantId || String(consent.authSubject || "").toLowerCase() !== subject
    || consent.withdrawnAt != null || !Number.isFinite(Date.parse(consent.acceptedAt || ""))) {
    fail("maritime_capafy_publisher_agreement_consent_required");
  }
  if (consent.agreementVersion !== CAPAFY_PUBLISHER_AGREEMENT_VERSION
    || consent.effectiveDate !== CAPAFY_PUBLISHER_AGREEMENT_EFFECTIVE_DATE) {
    fail("maritime_capafy_agreement_version_stale");
  }
  if (!new Set(["individual", "entity"]).has(consent.publisherType)
    || (consent.publisherType === "individual" && consent.ageOfMajorityAttested !== true)
    || (consent.publisherType === "entity" && consent.entityAuthorityAttested !== true)) {
    fail("maritime_capafy_age_of_majority_required");
  }
  if (consent.supportedRegionAttested !== true) fail("maritime_capafy_supported_region_required");
  if (consent.sanctionsEligibilityAttested !== true) fail("maritime_capafy_sanctions_eligibility_required");
  if (!nonempty(consent.legalName) || !nonempty(consent.jurisdiction, 100)
    || !EMAIL.test(String(consent.verifiedContactEmail || ""))
    || consent.identityContactAccurateAttested !== true) {
    fail("maritime_capafy_identity_contact_facts_required");
  }
  if (!EMAIL.test(String(consent.publicSupportEmail || ""))) fail("maritime_capafy_public_support_email_required");
  if (consent.singlePublisherAccountAttested !== true) fail("maritime_capafy_single_publisher_account_required");
  if (consent.certificationFeeNonRefundableAcknowledged !== true) {
    fail("maritime_capafy_certification_fee_acknowledgement_required");
  }
  if (consent.dataDisclosuresAccepted !== true || consent.agreementAccepted !== true) {
    fail("maritime_capafy_data_disclosure_required");
  }
  if (consent.supportObligationsAccepted !== true) fail("maritime_capafy_support_obligations_required");
  if (typeof skillId !== "string" || !SKILL_ID.test(skillId)) fail("maritime_capafy_skill_id_required");
  if (typeof disclosureSha256 !== "string" || !SHA256.test(disclosureSha256)
    || !skillDisclosure || skillDisclosure.tenantId !== tenantId
    || String(skillDisclosure.authSubject || "").toLowerCase() !== subject
    || skillDisclosure.agreementVersion !== CAPAFY_PUBLISHER_AGREEMENT_VERSION
    || skillDisclosure.skillId !== skillId || skillDisclosure.disclosureSha256 !== disclosureSha256
    || skillDisclosure.withdrawnAt != null || !Number.isFinite(Date.parse(skillDisclosure.acceptedAt || ""))) {
    fail("maritime_capafy_skill_data_disclosure_required");
  }
  return Object.freeze({ allowed: true, skillId, disclosureSha256,
    payoutTaxStatus: "unverified_deferrable", revenueLabelAllowed: false });
}

module.exports = { assertCapafyPublisherActionAllowed };
