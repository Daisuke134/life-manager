"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createHash } = require("node:crypto");
const {
  parseRuntimeCommand,
  validateComposeModel,
  runRuntimeUp,
  buildSchedulerHolderToken,
  marketingGenerationDueDate,
  listGenerationReceipts,
  listHonneJaShadowGenerationReceipts,
  listObservablePublicationReceipts,
  executeCapabilityJob,
  createScopedEnvironmentSecretProvider,
  createWorkerHandlers,
  observeWorkerPoll,
} = require("./runtime-up.js");
const {
  buildMarketingObservationJob,
} = require("../lib/marketing-observation-adapter.js");
const {
  buildMarketingVideoGenerationJob,
} = require("../lib/marketing-video-generation-adapter.js");
const {
  importContentObject,
} = require("../lib/content-object-store.js");
const {
  verifyOutboundEvidence,
} = require("../lib/outbound-evidence.js");
const {
  buildVerifiedOutboundReceipt,
} = require("../lib/outbound-success.js");

const ROOT = path.join(__dirname, "../../..");
const COMPOSE_PATH = path.join(ROOT, "deploy/local/compose.yaml");
const LEASE_MIGRATION = path.join(
  __dirname,
  "../migrations/20260729_runtime_scheduler_lease.sql",
);

test("active capability work refreshes worker liveness without starting a second claim", () => {
  const state = { lastPollAt: "2026-08-01T00:00:00.000Z" };
  assert.equal(observeWorkerPoll(state, true, () => "2026-08-01T00:01:00.000Z"), false);
  assert.equal(state.lastPollAt, "2026-08-01T00:01:00.000Z");
  assert.equal(observeWorkerPoll(state, false, () => "2026-08-01T00:02:00.000Z"), true);
  assert.equal(state.lastPollAt, "2026-08-01T00:02:00.000Z");
});

function healthyService(environment = {}) {
  return {
    environment,
    healthcheck: { test: ["CMD", "true"] },
  };
}

function validModel() {
  return {
    services: {
      postgres: {
        ...healthyService(),
        volumes: ["postgres-data:/var/lib/postgresql/data"],
      },
      "object-store": {
        ...healthyService(),
        volumes: ["object-data:/data"],
      },
      migrate: {
        environment: {},
        depends_on: { postgres: { condition: "service_healthy" } },
      },
      "runtime-init": {
        environment: {},
        depends_on: { migrate: { condition: "service_completed_successfully" } },
      },
      api: healthyService({
        LM_DEPLOYMENT_ROLE: "api",
        LIFE_RUN_LOOPS: "false",
      }),
      scheduler: healthyService({
        LM_DEPLOYMENT_ROLE: "scheduler",
        LM_SCHEDULER_OWNER: "local-primary",
        LIFE_RUN_LOOPS: "true",
      }),
      worker: healthyService({
        LM_DEPLOYMENT_ROLE: "worker",
        LIFE_RUN_LOOPS: "false",
      }),
    },
    volumes: {
      "postgres-data": {},
      "object-data": {},
      "runtime-data": {},
    },
  };
}

async function verifiedOutboundReceipt(job) {
  const bytes = Buffer.alloc(5000, 0x61);
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(bytes);
  const digest = createHash("sha256").update(bytes).digest("hex");
  const evidence = await verifyOutboundEvidence({
    tenantId: job.tenant_id,
    attemptRef: `runtime-attempt://${job.tenant_id}/${job.job_id}/${job.attempt}`,
    externalReceiptRef: `provider-receipt://${job.tenant_id}/receipt-1`,
    artifactRef: `object://sha256/${digest}`,
    canonicalUrl: "https://lu.ma/tokyo-agent-night",
  }, {
    readExternalReceipt: async () => ({
      kind: "provider_response",
      provider_id: "receipt-1",
      observed_at: "2026-08-01T09:00:00.000Z",
    }),
    readArtifact: async () => bytes,
    fetchImpl: async () => ({ status: 200 }),
  });
  return buildVerifiedOutboundReceipt({
    tenantId: job.tenant_id,
    jobId: job.job_id,
    attempt: job.attempt,
    verifiedAt: "2026-08-01T09:00:01.000Z",
  }, evidence);
}

