-- Provider cost settlement is additive. Legacy rows remain readable as estimated/unknown.
ALTER TABLE public.lm_api_cost
  ADD COLUMN IF NOT EXISTS provider text,
  ADD COLUMN IF NOT EXISTS product text,
  ADD COLUMN IF NOT EXISTS sku text,
  ADD COLUMN IF NOT EXISTS operation text,
  ADD COLUMN IF NOT EXISTS actual_usd numeric,
  ADD COLUMN IF NOT EXISTS billing_status text,
  ADD COLUMN IF NOT EXISTS pricing_version text,
  ADD COLUMN IF NOT EXISTS source_receipt_ref text;

DO $$
BEGIN
  ALTER TABLE public.lm_api_cost
    ADD CONSTRAINT lm_api_cost_billing_status_check
    CHECK (billing_status IS NULL OR billing_status IN ('estimated', 'settled', 'unknown', 'not_applicable'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS lm_api_cost_provider_billing_idx
  ON public.lm_api_cost (uid, provider, billing_status, ts);

CREATE OR REPLACE FUNCTION public.lm_provider_cost_summary(
  p_period_start timestamptz,
  p_period_end timestamptz,
  p_tenant_id text DEFAULT NULL
) RETURNS TABLE (
  usage_day timestamptz,
  tenant_id text,
  provider text,
  product text,
  sku text,
  billing_status text,
  event_count bigint,
  provider_units numeric,
  estimated_cost_usd numeric,
  settled_cost_usd numeric,
  unknown_count bigint
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  SELECT date_trunc('day', ts), uid, provider, product, sku,
    COALESCE(billing_status, CASE WHEN est_usd IS NULL THEN 'unknown' ELSE 'estimated' END),
    count(*)::bigint, COALESCE(sum(quantity), 0)::numeric,
    COALESCE(sum(est_usd) FILTER (WHERE COALESCE(billing_status, 'estimated') = 'estimated'), 0)::numeric,
    sum(actual_usd) FILTER (WHERE billing_status = 'settled')::numeric,
    count(*) FILTER (WHERE COALESCE(billing_status, 'unknown') = 'unknown')::bigint
  FROM public.lm_api_cost
  WHERE kind = 'provider_cost' AND ts >= p_period_start AND ts < p_period_end
    AND (p_tenant_id IS NULL OR uid = p_tenant_id)
  GROUP BY 1, 2, 3, 4, 5, 6
  ORDER BY 1 DESC, 2, 3, 4, 5, 6;
$$;

REVOKE ALL ON FUNCTION public.lm_provider_cost_summary(timestamptz, timestamptz, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lm_provider_cost_summary(timestamptz, timestamptz, text)
  TO service_role;
