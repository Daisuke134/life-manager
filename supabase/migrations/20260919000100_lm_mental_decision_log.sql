-- Canonical Supabase CLI copy of apps/life-manager/migrations/2026-09-18-lm-mental-decision-log.sql.
-- Closed MENTAL V1 decision rows. No raw Telegram, Gmail, calendar, or profile text is stored.
CREATE TABLE IF NOT EXISTS public.lm_mental_decision_log (
  id bigserial PRIMARY KEY,
  decision_key text NOT NULL UNIQUE CHECK (char_length(decision_key) = 64),
  uid text NOT NULL,
  policy_version text NOT NULL CHECK (char_length(policy_version) BETWEEN 1 AND 120),
  profile_version text NOT NULL CHECK (char_length(profile_version) BETWEEN 1 AND 120),
  source_outcome_id text,
  candidate_quote_ids jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(candidate_quote_ids) = 'array'),
  selected_quote_id text,
  silence_reason text,
  calendar_busy boolean NOT NULL,
  "window" text NOT NULL CHECK ("window" IN ('morning_orientation', 'midday_awareness', 'evening_direction')),
  telegram_message_id text,
  locale text NOT NULL CHECK (char_length(locale) BETWEEN 2 AND 16),
  family text CHECK (family IS NULL OR family IN ('affirmation', 'manifestation', 'mindfulness_inquiry')),
  local_day date,
  status text NOT NULL CHECK (status IN ('planned', 'silence', 'delivered', 'send_failed')),
  observed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (selected_quote_id IS NOT NULL OR silence_reason IS NOT NULL),
  CHECK (selected_quote_id IS NULL OR family IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS lm_mental_decision_log_uid_observed
  ON public.lm_mental_decision_log (uid, observed_at DESC);

ALTER TABLE public.lm_mental_decision_log ENABLE ROW LEVEL SECURITY;
