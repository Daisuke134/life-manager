CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS private.lm_maritime_manager_capafy_publisher_consents (
  uid text NOT NULL,
  auth_subject uuid NOT NULL,
  agreement_version text NOT NULL CHECK (agreement_version = 'v1.2'),
  effective_date date NOT NULL CHECK (effective_date = DATE '2026-09-28'),
  agreement_url text NOT NULL CHECK (agreement_url = 'https://capafy.ai/publisher-agreement/'),
  publisher_type text NOT NULL CHECK (publisher_type IN ('individual', 'entity')),
  legal_name text NOT NULL CHECK (length(trim(legal_name)) BETWEEN 1 AND 200),
  jurisdiction text NOT NULL CHECK (length(trim(jurisdiction)) BETWEEN 1 AND 100),
  verified_contact_email text NOT NULL,
  public_support_email text NOT NULL,
  age_of_majority_attested boolean NOT NULL,
  entity_authority_attested boolean NOT NULL,
  supported_region_attested boolean NOT NULL CHECK (supported_region_attested),
  sanctions_eligibility_attested boolean NOT NULL CHECK (sanctions_eligibility_attested),
  identity_contact_accurate_attested boolean NOT NULL CHECK (identity_contact_accurate_attested),
  single_publisher_account_attested boolean NOT NULL CHECK (single_publisher_account_attested),
  certification_fee_usd numeric(4,2) NOT NULL CHECK (certification_fee_usd = 0.99),
  certification_fee_non_refundable_acknowledged boolean NOT NULL CHECK (certification_fee_non_refundable_acknowledged),
  data_disclosures_accepted boolean NOT NULL CHECK (data_disclosures_accepted),
  data_disclosure_sections text NOT NULL CHECK (data_disclosure_sections = 'v1.2:3.4,3.5,8.1-8.7'),
  support_obligations_accepted boolean NOT NULL CHECK (support_obligations_accepted),
  support_obligation_sections text NOT NULL CHECK (support_obligation_sections = 'v1.2:3.2,4.2-4.3,8.5'),
  agreement_accepted boolean NOT NULL CHECK (agreement_accepted),
  accepted_at timestamptz NOT NULL,
  withdrawn_at timestamptz,
  consent_digest text NOT NULL CHECK (consent_digest ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (uid, auth_subject, agreement_version),
  CHECK (uid ~ '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  CHECK ((publisher_type = 'individual' AND age_of_majority_attested AND NOT entity_authority_attested)
    OR (publisher_type = 'entity' AND entity_authority_attested AND NOT age_of_majority_attested)),
  FOREIGN KEY (uid, auth_subject)
    REFERENCES public.lm_maritime_manager_enrollments(uid, auth_subject) ON DELETE CASCADE
);

ALTER TABLE private.lm_maritime_manager_capafy_publisher_consents
  ADD COLUMN IF NOT EXISTS withdrawn_at timestamptz;

ALTER TABLE private.lm_maritime_manager_capafy_publisher_consents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lm_maritime_manager_capafy_publisher_consents_service_role_access
  ON private.lm_maritime_manager_capafy_publisher_consents;
CREATE POLICY lm_maritime_manager_capafy_publisher_consents_service_role_access
  ON private.lm_maritime_manager_capafy_publisher_consents FOR ALL TO service_role
  USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE private.lm_maritime_manager_capafy_publisher_consents FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA private TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE private.lm_maritime_manager_capafy_publisher_consents TO service_role;
