#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LEGACY_MIGRATION="$ROOT_DIR/migrations/2026-07-18-lm-api-cost.sql"
APPEND_ONLY_MIGRATION="$ROOT_DIR/migrations/2026-10-06-lm-api-cost-append-only.sql"
FUNNEL_MIGRATION="$ROOT_DIR/migrations/2026-10-08-zz-lm-web-funnel-events.sql"
for migration in "$LEGACY_MIGRATION" "$APPEND_ONLY_MIGRATION" "$FUNNEL_MIGRATION"; do
  if [[ ! -f "$migration" ]]; then
    printf 'missing migration: %s\n' "$migration" >&2
    exit 1
  fi
done
TEST_TMP="$(mktemp -d "/tmp/lm-api-cost-pg.XXXXXX")"
PGDATA_DIR="$TEST_TMP/data"
PGSOCKET_DIR="$TEST_TMP/socket"
PGLOG="$TEST_TMP/postgres.log"
DB_NAME="lm_api_cost_append_only_test"
DB_MODE="local"
DOCKER_NAME="lm-api-cost-append-only-pg-$$"

cleanup() {
  if [[ "$DB_MODE" == "docker" ]]; then
    docker stop "$DOCKER_NAME" >/dev/null 2>&1 || true
  elif [[ -f "$PGDATA_DIR/postmaster.pid" ]]; then
    pg_ctl -D "$PGDATA_DIR" -m immediate stop >/dev/null 2>&1 || true
  fi
  rm -rf -- "$TEST_TMP"
}
trap cleanup EXIT INT TERM

if command -v postgres >/dev/null 2>&1; then
  mkdir -p "$PGSOCKET_DIR"
  initdb -D "$PGDATA_DIR" -A trust --no-locale >/dev/null
  pg_ctl -D "$PGDATA_DIR" -l "$PGLOG" -o "-F -h '' -k $PGSOCKET_DIR" start >/dev/null
  createdb -h "$PGSOCKET_DIR" "$DB_NAME"
  PSQL=(psql -X -q -v ON_ERROR_STOP=1 -h "$PGSOCKET_DIR" -d "$DB_NAME")
else
  DB_MODE="docker"
  export PGPASSWORD="lm-api-cost-append-only-test"
  docker run --rm -d --name "$DOCKER_NAME" \
    -e POSTGRES_PASSWORD="$PGPASSWORD" -e POSTGRES_DB="$DB_NAME" \
    -p 127.0.0.1::5432 postgres:18-alpine >/dev/null
  MAPPED="$(docker port "$DOCKER_NAME" 5432/tcp)"
  PGPORT="${MAPPED##*:}"
  for _ in {1..100}; do
    pg_isready -h 127.0.0.1 -p "$PGPORT" -U postgres -d "$DB_NAME" >/dev/null 2>&1 && break
    sleep 0.1
  done
  pg_isready -h 127.0.0.1 -p "$PGPORT" -U postgres -d "$DB_NAME" >/dev/null
