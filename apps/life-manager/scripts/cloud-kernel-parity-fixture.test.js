"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { runFixture } = require("./cloud-kernel-parity-fixture.js");

test("portable fixture returns deterministic same-kernel receipt and replay-zero proof", async () => {
  const first = await runFixture();
  const second = await runFixture();
  assert.deepEqual(second, first);
  assert.equal(first.schema_version, "life-manager.cloud-kernel-parity.v1");
  assert.match(first.business_kernel_sha, /^[a-f0-9]{64}$/);
  assert.match(first.receipt_hash, /^[a-f0-9]{64}$/);
  assert.match(first.evidence_hash, /^[a-f0-9]{64}$/);
  assert.equal(first.official_readback, true);
  assert.equal(first.replay_zero, true);
  assert.equal(first.effect, "none");
  assert.equal(first.human_input_count, 0);
  assert.doesNotMatch(JSON.stringify(first), /credential|password|token|cookie/i);
});
