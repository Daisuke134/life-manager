"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createHash } = require("node:crypto");
const { spawnSync } = require("node:child_process");
const {
  executeCapabilityJob,
  createScopedEnvironmentSecretProvider,
  createMaritimeManagerWorkerDependencies,
  createMaritimeCapafyAccountBinding,
  createWorkerHandlers,
  observeWorkerPoll,
  reconcileMaritimeCapabilityJobs,
  recoverMaritimeEnrollments,
  recoverReconsentedMaritimeConfigurations,
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
const MONEY_TENANT = "tenant-a";
const MONEY_OPPORTUNITY_ID = "a".repeat(64);
const MONEY_GOAL_REF = `intent-entry://${MONEY_TENANT}/${MONEY_OPPORTUNITY_ID}`;

test("a continuation is activated only after durable current-job completion", async () => {
  const order = [];
  await executeCapabilityJob({ tenant_id: "tenant-a", job_id: "job-a", attempt: 1,
    capability: "agent-economy.start", effect_class: "money" }, {
    workerId: "worker-a",
    handlers: { "agent-economy.start": async () => ({
      receipt: { kind: "agent_economy_wake", status: "completed" },
      continuation: { job: { job_id: "next" }, availableAt: "2026-09-11T00:05:00.000Z" },
    }) },
    completeJob: async () => { throw new Error("non-atomic completion used"); },
    completeJobAndEnqueue: async (input) => { order.push("atomic"); assert.equal(input.nextJob.job_id, "next"); },
    failJob: async () => { throw new Error("unexpected failure"); },
  });
  assert.deepEqual(order, ["atomic"]);
});
const MONEY_JOB_ID = `goal:${MONEY_OPPORTUNITY_ID}`;

test("active capability work refreshes worker liveness without starting a second claim", () => {
  const state = { lastPollAt: "2026-08-01T00:00:00.000Z" };
  assert.equal(observeWorkerPoll(state, true, () => "2026-08-01T00:01:00.000Z"), false);
  assert.equal(state.lastPollAt, "2026-08-01T00:01:00.000Z");
  assert.equal(observeWorkerPoll(state, false, () => "2026-08-01T00:02:00.000Z"), true);
  assert.equal(state.lastPollAt, "2026-08-01T00:02:00.000Z");
});

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

test("Railway start command routes the worker role to internal-worker", () => {
  const railway = fs.readFileSync(path.join(ROOT, "apps/life-manager/railway.toml"), "utf8");
  const match = railway.match(/^startCommand = "((?:\\.|[^"])*)"$/m);
  assert.ok(match, "railway.toml must define a startCommand");
  assert.equal(
    match[1].replace(/\\"/g, '"'),
    'if [ "$LM_DEPLOYMENT_ROLE" = "worker" ]; then exec node scripts/runtime-up.js internal-worker; else exec node server.js; fi',
  );
});

test("Agent Economy Cloud worker packages the shared monorepo runtime without Docker", () => {
  const config = fs.readFileSync(path.join(ROOT, "railway.worker.toml"), "utf8");
  assert.match(config, /npm ci --ignore-scripts --prefix apps\/life-manager/);
  assert.match(config, /npm ci --ignore-scripts --prefix skills\/earn\/taskmarket/);
  assert.match(config, /nixpacksConfigPath = "nixpacks\.worker\.toml"/);
  const nixpacks = fs.readFileSync(path.join(ROOT, "nixpacks.worker.toml"), "utf8");
  assert.match(nixpacks, /nixPkgs = \["\.\.\.", "python3", "curl"\]/);
  assert.doesNotMatch(fs.readFileSync(path.join(ROOT, "skills/earn/taskmarket/run.sh"), "utf8"), /homebrew/);
  assert.match(config, /node apps\/life-manager\/scripts\/runtime-up\.js internal-worker/);
  assert.doesNotMatch(config, /docker/i);
  assert.equal(fs.existsSync(path.join(ROOT, "runtime/loop/index.mjs")), true);
  assert.equal(fs.existsSync(path.join(ROOT, "skills/earn/run.sh")), true);
  const buildIgnore = fs.readFileSync(path.join(ROOT, ".dockerignore"), "utf8");
  assert.match(buildIgnore, /!runtime\/loop\/\*\*/);
  assert.doesNotMatch(buildIgnore, /^!runtime\/\*\*$/m);
  assert.match(buildIgnore, /!skills\/registry\.json/);
  assert.doesNotMatch(buildIgnore, /^!skills\/\*\*$/m);
  const ignoreProbe = fs.mkdtempSync(path.join(os.tmpdir(), "lm-worker-ignore-"));
  fs.writeFileSync(path.join(ignoreProbe, ".gitignore"), buildIgnore);
  spawnSync("git", ["init", "--quiet"], { cwd: ignoreProbe });
  const checkIgnored = (relativePath) => {
    const absolutePath = path.join(ignoreProbe, relativePath);
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    fs.writeFileSync(absolutePath, "probe");
    return spawnSync(
      "git",
      ["check-ignore", "--no-index", "--quiet", relativePath],
      { cwd: ignoreProbe },
    ).status === 0;
  };
  for (const requiredPath of [
    "package.json",
    "package-lock.json",
    "runtime/loop/index.mjs",
    "runtime/contracts/citizen-identity.cjs",
    "runtime/contracts/common-record.cjs",
    "skills/registry.json",
    "skills/earn/run.sh",
    "skills/earn/lib/resolve-identity.mjs",
    "skills/earn/taskmarket/package.json",
    "skills/_shared/lib/earn-guard.mjs",
    "services/x402-endpoint/prisma/schema.prisma",
    "services/x402-endpoint/package.json",
    "services/x402-endpoint/package-lock.json",
    "services/x402-endpoint/pnpm-lock.yaml",
    "skills/earn/x402-sell/package.json",
    "runtime/compute-proxy/package-lock.json",
    "skills/video/lm-assets/package.json",
  ]) {
    assert.equal(checkIgnored(requiredPath), false, `${requiredPath} must be in the Railway build context`);
  }
  for (const excludedPath of [
    "runtime/loop/__tests__/wake.test.mjs",
    "runtime/loop/test/wake.test.mjs",
    "runtime/contracts/test_common_contracts.py",
    "runtime/agentmail/test-replier.sh",
    "runtime/loop/state/probe.jsonl",
    "runtime/README.md",
    "skills/earn/lib/__tests__/net-worth.test.mjs",
    "skills/earn/test/fixture.js",
    "skills/browser/scripts/test_session_vault.py",
    "skills/writer-agent/reference/private.json",
    "skills/x-repost/x-repost-cli.sh",
    "skills/resource-resolver/run.sh",
    "skills/report/anicca-report.sh",
    "skills/cook/run.sh",
    "skills/earn/polymarket-trade/run.sh",
    "skills/earn/x402-sell/run.sh",
    "skills/self/spawn/run.sh",
    "skills/earn/README.md",
    "skills/earn/references/provider.md",
    "skills/earn/state/earn-ledger.jsonl",
    "skills/earn/x402-sell/node_modules/example.js",
    "skills/earn/.env",
    "skills/earn/.env.production",
  ]) {
    assert.equal(checkIgnored(excludedPath), true, `${excludedPath} must stay out of the Railway build context`);
  }
  fs.rmSync(ignoreProbe, { recursive: true, force: true });
});

test("runtime worker entrypoint fails closed for every non-worker argv", () => {
  const script = path.join(ROOT, "apps/life-manager/scripts/runtime-up.js");
  for (const argv of [[], ["internal-scheduler"], ["internal-liveness"], ["runtime", "up"]]) {
    const result = spawnSync(process.execPath, [script, ...argv], { encoding: "utf8" });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /usage: runtime-up\.js internal-worker/);
  }
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

test("financial worker passes its injected Postgres boundary to the shared Financial Manager adapter", () => {
  const query = async () => ({ rows: [] });
  const readBalance = async () => "0";
  let financialServices;
  createWorkerHandlers({
    LM_RUNTIME_TENANT_ID: "tenant-a",
    LM_TELEGRAM_BOT_TOKEN: "telegram-token",
    SUPABASE_URL: "https://supa.example",
    SUPABASE_SERVICE_ROLE_KEY: "service-key",
  }, ["report.financial.telegram"], {
    query,
    readBalance,
    createRegistry({ servicesByAdapter }) {
      financialServices = servicesByAdapter["financial-report-telegram"];
      return {
        hasCapability: (capability) => capability === "report.financial.telegram",
        getByCapability: () => ({ execute: async () => ({ receipt: { status: "skipped" } }) }),
      };
    },
  });
  assert.equal(financialServices.query, query);
  assert.equal(financialServices.readBalance, readBalance);
});

test("general money worker wires its injected bounded specialist through the registry", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-runtime-money-specialist-"));
  const specialist = async (expected) => ({
    kind: "general_agent_work",
    status: "completed",
    tenant_id: expected.tenant_id,
    job_id: expected.job_id,
    goal_ref: expected.goal_ref,
    execution_id: "execution-runtime-1",
    next_job_refs: [],
  });
  let services;
  const handlers = createWorkerHandlers({
    SUPABASE_URL: "https://supa.example",
    SUPABASE_SERVICE_ROLE_KEY: "service-secret",
    LM_DATA_DIR: dataDir,
  }, ["general-agent.work"], {
    moneyPrinterSpecialist: specialist,
    createRegistry({ servicesByAdapter }) {
      services = servicesByAdapter["general-agent-work"];
      return {
        hasCapability: (capability) => capability === "general-agent.work",
        getByCapability: () => ({
          execute: async (job) => ({
            receipt: await services.runBoundedSpecialist({
              tenant_id: job.tenant_id,
              job_id: job.job_id,
              goal_ref: job.input_refs.goal_ref,
            }),
          }),
        }),
      };
    },
  });
  const job = {
    tenant_id: MONEY_TENANT,
    job_id: MONEY_JOB_ID,
    loop_id: "life-manager.manager",
    capability: "general-agent.work",
    effect_class: "none",
    effect_key: null,
    input_refs: { goal_ref: MONEY_GOAL_REF },
    max_attempts: 1,
  };

  assert.equal(services.runBoundedSpecialist, specialist);
  assert.deepEqual(await handlers["general-agent.work"](job), {
    receipt: await specialist({
      tenant_id: MONEY_TENANT,
      job_id: MONEY_JOB_ID,
      goal_ref: MONEY_GOAL_REF,
    }),
  });
});

