#!/usr/bin/env node
"use strict";

const path = require("node:path");
const http = require("node:http");
const os = require("node:os");
const dns = require("node:dns");
const { randomUUID } = require("node:crypto");
const { spawn, spawnSync: realSpawnSync } = require("node:child_process");

const REQUIRED_SERVICES = [
  "postgres",
  "object-store",
  "migrate",
  "runtime-init",
  "api",
  "scheduler",
  "worker",
];

function parseRuntimeCommand(argv) {
  if (
    !Array.isArray(argv)
    || argv[0] !== "runtime"
    || argv[1] !== "up"
    || argv[2] !== "--mode"
  ) {
    throw new Error("usage: life-manager runtime up --mode local");
  }
  if (argv[3] !== "local" || argv.length !== 4) {
    throw new Error("runtime up currently supports local mode only");
  }
  return { command: "up", mode: "local" };
}

function environmentObject(environment) {
  if (!environment) return {};
  if (!Array.isArray(environment)) return environment;
  return Object.fromEntries(environment.map((entry) => {
    const separator = String(entry).indexOf("=");
    return separator < 0
      ? [String(entry), ""]
      : [String(entry).slice(0, separator), String(entry).slice(separator + 1)];
  }));
}

function validateComposeModel(model) {
  if (!model || !model.services || !model.volumes) {
    throw new Error("local compose model is incomplete");
  }
  for (const service of REQUIRED_SERVICES) {
    if (!model.services[service]) throw new Error(`local compose missing ${service}`);
  }
  for (const service of ["postgres", "object-store", "api", "scheduler", "worker"]) {
    if (!model.services[service].healthcheck) {
      throw new Error(`local compose ${service} healthcheck missing`);
    }
  }
  for (const volume of ["postgres-data", "object-data", "runtime-data"]) {
    if (!Object.prototype.hasOwnProperty.call(model.volumes, volume)) {
      throw new Error(`local compose ${volume} volume missing`);
    }
  }
  const roles = Object.entries(model.services).map(([name, service]) => ({
    name,
    env: environmentObject(service.environment),
  }));
  const schedulers = roles.filter(({ env }) => env.LM_DEPLOYMENT_ROLE === "scheduler");
  if (schedulers.length !== 1) {
    throw new Error("local compose must have exactly one scheduler service");
  }
  const schedulerOwner = String(schedulers[0].env.LM_SCHEDULER_OWNER || "").trim();
  if (!schedulerOwner) throw new Error("local compose scheduler owner missing");
  const workerServices = roles
    .filter(({ env }) => env.LM_DEPLOYMENT_ROLE === "worker")
    .map(({ name }) => name);
  if (workerServices.length < 1) throw new Error("local compose worker missing");
  const api = roles.find(({ env }) => env.LM_DEPLOYMENT_ROLE === "api");
  if (!api) throw new Error("local compose api role missing");
  if (String(api.env.LIFE_RUN_LOOPS) !== "false") {
    throw new Error("local compose api must disable scheduler loops");
  }
  if (String(schedulers[0].env.LIFE_RUN_LOOPS) !== "true") {
    throw new Error("local compose scheduler must enable loops");
  }
  return {
    schedulerService: schedulers[0].name,
    schedulerOwner,
    workerServices,
  };
}

function execute(spawnSync, command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    maxBuffer: 20 * 1024 * 1024,
  });
  if (!result || result.status !== 0) {
    const detail = String((result && result.stderr) || "").trim();
    throw new Error(detail || `${command} failed`);
  }
  return String(result.stdout || "");
}

function runRuntimeUp(options = {}) {
  parseRuntimeCommand(options.argv || []);
  const repoRoot = path.resolve(options.repoRoot || path.join(__dirname, "../../.."));
  const composePath = path.join(repoRoot, "deploy/local/compose.yaml");
  const spawnSync = options.spawnSync || realSpawnSync;
  const base = ["compose", "-f", composePath];
  const rendered = execute(
    spawnSync,
    "docker",
    [...base, "config", "--format", "json"],
    repoRoot,
  );
  let model;
  try {
    model = JSON.parse(rendered);
  } catch {
    throw new Error("docker compose returned invalid JSON");
  }
  const topology = validateComposeModel(model);
  execute(
    spawnSync,
    "docker",
    [...base, "up", "-d", "--build", "--wait"],
    repoRoot,
  );
  return { ok: true, mode: "local", ...topology };
}

function requiredEnv(env, name) {
  const value = String(env[name] || "").trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function buildSchedulerHolderToken(
  ownerId,
  hostname = os.hostname(),
  uuidFactory = randomUUID,
) {
  return `${ownerId}:${hostname}:${uuidFactory()}`;
}

function marketingGenerationDueDate(nowMs, timeZone = "Asia/Tokyo") {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(nowMs)).map(({ type, value }) => [type, value]),
  );
  const hour = Number(parts.hour);
  const minute = Number(parts.minute);
  if (hour < 10 || (hour === 10 && minute < 15)) return null;
  return `${parts.year}-${parts.month}-${parts.day}`;
}

