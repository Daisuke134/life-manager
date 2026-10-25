"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  PROMOTION_CONFIRMATION,
  buildHonneEnCanaryTelegramJob,
  createMarketingLocalLedger,
} = require("../lib/marketing-canary.js");
const {
  main,
  parseArgs,
  assertPublicationReceipt,
  resolveCanaryTransport,
  runHonneEnCanary,
} = require("./honne-en-canary.js");

const testTempDirs = new Set();

function testTempDir(prefix) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  fs.writeFileSync(path.join(dataDir, ".lm-test-canary"), "life-manager-canary-test-v1\n", { mode: 0o600 });
  testTempDirs.add(dataDir);
  return dataDir;
}

test.after(() => {
  const leftovers = [];
  for (const dataDir of testTempDirs) {
    fs.rmSync(dataDir, { recursive: true, force: true });
    if (fs.existsSync(dataDir)) leftovers.push(path.basename(dataDir));
  }
  assert.deepEqual(leftovers, []);
});

const RECEIPT = {
  schema_version: 1,
  kind: "marketing_video_distribution",
  status: "published",
  product_id: "honne-ai",
  format_id: "reelclaw",
  form: "relationship-confession",
  locale: "en",
  slot: "2026-08-21T02:00:00.000Z",
  creative_id: "HEN-001-aaaaaaaaaaaa",
  platform: "tiktok",
  video_sha256: "a".repeat(64),
  caption_sha256: "b".repeat(64),
  public_url: "https://www.tiktok.com/@honne_reveal/video/7999999999999999999",
  provider_post_id: "postiz-7999999999999999999",
  provider_route: "postiz",
  provider_reconciled: true,
  provider_effect_created: true,
  origin_occurrence_id: "life-manager-honne-en:canary-run-1",
  published_at: "2026-08-21T02:01:00.000Z",
};
const TELEGRAM_RECEIPT = {
  schema_version: 1,
  kind: "telegram_marketing_liveness",
  lane: "honne-en-canary",
  product: "honne-ai",
  locale: "en",
  platform: "tiktok",
  slot: RECEIPT.slot,
  status: "published",
  public_url: RECEIPT.public_url,
  retry_state: "not_required",
  message_id: 42,
  chat_id_hash: "d".repeat(64),
  sent_at: "2026-08-21T02:02:00.000Z",
};

test("canary args require exactly one tenant and publication job", () => {
  assert.deepEqual(
    parseArgs(["run", "--tenant", "dais-local", "--job-id", "publication-job"]),
    { tenant: "dais-local", jobId: "publication-job" },
  );
  assert.throws(() => parseArgs(["run", "--tenant", "dais-local"]), /--job-id/i);
});

test("Postiz canary transport requires the exact promotion confirmation", () => {
  assert.equal(
    resolveCanaryTransport({
      LM_HONNE_EN_CANARY_TRANSPORT: "postiz",
      LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
    }),
    "postiz",
  );
  assert.throws(
    () => resolveCanaryTransport({ LM_HONNE_EN_CANARY_TRANSPORT: "postiz" }),
    /promotion confirmation/i,
  );
  assert.throws(
    () => resolveCanaryTransport({
      LM_HONNE_EN_CANARY_TRANSPORT: "postiz",
      LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
    }, { fakeTransport: true }),
    /fake transport/i,
  );
  assert.throws(
    () => resolveCanaryTransport({
      LM_HONNE_EN_CANARY_TRANSPORT: "postiz",
      LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
    }, {
      executeCapabilityJob: Object.assign(async () => {}, { postizTransport: true }),
    }),
    /fake transport|trusted|internal|Postiz/i,
  );
  const proxiedExecutor = new Proxy(async () => {}, {
    get(target, property, receiver) {
      if (typeof property === "symbol") return true;
      return Reflect.get(target, property, receiver);
    },
  });
  assert.throws(
    () => resolveCanaryTransport({
      LM_HONNE_EN_CANARY_TRANSPORT: "postiz",
      LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
    }, { executeCapabilityJob: proxiedExecutor }),
    /fake transport|trusted|internal|Postiz/i,
  );
});

test("Honne EN canary receipt is bound to the @honne_reveal TikTok account", () => {
  assert.throws(
    () => assertPublicationReceipt({
      ...RECEIPT,
      public_url: "https://www.tiktok.com/@other_account/video/7999999999999999999",
    }),
    /honne_reveal|account|TikTok/i,
  );
});

