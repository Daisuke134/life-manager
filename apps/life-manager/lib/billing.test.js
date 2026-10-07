"use strict";
// HARD-3 billing lifecycle — unit tests. Source of truth = Stripe subscription.status; ordering = event.created.
// Run: node --test lib/billing.test.js
const { test } = require("node:test");
const assert = require("node:assert");
const {
  entitlementFor, parseStripeEvent, isStale, toEpoch,
  claimEvent, unclaimEvent, applyBilling,
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
    data: { object: { customer: "cus_web", subscription: "sub_web", status: "paid", billing_reason: "subscription_cycle",
      amount_paid: 2900, amount_due: 2900 } } });
  const failed = parseStripeEvent({ id: "e2", type: "invoice.payment_failed", created: 1700000020,
    data: { object: { customer: "cus_web", parent: { subscription_details: { subscription: "sub_web" } },
      amount_paid: 0, amount_due: 2900 } } });
  assert.deepStrictEqual([paid.kind, paid.status, paid.subscriptionId], ["invoice", "paid", "sub_web"]);
  assert.deepStrictEqual([failed.kind, failed.status, failed.subscriptionId], ["invoice", "payment_failed", "sub_web"]);
  assert.deepStrictEqual([paid.eventId, paid.amountPaid, paid.amountDue, paid.billingReason],
    ["e1", 2900, 2900, "subscription_cycle"]);
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
      rpcCalls.push({ url, body: JSON.parse(opts.body) });
      return { ok: true, json: async () => true };
    }
    if (!method && url.includes("select=")) // a GET lookup (userByCustomer or userByUid)
      return { ok: true, json: async () => (state ? [{ ...state, web_billing_revision: Number(state.web_billing_revision || 0) }] : []) };
    if (method === "PATCH" && url.includes("lm_users?uid=eq.")) {
      const patch = JSON.parse(opts.body);
      patches.push({ url, body: patch });
      const parsed = new URL(url);
      if (parsed.searchParams.has("web_billing_revision")) {
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
const deps = (supa, notify) => ({ supaUrl: "http://s", supaKey: "k", fetchImpl: supa.f, notify });
const WEB_UID = "lm_11111111-1111-4111-8111-111111111111";
const webBillingRow = (overrides = {}) => ({
  uid: WEB_UID, telegram_chat_id: null,
  web_first_travel_at: "2030-01-01T00:00:00.000Z",
  calendar_connected_account_id: "ca-selected-123",
  stripe_customer_id: "cus_web", stripe_subscription_id: "sub_web",
  web_billing_revision: 0, paid: false, plan_status: "trialing",
  ...overrides,
});
const webSubscriptionEvent = (id, created, object) => ({
  id, type: "customer.subscription.updated", created,
  data: { object: { id: "sub_web", customer: "cus_web",
    metadata: { lm_uid: WEB_UID, lm_product: "life_manager_web_travel" }, ...object } },
});
const webInvoiceEvent = (id, type, created, object = {}) => ({
  id, type, created,
  data: { object: { customer: "cus_web", subscription: "sub_web", status: "paid",
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
  assert.equal(r.paid, true);
  assert.equal(s.patches[0].body.stripe_customer_id, "cus_web");
  assert.equal(s.patches[0].body.trial_expires_at, new Date(700000 * 1000).toISOString());
  assert.equal(s.rpcCalls[0].body.p_action, "resume");
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
    paid: true, plan_status: "trialing" };
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
    stripe_subscription_id: "sub_web", stripe_event_at: new Date(50_000).toISOString(), paid: false, plan_status: "trialing" };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "customer.subscription.updated", created: 100,
    data: { object: { id: "sub_web", customer: "cus_web", status: "active", current_period_end: 999,
      metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" } } } }, deps(s));
  assert.equal(r.paid, false);
  assert.equal(s.patches[0].body.paid, false);
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
test("Web trial cancellation request pauses automation before the Stripe trial ends", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_customer_id: "cus_web",
    stripe_subscription_id: "sub_web", stripe_event_at: new Date(50_000).toISOString(), paid: true, plan_status: "trialing" };
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
  assert.equal(trial.paid, true);
  assert.equal(invoiceFirst.row().plan_status, "trialing");
  assert.equal(invoiceFirst.row().paid, true);
  assert.equal(invoiceFirst.row().trial_expires_at, new Date(700000 * 1000).toISOString());

  const trialFirst = fakeSupa(webBillingRow());
  await applyBilling(trialCreated("sub_trial_first", 90), deps(trialFirst));
  await applyBilling(zeroInvoice, deps(trialFirst));
  assert.equal(trialFirst.row().plan_status, "trialing");
  assert.equal(trialFirst.row().paid, true);
  assert.equal(trialFirst.row().trial_expires_at, new Date(700000 * 1000).toISOString());
});

test("paid invoice evidence survives a later-created active subscription event delivered first", async () => {
  const s = fakeSupa(webBillingRow({
    paid: true, plan_status: "trialing", trial_expires_at: "2030-01-08T00:00:00.000Z",
  }));
  const active = await applyBilling(webSubscriptionEvent("sub_active_later", 101, {
    status: "active", current_period_end: 900000,
  }), deps(s));
  assert.equal(active.paid, false);
  const invoice = await applyBilling(webInvoiceEvent("invoice_paid_earlier", "invoice.paid", 100), deps(s));
  assert.equal(invoice.paid, true);
  assert.equal(s.row().plan_status, "active");
  assert.equal(s.row().paid, true);
  assert.equal(s.row().web_invoice_paid, true);
  assert.equal(s.row().trial_expires_at, null);
});

test("invoice payment after scheduled cancellation keeps Calendar entitlement paused", async () => {
  const s = fakeSupa(webBillingRow({
    paid: true, plan_status: "trialing", trial_expires_at: "2030-01-08T00:00:00.000Z",
  }));
  await applyBilling(webSubscriptionEvent("scheduled_cancel", 100, {
    status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
    cancel_at_period_end: true,
  }), deps(s));
  const invoice = await applyBilling(webInvoiceEvent("invoice_after_cancel", "invoice.paid", 101), deps(s));
  assert.equal(invoice.paid, false);
  assert.equal(s.row().web_billing_cancel_at_period_end, true);
  assert.equal(s.row().web_invoice_paid, true);
  assert.equal(s.row().paid, false);
});

test("same-second cancellation wins over a paid invoice in either delivery order", async () => {
  const cancel = webSubscriptionEvent("evt_cancel_same_second", 100, {
    status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
    cancel_at_period_end: true,
  });
  const invoice = webInvoiceEvent("evt_invoice_same_second", "invoice.paid", 100);
  for (const events of [[invoice, cancel], [cancel, invoice]]) {
    const s = fakeSupa(webBillingRow({ paid: true, plan_status: "trialing" }));
    for (const event of events) await applyBilling(event, deps(s));
    assert.equal(s.row().web_billing_cancel_at_period_end, true);
    assert.equal(s.row().paid, false);
  }
});

test("competing Web subscription writes use atomic revision CAS and cannot restore access after cancellation", async () => {
  const s = fakeSupa(webBillingRow());
  const trial = webSubscriptionEvent("evt_trial_race", 100, {
    status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
  });
  const cancel = webSubscriptionEvent("evt_cancel_race", 101, {
    status: "trialing", trial_end: 700000, default_payment_method: "pm_saved",
    cancel_at_period_end: true,
  });
  const raced = await Promise.allSettled([
    applyBilling(trial, deps(s)),
    applyBilling(cancel, deps(s)),
  ]);
  assert.ok(raced.some((result) => result.status === "rejected"), "losing CAS must cause Stripe retry");
  await applyBilling(cancel, deps(s));
  await applyBilling(trial, deps(s));
  assert.equal(s.row().web_billing_cancel_at_period_end, true);
  assert.equal(s.row().paid, false);
  assert.equal(s.row().plan_status, "trialing");
});
test("applyBilling Web paid invoice activates while failed invoice pauses immediately", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_customer_id: "cus_web",
    stripe_subscription_id: "sub_web", stripe_event_at: new Date(50_000).toISOString(), paid: true, plan_status: "active" };
  const paidStore = fakeSupa(row);
  const paid = await applyBilling({ id: "paid", type: "invoice.paid", created: 100,
    data: { object: { customer: "cus_web", subscription: "sub_web", status: "paid",
      amount_paid: 2900, amount_due: 2900, billing_reason: "subscription_cycle" } } }, deps(paidStore));
  assert.equal(paid.paid, true);
  assert.equal(paidStore.patches[0].body.plan_status, "active");

  const failedStore = fakeSupa(row);
  const failed = await applyBilling({ id: "failed", type: "invoice.payment_failed", created: 100,
    data: { object: { customer: "cus_web", parent: { subscription_details: { subscription: "sub_web" } } } } }, deps(failedStore));
  assert.equal(failed.paid, false);
  assert.equal(failedStore.patches[0].body.paid, false);
  assert.equal(failedStore.patches[0].body.plan_status, "past_due");
});
test("paid invoice can link a new no-trial subscription after the prior Web subscription was canceled", async () => {
  const row = { uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_customer_id: "cus_web",
    stripe_subscription_id: "sub_canceled", stripe_event_at: new Date(50_000).toISOString(),
    paid: false, plan_status: "canceled" };
  const s = fakeSupa(row);
  const r = await applyBilling({ id: "e", type: "invoice.paid", created: 100,
    data: { object: { customer: "cus_web", parent: { subscription_details: {
      subscription: "sub_restarted", metadata: { lm_uid: row.uid, lm_product: "life_manager_web_travel" },
    } }, status: "paid", amount_paid: 2900, amount_due: 2900, billing_reason: "subscription_create" } } }, deps(s));
  assert.equal(r.action, "invoice-paid");
  assert.equal(s.patches[0].body.stripe_subscription_id, "sub_restarted");
  assert.equal(s.patches[0].body.paid, true);
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
