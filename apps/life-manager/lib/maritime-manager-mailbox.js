"use strict";

// Tenant-only Capafy verification inboxes. The API key and message body stay in
// this trusted service; the agent receives neither. See docs at
// https://www.agentmail.to/docs/api-reference/inboxes/create.
const API_ORIGIN = "https://api.agentmail.to";
const API_BASE = `${API_ORIGIN}/v0`;
const UID = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SUBJECT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ATTEMPT_ID = SUBJECT;
const CHALLENGE_ID = /^[A-Za-z0-9_-]{8,512}$/;
const EMAIL = /^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@agentmail\.to$/i;
const INBOX_ID = /^[A-Za-z0-9._@+-]{1,320}$/;
const CODE_CONTEXT = /\b(?:verification|security|login|sign[ -]?in|authentication|one[- ]?time|otp)\b/i;
const CAPAFY_SENDER = /^[^\s<>@]+@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*capafy\.ai$/i;
const CHALLENGE_VERIFY_LEASE_MS = 120_000;

class MaritimeMailboxError extends Error {
  constructor(code, unknownEffect = false) {
    super(code);
    this.code = code;
    this.unknownEffect = unknownEffect;
  }
}

function validUid(value) {
  if (typeof value !== "string" || !UID.test(value)) throw new MaritimeMailboxError("maritime_mailbox_input_invalid");
  return value.toLowerCase();
}

function validSubject(value) {
  if (typeof value !== "string" || !SUBJECT.test(value)) throw new MaritimeMailboxError("maritime_mailbox_input_invalid");
  return value.toLowerCase();
}

function validAttemptId(value) {
  if (typeof value !== "string" || !ATTEMPT_ID.test(value)) throw new MaritimeMailboxError("maritime_mailbox_input_invalid");
  return value.toLowerCase();
}

function validChallengeId(value) {
  if (typeof value !== "string" || !CHALLENGE_ID.test(value)) throw new MaritimeMailboxError("maritime_mailbox_input_invalid");
  return value;
}

function validTime(value) {
  let parsed;
  try { parsed = typeof value === "string" || value instanceof Date ? new Date(value) : null; }
  catch { throw new MaritimeMailboxError("maritime_mailbox_input_invalid"); }
  if (!parsed || !Number.isFinite(parsed.getTime())) throw new MaritimeMailboxError("maritime_mailbox_input_invalid");
  return parsed.toISOString();
}

function clientIdFor(tenantId) {
  return `life-manager-${validUid(tenantId)}`;
}

function providerEmail(value) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function senderAddress(value) {
  if (typeof value === "string") {
    const raw = value.trim();
    const match = raw.match(/^[^<>]*<([^<>]+)>$/);
    const address = match ? match[1].trim() : raw;
    return /^[^\s<>@]+@[^\s<>@]+$/.test(address) ? address.toLowerCase() : "";
  }
  if (value && typeof value === "object") {
    return senderAddress(value.email || value.address || value.from || "");
  }
  return "";
}

function capafyDomain(value) {
  return typeof value === "string" && /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*capafy\.ai$/i.test(value.trim());
}

function authenticatedCapafyMessage(message) {
  if (!Array.isArray(message?.labels) || message.labels.some(label =>
    typeof label === "string" && label.toLowerCase() === "unauthenticated")) return false;
  const address = senderAddress(message?.from);
  if (!CAPAFY_SENDER.test(address)) return false;
  const auth = message?.authentication_results;
  if (!auth || typeof auth !== "object") return false;
  const alignedPass = (auth.spf === "pass" && capafyDomain(auth.spf_domain))
    || (auth.dkim === "pass" && capafyDomain(auth.dkim_domain))
    || (auth.dmarc === "pass" && capafyDomain(auth.dmarc_domain));
  return Boolean(alignedPass);
}

