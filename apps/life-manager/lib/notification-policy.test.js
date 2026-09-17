"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { decideNotification } = require("./notification-policy.js");

test("routine runtime events remain internal-only", () => {
  for (const kind of ["wake_completed", "retry_scheduled", "health_check", "evaluation_finished"]) {
    assert.deepEqual(decideNotification({ event_kind: kind }), {
      event_kind: kind,
      visibility: "internal_only",
      reason: "routine",
    });
  }
});

test("only the four user-facing event kinds enter the notification boundary", () => {
  for (const kind of [
    "human_action_required",
    "urgent_safety",
    "material_outcome",
    "persistent_blocker",
  ]) {
    assert.deepEqual(decideNotification({ event_kind: kind }), {
      event_kind: kind,
      visibility: "user_visible",
      reason: kind,
    });
  }
});

test("unknown event kinds fail closed to internal-only", () => {
  assert.deepEqual(decideNotification({ event_kind: "new_future_event" }), {
    event_kind: "new_future_event",
    visibility: "internal_only",
    reason: "unknown_event_kind",
  });
  assert.deepEqual(decideNotification({}), {
    event_kind: "unknown",
    visibility: "internal_only",
    reason: "unknown_event_kind",
  });
});
