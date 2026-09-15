"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const {
  buildProductLoopCompletionManifest,
  evaluateLocalCompletionGate,
  planProductOnboarding,
  readProductLoopCatalog,
} = require("./product-onboarding.js");

const ROOT = path.resolve(__dirname, "../../..");

test("one catalog describes all 14 public product loops on Local and Cloud", () => {
  const catalog = readProductLoopCatalog();
  assert.equal(catalog.loops.length, 14);
  assert.deepEqual(catalog.host_requirements, { local: ["telegram_credentials"], cloud: [] });
  assert.equal(new Set(catalog.loops.map((loop) => loop.id)).size, 14);
  for (const loop of catalog.loops) {
    assert.ok(loop.description.length > 20, loop.id);
    assert.ok(loop.hosts.local, `${loop.id} local`);
    assert.ok(loop.hosts.cloud, `${loop.id} cloud`);
  }
  const english = fs.readFileSync(path.join(ROOT, "README.md"), "utf8");
  const japanese = fs.readFileSync(path.join(ROOT, "README.ja.md"), "utf8");
  for (const loop of catalog.loops) {
    assert.match(english, new RegExp(loop.name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"));
    assert.match(japanese, new RegExp(loop.name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"));
  }
});

test("the catalog loads from the standalone Cloud application artifact", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cloud-onboarding-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "lib"), { recursive: true });
  fs.mkdirSync(path.join(root, "config"), { recursive: true });
  fs.copyFileSync(path.join(ROOT, "apps/life-manager/lib/product-onboarding.js"),
    path.join(root, "lib/product-onboarding.js"));
  fs.copyFileSync(path.join(ROOT, "apps/life-manager/config/product-loop-catalog.json"),
    path.join(root, "config/product-loop-catalog.json"));
  const packaged = require(path.join(root, "lib/product-onboarding.js"));
  assert.equal(packaged.readProductLoopCatalog().loops.length, 14);
  assert.equal(packaged.planProductOnboarding({
    host: "cloud", selected_loop_ids: ["agent-economy"],
  }).loops[0].state, "ready_to_start");
});

test("Local plans only selected loops and makes missing setup explicit", () => {
  const economy = planProductOnboarding({ host: "local", selected_loop_ids: ["agent-economy"],
    verified_requirements: ["telegram_credentials"] });
  assert.deepEqual(economy.selected_loop_ids, ["agent-economy"]);
  assert.equal(economy.loops[0].state, "ready_to_start");
  assert.deepEqual(economy.loops[0].command, ["./install.sh"]);
  assert.equal(economy.starts_automatically, false);
  assert.deepEqual(economy.external_effects, []);

  const connector = planProductOnboarding({ host: "local", selected_loop_ids: ["connector"],
    verified_requirements: ["telegram_credentials", "calendar", "telegram"] });
  assert.equal(connector.loops[0].state, "setup_required");
  assert.deepEqual(connector.loops[0].missing, ["provider_login_when_required"]);
  assert.deepEqual(connector.loops[0].command, ["./install.sh", "connector"]);
});

test("Cloud /start uses the same catalog while unsupported host adapters stay setup_required", () => {
  const economy = planProductOnboarding({ host: "cloud", selected_loop_ids: ["agent-economy"] });
  assert.equal(economy.loops[0].state, "ready_to_start");
  assert.deepEqual(economy.loops[0].command, ["/start"]);

  const mobile = planProductOnboarding({ host: "cloud", selected_loop_ids: ["mobile-apps"],
    verified_requirements: ["mobile_opportunity"] });
  assert.equal(mobile.loops[0].state, "setup_required");
  assert.deepEqual(mobile.loops[0].missing, ["host_adapter"]);
  assert.equal(mobile.loops[0].command, null);

  const investment = planProductOnboarding({ host: "cloud", selected_loop_ids: ["investment"],
    verified_requirements: ["alpaca_credentials", "investment_mode"] });
  assert.equal(investment.loops[0].state, "setup_required");
  assert.deepEqual(investment.loops[0].missing, ["host_adapter"]);
  assert.equal(investment.loops[0].command, null);
});

test("there is no start-all plan or Local enable-all endpoint", () => {
  for (const selected_loop_ids of [[], ["all"], ["connector", "connector"], ["unknown"]]) {
    assert.throws(() => planProductOnboarding({ host: "local", selected_loop_ids }));
  }
  const ui = fs.readFileSync(path.join(ROOT, "apps/oss-onboarding/index.html"), "utf8");
  const server = fs.readFileSync(path.join(ROOT, "scripts/life-manager-onboarding-server.py"), "utf8");
  assert.doesNotMatch(ui, /enableAll|Enable all|api\/enable-all/u);
  assert.doesNotMatch(server, /api\/enable-all/u);
});

test("the Local install entrypoint emits a zero-effect selected-loop plan", () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "lm-onboarding-plan-"));
  const result = spawnSync("bash", [path.join(ROOT, "install.sh"), "plan", "--loop", "agent-economy"], {
    cwd: ROOT, encoding: "utf8", env: { ...process.env, HOME: home },
  });
  fs.rmSync(home, { recursive: true, force: true });
  assert.equal(result.status, 0, result.stderr);
  const plan = JSON.parse(result.stdout);
  assert.equal(plan.host, "local");
  assert.deepEqual(plan.selected_loop_ids, ["agent-economy"]);
  assert.equal(plan.loops[0].state, "setup_required");
  assert.deepEqual(plan.loops[0].missing, ["telegram_credentials"]);
  assert.deepEqual(plan.external_effects, []);
});

