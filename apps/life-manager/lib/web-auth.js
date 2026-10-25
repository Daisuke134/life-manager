"use strict";

const { createHash, createHmac } = require("node:crypto");
const {
  WEB_ATTRIBUTION_COOKIE,
  WEB_ATTRIBUTION_MAX_AGE_SECONDS,
  WEB_ATTRIBUTION_UTM_KEYS,
  captureWebAttribution,
  consumeWebAttribution,
  sanitizeWebAttribution,
} = require("./web-attribution.js");
const { recordWebFunnelEvent } = require("./web-funnel-events.js");

const WEB_AUTH_COOKIE = "lm-web-auth";
const GOOGLE_OAUTH_INTENT_COOKIE = "lm-web-auth-intent";
const GOOGLE_OAUTH_CALLBACK_PATH = "/auth/google/callback";
const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function envFor(opts) {
  return opts && opts.env && typeof opts.env === "object" ? opts.env : process.env;
}

function requiredSupabaseUrl(opts = {}) {
  const env = envFor(opts);
  const value = String(opts.supabaseUrl || env.SUPABASE_URL || "").trim().replace(/\/+$/, "");
  if (!value) throw new Error("SUPABASE_URL is required");
  let parsed;
  try { parsed = new URL(value); } catch { throw new Error("SUPABASE_URL is invalid"); }
  if (!/^https?:$/.test(parsed.protocol) || parsed.username || parsed.password
    || (parsed.protocol !== "https:" && !["localhost", "127.0.0.1"].includes(parsed.hostname))) {
    throw new Error("SUPABASE_URL is invalid");
  }
  return value;
}

function jwtRole(key) {
  const parts = String(key || "").split(".");
  if (parts.length !== 3) return "";
  try {
    const claims = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
    return String(claims.role || "");
  } catch {
    return "";
  }
}

function isServiceRoleKey(key) {
  return String(key || "").startsWith("sb_secret_") || jwtRole(key) === "service_role";
}

