"use strict";
// HARD-3 billing lifecycle — unit tests. Source of truth = Stripe subscription.status; ordering = event.created.
// Run: node --test lib/billing.test.js
const { test } = require("node:test");
const assert = require("node:assert");
const {
  entitlementFor, parseStripeEvent, isStale, toEpoch,
  claimEvent, unclaimEvent, applyBilling, webPaidCheckoutEligible, webTravelEntitled,
} = require("./billing.js");

// ── entitlementFor: the fixed Stripe status → entitlement table (REQ-38) ──────
test("entitlementFor: active/trialing/past_due → paid=true (provision + grace)", () => {
  for (const s of ["active", "trialing", "past_due", "ACTIVE", "Trialing"]) assert.strictEqual(entitlementFor(s).paid, true, s);
});
test("entitlementFor: canceled/unpaid/incomplete* → paid=false (revoke)", () => {
  for (const s of ["canceled", "unpaid", "incomplete", "incomplete_expired", "paused"]) assert.strictEqual(entitlementFor(s).paid, false, s);
});
test("entitlementFor: unknown/empty/null → paid=false (fail-safe)", () => {
  for (const s of [undefined, null, "", "weird"]) assert.strictEqual(entitlementFor(s).paid, false);
  assert.strictEqual(entitlementFor("active").plan_status, "active");
  assert.strictEqual(entitlementFor(null).plan_status, null);
});

// ── parseStripeEvent (REQ-37/38) ──────
test("parseStripeEvent: checkout → uid, customer, sub, paymentStatus, created", () => {
  const p = parseStripeEvent({ id: "e", type: "checkout.session.completed", created: 1700000000,
    data: { object: { client_reference_id: "uid-abc", customer: "cus_1", subscription: "sub_1", payment_status: "paid" } } });
  assert.deepStrictEqual([p.kind, p.uid, p.customerId, p.subscriptionId, p.paymentStatus, p.created],
    ["checkout", "uid-abc", "cus_1", "sub_1", "paid", 1700000000]);
});
test("parseStripeEvent: subscription.updated → status, currentPeriodEnd, created", () => {
  const p = parseStripeEvent({ id: "e", type: "customer.subscription.updated", created: 1700000005,
    data: { object: { id: "sub_1", customer: "cus_1", status: "past_due", current_period_end: 1750000000 } } });
  assert.deepStrictEqual([p.kind, p.customerId, p.subscriptionId, p.status, p.currentPeriodEnd, p.created],
    ["subscription", "cus_1", "sub_1", "past_due", 1750000000, 1700000005]);
});
test("parseStripeEvent: current Stripe subscription item period supplies currentPeriodEnd", () => {
  const p = parseStripeEvent({ id: "e", type: "customer.subscription.updated", created: 1700000005,
    data: { object: { id: "sub_1", customer: "cus_1", status: "active", items: { data: [
      { current_period_end: 1750000000 }, { current_period_end: 1750003600 },
    ] } } } });
  assert.strictEqual(p.currentPeriodEnd, 1750003600);
});
test("parseStripeEvent: deleted → canceled; unknown → null", () => {
  assert.strictEqual(parseStripeEvent({ id: "e", type: "customer.subscription.deleted", data: { object: { status: "canceled" } } }).status, "canceled");
  assert.strictEqual(parseStripeEvent({ id: "x", type: "ping", data: { object: {} } }), null);
});
test("parseStripeEvent: Web trial includes uid, trial end, and retained payment method", () => {
  const p = parseStripeEvent({ id: "e", type: "customer.subscription.created", created: 1700000005,
    data: { object: { id: "sub_web", customer: "cus_web", status: "trialing", trial_end: 1700604800,
      default_payment_method: "pm_saved", metadata: { lm_uid: "lm_11111111-1111-4111-8111-111111111111", lm_product: "life_manager_web_travel" } } } });
  assert.deepStrictEqual([p.uid, p.trialEnd, p.hasPaymentMethod, p.isWebTravel],
    ["lm_11111111-1111-4111-8111-111111111111", 1700604800, true, true]);
});
test("parseStripeEvent: scheduled cancellation is distinct from trialing status", () => {
  const p = parseStripeEvent({ id: "e", type: "customer.subscription.updated", created: 1700000010,
    data: { object: { id: "sub_web", customer: "cus_web", status: "trialing", trial_end: 1700604800,
      default_payment_method: "pm_saved", cancel_at_period_end: true,
      metadata: { lm_uid: "lm_11111111-1111-4111-8111-111111111111", lm_product: "life_manager_web_travel" } } } });
  assert.equal(p.status, "trialing");
  assert.equal(p.cancelAtPeriodEnd, true);
});
test("parseStripeEvent: invoice payment outcomes include subscription identity", () => {
  const paid = parseStripeEvent({ id: "e1", type: "invoice.paid", created: 1700000010,
    data: { object: { id: "in_paid", customer: "cus_web", subscription: "sub_web", status: "paid", billing_reason: "subscription_cycle",
      amount_paid: 2900, amount_due: 2900 } } });
  const failed = parseStripeEvent({ id: "e2", type: "invoice.payment_failed", created: 1700000020,
    data: { object: { id: "in_failed", customer: "cus_web", parent: { subscription_details: { subscription: "sub_web" } },
      amount_paid: 0, amount_due: 2900 } } });
  assert.deepStrictEqual([paid.kind, paid.status, paid.subscriptionId], ["invoice", "paid", "sub_web"]);
  assert.deepStrictEqual([failed.kind, failed.status, failed.subscriptionId], ["invoice", "payment_failed", "sub_web"]);
  assert.deepStrictEqual([paid.eventId, paid.invoiceId, paid.amountPaid, paid.amountDue, paid.billingReason],
    ["e1", "in_paid", 2900, 2900, "subscription_cycle"]);
  assert.deepStrictEqual([failed.eventId, failed.amountPaid, failed.amountDue], ["e2", 0, 2900]);
});

// ── isStale: out-of-order guard keyed on event.created (REQ-39, FIND-002) ──────
test("isStale: older created → stale; newer/equal → fresh", () => {
  const row = { stripe_event_at: new Date(1700000100 * 1000).toISOString() };
  assert.strictEqual(isStale(1700000050, row), true);
  assert.strictEqual(isStale(1700000200, row), false);
  assert.strictEqual(isStale(1700000100, row), false);
});
test("isStale: no stored timestamp → never stale (first event applies)", () => {
  assert.strictEqual(isStale(100, null), false);
  assert.strictEqual(isStale(100, {}), false);
});
test("FIND-002: immediate-cancel with LOWER current_period_end but LATER created still applies (not stale)", () => {
  // active applied at created=1700000100 (period_end far future); cancel arrives later created=1700000200
  // but with an earlier current_period_end. Keyed on created → cancel is NOT stale → downgrade applies.
  const row = { stripe_event_at: new Date(1700000100 * 1000).toISOString() };
  assert.strictEqual(isStale(1700000200, row), false, "cancel (later created) must apply even with lower period_end");
});
test("toEpoch parses ISO + numeric + epoch", () => {
  assert.strictEqual(toEpoch(1700000100), 1700000100);
  assert.strictEqual(toEpoch("1700000100"), 1700000100);
  assert.strictEqual(toEpoch(new Date(1700000100 * 1000).toISOString()), 1700000100);
  assert.strictEqual(toEpoch(null), 0);
});

// ── claim / unclaim idempotency ledger (REQ-36) ──────
test("claimEvent: 201 → true; 409 → false; no creds → true", async () => {
  let n = 0;
  const f = async () => ({ status: ++n === 1 ? 201 : 409 });
  assert.strictEqual(await claimEvent("e1", "t", "http://s", "k", f), true);
  assert.strictEqual(await claimEvent("e1", "t", "http://s", "k", f), false);
  assert.strictEqual(await claimEvent("e1", "t", "", "", null), true);
  await assert.rejects(claimEvent("e2", "t", "http://s", "k", async () => ({ status: 503 })), /claim failed/);
  await assert.rejects(claimEvent("e3", "t", "http://s", "k", async () => { throw new Error("offline"); }), /store unavailable/);
});
test("unclaimEvent: DELETE → true; failure → false (caller logs RECONCILE)", async () => {
  assert.strictEqual(await unclaimEvent("e1", "http://s", "k", async () => ({ status: 204 })), true);
  assert.strictEqual(await unclaimEvent("e1", "http://s", "k", async () => ({ status: 500 })), false);
});

