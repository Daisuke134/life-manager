"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { classifyConnectorOutcome } = require("./connector-outcome.js");

const TRACE = Object.freeze({
  occurrence_id: "life-manager-connector-native:occurrence-1",
  run_id: "run-1",
  release_sha: "a".repeat(40),
});

test("a healthy process pass without a provider effect stays external-not-attempted", () => {
  assert.deepEqual(classifyConnectorOutcome({
    ...TRACE,
    result: { status: "completed_no_effect", safe_reason: "providers_exhausted", registration_attempted: false },
  }), {
    schema_version: 1,
    ...TRACE,
    process_status: "pass",
    external_registration_status: "not_attempted",
    provider_receipt_ref: null,
    confirmation_mail_ref: null,
    calendar_event_ref: null,
    safe_reason: "providers_exhausted",
  });
});

test("a reused bundle is not mislabeled as an unattempted external registration", () => {
  assert.equal(classifyConnectorOutcome({
    ...TRACE,
    result: { status: "completed_no_effect", safe_reason: "existing_bundles_reused" },
  }).external_registration_status, "unknown");
});

test("a completed no-effect result without an attempt marker stays externally unknown", () => {
  assert.equal(classifyConnectorOutcome({
    ...TRACE,
    result: { status: "completed_no_effect", safe_reason: "providers_exhausted" },
  }).external_registration_status, "unknown");
});

test("a no-effect result with a prior registration attempt stays externally unknown", () => {
  assert.equal(classifyConnectorOutcome({
    ...TRACE,
    result: { status: "completed_no_effect", safe_reason: "providers_exhausted", registration_attempted: true },
  }).external_registration_status, "unknown");
});

test("a no-effect result with any journey receipt never claims not-attempted", () => {
  assert.equal(classifyConnectorOutcome({
    ...TRACE,
    result: {
      status: "completed_no_effect",
      safe_reason: "providers_exhausted",
      registration_attempted: false,
      journey: { registration: { provider_receipt_ref: "provider-receipt://luma/receipt" } },
    },
}).external_registration_status, "unknown");
});

test("a completed no-effect result with all occurrence-bound receipts is still externally unknown", () => {
  assert.equal(classifyConnectorOutcome({
    ...TRACE,
    result: {
      status: "completed_no_effect",
      safe_reason: "providers_exhausted",
      registration_attempted: false,
      journey: {
        registration: { occurrence_id: TRACE.occurrence_id, provider_receipt_ref: "provider-receipt://luma/receipt" },
        confirmation_mail: { occurrence_id: TRACE.occurrence_id, external_receipt_ref: "gmail-message://dais-local/mail" },
        calendar: { occurrence_id: TRACE.occurrence_id, calendar_event_ref: "calendar-evidence://google/event/event-1" },
      },
    },
  }).external_registration_status, "unknown");
});

test("an invalid registration attempt marker fails closed", () => {
  assert.throws(() => classifyConnectorOutcome({
    ...TRACE,
    result: { status: "completed_no_effect", safe_reason: "providers_exhausted", registration_attempted: "false" },
  }), /invalid/i);
});

test("a wake that defers fallback is not mislabeled as an unattempted external registration", () => {
  assert.equal(classifyConnectorOutcome({
    ...TRACE,
    result: { status: "completed_no_effect", safe_reason: "fallback_deferred_for_wake_budget" },
  }).external_registration_status, "unknown");
});

test("an applied bundle is external-verified only with all provider, mail, and Calendar refs", () => {
  assert.equal(classifyConnectorOutcome({
    ...TRACE,
    result: {
      status: "applied_bundle",
      safe_reason: "applied_bundle",
      journey: {
        registration: { occurrence_id: TRACE.occurrence_id, provider_receipt_ref: "provider-receipt://luma/receipt" },
        confirmation_mail: { occurrence_id: TRACE.occurrence_id, external_receipt_ref: "gmail-message://dais-local/mail" },
        calendar: { occurrence_id: TRACE.occurrence_id, calendar_event_ref: "calendar-evidence://google/event/event-1" },
      },
    },
  }).external_registration_status, "verified");
});

test("the common write pipeline's complete result is also process-pass when all refs are present", () => {
  const outcome = classifyConnectorOutcome({
    ...TRACE,
    result: {
      status: "complete",
      outcome: "verified_delivery",
      journey: {
        registration: { occurrence_id: TRACE.occurrence_id, provider_receipt_ref: "provider-receipt://luma/receipt" },
        confirmation_mail: { occurrence_id: TRACE.occurrence_id, external_receipt_ref: "gmail-message://dais-local/mail" },
        calendar: { occurrence_id: TRACE.occurrence_id, calendar_event_ref: "calendar-evidence://google/event/event-1" },
      },
    },
  });
  assert.equal(outcome.process_status, "pass");
  assert.equal(outcome.external_registration_status, "verified");
});

test("a failed process never claims an external registration", () => {
  assert.equal(classifyConnectorOutcome({
    ...TRACE,
    result: { status: "circuit_open", safe_reason: "browser_open_failed" },
  }).external_registration_status, "unknown");
});

test("an applied bundle with any mismatched journey occurrence stays externally unknown", () => {
  for (const stage of ["registration", "confirmation_mail", "calendar"]) {
    const journey = {
      registration: { occurrence_id: TRACE.occurrence_id, provider_receipt_ref: "provider-receipt://luma/receipt" },
      confirmation_mail: { occurrence_id: TRACE.occurrence_id, external_receipt_ref: "gmail-message://dais-local/mail" },
      calendar: { occurrence_id: TRACE.occurrence_id, calendar_event_ref: "calendar-evidence://google/event/event-1" },
    };
    journey[stage].occurrence_id = `${TRACE.occurrence_id}:other`;
    assert.equal(classifyConnectorOutcome({
      ...TRACE,
      result: { status: "applied_bundle", safe_reason: "applied_bundle", journey },
    }).external_registration_status, "unknown", stage);
  }
});
