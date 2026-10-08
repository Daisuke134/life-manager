"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

let parseWebTelegramStart = null;
let createWebMessageLink = null;
let handleWebMessageLinkRequest = null;
let consumeWebMessageLink = null;
let webTelegramUserBySender = null;
let webTelegramChannelsForUids = null;
try { ({ parseWebTelegramStart, createWebMessageLink, handleWebMessageLinkRequest, consumeWebMessageLink, webTelegramUserBySender, webTelegramChannelsForUids } = require("./message-links.js")); } catch {}

test("Web Telegram start parser accepts only the exact short-lived link payload", () => {
  assert.equal(typeof parseWebTelegramStart, "function", "the Web-to-Telegram parser must exist");
  const token = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
  assert.deepEqual(parseWebTelegramStart(`/start lmw_${token}`), { matched: true, token });
  assert.deepEqual(parseWebTelegramStart(`/start@LifeManagerBot lmw_${token}`), { matched: true, token });
  assert.deepEqual(parseWebTelegramStart("/start ordinary-payload"), { matched: false, token: null });
  assert.deepEqual(parseWebTelegramStart(`/start lmw_${token}!`), { matched: true, token: null });
  assert.deepEqual(parseWebTelegramStart("/start-lmw_token"), { matched: false, token: null });
});

test("Telegram link stores only a token hash and expires after ten minutes", async () => {
  assert.equal(typeof createWebMessageLink, "function", "the authenticated Web link creator must exist");
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const token = "A".repeat(32);
  const requests = [];
  const result = await createWebMessageLink(uid, "telegram", {
    env: {
      SUPABASE_URL: "https://fixture.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role",
      LM_TELEGRAM_BOT_USERNAME: "LifeManagerBot",
    },
    nowMs: 1_800_000_000_000,
    randomBytesImpl: (size) => {
      assert.equal(size, 24);
      return Buffer.alloc(24);
    },
    fetchImpl: async (url, init) => {
      requests.push({ url: String(url), init });
      return { ok: true, status: 200, async json() { return true; } };
    },
  });
  assert.deepEqual(result, {
    url: `https://t.me/LifeManagerBot?start=lmw_${token}`,
    expiresAt: new Date(1_800_000_600_000).toISOString(),
  });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "https://fixture.supabase.co/rest/v1/rpc/create_lm_web_message_link");
  const body = JSON.parse(requests[0].init.body);
  assert.equal(body.p_uid, uid);
  assert.equal(body.p_channel, "telegram");
  assert.equal(body.p_token_hash, require("node:crypto").createHash("sha256").update(token).digest("hex"));
  assert.equal(body.p_expires_at, result.expiresAt);
  assert.equal(JSON.stringify(body).includes(token), false);
});

function requestResponse() {
  return {
    status: 0,
    headers: {},
    body: "",
    writeHead(status, headers = {}) { this.status = status; this.headers = headers; },
    end(body = "") { this.body = String(body); },
  };
}

function linkRequest({ origin = "https://aniccaai.com", csrf = "csrf-fixture", body = { channel: "telegram" } } = {}) {
  return {
    method: "POST",
    url: "/api/lm-web/message-link",
    headers: {
      origin,
      "content-type": "application/json",
      "x-lm-web-csrf": csrf,
    },
    body,
  };
}

test("authenticated Web user can request an optional Telegram link without supplying a phone number", async () => {
  assert.equal(typeof handleWebMessageLinkRequest, "function", "the Web message-link endpoint must exist");
  const response = requestResponse();
  let writes = 0;
  await handleWebMessageLinkRequest(linkRequest(), response, {
    publicOrigin: "https://aniccaai.com/lm",
    env: {
      SUPABASE_URL: "https://fixture.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role",
      LM_TELEGRAM_BOT_USERNAME: "LifeManagerBot",
    },
    resolveWebUserImpl: async () => ({ uid: "lm_12345678-1234-4234-8234-123456789abc", csrf: "csrf-fixture" }),
    readJsonImpl: async (req) => req.body,
    nowMs: 1_800_000_000_000,
    randomBytesImpl: (size) => Buffer.alloc(size),
    fetchImpl: async (_url, init) => {
      writes += 1;
      assert.equal(init.method, "POST");
      return { ok: true, status: 200, async json() { return true; } };
    },
  });
  assert.equal(response.status, 200);
  assert.match(response.headers["content-type"], /application\/json/);
  const body = JSON.parse(response.body);
  assert.equal(body.url, `https://t.me/LifeManagerBot?start=lmw_${"A".repeat(32)}`);
  assert.equal(body.expiresAt, new Date(1_800_000_600_000).toISOString());
  assert.equal("uid" in body, false);
  assert.equal(writes, 1);
});

test("cross-origin and bad-CSRF link requests cannot mint a channel token", async () => {
  assert.equal(typeof handleWebMessageLinkRequest, "function", "the Web message-link endpoint must exist");
  for (const request of [
    linkRequest({ origin: "https://attacker.example" }),
    linkRequest({ csrf: "wrong-token" }),
  ]) {
    const response = requestResponse();
    let writes = 0;
    await handleWebMessageLinkRequest(request, response, {
      publicOrigin: "https://aniccaai.com",
      env: { SUPABASE_URL: "https://fixture.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role", LM_TELEGRAM_BOT_USERNAME: "LifeManagerBot" },
      resolveWebUserImpl: async () => ({ uid: "lm_12345678-1234-4234-8234-123456789abc", csrf: "csrf-fixture" }),
      readJsonImpl: async (req) => req.body,
      fetchImpl: async () => { writes += 1; return { ok: true, async json() { return true; } }; },
    });
    assert.equal(response.status, 403);
    assert.equal(writes, 0);
  }
});