async function listGenerationReceipts(pool, options) {
  const tenantId = String(options && options.tenantId || "").trim();
  const after = String(options && options.after || "").trim();
  if (!tenantId || !Number.isFinite(Date.parse(after))) {
    throw new Error("marketing publication chain scan boundary is invalid");
  }
  const result = await pool.query(`
    SELECT r.receipt
    FROM public.lm_runtime_job_receipts r
    JOIN public.lm_runtime_jobs j
      ON j.job_id = r.job_id
      AND j.tenant_id = r.tenant_id
    WHERE j.tenant_id = $1
      AND j.capability = 'marketing.life-manager.daily.generate'
      AND r.outcome = 'completed'
      AND r.created_at >= $2::timestamptz
      AND r.receipt->>'kind' = 'marketing_daily_generation'
      AND r.receipt->>'status' = 'rendered'
    ORDER BY r.created_at ASC
    LIMIT 100
  `, [tenantId, after]);
  return result.rows.map((row) => row.receipt);
}

async function listObservablePublicationReceipts(pool, options) {
  const tenantId = String(options && options.tenantId || "").trim();
  const after = String(options && options.after || "").trim();
  if (!tenantId || !Number.isFinite(Date.parse(after))) {
    throw new Error("marketing observation chain scan boundary is invalid");
  }
  const result = await pool.query(`
    SELECT j.job_id, r.receipt
    FROM public.lm_runtime_job_receipts r
    JOIN public.lm_runtime_jobs j
      ON j.job_id = r.job_id
      AND j.tenant_id = r.tenant_id
    WHERE j.tenant_id = $1
      AND j.capability = 'marketing.life-manager.daily.publish'
      AND r.outcome = 'completed'
      AND r.created_at >= $2::timestamptz
      AND r.receipt->>'kind' = 'marketing_daily_distribution'
      AND r.receipt->>'status' = 'published'
      AND COALESCE(r.receipt->>'provider_post_id', '') <> ''
      AND COALESCE(r.receipt->>'provider_route', '') <> ''
    ORDER BY r.created_at DESC
    LIMIT 100
  `, [tenantId, after]);
  return result.rows.map((row) => ({
    job_id: row.job_id,
    receipt: row.receipt,
  }));
}

async function listHonneJaShadowGenerationReceipts(pool, options) {
  const tenantId = String(options && options.tenantId || "").trim();
  const after = String(options && options.after || "").trim();
  const productId = String(options && options.productId || "").trim();
  const formatId = String(options && options.formatId || "").trim();
  const locale = String(options && options.locale || "").trim();
  if (
    !tenantId
    || !productId
    || !formatId
    || !locale
    || !Number.isFinite(Date.parse(after))
  ) {
    throw new Error("honne JA shadow scan boundary is invalid");
  }
  const result = await pool.query(`
    SELECT r.receipt
    FROM public.lm_runtime_job_receipts r
    JOIN public.lm_runtime_jobs j
      ON j.job_id = r.job_id
      AND j.tenant_id = r.tenant_id
    WHERE j.tenant_id = $1
      AND j.capability = 'marketing.video.generate'
      AND r.outcome = 'completed'
      AND r.created_at >= $2::timestamptz
      AND r.receipt->>'kind' = 'marketing_video_artifact'
      AND r.receipt->>'status' = 'ready'
      AND r.receipt->>'product_id' = $3
      AND r.receipt->>'format_id' = $4
      AND r.receipt->>'locale' = $5
    ORDER BY r.created_at ASC
    LIMIT 100
  `, [tenantId, after, productId, formatId, locale]);
  return result.rows.map((row) => row.receipt);
}

function createHealthServer(port, state) {
  const server = http.createServer((request, response) => {
    if (request.url !== "/health") {
      response.writeHead(404).end("not found");
      return;
    }
    const ok = state.ready === true && state.error == null;
    response.writeHead(ok ? 200 : 503, { "content-type": "application/json" });
    response.end(JSON.stringify({
      ok,
      role: state.role,
      worker_id: state.workerId,
      capabilities: state.capabilities,
      last_poll_at: state.lastPollAt,
    }));
  });
  server.listen(port, "0.0.0.0");
  return server;
}

function createScopedEnvironmentSecretProvider(env = process.env) {
  const { createSecretProvider } = require("../lib/secret-provider.js");
  const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
  const bindings = new Map([
    ["secret://telegram/bot-token", "LM_TELEGRAM_BOT_TOKEN"],
    ["secret://postiz/api-key", "LM_POSTIZ_API_KEY"],
  ]);
  return createSecretProvider({
    mode: "local",
    keychain: {
      async get(requestTenantId, ref) {
        if (requestTenantId !== tenantId) {
          throw new Error("environment secret tenant scope mismatch");
        }
        const envName = bindings.get(ref);
        if (!envName) throw new Error("environment secret reference is not declared");
        return requiredEnv(env, envName);
      },
      async health() {
        return { ok: true };
      },
    },
  });
}

