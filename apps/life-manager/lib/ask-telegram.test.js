"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { askTick } = require("./ask.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const EVENT = {
  id: "e2e_telegram_ambiguous_send_20261010",
  summary: "LM E2E 20261010 self-only ask",
  start: { dateTime: "2030-01-01T12:00:00+09:00" },
  location: "",
};

test("ambiguous Telegram ask send keeps its claim and a second tick does not resend", async () => {
  const originalFetch = global.fetch;
  const providerTexts = [];
  const claimedRows = [];
  let claimExists = false;
  let claimDeletes = 0;
  let emailSends = 0;

  global.fetch = async (url, init = {}) => {
    const target = String(url);
    const method = String(init.method || "GET");
    if (target.includes("api.telegram.org/") && target.endsWith("/sendMessage")) {
      providerTexts.push(JSON.parse(init.body).text);
      throw new Error("response lost after request may have reached Telegram");
    }
    if (target.includes("api.resend.com")) {
      emailSends++;
      return { ok: true, status: 200, async json() { return { id: "unexpected-email" }; } };
    }
    if (target.includes("/lm_ask_log") && method === "POST") {
      const row = JSON.parse(init.body);
      claimedRows.push(row);
      if (claimExists) return { ok: false, status: 409, async json() { return []; } };
      claimExists = true;
      return { ok: true, status: 201, async json() { return []; } };
    }
    if (target.includes("/lm_ask_log") && method === "DELETE") {
      claimDeletes++;
      claimExists = false;
      return { ok: true, status: 204, async json() { return []; } };
    }
    throw new Error(`unexpected request ${method} ${new URL(target).origin}`);
  };

  const askedSet = async () => {
    const set = new Set(claimExists ? [EVENT.id] : []);
    set.seriesAnswers = {};
    set.pendingIMessage = false;
    return set;
  };
  const opts = {
    composioKey: "fixture-composio",
    supaUrl: "https://fixture.supabase.co",
    supaKey: "fixture-service-role",
    telegramToken: "fixture-bot-token",
    telegramChatId: "123456",
    userEmail: "owner@example.invalid",
    resendKey: "fixture-resend",
    nowMs: Date.parse("2030-01-01T00:00:00Z"),
    listEvents: async () => [EVENT],
    askedSet,
    patchEvent: async () => { throw new Error("an unresolved ask must not write Calendar"); },
    recordResolution: async () => {},
    recall: async () => null,
    resolve: async () => ({ kind: "ask" }),
    geminiRaw: async () => ({}),
    mail: { ready: () => false, searchInbox: async () => { throw new Error("must not read Gmail"); } },
  };

  try {
    const first = await askTick(UID, opts);
    const replay = await askTick(UID, opts);

    assert.deepEqual(first, { autofilled: 0, asked: 0, resolved: 0 });
    assert.deepEqual(replay, { autofilled: 0, asked: 0, resolved: 0 });
    assert.equal(providerTexts.length, 1);
    assert.match(providerTexts[0], /LM E2E 20261010 self-only ask/);
    assert.equal(claimedRows.length, 1);
    assert.equal(claimedRows[0].uid, UID);
    assert.equal(claimedRows[0].event_id, EVENT.id);
    assert.equal(claimedRows[0].question_context.replyChannel, "telegram");
    assert.equal(claimDeletes, 0);
    assert.equal(claimExists, true);
    assert.equal(emailSends, 0);
  } finally {
    global.fetch = originalFetch;
  }
});
