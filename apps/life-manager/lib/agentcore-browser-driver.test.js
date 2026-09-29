"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createMemoryBrowserSessionLeaseStore,
  createBrowserSessionLeaseCoordinator,
} = require("./browser-session-lease.js");
const {
  createAgentCoreBrowserDriver,
  createAwsAgentCoreBrowserClient,
} = require("./agentcore-browser-driver.js");

function fixture(options = {}) {
  const calls = [];
  const leaseStore = createMemoryBrowserSessionLeaseStore();
  const provider = {
    async startSession(input) {
      calls.push(["start", input]);
      return {
        browserIdentifier: "browser-tokyo",
        sessionId: options.sessionId || "session-a",
        streams: {
          automationStream: {
            streamEndpoint: "wss://provider.invalid/private-cdp",
            streamStatus: "ENABLED",
          },
        },
      };
    },
    async saveProfile(input) {
      calls.push(["save", input]);
      return { ...input, lastUpdatedAt: new Date("2026-09-29T12:00:00.000Z") };
    },
    async stopSession(input) {
      calls.push(["stop", input]);
      if (options.stopError) throw new Error("provider stop unavailable");
      return { ...input, lastUpdatedAt: new Date("2026-09-29T12:00:01.000Z") };
    },
  };
  const lease = createBrowserSessionLeaseCoordinator(leaseStore, {
    now: () => 1_800_000_000_000,
    ttlMs: 600_000,
    releaseProviderSession: async (sessionId) => {
      await provider.stopSession({ browserIdentifier: "browser-tokyo", sessionId });
      return true;
    },
    token: (() => {
      let index = 0;
      return () => `00000000-0000-4000-8000-${String(++index).padStart(12, "0")}`;
    })(),
  });
  const reconciliations = [];
  const driver = createAgentCoreBrowserDriver({
    browserIdentifier: "browser-tokyo",
    provider: "agentcore",
    profileStore: {
      async read(tenantId, providerName) {
        calls.push(["profile-read", tenantId, providerName]);
        return options.profile || {
          tenant_id: tenantId,
          provider: providerName,
          profile_id: "profile-agent-a",
          principal_type: "agent_owned",
        };
      },
    },
    lease,
    providerClient: provider,
    reconciliationStore: {
      async record(value) { reconciliations.push(structuredClone(value)); },
    },
    clientToken: ({ tenantId, jobId, phase }) => `${phase}:${tenantId}:${jobId}`,
  });
  return { calls, driver, leaseStore, reconciliations };
}

test("uses an agent-owned tenant profile, saves only after verification, and releases the exact session", async () => {
  const f = fixture();
  const result = await f.driver.run({ tenantId: "tenant-a", jobId: "job-a" }, async (browser) => {
    f.calls.push(["action", browser]);
    assert.equal(browser.automationEndpoint, "wss://provider.invalid/private-cdp");
    return { verified: true, evidence_sha256: "a".repeat(64), result: { title: "Example" } };
  });

  assert.deepEqual(f.calls.map(([name]) => name), [
    "profile-read", "start", "action", "save", "stop",
  ]);
  assert.deepEqual(f.calls[0].slice(1), ["tenant-a", "agentcore"]);
  assert.equal(f.calls[1][1].profileConfiguration.profileIdentifier, "profile-agent-a");
  assert.deepEqual(f.calls[3][1], {
    profileIdentifier: "profile-agent-a",
    browserIdentifier: "browser-tokyo",
    sessionId: "session-a",
    clientToken: "save:tenant-a:job-a",
  });
  assert.deepEqual(f.calls[4][1], {
    browserIdentifier: "browser-tokyo",
    sessionId: "session-a",
    clientToken: "stop:tenant-a:job-a",
  });
  assert.deepEqual(result, {
    status: "completed",
    tenant_id: "tenant-a",
    job_id: "job-a",
    profile_ref: "lm-resource://browser-profile/tenant-a/profile-agent-a",
    session_ref: "lm-resource://browser-session/tenant-a/session-a",
    evidence_sha256: "a".repeat(64),
    result: { title: "Example" },
  });
  assert.doesNotMatch(JSON.stringify(result), /wss:|cookie|credential/i);
  assert.deepEqual(f.leaseStore.snapshot(), []);
});

