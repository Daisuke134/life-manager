-- Persist the provider handle returned by the outbound call API on the wake ledger.
ALTER TABLE public.lm_wake_log ADD COLUMN IF NOT EXISTS provider_call_id text;

COMMENT ON COLUMN public.lm_wake_log.provider_call_id IS
  'Provider call identifier returned when the wake call was placed; NULL means no provider acceptance was recorded.';