// ── applyBilling: the orchestration core (REQ-37/38/39/40, FIND-004) ──────
// fakeSupa: routes PostgREST calls; GET lm_users?stripe_customer_id → storedRow; PATCH → records patch.
function fakeSupa(storedRow) {
  const state = storedRow ? { ...storedRow } : null;
  const patches = [], rpcCalls = [];
  const f = async (url, opts) => {
    const method = opts && opts.method;
    if (url.includes("/rpc/")) {
      const body = JSON.parse(opts.body);
      rpcCalls.push({ url, body });
      if (url.endsWith("/rpc/resume_lm_web_billing_automation")) {
        if (!state || state.telegram_chat_id !== null
          || body.p_calendar_account_id !== state.calendar_connected_account_id) {
          return { ok: true, json: async () => false };
        }
        if (state.web_automation_resume_pending && state.web_automation_user_paused !== true) {
          state.web_automation_resume_pending = false;
          state.web_billing_revision = Number(state.web_billing_revision || 0) + 1;
        }
      }
      return { ok: true, json: async () => true };
    }
    if (!method && url.includes("select=")) // a GET lookup (userByCustomer or userByUid)
      return { ok: true, json: async () => (state ? [{ ...state, web_billing_revision: Number(state.web_billing_revision || 0) }] : []) };
    if (method === "PATCH" && url.includes("lm_users?uid=eq.")) {
      const patch = JSON.parse(opts.body);
      patches.push({ url, body: patch });
      const parsed = new URL(url);
      if (parsed.searchParams.has("web_billing_revision")) {
        const matchesFence = (column) => {
          const predicate = parsed.searchParams.get(column);
          if (predicate === null) return true;
          if (predicate === "is.null") return state && state[column] == null;
          if (predicate.startsWith("eq.")) return state && String(state[column] ?? "") === predicate.slice(3);
          return false;
        };
        if (!state || !["telegram_chat_id", "stripe_customer_id", "stripe_subscription_id",
          "calendar_provider", "calendar_connected_account_id"].every(matchesFence)) {
          return { ok: true, status: 200, json: async () => [] };
        }
        const expectedRevision = Number(parsed.searchParams.get("web_billing_revision").replace(/^eq\./, ""));
        if (!state || Number(state.web_billing_revision || 0) !== expectedRevision) {
          return { ok: true, status: 200, json: async () => [] };
        }
        Object.assign(state, patch);
        return { ok: true, status: 200, json: async () => [{ uid: state.uid }] };
      }
      if (state) Object.assign(state, patch);
      return { ok: true, status: 204 };
    }
    return { ok: false, status: 404, json: async () => [] };
  };
  return { f, patches, rpcCalls, row: () => state };
}
const deps = (supa, notify) => ({
  supaUrl: "http://s", supaKey: "k", fetchImpl: supa.f, notify,
  retrieveSubscription: async (subscriptionId) => {
    const row = supa.row();
    if (!row) return null;
    return {
      id: subscriptionId,
      customer: row.stripe_customer_id || "cus_web",
      created: toEpoch(row.web_subscription_created_at) || 90,
      status: row.plan_status || null,
      current_period_end: toEpoch(row.current_period_end) || 0,
      trial_end: toEpoch(row.trial_expires_at),
      default_payment_method: row.web_trial_payment_method_present === true ? "pm_saved" : null,
      cancel_at_period_end: row.web_billing_cancel_at_period_end === true,
      latest_invoice: row.web_subscription_latest_invoice_id || null,
      metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" },
    };
  },
});
const WEB_UID = "lm_11111111-1111-4111-8111-111111111111";
const webBillingRow = (overrides = {}) => ({
  uid: WEB_UID, telegram_chat_id: null,
  web_first_travel_at: "2030-01-01T00:00:00.000Z",
  calendar_provider: "composio_gcal",
  calendar_connected_account_id: "ca-selected-123",
  stripe_customer_id: "cus_web", stripe_subscription_id: "sub_web",
  web_billing_revision: 0, web_automation_resume_pending: false,
  web_automation_user_paused: false, web_trial_payment_method_present: false,
  paid: false, plan_status: "trialing",
  ...overrides,
});
const webSubscriptionEvent = (id, created, object) => ({
  id, type: "customer.subscription.updated", created,
  data: { object: { id: "sub_web", customer: "cus_web",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" }, ...object } },
});
const webInvoiceEvent = (id, type, created, object = {}) => ({
  id, type, created,
  data: { object: { id: `in_${id}`, customer: "cus_web", subscription: "sub_web", status: "paid",
    amount_paid: 2900, amount_due: 2900, billing_reason: "subscription_cycle", ...object } },
});

test("applyBilling checkout PAID → provision (paid=true, plan=active, linked)", async () => {
  const s = fakeSupa(null);
  const r = await applyBilling({ id: "e", type: "checkout.session.completed", created: 100,
    data: { object: { client_reference_id: "u1", customer: "cus", subscription: "sub", payment_status: "paid" } } }, deps(s));
  assert.strictEqual(r.action, "provision");
  assert.strictEqual(s.patches[0].body.paid, true);
  assert.strictEqual(s.patches[0].body.plan_status, "active");
  assert.strictEqual(s.patches[0].body.stripe_customer_id, "cus");
});
test("applyBilling checkout UNPAID → link only, paid=false (FIND-003)", async () => {
  const s = fakeSupa(null);
  const r = await applyBilling({ id: "e", type: "checkout.session.completed", created: 100,
    data: { object: { client_reference_id: "u1", customer: "cus", subscription: "sub", payment_status: "unpaid" } } }, deps(s));
  assert.strictEqual(r.action, "link-unpaid");
  assert.strictEqual(s.patches[0].body.paid, false);
});
test("FIND-007: out-of-order UNPAID checkout (older created) does NOT clobber an active payer", async () => {
  // a subscription.active was already applied at created=200 (paid=true); a LATE unpaid checkout (created=100)
  // must be stale → NO write → the active payer keeps paid=true and stripe_event_at is not regressed.
  const row = { uid: "u1", paid: true, stripe_event_at: new Date(200 * 1000).toISOString() };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "checkout.session.completed", created: 100,
    data: { object: { client_reference_id: "u1", customer: "cus", payment_status: "unpaid" } } }, deps(s));
  assert.strictEqual(r.action, "stale-checkout");
  assert.strictEqual(s.patches.length, 0, "no write — active payer not downgraded, timestamp not regressed");
});
test("FIND-007: a FRESH checkout (no prior event) still provisions (first event never stale)", async () => {
  const s = fakeSupa(null);
  const r = await applyBilling({ id: "e", type: "checkout.session.completed", created: 100,
    data: { object: { client_reference_id: "u1", customer: "cus", subscription: "sub", payment_status: "paid" } } }, deps(s));
  assert.strictEqual(r.action, "provision");
  assert.strictEqual(s.patches[0].body.paid, true);
});
test("Web tenant checkout cannot fall through to legacy billing when product metadata is absent or wrong", async () => {
  for (const metadata of [undefined, { lm_product: "other_product" }]) {
    const s = fakeSupa(webBillingRow({ paid: false, plan_status: "trialing" }));
    const result = await applyBilling({ id: "evt_checkout_without_web_product", type: "checkout.session.completed", created: 500,
      data: { object: { client_reference_id: WEB_UID, customer: "cus_web", subscription: "sub_new",
        payment_status: "no_payment_required", ...(metadata ? { metadata } : {}) } } }, deps(s));

    assert.equal(result.action, "web-checkout-product-mismatch");
    assert.equal(s.row().paid, false);
    assert.equal(s.row().plan_status, "trialing");
    assert.equal(s.row().stripe_subscription_id, "sub_web");
    assert.equal(s.patches.length, 0);
  }
});
test("pre-Travel Web tenants cannot be activated by metadata-free subscription or invoice events", async () => {
  const s = fakeSupa(webBillingRow({ web_first_travel_at: null, stripe_subscription_id: null,
    paid: false, plan_status: null }));
  const subscription = { id: "evt_early_subscription", type: "customer.subscription.created", created: 100,
    data: { object: { id: "sub_early", customer: "cus_web", status: "active",
      metadata: { lm_uid: WEB_UID } } } };
  const invoice = webInvoiceEvent("evt_early_invoice", "invoice.paid", 101, {
    id: "in_early", subscription: "sub_early",
    parent: { subscription_details: { subscription: "sub_early", metadata: { lm_uid: WEB_UID } } },
  });

  const subscriptionResult = await applyBilling(subscription, deps(s));
  const invoiceResult = await applyBilling(invoice, deps(s));

  assert.equal(subscriptionResult.action, "web-first-travel-required");
  assert.equal(invoiceResult.action, "web-first-travel-required");
  assert.equal(s.patches.length, 0);
  assert.equal(s.row().stripe_subscription_id, null);
  assert.equal(s.row().plan_status, null);
  assert.equal(s.row().paid, false);
});
test("applyBilling subscription active → provision; canceled → deprovision", async () => {
  const row = { uid: "u1", stripe_event_at: new Date(50 * 1000).toISOString() };
  let s = fakeSupa(row);
  let r = await applyBilling({ id: "e", type: "customer.subscription.updated", created: 100,
    data: { object: { id: "sub", customer: "cus", status: "active", current_period_end: 999 } } }, deps(s));
  assert.strictEqual(r.action, "provision"); assert.strictEqual(s.patches[0].body.paid, true);
  s = fakeSupa(row);
  r = await applyBilling({ id: "e", type: "customer.subscription.deleted", created: 100,
    data: { object: { id: "sub", customer: "cus", status: "canceled", current_period_end: 999 } } }, deps(s));
  assert.strictEqual(r.action, "deprovision"); assert.strictEqual(s.patches[0].body.paid, false);
});
test("applyBilling subscription STALE (older created) → no write", async () => {
  const row = { uid: "u1", stripe_event_at: new Date(200 * 1000).toISOString() };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "customer.subscription.updated", created: 100,
    data: { object: { id: "sub", customer: "cus", status: "active", current_period_end: 999 } } }, deps(s));
  assert.strictEqual(r.action, "stale"); assert.strictEqual(s.patches.length, 0);
});
test("applyBilling orphan customer (no row) → no-op, no throw", async () => {
  const s = fakeSupa(null);
  const r = await applyBilling({ id: "e", type: "customer.subscription.updated", created: 100,
    data: { object: { id: "sub", customer: "cus_unknown", status: "active" } } }, deps(s));
  assert.strictEqual(r.action, "orphan-subscription"); assert.strictEqual(s.patches.length, 0);
});
test("Web billing user-store failure throws so the webhook can unclaim and retry", async () => {
  const event = webSubscriptionEvent("evt_db_down", 100, { status: "trialing", trial_end: 900000,
    default_payment_method: "pm_saved" });
  await assert.rejects(applyBilling(event, {
    supaUrl: "http://s", supaKey: "k",
    fetchImpl: async () => ({ ok: false, status: 503, json: async () => ({}) }),
  }), /billing user lookup failed/);
});
test("applyBilling past_due → paid=true (grace) + dunning notify fired once", async () => {
  const row = { uid: "u1", stripe_event_at: new Date(50 * 1000).toISOString() };
  const s = fakeSupa(row); let dunned = [];
  const r = await applyBilling({ id: "e", type: "customer.subscription.updated", created: 100,
    data: { object: { id: "sub", customer: "cus", status: "past_due", current_period_end: 999 } } }, deps(s, (uid) => dunned.push(uid)));
  assert.strictEqual(r.paid, true); assert.strictEqual(s.patches[0].body.plan_status, "past_due");
  assert.deepStrictEqual(dunned, ["u1"]);
});
test("applyBilling Web trial requires a saved payment method and activates automation on created", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", calendar_connected_account_id: "ca-selected-123",
    stripe_event_at: null, paid: false };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "customer.subscription.created", created: 100,
    data: { object: { id: "sub_web", customer: "cus_web", status: "trialing", trial_end: 700000,
      default_payment_method: "pm_saved", metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(r.paid, false);
  assert.equal(s.patches[0].body.stripe_customer_id, "cus_web");
  assert.equal(s.patches[0].body.trial_expires_at, new Date(700000 * 1000).toISOString());
  assert.equal(s.patches[0].body.web_trial_payment_method_present, true);
  assert.equal(s.patches[0].body.web_automation_resume_pending, true);
  assert.match(s.rpcCalls[0].url, /resume_lm_web_billing_automation$/);
  assert.equal(s.row().web_automation_resume_pending, false);
  assert.equal(s.row().paid, false);
  assert.equal(webTravelEntitled(s.row(), 600_000_000), true);
});
test("applyBilling Web trial without a saved payment method stays unpaid", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", calendar_connected_account_id: "ca-selected-123", paid: false };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "customer.subscription.created", created: 100,
    data: { object: { id: "sub_web", customer: "cus_web", status: "trialing", trial_end: 700000,
      metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(r.paid, false);
  assert.equal(s.patches[0].body.paid, false);
  assert.equal(s.rpcCalls.length, 0);
});
test("Web Checkout completion links Stripe ids in pending state without granting entitlement", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_event_at: null, paid: false, plan_status: null };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "checkout.session.completed", created: 100,
    data: { object: { client_reference_id: row.uid, customer: "cus_web", subscription: "sub_web",
      payment_status: "no_payment_required", metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(r.action, "link-web-checkout");
  assert.deepEqual(s.patches[0].body, {
    stripe_customer_id: "cus_web", stripe_subscription_id: "sub_web", paid: false, plan_status: "incomplete",
    web_billing_revision: 1,
  });
});
test("late Web Checkout completion cannot downgrade an already verified trial", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_customer_id: "cus_web",
    stripe_subscription_id: "sub_web", stripe_event_at: new Date(100_000).toISOString(),
    paid: false, plan_status: "trialing", web_trial_payment_method_present: true,
    trial_expires_at: "2030-01-08T00:00:00.000Z" };
  const s = fakeSupa(row);
  await applyBilling({ id: "e", type: "checkout.session.completed", created: 200,
    data: { object: { client_reference_id: row.uid, customer: "cus_web", subscription: "sub_web",
      payment_status: "paid", metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(s.patches[0].body.paid, undefined);
  assert.equal(s.patches[0].body.plan_status, undefined);
});
test("Web subscription active does not grant access until a paid invoice is verified", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_customer_id: "cus_web",
    stripe_subscription_id: "sub_web", stripe_event_at: new Date(50_000).toISOString(), paid: false,
    plan_status: "trialing", web_trial_payment_method_present: true, trial_expires_at: "2030-01-08T00:00:00.000Z" };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "customer.subscription.updated", created: 100,
    data: { object: { id: "sub_web", customer: "cus_web", status: "active", current_period_end: 999,
      latest_invoice: "in_pending",
      metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(r.paid, false);
  assert.equal(s.patches[0].body.paid, false);
});

test("old paid invoice evidence cannot activate a newer active subscription invoice", async () => {
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "active",
    web_subscription_event_at: new Date(200_000).toISOString(),
    web_subscription_event_priority: 70, web_subscription_event_id: "evt_active_latest",
    web_subscription_latest_invoice_id: "in_latest",
    web_invoice_event_at: new Date(100_000).toISOString(), web_invoice_event_priority: 70,
    web_invoice_event_id: "evt_old_paid", web_invoice_id: "in_old",
    web_invoice_subscription_id: "sub_web", web_invoice_paid: true, web_invoice_amount_paid: 2900 }));

  const oldInvoice = await applyBilling(webInvoiceEvent("evt_old_paid_late", "invoice.paid", 300,
    { id: "in_old" }), deps(s));

  assert.equal(oldInvoice.action, "stale-invoice");
  assert.equal(s.row().paid, false);
  assert.equal(s.row().web_invoice_id, "in_old");
  assert.equal(s.row().web_subscription_latest_invoice_id, "in_latest");
});

