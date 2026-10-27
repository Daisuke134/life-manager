-- Cloud subscription state is separate from Calendar billing and customer Capafy proceeds.
CREATE TABLE IF NOT EXISTS public.lm_maritime_cloud_subscriptions (
  uid text PRIMARY KEY
    REFERENCES public.lm_maritime_manager_enrollments(uid) ON DELETE CASCADE,
  stripe_subscription_id text NOT NULL UNIQUE
    CHECK (stripe_subscription_id ~ '^sub_[A-Za-z0-9]+$'),
  stripe_product_id text NOT NULL
    CHECK (stripe_product_id ~ '^prod_[A-Za-z0-9]+$'),
  stripe_price_id text NOT NULL
    CHECK (stripe_price_id ~ '^price_[A-Za-z0-9]+$'),
  stripe_status text NOT NULL
    CHECK (stripe_status IN ('active','trialing','past_due','unpaid','canceled','incomplete','incomplete_expired','paused','ambiguous')),
  entitled boolean NOT NULL,
  stripe_subscription_created bigint NOT NULL CHECK (stripe_subscription_created > 0),
  last_event_created bigint NOT NULL CHECK (last_event_created > 0),
  last_event_id text NOT NULL CHECK (last_event_id ~ '^evt_[A-Za-z0-9]+$'),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (uid ~ '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  CHECK (entitled = (stripe_status = 'active'))
);

ALTER TABLE public.lm_maritime_cloud_subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lm_maritime_cloud_subscriptions_service_role_access
  ON public.lm_maritime_cloud_subscriptions;
CREATE POLICY lm_maritime_cloud_subscriptions_service_role_access
  ON public.lm_maritime_cloud_subscriptions FOR ALL TO service_role
  USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE public.lm_maritime_cloud_subscriptions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.lm_maritime_cloud_subscriptions TO service_role;
