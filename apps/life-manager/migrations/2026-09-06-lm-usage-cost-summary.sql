-- COST-01: bounded, service-role-only dashboard query over the existing append-only cost ledger.
-- Raw provider payloads, credentials, addresses, coordinates, and customer billing state do not
-- belong in lm_api_cost.meta.
CREATE OR REPLACE FUNCTION public.lm_usage_cost_summary(
  p_period_start timestamptz,
  p_period_end timestamptz,
  p_tenant_id text DEFAULT NULL
) RETURNS TABLE (
  usage_day timestamptz,
  tenant_id text,
  provider text,
  feature text,
  outcome text,
  failure_class text,
  cache_hit boolean,
  event_count bigint,
  provider_units numeric,
  estimated_cost_usd numeric
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  SELECT
    date_trunc('day', ts) AS usage_day,
    uid AS tenant_id,
    meta->>'provider' AS provider,
    meta->>'feature' AS feature,
    meta->>'outcome' AS outcome,
    meta->>'failure_class' AS failure_class,
    COALESCE((meta->>'cache_hit')::boolean, false) AS cache_hit,
    count(*)::bigint AS event_count,
    COALESCE(sum(quantity), 0)::numeric AS provider_units,
    COALESCE(sum(est_usd), 0)::numeric AS estimated_cost_usd
  FROM public.lm_api_cost
  WHERE kind = 'provider_usage'
    AND ts >= p_period_start
    AND ts < p_period_end
    AND (p_tenant_id IS NULL OR uid = p_tenant_id)
  GROUP BY 1, 2, 3, 4, 5, 6, 7
  ORDER BY 1 DESC, 2, 3, 4, 5, 6, 7;
$$;

REVOKE ALL ON FUNCTION public.lm_usage_cost_summary(timestamptz, timestamptz, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lm_usage_cost_summary(timestamptz, timestamptz, text)
  TO service_role;

-- Budget governor readback: estimates, provider units, cache hits, and explicit unknowns.
CREATE OR REPLACE FUNCTION public.lm_provider_budget_summary(
  p_period_start timestamptz,
  p_period_end timestamptz,
  p_tenant_id text DEFAULT NULL
) RETURNS TABLE (
  tenant_id text,
  provider text,
  event_count bigint,
  provider_units numeric,
  estimated_cost_usd numeric,
  cache_hits bigint,
  unknown_count bigint,
  last_observed_at timestamptz
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  SELECT uid, meta->>'provider', count(*)::bigint, COALESCE(sum(quantity), 0)::numeric,
    sum(est_usd)::numeric,
    count(*) FILTER (WHERE COALESCE((meta->>'cache_hit')::boolean, false)),
    count(*) FILTER (WHERE est_usd IS NULL AND COALESCE((meta->>'cache_hit')::boolean, false) = false),
    max(ts)
  FROM public.lm_api_cost
  WHERE kind = 'provider_usage' AND ts >= p_period_start AND ts < p_period_end
    AND (p_tenant_id IS NULL OR uid = p_tenant_id)
  GROUP BY uid, meta->>'provider';
$$;

REVOKE ALL ON FUNCTION public.lm_provider_budget_summary(timestamptz, timestamptz, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lm_provider_budget_summary(timestamptz, timestamptz, text)
  TO service_role;
