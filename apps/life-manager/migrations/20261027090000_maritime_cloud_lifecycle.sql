-- Cloud subscription lifecycle is independent of manager activation and Calendar billing.
ALTER TABLE public.lm_maritime_cloud_subscriptions
  DROP CONSTRAINT IF EXISTS lm_maritime_cloud_subscriptions_uid_fkey;
ALTER TABLE public.lm_maritime_cloud_subscriptions
  ADD CONSTRAINT lm_maritime_cloud_subscriptions_uid_fkey
  FOREIGN KEY (uid) REFERENCES public.lm_users(uid) ON DELETE CASCADE;

ALTER TABLE public.lm_maritime_cloud_subscriptions
  ADD COLUMN IF NOT EXISTS stripe_customer_id text
    CHECK (stripe_customer_id IS NULL OR stripe_customer_id ~ '^cus_[A-Za-z0-9]+$'),
  ADD COLUMN IF NOT EXISTS cancel_at_period_end boolean NOT NULL DEFAULT false;

ALTER TABLE public.lm_maritime_cloud_subscriptions
  DROP CONSTRAINT IF EXISTS lm_maritime_cloud_subscriptions_entitled_check;
ALTER TABLE public.lm_maritime_cloud_subscriptions
  ADD CONSTRAINT lm_maritime_cloud_subscriptions_entitled_check
  CHECK (entitled = (stripe_status IN ('active','trialing','past_due')));
