-- Legacy v1 enrollments must remain idle until activation records current consent.
CREATE OR REPLACE FUNCTION public.claim_lm_maritime_manager_provision_v1(p_uid text)
RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
  WITH claimed AS (
    UPDATE public.lm_maritime_manager_enrollments
    SET status = 'provisioning'
    WHERE uid = p_uid AND status = 'pending' AND paused_at IS NULL
      AND consent_version = 'maritime-manager-v2'
    RETURNING uid
  ) SELECT EXISTS (SELECT 1 FROM claimed);
$$;

REVOKE ALL ON FUNCTION public.claim_lm_maritime_manager_provision_v1(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_lm_maritime_manager_provision_v1(text) TO service_role;

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
    SET agent_id = p_agent_id,
        status = CASE WHEN paused_at IS NOT NULL THEN 'paused' ELSE 'active' END
    WHERE uid = p_uid AND auth_subject = p_auth_subject
      AND release_sha = p_release_sha
      AND consent_version = 'maritime-manager-v2'
      AND (agent_id IS NULL OR agent_id = p_agent_id)
      AND (status IN ('provisioning', 'effect_unknown', 'paused')
           OR (status = 'active' AND agent_id = p_agent_id));
  changed := FOUND;
  RETURN changed;
EXCEPTION WHEN unique_violation THEN
  RETURN false;
END;
$$;
REVOKE ALL ON FUNCTION public.bind_lm_maritime_manager_agent_v1(text, uuid, text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.bind_lm_maritime_manager_agent_v1(text, uuid, text, text) TO service_role;
