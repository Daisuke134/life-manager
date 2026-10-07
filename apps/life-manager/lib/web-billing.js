"use strict";

const crypto = require("node:crypto");
const { resolveWebUser } = require("./web-auth.js");
const { webTrialEligible, webPaidCheckoutEligible, resumeWebAutomation } = require("./billing.js");

const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CHECKOUT_PATH = "/api/lm-web/checkout";
const PORTAL_PATH = "/api/lm-web/billing/portal";
const TRIAL_SECONDS = 7 * 24 * 60 * 60;
const BILLING_FIELDS = [
  "uid", "telegram_chat_id", "calendar_provider", "calendar_connected_account_id",
  "calendar_enable_pending", "web_initial_scan_completed_at", "web_first_travel_at",
  "stripe_customer_id", "stripe_subscription_id", "trial_expires_at", "plan_status", "paid",
].join(",");

function webError(status, code) {
  const error = new Error(code);
  error.status = status;
  error.code = code;
  return error;
}

function envFor(opts = {}) {
  return opts.env && typeof opts.env === "object" ? opts.env : process.env;
}

function serviceHeaders(key, extra = {}) {
  return { apikey: key, Authorization: `Bearer ${key}`, ...extra };
}

function appOrigin(opts = {}) {
  const env = envFor(opts);
  let url;
  try { url = new URL(String(opts.publicOrigin || env.LM_PANEL_BASE || "")); }
  catch { throw webError(503, "billing_origin_unavailable"); }
  if (url.username || url.password || url.pathname !== "/" || url.search || url.hash
    || !["https:", ...(env.NODE_ENV === "test" ? ["http:"] : [])].includes(url.protocol)) {
    throw webError(503, "billing_origin_unavailable");
  }
  return url.origin;
}

async function readWebBillingUser(uid, opts = {}) {
  if (!WEB_UID_RE.test(String(uid || ""))) throw webError(401, "unauthorized");
  const root = String(opts.supaUrl || envFor(opts).SUPABASE_URL || "").replace(/\/$/, "");
  const key = String(opts.supaKey || envFor(opts).SUPABASE_SERVICE_ROLE_KEY || "").trim();
  if (!root || !key) throw webError(503, "billing_unavailable");
  const url = new URL(`${root}/rest/v1/lm_users`);
  url.searchParams.set("uid", `eq.${uid}`);
  url.searchParams.set("telegram_chat_id", "is.null");
  url.searchParams.set("select", BILLING_FIELDS);
  url.searchParams.set("limit", "2");
  const response = await (opts.fetchImpl || fetch)(url.toString(), { headers: serviceHeaders(key) });
  if (!response || !response.ok) throw webError(502, "billing_user_read_failed");
  const rows = await response.json().catch(() => null);
  if (!Array.isArray(rows) || rows.length !== 1 || rows[0].uid !== uid || rows[0].telegram_chat_id !== null) {
    throw webError(403, "unauthorized");
  }
  return rows[0];
}

function stripeFor(opts = {}) {
  const stripe = opts.stripeClient || opts.stripe;
  if (!stripe) throw webError(503, "billing_unavailable");
  return stripe;
}

async function assertExistingMonthlyPrice(stripe, opts = {}) {
  const env = envFor(opts);
  const priceId = String(opts.priceId || env.LM_STRIPE_PRICE_ID || "").trim();
  if (!/^price_[A-Za-z0-9]+$/.test(priceId)) throw webError(503, "billing_price_unavailable");
  let price;
  try { price = await stripe.prices.retrieve(priceId); }
  catch { throw webError(503, "billing_price_unavailable"); }
  const key = String(env.STRIPE_SECRET_KEY || "").trim();
  const liveKey = key.startsWith("sk_live_") || key.startsWith("rk_live_");
  const testKey = key.startsWith("sk_test_") || key.startsWith("rk_test_");
  if (!price || price.id !== priceId || price.active !== true || price.currency !== "usd"
    || price.unit_amount !== 2900 || !price.recurring || price.recurring.interval !== "month"
    || liveKey && price.livemode !== true || testKey && price.livemode !== false) {
    throw webError(503, "billing_price_unavailable");
  }
  return priceId;
}

