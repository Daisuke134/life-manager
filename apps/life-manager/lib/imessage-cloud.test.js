"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

let api = {};
try { api = require("./imessage-cloud.js"); } catch {}

const uid = "lm_12345678-1234-4234-8234-123456789abc";
const senderId = "+819012345678";
const token = "F".repeat(32);

function textMessage(text, overrides = {}) {
  return {
    platform: "imessage",
    id: "imsg-message-1",
    sender: { id: senderId },
    content: { type: "text", text },
    ...overrides,
  };
}

function dmSpace(sent = []) {
  return {
    id: "any;-;+819012345678",
    type: "dm",
    async send(text) { sent.push(String(text)); return { ok: true }; },
  };
}

test("Spectrum stream stays disabled without both project credentials", async () => {
  assert.equal(typeof api.startIMessageCloud, "function", "the managed iMessage stream adapter must exist");
  let imports = 0;
  const client = await api.startIMessageCloud({
    env: { SPECTRUM_PROJECT_ID: "project-only" },
    loadSpectrumRuntimeImpl: async () => { imports += 1; return {}; },
  });
  assert.equal(client.enabled, false);
  assert.equal(imports, 0);
});

test("iMessage Web link requires the manual flag, a ready Cloud stream, and a fixed recipient number", () => {
  assert.equal(typeof api.isIMessageLinkReady, "function", "the Web channel gate must exist");
  const env = {
    LM_IMESSAGE_WEB_LINKS_ENABLED: "1",
    LM_IMESSAGE_CONTACT_NUMBER: "+15551234567",
    SPECTRUM_PROJECT_ID: "project-id",
    SPECTRUM_PROJECT_SECRET: "project-secret",
  };
  assert.equal(api.isIMessageLinkReady(env, null), false);
  assert.equal(api.isIMessageLinkReady(env, { enabled: false }), false);
  assert.equal(api.isIMessageLinkReady(env, { enabled: true }), true);
  assert.equal(api.isIMessageLinkReady({ ...env, LM_IMESSAGE_WEB_LINKS_ENABLED: "0" }, { enabled: true }), false);
  assert.equal(api.isIMessageLinkReady({ ...env, LM_IMESSAGE_CONTACT_NUMBER: "" }, { enabled: true }), false);
});

test("iMessage pairing code parser accepts only the exact LMI code", () => {
  assert.equal(typeof api.parseIMessagePairingCode, "function", "the one-time code parser must exist");
  assert.equal(api.parseIMessagePairingCode(`LMI_${token}`), token);
  assert.equal(api.parseIMessagePairingCode(`lmi_${token}`), null);
  assert.equal(api.parseIMessagePairingCode(`LMI_${token}!`), null);
  assert.equal(api.parseIMessagePairingCode("ordinary reply text"), null);
});

test("iMessage sender canonicalization accepts E.164 and Apple ID email only", () => {
  assert.equal(typeof api.normalizeIMessageSender, "function", "the sender normalizer must exist");
  assert.equal(api.normalizeIMessageSender(senderId), senderId);
  assert.equal(api.normalizeIMessageSender("Person@Example.com"), "person@example.com");
  assert.equal(api.normalizeIMessageSender("+81 90 1234 5678"), null);
  assert.equal(api.normalizeIMessageSender("123456"), null);
  assert.equal(api.normalizeIMessageSender("+819012345678\n"), null);
});

test("valid iMessage pairing binds the exact sender and acknowledges once", async () => {
  assert.equal(typeof api.handleIMessageStreamMessage, "function", "the Spectrum stream message handler must exist");
  const sent = [];
  const calls = [];
  const result = await api.handleIMessageStreamMessage(dmSpace(sent), textMessage(`LMI_${token}`), {
    consumeWebMessageLinkImpl: async (...args) => { calls.push(args); return { uid, channel: "imessage" }; },
    webMessageUserBySenderImpl: async () => { throw new Error("pairing must not resolve an unlinked sender"); },
  });
  assert.deepEqual(calls.map((call) => call.slice(0, 3)), [[token, "imessage", senderId]]);
  assert.deepEqual(result, { handled: true, action: "linked", uid });
  assert.equal(sent.length, 1);
  assert.match(sent[0], /iMessage.*接続/);
});

