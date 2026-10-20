"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  reconcileUnknownEffect,
  MAX_UNKNOWN_RECONCILE_RESULTS,
} = require("./effect-reconciler.js");

function reconcilingJob(overrides = {}) {
  return {
    job_id: "job-001",
    tenant_id: "tenant-a",
    loop_id: "marketing.anicca.slideshow",
    effect_class: "publish",
    effect_key: "tiktok:anicca:asset-001",
    attempt: 1,
    max_attempts: 3,
    status: "reconciling",
    ...overrides,
  };
}

test("provider proof of presence completes the same attempt with an immutable receipt", async () => {
  const resolutions = [];
  const result = await reconcileUnknownEffect(reconcilingJob(), {
    adapter: {
      inspectEffect: async ({ effectKey }) => ({
        state: "present",
        receipt: {
          provider_id: "post-123",
          url: "https://example.com/post/123",
          checked_effect_key: effectKey,
        },
      }),
    },
    store: {
      resolveReconciliation: async (value) => {
        resolutions.push(value);
        return { status: "completed" };
      },
      recordUnknownReconciliation: async () => {
        throw new Error("present proof must not age the unknown counter");
      },
    },
  });

  assert.equal(result.status, "completed");
  assert.equal(resolutions.length, 1);
  assert.equal(resolutions[0].decision, "present");
  assert.equal(resolutions[0].attempt, 1);
  assert.equal(resolutions[0].receipt.provider_id, "post-123");
});

test("provider proof of absence is the only path that permits a retry", async () => {
  const resolutions = [];
  const result = await reconcileUnknownEffect(reconcilingJob(), {
    adapter: {
      inspectEffect: async () => ({
        state: "absent",
        receipt: { lookup: "provider_not_found" },
      }),
    },
    store: {
      resolveReconciliation: async (value) => {
        resolutions.push(value);
        return { status: "queued" };
      },
      recordUnknownReconciliation: async () => {
        throw new Error("absent proof must not age the unknown counter");
      },
    },
  });

  assert.equal(result.status, "queued");
  assert.equal(resolutions[0].decision, "absent");
});

test("unknown provider state stays reconciling and never calls a retry mutation", async () => {
  let mutations = 0;
  const aged = [];
  const result = await reconcileUnknownEffect(reconcilingJob({
    effect_class: "money",
  }), {
    adapter: {
      inspectEffect: async () => ({ state: "unknown" }),
    },
    store: {
      resolveReconciliation: async () => {
        mutations += 1;
      },
      recordUnknownReconciliation: async (value) => {
        aged.push(value);
        return { status: "reconciling", reconcile_attempts: 1 };
      },
    },
  });

  assert.deepEqual(result, {
    status: "reconciling",
    decision: "unknown",
  });
  assert.equal(mutations, 0);
  assert.equal(aged.length, 1);
  assert.deepEqual(aged[0], {
    tenantId: "tenant-a",
    jobId: "job-001",
    attempt: 1,
    maxUnknownResults: MAX_UNKNOWN_RECONCILE_RESULTS,
  });
});

test("unknown ages: 4 consecutive unknown results stay reconciling, the 5th dead-letters", async () => {
  assert.equal(MAX_UNKNOWN_RECONCILE_RESULTS, 5);
  let resolutions = 0;
  // Fake store mirroring migrations/20260730_runtime_reconcile_unknown_aging.sql:
  // each unknown result increments a durable counter; at the limit the job dead-letters.
  let reconcileAttempts = 0;
  let status = "reconciling";
  const store = {
    resolveReconciliation: async () => {
      resolutions += 1;
    },
    recordUnknownReconciliation: async ({ maxUnknownResults }) => {
      if (status !== "reconciling") throw new Error("runtime reconciliation lost job");
      reconcileAttempts += 1;
      if (reconcileAttempts >= maxUnknownResults) status = "dead_letter";
      return { status, reconcile_attempts: reconcileAttempts };
    },
  };
  const dependencies = {
    adapter: { inspectEffect: async () => ({ state: "unknown" }) },
    store,
  };

  for (let round = 1; round <= 4; round += 1) {
    const result = await reconcileUnknownEffect(reconcilingJob(), dependencies);
    assert.deepEqual(result, { status: "reconciling", decision: "unknown" });
  }
  assert.equal(status, "reconciling");

  const fifth = await reconcileUnknownEffect(reconcilingJob(), dependencies);
  assert.deepEqual(fifth, { status: "dead_letter", decision: "unknown_exhausted" });
  assert.equal(status, "dead_letter");
  assert.equal(reconcileAttempts, 5);
  assert.equal(resolutions, 0);
});

test("reconciler fails closed for a non-effect job or malformed adapter proof", async () => {
  const store = {
    resolveReconciliation: async () => ({}),
    recordUnknownReconciliation: async () => ({}),
  };
  await assert.rejects(
    reconcileUnknownEffect(reconcilingJob({ effect_class: "none" }), {
      adapter: { inspectEffect: async () => ({ state: "absent" }) },
      store,
    }),
    /effect class/i,
  );
  await assert.rejects(
    reconcileUnknownEffect(reconcilingJob(), {
      adapter: { inspectEffect: async () => ({ state: "maybe" }) },
      store,
    }),
    /adapter proof/i,
  );
});

test('known pending provider execution does not age unknown results or resolve an effect', async () => {
  const touched=[];
  const dependencies={adapter:{inspectEffect:async()=>({state:'pending'})},store:{
    resolveReconciliation:async()=>touched.push('resolve'),
    recordUnknownReconciliation:async()=>touched.push('age'),
  }};
  for(let i=0;i<25;i++)assert.deepEqual(await reconcileUnknownEffect(reconcilingJob(),dependencies),{status:'reconciling',decision:'pending'});
  assert.deepEqual(touched,[]);
});