test("Cloud provisioning is gated by the shared product model", () => {
  const source = fs.readFileSync(path.join(ROOT, "apps/life-manager/server.js"), "utf8");
  assert.match(source, /planProductOnboarding\(\{ host: "cloud", selected_loop_ids: \["agent-economy"\] \}\)/u);
  assert.match(source, /onboarding\.loops\[0\]\.command\?\.\[0\] !== "\/start"/u);
});

test("completion manifest covers every catalog loop and never treats unknown as complete", () => {
  const catalog = readProductLoopCatalog();
  const releaseSha = "a".repeat(40);
  const contract = {
    goal: true,
    context: true,
    admission: true,
    receipt: true,
    observability: true,
    evaluation: true,
  };
  const observations = catalog.loops.map((loop, index) => ({
    id: loop.id,
    state: index === 0 ? "unknown" : "setup_required",
    reason: index === 0 ? "evidence_not_collected" : "host_adapter_pending",
    contract,
  }));

  const manifest = buildProductLoopCompletionManifest({
    host: "local",
    release_sha: releaseSha,
    observations,
  });

  assert.equal(manifest.schema_version, "product.loop.completion.v1");
  assert.equal(manifest.loops.length, 14);
  assert.equal(manifest.unknown_count, 1);
  assert.equal(manifest.completion, false);
  assert.deepEqual(manifest.loops[0].job_ids, catalog.loops[0].job_ids);
  assert.deepEqual(manifest.loops.map((loop) => loop.id), catalog.loops.map((loop) => loop.id));
});

test("local completion gate blocks a manifest that still contains unknown loops", () => {
  const catalog = readProductLoopCatalog();
  const releaseSha = "4".repeat(40);
  const contract = {
    goal: true,
    context: true,
    admission: true,
    receipt: true,
    observability: true,
    evaluation: true,
  };
  const observations = catalog.loops.map((loop, index) => ({
    id: loop.id,
    state: index === 0 ? "unknown" : "setup_required",
    reason: index === 0 ? "evidence_not_collected" : "host_adapter_pending",
    contract,
  }));
  const manifest = buildProductLoopCompletionManifest({
    host: "local",
    release_sha: releaseSha,
    observations,
  });

  const gate = evaluateLocalCompletionGate(manifest);

  assert.deepEqual(gate, {
    schema_version: "product.local.completion.v1",
    decision: "block",
    host: "local",
    release_sha: releaseSha,
    reasons: ["unknown_product_loop"],
  });
});

