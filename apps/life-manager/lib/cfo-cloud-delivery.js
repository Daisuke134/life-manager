"use strict";

const crypto = require("node:crypto");
const { resendSend } = require("./mail-resend.js");

function receiptIO(deps = {}) {
  const root = String(deps.supaUrl || process.env.SUPABASE_URL || "").replace(/\/$/, "");
  const key = deps.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  const f = deps.fetchImpl || globalThis.fetch;
  const request = async (identity, method, body) => {
    if (!root || !key) throw new Error("cfo_receipt_store_unconfigured");
    const query = method === "POST" ? "" : `?uid=eq.${encodeURIComponent(identity.uid)}&period_key=eq.${encodeURIComponent(identity.periodKey)}&limit=1`;
    const response = await f(`${root}/rest/v1/lm_cfo_result_receipts${query}`, {
      method, headers: { apikey: key, Authorization: `Bearer ${key}`,
        "Content-Type": "application/json", Prefer: method === "POST"
          ? "resolution=ignore-duplicates,return=representation" : "return=representation" },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) throw new Error("cfo_receipt_store_failed");
    const rows = await response.json();
    if (!Array.isArray(rows)) throw new Error("cfo_receipt_store_invalid");
    return rows;
  };
  return {
    read: async identity => (await request(identity, "GET"))[0] || null,
    claim: async (identity, payload) => (await request(identity, "POST", payload)).length === 1,
    mark: async (identity, payload) => {
      if ((await request(identity, "PATCH", payload)).length !== 1) throw new Error("cfo_receipt_claim_lost");
    },
  };
}

// Separate channel-aware receipt table avoids pretending an email has a Telegram numeric ID.
async function deliverCloudCfoEmail({ uid, periodKey, message, observedAt, recipient }, deps = {}) {
  const io = deps.cfoReceiptIO || receiptIO(deps);
  const recipientHash = crypto.createHash("sha256").update(recipient).digest("hex");
  const identity = { uid, periodKey };
  let receipt = await io.read(identity);
  if (receipt?.status === "sent") {
    if (!receipt.provider_message_id || receipt.recipient_hash !== recipientHash) throw new Error("cfo_receipt_invalid");
    return { status: "duplicate", channel: "email", providerMessageId: receipt.provider_message_id,
      recipientHash, sentAt: receipt.sent_at, snapshotHash: crypto.createHash("sha256").update(receipt.message).digest("hex") };
  }
  if (!receipt) {
    const payload = { uid, period_key: periodKey, channel: "email", recipient_hash: recipientHash,
      status: "pending", message, observed_at: observedAt };
    if (!await io.claim(identity, payload)) throw new Error("cfo_claim_unresolved");
    receipt = payload;
  }
  if (Date.parse(observedAt) - Date.parse(receipt.observed_at) >= 23 * 60 * 60 * 1000) {
    throw new Error("cfo_email_idempotency_expired");
  }
  if (receipt.recipient_hash !== recipientHash) throw new Error("cfo_pending_recipient_changed");
  const send = deps.sendEmail || resendSend;
  let result;
  try { result = await send({ to: recipient, subject: "Life Manager: today's results",
    text: receipt.message, resendKey: deps.resendKey || process.env.RESEND_API_KEY,
    idempotencyKey: `cfo:${uid}:email:${periodKey}` });
  } catch { const error = new Error("cfo_email_effect_unknown"); error.unknownEffect = true; throw error; }
  if (!result?.sent || !result.id) {
    const error = new Error("cfo_email_receipt_missing"); error.unknownEffect = true; throw error;
  }
  try { await io.mark(identity, { status: "sent", provider_message_id: String(result.id), sent_at: observedAt }); }
  catch { const error = new Error("cfo_email_commit_unknown"); error.unknownEffect = true; throw error; }
  return { status: "sent", channel: "email", providerMessageId: String(result.id), recipientHash,
    sentAt: observedAt, snapshotHash: crypto.createHash("sha256").update(receipt.message).digest("hex") };
}
module.exports = { deliverCloudCfoEmail };
