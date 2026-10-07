-- Web billing uses per-stream event cursors and an optimistic row revision.
-- A Stripe invoice and subscription update are independent evidence streams; keeping separate cursors
-- lets a paid invoice restore a just-expired trial even when its event was created earlier.
ALTER TABLE public.lm_users
  ADD COLUMN IF NOT EXISTS web_billing_revision bigint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS web_billing_cancel_at_period_end boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS web_subscription_event_at timestamptz,
  ADD COLUMN IF NOT EXISTS web_subscription_event_priority smallint,
  ADD COLUMN IF NOT EXISTS web_subscription_event_id text,
  ADD COLUMN IF NOT EXISTS web_invoice_event_at timestamptz,
  ADD COLUMN IF NOT EXISTS web_invoice_event_priority smallint,
  ADD COLUMN IF NOT EXISTS web_invoice_event_id text,
  ADD COLUMN IF NOT EXISTS web_invoice_subscription_id text,
  ADD COLUMN IF NOT EXISTS web_invoice_paid boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS web_invoice_amount_paid bigint;
