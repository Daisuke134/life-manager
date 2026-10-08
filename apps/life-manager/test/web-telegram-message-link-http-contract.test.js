"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const crypto = require("node:crypto");

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return body; },
    async text() { return JSON.stringify(body); },
  };
}

test("Web-linked Telegram /start binds the Web UID without creating a legacy Telegram tenant", async () => {
  const envKeys = [
    "LM_TELEGRAM_BOT_TOKEN", "LM_TELEGRAM_WEBHOOK_SECRET", "LM_TELEGRAM_WEBHOOK_PATH",
    "LM_TELEGRAM_BOT_USERNAME", "LM_TELEGRAM_WEB_LINKS_ENABLED", "LM_PANEL_BASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "LIFE_RUN_LOOPS", "PORT",
  ];
  const before = Object.fromEntries(envKeys.map((key) => [key, process.env[key]]));
  Object.assign(process.env, {
    LM_TELEGRAM_BOT_TOKEN: "fixture-telegram-token",
    LM_TELEGRAM_WEBHOOK_SECRET: "fixture-webhook-secret",
    LM_TELEGRAM_BOT_USERNAME: "LifeManagerBot",
    LM_TELEGRAM_WEB_LINKS_ENABLED: "0",
    LM_PANEL_BASE_URL: "https://life-call-production.up.railway.app",
    SUPABASE_URL: "https://fixture.supabase.co",
    SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role",
    LIFE_RUN_LOOPS: "false",
    PORT: "0",
  });

  const originalCreateServer = http.createServer;
  const originalFetch = global.fetch;
  const webCsrf = "fixture-web-csrf";
  const uid = "lm_12345678-1234-4234-8234-123456789abc";
  const sends = [];
  const calls = [];
  const replies = [];
  let linked = false;
  let issuedTokenHash = null;
  let productionServer;
  let telegramReplyPath;
  let originalTelegramReplyExports;
  const webAuthPath = require.resolve("../lib/web-auth.js");
  const originalWebAuthExports = require(webAuthPath);
  require.cache[webAuthPath].exports = {
    ...originalWebAuthExports,
    resolveWebUser: async () => ({ uid, csrf: webCsrf }),
  };
  http.createServer = (handler) => {
    productionServer = originalCreateServer(handler);
    return productionServer;
  };
  global.fetch = async (input, init = {}) => {
    const url = new URL(String(input));
    const method = String(init.method || "GET").toUpperCase();
    calls.push({ url, method, body: init.body ? JSON.parse(init.body) : null });
    if (url.hostname === "api.telegram.org" && /sendMessage$/.test(url.pathname)) {
      sends.push(JSON.parse(init.body));
      return response(200, { ok: true, result: { message_id: 9001 + sends.length } });
    }
    if (url.pathname === "/rest/v1/rpc/create_lm_web_message_link") {
      issuedTokenHash = init.body && JSON.parse(init.body).p_token_hash;
      return response(200, true);
    }
    if (url.pathname === "/rest/v1/rpc/consume_lm_web_message_link") {
      const body = init.body ? JSON.parse(init.body) : {};
      const valid = body.p_token_hash === issuedTokenHash
        && body.p_channel === "telegram" && body.p_sender_id === "123456789";
      if (valid) linked = true;
      return response(200, valid ? uid : null);
    }
    if (url.pathname === "/rest/v1/lm_message_channels") {
      return response(200, linked && url.searchParams.get("sender_id") === "eq.123456789"
        ? [{ uid, channel: "telegram", sender_id: "123456789", owner_kind: "web_link" }]
        : []);
    }
    if (url.pathname === "/rest/v1/lm_users" && url.searchParams.has("uid")) {
      return response(200, linked && url.searchParams.get("uid") === `eq.${uid}`
        ? [{ uid, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "cal_abc123", gmail_account_id: null, paid: true }]
        : []);
    }
    if (url.pathname === "/rest/v1/lm_users") return response(200, []);
    if (url.pathname.startsWith("/rest/v1/rpc/claim_lm_panel_telegram_init")) {
      throw new Error("Web message link must not create a legacy Telegram user");
    }
    throw new Error(`unexpected fetch ${method} ${url.pathname}`);
  };

  try {
    telegramReplyPath = require.resolve("../lib/telegram-reply.js");
    originalTelegramReplyExports = require(telegramReplyPath);
    require.cache[telegramReplyPath].exports = {
      ...originalTelegramReplyExports,
      resolveTelegramReply: async (chatId, text) => {
        replies.push({ chatId, text });
        return { filled: true, event: "Product Review", location: "オンライン" };
      },
    };
    const serverPath = require.resolve("../server.js");
    delete require.cache[serverPath];
    require(serverPath);
    await new Promise((resolve) => productionServer.listen(0, "127.0.0.1", resolve));
    const port = productionServer.address().port;
    let updateId = 7100;
    let messageId = 8200;
    async function request(method, path, body = null, headers = {}) {
      const serialized = body == null ? "" : JSON.stringify(body);
      return new Promise((resolve, reject) => {
        const request = http.request(`http://127.0.0.1:${port}${path}`, {
          method,
          headers: {
            ...(serialized ? { "content-type": "application/json", "content-length": Buffer.byteLength(serialized) } : {}),
            ...headers,
          },
        }, (res) => {
          const chunks = [];
          res.on("data", (chunk) => chunks.push(chunk));
          res.on("end", () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString("utf8") }));
        });
        request.on("error", reject);
        request.end(serialized);
      });
    }
    async function postMessage(chatId, userId, text) {
      const body = JSON.stringify({
        update_id: updateId++,
        message: {
          message_id: messageId++,
          date: Math.floor(Date.now() / 1000),
          from: { id: userId, first_name: "Fixture" },
          chat: { id: chatId, type: chatId === userId ? "private" : "group" },
          text,
        },
      });
      return new Promise((resolve, reject) => {
        const request = http.request(`http://127.0.0.1:${port}/telegram`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "content-length": Buffer.byteLength(body),
            "x-telegram-bot-api-secret-token": "fixture-webhook-secret",
          },
        }, (res) => {
          res.resume();
          res.on("end", () => resolve(res.statusCode));
        });
        request.on("error", reject);
        request.end(body);
      });
    }

    const disabled = await request("POST", "/api/lm-web/message-link", { channel: "telegram" }, {
      origin: "https://life-call-production.up.railway.app",
      "x-lm-web-csrf": webCsrf,
    });
    assert.equal(disabled.status, 503);
    assert.equal(issuedTokenHash, null, "disabled provider link must not create a token");
    process.env.LM_TELEGRAM_WEB_LINKS_ENABLED = "1";
    const linkResponse = await request("POST", "/api/lm-web/message-link", { channel: "telegram" }, {
      origin: "https://life-call-production.up.railway.app",
      "x-lm-web-csrf": webCsrf,
    });
    assert.equal(linkResponse.status, 200);
    const link = JSON.parse(linkResponse.body);
    const linkUrl = new URL(link.url);
    assert.equal(linkUrl.hostname, "t.me");
    const startPayload = linkUrl.searchParams.get("start");
    assert.equal(startPayload?.startsWith("lmw_"), true);
    assert.equal(typeof issuedTokenHash, "string");
    assert.equal(issuedTokenHash, crypto.createHash("sha256").update(startPayload.slice(4)).digest("hex"));

    assert.equal(await postMessage("123456789", "123456789", `/start ${startPayload}`), 200);
    const rpcCalls = calls.filter((call) => call.url.pathname === "/rest/v1/rpc/consume_lm_web_message_link");
    assert.equal(rpcCalls.length, 1, "only the private chat with a well-formed token reaches the consume RPC");
    assert.deepEqual(rpcCalls[0].body, {
      p_token_hash: issuedTokenHash,
      p_channel: "telegram",
      p_sender_id: "123456789",
    });
    assert.equal(calls.some((call) => call.url.pathname === "/rest/v1/lm_users"), false,
      "a Web-linked /start must not look up or create a legacy Telegram tenant");
    assert.equal(calls.some((call) => call.url.pathname.startsWith("/rest/v1/rpc/claim_lm_panel_telegram_init")), false);
    assert.equal(await postMessage("123456789", "123456789", "The meeting is online"), 200);
    assert.deepEqual(replies, [{ chatId: "123456789", text: "The meeting is online" }]);
    assert.match(sends.at(-1).text, /Product Review.*オンライン/);
    const mappingLookupsBeforeGroup = calls.filter((call) => call.url.pathname === "/rest/v1/lm_message_channels").length;
    assert.equal(await postMessage("-100123456789", "123456789", `/start ${startPayload}`), 200);
    assert.equal(calls.filter((call) => call.url.pathname === "/rest/v1/lm_message_channels").length, mappingLookupsBeforeGroup,
      "a group chat must not query or disclose a member's private Web link state");
    assert.equal(await postMessage("555555555", "555555555", "/start lmw_invalid"), 200);
    assert.equal(calls.filter((call) => call.url.pathname === "/rest/v1/rpc/consume_lm_web_message_link").length, 1);
    assert.equal(calls.some((call) => call.url.pathname.startsWith("/rest/v1/rpc/claim_lm_panel_telegram_init")), false);
    assert.equal(sends.length, 4);
    assert.match(sends[0].text, /接続|connected/i);
    assert.match(sends[2].text, /リンク|expired|invalid/i);
    assert.doesNotMatch(sends[2].text, /接続済み|already connected/i);
  } finally {
    if (telegramReplyPath && originalTelegramReplyExports) require.cache[telegramReplyPath].exports = originalTelegramReplyExports;
    require.cache[webAuthPath].exports = originalWebAuthExports;
    http.createServer = originalCreateServer;
    global.fetch = originalFetch;
    for (const key of envKeys) {
      if (before[key] === undefined) delete process.env[key];
      else process.env[key] = before[key];
    }
    if (productionServer && productionServer.listening) {
      await new Promise((resolve) => productionServer.close(resolve));
    }
    delete require.cache[require.resolve("../server.js")];
  }
});
