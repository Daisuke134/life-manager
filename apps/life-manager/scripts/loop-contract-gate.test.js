"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { validateLoopContract } = require("./loop-contract-gate.js");

const catalogLoop = (overrides = {}) => ({
  id: "example",
  name: "Example",
  description: "Example loop",
  requirements: [],
  job_ids: ["example-job"],
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
  const result = validateLoopContract({ catalog: { schema_version: 1, loops: [catalogLoop()] }, registry: registry() });
  assert.equal(result.ok, true);
  assert.equal(result.catalog_loops, 1);
  assert.equal(result.mapped_jobs, 1);
  assert.deepEqual(result.errors, []);
});

test("loop contract rejects a catalog job absent from the registry", () => {
  const result = validateLoopContract({ catalog: { loops: [catalogLoop({ job_ids: ["missing-job"] })] }, registry: registry() });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "runtime_job_missing"));
});

test("loop contract rejects missing runtime ownership fields", () => {
  const result = validateLoopContract({ catalog: { loops: [catalogLoop()] }, registry: registry({ effect_class: "" }) });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "runtime_job_field_missing"));
});

test("loop contract rejects worktree or absolute entrypoints", () => {
  const result = validateLoopContract({ catalog: { loops: [catalogLoop()] }, registry: registry({ entrypoint: "/tmp/run.sh" }) });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "entrypoint_not_repository_relative"));
});