test("local completion gate passes only explicit setup states or verified receipts", () => {
  const catalog = readProductLoopCatalog();
  const releaseSha = "5".repeat(40);
  const contract = {
    goal: true,
    context: true,
    admission: true,
    receipt: true,
    observability: true,
    evaluation: true,
  };
  const observations = catalog.loops.map((loop) => ({
    id: loop.id,
    state: "setup_required",
    reason: "host_adapter_pending",
    contract,
  }));
  observations[0] = {
    id: catalog.loops[0].id,
    state: "verified",
    owner_id: "owner-1",
    release_sha: releaseSha,
    official_receipt: true,
    contract,
  };
  const manifest = buildProductLoopCompletionManifest({
    host: "local",
    release_sha: releaseSha,
    observations,
  });

  const gate = evaluateLocalCompletionGate(manifest);

  assert.deepEqual(gate, {
    schema_version: "product.local.completion.v1",
    decision: "pass",
    host: "local",
    release_sha: releaseSha,
    reasons: [],
  });
});

test("verified completion requires an official receipt and the canonical release", () => {
  const catalog = readProductLoopCatalog();
  const releaseSha = "b".repeat(40);
  const contract = {
    goal: true,
    context: true,
    admission: true,
    receipt: true,
    observability: true,
    evaluation: true,
  };
  const observations = catalog.loops.map((loop) => ({
    id: loop.id,
    state: "not_applicable",
    reason: "provider_surface_not_supported",
    contract,
  }));
  observations[0] = {
    id: catalog.loops[0].id,
    state: "verified",
    owner_id: "owner-1",
    release_sha: "c".repeat(40),
    official_receipt: false,
    contract,
  };

  assert.throws(
    () => buildProductLoopCompletionManifest({
      host: "cloud",
      release_sha: releaseSha,
      observations,
    }),
    /verified loop requires official receipt and matching release/u,
  );
});

test("completion manifest binds runtime status to every mapped job without promoting health to effect", () => {
  const catalog = readProductLoopCatalog();
  const releaseSha = "f".repeat(40);
  const observations = catalog.loops.map((loop) => ({
    id: loop.id,
    state: "setup_required",
    reason: "provider_surface_pending",
    contract: {},
  }));
  const runtimeRows = catalog.loops.flatMap((loop) => loop.job_ids.map((loopId) => ({
    loop_id: loopId,
    installed_release_sha: releaseSha,
    event_release_sha: releaseSha,
    last_terminal_result: "pass",
  })));

  const manifest = buildProductLoopCompletionManifest({
    host: "local",
    release_sha: releaseSha,
    observations,
    runtime_rows: runtimeRows,
  });

  assert.deepEqual(manifest.loops[0].runtime_evidence, {
    observed_job_ids: catalog.loops[0].job_ids,
    missing_job_ids: [],
    release_mismatch_job_ids: [],
    non_pass_job_ids: [],
    release_match: true,
    terminal_pass: true,
    ready: true,
    reason: null,
  });
  assert.equal(manifest.loops.every((loop) => loop.state === "setup_required"), true);
  assert.equal(manifest.completion, true);
});

test("verified completion rejects missing or stale mapped runtime evidence", () => {
  const catalog = readProductLoopCatalog();
  const releaseSha = "1".repeat(40);
  const contract = {
    goal: true,
    context: true,
    admission: true,
    receipt: true,
    observability: true,
    evaluation: true,
  };
  const observations = catalog.loops.map((loop) => ({
    id: loop.id,
    state: "not_applicable",
    reason: "provider_surface_not_supported",
    contract,
  }));
  observations[0] = {
    id: catalog.loops[0].id,
    state: "verified",
    owner_id: "owner-1",
    release_sha: releaseSha,
    official_receipt: true,
    contract,
  };
  const runtimeRows = catalog.loops[0].job_ids.map((loopId, index) => ({
    loop_id: loopId,
    installed_release_sha: releaseSha,
    event_release_sha: index === 0 ? "2".repeat(40) : releaseSha,
    last_terminal_result: "pass",
  }));

  assert.throws(
    () => buildProductLoopCompletionManifest({
      host: "cloud",
      release_sha: releaseSha,
      observations,
      runtime_rows: runtimeRows,
    }),
    /runtime evidence incomplete/u,
  );
});

