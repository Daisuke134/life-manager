"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { validateLoopContract } = require("./loop-contract-gate.js");

const RECOVERY_CLASSES = [
  "browser",
  "continuous_service",
  "deterministic",
  "external_effect_owner",
  "model",
  "read_only_external_owner",
];

const recoveryFixtures = () => ({
  schema_version: 1,
  classes: RECOVERY_CLASSES.map((id) => ({ id })),
});

const catalog = (loops) => ({
  schema_version: 1,
  recovery_contract: {
    schema_version: 1,
    classes: RECOVERY_CLASSES,
    fixture: "runtime/loop/fixtures/self-heal/recovery-classes.json",
  },
  loops,
});

const catalogLoop = (overrides = {}) => ({
  id: "example",
  name: "Example",
  description: "Example loop",
  requirements: [],
  job_ids: ["example-job"],
  recovery_classes: ["deterministic"],
  hosts: {
    local: { availability: "guided", command: ["./install.sh"] },
    cloud: { availability: "setup_required", command: null },
  },
  ...overrides,
});

const registry = (overrides = {}) => ({
  loops: {
    "example-job": {
      entrypoint: "skills/example/run.sh",
      label: "ai.anicca.example-job",
      provider_route: "deterministic",
      domain: "system",
      effect_class: "none",
      cadence: { start_interval_seconds: 300 },
      state_root: "~/.local/state/life-manager/example",
      ...overrides,
    },
  },
});

test("loop contract accepts a catalog mapped to canonical runtime jobs", () => {
  const result = validateLoopContract({
    catalog: catalog([catalogLoop()]), registry: registry(), recoveryFixtures: recoveryFixtures(),
  });
  assert.equal(result.ok, true);
  assert.equal(result.catalog_loops, 1);
  assert.equal(result.mapped_jobs, 1);
  assert.deepEqual(result.errors, []);
});

test("loop contract rejects a catalog job absent from the registry", () => {
  const result = validateLoopContract({
    catalog: catalog([catalogLoop({ job_ids: ["missing-job"] })]),
    registry: registry(), recoveryFixtures: recoveryFixtures(),
  });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "runtime_job_missing"));
});

test("loop contract rejects missing runtime ownership fields", () => {
  const result = validateLoopContract({
    catalog: catalog([catalogLoop()]), registry: registry({ effect_class: "" }),
    recoveryFixtures: recoveryFixtures(),
  });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "runtime_job_field_missing"));
});

test("loop contract rejects worktree or absolute entrypoints", () => {
  const result = validateLoopContract({
    catalog: catalog([catalogLoop()]), registry: registry({ entrypoint: "/tmp/run.sh" }),
    recoveryFixtures: recoveryFixtures(),
  });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "entrypoint_not_repository_relative"));
});

test("loop contract validates an unmapped registry job too", () => {
  const value = registry();
  value.loops.unmapped = { ...value.loops["example-job"], effect_class: "" };
  const result = validateLoopContract({
    catalog: catalog([catalogLoop()]), registry: value, recoveryFixtures: recoveryFixtures(),
  });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.path === "unmapped.effect_class"));
});

test("loop contract rejects an unmapped absolute entrypoint", () => {
  const value = registry();
  value.loops.unmapped = { ...value.loops["example-job"], entrypoint: "/tmp/run.sh" };
  const result = validateLoopContract({
    catalog: catalog([catalogLoop()]), registry: value, recoveryFixtures: recoveryFixtures(),
  });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.path === "unmapped.entrypoint"));
});

test("loop contract rejects a recovery class declaration that disagrees with registry facts", () => {
  const result = validateLoopContract({
    catalog: catalog([catalogLoop({ recovery_classes: ["model"] })]),
    registry: registry(), recoveryFixtures: recoveryFixtures(),
  });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "recovery_class_mismatch"));
});

test("loop contract maps a Paid owner to read-only external ownership", () => {
  const paid = registry({
    priority: "critical_paid",
    effect_class: "money",
    entrypoint: "skills/earn/example/scripts/paid-owner",
  });
  const result = validateLoopContract({
    catalog: catalog([catalogLoop({ recovery_classes: ["read_only_external_owner"] })]),
    registry: paid, recoveryFixtures: recoveryFixtures(),
  });
  assert.equal(result.ok, true);
});

test("loop contract rejects missing class fixtures and cross-loop duplicate jobs", () => {
  const missingFixture = recoveryFixtures();
  missingFixture.classes = missingFixture.classes.filter((row) => row.id !== "deterministic");
  const fixtureResult = validateLoopContract({
    catalog: catalog([catalogLoop()]), registry: registry(), recoveryFixtures: missingFixture,
  });
  assert.ok(fixtureResult.errors.some((error) => error.code === "recovery_fixture_missing"));

  const duplicateResult = validateLoopContract({
    catalog: catalog([catalogLoop({ id: "one" }), catalogLoop({ id: "two" })]),
    registry: registry(), recoveryFixtures: recoveryFixtures(),
  });
  assert.ok(duplicateResult.errors.some((error) => error.code === "runtime_job_mapped_multiple_times"));
});