test("money scout worker requires its cloud/runtime boundary and routes only runScout through the registry", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-runtime-money-scout-"));
  assert.throws(() => createWorkerHandlers({ LM_DATA_DIR: dataDir }, ["money-printer.scout"], {
    createRegistry() { return { hasCapability: () => false }; },
  }), /GEMINI_API_KEY is required/);
  let options;
  let services;
  const scout = async (expected) => ({
    kind: "money_printer_scout", status: "completed", tenant_id: expected.tenant_id,
    job_id: expected.job_id, cycle_ref: expected.cycle_ref,
    discovered_count: 0, created_count: 0, deduped_count: 0, opportunity_refs: [],
  });
  const handlers = createWorkerHandlers({
    GEMINI_API_KEY: "gemini-secret-key", LM_DATA_DIR: dataDir,
    LM_REPO_ROOT: "/app", LM_MONEY_SCOUT_TENANT_ID: MONEY_TENANT,
  }, ["money-printer.scout"], {
    query: async () => ({ rows: [] }),
    createMoneyPrinterScout(input) { options = input; return scout; },
    createRegistry({ servicesByAdapter }) {
      services = servicesByAdapter["money-printer-scout"];
      return {
        hasCapability: (capability) => capability === "money-printer.scout",
        getByCapability: () => ({
          execute: async (job) => ({ receipt: await services.runScout({
            tenant_id: job.tenant_id, job_id: job.job_id, cycle_ref: job.input_refs.cycle_ref,
          }) }),
        }),
      };
    },
  });
  const job = {
    tenant_id: MONEY_TENANT, job_id: `money-printer-scout:${"a".repeat(64)}`,
    loop_id: "life-manager.manager", capability: "money-printer.scout",
    effect_class: "none", effect_key: null, max_attempts: 2,
    input_refs: { cycle_ref: `money-printer-scout://${MONEY_TENANT}/0` },
  };
  assert.equal(options.apiKey, "gemini-secret-key");
  assert.equal(options.tenantId, MONEY_TENANT);
  assert.equal(typeof options.readOpportunityBySource, "function");
  assert.equal(typeof options.createOpportunity, "function");
  assert.equal(services.runScout, scout);
  assert.deepEqual(await handlers["money-printer.scout"](job), { receipt: await scout({
    tenant_id: MONEY_TENANT, job_id: job.job_id, cycle_ref: job.input_refs.cycle_ref,
  }) });
});

test("production general money worker fails before query, factory, registry, or effects without Gemini", () => {
  const calls = [];
  assert.throws(() => createWorkerHandlers({
    LM_DATA_DIR: fs.mkdtempSync(path.join(os.tmpdir(), "lm-runtime-money-missing-gemini-")),
  }, ["general-agent.work"], {
    async query() { calls.push("query"); return { rows: [] }; },
    createMoneyPrinterSpecialist() { calls.push("factory"); return async () => {}; },
    createRegistry() { calls.push("registry"); return { hasCapability: () => false }; },
  }), /GEMINI_API_KEY is required/);
  assert.deepEqual(calls, []);
});

test("general money worker permits an explicit runner without Gemini", () => {
  const runner = async () => ({ value: { status: "completed", execution_id: "test-runner" } });
  let options;
  createWorkerHandlers({
    LM_DATA_DIR: fs.mkdtempSync(path.join(os.tmpdir(), "lm-runtime-money-explicit-runner-")),
  }, ["general-agent.work"], {
    readOpportunity: async () => ({}),
    updateOpportunity: async () => ({}),
    runAgentRunner: runner,
    createMoneyPrinterSpecialist(input) { options = input; return async () => {}; },
    createRegistry() { return { hasCapability: () => false }; },
  });
  assert.equal(options.runAgentRunner, runner);
});

test("production general money worker resolves LM_REPO_ROOT and rejects filesystem root", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-runtime-money-repo-root-"));
  let options;
  const dependencies = {
    readOpportunity: async () => ({}),
    updateOpportunity: async () => ({}),
    createMoneyPrinterSpecialist(input) { options = input; return async () => {}; },
    createRegistry() { return { hasCapability: () => false }; },
  };
  createWorkerHandlers({
    LM_DATA_DIR: dataDir,
    GEMINI_API_KEY: "gemini-secret-key",
    LM_REPO_ROOT: "/app",
  }, ["general-agent.work"], dependencies);
  assert.equal(options.repoRoot, "/app");

  assert.throws(() => createWorkerHandlers({
    LM_DATA_DIR: dataDir,
    GEMINI_API_KEY: "gemini-secret-key",
    LM_REPO_ROOT: "/",
  }, ["general-agent.work"], {
    readOpportunity: async () => ({}),
    updateOpportunity: async () => ({}),
    createRegistry() { return { hasCapability: () => false }; },
  }), /repo root invalid/);
});

test("production general money worker injects Railway opportunity functions without Supabase", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-runtime-money-cloud-"));
  const geminiKey = "gemini-secret-key";
  let options;
  const specialist = async () => ({
    kind: "general_agent_work",
    status: "completed",
    tenant_id: MONEY_TENANT,
    job_id: MONEY_JOB_ID,
    goal_ref: MONEY_GOAL_REF,
    execution_id: "execution-runtime-cloud-1",
    next_job_refs: [],
  });
  const handlers = createWorkerHandlers({
    LM_DATA_DIR: dataDir,
    GEMINI_API_KEY: geminiKey,
  }, ["general-agent.work"], {
    async query(sql) {
      if (sql.includes("WITH updated AS")) {
        return { rows: [{
          uid: MONEY_TENANT, opportunity_id: MONEY_OPPORTUNITY_ID, goal_ref: MONEY_GOAL_REF,
          source_url: "https://public.example/opportunity", title: "Public opportunity",
          goal_statement: "Complete it.", value_minor: "50000", currency: "JPY", status: "QUALIFIED",
        }] };
      }
      return { rows: [{
        uid: MONEY_TENANT, opportunity_id: MONEY_OPPORTUNITY_ID, goal_ref: MONEY_GOAL_REF,
        source_url: "https://public.example/opportunity", title: "Public opportunity",
        goal_statement: "Complete it.", value_minor: "50000", currency: "JPY", status: "DISCOVERED",
      }] };
    },
    createMoneyPrinterSpecialist(input) {
      options = input;
      return specialist;
    },
    createRegistry({ servicesByAdapter }) {
      const services = servicesByAdapter["general-agent-work"];
      return {
        hasCapability: (capability) => capability === "general-agent.work",
        getByCapability: () => ({
          execute: async (job) => ({
            receipt: await services.runBoundedSpecialist({
              tenant_id: job.tenant_id,
              job_id: job.job_id,
              goal_ref: job.input_refs.goal_ref,
            }),
          }),
        }),
      };
    },
  });

  assert.equal(options.geminiKey, geminiKey);
  assert.equal(options.supaUrl, undefined);
  assert.equal(options.supaKey, undefined);
  assert.equal(typeof options.readOpportunity, "function");
  assert.equal(typeof options.updateOpportunity, "function");
  assert.equal(typeof options.humanTaskStore.createOnce, "function");
  assert.equal((await options.readOpportunity({
    tenant_id: MONEY_TENANT, opportunity_id: MONEY_OPPORTUNITY_ID, goal_ref: MONEY_GOAL_REF,
  })).status, "DISCOVERED");
  assert.equal((await options.updateOpportunity({
    tenant_id: MONEY_TENANT, opportunity_id: MONEY_OPPORTUNITY_ID, goal_ref: MONEY_GOAL_REF,
  }, "QUALIFIED")).status, "QUALIFIED");
  assert.doesNotMatch(JSON.stringify(await handlers["general-agent.work"]({
    tenant_id: MONEY_TENANT,
    job_id: MONEY_JOB_ID,
    capability: "general-agent.work",
    input_refs: { goal_ref: MONEY_GOAL_REF },
  })), new RegExp(geminiKey));
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

test("capability worker preserves a specialist-created waiting-human pause", async () => {
  const calls = [];
  await executeCapabilityJob({
    tenant_id: MONEY_TENANT,
    job_id: MONEY_JOB_ID,
    attempt: 1,
    capability: "general-agent.work",
    effect_class: "none",
  }, {
    workerId: "worker-a",
    handlers: {
      "general-agent.work": async () => ({ receipt: {
        kind: "general_agent_work", status: "blocked", tenant_id: MONEY_TENANT,
        job_id: MONEY_JOB_ID, goal_ref: MONEY_GOAL_REF, execution_id: "execution-human-1",
        next_job_refs: [`runtime-job://${MONEY_TENANT}/${encodeURIComponent(MONEY_JOB_ID)}`],
      } }),
    },
    completeJob: async (input) => calls.push({ kind: "complete", input }),
    failJob: async (input) => calls.push({ kind: "fail", input }),
  });

  assert.deepEqual(calls, []);
});

test("marketing liveness worker resolves only Life Manager Telegram refs and uses fake transport", async () => {
  const sent = [];
  const handlers = createWorkerHandlers({
    LM_RUNTIME_TENANT_ID: "tenant-a",
    LM_TELEGRAM_BOT_TOKEN: "fake-token",
    LM_TELEGRAM_ALERT_CHAT_ID: "fake-chat",
  }, ["marketing.liveness.telegram"], {
    createRegistry({ servicesByAdapter }) {
      const services = servicesByAdapter["marketing-liveness-telegram"];
      return {
        hasCapability: () => true,
        getByCapability: () => ({
          execute: async (job) => {
            const token = await services.secretProvider.get(job.tenant_id, job.input_refs.telegram_token_ref);
            const chat = await services.chatProvider.get(job.tenant_id, job.input_refs.telegram_chat_ref);
            sent.push({ token, chat });
            return { receipt: { kind: "fake_marketing_liveness" } };
          },
        }),
      };
    },
  });
  const job = {
    tenant_id: "tenant-a",
    capability: "marketing.liveness.telegram",
    input_refs: {
      telegram_token_ref: "secret://telegram/bot-token",
      telegram_chat_ref: "telegram-chat://owner",
    },
  };
  await handlers["marketing.liveness.telegram"](job);
  assert.deepEqual(sent, [{ token: "fake-token", chat: "fake-chat" }]);
  await assert.rejects(() => handlers["marketing.liveness.telegram"]({
    ...job, tenant_id: "other-tenant",
  }), /secret scope mismatch/i);
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
  const readLumaFormProfile = () => ({ form_answers: {} });
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
    readLumaFormProfile,
    createRegistry({ servicesByAdapter }) {
      services = servicesByAdapter["outbound-luma-rsvp"];
      return { hasCapability: () => false };
    },
  });
  assert.equal(composition.dailyDriver, dailyDriver);
  assert.equal(composition.auth, auth);
  assert.equal(composition.readLumaFormProfile, readLumaFormProfile);
  assert.equal(services.provider, provider);
});

