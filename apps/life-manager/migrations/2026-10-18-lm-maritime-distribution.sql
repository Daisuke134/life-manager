ALTER TABLE public.lm_web_funnel_events
  DROP CONSTRAINT IF EXISTS lm_web_funnel_events_event_name_check;

ALTER TABLE public.lm_web_funnel_events
  ADD CONSTRAINT lm_web_funnel_events_event_name_check CHECK (event_name IN (
    'landing_view', 'google_connect_start', 'google_authenticated', 'calendar_active',
    'first_travel_block', 'checkout_created', 'trial_started', 'paid_invoice',
    'cancellation_requested', 'subscription_canceled', 'refund_recorded',
    'maritime_landing_view', 'maritime_cta_click', 'maritime_start', 'maritime_consent',
    'maritime_consent_revoked', 'maritime_first_response', 'maritime_7day_return'
  ));

CREATE UNIQUE INDEX IF NOT EXISTS lm_web_funnel_events_maritime_once_idx
  ON public.lm_web_funnel_events (event_name, source_object_id)
  WHERE source_object_id IS NOT NULL AND event_name IN (
    'maritime_start', 'maritime_consent', 'maritime_consent_revoked',
    'maritime_first_response', 'maritime_7day_return'
  );

CREATE TABLE IF NOT EXISTS public.lm_maritime_pilot_participants (
  participant_id text PRIMARY KEY CHECK (participant_id ~ '^[a-f0-9]{64}$'),
  source text NOT NULL CHECK (source IN (
    'landing', 'aniccaai', 'x', 'reddit', 'discord', 'telegram',
    'community', 'referral', 'hackathon', 'direct', 'other'
  )),
  consent_version text NOT NULL,
  consented_at timestamptz NOT NULL,
  revoked_at timestamptz,
  first_response_at timestamptz,
  returned_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.lm_maritime_pilot_participants ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lm_maritime_pilot_participants FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.lm_maritime_pilot_participants TO service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE public.lm_maritime_pilot_participants FROM service_role;

CREATE OR REPLACE FUNCTION public.claim_lm_maritime_participant_v1(
  p_participant_id text,
  p_source text,
  p_consent_version text,
  p_max_users integer,
  p_now timestamptz DEFAULT now()
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
  v_existing public.lm_maritime_pilot_participants%ROWTYPE;
  v_count integer;
  v_now timestamptz := COALESCE(p_now, now());
BEGIN
  IF p_participant_id IS NULL OR p_participant_id !~ '^[a-f0-9]{64}$'
    OR p_source IS NULL OR p_source NOT IN ('landing', 'aniccaai', 'x', 'reddit', 'discord', 'telegram', 'community', 'referral', 'hackathon', 'direct', 'other')
    OR p_consent_version IS DISTINCT FROM 'maritime-retention-v1'
    OR p_max_users IS NULL OR p_max_users < 1 OR p_max_users > 1000 THEN
    RETURN 'invalid';
  END IF;

  PERFORM pg_advisory_xact_lock(824618221001);
  SELECT * INTO v_existing
    FROM public.lm_maritime_pilot_participants
    WHERE participant_id = p_participant_id
    FOR UPDATE;

  IF FOUND THEN
    IF v_existing.consent_version = p_consent_version
      AND v_existing.consented_at IS NOT NULL
      AND v_existing.revoked_at IS NULL THEN
      RETURN 'already_consented';
    END IF;
    UPDATE public.lm_maritime_pilot_participants
      SET source = COALESCE(v_existing.source, p_source),
          consent_version = p_consent_version,
          consented_at = v_now,
          revoked_at = NULL,
          updated_at = v_now
      WHERE participant_id = p_participant_id;
    RETURN 'consented';
  END IF;

  SELECT count(*)::integer INTO v_count
    FROM public.lm_maritime_pilot_participants
    WHERE consented_at IS NOT NULL;
  IF v_count >= p_max_users THEN
    RETURN 'capacity_full';
  END IF;

  INSERT INTO public.lm_maritime_pilot_participants (
    participant_id, source, consent_version, consented_at, created_at, updated_at
  ) VALUES (
    p_participant_id, p_source, p_consent_version, v_now, v_now, v_now
  );
  RETURN 'consented';
END;
$function$;

REVOKE ALL ON FUNCTION public.claim_lm_maritime_participant_v1(text, text, text, integer, timestamptz)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_lm_maritime_participant_v1(text, text, text, integer, timestamptz)
  TO service_role;

CREATE OR REPLACE FUNCTION public.mark_lm_maritime_pilot_milestone_v1(
  p_participant_id text,
  p_milestone text,
  p_at timestamptz DEFAULT now()
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
  v_at timestamptz := COALESCE(p_at, now());
BEGIN
  IF p_participant_id IS NULL OR p_participant_id !~ '^[a-f0-9]{64}$'
    OR p_milestone IS NULL OR p_milestone NOT IN ('first_response', 'return_7d') THEN
    RETURN false;
  END IF;

  IF p_milestone = 'first_response' THEN
    UPDATE public.lm_maritime_pilot_participants
      SET first_response_at = v_at, updated_at = v_at
      WHERE participant_id = p_participant_id
        AND consent_version = 'maritime-retention-v1'
        AND consented_at IS NOT NULL AND revoked_at IS NULL
        AND first_response_at IS NULL;
    RETURN FOUND;
  END IF;

  UPDATE public.lm_maritime_pilot_participants
    SET returned_at = v_at, updated_at = v_at
    WHERE participant_id = p_participant_id
      AND consent_version = 'maritime-retention-v1'
      AND consented_at IS NOT NULL AND revoked_at IS NULL
      AND first_response_at <= v_at - interval '7 days'
      AND returned_at IS NULL;
  RETURN FOUND;
END;
$function$;

REVOKE ALL ON FUNCTION public.mark_lm_maritime_pilot_milestone_v1(text, text, timestamptz)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.mark_lm_maritime_pilot_milestone_v1(text, text, timestamptz)
  TO service_role;