test("a delayed old invoice cannot regrant an active subscription with a different latest invoice", async () => {
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "active",
    web_subscription_latest_invoice_id: "in_latest",
    web_invoice_event_at: new Date(100_000).toISOString(), web_invoice_event_priority: 70,
    web_invoice_event_id: "evt_previous", web_invoice_id: "in_previous",
    web_invoice_subscription_id: "sub_web", web_invoice_paid: false, web_invoice_amount_paid: 0 }));

  const result = await applyBilling(webInvoiceEvent("evt_old_invoice_paid", "invoice.paid", 200,
    { id: "in_old", amount_paid: 2900 }), deps(s));

  assert.equal(result.action, "stale-invoice");
  assert.equal(s.row().paid, false);
  assert.equal(s.row().web_invoice_paid, false);
  assert.equal(s.row().web_invoice_id, "in_previous");
  assert.equal(s.row().web_subscription_latest_invoice_id, "in_latest");
});

test("a paid current invoice wins over older invoice events with arbitrary IDs and delivery order", async () => {
  const older = webInvoiceEvent("evt_z_old", "invoice.paid", 200, { id: "in_old" });
  const latest = webInvoiceEvent("evt_a_latest", "invoice.paid", 200, { id: "in_latest" });
  const oldAtNextSecond = webInvoiceEvent("evt_z_old_later", "invoice.paid", 201, { id: "in_old" });
  const current = { id: "sub_web", customer: "cus_web", created: 90, status: "active",
    current_period_end: 900000, latest_invoice: "in_latest",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };
  const run = async (events, latestAtStart = "in_latest") => {
    const s = fakeSupa(webBillingRow({ paid: false, plan_status: "active",
      web_subscription_event_at: new Date(100_000).toISOString(),
      web_subscription_event_priority: 70, web_subscription_event_id: "evt_active",
      web_subscription_latest_invoice_id: latestAtStart,
      web_invoice_event_at: new Date(100_000).toISOString(), web_invoice_event_priority: 50,
      web_invoice_event_id: "evt_prior_failed", web_invoice_id: "in_prior",
      web_invoice_subscription_id: "sub_web", web_invoice_paid: false, web_invoice_amount_paid: 0 }));
    const dependencies = { ...deps(s), retrieveSubscription: async () => current };
    for (const event of events) await applyBilling(event, dependencies);
    return s.row();
  };

  for (const events of [[older, latest], [latest, older], [latest, oldAtNextSecond]]) {
    const row = await run(events);
    assert.equal(row.web_subscription_latest_invoice_id, "in_latest");
    assert.equal(row.web_invoice_id, "in_latest");
    assert.equal(row.paid, true);
    assert.equal(webTravelEntitled(row, Date.now()), true);
  }

  const invoiceBeforeSubscription = await run([latest], "in_old");
  assert.equal(invoiceBeforeSubscription.web_subscription_latest_invoice_id, "in_latest");
  assert.equal(invoiceBeforeSubscription.web_invoice_id, "in_latest");
  assert.equal(invoiceBeforeSubscription.paid, true);
});
test("a late event from a prior canceled Web subscription cannot replace the paid restart", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_customer_id: "cus_web",
    stripe_subscription_id: "sub_new", stripe_event_at: new Date(200_000).toISOString(), paid: true, plan_status: "active" };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "customer.subscription.deleted", created: 300,
    data: { object: { id: "sub_old", customer: "cus_web", status: "canceled",
      metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(r.action, "stale-subscription-id");
  assert.equal(s.patches.length, 0);
});
test("Web checkout replacement compares the Stripe subscription creation time", async () => {
  const checkout = (id, subscriptionId, created) => ({ id, type: "checkout.session.completed", created,
    data: { object: { client_reference_id: WEB_UID, customer: "cus_web", subscription: subscriptionId,
      payment_status: "no_payment_required", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } } });
  const current = (subscriptionId, created) => ({ id: subscriptionId, customer: "cus_web", created,
    status: "trialing", trial_end: 900000, default_payment_method: "pm_saved",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } });
  const row = webBillingRow({ stripe_subscription_id: "sub_current", plan_status: "canceled", paid: false,
    web_subscription_created_at: new Date(200_000).toISOString(),
    web_subscription_event_at: new Date(250_000).toISOString(), web_subscription_event_id: "evt_current_cancel" });

  const older = fakeSupa(row);
  let olderReads = 0;
  const stale = await applyBilling(checkout("evt_old_checkout", "sub_old", 400), {
    ...deps(older), retrieveSubscription: async () => { olderReads++; return current("sub_old", 100); },
  });
  assert.equal(stale.action, "stale-web-checkout-subscription");
  assert.equal(olderReads, 1);
  assert.equal(older.row().stripe_subscription_id, "sub_current");
  assert.equal(older.patches.length, 0);

  const newer = fakeSupa(row);
  let newerReads = 0;
  const linked = await applyBilling(checkout("evt_new_checkout", "sub_new", 400), {
    ...deps(newer), retrieveSubscription: async () => { newerReads++; return current("sub_new", 300); },
  });
  assert.equal(linked.action, "link-web-checkout");
  assert.equal(newerReads, 1);
  assert.equal(newer.row().stripe_subscription_id, "sub_new");
  assert.equal(newer.row().plan_status, "incomplete");
});
test("Web trial cancellation request pauses automation before the Stripe trial ends", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_customer_id: "cus_web",
    stripe_subscription_id: "sub_web", stripe_event_at: new Date(50_000).toISOString(), paid: false,
    plan_status: "trialing", web_trial_payment_method_present: true, trial_expires_at: "2030-01-08T00:00:00.000Z" };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "customer.subscription.updated", created: 100,
    data: { object: { id: "sub_web", customer: "cus_web", status: "trialing", trial_end: 700000,
      default_payment_method: "pm_saved", cancel_at_period_end: true,
      metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(r.paid, false);
  assert.equal(s.patches[0].body.paid, false);
  assert.equal(s.rpcCalls.length, 0);
});

