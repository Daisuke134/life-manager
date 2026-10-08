"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { APPROVED_CLAIMS, JOBS, approvedBaselineScript, normalizePostizInstagramReceiptRoute, run, selectTarget, verifyLegacyPostizReceipt } = require("./ebook-distribute-daily.js");
const { buildMarketingVideoPublicationJob } = require("../lib/marketing-video-publication-adapter.js");

const ROOT = path.resolve(__dirname, "../../..");
const PACK = JSON.parse(fs.readFileSync(
  path.join(ROOT, "skills/earn/marketing-engine/registry/ebook-packs/ebook-ja-watercolor.json"), "utf8",
));
const PACK_EN = JSON.parse(fs.readFileSync(
  path.join(ROOT, "skills/earn/marketing-engine/registry/ebook-packs/ebook-en-anicca-monk.json"), "utf8",
));

test("each Japanese eBook publisher owner resolves one matching account and locale", () => {
  const instagram = selectTarget({
    root: ROOT, pack: PACK, ownerId: "ebook-ja-instagram-daily",
    platform: "instagram", accountId: "instagram.obou_anicca",
  });
  const tiktok = selectTarget({
    root: ROOT, pack: PACK, ownerId: "ebook-ja-tiktok-daily",
    platform: "tiktok", accountId: "tiktok.obou_anicca",
  });

  assert.equal(instagram.account.language, "ja");
  assert.equal(instagram.target.integration_id, instagram.integrationId);
  assert.equal(tiktok.account.language, "ja");
  assert.equal(tiktok.target.integration_id, tiktok.integrationId);
  assert.deepEqual(Object.keys(JOBS).sort(), [
    "ebook-en-tiktok-daily", "ebook-ja-instagram-daily", "ebook-ja-tiktok-daily",
  ]);
  assert.deepEqual(
    Object.entries(JOBS).filter(([owner]) => owner.startsWith("ebook-ja-")).map(([, lane]) => lane.platform).sort(),
    ["instagram", "tiktok"],
  );
});

test("English HeyGen owner resolves the approved active Monk TikTok route", () => {
  const lane = JOBS["ebook-en-tiktok-daily"];
  assert.deepEqual(lane, {
    productId: "ebook-en",
    platform: "tiktok",
    accountId: "tiktok.monk_anicca",
    formatId: "ebook-avatar-iv",
    form: "ebook-reflection-reel",
    locale: "en",
  });

  const selected = selectTarget({
    root: ROOT,
    pack: PACK_EN,
    ownerId: "ebook-en-tiktok-daily",
    platform: lane.platform,
    accountId: lane.accountId,
  });
  assert.equal(selected.account.status, "approved_active");
  assert.equal(selected.setup_required, false);
  assert.equal(selected.target.integration_id, "cmo5rwq2p00twn10yrsdglng3");
  assert.equal(selected.integrationId, "cmo5rwq2p00twn10yrsdglng3");
});

test("English baseline policy accepts only the owned HeyGen script and claims", () => {
  const script = {
    product_id: "ebook-en",
    language: "en",
    baseline: true,
    renderer_id: "heygen-avatar-iv",
    cta: "Read The Anicca Reset",
    source_mechanism_ids: ["baseline.owner-authored.ebook-en.1.1"],
  };
  assert.equal(approvedBaselineScript(script, PACK_EN), true);
  assert.equal(approvedBaselineScript({ ...script, language: "ja" }, PACK_EN), false);
  assert.equal(approvedBaselineScript(script, {
    ...PACK_EN, allowed_claims: [...PACK_EN.allowed_claims, "guaranteed results"],
  }), false);
});

test("English owner writes a typed no-effect hint before its first scheduled slot", async () => {
  const dataDir = path.join(os.tmpdir(), `ebook-en-disabled-${process.pid}-${Date.now()}`);
  const env = {
    LIFE_MANAGER_LOOP_ID: "ebook-en-tiktok-daily",
    LIFE_MANAGER_OCCURRENCE_ID: "ebook-en-tiktok-daily:run-1",
    LIFE_MANAGER_RELEASE_ROOT: ROOT,
    LIFE_MANAGER_RESULT_HINT_PATH: path.join(dataDir, "entrypoint-result.json"),
    LM_DATA_DIR: dataDir,
    LM_RUNTIME_TENANT_ID: "dais-local",
    LM_EBOOK_PUBLISHING_ENABLED: "true",
  };

  const result = await run(["ebook-en-tiktok-daily"], {
    env,
    nowMs: Date.parse("2026-10-06T07:30:00+09:00"),
  });

  assert.equal(result.state, "no_due_slot");
  assert.equal(result.effect, 0);
  const hintPath = env.LIFE_MANAGER_RESULT_HINT_PATH;
  assert.equal(fs.existsSync(hintPath), true);
  if (fs.existsSync(hintPath)) {
    assert.deepEqual(JSON.parse(fs.readFileSync(hintPath, "utf8")), {
      schema_version: 1,
      kind: "life_manager_no_effect_result",
      status: "verified_no_effect",
      effect: 0,
      owner_id: "ebook-en-tiktok-daily",
      occurrence_id: "ebook-en-tiktok-daily:run-1",
      reason: "no_due_slot",
    });
  }
});

