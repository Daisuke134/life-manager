"use strict";

const { createHash } = require("node:crypto");

const CAPAFY_PUBLISHER_AGREEMENT_VERSION = "v1.2";
const CAPAFY_PUBLISHER_AGREEMENT_EFFECTIVE_DATE = "2026-09-28";
const CAPAFY_PUBLISHER_AGREEMENT_URL = "https://capafy.ai/publisher-agreement/";
const CAPAFY_CERTIFICATION_FEE_USD = "0.99";
const CAPAFY_DATA_DISCLOSURE_SECTIONS = "v1.2:3.4,3.5,8.1-8.7";
const CAPAFY_SUPPORT_OBLIGATION_SECTIONS = "v1.2:3.2,4.2-4.3,8.5";
const TENANT = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SUBJECT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const TEXT_FIELDS = new Set(["legalName", "jurisdiction", "publicSupportEmail"]);
const ACKNOWLEDGEMENTS = ["supportedRegionAttested", "sanctionsEligibilityAttested",
  "identityContactAccurateAttested", "singlePublisherAccountAttested",
  "certificationFeeNonRefundableAcknowledged", "dataDisclosuresAccepted",
  "supportObligationsAccepted", "agreementAccepted"];
const CONSENT_FIELDS = new Set(["agreementVersion", "publisherType", ...TEXT_FIELDS,
  "ageOfMajorityAttested", "entityAuthorityAttested", ...ACKNOWLEDGEMENTS]);

function fail(code) { throw new Error(code); }
function validTenant(value) {
  if (typeof value !== "string" || !TENANT.test(value)) fail("maritime_capafy_consent_identity_invalid");
  return value;
}
function validSubject(value) {
  if (typeof value !== "string" || !SUBJECT.test(value)) fail("maritime_capafy_consent_identity_invalid");
  return value.toLowerCase();
}
function timestamp(value) {
  const date = value instanceof Date ? value : new Date(String(value));
  if (!Number.isFinite(date.getTime())) fail("maritime_capafy_consent_record_invalid");
  return date.toISOString();
}
function email(value) {
  if (typeof value !== "string" || value.length > 320 || !EMAIL.test(value)) fail("maritime_capafy_consent_invalid");
  return value.trim().toLowerCase();
}
function text(value, max = 200) {
  if (typeof value !== "string" || value.trim().length < 1 || value.trim().length > max
    || /[\u0000-\u001f\u007f]/.test(value)) fail("maritime_capafy_consent_invalid");
  return value.trim();
}
function publicRecord(row, uid, subject) {
  if (!row || row.uid !== uid || String(row.auth_subject).toLowerCase() !== subject
    || row.agreement_version !== CAPAFY_PUBLISHER_AGREEMENT_VERSION
    || String(row.effective_date).slice(0, 10) !== CAPAFY_PUBLISHER_AGREEMENT_EFFECTIVE_DATE
    || row.agreement_url !== CAPAFY_PUBLISHER_AGREEMENT_URL
    || Number(row.certification_fee_usd) !== Number(CAPAFY_CERTIFICATION_FEE_USD)) return null;
  return Object.freeze({ tenantId: uid, authSubject: subject,
    agreementVersion: CAPAFY_PUBLISHER_AGREEMENT_VERSION,
    effectiveDate: CAPAFY_PUBLISHER_AGREEMENT_EFFECTIVE_DATE,
    agreementUrl: CAPAFY_PUBLISHER_AGREEMENT_URL, certificationFeeUsd: CAPAFY_CERTIFICATION_FEE_USD,
    acceptedAt: timestamp(row.accepted_at) });
}