PSQL=(psql -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$PGPORT" -U postgres -d "$DB_NAME")
fi

scalar() {
  "${PSQL[@]}" -Atc "$1"
}

assert_scalar() {
  local label="$1" expected="$2" query="$3" actual
  if ! actual="$(scalar "$query")"; then
    printf 'FAIL: %s query failed\n' "$label" >&2
    return 1
  fi
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL: %s expected=%s actual=%s\n' "$label" "$expected" "$actual" >&2
    return 1
  fi
}

expect_error_contains() {
  local label="$1" expected="$2" sql="$3" output=""
  if output="$("${PSQL[@]}" -c "$sql" 2>&1)"; then
    printf 'FAIL: %s unexpectedly succeeded\n' "$label" >&2
    return 1
  fi
  if [[ "$output" != *"$expected"* ]]; then
    printf 'FAIL: %s failed for the wrong reason: %s\n' "$label" "$output" >&2
    return 1
  fi
}

"${PSQL[@]}" >/dev/null <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
SQL
"${PSQL[@]}" -f "$LEGACY_MIGRATION" >/dev/null
"${PSQL[@]}" >/dev/null <<'SQL'
GRANT ALL PRIVILEGES ON TABLE public.lm_api_cost TO PUBLIC, anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON SEQUENCE public.lm_api_cost_id_seq TO PUBLIC, anon, authenticated, service_role;
SET ROLE service_role;
INSERT INTO public.lm_api_cost(uid, kind, quantity, unit, est_usd, meta)
VALUES ('tenant-a', 'before_append_only', 1, 'request', 0.01, '{"evidence":"original"}');
RESET ROLE;
SQL

assert_scalar "legacy ALL grants allow service_role mutation" t "SELECT has_table_privilege('service_role', 'public.lm_api_cost', 'UPDATE') AND has_table_privilege('service_role', 'public.lm_api_cost', 'DELETE') AND has_table_privilege('service_role', 'public.lm_api_cost', 'TRUNCATE');"
BASELINE_UPDATE="$(scalar "SET ROLE service_role; UPDATE public.lm_api_cost SET kind = 'baseline_mutated' WHERE uid = 'tenant-a' RETURNING kind;")"
[[ "$BASELINE_UPDATE" == "baseline_mutated" ]]
"${PSQL[@]}" -c "UPDATE public.lm_api_cost SET kind = 'before_append_only' WHERE uid = 'tenant-a';" >/dev/null

"${PSQL[@]}" -f "$APPEND_ONLY_MIGRATION" >/dev/null
"${PSQL[@]}" -f "$APPEND_ONLY_MIGRATION" >/dev/null
"${PSQL[@]}" -f "$FUNNEL_MIGRATION" >/dev/null
"${PSQL[@]}" -f "$FUNNEL_MIGRATION" >/dev/null

assert_scalar "service_role SELECT/INSERT only" t "SELECT has_table_privilege('service_role', 'public.lm_api_cost', 'SELECT') AND has_table_privilege('service_role', 'public.lm_api_cost', 'INSERT') AND NOT has_table_privilege('service_role', 'public.lm_api_cost', 'UPDATE') AND NOT has_table_privilege('service_role', 'public.lm_api_cost', 'DELETE') AND NOT has_table_privilege('service_role', 'public.lm_api_cost', 'TRUNCATE') AND NOT has_table_privilege('service_role', 'public.lm_api_cost', 'REFERENCES') AND NOT has_table_privilege('service_role', 'public.lm_api_cost', 'TRIGGER');"
assert_scalar "service_role identity sequence grants" t "SELECT has_sequence_privilege('service_role', 'public.lm_api_cost_id_seq', 'USAGE') AND has_sequence_privilege('service_role', 'public.lm_api_cost_id_seq', 'SELECT') AND NOT has_sequence_privilege('service_role', 'public.lm_api_cost_id_seq', 'UPDATE');"
assert_scalar "append-only row and statement triggers" 2 "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'public.lm_api_cost'::regclass AND NOT tgisinternal AND tgname IN ('lm_api_cost_guard', 'lm_api_cost_truncate_guard');"
assert_scalar "guard is invoker with pinned search_path" t "SELECT NOT prosecdef AND proconfig @> ARRAY['search_path=pg_catalog']::text[] FROM pg_proc WHERE oid = 'public.lm_api_cost_guard()'::regprocedure;"
assert_scalar "row-level security enabled" t "SELECT relrowsecurity FROM pg_class WHERE oid = 'public.lm_api_cost'::regclass;"

for browser_role in anon authenticated; do
  assert_scalar "$browser_role has no table privileges" t "SELECT NOT (has_table_privilege('$browser_role', 'public.lm_api_cost', 'SELECT') OR has_table_privilege('$browser_role', 'public.lm_api_cost', 'INSERT') OR has_table_privilege('$browser_role', 'public.lm_api_cost', 'UPDATE') OR has_table_privilege('$browser_role', 'public.lm_api_cost', 'DELETE') OR has_table_privilege('$browser_role', 'public.lm_api_cost', 'TRUNCATE') OR has_table_privilege('$browser_role', 'public.lm_api_cost', 'REFERENCES') OR has_table_privilege('$browser_role', 'public.lm_api_cost', 'TRIGGER'));"
  assert_scalar "$browser_role has no sequence privileges" t "SELECT NOT (has_sequence_privilege('$browser_role', 'public.lm_api_cost_id_seq', 'USAGE') OR has_sequence_privilege('$browser_role', 'public.lm_api_cost_id_seq', 'SELECT') OR has_sequence_privilege('$browser_role', 'public.lm_api_cost_id_seq', 'UPDATE'));"
  expect_error_contains "$browser_role SELECT" "permission denied for table lm_api_cost" "SET ROLE $browser_role; SELECT * FROM public.lm_api_cost;"
  expect_error_contains "$browser_role INSERT" "permission denied for table lm_api_cost" "SET ROLE $browser_role; INSERT INTO public.lm_api_cost(uid, kind) VALUES ('browser', 'forbidden');"
done

assert_scalar "service_role reads original row" 1 "SET ROLE service_role; SELECT count(*) FROM public.lm_api_cost WHERE uid = 'tenant-a' AND kind = 'before_append_only';"
SERVICE_INSERT="$(scalar "SET ROLE service_role; INSERT INTO public.lm_api_cost(uid, kind, quantity, unit, est_usd, meta) VALUES ('tenant-b', 'after_append_only', 1, 'request', 0.02, '{}'::jsonb) RETURNING uid;")"
[[ "$SERVICE_INSERT" == "tenant-b" ]]
assert_scalar "service_role reads both rows" 2 "SET ROLE service_role; SELECT count(*) FROM public.lm_api_cost;"

expect_error_contains "service_role UPDATE" "permission denied for table lm_api_cost" "SET ROLE service_role; UPDATE public.lm_api_cost SET kind = 'service_mutated' WHERE uid = 'tenant-a';"
expect_error_contains "service_role DELETE" "permission denied for table lm_api_cost" "SET ROLE service_role; DELETE FROM public.lm_api_cost WHERE uid = 'tenant-a';"
expect_error_contains "service_role TRUNCATE" "permission denied for table lm_api_cost" "SET ROLE service_role; TRUNCATE public.lm_api_cost;"

expect_error_contains "table owner UPDATE trigger" "lm_api_cost is append-only" "UPDATE public.lm_api_cost SET kind = 'owner_mutated' WHERE uid = 'tenant-a';"
expect_error_contains "table owner DELETE trigger" "lm_api_cost is append-only" "DELETE FROM public.lm_api_cost WHERE uid = 'tenant-a';"
expect_error_contains "table owner TRUNCATE trigger" "lm_api_cost is append-only" "TRUNCATE public.lm_api_cost;"

assert_scalar "original and service_role rows remain unchanged" t "SELECT count(*) = 2 AND count(*) FILTER (WHERE uid = 'tenant-a' AND kind = 'before_append_only' AND meta = '{\"evidence\":\"original\"}'::jsonb) = 1 AND count(*) FILTER (WHERE uid = 'tenant-b' AND kind = 'after_append_only') = 1 FROM public.lm_api_cost;"

assert_scalar "Web funnel service_role SELECT/INSERT only" t "SELECT has_table_privilege('service_role', 'public.lm_web_funnel_events', 'SELECT') AND has_table_privilege('service_role', 'public.lm_web_funnel_events', 'INSERT') AND NOT has_table_privilege('service_role', 'public.lm_web_funnel_events', 'UPDATE') AND NOT has_table_privilege('service_role', 'public.lm_web_funnel_events', 'DELETE') AND NOT has_table_privilege('service_role', 'public.lm_web_funnel_events', 'TRUNCATE') AND NOT has_table_privilege('service_role', 'public.lm_web_funnel_events', 'REFERENCES') AND NOT has_table_privilege('service_role', 'public.lm_web_funnel_events', 'TRIGGER');"
assert_scalar "Web funnel RLS and append-only triggers" t "SELECT relrowsecurity AND (SELECT count(*) FROM pg_trigger WHERE tgrelid = 'public.lm_web_funnel_events'::regclass AND NOT tgisinternal AND tgname IN ('lm_web_funnel_events_guard', 'lm_web_funnel_events_truncate_guard')) = 2 FROM pg_class WHERE oid = 'public.lm_web_funnel_events'::regclass;"
for browser_role in anon authenticated; do
  assert_scalar "$browser_role has no Web funnel privileges" t "SELECT NOT (has_table_privilege('$browser_role', 'public.lm_web_funnel_events', 'SELECT') OR has_table_privilege('$browser_role', 'public.lm_web_funnel_events', 'INSERT') OR has_table_privilege('$browser_role', 'public.lm_web_funnel_events', 'UPDATE') OR has_table_privilege('$browser_role', 'public.lm_web_funnel_events', 'DELETE') OR has_table_privilege('$browser_role', 'public.lm_web_funnel_events', 'TRUNCATE'));"
  expect_error_contains "$browser_role Web funnel SELECT" "permission denied for table lm_web_funnel_events" "SET ROLE $browser_role; SELECT * FROM public.lm_web_funnel_events;"
  expect_error_contains "$browser_role Web funnel INSERT" "permission denied for table lm_web_funnel_events" "SET ROLE $browser_role; INSERT INTO public.lm_web_funnel_events(event_id, event_name) VALUES ('browser', 'landing_view');"
done
SERVICE_FUNNEL_INSERT="$(scalar "SET ROLE service_role; INSERT INTO public.lm_web_funnel_events(event_id, event_name, attribution) VALUES ('view-test', 'landing_view', '{\"utm_source\":\"test\"}'::jsonb) RETURNING event_id;")"
[[ "$SERVICE_FUNNEL_INSERT" == "view-test" ]]
assert_scalar "service_role funnel event readback" 1 "SET ROLE service_role; SELECT count(*) FROM public.lm_web_funnel_events WHERE event_id = 'view-test' AND event_name = 'landing_view';"
expect_error_contains "service_role Web funnel UPDATE" "permission denied for table lm_web_funnel_events" "SET ROLE service_role; UPDATE public.lm_web_funnel_events SET event_name = 'refund_recorded' WHERE event_id = 'view-test';"
expect_error_contains "table owner Web funnel UPDATE trigger" "lm_web_funnel_events is append-only" "UPDATE public.lm_web_funnel_events SET event_name = 'refund_recorded' WHERE event_id = 'view-test';"
expect_error_contains "table owner Web funnel DELETE trigger" "lm_web_funnel_events is append-only" "DELETE FROM public.lm_web_funnel_events WHERE event_id = 'view-test';"
expect_error_contains "table owner Web funnel TRUNCATE trigger" "lm_web_funnel_events is append-only" "TRUNCATE public.lm_web_funnel_events;"

printf '%s\n' 'lm-api-cost-append-only-postgres: PASS provider_costs=append_only web_funnel=append_only service_role_select_insert=1 browser_roles=denied migration_rerun=1'