async function executeCapabilityJob(job, services) {
  const {
    workerId,
    handlers = {},
    heartbeatJob,
    completeJob,
    failJob,
    storeOptions,
    leaseSeconds = 300,
    setIntervalFn,
    clearIntervalFn,
  } = services;
  const identity = {
    tenantId: job.tenant_id,
    jobId: job.job_id,
    attempt: job.attempt,
    workerId,
  };
  const handler = handlers[job.capability];
  if (typeof handler !== "function") {
    if (job.effect_class === "none") {
      await completeJob({
        ...identity,
        receipt: {
          kind: "runtime_noop",
          worker_id: workerId,
          completed_at: new Date().toISOString(),
        },
      }, storeOptions);
      return;
    }
    await failJob({
      ...identity,
      errorCode: "CAPABILITY_ADAPTER_UNAVAILABLE",
      unknownEffect: true,
    }, storeOptions);
    return;
  }
  let leaseHeartbeat;
  if (typeof heartbeatJob === "function") {
    const {
      startRuntimeLeaseHeartbeat,
    } = require("../lib/runtime-lease-heartbeat.js");
    leaseHeartbeat = startRuntimeLeaseHeartbeat({
      ...identity,
      leaseSeconds,
    }, {
      heartbeatJob,
      storeOptions,
      setIntervalFn,
      clearIntervalFn,
    });
  }

  let execution;
  let executionError;
  let heartbeatFailed = false;
  let unknownEffect = false;
  try {
    execution = await handler(job);
    if (!execution || !execution.receipt) {
      throw new Error("capability adapter returned no receipt");
    }
    if (job.capability === "outbound.event.apply") {
      const {
        assertVerifiedOutboundReceipt,
      } = require("../lib/outbound-success.js");
      assertVerifiedOutboundReceipt(execution.receipt, job);
    }
  } catch (error) {
    executionError = error;
    unknownEffect = error && error.unknownEffect === true;
  }
  if (leaseHeartbeat) {
    try {
      await leaseHeartbeat.stop();
    } catch (error) {
      executionError = executionError || error;
      heartbeatFailed = true;
      unknownEffect = unknownEffect || job.effect_class !== "none";
    }
  }
  if (executionError) {
    const connectorCoverageCode = job.capability === "connector.coverage.refresh"
      && /^CONNECTOR_COVERAGE_[A-Z_]+$/.test(String(executionError.code || ""))
      ? executionError.code
      : null;
    const outboundLumaCode = job.capability === "outbound.event.apply"
      && new Set([
        "LUMA_LOGIN_REQUIRED",
        "LUMA_RSVP_UNAVAILABLE",
        "LUMA_FORM_INPUT_REQUIRED",
        "LUMA_EFFECT_UNKNOWN",
      ]).has(String(executionError.code || ""))
      ? executionError.code
      : null;
    await failJob({
      ...identity,
      errorCode: heartbeatFailed
        ? "CAPABILITY_HEARTBEAT_FAILED"
        : connectorCoverageCode || outboundLumaCode || "CAPABILITY_EXECUTION_FAILED",
      unknownEffect,
    }, storeOptions);
    return;
  }
  await completeJob({
    ...identity,
    receipt: execution.receipt,
  }, storeOptions);
}

