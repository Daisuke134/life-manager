"use strict";

const {
  consumeWebMessageLink,
  normalizeMessageSenderId,
  webMessageUserBySender,
} = require("./message-links.js");

const MAX_MESSAGE_ID_LENGTH = 255;
const MAX_MESSAGE_TEXT_LENGTH = 4000;
const PAIRING_CODE_RE = /^LMI_([A-Za-z0-9_-]{32})$/;
const IMESSAGE_CONTACT_RE = /^\+[1-9][0-9]{7,14}$/;
const LINKED_REPLY = "iMessageをLife Managerに接続しました。確認が必要な予定があるときだけ質問します。";

function normalizeIMessageSender(value) {
  return normalizeMessageSenderId("imessage", value);
}

function parseIMessagePairingCode(value) {
  const match = PAIRING_CODE_RE.exec(String(value || "").trim());
  return match ? match[1] : null;
}

function spectrumConfiguration(env = process.env) {
  const projectId = String(env.SPECTRUM_PROJECT_ID || "").trim();
  const projectSecret = String(env.SPECTRUM_PROJECT_SECRET || "").trim();
  return projectId && projectSecret ? { projectId, projectSecret } : null;
}

function isIMessageLinkReady(env = process.env, client) {
  const contactNumber = String(env.LM_IMESSAGE_CONTACT_NUMBER || "").trim();
  return env.LM_IMESSAGE_WEB_LINKS_ENABLED === "1"
    && Boolean(client && client.enabled === true)
    && Boolean(spectrumConfiguration(env))
    && IMESSAGE_CONTACT_RE.test(contactNumber);
}

function messageText(message) {
  if (!message || !message.content || message.content.type !== "text") return "";
  const text = String(message.content.text || "").trim();
  return text.length <= MAX_MESSAGE_TEXT_LENGTH ? text : "";
}

function linkedReplyText(reply) {
  if (reply && reply.needsLocation) return "場所はどこですか？住所か、お店・会社の名前を送ってください。";
  if (reply && reply.online === true) return "オンラインの予定として記録しました。移動時間は追加しません。";
  if (reply && reply.filled) return `✅ ${reply.event}の場所を${reply.location}に更新しました。`;
  return "確認が必要な予定への返信として一致しませんでした。Life Managerからの質問に返信してください。";
}

async function handleIMessageStreamMessage(space, message, opts = {}) {
  const messageId = String(message && message.id || "");
  if (!space || space.type !== "dm" || !message || message.platform !== "imessage"
    || !messageId || messageId.length > MAX_MESSAGE_ID_LENGTH) {
    return { handled: false, reason: "unsupported_message" };
  }
  const senderId = normalizeIMessageSender(message.sender && (message.sender.id || message.sender.address));
  const text = messageText(message);
  if (!senderId || !text) return { handled: false, reason: "invalid_sender_or_text" };

  if (text.startsWith("LMI_")) {
    const token = parseIMessagePairingCode(text);
    if (!token) return { handled: true, action: "invalid_pairing_code" };
    let binding = null;
    try {
      binding = await (opts.consumeWebMessageLinkImpl || consumeWebMessageLink)(token, "imessage", senderId, opts);
    } catch {
      return { handled: true, action: "pairing_store_unavailable" };
    }
    if (!binding || binding.channel !== "imessage" || !/^lm_[0-9a-f-]{36}$/i.test(String(binding.uid || ""))) {
      return { handled: true, action: "pairing_rejected" };
    }
    await space.send(LINKED_REPLY);
    return { handled: true, action: "linked", uid: binding.uid };
  }

  let user = null;
  try {
    user = await (opts.webMessageUserBySenderImpl || webMessageUserBySender)("imessage", senderId, opts);
  } catch {
    return { handled: true, action: "sender_lookup_unavailable" };
  }
  if (!user || !/^lm_[0-9a-f-]{36}$/i.test(String(user.uid || ""))) {
    return { handled: false, reason: "sender_not_linked" };
  }

  const resolveReply = opts.resolveIMessageReplyImpl
    || require("./telegram-reply.js").resolveIMessageReply;
  if (typeof resolveReply !== "function") return { handled: true, action: "reply_handler_unavailable" };
  const reply = await resolveReply(user.uid, senderId, text, opts);
  if (!reply || (!reply.filled && !reply.needsLocation && reply.online !== true)) {
    return { handled: true, action: "no_pending_reply" };
  }
  await space.send(linkedReplyText(reply));
  return { handled: true, action: reply.filled ? "location_updated" : reply.online ? "online_recorded" : "location_requested", uid: user.uid };
}

async function importSpectrumRuntime() {
  const [core, provider] = await Promise.all([
    import("@spectrum-ts/core"),
    import("@spectrum-ts/imessage"),
  ]);
  return { Spectrum: core.Spectrum, imessage: provider.default || provider.imessage };
}

async function startIMessageCloud(opts = {}) {
  const env = opts.env && typeof opts.env === "object" ? opts.env : process.env;
  const config = spectrumConfiguration(env);
  if (!config) {
    return {
      enabled: false,
      reason: "credentials_missing",
      ready: Promise.resolve(),
      async stop() {},
      async sendToSender() { return { ok: false, reason: "not_ready" }; },
    };
  }

  const runtime = opts.loadSpectrumRuntimeImpl
    ? await opts.loadSpectrumRuntimeImpl()
    : await importSpectrumRuntime();
  const Spectrum = runtime && runtime.Spectrum;
  const imessage = runtime && runtime.imessage;
  if (typeof Spectrum !== "function" || !imessage || typeof imessage.config !== "function") {
    throw new Error("spectrum_sdk_unavailable");
  }
  const app = await Spectrum({
    projectId: config.projectId,
    projectSecret: config.projectSecret,
    providers: [imessage.config()],
  });
  if (!app || !app.messages || typeof app.messages[Symbol.asyncIterator] !== "function") {
    if (app && typeof app.stop === "function") await app.stop().catch(() => {});
    throw new Error("spectrum_message_stream_unavailable");
  }

  let stopping = false;
  const handleMessage = opts.handleMessageImpl || ((space, message) => handleIMessageStreamMessage(space, message, {
    ...opts,
    env,
  }));
  const ready = (async () => {
    for await (const [space, message] of app.messages) {
      if (stopping) break;
      try {
        await handleMessage(space, message);
      } catch {
        if (typeof opts.onMessageError === "function") opts.onMessageError();
      }
    }
  })();

  async function sendToSender(senderAddress, text) {
    const sender = normalizeIMessageSender(senderAddress);
    if (!sender) return { ok: false, reason: "invalid_sender" };
    try {
      const im = imessage(app);
      const user = await im.user(sender);
      const space = await im.space.create(user);
      const receipt = await space.send(String(text || "").slice(0, 1000));
      const receiptId = receipt && receipt.id ? String(receipt.id) : "";
      return receiptId
        ? { ok: true, receiptId }
        : { ok: false, effectUnknown: true, reason: "receipt_missing" };
    } catch {
      return { ok: false, effectUnknown: true, reason: "send_outcome_unknown" };
    }
  }

  return {
    enabled: true,
    ready,
    sendToSender,
    async stop() {
      stopping = true;
      if (typeof app.stop === "function") await app.stop();
      await ready.catch(() => {});
    },
  };
}

module.exports = {
  handleIMessageStreamMessage,
  isIMessageLinkReady,
  normalizeIMessageSender,
  parseIMessagePairingCode,
  spectrumConfiguration,
  startIMessageCloud,
};