test("outbound event worker lazily reads its private Luma form profile from the durable data root", () => {
  let reader;
  const calls = [];
  createWorkerHandlers({
    LM_RUNTIME_TENANT_ID: "tenant-a",
    LM_DATA_DIR: "/var/lib/life-manager/data",
  }, ["outbound.event.apply"], {
    lumaDailyDriver: { withLumaPage: async () => {} },
    lumaAuth: { ensureAuthenticated: async () => ({ status: "authenticated" }) },
    lumaEvidenceStore: {
      record: async () => {}, readExternalReceipt: async () => {}, readArtifact: async () => {},
    },
    readPrivateLumaFormProfile(input) {
      calls.push(input);
      return { form_answers: {} };
    },
    createConnectorEventsPack(input) {
      reader = input.readLumaFormProfile;
      return { provider: { inspectRegistration: async () => {}, submitRegistration: async () => {} } };
    },
    createRegistry() { return { hasCapability: () => false }; },
  });

  assert.equal(calls.length, 0);
  assert.deepEqual(reader(), { form_answers: {} });
  assert.deepEqual(calls, [{ path: "/var/lib/life-manager/data/private/connector-luma-form-profile.json" }]);
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

test("marketing video publication worker wires the Honne EN profile and TikTok integration scopes", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-runtime-publish-"));
  let services;
  const handlers = createWorkerHandlers({
    LM_RUNTIME_TENANT_ID: "tenant-a",
    LM_DATA_DIR: root,
    LM_HONNE_EN_INSTAGRAM_PROFILE_REF: "profile://instagram/honne_reveal",
    LM_HONNE_EN_TIKTOK_INTEGRATION_REF: "integration://postiz/tiktok/cmoig11ew001zlv0yk6vqo1us",
    LM_INSTAGRAM_HANDLE: "honne_reveal",
    LM_INSTAGRAM_ACCOUNTS_PATH: path.join(root, "accounts.json"),
    LM_INSTAGRAM_SETTINGS_PATH: path.join(root, "settings.json"),
    LM_INSTAGRAM_CREDENTIALS_PATH: path.join(root, "credentials.json"),
    LM_INSTAGRAM_PROFILE_STATE_DIR: path.join(root, "profile"),
    LM_TIKTOK_INTEGRATION: "provider-integration-value",
  }, ["marketing.video.publish"], {
    createRegistry({ servicesByAdapter }) {
      services = servicesByAdapter["marketing-video-publication"];
      return {
        hasCapability: (capability) => capability === "marketing.video.publish",
        getByCapability: () => ({ execute: async () => ({ receipt: { kind: "fixture" } }) }),
      };
    },
  });
  assert.equal(typeof handlers["marketing.video.publish"], "function");
  assert.equal(typeof services.profileProvider.get, "function");
  assert.equal(typeof services.integrationProvider.get, "function");
  assert.equal(typeof services.secretProvider.get, "function");
});

test("Agent Economy Cloud worker runs the shared wake and schedules the next wake", async () => {
  const key = Buffer.alloc(32, 4).toString("base64");
  const root = await fs.promises.mkdtemp(path.join(os.tmpdir(), "lm-ae-worker-"));
  let services;
  let wakeCalls = 0;
  const handlers = createWorkerHandlers({ LM_CLOUD_CITIZEN_ENCRYPTION_KEY: key, LM_DATA_DIR: root }, ["agent-economy.start"], {
    async query(sql, values) {
      if (/INSERT INTO public\.lm_runtime_jobs/.test(sql)) {
        return { rows: [{ job_id: values[0], tenant_id: values[1], loop_id: values[2],
          capability: values[3], effect_class: values[4], effect_key: values[5],
          input_refs: JSON.parse(values[6]), max_attempts: values[7], available_at: values[8] }] };
      }
      assert.match(sql, /FROM public\.lm_cloud_citizens/);
      assert.doesNotMatch(sql, /ciphertext|private\.lm_cloud_citizen_signers/);
      return { rows: [{ tenant_id: values[0], citizen_id: "primary", instance_id: "cloud",
        wallet_address: `0x${"a".repeat(40)}` }] };
    },
    createAgentEconomyCloudWakeRunner({ citizenStore, dataDir }) {
      assert.ok(citizenStore);
      assert.equal(dataDir, root);
      return async (identity) => {
        wakeCalls += 1;
        assert.equal(identity.tenant_id, "tenant-a");
        return { wake_id: "wake-1", kind: "idle", slot: null, profitable: false };
      };
    },
    createRegistry({ servicesByAdapter }) {
      services = servicesByAdapter["agent-economy-cloud"];
      const { createAgentEconomyCloudLoopAdapter } = require("../lib/agent-economy-cloud-adapter.js");
      const adapter = createAgentEconomyCloudLoopAdapter(services);
      return { hasCapability: (value) => value === "agent-economy.start", getByCapability: () => adapter };
    },
  });
  const { buildAgentEconomyStartJob } = require("../lib/agent-economy-cloud-adapter.js");
  const result = await handlers["agent-economy.start"]({
    ...buildAgentEconomyStartJob({ tenantId: "tenant-a", citizenId: "primary", instanceId: "cloud" }),
    available_at: "2026-09-11T00:00:00.000Z",
  });
  assert.equal(result.receipt.kind, "agent_economy_wake");
  assert.equal(result.receipt.status, "completed");
  assert.equal(wakeCalls, 1);
  assert.ok(services.citizenStore);
});


test("Maritime worker reconciliation reads full jobs without redispatch and commits successors atomically", async () => {
  const job = { tenant_id: "tenant-a", job_id: "job-a", attempt: 1, status: "reconciling",
    capability: "maritime.manager.cycle", effect_class: "money", effect_key: "effect-a", input_refs: { cycle_ref: "cycle://a" } };
  const calls = [];
  let state = "pending";
  const adapter = {
    execute: () => { throw new Error("redispatch forbidden"); },
    reconcile: async fullJob => { assert.equal(fullJob, job); calls.push("read"); return { state, receipt: { valid: true } }; },
    verify: receipt => receipt.valid === true,
    continuation: async () => ({ job: { job_id: "next" }, availableAt: "2026-10-21T00:00:00.000Z" }),
  };
  const store = {
    claimReconcilingJobs: async input => { assert.deepEqual(input.capabilities, [job.capability]); return [job]; },
    resolveReconciliation: async () => { calls.push("resolve"); },
    recordUnknownReconciliation: async () => { calls.push("age"); return { status: "reconciling" }; },
    resolveReconciliationAndEnqueue: async input => { assert.equal(input.nextJob.job_id, "next"); calls.push("atomic"); },
  };
  const deps = { registry: { getByCapability: () => adapter }, store };
  await reconcileMaritimeCapabilityJobs([job.capability, "content.publish"], deps);
  assert.deepEqual(calls, ["read"]);
  state = "present"; calls.length = 0;
  await reconcileMaritimeCapabilityJobs([job.capability], deps);
  assert.deepEqual(calls, ["read", "atomic"]);
  state = "unknown"; calls.length = 0;
  await reconcileMaritimeCapabilityJobs([job.capability], deps);
  assert.deepEqual(calls, ["read", "age"]);
  state = "present"; adapter.verify = () => false; calls.length = 0;
  await reconcileMaritimeCapabilityJobs([job.capability], deps);
  assert.deepEqual(calls, ["read", "age"]);
});

test("Maritime pending code survives the worker failure boundary", async () => {
  let failure;
  await executeCapabilityJob({ tenant_id: "tenant-a", job_id: "job-a", attempt: 1,
    capability: "maritime.manager.cycle", effect_class: "money" }, {
    workerId: "worker-a",
    handlers: { "maritime.manager.cycle": async () => { const error = new Error("pending"); error.code = "MARITIME_CYCLE_PENDING"; error.unknownEffect = true; throw error; } },
    failJob: async value => { failure = value; },
  });
  assert.equal(failure.errorCode, "MARITIME_CYCLE_PENDING");
  assert.equal(failure.unknownEffect, true);
});


test("Maritime cycle worker injects the existing remote transport and activates verified continuations", async () => {
  const seen = [];
  const managerStore = {};
  const transport = Object.fromEntries(["dispatchCycle", "readExecution", "readCycleReceipt"].map(key => [key, async () => {}]));
  const receipt = { status: "completed" };
  const next = { job: { job_id: "next" }, availableAt: "2026-10-21T00:00:00.000Z" };
  const handlers = createWorkerHandlers({}, ["maritime.manager.cycle"], {
    maritimeManagerStore: managerStore, maritimeTransport: transport,
    createRegistry: ({ servicesByAdapter }) => {
      const services = servicesByAdapter["maritime-manager-cycle"];
      assert.equal(services.managerStore, managerStore);
      assert.equal(services.dispatchCycle, transport.dispatchCycle);
      return { hasCapability: () => true, getByCapability: () => ({
        execute: async () => ({ receipt }), verify: () => true,
        continuation: async job => { seen.push(job); return next; },
      }) };
    },
  });
  const job = { job_id: "cycle-a" };
  assert.deepEqual(await handlers["maritime.manager.cycle"](job), { receipt, continuation: next });
  assert.deepEqual(seen, [job]);
});


test("Maritime worker completion telemetry shares persisted Manager dependencies", async () => {
  let observed;
  const pgPool = { query: async () => ({ rows: [] }) };
  const manager = createMaritimeManagerWorkerDependencies({
    pgPool,
    env: { LM_UID_SECRET: "fixture-only-secret" },
    recordMaritimeManagerCompletion: async (job, receipt, options) => { observed = { job, receipt, options }; return true; },
  });
  const job = { tenant_id: "lm_11111111-1111-4111-8111-111111111111", job_id: "work-1" };
  const receipt = { status: "completed" };
  const signal = new AbortController().signal;
  assert.equal(await manager.onJobCompleted(job, receipt, { signal }), true);
  assert.equal(observed.job, job);
  assert.equal(observed.receipt, receipt);
  assert.equal(observed.options.managerStore, manager.managerStore);
  assert.equal(observed.options.distributionStore, manager.distributionStore);
  assert.equal(observed.options.readFirstTouch, manager.readFirstTouch);
  assert.equal(observed.options.cfoReceiptIO, manager.cfoReceiptIO);
  assert.equal(observed.options.signal, signal);
});


test("Maritime report worker injects existing queue reader and shared CFO receipt IO", async () => {
  const io = { read: async identity => ({ uid: identity.uid, period_key: identity.periodKey, status: "sent" }) };
  const queries = [];
  const managerStore = {};
  const managerDependencies = { managerStore, distributionStore: {}, cfoReceiptIO: io };
  const handlers = createWorkerHandlers({}, ["maritime.manager.report"], {
    maritimeManagerDependencies: managerDependencies, maritimeTransport: {},
    query: async (sql, params) => { queries.push({sql,params}); return { rows: [] }; },
    createRegistry: ({ servicesByAdapter }) => {
      const report = servicesByAdapter["maritime-manager-report"];
      assert.equal(report.managerStore, managerStore);
      assert.equal(typeof report.deliverDailyResult, "function");
      return { hasCapability: () => true, getByCapability: () => ({execute: async input => {
        const observations = await report.readDailyObservations(input);
        assert.deepEqual(observations, { actionReceipts: [], financialRecords: [] });
        return {receipt: await report.readReportDelivery(input)};
      }}) };
    },
  });
  const input = {uid:"lm_11111111-1111-4111-8111-111111111111",periodKey:"maritime:daily:2026-10-21"};
  assert.equal((await handlers["maritime.manager.report"](input)).receipt.status,"sent");
  assert.equal(queries.length,2);
  assert.equal(queries[1].params[0],input.uid);
});


test("pending Maritime enrollment recovery reuses stable jobs and skips undeclared capability",async()=>{
 const uid="lm_11111111-1111-4111-8111-111111111111",sha="a".repeat(40),calls=[];
 const dependencies={managerStore:{listPaused:async()=>[],listPending:async limit=>{assert.equal(limit,1);return [{uid,release_sha:sha,consent_version:"maritime-manager-v2"}];}},
  readProvisionJobState:async()=>null,enqueueJob:async job=>{calls.push(job);return {created:calls.length===1,job:{...job,status:"queued"}};}};
 await recoverMaritimeEnrollments(["maritime.manager.cycle"],dependencies);assert.equal(calls.length,0);
 await recoverMaritimeEnrollments(["maritime.manager.provision"],dependencies);
 await recoverMaritimeEnrollments(["maritime.manager.provision"],dependencies);
 assert.deepEqual(calls[0],calls[1]);assert.equal(calls[0].tenant_id,uid);assert.equal(calls[0].capability,"maritime.manager.provision");
});

test("pending provision recovers after a consent-guard dead letter appears between worker polls",async()=>{
 const uid="lm_11111111-1111-4111-8111-111111111111",sha="a".repeat(40),anchor="2026-10-22T00:00:00.000Z";
 const row={uid,release_sha:sha,status:"provisioning",consent_version:"maritime-manager-v2",consent_v2_at:anchor};
 const runtime=require("../lib/maritime-manager-runtime.js"),base=runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha:sha});
 const states=new Map([[base.job_id,{job_id:base.job_id,tenant_id:uid,status:"running",attempt:1,last_error_code:null}]]),queued=[],quarantined=[];
 const deps={managerStore:{listPending:async()=>[row],listPaused:async()=>[],quarantinePendingProvision:async id=>{quarantined.push(id);}},
  readProvisionJobState:async({tenantId,job})=>{assert.equal(tenantId,uid);return states.get(job.job_id)||null;},
  enqueueJob:async job=>{queued.push(job);return {created:false,job:{...job,status:"running"}};}};
 await recoverMaritimeEnrollments(["maritime.manager.provision"],deps);
 assert.equal(queued.length,0);assert.deepEqual(quarantined,[]);
 states.set(base.job_id,{job_id:base.job_id,tenant_id:uid,status:"dead_letter",attempt:1,last_error_code:"MARITIME_PROVISION_CONSENT_REQUIRED"});
 const resume=runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha:sha,resumeAt:anchor});
 await recoverMaritimeEnrollments(["maritime.manager.provision"],{...deps,enqueueJob:async job=>{queued.push(job);return {created:true,job:{...job,status:"queued"}};}});
 assert.equal(queued.length,1);assert.equal(queued[0].job_id,resume.job_id);assert.deepEqual(quarantined,[]);
});