function createMaritimeCapafyPublisherConsentStore({ query, now = () => new Date().toISOString() } = {}) {
  if (typeof query !== "function") fail("maritime_capafy_consent_store_unavailable");

  function normalize(input = {}) {
    const uid = validTenant(input.tenantId), subject = validSubject(input.authSubject);
    if (!input.consent || typeof input.consent !== "object" || Array.isArray(input.consent)
      || Object.keys(input.consent).some(key => !CONSENT_FIELDS.has(key))
      || Object.keys(input.consent).length !== CONSENT_FIELDS.size) fail("maritime_capafy_consent_invalid");
    const c = input.consent;
    if (c.agreementVersion !== CAPAFY_PUBLISHER_AGREEMENT_VERSION) fail("maritime_capafy_agreement_version_stale");
    if (!new Set(["individual", "entity"]).has(c.publisherType)) fail("maritime_capafy_consent_invalid");
    const age = c.ageOfMajorityAttested, authority = c.entityAuthorityAttested;
    if (typeof age !== "boolean" || typeof authority !== "boolean"
      || (c.publisherType === "individual" ? age !== true || authority !== false : authority !== true || age !== false)) {
      fail("maritime_capafy_consent_required");
    }
    for (const field of ACKNOWLEDGEMENTS) if (c[field] !== true) fail("maritime_capafy_consent_required");
    const legalName = text(c.legalName), jurisdiction = text(c.jurisdiction, 100);
    const verifiedContactEmail = email(input.verifiedContactEmail);
    const publicSupportEmail = email(c.publicSupportEmail);
    const canonical = { uid, subject, agreementVersion: CAPAFY_PUBLISHER_AGREEMENT_VERSION,
      effectiveDate: CAPAFY_PUBLISHER_AGREEMENT_EFFECTIVE_DATE, agreementUrl: CAPAFY_PUBLISHER_AGREEMENT_URL,
      publisherType: c.publisherType, legalName, jurisdiction, verifiedContactEmail, publicSupportEmail,
      ageOfMajorityAttested: age, entityAuthorityAttested: authority,
      supportedRegionAttested: c.supportedRegionAttested, sanctionsEligibilityAttested: c.sanctionsEligibilityAttested,
      identityContactAccurateAttested: c.identityContactAccurateAttested,
      singlePublisherAccountAttested: c.singlePublisherAccountAttested,
      certificationFeeUsd: CAPAFY_CERTIFICATION_FEE_USD,
      certificationFeeNonRefundableAcknowledged: c.certificationFeeNonRefundableAcknowledged,
      dataDisclosuresAccepted: c.dataDisclosuresAccepted, dataDisclosureSections: CAPAFY_DATA_DISCLOSURE_SECTIONS,
      supportObligationsAccepted: c.supportObligationsAccepted,
      supportObligationSections: CAPAFY_SUPPORT_OBLIGATION_SECTIONS, agreementAccepted: c.agreementAccepted };
    return { ...canonical, digest: createHash("sha256").update(JSON.stringify(canonical)).digest("hex") };
  }

  async function readCurrent({ tenantId, authSubject } = {}) {
    const uid = validTenant(tenantId), subject = validSubject(authSubject);
    const rows = (await query(`SELECT uid,auth_subject,agreement_version,effective_date,agreement_url,certification_fee_usd,accepted_at
      FROM private.lm_maritime_manager_capafy_publisher_consents
      WHERE uid=$1 AND auth_subject=$2 AND agreement_version=$3 LIMIT 2`,
    [uid, subject, CAPAFY_PUBLISHER_AGREEMENT_VERSION])).rows;
    if (!Array.isArray(rows) || rows.length > 1) fail("maritime_capafy_consent_record_invalid");
    if (!rows.length) return null;
    const record = publicRecord(rows[0], uid, subject);
    if (!record) return null;
    if (record.acceptedAt > timestamp(now())) return null;
    return record;
  }

  async function record(input = {}) {
    const c = normalize(input), acceptedAt = timestamp(now());
    if (acceptedAt > timestamp(now())) fail("maritime_capafy_consent_record_invalid");
    const values = [c.uid, c.subject, c.agreementVersion, c.effectiveDate, c.agreementUrl,
      c.publisherType, c.legalName, c.jurisdiction, c.verifiedContactEmail, c.publicSupportEmail,
      c.ageOfMajorityAttested, c.entityAuthorityAttested, c.supportedRegionAttested,
      c.sanctionsEligibilityAttested, c.identityContactAccurateAttested,
      c.singlePublisherAccountAttested, c.certificationFeeUsd, c.certificationFeeNonRefundableAcknowledged,
      c.dataDisclosuresAccepted, c.dataDisclosureSections, c.supportObligationsAccepted,
      c.supportObligationSections, c.agreementAccepted, acceptedAt, c.digest];
    const inserted = (await query(`INSERT INTO private.lm_maritime_manager_capafy_publisher_consents
      (uid,auth_subject,agreement_version,effective_date,agreement_url,publisher_type,legal_name,jurisdiction,
       verified_contact_email,public_support_email,age_of_majority_attested,entity_authority_attested,
       supported_region_attested,sanctions_eligibility_attested,identity_contact_accurate_attested,
       single_publisher_account_attested,certification_fee_usd,certification_fee_non_refundable_acknowledged,
       data_disclosures_accepted,data_disclosure_sections,support_obligations_accepted,
       support_obligation_sections,agreement_accepted,accepted_at,consent_digest)
      VALUES ($1,$2,$3,$4::date,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24::timestamptz,$25)
      ON CONFLICT (uid,auth_subject,agreement_version) DO NOTHING
      RETURNING uid,auth_subject,agreement_version,effective_date,agreement_url,certification_fee_usd,accepted_at,consent_digest`, values)).rows;
    if (!Array.isArray(inserted) || inserted.length > 1) fail("maritime_capafy_consent_record_invalid");
    if (inserted.length === 1) {
      if (inserted[0].consent_digest !== c.digest) fail("maritime_capafy_consent_record_invalid");
      const publicResult = publicRecord(inserted[0], c.uid, c.subject);
      if (!publicResult) fail("maritime_capafy_consent_record_invalid");
      return publicResult;
    }
    const rows = (await query(`SELECT uid,auth_subject,agreement_version,effective_date,agreement_url,certification_fee_usd,accepted_at,consent_digest
      FROM private.lm_maritime_manager_capafy_publisher_consents
      WHERE uid=$1 AND auth_subject=$2 AND agreement_version=$3 LIMIT 2`,
    [c.uid, c.subject, c.agreementVersion])).rows;
    if (!Array.isArray(rows) || rows.length !== 1 || rows[0].consent_digest !== c.digest) {
      fail("maritime_capafy_consent_already_recorded");
    }
    const publicResult = publicRecord(rows[0], c.uid, c.subject);
    if (!publicResult) fail("maritime_capafy_consent_record_invalid");
    return publicResult;
  }

  return Object.freeze({ record, readCurrent });
}

module.exports = { CAPAFY_PUBLISHER_AGREEMENT_VERSION, CAPAFY_PUBLISHER_AGREEMENT_EFFECTIVE_DATE,
  CAPAFY_PUBLISHER_AGREEMENT_URL, CAPAFY_CERTIFICATION_FEE_USD, CAPAFY_DATA_DISCLOSURE_SECTIONS,
  CAPAFY_SUPPORT_OBLIGATION_SECTIONS, createMaritimeCapafyPublisherConsentStore };
