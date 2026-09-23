"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { resolveMobileAppLoop } = require("./mobile-app-command.js");

const root = path.resolve(__dirname, "../../..");
const manifest = require("../config/mobile-app-loops.json");
const products = require("../config/mobile-products.json");
const registry = require("../../../config/loop-registry.json");

test("all mobile publication loops share one command and one manifest", () => {
  assert.equal(Object.keys(manifest.loops).length, 18);
  assert.deepEqual(
    new Set(products.products.map((item) => item.product_id)),
    new Set(Object.values(manifest.loops).map((item) => item.product_id)),
  );
  assert.doesNotMatch(JSON.stringify(products), /\/Users\/|openclaw|hermes|credential/iu);
  for (const [loopId, expected] of Object.entries(manifest.loops)) {
    const entry = registry.loops[loopId];
    assert.ok(entry, loopId);
    assert.equal(entry.entrypoint, "apps/life-manager/scripts/mobile-app");
    assert.equal(entry.adapter, "exec");
    assert.deepEqual(entry.command, [loopId]);
    const resolved = resolveMobileAppLoop(loopId);
    assert.equal(resolved.productId, expected.product_id);
    assert.equal(path.basename(resolved.runner), expected.runner);
    assert.equal(resolved.action, expected.action);
    const product = products.products.find((item) => item.product_id === expected.product_id);
    assert.ok(product, expected.product_id);
    assert.equal(resolved.origin, product.origin);
    assert.equal(resolved.workspaceRel, `mobile-products/${expected.product_id}`);
    assert.deepEqual(resolved.source, {
      ...product.source,
      git_remote: new URL(product.source.git_remote).toString(),
    });
    if (expected.product_id === "anicca-ios") {
      assert.equal(resolved.source.canonical_source_rel, "apps/mobile/anicca-ios");
      assert.ok(fs.existsSync(path.join(root, resolved.source.canonical_source_rel, "aniccaios.xcodeproj", "project.pbxproj")));
    }
    if (expected.product_id === "honne-ai") {
      assert.equal(resolved.source.canonical_source_rel, "apps/mobile/honne-ai");
      assert.ok(fs.existsSync(path.join(root, resolved.source.canonical_source_rel, "BenYinFanYiAI.xcodeproj", "project.pbxproj")));
    }
  }
});

test("retired per-lane boot wrappers are absent", () => {
  for (const file of fs.readdirSync(path.join(root, "apps/life-manager/scripts"))) {
    assert.ok(!/-production-boot\.sh$/.test(file) || /^(instagram|tiktok)-metrics-production-boot\.sh$/.test(file), file);
  }
});

test("the shared mobile wrapper is host portable and uses the repository timeout", () => {
  const wrapper = fs.readFileSync(path.join(root, "apps/life-manager/scripts/mobile-app"), "utf8");
  assert.match(wrapper, /command -v node/);
  assert.match(wrapper, /command -v python3/);
  assert.match(wrapper, /runtime\/run-with-timeout\.py/);
  assert.match(wrapper, /LIFE_MANAGER_MOBILE_PRODUCT_ORIGIN/);
  assert.match(wrapper, /LIFE_MANAGER_MOBILE_PRODUCT_WORKSPACE_REL/);
  assert.doesNotMatch(wrapper, /\/opt\/homebrew|\/Users\/|openclaw|hermes|profitable-claude/iu);
});