test("$0 trial invoice never grants an unbounded subscription, in either webhook order", async () => {
  const trialCreated = (id, created) => ({ id, type: "customer.subscription.created", created,
    data: { object: { id: "sub_web", customer: "cus_web", status: "trialing", trial_end: 700000,
      default_payment_method: "pm_saved", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } } });
  const zeroInvoice = webInvoiceEvent("in_zero", "invoice.paid", 100,
    { amount_paid: 0, amount_due: 0, billing_reason: "subscription_create" });

  const invoiceFirst = fakeSupa(webBillingRow({ plan_status: "incomplete" }));
  const zero = await applyBilling(zeroInvoice, deps(invoiceFirst));
  assert.equal(zero.action, "zero-dollar-invoice");
  assert.equal(invoiceFirst.patches.length, 0);
  const trial = await applyBilling(trialCreated("sub_trial", 90), deps(invoiceFirst));
  assert.equal(trial.paid, false);
  assert.equal(invoiceFirst.row().plan_status, "trialing");
  assert.equal(invoiceFirst.row().paid, false);
  assert.equal(invoiceFirst.row().web_trial_payment_method_present, true);
  assert.equal(webTravelEntitled(invoiceFirst.row(), 600_000_000), true);
  assert.equal(invoiceFirst.row().trial_expires_at, new Date(700000 * 1000).toISOString());

  const trialFirst = fakeSupa(webBillingRow());
  await applyBilling(trialCreated("sub_trial_first", 90), deps(trialFirst));
  await applyBilling(zeroInvoice, deps(trialFirst));
  assert.equal(trialFirst.row().plan_status, "trialing");
  assert.equal(trialFirst.row().paid, false);
  assert.equal(trialFirst.row().web_trial_payment_method_present, true);
  assert.equal(trialFirst.row().trial_expires_at, new Date(700000 * 1000).toISOString());
});

test("paid invoice evidence survives a later-created active subscription event delivered first", async () => {
  const s = fakeSupa(webBillingRow({
    paid: false, plan_status: "trialing", web_trial_payment_method_present: true,
    trial_expires_at: "2030-01-08T00:00:00.000Z",
  }));
  const active = await applyBilling(webSubscriptionEvent("sub_active_later", 101, {
    status: "active", current_period_end: 900000, latest_invoice: "in_invoice_paid_earlier",
  }), deps(s));
  assert.equal(active.paid, false);
  const invoice = await applyBilling(webInvoiceEvent("invoice_paid_earlier", "invoice.paid", 100), deps(s));
  assert.equal(invoice.paid, true);
  assert.equal(s.row().plan_status, "active");
  assert.equal(s.row().paid, true);
  assert.equal(s.row().web_invoice_paid, true);
  assert.equal(s.row().trial_expires_at, null);
});

test("a delayed paid invoice cannot replace a newer past_due subscription state", async () => {
  const pastDueAt = new Date(200_000).toISOString();
  const s = fakeSupa(webBillingRow({
    paid: false, plan_status: "past_due",
    web_subscription_event_at: pastDueAt,
    web_subscription_event_priority: 50,
    web_subscription_event_id: "evt_past_due",
  }));
  const invoice = await applyBilling(webInvoiceEvent("evt_old_paid", "invoice.paid", 100), {
    ...deps(s), retrieveSubscription: async () => ({ id: "sub_web", customer: "cus_web", created: 90,
      status: "past_due", latest_invoice: "in_evt_old_paid",
      metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } }),
  });
  assert.equal(invoice.paid, false);
  assert.equal(s.row().plan_status, "past_due");
  assert.equal(s.row().paid, false);
  assert.equal(s.row().web_invoice_paid, true);
});

test("paid invoice after past_due waits for the active subscription event before resuming", async () => {
  const s = fakeSupa(webBillingRow({
    paid: false, plan_status: "past_due",
    web_subscription_latest_invoice_id: "in_evt_paid_2",
    web_subscription_event_at: new Date(200_000).toISOString(),
    web_subscription_event_priority: 50,
    web_subscription_event_id: "evt_past_due_2",
  }));
  const invoice = await applyBilling(webInvoiceEvent("evt_paid_2", "invoice.paid", 201), {
    ...deps(s), retrieveSubscription: async () => ({ id: "sub_web", customer: "cus_web", created: 90,
      status: "past_due", latest_invoice: "in_evt_paid_2",
      metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } }),
  });
  assert.equal(invoice.paid, false);
  assert.equal(s.row().plan_status, "past_due");
  const active = await applyBilling(webSubscriptionEvent("evt_active_after_payment", 202, {
    status: "active", current_period_end: 900000, latest_invoice: "in_evt_paid_2",
  }), deps(s));
  assert.equal(active.paid, true);
  assert.equal(s.row().plan_status, "active");
  assert.equal(s.row().paid, true);
});

