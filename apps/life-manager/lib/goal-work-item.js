"use strict";

const { goalReference, validatePortfolioGoalShape } = require("./goal-portfolio.js");
const { buildRuntimeJob } = require("./runtime-job-store.js");

const LOOP_ID = "life-manager.manager";
const CAPABILITY = "general-agent.work";

function buildGoalWorkItem(goal, nowMs) {
  if (!Number.isFinite(nowMs)) throw new Error("WorkItem observation time is required");
  validatePortfolioGoalShape(goal);
  const reference = goalReference(goal);
  if (
    goal.status !== "active"
    || (goal.expires_at !== null && (
      typeof goal.expires_at !== "string"
      || !Number.isFinite(Date.parse(goal.expires_at))
      || Date.parse(goal.expires_at) <= nowMs
    ))
  ) {
    throw new Error("WorkItem requires one active portfolio goal");
  }
  return buildRuntimeJob({
    jobId: `goal:${goal.goal_id}:r${goal.revision}`,
    tenantId: goal.tenant_id,
    loopId: LOOP_ID,
    capability: CAPABILITY,
    effectClass: "none",
    effectKey: null,
    inputRefs: {
      goal_ref: reference,
    },
    maxAttempts: 1,
  });
}

module.exports = { LOOP_ID, CAPABILITY, buildGoalWorkItem };