test("real Postiz canary checks the Life Manager secret boundary before claiming a job", async () => {
  const store = createMarketingLocalLedger({
    dataDir: testTempDir("lm-canary-postiz-preflight-"),
  });
  await assert.rejects(
    runHonneEnCanary(
      ["run", "--tenant", "dais-local", "--job-id", "missing-job"],
      {
        env: {
          LM_RUNTIME_TENANT_ID: "dais-local",
          LM_DATA_DIR: store.dataDir,
          LM_HONNE_EN_CANARY_TRANSPORT: "postiz",
          LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
          LM_HONNE_EN_TIKTOK_INTEGRATION_REF: "integration://postiz/tiktok/cmoig11ew001zlv0yk6vqo1us",
          LM_HONNE_EN_TIKTOK_INTEGRATION: "cmoig11ew001zlv0yk6vqo1us",
          LM_TELEGRAM_BOT_TOKEN: "",
          LM_TELEGRAM_ALERT_CHAT_ID: "",
        },
        store,
      },
    ),
    /LM_POSTIZ_API_KEY/i,
  );
  assert.equal(await store.readJob({ tenantId: "dais-local", jobId: "missing-job" }), null);
});

test("real Postiz canary rejects injected URL verification", async () => {
  const store = createMarketingLocalLedger({
    dataDir: testTempDir("lm-canary-postiz-verifier-"),
  });
  await assert.rejects(
    runHonneEnCanary(
      ["run", "--tenant", "dais-local", "--job-id", "missing-job"],
      {
        env: {
          LM_RUNTIME_TENANT_ID: "dais-local",
          LM_DATA_DIR: store.dataDir,
          LM_HONNE_EN_CANARY_TRANSPORT: "postiz",
          LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
          LM_POSTIZ_API_KEY: "provider-secret",
          LM_TELEGRAM_BOT_TOKEN: "telegram-secret",
          LM_TELEGRAM_ALERT_CHAT_ID: "owner-chat",
          LM_HONNE_EN_TIKTOK_INTEGRATION_REF: "integration://postiz/tiktok/cmoig11ew001zlv0yk6vqo1us",
          LM_HONNE_EN_TIKTOK_INTEGRATION: "cmoig11ew001zlv0yk6vqo1us",
        },
        store,
        verifyDirectPublicUrl: async () => ({ status: 200, url: RECEIPT.public_url }),
      },
    ),
    /verifier|fetcher|injection/i,
  );
});

test("module canary invocation fails closed unless fake transport is explicit", async () => {
  await assert.rejects(
    runHonneEnCanary(
      ["run", "--tenant", "dais-local", "--job-id", "publication-job"],
      { env: { LM_RUNTIME_TENANT_ID: "dais-local" }, store: {} },
    ),
    /fake transport/i,
  );
});

test("configured fake transport still rejects an unmarked custom executor", async () => {
  await assert.rejects(
    runHonneEnCanary(
      ["run", "--tenant", "dais-local", "--job-id", "publication-job"],
      {
        env: {
          LM_RUNTIME_TENANT_ID: "dais-local",
          LM_HONNE_EN_CANARY_TRANSPORT: "fake",
        },
        store: {},
        executeCapabilityJob: async () => {},
      },
    ),
    /custom executor|fake transport marker/i,
  );
});

