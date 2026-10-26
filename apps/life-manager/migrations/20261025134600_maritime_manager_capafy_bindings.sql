-- Per-tenant Capafy seller identity and encrypted access token.
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;

-- PostgreSQL requires an exact unique key for the composite binding FK even
-- though uid and auth_subject are each unique on their own.
CREATE UNIQUE INDEX IF NOT EXISTS lm_maritime_manager_enrollments_uid_auth_subject
  ON public.lm_maritime_manager_enrollments (uid, auth_subject);

CREATE TABLE IF NOT EXISTS private.lm_maritime_manager_capafy_bindings (
  uid text PRIMARY KEY,
  auth_subject uuid NOT NULL,
  provider_subject uuid NOT NULL UNIQUE,
  account_ref text NOT NULL UNIQUE,
  ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) BETWEEN 1 AND 1024),
  iv bytea NOT NULL CHECK (octet_length(iv) = 12),
  tag bytea NOT NULL CHECK (octet_length(tag) = 16),
  autonomy_consent_version text NOT NULL
    CHECK (autonomy_consent_version = 'maritime-capafy-autonomy-v1'),
  policy_consent_version text NOT NULL,
  terms_accepted_at timestamptz NOT NULL,
  terms_url text NOT NULL,
  privacy_url text NOT NULL,
  connected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (uid ~ '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  CHECK (account_ref = 'account://capafy/' || uid || '/' || provider_subject::text),
  FOREIGN KEY (uid, auth_subject)
    REFERENCES public.lm_maritime_manager_enrollments(uid, auth_subject) ON DELETE CASCADE
);

-- Keep older bindings readable only when they contain explicit publisher-policy
-- consent. Existing rows without this evidence remain invalid until reconnected.
ALTER TABLE private.lm_maritime_manager_capafy_bindings
  ADD COLUMN IF NOT EXISTS policy_consent_version text,
  ADD COLUMN IF NOT EXISTS terms_accepted_at timestamptz,
  ADD COLUMN IF NOT EXISTS terms_url text,
  ADD COLUMN IF NOT EXISTS privacy_url text;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'lm_maritime_manager_capafy_policy_consent_check') THEN
    ALTER TABLE private.lm_maritime_manager_capafy_bindings
      ADD CONSTRAINT lm_maritime_manager_capafy_policy_consent_check
      CHECK (policy_consent_version IS NOT NULL
        AND policy_consent_version = 'capafy-publisher-terms-privacy-v1'
        AND terms_accepted_at IS NOT NULL
        AND terms_url IS NOT NULL
        AND terms_url = 'https://api.capafy.ai/terms-of-service'
        AND privacy_url IS NOT NULL
        AND privacy_url = 'https://api.capafy.ai/privacy-policy') NOT VALID;
  END IF;
END $$;

ALTER TABLE private.lm_maritime_manager_capafy_bindings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lm_maritime_manager_capafy_bindings_service_role_access
  ON private.lm_maritime_manager_capafy_bindings;
CREATE POLICY lm_maritime_manager_capafy_bindings_service_role_access
  ON private.lm_maritime_manager_capafy_bindings FOR ALL TO service_role
  USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE private.lm_maritime_manager_capafy_bindings FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA private TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE private.lm_maritime_manager_capafy_bindings TO service_role;

-- Keep the first verified Publisher identity after credential unlink so a later
-- reconnect cannot silently bind a second account. The immutable claim is
-- inserted before a token binding and is tenant-scoped by the authenticated
-- enrollment identity.
CREATE TABLE IF NOT EXISTS private.lm_maritime_manager_capafy_publisher_account_claims (
  uid text PRIMARY KEY,
  auth_subject uuid NOT NULL,
  provider_subject uuid NOT NULL UNIQUE,
  account_ref text NOT NULL UNIQUE,
  claimed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (uid ~ '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  CHECK (account_ref = 'account://capafy/' || uid || '/' || provider_subject::text),
  FOREIGN KEY (uid, auth_subject)
    REFERENCES public.lm_maritime_manager_enrollments(uid, auth_subject) ON DELETE CASCADE
);
INSERT INTO private.lm_maritime_manager_capafy_publisher_account_claims
  (uid,auth_subject,provider_subject,account_ref,claimed_at)
SELECT uid,auth_subject,provider_subject,account_ref,connected_at
FROM private.lm_maritime_manager_capafy_bindings
ON CONFLICT (uid) DO NOTHING;

ALTER TABLE private.lm_maritime_manager_capafy_publisher_account_claims ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lm_maritime_manager_capafy_publisher_account_claims_service_role_access
  ON private.lm_maritime_manager_capafy_publisher_account_claims;
CREATE POLICY lm_maritime_manager_capafy_publisher_account_claims_service_role_access
  ON private.lm_maritime_manager_capafy_publisher_account_claims FOR ALL TO service_role
  USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE private.lm_maritime_manager_capafy_publisher_account_claims FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON TABLE private.lm_maritime_manager_capafy_publisher_account_claims TO service_role;

-- A durable keyset prevents a finite recovery batch from repeatedly selecting
-- the same deferred cycles and starving older or other-tenant work.
CREATE TABLE IF NOT EXISTS private.lm_maritime_manager_capafy_recovery_cursor (
  cursor_key text PRIMARY KEY CHECK (cursor_key = 'cycle_admission'),
  completed_at timestamptz,
  tenant_id text,
  job_id text,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (
    (completed_at IS NULL AND tenant_id IS NULL AND job_id IS NULL)
    OR (completed_at IS NOT NULL AND tenant_id ~ '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
      AND job_id ~ '^maritime-cycle:[0-9a-f]{64}$')
  )
);
INSERT INTO private.lm_maritime_manager_capafy_recovery_cursor(cursor_key)
VALUES ('cycle_admission') ON CONFLICT (cursor_key) DO NOTHING;

ALTER TABLE private.lm_maritime_manager_capafy_recovery_cursor ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lm_maritime_manager_capafy_recovery_cursor_service_role_access
  ON private.lm_maritime_manager_capafy_recovery_cursor;
CREATE POLICY lm_maritime_manager_capafy_recovery_cursor_service_role_access
  ON private.lm_maritime_manager_capafy_recovery_cursor FOR ALL TO service_role
  USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE private.lm_maritime_manager_capafy_recovery_cursor FROM PUBLIC, anon, authenticated;
GRANT SELECT, UPDATE ON TABLE private.lm_maritime_manager_capafy_recovery_cursor TO service_role;