test("same trial webhook retry resumes automation after its billing write already succeeded", async () => {
  const s = fakeSupa(webBillingRow());
  const trialEnd = Math.floor(Date.now() / 1000) + 7 * 24 * 60 * 60;
  const event = {
    id: "evt_trial_resume_retry", type: "customer.subscription.created", created: 100,
    data: { object: { id: "sub_web", customer: "cus_web", status: "trialing", trial_end: trialEnd,
      default_payment_method: "pm_saved",
      metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } },
  };
  let failResume = true;
  const fetchImpl = async (url, init = {}) => {
    if (String(url).includes("/rpc/resume_lm_web_billing_automation") && failResume) {
      failResume = false;
      return { ok: false, status: 503, json: async () => ({ message: "temporary" }) };
    }
    return s.f(url, init);
  };
  await assert.rejects(applyBilling(event, { ...deps(s), fetchImpl }));
  assert.equal(s.row().paid, false);
  assert.equal(s.row().web_trial_payment_method_present, true);
  assert.equal(webTravelEntitled(s.row()), true);
  assert.equal(s.row().plan_status, "trialing");
  assert.equal(s.row().web_automation_resume_pending, true);

  const retried = await applyBilling(event, { ...deps(s), fetchImpl });
  assert.equal(retried.action, "web-automation-resumed");
  assert.equal(s.rpcCalls.length, 1);
  assert.equal(s.row().web_automation_resume_pending, false);
});

test("a delayed first trial-created webhook does not override a pause made after Checkout", async () => {
  const trialEnd = Math.floor(Date.now() / 1000) + 7 * 24 * 60 * 60;
  const s = fakeSupa(webBillingRow({ web_automation_user_paused: true, daily_automation_enabled: false,
    stripe_subscription_id: null, plan_status: "incomplete", paid: false }));
  const event = { id: "evt_first_trial_after_pause", type: "customer.subscription.created", created: 100,
    data: { object: { id: "sub_web", customer: "cus_web", created: 100, status: "trialing", trial_end: trialEnd,
      default_payment_method: "pm_saved", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } } };

  const result = await applyBilling(event, deps(s));

  assert.equal(result.paid, false);
  assert.equal(s.row().web_automation_user_paused, true);
  assert.equal(s.row().web_automation_resume_pending, false);
  assert.equal(s.row().daily_automation_enabled, false);
  assert.equal(s.rpcCalls.length, 0);
  assert.equal(webTravelEntitled(s.row(), Date.now()), true);
});

test("trial access is separate from paid until a positive invoice is verified", async () => {
  const trialEnd = Math.floor(Date.now() / 1000) + 7 * 24 * 60 * 60;
  const s = fakeSupa(webBillingRow());
  const event = { id: "evt_trial_not_paid", type: "customer.subscription.created", created: 100,
    data: { object: { id: "sub_web", customer: "cus_web", created: 100, status: "trialing", trial_end: trialEnd,
      default_payment_method: "pm_saved", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } } };

  await applyBilling(event, deps(s));

  assert.equal(s.row().paid, false);
  assert.equal(s.row().web_trial_payment_method_present, true);
  assert.equal(webTravelEntitled(s.row()), true);
  assert.equal(webTravelEntitled({ ...s.row(), web_trial_payment_method_present: false }), false);
  assert.equal(webTravelEntitled(s.row(), (trialEnd + 1) * 1000), false);
});

test("a later entitled subscription update completes a pending trial activation", async () => {
  const trialEnd = Math.floor(Date.now() / 1000) + 7 * 24 * 60 * 60;
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "trialing", web_trial_payment_method_present: true,
    trial_expires_at: new Date(trialEnd * 1000).toISOString(),
    web_subscription_event_at: new Date(100_000).toISOString(),
    web_subscription_event_priority: 40, web_subscription_event_id: "evt_trial_created",
    web_automation_resume_pending: true }));

  await applyBilling(webSubscriptionEvent("evt_trial_updated", 101, {
    status: "trialing", trial_end: trialEnd, default_payment_method: "pm_saved",
  }), deps(s));

  assert.equal(s.row().web_subscription_event_id, "evt_trial_updated");
  assert.equal(s.row().web_automation_resume_pending, false);
  assert.equal(s.rpcCalls.length, 1);
  assert.match(s.rpcCalls[0].url, /resume_lm_web_billing_automation$/);
});

test("duplicate trial webhook does not undo an explicit user pause after resume completed", async () => {
  const trialEnd = Math.floor(Date.now() / 1000) + 7 * 24 * 60 * 60;
  const eventId = "evt_trial_already_resumed";
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "trialing", web_trial_payment_method_present: true,
    trial_expires_at: new Date(trialEnd * 1000).toISOString(),
    web_subscription_event_at: new Date(100_000).toISOString(),
    web_subscription_event_priority: 40, web_subscription_event_id: eventId,
    web_automation_resume_pending: false }));
  const event = { id: eventId, type: "customer.subscription.created", created: 100,
    data: { object: { id: "sub_web", customer: "cus_web", status: "trialing", trial_end: trialEnd,
      default_payment_method: "pm_saved", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } } };

  const result = await applyBilling(event, deps(s));

  assert.equal(result.action, "stale");
  assert.equal(s.rpcCalls.length, 0);
  assert.equal(s.row().paid, false);
});

test("same-second cancellation and cancellation removal converge to Stripe's current subscription snapshot", async () => {
  const trialEnd = Math.floor(Date.now() / 1000) + 7 * 24 * 60 * 60;
  const snapshot = { id: "sub_web", customer: "cus_web", status: "trialing", created: 90,
    trial_end: trialEnd, default_payment_method: "pm_saved", cancel_at_period_end: false,
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };
  const cancellation = (id, cancelAtPeriodEnd) => webSubscriptionEvent(id, 100, {
    created: 90, status: "trialing", trial_end: trialEnd, default_payment_method: "pm_saved", cancel_at_period_end: cancelAtPeriodEnd,
  });

  for (const events of [
    [cancellation("evt_cancel_first", true), cancellation("evt_uncancel_second", false)],
    [cancellation("evt_uncancel_first", false), cancellation("evt_cancel_second", true)],
  ]) {
    const s = fakeSupa(webBillingRow({ web_subscription_created_at: new Date(90_000).toISOString(),
      web_subscription_event_at: new Date(99_000).toISOString(), web_subscription_event_priority: 40,
      web_subscription_event_id: "evt_prior", plan_status: "trialing", paid: false,
      web_trial_payment_method_present: true }));
    let snapshotReads = 0;
    const dependencies = { ...deps(s), retrieveSubscription: async (subscriptionId) => {
      snapshotReads++;
      assert.equal(subscriptionId, "sub_web");
      return snapshot;
    } };
    await applyBilling(events[0], dependencies);
    await applyBilling(events[1], dependencies);
    assert.equal(s.row().web_billing_cancel_at_period_end, false);
    assert.equal(s.row().paid, false);
    assert.equal(webTravelEntitled(s.row()), true);
    assert.equal(snapshotReads, 1);
  }
});

