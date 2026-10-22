// lib/transport/calendar-composio.js — CLOUD calendar transport (#74 convergence). Wraps the Composio
// managed-OAuth GOOGLECALENDAR_* tools behind the adapter interface every life-logic module will use,
// so the same JS runs cloud (this) or local (calendar-gog.js, slice 5). Behaviour-identical to the
// inline Composio calls it replaces — the live caller is unchanged.
"use strict";
const { createHash } = require("node:crypto");
const { recordCost } = require("../ledger.js");
const { runtimeTrace, usageRuntimeEnv } = require("../usage-event.js");
const { readWebTravelControlState, resolveSupabaseServiceConfig } = require("../runtime-preferences.js");

const COMPOSIO_EXEC = "https://backend.composio.dev/api/v3/tools/execute";
const COMPOSIO_PROXY_EXEC = "https://backend.composio.dev/api/v3.1/tools/execute/proxy";
const WEB_REMINDER_CREATE_TOOL = "GOOGLECALENDAR_CREATE_EVENT_WITH_REMINDER";
const GOOGLE_CALENDAR_EVENTS_ENDPOINT = "https://www.googleapis.com/calendar/v3/calendars/primary/events";
const WEB_TRAVEL_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function accountRefHash(uid, accountId) {
  return createHash("sha256").update(JSON.stringify([uid, accountId])).digest("hex");
}

async function ownedAccountId(uid, apiKey, opts) {
  const config = resolveSupabaseServiceConfig(opts);
  if (!config || !apiKey) throw new Error("calendar owned binding unavailable");
  const url = new URL(`${config.supaUrl}/rest/v1/lm_users`);
  url.searchParams.set("uid", `eq.${uid}`);
  url.searchParams.set("select", "uid,calendar_provider,calendar_connected_account_id");
  url.searchParams.set("limit", "2");
  const response = await (opts.fetchImpl || fetch)(url.toString(), {
    headers: { apikey: config.supaKey, Authorization: `Bearer ${config.supaKey}` },
  });
  const rows = response.ok ? await response.json() : null;
  const row = Array.isArray(rows) && rows.length === 1 ? rows[0] : null;
  const id = row && row.calendar_connected_account_id;
  if (!row || row.uid !== uid || row.calendar_provider !== "composio_gcal"
    || typeof id !== "string" || !/^[A-Za-z0-9_-]{3,128}$/.test(id)
    || opts.expectedCalendarAccountId != null && opts.expectedCalendarAccountId !== id
    || opts.ownedReadAccountRef && opts.ownedReadAccountRef !== accountRefHash(uid, id)) {
    throw new Error("calendar owned binding changed");
  }
  // Lazy import avoids panel-api -> transport -> panel-api initialization cycles.
  const { composioCalendarAccountStatus } = require("../panel-api.js");
  if (await composioCalendarAccountStatus({ uid }, id, { composioKey: apiKey, fetchImpl: opts.fetchImpl }) !== "ACTIVE") {
    throw new Error("calendar owned account inactive");
  }
  return id;
}

function googleEventFromComposio(args = {}) {
  const startText = String(args.start_datetime || "");
  const startMs = Date.parse(/[zZ]|[+-]\d{2}:?\d{2}$/.test(startText) ? startText : `${startText}Z`);
  const durationMs = ((Number(args.event_duration_hour) || 0) * 60
    + (Number(args.event_duration_minutes) || 0)) * 60000;
  if (!Number.isFinite(startMs) || durationMs <= 0 || !args.reminders) return null;
  return {
    summary: String(args.summary || ""),
    start: { dateTime: new Date(startMs).toISOString(), timeZone: "UTC" },
    end: { dateTime: new Date(startMs + durationMs).toISOString(), timeZone: "UTC" },
    location: String(args.location || ""),
    description: String(args.description || ""),
    reminders: args.reminders,
  };
}