test("completion is true only when every loop is verified or explicitly unsupported", () => {
  const catalog = readProductLoopCatalog();
  const releaseSha = "d".repeat(40);
  const contract = {
    goal: true,
    context: true,
    admission: true,
    receipt: true,
    observability: true,
    evaluation: true,
  };
  const observations = catalog.loops.map((loop) => ({
    id: loop.id,
    state: "not_applicable",
    reason: "provider_surface_not_supported",
    contract,
  }));
  observations[0] = {
    id: catalog.loops[0].id,
    state: "verified",
    reason: "official_receipt_verified",
    owner_id: "owner-1",
    release_sha: releaseSha,
    official_receipt: true,
    contract,
  };

  const manifest = buildProductLoopCompletionManifest({
    host: "cloud",
    release_sha: releaseSha,
    observations,
  });

  assert.equal(manifest.completion, true);
  assert.equal(manifest.unknown_count, 0);
  assert.equal(manifest.counts.verified, 1);
  assert.equal(manifest.counts.not_applicable, 13);
});

test("completion manifest CLI writes a private deterministic projection", () => {
  const catalog = readProductLoopCatalog();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-completion-cli-"));
  const observationsPath = path.join(root, "observations.json");
  const outputPath = path.join(root, "completion.json");
  const observations = catalog.loops.map((loop) => ({
    id: loop.id,
    state: "setup_required",
    reason: "host_adapter_pending",
    contract: {},
  }));
  fs.writeFileSync(observationsPath, JSON.stringify(observations));

  const result = spawnSync(process.execPath, [
    path.join(ROOT, "apps/life-manager/scripts/product-loop-completion.js"),
    "--host", "cloud",
    "--release-sha", "e".repeat(40),
    "--observations", observationsPath,
    "--output", outputPath,
  ], { cwd: ROOT, encoding: "utf8" });

  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(fs.readFileSync(outputPath, "utf8")).completion, true);
  assert.equal(fs.statSync(outputPath).mode & 0o777, 0o600);
  fs.rmSync(root, { recursive: true, force: true });
});

test("completion manifest CLI binds lm-loop status JSON when requested", () => {
  const catalog = readProductLoopCatalog();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-completion-runtime-cli-"));
  const observationsPath = path.join(root, "observations.json");
  const runtimePath = path.join(root, "runtime-status.json");
  const outputPath = path.join(root, "completion.json");
  const releaseSha = "2".repeat(40);
  const observations = catalog.loops.map((loop) => ({
    id: loop.id,
    state: "setup_required",
    reason: "host_adapter_pending",
    contract: {},
  }));
  const runtimeRows = catalog.loops.flatMap((loop) => loop.job_ids.map((loopId) => ({
    loop_id: loopId,
    installed_release_sha: releaseSha,
    event_release_sha: releaseSha,
    last_terminal_result: "pass",
  })));
  fs.writeFileSync(observationsPath, JSON.stringify(observations));
  fs.writeFileSync(runtimePath, JSON.stringify(runtimeRows));

  const result = spawnSync(process.execPath, [
    path.join(ROOT, "apps/life-manager/scripts/product-loop-completion.js"),
    "--host", "local",
    "--release-sha", releaseSha,
    "--observations", observationsPath,
    "--runtime-status", runtimePath,
    "--output", outputPath,
  ], { cwd: ROOT, encoding: "utf8" });

  assert.equal(result.status, 0, result.stderr);
  const manifest = JSON.parse(fs.readFileSync(outputPath, "utf8"));
  assert.equal(manifest.loops[0].runtime_evidence.ready, true);
  fs.rmSync(root, { recursive: true, force: true });
});

test("each public product loop maps only to existing canonical runtime jobs", () => {
  const catalog = readProductLoopCatalog();
  const registry = JSON.parse(fs.readFileSync(
    path.join(ROOT, "config/loop-registry.json"),
    "utf8",
  ));
  const seen = new Set();
  for (const loop of catalog.loops) {
    assert.ok(Array.isArray(loop.job_ids) && loop.job_ids.length > 0, loop.id);
    for (const jobId of loop.job_ids) {
      assert.equal(typeof jobId, "string", `${loop.id}: job id type`);
      assert.equal(seen.has(jobId), false, `${jobId}: assigned more than once`);
      seen.add(jobId);
      const job = registry.loops[jobId];
      assert.ok(job, `${loop.id}: unknown job ${jobId}`);
      assert.match(String(job.label || ""), /^ai\./u);
      assert.ok(String(job.entrypoint || "").length > 0, `${jobId}: entrypoint`);
      assert.ok(job.cadence && typeof job.cadence === "object", `${jobId}: cadence`);
      assert.ok(String(job.effect_class || "").length > 0, `${jobId}: effect class`);
    }
  }
});
