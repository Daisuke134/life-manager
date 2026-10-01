"use strict";

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9:._-]{2,255}$/;
const SAFE_REASON = /^[a-z0-9][a-z0-9_:-]{1,99}$/;
const RECEIPT = /^(?:provider-receipt|gmail-message|calendar-evidence):\/\/[^\s]{3,1024}$/;

function invalid() {
  throw new Error("Connector outcome invalid");
}

function id(value, label) {
  const result = String(value == null ? "" : value).trim();
  if (!SAFE_ID.test(result)) invalid(`${label} invalid`);
  return result;
}

function optionalReceipt(value) {
  if (value == null) return null;
  const result = String(value).trim();
  if (!RECEIPT.test(result)) invalid("Connector receipt invalid");
  return result;
}

function classifyConnectorOutcome(input = {}) {
  if (!input || typeof input !== "object" || Array.isArray(input)) invalid();
  const result = input.result;
  if (!result || typeof result !== "object" || Array.isArray(result)) invalid();
  const occurrenceId = id(input.occurrence_id, "occurrence");
  const runId = id(input.run_id, "run");
  const releaseSha = String(input.release_sha || "unknown").trim();
  if (releaseSha !== "unknown" && !/^[0-9a-f]{40}$/.test(releaseSha)) invalid("release invalid");
  const status = String(result.status || "");
  const processStatus = ["applied_bundle", "completed_no_effect", "complete"].includes(status) ? "pass" : "fail";
  const journey = result.journey && typeof result.journey === "object" && !Array.isArray(result.journey)
    ? result.journey : {};
  const registration = journey.registration || {};
  const confirmation = journey.confirmation_mail || {};
  const calendar = journey.calendar || {};
  const occurrenceBound = (stage) => Boolean(
    stage && typeof stage === "object" && !Array.isArray(stage)
      && stage.occurrence_id === occurrenceId,
  );
  const providerReceiptRef = optionalReceipt(registration.provider_receipt_ref);
  const confirmationMailRef = optionalReceipt(confirmation.external_receipt_ref);
  const calendarEventRef = optionalReceipt(calendar.calendar_event_ref);
  const externalRegistrationStatus = status === "completed_no_effect"
    ? "not_attempted"
    : processStatus === "pass"
      && occurrenceBound(registration)
      && occurrenceBound(confirmation)
      && occurrenceBound(calendar)
      && providerReceiptRef && confirmationMailRef && calendarEventRef
      ? "verified" : "unknown";
  const safeReason = String(result.safe_reason || (status === "applied_bundle" ? "applied_bundle" : "unknown")).trim();
  if (!SAFE_REASON.test(safeReason)) invalid("safe reason invalid");
  return Object.freeze({
    schema_version: 1,
    occurrence_id: occurrenceId,
    run_id: runId,
    release_sha: releaseSha,
    process_status: processStatus,
    external_registration_status: externalRegistrationStatus,
    provider_receipt_ref: providerReceiptRef,
    confirmation_mail_ref: confirmationMailRef,
    calendar_event_ref: calendarEventRef,
    safe_reason: safeReason,
  });
}

module.exports = { classifyConnectorOutcome };