function requiredAnonKey(opts = {}) {
  const env = envFor(opts);
  const key = String(opts.anonKey || env.SUPABASE_ANON_KEY || "").trim();
  if (!key) throw new Error("SUPABASE_ANON_KEY is required");
  const serviceRoleKey = String(opts.serviceRoleKey || env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  if (key === serviceRoleKey || isServiceRoleKey(key)) {
    throw new Error("SUPABASE_ANON_KEY must be a public key, not a service-role key");
  }
  return key;
}

function requiredServiceRoleKey(opts = {}) {
  const env = envFor(opts);
  const key = String(opts.serviceRoleKey || env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  if (!key) throw new Error("SUPABASE_SERVICE_ROLE_KEY is required");
  const anonKey = String(opts.anonKey || env.SUPABASE_ANON_KEY || "").trim();
  if (key === anonKey || key.startsWith("sb_publishable_") || !isServiceRoleKey(key)) {
    throw new Error("SUPABASE_SERVICE_ROLE_KEY must be separate from the public anon key");
  }
  return key;
}

function ssrFor(opts = {}) {
  return opts.ssr || require("@supabase/ssr");
}

function authCookieName(opts = {}) {
  return String(opts.authCookieName || WEB_AUTH_COOKIE);
}

function cookieOptions(opts = {}) {
  const env = envFor(opts);
  const secure = opts.secureCookies === true
    || (opts.secureCookies !== false && env.NODE_ENV !== "test" && env.NODE_ENV !== "development");
  return {
    name: authCookieName(opts),
    path: "/",
    sameSite: "lax",
    httpOnly: true,
    secure,
  };
}

function applyResponseHeaders(res, headers) {
  if (!res || typeof res.setHeader !== "function" || !headers) return;
  const entries = typeof headers.entries === "function" ? headers.entries() : Object.entries(headers);
  for (const [name, value] of entries) res.setHeader(name, value);
}

function appendResponseCookies(res, cookies, serializeCookieHeader) {
  if (!res || typeof res.setHeader !== "function" || !Array.isArray(cookies)) return;
  const previous = typeof res.getHeader === "function" ? res.getHeader("set-cookie") : null;
  const values = Array.isArray(previous) ? previous.slice() : previous ? [previous] : [];
  for (const cookie of cookies) {
    if (!cookie || typeof cookie.name !== "string") continue;
    values.push(serializeCookieHeader(cookie.name, String(cookie.value || ""), cookie.options || {}));
  }
  if (values.length) res.setHeader("set-cookie", values);
}

function createWebAuthClient(req, res, opts = {}) {
  const url = requiredSupabaseUrl(opts);
  const anonKey = requiredAnonKey(opts);
  const ssr = ssrFor(opts);
  const serializeCookieHeader = opts.serializeCookieHeader || ssr.serializeCookieHeader;
  if (typeof ssr.createServerClient !== "function"
    || typeof ssr.parseCookieHeader !== "function"
    || typeof serializeCookieHeader !== "function") {
    throw new Error("Supabase SSR cookie adapter unavailable");
  }
  const cookies = {
    getAll() {
      return ssr.parseCookieHeader(String(req && req.headers && req.headers.cookie || ""));
    },
    setAll(cookiesToSet, headers) {
      appendResponseCookies(res, cookiesToSet, serializeCookieHeader);
      applyResponseHeaders(res, headers);
    },
  };
  return ssr.createServerClient(url, anonKey, {
    auth: {
      flowType: "pkce",
      persistSession: true,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
    cookieOptions: cookieOptions(opts),
    cookies,
  });
}

function uidForSubject(subject) {
  const value = String(subject || "");
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (!uuid.test(value)) throw new Error("verified Supabase subject unavailable");
  return `lm_${value}`;
}

function separateWebUidForSubject(subject) {
  const value = String(subject || "");
  uidForSubject(value);
  const hex = createHash("sha256").update(`life-manager:web-tenant:v1\0${value}`).digest("hex").slice(0, 32).split("");
  hex[12] = "8";
  hex[16] = (Number.parseInt(hex[16], 16) & 0x3 | 0x8).toString(16);
  const uuid = `${hex.slice(0, 8).join("")}-${hex.slice(8, 12).join("")}-${hex.slice(12, 16).join("")}-${hex.slice(16, 20).join("")}-${hex.slice(20, 32).join("")}`;
  return `lm_${uuid}`;
}

function createWebCsrfToken(uid, secret) {
  const tenantUid = String(uid || "");
  const key = String(secret || "");
  if (!WEB_UID_RE.test(tenantUid)) throw new Error("verified Web uid is required");
  if (!key) throw new Error("Web CSRF secret is required");
  return createHmac("sha256", key).update(`life-manager-web-csrf:v1\0${tenantUid}`).digest("hex");
}

function csrfSecret(opts = {}) {
  const env = envFor(opts);
  return String(opts.csrfSecret || env.LM_WEB_CSRF_SECRET || env.LM_PANEL_SESSION_ROTATION_SECRET || env.LM_UID_SECRET || "").trim();
}

function attributionSecret(opts = {}) {
  const env = envFor(opts);
  return String(env.LM_UID_SECRET || "").trim();
}

function attributionCookie(req, opts = {}) {
  const matches = requestCookies(req, opts).filter((cookie) => cookie && cookie.name === WEB_ATTRIBUTION_COOKIE);
  return { present: matches.length > 0, value: matches.length === 1 ? String(matches[0].value || "") : "" };
}

function setAttributionCookie(res, opts, value) {
  const serializer = opts.serializeCookieHeader || ssrFor(opts).serializeCookieHeader;
  if (typeof serializer !== "function") return;
  appendResponseCookies(res, [{
    name: WEB_ATTRIBUTION_COOKIE,
    value,
    options: {
      path: "/",
      sameSite: "lax",
      httpOnly: true,
      secure: cookieOptions(opts).secure,
      maxAge: WEB_ATTRIBUTION_MAX_AGE_SECONDS,
    },
  }], serializer);
}

function captureWebFirstTouchCookie(req, res, attribution, opts = {}) {
  const existing = attributionCookie(req, opts);
  const secret = attributionSecret(opts);
  if (consumeWebAttribution(existing.value, secret)) return;
  const cookie = captureWebAttribution(attribution, secret);
  if (cookie) setAttributionCookie(res, opts, cookie);
}
function readWebFirstTouchCookie(req, opts = {}) {
  return consumeWebAttribution(attributionCookie(req, opts).value, attributionSecret(opts)) || {};
}

function matchesAttribution(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const actualKeys = Object.keys(value).sort();
  const expectedKeys = Object.keys(expected).sort();
  return actualKeys.length === expectedKeys.length
    && actualKeys.every((key, index) => key === expectedKeys[index] && value[key] === expected[key]);
}

function isUnboundWebRow(row, uid) {
  return Boolean(row && row.uid === uid
    && Object.prototype.hasOwnProperty.call(row, "telegram_chat_id")
    && row.telegram_chat_id === null);
}

function hasVerifiedGoogleIdentity(user) {
  if (!user || typeof user !== "object") return false;
  const appMetadata = user.app_metadata && typeof user.app_metadata === "object" ? user.app_metadata : {};
  const providers = [appMetadata.provider, ...(Array.isArray(appMetadata.providers) ? appMetadata.providers : [])];
  const identities = Array.isArray(user.identities) ? user.identities : [];
  return [...providers, ...identities.map((identity) => identity && identity.provider)]
    .some((provider) => String(provider || "").trim().toLowerCase() === "google");
}

async function readWebFirstTouchRow(uid, fetchImpl, root, key) {
  const response = await fetchImpl(
    `${root}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}&select=uid,telegram_chat_id,web_first_touch&limit=2`,
    { headers: serviceHeaders(key) },
  );
  if (!response || !response.ok) throw new Error("Web first-touch readback failed");
  const rows = await response.json();
  if (!Array.isArray(rows) || rows.length !== 1) return false;
  const row = rows[0];
  return isUnboundWebRow(row, uid) ? row : null;
}

async function readWebFirstTouch(uid, fetchImpl, root, key) {
  const row = await readWebFirstTouchRow(uid, fetchImpl, root, key);
  return Boolean(row && row.web_first_touch != null);
}
async function readWebFirstTouchValue(uid, opts = {}) {
  if (!WEB_UID_RE.test(String(uid || ""))) throw new Error("verified Web uid is required");
  const row = await readWebFirstTouchRow(uid, opts.fetch || globalThis.fetch, requiredSupabaseUrl(opts), requiredServiceRoleKey(opts));
  return sanitizeWebAttribution(row?.web_first_touch);
}

async function storeWebFirstTouch(uid, attribution, opts = {}) {
  const fetchImpl = opts.fetch || globalThis.fetch;
  if (typeof fetchImpl !== "function") throw new Error("Supabase fetch unavailable");
  const root = requiredSupabaseUrl(opts);
  const key = requiredServiceRoleKey(opts);
  const response = await fetchImpl(
    `${root}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}&web_first_touch=is.null&telegram_chat_id=is.null&select=uid,telegram_chat_id,web_first_touch`,
    {
      method: "PATCH",
      headers: serviceHeaders(key, {
        "content-type": "application/json",
        Prefer: "return=representation",
      }),
      body: JSON.stringify({ web_first_touch: attribution }),
    },
  );
  if (!response || !response.ok) throw new Error("Web first-touch write failed");
  const rows = response.status === 204 ? [] : await response.json();
  if (!Array.isArray(rows) || rows.length > 1) return false;
  if (rows.length === 1) {
    const row = rows[0];
    return Boolean(isUnboundWebRow(row, uid)
      && matchesAttribution(row.web_first_touch, attribution));
  }
  return readWebFirstTouch(uid, fetchImpl, root, key);
}

async function resolveWebUser(req, res, opts = {}) {
  try {
    const client = createWebAuthClient(req, res, opts);
    const result = await client.auth.getUser();
    const user = result && result.data && result.data.user;
    if (!user || result.error || !hasVerifiedGoogleIdentity(user)) return null;
    const subject = String(user.id || "");
    const uid = await resolveWebTenantUid(subject, opts);
    if (!uid) return null;
    const secret = csrfSecret(opts);
    if (!secret) return null;
    return { uid, subject, email: user.email || null, csrf: createWebCsrfToken(uid, secret) };
  } catch {
    return null;
  }
}

function rowUrl(root, uid) {
  return `${root}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}&select=uid,telegram_chat_id&limit=2`;
}

function serviceHeaders(key, extra = {}) {
  return { apikey: key, Authorization: `Bearer ${key}`, ...extra };
}

async function readWebUserRow(uid, opts, root, key) {
  const fetchImpl = opts.fetch || globalThis.fetch;
  if (typeof fetchImpl !== "function") throw new Error("Supabase fetch unavailable");
  const response = await fetchImpl(rowUrl(root, uid), { headers: serviceHeaders(key) });
  if (!response || !response.ok) throw new Error("Web user read failed");
  const rows = await response.json();
  if (!Array.isArray(rows) || rows.length > 1) throw new Error("Web user row unavailable");
  return rows[0] || null;
}

async function resolveWebTenantUid(subject, opts = {}) {
  const canonicalUid = uidForSubject(subject);
  const root = requiredSupabaseUrl(opts);
  const key = requiredServiceRoleKey(opts);
  const canonicalRow = await readWebUserRow(canonicalUid, opts, root, key);
  if (!canonicalRow) return canonicalUid;
  if (canonicalRow.telegram_chat_id === null) return canonicalUid;

  const separateUid = separateWebUidForSubject(subject);
  const separateRow = await readWebUserRow(separateUid, opts, root, key);
  return separateRow && separateRow.telegram_chat_id === null ? separateUid : null;
}

function rejectNonWebRow(row) {
  if (row && row.telegram_chat_id !== null) {
    const error = new Error("Web uid is not an unbound tenant");
    error.code = "web_tenant_bound";
    throw error;
  }
}

async function ensureWebUserRow(uid, opts, root, key, knownRow) {
  const existing = knownRow === undefined ? await readWebUserRow(uid, opts, root, key) : knownRow;
  if (existing) {
    rejectNonWebRow(existing);
    return uid;
  }

  const fetchImpl = opts.fetch || globalThis.fetch;
  const inserted = await fetchImpl(`${root}/rest/v1/lm_users?on_conflict=uid`, {
    method: "POST",
    headers: serviceHeaders(key, {
      "content-type": "application/json",
      Prefer: "resolution=ignore-duplicates,return=minimal",
    }),
    body: JSON.stringify({ uid }),
  });
  if (!inserted || !inserted.ok) throw new Error("Web user insert failed");
  const readback = await readWebUserRow(uid, opts, root, key);
  if (!readback) throw new Error("Web user insert readback unavailable");
  rejectNonWebRow(readback);
  return uid;
}

async function ensureWebUser(uid, opts = {}) {
  const supplied = String(uid || "");
  const subject = supplied.startsWith("lm_") ? supplied.slice(3) : supplied;
  const canonicalUid = uidForSubject(subject);
  const root = requiredSupabaseUrl(opts);
  const key = requiredServiceRoleKey(opts);
  const canonicalRow = await readWebUserRow(canonicalUid, opts, root, key);
  if (canonicalRow && canonicalRow.telegram_chat_id !== null) {
    return ensureWebUserRow(separateWebUidForSubject(subject), opts, root, key);
  }

  try {
    return await ensureWebUserRow(canonicalUid, opts, root, key, canonicalRow);
  } catch (error) {
    // A Telegram onboarding can create the canonical row between our read and insert.
    if (!error || error.code !== "web_tenant_bound") throw error;
    return ensureWebUserRow(separateWebUidForSubject(subject), opts, root, key);
  }
}

function requestPath(req) {
  try { return new URL(String(req && req.url || "/"), "http://localhost").pathname; }
  catch { return "/"; }
}

function requestQuery(req) {
  try { return new URL(String(req && req.url || "/"), "http://localhost").searchParams; }
  catch { return new URLSearchParams(); }
}

function signedOutCalendarHandoffLocation(req) {
  if (String(req && req.method || "GET").toUpperCase() !== "GET" || requestPath(req) !== "/lm") return null;
  const query = requestQuery(req);
  const startFlags = query.getAll("start_calendar");
  if (startFlags.length !== 1 || startFlags[0] !== "1") return null;
  if (WEB_ATTRIBUTION_UTM_KEYS.some((key) => query.getAll(key).length > 1)) return null;
  const attribution = sanitizeWebAttribution(query);
  const search = new URLSearchParams(attribution).toString();
  return search ? `/auth/google?${search}` : "/auth/google";
}

function requestCookies(req, opts = {}) {
  const ssr = ssrFor(opts);
  if (typeof ssr.parseCookieHeader !== "function") throw new Error("Supabase SSR cookie parser unavailable");
  return ssr.parseCookieHeader(String(req && req.headers && req.headers.cookie || ""));
}

function hasPkceVerifier(req, opts = {}) {
  const name = `${authCookieName(opts)}-code-verifier`;
  return requestCookies(req, opts).some((cookie) => cookie && cookie.name === name && String(cookie.value || "").length > 0);
}

function publicOrigin(req, opts = {}) {
  const env = envFor(opts);
  const configured = String(opts.publicOrigin || env.LM_PANEL_BASE_URL || (env.RAILWAY_PUBLIC_DOMAIN ? `https://${env.RAILWAY_PUBLIC_DOMAIN}` : "")).trim();
  if (configured) {
    let parsed;
    try { parsed = new URL(configured); } catch { throw new Error("public Web origin is invalid"); }
    if (!/^https?:$/.test(parsed.protocol) || parsed.username || parsed.password
      || (parsed.protocol !== "https:" && !["localhost", "127.0.0.1"].includes(parsed.hostname))) {
      throw new Error("public Web origin is invalid");
    }
    return parsed.origin;
  }
  const host = req && req.headers && String(req.headers.host || "").trim();
  if (host && ["localhost", "127.0.0.1"].includes(host.split(":")[0])) return `http://${host}`;
  throw new Error("public Web origin unavailable");
}

function cloudPublicOrigin(req, opts = {}) {
  const env = envFor(opts);
  const configured = String(opts.cloudPublicOrigin || env.LM_MARITIME_WEB_ORIGIN || "").trim();
  if (!configured) throw new Error("Life Manager Cloud public origin is required");
  return publicOrigin(req, { ...opts, publicOrigin: configured });
}

function sendText(res, status, text) {
  if (!res.headersSent) {
    res.writeHead(status, {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    });
  }
  res.end(text);
}

function sendRedirect(res, location) {
  res.writeHead(302, { location, "cache-control": "no-store", "content-length": "0" });
  res.end();
}

function redirectToConnectionError(res, intent = null) {
  const language = intent === "maritime_cloud-ja" ? "ja"
    : intent === "maritime_cloud-en" ? "en" : null;
  sendRedirect(res, language
    ? "/maritime?auth_error=connection&lang=" + language
    : "/lm?auth_error=connection");
}

function clearCookie(res, opts, name) {
  const serializer = opts.serializeCookieHeader || ssrFor(opts).serializeCookieHeader;
  if (typeof serializer !== "function") return;
  const settings = cookieOptions(opts);
  delete settings.name;
  appendResponseCookies(res, [{ name, value: "", options: { ...settings, maxAge: 0, expires: new Date(0) } }], serializer);
}

function setGoogleOAuthIntentCookie(res, opts, intent) {
  const serializer = opts.serializeCookieHeader || ssrFor(opts).serializeCookieHeader;
  if (typeof serializer !== "function") return;
  const settings = cookieOptions(opts);
  delete settings.name;
  appendResponseCookies(res, [{ name: GOOGLE_OAUTH_INTENT_COOKIE, value: intent, options: {
    ...settings, path: GOOGLE_OAUTH_CALLBACK_PATH, maxAge: 600,
  } }], serializer);
}

function clearGoogleOAuthIntentCookie(res, opts) {
  const serializer = opts.serializeCookieHeader || ssrFor(opts).serializeCookieHeader;
  if (typeof serializer !== "function") return;
  const settings = cookieOptions(opts);
  delete settings.name;
  appendResponseCookies(res, [{ name: GOOGLE_OAUTH_INTENT_COOKIE, value: "", options: {
    ...settings, path: GOOGLE_OAUTH_CALLBACK_PATH, maxAge: 0, expires: new Date(0),
  } }], serializer);
}

function googleOAuthIntentFromQuery(query) {
  const intents = query.getAll("intent");
  const languages = query.getAll("lang");
  if (intents.length !== 1 || intents[0] !== "maritime_cloud" || languages.length > 1) return null;
  const language = String(languages[0] || "en").toLowerCase();
  return ["en", "ja"].includes(language) ? `maritime_cloud-${language}` : null;
}

function googleOAuthIntentFromCookie(req, opts) {
  let cookies;
  try { cookies = requestCookies(req, opts); } catch { return null; }
  const matching = cookies.filter((cookie) => cookie && cookie.name === GOOGLE_OAUTH_INTENT_COOKIE);
  if (matching.length !== 1 || !["maritime_cloud-en", "maritime_cloud-ja"].includes(String(matching[0].value || ""))) return null;
  return String(matching[0].value);
}

function responseCookieCleared(res, name) {
  const previous = typeof res.getHeader === "function" ? res.getHeader("set-cookie") : null;
  const values = Array.isArray(previous) ? previous : previous ? [previous] : [];
  const line = values.slice().reverse().map(String).find((value) => value.startsWith(`${name}=`));
  if (!line) return false;
  const value = line.slice(name.length + 1).split(";", 1)[0];
  return value === "" || /(?:^|;)\s*max-age=0(?:;|$)/i.test(line);
}

function responseCookieNames(res) {
  const previous = typeof res.getHeader === "function" ? res.getHeader("set-cookie") : null;
  const values = Array.isArray(previous) ? previous : previous ? [previous] : [];
  return values.map((header) => {
    const pair = String(header).split(";", 1)[0];
    const equals = pair.indexOf("=");
    return equals > 0 ? pair.slice(0, equals).trim() : "";
  }).filter(Boolean);
}

function isCookieOrChunk(name, base) {
  if (name === base) return true;
  const prefix = `${base}.`;
  return name.startsWith(prefix) && /^(0|[1-9][0-9]*)$/.test(name.slice(prefix.length));
}

function authCookieNames(req, res, opts) {
  const base = authCookieName(opts);
  const verifier = `${base}-code-verifier`;
  const names = new Set([base, verifier]);
  let requestNames = [];
  try { requestNames = requestCookies(req, opts).map((cookie) => cookie && cookie.name); } catch { /* base cookies still expire below */ }
  for (const name of [...requestNames, ...responseCookieNames(res)]) {
    if (typeof name === "string" && (isCookieOrChunk(name, base) || isCookieOrChunk(name, verifier))) names.add(name);
  }
  return names;
}

async function clearWebSession(client, req, res, opts) {
  try { await client.auth.signOut({ scope: "local" }); } catch { /* clear the local cookie below */ }
  for (const name of authCookieNames(req, res, opts)) {
    if (!responseCookieCleared(res, name)) clearCookie(res, opts, name);
  }
}

async function handleWebAuthRequest(req, res, opts = {}) {
  const path = requestPath(req);
  const method = String(req && req.method || "GET").toUpperCase();
  if (path !== "/auth/google" && path !== "/auth/google/callback") {
    sendText(res, 404, "not found");
    return;
  }
  if (method !== "GET") {
    res.writeHead(405, { allow: "GET", "cache-control": "no-store", "content-length": "0" });
    res.end();
    return;
  }

  if (path === "/auth/google") {
    const intent = googleOAuthIntentFromQuery(requestQuery(req));
    try {
      const client = createWebAuthClient(req, res, opts);
      const origin = intent ? cloudPublicOrigin(req, opts) : publicOrigin(req, opts);
      const result = await client.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${origin}/auth/google/callback`, scopes: "openid email profile", skipBrowserRedirect: true },
      });
      const redirect = result && result.data && result.data.url;
      if (!redirect || result.error) throw new Error("Google OAuth start failed");
      const existing = attributionCookie(req, opts);
      const secret = attributionSecret(opts);
      const validExisting = existing.present && consumeWebAttribution(existing.value, secret) !== null;
      if (existing.present && !validExisting) clearCookie(res, opts, WEB_ATTRIBUTION_COOKIE);
      if (!validExisting) {
        const cookie = captureWebAttribution(requestQuery(req), secret);
        if (cookie) setAttributionCookie(res, opts, cookie);
      }
      clearGoogleOAuthIntentCookie(res, opts);
      if (intent) setGoogleOAuthIntentCookie(res, opts, intent);
      sendRedirect(res, redirect);
    } catch {
      clearGoogleOAuthIntentCookie(res, opts);
      redirectToConnectionError(res, intent);
    }
    return;
  }

  const oauthIntent = googleOAuthIntentFromCookie(req, opts);
  const callbackFailure = () => {
    clearGoogleOAuthIntentCookie(res, opts);
    redirectToConnectionError(res, oauthIntent);
  };
  const query = requestQuery(req);
  const code = String(query.get("code") || "");
  if (!code) {
    callbackFailure();
    return;
  }
  try {
    if (!hasPkceVerifier(req, opts)) {
      callbackFailure();
      return;
    }
  } catch {
    callbackFailure();
    return;
  }

  let client = null;
  let sessionMayExist = false;
  try {
    requiredServiceRoleKey(opts);
    client = createWebAuthClient(req, res, opts);
    const exchange = await client.auth.exchangeCodeForSession(code);
    sessionMayExist = Boolean(exchange && exchange.data && exchange.data.session);
    if (!exchange || exchange.error || !sessionMayExist) {
      clearCookie(res, opts, `${authCookieName(opts)}-code-verifier`);
      callbackFailure();
      return;
    }

    const verified = await client.auth.getUser();
    const user = verified && verified.data && verified.data.user;
    if (!verified || verified.error || !user || !hasVerifiedGoogleIdentity(user)) {
      await clearWebSession(client, req, res, opts);
      callbackFailure();
      return;
    }
    const uid = await ensureWebUser(user.id, {
      env: envFor(opts),
      supabaseUrl: requiredSupabaseUrl(opts),
      serviceRoleKey: requiredServiceRoleKey(opts),
      anonKey: opts.anonKey || envFor(opts).SUPABASE_ANON_KEY,
      fetch: opts.fetch,
    });
    let firstTouch = {};
    const firstTouchCookie = attributionCookie(req, opts);
    if (firstTouchCookie.present) {
      const attribution = consumeWebAttribution(firstTouchCookie.value, attributionSecret(opts));
      if (!attribution) {
        clearCookie(res, opts, WEB_ATTRIBUTION_COOKIE);
      } else {
        firstTouch = attribution;
        try {
          const stored = await storeWebFirstTouch(uid, attribution, {
            env: envFor(opts),
            supabaseUrl: requiredSupabaseUrl(opts),
            serviceRoleKey: requiredServiceRoleKey(opts),
            fetch: opts.fetch,
          });
          if (stored) clearCookie(res, opts, WEB_ATTRIBUTION_COOKIE);
        } catch {
          // Attribution is optional to sign-in; retain the signed cookie for a later callback attempt.
        }
      }
    }
    try {
      const record = opts.recordWebFunnelEventImpl || recordWebFunnelEvent;
      await record({ eventName: "google_authenticated", uid, sourceObjectId: uid, attribution: firstTouch }, {
        supaUrl: requiredSupabaseUrl(opts),
        supaKey: requiredServiceRoleKey(opts),
        fetchImpl: opts.fetch,
      });
    } catch { /* funnel telemetry must not block a verified Google sign-in */ }
    clearCookie(res, opts, `${authCookieName(opts)}-code-verifier`);
    clearGoogleOAuthIntentCookie(res, opts);
    const location = oauthIntent === "maritime_cloud-ja"
      ? "/maritime?lang=ja&verified=1"
      : oauthIntent === "maritime_cloud-en"
        ? "/maritime?lang=en&verified=1"
        : "/lm?start_calendar=1";
    sendRedirect(res, location);
  } catch (error) {
    if (sessionMayExist && client) await clearWebSession(client, req, res, opts);
    callbackFailure();
  }
}

module.exports = {
  publicOrigin,
  cloudPublicOrigin,
  hasPkceVerifier,
  csrfSecret,
  createWebAuthClient,
  createWebCsrfToken,
  ensureWebUser,
  handleWebAuthRequest,
  resolveWebUser,
  signedOutCalendarHandoffLocation,
  separateWebUidForSubject,
  captureWebFirstTouchCookie,
  readWebFirstTouchCookie,
  storeWebFirstTouch,
  readWebFirstTouchValue,
};
