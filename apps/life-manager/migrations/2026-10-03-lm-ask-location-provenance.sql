-- Preserve source/licence/attribution proof for provider-backed calendar locations.
ALTER TABLE public.lm_ask_log
  ADD COLUMN IF NOT EXISTS resolution_provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