test("active reconsented configuration recovers only the known no-effect dead letter",async()=>{
 const uid="lm_22222222-2222-4222-8222-222222222222",sha="b".repeat(40),anchor="2026-10-22T00:00:00.000Z";
 const row={uid,release_sha:sha,status:"active",consent_version:"maritime-manager-v2",consent_v2_at:anchor,agent_id:"agent-b"};
 const runtime=require("../lib/maritime-manager-runtime.js"),base=runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha:sha,phase:"configure"});
 const states=new Map([[base.job_id,{job_id:base.job_id,tenant_id:uid,status:"dead_letter",attempt:1,last_error_code:"MARITIME_PROVISION_CONSENT_REQUIRED"}]]),queued=[];
 const deps={managerStore:{listReconsentedActive:async(limit,after)=>{assert.equal(limit,20);assert.equal(after,null);return [row];}},
  readProvisionJobState:async({job})=>states.get(job.job_id)||null,
  enqueueJob:async job=>{queued.push(job);return {created:true,job:{...job,status:"queued"}};}};
 const cursor=await recoverReconsentedMaritimeConfigurations(["maritime.manager.provision"],deps);
 const resume=runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha:sha,phase:"configure",resumeAt:anchor});
 assert.equal(cursor,null);assert.equal(queued.length,1);assert.equal(queued[0].job_id,resume.job_id);
});