test("a second owner cannot start while the first tenant session is active", async () => {
  const f = fixture();
  let releaseAction;
  const gate = new Promise((resolve) => { releaseAction = resolve; });
  const first = f.driver.run({ tenantId: "tenant-a", jobId: "job-a" }, async () => {
    await gate;
    return { verified: true, evidence_sha256: "b".repeat(64), result: {} };
  });
  while (!f.calls.some(([name]) => name === "start")) await new Promise(setImmediate);

  await assert.rejects(
    f.driver.run({ tenantId: "tenant-a", jobId: "job-b" }, async () => ({
      verified: true, evidence_sha256: "c".repeat(64), result: {},
    })),
    /lease unavailable/i,
  );
  assert.equal(f.calls.filter(([name]) => name === "start").length, 1);
  releaseAction();
  await first;
});

test("rejects foreign or human profiles before provider calls", async () => {
  for (const profile of [
    { tenant_id: "tenant-b", provider: "agentcore", profile_id: "profile-b", principal_type: "agent_owned" },
    { tenant_id: "tenant-a", provider: "agentcore", profile_id: "profile-a", principal_type: "human" },
  ]) {
    const f = fixture({ profile });
    await assert.rejects(
      f.driver.run({ tenantId: "tenant-a", jobId: "job-a" }, async () => ({})),
      /tenant|agent_owned|principal/i,
    );
    assert.equal(f.calls.some(([name]) => name === "start"), false);
  }
});

test("does not save an unverified action and retains reconciliation plus ownership when stop fails", async () => {
  const f = fixture({ stopError: true });
  await assert.rejects(
    f.driver.run({ tenantId: "tenant-a", jobId: "job-a" }, async () => ({
      verified: false,
      evidence_sha256: "d".repeat(64),
      result: { partial: true },
    })),
    /stop|release/i,
  );

  assert.equal(f.calls.some(([name]) => name === "save"), false);
  assert.equal(f.reconciliations.length, 1);
  assert.deepEqual(f.reconciliations[0], {
    tenant_id: "tenant-a",
    job_id: "job-a",
    provider: "agentcore",
    browser_identifier: "browser-tokyo",
    session_id: "session-a",
    profile_id: "profile-agent-a",
    reason: "provider_stop_failed",
  });
  assert.equal(f.leaseStore.snapshot().length, 1);
});

test("AWS client maps lifecycle calls to the three official AgentCore Browser commands", async () => {
  const calls = [];
  const client = createAwsAgentCoreBrowserClient({
    client: {
      async send(command) {
        calls.push({ name: command.constructor.name, input: command.input });
        return { ...command.input, sessionId: command.input.sessionId || "session-sdk" };
      },
    },
  });
  const start = {
    browserIdentifier: "browser-tokyo",
    name: "lm-tenant-job",
    sessionTimeoutSeconds: 900,
    viewPort: { width: 1440, height: 900 },
    profileConfiguration: { profileIdentifier: "profile-a" },
    clientToken: "start-token",
  };
  const save = {
    profileIdentifier: "profile-a",
    browserIdentifier: "browser-tokyo",
    sessionId: "session-sdk",
    clientToken: "save-token",
  };
  const stop = {
    browserIdentifier: "browser-tokyo",
    sessionId: "session-sdk",
    clientToken: "stop-token",
  };

  await client.startSession(start);
  await client.saveProfile(save);
  await client.stopSession(stop);

  assert.deepEqual(calls, [
    { name: "StartBrowserSessionCommand", input: start },
    { name: "SaveBrowserSessionProfileCommand", input: save },
    { name: "StopBrowserSessionCommand", input: stop },
  ]);
});
