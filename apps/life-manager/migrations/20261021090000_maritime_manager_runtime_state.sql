-- Manager-only identity state. This table has no FK to global lm_users.
CREATE TABLE IF NOT EXISTS public.lm_maritime_manager_identities (
  uid text PRIMARY KEY CHECK (uid ~ '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  auth_subject uuid NOT NULL UNIQUE,
  verified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  first_touch jsonb,
  first_touch_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
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
