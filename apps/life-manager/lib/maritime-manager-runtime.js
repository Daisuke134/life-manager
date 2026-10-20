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
module.exports = { buildMaritimeManagerProvisionJob };