test("runtime command accepts only the explicit local up contract", () => {
  assert.deepEqual(
    parseRuntimeCommand(["runtime", "up", "--mode", "local"]),
    { command: "up", mode: "local" },
  );
  assert.throws(
    () => parseRuntimeCommand(["runtime", "up", "--mode", "cloud"]),
    /local/i,
  );
  assert.throws(() => parseRuntimeCommand(["up"]), /usage/i);
});

test("coverage worker capability receives the assembled Connector refresh services", () => {
  const connectorCoverageServices = Object.freeze({
    coverageStore: { read: async () => {}, save: async () => {} },
    refreshCoverage: async () => {},
  });
  let observedServices;
  const handlers = createWorkerHandlers({}, ["connector.coverage.refresh"], {
    connectorCoverageServices,
    createRegistry({ servicesByAdapter }) {
      observedServices = servicesByAdapter["connector-coverage-refresh"];
      return {
        hasCapability(capability) { return capability === "connector.coverage.refresh"; },
        getByCapability() { return { execute: async () => "coverage-executed" }; },
      };
    },
  });

  assert.equal(observedServices, connectorCoverageServices);
  assert.equal(typeof handlers["connector.coverage.refresh"], "function");
});

test("coverage worker assembles production services from its query and connect boundaries", () => {
  const query = async () => {};
  const connect = async () => {};
  const assembled = { coverageStore: {}, refreshCoverage: async () => {} };
  let observedRuntime;
  let observedServices;
  createWorkerHandlers({ LM_RUNTIME_TENANT_ID: "dais-local" }, ["connector.coverage.refresh"], {
    query,
    connect,
    createConnectorCoverageRuntimeServices(env, runtime) {
      assert.equal(env.LM_RUNTIME_TENANT_ID, "dais-local");
      observedRuntime = runtime;
      return assembled;
    },
    createRegistry({ servicesByAdapter }) {
      observedServices = servicesByAdapter["connector-coverage-refresh"];
      return {
        hasCapability() { return true; },
        getByCapability() { return { execute: async () => ({ receipt: {} }) }; },
      };
    },
  });
  assert.deepEqual(observedRuntime, { query, connect });
  assert.equal(observedServices, assembled);
});

test("compose topology has durable stores, health checks, distinct roles, and one scheduler owner", () => {
  assert.deepEqual(validateComposeModel(validModel()), {
    schedulerService: "scheduler",
    schedulerOwner: "local-primary",
    workerServices: ["worker"],
  });

  const duplicate = validModel();
  duplicate.services["scheduler-copy"] = healthyService({
    LM_DEPLOYMENT_ROLE: "scheduler",
    LM_SCHEDULER_OWNER: "local-copy",
    LIFE_RUN_LOOPS: "true",
  });
  assert.throws(() => validateComposeModel(duplicate), /exactly one scheduler/i);

  const noVolume = validModel();
  delete noVolume.volumes["object-data"];
  assert.throws(() => validateComposeModel(noVolume), /object-data/i);
});

