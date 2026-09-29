#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS="$ROOT_DIR/migrations"
PREREQUISITES=(
  "20260729_runtime_jobs.sql"
  "2026-07-28-lm-browser-jobs.sql"
  "2026-07-28-lm-browser-jobs-principal-kind.sql"
  "2026-07-29-lm-browser-job-auth-trace.sql"
)
RELEASE_MIGRATIONS=(
  "20260928_agentcore_cloud_runtime.sql"
  "2026-09-29-lm-agent-identity-refs.sql"
  "2026-09-29-lm-browser-no-human.sql"
  "2026-09-29-lm-cloud-cost-reservations.sql"
  "2026-09-29-lm-cloud-free-onboarding.sql"
)

TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/lm-cloud-release-pg.XXXXXX")"
DB_NAME="lm_cloud_release_test"
PGDATA_DIR="$TEST_TMP/data"
PGSOCKET_DIR="$TEST_TMP/socket"
PGLOG="$TEST_TMP/postgres.log"

cleanup() {
  if [[ -f "$PGDATA_DIR/postmaster.pid" ]]; then
    pg_ctl -D "$PGDATA_DIR" -m immediate stop >/dev/null 2>&1 || true
  fi
  rm -rf -- "$TEST_TMP"
}
trap cleanup EXIT INT TERM

mkdir -p "$PGSOCKET_DIR"
initdb -D "$PGDATA_DIR" -A trust --no-locale >/dev/null
pg_ctl -D "$PGDATA_DIR" -l "$PGLOG" -o "-F -h '' -k $PGSOCKET_DIR" start >/dev/null
createdb -h "$PGSOCKET_DIR" "$DB_NAME"
PSQL=(psql -X -v ON_ERROR_STOP=1 -h "$PGSOCKET_DIR" -d "$DB_NAME")

"${PSQL[@]}" >/dev/null <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
SQL

for migration in "${PREREQUISITES[@]}"; do
  "${PSQL[@]}" -f "$MIGRATIONS/$migration" >/dev/null
done

apply_release() {
  local migration
  for migration in "${RELEASE_MIGRATIONS[@]}"; do
    "${PSQL[@]}" -f "$MIGRATIONS/$migration" >/dev/null
  done
}

schema_sha() {
  pg_dump -h "$PGSOCKET_DIR" -d "$DB_NAME" --schema-only --no-owner --no-privileges \
    | shasum -a 256 | awk '{print $1}'
}

scalar() { "${PSQL[@]}" -Atqc "$1"; }

apply_release
FIRST_SCHEMA_SHA="$(schema_sha)"
apply_release
SECOND_SCHEMA_SHA="$(schema_sha)"
[[ "$FIRST_SCHEMA_SHA" == "$SECOND_SCHEMA_SHA" ]]

[[ "$(scalar "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('lm_plan_entitlements','lm_cloud_tenants','lm_cloud_runtime_leases','lm_cloud_browser_profiles','lm_cloud_usage_ledger','lm_agent_identity_refs','lm_cloud_cost_reservations');")" == "7" ]]
[[ "$(scalar "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='lm_cloud_tenants' AND column_name='first_verified_result_at';")" == "1" ]]
[[ "$(scalar "SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname IN ('reserve_lm_cloud_cost','settle_lm_cloud_cost','mark_lm_cloud_first_verified_result');")" == "3" ]]
[[ "$(scalar "SELECT count(*) FROM pg_constraint WHERE conrelid='public.lm_browser_jobs'::regclass AND conname='lm_browser_jobs_status_no_human_check' AND pg_get_constraintdef(oid) LIKE '%not_applicable%' AND pg_get_constraintdef(oid) NOT LIKE '%handoff_required%';")" == "1" ]]
[[ "$(scalar "SELECT count(*) FROM public.lm_plan_entitlements WHERE plan_version IN ('free-v1','founding-pro-v1');")" == "2" ]]

MANIFEST_SHA="$({ for migration in "${RELEASE_MIGRATIONS[@]}"; do printf '%s\0' "$migration"; cat "$MIGRATIONS/$migration"; done; } | shasum -a 256 | awk '{print $1}')"
printf '%s\n' "cloud-release-migrations-postgres: PASS ordered=5 replay=2 schema_sha=$SECOND_SCHEMA_SHA manifest_sha=$MANIFEST_SHA tables=7 no_human=1 plans=2"
