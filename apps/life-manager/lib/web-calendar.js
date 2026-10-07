"use strict";

const crypto = require("node:crypto");
const { resolveWebUser } = require("./web-auth.js");
const { startCalendarOAuth } = require("./user-command.js");
const { readWebTravelControlState } = require("./runtime-preferences.js");

const STATUS_PATH = "/api/lm-web/calendar/status";
const START_PATH = "/api/lm-web/calendar/start";
const CALLBACK_PATH = "/lm/oauth/calendar/callback";
const STATE_TTL_MS = 5 * 60 * 1000;
const STATE_RE = /^[A-Za-z0-9_-]{43}$/;
const ACCOUNT_ID_RE = /^[A-Za-z0-9_-]{3,128}$/;
const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ENABLE_CLAIM_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ENABLE_REQUEST_TIMEOUT_MS = 20_000;
const OAUTH_STATUSES = new Set(["ACTIVE", "MISSING", "EXPIRED", "DISABLED", "INACTIVE"]);

function sendJson(res, status, body, extra = {}) {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    ...extra,
  });
  res.end(JSON.stringify(body));
}

function sendText(res, status, value, extra = {}) {
  res.writeHead(status, {
    "content-type": "text/plain; charset=utf-8",
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
    ...extra,
  });
  res.end(value);
}

function requestUrl(req) {
  try { return new URL(String(req && req.url || "/"), "http://life-manager.local"); }
  catch { return new URL("/", "http://life-manager.local"); }
}

function configuredOrigin(opts = {}) {
  const env = opts.env && typeof opts.env === "object" ? opts.env : process.env;
  const value = String(opts.publicOrigin || opts.panelOrigin || opts.panelBaseUrl
    || env.LM_PANEL_BASE_URL || (env.RAILWAY_PUBLIC_DOMAIN ? `https://${env.RAILWAY_PUBLIC_DOMAIN}` : ""));
  if (!value || value !== value.trim()) return "";
  try {
    const parsed = new URL(value);
    if ((parsed.protocol !== "https:" && !(parsed.protocol === "http:" && ["localhost", "127.0.0.1"].includes(parsed.hostname)))
      || parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) return "";
    return parsed.origin;
  } catch { return ""; }
}

function validCsrf(req, user) {
  const received = Buffer.from(String(req.headers && req.headers["x-lm-web-csrf"] || ""));
  const expected = Buffer.from(String(user && user.csrf || ""));
  return received.length > 0 && received.length === expected.length && crypto.timingSafeEqual(received, expected);
}

function jsonContentType(req) {
  return /^application\/json(?:\s*;|$)/i.test(String(req.headers && req.headers["content-type"] || ""));
}

function stateHash(state) {
  return crypto.createHash("sha256").update(state).digest("hex");
}

function parseOAuthState(searchParams) {
  let state = "", count = 0;
  for (const [key, value] of searchParams) {
    if (!key.toLowerCase().startsWith("state")) continue;
    if (key !== "state" || ++count > 1) return "";
    state = value;
  }
  return count === 1 && STATE_RE.test(state) ? state : "";
}

function panelApi() {
  return require("./panel-api.js");
}

function storeError(message, status) {
  const error = new Error(message);
  error.status = status;
  return error;
}

async function rpc(name, body, opts = {}) {
  const base = String(opts.supaUrl || "").replace(/\/$/, "");
  if (!base || !opts.supaKey) throw new Error("oauth_state_unavailable");
  const response = await (opts.fetchImpl || fetch)(`${base}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: { apikey: opts.supaKey, Authorization: `Bearer ${opts.supaKey}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    const message = String(failure && failure.message || "");
    if (message.includes("calendar_disconnect_pending")) throw storeError("calendar_disconnect_pending", 409);
    if (message.includes("calendar_enable_pending")) throw storeError("calendar_enable_pending", 409);
    if (message.includes("calendar_operation_pending")) throw storeError("calendar_operation_pending", 409);
    if (message.includes("calendar_account_changed")) throw storeError("calendar_account_changed", 409);
    throw new Error("oauth_state_unavailable");
  }
  return response.json().catch(() => null);
}

function firstValue(value) {
  return Array.isArray(value) ? value[0] : value;
}