test("committed local compose is self-contained and never references a legacy runtime", () => {
  const compose = fs.readFileSync(COMPOSE_PATH, "utf8");
  for (const service of [
    "postgres",
    "object-store",
    "migrate",
    "runtime-init",
    "api",
    "scheduler",
    "worker",
  ]) {
    assert.match(compose, new RegExp(`^  ${service}:`, "m"));
  }
  assert.match(compose, /healthcheck:/);
  assert.match(compose, /condition: service_healthy/);
  assert.match(compose, /condition: service_completed_successfully/);
  assert.match(compose, /^  postgres-data:/m);
  assert.match(compose, /^  object-data:/m);
  assert.match(compose, /^  runtime-data:/m);
  assert.match(compose, /LM_SCHEDULER_OWNER: local-primary/);
  assert.match(compose, /LM_RUNTIME_TENANT_ID: \$\{LM_RUNTIME_TENANT_ID:-\}/);
  assert.match(
    compose,
    /\$\{LM_LOCAL_WORKER_HEALTH_PORT:-18790\}:8790/,
  );
  assert.match(
    compose,
    /LM_FINANCIAL_REPORT_POLL_MS: \$\{LM_FINANCIAL_REPORT_POLL_MS:-300000\}/,
  );
  assert.match(
    compose,
    /LM_MARKETING_PUBLICATION_CHAIN_ENABLED: \$\{LM_MARKETING_PUBLICATION_CHAIN_ENABLED:-false\}/,
  );
  assert.match(
    compose,
    /LM_MARKETING_PUBLICATION_CHAIN_AFTER: \$\{LM_MARKETING_PUBLICATION_CHAIN_AFTER:-\}/,
  );
  assert.match(
    compose,
    /LM_MARKETING_OBSERVATION_ENABLED: \$\{LM_MARKETING_OBSERVATION_ENABLED:-false\}/,
  );
  assert.match(
    compose,
    /LM_MARKETING_OBSERVATION_PRODUCT_ID: \$\{LM_MARKETING_OBSERVATION_PRODUCT_ID:-\}/,
  );
  assert.match(
    compose,
    /LM_WORKER_CAPABILITIES: \$\{LM_WORKER_CAPABILITIES:-runtime\.noop\}/,
  );
  assert.match(compose, /^  worker:\n(?:.*\n){0,4}    build: \*runtime-build/m);
  assert.match(compose, /LM_TELEGRAM_BOT_TOKEN: \$\{LM_TELEGRAM_BOT_TOKEN:-\}/);
  assert.doesNotMatch(
    compose,
    /\.openclaw|profitable-claude|life-manager-v0|\/Users\/anicca/i,
  );
});

test("scheduler lease uses row ownership and atomic conflict handling without advisory locks", () => {
  const sql = fs.readFileSync(LEASE_MIGRATION, "utf8");
  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.lm_runtime_scheduler_leases/i);
  assert.match(sql, /scheduler_key text PRIMARY KEY|PRIMARY KEY \(scheduler_key\)/i);
  assert.match(sql, /ON CONFLICT \(scheduler_key\) DO UPDATE/i);
  assert.match(sql, /lease_expires_at <= clock_timestamp\(\)/i);
  assert.match(sql, /RETURNING/i);
  assert.doesNotMatch(sql, /advisory_(?:lock|xact_lock)/i);
});

test("runtime up validates docker compose JSON before starting the stack", () => {
  const calls = [];
  const spawnSync = (command, args) => {
    calls.push({ command, args });
    if (args.includes("config")) {
      return {
        status: 0,
        stdout: JSON.stringify(validModel()),
        stderr: "",
      };
    }
    return { status: 0, stdout: "", stderr: "" };
  };
  const result = runRuntimeUp({
    argv: ["runtime", "up", "--mode", "local"],
    spawnSync,
    repoRoot: ROOT,
  });

  assert.equal(result.ok, true);
  assert.equal(result.schedulerOwner, "local-primary");
  assert.deepEqual(calls.map(({ command }) => command), ["docker", "docker"]);
  assert.deepEqual(calls[0].args.slice(-3), ["config", "--format", "json"]);
  assert.deepEqual(calls[1].args.slice(-4), ["up", "-d", "--build", "--wait"]);
});

test("scheduler holder token changes on every process start even in the same container", () => {
  const ids = ["start-a", "start-b"];
  const randomUUID = () => ids.shift();
  assert.equal(
    buildSchedulerHolderToken("local-primary", "same-container", randomUUID),
    "local-primary:same-container:start-a",
  );
  assert.equal(
    buildSchedulerHolderToken("local-primary", "same-container", randomUUID),
    "local-primary:same-container:start-b",
  );
});

test("daily marketing generation becomes due at 10:15 JST and never before", () => {
  assert.equal(
    marketingGenerationDueDate(Date.parse("2026-07-30T01:14:59.000Z")),
    null,
  );
  assert.equal(
    marketingGenerationDueDate(Date.parse("2026-07-30T01:15:00.000Z")),
    "2026-07-30",
  );
  assert.equal(
    marketingGenerationDueDate(Date.parse("2026-07-30T14:59:00.000Z")),
    "2026-07-30",
  );
});

