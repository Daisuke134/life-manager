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
const SKILL_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SHA256 = /^[a-f0-9]{64}$/;
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
function publicMetadata(row, uid, subject) {
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
function publicRecord(row, uid, subject) {
  if (row?.withdrawn_at != null) return null;
  return publicMetadata(row, uid, subject);
}
function tenantRecord(row, uid, subject) {
  const metadata = publicMetadata(row, uid, subject);
  if (!metadata || !new Set(["individual", "entity"]).has(row.publisher_type)) return null;
  const booleans = ["age_of_majority_attested", "entity_authority_attested", "supported_region_attested",
    "sanctions_eligibility_attested", "identity_contact_accurate_attested", "single_publisher_account_attested",
    "certification_fee_non_refundable_acknowledged", "data_disclosures_accepted", "support_obligations_accepted",
    "agreement_accepted"];
  if (booleans.some(field => typeof row[field] !== "boolean")) return null;
  return Object.freeze({ ...metadata, publisherType: row.publisher_type, legalName: text(row.legal_name),
    jurisdiction: text(row.jurisdiction, 100), verifiedContactEmail: email(row.verified_contact_email),
    publicSupportEmail: email(row.public_support_email), ageOfMajorityAttested: row.age_of_majority_attested,
    entityAuthorityAttested: row.entity_authority_attested, supportedRegionAttested: row.supported_region_attested,
    sanctionsEligibilityAttested: row.sanctions_eligibility_attested,
    identityContactAccurateAttested: row.identity_contact_accurate_attested,
    singlePublisherAccountAttested: row.single_publisher_account_attested,
    certificationFeeNonRefundableAcknowledged: row.certification_fee_non_refundable_acknowledged,
    dataDisclosuresAccepted: row.data_disclosures_accepted,
    dataDisclosureSections: row.data_disclosure_sections,
    supportObligationsAccepted: row.support_obligations_accepted,
    supportObligationSections: row.support_obligation_sections,
    agreementAccepted: row.agreement_accepted,
    withdrawnAt: row.withdrawn_at == null ? null : timestamp(row.withdrawn_at) });
}
function skillDisclosureRecord(row, uid, subject, skillId, disclosureSha256) {
  if (!row || row.uid !== uid || String(row.auth_subject).toLowerCase() !== subject
    || row.agreement_version !== CAPAFY_PUBLISHER_AGREEMENT_VERSION || row.skill_id !== skillId
    || row.disclosure_sha256 !== disclosureSha256) return null;
  return Object.freeze({ tenantId: uid, authSubject: subject, skillId,
    disclosureSha256, agreementVersion: CAPAFY_PUBLISHER_AGREEMENT_VERSION,
    acceptedAt: timestamp(row.accepted_at), withdrawnAt: row.withdrawn_at == null ? null : timestamp(row.withdrawn_at) });
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
      WHERE uid=$1 AND auth_subject=$2 AND agreement_version=$3 AND withdrawn_at IS NULL LIMIT 2`,
    [uid, subject, CAPAFY_PUBLISHER_AGREEMENT_VERSION])).rows;
    if (!Array.isArray(rows) || rows.length > 1) fail("maritime_capafy_consent_record_invalid");
    if (!rows.length) return null;
    const record = publicRecord(rows[0], uid, subject);
    if (!record) return null;
    if (record.acceptedAt > timestamp(now())) return null;
    return record;
  }

  async function readForTenant({ tenantId, authSubject } = {}) {
    const uid = validTenant(tenantId), subject = validSubject(authSubject);
    const rows = (await query(`SELECT uid,auth_subject,agreement_version,effective_date,agreement_url,certification_fee_usd,
      publisher_type,legal_name,jurisdiction,verified_contact_email,public_support_email,age_of_majority_attested,
      entity_authority_attested,supported_region_attested,sanctions_eligibility_attested,
      identity_contact_accurate_attested,single_publisher_account_attested,certification_fee_non_refundable_acknowledged,
      data_disclosures_accepted,data_disclosure_sections,support_obligations_accepted,support_obligation_sections,
      agreement_accepted,accepted_at,withdrawn_at
      FROM private.lm_maritime_manager_capafy_publisher_consents
      WHERE uid=$1 AND auth_subject=$2 AND agreement_version=$3 LIMIT 2`,
    [uid, subject, CAPAFY_PUBLISHER_AGREEMENT_VERSION])).rows;
    if (!Array.isArray(rows) || rows.length > 1) fail("maritime_capafy_consent_record_invalid");
    return rows.length ? tenantRecord(rows[0], uid, subject) : null;
  }

  async function recordSkillDisclosure(input = {}) {
    const uid = validTenant(input.tenantId), subject = validSubject(input.authSubject);
    if (Object.keys(input).some(key => !new Set(["tenantId", "authSubject", "skillId", "disclosureSha256", "accepted"]).has(key))
      || typeof input.skillId !== "string" || !SKILL_ID.test(input.skillId)
      || typeof input.disclosureSha256 !== "string" || !SHA256.test(input.disclosureSha256)
      || input.accepted !== true) fail("maritime_capafy_skill_data_disclosure_required");
    if (!await readCurrent({ tenantId: uid, authSubject: subject })) {
      fail("maritime_capafy_publisher_agreement_consent_required");
    }
    const acceptedAt = timestamp(now());
    const values = [uid, subject, CAPAFY_PUBLISHER_AGREEMENT_VERSION, input.skillId, input.disclosureSha256, acceptedAt];
    const inserted = (await query(`INSERT INTO private.lm_maritime_manager_capafy_skill_disclosures
      (uid,auth_subject,agreement_version,skill_id,disclosure_sha256,accepted_at)
      VALUES ($1,$2,$3,$4,$5,$6::timestamptz)
      ON CONFLICT (uid,auth_subject,agreement_version,skill_id,disclosure_sha256) DO NOTHING
      RETURNING uid,auth_subject,agreement_version,skill_id,disclosure_sha256,accepted_at,withdrawn_at`, values)).rows;
    if (!Array.isArray(inserted) || inserted.length > 1) fail("maritime_capafy_skill_data_disclosure_invalid");
    if (inserted.length === 1) {
      const record = skillDisclosureRecord(inserted[0], uid, subject, input.skillId, input.disclosureSha256);
      if (!record || record.withdrawnAt) fail("maritime_capafy_skill_data_disclosure_invalid");
      return Object.freeze({ skillId: record.skillId, disclosureSha256: record.disclosureSha256,
        agreementVersion: record.agreementVersion, acceptedAt: record.acceptedAt });
    }
    const rows = (await query(`SELECT uid,auth_subject,agreement_version,skill_id,disclosure_sha256,accepted_at,withdrawn_at
      FROM private.lm_maritime_manager_capafy_skill_disclosures
      WHERE uid=$1 AND auth_subject=$2 AND agreement_version=$3 AND skill_id=$4 AND disclosure_sha256=$5 LIMIT 2`,
    values.slice(0, 5))).rows;
    if (!Array.isArray(rows) || rows.length !== 1) fail("maritime_capafy_skill_data_disclosure_invalid");
    const record = skillDisclosureRecord(rows[0], uid, subject, input.skillId, input.disclosureSha256);
    if (!record) fail("maritime_capafy_skill_data_disclosure_invalid");
    if (record.withdrawnAt) fail("maritime_capafy_skill_data_disclosure_withdrawn");
    return Object.freeze({ skillId: record.skillId, disclosureSha256: record.disclosureSha256,
      agreementVersion: record.agreementVersion, acceptedAt: record.acceptedAt });
  }

  async function readSkillDisclosure({ tenantId, authSubject, skillId, disclosureSha256 } = {}) {
    const uid = validTenant(tenantId), subject = validSubject(authSubject);
    if (typeof skillId !== "string" || !SKILL_ID.test(skillId)
      || typeof disclosureSha256 !== "string" || !SHA256.test(disclosureSha256)) {
      fail("maritime_capafy_skill_data_disclosure_invalid");
    }
    const rows = (await query(`SELECT uid,auth_subject,agreement_version,skill_id,disclosure_sha256,accepted_at,withdrawn_at
      FROM private.lm_maritime_manager_capafy_skill_disclosures
      WHERE uid=$1 AND auth_subject=$2 AND agreement_version=$3 AND skill_id=$4 AND disclosure_sha256=$5
      AND withdrawn_at IS NULL LIMIT 2`, [uid, subject, CAPAFY_PUBLISHER_AGREEMENT_VERSION,
      skillId, disclosureSha256])).rows;
    if (!Array.isArray(rows) || rows.length > 1) fail("maritime_capafy_skill_data_disclosure_invalid");
    if (!rows.length) return null;
    return skillDisclosureRecord(rows[0], uid, subject, skillId, disclosureSha256);
  }

  async function withdraw({ tenantId, authSubject } = {}) {
    const uid = validTenant(tenantId), subject = validSubject(authSubject);
    const rows = (await query(`UPDATE private.lm_maritime_manager_capafy_publisher_consents
      SET withdrawn_at=COALESCE(withdrawn_at,$4::timestamptz)
      WHERE uid=$1 AND auth_subject=$2 AND agreement_version=$3
      RETURNING uid,auth_subject,agreement_version,effective_date,agreement_url,certification_fee_usd,accepted_at,withdrawn_at`,
    [uid, subject, CAPAFY_PUBLISHER_AGREEMENT_VERSION, timestamp(now())])).rows;
    if (!Array.isArray(rows) || rows.length > 1) fail("maritime_capafy_consent_record_invalid");
    const metadata = rows.length ? publicMetadata(rows[0], uid, subject) : null;
    if (!metadata) return null;
    return Object.freeze({ ...metadata, withdrawnAt: timestamp(rows[0].withdrawn_at) });
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
    const rows = (await query(`SELECT uid,auth_subject,agreement_version,effective_date,agreement_url,certification_fee_usd,accepted_at,consent_digest,withdrawn_at
      FROM private.lm_maritime_manager_capafy_publisher_consents
      WHERE uid=$1 AND auth_subject=$2 AND agreement_version=$3 LIMIT 2`,
    [c.uid, c.subject, c.agreementVersion])).rows;
    if (!Array.isArray(rows) || rows.length !== 1 || rows[0].consent_digest !== c.digest) {
      fail("maritime_capafy_consent_already_recorded");
    }
    if (rows[0].withdrawn_at != null) fail("maritime_capafy_consent_withdrawn");
    const publicResult = publicRecord(rows[0], c.uid, c.subject);
    if (!publicResult) fail("maritime_capafy_consent_record_invalid");
    return publicResult;
  }

  return Object.freeze({ record, readCurrent, readForTenant, recordSkillDisclosure, readSkillDisclosure, withdraw });
}

module.exports = { CAPAFY_PUBLISHER_AGREEMENT_VERSION, CAPAFY_PUBLISHER_AGREEMENT_EFFECTIVE_DATE,
  CAPAFY_PUBLISHER_AGREEMENT_URL, CAPAFY_CERTIFICATION_FEE_USD, CAPAFY_DATA_DISCLOSURE_SECTIONS,
  CAPAFY_SUPPORT_OBLIGATION_SECTIONS, createMaritimeCapafyPublisherConsentStore };
