"use strict";

const MAX_UID_LENGTH = 256;
const MAX_EVENT_KEY_LENGTH = 512;
const MAX_PROVIDER_ID_LENGTH = 512;
const MAX_HANGUP_CAUSE_LENGTH = 512;
const AMD_RESULTS = new Set(["human", "machine", "not_sure"]);
const CALL_OUTCOMES = new Set(["conversation", "no_answer", "dial_failed"]);

function isRequiredText(value, maxLength) {
  return typeof value === "string"
    && value.trim().length > 0
    && value.length <= maxLength;
}

function isOptionalText(value) {
  return value === null || value === undefined
    || (typeof value === "string" && value.trim().length > 0 && value.length <= MAX_PROVIDER_ID_LENGTH);
}

function failure(error) {
  return { ok: false, matched: 0, error };
}

/**
 * Record the provider identity for one already-claimed wake row.
 *
 * The database RPC is the conflict arbiter. This client deliberately performs no read and never
 * retries: callers can reconcile an unknown response without risking a second provider effect.
 */
async function recordTelnyxWakeReceipt(input = {}, deps = {}) {
  input = input || {};
  deps = deps || {};
  const uid = input.uid;
  const eventKey = input.eventKey;
  const claimToken = input.claimToken;
  const callControlId = input.callControlId;
  const callSessionId = input.callSessionId ?? null;
  const callLegId = input.callLegId ?? null;
  const webhookEventId = input.webhookEventId ?? null;
  const amdResult = input.amdResult ?? null;

  if (!isRequiredText(uid, MAX_UID_LENGTH)
    || !isRequiredText(eventKey, MAX_EVENT_KEY_LENGTH)
    || !isRequiredText(claimToken, MAX_PROVIDER_ID_LENGTH)
    || !isRequiredText(callControlId, MAX_PROVIDER_ID_LENGTH)) {
    return failure("missing_args");
  }
  if (!isOptionalText(callSessionId) || !isOptionalText(callLegId) || !isOptionalText(webhookEventId)) {
    return failure("invalid_args");
  }
  if (amdResult !== null && (typeof amdResult !== "string" || !AMD_RESULTS.has(amdResult))) {
    return failure("invalid_amd_result");
  }

  const supaUrl = typeof deps.supaUrl === "string" ? deps.supaUrl.replace(/\/+$/, "") : "";
  const supaKey = typeof deps.supaKey === "string" ? deps.supaKey : "";
  if (!supaUrl || !supaKey) return failure("missing_config");
  const fetchImpl = deps.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== "function") return failure("network_error");

  const body = JSON.stringify({
    p_uid: uid,
    p_event_key: eventKey,
    p_claim_token: claimToken,
    p_telnyx_call_control_id: callControlId,
    p_telnyx_call_session_id: callSessionId,
    p_telnyx_call_leg_id: callLegId,
    p_telnyx_webhook_event_id: webhookEventId,
    p_amd_result: amdResult,
  });

  let response;
  try {
    response = await fetchImpl(`${supaUrl}/rest/v1/rpc/record_lm_wake_telnyx_receipt`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: supaKey,
        Authorization: `Bearer ${supaKey}`,
      },
      body,
    });
  } catch {
    return failure("network_error");
  }
  if (!response || response.status < 200 || response.status >= 300 || response.ok === false) {
    return failure("http_error");
  }

  let matched;
  try {
    matched = await response.json();
  } catch {
    return failure("unreadable_response");
  }
  if (!Number.isInteger(matched) || matched < 0) return failure("invalid_result");
  return { ok: true, matched };
}

async function recordTelnyxWakeOutcome(input = {}, deps = {}) {
  input = input || {};
  deps = deps || {};
  const uid = input.uid;
  const eventKey = input.eventKey;
  const claimToken = input.claimToken;
  const callControlId = input.callControlId;
  const callOutcome = input.callOutcome ?? null;
  const hangupCause = input.hangupCause ?? null;
  const connectedSeconds = input.connectedSeconds ?? null;
  if (!isRequiredText(uid, MAX_UID_LENGTH)
    || !isRequiredText(eventKey, MAX_EVENT_KEY_LENGTH)
    || !isRequiredText(claimToken, MAX_PROVIDER_ID_LENGTH)
    || !isRequiredText(callControlId, MAX_PROVIDER_ID_LENGTH)) {
    return failure("missing_args");
  }
  if (callOutcome !== null && (typeof callOutcome !== "string" || !CALL_OUTCOMES.has(callOutcome))) {
    return failure("invalid_outcome");
  }
  if (hangupCause !== null && (typeof hangupCause !== "string"
    || hangupCause.trim() === "" || hangupCause.length > MAX_HANGUP_CAUSE_LENGTH)) {
    return failure("invalid_hangup_cause");
  }
  if (connectedSeconds !== null && (!Number.isInteger(connectedSeconds) || connectedSeconds < 0 || connectedSeconds > 14400)) {
    return failure("invalid_connected_seconds");
  }
  const supaUrl = typeof deps.supaUrl === "string" ? deps.supaUrl.replace(/\/+$/, "") : "";
  const supaKey = typeof deps.supaKey === "string" ? deps.supaKey : "";
  if (!supaUrl || !supaKey) return failure("missing_config");
  const fetchImpl = deps.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== "function") return failure("network_error");
  const legacyOutcome = callOutcome === "no_answer" ? "machine"
    : callOutcome === "conversation" ? "human" : null;
  const recordLegacyOutcome = async () => {
    if (!legacyOutcome) return { ok: true, matched: 0, legacy: true };
    const legacyUrl = `${supaUrl}/rest/v1/lm_wake_log?uid=eq.${encodeURIComponent(uid)}`
      + `&event_key=eq.${encodeURIComponent(eventKey)}`
      + `&claim_token=eq.${encodeURIComponent(claimToken)}`
      + `&telnyx_call_control_id=eq.${encodeURIComponent(callControlId)}`
      + "&amd_result=is.null&select=event_key";
    let legacyResponse;
    try {
      legacyResponse = await fetchImpl(legacyUrl, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Prefer: "return=representation",
          apikey: supaKey,
          Authorization: `Bearer ${supaKey}`,
        },
        body: JSON.stringify({ amd_result: legacyOutcome }),
      });
    } catch {
      return failure("network_error");
    }
    if (!legacyResponse || !legacyResponse.ok) return failure("http_error");
    const rows = await legacyResponse.json().catch(() => null);
    if (!Array.isArray(rows)) return failure("unreadable_response");
    return { ok: true, matched: rows.length, legacy: true };
  };
  let response;
  try {
    response = await fetchImpl(`${supaUrl}/rest/v1/rpc/record_lm_wake_telnyx_outcome`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: supaKey,
        Authorization: `Bearer ${supaKey}`,
      },
      body: JSON.stringify({
        p_uid: uid,
        p_event_key: eventKey,
        p_claim_token: claimToken,
        p_telnyx_call_control_id: callControlId,
        p_call_outcome: callOutcome,
        p_hangup_cause: hangupCause,
        p_connected_seconds: connectedSeconds,
      }),
    });
  } catch {
    return failure("network_error");
  }
  if (response && response.status === 404) return recordLegacyOutcome();
  if (!response || response.status < 200 || response.status >= 300 || response.ok === false) {
    return failure("http_error");
  }
  let matched;
  try {
    matched = await response.json();
  } catch {
    return failure("unreadable_response");
  }
  if (!Number.isInteger(matched) || matched < 0) return failure("invalid_result");
  return { ok: true, matched };
}

module.exports = { recordTelnyxWakeReceipt, recordTelnyxWakeOutcome };
