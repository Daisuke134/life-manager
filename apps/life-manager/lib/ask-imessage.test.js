"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { askTick } = require("./ask.js");

test("unresolved Web ask sends through the linked iMessage sender and no email fallback", async () => {
  const originalFetch = global.fetch;
  const claims = [];
  const sends = [];
  let rawCalls = 0;
  global.fetch = async (url, init = {}) => {
    claims.push({ url: String(url), init });
    return { ok: true, status: 201, async json() { return []; } };
  };
  try {
    const result = await askTick("lm_11111111-1111-4111-8111-111111111111", {
      composioKey: "fixture-composio",
      userEmail: null,
      resendKey: "fixture-resend",
      supaUrl: "https://fixture.supabase.co",
      supaKey: "fixture-service-role",
      mapsKey: "fixture-maps",
      geminiKey: "fixture-gemini",
      imessageSenderId: "+819012345678",
      imessageSend: async (sender, text) => {
        sends.push({ sender, text });
        return { ok: true, receiptId: "provider-send-fixture" };
      },
      nowMs: Date.parse("2030-01-01T00:00:00Z"),
      listEvents: async () => [{
        id: "event-lunch",
        summary: "Lunch with Mai",
        description: "",
        start: { dateTime: "2030-01-01T12:00:00+09:00" },
        location: "",
      }],
      askedSet: async () => new Set(),
      patchEvent: async () => { throw new Error("unresolved asks must not patch Calendar"); },
      recordResolution: async () => {},
      recall: async () => null,
      resolve: async () => ({ kind: "ask" }),
      geminiRaw: async () => {
        rawCalls += 1;
        if (rawCalls === 1) return { candidates: [{ content: { parts: [{ text: "No reliable venue found." }] } }] };
        return { candidates: [{ content: { parts: [{ functionCall: { name: "submit_candidate", args: { found: false, candidate: "", source: "web_search" } } }] } }] };
      },
      mail: { ready: () => false, searchInbox: async () => { throw new Error("Web-only question must not read Gmail"); } },
    });
    assert.deepEqual(result, { autofilled: 0, asked: 1, resolved: 0 });
    assert.equal(sends.length, 1);
    assert.equal(sends[0].sender, "+819012345678");
    assert.match(sends[0].text, /オンライン/);
    assert.match(sends[0].text, /対面/);
    assert.equal(claims.length, 1);
    assert.match(claims[0].url, /lm_ask_log/);
    const claimedAsk = JSON.parse(claims[0].init.body);
    assert.equal(claimedAsk.uid, "lm_11111111-1111-4111-8111-111111111111");
    assert.equal(claimedAsk.question_context.replyChannel, "imessage");
  } finally {
    global.fetch = originalFetch;
  }
});

test("iMessage ask loop waits for the current pending question before asking another event", async () => {
  const originalFetch = global.fetch;
  const writes = [];
  const sends = [];
  let rawCalls = 0;
  global.fetch = async (url, init = {}) => {
    writes.push({ url: String(url), init });
    return { ok: true, status: 201, async json() { return []; } };
  };
  try {
    const pending = new Set();
    pending.pendingIMessage = true;
    const result = await askTick("lm_11111111-1111-4111-8111-111111111111", {
      composioKey: "fixture-composio", supaUrl: "https://fixture.supabase.co",
      supaKey: "fixture-service-role", geminiKey: "fixture-gemini", mapsKey: "fixture-maps",
      imessageSenderId: "+819012345678",
      imessageSend: async (_sender, text) => { sends.push(text); return { ok: true }; },
      nowMs: Date.parse("2030-01-01T00:00:00Z"),
      listEvents: async () => [{ id: "event-next", summary: "Lunch with Mai", start: { dateTime: "2030-01-01T12:00:00+09:00" }, location: "" }],
      askedSet: async () => pending,
      patchEvent: async () => { throw new Error("unresolved ask must not patch Calendar"); },
      recordResolution: async () => {},
      recall: async () => null,
      resolve: async () => ({ kind: "ask" }),
      geminiRaw: async () => {
        rawCalls += 1;
        if (rawCalls === 1) return { candidates: [{ content: { parts: [{ text: "No reliable venue found." }] } }] };
        return { candidates: [{ content: { parts: [{ functionCall: { name: "submit_candidate", args: { found: false, candidate: "", source: "web_search" } } }] } }] };
      },
      mail: { ready: () => false, searchInbox: async () => { throw new Error("Web-only iMessage asks must not read email"); } },
    });
    assert.deepEqual(result, { autofilled: 0, asked: 0, resolved: 0 });
    assert.deepEqual(writes, []);
    assert.deepEqual(sends, []);
  } finally {
    global.fetch = originalFetch;
  }
});

test("ambiguous iMessage send keeps the atomic ask claim and does not replay the message", async () => {
  const originalFetch = global.fetch;
  const requests = [];
  let rawCalls = 0;
  global.fetch = async (url, init = {}) => {
    requests.push({ url: String(url), method: String(init.method || "GET") });
    return { ok: true, status: init.method === "POST" ? 201 : 204, async json() { return []; } };
  };
  try {
    const result = await askTick("lm_11111111-1111-4111-8111-111111111111", {
      composioKey: "fixture-composio", supaUrl: "https://fixture.supabase.co",
      supaKey: "fixture-service-role", geminiKey: "fixture-gemini", mapsKey: "fixture-maps",
      imessageSenderId: "+819012345678",
      imessageSend: async () => ({ ok: false, effectUnknown: true, reason: "timeout_after_send" }),
      nowMs: Date.parse("2030-01-01T00:00:00Z"),
      listEvents: async () => [{
        id: "event-lunch", summary: "Lunch with Mai", start: { dateTime: "2030-01-01T12:00:00+09:00" }, location: "",
      }],
      askedSet: async () => new Set(),
      patchEvent: async () => { throw new Error("unresolved asks must not patch Calendar"); },
      recordResolution: async () => {}, recall: async () => null, resolve: async () => ({ kind: "ask" }),
      geminiRaw: async () => {
        rawCalls += 1;
        if (rawCalls === 1) return { candidates: [{ content: { parts: [{ text: "No reliable venue found." }] } }] };
        return { candidates: [{ content: { parts: [{ functionCall: { name: "submit_candidate", args: { found: false, candidate: "", source: "web_search" } } }] } }] };
      },
      mail: { ready: () => false, searchInbox: async () => { throw new Error("iMessage send uncertainty must not fall back to email"); } },
    });
    assert.deepEqual(result, { autofilled: 0, asked: 0, resolved: 0 });
    assert.deepEqual(requests.map((request) => request.method), ["POST"]);
    assert.match(requests[0].url, /lm_ask_log/);
  } finally {
    global.fetch = originalFetch;
  }
});