async function readCalendarControlState(uid, opts = {}) {
  const readState = opts.readWebTravelControlStateImpl || readWebTravelControlState;
  const state = await readState(uid, opts);
  if (!state || typeof state.disconnectPending !== "boolean" || typeof state.enablePending !== "boolean") {
    throw storeError("calendar_control_state_unavailable", 503);
  }
  if (state.enablePending && (!ENABLE_CLAIM_ID_RE.test(String(state.enableClaimId || ""))
    || typeof state.enableClaimedAt !== "string" || !Number.isFinite(Date.parse(state.enableClaimedAt)))) {
    throw storeError("calendar_control_state_unavailable", 503);
  }
  return state;
}

async function calendarEnableClaim(name, uid, accountId, claimId, opts = {}, newClaimId = null) {
  const body = {
    p_uid: uid,
    p_calendar_account_id: accountId,
  };
  if (name === "recover_lm_web_calendar_enable") {
    body.p_expected_claim_id = claimId;
    body.p_new_claim_id = newClaimId;
  } else {
    body.p_claim_id = claimId;
  }
  const result = firstValue(await rpc(name, body, opts));
  if (result !== true) {
    const pending = name === "begin_lm_web_calendar_enable" || name === "recover_lm_web_calendar_enable";
    throw storeError(pending ? "calendar_enable_pending" : "calendar_enable_unconfirmed", 409);
  }
  return true;
}

function createWebCalendarStore(opts = {}) {
  return {
    async createWebOAuthState(scope, state) {
      const result = firstValue(await rpc("create_lm_web_calendar_oauth_state", {
        p_state_hash: state.stateHash,
        p_uid: scope.uid,
        p_provider: state.provider,
        p_expires_at: state.expiresAt,
      }, opts));
      if (result !== true) throw storeError("oauth_state_in_progress", 409);
      return true;
    },
    async attachWebOAuthAccount(scope, stateHashValue, connectedAccountId) {
      const result = firstValue(await rpc("attach_lm_web_calendar_oauth_account", {
        p_state_hash: stateHashValue,
        p_uid: scope.uid,
        p_connected_account_id: connectedAccountId,
      }, opts));
      return result === true;
    },
    async claimWebOAuthAccount(scope, stateHashValue) {
      const result = firstValue(await rpc("claim_lm_web_calendar_oauth_account", {
        p_state_hash: stateHashValue,
        p_uid: scope.uid,
      }, opts));
      return result == null ? null : String(result);
    },
  };
}

function serviceHeaders(key, extra = {}) {
  return { apikey: key, Authorization: `Bearer ${key}`, ...extra };
}

async function assertWebUserUnbound(uid, opts = {}) {
  const base = String(opts.supaUrl || "").replace(/\/$/, "");
  if (!base || !opts.supaKey) return false;
  const url = new URL(`${base}/rest/v1/lm_users`);
  url.searchParams.set("uid", `eq.${uid}`);
  url.searchParams.set("telegram_chat_id", "is.null");
  url.searchParams.set("select", "uid,telegram_chat_id");
  url.searchParams.set("limit", "2");
  const response = await (opts.fetchImpl || fetch)(url.toString(), { headers: serviceHeaders(opts.supaKey) });
  if (!response.ok) throw new Error("web_user_read_failed");
  const rows = await response.json().catch(() => []);
  const row = Array.isArray(rows) ? rows[0] : null;
  return Boolean(row && row.uid === uid && row.telegram_chat_id === null);
}

function userRowsUrl(uid, opts = {}) {
  const base = String(opts.supaUrl || "").replace(/\/$/, "");
  if (!base || !opts.supaKey) throw new Error("calendar_binding_unavailable");
  const url = new URL(`${base}/rest/v1/lm_users`);
  url.searchParams.set("uid", `eq.${uid}`);
  url.searchParams.set("telegram_chat_id", "is.null");
  url.searchParams.set("select", "uid,telegram_chat_id,calendar_provider,calendar_connected_account_id");
  url.searchParams.set("limit", "1");
  return url;
}