function messageTime(message) {
  const value = message?.timestamp || message?.created_at;
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function verificationCode(message) {
  const fields = [message?.subject, message?.text, message?.extracted_text, message?.preview,
    message?.html, message?.extracted_html];
  if (fields.some(value => value != null && (typeof value !== "string" || Buffer.byteLength(value) > 32_768))) return null;
  const text = fields.map(value => value || "").join("\n");
  if (!CODE_CONTEXT.test(text)) return null;
  const codes = new Set([...text.matchAll(/(?<!\d)\d{4,8}(?!\d)/g)].map(match => match[0]));
  return codes.size === 1 ? [...codes][0] : null;
}

function createAgentMailMailboxProvider({ apiKey, fetchImpl = globalThis.fetch } = {}) {
  const key = String(apiKey || "");
  if (typeof fetchImpl !== "function") throw new MaritimeMailboxError("maritime_mailbox_unavailable");

  async function request(path, { method = "GET", body } = {}) {
    if (!key) throw new MaritimeMailboxError("maritime_mailbox_unconfigured");
    let response;
    try {
      response = await fetchImpl(`${API_BASE}${path}`, {
        method,
        redirect: "error",
        signal: AbortSignal.timeout(15_000),
        headers: { accept: "application/json", authorization: `Bearer ${key}`,
          ...(body === undefined ? {} : { "content-type": "application/json" }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch {
      throw new MaritimeMailboxError(method === "POST"
        ? "maritime_mailbox_create_effect_unknown" : "maritime_mailbox_read_unavailable", method === "POST");
    }
    if (!response || response.ok !== true) {
      const unknown = method === "POST" && (!Number.isInteger(response?.status) || response.status >= 500);
      throw new MaritimeMailboxError(unknown ? "maritime_mailbox_create_effect_unknown"
        : method === "POST" ? "maritime_mailbox_create_rejected" : "maritime_mailbox_read_unavailable", unknown);
    }
    try { return await response.json(); }
    catch { throw new MaritimeMailboxError(method === "POST"
      ? "maritime_mailbox_create_effect_unknown" : "maritime_mailbox_read_unavailable", method === "POST"); }
  }

  async function createInbox({ tenantId } = {}) {
    const uid = validUid(tenantId);
    const clientId = clientIdFor(uid);
    const payload = await request("/inboxes", { method: "POST", body: {
      client_id: clientId,
      display_name: "Life Manager verification",
    } });
    const inboxId = payload && payload.inbox_id;
    const email = providerEmail(payload && payload.email);
    if (!payload || typeof inboxId !== "string" || !INBOX_ID.test(inboxId)
      || !EMAIL.test(email) || (payload.client_id != null && payload.client_id !== clientId)
      || (payload.status != null && payload.status !== "active")) {
      throw new MaritimeMailboxError("maritime_mailbox_provider_receipt_invalid", true);
    }
    return Object.freeze({ provider: "agentmail", tenantId: uid, inboxId, email, clientId });
  }

  async function readCapafyVerificationCode({ inboxId, afterMs } = {}) {
    if (typeof inboxId !== "string" || !INBOX_ID.test(inboxId)
      || !Number.isFinite(afterMs) || afterMs < 0) throw new MaritimeMailboxError("maritime_mailbox_input_invalid");
    const path = `/inboxes/${encodeURIComponent(inboxId)}/messages?limit=20`;
    const payload = await request(path);
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.messages)) {
      throw new MaritimeMailboxError("maritime_mailbox_read_unavailable");
    }
    const messages = payload.messages;
    const candidates = messages.filter(message => {
      const at = messageTime(message);
      return at != null && at >= afterMs && CAPAFY_SENDER.test(senderAddress(message?.from))
        && CODE_CONTEXT.test(String(message?.subject || ""));
    }).sort((a, b) => messageTime(b) - messageTime(a));
    for (const message of candidates.slice(0, 3)) {
      const messageId = typeof message.message_id === "string" ? message.message_id : "";
      if (!messageId || messageId.length > 512 || /[\r\n]/.test(messageId)) continue;
      const detail = await request(`/inboxes/${encodeURIComponent(inboxId)}/messages/${encodeURIComponent(messageId)}`);
      if (!detail || typeof detail !== "object" || detail.message_id !== messageId
        || typeof detail.from !== "string" || typeof detail.subject !== "string" || messageTime(detail) == null
        || messageTime(detail) < afterMs) {
        throw new MaritimeMailboxError("maritime_mailbox_read_unavailable");
      }
      if (!authenticatedCapafyMessage(detail)) continue;
      const code = verificationCode(detail);
      if (code) return Object.freeze({ status: "code", code });
    }
    return Object.freeze({ status: "not_found" });
  }

  return Object.freeze({ createInbox, readCapafyVerificationCode });
}

function validateMailboxRow(row, identity) {
  const uid = validUid(row?.uid);
  const authSubject = validSubject(row?.auth_subject);
  const inboxId = row?.inbox_id;
  const email = providerEmail(row?.email);
  const clientId = row?.client_id;
  if (uid !== identity.tenantId || authSubject !== identity.authSubject
    || typeof inboxId !== "string" || !INBOX_ID.test(inboxId) || !EMAIL.test(email)
    || clientId !== clientIdFor(identity.tenantId)
    || !Number.isFinite(Date.parse(String(row?.created_at || "")))) {
    throw new MaritimeMailboxError("maritime_mailbox_binding_invalid");
  }
  return Object.freeze({ connected: true, provider: "agentmail", tenantId: uid,
    inboxId, email, clientId });
}

function createMaritimeManagerMailboxStore({ query, provider, now = () => new Date().toISOString() } = {}) {
  if (typeof query !== "function" || typeof provider?.createInbox !== "function"
    || typeof provider?.readCapafyVerificationCode !== "function") {
    throw new MaritimeMailboxError("maritime_mailbox_unconfigured");
  }

  async function readRow(identity) {
    let result;
    try {
      result = await query(`SELECT uid,auth_subject,inbox_id,email,client_id,created_at
        FROM private.lm_maritime_manager_mailboxes WHERE uid=$1 AND auth_subject=$2 LIMIT 2`,
      [identity.tenantId, identity.authSubject]);
    } catch { throw new MaritimeMailboxError("maritime_mailbox_store_unavailable"); }
    if (!result || !Array.isArray(result.rows) || result.rows.length > 1) {
      throw new MaritimeMailboxError("maritime_mailbox_binding_invalid");
    }
    return result.rows[0] || null;
  }

  async function read(input = {}) {
    const identity = { tenantId: validUid(input.tenantId), authSubject: validSubject(input.authSubject) };
    const row = await readRow(identity);
    return row ? validateMailboxRow(row, identity) : null;
  }

  async function ensure(input = {}) {
    const identity = { tenantId: validUid(input.tenantId), authSubject: validSubject(input.authSubject) };
    const existing = await read(identity);
    if (existing) return existing;
    const mailbox = await provider.createInbox({ tenantId: identity.tenantId });
    if (mailbox?.provider !== "agentmail" || mailbox.tenantId !== identity.tenantId
      || mailbox.clientId !== clientIdFor(identity.tenantId) || !INBOX_ID.test(mailbox.inboxId || "")
      || !EMAIL.test(providerEmail(mailbox.email))) throw new MaritimeMailboxError("maritime_mailbox_provider_receipt_invalid", true);
    let createdAt;
    try { createdAt = new Date(now()).toISOString(); }
    catch { throw new MaritimeMailboxError("maritime_mailbox_store_unavailable", true); }
    let result;
    try {
      result = await query(`INSERT INTO private.lm_maritime_manager_mailboxes
        (uid,auth_subject,inbox_id,email,client_id,created_at)
        VALUES ($1,$2,$3,$4,$5,$6::timestamptz)
        ON CONFLICT (uid) DO NOTHING
        RETURNING uid,auth_subject,inbox_id,email,client_id,created_at`,
      [identity.tenantId, identity.authSubject, mailbox.inboxId, mailbox.email, mailbox.clientId, createdAt]);
    } catch { throw new MaritimeMailboxError("maritime_mailbox_persist_effect_unknown", true); }
    if (Array.isArray(result?.rows) && result.rows.length === 1) return validateMailboxRow(result.rows[0], identity);
    const raced = await readRow(identity);
    const bound = raced ? validateMailboxRow(raced, identity) : null;
    if (!bound || bound.inboxId !== mailbox.inboxId || bound.email !== mailbox.email) {
      throw new MaritimeMailboxError("maritime_mailbox_persist_effect_unknown", true);
    }
    return bound;
  }

  async function readCapafyVerificationCode(input = {}) {
    const identity = { tenantId: validUid(input.tenantId), authSubject: validSubject(input.authSubject) };
    if (!Number.isFinite(input.afterMs) || input.afterMs < 0) throw new MaritimeMailboxError("maritime_mailbox_input_invalid");
    const mailbox = await read(identity);
    if (!mailbox) return Object.freeze({ status: "not_found" });
    return provider.readCapafyVerificationCode({ inboxId: mailbox.inboxId, afterMs: input.afterMs });
  }

  async function updateChallenge(statement, values) {
    let result;
    try { result = await query(statement, values); }
    catch { throw new MaritimeMailboxError("maritime_mailbox_challenge_store_unavailable"); }
    if (!result || !Array.isArray(result.rows) || result.rows.length > 1) {
      throw new MaritimeMailboxError("maritime_mailbox_challenge_state_invalid");
    }
    return result.rows.length === 1;
  }

  async function reserveCapafyChallenge(input = {}) {
    const tenantId = validUid(input.tenantId), authSubject = validSubject(input.authSubject);
    const attemptId = validAttemptId(input.attemptId), startedAt = validTime(input.startedAt);
    const leaseExpiresAt = validTime(input.leaseExpiresAt);
    if (Date.parse(leaseExpiresAt) <= Date.parse(startedAt)
      || Date.parse(leaseExpiresAt) - Date.parse(startedAt) > 600_000) {
      throw new MaritimeMailboxError("maritime_mailbox_input_invalid");
    }
    return updateChallenge(`UPDATE private.lm_maritime_manager_mailboxes
      SET capafy_challenge_status='starting', capafy_challenge_attempt_id=$3,
        capafy_challenge_id=NULL, capafy_challenge_started_at=$4::timestamptz,
        capafy_challenge_expires_at=$5::timestamptz,
        capafy_challenge_verification_lease_expires_at=NULL
      WHERE uid=$1 AND auth_subject=$2 AND (capafy_challenge_status IS NULL
        OR (capafy_challenge_status IN ('starting','pending')
          AND capafy_challenge_expires_at <= $4::timestamptz)
        OR (capafy_challenge_status='verifying'
          AND capafy_challenge_verification_lease_expires_at <= $4::timestamptz))
      RETURNING uid`, [tenantId, authSubject, attemptId, startedAt, leaseExpiresAt]);
  }

  async function bindCapafyChallenge(input = {}) {
    const tenantId = validUid(input.tenantId), authSubject = validSubject(input.authSubject);
    const attemptId = validAttemptId(input.attemptId), challengeId = validChallengeId(input.challengeId);
    const expiresAt = validTime(input.expiresAt);
    return updateChallenge(`UPDATE private.lm_maritime_manager_mailboxes
      SET capafy_challenge_status='pending', capafy_challenge_attempt_id=NULL,
        capafy_challenge_id=$4, capafy_challenge_expires_at=$5::timestamptz,
        capafy_challenge_verification_lease_expires_at=NULL
      WHERE uid=$1 AND auth_subject=$2 AND capafy_challenge_status='starting'
        AND capafy_challenge_attempt_id=$3 AND capafy_challenge_expires_at >= $5::timestamptz
        AND capafy_challenge_started_at < $5::timestamptz
      RETURNING uid`, [tenantId, authSubject, attemptId, challengeId, expiresAt]);
  }

  async function claimCapafyChallengeVerification(input = {}) {
    const tenantId = validUid(input.tenantId), authSubject = validSubject(input.authSubject);
    const challengeId = validChallengeId(input.challengeId), current = validTime(input.now);
    const leaseExpiresAt = new Date(Date.parse(current) + CHALLENGE_VERIFY_LEASE_MS).toISOString();
    return updateChallenge(`UPDATE private.lm_maritime_manager_mailboxes
      SET capafy_challenge_status='verifying', capafy_challenge_verification_lease_expires_at=$4::timestamptz
      WHERE uid=$1 AND auth_subject=$2 AND capafy_challenge_status='pending'
        AND capafy_challenge_id=$3 AND capafy_challenge_expires_at > $5::timestamptz
      RETURNING uid`, [tenantId, authSubject, challengeId, leaseExpiresAt, current]);
  }

  async function renewCapafyChallengeVerification(input = {}) {
    const tenantId = validUid(input.tenantId), authSubject = validSubject(input.authSubject);
    const challengeId = validChallengeId(input.challengeId), current = validTime(input.now);
    const leaseExpiresAt = validTime(input.leaseExpiresAt);
    if (Date.parse(leaseExpiresAt) <= Date.parse(current)
      || Date.parse(leaseExpiresAt) - Date.parse(current) > CHALLENGE_VERIFY_LEASE_MS) {
      throw new MaritimeMailboxError("maritime_mailbox_input_invalid");
    }
    return updateChallenge(`UPDATE private.lm_maritime_manager_mailboxes
      SET capafy_challenge_verification_lease_expires_at=$4::timestamptz
      WHERE uid=$1 AND auth_subject=$2 AND capafy_challenge_status='verifying'
        AND capafy_challenge_id=$3 AND capafy_challenge_expires_at > $5::timestamptz
        AND capafy_challenge_verification_lease_expires_at > $5::timestamptz
      RETURNING uid`, [tenantId, authSubject, challengeId, leaseExpiresAt, current]);
  }

  async function releaseCapafyChallengeVerification(input = {}) {
    const tenantId = validUid(input.tenantId), authSubject = validSubject(input.authSubject);
    const challengeId = validChallengeId(input.challengeId);
    return updateChallenge(`UPDATE private.lm_maritime_manager_mailboxes
      SET capafy_challenge_status='pending', capafy_challenge_verification_lease_expires_at=NULL
      WHERE uid=$1 AND auth_subject=$2 AND capafy_challenge_status='verifying'
        AND capafy_challenge_id=$3
      RETURNING uid`, [tenantId, authSubject, challengeId]);
  }

  async function completeCapafyChallenge(input = {}) {
    const tenantId = validUid(input.tenantId), authSubject = validSubject(input.authSubject);
    const challengeId = validChallengeId(input.challengeId);
    return updateChallenge(`UPDATE private.lm_maritime_manager_mailboxes
      SET capafy_challenge_status=NULL, capafy_challenge_attempt_id=NULL, capafy_challenge_id=NULL,
        capafy_challenge_started_at=NULL, capafy_challenge_expires_at=NULL,
        capafy_challenge_verification_lease_expires_at=NULL
      WHERE uid=$1 AND auth_subject=$2 AND capafy_challenge_status='verifying'
        AND capafy_challenge_id=$3
      RETURNING uid`, [tenantId, authSubject, challengeId]);
  }

  return Object.freeze({ ensure, read, readCapafyVerificationCode, reserveCapafyChallenge,
    bindCapafyChallenge, claimCapafyChallengeVerification, renewCapafyChallengeVerification,
    releaseCapafyChallengeVerification,
    completeCapafyChallenge });
}

module.exports = { createAgentMailMailboxProvider, createMaritimeManagerMailboxStore,
  clientIdFor, verificationCode };