test("renderer receives scoped HeyGen environment only for the English eBook", async () => {
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), "ebook-renderer-env-"));
  const fakePython = path.join(temporaryRoot, "fake-python");
  const capturedKeys = [
    "LIFE_MANAGER_HEYGEN",
    "HEYGEN_NO_ANALYTICS",
    "LM_POSTIZ_API_KEY",
    "PRIVATE_UNRELATED_SECRET",
  ];
  fs.writeFileSync(fakePython, `#!${process.execPath}\nconst fs = require("node:fs");\nconst path = require("node:path");\nconst stateIndex = process.argv.indexOf("--state-root");\nconst stateRoot = process.argv[stateIndex + 1];\nfs.mkdirSync(stateRoot, { recursive: true });\nconst received = Object.fromEntries(${JSON.stringify(capturedKeys)}.map((key) => [key, process.env[key] ?? null]));\nfs.writeFileSync(path.join(stateRoot, "renderer-env.json"), JSON.stringify(received));\nprocess.stdout.write(JSON.stringify({ schema_version: "marketing.ebook-owner-input.v1", receipt: { state: "rendered" } }) + "\\n");\n`);
  fs.chmodSync(fakePython, 0o700);

  async function captureRendererEnvironment(ownerId, now, overrides = {}) {
    const stateDir = path.join(temporaryRoot, ownerId);
    const env = {
      HOME: process.env.HOME || "",
      PATH: process.env.PATH || "",
      LIFE_MANAGER_LOOP_ID: ownerId,
      LIFE_MANAGER_OCCURRENCE_ID: `${ownerId}:renderer-env-test`,
      LIFE_MANAGER_RELEASE_ROOT: ROOT,
      LIFE_MANAGER_RESULT_HINT_PATH: path.join(stateDir, "entrypoint-result.json"),
      LIFE_MANAGER_HEYGEN: path.join(temporaryRoot, "bin/heygen"),
      HEYGEN_NO_ANALYTICS: "1",
      LM_DATA_DIR: path.join(stateDir, "data"),
      LM_EBOOK_PUBLISHING_ENABLED: "true",
      LM_POSTIZ_API_KEY: "test-only-not-a-real-key",
      LM_PYTHON: fakePython,
      LM_RUNTIME_TENANT_ID: "dais-local",
      PRIVATE_UNRELATED_SECRET: "must-not-reach-renderer",
      ...overrides,
    };

    await assert.rejects(
      run([ownerId], { env, nowMs: Date.parse(now) }),
      /eBook render receipt and baseline script do not match/,
    );
    return JSON.parse(fs.readFileSync(
      path.join(stateDir, "data/marketing/ebook/renderer-env.json"), "utf8",
    ));
  }

  try {
    const english = await captureRendererEnvironment(
      "ebook-en-tiktok-daily", "2026-10-08T08:00:00+09:00",
    );
    assert.equal(english.LIFE_MANAGER_HEYGEN, path.join(temporaryRoot, "bin/heygen"));
    assert.equal(english.HEYGEN_NO_ANALYTICS, "1");
    assert.equal(english.LM_POSTIZ_API_KEY, null);
    assert.equal(english.PRIVATE_UNRELATED_SECRET, null);

    const japanese = await captureRendererEnvironment(
      "ebook-ja-tiktok-daily", "2026-10-08T12:30:00+09:00",
    );
    assert.equal(japanese.LIFE_MANAGER_HEYGEN, null);
    assert.equal(japanese.HEYGEN_NO_ANALYTICS, null);
    assert.equal(japanese.LM_POSTIZ_API_KEY, null);
    assert.equal(japanese.PRIVATE_UNRELATED_SECRET, null);
  } finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
});

