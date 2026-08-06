"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { runControlledErrorInjection } = require("./error-injection.js");


test("three observed failures become three closed incident classes", async () => {
  const persisted = [];
  const fail = async () => { throw new Error("raw private provider failure"); };
  const result = await runControlledErrorInjection({
    provenanceKey: "fixture-error-provenance-key",
    timeoutProbe: fail,
    sideEffectProbe: fail,
    runtimeProbe: fail,
    persist: async (intake) => {
      persisted.push(intake);
      return { id: String(persisted.length), duplicate: false };
    },
  });
  assert.deepEqual(result.map((item) => item.incidentClass), [
    "provider-timeout",
    "side-effect-failed",
    "runtime-regression",
  ]);
  assert.deepEqual(persisted.map((item) => item.labels[1]), result.map((item) => item.incidentClass));
  assert.equal(JSON.stringify(persisted).includes("raw private provider failure"), false);
});


test("a probe that does not actually fail is rejected without creating intake", async () => {
  let writes = 0;
  await assert.rejects(
    runControlledErrorInjection({
      provenanceKey: "fixture-error-provenance-key",
      timeoutProbe: async () => {},
      sideEffectProbe: async () => { throw new Error("expected"); },
      runtimeProbe: async () => { throw new Error("expected"); },
      persist: async () => { writes += 1; },
    }),
    /controlled_failure_missing/,
  );
  assert.equal(writes, 0);
});


test("a delivery probe returning sent:false is recorded as a side-effect failure", async () => {
  const persisted = [];
  const fail = async () => { throw new Error("controlled failure"); };
  const result = await runControlledErrorInjection({
    provenanceKey: "fixture-error-provenance-key",
    timeoutProbe: fail,
    sideEffectProbe: async () => ({ sent: false }),
    runtimeProbe: fail,
    persist: async (intake) => {
      persisted.push(intake);
      return { id: String(persisted.length), duplicate: false };
    },
  });
  assert.equal(result[1].incidentClass, "side-effect-failed");
  assert.equal(persisted[1].summary, "Side effect failed in delivery (controlled-delivery-failure).");
});
