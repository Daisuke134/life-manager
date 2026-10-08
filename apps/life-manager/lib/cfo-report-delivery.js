"use strict";

const { resendSend } = require("./mail-resend.js");
const { notifyViaLocalOutbox } = require("./financial-transition-local.js");

// Email is the default. Never fall back to another audience or channel on failure.
function reportDestination(options = {}) {
  const channel = options.reportChannel || "email";
  if (channel === "email" && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(options.reportEmail || "")) {
    return { channel, recipient: options.reportEmail };
  }
  if (channel === "telegram" && String(options.chatId || "").trim()) {
    return { channel, recipient: String(options.chatId) };
  }
  throw new Error("cfo_report_destination_unconfigured");
}

async function notifyCfoReport(input, options = {}) {
  const destination = reportDestination(options);
  if (destination.channel === "telegram") {
    const delivery = notifyViaLocalOutbox(input, options);
    return delivery;
  }
  const send = options.sendEmail || resendSend;
  const response = await send({
    to: destination.recipient, subject: "Life Manager: today's results", text: input.message,
    resendKey: options.resendKey, idempotencyKey: input.eventKey,
  });
  // Provider acceptance is a receipt, not a claim that the inbox was read.
  return { delivery: response?.sent && response.id ? "delivered" : "pending",
    provider_message_id: response?.id || null, attempted: 1, delivered: response?.sent && response.id ? 1 : 0,
    delivery_uncertain: 0, pre_send_failed: 0 };
}

module.exports = { reportDestination, notifyCfoReport };
