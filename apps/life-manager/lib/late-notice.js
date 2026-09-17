// LM-30 location-gated late notice decision core + Supabase helpers.
// A fresh Telegram live location is the only gate. The scheduler observes and reports; it never asks.
"use strict";

const { isHelperBlock } = require("./wake-filter.js");
const { shouldMarkAnswered } = require("./answered.js");
const { recordTelnyxWakeReceipt, recordTelnyxWakeOutcome } = require("./telnyx-receipt.js");
const { resolveLateRecipients } = require("./late-recipient-resolver.js");
const {
  createLateDraft,
  createLateApprovalCallbackData,
  recordLateApprovalCard,
  createSupabaseLateApprovalStore,
} = require("./late-approval.js");

const NO_DESTINATION_MESSAGE = "⚠️ 先方の連絡先が見つからず、遅刻連絡は送れていません";
const MAIL_FAILURE_MESSAGE = "⚠️ 遅刻連絡メールを送信できませんでした";
const MAX_PROVIDER_ID_LENGTH = 512;

function validProviderId(value) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= MAX_PROVIDER_ID_LENGTH;
}

// sendMessage uses Telegram's HTML parse mode globally.  Card text contains calendar-controlled
// recipient names, addresses, evidence, and event text, so send the wire copy escaped while keeping
// the unescaped request snapshot available to the callback/contract boundary.
function escapeTelegramHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function evaluateLateArrival({ nowMs, event, travelMinutes, location }) {
  if (!location) return { decision: "location_missing" };
  const expiresMs = Date.parse(location.expires_at || location.expiresAt || "");
  if (!Number.isFinite(expiresMs) || expiresMs <= nowMs) return { decision: "location_expired" };
  if (!event || !Number.isFinite(event.startMs)) return { decision: "no_event" };
  if (!Number.isFinite(travelMinutes) || travelMinutes < 0) return { decision: "route_unavailable" };
  const arrivalMs = nowMs + travelMinutes * 60_000;
  const lateMinutes = Math.max(0, Math.ceil((arrivalMs - event.startMs) / 60_000));
  return { decision: arrivalMs > event.startMs ? "late" : "on_time", arrivalMs, lateMinutes };
}

function offsetMinutes(iso) {
  if (/Z$/i.test(String(iso || ""))) return 0;
  const match = /([+-])(\d{2}):(\d{2})$/.exec(String(iso || ""));
  if (!match) return 0;
  const minutes = Number(match[2]) * 60 + Number(match[3]);
  return match[1] === "-" ? -minutes : minutes;
}

function clockAt(ms, referenceIso) {
  const shifted = new Date(ms + offsetMinutes(referenceIso) * 60_000);
  return `${String(shifted.getUTCHours()).padStart(2, "0")}:${String(shifted.getUTCMinutes()).padStart(2, "0")}`;
}

function roundedEtaMinutes(minutes) {
  return Math.max(5, Math.ceil(minutes / 5) * 5);
}

function formatLateSuccessMessage(event, arrivalMs, lateMinutes) {
  const eta = roundedEtaMinutes(lateMinutes);
  return `📨 現在地から見て${clockAt(event.startMs, event.startIso)}に間に合わないため、先方に「${eta}分ほど遅れます」とメールを送っておきました。次の電車なら${clockAt(arrivalMs, event.startIso)}着です。`;
}

function externalAttendees(event) {
  return (event && Array.isArray(event.attendees) ? event.attendees : [])
    .filter((attendee) => attendee && attendee.email && !attendee.self && !attendee.organizer)
    .map((attendee) => attendee.email);
}

function locationOrigin(location) {
  return `${Number(location.latitude)},${Number(location.longitude)}`;
}

function eventKey(event) {
  return String(event.id || `${event.startIso || event.startMs}|${event.summary || "event"}`);
}

function lateRecipientStatus(status) {
  if (status === "resolved") return "resolved";
  if (status === "ambiguous" || status === "recipient_ambiguous") return "recipient_ambiguous";
  return "recipient_missing";
}

function userActorEmails(user = {}) {
  return [
    user.email,
    user.email_address,
    user.emailAddress,
    ...(Array.isArray(user.emails) ? user.emails : []),
  ].filter(Boolean);
}

