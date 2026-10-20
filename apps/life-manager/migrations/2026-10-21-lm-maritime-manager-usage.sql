ALTER TABLE public.lm_web_funnel_events DROP CONSTRAINT IF EXISTS lm_web_funnel_events_event_name_check;
ALTER TABLE public.lm_web_funnel_events ADD CONSTRAINT lm_web_funnel_events_event_name_check CHECK (event_name IN (
  'landing_view',
  'google_connect_start',
  'google_authenticated',
  'calendar_active',
  'first_travel_block',
  'checkout_created',
  'trial_started',
  'paid_invoice',
  'cancellation_requested',
  'subscription_canceled',
  'refund_recorded',
  'maritime_landing_view',
  'maritime_cta_click',
  'maritime_start',
  'maritime_consent',
  'maritime_consent_revoked',
  'maritime_first_response',
  'maritime_7day_return',
  'maritime_email_verified',
  'maritime_manager_activated',
  'maritime_work_completed',
  'maritime_report_sent',
  'maritime_returned'
));
ALTER TABLE public.lm_web_funnel_events ADD COLUMN IF NOT EXISTS audience_kind text;
ALTER TABLE public.lm_web_funnel_events DROP CONSTRAINT IF EXISTS lm_web_funnel_events_audience_kind_check;
ALTER TABLE public.lm_web_funnel_events ADD CONSTRAINT lm_web_funnel_events_audience_kind_check
  CHECK (audience_kind IS NULL OR (event_name LIKE 'maritime\_%' ESCAPE '\' AND audience_kind IN ('internal','external')));
