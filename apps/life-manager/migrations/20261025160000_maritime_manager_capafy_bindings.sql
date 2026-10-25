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
  connected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (uid ~ '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  CHECK (account_ref = 'account://capafy/' || uid || '/' || provider_subject::text),
  FOREIGN KEY (uid, auth_subject)
    REFERENCES public.lm_maritime_manager_enrollments(uid, auth_subject) ON DELETE CASCADE
);

ALTER TABLE private.lm_maritime_manager_capafy_bindings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lm_maritime_manager_capafy_bindings_service_role_access
  ON private.lm_maritime_manager_capafy_bindings;
CREATE POLICY lm_maritime_manager_capafy_bindings_service_role_access
  ON private.lm_maritime_manager_capafy_bindings FOR ALL TO service_role
  USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE private.lm_maritime_manager_capafy_bindings FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA private TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE private.lm_maritime_manager_capafy_bindings TO service_role;

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
