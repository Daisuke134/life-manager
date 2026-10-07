"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  buildVideoPublicationJobsFromGeneration,
  enqueueVideoGenerationPublications,
} = require("./marketing-video-publication-chain.js");

const VIDEO_HASH = "a".repeat(64);
const COPY_HASH = "b".repeat(64);
const APPROVAL_HASH = "c".repeat(64);

function generationReceipt(overrides = {}) {
  return {
    schema_version: 1,
    kind: "marketing_video_artifact",
    status: "ready",
    product_id: "honne-ai",
    format_id: "reelclaw",
    form: "relationship-confession",
    locale: "ja",
    slot: "2026-07-30T12:30:00.000Z",
    creative_id: "HJA-007-aaaaaaaaaaaa",
    hook_id: "HJA-007",
    hook_sha256: "e".repeat(64),
    video_ref: `object://sha256/${VIDEO_HASH}`,
    video_sha256: VIDEO_HASH,
    copy_ref: `object://sha256/${COPY_HASH}`,
    copy_sha256: COPY_HASH,
    generated_at: "2026-07-30T12:30:01.000Z",
    ...overrides,
  };
}

function options(overrides = {}) {
  return {
    tenantId: "tenant-a",
    productId: "honne-ai",
    approvalRef: `object://sha256/${APPROVAL_HASH}`,
    instagramProfileRef: "profile://instagram/honne-ai-ja",
    instagramIntegrationRef: "integration://postiz/instagram/honne-ai-ja",
    postizTokenRef: "secret://postiz/api-key",
    tiktokIntegrationRef: "integration://postiz/tiktok/honne-ai-ja",
    ...overrides,
  };
}

test("one generic video generation receipt fans out to independent Instagram and TikTok publication jobs", () => {
  const jobs = buildVideoPublicationJobsFromGeneration(generationReceipt(), options());

  assert.equal(jobs.length, 2);
  assert.deepEqual(jobs.map((job) => job.input_refs.platform_ref), [
    "platform://instagram",
    "platform://tiktok",
  ]);
  assert.deepEqual(
    jobs.map((job) => job.input_refs.instagram_integration_ref || job.input_refs.tiktok_integration_ref),
    [
      "integration://postiz/instagram/honne-ai-ja",
      "integration://postiz/tiktok/honne-ai-ja",
    ],
  );
  assert.ok(jobs.every((job) => (
    job.tenant_id === "tenant-a"
    && job.input_refs.product_ref === "product://honne-ai"
    && job.input_refs.creative_ref === "creative://honne-ai/HJA-007-aaaaaaaaaaaa"
    && job.input_refs.video_ref === `object://sha256/${VIDEO_HASH}`
    && job.input_refs.caption_ref === `object://sha256/${COPY_HASH}`
    && job.input_refs.approval_ref === `object://sha256/${APPROVAL_HASH}`
    && job.effect_class === "publish"
  )));
  assert.notEqual(jobs[0].job_id, jobs[1].job_id);
  assert.notEqual(jobs[0].effect_key, jobs[1].effect_key);
  assert.doesNotMatch(JSON.stringify(jobs), /\.openclaw|\/Users\/|password|raw-token/i);
});

test("chain rejects a hash-mismatched generation receipt before any job is created", () => {
  assert.throws(
    () => buildVideoPublicationJobsFromGeneration(
      generationReceipt({ video_sha256: "d".repeat(64) }),
      options(),
    ),
    /generation receipt/i,
  );
});

test("chain rejects a cross-product generation receipt before any job is created", () => {
  assert.throws(
    () => buildVideoPublicationJobsFromGeneration(
      generationReceipt({ product_id: "anicca-ios" }),
      options(),
    ),
    /generation receipt/i,
  );
});