test("Python renderer emits a safe failure envelope without exception text", () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "ebook-renderer-error-envelope-"));
  try {
    const renderer = path.join(ROOT, "skills/earn/marketing-engine/ebook_distribute_daily.py");
    const result = spawnSync("python3", [renderer, "--product", "invalid", "--slot-at",
      "2026-10-08T08:00:00+09:00", "--state-root", stateDir], {
      cwd: ROOT,
      env: { HOME: process.env.HOME || "/tmp", PATH: process.env.PATH || "", LANG: "C.UTF-8" },
      encoding: "utf8",
    });
    let failure = null;
    try { failure = JSON.parse(String(result.stdout || "").trim()); } catch {}
    assert.equal(result.status, 1);
    assert.deepEqual(failure, {
      schema_version: "marketing.ebook-render-failure.v1",
      error_class: "ValueError",
    });
    assert.equal(result.stderr, "");
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("English owner propagates only safe renderer error metadata", async () => {
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), "ebook-renderer-safe-error-"));
  const fakePython = path.join(temporaryRoot, "fake-python");
  fs.writeFileSync(fakePython, `#!${process.execPath}\nprocess.stdout.write(JSON.stringify({ schema_version: "marketing.ebook-render-failure.v1", error_class: "ValueError" }) + "\\n");\nprocess.stderr.write("PRIVATE_UNRELATED_SECRET must not leak\\n");\nprocess.exitCode = 1;\n`);
  fs.chmodSync(fakePython, 0o700);

  const stateDir = path.join(temporaryRoot, "state");
  const env = {
    HOME: process.env.HOME || "",
    PATH: process.env.PATH || "",
    LIFE_MANAGER_LOOP_ID: "ebook-en-tiktok-daily",
    LIFE_MANAGER_OCCURRENCE_ID: "ebook-en-tiktok-daily:renderer-error-test",
    LIFE_MANAGER_RELEASE_ROOT: ROOT,
    LIFE_MANAGER_RESULT_HINT_PATH: path.join(stateDir, "entrypoint-result.json"),
    LIFE_MANAGER_HEYGEN: path.join(temporaryRoot, "bin/heygen"),
    HEYGEN_NO_ANALYTICS: "1",
    LM_DATA_DIR: path.join(stateDir, "data"),
    LM_EBOOK_PUBLISHING_ENABLED: "true",
    LM_POSTIZ_API_KEY: "test-only-not-a-real-key",
    LM_PYTHON: fakePython,
    LM_RUNTIME_TENANT_ID: "dais-local",
  };

  try {
    let message = "";
    try {
      await run(["ebook-en-tiktok-daily"], {
        env,
        nowMs: Date.parse("2026-10-08T08:00:00+09:00"),
      });
    } catch (error) {
      message = error.message;
    }
    assert.equal(message, "eBook renderer failed: ValueError (exit 1)");
    assert.doesNotMatch(message, /PRIVATE_UNRELATED_SECRET|test-only-not-a-real-key/);
  } finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
});