test("the browser cannot choose the linked tenant or request an unimplemented channel", async () => {
  assert.equal(typeof handleWebMessageLinkRequest, "function", "the Web message-link endpoint must exist");
  for (const body of [
    { channel: "telegram", uid: "lm_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
    { channel: "email" },
  ]) {
    const response = requestResponse();
    let writes = 0;
    await handleWebMessageLinkRequest(linkRequest({ body }), response, {
      publicOrigin: "https://aniccaai.com",
      env: { SUPABASE_URL: "https://fixture.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role", LM_TELEGRAM_BOT_USERNAME: "LifeManagerBot" },
      resolveWebUserImpl: async () => ({ uid: "lm_12345678-1234-4234-8234-123456789abc", csrf: "csrf-fixture" }),
      readJsonImpl: async (req) => req.body,
      fetchImpl: async () => { writes += 1; return { ok: true, async json() { return true; } }; },
    });
    assert.equal(response.status, 400);
    assert.equal(writes, 0);
  }
});

test("one-time Telegram link binds only a valid sender and sends the token hash to the atomic RPC", async () => {
  assert.equal(typeof consumeWebMessageLink, "function", "the atomic link consumer must exist");
  const token = "B".repeat(32);
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const requests = [];
  const result = await consumeWebMessageLink(token, "telegram", "123456789", {
    env: { SUPABASE_URL: "https://fixture.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role" },
    fetchImpl: async (url, init) => {
      requests.push({ url: String(url), init });
      return { ok: true, status: 200, async json() { return uid; } };
    },
  });
  assert.deepEqual(result, { uid, channel: "telegram" });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "https://fixture.supabase.co/rest/v1/rpc/consume_lm_web_message_link");
  const body = JSON.parse(requests[0].init.body);
  assert.deepEqual(body, {
    p_token_hash: require("node:crypto").createHash("sha256").update(token).digest("hex"),
    p_channel: "telegram",
    p_sender_id: "123456789",
  });
  assert.equal(JSON.stringify(body).includes(token), false);
});

test("malformed Telegram link tokens and group senders never reach the binding RPC", async () => {
  assert.equal(typeof consumeWebMessageLink, "function", "the atomic link consumer must exist");
  let requests = 0;
  const opts = {
    env: { SUPABASE_URL: "https://fixture.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role" },
    fetchImpl: async () => { requests += 1; return { ok: true, async json() { return "lm_12345678-1234-4234-8234-123456789abc"; } }; },
  };
  assert.equal(await consumeWebMessageLink("short", "telegram", "123456789", opts), null);
  assert.equal(await consumeWebMessageLink("C".repeat(32), "telegram", "-100123456789", opts), null);
  assert.equal(requests, 0);
});

test("linked Telegram sender resolves through the canonical channel table to a Web-only user", async () => {
  assert.equal(typeof webTelegramUserBySender, "function", "the Web sender lookup must exist");
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const urls = [];
  const user = await webTelegramUserBySender("123456789", {
    supaUrl: "https://fixture.supabase.co",
    supaKey: "fixture-service-role",
    fetchImpl: async (input) => {
      const url = new URL(String(input));
      urls.push(url);
      if (url.pathname === "/rest/v1/lm_message_channels") {
        return { ok: true, async json() { return [{ uid, sender_id: "123456789", owner_kind: "web_link" }]; } };
      }
      if (url.pathname === "/rest/v1/lm_users") {
        return { ok: true, async json() { return [{
          uid, telegram_chat_id: null, calendar_provider: "composio_gcal",
          calendar_connected_account_id: "cal_abc123", gmail_account_id: null, paid: true,
        }]; } };
      }
      throw new Error(`unexpected lookup ${url.pathname}`);
    },
  });
  assert.deepEqual(user, {
    uid, telegram_chat_id: null, calendar_provider: "composio_gcal",
    calendar_connected_account_id: "cal_abc123", gmail_account_id: null, paid: true,
    web_message_telegram_chat_id: "123456789",
  });
  assert.equal(urls.length, 2);
  assert.match(urls[0].search, /channel=eq\.telegram/);
  assert.match(urls[0].search, /owner_kind=eq\.web_link/);
  assert.match(urls[0].search, /sender_id=eq\.123456789/);
  assert.match(urls[1].search, /telegram_chat_id=is\.null/);
});

test("scheduler channel map returns only Web-linked Telegram identities", async () => {
  assert.equal(typeof webTelegramChannelsForUids, "function", "the scheduler channel map reader must exist");
  const webUid = "lm_12345678-1234-4234-8234-123456789abc";
  const map = await webTelegramChannelsForUids([webUid, "lm_tg_legacy"], {
    supaUrl: "https://fixture.supabase.co",
    supaKey: "fixture-service-role",
    fetchImpl: async (input) => {
      const url = new URL(String(input));
      assert.equal(url.pathname, "/rest/v1/lm_message_channels");
      assert.match(url.search, /owner_kind=eq\.web_link/);
      assert.match(url.search, /channel=eq\.telegram/);
      return { ok: true, async json() { return [
        { uid: webUid, sender_id: "123456789", owner_kind: "web_link" },
        { uid: "lm_tg_legacy", sender_id: "987654321", owner_kind: "legacy" },
        { uid: "legacy-user", sender_id: "555", owner_kind: "web_link" },
      ]; } };
    },
  });
  assert.deepEqual([...map.entries()], [[webUid, "123456789"]]);
});
