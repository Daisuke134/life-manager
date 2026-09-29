"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  evaluateBrowserPrincipal,
  createBrowserObservationBroker,
} = require("./browser-principal-policy.js");

test("agent-owned work is admitted without any human continuation surface", () => {
  const decision = evaluateBrowserPrincipal({
    uid: "tenant-1",
    principal_kind: "agent_owned",
    requires_login: true,
    goal: "publish through the agent-owned account",
  });
  assert.deepEqual(decision, { allowed: true, principal_kind: "agent_owned" });
  assert.doesNotMatch(JSON.stringify(decision), /ask|approve|takeover|resume|credential/i);
});

for (const input of [
  { principal_kind: "user_provided", requires_login: true, goal: "open account" },
  { principal_kind: "none", requires_login: false, goal: "complete CAPTCHA" },
  { principal_kind: "none", requires_login: false, goal: "finish OAuth consent" },
  { principal_kind: "none", requires_login: false, goal: "enter the 2FA code" },
  { principal_kind: "none", requires_login: false, goal: "complete 3DS payment" },
  { principal_kind: "none", requires_login: false, goal: "finish KYC interview and signature" },
]) {
  test(`human-principal work is terminally excluded: ${input.goal}`, () => {
    assert.deepEqual(evaluateBrowserPrincipal({ uid: "tenant-1", ...input }), {
      allowed: false,
      status: "not_applicable",
      reason: "requires_human_principal",
      external_effect: "none",
    });
  });
}

test("opaque observation refs are tenant-bound, read-only, and cross-tenant calls stop before providers", async () => {
  let providerCalls = 0;
  const broker = createBrowserObservationBroker({
    secret: "a".repeat(32),
    readActivity: async () => { providerCalls += 1; return [{ phase: "working" }]; },
    emergencyStop: async () => { providerCalls += 1; return true; },
  });
  const issued = broker.issue({ tenantId: "tenant-1", sessionId: "session-1", leaseGeneration: 4 });
  assert.match(issued.viewer_ref, /^lm-viewer:/);
  assert.doesNotMatch(JSON.stringify(issued), /session-1|wss:|cookie|credential/i);
  await assert.rejects(broker.activity({ tenantId: "tenant-2", viewerRef: issued.viewer_ref }), /tenant/i);
  assert.equal(providerCalls, 0);
  assert.deepEqual(await broker.activity({ tenantId: "tenant-1", viewerRef: issued.viewer_ref }), [{ phase: "working" }]);
  assert.deepEqual(await broker.stop({ tenantId: "tenant-1", viewerRef: issued.viewer_ref }), {
    status: "stopped",
    external_effect: "none",
  });
  assert.equal(providerCalls, 2);
});

test("optional break-glass stops the writer first and is never automated success or resumable", async () => {
  const calls = [];
  const broker = createBrowserObservationBroker({
    secret: "b".repeat(32),
    allowBreakGlass: true,
    readActivity: async () => [],
    emergencyStop: async (input) => { calls.push(["stop", input.leaseGeneration]); return true; },
    recordManualExternal: async (input) => { calls.push(["record", input.leaseGeneration]); },
  });
  const issued = broker.issue({ tenantId: "tenant-1", sessionId: "session-1", leaseGeneration: 7 });
  const result = await broker.breakGlass({ tenantId: "tenant-1", viewerRef: issued.viewer_ref });
  assert.deepEqual(calls, [["stop", 7], ["record", 7]]);
  assert.deepEqual(result, {
    status: "manual_external",
    automated_success: false,
    revenue_eligible: false,
  });
  assert.doesNotMatch(JSON.stringify(result), /resume|callback|approve/i);
});
