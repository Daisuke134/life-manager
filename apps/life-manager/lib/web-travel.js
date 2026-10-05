"use strict";

const crypto = require("node:crypto");
const { resolveWebUser } = require("./web-auth.js");
const { assertWebUserUnbound } = require("./web-calendar.js");
const { isTravel, listEvents7d, travelDecision } = require("./travel.js");

const SETUP_PATH = "/api/lm-web/setup";
const TODAY_PATH = "/api/lm-web/today";
const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ACCOUNT_ID_RE = /^[A-Za-z0-9_-]{3,128}$/;
const SERVICE_FIELDS = "uid,telegram_chat_id,calendar_provider,calendar_connected_account_id,home_address,trial_expires_at,paid";

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
  const expected = String(user && user.csrf || "");
  const actual = String(req.headers && req.headers["x-lm-web-csrf"] || "");
  if (!expected || expected.length !== actual.length) return false;
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(actual));
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
  if (!["ACTIVE", "DISABLED", "MISSING"].includes(status)) {
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
    if (String(failure && failure.message || "").includes("calendar_account_changed")) {
      throw webError(409, "calendar_account_changed");
    }
    throw webError(502, "setup_unavailable");
  }
  return response.json().catch(() => null);
}

function firstValue(value) {
  return Array.isArray(value) ? value[0] : value;
}

async function completeWebTravelSetup(uid, homeAddress, opts = {}) {
  const address = normalizeHomeAddress(homeAddress);
  if (!address) throw webError(400, "invalid_home_address");
  if (!WEB_UID_RE.test(String(uid || ""))) throw webError(401, "unauthorized");

  const activeCalendar = await readActiveCalendarUser(uid, opts);
  if (activeCalendar.status !== "ACTIVE") throw webError(409, "calendar_not_active");

  const result = firstValue(await rpc("complete_lm_web_travel_setup", {
    p_uid: uid,
    p_home_address: address,
    p_calendar_account_id: activeCalendar.row.calendar_connected_account_id,
  }, opts));
  const trialExpiresAt = typeof result === "string" ? result : result && result.trial_expires_at;
  if (typeof trialExpiresAt !== "string" || !Number.isFinite(Date.parse(trialExpiresAt))) {
    throw webError(502, "setup_readback_unavailable");
  }
  return { trialExpiresAt };
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

function baseSnapshot(row, setupState, calendarState) {
  return {
    setupState,
    calendarState,
    nextEvent: null,
    travelBlock: null,
    departureAt: null,
    trialExpiresAt: row && row.trial_expires_at || null,
    paid: row && typeof row.paid === "boolean" ? row.paid : null,
  };
}

async function buildTodaySnapshot(uid, opts = {}) {
  if (!WEB_UID_RE.test(String(uid || ""))) throw webError(401, "unauthorized");
  let current;
  try { current = await readActiveCalendarUser(uid, opts); }
  catch (error) {
    if (error && error.code === "calendar_status_unavailable") {
      return baseSnapshot(error.userRow, "sync_pending", "unavailable");
    }
    throw error;
  }
  const { row, status } = current;
  if (status !== "ACTIVE") return baseSnapshot(row, "needs_calendar", "action_required");

  const nowMs = opts.nowMs == null ? Date.now() : opts.nowMs;
  // The selected account's exact ACTIVE result above is still current only if its marker is unchanged.
  // Re-read that row and run Task 2's NULL-Telegram check immediately before the Calendar event read.
  const beforeReadRow = await readWebUserRow(uid, opts);
  await assertUnbound(uid, opts);
  if (beforeReadRow.calendar_provider !== "composio_gcal"
    || beforeReadRow.calendar_connected_account_id !== row.calendar_connected_account_id) {
    return baseSnapshot(beforeReadRow, "needs_calendar", "action_required");
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
    return baseSnapshot(beforeReadRow, "sync_pending", "connected");
  }
  const ordered = events.slice().sort((a, b) => a.startMs - b.startMs);
  const nextEvent = ordered.find((event) => event.startMs >= nowMs && !isTravel(event.summary)) || null;
  const matches = matchingTravelBlocks(ordered, nextEvent);
  const travel = matches.length === 1 ? matches[0] : null;
  const snapshot = baseSnapshot(beforeReadRow, "ready", "connected");
  snapshot.nextEvent = eventSnapshot(nextEvent);
  snapshot.travelBlock = eventSnapshot(travel);
  snapshot.departureAt = travel && Number.isFinite(travel.startMs) ? new Date(travel.startMs).toISOString() : null;

  const home = String(beforeReadRow.home_address || "").trim();
  if (matches.length > 1) snapshot.setupState = "sync_pending";
  else if (!home) snapshot.setupState = "needs_home";
  else if (nextEvent && nextEvent.location) {
    const before = ordered.filter((event) => event.startMs < nextEvent.startMs && !isTravel(event.summary)).at(-1) || null;
    if (travelDecision(nextEvent, before, home).insert && !travel) snapshot.setupState = "sync_pending";
  }
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

async function travelOwnerOnce(user, opts = {}) {
  const run = opts.travelUserOnceImpl || require("../scheduler.js").travelUserOnce;
  return run(user);
}

async function handleWebTravelRequest(req, res, opts = {}) {
  const url = requestUrl(req);
  if (![SETUP_PATH, TODAY_PATH].includes(url.pathname)) return sendJson(res, 404, { error: "not_found" });
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

  try {
    const homeAddress = normalizeHomeAddress(body.homeAddress);
    if (!homeAddress) throw webError(400, "invalid_home_address");
    await completeWebTravelSetup(uid, homeAddress, opts);

    // Confirm the selected account is still ACTIVE after the atomic setup transition, then use the
    // existing shared owner once. A second exact read below decides whether any helper is reportable.
    let activeForSync;
    try { activeForSync = await readActiveCalendarUser(uid, opts); }
    catch (error) {
      if (!error || error.code !== "calendar_status_unavailable") throw error;
    }
    const { row, status } = activeForSync || {};
    let travelResult = null;
    if (status === "ACTIVE") {
      await assertUnbound(uid, opts);
      try {
        travelResult = await travelOwnerOnce({
          uid,
          home_address: homeAddress,
          call_time_zone: null,
          daily_automation_enabled: true,
          call_enabled: false,
          notifications_enabled: false,
          telegram_chat_id: null,
          expectedCalendarAccountId: row.calendar_connected_account_id,
        }, opts);
      } catch { /* the strict post-run Calendar read remains the success boundary */ }
    }
    const snapshot = await buildTodaySnapshot(uid, opts);
    return sendJson(res, 200, { ...snapshot, syncState: syncState(snapshot, travelResult) });
  } catch (error) {
    const status = Number.isInteger(error && error.status) ? error.status : 502;
    return sendJson(res, status, { error: status < 500 ? error.code : "setup_unavailable" });
  }
}

module.exports = {
  SETUP_PATH,
  TODAY_PATH,
  buildTodaySnapshot,
  completeWebTravelSetup,
  handleWebTravelRequest,
};
