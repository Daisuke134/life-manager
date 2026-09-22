"use strict";

const { buildGoalWorkItem } = require("./goal-work-item.js");

const ADAPTER_ID = "general-agent-work";
const CAPABILITY = "general-agent.work";
const LOOP_ID = "life-manager.manager";
const RECEIPT_KEYS = [
  "execution_id", "goal_ref", "job_id", "kind", "next_job_refs", "status", "tenant_id",
];
const STATUSES = new Set(["planned", "completed", "blocked"]);
const IDENTIFIER = /^[a-z0-9][a-z0-9._:-]{0,199}$/i;

function contract(job) {
  const refs = job && job.input_refs;
  if (
    !job || job.loop_id !== LOOP_ID || job.capability !== CAPABILITY
    || job.effect_class !== "none" || job.effect_key !== null || job.max_attempts !== 1
    || typeof job.tenant_id !== "string" || !job.tenant_id
    || typeof job.job_id !== "string"
    || !refs || JSON.stringify(Object.keys(refs)) !== JSON.stringify(["goal_ref"])
  ) throw new Error("general agent WorkItem invalid");
  const identity = /^goal:([a-z0-9][a-z0-9._-]{0,199}):r([1-9][0-9]*)$/iu.exec(job.job_id);
  let parsed;
  try { parsed = new URL(refs.goal_ref); } catch { throw new Error("general agent WorkItem invalid"); }
  if (!identity
    || parsed.protocol !== "goal-portfolio:"
    || parsed.username || parsed.password || parsed.port || parsed.hash
    || parsed.hostname !== job.tenant_id
    || decodeURIComponent(parsed.pathname) !== `/${identity[1]}`
    || parsed.searchParams.size !== 1
    || parsed.searchParams.get("revision") !== identity[2]
    || refs.goal_ref !== `goal-portfolio://${encodeURIComponent(job.tenant_id)}/${encodeURIComponent(identity[1])}?revision=${identity[2]}`
  ) throw new Error("general agent WorkItem invalid");
  return Object.freeze({
    tenant_id: job.tenant_id,
    job_id: job.job_id,
    goal_ref: refs.goal_ref,
  });
}

function receipt(value, expected) {
  if (
    !value || typeof value !== "object" || Array.isArray(value)
    || JSON.stringify(Object.keys(value).sort()) !== JSON.stringify(RECEIPT_KEYS)
    || value.kind !== "general_agent_work" || !STATUSES.has(value.status)
    || !IDENTIFIER.test(String(value.execution_id || ""))
    || !Array.isArray(value.next_job_refs) || value.next_job_refs.length > 100
  ) throw new Error("general agent work receipt invalid");
  if (expected && (
    value.tenant_id !== expected.tenant_id || value.job_id !== expected.job_id
    || value.goal_ref !== expected.goal_ref
  )) throw new Error("general agent work receipt invalid");
  const prefix = `runtime-job://${encodeURIComponent(value.tenant_id)}/`;
  if (value.next_job_refs.some((ref) => (
    typeof ref !== "string" || !ref.startsWith(prefix)
    || ref.length <= prefix.length || ref.length > 1024 || /\s/.test(ref)
  ))) throw new Error("general agent work receipt invalid");
  return value;
}

function createGeneralAgentWorkLoopAdapter(deps = {}) {
  return Object.freeze({
    async plan(context = {}) {
      return [buildGoalWorkItem(context.portfolioGoal, context.nowMs)];
    },
    async execute(job, services = {}) {
      const expected = contract(job);
      const specialist = services.runBoundedSpecialist || deps.runBoundedSpecialist;
      if (typeof specialist !== "function") throw new Error("bounded specialist unavailable");
      return { receipt: receipt(await specialist(expected), expected) };
    },
    async reconcile() {
      return { state: "unknown" };
    },
    verify(value, job) {
      try { return receipt(value, contract(job)) === value; } catch { return false; }
    },
    report(value) {
      const verified = receipt(value);
      return Object.freeze({
        status: verified.status,
        execution_id: verified.execution_id,
        next_job_count: verified.next_job_refs.length,
      });
    },
  });
}

module.exports = {
  ADAPTER_ID,
  CAPABILITY,
  LOOP_ID,
  createGeneralAgentWorkLoopAdapter,
};
