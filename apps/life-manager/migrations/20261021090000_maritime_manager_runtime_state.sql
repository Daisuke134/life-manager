-- Manager-only identity state. This table has no FK to global lm_users.
CREATE TABLE IF NOT EXISTS public.lm_maritime_manager_identities (
  uid text PRIMARY KEY CHECK (uid ~ '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  auth_subject uuid NOT NULL UNIQUE,
  verified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  first_touch jsonb,
  first_touch_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (uid, auth_subject),
  CHECK (first_touch IS NULL OR jsonb_typeof(first_touch) = 'object'),
  CHECK ((first_touch IS NULL) = (first_touch_at IS NULL))
);

CREATE OR REPLACE FUNCTION public.prevent_lm_maritime_manager_identity_reassignment_v1()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF NEW.uid IS DISTINCT FROM OLD.uid OR NEW.auth_subject IS DISTINCT FROM OLD.auth_subject THEN
    RAISE EXCEPTION 'maritime_manager_identity_reassignment_rejected'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS lm_maritime_manager_identity_reassignment_guard
  ON public.lm_maritime_manager_identities;
CREATE TRIGGER lm_maritime_manager_identity_reassignment_guard
  BEFORE UPDATE ON public.lm_maritime_manager_identities
  FOR EACH ROW EXECUTE FUNCTION public.prevent_lm_maritime_manager_identity_reassignment_v1();

-- Manager enrollment is independent of the shared lm_users/Calendar/Telegram store.
CREATE TABLE IF NOT EXISTS public.lm_maritime_manager_enrollments (
  uid text PRIMARY KEY,
  auth_subject uuid NOT NULL UNIQUE,
  email text NOT NULL CHECK (length(email) BETWEEN 3 AND 320),
  timezone text NOT NULL DEFAULT 'UTC',
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'provisioning', 'active', 'paused', 'effect_unknown')),
  source text NOT NULL,
  consent_version text NOT NULL,
  agent_id text UNIQUE,
  release_sha text NOT NULL CHECK (release_sha ~ '^[0-9a-f]{40}$'),
  paused_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (uid, auth_subject)
    REFERENCES public.lm_maritime_manager_identities(uid, auth_subject)
);
CREATE UNIQUE INDEX IF NOT EXISTS lm_maritime_manager_uid_agent
  ON public.lm_maritime_manager_enrollments (uid, agent_id);

CREATE OR REPLACE FUNCTION public.claim_lm_maritime_manager_provision_v1(p_uid text)
RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
  WITH claimed AS (
    UPDATE public.lm_maritime_manager_enrollments
    SET status = 'provisioning'
    WHERE uid = p_uid AND status = 'pending' AND paused_at IS NULL
    RETURNING uid
  ) SELECT EXISTS (SELECT 1 FROM claimed);
$$;

CREATE OR REPLACE FUNCTION public.bind_lm_maritime_manager_agent_v1(
  p_uid text, p_auth_subject uuid, p_agent_id text, p_release_sha text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
DECLARE changed boolean;
BEGIN
  IF p_agent_id IS NULL OR p_agent_id !~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'
     OR p_release_sha IS NULL OR p_release_sha !~ '^[0-9a-f]{40}$' THEN
    RAISE EXCEPTION 'maritime_manager_input_invalid';
  END IF;
  UPDATE public.lm_maritime_manager_enrollments
    SET agent_id = p_agent_id, release_sha = p_release_sha,
        status = CASE WHEN paused_at IS NOT NULL THEN 'paused' ELSE 'active' END
    WHERE uid = p_uid AND auth_subject = p_auth_subject
      AND (agent_id IS NULL OR agent_id = p_agent_id)
      AND (status IN ('provisioning', 'effect_unknown', 'paused')
           OR (status = 'active' AND agent_id = p_agent_id));
  changed := FOUND;
  RETURN changed;
EXCEPTION WHEN unique_violation THEN
  RETURN false;
END;
$$;
