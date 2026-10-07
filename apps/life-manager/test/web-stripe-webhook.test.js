"use strict";

const assert = require("node:assert/strict");
const http = require("node:http");
const test = require("node:test");
const Stripe = require("stripe");

const UID = "lm_123e4567-e89b-12d3-a456-426614174000";
const WEBHOOK_SECRET = "whsec_lm_webhook_retry_test_only";

test("Web webhook claim/read/resume failures remain retryable through duplicate delivery", async () => {
  const envNames = ["NODE_ENV", "STRIPE_SECRET_KEY", "STRIPE_TEST_WEBHOOK_SECRET",
    "STRIPE_WEBHOOK_SECRET", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"];
  const previous = Object.fromEntries(envNames.map((name) => [name, process.env[name]]));
  const row = {
    uid: UID,
    telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z",
    calendar_connected_account_id: "ca-test-123",
    stripe_customer_id: "cus_web_test",
    stripe_subscription_id: null,
    current_period_end: null,
    stripe_event_at: null,
    plan_status: null,
    paid: false,
    trial_expires_at: null,
    web_billing_revision: 0,
    web_billing_cancel_at_period_end: false,
    web_automation_resume_pending: false,
    web_subscription_created_at: null,
    daily_automation_enabled: false,
    web_subscription_event_at: null,
    web_subscription_event_priority: null,
    web_subscription_event_id: null,
    web_subscription_latest_invoice_id: null,
    web_invoice_event_at: null,
    web_invoice_event_priority: null,
    web_invoice_event_id: null,
    web_invoice_id: null,
    web_invoice_subscription_id: null,
    web_invoice_paid: false,
    web_invoice_amount_paid: null,
  };
  const eventIds = new Set();
  let claimFailures = 1;
  let readFailures = 1;
  let unclaimFailures = 1;
  let resumeFailures = 1;
  let resumeCalls = 0;
  const supabase = http.createServer(async (req, res) => {
    const url = new URL(req.url || "/", "http://127.0.0.1");
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
    const json = (status, value) => {
      res.writeHead(status, { "content-type": "application/json" });
      res.end(JSON.stringify(value));
    };

    if (url.pathname === "/rest/v1/lm_stripe_events" && req.method === "POST") {
      if (claimFailures-- > 0) return json(503, { message: "temporary claim failure" });
      if (eventIds.has(body.event_id)) return json(409, { message: "duplicate" });
      eventIds.add(body.event_id);
      return json(201, {});
    }
    if (url.pathname === "/rest/v1/lm_stripe_events" && req.method === "DELETE") {
      if (unclaimFailures-- > 0) return json(503, { message: "temporary unclaim failure" });
      eventIds.delete(url.searchParams.get("event_id").replace(/^eq\./, ""));
      res.writeHead(204); return res.end();
    }
    if (url.pathname === "/rest/v1/lm_users" && req.method === "GET") {
      if (readFailures-- > 0) return json(503, { message: "temporary user read failure" });
      return json(200, [{ ...row }]);
    }
    if (url.pathname === "/rest/v1/lm_users" && req.method === "PATCH") {
      const expected = Number(url.searchParams.get("web_billing_revision").replace(/^eq\./, ""));
      if (expected !== row.web_billing_revision) return json(200, []);
      Object.assign(row, body);
      return json(200, [{ uid: row.uid }]);
    }
    if (url.pathname === "/rest/v1/rpc/resume_lm_web_billing_automation" && req.method === "POST") {
      resumeCalls++;
      assert.equal(body.p_uid, UID);
      assert.equal(body.p_calendar_account_id, "ca-test-123");
      if (resumeFailures-- > 0) return json(503, { message: "temporary resume failure" });
      if (row.web_automation_resume_pending) {
        row.web_automation_resume_pending = false;
        row.web_billing_revision++;
        row.daily_automation_enabled = true;
      }
      return json(200, true);
    }
    return json(404, { message: "unexpected endpoint" });
  });

  await new Promise((resolve) => supabase.listen(0, "127.0.0.1", resolve));
  const supabaseUrl = `http://127.0.0.1:${supabase.address().port}`;
  process.env.NODE_ENV = "test";
  process.env.STRIPE_SECRET_KEY = "sk_test_lm_webhook_retry_test_123456";
  process.env.STRIPE_TEST_WEBHOOK_SECRET = WEBHOOK_SECRET;
  delete process.env.STRIPE_WEBHOOK_SECRET;
  process.env.SUPABASE_URL = supabaseUrl;
  process.env.SUPABASE_SERVICE_ROLE_KEY = "service-role-test";

  let appServer;
  try {
    delete require.cache[require.resolve("../server.js")];
    appServer = require("../server.js").server;
    await new Promise((resolve) => appServer.listen(0, "127.0.0.1", resolve));
    const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);
    const created = Math.floor(Date.now() / 1000);
    const event = {
      id: "evt_lm_webhook_retry_test",
      type: "customer.subscription.created",
      created,
      data: { object: {
        id: "sub_web_test",
        customer: "cus_web_test",
        status: "trialing",
        trial_end: created + 7 * 24 * 60 * 60,
        default_payment_method: "pm_test_saved",
        metadata: { lm_uid: UID, lm_product: "life_manager_web_travel" },
      } },
    };
    const payload = JSON.stringify(event);
    const signature = stripe.webhooks.generateTestHeaderString({ payload, secret: WEBHOOK_SECRET });
    const endpoint = `http://127.0.0.1:${appServer.address().port}/api/stripe/webhook`;
    const send = () => fetch(endpoint, { method: "POST", headers: {
      "content-type": "application/json", "stripe-signature": signature,
    }, body: payload });

    const responses = [];
    for (let i = 0; i < 4; i++) responses.push((await send()).status);

    assert.deepEqual(responses, [500, 500, 500, 200]);
    assert.equal(row.web_billing_revision, 2);
    assert.equal(row.paid, true);
    assert.equal(row.plan_status, "trialing");
    assert.equal(row.web_subscription_event_id, event.id);
    assert.equal(row.web_automation_resume_pending, false);
    assert.equal(row.daily_automation_enabled, true);
    assert.equal(eventIds.has(event.id), true);
    assert.equal(resumeCalls, 2);

    // The user-facing pause RPC clears the activation intent while holding the lm_users row lock.
    row.web_billing_revision++;
    row.web_automation_resume_pending = false;
    row.daily_automation_enabled = false;
    assert.equal((await send()).status, 200);
    assert.equal(resumeCalls, 2);
    assert.equal(row.daily_automation_enabled, false);
  } finally {
    if (appServer && appServer.listening) await new Promise((resolve) => appServer.close(resolve));
    await new Promise((resolve) => supabase.close(resolve));
    for (const name of envNames) {
      if (previous[name] === undefined) delete process.env[name];
      else process.env[name] = previous[name];
    }
    delete require.cache[require.resolve("../server.js")];
  }
});
