"use strict";

const { createHmac } = require("node:crypto");

const MAX_MESSAGE_CHARS = 2000;
const UID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const API_KEY_PATTERN = /^mk_[A-Za-z0-9_-]{4,}$/;
const AGENT_INSTRUCTIONS = [
  "You are a Life Manager pilot assistant. Help the user plan everyday tasks clearly and briefly.",
  "You have no connected calendar, email, browser, purchasing, or messaging tools.",
  "Do not claim that you performed an action or accessed an account.",
].join(" ");

function parseAllowlist(value) {
  const entries = String(value || "").split(",").map((uid) => uid.trim());
  if (entries.length < 1 || entries.length > 3) return null;
  if (entries.some((uid) => !UID_PATTERN.test(uid))) return null;
  if (new Set(entries).size !== entries.length) return null;
  return new Set(entries);
}

function createMaritimePilotTransport({ env = {}, client = null, loadSdk } = {}) {
  const allowlist = parseAllowlist(env.MARITIME_PILOT_UID_ALLOWLIST);
  const apiKey = String(env.MARITIME_API_KEY || "");
  const uidSecret = String(env.LM_UID_SECRET || "");
  let clientPromise = null;

  const configEnabled = env.MARITIME_PILOT_ENABLED === "1"
    && env.MARITIME_PILOT_DATA_APPROVED === "1"
    && API_KEY_PATTERN.test(apiKey)
    && uidSecret.length > 0
    && allowlist !== null;

  function isEnabledFor(uid) {
    const value = String(uid || "");
    return configEnabled && UID_PATTERN.test(value) && allowlist.has(value);
  }

  function scopedId(kind, uid) {
    return `lm-pilot-${createHmac("sha256", uidSecret).update(`${kind}:${uid}`).digest("hex").slice(0, 32)}`;
  }

  async function getClient() {
    if (client) return client;
    if (!clientPromise) {
      clientPromise = (async () => {
        const options = { apiKey, maxRetries: 0 };
        if (loadSdk) return loadSdk(options);
        const module = await import("maritime-sdk");
        const Maritime = module.default || module.Maritime;
        if (typeof Maritime !== "function") throw new Error("Maritime SDK export unavailable");
        return new Maritime(options);
      })();
    }
    return clientPromise;
  }

  async function chatForUser(uid, message) {
    if (!isEnabledFor(uid)) return { ok: false, reason: "disabled" };
    const text = String(message || "").trim();
    if (!text || text.length > MAX_MESSAGE_CHARS) return { ok: false, reason: "invalid_message" };

    try {
      const maritime = await getClient();
      const externalId = scopedId("agent", uid);
      const conversationId = scopedId("conversation", uid);
      const agent = await maritime.agents.provision({
        externalId,
        name: externalId,
        template: "openclaw",
        instructions: AGENT_INSTRUCTIONS,
      });
      if (!agent || typeof agent.id !== "string" || !agent.id) {
        return { ok: false, reason: "provider_error" };
      }

      const result = await maritime.agents.chat(agent.id, text, { conversationId });
      if (result?.error || typeof result?.response !== "string" || !result.response.trim()) {
        return { ok: false, reason: "provider_error" };
      }
      return { ok: true, response: result.response.trim() };
    } catch {
      // Provider errors may include request content or credentials. Keep them out of logs and chat.
      return { ok: false, reason: "provider_error" };
    }
  }

  return Object.freeze({ isEnabledFor, chatForUser });
}

module.exports = { MAX_MESSAGE_CHARS, createMaritimePilotTransport };
