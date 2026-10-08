#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATION="$ROOT_DIR/migrations/2026-10-08-zzz-lm-message-channels.sql"
if [[ ! -f "$MIGRATION" ]]; then
  printf '%s\n' 'FAIL missing tenant-safe message-channel migration' >&2
  exit 1
fi

TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/lm-message-channels-pg.XXXXXX")"
PGDATA_DIR="$TEST_TMP/data"
PGSOCKET_DIR="$TEST_TMP/socket"
PGLOG="$TEST_TMP/postgres.log"
DB_NAME="lm_message_channels_test"
DB_MODE="local"
DOCKER_NAME="lm-message-channels-pg-$$"

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
  export PGPASSWORD="lm-message-channels-test-only"
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
CREATE TABLE public.lm_users (
  uid text PRIMARY KEY,
  telegram_chat_id text,
  name text,
  tg_onboard_stage text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO public.lm_users(uid, telegram_chat_id, name, tg_onboard_stage)
VALUES ('lm_tg_legacy', '123456789', 'Legacy', 'done');
INSERT INTO public.lm_users(uid, telegram_chat_id, name, tg_onboard_stage)
VALUES ('lm_tg_empty', '', 'Empty legacy value', 'done');
INSERT INTO public.lm_users(uid, telegram_chat_id, name, tg_onboard_stage)
VALUES
  ('lm_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', NULL, 'Web A', 'done'),
  ('lm_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', NULL, 'Web B', 'done'),
  ('lm_cccccccc-cccc-4ccc-8ccc-cccccccccccc', NULL, 'Web C', 'done'),
  ('lm_dddddddd-dddd-4ddd-8ddd-dddddddddddd', NULL, 'Web D', 'done');
SQL

"${PSQL[@]}" -f "$MIGRATION" >/dev/null
"${PSQL[@]}" -f "$MIGRATION" >/dev/null

[[ "$("${PSQL[@]}" -Atqc "SELECT owner_kind FROM public.lm_message_channels WHERE channel='telegram' AND sender_id='123456789';")" == "legacy" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT count(*) FROM public.lm_message_channels WHERE channel='telegram' AND sender_id='';")" == "0" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT public.create_lm_web_message_link('lm_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','telegram',repeat('a',64),now()+interval '10 minutes');")" == "t" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT public.consume_lm_web_message_link(repeat('a',64),'telegram','987654321');")" == "lm_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" ]]
[[ -z "$("${PSQL[@]}" -Atqc "SELECT public.consume_lm_web_message_link(repeat('a',64),'telegram','987654321');")" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT uid FROM public.lm_message_channels WHERE channel='telegram' AND sender_id='987654321';")" == "lm_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" ]]

[[ "$("${PSQL[@]}" -Atqc "SELECT public.create_lm_web_message_link('lm_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','telegram',repeat('b',64),now()+interval '10 minutes');")" == "t" ]]
[[ -z "$("${PSQL[@]}" -Atqc "SELECT public.consume_lm_web_message_link(repeat('b',64),'telegram','987654321');")" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT uid FROM public.lm_message_channels WHERE channel='telegram' AND sender_id='987654321';")" == "lm_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" ]]

[[ "$("${PSQL[@]}" -Atqc "SELECT public.create_lm_web_message_link('lm_cccccccc-cccc-4ccc-8ccc-cccccccccccc','telegram',repeat('c',64),now()+interval '10 minutes');")" == "t" ]]
[[ -z "$("${PSQL[@]}" -Atqc "SELECT public.consume_lm_web_message_link(repeat('c',64),'telegram','123456789');")" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT public.create_lm_web_message_link('lm_tg_legacy','telegram',repeat('d',64),now()+interval '10 minutes');")" == "f" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT public.create_lm_web_message_link('lm_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','telegram',repeat('e',64),now()-interval '1 second');")" == "f" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT public.create_lm_web_message_link('lm_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','telegram','bad-hash',now()+interval '10 minutes');")" == "f" ]]

if "${PSQL[@]}" -c "INSERT INTO public.lm_users(uid,telegram_chat_id) VALUES ('lm_tg_conflict','987654321');" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL legacy Telegram owner stole a Web-linked sender' >&2
  exit 1
fi
[[ "$("${PSQL[@]}" -Atqc "SELECT count(*) FROM public.lm_users WHERE uid='lm_tg_conflict';")" == "0" ]]
[[ "$("${PSQL[@]}" -Atqc "INSERT INTO public.lm_users(uid,telegram_chat_id) VALUES ('lm_tg_new','222222222') RETURNING uid;")" == "lm_tg_new" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT owner_kind FROM public.lm_message_channels WHERE channel='telegram' AND sender_id='222222222';")" == "legacy" ]]

if "${PSQL[@]}" -c "INSERT INTO public.lm_users(uid,telegram_chat_id) VALUES ('lm_dddddddd-dddd-4ddd-8ddd-dddddddddddd','333333333');" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL Web UID acquired a legacy Telegram identity' >&2
  exit 1
fi

SERVICE_ROLE_CREATE="$("${PSQL[@]}" -Atqc "SET ROLE service_role; SELECT public.create_lm_web_message_link('lm_dddddddd-dddd-4ddd-8ddd-dddddddddddd','telegram',repeat('f',64),now()+interval '10 minutes'); RESET ROLE;")"
[[ "$SERVICE_ROLE_CREATE" == "t" ]]
SERVICE_ROLE_CONSUME="$("${PSQL[@]}" -Atqc "SET ROLE service_role; SELECT public.consume_lm_web_message_link(repeat('f',64),'telegram','444444444'); RESET ROLE;")"
[[ "$SERVICE_ROLE_CONSUME" == "lm_dddddddd-dddd-4ddd-8ddd-dddddddddddd" ]]

[[ "$("${PSQL[@]}" -Atqc "SELECT relrowsecurity FROM pg_class WHERE oid='public.lm_message_channels'::regclass;")" == "t" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT relrowsecurity FROM pg_class WHERE oid='public.lm_web_message_link_tokens'::regclass;")" == "t" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT has_table_privilege('anon','public.lm_message_channels','SELECT')::text;")" == "false" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT has_table_privilege('authenticated','public.lm_message_channels','SELECT')::text;")" == "false" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT has_table_privilege('service_role','public.lm_message_channels','SELECT')::text;")" == "true" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT has_table_privilege('service_role','public.lm_message_channels','UPDATE')::text;")" == "false" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT has_function_privilege('anon','public.consume_lm_web_message_link(text,text,text)','EXECUTE')::text;")" == "false" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT has_function_privilege('service_role','public.consume_lm_web_message_link(text,text,text)','EXECUTE')::text;")" == "true" ]]

if "${PSQL[@]}" -c "UPDATE public.lm_message_channels SET owner_kind='legacy' WHERE sender_id='987654321';" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL message-channel identity update was accepted' >&2
  exit 1
fi
if "${PSQL[@]}" -c "TRUNCATE public.lm_web_message_link_tokens;" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL message-link token truncate was accepted' >&2
  exit 1
fi

printf '%s\n' 'PASS message-channel ownership, one-use linking, RLS, ACL, and immutable records'