test("invalid, expired, or replayed iMessage code has no binding or reply side effect", async () => {
  assert.equal(typeof api.handleIMessageStreamMessage, "function", "the Spectrum stream message handler must exist");
  for (const text of [`LMI_${token}`, "LMI_short"]) {
    const sent = [];
    let lookups = 0;
    const result = await api.handleIMessageStreamMessage(dmSpace(sent), textMessage(text), {
      consumeWebMessageLinkImpl: async () => null,
      webMessageUserBySenderImpl: async () => { lookups += 1; return null; },
      resolveIMessageReplyImpl: async () => { throw new Error("unbound sender cannot reach Calendar reply logic"); },
    });
    assert.equal(result.handled, true);
    assert.equal(sent.length, 0);
    assert.equal(lookups, 0);
  }
});

test("duplicate stream delivery consumes a one-time pairing token only once", async () => {
  assert.equal(typeof api.handleIMessageStreamMessage, "function", "the Spectrum stream message handler must exist");
  const sent = [];
  let consumed = false;
  const message = textMessage(`LMI_${token}`);
  const deps = {
    consumeWebMessageLinkImpl: async () => {
      if (consumed) return null;
      consumed = true;
      return { uid, channel: "imessage" };
    },
  };
  await api.handleIMessageStreamMessage(dmSpace(sent), message, deps);
  await api.handleIMessageStreamMessage(dmSpace(sent), message, deps);
  assert.equal(sent.length, 1);
});

test("linked iMessage replies resolve only the linked Web tenant and use the same DM", async () => {
  assert.equal(typeof api.handleIMessageStreamMessage, "function", "the Spectrum stream message handler must exist");
  const sent = [];
  const lookups = [];
  const replies = [];
  const message = textMessage("オンライン開催です");
  const result = await api.handleIMessageStreamMessage(dmSpace(sent), message, {
    consumeWebMessageLinkImpl: async () => null,
    webMessageUserBySenderImpl: async (...args) => { lookups.push(args); return { uid, channel: "imessage" }; },
    resolveIMessageReplyImpl: async (...args) => { replies.push(args); return { filled: true, event: "相談", location: "オンライン" }; },
  });
  assert.equal(result.handled, true);
  assert.deepEqual(lookups.map((call) => call.slice(0, 2)), [["imessage", senderId]]);
  assert.deepEqual(replies.map((call) => call.slice(0, 3)), [[uid, senderId, "オンライン開催です"]]);
  assert.equal(replies[0][3].messageId, message.id);
  assert.equal(sent.length, 1);
  assert.match(sent[0], /オンライン/);
});

test("non-direct, non-text, or malformed-sender messages cannot reach a tenant", async () => {
  assert.equal(typeof api.handleIMessageStreamMessage, "function", "the Spectrum stream message handler must exist");
  const cases = [
    [ { id: "group-chat", type: "group", async send() {} }, textMessage(`LMI_${token}`) ],
    [ dmSpace(), textMessage(`LMI_${token}`, { content: { type: "image", url: "https://example.invalid" } }) ],
    [ dmSpace(), textMessage(`LMI_${token}`, { sender: { id: "not-a-sender" } }) ],
    [ dmSpace(), textMessage(`LMI_${token}`, { id: "" }) ],
  ];
  for (const [space, message] of cases) {
    let effects = 0;
    const result = await api.handleIMessageStreamMessage(space, message, {
      consumeWebMessageLinkImpl: async () => { effects += 1; return { uid, channel: "imessage" }; },
      webMessageUserBySenderImpl: async () => { effects += 1; return { uid, channel: "imessage" }; },
      resolveIMessageReplyImpl: async () => { effects += 1; return { filled: true }; },
    });
    assert.equal(result.handled, false);
    assert.equal(effects, 0);
  }
});

