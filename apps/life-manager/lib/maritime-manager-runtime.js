"use strict";
const { createHash } = require("node:crypto");
const { buildRuntimeJob } = require("./runtime-job-store.js");
function buildMaritimeManagerProvisionJob({ tenantId, releaseSha }) {
  if (!/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(tenantId)
    || !/^[0-9a-f]{40}$/.test(releaseSha)) throw new Error("maritime_provision_job_invalid");
  const digest = createHash("sha256").update(`maritime-manager-provision:v1:${tenantId}`).digest("hex");
  return buildRuntimeJob({ jobId: `maritime-provision:${digest}`, tenantId,
    loopId: "maritime.manager", capability: "maritime.manager.provision", effectClass: "money",
    effectKey: `maritime-provision://${digest}`, maxAttempts: 1,
    inputRefs: { enrollment_ref: `maritime-enrollment://${tenantId}`, release_ref: `release://git/${releaseSha}` } });
}
function managerDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}
function managerJob(kind, { tenantId, releaseSha }, key, effectClass, extraRefs) {
  if (typeof tenantId !== "string" || !/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(tenantId)
    || typeof releaseSha !== "string" || !/^[0-9a-f]{40}$/.test(releaseSha)) throw new Error("maritime_manager_job_invalid");
  const digest = createHash("sha256").update(`maritime-manager-${kind}:v1:${tenantId}:${key}`).digest("hex");
  return buildRuntimeJob({ jobId: `maritime-${kind}:${digest}`, tenantId,
    loopId: `maritime.manager.${kind}`, capability: `maritime.manager.${kind}`, effectClass,
    effectKey: `maritime-${kind}://${tenantId}/${encodeURIComponent(key)}`, maxAttempts: 1,
    inputRefs: { enrollment_ref: `maritime-enrollment://${tenantId}`,
      release_ref: `release://git/${releaseSha}`, ...extraRefs } });
}
function buildMaritimeManagerCycleJob(input) {
  const { occurrenceId, dateKey } = input || {};
  if (typeof occurrenceId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(occurrenceId)
    || !managerDate(dateKey)) throw new Error("maritime_manager_job_invalid");
  return managerJob("cycle", input, occurrenceId, "money", {
    cycle_ref: `maritime-cycle://${input.tenantId}/${encodeURIComponent(occurrenceId)}`, date_ref: `date://${dateKey}`,
  });
}
function buildMaritimeManagerReportJob(input) {
  const { periodKey } = input || {};
  if (typeof periodKey !== "string" || !periodKey.startsWith("maritime:daily:")
    || !managerDate(periodKey.slice("maritime:daily:".length))) throw new Error("maritime_manager_job_invalid");
  return managerJob("report", input, periodKey, "message", {
    period_ref: `maritime-period://${encodeURIComponent(periodKey)}`,
  });
}
module.exports = { buildMaritimeManagerProvisionJob, buildMaritimeManagerCycleJob, buildMaritimeManagerReportJob };