test("controlled canary promotes one job, publishes one receipt, sends one URL receipt, and replays idempotently", async () => {
  const store = createMarketingLocalLedger({
    dataDir: testTempDir("lm-canary-script-test-"),
    now: () => "2026-08-21T02:00:00.000Z",
  });
  await store.enqueueJob({
    job_id: "publication-job",
    tenant_id: "dais-local",
    loop_id: "marketing.video",
    capability: "marketing.video.publish",
    effect_class: "publish",
    effect_key: "marketing:video:honne-ai:tiktok:creative:video:caption",
    input_refs: {
      product_ref: "product://honne-ai",
      locale_ref: "locale://en",
      platform_ref: "platform://tiktok",
    },
    max_attempts: 3,
    available_at: "9999-12-31T23:59:59.000Z",
  });
  let executionCount = 0;
  const fakeExecutor = async (job, services) => {
    executionCount += 1;
    await services.completeJob({
      tenantId: job.tenant_id,
      jobId: job.job_id,
      attempt: job.attempt,
      workerId: services.workerId || "honne-en-canary",
      receipt: job.capability === "marketing.video.publish" ? RECEIPT : TELEGRAM_RECEIPT,
    });
  };
  fakeExecutor.fakeTransport = true;
  const deps = {
    env: {
      LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
      LM_RUNTIME_TENANT_ID: "dais-local",
      LM_HONNE_EN_CANARY_TRANSPORT: "fake",
      LIFE_MANAGER_OCCURRENCE_ID: RECEIPT.origin_occurrence_id,
    },
    store,
    fakeTransport: true,
    verifyDirectPublicUrl: async (url) => ({ status: 200, url }),
    executeCapabilityJob: fakeExecutor,
  };
  const result = await runHonneEnCanary(
    ["run", "--tenant", "dais-local", "--job-id", "publication-job"],
    deps,
  );
  deps.env.LIFE_MANAGER_OCCURRENCE_ID = "life-manager-honne-en:canary-run-2";
  const replayed = await runHonneEnCanary(
    ["run", "--tenant", "dais-local", "--job-id", "publication-job"],
    deps,
  );
  assert.equal(executionCount, 2);
  assert.equal(result.publication.public_url, RECEIPT.public_url);
  assert.equal(result.publication.created, true);
  assert.equal(result.publication.provider_effect_created, true);
  assert.equal(result.publication.origin_occurrence_id, "life-manager-honne-en:canary-run-1");
  assert.equal(result.publication.provider_reconciled, true);
  assert.equal(result.telegram.created, true);
  assert.equal(result.telegram.message_id, 42);
  assert.equal(result.telegram.replay_created, false);
  assert.equal(replayed.publication.replay_created, false);
  assert.equal(replayed.publication.created, false);
  assert.equal(replayed.publication.provider_effect_created, false);
  assert.equal(replayed.publication.origin_occurrence_id, "life-manager-honne-en:canary-run-1");
  assert.equal(replayed.publication.result_occurrence_id, "life-manager-honne-en:canary-run-2");
  assert.equal(replayed.telegram.created, false);
  assert.equal(replayed.telegram.replay_created, false);
  assert.equal((await store.readReceipt({ tenantId: "dais-local", jobId: result.telegram.job_id })).message_id, 42);
});

test("canary refuses to repost when publication receipt is missing after a terminal job", async () => {
  const store = createMarketingLocalLedger({
    dataDir: testTempDir("lm-canary-missing-receipt-"),
    now: () => "2026-08-21T02:00:00.000Z",
  });
  await store.enqueueJob({
    job_id: "publication-job",
    tenant_id: "dais-local",
    loop_id: "marketing.video",
    capability: "marketing.video.publish",
    effect_class: "publish",
    effect_key: "marketing:video:honne-ai:tiktok:missing-receipt",
    input_refs: {
      product_ref: "product://honne-ai",
      locale_ref: "locale://en",
      platform_ref: "platform://tiktok",
    },
    max_attempts: 3,
    available_at: "9999-12-31T23:59:59.000Z",
  });
  await store.promoteJob({
    tenantId: "dais-local",
    jobId: "publication-job",
    confirmation: PROMOTION_CONFIRMATION,
  });
  const claim = await store.claimJob({
    tenantId: "dais-local",
    jobId: "publication-job",
    capability: "marketing.video.publish",
    workerId: "seed-worker",
    leaseSeconds: 30,
  });
  await store.failJob({
    tenantId: "dais-local",
    jobId: "publication-job",
    attempt: claim.attempt,
    workerId: "seed-worker",
    errorCode: "seed_terminal",
  });
  await assert.rejects(
    runHonneEnCanary(
      ["run", "--tenant", "dais-local", "--job-id", "publication-job"],
      {
        env: {
          LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
          LM_RUNTIME_TENANT_ID: "dais-local",
          LM_HONNE_EN_CANARY_TRANSPORT: "fake",
        },
        store,
        executeCapabilityJob: Object.assign(async () => {}, { fakeTransport: true }),
      },
    ),
    /receipt|terminal|repost/i,
  );
});

test("canary rerun claims a promotion that persisted before the first process crashed", async () => {
  const store = createMarketingLocalLedger({
    dataDir: testTempDir("lm-canary-promoted-restart-"),
    now: () => "2026-08-21T02:00:00.000Z",
  });
  await store.enqueueJob({
    job_id: "publication-job",
    tenant_id: "dais-local",
    loop_id: "marketing.video",
    capability: "marketing.video.publish",
    effect_class: "publish",
    effect_key: "marketing:video:honne-ai:tiktok:promoted-restart",
    input_refs: {
      product_ref: "product://honne-ai",
      locale_ref: "locale://en",
      platform_ref: "platform://tiktok",
    },
    max_attempts: 3,
    available_at: "9999-12-31T23:59:59.000Z",
  });
  await store.promoteJob({
    tenantId: "dais-local",
    jobId: "publication-job",
    confirmation: PROMOTION_CONFIRMATION,
  });
  let executionCount = 0;
  const fakeExecutor = async (job, services) => {
    executionCount += 1;
    await services.completeJob({
      tenantId: job.tenant_id,
      jobId: job.job_id,
      attempt: job.attempt,
      workerId: services.workerId,
      receipt: job.capability === "marketing.video.publish" ? RECEIPT : TELEGRAM_RECEIPT,
    });
  };
  fakeExecutor.fakeTransport = true;
  const result = await runHonneEnCanary(
    ["run", "--tenant", "dais-local", "--job-id", "publication-job"],
    {
      env: {
        LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
        LM_RUNTIME_TENANT_ID: "dais-local",
        LM_HONNE_EN_CANARY_TRANSPORT: "fake",
      },
      store,
      executeCapabilityJob: fakeExecutor,
      verifyDirectPublicUrl: async (url) => ({ status: 200, url }),
    },
  );
  assert.equal(executionCount, 2);
  assert.equal(result.telegram.created, true);
});