test("active configuration with an unknown terminal result remains fenced",async()=>{
 const uid="lm_22222222-2222-4222-8222-222222222222",sha="b".repeat(40);
 const row={uid,release_sha:sha,status:"active",consent_version:"maritime-manager-v2",consent_v2_at:"2026-10-22T00:00:00.000Z",agent_id:"agent-b"};
 const runtime=require("../lib/maritime-manager-runtime.js"),base=runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha:sha,phase:"configure"});
 const deps={managerStore:{listReconsentedActive:async()=>[row]},
  isProvisionReady:async()=>false,readProvisionJobState:async()=>({job_id:base.job_id,tenant_id:uid,status:"dead_letter",attempt:1,last_error_code:"MARITIME_PROVISION_CONFIGURATION_UNCONFIRMED"}),
  enqueueJob:async()=>{throw new Error("unknown configure must not be retried");}};
 await recoverReconsentedMaritimeConfigurations(["maritime.manager.provision"],deps);
});

test("completed active configure job is not reconfigured by background recovery",async()=>{
 const uid="lm_22222222-2222-4222-8222-222222222222",sha="b".repeat(40);
 const row={uid,release_sha:sha,status:"active",consent_version:"maritime-manager-v2",consent_v2_at:"2026-10-22T00:00:00.000Z",agent_id:"agent-b"};
 const runtime=require("../lib/maritime-manager-runtime.js"),base=runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha:sha,phase:"configure"});
 const deps={managerStore:{listReconsentedActive:async()=>[row]},
  readProvisionJobState:async()=>({job_id:base.job_id,tenant_id:uid,status:"completed",attempt:1,last_error_code:null}),
  enqueueJob:async()=>{throw new Error("ready tenants must not be reconfigured");}};
 await recoverReconsentedMaritimeConfigurations(["maritime.manager.provision"],deps);
});

test("Maritime provision worker binds release-specific source and shared Manager persistence",async()=>{
 const sha="a".repeat(40),transport=Object.fromEntries(["ensureAgent","readAgent","configureWake","readWakeConfiguration","writeScheduleSnapshot"].map(key=>[key,async()=>{}]));
 const managerStore={},queries=[];let services;
 const distributionStore={getParticipant:async()=>{queries.push('participant');return {ok:true,participant:null};},revoke:async()=>true};
 createWorkerHandlers({LM_MARITIME_MANAGER_IMAGE_RELEASE_SHA:sha,LM_MARITIME_MANAGER_SOURCE_S3_KEY:"uploads/fixture.zip",LM_MARITIME_MANAGER_SOURCE_ARCHIVE_SHA256:"b".repeat(64)},["maritime.manager.provision"],{
  maritimeManagerDependencies:{managerStore,distributionStore,cfoReceiptIO:{}},maritimeTransport:transport,query:async()=>({rows:[]}),
  createRegistry:({servicesByAdapter})=>{services=servicesByAdapter["maritime-manager-provision"];return {hasCapability:()=>false};},
 });
 assert.equal(services.managerStore,managerStore);assert.equal(await services.isConsentRevoked("lm_11111111-1111-4111-8111-111111111111"),true);assert.deepEqual(queries,['participant']);
 assert.equal(services.ensureAgent,transport.ensureAgent);assert.equal(services.readWakeConfiguration,transport.readWakeConfiguration);
 assert.equal(services.provisionSource(sha).uploadS3Key,"uploads/fixture.zip");
 assert.throws(()=>services.provisionSource("c".repeat(40)),/source/);
});


test("Maritime post-send continuation failure reconciles the receipt without a second send",async()=>{
 let sends=0,continuations=0,failure,atomic=0;
 const receipt={status:"completed"},next={job:{job_id:"next"},availableAt:"2026-10-22T00:00:00.000Z"};
 const adapter={execute:async()=>{sends++;return {receipt};},verify:()=>true,
  continuation:async()=>{if(++continuations===1)throw new Error("store temporarily unavailable");return next;},
  reconcile:async()=>({state:"present",receipt})};
 const registry={hasCapability:()=>true,getByCapability:()=>adapter};
 const handlers=createWorkerHandlers({},["maritime.manager.report"],{maritimeManagerStore:{},maritimeReportReceiptIO:{read:async()=>null,claim:async()=>true,mark:async()=>true},maritimeTransport:{},query:async()=>({rows:[]}),createRegistry:()=>registry});
 const job={tenant_id:"tenant-a",job_id:"report-a",attempt:1,capability:"maritime.manager.report",effect_class:"message",effect_key:"message-a",status:"running"};
 await executeCapabilityJob(job,{workerId:"worker-a",handlers,failJob:async input=>{failure=input;}});
 assert.equal(sends,1);assert.equal(failure.unknownEffect,true);
 await reconcileMaritimeCapabilityJobs([job.capability],{registry,store:{
  claimReconcilingJobs:async()=>[{...job,status:"reconciling"}],recordUnknownReconciliation:async()=>{throw new Error("not unknown");},
  resolveReconciliation:async()=>{throw new Error("non-atomic");},resolveReconciliationAndEnqueue:async input=>{assert.equal(input.nextJob.job_id,"next");atomic++;},
 }});
 assert.equal(sends,1);assert.equal(atomic,1);
});

test("terminal pending provision is quarantined so the next tenant can recover",async()=>{
 const a={uid:"lm_11111111-1111-4111-8111-111111111111",release_sha:"a".repeat(40),consent_version:"maritime-manager-v2"},b={...a,uid:"lm_22222222-2222-4222-8222-222222222222"};
 const rows=[a,b],queued=[],quarantined=[];
 const deps={managerStore:{listPaused:async()=>[],listPending:async()=>rows.slice(0,1),quarantinePendingProvision:async uid=>{quarantined.push(uid);rows.shift();}},
 readProvisionJobState:async({tenantId,job})=>tenantId===a.uid?{job_id:job.job_id,tenant_id:tenantId,status:"dead_letter",attempt:1,last_error_code:"MARITIME_PROVISION_UNCONFIGURED"}:null,
 enqueueJob:async job=>{queued.push(job.tenant_id);return {created:job.tenant_id===b.uid,job:{...job,status:job.tenant_id===a.uid?"dead_letter":"queued"}};}};
 await recoverMaritimeEnrollments(["maritime.manager.provision"],deps);await recoverMaritimeEnrollments(["maritime.manager.provision"],deps);
 assert.deepEqual(quarantined,[a.uid]);assert.deepEqual(queued,[b.uid]);
});

test("legacy pending tenants stay reconsentable without a job or after the no-effect consent dead letter",async()=>{
 const sha="c".repeat(40);
 for(const state of [null,{status:"dead_letter",attempt:1,last_error_code:"MARITIME_PROVISION_CONSENT_REQUIRED"}]){
  const uid=state?"lm_44444444-4444-4444-8444-444444444444":"lm_33333333-3333-4333-8333-333333333333";
  const row={uid,release_sha:sha,status:"pending",consent_version:"maritime-manager-v1",consent_v2_at:null,agent_id:null,paused_at:null};
  const quarantined=[];let reads=0,enqueues=0;
  const store={listPending:async()=>[row],listPaused:async()=>[],quarantinePendingProvision:async id=>{quarantined.push(id);row.status="effect_unknown";},
   reconsent:async()=>{if(row.status!=="pending"||row.consent_version!=="maritime-manager-v1")return null;
    row.consent_version="maritime-manager-v2";row.consent_v2_at="2026-10-22T00:00:00.000Z";return row;}};
  await recoverMaritimeEnrollments(["maritime.manager.provision"],{managerStore:store,
   readProvisionJobState:async()=>{reads++;return state?{job_id:"old",tenant_id:uid,...state}:null;},
   enqueueJob:async()=>{enqueues++;throw new Error("legacy tenant must not dispatch before reconsent");}});
  assert.deepEqual(quarantined,[]);assert.equal(row.status,"pending");assert.equal(reads,0);assert.equal(enqueues,0);
  const updated=await store.reconsent();assert.equal(updated.consent_version,"maritime-manager-v2");
 }
});


test("Maritime pause job uses the existing consent store and never sends a report",async()=>{
 const uid="lm_11111111-1111-4111-8111-111111111111",sha="a".repeat(40);let revoked=false,calls=0;
 const runtime=require('../lib/maritime-manager-runtime.js');
 const handlers=createWorkerHandlers({},['maritime.manager.provision'],{
  withControlLock:async(_uid,operation)=>operation(),
  maritimeManagerStore:{read:async()=>({uid,agent_id:null,release_sha:sha,status:'paused',paused_at:'2026-10-21T00:00:00.000Z'})},
  maritimeTransport:{},query:async()=>{throw new Error('no report enqueue');},
  maritimeDistributionStore:{getParticipant:async()=>({ok:true,participant:{revoked_at:revoked?'2026-10-21T00:00:01.000Z':null}}),revoke:async()=>{calls++;revoked=true;return true;}},
  createRegistry:({servicesByAdapter})=>{const adapter=runtime.createMaritimeManagerProvisionAdapter(servicesByAdapter['maritime-manager-provision']);return {hasCapability:()=>true,getByCapability:()=>adapter};},
 });
 const job=runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha:sha,phase:'pause'});
 assert.equal((await handlers[job.capability](job)).receipt.consent_revoked,true);assert.equal(calls,1);
 await handlers[job.capability](job);assert.equal(calls,1);
});


