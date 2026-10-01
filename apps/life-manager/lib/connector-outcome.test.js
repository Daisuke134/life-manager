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
    result: { status: "completed_no_effect", safe_reason: "providers_exhausted" },
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

test("an applied bundle is external-verified only with all provider, mail, and Calendar refs", () => {
  assert.equal(classifyConnectorOutcome({
    ...TRACE,
    result: {
      status: "applied_bundle",
      safe_reason: "applied_bundle",
      journey: {
        registration: { provider_receipt_ref: "provider-receipt://luma/receipt" },
        confirmation_mail: { external_receipt_ref: "gmail-message://dais-local/mail" },
        calendar: { calendar_event_ref: "calendar-evidence://google/event/event-1" },
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
        registration: { provider_receipt_ref: "provider-receipt://luma/receipt" },
        confirmation_mail: { external_receipt_ref: "gmail-message://dais-local/mail" },
        calendar: { calendar_event_ref: "calendar-evidence://google/event/event-1" },
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
