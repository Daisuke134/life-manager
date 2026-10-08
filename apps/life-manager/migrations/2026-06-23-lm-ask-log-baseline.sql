-- Source-owned baseline for the ask/reply ledger used by lib/ask.js and inbound reply handlers.
-- Keep this before 2026-06-24-ch1-atomic-dedup.sql so a fresh migration sequence has the table first.
CREATE TABLE IF NOT EXISTS public.lm_ask_log (
  id bigserial PRIMARY KEY,
  uid text NOT NULL,
  event_id text NOT NULL,
  asked_at timestamptz DEFAULT now(),
  reply_token text,
  answered_at timestamptz,
  resolved_from text,
  candidate_location text,
  semantic_key text,
  question_type text,
  question_context jsonb NOT NULL DEFAULT '{}'::jsonb,
  answer_value text,
  answer_source text,
  answer_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  telegram_chat_id text,
  CONSTRAINT lm_ask_log_uid_event_id_key UNIQUE (uid, event_id)
);

CREATE INDEX IF NOT EXISTS lm_ask_log_reply_token_idx
  ON public.lm_ask_log (reply_token);

CREATE UNIQUE INDEX IF NOT EXISTS lm_ask_log_uid_semantic_key_key
  ON public.lm_ask_log (uid, semantic_key)
  WHERE semantic_key IS NOT NULL;

ALTER TABLE public.lm_ask_log ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lm_ask_log FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.lm_ask_log TO service_role;

REVOKE ALL ON SEQUENCE public.lm_ask_log_id_seq FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE public.lm_ask_log_id_seq TO service_role;
