"use strict";
const { createHash } = require("node:crypto");
const { isDeepStrictEqual } = require("node:util");
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
class CycleError extends Error {
  constructor(code, unknownEffect = true) { super(code); this.code = code.toUpperCase(); this.unknownEffect = unknownEffect; }
}
const EXECUTION_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
function cycleContract(job) {
  try {
    const normalized = buildRuntimeJob(job);
    const prefix = `maritime-cycle://${normalized.tenant_id}/`;
    if (!normalized.input_refs.cycle_ref?.startsWith(prefix)) throw new Error();
    const identity = Object.freeze({ tenantId: normalized.tenant_id,
      occurrenceId: decodeURIComponent(normalized.input_refs.cycle_ref.slice(prefix.length)),
      dateKey: normalized.input_refs.date_ref?.slice('date://'.length),
      releaseSha: normalized.input_refs.release_ref?.slice('release://git/'.length) });
    if (!isDeepStrictEqual(normalized, buildMaritimeManagerCycleJob(identity))) throw new Error();
    return identity;
  } catch { throw new CycleError('maritime_cycle_job_invalid', false); }
}
function artifactRefsValid(refs, completed) {
  return Array.isArray(refs) && (completed ? refs.length > 0 : refs.length === 0)
    && refs.every(ref => typeof ref === 'string' && ref.startsWith('artifact://') && !ref.includes('\0')
      && ref.slice('artifact://'.length).split('/').every(part => part && part !== '.' && part !== '..'));
}
function verifyCycleReceipt(receipt, job) {
  try {
    const c = cycleContract(job);
    return Boolean(receipt?.schema_version === 1 && receipt.kind === 'maritime_manager_cycle'
      && receipt.tenant_id === c.tenantId && receipt.job_id === job.job_id
      && receipt.occurrence_id === c.occurrenceId && receipt.date_key === c.dateKey
      && receipt.release_sha === c.releaseSha && typeof receipt.agent_id === 'string' && EXECUTION_ID.test(receipt.agent_id)
      && typeof receipt.execution_id === 'string' && EXECUTION_ID.test(receipt.execution_id)
      && receipt.provider === 'maritime'
      && receipt.external_ref === `maritime-execution://${receipt.agent_id}/${receipt.execution_id}`
      && isDeepStrictEqual(receipt.evidence_refs, [receipt.external_ref])
      && ['completed', 'deferred'].includes(receipt.status)
      && artifactRefsValid(receipt.artifact_refs, receipt.status === 'completed')
      && (receipt.status === 'completed' ? receipt.error_class === null
        : ['no_work', 'cloud_model_config_missing'].includes(receipt.error_class)));
  } catch { return false; }
}
function createMaritimeManagerLoopAdapter(services = {}) {
  const store = services.managerStore;
  function configured() {
    if (!store || ['read', 'readCycleDispatch', 'claimCycleDispatch', 'bindCycleExecution'].some(key => typeof store[key] !== 'function')
      || ['dispatchCycle', 'readExecution', 'readCycleReceipt'].some(key => typeof services[key] !== 'function')
) {
      throw new CycleError('maritime_cycle_unconfigured', false);
    }
  }
  async function binding(c) {
    const enrollment = await store.read(c.tenantId);
    if (!enrollment || enrollment.uid !== c.tenantId || typeof enrollment.agent_id !== 'string'
      || !EXECUTION_ID.test(enrollment.agent_id)) throw new CycleError('maritime_cycle_binding_unknown');
    return { enrollment, identity: Object.freeze({ uid: c.tenantId, agentId: enrollment.agent_id,
      occurrenceId: c.occurrenceId, dateKey: c.dateKey, releaseSha: c.releaseSha }) };
  }
  function checkpoint(row, identity) {
    if (!row || row.uid !== identity.uid || row.agent_id !== identity.agentId
      || row.occurrence_id !== identity.occurrenceId || row.date_key !== identity.dateKey
      || row.release_sha !== identity.releaseSha || (row.execution_id !== null
        && (typeof row.execution_id !== 'string' || !EXECUTION_ID.test(row.execution_id)))) {
      throw new CycleError('maritime_cycle_checkpoint_invalid');
    }
    return row.execution_id;
  }
  function active(enrollment, c) {
    if (enrollment.status === 'paused' || enrollment.paused_at) throw new CycleError('maritime_cycle_paused', false);
    if (enrollment.status !== 'active' || enrollment.release_sha !== c.releaseSha) throw new CycleError('maritime_cycle_inactive', false);
  }
  async function inspect(job, c, identity, executionId) {
    const execution = await services.readExecution({ agentId: identity.agentId, executionId });
    if (['running', 'pending', 'queued'].includes(execution?.status)) return { state: 'pending' };
    if (execution?.status !== 'completed' || execution.exitCode !== 0) throw new CycleError('maritime_cycle_result_unknown');
    const envelope = await services.readCycleReceipt({ uid: c.tenantId, agentId: identity.agentId, occurrenceId: c.occurrenceId });
    const r = envelope?.result;
    let capturedResult;
    try {
      if (typeof execution.stdout !== 'string') throw new Error();
      capturedResult = JSON.parse(execution.stdout);
    } catch { throw new CycleError('maritime_cycle_receipt_invalid'); }
    if (!envelope || envelope.dateKey !== c.dateKey || envelope.releaseSha !== c.releaseSha
      || !r || !isDeepStrictEqual(capturedResult, r) || r.tenantId !== c.tenantId || r.occurrenceId !== c.occurrenceId
      || r.providerSnapshotRef !== null || !Array.isArray(r.providerReceiptRefs) || r.providerReceiptRefs.length !== 0
      || r.nextEligibleAt !== null) throw new CycleError('maritime_cycle_receipt_invalid');
    const receipt = { schema_version: 1, kind: 'maritime_manager_cycle', tenant_id: c.tenantId, job_id: job.job_id,
      agent_id: identity.agentId, execution_id: executionId, occurrence_id: c.occurrenceId, date_key: c.dateKey,
      release_sha: c.releaseSha, status: r.status, artifact_refs: r.artifactRefs, error_class: r.errorClass,
      provider: 'maritime', external_ref: `maritime-execution://${identity.agentId}/${executionId}`,
      evidence_refs: [`maritime-execution://${identity.agentId}/${executionId}`] };
    if (!verifyCycleReceipt(receipt, job)) throw new CycleError('maritime_cycle_receipt_invalid');
    return { state: 'present', receipt };
  }
  return Object.freeze({
    plan: async input => [buildMaritimeManagerCycleJob(input)],
    async execute(job) {
      const c = cycleContract(job); configured();
      try {
        const bound = await binding(c);
        let row = await store.readCycleDispatch(bound.identity);
        let executionId;
        if (row) {
          executionId = checkpoint(row, bound.identity);
          if (!executionId) throw new CycleError('maritime_cycle_dispatch_unconfirmed');
        } else {
          active(bound.enrollment, c);
          const claim = await store.claimCycleDispatch(bound.identity);
          if (typeof claim?.claimed !== 'boolean') throw new CycleError('maritime_cycle_checkpoint_invalid');
          executionId = checkpoint(claim.row, bound.identity);
          if (!executionId) {
            if (!claim.claimed) throw new CycleError('maritime_cycle_dispatch_unconfirmed');
            const current = await binding(c);
            if (!isDeepStrictEqual(current.identity, bound.identity)) throw new CycleError('maritime_cycle_binding_unknown');
            active(current.enrollment, c);
            const dispatched = await services.dispatchCycle({ uid: c.tenantId, agentId: bound.identity.agentId,
              occurrenceId: c.occurrenceId, dateKey: c.dateKey, releaseSha: c.releaseSha });
            executionId = dispatched?.executionId;
            if (typeof executionId !== 'string' || !EXECUTION_ID.test(executionId)) throw new CycleError('maritime_cycle_dispatch_unconfirmed');
            row = await store.bindCycleExecution({ ...bound.identity, executionId });
            if (checkpoint(row, bound.identity) !== executionId) throw new CycleError('maritime_cycle_checkpoint_invalid');
          }
        }
        const proof = await inspect(job, c, bound.identity, executionId);
        if (proof.state === 'present') return { receipt: proof.receipt };
        throw new CycleError('maritime_cycle_pending');
      } catch (error) {
        if (error instanceof CycleError) throw error;
        throw new CycleError('maritime_cycle_effect_unknown');
      }
    },
    async reconcile(job) {
      const c = cycleContract(job); configured();
      try {
        const { identity } = await binding(c);
        const row = await store.readCycleDispatch(identity);
        const executionId = row && checkpoint(row, identity);
        if (!executionId) return { state: 'unknown', errorClass: 'maritime_cycle_dispatch_unconfirmed',
          nextAction: 'inspect_provider_execution', retryable: false };
        return await inspect(job, c, identity, executionId);
      } catch (error) { return { state: 'unknown',
        errorClass: error instanceof CycleError ? error.message : 'maritime_cycle_readback_unavailable',
        nextAction: 'inspect_provider_execution', retryable: false }; }
    },
    verify: verifyCycleReceipt,
    report(receipt) {
      try {
        const job = buildMaritimeManagerCycleJob({ tenantId: receipt.tenant_id, occurrenceId: receipt.occurrence_id,
          dateKey: receipt.date_key, releaseSha: receipt.release_sha });
        if (!verifyCycleReceipt(receipt, job)) throw new Error();
        return { status: receipt.status, artifact_count: receipt.artifact_refs.length, error_class: receipt.error_class };
      } catch { throw new CycleError('maritime_cycle_receipt_invalid', false); }
    },
  });
}
module.exports = { buildMaritimeManagerProvisionJob, buildMaritimeManagerCycleJob, buildMaritimeManagerReportJob, createMaritimeManagerLoopAdapter, readMaritimeCycleContract: cycleContract, maritimeArtifactRefsValid: artifactRefsValid };
