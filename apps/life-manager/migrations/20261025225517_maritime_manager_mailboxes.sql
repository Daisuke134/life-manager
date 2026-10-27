-- Tenant-owned verification inboxes. Mail content and provider credentials are
-- read only by the Life Manager service; browser roles cannot access this data.
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;

CREATE UNIQUE INDEX IF NOT EXISTS lm_maritime_manager_enrollments_uid_auth_subject
  ON public.lm_maritime_manager_enrollments (uid, auth_subject);

CREATE TABLE IF NOT EXISTS private.lm_maritime_manager_mailboxes (
  uid text PRIMARY KEY,
  auth_subject uuid NOT NULL,
  inbox_id text NOT NULL UNIQUE,
  email text NOT NULL UNIQUE,
  client_id text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  capafy_challenge_status text,
  capafy_challenge_attempt_id uuid,
  capafy_challenge_id text,
  capafy_challenge_started_at timestamptz,
  capafy_challenge_expires_at timestamptz,
  capafy_challenge_verification_lease_expires_at timestamptz,
  CHECK (uid ~ '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  CHECK (char_length(inbox_id) BETWEEN 1 AND 320 AND inbox_id ~ '^[A-Za-z0-9._@+-]+$'),
  CHECK (email = lower(email) AND email ~ '^[a-z0-9.!#$%&''*+/=?^_`{|}~-]+@agentmail\.to$'),
  CHECK (client_id = 'life-manager-' || uid),
  FOREIGN KEY (uid, auth_subject)
    REFERENCES public.lm_maritime_manager_enrollments(uid, auth_subject) ON DELETE CASCADE
);

ALTER TABLE private.lm_maritime_manager_mailboxes
  ADD COLUMN IF NOT EXISTS capafy_challenge_status text,
  ADD COLUMN IF NOT EXISTS capafy_challenge_attempt_id uuid,
  ADD COLUMN IF NOT EXISTS capafy_challenge_id text,
  ADD COLUMN IF NOT EXISTS capafy_challenge_started_at timestamptz,
  ADD COLUMN IF NOT EXISTS capafy_challenge_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS capafy_challenge_verification_lease_expires_at timestamptz;

ALTER TABLE private.lm_maritime_manager_mailboxes
  DROP CONSTRAINT IF EXISTS lm_maritime_manager_mailboxes_capafy_challenge_state_check;
ALTER TABLE private.lm_maritime_manager_mailboxes
  ADD CONSTRAINT lm_maritime_manager_mailboxes_capafy_challenge_state_check CHECK ((
    (capafy_challenge_status IS NULL AND capafy_challenge_attempt_id IS NULL
      AND capafy_challenge_id IS NULL AND capafy_challenge_started_at IS NULL
      AND capafy_challenge_expires_at IS NULL
      AND capafy_challenge_verification_lease_expires_at IS NULL)
    OR (capafy_challenge_status = 'starting' AND capafy_challenge_attempt_id IS NOT NULL
      AND capafy_challenge_id IS NULL AND capafy_challenge_started_at IS NOT NULL
      AND capafy_challenge_expires_at IS NOT NULL
      AND capafy_challenge_expires_at > capafy_challenge_started_at
      AND capafy_challenge_expires_at <= capafy_challenge_started_at + interval '10 minutes'
      AND capafy_challenge_verification_lease_expires_at IS NULL)
    OR (capafy_challenge_status = 'pending' AND capafy_challenge_attempt_id IS NULL
      AND capafy_challenge_id IS NOT NULL AND char_length(capafy_challenge_id) BETWEEN 8 AND 512
      AND capafy_challenge_id ~ '^[A-Za-z0-9_-]+$' AND capafy_challenge_started_at IS NOT NULL
      AND capafy_challenge_expires_at IS NOT NULL
      AND capafy_challenge_expires_at > capafy_challenge_started_at
      AND capafy_challenge_expires_at <= capafy_challenge_started_at + interval '10 minutes'
      AND capafy_challenge_verification_lease_expires_at IS NULL)
    OR (capafy_challenge_status = 'verifying' AND capafy_challenge_attempt_id IS NULL
      AND capafy_challenge_id IS NOT NULL AND char_length(capafy_challenge_id) BETWEEN 8 AND 512
      AND capafy_challenge_id ~ '^[A-Za-z0-9_-]+$' AND capafy_challenge_started_at IS NOT NULL
      AND capafy_challenge_expires_at IS NOT NULL
      AND capafy_challenge_expires_at > capafy_challenge_started_at
      AND capafy_challenge_expires_at <= capafy_challenge_started_at + interval '10 minutes'
      AND capafy_challenge_verification_lease_expires_at IS NOT NULL
      AND capafy_challenge_verification_lease_expires_at > capafy_challenge_started_at
      AND capafy_challenge_verification_lease_expires_at <= capafy_challenge_started_at + interval '12 minutes')
  ) IS TRUE);

ALTER TABLE private.lm_maritime_manager_mailboxes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lm_maritime_manager_mailboxes_service_role_access
  ON private.lm_maritime_manager_mailboxes;
CREATE POLICY lm_maritime_manager_mailboxes_service_role_access
  ON private.lm_maritime_manager_mailboxes FOR ALL TO service_role
  USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE private.lm_maritime_manager_mailboxes FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA private TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE private.lm_maritime_manager_mailboxes TO service_role;
