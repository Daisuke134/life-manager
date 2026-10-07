"use strict";
const { webTravelEntitled } = require("./billing.js");

// spec §5.2.1 — the phone is OPT-IN. Measured, it reached a human 3 times against 17 voicemails, and
// Telegram is what actually pushes someone out the door, so a user who has expressed no preference
// gets no call. Only `call_enabled` flipped: notifications and the daily automation are how the
// product now reaches everyone (§5.3), and they keep their opt-OUT semantics.
//
// A default alone cannot enforce this — a preference row that exists for some OTHER setting returns
// call_enabled as SQL NULL, which spreads straight over this object. Consumers must test `=== true`,
// never `!== false`. See scheduler.js wakeTick / wakeCallOnce.
const DEFAULTS = Object.freeze({ call_enabled: false, notifications_enabled: true, daily_automation_enabled: true });
const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const WEB_CLAIM_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function resolveSupabaseServiceConfig(opts = {}) {
  const supaUrl = String(opts.supaUrl || process.env.SUPABASE_URL || "").replace(/\/$/, "");
  const supaKey = opts.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  return supaUrl && supaKey ? { supaUrl, supaKey } : null;
}

async function readRuntimePreferences(uid, opts = {}) {
  if (!uid || !opts.supaUrl || !opts.supaKey) return null;
  const response = await (opts.fetchImpl || fetch)(`${String(opts.supaUrl).replace(/\/$/, "")}/rest/v1/lm_panel_preferences?uid=eq.${encodeURIComponent(uid)}&select=call_enabled,notifications_enabled,daily_automation_enabled&limit=1`, {
    headers: { apikey: opts.supaKey, Authorization: `Bearer ${opts.supaKey}` },
  }).catch(() => null);
  if (!response || !response.ok) return null;
  const rows = await response.json().catch(() => null);
  if (!Array.isArray(rows)) return null;
  return { ...DEFAULTS, ...(rows[0] || {}) };
}

async function readWebTravelControlState(uid, opts = {}) {
  const config = resolveSupabaseServiceConfig(opts);
  if (!WEB_UID_RE.test(String(uid || "")) || !config) return null;
  const base = config.supaUrl;
  const headers = { apikey: config.supaKey, Authorization: `Bearer ${config.supaKey}` };
  const fetchImpl = opts.fetchImpl || fetch;
  const userUrl = new URL(`${base}/rest/v1/lm_users`);
  userUrl.searchParams.set("uid", `eq.${uid}`);
  userUrl.searchParams.set("telegram_chat_id", "is.null");
  userUrl.searchParams.set("select", "uid,telegram_chat_id,calendar_provider,calendar_connected_account_id,calendar_enable_pending,calendar_enable_claim_id,calendar_enable_claimed_at,web_initial_scan_completed_at,web_first_travel_at,stripe_subscription_id,trial_expires_at,plan_status,paid,web_billing_cancel_at_period_end");
  userUrl.searchParams.set("limit", "2");
  const userResponse = await fetchImpl(userUrl.toString(), { headers }).catch(() => null);
  if (!userResponse || !userResponse.ok) return null;
  const users = await userResponse.json().catch(() => null);
  if (!Array.isArray(users) || users.length !== 1
    || users[0].uid !== uid || users[0].telegram_chat_id !== null
    || typeof users[0].calendar_enable_pending !== "boolean") return null;
  const enableClaim = users[0].calendar_enable_pending
    ? {
      enableClaimId: users[0].calendar_enable_claim_id,
      enableClaimedAt: users[0].calendar_enable_claimed_at,
    }
    : {};
  if (users[0].calendar_enable_pending
    && (typeof enableClaim.enableClaimId !== "string" || !WEB_CLAIM_ID_RE.test(enableClaim.enableClaimId)
      || typeof enableClaim.enableClaimedAt !== "string" || !Number.isFinite(Date.parse(enableClaim.enableClaimedAt)))) return null;

  const preferenceUrl = new URL(`${base}/rest/v1/lm_panel_preferences`);
  preferenceUrl.searchParams.set("uid", `eq.${uid}`);
  preferenceUrl.searchParams.set("select", "daily_automation_enabled,calendar_disconnect_pending");
  preferenceUrl.searchParams.set("limit", "2");
  const preferenceResponse = await fetchImpl(preferenceUrl.toString(), { headers }).catch(() => null);
  if (!preferenceResponse || !preferenceResponse.ok) return null;
  const preferences = await preferenceResponse.json().catch(() => null);
  if (!Array.isArray(preferences)) return null;
  if (preferences.length === 0) {
    const user = users[0];
    return {
      dailyAutomationEnabled: null,
      disconnectPending: false,
      enablePending: user.calendar_enable_pending,
      initialScanAllowed: false,
      billingEntitled: user.web_billing_cancel_at_period_end !== true
        && webTravelEntitled(user, opts.nowMs == null ? Date.now() : opts.nowMs),
      ...enableClaim,
    };
  }
  if (preferences.length !== 1
    || typeof preferences[0].daily_automation_enabled !== "boolean"
    || typeof preferences[0].calendar_disconnect_pending !== "boolean") return null;
  const user = users[0];
  const preference = preferences[0];
  const billingEntitled = user.web_billing_cancel_at_period_end !== true
    && webTravelEntitled(user, opts.nowMs == null ? Date.now() : opts.nowMs);
  const initialScanAllowed = Boolean(opts.expectedCalendarAccountId
    && user.calendar_provider === "composio_gcal"
    && user.calendar_connected_account_id === opts.expectedCalendarAccountId
    && !user.web_first_travel_at
    && !user.stripe_subscription_id
    && !user.trial_expires_at
    && !user.plan_status
    && user.paid !== true
    && preference.daily_automation_enabled === false
    && preference.calendar_disconnect_pending === false
    && user.calendar_enable_pending === false);
  return {
    dailyAutomationEnabled: preference.daily_automation_enabled,
    disconnectPending: preference.calendar_disconnect_pending,
    enablePending: user.calendar_enable_pending,
    initialScanAllowed,
    billingEntitled,
    ...enableClaim,
  };
}

module.exports = { DEFAULTS, readRuntimePreferences, readWebTravelControlState, resolveSupabaseServiceConfig };
