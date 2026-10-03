-- Provider-lane CFO readback. This is additive to lm_usage_cost_summary: the lane gate needs an
-- explicit tenant binding and an explicit unknown-count column, so a missing field cannot become 0.
CREATE OR REPLACE FUNCTION public.lm_provider_lane_summary(
  p_period_start timestamptz,
  p_period_end timestamptz,
  p_tenant_id text
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
  estimated_cost_usd numeric,
  unknown_count bigint
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
    COALESCE(sum(est_usd), 0)::numeric AS estimated_cost_usd,
    count(*) FILTER (WHERE COALESCE(meta->>'actual_status', 'unknown') = 'unknown')::bigint AS unknown_count
  FROM public.lm_api_cost
  WHERE kind = 'provider_usage'
    AND uid = p_tenant_id
    AND ts >= p_period_start
    AND ts < p_period_end
  GROUP BY 1, 2, 3, 4, 5, 6, 7
  ORDER BY 1 DESC, 2, 3, 4, 5, 6, 7;
$$;

REVOKE ALL ON FUNCTION public.lm_provider_lane_summary(timestamptz, timestamptz, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lm_provider_lane_summary(timestamptz, timestamptz, text)
  TO service_role;