test("publication chain scans only one tenant and an explicit non-backfill window", async () => {
  const calls = [];
  const pool = {
    async query(sql, params) {
      calls.push({ sql, params });
      return { rows: [{ receipt: { kind: "marketing_daily_generation" } }] };
    },
  };
  const rows = await listGenerationReceipts(pool, {
    tenantId: "tenant-a",
    after: "2026-08-01T00:00:00.000Z",
  });

  assert.deepEqual(rows, [{ kind: "marketing_daily_generation" }]);
  assert.match(calls[0].sql, /j\.tenant_id = \$1/);
  assert.match(calls[0].sql, /r\.outcome = 'completed'/);
  assert.match(calls[0].sql, /r\.created_at >= \$2::timestamptz/);
  assert.match(calls[0].sql, /LIMIT 100/);
  assert.deepEqual(calls[0].params, [
    "tenant-a",
    "2026-08-01T00:00:00.000Z",
  ]);
});

test("observation chain scans only observable publication receipts in one tenant window", async () => {
  const calls = [];
  const pool = {
    async query(sql, params) {
      calls.push({ sql, params });
      return {
        rows: [{
          job_id: `marketing-daily:${"c".repeat(64)}`,
          receipt: { kind: "marketing_daily_distribution" },
        }],
      };
    },
  };
  const rows = await listObservablePublicationReceipts(pool, {
    tenantId: "tenant-a",
    after: "2026-08-01T00:00:00.000Z",
  });

  assert.equal(rows.length, 1);
  assert.match(calls[0].sql, /j\.tenant_id = \$1/);
  assert.match(
    calls[0].sql,
    /j\.capability = 'marketing\.life-manager\.daily\.publish'/,
  );
  assert.match(calls[0].sql, /r\.outcome = 'completed'/);
  assert.match(calls[0].sql, /provider_post_id/);
  assert.match(calls[0].sql, /provider_route/);
  assert.match(calls[0].sql, /r\.created_at >= \$2::timestamptz/);
  assert.match(calls[0].sql, /ORDER BY r\.created_at DESC/);
  assert.deepEqual(calls[0].params, [
    "tenant-a",
    "2026-08-01T00:00:00.000Z",
  ]);
});

test("honne JA shadow scan is scoped to one tenant/product/format/locale and an explicit window", async () => {
  const calls = [];
  const pool = {
    async query(sql, params) {
      calls.push({ sql, params });
      return { rows: [{ receipt: { kind: "marketing_video_artifact" } }] };
    },
  };
  const rows = await listHonneJaShadowGenerationReceipts(pool, {
    tenantId: "tenant-a",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    after: "2026-07-30T00:00:00.000Z",
  });

  assert.deepEqual(rows, [{ kind: "marketing_video_artifact" }]);
  assert.match(calls[0].sql, /j\.tenant_id = \$1/);
  assert.match(calls[0].sql, /j\.capability = 'marketing\.video\.generate'/);
  assert.match(calls[0].sql, /r\.outcome = 'completed'/);
  assert.match(calls[0].sql, /r\.receipt->>'status' = 'ready'/);
  assert.match(calls[0].sql, /r\.created_at >= \$2::timestamptz/);
  assert.deepEqual(calls[0].params, [
    "tenant-a",
    "2026-07-30T00:00:00.000Z",
    "honne-ai",
    "reelclaw",
    "ja",
  ]);

  await assert.rejects(
    listHonneJaShadowGenerationReceipts(pool, {
      tenantId: "tenant-a",
      productId: "honne-ai",
      formatId: "reelclaw",
      locale: "ja",
      after: "not-a-boundary",
    }),
    /honne JA shadow scan boundary is invalid/,
  );
  await assert.rejects(
    listHonneJaShadowGenerationReceipts(pool, {
      tenantId: "tenant-a",
      productId: "",
      formatId: "reelclaw",
      locale: "ja",
      after: "2026-07-30T00:00:00.000Z",
    }),
    /honne JA shadow scan boundary is invalid/,
  );
});

test("capability worker completes a registered financial report with only its safe receipt", async () => {
  const calls = [];
  const job = {
    tenant_id: "tenant-a",
    job_id: "job-a",
    attempt: 1,
    capability: "report.financial.telegram",
    effect_class: "message",
  };
  await executeCapabilityJob(job, {
    workerId: "worker-a",
    handlers: {
      "report.financial.telegram": async () => ({
        receipt: {
          kind: "telegram_financial_report",
          message_id: 44,
          snapshot_hash: "a".repeat(64),
        },
      }),
    },
    completeJob: async (input) => calls.push({ kind: "complete", input }),
    failJob: async (input) => calls.push({ kind: "fail", input }),
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].kind, "complete");
  assert.deepEqual(calls[0].input.receipt, {
    kind: "telegram_financial_report",
    message_id: 44,
    snapshot_hash: "a".repeat(64),
  });
});

