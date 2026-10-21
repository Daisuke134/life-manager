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
    SET agent_id = p_agent_id,
        status = CASE WHEN paused_at IS NOT NULL THEN 'paused' ELSE 'active' END
    WHERE uid = p_uid AND auth_subject = p_auth_subject
      AND release_sha = p_release_sha
      AND (agent_id IS NULL OR agent_id = p_agent_id)
      AND (status IN ('provisioning', 'effect_unknown', 'paused')
           OR (status = 'active' AND agent_id = p_agent_id));
  changed := FOUND;
  RETURN changed;
EXCEPTION WHEN unique_violation THEN
  RETURN false;
END;
$$;

-- This is only a dispatch checkpoint; terminal state and receipts stay in runtime_jobs.
CREATE TABLE IF NOT EXISTS public.lm_maritime_manager_executions (
  uid text NOT NULL,
  occurrence_id text NOT NULL CHECK (occurrence_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
  agent_id text NOT NULL,
  date_key date NOT NULL,
  release_sha text NOT NULL CHECK (release_sha ~ '^[0-9a-f]{40}$'),
  execution_id text CHECK (execution_id IS NULL OR execution_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'),
  claimed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (uid, occurrence_id),
  FOREIGN KEY (uid, agent_id) REFERENCES public.lm_maritime_manager_enrollments(uid, agent_id),
  UNIQUE (agent_id, execution_id)
);

CREATE OR REPLACE FUNCTION public.claim_lm_maritime_manager_cycle_v1(
  p_uid text, p_occurrence_id text, p_agent_id text, p_release_sha text, p_date_key date
) RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
  WITH claimed AS (
    INSERT INTO public.lm_maritime_manager_executions(uid, occurrence_id, agent_id, release_sha, date_key)
      SELECT uid, p_occurrence_id, agent_id, p_release_sha, p_date_key
      FROM public.lm_maritime_manager_enrollments
      WHERE uid = p_uid AND agent_id = p_agent_id AND release_sha = p_release_sha
        AND status = 'active' AND paused_at IS NULL
      ON CONFLICT (uid, occurrence_id) DO NOTHING
      RETURNING uid
  ) SELECT EXISTS (SELECT 1 FROM claimed);
$$;

CREATE OR REPLACE FUNCTION public.bind_lm_maritime_manager_execution_v1(
  p_uid text, p_occurrence_id text, p_agent_id text, p_release_sha text, p_date_key date,
  p_execution_id text
) RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
  WITH bound AS (
    UPDATE public.lm_maritime_manager_executions SET execution_id = p_execution_id
      WHERE uid = p_uid AND occurrence_id = p_occurrence_id AND agent_id = p_agent_id
        AND release_sha = p_release_sha AND date_key = p_date_key
        AND p_execution_id IS NOT NULL
        AND (execution_id IS NULL OR execution_id = p_execution_id)
      RETURNING uid
  ) SELECT EXISTS (SELECT 1 FROM bound);
$$;

CREATE TABLE IF NOT EXISTS public.lm_maritime_pilot_participants (
  participant_id text PRIMARY KEY CHECK (participant_id ~ '^[a-f0-9]{64}$'),
  source text NOT NULL CHECK (source IN (
    'landing', 'aniccaai', 'x', 'instagram', 'reddit', 'discord', 'telegram',
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

CREATE OR REPLACE FUNCTION public.claim_lm_maritime_participant_v1(
  p_participant_id text,
  p_source text,
  p_consent_version text,
  p_max_users integer,
  p_now timestamptz DEFAULT now()
) RETURNS text LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
DECLARE
  existing_participant public.lm_maritime_pilot_participants%ROWTYPE;
  participant_count integer;
  claimed_at timestamptz := COALESCE(p_now, now());
BEGIN
  IF p_participant_id IS NULL OR p_participant_id !~ '^[a-f0-9]{64}$'
    OR p_source IS NULL OR p_source NOT IN (
      'landing', 'aniccaai', 'x', 'instagram', 'reddit', 'discord', 'telegram',
      'community', 'referral', 'hackathon', 'direct', 'other'
    )
    OR p_consent_version IS DISTINCT FROM 'maritime-retention-v1'
    OR p_max_users IS NULL OR p_max_users < 1 OR p_max_users > 1000 THEN
    RETURN 'invalid';
  END IF;

  PERFORM pg_advisory_xact_lock(824618221001);
  SELECT * INTO existing_participant
    FROM public.lm_maritime_pilot_participants
    WHERE participant_id = p_participant_id
    FOR UPDATE;

  IF FOUND THEN
    IF existing_participant.consent_version = p_consent_version
      AND existing_participant.consented_at IS NOT NULL
      AND existing_participant.revoked_at IS NULL THEN
      RETURN 'already_consented';
    END IF;
    UPDATE public.lm_maritime_pilot_participants
      SET source = COALESCE(existing_participant.source, p_source),
          consent_version = p_consent_version,
          consented_at = claimed_at,
          revoked_at = NULL,
          updated_at = claimed_at
      WHERE participant_id = p_participant_id;
    RETURN 'consented';
  END IF;

  SELECT count(*)::integer INTO participant_count
    FROM public.lm_maritime_pilot_participants
    WHERE consented_at IS NOT NULL;
  IF participant_count >= p_max_users THEN
    RETURN 'capacity_full';
  END IF;

  INSERT INTO public.lm_maritime_pilot_participants (
    participant_id, source, consent_version, consented_at, created_at, updated_at
  ) VALUES (
    p_participant_id, p_source, p_consent_version, claimed_at, claimed_at, claimed_at
  );
  RETURN 'consented';
END;
$$;

CREATE TABLE IF NOT EXISTS public.lm_web_funnel_events (
  event_id text PRIMARY KEY,
  event_name text NOT NULL,
  audience_kind text,
  uid text CHECK (uid IS NULL OR uid ~ '^lm_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'),
  source_object_id text,
  source_event_id text UNIQUE,
  attribution jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(attribution) = 'object'),
  amount_usd numeric CHECK (amount_usd IS NULL OR amount_usd >= 0),
  currency text CHECK (currency IS NULL OR currency ~ '^[a-z]{3}$'),
  billing_reason text,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.lm_web_funnel_events ADD COLUMN IF NOT EXISTS audience_kind text;
ALTER TABLE public.lm_web_funnel_events DROP CONSTRAINT IF EXISTS lm_web_funnel_events_event_name_check;
ALTER TABLE public.lm_web_funnel_events ADD CONSTRAINT lm_web_funnel_events_event_name_check CHECK (event_name IN (
  'landing_view', 'google_connect_start', 'google_authenticated', 'calendar_active',
  'first_travel_block', 'checkout_created', 'trial_started', 'paid_invoice',
  'cancellation_requested', 'subscription_canceled', 'refund_recorded',
  'maritime_landing_view', 'maritime_cta_click', 'maritime_start', 'maritime_consent',
  'maritime_consent_revoked', 'maritime_first_response', 'maritime_7day_return',
  'maritime_email_verified', 'maritime_manager_activated', 'maritime_work_completed',
  'maritime_report_sent', 'maritime_returned'
));
ALTER TABLE public.lm_web_funnel_events DROP CONSTRAINT IF EXISTS lm_web_funnel_events_audience_kind_check;
ALTER TABLE public.lm_web_funnel_events ADD CONSTRAINT lm_web_funnel_events_audience_kind_check
  CHECK (audience_kind IS NULL OR (left(event_name, 9) = 'maritime_' AND audience_kind IN ('internal', 'external')));

CREATE INDEX IF NOT EXISTS lm_web_funnel_events_name_time_idx
  ON public.lm_web_funnel_events (event_name, occurred_at);
CREATE INDEX IF NOT EXISTS lm_web_funnel_events_uid_time_idx
  ON public.lm_web_funnel_events (uid, occurred_at) WHERE uid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS lm_web_funnel_events_once_per_source_idx
  ON public.lm_web_funnel_events (event_name, source_object_id)
  WHERE source_object_id IS NOT NULL AND event_name IN (
    'google_authenticated', 'calendar_active', 'first_travel_block', 'checkout_created',
    'trial_started', 'paid_invoice', 'refund_recorded'
  );
CREATE UNIQUE INDEX IF NOT EXISTS lm_web_funnel_events_maritime_once_idx
  ON public.lm_web_funnel_events (event_name, source_object_id)
  WHERE source_object_id IS NOT NULL AND event_name IN (
    'maritime_start', 'maritime_consent', 'maritime_consent_revoked',
    'maritime_first_response', 'maritime_7day_return'
  );
CREATE UNIQUE INDEX IF NOT EXISTS lm_web_funnel_events_manager_once_idx
  ON public.lm_web_funnel_events (event_name, source_object_id)
  WHERE source_object_id IS NOT NULL AND event_name IN (
    'maritime_email_verified', 'maritime_manager_activated', 'maritime_returned'
  );

CREATE OR REPLACE FUNCTION public.lm_web_funnel_events_guard()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
  RAISE EXCEPTION 'lm_web_funnel_events is append-only';
END;
$$;
DROP TRIGGER IF EXISTS lm_web_funnel_events_guard ON public.lm_web_funnel_events;
CREATE TRIGGER lm_web_funnel_events_guard
  BEFORE UPDATE OR DELETE ON public.lm_web_funnel_events
  FOR EACH ROW EXECUTE FUNCTION public.lm_web_funnel_events_guard();
DROP TRIGGER IF EXISTS lm_web_funnel_events_truncate_guard ON public.lm_web_funnel_events;
CREATE TRIGGER lm_web_funnel_events_truncate_guard
  BEFORE TRUNCATE ON public.lm_web_funnel_events
  FOR EACH STATEMENT EXECUTE FUNCTION public.lm_web_funnel_events_guard();

CREATE TABLE IF NOT EXISTS public.lm_cfo_result_receipts (
  uid text NOT NULL REFERENCES public.lm_maritime_manager_identities(uid),
  period_key text NOT NULL,
  channel text NOT NULL CHECK (channel = 'email'),
  recipient_hash text NOT NULL CHECK (recipient_hash ~ '^[0-9a-f]{64}$'),
  status text NOT NULL CHECK (status IN ('pending', 'sent')),
  message text NOT NULL,
  observed_at timestamptz NOT NULL,
  provider_message_id text,
  sent_at timestamptz,
  PRIMARY KEY (uid, period_key),
  CHECK ((status = 'sent' AND provider_message_id IS NOT NULL AND sent_at IS NOT NULL)
    OR (status = 'pending' AND provider_message_id IS NULL AND sent_at IS NULL))
);