async function readCalendarBinding(uid, opts = {}) {
  const response = await (opts.fetchImpl || fetch)(userRowsUrl(uid, opts).toString(), {
    headers: serviceHeaders(opts.supaKey),
  });
  if (!response.ok) throw new Error("calendar_binding_unavailable");
  const rows = await response.json().catch(() => []);
  const row = Array.isArray(rows) ? rows[0] : null;
  if (!row || row.uid !== uid || row.telegram_chat_id !== null
    || !Object.hasOwn(row, "calendar_provider") || !Object.hasOwn(row, "calendar_connected_account_id")) return null;
  return row;
}

function calendarBindingMatches(row, uid, connectedAccountId) {
  return Boolean(row && row.uid === uid && row.telegram_chat_id === null
    && row.calendar_provider === "composio_gcal"
    && row.calendar_connected_account_id === connectedAccountId);
}

function calendarMarkerUnchanged(before, after, uid) {
  return Boolean(before && after && before.uid === uid && after.uid === uid
    && before.telegram_chat_id === null && after.telegram_chat_id === null
    && before.calendar_provider === after.calendar_provider
    && before.calendar_connected_account_id === after.calendar_connected_account_id);
}

async function persistCalendarBinding(uid, connectedAccountId, opts = {}, expectedBinding = null) {
  const before = expectedBinding || await readCalendarBinding(uid, opts);
  if (!before) throw new Error("calendar_binding_write_failed");
  const result = firstValue(await rpc("bind_lm_web_calendar_account", {
    p_uid: uid,
    p_connected_account_id: connectedAccountId,
    p_expected_calendar_provider: before.calendar_provider,
    p_expected_calendar_account_id: before.calendar_connected_account_id,
  }, opts));
  if (result !== true) throw new Error("calendar_binding_write_failed");

  const readback = await readCalendarBinding(uid, opts);
  if (!calendarBindingMatches(readback, uid, connectedAccountId)) throw new Error("calendar_binding_readback_failed");
}

function providerOptions(opts, origin) {
  const env = opts.env && typeof opts.env === "object" ? opts.env : process.env;
  return {
    ...opts,
    panelBaseUrl: opts.panelBaseUrl || origin,
    composioKey: opts.composioKey || env.COMPOSIO_API_KEY,
    composioAuthConfig: opts.composioAuthConfig || env.COMPOSIO_GCAL_AUTH_CONFIG,
  };
}

function allowedStatus(value) {
  return OAUTH_STATUSES.has(String(value || ""));
}

async function verifyCalendarBinding(uid, binding, provider) {
  const accountId = String(binding && binding.calendar_connected_account_id || "");
  if (!binding || binding.calendar_provider !== "composio_gcal" || !ACCOUNT_ID_RE.test(accountId)) return null;
  const status = await (provider.composioCalendarAccountStatusImpl || panelApi().composioCalendarAccountStatus)(
    { uid }, accountId, provider,
  );
  if (!allowedStatus(status)) throw new Error("calendar_status_unavailable");
  const current = await readCalendarBinding(uid, provider);
  return calendarMarkerUnchanged(binding, current, uid) ? { accountId, status } : null;
}

async function resolveActiveWebCalendar(uid, opts = {}) {
  if (!WEB_UID_RE.test(String(uid || ""))) return null;
  const provider = providerOptions(opts, configuredOrigin(opts));
  const binding = await readCalendarBinding(uid, provider);
  const current = await verifyCalendarBinding(uid, binding, provider);
  return current && current.status === "ACTIVE" ? { accountId: current.accountId } : null;
}

function exactCalendarAccount(uid, item) {
  const owner = item && (item.user_id || item.userId || item.connection?.user_id);
  const toolkit = item && (item.toolkit_slug || item.toolkit?.slug || item.toolkit?.slug_name);
  return Boolean(item && item.id && String(owner) === uid && toolkit === "googlecalendar");
}

