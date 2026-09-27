"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { activeSuppressedEventRefs } = require("./connector-candidate-suppression.js");

test("latest terminal known failures stay suppressed until retry_after", () => {
  const suppressed = activeSuppressedEventRefs({
    now: "2026-08-06T01:00:00.000Z",
    attempts: [{
      event_ref: "luma-event://event/terminal",
      outcome: "known_no_effect",
      safe_reason: "LUMA_RSVP_UNAVAILABLE",
      observed_at: "2026-08-06T00:00:00.000Z",
      retry_after: null,
    }, {
      event_ref: "luma-event://event/future-retry",
      outcome: "known_no_effect",
      safe_reason: "LUMA_FORM_INPUT_REQUIRED",
      observed_at: "2026-08-06T00:00:01.000Z",
      retry_after: "2026-08-06T02:00:00.000Z",
    }, {
      event_ref: "luma-event://event/retry-ready",
      outcome: "known_no_effect",
      safe_reason: "LUMA_RSVP_UNAVAILABLE",
      observed_at: "2026-08-06T00:00:02.000Z",
      retry_after: "2026-08-06T00:30:00.000Z",
    }],
  });

  assert.deepEqual([...suppressed].sort(), [
    "luma-event://event/future-retry",
    "luma-event://event/terminal",
  ]);
});

test("a later non-terminal observation supersedes an older known failure", () => {
  const suppressed = activeSuppressedEventRefs({
    now: "2026-08-06T01:00:00.000Z",
    attempts: [{
      event_ref: "luma-event://event/changed",
      outcome: "known_no_effect",
      safe_reason: "LUMA_RSVP_UNAVAILABLE",
      observed_at: "2026-08-06T00:00:00.000Z",
      retry_after: null,
    }, {
      event_ref: "luma-event://event/changed",
      outcome: "recovery_required",
      safe_reason: "calendar_sync_failed",
      observed_at: "2026-08-06T00:10:00.000Z",
      retry_after: null,
    }],
  });

  assert.deepEqual([...suppressed], []);
});

test("a connpass known failure is suppressed exactly like a luma one", () => {
  const suppressed = activeSuppressedEventRefs({
    now: "2026-09-28T01:00:00.000Z",
    attempts: [{
      event_ref: "connpass-event://event/408094",
      outcome: "known_no_effect",
      safe_reason: "CONNPASS_TIER_UNAVAILABLE",
      observed_at: "2026-09-27T23:23:46.000Z",
      retry_after: null,
    }],
  });

  assert.deepEqual([...suppressed], ["connpass-event://event/408094"]);
});

test("a form capability upgrade re-evaluates an old form failure exactly once", () => {
  const legacy = {
    event_ref: "luma-event://event/form-upgrade",
    outcome: "known_no_effect",
    safe_reason: "LUMA_FORM_INPUT_REQUIRED",
    observed_at: "2026-08-06T00:00:00.000Z",
    retry_after: null,
    capability_version: null,
  };
  assert.deepEqual([...activeSuppressedEventRefs({
    now: "2026-08-06T01:00:00.000Z",
    capabilityVersion: "luma-form-submit-v1",
    attempts: [legacy],
  })], []);

  const retried = {
    ...legacy,
    observed_at: "2026-08-06T01:00:00.000Z",
    capability_version: "luma-form-submit-v1",
  };
  assert.deepEqual([...activeSuppressedEventRefs({
    now: "2026-08-06T01:01:00.000Z",
    capabilityVersion: "luma-form-submit-v1",
    attempts: [legacy, retried],
  })], [legacy.event_ref]);
  assert.deepEqual([...activeSuppressedEventRefs({
    now: "2026-08-06T01:02:00.000Z",
    capabilityVersion: "luma-form-submit-v2",
    attempts: [legacy, retried],
  })], []);
});