test("cross-subscription ordering uses Stripe subscription creation time, not event ID order", async () => {
  const row = webBillingRow({ stripe_subscription_id: "sub_old", paid: false, plan_status: "canceled",
    web_billing_cancel_at_period_end: true,
    web_subscription_created_at: new Date(50_000).toISOString(),
    web_subscription_event_at: new Date(100_000).toISOString(),
    web_subscription_event_priority: 100, web_subscription_event_id: "evt_z_old_cancel" });
  const s = fakeSupa(row);
  const created = Math.floor(Date.now() / 1000) + 7 * 24 * 60 * 60;
  const replacement = await applyBilling({ id: "evt_a_new_subscription", type: "customer.subscription.created", created: 100,
    data: { object: { id: "sub_new", customer: "cus_web", created: 100, status: "trialing", trial_end: created,
      default_payment_method: "pm_saved", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(replacement.paid, false);
  assert.equal(s.row().stripe_subscription_id, "sub_new");
  assert.equal(s.row().web_trial_payment_method_present, true);
  assert.equal(webTravelEntitled(s.row()), true);

  const lateOld = await applyBilling({ id: "evt_z_late_old_subscription", type: "customer.subscription.deleted", created: 300,
    data: { object: { id: "sub_old", customer: "cus_web", created: 50, status: "canceled",
      metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(lateOld.action, "stale-subscription-id");
  assert.equal(s.row().stripe_subscription_id, "sub_new");
  assert.equal(s.row().paid, false);
});

test("invoice payment after scheduled cancellation keeps Calendar entitlement paused", async () => {
  const s = fakeSupa(webBillingRow({
    paid: false, plan_status: "trialing", web_trial_payment_method_present: true,
    trial_expires_at: "2030-01-08T00:00:00.000Z",
  }));
  await applyBilling(webSubscriptionEvent("scheduled_cancel", 100, {
    status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
    cancel_at_period_end: true,
  }), deps(s));
  const invoice = await applyBilling(webInvoiceEvent("invoice_after_cancel", "invoice.paid", 101), {
    ...deps(s), retrieveSubscription: async () => ({ id: "sub_web", customer: "cus_web", created: 90,
      status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
      cancel_at_period_end: true, latest_invoice: "in_invoice_after_cancel",
      metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } }),
  });
  assert.equal(invoice.paid, false);
  assert.equal(s.row().web_billing_cancel_at_period_end, true);
  assert.equal(s.row().web_invoice_paid, true);
  assert.equal(s.row().paid, false);
});

test("active subscription cannot reuse paid evidence for a different latest invoice", async () => {
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "past_due",
    web_subscription_event_at: new Date(100_000).toISOString(),
    web_subscription_event_priority: 60, web_subscription_event_id: "evt_past_due_old_invoice",
    web_subscription_latest_invoice_id: "in_old",
    web_invoice_event_at: new Date(100_000).toISOString(), web_invoice_id: "in_old",
    web_invoice_subscription_id: "sub_web", web_invoice_paid: true, web_invoice_amount_paid: 2900 }));

  const active = await applyBilling(webSubscriptionEvent("evt_active_new_invoice", 200, {
    status: "active", current_period_end: 900000, latest_invoice: "in_new",
  }), deps(s));

  assert.equal(active.paid, false);
  assert.equal(s.row().paid, false);
  assert.equal(s.row().plan_status, "active");
  assert.equal(s.row().web_invoice_id, "in_old");
});

test("late invoice on a fully canceled subscription preserves immediate paid-restart eligibility", async () => {
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "canceled",
    web_billing_cancel_at_period_end: true }));
  await applyBilling(webInvoiceEvent("evt_late_after_cancel", "invoice.paid", 101), deps(s));
  assert.equal(s.row().plan_status, "canceled");
  assert.equal(s.row().paid, false);
  assert.equal(s.row().web_billing_cancel_at_period_end, true);
  assert.equal(webPaidCheckoutEligible(s.row()), true);
});

test("same-second cancellation wins over a paid invoice in either delivery order", async () => {
  const cancel = webSubscriptionEvent("evt_cancel_same_second", 100, {
    status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
    cancel_at_period_end: true,
  });
  const invoice = webInvoiceEvent("evt_invoice_same_second", "invoice.paid", 100);
  for (const events of [[invoice, cancel], [cancel, invoice]]) {
    const s = fakeSupa(webBillingRow({ paid: false, plan_status: "trialing", web_trial_payment_method_present: true }));
    for (const event of events) await applyBilling(event, deps(s));
    assert.equal(s.row().web_billing_cancel_at_period_end, true);
    assert.equal(s.row().paid, false);
  }
});

test("same-second invoice recovery uses a stable event-ID tie-breaker in either delivery order", async () => {
  const failed = webInvoiceEvent("evt_a_failed", "invoice.payment_failed", 100);
  const paid = webInvoiceEvent("evt_z_paid", "invoice.paid", 100);
  for (const events of [[failed, paid], [paid, failed]]) {
    const s = fakeSupa(webBillingRow({ paid: false, plan_status: "active",
      web_subscription_latest_invoice_id: "in_evt_z_paid" }));
    for (const event of events) await applyBilling(event, deps(s));
    assert.equal(s.row().web_invoice_paid, true);
    assert.equal(s.row().paid, true);
  }
});

test("same-second subscription recovery reconciles to the current Stripe status in either delivery order", async () => {
  const pastDue = webSubscriptionEvent("evt_a_past_due", 100, { status: "past_due", latest_invoice: "in_same_second" });
  const active = webSubscriptionEvent("evt_z_active", 100, {
    status: "active", current_period_end: 900000, latest_invoice: "in_same_second",
  });
  const current = { id: "sub_web", customer: "cus_web", created: 90,
    status: "active", current_period_end: 900000, latest_invoice: "in_same_second",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };
  for (const events of [[pastDue, active], [active, pastDue]]) {
    const s = fakeSupa(webBillingRow({ paid: false, plan_status: "past_due",
      web_invoice_event_at: new Date(100_000).toISOString(),
      web_invoice_id: "in_same_second", web_invoice_subscription_id: "sub_web", web_invoice_paid: true,
      web_invoice_amount_paid: 2900,
      web_subscription_latest_invoice_id: "in_same_second" }));
    for (const event of events) await applyBilling(event, { ...deps(s), retrieveSubscription: async () => current });
    assert.equal(s.row().plan_status, "active");
    assert.equal(s.row().paid, true);
  }
});

test("same-second latest-invoice changes reconcile to Stripe even when the new event ID sorts older", async () => {
  const old = webSubscriptionEvent("evt_z_old_invoice", 100, {
    created: 90, status: "active", latest_invoice: "in_old", current_period_end: 900000,
  });
  const newer = webSubscriptionEvent("evt_a_new_invoice", 100, {
    created: 90, status: "active", latest_invoice: "in_new", current_period_end: 900000,
  });
  const current = { id: "sub_web", customer: "cus_web", created: 90,
    status: "active", current_period_end: 900000, latest_invoice: "in_new",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };

  for (const events of [[newer, old], [old, newer]]) {
    const s = fakeSupa(webBillingRow({ paid: true, plan_status: "active",
      web_subscription_created_at: new Date(90_000).toISOString(),
      web_subscription_event_at: new Date(100_000).toISOString(),
      web_subscription_event_priority: 70, web_subscription_event_id: "evt_z_prior",
      web_subscription_latest_invoice_id: "in_old",
      web_invoice_event_at: new Date(99_000).toISOString(), web_invoice_id: "in_old",
      web_invoice_subscription_id: "sub_web", web_invoice_paid: true, web_invoice_amount_paid: 2900 }));
    let reads = 0;
    const dependencies = { ...deps(s), retrieveSubscription: async () => { reads++; return current; } };
    for (const event of events) await applyBilling(event, dependencies);
    assert.equal(s.row().web_subscription_latest_invoice_id, "in_new");
    assert.equal(s.row().paid, false);
    assert.equal(reads > 0, true);
  }
});

test("a same-second Stripe past_due snapshot overrides the paid-invoice stale-event shortcut", async () => {
  const s = fakeSupa(webBillingRow({ paid: true, plan_status: "active",
    web_subscription_event_at: new Date(100_000).toISOString(),
    web_subscription_event_priority: 70, web_subscription_event_id: "evt_active",
    web_subscription_latest_invoice_id: "in_current",
    web_invoice_event_at: new Date(100_000).toISOString(), web_invoice_event_priority: 70,
    web_invoice_event_id: "evt_invoice_paid", web_invoice_id: "in_current",
    web_invoice_subscription_id: "sub_web", web_invoice_paid: true, web_invoice_amount_paid: 2900 }));
  let snapshotReads = 0;
  const current = { id: "sub_web", customer: "cus_web", created: 90,
    status: "past_due", latest_invoice: "in_current",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };

  await applyBilling(webSubscriptionEvent("evt_past_due_current", 100, {
    status: "past_due", latest_invoice: "in_current",
  }), { ...deps(s), retrieveSubscription: async () => { snapshotReads++; return current; } });

  assert.equal(snapshotReads, 1);
  assert.equal(s.row().plan_status, "past_due");
  assert.equal(s.row().paid, false);
});

test("same-second trial-end shortening converges to Stripe's current expiry", async () => {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const currentTrialEnd = nowSeconds + 2 * 24 * 60 * 60;
  const staleTrialEnd = nowSeconds + 7 * 24 * 60 * 60;
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "trialing",
    web_trial_payment_method_present: true,
    trial_expires_at: new Date(currentTrialEnd * 1000).toISOString(),
    web_subscription_created_at: new Date(90_000).toISOString(),
    web_subscription_event_at: new Date(100_000).toISOString(),
    web_subscription_event_priority: 40, web_subscription_event_id: "evt_z_long_trial",
  }));
  let reads = 0;
  const current = { id: "sub_web", customer: "cus_web", created: 90,
    status: "trialing", trial_end: currentTrialEnd, default_payment_method: "pm_saved",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };
  const result = await applyBilling(webSubscriptionEvent("evt_a_stale_long_trial", 100, {
    created: 90, status: "trialing", trial_end: staleTrialEnd, default_payment_method: "pm_saved",
  }), { ...deps(s), retrieveSubscription: async () => { reads++; return current; } });

  assert.equal(result.paid, false);
  assert.equal(s.row().trial_expires_at, new Date(currentTrialEnd * 1000).toISOString());
  assert.equal(webTravelEntitled(s.row(), currentTrialEnd * 1000 - 1000), true);
  assert.equal(webTravelEntitled(s.row(), (currentTrialEnd + 1) * 1000), false);
  assert.equal(reads, 1);
});

