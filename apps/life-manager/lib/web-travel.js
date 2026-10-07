"use strict";

const crypto = require("node:crypto");
const { resolveWebUser } = require("./web-auth.js");
const { assertWebUserUnbound } = require("./web-calendar.js");
const { readWebTravelControlState } = require("./runtime-preferences.js");
const { isTravel, listEvents7d, travelDecision } = require("./travel.js");

const SETUP_PATH = "/api/lm-web/setup";
const TODAY_PATH = "/api/lm-web/today";
const CONTROL_PATH = "/api/lm-web/travel/control";
const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ACCOUNT_ID_RE = /^[A-Za-z0-9_-]{3,128}$/;
const SERVICE_FIELDS = "uid,telegram_chat_id,calendar_provider,calendar_connected_account_id,home_address,trial_expires_at,paid,plan_status,stripe_subscription_id,current_period_end,web_initial_scan_completed_at,web_first_travel_at";

function requestUrl(req) {
  try { return new URL(req.url || "/", "http://life-manager.local"); }
  catch { return new URL("/", "http://life-manager.local"); }
}

function sendJson(res, status, body, headers = {}) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers });
  res.end(JSON.stringify(body));
}

function webError(status, code) {
  const error = new Error(code);
  error.status = status;
  error.code = code;
  return error;
}

function originFor(opts = {}) {
  const configured = String(opts.publicOrigin || opts.panelBaseUrl || "").trim();
  if (!configured) return "";
  try { return new URL(configured).origin; } catch { return ""; }
}

function hasJsonContentType(req) {
  return /^application\/json(?:\s*;|$)/i.test(String(req.headers && req.headers["content-type"] || ""));
}

function validCsrf(req, user) {
  const expected = Buffer.from(String(user && user.csrf || ""));
  const actual = Buffer.from(String(req.headers && req.headers["x-lm-web-csrf"] || ""));
  return expected.length > 0 && expected.length === actual.length && crypto.timingSafeEqual(actual, expected);
}

function normalizeHomeAddress(value) {
  if (typeof value !== "string") return "";
  const address = value.trim();
  const length = Array.from(address).length;
  return length >= 1 && length <= 240 ? address : "";
}

function serviceHeaders(key, extra = {}) {
  return { apikey: key, Authorization: `Bearer ${key}`, ...extra };
}

async function readWebUserRow(uid, opts = {}) {
  const base = String(opts.supaUrl || "").replace(/\/$/, "");
  if (!base || !opts.supaKey) throw webError(503, "web_user_read_unavailable");
  const url = new URL(`${base}/rest/v1/lm_users`);
  url.searchParams.set("uid", `eq.${uid}`);
  url.searchParams.set("telegram_chat_id", "is.null");
  url.searchParams.set("select", SERVICE_FIELDS);
  url.searchParams.set("limit", "2");
  const response = await (opts.fetchImpl || fetch)(url.toString(), { headers: serviceHeaders(opts.supaKey) });
  if (!response.ok) throw webError(502, "web_user_read_failed");
  const rows = await response.json().catch(() => null);
  const row = Array.isArray(rows) && rows.length === 1 ? rows[0] : null;
  if (!row || row.uid !== uid || row.telegram_chat_id != null) throw webError(403, "unauthorized");
  return row;
}

async function readWebAutomationPreference(uid, opts = {}) {
  const readState = opts.readWebTravelControlStateImpl || readWebTravelControlState;
  const state = await readState(uid, opts);
  if (!state || typeof state.disconnectPending !== "boolean" || typeof state.enablePending !== "boolean") {
    throw webError(502, "control_readback_unavailable");
  }
  return state;
}

async function assertUnbound(uid, opts) {
  const check = opts.assertWebUserUnboundImpl || assertWebUserUnbound;
  if (!await check(uid, opts)) throw webError(403, "unauthorized");
}

function providerOptions(opts = {}) {
  const env = opts.env && typeof opts.env === "object" ? opts.env : process.env;
  return {
    ...opts,
    composioKey: opts.composioKey || env.COMPOSIO_API_KEY,
    composioAuthConfig: opts.composioAuthConfig || env.COMPOSIO_GCAL_AUTH_CONFIG,
  };
}

function panelApi() {
  return require("./panel-api.js");
}

