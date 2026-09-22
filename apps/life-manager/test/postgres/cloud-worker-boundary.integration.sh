#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_MIGRATION="$ROOT_DIR/migrations/20260729_runtime_jobs.sql"
GOAL_MIGRATION="$ROOT_DIR/migrations/2026-09-22-lm-goal-context-portfolios.sql"
ADMISSION_MIGRATION="$ROOT_DIR/migrations/2026-09-22-lm-cloud-work-admission.sql"
TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/cloud-worker-pg.XXXXXX")"
PGDATA_DIR="$TEST_TMP/data"
PGSOCKET_DIR="$TEST_TMP/socket"
PGLOG="$TEST_TMP/postgres.log"
DB_NAME="cloud_worker_test"
DB_MODE="local"
DOCKER_NAME="cloud-worker-pg-$$"

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
  export PGPASSWORD="cloud-worker-test-only"
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
"${PSQL[@]}" -f "$ADMISSION_MIGRATION" >/dev/null

export NODE_PATH="$ROOT_DIR/node_modules"
export CLOUD_WORK_OUTPUT="$TEST_TMP/result.json"
cd "$ROOT_DIR"

node <<'NODE'
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { Pool } = require("pg");
const { createCloudCredentialBroker } = require("./lib/cloud-credential-broker.js");
const { createCloudGeneralAgentWorker } = require("./lib/cloud-general-agent-worker.js");
const { createCloudWorkAuthority } = require("./lib/cloud-work-authority.js");
const { createCloudWorkerAdmission } = require("./lib/cloud-worker-admission.js");
const { claimCloudJob, completeJob, enqueueJob } = require("./lib/runtime-job-store.js");

const KEY = Buffer.alloc(32, 31).toString("base64");
const NOW = Date.parse("2026-09-23T00:00:00.000Z");
const RAW_SECRET = "CC04_PLAINTEXT_MUST_NOT_PERSIST_927";

function runtimeJob(tenantId, goalId) {
  return {
    jobId: `goal:${goalId}:r1`, tenantId, loopId: "life-manager.manager",
    capability: "general-agent.work", effectClass: "none", effectKey: null,
    inputRefs: { goal_ref: `goal-portfolio://${tenantId}/${goalId}?revision=1` },
    maxAttempts: 1,
  };
}

function admission({ tenantId, workerId, query, authority }) {
  return createCloudWorkerAdmission({
    tenantId, workerId, authority,
    claimCloudJob: (input) => claimCloudJob(input, { query }),
  });
}

(async () => {
  const pool = new Pool();
  const query = pool.query.bind(pool);
  await pool.query(`
    INSERT INTO public.lm_runtime_jobs(
      job_id, tenant_id, loop_id, capability, effect_class, effect_key,
      input_refs, max_attempts, available_at
    ) VALUES (
      'goal:poison:r1', 'tenant-a', 'life-manager.manager', 'general-agent.work',
      'none', NULL, '{"goal_ref":"goal-portfolio://tenant-a/other?revision=1"}'::jsonb,
      1, '2020-01-01T00:00:00Z'
    )
  `);
  await pool.query(`
    INSERT INTO public.lm_runtime_jobs(
      job_id, tenant_id, loop_id, capability, effect_class, effect_key,
      input_refs, max_attempts, attempt, status, lease_owner, lease_expires_at
    ) VALUES (
      'goal:expired:r1', 'tenant-c', 'life-manager.manager', 'general-agent.work',
      'none', NULL, '{"goal_ref":"goal-portfolio://tenant-c/expired?revision=1"}'::jsonb,
      1, 1, 'running', 'expired-worker', '2020-01-01T00:00:00Z'
    )
  `);
  for (const item of [
    runtimeJob("tenant-a", "continuity-a"),
    runtimeJob("tenant-a", "continuity-b"),
    runtimeJob("tenant-b", "continuity-c"),
  ]) await enqueueJob(item, { query });

  const authority = createCloudWorkAuthority({ signingKey: KEY, now: () => NOW });
  assert.equal(await claimCloudJob({
    workerId: "worker-c1", capabilities: ["general-agent.work"],
    tenantId: "tenant-c", leaseSeconds: 180,
  }, { query }), null);
  const expired = (await pool.query(`
    SELECT status, attempt, lease_owner FROM public.lm_runtime_jobs
    WHERE tenant_id = 'tenant-c' AND job_id = 'goal:expired:r1'
  `)).rows[0];
  assert.deepEqual(expired, { status: "running", attempt: 1, lease_owner: "expired-worker" });
  const [a1, a2, b1] = await Promise.all([
    admission({ tenantId: "tenant-a", workerId: "worker-a1", query, authority }).claim(),
    admission({ tenantId: "tenant-a", workerId: "worker-a2", query, authority }).claim(),
    admission({ tenantId: "tenant-b", workerId: "worker-b1", query, authority }).claim(),
  ]);
  const tenantAClaims = [a1, a2].filter(Boolean);
  assert.equal(tenantAClaims.length, 1);
  assert.ok(b1);
  const claimed = tenantAClaims[0];
  assert.notEqual(claimed.job.job_id, "goal:poison:r1");
  const poison = (await pool.query(`
    SELECT status, attempt, lease_owner FROM public.lm_runtime_jobs
    WHERE tenant_id = 'tenant-a' AND job_id = 'goal:poison:r1'
  `)).rows[0];
  assert.deepEqual(poison, { status: "queued", attempt: 0, lease_owner: null });
  const workerId = claimed.job.job_id === a1?.job.job_id ? "worker-a1" : "worker-a2";
  let vaultCalls = 0;
  let providerCalls = 0;
  const broker = createCloudCredentialBroker({
    authority,
    secretProvider: {
      async health() { return { ok: true, mode: "cloud", provider: "vault" }; },
      async get(tenantId, ref) {
        vaultCalls += 1;
        assert.equal(tenantId, "tenant-a");
        assert.equal(ref, "secret://gemini/api-key");
        return RAW_SECRET;
      },
    },
    async providerCall(input) {
      providerCalls += 1;
      assert.equal(input.credentialValue, RAW_SECRET);
      return {
        operation_id: "postgres-broker-operation-1", status: "completed",
        tenant_id: input.tenantId, job_id: input.jobId, attempt: input.attempt,
        capability: input.capability,
        evidence_refs: [`broker://${input.tenantId}/postgres-operation/result`],
      };
    },
  });

  await assert.rejects(broker.invoke({
    grant: claimed.grant,
    tenantId: "tenant-b",
    jobId: claimed.job.job_id,
    attempt: 1,
    workerId,
    capability: "general-agent.work",
    effectClass: "none",
    credentialRef: "secret://gemini/api-key",
    operation: "gemini.generate-plan",
    inputRefs: claimed.job.input_refs,
  }), /cloud credential invocation invalid/i);
  assert.equal(vaultCalls, 0);

  let offered = true;
  const worker = createCloudGeneralAgentWorker({
    tenantId: "tenant-a", workerId,
    admission: { async claim() { if (!offered) return null; offered = false; return claimed; } },
    broker,
    completeJob: (input) => completeJob(input, { query }),
    failJob: async () => { throw new Error("must not fail"); },
  });
  const completed = await worker.runOnce();
  assert.equal(completed.status, "completed");
  assert.equal((await worker.runOnce()).status, "idle");
  assert.equal(vaultCalls, 1);
  assert.equal(providerCalls, 1);

  const secretRows = (await pool.query(`
    SELECT
      (SELECT count(*)::integer FROM public.lm_runtime_jobs
        WHERE input_refs::text LIKE '%' || $1 || '%')
      + (SELECT count(*)::integer FROM public.lm_runtime_job_receipts
        WHERE receipt::text LIKE '%' || $1 || '%') AS count
  `, [RAW_SECRET])).rows[0].count;
  assert.equal(secretRows, 0);
  fs.writeFileSync(process.env.CLOUD_WORK_OUTPUT, JSON.stringify({
    tenant_id: completed.tenant_id,
    job_id: completed.job_id,
    attempt: completed.attempt,
    vault_calls: vaultCalls,
    provider_calls: providerCalls,
    tenant_b_job_id: b1.job.job_id,
  }));
  await pool.end();
})().catch((error) => { console.error(error); process.exitCode = 1; });
NODE

