#!/usr/bin/env node
"use strict";

const Stripe = require("stripe");
const { buildWebFunnelReport } = require("../lib/web-funnel-report.js");

const PAGE_SIZE = 1000;
const UID_BATCH_SIZE = 80;

function config(env = process.env) {
  const supaUrl = String(env.SUPABASE_URL || "").replace(/\/$/, "");
  const supaKey = String(env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  const stripeKey = String(env.STRIPE_SECRET_KEY || "").trim();
  let parsedUrl;
  try { parsedUrl = new URL(supaUrl); } catch { parsedUrl = null; }
  if (!parsedUrl || parsedUrl.protocol !== "https:" || parsedUrl.username || parsedUrl.password || !supaKey) {
    throw new Error("web funnel report Supabase configuration unavailable");
  }
  if (!/^(?:sk|rk)_live_/.test(stripeKey)) throw new Error("web funnel report requires live Stripe read credentials");
  return { supaUrl, supaKey, stripeKey };
}

async function getRows(table, filters, { supaUrl, supaKey, fetchImpl = fetch }) {
  const rows = [];
  for (let start = 0; start < 100000; start += PAGE_SIZE) {
    const url = new URL(`${supaUrl}/rest/v1/${table}`);
    for (const [key, value] of Object.entries(filters)) url.searchParams.set(key, value);
    const response = await fetchImpl(url.toString(), {
      headers: {
        apikey: supaKey,
        Authorization: `Bearer ${supaKey}`,
        Range: `${start}-${start + PAGE_SIZE - 1}`,
        "Range-Unit": "items",
      },
    });
    if (!response || !response.ok) throw new Error("web funnel report data read failed");
    const page = await response.json().catch(() => null);
    if (!Array.isArray(page)) throw new Error("web funnel report data response invalid");
    rows.push(...page);
    if (page.length < PAGE_SIZE) return rows;
  }
  throw new Error("web funnel report row cap exceeded");
}

async function stripePages(list, params) {
  const rows = [];
  let cursor = null;
  for (let pageIndex = 0; pageIndex < 100; pageIndex++) {
    const page = await list({ ...params, ...(cursor ? { starting_after: cursor } : {}) });
    if (!page || !Array.isArray(page.data)) throw new Error("Stripe report response invalid");
    rows.push(...page.data);
    if (!page.has_more) return rows;
    if (!page.data.length || !page.data.at(-1).id) throw new Error("Stripe report cursor unavailable");
    cursor = page.data.at(-1).id;
  }
  throw new Error("Stripe report page cap exceeded");
}

async function stripeFeeRows(stripe, usersByCustomer, startSec) {
  const rows = [];
  let complete = true;
  if (!usersByCustomer.size) return { rows, complete };
  let transactions;
  try {
    transactions = await stripePages(stripe.balanceTransactions.list.bind(stripe.balanceTransactions), {
      created: { gte: startSec }, limit: 100, expand: ["data.source"],
    });
  } catch {
    return { rows, complete: false };
  }
  for (const transaction of transactions) {
    if (!["charge", "refund"].includes(transaction.type)) continue;
    let source = transaction.source && typeof transaction.source === "object" ? transaction.source : null;
    const sourceId = typeof transaction.source === "string" ? transaction.source : transaction.source && transaction.source.id;
    if (!source && sourceId) {
      try {
        source = transaction.type === "refund" && sourceId.startsWith("re_")
          ? await stripe.refunds.retrieve(sourceId)
          : await stripe.charges.retrieve(sourceId.startsWith("ch_") ? sourceId : "");
      } catch {
        complete = false;
        continue;
      }
    }
    const customerValue = source && source.customer;
    const customerId = typeof customerValue === "string" ? customerValue : customerValue && customerValue.id;
    const uid = customerId && usersByCustomer.get(customerId);
    if (!uid) continue;
    rows.push({
      uid,
      fee: transaction.fee,
      currency: transaction.currency,
      status: transaction.status,
      created: new Date(Number(transaction.created) * 1000).toISOString(),
    });
  }
  return { rows, complete };
}

async function runWebFunnelReport({ env = process.env, fetchImpl = fetch, stripeClient, nowMs = Date.now(), periodDays = 30 } = {}) {
  const settings = config(env);
  const stripe = stripeClient || new Stripe(settings.stripeKey);
  const startIso = new Date(nowMs - periodDays * 86400000).toISOString();
  const users = await getRows("lm_users", {
    select: "uid,telegram_chat_id,web_first_touch,web_first_travel_at,web_initial_scan_completed_at,plan_status,paid,trial_expires_at,web_billing_cancel_at_period_end,stripe_customer_id,stripe_subscription_id",
    telegram_chat_id: "is.null",
  }, { ...settings, fetchImpl });
  const events = await getRows("lm_web_funnel_events", {
    select: "event_id,event_name,uid,source_object_id,source_event_id,attribution,amount_usd,currency,billing_reason,occurred_at",
    occurred_at: `gte.${startIso}`,
    order: "occurred_at.asc",
  }, { ...settings, fetchImpl });
  const uids = users.map((user) => user.uid).filter((uid) => /^lm_[0-9a-f-]{36}$/i.test(String(uid || "")));
  const providerCosts = [];
  for (let i = 0; i < uids.length; i += UID_BATCH_SIZE) {
    const chunk = uids.slice(i, i + UID_BATCH_SIZE);
    providerCosts.push(...await getRows("lm_api_cost", {
      select: "uid,kind,ts,est_usd,meta",
      kind: "eq.provider_usage",
      uid: `in.(${chunk.join(",")})`,
      ts: `gte.${startIso}`,
    }, { ...settings, fetchImpl }));
  }
  const subscriptions = await stripePages(stripe.subscriptions.list.bind(stripe.subscriptions), {
    status: "all", limit: 100,
  });
  const usersByCustomer = new Map(users
    .filter((user) => user.stripe_customer_id)
    .map((user) => [String(user.stripe_customer_id), String(user.uid)]));
  const feeResult = await stripeFeeRows(stripe, usersByCustomer, Math.floor((nowMs - periodDays * 86400000) / 1000));
  return buildWebFunnelReport({
    events, users, providerCosts, subscriptions, balanceTransactions: feeResult.rows,
    stripeFeesComplete: feeResult.complete, nowMs, periodDays,
  });
}

if (require.main === module) {
  runWebFunnelReport().then((report) => {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  }).catch(() => {
    process.stderr.write("Life Manager Web funnel report failed at a provider read boundary.\n");
    process.exitCode = 1;
  });
}

module.exports = { config, getRows, runWebFunnelReport, stripeFeeRows, stripePages };
