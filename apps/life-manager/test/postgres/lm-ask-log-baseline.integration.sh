#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATION="$ROOT_DIR/migrations/2026-06-23-lm-ask-log-baseline.sql"
if [[ ! -f "$MIGRATION" ]]; then
  printf '%s\n' 'FAIL missing source-owned lm_ask_log baseline migration' >&2
  exit 1
fi

TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/lm-ask-log-pg.XXXXXX")"
PGDATA_DIR="$TEST_TMP/data"
PGSOCKET_DIR="$TEST_TMP/socket"
PGLOG="$TEST_TMP/postgres.log"
DB_NAME="lm_ask_log_test"
DB_MODE="local"
DOCKER_NAME="lm-ask-log-pg-$$"

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
  export PGPASSWORD="lm-ask-log-test-only"
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

"${PSQL[@]}" >/dev/null <<'SQL'
DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE service_role NOLOGIN BYPASSRLS; EXCEPTION WHEN duplicate_object THEN ALTER ROLE service_role BYPASSRLS; END $$;
SQL

"${PSQL[@]}" -f "$MIGRATION" >/dev/null
"${PSQL[@]}" -f "$MIGRATION" >/dev/null

expect_query() {
  local label="$1" expected="$2" sql="$3" actual
  if ! actual="$("${PSQL[@]}" -Atqc "$sql")"; then
    printf 'FAIL %s query failed\n' "$label" >&2
    exit 1
  fi
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL %s expected=%s actual=%s\n' "$label" "$expected" "$actual" >&2
    exit 1
  fi
}

expect_query columns 15 "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_ask_log' AND column_name IN ('id','uid','event_id','asked_at','reply_token','answered_at','resolved_from','candidate_location','semantic_key','question_type','question_context','answer_value','answer_source','answer_provenance','telegram_chat_id');"
expect_query column_count 15 "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_ask_log';"
expect_query rls_enabled t "SELECT relrowsecurity FROM pg_class WHERE oid='public.lm_ask_log'::regclass;"
expect_query no_policies 0 "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='lm_ask_log';"
expect_query unique_constraints 1 "SELECT count(*) FROM pg_constraint WHERE conrelid='public.lm_ask_log'::regclass AND contype='u' AND conname='lm_ask_log_uid_event_id_key';"
expect_query indexes 2 "SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND tablename='lm_ask_log' AND indexname IN ('lm_ask_log_reply_token_idx','lm_ask_log_uid_semantic_key_key');"
expect_query service_crud t "SELECT has_table_privilege('service_role','public.lm_ask_log','SELECT') AND has_table_privilege('service_role','public.lm_ask_log','INSERT') AND has_table_privilege('service_role','public.lm_ask_log','UPDATE') AND has_table_privilege('service_role','public.lm_ask_log','DELETE');"
expect_query browser_denied t "SELECT NOT has_table_privilege('anon','public.lm_ask_log','SELECT') AND NOT has_table_privilege('authenticated','public.lm_ask_log','SELECT');"
expect_query asked_at_default t "SELECT column_default='now()' FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_ask_log' AND column_name='asked_at';"
expect_query json_defaults 2 "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_ask_log' AND column_name IN ('question_context','answer_provenance') AND is_nullable='NO' AND column_default LIKE '%{}%';"
expect_query sequence_acl t "SELECT has_sequence_privilege('service_role','public.lm_ask_log_id_seq','USAGE') AND has_sequence_privilege('service_role','public.lm_ask_log_id_seq','SELECT') AND NOT has_sequence_privilege('anon','public.lm_ask_log_id_seq','USAGE') AND NOT has_sequence_privilege('authenticated','public.lm_ask_log_id_seq','USAGE');"

if "${PSQL[@]}" -c "SET ROLE anon; SELECT id FROM public.lm_ask_log;" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL anon can query lm_ask_log' >&2
  exit 1
fi
if "${PSQL[@]}" -c "SET ROLE authenticated; SELECT id FROM public.lm_ask_log;" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL authenticated can query lm_ask_log' >&2
  exit 1
fi

"${PSQL[@]}" -c "SET ROLE service_role; INSERT INTO public.lm_ask_log(uid,event_id) VALUES ('uid-test','event-test'); RESET ROLE;" >/dev/null
[[ "$("${PSQL[@]}" -Atqc "SELECT count(*) FROM public.lm_ask_log WHERE uid='uid-test' AND event_id='event-test' AND question_context='{}'::jsonb AND answer_provenance='{}'::jsonb;")" == "1" ]]
if "${PSQL[@]}" -c "SET ROLE service_role; INSERT INTO public.lm_ask_log(uid,event_id) VALUES ('uid-test','event-test');" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL duplicate uid/event ask claim was accepted' >&2
  exit 1
fi

printf '%s\n' 'lm-ask-log-baseline-postgres: PASS migration_rerun=1 columns=15 unique_claim=1 semantic_index=1 rls=1 browser_roles=denied service_role_crud=1'
