"use strict";

const crypto = require("node:crypto");
const { resolveWebUser } = require("./web-auth.js");

const WEB_MESSAGE_LINK_PATH = "/api/lm-web/message-link";
const WEB_TELEGRAM_START_PREFIX = "lmw_";
const WEB_MESSAGE_TOKEN_RE = /^[A-Za-z0-9_-]{32}$/;
const WEB_MESSAGE_CHANNELS = new Set(["telegram", "imessage"]);
const IMESSAGE_PAIRING_CODE_PREFIX = "LMI_";
const IMESSAGE_CONTACT_RE = /^\+[1-9][0-9]{7,14}$/;
const IMESSAGE_EMAIL_RE = /^[^@\s]{1,64}@[^@\s.]+(?:\.[^@\s.]+)+$/;
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
  return { matched: true, token: WEB_MESSAGE_TOKEN_RE.test(token) ? token : null };
}

function normalizeMessageSenderId(channel, senderId) {
  const raw = String(senderId || "");
  if (raw !== raw.trim() || /[\x00-\x1f\x7f]/.test(raw)) return null;
  const sender = raw;
  if (channel === "telegram") return /^[1-9][0-9]{0,19}$/.test(sender) ? sender : null;
  if (channel !== "imessage") return null;
  if (IMESSAGE_CONTACT_RE.test(sender)) return sender;
  if (IMESSAGE_EMAIL_RE.test(sender)) return sender.toLowerCase();
  return null;
}

async function createWebMessageLink(uid, channel, opts = {}) {
  const tenantUid = String(uid || "");
  if (!WEB_UID_RE.test(tenantUid)) throw new Error("web_message_tenant_invalid");
  if (!WEB_MESSAGE_CHANNELS.has(channel)) throw new Error("web_message_channel_unavailable");
  const env = opts.env && typeof opts.env === "object" ? opts.env : process.env;
  let url, code = null;
  if (channel === "telegram") {
    const botUsername = String(opts.botUsername || env.LM_TELEGRAM_BOT_USERNAME || "").replace(/^@/, "");
    if (!TELEGRAM_BOT_USERNAME_RE.test(botUsername)) throw new Error("telegram_bot_unavailable");
    url = `https://t.me/${botUsername}?start=${WEB_TELEGRAM_START_PREFIX}`;
  } else {
    const contactNumber = String(opts.imessageContactNumber || env.LM_IMESSAGE_CONTACT_NUMBER || "").trim();
    const ready = opts.imessageReady === true;
    if (env.LM_IMESSAGE_WEB_LINKS_ENABLED !== "1" || !ready
      || !env.SPECTRUM_PROJECT_ID || !env.SPECTRUM_PROJECT_SECRET
      || !IMESSAGE_CONTACT_RE.test(contactNumber)) {
      throw new Error("imessage_link_unavailable");
    }
    url = `sms:${contactNumber}`;
  }
  const randomBytes = opts.randomBytesImpl || crypto.randomBytes;
  const token = randomBytes(24).toString("base64url");
  if (!WEB_MESSAGE_TOKEN_RE.test(token)) throw new Error("message_link_token_unavailable");
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
  return channel === "telegram"
    ? { url: `${url}${token}`, expiresAt }
    : { url, code: `${IMESSAGE_PAIRING_CODE_PREFIX}${token}`, expiresAt };
}

async function consumeWebMessageLink(token, channel, senderId, opts = {}) {
  const rawToken = String(token || "");
  const sender = normalizeMessageSenderId(channel, senderId);
  if (!WEB_MESSAGE_CHANNELS.has(channel) || !WEB_MESSAGE_TOKEN_RE.test(rawToken) || !sender) return null;
  const result = await rpc("consume_lm_web_message_link", {
    p_token_hash: crypto.createHash("sha256").update(rawToken).digest("hex"),
    p_channel: channel,
    p_sender_id: sender,
  }, opts);
  const uid = Array.isArray(result) ? result[0] : result;
  return WEB_UID_RE.test(String(uid || "")) ? { uid, channel } : null;
}

async function webMessageUserBySender(channel, senderId, opts = {}) {
  const sender = normalizeMessageSenderId(channel, senderId);
  if (!WEB_MESSAGE_CHANNELS.has(channel) || !sender) return null;
  const { supaUrl, supaKey } = serviceConfig(opts);
  const fetchImpl = opts.fetchImpl || fetch;
  const headers = { apikey: supaKey, Authorization: `Bearer ${supaKey}` };
  const linkUrl = new URL(`${supaUrl}/rest/v1/lm_message_channels`);
  linkUrl.searchParams.set("channel", `eq.${channel}`);
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
  userUrl.searchParams.set("select", "uid,telegram_chat_id,calendar_provider,calendar_connected_account_id,gmail_account_id,paid,plan_status,trial_expires_at,web_trial_payment_method_present,web_billing_cancel_at_period_end");
  userUrl.searchParams.set("limit", "2");
  const userResponse = await fetchImpl(userUrl.toString(), { headers });
  if (!userResponse || !userResponse.ok) return null;
  const users = await userResponse.json().catch(() => null);
  if (!Array.isArray(users) || users.length !== 1 || users[0].uid !== links[0].uid || users[0].telegram_chat_id != null) return null;
  return { ...users[0], [`web_message_${channel}_sender_id`]: sender };
}

async function webTelegramUserBySender(senderId, opts = {}) {
  const user = await webMessageUserBySender("telegram", senderId, opts);
  if (!user) return null;
  const sender = user.web_message_telegram_sender_id;
  const { web_message_telegram_sender_id: _removed, ...rest } = user;
  return { ...rest, web_message_telegram_chat_id: sender };
}

async function webMessageChannelsForUids(uids, channel, opts = {}) {
  if (!WEB_MESSAGE_CHANNELS.has(channel)) return new Map();
  const webUids = new Set((Array.isArray(uids) ? uids : [])
    .map((uid) => String(uid || ""))
    .filter((uid) => WEB_UID_RE.test(uid)));
  if (webUids.size === 0) return new Map();
  const { supaUrl, supaKey } = serviceConfig(opts);
  const fetchImpl = opts.fetchImpl || fetch;
  const url = new URL(`${supaUrl}/rest/v1/lm_message_channels`);
  url.searchParams.set("channel", `eq.${channel}`);
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
    const sender = normalizeMessageSenderId(channel, row && row.sender_id);
    if (row.owner_kind !== "web_link" || !webUids.has(uid) || !sender) continue;
    counts.set(uid, [...(counts.get(uid) || []), sender]);
  }
  const result = new Map();
  for (const [uid, senders] of counts) if (senders.length === 1) result.set(uid, senders[0]);
  return result;
}

async function webTelegramChannelsForUids(uids, opts = {}) {
  return webMessageChannelsForUids(uids, "telegram", opts);
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
    || Object.keys(body).length !== 1 || !WEB_MESSAGE_CHANNELS.has(body.channel)) {
    return sendJson(res, 400, { error: "invalid_channel" });
  }
  if ((body.channel === "telegram" && opts.telegramReady === false)
    || (body.channel === "imessage" && opts.imessageReady !== true)) {
    return sendJson(res, 503, { error: "message_link_unavailable" });
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
  normalizeMessageSenderId,
  parseWebTelegramStart,
  webMessageChannelsForUids,
  webMessageUserBySender,
  webTelegramChannelsForUids,
  webTelegramUserBySender,
};
