#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATION="$ROOT_DIR/migrations/2026-10-22-lm-travel-write-receipts.sql"
TEST_TMP="$(mktemp -d /tmp/lm-travel-write-receipts-pg.XXXXXX)"
cleanup() {
  if [[ -f "$TEST_TMP/data/postmaster.pid" ]]; then pg_ctl -D "$TEST_TMP/data" -m immediate stop >/dev/null 2>&1 || true; fi
  rm -rf -- "$TEST_TMP"
}
trap cleanup EXIT INT TERM
mkdir -p "$TEST_TMP/socket"
initdb -D "$TEST_TMP/data" -A trust --no-locale >/dev/null
pg_ctl -D "$TEST_TMP/data" -l "$TEST_TMP/postgres.log" -o "-F -h '' -k $TEST_TMP/socket" start >/dev/null
createdb -h "$TEST_TMP/socket" receipt_test
PSQL=(psql -X -v ON_ERROR_STOP=1 -h "$TEST_TMP/socket" -d receipt_test)
"${PSQL[@]}" >/dev/null <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;
CREATE TABLE public.lm_ask_log(uid text, event_id text);
SQL
"${PSQL[@]}" -f "$ROOT_DIR/migrations/2026-06-24-ch1-atomic-dedup.sql" >/dev/null
"${PSQL[@]}" -f "$ROOT_DIR/migrations/2026-08-28-lm-travel-log-legs.sql" >/dev/null
"${PSQL[@]}" -f "$ROOT_DIR/migrations/2026-08-29-lm-travel-telegram-receipt.sql" >/dev/null
"${PSQL[@]}" >/dev/null <<'SQL'
INSERT INTO public.lm_travel_log(uid,event_key,leg) VALUES ('tenant-a','legacy','go'),('tenant-a','legacy','telegram-t5');
GRANT SELECT,INSERT,UPDATE,DELETE ON public.lm_travel_log TO service_role;
SQL
"${PSQL[@]}" -f "$MIGRATION" >/dev/null
"${PSQL[@]}" -f "$MIGRATION" >/dev/null
"${PSQL[@]}" >/dev/null <<'SQL'
CREATE TEMP TABLE receipt_fixture AS SELECT jsonb_build_object(
  'schema_version',1,'request_id',repeat('1',64),'source_event_hash',repeat('2',64),
  'source_event_version',repeat('3',64),'request_fingerprint',repeat('4',64),'account_ref_hash',NULL,
  'leg','go','phase','claimed','command','calendar.create','effect','unknown',
  'runtime_trace',jsonb_build_object('schema_version',1,'status','unlinked'),
  'http_status',NULL,'error_class','not_dispatched','provider_event_id',NULL,
  'readback',NULL,'evidence_ref',NULL,'retryable',false,'next_action','owned_readback') AS receipt;
INSERT INTO public.lm_travel_log(uid,event_key,leg,calendar_write_receipt)
SELECT 'tenant-a','future','go',receipt FROM receipt_fixture;
INSERT INTO public.lm_travel_log(uid,event_key,leg,calendar_write_receipt)
SELECT 'tenant-b','future','go',receipt FROM receipt_fixture;
INSERT INTO public.lm_travel_log(uid,event_key,leg,calendar_write_receipt)
SELECT 'tenant-a','no-effect','go',receipt || jsonb_build_object('phase','response','effect','no_effect',
  'error_class','account_binding_unavailable','next_action','release_claim') FROM receipt_fixture;