test("Spectrum app.messages stream dispatches sequentially and closes cleanly", async () => {
  assert.equal(typeof api.startIMessageCloud, "function", "the managed iMessage stream adapter must exist");
  const sent = [];
  const handled = [];
  let createdOptions = null;
  let stopped = false;
  const app = {
    messages: {
      async *[Symbol.asyncIterator]() {
        yield [dmSpace(sent), textMessage(`LMI_${token}`)];
        yield [dmSpace(sent), textMessage("hello", { id: "imsg-message-2" })];
      },
    },
    async stop() { stopped = true; },
  };
  const client = await api.startIMessageCloud({
    env: { SPECTRUM_PROJECT_ID: "project-id", SPECTRUM_PROJECT_SECRET: "project-secret" },
    loadSpectrumRuntimeImpl: async () => ({
      Spectrum: async (options) => { createdOptions = options; return app; },
      imessage: { config: () => ({ provider: "imessage" }) },
    }),
    handleMessageImpl: async (_space, message) => { handled.push(message.id); },
  });
  assert.equal(client.enabled, true);
  await client.ready;
  assert.deepEqual(handled, ["imsg-message-1", "imsg-message-2"]);
  assert.equal(createdOptions.projectId, "project-id");
  assert.equal(createdOptions.projectSecret, "project-secret");
  assert.equal(createdOptions.providers[0].provider, "imessage");
  await client.stop();
  assert.equal(stopped, true);
});

test("scheduled iMessage sends create a DM for the exact linked sender", async () => {
  assert.equal(typeof api.startIMessageCloud, "function", "the managed iMessage stream adapter must exist");
  const sent = [];
  const calls = [];
  const app = { messages: { async *[Symbol.asyncIterator]() {} }, async stop() {} };
  const provider = (client) => {
    assert.equal(client, app);
    return {
      async user(address) { calls.push(["user", address]); return { address }; },
      space: {
        async create(user) { calls.push(["create", user.address]); return { async send(text) { sent.push(text); return { id: "provider-send-1" }; } }; },
      },
    };
  };
  provider.config = () => ({ provider: "imessage" });
  const client = await api.startIMessageCloud({
    env: { SPECTRUM_PROJECT_ID: "project-id", SPECTRUM_PROJECT_SECRET: "project-secret" },
    loadSpectrumRuntimeImpl: async () => ({ Spectrum: async () => app, imessage: provider }),
  });
  const receipt = await client.sendToSender(senderId, "場所はどこですか？");
  assert.deepEqual(calls, [["user", senderId], ["create", senderId]]);
  assert.deepEqual(sent, ["場所はどこですか？"]);
  assert.deepEqual(receipt, { ok: true, receiptId: "provider-send-1" });
  await client.stop();
});

test("scheduled iMessage send without a provider message id is fenced as outcome-unknown", async () => {
  assert.equal(typeof api.startIMessageCloud, "function", "the managed iMessage stream adapter must exist");
  const app = { messages: { async *[Symbol.asyncIterator]() {} }, async stop() {} };
  const provider = () => ({
    async user(address) { return { address }; },
    space: { async create() { return { async send() { return {}; } }; } },
  });
  provider.config = () => ({ provider: "imessage" });
  const client = await api.startIMessageCloud({
    env: { SPECTRUM_PROJECT_ID: "project-id", SPECTRUM_PROJECT_SECRET: "project-secret" },
    loadSpectrumRuntimeImpl: async () => ({ Spectrum: async () => app, imessage: provider }),
  });
  assert.deepEqual(await client.sendToSender(senderId, "場所はどこですか？"), {
    ok: false, effectUnknown: true, reason: "receipt_missing",
  });
  await client.stop();
});
