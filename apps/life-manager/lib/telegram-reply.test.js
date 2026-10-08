"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { resolveTelegramReply, userByChatId } = require("./telegram-reply.js");

test("Telegram reply lookup resolves a linked Web UID without merging or reading Gmail", async () => {
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const urls = [];
  const user = await userByChatId("123456789", {
    supaUrl: "https://fixture.supabase.co",
    supaKey: "fixture-service-role",
    fetchImpl: async (input) => {
      const url = new URL(String(input));
      urls.push(url);
      if (url.pathname === "/rest/v1/lm_users" && url.searchParams.get("telegram_chat_id") === "eq.123456789") {
        return { ok: true, async json() { return []; } };
      }
      if (url.pathname === "/rest/v1/lm_message_channels") {
        return { ok: true, async json() { return [{
          uid, channel: "telegram", sender_id: "123456789", owner_kind: "web_link",
        }]; } };
      }
      if (url.pathname === "/rest/v1/lm_users" && url.searchParams.has("uid")) {
        return { ok: true, async json() { return [{
          uid,
          telegram_chat_id: null,
          calendar_provider: "composio_gcal",
          calendar_connected_account_id: "cal_abc123",
          gmail_account_id: null,
          paid: true,
        }]; } };
      }
      throw new Error(`unexpected lookup ${url.pathname}`);
    },
  });
  assert.equal(user.uid, uid);
  assert.equal(user.telegram_chat_id, null);
  assert.equal(user.calendar_connected_account_id, "cal_abc123");
  assert.equal(user.gmail_account_id, null);
  assert.equal(urls.length, 3);
});

test("a repeated Web-linked Telegram answer patches one Calendar event only once", async () => {
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const webUser = {
    uid,
    telegram_chat_id: null,
    web_message_telegram_chat_id: "123456789",
    calendar_provider: "composio_gcal",
    calendar_connected_account_id: "cal_abc123",
    gmail_account_id: null,
    paid: true,
    plan_status: "active",
  };
  const event = {
    id: "event-1",
    summary: "Product review",
    start: { dateTime: "2030-01-01T10:00:00+09:00" },
    location: "",
  };
  const patches = [];
  let matches = 0;
  const deps = {
    composioKey: "fixture-composio",
    geminiKey: "fixture-gemini",
    lookupUser: async (chatId) => {
      assert.equal(chatId, "123456789");
      return webUser;
    },
    calendar: {
      async listEventsRaw(requestUid) {
        assert.equal(requestUid, uid);
        return [{ ...event }];
      },
      async patchEvent(requestUid, patch) {
        assert.equal(requestUid, uid);
        patches.push(patch);
        event.location = patch.location;
        return { successful: true };
      },
    },
    match: async (_text, pending) => {
      matches += 1;
      assert.deepEqual(pending.map((row) => row.id), ["event-1"]);
      return { eventId: "event-1", location: "Online" };
    },
    remember: async () => true,
    markAnswered: async () => {},
    nowMs: Date.parse("2030-01-01T08:00:00Z"),
  };
  const first = await resolveTelegramReply("123456789", "This is online", deps);
  const replay = await resolveTelegramReply("123456789", "This is online", deps);
  assert.equal(first.filled, true);
  assert.equal(replay.filled, false);
  assert.equal(patches.length, 1);
  assert.equal(matches, 1);
});

test("expired Web billing entitlement blocks a Telegram-linked reply before Calendar access", async () => {
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  let calendarReads = 0;
  let matches = 0;
  const result = await resolveTelegramReply("123456789", "Shibuya", {
    composioKey: "fixture-composio",
    geminiKey: "fixture-gemini",
    nowMs: Date.parse("2030-01-01T09:00:00Z"),
    lookupUser: async () => ({
      uid,
      telegram_chat_id: null,
      web_message_telegram_chat_id: "123456789",
      calendar_provider: "composio_gcal",
      calendar_connected_account_id: "cal_abc123",
      paid: false,
      plan_status: "incomplete",
      web_billing_cancel_at_period_end: true,
    }),
    calendar: { async listEventsRaw() { calendarReads += 1; return []; } },
    match: async () => { matches += 1; return null; },
  });
  assert.deepEqual(result, { filled: false, event: "", location: "" });
  assert.equal(calendarReads, 0);
  assert.equal(matches, 0);
});