test('off-slot Japanese TikTok persists an exact no-effect hint before renderer or Postiz', async () => {
  const dataDir = path.join(os.tmpdir(), `ebook-ja-no-slot-${process.pid}-${Date.now()}`);
  const ownerId = 'ebook-ja-tiktok-daily';
  const occurrenceId = `${ownerId}:run-off-slot`;
  const hintPath = path.join(dataDir, 'entrypoint-result.json');
  const env = {
    LIFE_MANAGER_LOOP_ID: ownerId,
    LIFE_MANAGER_OCCURRENCE_ID: occurrenceId,
    LIFE_MANAGER_RELEASE_ROOT: ROOT,
    LIFE_MANAGER_RESULT_HINT_PATH: hintPath,
    LM_DATA_DIR: dataDir,
    LM_RUNTIME_TENANT_ID: 'dais-local',
    LM_EBOOK_PUBLISHING_ENABLED: 'true',
  };

  const result = await run([ownerId], {
    env,
    nowMs: Date.parse('2026-10-08T00:33:17+09:00'),
  });

  assert.equal(result.state, 'no_due_slot');
  assert.equal(result.effect, 0);
  assert.equal(fs.existsSync(hintPath), true);
  if (fs.existsSync(hintPath)) {
    assert.deepEqual(JSON.parse(fs.readFileSync(hintPath, 'utf8')), {
      schema_version: 1,
      kind: 'life_manager_no_effect_result',
      status: 'verified_no_effect',
      effect: 0,
      owner_id: ownerId,
      occurrence_id: occurrenceId,
      reason: 'no_due_slot',
    });
  }
  fs.rmSync(dataDir, { recursive: true, force: true });
});
test("an idempotent Instagram replay normalizes only an exact Postiz readback", () => {
  const ownerId = "ebook-ja-instagram-daily";
  const occurrenceId = `${ownerId}:run-1`;
  const integrationId = "cmooplxmu04tpmd0y4h3cpk33";
  const integrationRef = `integration://postiz/instagram/${integrationId}`;
  const videoSha256 = "a".repeat(64);
  const captionSha256 = "b".repeat(64);
  const publicUrl = "https://www.instagram.com/reel/abc123";
  const job = buildMarketingVideoPublicationJob({
    tenantId: "dais-local",
    productId: "ebook-ja",
    formatId: "ebook-watercolor",
    form: "ebook-reflection-reel",
    locale: "ja",
    slot: "2026-10-07T03:30:00.000Z",
    creativeId: "baseline.ebook-ja.d3.s2-20261007T033000000Z",
    platform: "instagram",
    videoRef: `object://sha256/${videoSha256}`,
    captionRef: `object://sha256/${captionSha256}`,
    approvalRef: `object://sha256/${"c".repeat(64)}`,
    instagramProfileRef: "profile://instagram/obou.anicca",
    postizTokenRef: "secret://postiz/api-key",
    instagramIntegrationRef: integrationRef,
    slotScopedEffect: true,
  });
  const legacy = {
    schema_version: 1,
    kind: "marketing_video_distribution",
    status: "published",
    product_id: "ebook-ja",
    format_id: "ebook-watercolor",
    form: "ebook-reflection-reel",
    locale: "ja",
    slot: "2026-10-07T03:30:00.000Z",
    creative_id: "baseline.ebook-ja.d3.s2-20261007T033000000Z",
    platform: "instagram",
    video_sha256: videoSha256,
    caption_sha256: captionSha256,
    public_url: publicUrl,
    provider_post_id: "postiz-ig-1",
    provider_route: "instagram_file_script",
    provider_reconciled: true,
    published_at: "2026-10-07T07:03:41.088Z",
  };
  const context = {
    ownerId,
    occurrenceId,
    jobId: job.job_id,
    effectKey: job.effect_key,
    platform: "instagram",
    integrationId,
    accountId: "@obou.anicca",
  };
  const identity = {
    loop_id: ownerId,
    occurrence_id: occurrenceId,
    job_id: job.job_id,
    effect_key: job.effect_key,
    product_id: legacy.product_id,
    format_id: legacy.format_id,
    form: legacy.form,
    locale: legacy.locale,
    platform: legacy.platform,
    creative_id: legacy.creative_id,
    slot: legacy.slot,
    integration_ref: integrationRef,
    account_id: context.accountId,
    video_sha256: videoSha256,
    caption_sha256: captionSha256,
  };
  const proof = {
    status: "ready",
    owner_id: ownerId,
    occurrence_id: occurrenceId,
    verified: true,
    proof_kind: "postiz_official_readback",
    provider_receipt_id: legacy.provider_post_id,
    identity,
    provider_readback: {
      provider: "postiz",
      state: "PUBLISHED",
      post_id: legacy.provider_post_id,
      public_url: publicUrl,
      account_id: context.accountId,
      integration_ref: integrationRef,
      local_content: { video_sha256: videoSha256, caption_sha256: captionSha256 },
    },
  };
  const normalize = normalizePostizInstagramReceiptRoute;
  const result = typeof normalize === "function"
    ? normalize(legacy, context, proof)
    : undefined;

  assert.equal(result?.provider_route, "postiz");
  if (typeof normalize === "function") {
    assert.equal(legacy.provider_route, "instagram_file_script");
    assert.equal(
      normalize(legacy, { ...context, integrationId: "" }, proof).provider_route,
      "instagram_file_script",
    );
    assert.equal(
      normalize(legacy, context, {
        ...proof,
        identity: { ...identity, integration_ref: "integration://postiz/instagram/another" },
      }).provider_route,
      "instagram_file_script",
    );
    assert.equal(
      normalize(legacy, context, {
        ...proof,
        provider_readback: { ...proof.provider_readback, post_id: "another-post" },
      }).provider_route,
      "instagram_file_script",
    );
    assert.strictEqual(normalize(legacy, { ...context, platform: "tiktok" }, proof), legacy);
  }
});