test("a registered no-effect capability executes its adapter instead of becoming a runtime noop", async () => {
  const calls = [];
  await executeCapabilityJob({
    tenant_id: "tenant-a",
    job_id: "generation-a",
    attempt: 1,
    capability: "marketing.life-manager.daily.generate",
    effect_class: "none",
  }, {
    workerId: "worker-a",
    handlers: {
      "marketing.life-manager.daily.generate": async () => ({
        receipt: { kind: "marketing_daily_generation", status: "rendered" },
      }),
    },
    completeJob: async (input) => calls.push({ kind: "complete", input }),
    failJob: async (input) => calls.push({ kind: "fail", input }),
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].kind, "complete");
  assert.equal(calls[0].input.receipt.kind, "marketing_daily_generation");
});

test("coverage worker persists a bounded stage code without raw provider errors", async () => {
  const calls = [];
  const error = new Error("Connector coverage refresh unavailable");
  error.code = "CONNECTOR_COVERAGE_INVENTORY_FAILED";
  await executeCapabilityJob({
    tenant_id: "dais-local",
    job_id: `connector-coverage:${"c".repeat(64)}`,
    attempt: 1,
    capability: "connector.coverage.refresh",
    effect_class: "none",
  }, {
    workerId: "connector-local",
    handlers: { "connector.coverage.refresh": async () => { throw error; } },
    completeJob: async (input) => calls.push({ kind: "complete", input }),
    failJob: async (input) => calls.push({ kind: "fail", input }),
  });
  assert.deepEqual(calls.map(({ kind }) => kind), ["fail"]);
  assert.equal(calls[0].input.errorCode, "CONNECTOR_COVERAGE_INVENTORY_FAILED");
  assert.equal(calls[0].input.unknownEffect, false);
});

test("outbound Luma worker persists only an allowlisted provider state code", async () => {
  for (const [providerCode, expectedCode, unknownEffect] of [
    ["LUMA_LOGIN_REQUIRED", "LUMA_LOGIN_REQUIRED", false],
    ["LUMA_RSVP_UNAVAILABLE", "LUMA_RSVP_UNAVAILABLE", false],
    ["LUMA_FORM_INPUT_REQUIRED", "LUMA_FORM_INPUT_REQUIRED", false],
    ["LUMA_EFFECT_UNKNOWN", "LUMA_EFFECT_UNKNOWN", true],
    ["LUMA_PRIVATE_PROVIDER_DETAIL", "CAPABILITY_EXECUTION_FAILED", false],
  ]) {
    const calls = [];
    const error = new Error("private page text");
    error.code = providerCode;
    error.unknownEffect = unknownEffect;
    await executeCapabilityJob({
      tenant_id: "dais-local",
      job_id: `outbound-event:${"d".repeat(64)}`,
      attempt: 1,
      capability: "outbound.event.apply",
      effect_class: "publish",
    }, {
      workerId: "connector-local",
      handlers: { "outbound.event.apply": async () => { throw error; } },
      completeJob: async (input) => calls.push({ kind: "complete", input }),
      failJob: async (input) => calls.push({ kind: "fail", input }),
    });
    assert.deepEqual(calls.map(({ kind }) => kind), ["fail"]);
    assert.equal(calls[0].input.errorCode, expectedCode);
    assert.equal(calls[0].input.unknownEffect, unknownEffect);
    assert.doesNotMatch(JSON.stringify(calls), /private page text/);
  }
});

