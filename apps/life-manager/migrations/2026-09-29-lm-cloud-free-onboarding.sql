-- Natural no-card cloud onboarding. A checkout is eligible only after this
-- server-owned timestamp is set from a validated AgentCore result.

BEGIN;

ALTER TABLE public.lm_cloud_tenants
  ADD COLUMN IF NOT EXISTS first_verified_result_at timestamptz;

CREATE OR REPLACE FUNCTION public.mark_lm_cloud_first_verified_result(
  p_tenant_id text,
  p_job_id text,
  p_provider_request_id text
) RETURNS timestamptz
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
  v_mark timestamptz;
BEGIN
  IF p_provider_request_id IS NULL OR char_length(p_provider_request_id) NOT BETWEEN 1 AND 500 THEN
    RAISE EXCEPTION 'verified provider request id invalid';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.lm_runtime_jobs
    WHERE tenant_id = p_tenant_id AND job_id = p_job_id
  ) THEN
    RAISE EXCEPTION 'verified cloud job unavailable';
  END IF;
  UPDATE public.lm_cloud_tenants
  SET first_verified_result_at = COALESCE(first_verified_result_at, clock_timestamp()),
      updated_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND status = 'active'
  RETURNING first_verified_result_at INTO v_mark;
  IF v_mark IS NULL THEN RAISE EXCEPTION 'active cloud tenant unavailable'; END IF;
  RETURN v_mark;
END
$$;

REVOKE ALL ON FUNCTION public.mark_lm_cloud_first_verified_result(text,text,text) FROM PUBLIC;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.mark_lm_cloud_first_verified_result(text,text,text) TO service_role';
  END IF;
END
$$;

COMMIT;