test("legacy Postiz proof uses a read-only owner reconciler command", () => {
  const proof = { status: "ready", provider: "postiz" };
  const verify = verifyLegacyPostizReceipt;
  const result = typeof verify === "function" ? verify({
    root: "/release",
    python: "/python3",
    apiKey: "test-only",
    dataDir: "/state",
    tenantId: "dais-local",
    ownerId: "ebook-ja-instagram-daily",
    occurrenceId: "ebook-ja-instagram-daily:run-1",
    identityPath: "/state/identity.jsonl",
    ledgerPath: "/state/distribution.jsonl",
    env: { HOME: "/home/test", PATH: "/bin" },
    runner(command, args, options) {
      assert.equal(command, "/python3");
      assert.equal(args[0], "/release/apps/life-manager/scripts/mobile-postiz-provider-reconcile.py");
      assert.equal(args[1], "--verify-only");
      assert.equal(options.env.POSTIZ_API_KEY, "test-only");
      assert.equal(options.env.LM_RUNTIME_TENANT_ID, "dais-local");
      return { status: 0, stdout: JSON.stringify(proof) };
    },
  }) : undefined;

  assert.deepEqual(result, proof);
});

test("each eBook publication occurrence owns exactly one provider platform effect", () => {
  const slot = "2026-10-06T07:00:00.000Z";
  const jobs = Object.entries(JOBS).filter(([owner]) => owner.startsWith("ebook-ja-")).map(([, lane]) => buildMarketingVideoPublicationJob({
    tenantId: "dais-local",
    productId: "ebook-ja",
    formatId: "ebook-watercolor",
    form: "ebook-reflection-reel",
    locale: "ja",
    slot,
    creativeId: "baseline-ebook-ja-1-1",
    platform: lane.platform,
    videoRef: `object://sha256/${"a".repeat(64)}`,
    captionRef: `object://sha256/${"b".repeat(64)}`,
    approvalRef: `object://sha256/${"c".repeat(64)}`,
    instagramProfileRef: lane.platform === "instagram"
      ? "profile://instagram/obou.anicca" : "profile://instagram/unassigned",
    postizTokenRef: "secret://postiz/api-key",
    ...(lane.platform === "instagram"
      ? { instagramIntegrationRef: "integration://postiz/instagram/cmooplxmu04tpmd0y4h3cpk33" }
      : { tiktokIntegrationRef: "integration://postiz/tiktok/cmo5s4edx00vgn10ygnu34a0n" }),
    slotScopedEffect: true,
  }));

  assert.equal(jobs.length, 2);
  assert.equal(new Set(jobs.map((job) => job.input_refs.platform_ref)).size, 2);
  assert.deepEqual(jobs.map((job) => job.effect_class), ["publish", "publish"]);
  assert.equal(jobs.every((job) => job.loop_id === "marketing.video.publish"), true);
});

test("an unregistered eBook account fails before any render or provider work", async () => {
  const dataDir = path.join(os.tmpdir(), `ebook-closed-${process.pid}-${Date.now()}`);
  const env = {
    LIFE_MANAGER_LOOP_ID: "ebook-ja-instagram-daily",
    LIFE_MANAGER_OCCURRENCE_ID: "ebook-ja-instagram-daily:run-1",
    LIFE_MANAGER_RELEASE_ROOT: ROOT,
    LIFE_MANAGER_RESULT_HINT_PATH: path.join(dataDir, "entrypoint-result.json"),
    LM_DATA_DIR: dataDir,
    LM_RUNTIME_TENANT_ID: "dais-local",
  };
  const pack = { ...PACK, accounts: PACK.accounts.filter((row) => row.account_id !== "instagram.obou_anicca") };
  assert.throws(() => selectTarget({
    root: ROOT, pack, ownerId: "ebook-ja-instagram-daily",
    platform: "instagram", accountId: "instagram.obou_anicca",
  }));
  await assert.rejects(run(["ebook-ja-instagram-daily"], {
    env,
    nowMs: Date.parse("2026-10-06T08:00:00+09:00"),
  }), /readiness gate is closed/);
  assert.equal(fs.existsSync(dataDir), false);
});

test("the standing policy only approves the current Japanese baseline claim set", () => {
  const script = {
    product_id: "ebook-ja",
    language: "ja",
    baseline: true,
    renderer_id: "watercolor-monk",
    cta: "アニッチャ・リセットを読む",
    source_mechanism_ids: ["baseline.owner-authored.ebook-ja.1.1"],
  };
  const pack = {
    product_id: "ebook-ja",
    renderer_id: "watercolor-monk",
    allowed_claims: [...APPROVED_CLAIMS],
  };

  assert.equal(approvedBaselineScript(script, pack), true);
  assert.equal(approvedBaselineScript({ ...script, baseline: false }, pack), false);
  assert.equal(approvedBaselineScript(script, {
    ...pack, allowed_claims: [...APPROVED_CLAIMS, "guaranteed results"],
  }), false);
});
