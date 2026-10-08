"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

let parseWebTelegramStart = null;
let createWebMessageLink = null;
let handleWebMessageLinkRequest = null;
let consumeWebMessageLink = null;
let webTelegramUserBySender = null;
let webTelegramChannelsForUids = null;
let webMessageUserBySender = null;
let webMessageChannelsForUids = null;
try { ({ parseWebTelegramStart, createWebMessageLink, handleWebMessageLinkRequest, consumeWebMessageLink, webTelegramUserBySender, webTelegramChannelsForUids, webMessageUserBySender, webMessageChannelsForUids } = require("./message-links.js")); } catch {}

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

test("iMessage link returns a Messages URL and a one-time code without a phone form", async () => {
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const token = Buffer.alloc(24, 3).toString("base64url");
  const requests = [];
  let result, thrown;
  try {
    result = await createWebMessageLink(uid, "imessage", {
      env: {
        SUPABASE_URL: "https://fixture.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role",
        LM_IMESSAGE_WEB_LINKS_ENABLED: "1",
        LM_IMESSAGE_CONTACT_NUMBER: "+15551234567",
        SPECTRUM_PROJECT_ID: "spectrum-project",
        SPECTRUM_PROJECT_SECRET: "spectrum-secret-fixture",
      },
      imessageReady: true,
      nowMs: 1_800_000_000_000,
      randomBytesImpl: (size) => { assert.equal(size, 24); return Buffer.alloc(24, 3); },
      fetchImpl: async (url, init) => {
        requests.push({ url: String(url), init });
        return { ok: true, status: 200, async json() { return true; } };
      },
    });
  } catch (error) { thrown = error; }
  assert.equal(thrown, undefined, "configured iMessage should issue a pairing link");
  assert.deepEqual(result, {
    url: "sms:+15551234567",
    code: `LMI_${token}`,
    expiresAt: new Date(1_800_000_600_000).toISOString(),
  });
  assert.equal(requests.length, 1);
  const body = JSON.parse(requests[0].init.body);
  assert.equal(body.p_uid, uid);
  assert.equal(body.p_channel, "imessage");
  assert.equal(body.p_token_hash, require("node:crypto").createHash("sha256").update(token).digest("hex"));
  assert.equal(JSON.stringify(body).includes(token), false);
});

test("iMessage pairing requires its feature flag, provider credentials, and fixed contact number", async () => {
  const base = {
    SUPABASE_URL: "https://fixture.supabase.co",
    SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role",
    LM_IMESSAGE_CONTACT_NUMBER: "+15551234567",
    SPECTRUM_PROJECT_ID: "spectrum-project",
    SPECTRUM_PROJECT_SECRET: "spectrum-secret-fixture",
  };
  for (const env of [
    { ...base, LM_IMESSAGE_WEB_LINKS_ENABLED: "0" },
    { ...base, LM_IMESSAGE_WEB_LINKS_ENABLED: "1", SPECTRUM_PROJECT_SECRET: "" },
    { ...base, LM_IMESSAGE_WEB_LINKS_ENABLED: "1", LM_IMESSAGE_CONTACT_NUMBER: "" },
  ]) {
    let writes = 0;
    await assert.rejects(createWebMessageLink(
      "lm_12345678-1234-4234-8234-123456789abc", "imessage", {
        env, imessageReady: true,
        fetchImpl: async () => { writes += 1; return { ok: true, async json() { return true; } }; },
      }), (error) => error && error.message === "imessage_link_unavailable");
    assert.equal(writes, 0);
  }
});

test("Web message-link endpoint accepts iMessage only when the provider is ready", async () => {
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const response = requestResponse();
  let writes = 0;
  await handleWebMessageLinkRequest(linkRequest({ body: { channel: "imessage" } }), response, {
    publicOrigin: "https://aniccaai.com/lm",
    env: {
      SUPABASE_URL: "https://fixture.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role",
      LM_IMESSAGE_WEB_LINKS_ENABLED: "1",
      LM_IMESSAGE_CONTACT_NUMBER: "+15551234567",
      SPECTRUM_PROJECT_ID: "spectrum-project",
      SPECTRUM_PROJECT_SECRET: "spectrum-secret-fixture",
    },
    imessageReady: true,
    resolveWebUserImpl: async () => ({ uid, csrf: "csrf-fixture" }),
    readJsonImpl: async (req) => req.body,
    randomBytesImpl: () => Buffer.alloc(24, 3),
    fetchImpl: async () => { writes += 1; return { ok: true, async json() { return true; } }; },
  });
  assert.equal(response.status, 200);
  const body = JSON.parse(response.body);
  assert.equal(body.url, "sms:+15551234567");
  assert.match(body.code, /^LMI_[A-Za-z0-9_-]{32}$/);
  assert.equal(body.uid, undefined);
  assert.equal(writes, 1);

  const unavailable = requestResponse();
  await handleWebMessageLinkRequest(linkRequest({ body: { channel: "imessage" } }), unavailable, {
    publicOrigin: "https://aniccaai.com/lm",
    env: { SUPABASE_URL: "https://fixture.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role" },
    resolveWebUserImpl: async () => ({ uid, csrf: "csrf-fixture" }),
    readJsonImpl: async (req) => req.body,
    fetchImpl: async () => { writes += 1; return { ok: true, async json() { return true; } }; },
  });
  assert.equal(unavailable.status, 503);
  assert.equal(writes, 1);
});

