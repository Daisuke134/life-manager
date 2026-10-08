"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  POSTIZ_INTEGRATIONS_URL,
  createMarketingLaneManifest,
  fetchPostizIntegrationRegistry,
  isMarketingLaneManifest,
  serializeMarketingLaneManifest,
  writeMarketingLaneManifest,
} = require("./marketing-lane-manifest.js");

function row(overrides = {}) {
  return {
    id: "live-tt-honne-en",
    provider: "postiz",
    platform: "tiktok",
    profile: "@honne_reveal",
    account: "honne-en",
    product_id: "honne-ai",
    locale: "en",
    disabled: false,
    verified: true,
    ...overrides,
  };
}

function createManifest(input, options = {}) {
  const rows = Array.isArray(input) ? input : input.integrations;
  const config = { tenantId: "dais-local", ...options };
  if (!Object.hasOwn(config, "assignments")) config.assignments = rows.map((item) => ({ ...item }));
  return createMarketingLaneManifest(input, config);
}

test("creates a frozen secret-free manifest from explicit live routes", () => {
  const manifest = createManifest({
    tenant_id: "dais-local",
    integrations: [
      row({ lane_state: "production-armed" }),
      row({
        id: "live-ig-honne-en",
        platform: "instagram",
        profile: "@honne_reveal_ig",
        account: "honne-en-ig",
        lane_state: "default-off",
      }),
      row({
        id: "live-yt-anicca",
        platform: "youtube",
        profile: "@anicca-jp",
        account: "anicca-main-ja",
        product_id: "anicca",
        locale: "ja",
        disabled: true,
        lane_state: "disabled",
      }),
    ],
  });

  assert.equal(manifest.schema_version, 1);
  assert.match(manifest.manifest_id, /^marketing-lane-manifest:[0-9a-f]{64}$/);
  assert.equal(isMarketingLaneManifest(manifest), true);
  assert.equal(Object.isFrozen(manifest), true);
  assert.equal(Object.isFrozen(manifest.lanes), true);
  assert.equal(serializeMarketingLaneManifest(manifest), serializeMarketingLaneManifest(manifest));
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-lane-manifest-"));
  const output = writeMarketingLaneManifest(manifest, { dataDir });
  assert.equal(output, path.join(dataDir, "marketing", "lane-manifest.json"));
  assert.equal(fs.readFileSync(output, "utf8").trim(), serializeMarketingLaneManifest(manifest));
  assert.deepEqual(
    manifest.lanes.map(({ platform, product_id, lane_state, production_armed }) => ({
      platform, product_id, lane_state, production_armed,
    })),
    [
      { platform: "youtube", product_id: "anicca", lane_state: "disabled", production_armed: false },
      { platform: "instagram", product_id: "honne-ai", lane_state: "default-off", production_armed: false },
      { platform: "tiktok", product_id: "honne-ai", lane_state: "production-armed", production_armed: true },
    ],
  );
  assert.doesNotMatch(JSON.stringify(manifest), /token|secret|cookie|password|credential|openclaw|\/Users\//i);
});

test("encodes classified targets separately from unclassified zero-day holds", () => {
  const target = row({
    owner: "life-manager",
    lane_state: "default-off",
    disposition: "target",
    renderer: "reelclaw",
    format: "relationship-confession",
    approved_pack: "honne-ai-reelclaw-en.pack.json",
    canary_state: "verified",
    target_daily_limit: 3,
  });
  const manifest = createManifest({
    tenant_id: "dais-local",
    integrations: [target],
    holds: [{
      integration_id: "live-tt-unclassified",
      platform: "tiktok",
      account: "@unclassified",
      provider: "postiz",
      provider_disabled: false,
      owner: "life-manager",
      disposition: "hold",
      target_daily_limit: 0,
      verified: true,
    }],
  });
  assert.equal(manifest.schema_version, 2);
  assert.equal(manifest.lanes[0].production_armed, false);
  assert.equal(manifest.lanes[0].target_daily_limit, 3);
  assert.deepEqual(manifest.holds, [{
    integration_id: "live-tt-unclassified",
    platform: "tiktok",
    account: "@unclassified",
    provider: "postiz",
    provider_disabled: false,
    owner: "life-manager",
    disposition: "hold",
    target_daily_limit: 0,
  }]);
  assert.equal(isMarketingLaneManifest(manifest), true);
  assert.throws(
    () => createManifest({ tenant_id: "dais-local", integrations: [target], holds: [] }),
    /portfolio incomplete/i,
  );
  assert.throws(
    () => createManifest({
      tenant_id: "dais-local",
      integrations: [target],
      holds: [{ ...manifest.holds[0], target_daily_limit: 1, verified: true }],
    }),
    /hold disposition invalid/i,
  );
});

test("keeps X as a zero-day hold and permits only the selected Anicca YouTube skip", () => {
  const target = row({
    owner: "life-manager",
    lane_state: "default-off",
    disposition: "target",
    renderer: "reelclaw",
    format: "relationship-confession",
    approved_pack: "honne-ai-reelclaw-en.pack.json",
    canary_state: "verified",
    target_daily_limit: 3,
  });
  const manifest = createManifest({
    tenant_id: "dais-local",
    integrations: [target],
    holds: [
      {
        integration_id: "live-x-anicca",
        platform: "x",
        account: "@aniccaxxx",
        provider: "postiz",
        provider_disabled: false,
        owner: "life-manager",
        disposition: "hold",
        target_daily_limit: 0,
        verified: true,
      },
      {
        integration_id: "live-yt-anicca-skip",
        platform: "youtube",
        account: "@anicca-jp",
        provider: "postiz",
        provider_disabled: false,
        owner: "life-manager",
        disposition: "skip",
        target_daily_limit: 0,
        verified: true,
      },
    ],
  });
  assert.deepEqual(manifest.holds.map(({ platform, account, owner, disposition }) => ({
    platform, account, owner, disposition,
  })), [
    { platform: "x", account: "@aniccaxxx", owner: "life-manager", disposition: "hold" },
    { platform: "youtube", account: "@anicca-jp", owner: "life-manager", disposition: "skip" },
  ]);
  assert.equal(isMarketingLaneManifest(manifest), true);
  assert.throws(
    () => createManifest({
      tenant_id: "dais-local",
      integrations: [target],
      holds: [{
        integration_id: "wrong-skip",
        platform: "youtube",
        account: "@another-channel",
        provider: "postiz",
        provider_disabled: false,
        owner: "life-manager",
        disposition: "skip",
        target_daily_limit: 0,
        verified: true,
      }],
    }),
    /hold disposition invalid/i,
  );
});

test("normalizes Postiz's instagram-standalone identifier without copying raw payload fields", () => {
  const manifest = createManifest([row({
    identifier: "instagram-standalone",
    platform: undefined,
    id: "live-ig-standalone",
    account: "honne-en-ig",
    profile: "@honne_reveal_ig",
    picture: "https://cdn.example/avatar.jpg",
    customer: { email: "private@example.test" },
    raw_payload: { token: "must-not-escape" },
  })], { tenantId: "dais-local" });
  assert.equal(manifest.lanes[0].platform, "instagram");
  assert.doesNotMatch(JSON.stringify(manifest), /picture|customer|raw_payload|private@example|must-not-escape/i);
});

test("requires explicit tenant/product/locale/platform/account/integration/disabled fields", () => {
  for (const missing of ["product_id", "locale", "platform", "account", "disabled"]) {
    const value = row();
    delete value[missing];
    assert.throws(
      () => createManifest([value]),
      /invalid|required|unknown/i,
      missing,
    );
  }
  assert.throws(
    () => createManifest([row({ provider: "unknown" })]),
    /provider unknown/i,
  );
  assert.throws(
    () => createManifest([row({ product_id: "historical-pack" })]),
    /product unknown/i,
  );
});

test("fails closed when assignments or strict live verification are absent", () => {
  assert.throws(
    () => createMarketingLaneManifest([row()], { tenantId: "dais-local" }),
    /assignments required/i,
  );
  for (const verified of [undefined, false, "true", " true "]) {
    const liveRow = row();
    if (verified === undefined) delete liveRow.verified;
    else liveRow.verified = verified;
    assert.throws(
      () => createMarketingLaneManifest([liveRow], {
        tenantId: "dais-local",
        assignments: [{ ...liveRow, verified: true }],
      }),
      /live-verified|verified invalid|ambiguous/i,
      `verified=${String(verified)}`,
    );
  }
  assert.throws(
    () => createMarketingLaneManifest([row()], {
      tenantId: "dais-local",
      assignments: [{ ...row(), verified: undefined }],
    }),
    /live-verified|verified invalid|ambiguous/i,
  );
});

test("assignments cannot rewrite any route identity alias", () => {
  const mismatches = [
    ["platform", { identifier: "instagram-standalone" }],
    ["product", { product: "anicca" }],
    ["tenant", { tenant: "other-tenant" }],
    ["profile", { profile_handle: "@different-profile" }],
    ["account", { account_id: "different-account" }],
    ["provider", { provider_name: "other-provider" }],
  ];
  for (const [label, assignmentAlias] of mismatches) {
    const liveRow = row({ id: `mismatch-${label}` });
    const assignment = { ...liveRow, ...assignmentAlias };
    assert.throws(
      () => createMarketingLaneManifest([liveRow], { tenantId: "dais-local", assignments: [assignment] }),
      /ambiguous/i,
      label,
    );
  }
});

test("rejects ambiguous evidence, profile aliases, and registry containers", () => {
  const mixedEvidence = row({ source: "live", profile_status: "unknown" });
  assert.throws(
    () => createManifest([mixedEvidence]),
    /live-verified/i,
  );
  const conflictingProfileAliases = row({
    profile: { handle: "@honne_reveal", username: "@different-profile" },
  });
  assert.throws(
    () => createManifest([conflictingProfileAliases]),
    /profile ambiguous|assignment ambiguous/i,
  );
  assert.throws(
    () => createMarketingLaneManifest({
      tenant_id: "dais-local",
      tenant: "other-tenant",
      integrations: [row()],
      assignments: [row()],
    }, { tenantId: "dais-local", assignments: [row()] }),
    /tenant ambiguous|assignment ambiguous/i,
  );
  assert.throws(
    () => createMarketingLaneManifest({
      tenant_id: "dais-local",
      integrations: [row()],
      rows: [row({ id: "another-row" })],
      assignments: [row()],
    }, { tenantId: "dais-local", assignments: [row()] }),
    /ambiguous/i,
  );
});

test("rejects a profile URL whose platform differs from the assigned lane", () => {
  const mismatched = row({ profile: "https://www.youtube.com/@honne_reveal" });
  assert.throws(
    () => createManifest([mismatched]),
    /profile\/platform ambiguous/i,
  );
  const hiddenMismatchedAlias = row({
    profile: "@honne_reveal",
    profile_handle: "https://www.youtube.com/@honne_reveal",
  });
  assert.throws(
    () => createManifest([hiddenMismatchedAlias]),
    /profile\/platform ambiguous|assignment ambiguous/i,
  );
});

test("allows only Anicca YouTube lanes after the direct-URL contract", () => {
  const manifest = createManifest([row({
    id: "anicca-ai-youtube",
    product_id: "anicca",
    platform: "youtube",
    profile: "@anicca-ai",
    account: "@anicca-ai",
    disabled: false,
    lane_state: "production-armed",
    production_armed: true,
  })]);
  assert.equal(manifest.lanes[0].production_armed, true);
});

test("blocks Honne YouTube and duplicate or historical routes without guessing", () => {
  assert.throws(
    () => createManifest([row({ platform: "youtube" })]),
    /Honne YouTube/i,
  );
  assert.throws(
    () => createManifest([row(), row({ id: "live-tt-honne-en-2" })]),
    /ambiguous/i,
  );
  assert.throws(
    () => createManifest([row({ historical: true })]),
    /live-verified/i,
  );
  assert.throws(
    () => createManifest([row({ source: "unknown" })]),
    /live-verified/i,
  );
  assert.throws(
    () => createManifest([row({ source: " unknown " })]),
    /live-verified/i,
  );
  assert.throws(
    () => createManifest([row({ historical: "true" })]),
    /live-verified/i,
  );
});

test("explicit assignments must each match exactly one live registry row", () => {
  const expected = row({ id: "expected-route", account: "honne-en-expected" });
  assert.throws(
    () => createMarketingLaneManifest([expected], {
      tenantId: "dais-local",
      assignments: [expected, row({ id: "missing-route", account: "honne-en-missing" })],
    }),
    /assignment missing/i,
  );
  assert.throws(
    () => createMarketingLaneManifest([
      expected,
      row({ id: "second-route", account: "honne-en-expected" }),
    ], { tenantId: "dais-local", assignments: [expected] }),
    /missing|ambiguous/i,
  );
});

test("disabled, default-off, and shadow routes never become production-armed", () => {
  const manifest = createManifest([
    row({ id: "disabled", account: "honne-en-disabled", disabled: true }),
    row({ id: "default-off", account: "honne-en-default", disabled: false, lane_state: "default-off" }),
    row({ id: "shadow", account: "honne-en-shadow", disabled: false, lane_state: "shadow" }),
  ], { tenantId: "dais-local" });
  assert.deepEqual(manifest.lanes.map((lane) => lane.production_armed), [false, false, false]);
  assert.throws(
    () => createManifest([row({ disabled: true, lane_state: "production-armed" })]),
    /disabled state/i,
  );
  assert.throws(
    () => createManifest([row({ disabled: false, lane_state: "disabled" })]),
    /disabled state/i,
  );
  assert.throws(
    () => createManifest([row({ production_armed: true, lane_state: "shadow" })]),
    /production state/i,
  );
  assert.throws(
    () => createManifest([row({ lane_state: "production-armed", production_armed: false })]),
    /production state/i,
  );
  const assignmentWithFalseProductionState = row({ lane_state: "production-armed" });
  assert.throws(
    () => createMarketingLaneManifest([assignmentWithFalseProductionState], {
      tenantId: "dais-local",
      assignments: [{ ...assignmentWithFalseProductionState, production_armed: false }],
    }),
    /production state|ambiguous/i,
  );
});

test("recognizes the disabled English eBook route without arming it", () => {
  const manifest = createManifest([row({
    id: "ebook-en-provider-disabled",
    product_id: "ebook-en",
    locale: "en",
    platform: "tiktok",
    profile: "@monk_anicca",
    account: "ebook-en-tiktok",
    disabled: true,
    lane_state: "disabled",
  })]);

  assert.equal(manifest.lanes[0].product_id, "ebook-en");
  assert.equal(manifest.lanes[0].disabled, true);
  assert.equal(manifest.lanes[0].production_armed, false);
});

test("a verified portfolio target can become production-armed at its declared limit", () => {
  const target = row({
    disposition: "target",
    renderer: "reelclaw",
    format: "relationship-confession",
    approved_pack: "honne-en.pack.json",
    canary_state: "verified",
    target_daily_limit: 3,
    lane_state: "production-armed",
    production_armed: true,
  });
  const manifest = createMarketingLaneManifest(
    { tenant_id: "tenant-1", integrations: [target], holds: [{
      integration_id: "held-route",
      platform: "instagram",
      account: "@held",
      provider: "postiz",
      provider_disabled: false,
      disposition: "hold",
      target_daily_limit: 0,
      verified: true,
    }] },
    { tenantId: "tenant-1", assignments: [target] },
  );
  assert.equal(manifest.lanes[0].production_armed, true);
  assert.equal(manifest.lanes[0].target_daily_limit, 3);
});

test("Postiz registry fetch is GET-only, injectable, and fails with an exact missing-secret blocker", async () => {
  await assert.rejects(
    fetchPostizIntegrationRegistry({}),
    /Postiz integration registry fetch blocked: access token unavailable/i,
  );
  const calls = [];
  const body = { integrations: [row()] };
  const result = await fetchPostizIntegrationRegistry({
    accessToken: "test-token",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return { ok: true, status: 200, json: async () => body };
    },
  });
  assert.deepEqual(result, body);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, POSTIZ_INTEGRATIONS_URL);
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.headers.Authorization, "test-token");
  let customEndpointCalled = false;
  await assert.rejects(
    fetchPostizIntegrationRegistry({
      accessToken: "test-token",
      endpoint: "https://attacker.example/integrations",
      fetchImpl: async () => { customEndpointCalled = true; return { ok: true, json: async () => body }; },
    }),
    /endpoint invalid/i,
  );
  assert.equal(customEndpointCalled, false);
  await assert.rejects(
    fetchPostizIntegrationRegistry({
      accessToken: "test-token",
      fetchImpl: async () => ({ ok: false, status: 401 }),
    }),
    /fetch failed: HTTP 401/i,
  );
});

test("writer rejects ambiguous data roots and durably replaces the manifest", () => {
  const manifest = createManifest([row()]);
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-lane-writer-"));
  const otherDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-lane-writer-other-"));
  assert.throws(
    () => writeMarketingLaneManifest(manifest, { dataDir, env: { LM_DATA_DIR: otherDir } }),
    /data roots ambiguous/i,
  );
  const output = writeMarketingLaneManifest(manifest, { dataDir, env: { LM_DATA_DIR: dataDir } });
  assert.equal(fs.readFileSync(output, "utf8").trim(), serializeMarketingLaneManifest(manifest));
  assert.deepEqual(fs.readdirSync(path.dirname(output)).filter((name) => name.includes(".tmp-")), []);
});