# The worker/broker process is gone. A new process verifies the immutable receipt.
node <<'NODE'
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { Pool } = require("pg");
const { createGeneralAgentWorkLoopAdapter } = require("./lib/general-agent-work-adapter.js");

(async () => {
  const expected = JSON.parse(fs.readFileSync(process.env.CLOUD_WORK_OUTPUT, "utf8"));
  const pool = new Pool();
  const rows = (await pool.query(`
    SELECT jobs.*, receipts.receipt, receipts.outcome, receipts.attempt AS receipt_attempt
    FROM public.lm_runtime_jobs AS jobs
    JOIN public.lm_runtime_job_receipts AS receipts
      ON receipts.job_id = jobs.job_id AND receipts.tenant_id = jobs.tenant_id
    WHERE jobs.tenant_id = $1 AND jobs.job_id = $2
  `, [expected.tenant_id, expected.job_id])).rows;
  assert.equal(rows.length, 1);
  assert.equal(rows[0].status, "completed");
  assert.equal(rows[0].outcome, "completed");
  assert.equal(rows[0].receipt_attempt, expected.attempt);
  assert.equal(createGeneralAgentWorkLoopAdapter().verify(rows[0].receipt, rows[0]), true);
  assert.deepEqual({ vault_calls: expected.vault_calls, provider_calls: expected.provider_calls }, {
    vault_calls: 1, provider_calls: 1,
  });
  const foreign = (await pool.query(`
    SELECT count(*)::integer AS count FROM public.lm_runtime_job_receipts
    WHERE tenant_id = 'tenant-b' AND job_id = $1
  `, [expected.job_id])).rows[0].count;
  assert.equal(foreign, 0);
  await pool.end();
})().catch((error) => { console.error(error); process.exitCode = 1; });
NODE

if "${PSQL[@]}" -c "SET ROLE authenticated; SELECT * FROM public.claim_lm_cloud_runtime_job('foreign',ARRAY['general-agent.work'],'tenant-a',180);" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL authenticated role executed Cloud claim RPC' >&2
  exit 1
fi
if "${PSQL[@]}" -c "SET ROLE authenticated; SELECT * FROM public.lm_runtime_jobs;" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL authenticated role read runtime jobs' >&2
  exit 1
fi

[[ "$("${PSQL[@]}" -Atqc "SELECT count(*) FROM public.lm_runtime_jobs WHERE tenant_id='tenant-a' AND status='completed';")" == "1" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT count(*) FROM public.lm_runtime_jobs WHERE tenant_id='tenant-a' AND status='running';")" == "0" ]]
[[ "$("${PSQL[@]}" -Atqc "SELECT count(*) FROM public.lm_runtime_jobs WHERE tenant_id='tenant-b' AND status='running';")" == "1" ]]
printf '%s\n' 'cloud worker tenant admission/grant/surrogate/receipt/isolation: ok'