test("canary fails closed on a reconciling publication with no receipt", async () => {
  let clock = "2026-08-21T02:00:00.000Z";
  const store = createMarketingLocalLedger({
    dataDir: testTempDir("lm-canary-reconciling-"),
    now: () => clock,
  });
  await store.enqueueJob({
    job_id: "publication-job",
    tenant_id: "dais-local",
    loop_id: "marketing.video",
    capability: "marketing.video.publish",
    effect_class: "publish",
    effect_key: "marketing:video:honne-ai:tiktok:reconciling",
    input_refs: {
      product_ref: "product://honne-ai",
      locale_ref: "locale://en",
      platform_ref: "platform://tiktok",
    },
    max_attempts: 3,
    available_at: "9999-12-31T23:59:59.000Z",
  });
  await store.promoteJob({ tenantId: "dais-local", jobId: "publication-job", confirmation: PROMOTION_CONFIRMATION });
  await store.claimJob({
    tenantId: "dais-local", jobId: "publication-job", capability: "marketing.video.publish", workerId: "crashed-worker", leaseSeconds: 30,
  });
  clock = "2026-08-21T02:00:31.000Z";
  assert.equal(await store.claimJob({
    tenantId: "dais-local", jobId: "publication-job", capability: "marketing.video.publish", workerId: "recovery-worker", leaseSeconds: 30,
  }), null);
  let executionCount = 0;
  const fakeExecutor = Object.assign(async () => { executionCount += 1; }, { fakeTransport: true });
  await assert.rejects(
    runHonneEnCanary(
      ["run", "--tenant", "dais-local", "--job-id", "publication-job"],
      {
        env: {
          LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
          LM_RUNTIME_TENANT_ID: "dais-local",
          LM_HONNE_EN_CANARY_TRANSPORT: "fake",
        },
        store,
        executeCapabilityJob: fakeExecutor,
      },
    ),
    /receipt|repost|terminal/i,
  );
  assert.equal(executionCount, 0);
});

test("fake-gated main runs the local process without constructing a real provider transport", async () => {
  const store = createMarketingLocalLedger({
    dataDir: testTempDir("lm-canary-main-test-"),
    now: () => "2026-08-21T02:00:00.000Z",
  });
  await store.enqueueJob({
    job_id: "publication-job",
    tenant_id: "dais-local",
    loop_id: "marketing.video",
    capability: "marketing.video.publish",
    effect_class: "publish",
    effect_key: "marketing:video:honne-ai:tiktok:creative:video:caption",
    input_refs: {
      product_ref: "product://honne-ai",
      locale_ref: "locale://en",
      platform_ref: "platform://tiktok",
    },
    max_attempts: 3,
    available_at: "9999-12-31T23:59:59.000Z",
  });
  let output = "";
  const result = await main(
    ["run", "--tenant", "dais-local", "--job-id", "publication-job"],
    {
      LM_RUNTIME_TENANT_ID: "dais-local",
      LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION,
      LM_HONNE_EN_CANARY_TRANSPORT: "fake",
    },
    { store, stdout: { write: (value) => { output += value; } } },
  );
  assert.equal(result.publication.public_url, "https://www.tiktok.com/@honne_reveal/video/1");
  assert.match(output, /"replay_created":false/);
});

test("main fails closed when the fake transport gate is unset or real", async () => {
  const args = ["run", "--tenant", "dais-local", "--job-id", "publication-job"];
  await assert.rejects(
    main(args, { LM_RUNTIME_TENANT_ID: "dais-local" }, { store: {} }),
    /LM_HONNE_EN_CANARY_TRANSPORT=fake|fake transport/i,
  );
  await assert.rejects(
    main(
      args,
      {
        LM_RUNTIME_TENANT_ID: "dais-local",
        LM_HONNE_EN_CANARY_TRANSPORT: "real",
      },
      { store: {} },
    ),
    /fake transport|external transport/i,
  );
});