test("same-second active status waits safely for the paid invoice delivered one second later", async () => {
  const pastDue = webSubscriptionEvent("evt_a_past_due_delayed_invoice", 100, {
    status: "past_due", latest_invoice: "in_delayed_recovery",
  });
  const active = webSubscriptionEvent("evt_z_active_delayed_invoice", 100, {
    status: "active", current_period_end: 900000, latest_invoice: "in_delayed_recovery",
  });
  const invoice = webInvoiceEvent("evt_delayed_recovery_paid", "invoice.paid", 101,
    { id: "in_delayed_recovery" });
  const current = { id: "sub_web", customer: "cus_web", created: 90,
    status: "active", current_period_end: 900000, latest_invoice: "in_delayed_recovery",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };
  for (const events of [[pastDue, active], [active, pastDue]]) {
    const s = fakeSupa(webBillingRow({ paid: false, plan_status: "past_due",
      web_subscription_event_at: new Date(99_000).toISOString(), web_subscription_event_id: "evt_before" }));
    for (const event of events) await applyBilling(event, { ...deps(s), retrieveSubscription: async () => current });
    assert.equal(s.row().plan_status, "active");
    assert.equal(s.row().paid, false, "active status alone is not payment evidence");
    await applyBilling(invoice, deps(s));
    assert.equal(s.row().paid, true);
  }
});

test("same-second paid invoice and past_due update preserve the confirmed recovery in either order", async () => {
  const invoice = webInvoiceEvent("evt_paid_recovery", "invoice.paid", 100, { id: "in_recovery" });
  const pastDue = webSubscriptionEvent("evt_past_due_recovery", 100, {
    status: "past_due", latest_invoice: "in_recovery",
  });

  const pastDueFirst = fakeSupa(webBillingRow({ paid: false, plan_status: "past_due",
    web_subscription_event_at: new Date(99_000).toISOString(), web_subscription_event_id: "evt_prior",
    web_subscription_latest_invoice_id: "in_recovery" }));
  const activeSnapshot = { id: "sub_web", customer: "cus_web", created: 90, status: "active",
    current_period_end: 900000, latest_invoice: "in_recovery",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };
  const withActiveSnapshot = (s) => ({ ...deps(s), retrieveSubscription: async () => activeSnapshot });
  await applyBilling(pastDue, withActiveSnapshot(pastDueFirst));
  await applyBilling(invoice, withActiveSnapshot(pastDueFirst));
  assert.equal(pastDueFirst.row().plan_status, "active");
  assert.equal(pastDueFirst.row().paid, true);

  const invoiceFirst = fakeSupa(webBillingRow({ paid: false, plan_status: "active",
    web_subscription_event_at: new Date(99_000).toISOString(), web_subscription_event_id: "evt_prior",
    web_subscription_latest_invoice_id: "in_recovery" }));
  await applyBilling(invoice, withActiveSnapshot(invoiceFirst));
  const recovered = await applyBilling(pastDue, withActiveSnapshot(invoiceFirst));
  assert.equal(recovered.paid, true);
  assert.equal(invoiceFirst.row().plan_status, "active");
  assert.equal(invoiceFirst.row().paid, true);
});

test("same-second paid invoice recovery requires Stripe to confirm an active subscription", async () => {
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "past_due",
    web_subscription_event_at: new Date(100_000).toISOString(), web_subscription_latest_invoice_id: "in_recovery" }));
  let reads = 0;
  const current = { id: "sub_web", customer: "cus_web", created: 90, status: "past_due",
    latest_invoice: "in_recovery", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };

  const result = await applyBilling(webInvoiceEvent("evt_paid_recovery", "invoice.paid", 100,
    { id: "in_recovery" }), { ...deps(s), retrieveSubscription: async () => { reads++; return current; } });

  assert.equal(reads, 1);
  assert.equal(result.paid, false);
  assert.equal(s.row().plan_status, "past_due");
  assert.equal(s.row().paid, false);
  assert.equal(s.row().web_invoice_paid, true);
});

test("same-second invoice recovery does not activate a non-current invoice", async () => {
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "past_due",
    web_subscription_event_at: new Date(100_000).toISOString(), web_subscription_latest_invoice_id: "in_recovery" }));
  const current = { id: "sub_web", customer: "cus_web", created: 90, status: "active",
    latest_invoice: "in_later", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };

  const result = await applyBilling(webInvoiceEvent("evt_paid_recovery", "invoice.paid", 100,
    { id: "in_recovery" }), { ...deps(s), retrieveSubscription: async () => current });

  assert.equal(result.action, "stale-invoice");
  assert.equal(s.patches.length, 0);
  assert.equal(s.row().plan_status, "past_due");
  assert.equal(s.row().paid, false);
  assert.equal(s.row().web_invoice_paid, undefined);
});

test("invoice recovery readback failure leaves billing entitlement unchanged for retry", async () => {
  const row = webBillingRow({ paid: false, plan_status: "past_due",
    web_subscription_event_at: new Date(100_000).toISOString(), web_subscription_latest_invoice_id: "in_recovery" });
  const s = fakeSupa(row);

  await assert.rejects(applyBilling(webInvoiceEvent("evt_paid_recovery", "invoice.paid", 100,
    { id: "in_recovery" }), { ...deps(s), retrieveSubscription: async () => { throw new Error("offline"); } }),
  /Stripe readback failed/);

  assert.equal(s.patches.length, 0);
  assert.equal(s.row().plan_status, "past_due");
  assert.equal(s.row().paid, false);
});

test("paid invoice at trial expiry does not convert until Stripe reports active", async () => {
  const trialEnd = new Date(200_000).toISOString();
  const s = fakeSupa(webBillingRow({ paid: false, plan_status: "trialing",
    trial_expires_at: trialEnd, web_trial_payment_method_present: true,
    web_subscription_latest_invoice_id: "in_trial_end" }));
  let reads = 0;
  const current = { id: "sub_web", customer: "cus_web", created: 90, status: "trialing",
    trial_end: 200, default_payment_method: "pm_saved", latest_invoice: "in_trial_end",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };

  const result = await applyBilling(webInvoiceEvent("evt_trial_end_paid", "invoice.paid", 200,
    { id: "in_trial_end" }), { ...deps(s), retrieveSubscription: async () => { reads++; return current; } });

  assert.equal(reads, 1);
  assert.equal(result.paid, false);
  assert.equal(s.row().plan_status, "trialing");
  assert.equal(s.row().trial_expires_at, trialEnd);
  assert.equal(s.row().web_trial_payment_method_present, true);
  assert.equal(s.row().paid, false);
});

test("same-second paid invoice suppression checks Stripe before ignoring past_due", async () => {
  const s = fakeSupa(webBillingRow({ paid: true, plan_status: "active",
    web_subscription_event_at: new Date(99_000).toISOString(),
    web_subscription_latest_invoice_id: "in_current",
    web_invoice_event_at: new Date(100_000).toISOString(), web_invoice_id: "in_current",
    web_invoice_subscription_id: "sub_web", web_invoice_paid: true, web_invoice_amount_paid: 2900 }));
  let reads = 0;
  const current = { id: "sub_web", customer: "cus_web", created: 90, status: "past_due",
    latest_invoice: "in_current", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } };

  const result = await applyBilling(webSubscriptionEvent("evt_past_due_after_paid", 100,
    { status: "past_due", latest_invoice: "in_current" }), {
    ...deps(s), retrieveSubscription: async () => { reads++; return current; },
  });

  assert.equal(reads, 1);
  assert.equal(result.paid, false);
  assert.equal(s.row().plan_status, "past_due");
  assert.equal(s.row().paid, false);
});

