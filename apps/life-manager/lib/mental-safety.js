"use strict";

// This boundary consumes a verdict from an explicitly authorized safety owner. It never classifies
// Gmail, Calendar, silence, rejection, or ordinary conversation itself, and it never claims to
// provide monitoring, dispatch, treatment, or suicide prevention.
const SAFETY_VERDICTS = Object.freeze(["none", "unknown", "imminent_self_harm"]);

function evaluateMentalSafety({ verdict } = {}) {
  if (verdict === "imminent_self_harm") {
    return { decision: "safety_route_required", reason: "explicit-imminent-self-harm" };
  }
  return { decision: "continue" };
}

module.exports = { SAFETY_VERDICTS, evaluateMentalSafety };
