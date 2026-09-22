"use strict";

const { goalReference, validatePortfolioGoalShape } = require("./goal-portfolio.js");
const { buildRuntimeJob } = require("./runtime-job-store.js");

const LOOP_ID = "life-manager.manager";
const CAPABILITY = "general-agent.work";
const GOAL_JOB_ID = /^goal:([a-z0-9][a-z0-9._-]{0,199}):r([1-9][0-9]*)$/iu;

function invalidWorkItem() {
  throw new Error("general agent WorkItem invalid");
}

function validateGoalWorkItem(job) {
  const refs = job && job.input_refs;
  if (!job || job.loop_id !== LOOP_ID || job.capability !== CAPABILITY
    || job.effect_class !== "none" || job.effect_key !== null || job.max_attempts !== 1
    || typeof job.tenant_id !== "string" || !job.tenant_id
    || typeof job.job_id !== "string"
    || !refs || typeof refs !== "object" || Array.isArray(refs)
    || JSON.stringify(Object.keys(refs)) !== JSON.stringify(["goal_ref"])) invalidWorkItem();
  const identity = GOAL_JOB_ID.exec(job.job_id);
  let parsed;
  let pathname;
  try {
    parsed = new URL(refs.goal_ref);
    pathname = decodeURIComponent(parsed.pathname);
  } catch { return invalidWorkItem(); }
  if (!identity || parsed.protocol !== "goal-portfolio:"
    || parsed.username || parsed.password || parsed.port || parsed.hash
    || parsed.hostname !== job.tenant_id || pathname !== `/${identity[1]}`
    || parsed.searchParams.size !== 1 || parsed.searchParams.get("revision") !== identity[2]
    || refs.goal_ref !== `goal-portfolio://${encodeURIComponent(job.tenant_id)}/${encodeURIComponent(identity[1])}?revision=${identity[2]}`) {
    invalidWorkItem();
  }
  return Object.freeze({
    tenant_id: job.tenant_id,
    job_id: job.job_id,
    goal_ref: refs.goal_ref,
  });
}

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

module.exports = { LOOP_ID, CAPABILITY, buildGoalWorkItem, validateGoalWorkItem };