function normalizeRecipientResolution(result) {
  const value = result && typeof result === "object" ? result : {};
  const candidates = Array.isArray(value.candidates) ? value.candidates : [];
  const status = value.status || value.recipientStatus || value.recipient_status;
  return {
    status: status === "resolved" ? "resolved" : (status === "ambiguous" || status === "recipient_ambiguous" ? "ambiguous" : "missing"),
    candidates,
    evidenceRefs: Array.isArray(value.evidenceRefs)
      ? value.evidenceRefs
      : (Array.isArray(value.evidence_refs) ? value.evidence_refs : []),
  };
}

function lateBodySnapshot(event, user, etaMinutes) {
  const name = user && user.name ? user.name : "Your contact";
  const meeting = event && event.summary ? event.summary : "the meeting";
  const eta = Number.isFinite(etaMinutes) ? `about ${etaMinutes} minutes` : "a little";
  return `Hi — ${name} is running ${eta} late to “${meeting}” and wanted you to know.\n\n` +
    `(Sent automatically by Life Manager on ${name}'s behalf — reply to reach ${name} directly.)`;
}

function lateEtaSnapshot({ nowMs, event, location, travelMinutes, assessment, etaMinutes }) {
  return {
    basis: "route_eta_from_live_location",
    calculatedAt: new Date(nowMs).toISOString(),
    routeMinutes: travelMinutes,
    lateMinutes: assessment.lateMinutes,
    etaMinutes,
    arrivalMs: assessment.arrivalMs,
    arrivalIso: new Date(assessment.arrivalMs).toISOString(),
    eventStartMs: event.startMs,
    eventStartIso: event.startIso || new Date(event.startMs).toISOString(),
    locationObservedAt: location.observed_at || location.observedAt || location.observed_at_ms || null,
    locationExpiresAt: location.expires_at || location.expiresAt || location.expires_at_ms || null,
  };
}

function lateApprovalCardRequest(input, event, draft) {
  const recipients = draft.recipients.map((recipient) => {
    const name = recipient.display_name || recipient.displayName || "(名前不明)";
    return `${name} <${recipient.email}>`;
  }).join(", ");
  const sources = draft.recipients.map((recipient) => recipient.source || "unknown").join(", ");
  const evidence = draft.recipients.flatMap((recipient) => recipient.evidence_refs || []).join(", ");
  const eta = draft.etaEvidence || {};
  const text = [
    "⚠️ 遅刻連絡の確認",
    `宛先: ${recipients}`,
    `source: ${sources}`,
    `evidence: ${evidence || "none"}`,
    `ETA根拠: ${eta.basis || "unknown"} (${eta.routeMinutes}分 → ${eta.etaMinutes}分遅れ見込み)`,
    "",
    draft.bodySnapshot,
  ].join("\n");
  const callbackSecret = input.callbackSecret || input.lateApprovalCallbackSecret;
  const callbackNowMs = input.nowMs === undefined ? Date.now() : input.nowMs;
  const callbackExpiresAtMs = input.callbackExpiresAtMs === undefined
    ? callbackNowMs + 10 * 60_000
    : input.callbackExpiresAtMs;
  const draftId = String(draft.draftId);
  return {
    token: input.telegramToken,
    chatId: input.user && input.user.telegram_chat_id,
    text,
    extra: {
      reply_markup: {
        inline_keyboard: [[
          {
            text: "送る",
            callback_data: createLateApprovalCallbackData({
              action: "send", draftId, secret: callbackSecret,
              nowMs: callbackNowMs, expiresAtMs: callbackExpiresAtMs,
            }),
          },
          {
            text: "送らない",
            callback_data: createLateApprovalCallbackData({
              action: "do_not_send", draftId, secret: callbackSecret,
              nowMs: callbackNowMs, expiresAtMs: callbackExpiresAtMs,
            }),
          },
        ]],
      },
    },
    draft,
    event,
  };
}