test("external-effect execution heartbeats its lease before recording completion", async () => {
  const calls = [];
  let scheduledHeartbeat;
  const job = {
    tenant_id: "dais",
    job_id: `outbound-event:${"d".repeat(64)}`,
    attempt: 1,
    capability: "outbound.event.apply",
    effect_class: "publish",
  };
  const receipt = await verifiedOutboundReceipt(job);
  await executeCapabilityJob(job, {
    workerId: "connector-local",
    handlers: {
      "outbound.event.apply": async () => {
        await scheduledHeartbeat();
        return { receipt };
      },
    },
    heartbeatJob: async (input) => calls.push({ kind: "heartbeat", input }),
    completeJob: async (input) => calls.push({ kind: "complete", input }),
    failJob: async (input) => calls.push({ kind: "fail", input }),
    leaseSeconds: 90,
    setIntervalFn(callback) {
      scheduledHeartbeat = callback;
      return "heartbeat-timer";
    },
    clearIntervalFn(timer) {
      calls.push({ kind: "clear", timer });
    },
  });

  assert.deepEqual(calls.map(({ kind }) => kind), ["heartbeat", "clear", "complete"]);
  assert.deepEqual(calls[0].input, {
    tenantId: "dais",
    jobId: `outbound-event:${"d".repeat(64)}`,
    attempt: 1,
    workerId: "connector-local",
    leaseSeconds: 90,
  });
});

test("outbound handlerのbare successはcompletedにせずunknown effectへ落とす", async () => {
  const calls = [];
  await executeCapabilityJob({
    tenant_id: "dais",
    job_id: `outbound-event:${"1".repeat(64)}`,
    attempt: 1,
    capability: "outbound.event.apply",
    effect_class: "publish",
  }, {
    workerId: "connector-local",
    handlers: {
      "outbound.event.apply": async () => ({
        receipt: { status: "success" },
      }),
    },
    completeJob: async (input) => calls.push({ kind: "complete", input }),
    failJob: async (input) => calls.push({ kind: "fail", input }),
  });
  assert.deepEqual(calls.map(({ kind }) => kind), ["fail"]);
  assert.equal(calls[0].input.errorCode, "CAPABILITY_EXECUTION_FAILED");
  assert.equal(calls[0].input.unknownEffect, true);
});

test("a lost heartbeat fails an external-effect attempt as unknown", async () => {
  const calls = [];
  let scheduledHeartbeat;
  await executeCapabilityJob({
    tenant_id: "dais",
    job_id: `outbound-event:${"e".repeat(64)}`,
    attempt: 1,
    capability: "outbound.event.apply",
    effect_class: "publish",
  }, {
    workerId: "connector-local",
    handlers: {
      "outbound.event.apply": async () => {
        await scheduledHeartbeat();
        return { receipt: { kind: "event_application", status: "submitted" } };
      },
    },
    heartbeatJob: async () => {
      throw new Error("runtime heartbeat lost lease");
    },
    completeJob: async (input) => calls.push({ kind: "complete", input }),
    failJob: async (input) => calls.push({ kind: "fail", input }),
    leaseSeconds: 90,
    setIntervalFn(callback) {
      scheduledHeartbeat = callback;
      return "heartbeat-timer";
    },
    clearIntervalFn(timer) {
      calls.push({ kind: "clear", timer });
    },
  });

  assert.deepEqual(calls.map(({ kind }) => kind), ["clear", "fail"]);
  assert.equal(calls[1].input.errorCode, "CAPABILITY_HEARTBEAT_FAILED");
  assert.equal(calls[1].input.unknownEffect, true);
});

test("adapter failure cannot make a simultaneous lost heartbeat retryable", async () => {
  const calls = [];
  let scheduledHeartbeat;
  await executeCapabilityJob({
    tenant_id: "dais",
    job_id: `outbound-event:${"f".repeat(64)}`,
    attempt: 1,
    capability: "outbound.event.apply",
    effect_class: "publish",
  }, {
    workerId: "connector-local",
    handlers: {
      "outbound.event.apply": async () => {
        await scheduledHeartbeat();
        throw new Error("browser result unavailable");
      },
    },
    heartbeatJob: async () => {
      throw new Error("runtime heartbeat lost lease");
    },
    completeJob: async (input) => calls.push({ kind: "complete", input }),
    failJob: async (input) => calls.push({ kind: "fail", input }),
    leaseSeconds: 90,
    setIntervalFn(callback) {
      scheduledHeartbeat = callback;
      return "heartbeat-timer";
    },
    clearIntervalFn() {},
  });

  assert.deepEqual(calls.map(({ kind }) => kind), ["fail"]);
  assert.equal(calls[0].input.errorCode, "CAPABILITY_HEARTBEAT_FAILED");
  assert.equal(calls[0].input.unknownEffect, true);
});