function createWorkerHandlers(env, capabilities, dependencies = {}) {
  const handlers = {};
  const servicesByAdapter = {};
  if (capabilities.includes("connector.coverage.refresh")) {
    const factory = dependencies.createConnectorCoverageRuntimeServices || (
      require("../lib/connector-coverage-runtime-services.js")
        .createConnectorCoverageRuntimeServices
    );
    const services = dependencies.connectorCoverageServices || factory(env, {
      query: dependencies.query,
      connect: dependencies.connect,
    });
    if (!services || typeof services !== "object" || Array.isArray(services)) {
      throw new Error("Connector coverage refresh services are unavailable");
    }
    servicesByAdapter["connector-coverage-refresh"] = services;
  }
  if (capabilities.includes("report.financial.telegram")) {
    const { readUsdcBalance } = require("../lib/base-usdc-balance.js");
    const secretProvider = createScopedEnvironmentSecretProvider(env);
    servicesByAdapter["financial-report-telegram"] = {
      secretProvider,
      supaUrl: requiredEnv(env, "SUPABASE_URL"),
      supaKey: requiredEnv(env, "SUPABASE_SERVICE_ROLE_KEY"),
      fetchImpl: globalThis.fetch,
      readBalance: (walletAddress) => readUsdcBalance(walletAddress, {
        rpcUrl: String(env.BASE_RPC_URL || "https://mainnet.base.org"),
        fetchImpl: globalThis.fetch,
      }),
    };
  }
  if (capabilities.includes("marketing.life-manager.daily.publish")) {
    const secretProvider = createScopedEnvironmentSecretProvider(env);
    const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
    const dataDir = path.resolve(requiredEnv(env, "LM_DATA_DIR"));
    const runtimeOwnedPath = (name) => {
      const resolved = path.resolve(requiredEnv(env, name));
      if (resolved !== dataDir && !resolved.startsWith(`${dataDir}${path.sep}`)) {
        throw new Error(`${name} must be beneath LM_DATA_DIR`);
      }
      return resolved;
    };
    servicesByAdapter["marketing-life-manager-daily"] = {
      secretProvider,
      profileProvider: {
        async get(requestTenantId, ref) {
          if (requestTenantId !== tenantId || ref !== "profile://instagram/life-manager") {
            throw new Error("Instagram profile tenant scope mismatch");
          }
          return {
            handle: requiredEnv(env, "LM_INSTAGRAM_HANDLE"),
            accountsPath: runtimeOwnedPath("LM_INSTAGRAM_ACCOUNTS_PATH"),
            settingsPath: runtimeOwnedPath("LM_INSTAGRAM_SETTINGS_PATH"),
            credentialsPath: runtimeOwnedPath("LM_INSTAGRAM_CREDENTIALS_PATH"),
            stateDir: runtimeOwnedPath("LM_INSTAGRAM_PROFILE_STATE_DIR"),
          };
        },
      },
      integrationProvider: {
        async get(requestTenantId, ref) {
          if (
            requestTenantId !== tenantId
            || ref !== "integration://postiz/tiktok/life-manager"
          ) {
            throw new Error("TikTok integration tenant scope mismatch");
          }
          return requiredEnv(env, "LM_TIKTOK_INTEGRATION");
        },
      },
    };
  }
  if (capabilities.includes("marketing.life-manager.daily.generate")) {
    servicesByAdapter["marketing-life-manager-daily-generation"] = {
      dataDir: path.resolve(requiredEnv(env, "LM_DATA_DIR")),
      pythonBin: String(env.PYTHON_BIN || "python3"),
    };
  }
  if (capabilities.includes("marketing.video.generate")) {
    const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
    const query = dependencies.query;
    if (typeof query !== "function") {
      throw new Error("marketing video generation receipt store is unavailable");
    }
    servicesByAdapter["marketing-video-generation"] = {
      dataDir: path.resolve(requiredEnv(env, "LM_DATA_DIR")),
      historyProvider: {
        async list(request) {
          if (
            !request
            || request.tenantId !== tenantId
            || !request.productId
            || !request.formatId
            || !request.locale
          ) {
            throw new Error("marketing video generation history scope mismatch");
          }
          const result = await query(`
            SELECT r.receipt
            FROM public.lm_runtime_job_receipts r
            JOIN public.lm_runtime_jobs j
              ON j.job_id = r.job_id
              AND j.tenant_id = r.tenant_id
            WHERE r.tenant_id = $1
              AND j.capability = 'marketing.video.generate'
              AND r.outcome = 'completed'
              AND r.receipt->>'kind' = 'marketing_video_artifact'
              AND r.receipt->>'product_id' = $2
              AND r.receipt->>'format_id' = $3
              AND r.receipt->>'locale' = $4
            ORDER BY r.created_at ASC
            LIMIT 500
          `, [
            tenantId,
            request.productId,
            request.formatId,
            request.locale,
          ]);
          return result.rows.map((row) => row.receipt);
        },
      },
      now: dependencies.now || (() => new Date().toISOString()),
    };
  }
  if (capabilities.includes("marketing.observation.collect")) {
    const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
    const query = dependencies.query;
    if (typeof query !== "function") {
      throw new Error("marketing observation receipt store is unavailable");
    }
    const fetchImpl = dependencies.fetchImpl || globalThis.fetch;
    const secretProvider = createScopedEnvironmentSecretProvider(env);
    const {
      normalizePostizMetrics,
    } = require("../lib/marketing-observation-adapter.js");
    const unavailablePlatform = () => ({
      views: { status: "unavailable", value: null, reason: "metric_not_supported" },
      likes: { status: "unavailable", value: null, reason: "metric_not_supported" },
      comments: { status: "unavailable", value: null, reason: "metric_not_supported" },
      shares: { status: "unavailable", value: null, reason: "metric_not_supported" },
    });
    servicesByAdapter["marketing-platform-observation"] = {
      receiptProvider: {
        async get(requestTenantId, ref) {
          const match = /^runtime-receipt:\/\/(marketing-daily:[0-9a-f]{64})$/.exec(
            String(ref || ""),
          );
          if (requestTenantId !== tenantId || !match) {
            throw new Error("marketing observation receipt scope mismatch");
          }
          const rows = (await query(`
            SELECT r.receipt
            FROM public.lm_runtime_job_receipts r
            JOIN public.lm_runtime_jobs j
              ON j.job_id = r.job_id
              AND j.tenant_id = r.tenant_id
            WHERE r.tenant_id = $1
              AND r.job_id = $2
              AND r.outcome = 'completed'
              AND j.capability = 'marketing.life-manager.daily.publish'
            ORDER BY r.attempt DESC
            LIMIT 1
          `, [requestTenantId, match[1]])).rows;
          if (rows.length !== 1) {
            throw new Error("marketing publication receipt is unavailable");
          }
          return rows[0].receipt;
        },
      },
      platformMetricProvider: {
        async collect({ publication, window }) {
          if (publication.provider_route !== "postiz") {
            return unavailablePlatform();
          }
          const token = await secretProvider.get(
            tenantId,
            "secret://postiz/api-key",
          );
          const days = { "2h": 1, "24h": 1, "72h": 3, "7d": 7 }[window];
          const response = await fetchImpl(
            `https://api.postiz.com/public/v1/analytics/post/${
              encodeURIComponent(publication.provider_post_id)
            }?date=${days}`,
            {
              headers: { Authorization: token },
              signal: AbortSignal.timeout(30_000),
            },
          );
          if (!response || response.ok !== true) {
            throw new Error("Postiz metric request failed");
          }
          return normalizePostizMetrics(await response.json());
        },
      },
      productMetricProvider: {
        async collect() {
          const value = {
            status: "unavailable",
            value: null,
            reason: "attribution_not_configured",
          };
          return {
            installs: { ...value },
            activations: { ...value },
            trials: { ...value },
            paid: { ...value },
            proceeds_minor: { ...value },
          };
        },
      },
      now: dependencies.now || (() => new Date().toISOString()),
    };
  }
  if (capabilities.includes("outbound.event.apply")) {
    const { createLumaEvidenceStore } = require("../lib/luma-evidence-store.js");
    const evidenceStore = dependencies.lumaEvidenceStore || createLumaEvidenceStore({
      dataDir: path.resolve(requiredEnv(env, "LM_DATA_DIR")),
    });
    let provider = dependencies.lumaProvider;
    if (!provider) {
      const { chromium } = require("playwright-core");
      const {
        createCloakBrowserDailyDriver,
      } = require("../lib/cloakbrowser-daily-driver.js");
      const lookup = dependencies.lookupHost || dns.promises.lookup;
      const dailyDriver = dependencies.lumaDailyDriver || createCloakBrowserDailyDriver({
        connectOverCDP: dependencies.connectOverCDP
          || ((endpoint) => chromium.connectOverCDP(endpoint)),
        resolveEndpoint: dependencies.resolveCloakEndpoint || (async () => {
          const resolved = await lookup("host.docker.internal", { family: 4 });
          const address = typeof resolved === "string" ? resolved : resolved.address;
          return `http://${address}:9222`;
        }),
      });
      const {
        createReadOnlyLumaSessionAuth,
      } = require("../lib/luma-daily-driver-auth.js");
      const {
        createConnectorEventsPack,
      } = require("../lib/connector-events-pack.js");
      const auth = dependencies.lumaAuth || createReadOnlyLumaSessionAuth({ dailyDriver });
      const pack = (dependencies.createConnectorEventsPack || createConnectorEventsPack)({
        dailyDriver,
        auth,
        evidenceStore,
        now: dependencies.now,
      });
      provider = pack.provider;
    }
    servicesByAdapter["outbound-luma-rsvp"] = {
      provider,
      readExternalReceipt: evidenceStore.readExternalReceipt,
      readArtifact: evidenceStore.readArtifact,
      fetchImpl: dependencies.fetchImpl || globalThis.fetch,
      now: dependencies.now,
    };
  }
  const createRegistry = dependencies.createRegistry || (
    require("../lib/loop-adapter-registry.js").createConfiguredLoopAdapterRegistry
  );
  const registry = createRegistry({ servicesByAdapter });
  for (const capability of capabilities) {
    if (!registry.hasCapability(capability)) continue;
    const adapter = registry.getByCapability(capability);
    handlers[capability] = (job) => adapter.execute(job);
  }
  return handlers;
}

