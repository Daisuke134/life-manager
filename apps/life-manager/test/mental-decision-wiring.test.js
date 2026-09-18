"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const scheduler = require("../scheduler.js");

const USER = { uid: "u1", call_time_zone: "Asia/Tokyo" };

test("decision-log requirement is explicit and defaults off during migration rollout", () => {
  const old = process.env.LM_MENTAL_DECISION_LOG_REQUIRED;
  try {
    delete process.env.LM_MENTAL_DECISION_LOG_REQUIRED;
    assert.equal(scheduler.mentalV1Deps(USER, [], {}).recordDecision, undefined);
    process.env.LM_MENTAL_DECISION_LOG_REQUIRED = "1";
    assert.equal(typeof scheduler.mentalV1Deps(USER, [], {}).recordDecision, "function");
  } finally {
    if (old === undefined) delete process.env.LM_MENTAL_DECISION_LOG_REQUIRED;
    else process.env.LM_MENTAL_DECISION_LOG_REQUIRED = old;
  }
});

