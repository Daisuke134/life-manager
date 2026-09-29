"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createAgentCoreRuntimeClient,
  runtimeSessionId,
} = require("./agentcore-runtime-client.js");

const INVOCATION = Object.freeze({
  runtimeArn: "arn:aws:bedrock-agentcore:ap-northeast-1:000000000000:runtime/life-manager",
  tenantId: "tenant-a",
  jobId: "job-a",
  attempt: 1,
  releaseSha: "a".repeat(40),
  request: { tenant_id: "tenant-a", job_id: "job-a" },
});

test("derives one stable opaque runtime session id per immutable attempt", () => {
  const first = runtimeSessionId(INVOCATION);
  const replay = runtimeSessionId({ ...INVOCATION });
  const nextAttempt = runtimeSessionId({ ...INVOCATION, attempt: 2 });

  assert.equal(first, replay);
  assert.notEqual(first, nextAttempt);
  assert.match(first, /^lm-[a-f0-9]{64}$/);
  assert.doesNotMatch(first, /tenant-a|job-a/);
});

test("invokes the injected AWS boundary with a bounded timeout and returns its parsed envelope", async () => {
  const calls = [];
  const expected = { status: "completed", receipt_ref: "lm-resource://receipt/tenant-a/r-a" };
  const client = createAgentCoreRuntimeClient({
    timeoutMs: 4_000,
    async invoke(command) {
      calls.push(command);
      return { response: expected, provider_request_id: "request-a" };
    },
  });

  assert.deepEqual(await client.invoke(INVOCATION), {
    disposition: "completed",
    result: expected,
    provider_request_id: "request-a",
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].runtimeArn, INVOCATION.runtimeArn);
  assert.equal(calls[0].runtimeSessionId, runtimeSessionId(INVOCATION));
  assert.deepEqual(calls[0].payload, INVOCATION.request);
  assert.equal(calls[0].timeoutMs, 4_000);
  assert.equal(calls[0].signal instanceof AbortSignal, true);
});

test("maps known pre-acceptance transients to retry and ambiguous acceptance to reconcile", async () => {
  for (const [error, expected] of [
    [Object.assign(new Error("throttled"), { name: "ThrottlingException", accepted: false }), "retry"],
    [Object.assign(new Error("transport lost"), { name: "TimeoutError" }), "reconcile"],
    [Object.assign(new Error("accepted then disconnected"), { accepted: true }), "reconcile"],
  ]) {
    const client = createAgentCoreRuntimeClient({
      async invoke() { throw error; },
    });
    const result = await client.invoke(INVOCATION);
    assert.equal(result.disposition, expected);
    assert.equal(result.retryable, expected === "retry");
    assert.equal(Object.hasOwn(result, "payload"), false);
    assert.equal(Object.hasOwn(result, "signed_url"), false);
  }
});

