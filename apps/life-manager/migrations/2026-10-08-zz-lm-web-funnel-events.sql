CREATE TABLE IF NOT EXISTS public.lm_web_funnel_events (
  event_id text PRIMARY KEY,
  event_name text NOT NULL CHECK (event_name IN (
    'landing_view', 'google_connect_start', 'google_authenticated', 'calendar_active',
    'first_travel_block', 'checkout_created', 'trial_started', 'paid_invoice',
    'cancellation_requested', 'subscription_canceled', 'refund_recorded'
  )),
  uid text CHECK (uid IS NULL OR uid ~ '^lm_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'),
  source_object_id text,
  source_event_id text UNIQUE,
  attribution jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(attribution) = 'object'),
  amount_usd numeric CHECK (amount_usd IS NULL OR amount_usd >= 0),
  currency text CHECK (currency IS NULL OR currency ~ '^[a-z]{3}$'),
  billing_reason text,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

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

CREATE OR REPLACE FUNCTION public.lm_web_funnel_events_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
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

ALTER TABLE public.lm_web_funnel_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lm_web_funnel_events FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON TABLE public.lm_web_funnel_events TO service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE public.lm_web_funnel_events FROM service_role;