function observeWorkerPoll(state, active, now = () => new Date().toISOString()) {
  const observedAt = String(now());
  if (!Number.isFinite(Date.parse(observedAt))) {
    throw new Error("worker poll timestamp is invalid");
  }
  state.lastPollAt = observedAt;
  return active !== true;
}

async function runCapabilityWorker(env = process.env) {
  const { Pool } = require("pg");
  const {
    claimJobs,
    heartbeatJob,
    completeJob,
    failJob,
  } = require("../lib/runtime-job-store.js");
  const connectionString = requiredEnv(env, "LM_RUNTIME_DATABASE_URL");
  const capabilities = requiredEnv(env, "LM_WORKER_CAPABILITIES")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (capabilities.length < 1) throw new Error("LM_WORKER_CAPABILITIES is empty");
  const workerId = String(env.LM_WORKER_ID || os.hostname()).trim();
  const pool = new Pool({ connectionString, max: 2 });
  const opts = { query: pool.query.bind(pool) };
  const handlers = createWorkerHandlers(env, capabilities, {
    query: opts.query,
    connect: pool.connect.bind(pool),
  });
  const state = {
    role: "worker",
    workerId,
    capabilities,
    ready: false,
    error: null,
    lastPollAt: null,
  };
  const health = createHealthServer(Number(env.LM_WORKER_HEALTH_PORT || 8790), state);
  const leaseSeconds = Number(env.LM_WORKER_LEASE_SECONDS || 300);
  let active = false;

  async function tick() {
    if (!observeWorkerPoll(state, active)) return;
    active = true;
    try {
      await pool.query("SELECT 1");
      const jobs = await claimJobs({
        workerId,
        capabilities,
        limit: 1,
        leaseSeconds,
      }, opts);
      for (const job of jobs) {
        await executeCapabilityJob(job, {
          workerId,
          handlers,
          heartbeatJob,
          completeJob,
          failJob,
          storeOptions: opts,
          leaseSeconds,
        });
      }
      state.ready = true;
      state.error = null;
      state.lastPollAt = new Date().toISOString();
    } catch (error) {
      state.error = error;
    } finally {
      active = false;
    }
  }

  await tick();
  const timer = setInterval(tick, Number(env.LM_WORKER_POLL_MS || 1000));
  const stop = async () => {
    clearInterval(timer);
    health.close();
    await pool.end();
  };
  process.once("SIGTERM", () => stop().finally(() => process.exit(0)));
  process.once("SIGINT", () => stop().finally(() => process.exit(0)));
}