async function requireActiveCalendar(uid, row, opts = {}) {
  const accountId = String(row.calendar_connected_account_id || "");
  if (row.calendar_provider !== "composio_gcal" || !/^[A-Za-z0-9_-]{3,128}$/.test(accountId)
    || row.calendar_enable_pending === true) throw webError(409, "calendar_not_active");
  let status;
  try {
    const check = opts.calendarAccountStatusImpl
      || require("./panel-api.js").composioCalendarAccountStatus;
    status = await check({ uid }, accountId, {
      composioKey: opts.composioKey || envFor(opts).COMPOSIO_API_KEY,
      composioAuthConfig: opts.composioAuthConfig || envFor(opts).COMPOSIO_GCAL_AUTH_CONFIG,
      fetchImpl: opts.fetchImpl || opts.fetch,
      signal: opts.signal,
    });
  } catch {
    throw webError(502, "calendar_status_unavailable");
  }
  if (status !== "ACTIVE") throw webError(409, "calendar_not_active");
}

function validStripeUrl(value, host) {
  try {
    const url = new URL(String(value || ""));
    return url.protocol === "https:" && url.hostname === host && !url.username && !url.password
      ? url.toString() : "";
  } catch {
    return "";
  }
}

async function createWebCheckoutSession(uid, user, opts = {}) {
  if (!WEB_UID_RE.test(String(uid || "")) || !user || user.uid !== uid) throw webError(401, "unauthorized");
  const row = await readWebBillingUser(uid, opts);
  const trialEligible = webTrialEligible(row);
  if (!row.web_initial_scan_completed_at || !row.web_first_travel_at
    || !trialEligible && !webPaidCheckoutEligible(row)) {
    throw webError(409, "trial_unavailable");
  }
  await requireActiveCalendar(uid, row, opts);
  const stripe = stripeFor(opts);
  const priceId = await assertExistingMonthlyPrice(stripe, opts);
  const origin = appOrigin(opts);
  const nowMs = opts.nowMs == null ? Date.now() : Number(opts.nowMs);
  if (!Number.isFinite(nowMs)) throw webError(503, "billing_unavailable");
  const trialEnd = trialEligible ? Math.floor(nowMs / 1000) + TRIAL_SECONDS : null;
  const metadata = { lm_uid: uid, lm_product: "life_manager_web_travel" };
  const subscriptionData = { metadata };
  if (trialEligible) subscriptionData.trial_period_days = 7;
  const params = {
    mode: "subscription",
    line_items: [{ price: priceId, quantity: 1 }],
    payment_method_collection: "always",
    client_reference_id: uid,
    metadata,
    subscription_data: subscriptionData,
    success_url: `${origin}/lm?checkout=success&session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${origin}/lm?checkout=cancelled`,
  };
  if (row.stripe_customer_id) params.customer = row.stripe_customer_id;
  const digest = crypto.createHash("sha256").update(`${uid}:${row.web_first_travel_at}:${priceId}:${trialEligible ? "trial" : "paid"}:${row.stripe_subscription_id || ""}`).digest("hex").slice(0, 40);
  let session;
  try { session = await stripe.checkout.sessions.create(params, { idempotencyKey: `lm-web-trial-${digest}` }); }
  catch { throw webError(502, "checkout_unavailable"); }
  const url = validStripeUrl(session && session.url, "checkout.stripe.com");
  if (!url) throw webError(502, "checkout_unavailable");
  const supaUrl = String(opts.supaUrl || envFor(opts).SUPABASE_URL || "").replace(/\/$/, "");
  const supaKey = String(opts.supaKey || envFor(opts).SUPABASE_SERVICE_ROLE_KEY || "").trim();
  if (!await resumeWebAutomation(uid, row, supaUrl, supaKey, opts.fetchImpl)) {
    throw webError(502, "billing_unavailable");
  }
  return { url, trialEnd, trialEligible };
}