async function enqueueLateApprovalCard(input, event, draft, deps) {
  const request = lateApprovalCardRequest(input, event, draft);
  if (!request.token || !request.chatId) return { queued: false, reason: "telegram_unavailable", request };
  const enqueue = deps.enqueueLateApprovalCard || deps.enqueueApprovalCard || deps.enqueueTelegramApprovalCard;
  if (typeof enqueue === "function") return { ...(await enqueue(request) || {}), request };
  if (typeof deps.sendMessage !== "function") return { queued: false, reason: "telegram_unavailable", request };
  const sent = await deps.sendMessage(
    request.token,
    request.chatId,
    escapeTelegramHtml(request.text),
    request.extra,
  );
  const result = { queued: Boolean(sent && sent.ok !== false), request };
  const messageId = sent && sent.result && sent.result.message_id;
  if (messageId !== undefined && messageId !== null) {
    result.telegramMessageId = messageId;
    const store = deps.lateApprovalStore || deps.approvalStore || input.lateApprovalStore;
    let productionStore = store;
    if (!productionStore && (deps.supaUrl || input.supaUrl)) {
      try {
        productionStore = createSupabaseLateApprovalStore({
          supaUrl: deps.supaUrl || input.supaUrl,
          supaKey: deps.supaKey || input.supaKey,
          fetchImpl: deps.fetchImpl || input.fetchImpl,
        });
      } catch {
        productionStore = null;
      }
    }
    const recorder = deps.recordLateApprovalCard ||
      (productionStore && typeof productionStore.recordLateApprovalCard === "function" ?
        (input) => recordLateApprovalCard(input, productionStore) : null);
    if (recorder) {
      try {
        result.draft = await recorder({
          uid: input.user && input.user.uid,
          draftId: draft.draftId,
          chatId: request.chatId,
          telegramMessageId: String(messageId),
        });
      } catch (error) {
        // Telegram accepted the card, so never send a second card. The callback update still carries
        // this message id and can repair the durable record before editing the same card on receipt.
        result.cardRecordFailed = true;
        result.cardRecordError = String(error && error.message || error);
      }
    }
  }
  return result;
}

function cloneLateDraft(value) {
  if (!value || typeof value !== "object") return null;
  return JSON.parse(JSON.stringify(value));
}

function normalizeExistingLateDraft(value) {
  if (Array.isArray(value)) return normalizeExistingLateDraft(value[0]);
  if (!value || typeof value !== "object") return null;
  const row = value.row && typeof value.row === "object" ? value.row : value;
  const draftId = row.draftId || row.draft_id;
  if (!draftId) return null;
  const draft = {
    ...row,
    draftId,
    uid: row.uid,
    eventKey: row.eventKey || row.event_key,
    status: row.status,
    recipientStatus: row.recipientStatus || row.recipient_status,
    recipients: row.recipients || row.recipient_snapshot || [],
    evidenceSnapshot: row.evidenceSnapshot || row.evidence_snapshot || {},
    bodySnapshot: row.bodySnapshot || row.body_snapshot,
    etaEvidence: row.etaEvidence || row.eta_evidence_snapshot || {},
  };
  return cloneLateDraft(draft);
}

async function findExistingLateDraft(input, event, deps) {
  const uid = input.user && input.user.uid;
  const key = eventKey(event);
  const request = { uid, eventKey: key, event_key: key };
  const direct = deps.getLateDraft || deps.findLateDraft;
  if (typeof direct === "function") {
    try { return normalizeExistingLateDraft(await direct(request)); } catch { return null; }
  }

  const store = deps.lateApprovalStore || deps.approvalStore || input.lateApprovalStore;
  if (store && typeof store.getLateDraft === "function") {
    try { return normalizeExistingLateDraft(await store.getLateDraft(request)); } catch { return null; }
  }
  if (store && typeof store.findLateDraft === "function") {
    try { return normalizeExistingLateDraft(await store.findLateDraft(request)); } catch { return null; }
  }
  if (store && typeof store.getDraftByEventKey === "function") {
    try { return normalizeExistingLateDraft(await store.getDraftByEventKey(uid, key)); } catch { return null; }
  }

  // Production fallback: the approval RPC is intentionally create-only, so the tick reads the
  // immutable row first through service-role PostgREST. A failed read is fail-closed for the card
  // path but does not weaken the Task 2 collision guard: createLateDraft still owns collision checks.
  const supaUrl = String(deps.supaUrl || input.supaUrl || process.env.SUPABASE_URL || "").replace(/\/$/, "");
  const supaKey = deps.supaKey || input.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  const fetchImpl = deps.fetchImpl || input.fetchImpl || globalThis.fetch;
  if (!supaUrl || !supaKey || typeof fetchImpl !== "function") return null;
  const url = `${supaUrl}/rest/v1/lm_late_approval_drafts?uid=eq.${encodeURIComponent(uid)}` +
    `&event_key=eq.${encodeURIComponent(key)}&select=*&limit=1`;
  try {
    const response = await fetchImpl(url, { headers: supaHeaders(supaKey) });
    if (!response || !response.ok) return null;
    return normalizeExistingLateDraft(await response.json());
  } catch {
    return null;
  }
}

