-- Writer click attribution is an optional tenant-scoped join key.
-- It is populated only from a validated Telegram /start wr_<uuid> payload and
-- never changes Stripe's paid entitlement source of truth.
ALTER TABLE public.lm_users
  ADD COLUMN IF NOT EXISTS writer_attribution_ref text;

CREATE INDEX IF NOT EXISTS lm_users_writer_attribution_ref_idx
  ON public.lm_users (writer_attribution_ref)
  WHERE writer_attribution_ref IS NOT NULL;