async function createCustomerPortalSession(uid, user, opts = {}) {
  if (!WEB_UID_RE.test(String(uid || "")) || !user || user.uid !== uid) throw webError(401, "unauthorized");
  const row = await readWebBillingUser(uid, opts);
  if (!row.stripe_customer_id) throw webError(409, "billing_portal_unavailable");
  const stripe = stripeFor(opts);
  let session;
  try {
    session = await stripe.billingPortal.sessions.create({
      customer: row.stripe_customer_id,
      return_url: `${appOrigin(opts)}/lm`,
    });
  } catch {
    throw webError(502, "billing_portal_unavailable");
  }
  const url = validStripeUrl(session && session.url, "billing.stripe.com");
  if (!url) throw webError(502, "billing_portal_unavailable");
  return { url };
}

function sendJson(res, status, body, headers = {}) {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    ...headers,
  });
  res.end(JSON.stringify(body));
}

function csrfMatches(req, user) {
  const supplied = String(req.headers && req.headers["x-lm-web-csrf"] || "");
  const expected = String(user && user.csrf || "");
  if (!supplied || !expected) return false;
  const left = Buffer.from(supplied);
  const right = Buffer.from(expected);
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

async function handleWebBillingRequest(req, res, opts = {}) {
  let pathname;
  try { pathname = new URL(String(req.url || "/"), "https://life-manager.invalid").pathname; }
  catch { return sendJson(res, 400, { error: "invalid_request" }); }
  if (pathname !== CHECKOUT_PATH && pathname !== PORTAL_PATH) return sendJson(res, 404, { error: "not_found" });
  if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" }, { allow: "POST" });
  let user;
  try { user = await (opts.resolveWebUserImpl || resolveWebUser)(req, res, opts); } catch {}
  if (!user || !WEB_UID_RE.test(String(user.uid || ""))) return sendJson(res, 401, { error: "unauthorized" });
  let origin;
  try { origin = new URL(appOrigin(opts)).origin; } catch { return sendJson(res, 503, { error: "billing_unavailable" }); }
  if (String(req.headers && req.headers.origin || "") !== origin) return sendJson(res, 403, { error: "origin_rejected" });
  if (!/^application\/json(?:\s*;|\s*$)/i.test(String(req.headers && req.headers["content-type"] || ""))) {
    return sendJson(res, 415, { error: "json_required" });
  }
  if (!csrfMatches(req, user)) return sendJson(res, 403, { error: "csrf_rejected" });
  let body;
  try { body = await (opts.readJsonImpl || require("./panel-api.js").readJson)(req); }
  catch { return sendJson(res, 400, { error: "invalid_json" }); }
  if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).length !== 0) {
    return sendJson(res, 400, { error: "invalid_request" });
  }
  try {
    const result = pathname === CHECKOUT_PATH
      ? await createWebCheckoutSession(user.uid, user, opts)
      : await createCustomerPortalSession(user.uid, user, opts);
    return sendJson(res, 200, result);
  } catch (error) {
    const status = Number.isInteger(error && error.status) ? error.status : 502;
    const code = status < 500 ? error.code : pathname === CHECKOUT_PATH ? "checkout_unavailable" : "billing_portal_unavailable";
    return sendJson(res, status, { error: code });
  }
}

function trialEndFor(nowMs = Date.now()) {
  const value = Number(nowMs);
  return Number.isFinite(value) ? Math.floor(value / 1000) + TRIAL_SECONDS : null;
}

module.exports = {
  CHECKOUT_PATH,
  PORTAL_PATH,
  createWebCheckoutSession,
  createCustomerPortalSession,
  handleWebBillingRequest,
  readWebBillingUser,
  trialEndFor,
};