function existingLateDraftResult(draft) {
  const duplicate = { ...draft, duplicate: true };
  return {
    decision: "late",
    sent: false,
    notified: false,
    approvalRequired: draft.status === "awaiting_decision",
    draft: duplicate,
  };
}

async function processLocationLateNotice(input, deps = {}) {
  const nowMs = input.nowMs === undefined ? Date.now() : input.nowMs;
  const candidates = (input.events || []).filter((candidate) => candidate && !isHelperBlock(candidate.summary) &&
    candidate.location && Number.isFinite(candidate.startMs));
  const gate = evaluateLateArrival({ nowMs, event: candidates[0] || null, travelMinutes: null, location: input.location });
  if (["location_missing", "location_expired", "no_event"].includes(gate.decision)) return gate;

  // A meeting we already acted on must not hide the rest of the day. Seen in production 2026-07-25:
  // an all-day located event was claimed in the morning and ran until evening, so every later event
  // was unreachable — continue to the next event if the first one is not late.
  for (const event of candidates) {
    const existing = await findExistingLateDraft(input, event, deps);
    if (existing) return existingLateDraftResult(existing);

    const travelMinutes = await deps.routeMinutes(
      locationOrigin(input.location), event.location, input.mapsKey, event.startMs, nowMs,
    );
    const assessment = evaluateLateArrival({ nowMs, event, travelMinutes, location: input.location });
    if (assessment.decision !== "late") return assessment;

    const resolver = deps.resolveLateRecipients || deps.recipientResolver || resolveLateRecipients;
    let resolution;
    try {
      resolution = normalizeRecipientResolution(await resolver({
        uid: input.user && input.user.uid,
        event,
        actorEmails: userActorEmails(input.user),
      }, deps.recipientResolverDeps || deps));
    } catch (error) {
      resolution = { status: "missing", candidates: [], evidenceRefs: [], error: String(error && error.message || error) };
    }
    const etaMinutes = roundedEtaMinutes(assessment.lateMinutes);
    const recipientStatus = lateRecipientStatus(resolution.status);
    const draftInput = {
      uid: input.user && input.user.uid,
      eventKey: eventKey(event),
      recipientStatus,
      recipients: resolution.candidates,
      evidenceSnapshot: {
        refs: resolution.evidenceRefs,
        candidates: resolution.candidates,
        status: resolution.status,
      },
      bodySnapshot: lateBodySnapshot(event, input.user || {}, etaMinutes),
      etaEvidence: lateEtaSnapshot({ nowMs, event, location: input.location, travelMinutes, assessment, etaMinutes }),
      nowMs,
    };
    let draft;
    try {
      const persistDraft = deps.createLateDraft || createLateDraft;
      draft = await persistDraft(draftInput, deps.lateApprovalStore || deps.approvalStore || input.lateApprovalStore);
    } catch (error) {
      return {
        ...assessment,
        sent: false,
        notified: false,
        reason: "draft_failed",
        error: String(error && error.message || error),
      };
    }

    const result = {
      ...assessment,
      decision: "late",
      sent: false,
      notified: false,
      approvalRequired: draft.status === "awaiting_decision",
      draft,
    };
    if (draft.status !== "awaiting_decision" || draft.duplicate) return result;
    const card = await enqueueLateApprovalCard(input, event, draft, deps);
    result.card = card;
    result.notified = Boolean(card && card.queued);
    if (card && card.telegramMessageId !== undefined) result.telegramMessageId = card.telegramMessageId;
    return result;
  }
  return gate;
}

function supaHeaders(key, prefer) {
  return {
    apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json",
    ...(prefer ? { Prefer: prefer } : {}),
  };
}

