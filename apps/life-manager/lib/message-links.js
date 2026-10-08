"use strict";

const crypto = require("node:crypto");
const { resolveWebUser } = require("./web-auth.js");

const WEB_MESSAGE_LINK_PATH = "/api/lm-web/message-link";
const WEB_TELEGRAM_START_PREFIX = "lmw_";
const WEB_TELEGRAM_TOKEN_RE = /^[A-Za-z0-9_-]{32}$/;
const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TELEGRAM_BOT_USERNAME_RE = /^[A-Za-z][A-Za-z0-9_]{4,31}$/;
const LINK_TTL_MS = 10 * 60 * 1000;

function serviceConfig(opts = {}) {
  const env = opts.env && typeof opts.env === "object" ? opts.env : process.env;
  const supaUrl = String(opts.supaUrl || env.SUPABASE_URL || "").replace(/\/$/, "");
  const supaKey = String(opts.supaKey || env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  if (!supaUrl || !supaKey) throw new Error("message_link_store_unavailable");
  return { supaUrl, supaKey };
}

async function rpc(name, body, opts = {}) {
  const { supaUrl, supaKey } = serviceConfig(opts);
  const fetchImpl = opts.fetchImpl || fetch;
  const response = await fetchImpl(`${supaUrl}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: {
      apikey: supaKey,
      Authorization: `Bearer ${supaKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response || !response.ok) throw new Error("message_link_store_unavailable");
  return response.json().catch(() => null);
}

function parseWebTelegramStart(text) {
  const command = /^\/start(?:@[A-Za-z0-9_]+)?(?:\s+(.+))?$/i.exec(String(text || "").trim());
  if (!command) return { matched: false, token: null };
  const payload = String(command[1] || "").trim();
  if (!payload.startsWith(WEB_TELEGRAM_START_PREFIX)) return { matched: false, token: null };
  const token = payload.slice(WEB_TELEGRAM_START_PREFIX.length);
  return { matched: true, token: WEB_TELEGRAM_TOKEN_RE.test(token) ? token : null };
}

async function createWebMessageLink(uid, channel, opts = {}) {
  const tenantUid = String(uid || "");
  if (!WEB_UID_RE.test(tenantUid)) throw new Error("web_message_tenant_invalid");
  if (channel !== "telegram") throw new Error("web_message_channel_unavailable");
  const env = opts.env && typeof opts.env === "object" ? opts.env : process.env;
  const botUsername = String(opts.botUsername || env.LM_TELEGRAM_BOT_USERNAME || "").replace(/^@/, "");
  if (!TELEGRAM_BOT_USERNAME_RE.test(botUsername)) throw new Error("telegram_bot_unavailable");
  const randomBytes = opts.randomBytesImpl || crypto.randomBytes;
  const token = randomBytes(24).toString("base64url");
  if (!WEB_TELEGRAM_TOKEN_RE.test(token)) throw new Error("message_link_token_unavailable");
  const expiresAt = new Date((opts.nowMs == null ? Date.now() : Number(opts.nowMs)) + LINK_TTL_MS).toISOString();
  const tokenHash = crypto.createHash("sha256").update(token).digest("hex");
  const created = await rpc("create_lm_web_message_link", {
    p_uid: tenantUid,
    p_channel: channel,
    p_token_hash: tokenHash,
    p_expires_at: expiresAt,
  }, opts);
  const accepted = Array.isArray(created) ? created[0] === true : created === true;
  if (!accepted) throw new Error("message_link_not_created");
  return {
    url: `https://t.me/${botUsername}?start=${WEB_TELEGRAM_START_PREFIX}${token}`,
    expiresAt,
  };
}

async function consumeWebMessageLink(token, channel, senderId, opts = {}) {
  const rawToken = String(token || "");
  const sender = String(senderId || "");
  if (channel !== "telegram" || !WEB_TELEGRAM_TOKEN_RE.test(rawToken)
    || !/^[1-9][0-9]{0,19}$/.test(sender)) return null;
  const result = await rpc("consume_lm_web_message_link", {
    p_token_hash: crypto.createHash("sha256").update(rawToken).digest("hex"),
    p_channel: channel,
    p_sender_id: sender,
  }, opts);
  const uid = Array.isArray(result) ? result[0] : result;
  return WEB_UID_RE.test(String(uid || "")) ? { uid, channel } : null;
}

async function webTelegramUserBySender(senderId, opts = {}) {
  const sender = String(senderId || "");
  if (!/^[1-9][0-9]{0,19}$/.test(sender)) return null;
  const { supaUrl, supaKey } = serviceConfig(opts);
  const fetchImpl = opts.fetchImpl || fetch;
  const headers = { apikey: supaKey, Authorization: `Bearer ${supaKey}` };
  const linkUrl = new URL(`${supaUrl}/rest/v1/lm_message_channels`);
  linkUrl.searchParams.set("channel", "eq.telegram");
  linkUrl.searchParams.set("owner_kind", "eq.web_link");
  linkUrl.searchParams.set("sender_id", `eq.${sender}`);
  linkUrl.searchParams.set("select", "uid,owner_kind");
  linkUrl.searchParams.set("limit", "2");
  const linkResponse = await fetchImpl(linkUrl.toString(), { headers });
  if (!linkResponse || !linkResponse.ok) return null;
  const links = await linkResponse.json().catch(() => null);
  if (!Array.isArray(links) || links.length !== 1 || links[0].owner_kind !== "web_link"
    || !WEB_UID_RE.test(String(links[0].uid || ""))) return null;

  const userUrl = new URL(`${supaUrl}/rest/v1/lm_users`);
  userUrl.searchParams.set("uid", `eq.${links[0].uid}`);
  userUrl.searchParams.set("telegram_chat_id", "is.null");
  userUrl.searchParams.set("select", "uid,telegram_chat_id,calendar_provider,calendar_connected_account_id,gmail_account_id,paid");
  userUrl.searchParams.set("limit", "2");
  const userResponse = await fetchImpl(userUrl.toString(), { headers });
  if (!userResponse || !userResponse.ok) return null;
  const users = await userResponse.json().catch(() => null);
  if (!Array.isArray(users) || users.length !== 1 || users[0].uid !== links[0].uid || users[0].telegram_chat_id != null) return null;
  return { ...users[0], web_message_telegram_chat_id: sender };
}

async function webTelegramChannelsForUids(uids, opts = {}) {
  const webUids = new Set((Array.isArray(uids) ? uids : [])
    .map((uid) => String(uid || ""))
    .filter((uid) => WEB_UID_RE.test(uid)));
  if (webUids.size === 0) return new Map();
  const { supaUrl, supaKey } = serviceConfig(opts);
  const fetchImpl = opts.fetchImpl || fetch;
  const url = new URL(`${supaUrl}/rest/v1/lm_message_channels`);
  url.searchParams.set("channel", "eq.telegram");
  url.searchParams.set("owner_kind", "eq.web_link");
  url.searchParams.set("select", "uid,sender_id,owner_kind");
  url.searchParams.set("limit", "1000");
  let response;
  try {
    response = await fetchImpl(url.toString(), {
      headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}` },
    });
  } catch { return new Map(); }
  if (!response || !response.ok) return new Map();
  const rows = await response.json().catch(() => null);
  if (!Array.isArray(rows)) return new Map();
  const counts = new Map();
  for (const row of rows) {
    const uid = String(row && row.uid || "");
    const sender = String(row && row.sender_id || "");
    if (row.owner_kind !== "web_link" || !webUids.has(uid) || !/^[1-9][0-9]{0,19}$/.test(sender)) continue;
    counts.set(uid, [...(counts.get(uid) || []), sender]);
  }
  const result = new Map();
  for (const [uid, senders] of counts) if (senders.length === 1) result.set(uid, senders[0]);
  return result;
}

function sendJson(res, status, body) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(JSON.stringify(body));
}

function requestUrl(req) {
  try { return new URL(req.url || "/", "http://life-manager.local"); }
  catch { return new URL("/", "http://life-manager.local"); }
}

function requestOrigin(opts = {}) {
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
  return expected.length > 0 && expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
}

function panelApi() {
  return require("./panel-api.js");
}

async function handleWebMessageLinkRequest(req, res, opts = {}) {
  const url = requestUrl(req);
  if (url.pathname !== WEB_MESSAGE_LINK_PATH) return sendJson(res, 404, { error: "not_found" });
  if (String(req && req.method || "GET").toUpperCase() !== "POST") {
    return sendJson(res, 405, { error: "method_not_allowed" });
  }

  let user = null;
  try { user = await (opts.resolveWebUserImpl || resolveWebUser)(req, res, opts); } catch {}
  if (!user || !WEB_UID_RE.test(String(user.uid || ""))) return sendJson(res, 401, { error: "unauthorized" });
  const origin = requestOrigin(opts);
  if (!origin || String(req.headers && req.headers.origin || "") !== origin) return sendJson(res, 403, { error: "origin_rejected" });
  if (!hasJsonContentType(req)) return sendJson(res, 415, { error: "json_required" });
  if (!validCsrf(req, user)) return sendJson(res, 403, { error: "csrf_rejected" });

  let body;
  try { body = await (opts.readJsonImpl || panelApi().readJson)(req); }
  catch { return sendJson(res, 400, { error: "invalid_json" }); }
  if (!body || typeof body !== "object" || Array.isArray(body)
    || Object.keys(body).length !== 1 || body.channel !== "telegram") {
    return sendJson(res, 400, { error: "invalid_channel" });
  }
  try {
    const link = await (opts.createWebMessageLinkImpl || createWebMessageLink)(user.uid, body.channel, opts);
    return sendJson(res, 200, link);
  } catch (error) {
    const code = String(error && error.message || "");
    const status = code === "message_link_not_created" ? 409
      : code === "web_message_tenant_invalid" || code === "web_message_channel_unavailable" ? 400 : 503;
    return sendJson(res, status, { error: status < 500 ? code : "message_link_unavailable" });
  }
}

module.exports = {
  WEB_MESSAGE_LINK_PATH,
  createWebMessageLink,
  consumeWebMessageLink,
  handleWebMessageLinkRequest,
  parseWebTelegramStart,
  webTelegramChannelsForUids,
  webTelegramUserBySender,
};
