-- CLD02: future Calendar attempts join the existing atomic leg claim. Legacy claims stay NULL.
ALTER TABLE public.lm_travel_log ADD COLUMN IF NOT EXISTS calendar_write_receipt jsonb;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.lm_travel_log'::regclass
    AND conname='lm_travel_log_calendar_write_receipt_check') THEN
    ALTER TABLE public.lm_travel_log ADD CONSTRAINT lm_travel_log_calendar_write_receipt_check CHECK (
      calendar_write_receipt IS NULL OR (
        leg IN ('go','return') AND jsonb_typeof(calendar_write_receipt)='object'
        AND calendar_write_receipt ?& ARRAY['schema_version','request_id','source_event_hash','source_event_version',
          'request_fingerprint','account_ref_hash','leg','phase','command','effect','runtime_trace',
          'http_status','error_class','provider_event_id','readback','evidence_ref','retryable','next_action']
        AND calendar_write_receipt - ARRAY['schema_version','request_id','source_event_hash','source_event_version',
          'request_fingerprint','account_ref_hash','leg','phase','command','effect','runtime_trace',
          'http_status','error_class','provider_event_id','readback','evidence_ref','retryable','next_action']='{}'::jsonb
        AND coalesce(calendar_write_receipt->>'schema_version','')='1'
        AND coalesce(calendar_write_receipt->>'request_id','') ~ '^[a-f0-9]{64}$'
        AND coalesce(calendar_write_receipt->>'source_event_hash','') ~ '^[a-f0-9]{64}$'
        AND coalesce(calendar_write_receipt->>'source_event_version','') ~ '^[a-f0-9]{64}$'
        AND coalesce(calendar_write_receipt->>'request_fingerprint','') ~ '^[a-f0-9]{64}$'
        AND (calendar_write_receipt->>'account_ref_hash' IS NULL OR calendar_write_receipt->>'account_ref_hash' ~ '^[a-f0-9]{64}$')
        AND coalesce(calendar_write_receipt->>'leg','')=leg
        AND coalesce(calendar_write_receipt->>'phase','') IN ('claimed','dispatching','response','readback')
        AND coalesce(calendar_write_receipt->>'command','')='calendar.create'
        AND coalesce(calendar_write_receipt->>'effect','') IN ('unknown','created','verified','no_effect')
        AND jsonb_typeof(calendar_write_receipt->'runtime_trace')='object'
        AND (calendar_write_receipt->>'http_status' IS NULL OR calendar_write_receipt->>'http_status' ~ '^[1-5][0-9]{2}$')
        AND (calendar_write_receipt->>'error_class' IS NULL OR calendar_write_receipt->>'error_class' ~ '^[a-z_]{1,64}$')
        AND (calendar_write_receipt->>'provider_event_id' IS NULL OR (
          calendar_write_receipt->>'provider_event_id' ~ '^[A-Za-z0-9_-]+$'
          AND length(calendar_write_receipt->>'provider_event_id')<=1024))
        AND (calendar_write_receipt->>'readback' IS NULL OR calendar_write_receipt->>'readback' IN ('exact_one','absent','ambiguous','error'))
        AND (calendar_write_receipt->>'evidence_ref' IS NULL OR calendar_write_receipt->>'evidence_ref' ~ '^calendar-event:[a-f0-9]{64}$')
        AND coalesce(calendar_write_receipt->>'retryable','')='false'
        AND coalesce(calendar_write_receipt->>'next_action','') IN ('owned_readback','release_claim','none')
        AND (calendar_write_receipt->>'phase'<>'claimed' OR (calendar_write_receipt->>'effect'='unknown'
          AND calendar_write_receipt->>'account_ref_hash' IS NULL))
        AND (calendar_write_receipt->>'phase'<>'dispatching' OR (calendar_write_receipt->>'effect'='unknown'
          AND calendar_write_receipt->>'account_ref_hash' IS NOT NULL))
        AND (calendar_write_receipt->>'effect' NOT IN ('created','verified') OR (
          calendar_write_receipt->>'account_ref_hash' IS NOT NULL
          AND calendar_write_receipt->>'provider_event_id' IS NOT NULL))
        AND (calendar_write_receipt->>'effect'<>'verified' OR (
          calendar_write_receipt->>'phase'='readback' AND coalesce(calendar_write_receipt->>'readback','')='exact_one'
          AND calendar_write_receipt->>'evidence_ref' IS NOT NULL AND calendar_write_receipt->>'next_action'='none'))
        AND (calendar_write_receipt->>'effect'<>'no_effect' OR (
          calendar_write_receipt->>'phase'='response' AND calendar_write_receipt->>'error_class' IS NOT NULL))
      )
    );
  END IF;
END $$;
-- No claim rewrite, release, browser grant, RLS policy or leg/Telegram receipt change.