async function upsertLiveLocation(uid, location, opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!opts.supaUrl || !opts.supaKey || !uid || !location ||
      !Number.isFinite(location.latitude) || !Number.isFinite(location.longitude) ||
      !Number.isFinite(location.observedAtMs) || !Number.isFinite(location.expiresAtMs) ||
      location.expiresAtMs <= location.observedAtMs) return false;
  const response = await f(`${opts.supaUrl}/rest/v1/lm_user_locations?on_conflict=uid`, {
    method: "POST",
    headers: supaHeaders(opts.supaKey, "resolution=merge-duplicates,return=minimal"),
    body: JSON.stringify({
      uid,
      latitude: location.latitude,
      longitude: location.longitude,
      telegram_message_id: String(location.messageId || ""),
      source: "telegram_live_location",
      observed_at: new Date(location.observedAtMs).toISOString(),
      expires_at: new Date(location.expiresAtMs).toISOString(),
    }),
  }).catch(() => null);
  return Boolean(response && response.ok);
}

async function getLiveLocation(uid, nowMs = Date.now(), opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!opts.supaUrl || !opts.supaKey || !uid) return null;
  const url = `${opts.supaUrl}/rest/v1/lm_user_locations?uid=eq.${encodeURIComponent(uid)}&select=uid,latitude,longitude,observed_at,expires_at&limit=1`;
  const response = await f(url, { headers: supaHeaders(opts.supaKey) }).catch(() => null);
  if (!response || !response.ok) return null;
  const rows = await response.json().catch(() => []);
  const row = Array.isArray(rows) && rows[0] ? rows[0] : null;
  return row && Date.parse(row.expires_at) > nowMs ? row : null;
}

// /stop (spec §12.1 row 4): the user's manual disconnect. The uid filter is the tenant boundary — an
// unfiltered DELETE would wipe every user's fix, so the guard refuses to run without one. The Prefer
// header reads back what was removed: the caller reports the true count, and a request we could not
// complete returns null (unknown), never a comforting zero.
async function deleteLiveLocation(uid, opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!opts.supaUrl || !opts.supaKey || !uid) return null;
  const url = `${opts.supaUrl}/rest/v1/lm_user_locations?uid=eq.${encodeURIComponent(uid)}`;
  const response = await f(url, {
    method: "DELETE", headers: supaHeaders(opts.supaKey, "return=representation"),
  }).catch(() => null);
  if (!response || !response.ok) return null;
  const rows = await response.json().catch(() => null);
  if (!Array.isArray(rows)) return null;
  return { deleted: rows.length };
}

async function claimLateEvent(uid, key, opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!opts.supaUrl || !opts.supaKey || !uid || !key) return false;
  const response = await f(`${opts.supaUrl}/rest/v1/lm_late_notice_log`, {
    method: "POST", headers: supaHeaders(opts.supaKey, "return=minimal"),
    body: JSON.stringify({ uid, event_key: key }),
  }).catch(() => null);
  return Boolean(response && response.status === 201);
}

// spec §1.3: markAnswered used to answer `false` for BOTH "the PATCH matched zero rows" and "the
// request never landed", and its one caller threw the value away. That is how a rotated Telnyx
// signing key could silence every wake call forever while looking identical to a user who did not
// pick up. Every wake-log write now reports which of the three it was:
//
//   { ok: true,  matched: n>0 }  the write landed and changed n rows
//   { ok: true,  matched: 0   }  the write landed and correctly matched nothing (no such row / latched)
//   { ok: false, matched: 0, error } we never got a successful write — a recording failure
//
// A caller that ignores `error` is ignoring an outage, so call sites log the two apart.
async function patchWakeLog(uid, key, { filter = "", body, ...opts }) {
  const f = opts.fetchImpl || fetch;
  if (!opts.supaUrl || !opts.supaKey || !uid || !key) return { ok: false, matched: 0, error: "missing_args" };
  const url = `${opts.supaUrl}/rest/v1/lm_wake_log?uid=eq.${encodeURIComponent(uid)}` +
    `&event_key=eq.${encodeURIComponent(key)}${filter}&select=event_key`;
  const response = await f(url, {
    method: "PATCH", headers: supaHeaders(opts.supaKey, "return=representation"),
    body: JSON.stringify(body),
  }).catch(() => ({ __threw: "network_error" }));
  if (response && response.__threw) return { ok: false, matched: 0, error: response.__threw };
  if (!response || !response.ok) return { ok: false, matched: 0, error: `http_${(response && response.status) || "unknown"}` };
  const rows = await response.json().catch(() => null);
  if (!Array.isArray(rows)) return { ok: false, matched: 0, error: "unreadable_response" };
  return { ok: true, matched: rows.length };
}