test("environment secret provider is tenant-scoped and resolves only declared refs", async () => {
  const provider = createScopedEnvironmentSecretProvider({
    LM_RUNTIME_TENANT_ID: "tenant-a",
    LM_TELEGRAM_BOT_TOKEN: "private-token",
  });

  assert.equal(
    await provider.get("tenant-a", "secret://telegram/bot-token"),
    "private-token",
  );
  await assert.rejects(
    provider.get("tenant-b", "secret://telegram/bot-token"),
    /tenant/i,
  );
  await assert.rejects(
    provider.get("tenant-a", "secret://telegram/raw-token"),
    /reference/i,
  );
});

test("worker handlers are routed through the configured loop adapter registry", async () => {
  const calls = [];
  const handlers = createWorkerHandlers(
    { LM_RUNTIME_TENANT_ID: "tenant-a" },
    ["fixture.execute"],
    {
      createRegistry({ servicesByAdapter }) {
        calls.push({ kind: "registry", servicesByAdapter });
        return {
          hasCapability: (capability) => capability === "fixture.execute",
          getByCapability: () => ({
            execute: async (job) => {
              calls.push({ kind: "execute", job });
              return { receipt: { kind: "fixture" } };
            },
          }),
        };
      },
    },
  );

  assert.equal(typeof handlers["fixture.execute"], "function");
  assert.deepEqual(
    await handlers["fixture.execute"]({ job_id: "job-a" }),
    { receipt: { kind: "fixture" } },
  );
  assert.equal(calls[0].kind, "registry");
  assert.deepEqual(calls[1], {
    kind: "execute",
    job: { job_id: "job-a" },
  });
});

test("outbound event worker wires the Luma browser provider and tenant evidence readers", async () => {
  const provider = {
    async inspectRegistration() {},
    async submitRegistration() {},
  };
  const evidenceStore = {
    async readExternalReceipt() {},
    async readArtifact() {},
  };
  const fetchImpl = async () => {};
  const now = () => "2026-08-01T10:00:00.000Z";
  let services;
  const handlers = createWorkerHandlers({
    LM_RUNTIME_TENANT_ID: "tenant-a",
    LM_DATA_DIR: "/var/lib/life-manager/data",
  }, ["outbound.event.apply"], {
    lumaProvider: provider,
    lumaEvidenceStore: evidenceStore,
    fetchImpl,
    now,
    createRegistry({ servicesByAdapter }) {
      services = servicesByAdapter["outbound-luma-rsvp"];
      return {
        hasCapability: (capability) => capability === "outbound.event.apply",
        getByCapability: () => ({
          execute: async () => ({ receipt: { kind: "fixture" } }),
        }),
      };
    },
  });

  assert.equal(typeof handlers["outbound.event.apply"], "function");
  assert.equal(services.provider, provider);
  assert.equal(services.readExternalReceipt, evidenceStore.readExternalReceipt);
  assert.equal(services.readArtifact, evidenceStore.readArtifact);
  assert.equal(services.fetchImpl, fetchImpl);
  assert.equal(services.now, now);
});

test("outbound event worker obtains its provider from the canonical events pack", () => {
  const dailyDriver = { withLumaPage: async () => {} };
  const auth = { ensureAuthenticated: async () => ({ status: "authenticated" }) };
  const provider = { inspectRegistration: async () => {}, submitRegistration: async () => {} };
  let composition;
  let services;
  createWorkerHandlers({
    LM_RUNTIME_TENANT_ID: "tenant-a",
    LM_DATA_DIR: "/var/lib/life-manager/data",
  }, ["outbound.event.apply"], {
    lumaDailyDriver: dailyDriver,
    lumaAuth: auth,
    lumaEvidenceStore: {
      record: async () => {},
      readExternalReceipt: async () => {},
      readArtifact: async () => {},
    },
    createConnectorEventsPack(input) {
      composition = input;
      return { provider };
    },
    createRegistry({ servicesByAdapter }) {
      services = servicesByAdapter["outbound-luma-rsvp"];
      return { hasCapability: () => false };
    },
  });
  assert.equal(composition.dailyDriver, dailyDriver);
  assert.equal(composition.auth, auth);
  assert.equal(services.provider, provider);
});

