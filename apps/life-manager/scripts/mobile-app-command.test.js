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
  assert.equal(Object.keys(manifest.loops).length, 18); // obou-instagram retired (ebook account, out of mobile scope)
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

test("the EN2 TikTok account resolves to the shared Anicca iOS carousel runner", () => {
  const resolved = resolveMobileAppLoop("life-manager-anicca-en2-affirmation-tiktok");
  assert.equal(resolved.productId, "anicca-ios");
  assert.equal(path.basename(resolved.runner), "anicca-larry-ja-rotating.js");
  assert.equal(resolved.action, "run-en2-affirmation-tiktok-production");
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

for (const binding of [
  {name: "bound", value: "a".repeat(40), expected: "a".repeat(40)},
  {name: "absent", value: undefined, expected: "unset"},
  {name: "empty", value: "", expected: ""},
]) {
test(`the shared mobile wrapper preserves ${binding.name} release binding through reconciliation and runner`, (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lm-mobile-wrapper-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const calls = path.join(directory, "python-calls.txt");
  const python = path.join(directory, "python");
  const envFile = path.join(directory, "marketing.env");
  const resultHint = path.join(directory, "effect-result.json");
  const releaseSha = binding.expected;
  const staleReleaseSha = "b".repeat(40);
  fs.writeFileSync(
    python,
    `#!/bin/sh\nprintf '%s|release=%s\\n' "$*" "\${LIFE_MANAGER_RELEASE_SHA-unset}" >> "${calls}"\ncase "$1" in\n  *run-with-timeout.py) printf '%s\\n' '{"publication":{"created":false,"status":"published","provider_reconciled":true,"replay_created":false,"provider_post_id":"postiz-existing-1"}}' ;;\n  *) printf '%s\\n' '{"status":"no_match"}' ;;\nesac\nexit 0\n`,
    { mode: 0o700 },
  );
  fs.writeFileSync(
    envFile,
    `LM_POSTIZ_API_KEY=test-token\nLM_DATA_DIR=${directory}/data\nLM_RUNTIME_TENANT_ID=dais-local\nLIFE_MANAGER_RELEASE_SHA=${staleReleaseSha}\n`,
    { mode: 0o600 },
  );

  const result = spawnSync(
    path.join(root, "apps/life-manager/scripts/mobile-app"),
    ["life-manager-honne-ja"],
    {
      cwd: root,
      env: {
        ...Object.fromEntries(Object.entries(process.env).filter(([key]) => key !== "LIFE_MANAGER_RELEASE_SHA")),
        LIFE_MANAGER_MARKETING_ENV_FILE: envFile,
        LIFE_MANAGER_PYTHON: python,
        LIFE_MANAGER_LOOP_ID: "life-manager-honne-ja",
        LIFE_MANAGER_OCCURRENCE_ID: "life-manager-honne-ja:run-1",
        LIFE_MANAGER_RESULT_HINT_PATH: resultHint,
        ...(binding.value === undefined ? {} : {LIFE_MANAGER_RELEASE_SHA: binding.value}),
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
  assert.ok(invoked.every((call) => call.endsWith(`|release=${releaseSha}`)), "the release binding must survive loading mutable marketing env");
  assert.equal(result.stdout.trim(), '{"publication":{"created":false,"status":"published","provider_reconciled":true,"replay_created":false,"provider_post_id":"postiz-existing-1"}}');
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
}

test("the shared mobile wrapper does not publish after an unresolved prior effect", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lm-mobile-unresolved-effect-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const calls = path.join(directory, "python-calls.txt");
  const runnerCalled = path.join(directory, "runner-called");
  const python = path.join(directory, "python");
  const envFile = path.join(directory, "marketing.env");
  fs.writeFileSync(
    python,
    `#!/bin/sh\nprintf '%s\\n' "$*" >> "${calls}"\ncase "$1" in\n  *mobile-postiz-provider-reconcile.py) printf '%s\\n' '{"status":"no_match","inspected":1}'; exit 1 ;;\n  *run-with-timeout.py) touch "${runnerCalled}"; printf '%s\\n' '{"publication":{"created":true,"provider_post_id":"should-not-publish"}}'; exit 0 ;;\n  *) exit 0 ;;\nesac\n`,
    { mode: 0o700 },
  );
  fs.writeFileSync(envFile, "LM_POSTIZ_API_KEY=test-token\nLM_DATA_DIR=/tmp/lm-mobile-data\nLM_RUNTIME_TENANT_ID=dais-local\n", { mode: 0o600 });

  const result = spawnSync(path.join(root, "apps/life-manager/scripts/mobile-app"), ["life-manager-honne-ja"], {
    cwd: root,
    env: {
      ...Object.fromEntries(Object.entries(process.env).filter(([key]) => key !== "LIFE_MANAGER_RELEASE_SHA")),
      LIFE_MANAGER_MARKETING_ENV_FILE: envFile,
      LIFE_MANAGER_NODE: process.execPath,
      LIFE_MANAGER_PYTHON: python,
      LIFE_MANAGER_LOOP_ID: "life-manager-honne-ja",
      LIFE_MANAGER_OCCURRENCE_ID: "life-manager-honne-ja:run-2",
    },
    encoding: "utf8",
  });

  assert.equal(result.status, 75, result.stderr);
  assert.match(result.stderr, /prior-effect reconciliation deferred/);
  assert.equal(fs.readFileSync(calls, "utf8").trim().split("\n").length, 1);
  assert.equal(fs.existsSync(runnerCalled), false);
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

test("retained #6591 fixture: an Instagram replay without official readback cannot settle an effect-unknown hold", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-effect-unknown-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const input = path.join(directory, "runner.stdout");
  const output = path.join(directory, "effect-result.json");
  fs.writeFileSync(input, `${JSON.stringify({ publication: { created: false, provider_post_id: "postiz-replay-6591" } })}\n`);

  const result = spawnSync(process.execPath, [path.join(root, "apps/life-manager/scripts/mobile-effect-result.js"), input], {
    cwd: root,
    env: {
      ...process.env,
      LIFE_MANAGER_LOOP_ID: "life-manager-anicca-main-instagram",
      LIFE_MANAGER_OCCURRENCE_ID: "life-manager-anicca-main-instagram:18db4935a708d788-75177",
      LIFE_MANAGER_RELEASE_SHA: "1a7a8e2faf1eb34931f05287d846fc036bc9eec0",
      LIFE_MANAGER_RESULT_HINT_PATH: output,
    },
    encoding: "utf8",
  });

  assert.notEqual(result.status, 0);
  assert.equal(fs.existsSync(output), false);

  const readbackInput = path.join(directory, "readback.stdout");
  const readbackOutput = path.join(directory, "readback-result.json");
  fs.writeFileSync(readbackInput, `${JSON.stringify({ publication: {
    created: false,
    status: "published",
    provider_reconciled: true,
    replay_created: false,
    provider_post_id: "postiz-replay-6591",
  } })}\n`);
  const readback = spawnSync(process.execPath, [path.join(root, "apps/life-manager/scripts/mobile-effect-result.js"), readbackInput], {
    cwd: root,
    env: {
      ...process.env,
      LIFE_MANAGER_LOOP_ID: "life-manager-anicca-main-instagram",
      LIFE_MANAGER_OCCURRENCE_ID: "life-manager-anicca-main-instagram:18db4935a708d788-75177",
      LIFE_MANAGER_RELEASE_SHA: "1a7a8e2faf1eb34931f05287d846fc036bc9eec0",
      LIFE_MANAGER_RESULT_HINT_PATH: readbackOutput,
    },
    encoding: "utf8",
  });
  assert.equal(readback.status, 0, readback.stderr);
  assert.equal(JSON.parse(fs.readFileSync(readbackOutput, "utf8")).effect_status, "reconciled");
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

test("the mobile wrapper uses managed Node and Python when launchd PATH has neither", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lm-mobile-managed-runtime-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const isolatedPath = path.join(directory, "path");
  fs.mkdirSync(isolatedPath);
  for (const [name, target] of Object.entries({
    bash: "/bin/bash",
    dirname: "/usr/bin/dirname",
    grep: "/usr/bin/grep",
    mktemp: "/usr/bin/mktemp",
    rm: "/bin/rm",
    tee: "/usr/bin/tee",
    tr: "/usr/bin/tr",
  })) {
    fs.symlinkSync(target, path.join(isolatedPath, name));
  }

  const managedNode = path.join(directory, "managed-node");
  const managedPython = path.join(directory, "managed-python");
  const nodeCalls = path.join(directory, "node-calls.txt");
  const pythonCalls = path.join(directory, "python-calls.txt");
  const envFile = path.join(directory, "marketing.env");
  fs.writeFileSync(managedNode, [
    "#!/bin/sh",
    "echo \"$1\" >> " + JSON.stringify(nodeCalls),
    "echo 'runner.js\tpublish\tanicca-ios\tappstore\tmobile-products/anicca-ios'",
    "",
  ].join("\n"), { mode: 0o700 });
  fs.writeFileSync(managedPython, [
    "#!/bin/sh",
    "echo \"$*\" >> " + JSON.stringify(pythonCalls),
    "case \"$1\" in",
    "  *mobile-postiz-provider-reconcile.py) exit 0 ;;",
    "  *run-with-timeout.py) echo '{\"runner\":\"ok\"}'; exit 0 ;;",
    "  *) exit 99 ;;",
    "esac",
    "",
  ].join("\n"), { mode: 0o700 });
  fs.writeFileSync(envFile, "LM_POSTIZ_API_KEY=fake-local-test-token\n", { mode: 0o600 });

  const result = spawnSync(path.join(root, "apps/life-manager/scripts/mobile-app"), [
    "life-manager-anicca-en2-affirmation-tiktok",
  ], {
    cwd: root,
    env: {
      HOME: directory,
      PATH: isolatedPath,
      TMPDIR: directory,
      LIFE_MANAGER_MARKETING_ENV_FILE: envFile,
      LIFE_MANAGER_RUNTIME_NODE: managedNode,
      LIFE_MANAGER_RUNTIME_PYTHON: managedPython,
    },
    encoding: "utf8",
  });

  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.readFileSync(nodeCalls, "utf8").trim(), path.join(root, "apps/life-manager/scripts/mobile-app-command.js"));
  assert.equal(fs.readFileSync(pythonCalls, "utf8").trim().split("\n").length, 2);
  assert.equal(result.stdout.trim(), '{"runner":"ok"}');
});
