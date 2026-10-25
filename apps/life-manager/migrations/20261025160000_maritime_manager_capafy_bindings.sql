-- Per-tenant Capafy seller identity and encrypted access token.
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;

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
REVOKE ALL ON TABLE private.lm_maritime_manager_capafy_bindings FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA private TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE private.lm_maritime_manager_capafy_bindings TO service_role;