test("competing Web subscription writes re-read revisions and cannot restore access after cancellation", async () => {
  const s = fakeSupa(webBillingRow());
  const trial = webSubscriptionEvent("evt_trial_race", 100, {
    status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
  });
  const cancel = webSubscriptionEvent("evt_cancel_race", 101, {
    status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
    cancel_at_period_end: true,
  });
  const dependencies = { ...deps(s), retrieveSubscription: async () => ({
    id: "sub_web", customer: "cus_web", created: 90, status: "trialing", trial_end: 700000,
    default_payment_method: "pm_saved", cancel_at_period_end: true,
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" },
  }) };
  const raced = await Promise.allSettled([
    applyBilling(trial, dependencies),
    applyBilling(cancel, dependencies),
  ]);
  assert.ok(raced.every((result) => result.status === "fulfilled"), "one failed CAS is re-read and re-evaluated");
  await applyBilling(cancel, dependencies);
  await applyBilling(trial, dependencies);
  assert.equal(s.row().web_billing_cancel_at_period_end, true);
  assert.equal(s.row().paid, false);
  assert.equal(s.row().plan_status, "trialing");
});

test("Web billing CAS re-reads tenant and Calendar bindings changed without a revision", async () => {
  const event = webSubscriptionEvent("evt_trial_binding_race", 100, {
    status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
  });
  const telegramBound = fakeSupa(webBillingRow());
  let telegramMutation = false;
  const telegramFetch = async (url, options = {}) => {
    if (options.method === "PATCH" && url.includes("web_billing_revision") && !telegramMutation) {
      telegramBound.row().telegram_chat_id = "chat-1";
      telegramMutation = true;
    }
    return telegramBound.f(url, options);
  };
  const tenantResult = await applyBilling(event, { ...deps(telegramBound), fetchImpl: telegramFetch });
  assert.equal(telegramMutation, true);
  assert.equal(tenantResult.action, "web-tenant-mismatch");
  assert.equal(telegramBound.row().telegram_chat_id, "chat-1");
  assert.equal(telegramBound.row().web_subscription_event_id, undefined);
  assert.equal(telegramBound.row().web_automation_resume_pending, false);
  assert.equal(telegramBound.rpcCalls.length, 0);

  const rebound = fakeSupa(webBillingRow());
  let calendarMutation = false;
  const calendarFetch = async (url, options = {}) => {
    if (options.method === "PATCH" && url.includes("web_billing_revision") && !calendarMutation) {
      rebound.row().calendar_connected_account_id = "ca-new-account";
      calendarMutation = true;
    }
    return rebound.f(url, options);
  };
  await applyBilling(event, { ...deps(rebound), fetchImpl: calendarFetch });
  assert.equal(calendarMutation, true);
  assert.equal(rebound.row().calendar_connected_account_id, "ca-new-account");
  assert.equal(rebound.row().web_subscription_event_id, "evt_trial_binding_race");
  assert.deepEqual(rebound.rpcCalls.map((call) => call.body.p_calendar_account_id), ["ca-new-account"]);
});
test("Web invoice payment evidence pauses or resumes without rewriting Stripe subscription status", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_customer_id: "cus_web",
    stripe_subscription_id: "sub_web", stripe_event_at: new Date(50_000).toISOString(), paid: true,
    plan_status: "active", web_subscription_latest_invoice_id: "in_paid" };
  const paidStore = fakeSupa(row);
  const paid = await applyBilling({ id: "paid", type: "invoice.paid", created: 100,
    data: { object: { id: "in_paid", customer: "cus_web", subscription: "sub_web", status: "paid",
      amount_paid: 2900, amount_due: 2900, billing_reason: "subscription_cycle" } } }, deps(paidStore));
  assert.equal(paid.paid, true);
  assert.equal(paidStore.patches[0].body.plan_status, undefined);

  const failedStore = fakeSupa(row);
  const failed = await applyBilling({ id: "failed", type: "invoice.payment_failed", created: 100,
    data: { object: { customer: "cus_web", parent: { subscription_details: { subscription: "sub_web" } } } } }, deps(failedStore));
  assert.equal(failed.paid, false);
  assert.equal(failedStore.patches[0].body.paid, false);
  assert.equal(failedStore.patches[0].body.plan_status, undefined);
  assert.equal(failedStore.patches[0].body.web_invoice_paid, false);
});
test("paid invoice can link a no-trial restart, then the active subscription confirms access", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", calendar_connected_account_id: "ca-selected-123", stripe_customer_id: "cus_web",
    stripe_subscription_id: "sub_canceled", stripe_event_at: new Date(50_000).toISOString(),
    paid: false, plan_status: "canceled" };
  const s = fakeSupa(row);
  const active = await applyBilling({ id: "subscription-active", type: "customer.subscription.created", created: 100,
    data: { object: { id: "sub_restarted", customer: "cus_web", created: 100, status: "active", current_period_end: 900000,
      latest_invoice: "in_invoice-paid",
      metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(active.paid, false);
  assert.equal(s.row().stripe_subscription_id, "sub_restarted");
  const invoice = await applyBilling({ id: "invoice-paid", type: "invoice.paid", created: 101,
    data: { object: { id: "in_invoice-paid", customer: "cus_web", parent: { subscription_details: {
      subscription: "sub_restarted", metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" },
    } }, status: "paid", amount_paid: 2900, amount_due: 2900, billing_reason: "subscription_create" } } }, deps(s));
  assert.equal(invoice.action, "invoice-paid");
  assert.equal(invoice.paid, true);
  assert.equal(s.row().plan_status, "active");
  assert.equal(s.row().paid, true);
});

test("new subscription invoice waits for the new subscription event, then ignores the prior invoice cursor", async () => {
  const row = webBillingRow({ stripe_subscription_id: "sub_old", plan_status: "canceled", paid: false,
    web_subscription_event_at: new Date(100_000).toISOString(),
    web_subscription_event_priority: 60, web_subscription_event_id: "evt_old_cancel",
    web_invoice_event_at: new Date(300_000).toISOString(),
    web_invoice_event_priority: 60, web_invoice_event_id: "evt_old_late_invoice",
    web_invoice_subscription_id: "sub_old", web_invoice_paid: false });
  const s = fakeSupa(row);
  const invoice = webInvoiceEvent("evt_new_invoice", "invoice.paid", 201, {
    id: "in_evt_new_invoice", subscription: "sub_new", parent: { subscription_details: {
      subscription: "sub_new", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" },
    } },
  });
  await assert.rejects(applyBilling(invoice, deps(s)), /subscription link/i);
  assert.equal(s.row().stripe_subscription_id, "sub_old");
  assert.equal(s.row().paid, false);

  const linked = await applyBilling({ id: "evt_new_subscription", type: "customer.subscription.created", created: 200,
    data: { object: { id: "sub_new", customer: "cus_web", created: 200, status: "active", current_period_end: 900000,
      latest_invoice: "in_evt_new_invoice",
      metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(linked.paid, false);
  assert.equal(s.row().stripe_subscription_id, "sub_new");
  assert.equal(s.row().web_invoice_event_at, null);

  const retriedInvoice = await applyBilling(invoice, deps(s));
  assert.equal(retriedInvoice.paid, true);
  assert.equal(s.row().web_invoice_subscription_id, "sub_new");
  assert.equal(s.row().paid, true);
});

test("an older subscription event cannot replace the current canceled subscription", async () => {
  const s = fakeSupa(webBillingRow({ stripe_subscription_id: "sub_current", plan_status: "canceled", paid: false,
    web_subscription_event_at: new Date(300_000).toISOString(),
    web_subscription_event_priority: 60, web_subscription_event_id: "evt_current_cancel" }));
  const old = await applyBilling({ id: "evt_old_subscription", type: "customer.subscription.created", created: 200,
    data: { object: { id: "sub_old", customer: "cus_web", status: "trialing", trial_end: 900000,
      default_payment_method: "pm_old", metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(old.action, "stale-subscription-id");
  assert.equal(s.row().stripe_subscription_id, "sub_current");
  assert.equal(s.row().plan_status, "canceled");
  assert.equal(s.row().paid, false);
});
test("applyBilling unknown event type → ignored, no write", async () => {
  const s = fakeSupa(null);
  const r = await applyBilling({ id: "e", type: "invoice.created", data: { object: {} } }, deps(s));
  assert.strictEqual(r.action, "ignored"); assert.strictEqual(s.patches.length, 0);
});
test("applyBilling patch failure → throws (handler 500s + unclaims)", async () => {
  const failSupa = { f: async (url, opts) => (opts && opts.method === "PATCH" ? { status: 500 } : { ok: true, json: async () => [{ uid: "u1" }] }) };
  await assert.rejects(applyBilling({ id: "e", type: "checkout.session.completed", created: 100,
    data: { object: { client_reference_id: "u1", customer: "cus", payment_status: "paid" } } },
    { supaUrl: "http://s", supaKey: "k", fetchImpl: failSupa.f }));
});
