// lib/transport/calendar-composio.js — CLOUD calendar transport (#74 convergence). Wraps the Composio
// managed-OAuth GOOGLECALENDAR_* tools behind the adapter interface every life-logic module will use,
// so the same JS runs cloud (this) or local (calendar-gog.js, slice 5). Behaviour-identical to the
// inline Composio calls it replaces — the live caller is unchanged.
"use strict";
const { recordCost } = require("../ledger.js");
const { runtimeTrace, usageRuntimeEnv } = require("../usage-event.js");

const COMPOSIO_EXEC = "https://backend.composio.dev/api/v3/tools/execute";

async function selectedAccountId(uid, apiKey, opts = {}) {
  if (opts.expectedCalendarAccountId != null) {
    const expected = String(opts.expectedCalendarAccountId);
    const base = String(opts.supaUrl || process.env.SUPABASE_URL || "").replace(/\/$/, "");
    const key = opts.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!base || !key || !/^[A-Za-z0-9_-]{3,128}$/.test(expected)) {
      throw new Error("calendar account binding changed");
    }
    const url = new URL(`${base}/rest/v1/lm_users`);
    url.searchParams.set("uid", `eq.${uid}`);
    url.searchParams.set("telegram_chat_id", "is.null");
    url.searchParams.set("select", "uid,telegram_chat_id,calendar_provider,calendar_connected_account_id");
    url.searchParams.set("limit", "2");
    const response = await (opts.fetchImpl || fetch)(url.toString(), {
      headers: { apikey: key, Authorization: `Bearer ${key}` },
    });
    if (!response.ok) throw new Error("calendar account lookup failed");
    const rows = await response.json();
    const row = Array.isArray(rows) && rows.length === 1 ? rows[0] : null;
    if (!row || row.uid !== uid || row.telegram_chat_id !== null
      || row.calendar_provider !== "composio_gcal"
      || row.calendar_connected_account_id !== expected) {
      throw new Error("calendar account binding changed");
    }
    return expected;
  }
  if (typeof opts.resolveConnectedAccountId === "function") return opts.resolveConnectedAccountId(uid);
  const base = opts.supaUrl || process.env.SUPABASE_URL;
  const key = opts.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!base || !key) return null;
  const r = await (opts.fetchImpl || fetch)(`${base}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}&select=calendar_connected_account_id&limit=1`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
  });
  if (!r.ok) throw new Error("calendar account lookup failed");
  const rows = await r.json();
  const selected = Array.isArray(rows) && rows[0] ? rows[0].calendar_connected_account_id || null : null;
  if (selected) return selected;
  const accountsResponse = await (opts.fetchImpl || fetch)(`https://backend.composio.dev/api/v3/connected_accounts?user_ids=${encodeURIComponent(uid)}&toolkit_slugs=googlecalendar`, { headers: { "x-api-key": apiKey } });
  if (!accountsResponse.ok) throw new Error("calendar account lookup failed");
  const accountsBody = await accountsResponse.json();
  const active = (Array.isArray(accountsBody.items) ? accountsBody.items : []).filter((item) => item && String(item.user_id || item.userId || item.connection?.user_id) === String(uid)
    && String(item.toolkit_slug || item.toolkit?.slug || item.toolkit?.slug_name) === "googlecalendar"
    && item.status === "ACTIVE" && item.is_disabled !== true && (item.enabled === undefined || item.enabled === true));
  if (active.length !== 1 || !active[0].id) throw new Error("calendar account is not uniquely bound");
  const saved = await (opts.fetchImpl || fetch)(`${base}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}&calendar_connected_account_id=is.null`, {
    method: "PATCH",
    headers: { apikey: key, Authorization: `Bearer ${key}`, "content-type": "application/json", Prefer: "return=minimal" },
    body: JSON.stringify({ calendar_connected_account_id: active[0].id }),
  });
  if (!saved.ok) throw new Error("calendar account backfill failed");
  const readback = await (opts.fetchImpl || fetch)(`${base}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}&select=calendar_connected_account_id&limit=1`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
  });
  const readbackRows = readback.ok ? await readback.json() : [];
  if (!Array.isArray(readbackRows) || readbackRows[0]?.calendar_connected_account_id !== active[0].id) throw new Error("calendar account backfill conflict");
  return active[0].id;
}

