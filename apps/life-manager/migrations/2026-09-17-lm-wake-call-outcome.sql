-- Record the product result of a provider-accepted wake call without changing the existing
-- lm_wake_log correlation ledger or charging unanswered attempts as conversation seconds.

ALTER TABLE public.lm_wake_log
  ADD COLUMN IF NOT EXISTS call_outcome text,
  ADD COLUMN IF NOT EXISTS telnyx_hangup_cause text,
  ADD COLUMN IF NOT EXISTS telnyx_call_duration_seconds integer;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'public.lm_wake_log'::regclass
       AND conname = 'lm_wake_log_call_outcome_check'
  ) THEN
    ALTER TABLE public.lm_wake_log
      ADD CONSTRAINT lm_wake_log_call_outcome_check
      CHECK (call_outcome IS NULL OR call_outcome IN ('conversation', 'no_answer', 'dial_failed'));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conrelid = 'public.lm_wake_log'::regclass
       AND conname = 'lm_wake_log_telnyx_call_duration_seconds_check'
  ) THEN
    ALTER TABLE public.lm_wake_log
      ADD CONSTRAINT lm_wake_log_telnyx_call_duration_seconds_check
      CHECK (telnyx_call_duration_seconds IS NULL
        OR telnyx_call_duration_seconds BETWEEN 0 AND 14400);
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS lm_wake_log_uid_called_outcome_idx
  ON public.lm_wake_log (uid, called_at, call_outcome);

CREATE OR REPLACE FUNCTION public.record_lm_wake_telnyx_outcome(
  p_uid text,
  p_event_key text,
  p_claim_token text,
  p_telnyx_call_control_id text,
  p_call_outcome text DEFAULT NULL,
  p_hangup_cause text DEFAULT NULL,
  p_connected_seconds integer DEFAULT NULL
) RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_matched integer;
BEGIN
  IF p_uid IS NULL OR btrim(p_uid) = '' OR char_length(p_uid) > 256
    OR p_event_key IS NULL OR btrim(p_event_key) = '' OR char_length(p_event_key) > 512
    OR p_claim_token IS NULL OR btrim(p_claim_token) = '' OR char_length(p_claim_token) > 512
    OR p_telnyx_call_control_id IS NULL OR btrim(p_telnyx_call_control_id) = ''
    OR char_length(p_telnyx_call_control_id) > 512
    OR (p_call_outcome IS NOT NULL
      AND p_call_outcome NOT IN ('conversation', 'no_answer', 'dial_failed'))
    OR (p_hangup_cause IS NOT NULL
      AND (btrim(p_hangup_cause) = '' OR char_length(p_hangup_cause) > 512))
    OR (p_connected_seconds IS NOT NULL
      AND (p_connected_seconds < 0 OR p_connected_seconds > 14400)) THEN
    RAISE EXCEPTION 'invalid Telnyx wake outcome';
  END IF;

  UPDATE public.lm_wake_log
     SET call_outcome = CASE
           WHEN p_call_outcome IS NULL THEN call_outcome
           WHEN p_call_outcome = 'conversation' THEN 'conversation'
           WHEN call_outcome IN ('conversation', 'no_answer') THEN call_outcome
           ELSE p_call_outcome
         END,
         telnyx_hangup_cause = COALESCE(telnyx_hangup_cause, p_hangup_cause),
         telnyx_call_duration_seconds = COALESCE(telnyx_call_duration_seconds, p_connected_seconds)
   WHERE uid = p_uid
     AND event_key = p_event_key
     AND claim_token = p_claim_token
     AND telnyx_call_control_id = p_telnyx_call_control_id;

  GET DIAGNOSTICS v_matched = ROW_COUNT;
  RETURN v_matched;
END;
$$;

REVOKE ALL ON FUNCTION public.record_lm_wake_telnyx_outcome(text,text,text,text,text,text,integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_lm_wake_telnyx_outcome(text,text,text,text,text,text,integer)
  TO service_role;
