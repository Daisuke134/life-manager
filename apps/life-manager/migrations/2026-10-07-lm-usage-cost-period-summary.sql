-- COST-03: bounded, service-role-only cost summary by provider, SKU, operation, unit, loop, and owner.
CREATE OR REPLACE FUNCTION public.lm_usage_cost_period_summary(
  p_period_start timestamptz,
  p_period_end timestamptz,
  p_tenant_id text
) RETURNS TABLE (
  provider text,
  sku text,
  operation text,
  unit text,
  loop_id text,
  owner_id text,
  trace_status text,
  event_count bigint,
  request_count bigint,
  cache_hit_count bigint,
  cache_miss_count bigint,
  provider_units numeric,
  estimated_cost_usd numeric,
  settled_cost_usd numeric,
  unknown_estimate_event_count bigint,
  unknown_actual_event_count bigint,
  not_applicable_count bigint,
  linked_trace_event_count bigint,
  partial_trace_event_count bigint,
  unlinked_trace_event_count bigint,
  distinct_run_count bigint,
  distinct_occurrence_count bigint,
  distinct_release_count bigint,
  latest_trace jsonb
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  WITH raw_events AS (
    SELECT
      meta->>'provider' AS provider,
      meta->>'sku' AS sku,
      meta->>'operation' AS operation,
      unit,
      quantity,
      est_usd,
      meta->>'estimate_status' AS estimate_status,
      meta->>'billing_status' AS billing_status,
      meta->'runtime_trace' AS runtime_trace,
      ts,
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
  events AS (
    SELECT
      raw_events.*,
      COALESCE(CASE
        WHEN runtime_trace->>'loop_id' ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
          AND runtime_trace->>'loop_id' <> 'unknown'
          AND runtime_trace->>'loop_id' !~* '((token|secret|password|credential|api.?key)[[:space:]]*[=:]|auth\.json|sk-[A-Za-z0-9_-]{16,})'
          THEN runtime_trace->>'loop_id'
      END, 'unattributed') AS loop_id,
      COALESCE(CASE
        WHEN runtime_trace->>'owner_id' ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
          AND runtime_trace->>'owner_id' <> 'unknown'
          AND runtime_trace->>'owner_id' !~* '((token|secret|password|credential|api.?key)[[:space:]]*[=:]|auth\.json|sk-[A-Za-z0-9_-]{16,})'
          THEN runtime_trace->>'owner_id'
      END, 'unattributed') AS owner_id,
      CASE runtime_trace->>'status'
        WHEN 'linked' THEN 'linked'
        WHEN 'partial' THEN 'partial'
        ELSE 'unlinked'
      END AS trace_status,
      CASE
        WHEN runtime_trace->>'run_id' ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
          AND runtime_trace->>'run_id' <> 'unknown'
          AND runtime_trace->>'run_id' !~* '((token|secret|password|credential|api.?key)[[:space:]]*[=:]|auth\.json|sk-[A-Za-z0-9_-]{16,})'
          THEN runtime_trace->>'run_id'
      END AS run_id,
      CASE
        WHEN runtime_trace->>'occurrence_id' ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
          AND runtime_trace->>'occurrence_id' <> 'unknown'
          AND runtime_trace->>'occurrence_id' !~* '((token|secret|password|credential|api.?key)[[:space:]]*[=:]|auth\.json|sk-[A-Za-z0-9_-]{16,})'
          THEN runtime_trace->>'occurrence_id'
      END AS occurrence_id,
      CASE
        WHEN runtime_trace->>'release_sha' ~ '^(?:[a-f0-9]{40}|[a-f0-9]{64})$'
          THEN runtime_trace->>'release_sha'
      END AS release_sha
    FROM raw_events
  ),
  classified_events AS (
    SELECT
      *,
      CASE
        WHEN est_usd >= 0
          AND estimate_status IS DISTINCT FROM 'unavailable'
          AND (est_usd <> 0 OR estimate_status IN ('estimated', 'not_applicable'))
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
    loop_id,
    owner_id,
    CASE
      WHEN count(*) FILTER (WHERE trace_status = 'linked') = count(*) THEN 'linked'
      WHEN count(*) FILTER (WHERE trace_status = 'unlinked') = count(*) THEN 'unlinked'
      ELSE 'partial'
    END AS trace_status,
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
    )::bigint AS not_applicable_count,
    count(*) FILTER (WHERE trace_status = 'linked')::bigint AS linked_trace_event_count,
    count(*) FILTER (WHERE trace_status = 'partial')::bigint AS partial_trace_event_count,
    count(*) FILTER (WHERE trace_status = 'unlinked')::bigint AS unlinked_trace_event_count,
    count(DISTINCT run_id)::bigint AS distinct_run_count,
    count(DISTINCT occurrence_id)::bigint AS distinct_occurrence_count,
    count(DISTINCT release_sha)::bigint AS distinct_release_count,
    (
      jsonb_agg(jsonb_build_object(
        'run_id', run_id,
        'occurrence_id', occurrence_id,
        'release_sha', release_sha
      ) ORDER BY ts DESC)
      FILTER (WHERE run_id IS NOT NULL OR occurrence_id IS NOT NULL OR release_sha IS NOT NULL)
    )->0 AS latest_trace
  FROM classified_events
  GROUP BY provider, sku, operation, unit, loop_id, owner_id
  ORDER BY provider, sku, operation, unit, loop_id, owner_id;
$$;

REVOKE ALL ON FUNCTION public.lm_usage_cost_period_summary(timestamptz, timestamptz, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lm_usage_cost_period_summary(timestamptz, timestamptz, text)
  TO service_role;