DO $$ DECLARE n integer; invalid jsonb; BEGIN
  IF (SELECT count(*) FROM public.lm_travel_log WHERE event_key='legacy' AND calendar_write_receipt IS NULL) <> 2 THEN
    RAISE EXCEPTION 'legacy rows changed';
  END IF;
  BEGIN
    INSERT INTO public.lm_travel_log(uid,event_key,leg) VALUES ('tenant-a','future','go');
    RAISE EXCEPTION 'duplicate claim accepted';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  FOR invalid IN SELECT receipt || patch FROM receipt_fixture CROSS JOIN (VALUES
    ('{"request_id":"not-a-hash"}'::jsonb), ('{"leg":"return"}'::jsonb),
    ('{"phase":"invented"}'::jsonb), ('{"location":"private address"}'::jsonb),
    ('{"source_event_version":null}'::jsonb), ('{"effect":"verified"}'::jsonb),
    ('{"phase":"dispatching"}'::jsonb), ('{"command":null}'::jsonb)) AS patches(patch)
  LOOP
    BEGIN
      INSERT INTO public.lm_travel_log(uid,event_key,leg,calendar_write_receipt) VALUES ('tenant-a','invalid','go',invalid);
      RAISE EXCEPTION 'invalid receipt accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
  END LOOP;
  UPDATE public.lm_travel_log SET calendar_write_receipt=calendar_write_receipt || '{"phase":"dispatching","account_ref_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
    WHERE uid='tenant-a' AND event_key='future' AND leg='go' AND calendar_write_receipt->>'request_id'=repeat('1',64);
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>1 THEN RAISE EXCEPTION 'scoped receipt latch failed'; END IF;
  IF (SELECT calendar_write_receipt->>'phase' FROM public.lm_travel_log WHERE uid='tenant-b' AND event_key='future') <> 'claimed' THEN
    RAISE EXCEPTION 'other tenant changed';
  END IF;
  UPDATE public.lm_travel_log SET calendar_write_receipt=calendar_write_receipt || '{"effect":"verified"}'
    WHERE uid='tenant-a' AND event_key='future' AND leg='go' AND calendar_write_receipt->>'request_id'=repeat('9',64);
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>0 THEN RAISE EXCEPTION 'wrong request changed receipt'; END IF;
  UPDATE public.lm_travel_log SET calendar_write_receipt=calendar_write_receipt || jsonb_build_object(
    'phase','response','effect','created','provider_event_id','synthetic_event','next_action','none')
    WHERE uid='tenant-a' AND event_key='future' AND leg='go' AND calendar_write_receipt->>'effect'='unknown';
  UPDATE public.lm_travel_log SET calendar_write_receipt=calendar_write_receipt || jsonb_build_object(
    'phase','readback','effect','verified','readback','exact_one','evidence_ref','calendar-event:' || repeat('b',64))
    WHERE uid='tenant-a' AND event_key='future' AND leg='go';
  UPDATE public.lm_travel_log SET calendar_write_receipt=calendar_write_receipt || '{"phase":"response","effect":"unknown"}'
    WHERE uid='tenant-a' AND event_key='future' AND leg='go' AND calendar_write_receipt->>'effect'='unknown';
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>0 THEN RAISE EXCEPTION 'late unknown overwrote verified'; END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='public.lm_travel_log'::regclass) THEN RAISE EXCEPTION 'RLS disabled'; END IF;
  IF (SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='lm_travel_log')<>0 THEN RAISE EXCEPTION 'RLS policy changed'; END IF;
  IF has_table_privilege('anon','public.lm_travel_log','UPDATE') OR has_table_privilege('authenticated','public.lm_travel_log','UPDATE') THEN
    RAISE EXCEPTION 'browser write grant added';
  END IF;
  IF NOT has_function_privilege('service_role','public.record_lm_travel_telegram_receipt(text,text,text,bigint)','EXECUTE') THEN
    RAISE EXCEPTION 'Telegram receipt grant changed';
  END IF;
END $$;
SET ROLE service_role;
SELECT 1 FROM public.lm_travel_log LIMIT 1;
RESET ROLE;
SQL
printf '%s\n' 'lm-travel-write-receipts-postgres: PASS legacy=1 unique=1 receipt_shape=1 scoped_cas=1 tenant=1 rls=1 acl=1 telegram=1 rerun=1'
