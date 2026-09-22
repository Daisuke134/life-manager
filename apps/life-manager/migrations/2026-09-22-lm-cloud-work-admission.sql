-- CC04: one bounded non-effectful Cloud claim per tenant. This reuses the
-- canonical runtime queue and its lease/attempt fields; it is not a second scheduler.

CREATE OR REPLACE FUNCTION public.claim_lm_cloud_runtime_job(
  p_worker_id text,
  p_capabilities text[],
  p_tenant_id text,
  p_lease_seconds integer DEFAULT 180
) RETURNS SETOF public.lm_runtime_jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  candidate_job_id text;
BEGIN
  IF p_worker_id IS NULL OR char_length(p_worker_id) NOT BETWEEN 1 AND 200
    OR p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'
    OR p_tenant_id IS NULL OR char_length(p_tenant_id) NOT BETWEEN 1 AND 200
    OR p_tenant_id !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
    OR p_capabilities IS NULL
    OR p_capabilities <> ARRAY['general-agent.work']::text[]
    OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 30 AND 900
  THEN
    RAISE EXCEPTION 'cloud runtime claim invalid';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended('lm_cloud_work:' || p_tenant_id, 0)
  );

  IF EXISTS (
    SELECT 1 FROM public.lm_runtime_jobs AS active
    WHERE active.tenant_id = p_tenant_id
      AND active.loop_id = 'life-manager.manager'
      AND active.capability = 'general-agent.work'
      AND active.effect_class = 'none'
      AND active.effect_key IS NULL
      AND active.max_attempts = 1
      AND jsonb_typeof(active.input_refs) = 'object'
      AND active.input_refs ? 'goal_ref'
      AND active.input_refs = jsonb_build_object(
        'goal_ref', active.input_refs->>'goal_ref'
      )
      AND left(
        active.input_refs->>'goal_ref',
        char_length('goal-portfolio://' || p_tenant_id || '/')
      ) = 'goal-portfolio://' || p_tenant_id || '/'
      AND active.job_id ~ '^goal:[a-z0-9][a-z0-9._-]{0,199}:r[1-9][0-9]*$'
      AND active.input_refs->>'goal_ref' =
        'goal-portfolio://' || p_tenant_id || '/'
        || split_part(active.job_id, ':', 2) || '?revision='
        || substring(split_part(active.job_id, ':', 3) FROM 2)
      AND active.status = 'running'
      AND active.lease_expires_at > clock_timestamp()
  ) THEN
    RETURN;
  END IF;

  SELECT jobs.job_id INTO candidate_job_id
  FROM public.lm_runtime_jobs AS jobs
  WHERE jobs.tenant_id = p_tenant_id
    AND jobs.loop_id = 'life-manager.manager'
    AND jobs.capability = ANY(p_capabilities)
    AND jobs.capability = 'general-agent.work'
    AND jobs.effect_class = 'none'
    AND jobs.effect_key IS NULL
    AND jobs.max_attempts = 1
    AND jsonb_typeof(jobs.input_refs) = 'object'
    AND jobs.input_refs ? 'goal_ref'
    AND jobs.input_refs = jsonb_build_object(
      'goal_ref', jobs.input_refs->>'goal_ref'
    )
    AND left(
      jobs.input_refs->>'goal_ref',
      char_length('goal-portfolio://' || p_tenant_id || '/')
    ) = 'goal-portfolio://' || p_tenant_id || '/'
    AND jobs.job_id ~ '^goal:[a-z0-9][a-z0-9._-]{0,199}:r[1-9][0-9]*$'
    AND jobs.input_refs->>'goal_ref' =
      'goal-portfolio://' || p_tenant_id || '/'
      || split_part(jobs.job_id, ':', 2) || '?revision='
      || substring(split_part(jobs.job_id, ':', 3) FROM 2)
    AND jobs.available_at <= clock_timestamp()
    AND jobs.attempt < jobs.max_attempts
    AND (
      jobs.status = 'queued'
      OR (
        jobs.status = 'running'
        AND jobs.lease_expires_at <= clock_timestamp()
      )
    )
  ORDER BY jobs.available_at, jobs.created_at, jobs.job_id
  LIMIT 1
  FOR UPDATE SKIP LOCKED;

  IF candidate_job_id IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  UPDATE public.lm_runtime_jobs AS jobs
  SET status = 'running',
      attempt = jobs.attempt + 1,
      lease_owner = p_worker_id,
      lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds),
      last_error_code = NULL,
      updated_at = clock_timestamp()
  WHERE jobs.job_id = candidate_job_id
    AND jobs.tenant_id = p_tenant_id
    AND jobs.effect_class = 'none'
    AND jobs.attempt < jobs.max_attempts
  RETURNING jobs.*;
END
$$;

REVOKE ALL ON FUNCTION public.claim_lm_cloud_runtime_job(text,text[],text,integer) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON FUNCTION public.claim_lm_cloud_runtime_job(text,text[],text,integer) FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON FUNCTION public.claim_lm_cloud_runtime_job(text,text[],text,integer) FROM authenticated';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.claim_lm_cloud_runtime_job(text,text[],text,integer) TO service_role';
  END IF;
END
$$;