async function runSchedulerOwner(env = process.env) {
  const { Pool } = require("pg");
  const connectionString = requiredEnv(env, "LM_RUNTIME_DATABASE_URL");
  const schedulerKey = String(env.LM_SCHEDULER_LEASE_KEY || "primary").trim();
  const ownerId = requiredEnv(env, "LM_SCHEDULER_OWNER");
  const holderToken = buildSchedulerHolderToken(ownerId);
  const leaseSeconds = Number(env.LM_SCHEDULER_LEASE_SECONDS || 30);
  const pool = new Pool({ connectionString, max: 1 });
  const claim = await pool.query(
    "SELECT * FROM public.claim_lm_runtime_scheduler_owner($1, $2, $3, $4)",
    [schedulerKey, ownerId, holderToken, leaseSeconds],
  );
  if (claim.rows.length !== 1) {
    await pool.end();
    throw new Error("scheduler owner lease is already held");
  }

  const financialTenant = String(env.LM_RUNTIME_TENANT_ID || "").trim();
  const financialIntervalMs = Number(env.LM_FINANCIAL_REPORT_POLL_MS || 300000);
  let forceOnNextFinancialEnqueue = String(
    env.LM_FINANCIAL_REPORT_FORCE_ON_START || "",
  ).trim();
  let financialTimer;
  async function enqueueFinancialReports() {
    if (!financialTenant) return;
    const { enqueueJob } = require("../lib/runtime-job-store.js");
    const { enqueueFinancialReportJobs } = require("../lib/report-job-adapter.js");
    const slotMs = Math.floor(Date.now() / financialIntervalMs) * financialIntervalMs;
    const args = ["enqueue", "--uid", financialTenant];
    const force = forceOnNextFinancialEnqueue;
    if (force) args.push("--force", force);
    forceOnNextFinancialEnqueue = "";
    await enqueueFinancialReportJobs(args, env, {
      nowMs: slotMs,
      enqueueJob: (input) => enqueueJob(input, { query: pool.query.bind(pool) }),
      stdout: { write() {} },
    });
  }
  await enqueueFinancialReports();
  if (financialTenant) {
    financialTimer = setInterval(() => {
      enqueueFinancialReports().catch(() => {});
    }, financialIntervalMs);
  }

  const marketingGenerationEnabled = String(
    env.LM_MARKETING_GENERATION_ENABLED || "false",
  ).trim().toLowerCase() === "true";
  const marketingGenerationPollMs = Number(
    env.LM_MARKETING_GENERATION_POLL_MS || 60000,
  );
  let marketingGenerationTimer;
  async function enqueueMarketingGeneration() {
    if (!marketingGenerationEnabled) return;
    const date = marketingGenerationDueDate(
      Date.now(),
      String(env.LM_MARKETING_GENERATION_TIME_ZONE || "Asia/Tokyo"),
    );
    if (!date) return;
    const { enqueueJob } = require("../lib/runtime-job-store.js");
    const {
      buildMarketingDailyGenerationJob,
    } = require("../lib/marketing-daily-generation-adapter.js");
    const job = buildMarketingDailyGenerationJob({
      tenantId: requiredEnv(env, "LM_RUNTIME_TENANT_ID"),
      date,
      bankRef: requiredEnv(env, "LM_MARKETING_GENERATION_BANK_REF"),
      callAudioRef: requiredEnv(env, "LM_MARKETING_GENERATION_CALL_AUDIO_REF"),
      stockRef: requiredEnv(env, "LM_MARKETING_GENERATION_STOCK_REF"),
      telegramProofRef: requiredEnv(env, "LM_MARKETING_GENERATION_TELEGRAM_PROOF_REF"),
      whisperAssRef: requiredEnv(env, "LM_MARKETING_GENERATION_WHISPER_ASS_REF"),
    });
    await enqueueJob({
      jobId: job.job_id,
      tenantId: job.tenant_id,
      loopId: job.loop_id,
      capability: job.capability,
      effectClass: job.effect_class,
      effectKey: job.effect_key,
      inputRefs: job.input_refs,
      maxAttempts: job.max_attempts,
    }, { query: pool.query.bind(pool) });
  }
  await enqueueMarketingGeneration();
  if (marketingGenerationEnabled) {
    marketingGenerationTimer = setInterval(() => {
      enqueueMarketingGeneration().catch(() => {});
    }, marketingGenerationPollMs);
  }

  const publicationChainEnabled = String(
    env.LM_MARKETING_PUBLICATION_CHAIN_ENABLED || "false",
  ).trim().toLowerCase() === "true";
  const publicationChainPollMs = Number(
    env.LM_MARKETING_PUBLICATION_CHAIN_POLL_MS || 60000,
  );
  let publicationChainTimer;
  let publicationChainActive = false;
  async function enqueueGeneratedPublications() {
    if (!publicationChainEnabled || publicationChainActive) return;
    publicationChainActive = true;
    try {
      const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
      const after = requiredEnv(env, "LM_MARKETING_PUBLICATION_CHAIN_AFTER");
      const receipts = await listGenerationReceipts(pool, { tenantId, after });
      const {
        enqueueGenerationPublications,
      } = require("../lib/marketing-publication-chain.js");
      const { enqueueJob } = require("../lib/runtime-job-store.js");
      for (const receipt of receipts) {
        await enqueueGenerationPublications(receipt, {
          tenantId,
          captionRef: requiredEnv(env, "LM_MARKETING_PUBLICATION_CHAIN_CAPTION_REF"),
          approvalRef: requiredEnv(env, "LM_MARKETING_PUBLICATION_CHAIN_APPROVAL_REF"),
        }, {
          enqueueJob: (input) => enqueueJob(input, {
            query: pool.query.bind(pool),
          }),
        });
      }
    } finally {
      publicationChainActive = false;
    }
  }
  await enqueueGeneratedPublications();
  if (publicationChainEnabled) {
    publicationChainTimer = setInterval(() => {
      enqueueGeneratedPublications().catch(() => {});
    }, publicationChainPollMs);
  }

  const observationEnabled = String(
    env.LM_MARKETING_OBSERVATION_ENABLED || "false",
  ).trim().toLowerCase() === "true";
  const observationPollMs = Number(
    env.LM_MARKETING_OBSERVATION_POLL_MS || 60000,
  );
  let observationTimer;
  let observationActive = false;
  async function enqueuePublicationObservations() {
    if (!observationEnabled || observationActive) return;
    observationActive = true;
    try {
      const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
      const publications = await listObservablePublicationReceipts(pool, {
        tenantId,
        after: requiredEnv(env, "LM_MARKETING_OBSERVATION_AFTER"),
      });
      const {
        enqueueDueObservations,
      } = require("../lib/marketing-observation-chain.js");
      const { enqueueJob } = require("../lib/runtime-job-store.js");
      const nowMs = Date.now();
      for (const publication of publications) {
        await enqueueDueObservations(publication, {
          tenantId,
          productId: requiredEnv(env, "LM_MARKETING_OBSERVATION_PRODUCT_ID"),
          nowMs,
        }, {
          enqueueJob: (input) => enqueueJob(input, {
            query: pool.query.bind(pool),
          }),
        });
      }
    } finally {
      observationActive = false;
    }
  }
  await enqueuePublicationObservations();
  if (observationEnabled) {
    observationTimer = setInterval(() => {
      enqueuePublicationObservations().catch(() => {});
    }, observationPollMs);
  }

  // Honne JA shadow slice — DEFAULT OFF (spec Order 11). The legacy launchd
  // owner ai.anicca.reelclaw-honne-ja keeps firing at 12:30/21:30 JST; this
  // wiring encodes the identical slots and only runs when
  // LM_HONNE_JA_SHADOW_ENABLED=true is deliberately configured. Generation is
  // enqueued for real (no-effect producer); publication jobs are enqueued and
  // HELD (shadow_held) — no worker is granted marketing.video.publish here, so
  // no Instagram/TikTok/Postiz call can happen in shadow.
  const {
    honneJaShadowConfig,
    planHonneJaShadowGeneration,
    holdHonneJaShadowPublications,
    appendHonneJaShadowHold,
  } = require("../lib/honne-ja-shadow-runtime.js");
  const honneJaShadow = honneJaShadowConfig(env);
  const honneJaShadowPollMs = Number(env.LM_HONNE_JA_SHADOW_POLL_MS || 60000);
  let honneJaShadowTimer;
  let honneJaShadowActive = false;
  async function runHonneJaShadowScan() {
    if (!honneJaShadow.enabled || honneJaShadowActive) return;
    honneJaShadowActive = true;
    try {
      const { enqueueJob } = require("../lib/runtime-job-store.js");
      const storeOptions = { query: pool.query.bind(pool) };
      const job = planHonneJaShadowGeneration(honneJaShadow, Date.now());
      if (job) {
        await enqueueJob({
          jobId: job.job_id,
          tenantId: job.tenant_id,
          loopId: job.loop_id,
          capability: job.capability,
          effectClass: job.effect_class,
          effectKey: job.effect_key,
          inputRefs: job.input_refs,
          maxAttempts: job.max_attempts,
        }, storeOptions);
      }
      const receipts = await listHonneJaShadowGenerationReceipts(pool, {
        tenantId: honneJaShadow.tenantId,
        productId: honneJaShadow.productId,
        formatId: honneJaShadow.formatId,
        locale: honneJaShadow.locale,
        after: requiredEnv(env, "LM_HONNE_JA_SHADOW_AFTER"),
      });
      for (const receipt of receipts) {
        await holdHonneJaShadowPublications(receipt, honneJaShadow, {
          enqueueJob,
          storeOptions,
          appendHold: (hold) => appendHonneJaShadowHold(hold, {
            dataDir: requiredEnv(env, "LM_DATA_DIR"),
            tenantId: honneJaShadow.tenantId,
            productId: honneJaShadow.productId,
          }),
        });
      }
    } finally {
      honneJaShadowActive = false;
    }
  }
  await runHonneJaShadowScan();
  if (honneJaShadow.enabled) {
    honneJaShadowTimer = setInterval(() => {
      runHonneJaShadowScan().catch(() => {});
    }, honneJaShadowPollMs);
  }

  const child = spawn(process.execPath, ["server.js"], {
    cwd: path.join(__dirname, ".."),
    env: {
      ...env,
      LM_DEPLOYMENT_ROLE: "scheduler",
      LM_SCHEDULER_OWNER: ownerId,
      LIFE_RUN_LOOPS: "true",
    },
    stdio: "inherit",
  });
  let stopping = false;
  const renew = setInterval(async () => {
    try {
      const heartbeat = await pool.query(
        "SELECT * FROM public.heartbeat_lm_runtime_scheduler_owner($1, $2, $3)",
        [schedulerKey, holderToken, leaseSeconds],
      );
      if (heartbeat.rows.length !== 1 && !stopping) child.kill("SIGTERM");
    } catch {
      if (!stopping) child.kill("SIGTERM");
    }
  }, Math.max(1000, Math.floor(leaseSeconds * 1000 / 3)));

  const stop = async (signal) => {
    if (stopping) return;
    stopping = true;
    clearInterval(renew);
    if (financialTimer) clearInterval(financialTimer);
    if (marketingGenerationTimer) clearInterval(marketingGenerationTimer);
    if (publicationChainTimer) clearInterval(publicationChainTimer);
    if (observationTimer) clearInterval(observationTimer);
    if (honneJaShadowTimer) clearInterval(honneJaShadowTimer);
    if (!child.killed) child.kill(signal || "SIGTERM");
    try {
      await pool.query(
        "SELECT public.release_lm_runtime_scheduler_owner($1, $2)",
        [schedulerKey, holderToken],
      );
    } finally {
      await pool.end();
    }
  };
  process.once("SIGTERM", () => stop("SIGTERM"));
  process.once("SIGINT", () => stop("SIGINT"));
  child.once("exit", (code, signal) => {
    stop(signal || "SIGTERM").finally(() => {
      process.exitCode = Number.isInteger(code) ? code : 1;
    });
  });
}

async function main(argv = process.argv.slice(2)) {
  if (argv[0] === "internal-worker") return runCapabilityWorker();
  if (argv[0] === "internal-scheduler") return runSchedulerOwner();
  const result = runRuntimeUp({ argv });
  process.stdout.write(`${JSON.stringify(result)}\n`);
  return result;
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  parseRuntimeCommand,
  validateComposeModel,
  runRuntimeUp,
  buildSchedulerHolderToken,
  marketingGenerationDueDate,
  listGenerationReceipts,
  listHonneJaShadowGenerationReceipts,
  listObservablePublicationReceipts,
  createScopedEnvironmentSecretProvider,
  createWorkerHandlers,
  observeWorkerPoll,
  executeCapabilityJob,
  runCapabilityWorker,
  runSchedulerOwner,
};
