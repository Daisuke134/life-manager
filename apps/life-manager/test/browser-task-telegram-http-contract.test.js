"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { buildBrowserJob } = require("../lib/browser-job-store.js");

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return body; },
    async text() { return JSON.stringify(body); },
  };
}

test("real Telegram webhook classifies and durably queues natural language without opening a browser inline", async () => {
  process.env.LM_TELEGRAM_BOT_TOKEN = "fixture-token";
  process.env.LM_TELEGRAM_WEBHOOK_SECRET = "fixture-webhook-secret";
  process.env.SUPABASE_URL = "https://fixture.supabase.co";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "fixture-service-role";
  process.env.GEMINI_API_KEY = "fixture-gemini";
  process.env.LM_BROWSER_TASKS_ENABLED = "1";
  process.env.LIFE_RUN_LOOPS = "false";

  const originalCreateServer = http.createServer;
  const originalFetch = global.fetch;
  let productionServer;
  let queued;
  let steelCalls = 0;
  const sent = [];
  let originalIntakeExports;
  let intakePath;
  http.createServer = (handler) => {
    productionServer = originalCreateServer(handler);
    return productionServer;
  };
  global.fetch = async (input, init = {}) => {
    const url = new URL(String(input));
    const method = String(init.method || "GET").toUpperCase();
    if (url.hostname === "generativelanguage.googleapis.com") {
      return response(200, {
        candidates: [{
          content: { parts: [{ text: JSON.stringify({
            browser_required: true,
            explicit_request: true,
            reversible: true,
            zero_cost: true,
            requires_kyc: false,
            requires_login: false,
            principal_kind: "none",
            action_kind: "registration",
            binding_commitment: false,
            goal: "Find and register the agent-owned email for a free public online AI event",
            locale: "en",
          }) }] },
        }],
      });
    }
    if (url.hostname === "api.telegram.org" && /sendMessage$/.test(url.pathname)) {
      sent.push(JSON.parse(init.body));
      return response(200, { ok: true, result: { message_id: 9001 } });
    }
    if (url.pathname === "/rest/v1/lm_message_channels" && method === "GET") {
      return response(200, [{ uid: "u1", owner_kind: "legacy" }]);
    }
    if (url.pathname === "/rest/v1/lm_users" && method === "GET") {
      return response(200, [{
        uid: "u1",
        telegram_chat_id: "100",
        tg_onboard_stage: "done",
        paid: true,
      }]);
    }
    if (url.hostname.includes("steel-browser")) {
      steelCalls += 1;
      throw new Error("browser must not run inside Telegram webhook");
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  };

  try {
    intakePath = require.resolve("../lib/browser-task-intake.js");
    originalIntakeExports = require(intakePath);
    require.cache[intakePath].exports = {
      ...originalIntakeExports,
      handleBrowserTaskMessage: (input, deps) => originalIntakeExports.handleBrowserTaskMessage(input, {
        ...deps,
        enqueue: async (enqueueInput) => {
          queued = buildBrowserJob(enqueueInput);
          return { created: true, job: { id: "browser-job-1", ...queued } };
        },
      }),
    };
    const serverPath = require.resolve("../server.js");
    delete require.cache[serverPath];
    require(serverPath);
    await new Promise((resolve) => productionServer.listen(0, "127.0.0.1", resolve));
    const body = JSON.stringify({
      update_id: 7001,
      message: {
        message_id: 8101,
        date: Math.floor(Date.now() / 1000),
        from: { id: 100, first_name: "Fixture" },
        chat: { id: 100, type: "private" },
        text: "Find a free public online AI event and register contact@aniccaai.com",
      },
    });
    const status = await new Promise((resolve, reject) => {
      const request = http.request(
        `http://127.0.0.1:${productionServer.address().port}/telegram`,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "content-length": Buffer.byteLength(body),
            "x-telegram-bot-api-secret-token": "fixture-webhook-secret",
          },
        },
        (res) => {
          res.resume();
          res.on("end", () => resolve(res.statusCode));
        },
      );
      request.on("error", reject);
      request.end(body);
    });
    assert.equal(status, 200);
    assert.equal(queued.uid, "u1");
    assert.equal(queued.telegram_message_id, "8101");
    assert.equal(queued.telegram_update_id, "7001");
    assert.equal(queued.principal_kind, "none");
    assert.match(queued.prompt_hash, /^[a-f0-9]{64}$/);
    assert.equal(JSON.stringify(queued).includes("contact@aniccaai.com"), false);
    assert.equal(sent.length, 1);
    assert.match(sent[0].text, /browser-job-1/);
    assert.equal(steelCalls, 0);
  } finally {
    if (intakePath && originalIntakeExports) require.cache[intakePath].exports = originalIntakeExports;
    delete process.env.LM_BROWSER_TASKS_ENABLED;
    http.createServer = originalCreateServer;
    global.fetch = originalFetch;
    if (productionServer && productionServer.listening) {
      await new Promise((resolve) => productionServer.close(resolve));
    }
  }
});