test("repeated chain scans enqueue the same deterministic jobs and depend on store idempotency", async () => {
  const stored = new Map();
  const calls = [];
  const enqueueJob = async (input) => {
    calls.push(input);
    const created = !stored.has(input.jobId);
    if (created) stored.set(input.jobId, input);
    return {
      created,
      job: {
        job_id: input.jobId,
        tenant_id: input.tenantId,
        capability: input.capability,
      },
    };
  };

  const first = await enqueueVideoGenerationPublications(
    generationReceipt(),
    options(),
    { enqueueJob },
  );
  const second = await enqueueVideoGenerationPublications(
    generationReceipt(),
    options(),
    { enqueueJob },
  );

  assert.deepEqual(first.map((item) => item.created), [true, true]);
  assert.deepEqual(second.map((item) => item.created), [false, false]);
  assert.equal(stored.size, 2);
  assert.equal(calls.length, 4);
});

// Fake durable store mirroring apps/life-manager/lib/runtime-job-store.js semantics AND the
// database rule UNIQUE (tenant_id, effect_key) from migrations/20260729_runtime_jobs.sql:33.
function createFakeRuntimeJobStore() {
  const rows = new Map();
  const toJob = (row) => ({
    job_id: row.jobId,
    tenant_id: row.tenantId,
    loop_id: row.loopId,
    capability: row.capability,
    effect_class: row.effectClass,
    effect_key: row.effectKey,
    input_refs: row.inputRefs,
    max_attempts: row.maxAttempts,
    status: row.status,
  });
  return {
    rows,
    async enqueueJob(input) {
      for (const row of rows.values()) {
        if (
          row.tenantId === input.tenantId
          && row.effectKey === input.effectKey
          && row.jobId !== input.jobId
        ) {
          throw new Error(
            'duplicate key value violates unique constraint "lm_runtime_jobs_tenant_id_effect_key_key"',
          );
        }
      }
      const existing = rows.get(input.jobId);
      if (existing) {
        if (
          existing.effectKey !== input.effectKey
          || JSON.stringify(existing.inputRefs) !== JSON.stringify(input.inputRefs)
        ) {
          throw new Error("runtime job id collision");
        }
        return { created: false, job: toJob(existing) };
      }
      rows.set(input.jobId, { ...input, status: "queued" });
      return { created: true, job: toJob(rows.get(input.jobId)) };
    },
    claim() {
      const claimed = [...rows.values()].filter((row) => row.status === "queued");
      for (const row of claimed) row.status = "running";
      return claimed.map(toJob);
    },
    complete(jobId, receipt) {
      const row = rows.get(jobId);
      if (!row || row.status !== "running") throw new Error("fake store lease lost");
      row.status = "completed";
      row.receipt = receipt;
    },
  };
}

function countingAdapter(providerCalls, ledgerDir) {
  const { createMarketingVideoPublicationLoopAdapter } = require("./marketing-video-publication-adapter.js");
  return createMarketingVideoPublicationLoopAdapter({
    objectStore: { resolve: (ref) => `/objects/${ref.slice(-64)}` },
    profileProvider: {
      get: async () => ({
        handle: "honne_ai",
        accountsPath: "/profiles/accounts.json",
        settingsPath: "/profiles/settings.json",
        credentialsPath: "/profiles/credentials.json",
        stateDir: "/profiles/state",
      }),
    },
    secretProvider: { get: async () => "token" },
    integrationProvider: { get: async () => "integration" },
    ledgerPath: () => path.join(ledgerDir, "distribution.jsonl"),
    async runDistribution(input) {
      providerCalls.push(input);
      return {
        creative_id: "HJA-007-aaaaaaaaaaaa",
        video_sha256: VIDEO_HASH,
        caption_sha256: COPY_HASH,
        platform: input.platform,
        public_url: input.platform === "instagram"
          ? "https://www.instagram.com/reel/abc123/"
          : "https://www.tiktok.com/@honne_ai/video/7999999999999999999",
        provider_post_id: `postiz-${input.platform}-HJA-007`,
        provider_route: "postiz",
        provider_reconciled: false,
      };
    },
  });
}

