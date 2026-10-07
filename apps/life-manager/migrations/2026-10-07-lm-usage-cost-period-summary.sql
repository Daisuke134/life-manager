-- COST-02: bounded, service-role-only cost summary by provider, SKU, operation, and unit.
CREATE OR REPLACE FUNCTION public.lm_usage_cost_period_summary(
  p_period_start timestamptz,
  p_period_end timestamptz,
  p_tenant_id text
) RETURNS TABLE (
  provider text,
  sku text,
  operation text,
  unit text,
  event_count bigint,
  request_count bigint,
  cache_hit_count bigint,
  cache_miss_count bigint,
  provider_units numeric,
  estimated_cost_usd numeric,
  settled_cost_usd numeric,
  unknown_estimate_event_count bigint,
  unknown_actual_event_count bigint,
  not_applicable_count bigint
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  WITH events AS (
    SELECT
      meta->>'provider' AS provider,
      meta->>'sku' AS sku,
      meta->>'operation' AS operation,
      unit,
      quantity,
      est_usd,
      meta->>'estimate_status' AS estimate_status,
      meta->>'billing_status' AS billing_status,
      COALESCE((meta->>'cache_hit')::boolean, false) AS cache_hit,
      CASE
        WHEN jsonb_typeof(meta->'actual_usd') = 'number'
          THEN (meta->>'actual_usd')::numeric
        ELSE NULL
      END AS actual_usd
    FROM public.lm_api_cost
    WHERE kind = 'provider_usage'
      AND ts >= p_period_start
      AND ts < p_period_end
      AND uid = p_tenant_id
  ),
  classified_events AS (
    SELECT
      *,
      CASE
        WHEN est_usd >= 0
          AND estimate_status IS DISTINCT FROM 'unavailable'
          AND (est_usd <> 0 OR estimate_status IN ('estimated', 'not_applicable') OR cache_hit)
          THEN true
        ELSE false
      END AS estimate_known,
      CASE
        WHEN billing_status = 'settled' AND actual_usd >= 0 THEN true
        WHEN billing_status = 'not_applicable' AND actual_usd = 0 THEN true
        ELSE false
      END AS actual_known
    FROM events
  )
  SELECT
    provider,
    sku,
    operation,
    unit,
    count(*)::bigint AS event_count,
    count(*) FILTER (WHERE unit = 'request' AND NOT cache_hit)::bigint AS request_count,
    count(*) FILTER (WHERE cache_hit)::bigint AS cache_hit_count,
    count(*) FILTER (WHERE NOT cache_hit)::bigint AS cache_miss_count,
    sum(quantity)::numeric AS provider_units,
    sum(est_usd) FILTER (WHERE estimate_known)::numeric AS estimated_cost_usd,
    sum(actual_usd) FILTER (
      WHERE billing_status = 'settled' AND actual_usd >= 0
    )::numeric AS settled_cost_usd,
    count(*) FILTER (WHERE NOT estimate_known)::bigint AS unknown_estimate_event_count,
    count(*) FILTER (WHERE NOT actual_known)::bigint AS unknown_actual_event_count,
    count(*) FILTER (
      WHERE billing_status = 'not_applicable' AND actual_usd = 0
    )::bigint AS not_applicable_count
  FROM classified_events
  GROUP BY provider, sku, operation, unit
  ORDER BY provider, sku, operation, unit;
$$;

REVOKE ALL ON FUNCTION public.lm_usage_cost_period_summary(timestamptz, timestamptz, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lm_usage_cost_period_summary(timestamptz, timestamptz, text)
  TO service_role;