async function listCalendarAccounts(uid, provider) {
  let accounts;
  if (typeof provider.composioCalendarAccountsImpl === "function") {
    accounts = await provider.composioCalendarAccountsImpl({ uid }, provider);
  } else {
    if (!provider.composioKey) throw new Error("provider_unavailable");
    const response = await (provider.fetchImpl || fetch)(
      `https://backend.composio.dev/api/v3/connected_accounts?user_ids=${encodeURIComponent(uid)}&toolkit_slugs=googlecalendar`,
      { headers: { "x-api-key": provider.composioKey } },
    );
    if (!response.ok) throw new Error("provider_failed");
    const body = await response.json().catch(() => ({}));
    accounts = Array.isArray(body && body.items) ? body.items : [];
  }
  if (!Array.isArray(accounts) || accounts.some((account) => !exactCalendarAccount(uid, account))) {
    throw new Error("provider_ownership");
  }
  return accounts.filter((account) => account.status !== "EXPIRED");
}

function validRedirectUrl(value) {
  if (typeof value !== "string" || /[\r\n]/.test(value)) return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password && url.origin !== "null";
  } catch { return false; }
}

async function handleStatus(scope, res, provider) {
  const controlState = await readCalendarControlState(scope.uid, provider);
  const active = await resolveActiveWebCalendar(scope.uid, provider);
  if (controlState.enablePending) {
    return sendJson(res, 200, { connected: false, state: "enable_pending", enablePending: true });
  }
  if (active) return sendJson(res, 200, { connected: true, state: "connected" });
  return sendJson(res, 200, { connected: false, state: "action_required" });
}