test("paused cleanup recovery advances beyond completed old jobs and wraps its cursor",async()=>{
 const rows=Array.from({length:21},(_,i)=>({uid:`lm_${(i+1).toString(16).padStart(8,'0')}-1111-4111-8111-111111111111`,release_sha:'a'.repeat(40)}));
 const seen=[];
 const deps={managerStore:{listPending:async()=>[],listPaused:async(limit,after)=>{assert.equal(limit,20);return rows.filter(row=>!after||row.uid>after).slice(0,limit);}},
  enqueueJob:async job=>{assert.equal(job.input_refs.provision_phase_ref,'maritime-provision-phase://pause');seen.push(job.tenant_id);return {created:false,job:{...job,status:'completed'}};}};
 const cursor=await recoverMaritimeEnrollments(['maritime.manager.provision'],deps);assert.equal(cursor,rows[19].uid);
 assert.equal(await recoverMaritimeEnrollments(['maritime.manager.provision'],{...deps,pausedCursor:cursor}),null);
 assert.equal(new Set(seen).size,21);
});


test("Maritime completion telemetry runs after durable completion and cannot trigger a resend",async()=>{
 const order=[],job={tenant_id:'tenant-a',job_id:'job-a',attempt:1,capability:'maritime.manager.report',effect_class:'message'};
 const completed={...job,status:'completed',completed_at:'2026-10-21T01:00:00.000Z'};
 await executeCapabilityJob(job,{workerId:'worker-a',handlers:{[job.capability]:async()=>({receipt:{status:'completed'}})},
 completeJob:async()=>{order.push('complete');return completed;},failJob:async()=>{throw new Error('do not fail completed mail');},
 onJobCompleted:async row=>{assert.equal(row,completed);order.push('usage');throw new Error('metrics unavailable');}});
 assert.deepEqual(order,['complete','usage']);
});
test("reconciled Maritime telemetry follows the atomic successor commit",async()=>{
 const job={tenant_id:'tenant-a',job_id:'job-a',attempt:1,status:'reconciling',capability:'maritime.manager.cycle',effect_class:'money',effect_key:'effect-a'},order=[];
 const adapter={reconcile:async()=>({state:'present',receipt:{status:'completed'}}),verify:()=>true,continuation:async()=>({job:{job_id:'next'},availableAt:'2026-10-21T01:15:00.000Z'})};
 await reconcileMaritimeCapabilityJobs([job.capability],{registry:{getByCapability:()=>adapter},store:{claimReconcilingJobs:async()=>[job],recordUnknownReconciliation:async()=>{},resolveReconciliation:async()=>{},resolveReconciliationAndEnqueue:async()=>{order.push('atomic');return {...job,status:'completed'};}},
 onJobCompleted:async row=>{assert.equal(row.status,'completed');order.push('usage');return true;}});
 assert.deepEqual(order,['atomic','usage']);
});


test("Maritime telemetry consumes the SQL completion receipt row rather than assuming a job row",async()=>{
 const receipt={status:'completed'},time='2026-10-21T01:00:00.000Z';let observed=0;
 const job={tenant_id:'tenant-a',job_id:'job-a',attempt:1,capability:'maritime.manager.report',effect_class:'message'};
 await executeCapabilityJob(job,{workerId:'worker-a',handlers:{[job.capability]:async()=>({receipt})},
  completeJob:async()=>({tenant_id:job.tenant_id,job_id:job.job_id,attempt:job.attempt,outcome:'completed',receipt,created_at:time}),
  onJobCompleted:async completed=>{assert.equal(completed.status,'completed');assert.equal(completed.completed_at,time);assert.equal(completed.capability,job.capability);observed++;},
  failJob:async()=>{throw new Error('unexpected failure');}});
 assert.equal(observed,1);
});

test('Maritime completed work returns when telemetry stalls',async()=>{
 const job={tenant_id:'tenant-a',job_id:'job-a',attempt:1,capability:'maritime.manager.report',effect_class:'message'},logs=[];let signal;
 await executeCapabilityJob(job,{workerId:'worker-a',usageTimeoutMs:10,writeUsageDiagnostic:row=>logs.push(row),
 handlers:{[job.capability]:async()=>({receipt:{status:'completed'}})},
 completeJob:async()=>({...job,status:'completed',completed_at:'2026-10-21T01:00:00Z'}),
 failJob:async()=>assert.fail('business must not retry'),
 onJobCompleted:async(row,receipt,opts)=>{signal=opts.signal;await new Promise(()=>{});}});
 assert.equal(signal.aborted,true);assert.equal(logs[0].error_class,'usage_timeout');
});