async function exec(tool, uid, args, apiKey, opts, recordOutcome, effectAwareCreate = false) {
  let connectedAccountId;
  try { connectedAccountId = await selectedAccountId(uid, apiKey, opts); }
  catch (error) {
    if (effectAwareCreate) return { effect: "no_effect", result: { successful: false } };
    throw error;
  }
  let result;
  let response;
  try {
    response = await (opts.fetchImpl || fetch)(`${COMPOSIO_EXEC}/${tool}`, {
      method: "POST",
      headers: { "x-api-key": apiKey, "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: uid, ...(connectedAccountId ? { connected_account_id: connectedAccountId } : {}), arguments: args }),
    });
  } catch (error) {
    await recordOutcome("unknown");
    if (effectAwareCreate) return { effect: "unknown", result: { successful: false } };
    throw error;
  }
  const status = Number.isInteger(response?.status) ? response.status : null;
  if (effectAwareCreate && status !== null && status >= 400 && status < 500) {
    await recordOutcome("failure");
    return { effect: "no_effect", result: { successful: false } };
  }
  if (effectAwareCreate && status !== null && (status < 200 || status >= 300)) {
    await recordOutcome("unknown");
    return { effect: "unknown", result: { successful: false } };
  }
  try { result = await response.json(); }
  catch (error) {
    await recordOutcome("unknown");
    if (effectAwareCreate) return { effect: "unknown", result: { successful: false } };
    throw error;
  }
  if (effectAwareCreate) {
    const effect = result && result.successful === true ? "created" : "unknown";
    await recordOutcome(effect === "created" ? "success" : "unknown");
    return { effect, result };
  }
  await recordOutcome(result && result.successful === true ? "success"
    : result && result.successful === false ? "failure" : "unknown");
  return result;
}

function makeComposioCalendar(opts = {}) {
  const { apiKey, recordCall } = opts;
  const key = apiKey || process.env.COMPOSIO_API_KEY;
  const ledger = recordCall || ((uid, tool, details) => {
    if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) return false;
    const { outcome, runtimeTrace: trace } = details || {};
    return recordCost({
      uid, kind: "composio_call", quantity: 1, unit: "call", estUsd: 0,
      meta: { tool, outcome, runtime_trace: trace },
    });
  });
  const execute = async (tool, uid, args, expectedCalendarAccountId = opts.expectedCalendarAccountId, effectAwareCreate = false) => {
    const operationOpts = expectedCalendarAccountId == null ? opts : { ...opts, expectedCalendarAccountId };
    const runtimeEnv = usageRuntimeEnv(opts.runtimeEnv || process.env, { fallbackOwnerId: "life-call-calendar" });
    const trace = runtimeTrace({ tenantId: uid }, runtimeEnv);
    const recordOutcome = async (outcome) => {
      try { await ledger(uid, tool, { outcome, runtimeTrace: trace }); } catch { /* observability must not break calendar calls */ }
    };
    return exec(tool, uid, args, key, operationOpts, recordOutcome, effectAwareCreate);
  };
  const withCreateEffect = ({ effect, result }) => {
    const value = result && typeof result === "object" ? result : { successful: false };
    Object.defineProperty(value, "effect", { value: effect, configurable: true });
    return value;
  };
  // ONE page of Google Calendar items PLUS the cursor that unlocks the next. events.list returns at
  // most `maxResults` items per page (250 by default, 2500 max) and sets data.nextPageToken whenever
  // more remain — measured against this exact endpoint on 2026-07-26: a 548-day window came back as
  // 250 + 250 + 203 with a live token on the first two pages, and the identical 703 events arrive in
  // one call at maxResults=2500 with NO token. listEventsRaw used to drop that token on the floor,
  // which left "the calendar holds 703 events" and "it holds 7000 and you were handed page one"
  // indistinguishable to every caller. A caller that persists an append-only record
  // (fetchCalendarHistory → lm_care_scan_log) cannot live with that ambiguity, so the cursor is now
  // part of the transport contract.
  // Error contract unchanged and shared with listEventsRaw: default (wake path) swallows every
  // failure to an empty page — load-bearing, a transport blip must not crash the 60s tick — while
  // strict (history path) THROWS, because "empty calendar" and "the read failed" must never merge.
  const listEventsPage = async (uid, { timeMin, timeMax, maxResults, pageToken, strict, expectedCalendarAccountId } = {}) => {
    const empty = { items: [], nextPageToken: null };
    if (!key || !uid) {
      if (strict) throw new Error(`calendar transport not ready (missing ${key ? "uid" : "API key"})`);
      return empty;
    }
    const args = { calendarId: "primary", singleEvents: true, orderBy: "startTime", timeMin, timeMax };
    if (maxResults) args.maxResults = maxResults;
    if (pageToken) args.pageToken = pageToken;
    let j;
    try {
      j = await execute("GOOGLECALENDAR_EVENTS_LIST", uid, args, expectedCalendarAccountId);
    } catch (e) {
      if (strict) throw e;
      return empty;
    }
    if (!j || !j.successful) {
      if (strict) throw new Error(`calendar list failed: ${String((j && (j.error || j.message)) || "unsuccessful response")}`);
      return empty;
    }
    const d = j.data || {};
    return {
      items: d.items || d.events || [],
      nextPageToken: typeof d.nextPageToken === "string" && d.nextPageToken ? d.nextPageToken : null,
    };
  };
  return {
    kind: "composio",
    ready: () => !!key,
    listEventsPage,
    // Raw Google Calendar items (each consumer maps to its own shape) for [timeMin, timeMax] (ISO Z),
    // FIRST page only — the wake path reads an 18-hour horizon and has never approached a page
    // boundary. Callers that need provable completeness follow listEventsPage's cursor instead.
    async listEventsRaw(uid, opts = {}) {
      return (await listEventsPage(uid, opts)).items;
    },
    async createEvent(uid, args, operationOpts = {}) {
      if (!key) return withCreateEffect({ effect: "no_effect", result: { successful: false } });
      try {
        return withCreateEffect(await execute("GOOGLECALENDAR_CREATE_EVENT", uid, args,
          operationOpts.expectedCalendarAccountId, true));
      } catch { return withCreateEffect({ effect: "unknown", result: { successful: false } }); }
    },
    async patchEvent(uid, args, operationOpts = {}) {
      if (!key) return { successful: false };
      try { return await execute("GOOGLECALENDAR_PATCH_EVENT", uid, args, operationOpts.expectedCalendarAccountId); } catch { return { successful: false }; }
    },
  };
}

module.exports = { makeComposioCalendar };
