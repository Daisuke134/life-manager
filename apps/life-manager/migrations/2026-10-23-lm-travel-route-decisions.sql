-- CLD03d2b: bind private route evidence to the existing atomic Calendar write.
BEGIN;
SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '5s';
ALTER TABLE public.lm_travel_log ADD COLUMN IF NOT EXISTS route_decision jsonb;
ALTER TABLE public.lm_travel_log DROP CONSTRAINT IF EXISTS lm_travel_log_route_decision_check;
ALTER TABLE public.lm_travel_log ADD CONSTRAINT lm_travel_log_route_decision_check CHECK (
  route_decision IS NULL OR (
    calendar_write_receipt IS NOT NULL
    AND calendar_write_receipt->>'command' IN ('calendar.create','calendar.update')
    AND jsonb_typeof(route_decision)='object'
    AND route_decision ?& ARRAY['schema_version','request_id','leg','source_event_version',
      'request_fingerprint','resolver_kind','resolved_from','destination_hmac','route_event_version']
    AND route_decision - ARRAY['schema_version','request_id','leg','source_event_version',
      'request_fingerprint','resolver_kind','resolved_from','destination_hmac','route_event_version']='{}'::jsonb
    AND route_decision->'schema_version'='1'::jsonb
    AND jsonb_typeof(route_decision->'request_id')='string'
    AND route_decision->>'request_id'=calendar_write_receipt->>'request_id'
    AND jsonb_typeof(route_decision->'leg')='string'
    AND route_decision->>'leg'=leg
    AND route_decision->>'leg'=calendar_write_receipt->>'leg'
    AND jsonb_typeof(route_decision->'source_event_version')='string'
    AND route_decision->>'source_event_version'=calendar_write_receipt->>'source_event_version'
    AND jsonb_typeof(route_decision->'request_fingerprint')='string'
    AND route_decision->>'request_fingerprint'=calendar_write_receipt->>'request_fingerprint'
    AND jsonb_typeof(route_decision->'resolver_kind')='string'
    AND route_decision->>'resolver_kind' IN ('not_called','filled','online','ask','error','unknown')
    AND (route_decision->'resolved_from'='null'::jsonb OR (
      jsonb_typeof(route_decision->'resolved_from')='string'
      AND route_decision->>'resolved_from' IN ('location_field','description','web_search')
      AND route_decision->>'resolver_kind'='filled'))
    AND jsonb_typeof(route_decision->'destination_hmac')='string'
    AND route_decision->>'destination_hmac' ~ '^[a-f0-9]{64}$'
    AND (route_decision->'route_event_version'='null'::jsonb OR (
      jsonb_typeof(route_decision->'route_event_version')='string'
      AND route_decision->>'route_event_version' ~ '^[a-f0-9]{64}$'))
  )
);
COMMIT;
-- Keep legacy NULLs, strict transport receipts, RLS, grants, unique keys and indexes.