async function startCalendar(scope, req, res, opts, origin) {
  if (!origin || String(req.headers && req.headers.origin || "") !== origin) return sendJson(res, 403, { error: "origin_rejected" });
  if (!jsonContentType(req)) return sendJson(res, 415, { error: "json_required" });
  if (!validCsrf(req, opts.user)) return sendJson(res, 403, { error: "csrf_rejected" });

  let body;
  try { body = await (opts.readJsonImpl || panelApi().readJson)(req); }
  catch (error) { return sendJson(res, error && error.status === 413 ? 413 : 400, { error: "invalid_json" }); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return sendJson(res, 400, { error: "invalid_json" });
  if (!await (opts.assertWebUserUnboundImpl || assertWebUserUnbound)(scope.uid, opts)) {
    return sendJson(res, 403, { error: "unauthorized" });
  }

  const provider = providerOptions(opts, origin);
  const controlState = await readCalendarControlState(scope.uid, provider);
  if (controlState.disconnectPending) return sendJson(res, 409, { error: "disconnect_pending" });
  const binding = await readCalendarBinding(scope.uid, provider);
  const current = await verifyCalendarBinding(scope.uid, binding, provider);
  let enablePending = controlState.enablePending;
  let enableClaimId = controlState.enableClaimId || null;
  if (enablePending) {
    if (current && current.status === "ACTIVE") {
      await calendarEnableClaim("finish_lm_web_calendar_enable", scope.uid, current.accountId, enableClaimId, provider);
      enablePending = false;
      enableClaimId = null;
    } else if (current && ["DISABLED", "MISSING", "EXPIRED"].includes(current.status)) {
      const recoveredClaimId = crypto.randomUUID();
      await calendarEnableClaim("recover_lm_web_calendar_enable", scope.uid, current.accountId,
        enableClaimId, provider, recoveredClaimId);
      enableClaimId = recoveredClaimId;
      if (current.status === "MISSING" || current.status === "EXPIRED") {
        await calendarEnableClaim("finish_lm_web_calendar_enable", scope.uid, current.accountId, enableClaimId, provider);
        enablePending = false;
        enableClaimId = null;
      }
    } else {
      return sendJson(res, 409, { error: "calendar_enable_pending" });
    }
  }
  if (current && current.status === "ACTIVE") {
    return sendJson(res, 200, { connected: true, state: "connected" });
  }
  if (current && current.status === "DISABLED") {
    if (!await (opts.assertWebUserUnboundImpl || assertWebUserUnbound)(scope.uid, opts)) {
      return sendJson(res, 403, { error: "unauthorized" });
    }
    if (!enablePending) {
      enableClaimId = crypto.randomUUID();
      await calendarEnableClaim("begin_lm_web_calendar_enable", scope.uid, current.accountId, enableClaimId, provider);
      enablePending = true;
    }
    let resumed;
    try {
      resumed = await (provider.composioCalendarStartImpl || panelApi().composioCalendarStart)(scope, {
        ...provider, connectedAccountId: current.accountId, requireExplicitDisabled: true,
      });
    } catch (error) {
      if (error && error.calendarEnableEffect === "no_effect") {
        await calendarEnableClaim("finish_lm_web_calendar_enable", scope.uid, current.accountId, enableClaimId, provider);
        enablePending = false;
        enableClaimId = null;
      }
      throw error;
    }
    if (resumed && (resumed.state === "connected" || resumed.connected === true)) {
      const activeStatus = await (provider.composioCalendarAccountStatusImpl || panelApi().composioCalendarAccountStatus)(
        scope, current.accountId, { ...provider, signal: AbortSignal.timeout(ENABLE_REQUEST_TIMEOUT_MS) },
      );
      if (activeStatus !== "ACTIVE") throw new Error("provider_readback_failed");
      await calendarEnableClaim("finish_lm_web_calendar_enable", scope.uid, current.accountId, enableClaimId, provider);
      const latestBinding = await readCalendarBinding(scope.uid, provider);
      if (!calendarMarkerUnchanged(binding, latestBinding, scope.uid)) throw new Error("calendar_binding_readback_failed");
      return sendJson(res, 200, { connected: true, state: "connected" });
    }
    return sendJson(res, 409, { error: "calendar_enable_pending" });
  }
  if (enablePending) {
    return sendJson(res, 409, { error: "calendar_enable_pending" });
  }

  const activeAccounts = (await listCalendarAccounts(scope.uid, provider)).filter((account) =>
    account.status === "ACTIVE" && account.is_disabled !== true
      && (account.enabled === undefined || account.enabled === true));
  if (activeAccounts.length > 1) throw new Error("provider_ambiguous");
  if (activeAccounts.length === 1) {
    const accountId = String(activeAccounts[0].id || "");
    if (!ACCOUNT_ID_RE.test(accountId)) throw new Error("provider_unavailable");
    if (await (provider.composioCalendarAccountStatusImpl || panelApi().composioCalendarAccountStatus)(scope, accountId, provider) === "ACTIVE") {
      if (!await (opts.assertWebUserUnboundImpl || assertWebUserUnbound)(scope.uid, opts)) {
        return sendJson(res, 403, { error: "unauthorized" });
      }
      const latestBinding = await readCalendarBinding(scope.uid, provider);
      if (!calendarMarkerUnchanged(binding, latestBinding, scope.uid)) {
        return sendJson(res, 200, { connected: false, state: "action_required" });
      }
      await persistCalendarBinding(scope.uid, accountId, provider, binding);
      return sendJson(res, 200, { connected: true, state: "connected" });
    }
  }

  const bytes = (opts.randomBytes || crypto.randomBytes)(32);
  const state = bytes.toString("base64url");
  if (!STATE_RE.test(state)) throw new Error("invalid_state");
  const digest = stateHash(state);
  const store = opts.webCalendarStore || createWebCalendarStore(provider);
  const stateRecord = {
    stateHash: digest,
    provider: "calendar",
    expiresAt: new Date((opts.nowMs == null ? Date.now() : opts.nowMs) + STATE_TTL_MS).toISOString(),
  };
  try {
    const created = await store.createWebOAuthState(scope, stateRecord);
    if (created !== true) return sendJson(res, 409, { error: "calendar_in_progress" });
  } catch (error) {
    if (error && (error.status === 409 || error.message === "oauth_state_in_progress")) {
      return sendJson(res, 409, { error: "calendar_in_progress" });
    }
    throw error;
  }

  if (!await (opts.assertWebUserUnboundImpl || assertWebUserUnbound)(scope.uid, opts)) {
    return sendJson(res, 403, { error: "unauthorized" });
  }
  const finalControlState = await readCalendarControlState(scope.uid, provider);
  if (finalControlState.disconnectPending || finalControlState.enablePending) {
    return sendJson(res, 409, { error: finalControlState.disconnectPending ? "disconnect_pending" : "calendar_enable_pending" });
  }
  const oauth = await (provider.startCalendarOAuthImpl || startCalendarOAuth)(scope, state, {
    ...provider,
    calendarCallbackPath: CALLBACK_PATH,
  });
  const accountId = String(oauth && oauth.connectedAccountId || "");
  if (!oauth || !ACCOUNT_ID_RE.test(accountId) || !validRedirectUrl(oauth.redirectUrl)
    || typeof store.attachWebOAuthAccount !== "function"
    || !await store.attachWebOAuthAccount(scope, digest, accountId)) throw new Error("oauth_account_bind_failed");
  return sendJson(res, 200, { connected: false, state: "action_required", redirectUrl: oauth.redirectUrl });
}

async function handleCallback(scope, req, res, opts, url) {
  if (req.method !== "GET") return sendJson(res, 405, { error: "method_not_allowed" }, { Allow: "GET" });
  const state = parseOAuthState(url.searchParams);
  if (!state) return sendText(res, 403, "calendar connection not verified");
  const provider = providerOptions(opts, configuredOrigin(opts));
  const controlState = await readCalendarControlState(scope.uid, provider);
  if (controlState.disconnectPending || controlState.enablePending) {
    return sendText(res, 403, "calendar connection not verified");
  }
  const store = opts.webCalendarStore || createWebCalendarStore(provider);
  const accountId = String(await store.claimWebOAuthAccount(scope, stateHash(state)) || "");
  if (!ACCOUNT_ID_RE.test(accountId)) return sendText(res, 403, "calendar connection expired");
  if (!await (opts.assertWebUserUnboundImpl || assertWebUserUnbound)(scope.uid, opts)) {
    return sendText(res, 403, "calendar connection not verified");
  }
  const binding = await readCalendarBinding(scope.uid, provider);

  let status;
  try {
    status = await (provider.composioCalendarAccountStatusImpl || panelApi().composioCalendarAccountStatus)(scope, accountId, provider);
  } catch (error) {
    if (error && error.message === "provider_ownership") return sendText(res, 403, "calendar connection not verified");
    throw error;
  }
  if (status !== "ACTIVE") return sendText(res, 403, "calendar connection not verified");
  await persistCalendarBinding(scope.uid, accountId, provider, binding);
  res.writeHead(303, { Location: "/lm?initial_scan=1", "cache-control": "no-store", "referrer-policy": "no-referrer" });
  res.end();
}

async function handleWebCalendarRequest(req, res, opts = {}) {
  const url = requestUrl(req);
  if (![STATUS_PATH, START_PATH, CALLBACK_PATH].includes(url.pathname)) return sendJson(res, 404, { error: "not_found" });
  let user = null;
  try { user = await (opts.resolveWebUserImpl || resolveWebUser)(req, res, opts); } catch {}
  if (!user || !WEB_UID_RE.test(String(user.uid || ""))) return sendJson(res, 401, { error: "unauthorized" });
  const scope = { uid: String(user.uid) };

  try {
    const unbound = await (opts.assertWebUserUnboundImpl || assertWebUserUnbound)(scope.uid, opts);
    if (!unbound) return sendJson(res, 403, { error: "unauthorized" });
    if (url.pathname === STATUS_PATH) {
      if (req.method !== "GET") return sendJson(res, 405, { error: "method_not_allowed" }, { Allow: "GET" });
      return await handleStatus(scope, res, providerOptions(opts, configuredOrigin(opts)));
    }
    if (url.pathname === START_PATH) {
      if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" }, { Allow: "POST" });
      return await startCalendar(scope, req, res, { ...opts, user }, configuredOrigin(opts));
    }
    return await handleCallback(scope, req, res, opts, url);
  } catch (error) {
    if (error && error.status === 409 && error.message === "calendar_enable_pending") {
      return sendJson(res, 409, { error: "calendar_enable_pending" });
    }
    if (error && Number.isInteger(error.status) && error.status >= 400 && error.status < 500) {
      return sendJson(res, error.status, { error: "calendar_unavailable" });
    }
    return sendJson(res, 502, { error: "calendar_unavailable" });
  }
}

module.exports = {
  CALLBACK_PATH,
  START_PATH,
  STATE_TTL_MS,
  STATUS_PATH,
  createWebCalendarStore,
  assertWebUserUnbound,
  resolveActiveWebCalendar,
  handleWebCalendarRequest,
};
