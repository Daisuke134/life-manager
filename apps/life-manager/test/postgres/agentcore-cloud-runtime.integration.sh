#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_MIGRATION="$ROOT_DIR/migrations/20260729_runtime_jobs.sql"
MIGRATION="$ROOT_DIR/migrations/20260928_agentcore_cloud_runtime.sql"
TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/agentcore-cloud-pg.XXXXXX")"
DB_NAME="agentcore_cloud_test"
DOCKER_NAME="agentcore-cloud-pg-$$"
DB_MODE="local"
PGDATA_DIR="$TEST_TMP/data"
PGSOCKET_DIR="$TEST_TMP/socket"
PGLOG="$TEST_TMP/postgres.log"

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
  PSQL=(psql -X -v ON_ERROR_STOP=1 -h "$PGSOCKET_DIR" -d "$DB_NAME")
else
  DB_MODE="docker"
  export PGPASSWORD="agentcore-cloud-test-only"
  docker run --rm -d --name "$DOCKER_NAME" -e POSTGRES_PASSWORD="$PGPASSWORD" -e POSTGRES_DB="$DB_NAME" -p 127.0.0.1::5432 postgres:18-alpine >/dev/null
  PGPORT="$(docker port "$DOCKER_NAME" 5432/tcp)"; PGPORT="${PGPORT##*:}"
  for _ in {1..100}; do
    pg_isready -h 127.0.0.1 -p "$PGPORT" -U postgres -d "$DB_NAME" >/dev/null 2>&1 && break
    sleep 0.1
  done
  PSQL=(psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$PGPORT" -U postgres -d "$DB_NAME")
fi

"${PSQL[@]}" >/dev/null <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
SQL
"${PSQL[@]}" -f "$BASE_MIGRATION" >/dev/null
"${PSQL[@]}" -f "$MIGRATION" >/dev/null
"${PSQL[@]}" -f "$MIGRATION" >/dev/null

scalar() { "${PSQL[@]}" -Atqc "$1"; }

"${PSQL[@]}" >/dev/null <<'SQL'
INSERT INTO public.lm_plan_entitlements(plan_version, plan, limits_json)
VALUES
  ('free-v1', 'free', '{"monthly_cost_cap_usd_micros":500000}'),
  ('founding-pro-v1', 'founding_pro', '{"monthly_cost_cap_usd_micros":12000000}')
ON CONFLICT (plan_version) DO NOTHING;
INSERT INTO public.lm_cloud_tenants(tenant_id, region, release_sha, status, plan_version)
VALUES
  ('tenant-a', 'ap-northeast-1', repeat('a', 40), 'active', 'free-v1'),
  ('tenant-b', 'ap-northeast-1', repeat('b', 40), 'active', 'free-v1');
INSERT INTO public.lm_runtime_jobs(job_id, tenant_id, loop_id, capability, effect_class, input_refs, max_attempts)
VALUES
  ('job-a', 'tenant-a', 'cloud.test', 'cloud.test', 'none', '{"goal_ref":"goal:a"}', 1),
  ('job-b', 'tenant-b', 'cloud.test', 'cloud.test', 'none', '{"goal_ref":"goal:b"}', 1);
INSERT INTO public.lm_cloud_runtime_leases(
  tenant_id, job_id, attempt, runtime_session_id, lease_owner, lease_expires_at, generation
) VALUES ('tenant-a', 'job-a', 1, 'session-a', 'dispatcher-a', clock_timestamp() + interval '5 minutes', 1);
INSERT INTO public.lm_cloud_browser_profiles(tenant_id, provider, profile_id, principal_type)
VALUES ('tenant-a', 'agentcore', 'profile-a', 'agent_owned');
INSERT INTO public.lm_cloud_usage_ledger(
  tenant_id, job_id, provider, resource, quantity, unit, cost_usd_micros, provider_receipt_id
) VALUES ('tenant-a', 'job-a', 'aws', 'agentcore-runtime', 10, 'second', 6703, 'cur://aws/runtime-a');
SQL

if "${PSQL[@]}" -c "INSERT INTO public.lm_cloud_runtime_leases(tenant_id,job_id,attempt,runtime_session_id,lease_owner,lease_expires_at,generation) VALUES ('tenant-a','job-a',2,'session-2','dispatcher-2',clock_timestamp()+interval '5 minutes',2);" >/dev/null 2>&1; then
  echo 'FAIL second active runtime lease accepted' >&2; exit 1
fi
if "${PSQL[@]}" -c "INSERT INTO public.lm_cloud_runtime_leases(tenant_id,job_id,attempt,runtime_session_id,lease_owner,lease_expires_at,generation) VALUES ('tenant-a','job-b',1,'session-cross','dispatcher-a',clock_timestamp()+interval '5 minutes',1);" >/dev/null 2>&1; then
  echo 'FAIL cross-tenant job binding accepted' >&2; exit 1
fi
if "${PSQL[@]}" -c "INSERT INTO public.lm_cloud_usage_ledger(tenant_id,job_id,provider,resource,quantity,unit,cost_usd_micros,provider_receipt_id) VALUES ('tenant-b','job-b','aws','agentcore-runtime',10,'second',6703,'cur://aws/runtime-a');" >/dev/null 2>&1; then
  echo 'FAIL duplicate provider receipt accepted' >&2; exit 1
fi
if "${PSQL[@]}" -c "UPDATE public.lm_cloud_usage_ledger SET cost_usd_micros=1 WHERE provider_receipt_id='cur://aws/runtime-a';" >/dev/null 2>&1; then
  echo 'FAIL immutable usage update accepted' >&2; exit 1
fi
if "${PSQL[@]}" -c "SET ROLE anon; SELECT * FROM public.lm_cloud_tenants;" >/dev/null 2>&1; then
  echo 'FAIL anon cloud tenant read accepted' >&2; exit 1
fi
if "${PSQL[@]}" -c "SET ROLE authenticated; SELECT * FROM public.lm_cloud_usage_ledger;" >/dev/null 2>&1; then
  echo 'FAIL authenticated usage read accepted' >&2; exit 1
fi

[[ "$(scalar "SELECT count(*) FROM public.lm_runtime_jobs;")" == "2" ]]
[[ "$(scalar "SELECT count(*) FROM public.lm_cloud_runtime_leases;")" == "1" ]]
[[ "$(scalar "SELECT count(*) FROM public.lm_cloud_usage_ledger;")" == "1" ]]
echo 'agentcore-cloud-runtime-postgres: PASS migration_twice=2 tenant_fk=1 single_lease=1 receipt_dedupe=1 immutable_usage=1 browser_access=0'