// Wake-call answer telemetry remains useful to the authenticated Telnyx webhook even though it no
// longer unlocks or triggers a late notice. No new T-0 rows are created by this helper.
// The answered_at=is.null filter is a latch, not a lookup: the FIRST human proof wins and later
// events must not rewrite the moment the user picked up. That is why amd_result is a separate write
// below rather than an extra field here — fusing them would force this latch onto a column whose
// rule is the opposite (last observation wins, always recorded).
async function markAnswered(uid, key, opts = {}) {
  return patchWakeLog(uid, key, {
    ...opts,
    filter: "&answered_at=is.null",
    body: { answered_at: new Date(opts.nowMs || Date.now()).toISOString() },
  });
}

// spec §3 row 2: persist what AMD actually said, on EVERY detection. Unfiltered by answered_at on
// purpose (see above), and the value is stored verbatim — folding not_sure into machine, or dropping
// it, would put it straight back into the NULL bucket that means "we never heard anything".
async function recordAmdResult(uid, key, opts = {}) {
  const result = typeof opts.result === "string" ? opts.result.trim() : "";
  if (!result) return { ok: false, matched: 0, error: "missing_result" };
  return patchWakeLog(uid, key, { ...opts, body: { amd_result: result } });
}

// AMD is a probabilistic observation. Keep its raw result and mark human/not_sure as answered,
// but never end a paid user's call solely because a machine label might be wrong. The provider
// per-call time limit and monthly voice ledger still bound voicemail cost.
async function applyAmdDetection(uid, key, opts = {}) {
  const result = typeof opts.result === "string" ? opts.result.trim() : "";
  const claimBound = validProviderId(opts.claimToken);
  const amd = claimBound
    ? (!validProviderId(opts.webhookEventId)
      ? { ok: false, matched: 0, error: "missing_event_id" }
      : await recordTelnyxWakeReceipt({
        uid,
        eventKey: key,
        claimToken: opts.claimToken,
        callControlId: opts.callControlId,
        callSessionId: opts.callSessionId ?? null,
        callLegId: opts.callLegId ?? null,
        webhookEventId: opts.webhookEventId,
        amdResult: result,
      }, {
        supaUrl: opts.supaUrl,
        supaKey: opts.supaKey,
        fetchImpl: opts.fetchImpl,
      }))
    : await recordAmdResult(uid, key, opts);
  const outcome = claimBound && amd.ok === true && amd.matched === 1
    && (result === "human" || result === "not_sure")
    ? await recordTelnyxWakeOutcome({
      uid,
      eventKey: key,
      claimToken: opts.claimToken,
      callControlId: opts.callControlId,
      callOutcome: "conversation",
    }, {
      supaUrl: opts.supaUrl,
      supaKey: opts.supaKey,
      fetchImpl: opts.fetchImpl,
    })
    : null;
  if (shouldMarkAnswered({ amdEnabled: true, signal: "amd", result })) {
    const answered = claimBound && !(amd.ok && amd.matched === 1)
      ? { ok: true, matched: 0 }
      : await markAnswered(uid, key, opts);
    return { result, amd, outcome, answered, hangup: null };
  }
  return { result, amd, outcome, answered: null, hangup: null };
}

// Test calls have no wake row to update. A detection only returns the observed label;
// it cannot justify hanging up on someone who may be speaking.
async function applyTestCallDetection(opts = {}) {
  const result = typeof opts.result === "string" ? opts.result.trim() : "";
  return { result, hangup: null };
}

module.exports = {
  NO_DESTINATION_MESSAGE, MAIL_FAILURE_MESSAGE,
  evaluateLateArrival, formatLateSuccessMessage, externalAttendees,
  processLocationLateNotice, lateApprovalCardRequest, enqueueLateApprovalCard,
  upsertLiveLocation, getLiveLocation, deleteLiveLocation, claimLateEvent,
  markAnswered, recordAmdResult, applyAmdDetection, applyTestCallDetection,
};