test("the shared mobile wrapper reconciles one exact prior occurrence before the runner", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lm-mobile-wrapper-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const calls = path.join(directory, "python-calls.txt");
  const python = path.join(directory, "python");
  const envFile = path.join(directory, "marketing.env");
  const resultHint = path.join(directory, "effect-result.json");
  fs.writeFileSync(
    python,
    `#!/bin/sh\nprintf '%s\\n' "$*" >> "${calls}"\ncase "$1" in\n  *run-with-timeout.py) printf '%s\\n' '{"publication":{"created":false,"provider_post_id":"postiz-existing-1"}}' ;;\nesac\nexit 0\n`,
    { mode: 0o700 },
  );
  fs.writeFileSync(
    envFile,
    `LM_POSTIZ_API_KEY=test-token\nLM_DATA_DIR=${directory}/data\nLM_RUNTIME_TENANT_ID=dais-local\n`,
    { mode: 0o600 },
  );

  const result = spawnSync(
    path.join(root, "apps/life-manager/scripts/mobile-app"),
    ["life-manager-honne-ja"],
    {
      cwd: root,
      env: {
        ...process.env,
        LIFE_MANAGER_MARKETING_ENV_FILE: envFile,
        LIFE_MANAGER_PYTHON: python,
        LIFE_MANAGER_LOOP_ID: "life-manager-honne-ja",
        LIFE_MANAGER_OCCURRENCE_ID: "life-manager-honne-ja:run-1",
        LIFE_MANAGER_RESULT_HINT_PATH: resultHint,
      },
      encoding: "utf8",
    },
  );

  assert.equal(result.status, 0, result.stderr);
  const invoked = fs.readFileSync(calls, "utf8").trim().split("\n");
  assert.equal(invoked.length, 2);
  assert.match(invoked[0], /mobile-postiz-provider-reconcile\.py --auto-owner life-manager-honne-ja/);
  assert.match(invoked[0], /--resolve/);
  assert.match(invoked[1], /runtime\/run-with-timeout\.py/);
  assert.equal(result.stdout.trim(), '{"publication":{"created":false,"provider_post_id":"postiz-existing-1"}}');
  assert.deepEqual(JSON.parse(fs.readFileSync(resultHint, "utf8")), {
    schema_version: 1,
    kind: "life_manager_effect_result",
    status: "verified_effect",
    effect: 1,
    owner_id: "life-manager-honne-ja",
    occurrence_id: "life-manager-honne-ja:run-1",
    provider: "postiz",
    provider_receipt_id: "postiz-existing-1",
    effect_status: "reconciled",
  });
  assert.equal(fs.statSync(resultHint).mode & 0o777, 0o600);
});

test("the mobile result helper accepts exact reconciled receipt shapes only", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lm-mobile-result-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const helper = path.join(root, "apps/life-manager/scripts/mobile-effect-result.js");

  function run(publication, name) {
    const input = path.join(directory, `${name}.stdout`);
    const output = path.join(directory, `${name}.json`);
    fs.writeFileSync(input, `${JSON.stringify({ publication })}\n`);
    const result = spawnSync(process.execPath, [helper, input], {
      cwd: root,
      env: {
        ...process.env,
        LIFE_MANAGER_LOOP_ID: "life-manager-honne-en",
        LIFE_MANAGER_OCCURRENCE_ID: "life-manager-honne-en:run-1",
        LIFE_MANAGER_RESULT_HINT_PATH: output,
      },
      encoding: "utf8",
    });
    return { output, result };
  }

  const reconciled = run({
    status: "published",
    provider_reconciled: true,
    replay_created: false,
    provider_post_id: "postiz-honne-en-1",
  }, "honne-en");
  assert.equal(reconciled.result.status, 0, reconciled.result.stderr);
  assert.equal(JSON.parse(fs.readFileSync(reconciled.output, "utf8")).effect_status, "reconciled");

  const created = run({
    created: true,
    provider_post_id: "postiz-created-1",
  }, "created");
  assert.equal(created.result.status, 0, created.result.stderr);
  assert.equal(JSON.parse(fs.readFileSync(created.output, "utf8")).effect_status, "verified");

  const ambiguous = run({ provider_post_id: "postiz-ambiguous-1" }, "ambiguous");
  assert.notEqual(ambiguous.result.status, 0);
  assert.equal(fs.existsSync(ambiguous.output), false);
});

test("unknown loop ids fail closed", () => {
  assert.throws(() => resolveMobileAppLoop("unknown-mobile-loop"), /manifest entry invalid/);
  assert.throws(() => resolveMobileAppLoop("../escape"), /loop id invalid/);
});

test("an unregistered or mismatched product fails before runner execution", (t) => {
  const directory = fs.mkdtempSync(path.join(require("node:os").tmpdir(), "lm-mobile-loop-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const registryFile = path.join(directory, "products.json");
  fs.writeFileSync(registryFile, JSON.stringify({ schema_version: 1, products: [] }));
  assert.throws(
    () => resolveMobileAppLoop("life-manager-honne-ja", undefined, registryFile),
    /product is not registered/,
  );
});