test("marketing observation worker reads one tenant receipt and preserves empty analytics as unavailable", async () => {
  const publicationJobId = `marketing-daily:${"a".repeat(64)}`;
  const calls = [];
  const handlers = createWorkerHandlers(
    {
      LM_RUNTIME_TENANT_ID: "tenant-a",
      LM_POSTIZ_API_KEY: "private-postiz-token",
    },
    ["marketing.observation.collect"],
    {
      async query(sql, params) {
        calls.push({ kind: "query", sql, params });
        return {
          rows: [{
            receipt: {
              schema_version: 1,
              kind: "marketing_daily_distribution",
              status: "published",
              creative_id: "B01",
              platform: "tiktok",
              video_sha256: "b".repeat(64),
              caption_sha256: "c".repeat(64),
              public_url: "https://www.tiktok.com/@life_manager/video/7999999999999999999",
              provider_post_id: "postiz-post-B01",
              provider_route: "postiz",
              provider_reconciled: false,
              published_at: "2026-07-29T12:00:00.000Z",
            },
          }],
        };
      },
      async fetchImpl(url, options) {
        calls.push({
          kind: "fetch",
          url,
          authorizationPresent: options.headers.Authorization.length > 0,
        });
        return {
          ok: true,
          async json() {
            return [];
          },
        };
      },
      now: () => "2026-07-29T14:01:00.000Z",
    },
  );
  const execution = await handlers["marketing.observation.collect"](
    buildMarketingObservationJob({
      tenantId: "tenant-a",
      productId: "life-manager",
      publicationJobId,
      window: "2h",
    }),
  );

  assert.equal(execution.receipt.status, "insufficient");
  assert.equal(execution.receipt.metrics.platform.views.value, null);
  assert.equal(execution.receipt.metrics.product.installs.value, null);
  assert.equal(calls.filter((call) => call.kind === "query").length, 1);
  assert.equal(calls.filter((call) => call.kind === "fetch").length, 1);
  assert.match(calls.find((call) => call.kind === "fetch").url, /analytics\/post\/postiz-post-B01/);
  assert.equal(calls.find((call) => call.kind === "fetch").authorizationPresent, true);
  assert.doesNotMatch(JSON.stringify(execution), /private-postiz-token/);
});

test("marketing video worker selects from tenant-scoped durable history and Life Manager objects", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-runtime-video-"));
  const objectDir = path.join(root, "objects");
  const packPath = path.join(root, "pack.json");
  const mediaPath = path.join(root, "v1.mp4");
  fs.writeFileSync(packPath, `${JSON.stringify({
    schema_version: 1,
    product_id: "honne-ai",
    format_id: "reelclaw",
    form: "relationship-confession",
    locale: "ja",
    title: "Honne",
    hashtags: [],
    hooks: [
      { id: "HJA-001", text: "first", status: "active", prior_used_at: null },
    ],
  })}\n`);
  fs.writeFileSync(mediaPath, Buffer.from("0000ftyp-video"));
  const pack = importContentObject(packPath, { objectDir });
  const media = importContentObject(mediaPath, { objectDir });
  const calls = [];
  const handlers = createWorkerHandlers({
    LM_RUNTIME_TENANT_ID: "tenant-a",
    LM_DATA_DIR: root,
  }, ["marketing.video.generate"], {
    async query(sql, params) {
      calls.push({ sql, params });
      return { rows: [] };
    },
    now: () => "2026-07-30T12:30:01.000Z",
  });
  const execution = await handlers["marketing.video.generate"](
    buildMarketingVideoGenerationJob({
      tenantId: "tenant-a",
      productId: "honne-ai",
      formatId: "reelclaw",
      locale: "ja",
      slot: "2026-07-30T12:30:00.000Z",
      packRef: pack.ref,
      mediaRefs: [media.ref],
    }),
  );

  assert.equal(execution.receipt.kind, "marketing_video_artifact");
  assert.equal(execution.receipt.hook_id, "HJA-001");
  assert.equal(calls.length, 1);
  assert.match(calls[0].sql, /tenant_id = \$1/);
  assert.match(calls[0].sql, /capability = 'marketing\.video\.generate'/);
  assert.match(calls[0].sql, /receipt->>'product_id' = \$2/);
  assert.deepEqual(calls[0].params, [
    "tenant-a",
    "honne-ai",
    "reelclaw",
    "ja",
  ]);
});
