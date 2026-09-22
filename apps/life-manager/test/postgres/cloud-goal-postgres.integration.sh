#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_MIGRATION="$ROOT_DIR/migrations/20260729_runtime_jobs.sql"
GOAL_MIGRATION="$ROOT_DIR/migrations/2026-09-22-lm-goal-context-portfolios.sql"
TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/cloud-goal-pg.XXXXXX")"
PGDATA_DIR="$TEST_TMP/data"
PGSOCKET_DIR="$TEST_TMP/socket"
PGLOG="$TEST_TMP/postgres.log"
DB_NAME="cloud_goal_test"
DB_MODE="local"
DOCKER_NAME="cloud-goal-pg-$$"

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
  export PGHOST="$PGSOCKET_DIR" PGDATABASE="$DB_NAME" PGUSER="$(id -un)"
  PSQL=(psql -X -v ON_ERROR_STOP=1)
else
  DB_MODE="docker"
  export PGPASSWORD="cloud-goal-test-only"
  docker run --rm -d --name "$DOCKER_NAME" -e POSTGRES_PASSWORD="$PGPASSWORD" \
    -e POSTGRES_DB="$DB_NAME" -p 127.0.0.1::5432 postgres:18-alpine >/dev/null
  MAPPED="$(docker port "$DOCKER_NAME" 5432/tcp)"
  export PGHOST="127.0.0.1" PGPORT="${MAPPED##*:}" PGDATABASE="$DB_NAME" PGUSER="postgres"
  for _ in {1..100}; do
    pg_isready >/dev/null 2>&1 && break
    sleep 0.1
  done
  pg_isready >/dev/null
  PSQL=(psql -X -v ON_ERROR_STOP=1)
fi

"${PSQL[@]}" >/dev/null <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN NOINHERIT;
CREATE TABLE public.lm_users(
  uid text PRIMARY KEY,
  telegram_chat_id text NOT NULL,
  paid boolean NOT NULL DEFAULT false
);
INSERT INTO public.lm_users(uid, telegram_chat_id, paid) VALUES
  ('tenant-a', '101', true),
  ('tenant-b', '202', true);
SQL

"${PSQL[@]}" -f "$RUNTIME_MIGRATION" >/dev/null
"${PSQL[@]}" -f "$GOAL_MIGRATION" >/dev/null

export START_OUTPUT="$TEST_TMP/start.json"
export NODE_PATH="$ROOT_DIR/node_modules"

cd "$ROOT_DIR"
node <<'NODE'
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { Pool } = require("pg");
const { createCloudGoalStore } = require("./lib/cloud-goal-store.js");
const { startCloudGoalSlice } = require("./lib/cloud-goal-slice.js");
const { enqueueJob } = require("./lib/runtime-job-store.js");

function candidate() {
  return {
    goal_id: "financial-continuity",
    statement: "Increase verified financial surplus within delegated boundaries",
    expected_outcome: "One attributable settled revenue receipt",
    confidence: 0.8,
    evidence_refs: ["policy://life-manager/J4"],
    cost_budget: { currency: "USD", minor_units: "0" },
    risk_budget: "low",
    dependencies: [],
    expires_at: null,
    success_receipt: null,
    status: "active",
  };
}

(async () => {
  const pool = new Pool();
  const query = pool.query.bind(pool);
  const deps = {
    resolveSession: async (session) => session === "session-a" ? { uid: "tenant-a", chatId: "101" } : null,
    store: createCloudGoalStore({ query }),
    generateGoalPortfolio: async () => ({ goals: [candidate()] }),
    enqueueJob: (input) => enqueueJob(input, { query }),
  };
  const results = await Promise.all([
    startCloudGoalSlice({ session: "session-a", nowMs: Date.parse("2026-09-22T12:00:00.000Z") }, deps),
    startCloudGoalSlice({ session: "session-a", nowMs: Date.parse("2026-09-22T12:00:00.000Z") }, deps),
  ]);
  assert.deepEqual(results.map((value) => value.created).sort(), [false, true]);
  assert.equal(results[0].job_ref, results[1].job_ref);
  fs.writeFileSync(process.env.START_OUTPUT, JSON.stringify({ ...results[0], created: false }));
  await pool.end();
})().catch((error) => { console.error(error); process.exitCode = 1; });
NODE

# The initiating Node process is gone here. A new process and store must recover the
# durable projection without the original HTTP response or browser state.
node <<'NODE'
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { Pool } = require("pg");
const { createCloudGoalStore } = require("./lib/cloud-goal-store.js");
const { readCloudGoalSlice } = require("./lib/cloud-goal-slice.js");

(async () => {
  const expected = JSON.parse(fs.readFileSync(process.env.START_OUTPUT, "utf8"));
  const pool = new Pool();
  const store = createCloudGoalStore({ query: pool.query.bind(pool) });
  const sessions = new Map([
    ["session-a", { uid: "tenant-a", chatId: "101" }],
    ["wrong-chat", { uid: "tenant-a", chatId: "999" }],
    ["session-b", { uid: "tenant-b", chatId: "202" }],
  ]);
  const deps = { resolveSession: async (session) => sessions.get(session) || null, store };
  const recovered = await readCloudGoalSlice({ session: "session-a" }, deps);
  assert.deepEqual(recovered, expected);
  for (const session of ["wrong-chat", "session-b"]) {
    const foreign = await readCloudGoalSlice({ session }, deps);
    assert.equal(foreign.status, "not_started");
    assert.equal(foreign.goal_ref, null);
    assert.equal(foreign.job_ref, null);
  }
  assert.doesNotMatch(JSON.stringify(recovered), /financial surplus|settled revenue|101|credential|provider_payload/i);
  const counts = (await pool.query(`
    SELECT
      (SELECT count(*)::integer FROM public.lm_goal_contexts) AS contexts,
      (SELECT count(*)::integer FROM public.lm_goal_portfolios) AS portfolios,
      (SELECT count(*)::integer FROM public.lm_runtime_jobs WHERE loop_id='life-manager.manager') AS jobs
  `)).rows[0];
  assert.deepEqual(counts, { contexts: 1, portfolios: 1, jobs: 1 });
  await pool.end();
})().catch((error) => { console.error(error); process.exitCode = 1; });
NODE

if "${PSQL[@]}" -c "SET ROLE service_role; INSERT INTO public.lm_goal_contexts(tenant_id,revision,context,context_sha256) VALUES ('tenant-b',1,'{}'::jsonb,repeat('a',64));" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL service_role bypassed Goal context RPC' >&2
  exit 1
fi

[[ "$("${PSQL[@]}" -Atqc "SELECT count(*) FROM public.lm_goal_contexts;")" == "1" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT count(*) FROM public.lm_goal_portfolios;")" == "1" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT count(*) FROM public.lm_runtime_jobs WHERE loop_id='life-manager.manager';")" == "1" ]]
printf '%s\n' 'cloud goal postgres closed-client continuity/replay/isolation: ok'