async function selectedAccountId(uid, apiKey, opts = {}) {
  if (opts.ownedReadAccountRef || opts.beforeDispatch && opts.expectedCalendarAccountId == null) {
    return ownedAccountId(uid, apiKey, opts);
  }
  if (opts.expectedCalendarAccountId != null) {
    const expected = String(opts.expectedCalendarAccountId);
    const config = resolveSupabaseServiceConfig(opts);
    const base = config && config.supaUrl;
    const key = config && config.supaKey;
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
    return opts.beforeDispatch ? ownedAccountId(uid, apiKey, opts) : expected;
  }
  if (typeof opts.resolveConnectedAccountId === "function") return opts.resolveConnectedAccountId(uid);
  const config = resolveSupabaseServiceConfig(opts);
  const base = config && config.supaUrl;
  const key = config && config.supaKey;
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

async function exec(tool, uid, args, apiKey, opts, recordOutcome, effectAwareWrite = false) {
  let dispatched = false;
  let accountHash = null;
  const finish = async (effect, result = { successful: false }, errorClass = null, httpStatus = null) => {
    const id = result?.data?.id;
    const writeReceipt = { phase: dispatched ? "response" : "claimed", command: "calendar.create",
      effect, account_ref_hash: accountHash, http_status: httpStatus, error_class: errorClass,
      provider_event_id: typeof id === "string" && /^[A-Za-z0-9_-]{1,1024}$/.test(id) ? id : null,
      readback: null, evidence_ref: null, retryable: false,
      next_action: effect === "created" || effect === "updated" || effect === "no_effect" ? "none" : "owned_readback" };
    const costReceiptSaved = await recordOutcome(effect === "created" || effect === "updated" ? "success"
      : effect === "no_effect" ? "failure" : "unknown", writeReceipt);
    return { effect, result, writeReceipt, costReceiptSaved };
  };
  const proxyCreate = tool === WEB_REMINDER_CREATE_TOOL;
  const proxyReminderPatch = tool === "GOOGLECALENDAR_PATCH_EVENT"
    && opts.expectedCalendarAccountId != null
    && args && args.calendar_id === "primary"
    && typeof args.event_id === "string" && args.event_id.length > 0
    && args.reminders && typeof args.reminders === "object" && !Array.isArray(args.reminders)
    && Object.keys(args).every((field) => ["calendar_id", "event_id", "reminders", "send_updates"].includes(field));
  const proxyOperation = proxyCreate || proxyReminderPatch;
  if (opts.ownedReadAccountRef && tool !== "GOOGLECALENDAR_EVENTS_LIST") throw new Error("owned readback is read only");
  let connectedAccountId;
  try { connectedAccountId = await selectedAccountId(uid, apiKey, opts); }
  catch (error) {
    if (effectAwareWrite) return finish("no_effect", undefined, "account_binding_unavailable");
    throw error;
  }
  if (connectedAccountId) accountHash = accountRefHash(uid, connectedAccountId);
  if (tool !== "GOOGLECALENDAR_EVENTS_LIST" && opts.expectedCalendarAccountId != null
    && WEB_TRAVEL_UID_RE.test(String(uid || ""))) {
    let state = null;
    try {
      const readState = opts.readWebTravelControlStateImpl || readWebTravelControlState;
      state = await readState(uid, { supaUrl: opts.supaUrl, supaKey: opts.supaKey,
        fetchImpl: opts.fetchImpl, expectedCalendarAccountId: opts.expectedCalendarAccountId, nowMs: opts.nowMs });
    } catch { /* unknown Web controls fail closed before provider mutation */ }
    const oneShotInitialScan = effectAwareWrite && opts.allowWebInitialScan === true
      && state && state.initialScanAllowed === true && state.dailyAutomationEnabled === false;
    const automatedBillingIsActive = state && state.dailyAutomationEnabled === true
      && state.billingEntitled === true;
    if (!state || (!automatedBillingIsActive && !oneShotInitialScan)
      || state.disconnectPending !== false || state.enablePending !== false) {
      if (effectAwareWrite) return finish("no_effect", undefined, "web_automation_paused");
      throw new Error("web calendar automation is paused or pending");
    }
  }
  let result;
  let response;
  try {
    const requestBody = proxyCreate
      ? { ...args, ...(connectedAccountId ? { connected_account_id: connectedAccountId } : {}) }
      : proxyReminderPatch ? {
        endpoint: `${GOOGLE_CALENDAR_EVENTS_ENDPOINT}/${encodeURIComponent(args.event_id)}`,
        method: "PATCH",
        parameters: [{ name: "sendUpdates", value: "none", type: "query" }],
        body: { reminders: args.reminders },
        ...(connectedAccountId ? { connected_account_id: connectedAccountId } : {}),
      }
        : { user_id: uid, ...(connectedAccountId ? { connected_account_id: connectedAccountId } : {}), arguments: args };
    if (typeof opts.beforeDispatch === "function") {
      const durable = await opts.beforeDispatch({ account_ref_hash: accountHash, command: "calendar.create" });
      if (durable !== true) return finish("unknown", undefined, "receipt_not_durable");
    }
    dispatched = true;
    response = await (opts.fetchImpl || fetch)(proxyOperation ? COMPOSIO_PROXY_EXEC : `${COMPOSIO_EXEC}/${tool}`, {
      method: "POST",
      headers: { "x-api-key": apiKey, "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });
  } catch (error) {
    if (effectAwareWrite) return finish("unknown", undefined, dispatched ? "transport_error" : "receipt_not_durable");
    await recordOutcome("unknown");
    throw error;
  }
  if (proxyOperation) {
    let proxied;
    try { proxied = await response.json(); }
    catch {
      return finish("unknown", undefined, "unreadable_response", response.status || null);
    }
    const upstreamStatus = Number(proxied && proxied.status) || 0;
    const proxyStatus = Number(response && response.status) || 0;
    const proxyError = proxied && typeof proxied.error === "string" ? proxied.error
      : proxied && proxied.error && typeof proxied.error.message === "string" ? proxied.error.message
        : proxied && typeof proxied.message === "string" ? proxied.message : "";
    const proxyValidationRejected = proxyStatus === 400
      && /invalid\s+(?:request\s+)?parameters?/i.test(proxyError);
    if ((upstreamStatus >= 400 && upstreamStatus < 500) || proxyValidationRejected) {
      return finish("no_effect", undefined, "provider_validation", upstreamStatus || proxyStatus);
    }
    if (proxyStatus >= 400 && proxyStatus < 500) {
      return finish("unknown", undefined, "unclassified_response", proxyStatus);
    }
    const rawData = proxied && proxied.data && typeof proxied.data === "object" ? proxied.data : null;
    const data = rawData && rawData.response_data && typeof rawData.response_data === "object"
      ? rawData.response_data : rawData;
    const eventIdMatches = proxyReminderPatch
      ? Boolean(data && String(data.id || "") === args.event_id) : Boolean(data && data.id);
    const successful = response.ok === true && (upstreamStatus === 0 || upstreamStatus >= 200 && upstreamStatus < 300)
      && eventIdMatches;
    const effect = successful ? proxyReminderPatch ? "updated" : "created" : "unknown";
    return finish(effect, { successful, data }, successful ? null : "unconfirmed_response", upstreamStatus || proxyStatus || null);
  }
  const status = Number.isInteger(response?.status) ? response.status : null;
  if (effectAwareWrite && status !== null && status >= 400 && status < 500) {
    if (opts.travelWriteContext) {
      let rejected;
      try { rejected = await response.json(); } catch { /* an opaque response cannot prove no effect */ }
      const message = typeof rejected?.error === "string" ? rejected.error : rejected?.error?.message || rejected?.message || "";
      const validated = status === 400 && /invalid\s+(?:request\s+)?parameters?/i.test(message);
      return finish(validated ? "no_effect" : "unknown", undefined,
        validated ? "provider_validation" : "unclassified_response", status);
    }
    return finish("no_effect", undefined, "provider_rejected", status);
  }
  if (effectAwareWrite && status !== null && (status < 200 || status >= 300)) {
    return finish("unknown", undefined, "provider_unavailable", status);
  }
  try { result = await response.json(); }
  catch (error) {
    if (effectAwareWrite) return finish("unknown", undefined, "unreadable_response", status);
    await recordOutcome("unknown");
    throw error;
  }
  if (effectAwareWrite) {
    const effect = result && result.successful === true && (!opts.travelWriteContext || typeof result.data?.id === "string")
      ? tool === "GOOGLECALENDAR_PATCH_EVENT" ? "updated" : "created"
      : "unknown";
    return finish(effect, result, effect === "unknown" ? "unconfirmed_response" : null, status);
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
    const { outcome, runtimeTrace: trace, travelWrite } = details || {};
    return recordCost({
      uid, kind: "composio_call", quantity: 1, unit: "call", estUsd: null,
      meta: { provider: "composio", operation: String(tool), tool, outcome, runtime_trace: trace,
        ...(travelWrite ? { travel_write: travelWrite } : {}) },
    });
  });
  const execute = async (tool, uid, args, expectedCalendarAccountId = opts.expectedCalendarAccountId,
    effectAwareWrite = false, extraOpts = {}) => {
    const operationOpts = { ...opts, ...extraOpts,
      ...(expectedCalendarAccountId == null ? {} : { expectedCalendarAccountId }) };
    const runtimeEnv = usageRuntimeEnv(opts.runtimeEnv || process.env, { fallbackOwnerId: "life-call-calendar" });
    const trace = extraOpts.travelWriteContext?.runtime_trace || runtimeTrace({ tenantId: uid }, runtimeEnv);
    const recordOutcome = async (outcome, receipt) => {
      const context = extraOpts.travelWriteContext;
      const travelWrite = context ? Object.fromEntries([
        "request_id", "source_event_hash", "source_event_version", "request_fingerprint", "leg",
      ].map((field) => [field, context[field]])) : null;
      if (travelWrite && receipt) Object.assign(travelWrite, receipt);
      try { return await ledger(uid, tool, { outcome, runtimeTrace: trace, ...(travelWrite ? { travelWrite } : {}) }) === true; }
      catch { return false; }
    };
    return exec(tool, uid, args, key, operationOpts, recordOutcome, effectAwareWrite);
  };
  const withCreateEffect = ({ effect, result, writeReceipt, costReceiptSaved }) => {
    const value = result && typeof result === "object" ? result : { successful: false };
    Object.defineProperty(value, "effect", { value: effect, configurable: true });
    if (writeReceipt) Object.defineProperty(value, "writeReceipt", { value: writeReceipt, configurable: true });
    Object.defineProperty(value, "costReceiptSaved", { value: costReceiptSaved === true, configurable: true });
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
  const listEventsPage = async (uid, { timeMin, timeMax, maxResults, pageToken, strict, expectedCalendarAccountId,
    ownedReadAccountRef, supaUrl, supaKey } = {}) => {
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
      j = await execute("GOOGLECALENDAR_EVENTS_LIST", uid, args, expectedCalendarAccountId, false,
        ownedReadAccountRef ? { ownedReadAccountRef, ...(supaUrl ? { supaUrl, supaKey } : {}) } : {});
    } catch (e) {
      if (strict) throw e;
      return empty;
    }
    if (!j || (ownedReadAccountRef ? j.successful !== true : !j.successful)) {
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
    async getOwnedEvent(uid, eventId, { accountRefHash: accountHash, ...input } = {}) {
      let dispatched = false, outcome = "unknown";
      try {
        if (!key || !uid || !/^[a-f0-9]{64}$/.test(String(accountHash || ""))
          || typeof eventId !== "string" || !/^[A-Za-z0-9_-]{1,1024}$/.test(eventId)) throw new Error();
        const readOpts = { ...opts, ...input, ownedReadAccountRef: accountHash };
        const connectedAccountId = await ownedAccountId(uid, key, readOpts);
        dispatched = true;
        const response = await (opts.fetchImpl || fetch)(COMPOSIO_PROXY_EXEC, {
          method: "POST", headers: { "x-api-key": key, "Content-Type": "application/json" },
          body: JSON.stringify({ connected_account_id: connectedAccountId, user_id: uid,
            endpoint: `${GOOGLE_CALENDAR_EVENTS_ENDPOINT}/${encodeURIComponent(eventId)}`, method: "GET" }),
        });
        const payload = await response.json();
        const event = payload?.data;
        if (response.ok !== true || payload?.status !== 200 || !event || typeof event !== "object"
          || Array.isArray(event) || event.id !== eventId) throw new Error();
        outcome = "success";
        return event;
      } catch { throw new Error("calendar owned event read failed"); }
      finally {
        if (dispatched) {
          try { await ledger(uid, "calendar.owned_get", { outcome,
            runtimeTrace: runtimeTrace({ tenantId: uid }, usageRuntimeEnv(opts.runtimeEnv || process.env,
              { fallbackOwnerId: "life-call-calendar" })) }); } catch { /* cost recording remains best effort */ }
        }
      }
    },
    async listOwnedEvents(uid, { accountRefHash: accountHash, ...input } = {}) {
      if (!/^[a-f0-9]{64}$/.test(String(accountHash || ""))) throw new Error("calendar receipt account missing");
      const items = [];
      const tokens = new Set();
      let pageToken;
      for (let page = 0; page < 20; page++) {
        const result = await listEventsPage(uid, { ...input, pageToken, maxResults: 2500,
          strict: true, ownedReadAccountRef: accountHash });
        if (!Array.isArray(result.items)) throw new Error("calendar readback malformed");
        items.push(...result.items);
        if (!result.nextPageToken) return items;
        if (tokens.has(result.nextPageToken)) break;
        tokens.add(result.nextPageToken);
        pageToken = result.nextPageToken;
      }
      throw new Error("calendar readback incomplete");
    },
    // Raw Google Calendar items (each consumer maps to its own shape) for [timeMin, timeMax] (ISO Z),
    // FIRST page only — the wake path reads an 18-hour horizon and has never approached a page
    // boundary. Callers that need provable completeness follow listEventsPage's cursor instead.
    async listEventsRaw(uid, opts = {}) {
      return (await listEventsPage(uid, opts)).items;
    },
    async createEvent(uid, args, operationOpts = {}) {
      if (!key) return withCreateEffect({ effect: "no_effect", result: { successful: false } });
      try {
        const reminderEvent = args && args.reminders && operationOpts.expectedCalendarAccountId
          ? googleEventFromComposio(args) : null;
        const tool = reminderEvent ? WEB_REMINDER_CREATE_TOOL : "GOOGLECALENDAR_CREATE_EVENT";
        const request = reminderEvent ? {
          endpoint: GOOGLE_CALENDAR_EVENTS_ENDPOINT,
          method: "POST",
          parameters: [{ name: "sendUpdates", value: String(args.send_updates || "none"), type: "query" }],
          body: reminderEvent,
        } : args && args.send_updates === "none" ? { ...args, send_updates: false } : args;
        return withCreateEffect(await execute(tool, uid, request,
          operationOpts.expectedCalendarAccountId, true,
          { allowWebInitialScan: operationOpts.allowWebInitialScan === true,
            ...(operationOpts.beforeDispatch ? { beforeDispatch: operationOpts.beforeDispatch,
              travelWriteContext: operationOpts.travelWriteContext,
              supaUrl: operationOpts.supaUrl || opts.supaUrl, supaKey: operationOpts.supaKey || opts.supaKey } : {}) }));
      } catch { return withCreateEffect({ effect: "unknown", result: { successful: false } }); }
    },
    async patchEvent(uid, args, operationOpts = {}) {
      if (!key) return { successful: false };
      const expectedCalendarAccountId = operationOpts.expectedCalendarAccountId;
      const effectAwareWrite = expectedCalendarAccountId != null;
      try {
        const result = await execute("GOOGLECALENDAR_PATCH_EVENT", uid, args, expectedCalendarAccountId,
          effectAwareWrite, { allowWebInitialScan: operationOpts.allowWebInitialScan === true });
        if (!result || !result.effect) return result;
        return { ...(result.result || {}), effect: result.effect, successful: result.effect === "updated" };
      } catch { return { successful: false, ...(effectAwareWrite ? { effect: "unknown" } : {}) }; }
    },
  };
}

module.exports = { makeComposioCalendar };