async function readActiveCalendarUser(uid, opts = {}) {
  await assertUnbound(uid, opts);
  const row = await readWebUserRow(uid, opts);
  const accountId = String(row.calendar_connected_account_id || "");
  if (row.calendar_provider !== "composio_gcal" || !ACCOUNT_ID_RE.test(accountId)) {
    return { row, status: "MISSING" };
  }
  await assertUnbound(uid, opts);
  const statusImpl = opts.composioCalendarAccountStatusImpl || panelApi().composioCalendarAccountStatus;
  let status;
  try { status = await statusImpl({ uid }, accountId, providerOptions(opts)); }
  catch { throw Object.assign(webError(502, "calendar_status_unavailable"), { userRow: row }); }
  if (!["ACTIVE", "DISABLED", "MISSING", "EXPIRED"].includes(status)) {
    throw Object.assign(webError(502, "calendar_status_unavailable"), { userRow: row });
  }
  return { row, status };
}

async function rpc(name, body, opts = {}) {
  const base = String(opts.supaUrl || "").replace(/\/$/, "");
  if (!base || !opts.supaKey) throw webError(503, "setup_unavailable");
  const response = await (opts.fetchImpl || fetch)(`${base}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: serviceHeaders(opts.supaKey, { "content-type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    const message = String(failure && failure.message || "");
    if (message.includes("calendar_account_changed")) throw webError(409, "calendar_account_changed");
    if (message.includes("calendar_disconnect_pending")) throw webError(409, "disconnect_pending");
    if (message.includes("calendar_enable_pending")) throw webError(409, "calendar_enable_pending");
    if (message.includes("calendar_operation_pending")) throw webError(409, "calendar_operation_pending");
    if (message.includes("home_required")) throw webError(409, "home_required");
    if (message.includes("calendar_not_connected")) throw webError(409, "calendar_not_connected");
    throw webError(502, "setup_unavailable");
  }
  return response.json().catch(() => null);
}

function firstValue(value) {
  return Array.isArray(value) ? value[0] : value;
}

async function recordWebInitialScan(uid, accountId, completedAt, firstTravelAt, opts = {}) {
  const result = firstValue(await rpc("record_lm_web_initial_scan", {
    p_uid: uid,
    p_calendar_account_id: accountId,
    p_completed_at: completedAt,
    p_first_travel_at: firstTravelAt,
  }, opts));
  if (result !== true) throw webError(502, "initial_scan_write_unconfirmed");
  await assertUnbound(uid, opts);
  const row = await readWebUserRow(uid, opts);
  if (row.calendar_provider !== "composio_gcal" || row.calendar_connected_account_id !== accountId
    || !row.web_initial_scan_completed_at
    || firstTravelAt && !row.web_first_travel_at) {
    throw webError(502, "initial_scan_readback_unavailable");
  }
  return row;
}

async function runInitialWebTravelScan(uid, opts = {}) {
  if (!WEB_UID_RE.test(String(uid || ""))) throw webError(401, "unauthorized");
  const active = await readActiveCalendarUser(uid, opts);
  if (active.status !== "ACTIVE") throw webError(409, "calendar_not_active");
  const initialRow = active.row;
  if (initialRow.web_initial_scan_completed_at) {
    const snapshot = await buildTodaySnapshot(uid, opts);
    return Object.assign(snapshot, {
      scanState: initialRow.web_first_travel_at ? "complete" : "zero_blocks",
      checkoutAvailable: Boolean(initialRow.web_first_travel_at && !initialRow.stripe_subscription_id),
    });
  }
  if (initialRow.stripe_subscription_id && initialRow.paid === true) {
    return Object.assign(await buildTodaySnapshot(uid, opts), { scanState: "already_subscribed", checkoutAvailable: false });
  }

  const paused = await applyWebTravelControl(uid, initialRow.calendar_connected_account_id, "pause", opts);
  if (paused.disconnectPending) throw webError(409, "disconnect_pending");
  if (paused.enablePending) throw webError(409, "calendar_enable_pending");

  const current = await readActiveCalendarUser(uid, opts);
  if (current.status !== "ACTIVE"
    || current.row.calendar_connected_account_id !== initialRow.calendar_connected_account_id) {
    throw webError(409, "calendar_account_changed");
  }
  await assertUnbound(uid, opts);
  const travelResult = await travelOwnerOnce({
    uid,
    home_address: current.row.home_address || null,
    call_time_zone: null,
    daily_automation_enabled: false,
    call_enabled: false,
    notifications_enabled: false,
    telegram_chat_id: null,
    expectedCalendarAccountId: current.row.calendar_connected_account_id,
  }, opts, { initialScan: true });

  const snapshot = await buildTodaySnapshot(uid, opts);
  if (travelResult == null || snapshot.calendarState !== "connected"
    || snapshot.setupState === "sync_pending"
    || travelResult.inserted > 0 && snapshot.confirmedTravelBlockCount === 0) {
    return Object.assign(snapshot, { scanState: "pending", checkoutAvailable: false });
  }

  const completedAt = new Date(opts.nowMs == null ? Date.now() : opts.nowMs).toISOString();
  const firstTravelAt = snapshot.confirmedTravelBlockCount > 0
    ? initialRow.web_first_travel_at || completedAt : null;
  const row = await recordWebInitialScan(uid, current.row.calendar_connected_account_id,
    completedAt, firstTravelAt, opts);
  const offerAvailable = Boolean(row.web_first_travel_at && !row.stripe_subscription_id);
  return Object.assign(snapshot, {
    setupState: row.web_first_travel_at ? "trial_offer" : "no_eligible_events",
    initialScanCompletedAt: row.web_initial_scan_completed_at,
    firstTravelAt: row.web_first_travel_at,
    scanState: row.web_first_travel_at ? "complete" : "zero_blocks",
    checkoutAvailable: offerAvailable,
    syncState: syncState(snapshot, travelResult),
  });
}

function eventSnapshot(event) {
  if (!event) return null;
  return {
    id: event.id || "",
    summary: event.summary || "",
    location: event.location || "",
    startIso: event.startIso || (Number.isFinite(event.startMs) ? new Date(event.startMs).toISOString() : ""),
    timezone: event.timezone || "",
    startMs: Number.isFinite(event.startMs) ? event.startMs : null,
    endMs: Number.isFinite(event.endMs) ? event.endMs : null,
  };
}

function matchingTravelBlocks(events, event) {
  if (!event || !event.location) return [];
  const location = String(event.location).replace(/\s+/g, "").toLowerCase();
  return events.filter((candidate) => isTravel(candidate.summary)
    && Number.isFinite(candidate.endMs)
    && candidate.endMs >= event.startMs - 2 * 60_000
    && candidate.endMs <= event.startMs + 60_000
    && String(candidate.location || "").replace(/\s+/g, "").toLowerCase() === location);
}

function confirmedTravelBlockCount(events, nowMs) {
  const blocks = new Set();
  for (const event of events) {
    if (event.startMs < nowMs || isTravel(event.summary) || !event.location) continue;
    const matches = matchingTravelBlocks(events, event);
    if (matches.length !== 1) continue;
    const block = matches[0];
    blocks.add(block.id || `${block.startMs}:${block.endMs}:${block.location || ""}`);
  }
  return blocks.size;
}

function validEventTimeZone(value) {
  if (typeof value !== "string") return null;
  const timezone = value.trim();
  if (!timezone || /^[+-]\d{2}(?::?\d{2})?$/.test(timezone)) return null;
  try { new Intl.DateTimeFormat("en-US", { timeZone: timezone }); return timezone; }
  catch { return null; }
}

function baseSnapshot(row, setupState, calendarState) {
  return {
    setupState,
    calendarState,
    calendarBound: Boolean(row && row.calendar_provider === "composio_gcal"
      && ACCOUNT_ID_RE.test(String(row.calendar_connected_account_id || ""))),
    dailyAutomationEnabled: null,
    disconnectPending: null,
    enablePending: null,
    nextEvent: null,
    travelBlock: null,
    departureAt: null,
    displayTimeZone: null,
    missingLocationCount: 0,
    initialScanCompletedAt: row && row.web_initial_scan_completed_at || null,
    firstTravelAt: row && row.web_first_travel_at || null,
    confirmedTravelBlockCount: 0,
    scanState: null,
    checkoutAvailable: false,
    trialExpiresAt: row && row.trial_expires_at || null,
    paid: row && typeof row.paid === "boolean" ? row.paid : null,
    planStatus: row && row.plan_status || null,
    stripeSubscriptionId: row && row.stripe_subscription_id || null,
  };
}

async function buildTodaySnapshot(uid, opts = {}) {
  if (!WEB_UID_RE.test(String(uid || ""))) throw webError(401, "unauthorized");
  let current;
  try { current = await readActiveCalendarUser(uid, opts); }
  catch (error) {
    if (error && error.code === "calendar_status_unavailable") {
      return Object.assign(baseSnapshot(error.userRow, "sync_pending", "unavailable"),
        await readWebAutomationPreference(uid, opts));
    }
    throw error;
  }
  const { row, status } = current;
  const preference = await readWebAutomationPreference(uid, opts);
  if (status !== "ACTIVE") {
    return Object.assign(baseSnapshot(row, "needs_calendar", "action_required"), preference);
  }

  const nowMs = opts.nowMs == null ? Date.now() : opts.nowMs;
  // The selected account's exact ACTIVE result above is still current only if its marker is unchanged.
  // Re-read that row and run Task 2's NULL-Telegram check immediately before the Calendar event read.
  const beforeReadRow = await readWebUserRow(uid, opts);
  await assertUnbound(uid, opts);
  if (beforeReadRow.calendar_provider !== "composio_gcal"
    || beforeReadRow.calendar_connected_account_id !== row.calendar_connected_account_id) {
    return Object.assign(baseSnapshot(beforeReadRow, "needs_calendar", "action_required"), preference);
  }

  let events;
  try {
    events = await (opts.listEvents7dImpl || listEvents7d)(
      uid,
      opts.apiKey || (opts.env && opts.env.COMPOSIO_API_KEY) || process.env.COMPOSIO_API_KEY,
      nowMs,
      opts.calendar,
      null,
      { strict: true, expectedCalendarAccountId: row.calendar_connected_account_id },
    );
  } catch {
    return Object.assign(baseSnapshot(beforeReadRow, "sync_pending", "connected"), preference);
  }
  const ordered = events.slice().sort((a, b) => a.startMs - b.startMs);
  const nextEvent = ordered.find((event) => event.startMs >= nowMs && !isTravel(event.summary)) || null;
  const matches = matchingTravelBlocks(ordered, nextEvent);
  const travel = matches.length === 1 ? matches[0] : null;
  const snapshot = Object.assign(baseSnapshot(beforeReadRow, "ready", "connected"), preference);
  snapshot.nextEvent = eventSnapshot(nextEvent);
  snapshot.travelBlock = eventSnapshot(travel);
  snapshot.departureAt = travel && Number.isFinite(travel.startMs) ? new Date(travel.startMs).toISOString() : null;
  snapshot.displayTimeZone = validEventTimeZone(nextEvent && nextEvent.timezone);
  snapshot.confirmedTravelBlockCount = confirmedTravelBlockCount(ordered, nowMs);
  const sevenDaysLater = nowMs + 7 * 86400_000;
  snapshot.missingLocationCount = ordered.filter((event) => event.startMs >= nowMs
    && event.startMs <= sevenDaysLater
    && !isTravel(event.summary)
    && !String(event.location || "").trim()).length;

  if (matches.length > 1) snapshot.setupState = "sync_pending";
  else if (nextEvent && nextEvent.location) {
    const previous = ordered.filter((event) => event.startMs < nextEvent.startMs && !isTravel(event.summary)).at(-1) || null;
    if (travelDecision(nextEvent, previous, String(beforeReadRow.home_address || "").trim()).insert && !travel) {
      snapshot.setupState = "sync_pending";
    }
  }
  if (snapshot.setupState !== "sync_pending" && !beforeReadRow.web_initial_scan_completed_at) snapshot.setupState = "needs_initial_scan";
  else if (snapshot.setupState !== "sync_pending" && beforeReadRow.web_first_travel_at
    && beforeReadRow.stripe_subscription_id && beforeReadRow.paid !== true) snapshot.setupState = "billing_inactive";
  else if (snapshot.setupState !== "sync_pending" && beforeReadRow.web_first_travel_at && beforeReadRow.paid === true
    && String(beforeReadRow.plan_status || "").toLowerCase() === "trialing") snapshot.setupState = "trial_active";
  else if (snapshot.setupState !== "sync_pending" && beforeReadRow.web_first_travel_at && beforeReadRow.paid === true) snapshot.setupState = "subscribed";
  else if (snapshot.setupState !== "sync_pending" && beforeReadRow.web_first_travel_at) snapshot.setupState = "trial_offer";
  else if (snapshot.setupState !== "sync_pending" && beforeReadRow.web_initial_scan_completed_at) snapshot.setupState = "no_eligible_events";
  else if (snapshot.setupState !== "sync_pending") snapshot.setupState = "needs_initial_scan";
  snapshot.scanState = beforeReadRow.web_initial_scan_completed_at
    ? beforeReadRow.web_first_travel_at ? "complete" : "zero_blocks" : "not_started";
  snapshot.checkoutAvailable = Boolean(beforeReadRow.web_first_travel_at
    && !beforeReadRow.stripe_subscription_id && beforeReadRow.paid !== true);
  return snapshot;
}

function syncState(snapshot, travelResult) {
  if (snapshot.setupState === "sync_pending") return "sync_pending";
  if (snapshot.travelBlock) {
    const nextEvent = snapshot.nextEvent;
    const eventId = nextEvent.id || `${nextEvent.startMs}:${nextEvent.summary || ""}`;
    const report = (travelResult && travelResult.outboundReports || []).find((item) => item && item.eventId === eventId);
    const addedForEvent = Boolean(travelResult && travelResult.inserted > 0 && report
      && report.leaveMs === snapshot.travelBlock.startMs
      && report.arriveMs === snapshot.travelBlock.endMs);
    return addedForEvent ? "travel_added" : "travel_verified";
  }
  return snapshot.setupState === "ready" ? "no_travel_needed" : "sync_pending";
}

async function travelOwnerOnce(user, opts = {}, runOptions = {}) {
  const run = opts.travelUserOnceImpl || require("../scheduler.js").travelUserOnce;
  const env = opts.env || process.env;
  return run(user, {
    initialScan: runOptions.initialScan === true,
    apiKey: opts.composioKey || env.COMPOSIO_API_KEY,
    mapsKey: opts.mapsKey || env.LIFE_MAPS_KEY || env.GOOGLE_API_KEY,
    geminiKey: opts.geminiKey || env.GEMINI_API_KEY,
    supaUrl: opts.supaUrl,
    supaKey: opts.supaKey,
    fetchImpl: opts.fetchImpl || opts.fetch,
    env,
    nowMs: opts.nowMs,
    calendar: opts.calendar,
  });
}

function selectedWebCalendarAccount(row) {
  if (row.calendar_provider == null && row.calendar_connected_account_id == null) return null;
  const accountId = String(row.calendar_connected_account_id || "");
  if (row.calendar_provider !== "composio_gcal" || !ACCOUNT_ID_RE.test(accountId)) {
    throw webError(409, "calendar_account_changed");
  }
  return accountId;
}

async function applyWebTravelControl(uid, accountId, action, opts = {}) {
  const result = firstValue(await rpc("control_lm_web_travel", {
    p_uid: uid,
    p_calendar_account_id: accountId,
    p_action: action,
  }, opts));
  if (result !== true) throw webError(409, "calendar_account_changed");

  await assertUnbound(uid, opts);
  const row = await readWebUserRow(uid, opts);
  const preference = await readWebAutomationPreference(uid, opts);
  const expectedAccountId = action === "disconnect_finish" ? null : accountId;
  const expectedPending = action === "disconnect_begin" ? true
    : action === "disconnect_finish" || action === "resume" ? false : null;
  const expectedEnablePending = action === "pause" ? null : false;
  if (selectedWebCalendarAccount(row) !== expectedAccountId
    || preference.dailyAutomationEnabled !== (action === "resume")
    || expectedPending !== null && preference.disconnectPending !== expectedPending
    || expectedEnablePending !== null && preference.enablePending !== expectedEnablePending) {
    throw webError(502, "control_readback_unavailable");
  }
  return {
    dailyAutomationEnabled: preference.dailyAutomationEnabled,
    disconnectPending: preference.disconnectPending,
    enablePending: preference.enablePending,
    calendarBound: expectedAccountId !== null,
  };
}

async function controlWebTravel(uid, action, opts = {}) {
  await assertUnbound(uid, opts);
  let row = await readWebUserRow(uid, opts);
  let accountId = selectedWebCalendarAccount(row);
  const preference = await readWebAutomationPreference(uid, opts);

  if (action === "resume") {
    if (preference.disconnectPending === true) throw webError(409, "disconnect_pending");
    if (preference.enablePending === true) throw webError(409, "calendar_enable_pending");
    const active = await readActiveCalendarUser(uid, opts);
    if (active.status !== "ACTIVE" || selectedWebCalendarAccount(active.row) !== accountId) {
      throw webError(409, "calendar_not_active");
    }
    row = active.row;
    await assertUnbound(uid, opts);
    const current = await readWebUserRow(uid, opts);
    if (selectedWebCalendarAccount(current) !== accountId) throw webError(409, "calendar_account_changed");
  }

  if (action === "disconnect") {
    if (!accountId) throw webError(409, "calendar_not_connected");
    let paused = false;
    try {
      await applyWebTravelControl(uid, accountId, "disconnect_begin", opts);
      paused = true;
      const disconnect = opts.composioCalendarDisconnectImpl || panelApi().composioCalendarDisconnect;
      const result = await disconnect({ uid }, {
        ...providerOptions(opts), connectedAccountId: accountId, rollbackOnReadbackFailure: false,
      });
      if (!result || result.provider !== "calendar" || result.state !== "action_required") {
        throw webError(502, "calendar_disconnect_unavailable");
      }
      const status = await (opts.composioCalendarAccountStatusImpl || panelApi().composioCalendarAccountStatus)(
        { uid }, accountId, providerOptions(opts),
      );
      if (status !== "DISABLED") throw webError(502, "calendar_disconnect_unavailable");
      return await applyWebTravelControl(uid, accountId, "disconnect_finish", opts);
    } catch (error) {
      if (paused && error && typeof error === "object") error.automationPaused = true;
      throw error;
    }
  }

  return applyWebTravelControl(uid, accountId, action, opts);
}

async function handleWebTravelRequest(req, res, opts = {}) {
  const url = requestUrl(req);
  if (![SETUP_PATH, TODAY_PATH, CONTROL_PATH].includes(url.pathname)) return sendJson(res, 404, { error: "not_found" });
  let user = null;
  try { user = await (opts.resolveWebUserImpl || resolveWebUser)(req, res, opts); } catch {}
  if (!user || !WEB_UID_RE.test(String(user.uid || ""))) return sendJson(res, 401, { error: "unauthorized" });
  const uid = String(user.uid);

  if (url.pathname === TODAY_PATH) {
    if (req.method !== "GET") return sendJson(res, 405, { error: "method_not_allowed" }, { allow: "GET" });
    try { return sendJson(res, 200, await buildTodaySnapshot(uid, opts)); }
    catch (error) {
      const status = Number.isInteger(error && error.status) ? error.status : 502;
      return sendJson(res, status, { error: status < 500 ? error.code : "today_unavailable" });
    }
  }

  if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" }, { allow: "POST" });
  const origin = originFor(opts);
  if (!origin || String(req.headers && req.headers.origin || "") !== origin) return sendJson(res, 403, { error: "origin_rejected" });
  if (!hasJsonContentType(req)) return sendJson(res, 415, { error: "json_required" });
  if (!validCsrf(req, user)) return sendJson(res, 403, { error: "csrf_rejected" });

  let body;
  try { body = await (opts.readJsonImpl || panelApi().readJson)(req); }
  catch (error) { return sendJson(res, error && error.status === 413 ? 413 : 400, { error: "invalid_json" }); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return sendJson(res, 400, { error: "invalid_json" });

  if (url.pathname === CONTROL_PATH) {
    if (Object.keys(body).length !== 1 || !["pause", "resume", "disconnect"].includes(body.action)) {
      return sendJson(res, 400, { error: "invalid_control_action" });
    }
    try { return sendJson(res, 200, await controlWebTravel(uid, body.action, opts)); }
    catch (error) {
      const status = Number.isInteger(error && error.status) ? error.status : 502;
      const response = { error: status < 500 ? error.code : "control_unavailable" };
      if (error && error.automationPaused === true) response.automationPaused = true;
      return sendJson(res, status, response);
    }
  }

  try {
    return sendJson(res, 200, await runInitialWebTravelScan(uid, opts));
  } catch (error) {
    const status = Number.isInteger(error && error.status) ? error.status : 502;
    return sendJson(res, status, { error: status < 500 ? error.code : "setup_unavailable" });
  }
}

module.exports = {
  CONTROL_PATH,
  SETUP_PATH,
  TODAY_PATH,
  buildTodaySnapshot,
  handleWebTravelRequest,
  runInitialWebTravelScan,
};