test("Maritime provider capabilities are registered with tenant-scoped central predecessor readers and fail closed without binding",async()=>{
  const uid="lm_11111111-1111-4111-8111-111111111111";
  const runtime=require("../lib/maritime-manager-provider-runtime.js");
  const caps=["maritime.manager.capafy.prepare","maritime.manager.capafy.publish"];
  let services;
  const handlers=createWorkerHandlers({},caps,{
    maritimeManagerStore:{},maritimeTransport:{},
    query:async(sql,values)=>{assert.deepEqual(values,[uid,"cycle-id"]);assert.match(sql,/jobs.tenant_id = \$1/);return {rows:[]};},
    onRegistry:registry=>{for(const cap of caps)assert.equal(registry.hasCapability(cap),true);},
    createRegistry:({servicesByAdapter})=>{
      services=servicesByAdapter["maritime-manager-capafy-prepare"];
      return require("../lib/loop-adapter-registry.js").createConfiguredLoopAdapterRegistry({servicesByAdapter});
    },
  });
  assert.deepEqual(await services.readCompletedCycle({tenantId:uid,jobId:"cycle-id"}),null);
  const job={...runtime.buildMaritimeCapafyPrepareJob({tenantId:uid,releaseSha:"a".repeat(40),occurrenceId:"one",
    cycleJobId:"maritime-cycle:"+"b".repeat(64),artifactRef:"artifact://original/listing.md",accountRef:`account://capafy/${uid}/seller-1`}),
    attempt:1,status:"running"};
  await assert.rejects(handlers[caps[0]](job),/unconfigured/);
});
test("only a durable completed cycle auto-enqueues its tenant-bound Capafy prepare job",async()=>{
 const uid="lm_11111111-1111-4111-8111-111111111111",releaseSha="a".repeat(40),providerSubject="019d3c7f-fe51-7c57-aa2e-8e1055bb36a5";
 const cycle={...require("../lib/maritime-manager-runtime.js").buildMaritimeManagerCycleJob({tenantId:uid,
   releaseSha,occurrenceId:"first",dateKey:"2026-10-23"}),status:"completed",completed_at:"2026-10-25T11:00:00.000Z"};
 const externalRef="maritime-execution://vm-1/exec-1";
 const receipt={schema_version:1,kind:"maritime_manager_cycle",tenant_id:uid,job_id:cycle.job_id,
   agent_id:"vm-1",execution_id:"exec-1",occurrence_id:"first",date_key:"2026-10-23",release_sha:releaseSha,
   status:"completed",artifact_refs:["artifact://original/listing.md"],error_class:null,provider:"maritime",
   external_ref:externalRef,evidence_refs:[externalRef]};
 const accountRef=`account://capafy/${uid}/${providerSubject}`,queued=[];
 const provider={readAccountBinding:async({tenantId})=>({provider:"capafy",tenantId,accountRef,providerSubject,
   autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
   withAccessToken:async({tenantId},operation)=>operation("am_sk_"+"t".repeat(32),{provider:"capafy",tenantId,
     accountRef,providerSubject,autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
   guardArtifact:async({identity})=>{assert.equal(identity.tenantId,uid);return {original:true,frozen:false,duplicate:false};},
   prepare:async()=>{},readPrepare:async()=>({state:"absent"}),readPublisherConfirmation:async()=>({}),readPublish:async()=>({state:"absent"})};
 const result=await require("./runtime-up.js").enqueueMaritimeCapafyPrepareAfterCompletion(cycle,receipt,{
   provider,managerStore:{read:async()=>({uid,release_sha:releaseSha,status:"active",paused_at:null})},
   enqueueJob:async job=>{queued.push(job);return {created:true,job};}});
 assert.equal(result.status,"queued");
 assert.equal(queued.length,1);assert.equal(queued[0].tenant_id,uid);
 assert.equal(queued[0].capability,"maritime.manager.capafy.prepare");
 assert.equal(queued[0].input_refs.source_cycle_job_id,cycle.job_id);
 assert.equal(queued[0].input_refs.artifact_ref,"artifact://original/listing.md");
});
test("Capafy admission ignores unfinished cycles and stays inert without a host executor",async()=>{
 const queued=[];let reads=0;
 const result=await require("./runtime-up.js").enqueueMaritimeCapafyPrepareAfterCompletion({
   tenant_id:"lm_11111111-1111-4111-8111-111111111111",job_id:"cycle",status:"running",
   capability:"maritime.manager.cycle"},{status:"completed"},{provider:{readAccountBinding:async()=>{reads++;}},
   managerStore:{read:async()=>null},enqueueJob:async job=>queued.push(job)});
 assert.equal(result.status,"skipped");assert.equal(reads,0);assert.equal(queued.length,0);
 const completed=await require("./runtime-up.js").enqueueMaritimeCapafyPrepareAfterCompletion({
   tenant_id:"lm_11111111-1111-4111-8111-111111111111",job_id:"cycle",status:"completed",
   capability:"maritime.manager.cycle"},{status:"completed"},{managerStore:{read:async()=>null},enqueueJob:async job=>queued.push(job)});
 assert.equal(completed.status,"skipped");assert.equal(queued.length,0);
});
test("Capafy host configuration fails closed without official Publisher confirmation readback",async()=>{
 const uid="lm_11111111-1111-4111-8111-111111111111",calls=[],releaseSha="a".repeat(40);
 const providerSubject="019d3c7f-fe51-7c57-aa2e-8e1055bb36a5",accountRef=`account://capafy/${uid}/${providerSubject}`;
 const job={...require("../lib/maritime-manager-runtime.js").buildMaritimeManagerCycleJob({tenantId:uid,
   releaseSha,occurrenceId:"first",dateKey:"2026-10-25"}),status:"completed"};
 const externalRef="maritime-execution://vm-1/exec-1";
 const receipt={schema_version:1,kind:"maritime_manager_cycle",tenant_id:uid,job_id:job.job_id,agent_id:"vm-1",
   execution_id:"exec-1",occurrence_id:"first",date_key:"2026-10-25",release_sha:releaseSha,status:"completed",
   artifact_refs:["artifact://original/listing.md"],error_class:null,provider:"maritime",external_ref:externalRef,evidence_refs:[externalRef]};
 const provider={readAccountBinding:async({tenantId})=>{calls.push("binding");return {provider:"capafy",tenantId,accountRef,
     providerSubject,autonomyConsentVersion:"maritime-capafy-autonomy-v1"};},
   withAccessToken:async({tenantId},operation)=>operation("am_sk_"+"t".repeat(32),{provider:"capafy",tenantId,
     accountRef,providerSubject,autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
   guardArtifact:async()=>{calls.push("guard");return {original:true,frozen:false,duplicate:false};},
   prepare:async()=>{},readPrepare:async()=>({state:"absent"}),publish:async()=>{},readPublish:async()=>({state:"absent"})};
 const result=await require("./runtime-up.js").enqueueMaritimeCapafyPrepareAfterCompletion(job,receipt,{
   provider,managerStore:{read:async()=>({uid,status:"active",release_sha:releaseSha})},
   enqueueJob:async()=>{calls.push("enqueue");return {created:true};}});
 assert.deepEqual(result,{status:"skipped",reason:"host_executor_unavailable"});
 assert.deepEqual(calls,[]);
});
test("Capafy auto-enqueue runs from the durable completion observer before usage telemetry",async()=>{
 const uid="lm_11111111-1111-4111-8111-111111111111",releaseSha="a".repeat(40),providerSubject="019d3c7f-fe51-7c57-aa2e-8e1055bb36a5";
 const cycle={...require("../lib/maritime-manager-runtime.js").buildMaritimeManagerCycleJob({tenantId:uid,
   releaseSha,occurrenceId:"first",dateKey:"2026-10-23"}),status:"completed"};
 const externalRef="maritime-execution://vm-1/exec-1";
 const receipt={schema_version:1,kind:"maritime_manager_cycle",tenant_id:uid,job_id:cycle.job_id,
   agent_id:"vm-1",execution_id:"exec-1",occurrence_id:"first",date_key:"2026-10-23",release_sha:releaseSha,
   status:"completed",artifact_refs:["artifact://original/listing.md"],error_class:null,provider:"maritime",
   external_ref:externalRef,evidence_refs:[externalRef]};
 const accountRef=`account://capafy/${uid}/${providerSubject}`,events=[];
 const provider={readAccountBinding:async({tenantId})=>({provider:"capafy",tenantId,accountRef,providerSubject,
   autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
   withAccessToken:async({tenantId},operation)=>operation("am_sk_"+"t".repeat(32),{provider:"capafy",tenantId,
     accountRef,providerSubject,autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
   guardArtifact:async()=>({original:true,frozen:false,duplicate:false}),prepare:async()=>{},
   readPrepare:async()=>({state:"absent"}),readPublisherConfirmation:async()=>({}),readPublish:async()=>({state:"absent"})};
 const observer=require("./runtime-up.js").createMaritimeCapafyCompletionObserver({provider,
   managerStore:{read:async()=>({uid,release_sha:releaseSha,status:"active",paused_at:null})},
   enqueueJob:async job=>{events.push(["enqueue",job.capability]);return {created:true,job};},
   onJobCompleted:async()=>events.push(["usage"])});
 await observer(cycle,receipt);
 assert.deepEqual(events,[["enqueue","maritime.manager.capafy.prepare"],["usage"]]);
});
test("worker recovery finds only recent active bound cycles without a prepare job",async()=>{
 const uid="lm_11111111-1111-4111-8111-111111111111",releaseSha="a".repeat(40),providerSubject="019d3c7f-fe51-7c57-aa2e-8e1055bb36a5";
 const cycle={...require("../lib/maritime-manager-runtime.js").buildMaritimeManagerCycleJob({tenantId:uid,
   releaseSha,occurrenceId:"first",dateKey:"2026-10-23"}),status:"completed",completed_at:"2026-10-25T11:00:00.000Z"};
 const externalRef="maritime-execution://vm-1/exec-1";
 const receipt={schema_version:1,kind:"maritime_manager_cycle",tenant_id:uid,job_id:cycle.job_id,
   agent_id:"vm-1",execution_id:"exec-1",occurrence_id:"first",date_key:"2026-10-23",release_sha:releaseSha,
   status:"completed",artifact_refs:["artifact://original/listing.md"],error_class:null,provider:"maritime",
   external_ref:externalRef,evidence_refs:[externalRef]};
 const accountRef=`account://capafy/${uid}/${providerSubject}`,queued=[];let sql="",cursorWrites=0;
 const provider={readAccountBinding:async({tenantId})=>({provider:"capafy",tenantId,accountRef,providerSubject,
   autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
   withAccessToken:async({tenantId},operation)=>operation("am_sk_"+"t".repeat(32),{provider:"capafy",tenantId,
     accountRef,providerSubject,autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
   guardArtifact:async()=>({original:true,frozen:false,duplicate:false}),prepare:async()=>{},
   readPrepare:async()=>({state:"absent"}),readPublisherConfirmation:async()=>({}),readPublish:async()=>({state:"absent"})};
 const result=await require("./runtime-up.js").recoverMaritimeCapafyCycleAdmissions(
   ["maritime.manager.capafy.prepare"],{enabled:true,provider,
     managerStore:{read:async()=>({uid,release_sha:releaseSha,status:"active",paused_at:null})},
     enqueueJob:async(job,options)=>{assert.equal(options.query,"store-query");queued.push(job);return {created:true,job};},
     query:async(statement,values=[])=>{
       if(/SELECT completed_at::text AS completed_at, tenant_id, job_id[\s\S]*FROM private\.lm_maritime_manager_capafy_recovery_cursor/i.test(statement))
         return {rows:[{completed_at:null,tenant_id:null,job_id:null}]};
       if(/UPDATE private\.lm_maritime_manager_capafy_recovery_cursor/i.test(statement)){
         cursorWrites++;return {rows:[{cursor_key:"cycle_admission"}]} ;
       }
       sql=statement;assert.match(statement,/SELECT jobs\.completed_at::text AS completed_at/i);assert.deepEqual(values,[null,null,null]);
       return {rows:[{job:cycle,receipt,tenant_id:uid,job_id:cycle.job_id,completed_at:cycle.completed_at}]};
     },
     storeOptions:{query:"store-query"}});
 assert.equal(result.status,"checked");assert.equal(result.candidates,1);assert.equal(result.queued,1);
 assert.equal(queued.length,1);assert.equal(queued[0].tenant_id,uid);
 assert.match(sql,/lm_maritime_manager_capafy_bindings/);assert.match(sql,/managers\.status='active'/);
 assert.match(sql,/source_cycle_job_id/);assert.match(sql,/interval '24 hours'/);assert.equal(cursorWrites,1);
});
test("bounded Capafy recovery advances a durable keyset past refused tenants", async () => {
 const runtime=require("../lib/maritime-manager-runtime.js"),providerSubject="019d3c7f-fe51-7c57-aa2e-8e1055bb36a5";
 const cycleRows=[];
 for(let n=1;n<=21;n++){
  const hex=String(n).padStart(8,"0"),uid=`lm_${hex}-1111-4111-8111-${hex}${hex.slice(0,4)}`,releaseSha="a".repeat(40);
  const cycle={...runtime.buildMaritimeManagerCycleJob({tenantId:uid,releaseSha,occurrenceId:`cycle-${n}`,dateKey:"2026-10-25"}),
    status:"completed",completed_at:`2026-10-25T00:${String(Math.floor((n-1)/60)).padStart(2,"0")}:${String((n-1)%60).padStart(2,"0")}.000Z`};
  const externalRef=`maritime-execution://vm-${n}/exec-${n}`;
  const receipt={schema_version:1,kind:"maritime_manager_cycle",tenant_id:uid,job_id:cycle.job_id,agent_id:`vm-${n}`,
    execution_id:`exec-${n}`,occurrence_id:`cycle-${n}`,date_key:"2026-10-25",release_sha:releaseSha,status:"completed",
    artifact_refs:[`artifact://original/${n===21?"valid":"duplicate"}.md`],error_class:null,provider:"maritime",
    external_ref:externalRef,evidence_refs:[externalRef]};
  cycleRows.push({job:cycle,receipt,completed_at:cycle.completed_at});
 }
 let cursor=null,providerCalls=0;
 const queued=[],queries=[];
 const query=async(sql,values=[])=>{
  queries.push({sql,values});
  if(/SELECT completed_at::text AS completed_at, tenant_id, job_id[\s\S]*FROM private\.lm_maritime_manager_capafy_recovery_cursor/i.test(sql))
    return {rows:[cursor||{completed_at:null,tenant_id:null,job_id:null}]};
  if(/UPDATE private\.lm_maritime_manager_capafy_recovery_cursor/i.test(sql)){
    cursor=values[1]===null?null:{completed_at:values[1],tenant_id:values[2],job_id:values[3]};
    return {rows:[{cursor_key:"cycle_admission"}]};
  }
  if(/SELECT jobs\.completed_at::text AS completed_at, jobs\.tenant_id, jobs\.job_id/i.test(sql)){
    const [afterTime,afterTenant,afterJob]=values;
    const candidates=cycleRows.filter(row=>{
      if(afterTime==null)return true;
      const current=[row.completed_at,row.job.tenant_id,row.job.job_id],after=[afterTime,afterTenant,afterJob];
      for(let index=0;index<current.length;index++){
        if(String(current[index])>String(after[index]))return true;
        if(String(current[index])<String(after[index]))return false;
      }
      return false;
    });
    return {rows:candidates.slice(0,20)};
  }
  assert.fail(`unexpected query: ${sql}`);
 };
 const provider={
  readAccountBinding:async({tenantId})=>({provider:"capafy",tenantId,
    accountRef:`account://capafy/${tenantId}/${providerSubject}`,providerSubject,
    autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
  withAccessToken:async({tenantId},operation)=>operation("am_sk_"+"t".repeat(32),{provider:"capafy",tenantId,
    accountRef:`account://capafy/${tenantId}/${providerSubject}`,providerSubject,
    autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
  guardArtifact:async({artifactRef})=>{providerCalls++;return artifactRef.endsWith("valid.md")
    ?{original:true,frozen:false,duplicate:false}:{original:true,frozen:false,duplicate:true};},
  prepare:async()=>{},readPrepare:async()=>({state:"absent"}),readPublisherConfirmation:async()=>({}),readPublish:async()=>({state:"absent"}),
 };
 const managerStore={read:async tenantId=>({uid:tenantId,status:"active",paused_at:null,release_sha:"a".repeat(40)})};
 const recover=require("./runtime-up.js").recoverMaritimeCapafyCycleAdmissions;
 const first=await recover(["maritime.manager.capafy.prepare"],{enabled:true,provider,managerStore,query,
   enqueueJob:async job=>{queued.push(job);return {created:true,job};}});
 assert.deepEqual(first,{status:"checked",queued:0,candidates:20});
 assert.equal(providerCalls,20);assert.deepEqual(cursor,cycleRows[19]&&{completed_at:cycleRows[19].completed_at,
   tenant_id:cycleRows[19].job.tenant_id,job_id:cycleRows[19].job.job_id});
 const second=await recover(["maritime.manager.capafy.prepare"],{enabled:true,provider,managerStore,query,
   enqueueJob:async job=>{queued.push(job);return {created:true,job};}});
 assert.deepEqual(second,{status:"checked",queued:1,candidates:1});
 assert.equal(queued.length,1);assert.equal(queued[0].tenant_id,cycleRows[20].job.tenant_id);
 const scan=queries.find(call=>/SELECT jobs\.completed_at::text AS completed_at, jobs\.tenant_id, jobs\.job_id/i.test(call.sql));
 assert.doesNotMatch(scan.sql,/DISTINCT ON/i);assert.match(scan.sql,/LIMIT 20/i);
 assert.ok(queries.filter(call=>/UPDATE private\.lm_maritime_manager_capafy_recovery_cursor/i.test(call.sql)).length>=21);
});
test("Capafy provider adapters take tenant identity from encrypted owner binding before any external effect",async()=>{
 const uid="lm_11111111-1111-4111-8111-111111111111",caps=["maritime.manager.capafy.prepare","maritime.manager.capafy.publish"],calls=[];
 const accountBinding={readAccountBinding:async identity=>{calls.push(["binding",identity]);return {provider:"capafy",tenantId:uid,
   accountRef:identity.accountRef,providerSubject:"019d3c7f-fe51-7c57-aa2e-8e1055bb36a5"};},
   withAccessToken:async(_identity,operation)=>operation("am_sk_"+"x".repeat(32),{tenantId:uid})};
 const provider={readAccountBinding:async()=>assert.fail("provider supplied identity must never override owner binding"),
   guardArtifact:async()=>{calls.push(["guard"]);return {original:true,frozen:false,duplicate:false};},
   prepare:async()=>{calls.push(["prepare"]);}};
 const handlers=createWorkerHandlers({},caps,{maritimeManagerStore:{read:async()=>({uid,release_sha:"a".repeat(40),status:"active",paused_at:null})},maritimeTransport:{},maritimeCapafyProvider:provider,
   maritimeCapafyAccountBinding:accountBinding,query:async()=>({rows:[]}),
   createRegistry:({servicesByAdapter})=>require("../lib/loop-adapter-registry.js").createConfiguredLoopAdapterRegistry({servicesByAdapter})});
 const job={...require("../lib/maritime-manager-provider-runtime.js").buildMaritimeCapafyPrepareJob({tenantId:uid,
   releaseSha:"a".repeat(40),occurrenceId:"one",cycleJobId:"maritime-cycle:"+"b".repeat(64),
   artifactRef:"artifact://original/listing.md",accountRef:`account://capafy/${uid}/seller-1`}),attempt:1,status:"running"};
 await assert.rejects(handlers[caps[0]](job),/invalid/);
 assert.deepEqual(calls,[["binding",{tenantId:uid,accountRef:job.input_refs.account_ref}]]);
});

test("production Capafy account binding requires a tenant-scoped encrypted credential key",()=>{
 const managerStore={read:async()=>null};
 assert.throws(()=>createMaritimeCapafyAccountBinding({query:async()=>({rows:[]}),managerStore,env:{}}),/encryption/i);
 const binding=createMaritimeCapafyAccountBinding({query:async()=>({rows:[]}),managerStore,
   env:{LM_MARITIME_CAPAFY_ENCRYPTION_KEY:"a".repeat(64)},fetchImpl:async()=>new Response("{}")});
 assert.equal(typeof binding.readAccountBinding,"function");
 assert.equal(typeof binding.withAccessToken,"function");
});
test("Maritime provider reconcile allowlist commits present successor atomically, resolves absent, and retains unknown",async()=>{
  for(const phase of ["prepare","publish"])for(const state of ["present","absent","unknown"]){
    const capability=`maritime.manager.capafy.${phase}`,calls=[];
    const job={job_id:"provider-job",tenant_id:"tenant-a",capability,attempt:1,status:"reconciling",effect_class:"publish",effect_key:"provider-effect"};
    const adapter={reconcile:async()=>({state,receipt:{provider:"capafy",status:state}}),verify:async()=>true,
      continuation:async()=>phase==="prepare"?{job:{job_id:"publish-next"},availableAt:"2026-10-23T12:00:00.000Z"}:null};
    await reconcileMaritimeCapabilityJobs([capability,"unrelated.publish"],{
      registry:{getByCapability:()=>adapter},store:{
        claimReconcilingJobs:async input=>{assert.deepEqual(input.capabilities,[capability]);return [job];},
        recordUnknownReconciliation:async()=>{calls.push("held");return {status:"reconciling"};},
        resolveReconciliation:async input=>{calls.push(input.decision);},
        resolveReconciliationAndEnqueue:async input=>{calls.push("atomic");assert.equal(input.nextJob.job_id,"publish-next");},
      },
    });
    assert.deepEqual(calls,state==="unknown"?[]:[state==="present"&&phase==="prepare"?"atomic":state]);
  }
});

test("provider unknown and invalid readback remain reconciling beyond aging threshold and later converge",async()=>{
 for(const phase of ["prepare","publish"])for(const invalidProof of [false,true]){
  const capability="maritime.manager.capafy."+phase;
  const job={job_id:"provider-job",tenant_id:"tenant-a",capability,attempt:1,status:"reconciling",effect_class:"publish",effect_key:"provider-effect"};
  let reads=0,aged=0,resolved=0;
  const adapter={reconcile:async()=>({state:++reads<=6?(invalidProof?"present":"unknown"):"present",receipt:{read:reads}}),
   verify:async receipt=>receipt.read>6,continuation:async()=>null};
  const deps={registry:{getByCapability:()=>adapter},store:{
   claimReconcilingJobs:async()=>[job],
   recordUnknownReconciliation:async()=>{aged++;return {status:aged>=5?"dead_letter":"reconciling"};},
   resolveReconciliation:async input=>{assert.equal(input.decision,"present");resolved++;},
  }};
  for(let n=0;n<7;n++)await reconcileMaritimeCapabilityJobs([capability],deps);
  assert.equal(aged,0);assert.equal(resolved,1);
 }
 let aged=0;
 await reconcileMaritimeCapabilityJobs(["maritime.manager.report"],{
  registry:{getByCapability:()=>({reconcile:async()=>({state:"unknown"})})},store:{
   claimReconcilingJobs:async()=>[{job_id:"report",tenant_id:"tenant-a",capability:"maritime.manager.report",attempt:1,status:"reconciling",effect_class:"message",effect_key:"report-effect"}],
   recordUnknownReconciliation:async()=>{aged++;return {status:"reconciling"};},
  },
 });
 assert.equal(aged,1);
});