test("claim, execute, complete, then replay drives zero additional provider executions", async () => {
  const store = createFakeRuntimeJobStore();
  const providerCalls = [];
  const ledgerDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-video-chain-e2e-"));
  const adapter = countingAdapter(providerCalls, ledgerDir);

  const first = await enqueueVideoGenerationPublications(
    generationReceipt(),
    options(),
    { enqueueJob: store.enqueueJob },
  );
  assert.deepEqual(first.map((item) => item.created), [true, true]);

  const claimed = store.claim();
  assert.equal(claimed.length, 2);
  for (const claimedJob of claimed) {
    const { receipt } = await adapter.execute(claimedJob);
    assert.equal(adapter.verify(receipt), true);
    store.complete(claimedJob.job_id, receipt);
  }
  assert.equal(providerCalls.length, 2);

  // Replay the whole chain: re-enqueue is deduped, nothing is claimable, and the
  // provider is never executed again.
  const second = await enqueueVideoGenerationPublications(
    generationReceipt(),
    options(),
    { enqueueJob: store.enqueueJob },
  );
  assert.deepEqual(second.map((item) => item.created), [false, false]);
  assert.equal(store.claim().length, 0);
  assert.equal(providerCalls.length, 2);
  assert.equal(
    [...store.rows.values()].filter((row) => row.status === "completed").length,
    2,
  );
});

test("an Instagram enqueue collision fails fast: TikTok is not enqueued in the same scan", async () => {
  // W-4: fanout must not be non-atomic. Seed the store with ONLY the Instagram job from a
  // prior slot, so this scan's Instagram enqueue collides (same identity, different slot
  // lineage) — the TikTok enqueue must then never be attempted.
  const store = createFakeRuntimeJobStore();
  const [instagramJob] = buildVideoPublicationJobsFromGeneration(
    generationReceipt(),
    options(),
  );
  await store.enqueueJob({
    jobId: instagramJob.job_id,
    tenantId: instagramJob.tenant_id,
    loopId: instagramJob.loop_id,
    capability: instagramJob.capability,
    effectClass: instagramJob.effect_class,
    effectKey: instagramJob.effect_key,
    inputRefs: instagramJob.input_refs,
    maxAttempts: instagramJob.max_attempts,
  });

  const calls = [];
  const enqueueJob = async (input) => {
    calls.push(input);
    return store.enqueueJob(input);
  };

  await assert.rejects(
    enqueueVideoGenerationPublications(
      generationReceipt({ slot: "2026-07-31T09:00:00.000Z" }),
      options(),
      { enqueueJob },
    ),
    /runtime job id collision/,
  );
  assert.equal(calls.length, 1);
  assert.equal(calls[0].inputRefs.platform_ref, "platform://instagram");
  assert.equal(store.rows.size, 1);
  assert.ok([...store.rows.values()].every((row) => (
    row.inputRefs.platform_ref !== "platform://tiktok"
  )));
});

test("re-enqueueing the same artifact at a different slot cannot create a second publish effect", async () => {
  const store = createFakeRuntimeJobStore();
  const providerCalls = [];
  const ledgerDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-video-chain-slot-"));
  const adapter = countingAdapter(providerCalls, ledgerDir);

  const first = await enqueueVideoGenerationPublications(
    generationReceipt(),
    options(),
    { enqueueJob: store.enqueueJob },
  );
  assert.deepEqual(first.map((item) => item.created), [true, true]);

  // Same bytes+caption+platform at a NEW slot: identity agrees (same job_id and
  // effect_key), so the store surfaces a controlled collision instead of a raw
  // (tenant_id, effect_key) unique-constraint exception — and never a second post.
  await assert.rejects(
    enqueueVideoGenerationPublications(
      generationReceipt({ slot: "2026-07-31T09:00:00.000Z" }),
      options(),
      { enqueueJob: store.enqueueJob },
    ),
    /runtime job id collision/,
  );
  assert.equal(store.rows.size, 2);

  for (const claimedJob of store.claim()) {
    const { receipt } = await adapter.execute(claimedJob);
    store.complete(claimedJob.job_id, receipt);
  }
  assert.equal(providerCalls.length, 2);
  assert.equal(store.claim().length, 0);
});
