-- A18: human-principal browser work is terminally excluded and never resumable.

DO $$
DECLARE
  constraint_name text;
BEGIN
  FOR constraint_name IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'public.lm_browser_jobs'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%status%'
  LOOP
    EXECUTE format('ALTER TABLE public.lm_browser_jobs DROP CONSTRAINT %I', constraint_name);
  END LOOP;
END
$$;

UPDATE public.lm_browser_jobs
SET status = 'not_applicable',
    receipt = COALESCE(receipt, '{}'::jsonb) || jsonb_build_object(
      'reason', 'requires_human_principal',
      'external_effect', 'none',
      'legacy_status', 'handoff_required'
    ),
    lease_expires_at = NULL,
    finished_at = COALESCE(finished_at, clock_timestamp()),
    updated_at = clock_timestamp()
WHERE status = 'handoff_required';

ALTER TABLE public.lm_browser_jobs
  ADD CONSTRAINT lm_browser_jobs_status_no_human_check CHECK (
    status IN ('queued', 'claimed', 'completed', 'possibly_completed', 'not_applicable', 'failed')
  ),
  ADD CONSTRAINT lm_browser_jobs_lifecycle_no_human_check CHECK (
    (status = 'queued' AND claimed_at IS NULL AND lease_expires_at IS NULL AND finished_at IS NULL)
    OR (status = 'claimed' AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL AND finished_at IS NULL)
    OR (status IN ('completed', 'possibly_completed', 'not_applicable', 'failed')
      AND claimed_at IS NOT NULL AND finished_at IS NOT NULL)
  );

CREATE OR REPLACE FUNCTION public.append_lm_browser_job_trace(
  p_job_id uuid,
  p_stage text,
  p_meta jsonb DEFAULT '{}'::jsonb
) RETURNS SETOF public.lm_browser_jobs
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
  IF p_stage NOT IN (
    'claimed', 'principal_excluded', 'discovery', 'selected', 'action_started',
    'action_observed', 'provider_readback',
    'auth_context_loaded', 'auth_context_saved', 'auth_context_invalidated',
    'telegram_sent', 'evidence_sent', 'steel_released'
  ) THEN
    RAISE EXCEPTION 'invalid browser trace stage';
  END IF;
  IF jsonb_typeof(COALESCE(p_meta, '{}'::jsonb)) <> 'object'
    OR octet_length(COALESCE(p_meta, '{}'::jsonb)::text) > 8192 THEN
    RAISE EXCEPTION 'invalid browser trace metadata';
  END IF;
  RETURN QUERY
  UPDATE public.lm_browser_jobs
  SET trace = trace || jsonb_build_array(jsonb_build_object(
        'stage', p_stage, 'at', clock_timestamp(), 'meta', COALESCE(p_meta, '{}'::jsonb)
      )),
      updated_at = clock_timestamp()
  WHERE id = p_job_id AND jsonb_array_length(trace) < 100
  RETURNING *;
END
$$;

CREATE OR REPLACE FUNCTION public.finish_lm_browser_job(
  p_job_id uuid,
  p_status text,
  p_receipt jsonb,
  p_telegram_message_id bigint DEFAULT NULL
) RETURNS SETOF public.lm_browser_jobs
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
  IF p_status NOT IN ('completed', 'possibly_completed', 'not_applicable', 'failed') THEN
    RAISE EXCEPTION 'invalid browser terminal status';
  END IF;
  IF jsonb_typeof(p_receipt) <> 'object' OR octet_length(p_receipt::text) > 16384 THEN
    RAISE EXCEPTION 'invalid browser receipt';
  END IF;
  RETURN QUERY
  UPDATE public.lm_browser_jobs
  SET status = p_status,
      receipt = p_receipt,
      telegram_result_message_id = p_telegram_message_id,
      lease_expires_at = NULL,
      finished_at = clock_timestamp(),
      updated_at = clock_timestamp()
  WHERE id = p_job_id AND status = 'claimed'
  RETURNING *;
END
$$;
