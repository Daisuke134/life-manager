#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATION="$ROOT_DIR/migrations/2026-10-22-lm-travel-write-receipts.sql"
UPDATE_MIGRATION="$ROOT_DIR/migrations/2026-10-23-lm-travel-update-receipts.sql"
TEST_TMP="$(mktemp -d /tmp/lm-travel-write-receipts-pg.XXXXXX)"
unset PGHOSTADDR PGSERVICE PGSERVICEFILE PGPASSWORD PGUSER PGPORT
export PGPASSFILE="$TEST_TMP/pgpass"
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
"${PSQL[@]}" -f "$UPDATE_MIGRATION" >/dev/null
"${PSQL[@]}" -f "$UPDATE_MIGRATION" >/dev/null
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
CREATE TEMP TABLE update_fixture AS SELECT calendar_write_receipt || jsonb_build_object(
  'request_id',repeat('5',64),'marker_request_id',repeat('1',64),'prior_request_fingerprint',repeat('4',64),
  'source_event_version',repeat('7',64),'request_fingerprint',repeat('6',64),
  'phase','dispatching','command','calendar.update','effect','unknown',
  'http_status',NULL,'error_class',NULL,'readback',NULL,'evidence_ref',NULL,'next_action','owned_readback') AS receipt
  FROM public.lm_travel_log WHERE uid='tenant-a' AND event_key='future' AND leg='go';
INSERT INTO public.lm_travel_log(uid,event_key,leg,calendar_write_receipt)
SELECT 'tenant-a','update-go','go',receipt FROM update_fixture;
INSERT INTO public.lm_travel_log(uid,event_key,leg,calendar_write_receipt)
SELECT 'tenant-a','update-return','return',receipt || '{"leg":"return"}' FROM update_fixture;
INSERT INTO public.lm_travel_log(uid,event_key,leg,calendar_write_receipt)
SELECT 'tenant-a','update-no-effect','go',receipt || jsonb_build_object('phase','response','effect','no_effect',
  'http_status',412,'error_class','provider_validation','next_action','none') FROM update_fixture;
DO $$ DECLARE n integer; invalid jsonb; BEGIN
  FOR invalid IN
    SELECT receipt - 'marker_request_id' FROM update_fixture
    UNION ALL SELECT receipt - 'prior_request_fingerprint' FROM update_fixture
    UNION ALL SELECT receipt || patch FROM update_fixture CROSS JOIN (VALUES
      ('{"marker_request_id":null}'::jsonb), ('{"prior_request_fingerprint":"not-a-hash"}'::jsonb),
      ('{"marker_request_id":5555555555555555555555555555555555555555555555555555555555555555}'::jsonb),
      ('{"marker_request_id":"5555555555555555555555555555555555555555555555555555555555555555"}'::jsonb),
      ('{"account_ref_hash":null}'::jsonb), ('{"provider_event_id":null}'::jsonb),
      ('{"phase":"claimed"}'::jsonb), ('{"effect":"created"}'::jsonb), ('{"effect":"updated"}'::jsonb),
      ('{"next_action":"release_claim"}'::jsonb), ('{"command":"calendar.delete"}'::jsonb),
      ('{"description":"private content"}'::jsonb)) AS patches(patch)
    UNION ALL SELECT receipt || jsonb_build_object('marker_request_id',repeat('1',64),
      'prior_request_fingerprint',repeat('4',64)) FROM receipt_fixture
  LOOP
    BEGIN
      INSERT INTO public.lm_travel_log(uid,event_key,leg,calendar_write_receipt) VALUES ('tenant-a','invalid-update','go',invalid);
      RAISE EXCEPTION 'invalid update receipt accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
  END LOOP;
  UPDATE public.lm_travel_log SET calendar_write_receipt=(SELECT receipt FROM update_fixture)
    WHERE uid='tenant-a' AND event_key='future' AND leg='go'
      AND calendar_write_receipt->>'request_id'=repeat('1',64)
      AND calendar_write_receipt->>'phase'='readback' AND calendar_write_receipt->>'effect'='verified'
      AND calendar_write_receipt->>'source_event_version'=repeat('3',64)
      AND calendar_write_receipt->>'request_fingerprint'=repeat('4',64)
      AND calendar_write_receipt->>'provider_event_id'='synthetic_event';
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>1 THEN RAISE EXCEPTION 'update dispatch CAS failed'; END IF;
  UPDATE public.lm_travel_log SET calendar_write_receipt=calendar_write_receipt || '{"phase":"response"}'
    WHERE uid='tenant-a' AND event_key='future' AND leg='go' AND calendar_write_receipt->>'request_id'=repeat('1',64);
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>0 THEN RAISE EXCEPTION 'late create callback changed update'; END IF;
  UPDATE public.lm_travel_log SET calendar_write_receipt=calendar_write_receipt || jsonb_build_object(
    'phase','readback','effect','verified','readback','exact_one','evidence_ref','calendar-event:' || repeat('c',64),'next_action','none')
    WHERE uid='tenant-a' AND event_key='future' AND leg='go' AND calendar_write_receipt->>'request_id'=repeat('5',64)
      AND calendar_write_receipt->>'phase'='dispatching' AND calendar_write_receipt->>'effect'='unknown';
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>1 THEN RAISE EXCEPTION 'owned update readback did not close operation'; END IF;
  UPDATE public.lm_travel_log SET calendar_write_receipt=calendar_write_receipt || '{"phase":"response","effect":"unknown","next_action":"owned_readback"}'
    WHERE uid='tenant-a' AND event_key='future' AND leg='go' AND calendar_write_receipt->>'request_id'=repeat('5',64)
      AND calendar_write_receipt->>'phase'='dispatching' AND calendar_write_receipt->>'effect'='unknown';
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>0 THEN RAISE EXCEPTION 'late update response overwrote readback'; END IF;
  IF (SELECT count(*) FROM public.lm_travel_log WHERE event_key='update-no-effect')<>1 THEN
    RAISE EXCEPTION 'update rejection released claim';
  END IF;
END $$;
SET ROLE service_role;
SELECT 1 FROM public.lm_travel_log LIMIT 1;
RESET ROLE;
SQL
printf '%s\n' 'lm-travel-write-receipts-postgres: PASS legacy=1 unique=1 receipt_shape=1 update_shape=1 scoped_cas=1 update_cas=1 late_callback=1 tenant=1 rls=1 acl=1 telegram=1 rerun=1'
