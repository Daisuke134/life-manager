"use strict";

const { createHmac } = require("node:crypto");

const WEB_AUTH_COOKIE = "lm-web-auth";
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

async function resolveWebUser(req, res, opts = {}) {
  try {
    const client = createWebAuthClient(req, res, opts);
    const result = await client.auth.getUser();
    const user = result && result.data && result.data.user;
    if (!user || result.error) return null;
    const subject = String(user.id || "");
    const uid = uidForSubject(subject);
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

function rejectTelegramBound(row) {
  if (row && row.telegram_chat_id != null && String(row.telegram_chat_id).trim() !== "") {
    const error = new Error("Telegram-bound uid cannot start a Web session");
    error.code = "telegram_bound";
    throw error;
  }
}

async function ensureWebUser(uid, opts = {}) {
  const tenantUid = String(uid || "");
  if (!WEB_UID_RE.test(tenantUid)) throw new Error("verified Web uid is required");
  const root = requiredSupabaseUrl(opts);
  const key = requiredServiceRoleKey(opts);
  const existing = await readWebUserRow(tenantUid, opts, root, key);
  rejectTelegramBound(existing);
  if (existing) return;

  const fetchImpl = opts.fetch || globalThis.fetch;
  const inserted = await fetchImpl(`${root}/rest/v1/lm_users?on_conflict=uid`, {
    method: "POST",
    headers: serviceHeaders(key, {
      "content-type": "application/json",
      Prefer: "resolution=ignore-duplicates,return=minimal",
    }),
    body: JSON.stringify({ uid: tenantUid }),
  });
  if (!inserted || !inserted.ok) throw new Error("Web user insert failed");
  const readback = await readWebUserRow(tenantUid, opts, root, key);
  if (!readback) throw new Error("Web user insert readback unavailable");
  rejectTelegramBound(readback);
}

function requestPath(req) {
  try { return new URL(String(req && req.url || "/"), "http://localhost").pathname; }
  catch { return "/"; }
}

function requestQuery(req) {
  try { return new URL(String(req && req.url || "/"), "http://localhost").searchParams; }
  catch { return new URLSearchParams(); }
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

function clearCookie(res, opts, name) {
  const ssr = ssrFor(opts);
  const serializer = opts.serializeCookieHeader || ssr.serializeCookieHeader;
  if (typeof serializer !== "function") return;
  const settings = cookieOptions(opts);
  delete settings.name;
  appendResponseCookies(res, [{ name, value: "", options: { ...settings, maxAge: 0, expires: new Date(0) } }], serializer);
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
    try {
      const client = createWebAuthClient(req, res, opts);
      const origin = publicOrigin(req, opts);
      const result = await client.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${origin}/auth/google/callback`, skipBrowserRedirect: true },
      });
      const redirect = result && result.data && result.data.url;
      if (!redirect || result.error) throw new Error("Google OAuth start failed");
      sendRedirect(res, redirect);
    } catch {
      sendText(res, 503, "Web sign-in unavailable");
    }
    return;
  }

  const query = requestQuery(req);
  const code = String(query.get("code") || "");
  if (!code) {
    sendText(res, 400, "Web sign-in unavailable");
    return;
  }
  try {
    if (!hasPkceVerifier(req, opts)) {
      sendText(res, 400, "Web sign-in unavailable");
      return;
    }
  } catch {
    sendText(res, 400, "Web sign-in unavailable");
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
      sendText(res, 401, "Web sign-in unavailable");
      return;
    }

    const verified = await client.auth.getUser();
    const user = verified && verified.data && verified.data.user;
    if (!verified || verified.error || !user) {
      await clearWebSession(client, req, res, opts);
      sendText(res, 401, "Web sign-in unavailable");
      return;
    }
    const uid = uidForSubject(user.id);
    await ensureWebUser(uid, {
      env: envFor(opts),
      supabaseUrl: requiredSupabaseUrl(opts),
      serviceRoleKey: requiredServiceRoleKey(opts),
      anonKey: opts.anonKey || envFor(opts).SUPABASE_ANON_KEY,
      fetch: opts.fetch,
    });
    clearCookie(res, opts, `${authCookieName(opts)}-code-verifier`);
    sendRedirect(res, "/lm");
  } catch (error) {
    if (sessionMayExist && client) await clearWebSession(client, req, res, opts);
    const status = error && error.code === "telegram_bound" ? 403 : 503;
    sendText(res, status, "Web sign-in unavailable");
  }
}

module.exports = {
  createWebAuthClient,
  createWebCsrfToken,
  ensureWebUser,
  handleWebAuthRequest,
  resolveWebUser,
};
