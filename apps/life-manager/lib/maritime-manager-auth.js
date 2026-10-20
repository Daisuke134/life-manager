"use strict";

const { createWebAuthClient, createWebCsrfToken, ensureWebUser, publicOrigin,
  hasPkceVerifier, csrfSecret } = require("./web-auth.js");
const SIGNUP_PATH = "/auth/maritime/email";
const CONFIRM_PATH = "/auth/maritime/confirm";
function enabled(options) {
  return (options.env || process.env).LM_MARITIME_MANAGER_EMAIL_ENABLED === "1";
}
function send(res, status, body, extra = {}) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store",
    "referrer-policy": "no-referrer", "x-content-type-options": "nosniff", ...extra });
  res.end(body == null ? "" : JSON.stringify(body));
}
function redirect(res, location) { send(res, 302, null, { location }); }
function clientFor(req, res, options) {
  return (options.createClient || createWebAuthClient)(req, res, options);
}
async function resolveMaritimeManagerUser(req, res, options = {}) {
  if (!enabled(options)) return null;
  try {
    const client = clientFor(req, res, options);
    const result = await client.auth.getUser();
    const user = result?.data?.user;
    if (result?.error || !user || !user.email || !Number.isFinite(Date.parse(user.email_confirmed_at))) return null;
    const uid = await (options.ensureWebUserImpl || ensureWebUser)(user.id, options);
    return { uid, subject: user.id, email: user.email,
      csrf: createWebCsrfToken(uid, csrfSecret(options)) };
  } catch { return null; }
}
async function signupBody(req) {
  const mime = String(req.headers?.["content-type"] || "").split(";")[0].trim().toLowerCase();
  if (!["application/json", "application/x-www-form-urlencoded"].includes(mime)) throw new Error("invalid_body");
  let text = "";
  for await (const chunk of req) {
    text += chunk.toString("utf8");
    if (Buffer.byteLength(text) > 4096) throw new Error("invalid_body");
  }
  let body;
  if (mime === "application/json") body = JSON.parse(text);
  else {
    const params = new URLSearchParams(text);
    if (params.getAll("email").length !== 1) throw new Error("invalid_body");
    body = Object.fromEntries(params);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)
    || Object.keys(body).some(key => key !== "email") || typeof body.email !== "string") throw new Error("invalid_body");
  const email = body.email.trim().toLowerCase();
  if (email.length > 320 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error("invalid_body");
  return email;
}
async function handleMaritimeManagerAuth(req, res, options = {}) {
  const url = new URL(req.url || "/", "http://localhost");
  if (![SIGNUP_PATH, CONFIRM_PATH].includes(url.pathname)) return false;
  if (!enabled(options)) { send(res, 503, { error: "manager_email_unavailable" }); return true; }
  const expectedMethod = url.pathname === SIGNUP_PATH ? "POST" : "GET";
  if (req.method !== expectedMethod) { send(res, 405, { error: "method_not_allowed" }, { allow: expectedMethod }); return true; }
  if (url.pathname === SIGNUP_PATH) {
    let origin;
    try { origin = publicOrigin(req, options); }
    catch { send(res, 503, { error: "manager_email_unavailable" }); return true; }
    if (req.headers?.origin !== origin) { send(res, 403, { error: "origin_rejected" }); return true; }
    let email;
    try { email = await signupBody(req); }
    catch { send(res, 400, { error: "invalid_email_request" }); return true; }
    try {
      const client = clientFor(req, res, options);
      const result = await client.auth.signInWithOtp({ email,
        options: { shouldCreateUser: true, emailRedirectTo: `${origin}${CONFIRM_PATH}` } });
      if (result?.error) {
        send(res, result.error.status === 429 ? 429 : 503, { error: "email_request_unavailable" });
      } else send(res, 202, { status: "check_email" });
    } catch { send(res, 503, { error: "email_request_unavailable" }); }
    return true;
  }
  // Mail link scanners can authenticate; only the later CSRF-protected POST activates work.
  let client;
  let sessionEstablished = false;
  try {
    for (const key of ["token_hash", "code", "type"]) {
      if (url.searchParams.getAll(key).length > 1) throw new Error("invalid_confirmation");
    }
    const hash = url.searchParams.get("token_hash"); const code = url.searchParams.get("code");
    if (Boolean(hash) === Boolean(code)) throw new Error("invalid_confirmation");
    if (hash && (url.searchParams.get("type") !== "email" || !/^[A-Za-z0-9_-]{16,512}$/.test(hash))) {
      throw new Error("invalid_confirmation");
    }
    if (code && (code.length > 2048 || !hasPkceVerifier(req, options))) throw new Error("invalid_confirmation");
    client = clientFor(req, res, options);
    const result = hash ? await client.auth.verifyOtp({ token_hash: hash, type: "email" })
      : await client.auth.exchangeCodeForSession(code);
    if (result?.error || !result?.data?.session) throw new Error("invalid_confirmation");
    sessionEstablished = true;
    const user = await resolveMaritimeManagerUser(req, res, { ...options, createClient: () => client });
    if (!user) throw new Error("invalid_confirmation");
    redirect(res, "/maritime?verified=1");
  } catch {
    if (client && sessionEstablished) { try { await client.auth.signOut({ scope: "local" }); } catch {} }
    redirect(res, "/maritime?auth_error=connection");
  }
  return true;
}
module.exports = { handleMaritimeManagerAuth, resolveMaritimeManagerUser };
