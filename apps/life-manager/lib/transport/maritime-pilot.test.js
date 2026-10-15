"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createMaritimePilotTransport } = require("./maritime-pilot.js");

const ENV = Object.freeze({
  MARITIME_PILOT_ENABLED: "1",
  MARITIME_PILOT_DATA_APPROVED: "1",
  MARITIME_PILOT_TOOL_POLICY_VERIFIED: "1",
  MARITIME_API_KEY: "mk_test_only",
  MARITIME_PILOT_UID_ALLOWLIST: "uid-a,uid-b,uid-c",
  LM_UID_SECRET: "test-secret",
});

function fakeClient(overrides = {}) {
  const calls = { provisions: [], chats: [] };
  const client = {
    agents: {
      provision: async (params) => {
        calls.provisions.push(params);
        return { id: "agent-1" };
      },
      chat: async (...args) => {
        calls.chats.push(args);
        return { response: "A useful reply." };
      },
      ...overrides,
    },
  };
  return { client, calls };
}

test("disabled, unapproved, incomplete, or invalid config makes no Maritime call", async () => {
  const invalidEnvs = [
    { ...ENV, MARITIME_PILOT_ENABLED: "0" },
    { ...ENV, MARITIME_PILOT_DATA_APPROVED: "0" },
    { ...ENV, MARITIME_PILOT_TOOL_POLICY_VERIFIED: "0" },
    Object.fromEntries(Object.entries(ENV).filter(([key]) => key !== "MARITIME_PILOT_TOOL_POLICY_VERIFIED")),
    { ...ENV, MARITIME_API_KEY: "" },
    { ...ENV, LM_UID_SECRET: "" },
    { ...ENV, MARITIME_PILOT_UID_ALLOWLIST: "uid-a,uid-b,uid-c,uid-d" },
    { ...ENV, MARITIME_PILOT_UID_ALLOWLIST: "uid-a,uid-a" },
    { ...ENV, MARITIME_PILOT_UID_ALLOWLIST: "uid-a,bad uid" },
  ];

  for (const env of invalidEnvs) {
    let sdkLoads = 0;
    const transport = createMaritimePilotTransport({
      env,
      loadSdk: async () => { sdkLoads++; throw new Error("must stay lazy"); },
    });
    assert.equal(transport.isEnabledFor("uid-a"), false);
    assert.deepEqual(await transport.chatForUser("uid-a", "hello"), { ok: false, reason: "disabled" });
    assert.equal(sdkLoads, 0);
  }
});

test("allowlist excludes other users without loading the SDK", async () => {
  let sdkLoads = 0;
  const transport = createMaritimePilotTransport({
    env: ENV,
    loadSdk: async () => { sdkLoads++; throw new Error("must stay lazy"); },
  });

  assert.equal(transport.isEnabledFor("uid-outside"), false);
  assert.deepEqual(await transport.chatForUser("uid-outside", "hello"), { ok: false, reason: "disabled" });
  assert.equal(sdkLoads, 0);
});

test("provisions one stable pseudonymous agent and conversation per UID, then chats once", async () => {
  const { client, calls } = fakeClient();
  const transport = createMaritimePilotTransport({ env: ENV, client });

  const first = await transport.chatForUser("uid-a", "Plan my day");
  const second = await transport.chatForUser("uid-a", "What is next?");

  assert.deepEqual(first, { ok: true, response: "A useful reply." });
  assert.deepEqual(second, { ok: true, response: "A useful reply." });
  assert.equal(calls.provisions.length, 2, "each get-or-create call uses the same idempotency key");
  assert.equal(calls.provisions[0].externalId, calls.provisions[1].externalId);
  assert.match(calls.provisions[0].externalId, /^lm-pilot-[a-f0-9]{32}$/);
  assert.equal(calls.provisions[0].externalId.includes("uid-a"), false);
  assert.equal(calls.provisions[0].template, "openclaw");
  assert.equal(calls.chats.length, 2);
  assert.deepEqual(calls.chats[0], ["agent-1", "Plan my day", { conversationId: calls.chats[1][2].conversationId }]);
});

test("lazy SDK client is created with API key and SDK retries disabled", async () => {
  let receivedOptions;
  const { client } = fakeClient();
  const transport = createMaritimePilotTransport({
    env: ENV,
    loadSdk: async (options) => {
      receivedOptions = options;
      return client;
    },
  });

  assert.deepEqual(await transport.chatForUser("uid-a", "hello"), { ok: true, response: "A useful reply." });
  assert.deepEqual(receivedOptions, { apiKey: "mk_test_only", maxRetries: 0 });
});

test("provision or chat failures return a generic failure and never retry chat", async () => {
  let chats = 0;
  const provisionFailure = createMaritimePilotTransport({
    env: ENV,
    client: fakeClient({ provision: async () => { throw new Error("secret-bearing SDK failure"); } }).client,
  });
  assert.deepEqual(await provisionFailure.chatForUser("uid-a", "hello"), { ok: false, reason: "provider_error" });

  const chatFailure = createMaritimePilotTransport({
    env: ENV,
    client: fakeClient({ chat: async () => { chats++; return { response: null, error: "private provider detail" }; } }).client,
  });
  assert.deepEqual(await chatFailure.chatForUser("uid-a", "hello"), { ok: false, reason: "provider_error" });
  assert.equal(chats, 1);
});

test("missing or blank provider responses are not reported as success", async () => {
  for (const response of [undefined, null, "", "   "]) {
    const transport = createMaritimePilotTransport({
      env: ENV,
      client: fakeClient({ chat: async () => ({ response }) }).client,
    });
    assert.deepEqual(await transport.chatForUser("uid-a", "hello"), { ok: false, reason: "provider_error" });
  }
});