test("iMessage token consumption binds only a valid E.164 sender and is one-use", async () => {
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const token = "E".repeat(32);
  const requests = [];
  const opts = {
    env: { SUPABASE_URL: "https://fixture.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role" },
    fetchImpl: async (url, init) => {
      requests.push({ url: String(url), init });
      return { ok: true, status: 200, async json() { return requests.length === 1 ? uid : null; } };
    },
  };
  assert.deepEqual(await consumeWebMessageLink(token, "imessage", "+819012345678", opts), { uid, channel: "imessage" });
  assert.equal(await consumeWebMessageLink(token, "imessage", "not-a-sender", opts), null);
  assert.equal(requests.length, 1);
  const body = JSON.parse(requests[0].init.body);
  assert.equal(body.p_channel, "imessage");
  assert.equal(body.p_sender_id, "+819012345678");
  assert.equal(body.p_token_hash, require("node:crypto").createHash("sha256").update(token).digest("hex"));
  assert.equal(JSON.stringify(body).includes(token), false);
});

test("linked iMessage sender resolves only through the iMessage owner row", async () => {
  assert.equal(typeof webMessageUserBySender, "function", "a channel-generic Web sender lookup must exist");
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const urls = [];
  const user = await webMessageUserBySender("imessage", "+819012345678", {
    supaUrl: "https://fixture.supabase.co", supaKey: "fixture-service-role",
    fetchImpl: async (input) => {
      const url = new URL(String(input)); urls.push(url);
      if (url.pathname === "/rest/v1/lm_message_channels") return { ok: true, async json() { return [{ uid, sender_id: "+819012345678", channel: "imessage", owner_kind: "web_link" }]; } };
      if (url.pathname === "/rest/v1/lm_users") return { ok: true, async json() { return [{ uid, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "cal_test", gmail_account_id: null, paid: true }]; } };
      throw new Error(`unexpected lookup ${url.pathname}`);
    },
  });
  assert.equal(user.uid, uid);
  assert.equal(user.telegram_chat_id, null);
  assert.equal(user.web_message_imessage_sender_id, "+819012345678");
  assert.match(urls[0].search, /channel=eq\.imessage/);
  assert.equal(urls[0].searchParams.get("sender_id"), "eq.+819012345678");
  assert.match(urls[1].search, /telegram_chat_id=is\.null/);
  for (const field of ["plan_status", "trial_expires_at", "web_trial_payment_method_present", "web_billing_cancel_at_period_end"]) {
    assert.ok(urls[1].searchParams.get("select").split(",").includes(field), `sender lookup must include ${field} for entitlement checks`);
  }
});

test("iMessage scheduler channel map returns only Web-linked senders", async () => {
  assert.equal(typeof webMessageChannelsForUids, "function", "a channel-generic scheduler map reader must exist");
  const webUid = "lm_12345678-1234-4234-8234-123456789abc";
  const map = await webMessageChannelsForUids([webUid], "imessage", {
    supaUrl: "https://fixture.supabase.co", supaKey: "fixture-service-role",
    fetchImpl: async (input) => {
      const url = new URL(String(input));
      assert.match(url.search, /channel=eq\.imessage/);
      assert.match(url.search, /owner_kind=eq\.web_link/);
      return { ok: true, async json() { return [
        { uid: webUid, sender_id: "+819012345678", owner_kind: "web_link" },
        { uid: "lm_foreign", sender_id: "+819099999999", owner_kind: "web_link" },
      ]; } };
    },
  });
  assert.deepEqual([...map.entries()], [[webUid, "+819012345678"]]);
});
