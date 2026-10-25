"use strict";
const { createHash } = require("node:crypto");
const { isDeepStrictEqual } = require("node:util");
const { buildRuntimeJob } = require("./runtime-job-store.js");
const { MANAGER_CONSENT_VERSION } = require("./maritime-distribution.js");
function buildMaritimeManagerProvisionJob({ tenantId, releaseSha, phase = "create", resumeAt = null }) {
  if (!/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(tenantId)
    || !/^[0-9a-f]{40}$/.test(releaseSha) || !["create", "configure", "pause"].includes(phase)
    || (resumeAt !== null && (typeof resumeAt !== "string" || !Number.isFinite(Date.parse(resumeAt))
      || new Date(resumeAt).toISOString() !== resumeAt))) throw new Error("maritime_provision_job_invalid");
  const namespace = resumeAt === null ? `v1:${tenantId}` : `v2:${tenantId}:${resumeAt}`;
  const digest = createHash("sha256").update(`maritime-manager-provision:${namespace}${phase === "create" ? "" : ":" + phase}`).digest("hex");
  return buildRuntimeJob({ jobId: `maritime-provision:${digest}`, tenantId,
    loopId: "maritime.manager", capability: "maritime.manager.provision", effectClass: "money",
    effectKey: `maritime-provision://${digest}`, maxAttempts: 1,
    inputRefs: { enrollment_ref: `maritime-enrollment://${tenantId}`, release_ref: `release://git/${releaseSha}`,
      ...(phase !== "create" ? { provision_phase_ref: `maritime-provision-phase://${phase}` } : {}),
      ...(resumeAt !== null ? { provision_resume_ref: `maritime-provision-resume://${encodeURIComponent(resumeAt)}` } : {}) } });
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
function managerConsentCurrent(enrollment) {
  return enrollment?.consent_version === MANAGER_CONSENT_VERSION;
}
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
function deferredCyclePreflight(c, job, agentId, services, preparationErrorClass) {
  const observedAt = (services.now || (() => new Date().toISOString()))();
  if (!Number.isFinite(Date.parse(observedAt))) throw new CycleError('maritime_cycle_clock_invalid', false);
  const externalRef = `runtime-preflight://${job.job_id.slice('maritime-cycle:'.length)}`;
  return { schema_version: 1, kind: 'maritime_manager_cycle_preflight', tenant_id: c.tenantId,
    job_id: job.job_id, occurrence_id: c.occurrenceId, date_key: c.dateKey, release_sha: c.releaseSha,
    agent_id: agentId, execution_id: null, status: 'deferred', artifact_refs: [], error_class: 'cloud_runtime_not_ready',
    phase: 'prepare', preparation_error_class: preparationErrorClass, retryable: true, next_action: 'retry_guest_readiness',
    provider: 'runtime', external_ref: externalRef, evidence_refs: [externalRef],
    observed_at: new Date(observedAt).toISOString(), next_eligible_at: new Date(Date.parse(observedAt) + 15 * 60 * 1000).toISOString() };
}
function verifyCycleReceipt(receipt, job) {
  try {
    const c = cycleContract(job);
    if (receipt?.kind === 'maritime_manager_cycle_preflight') {
      const observedMs = Date.parse(receipt.observed_at);
      return Boolean(receipt.schema_version === 1 && receipt.tenant_id === c.tenantId && receipt.job_id === job.job_id
        && receipt.occurrence_id === c.occurrenceId && receipt.date_key === c.dateKey && receipt.release_sha === c.releaseSha
        && typeof receipt.agent_id === 'string' && EXECUTION_ID.test(receipt.agent_id) && receipt.execution_id === null
        && receipt.status === 'deferred' && artifactRefsValid(receipt.artifact_refs, false)
        && receipt.error_class === 'cloud_runtime_not_ready' && receipt.provider === 'runtime'
        && receipt.phase === 'prepare' && /^MARITIME_[A-Z_]{1,160}$/.test(receipt.preparation_error_class || '')
        && receipt.retryable === true && receipt.next_action === 'retry_guest_readiness'
        && receipt.external_ref === `runtime-preflight://${job.job_id.slice('maritime-cycle:'.length)}`
        && isDeepStrictEqual(receipt.evidence_refs, [receipt.external_ref]) && Number.isFinite(observedMs)
        && new Date(observedMs).toISOString() === receipt.observed_at
        && receipt.next_eligible_at === new Date(observedMs + 15 * 60 * 1000).toISOString());
    }
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
  function controlLock(tenantId, operation) {
    const lock = services.withControlLock || ((uid, callback) => require('./runtime-job-store.js')
      .withRuntimeTenantControlLock({ tenantId: uid }, callback, services.storeOptions || {}));
    return lock(tenantId, operation);
  }
  function configured(requirePrepare = false) {
    if (!store || ['read', 'readCycleDispatch', 'claimCycleDispatch', 'bindCycleExecution'].some(key => typeof store[key] !== 'function')
      || ['dispatchCycle', 'readExecution', 'readCycleReceipt'].some(key => typeof services[key] !== 'function')
      || (requirePrepare && typeof services.prepareCycle !== 'function')
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
    if (!managerConsentCurrent(enrollment)) throw new CycleError('maritime_cycle_consent_required', false);
    if (enrollment.status !== 'active' || enrollment.release_sha !== c.releaseSha) throw new CycleError('maritime_cycle_inactive', false);
  }
  async function inspect(job, c, identity, executionId) {
    const execution = await services.readExecution({ uid: c.tenantId, agentId: identity.agentId, executionId });
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
      const c = cycleContract(job); configured(true);
      try {
        const bound = await binding(c);
        let row = await store.readCycleDispatch(bound.identity);
        let executionId;
        if (row) {
          executionId = checkpoint(row, bound.identity);
          if (!executionId) {
            executionId = await controlLock(c.tenantId, async () => {
              const latest = await store.readCycleDispatch(bound.identity);
              const persisted = checkpoint(latest, bound.identity);
              if (!persisted) throw new CycleError('maritime_cycle_dispatch_unconfirmed');
              return persisted;
            });
          }
        } else {
          active(bound.enrollment, c);
          let ready, preparationErrorClass = 'MARITIME_GUEST_NOT_READY';
          try { ready = await services.prepareCycle({ uid: c.tenantId, agentId: bound.identity.agentId, releaseSha: c.releaseSha }); }
          catch (error) {
            ready = null;
            preparationErrorClass = /^MARITIME_[A-Z_]{1,160}$/.test(error?.code || '') ? error.code : 'MARITIME_PREPARE_UNAVAILABLE';
          }
          if (ready?.ready !== true) return { receipt: deferredCyclePreflight(c, job, bound.identity.agentId, services, preparationErrorClass) };
          const current = await binding(c); active(current.enrollment, c);
          if (!isDeepStrictEqual(current.identity, bound.identity)) throw new CycleError('maritime_cycle_binding_unknown', false);
          executionId = await controlLock(c.tenantId, async () => {
            const locked = await binding(c); active(locked.enrollment, c);
            if (!isDeepStrictEqual(locked.identity, bound.identity)) throw new CycleError('maritime_cycle_binding_unknown', false);
            const prior = await store.readCycleDispatch(bound.identity);
            if (prior) {
              const persisted = checkpoint(prior, bound.identity);
              if (!persisted) throw new CycleError('maritime_cycle_dispatch_unconfirmed');
              return persisted;
            }
            const claim = await store.claimCycleDispatch(bound.identity);
            if (typeof claim?.claimed !== 'boolean') throw new CycleError('maritime_cycle_checkpoint_invalid');
            const claimedExecution = checkpoint(claim.row, bound.identity);
            if (claimedExecution) return claimedExecution;
            if (!claim.claimed) {
              const latest = await binding(c); active(latest.enrollment, c);
              throw new CycleError('maritime_cycle_dispatch_unconfirmed');
            }
            const beforeDispatch = await binding(c); active(beforeDispatch.enrollment, c);
            if (!isDeepStrictEqual(beforeDispatch.identity, bound.identity)) throw new CycleError('maritime_cycle_binding_unknown');
            const dispatched = await services.dispatchCycle({ uid: c.tenantId, agentId: bound.identity.agentId,
              occurrenceId: c.occurrenceId, dateKey: c.dateKey, releaseSha: c.releaseSha });
            const acceptedExecution = dispatched?.executionId;
            if (typeof acceptedExecution !== 'string' || !EXECUTION_ID.test(acceptedExecution)) {
              throw new CycleError('maritime_cycle_dispatch_unconfirmed');
            }
            row = await store.bindCycleExecution({ ...bound.identity, executionId: acceptedExecution });
            if (checkpoint(row, bound.identity) !== acceptedExecution) throw new CycleError('maritime_cycle_checkpoint_invalid');
            return acceptedExecution;
          });
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
    async continuation(job, receipt) {
      const c = cycleContract(job);
      const { enrollment } = await binding(c);
      if (enrollment.status !== 'active' || enrollment.paused_at || enrollment.release_sha !== c.releaseSha
        || !managerConsentCurrent(enrollment)) return null;
      const preflight = receipt?.kind === 'maritime_manager_cycle_preflight';
      if (preflight && !verifyCycleReceipt(receipt, job)) throw new CycleError('maritime_cycle_receipt_invalid', false);
      const due = Date.parse(preflight ? receipt.next_eligible_at : job.available_at);
      if (!Number.isFinite(due)) throw new CycleError('maritime_cycle_schedule_invalid', false);
      // A preparation deferral is central evidence of no claim, not a provider execution.
      // Its persisted retry time avoids replaying every overdue slot after an outage.
      const nextMs = preflight ? due : due + 15 * 60 * 1000;
      const availableAt = new Date(nextMs).toISOString();
      return { job: buildMaritimeManagerCycleJob({ tenantId: c.tenantId, releaseSha: c.releaseSha,
        occurrenceId: `slot:${nextMs}`, dateKey: availableAt.slice(0, 10) }), availableAt };
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
function provisionContract(job) {
  try {
    const normalized = buildRuntimeJob(job);
    const c = { tenantId: normalized.tenant_id, releaseSha: normalized.input_refs.release_ref.slice('release://git/'.length),
      phase: normalized.input_refs.provision_phase_ref === undefined ? 'create'
        : ['configure', 'pause'].find(phase => normalized.input_refs.provision_phase_ref === `maritime-provision-phase://${phase}`) || null,
      resumeAt: normalized.input_refs.provision_resume_ref === undefined ? null
        : decodeURIComponent(normalized.input_refs.provision_resume_ref.slice('maritime-provision-resume://'.length)) };
    if (!isDeepStrictEqual(normalized, buildMaritimeManagerProvisionJob(c))) throw new Error();
    return c;
  } catch { throw new CycleError('maritime_provision_job_invalid', false); }
}
function createMaritimeManagerProvisionAdapter(services = {}) {
  const emptyExecutionDigest = createHash('sha256').update('[]').digest('hex');
  const terminalExecutionStatuses = new Set(['completed', 'timed_out', 'cancelled', 'failed']);
  function controlLock(c, operation) {
    const lock = services.withControlLock || ((uid, callback) => require('./runtime-job-store.js').withRuntimeTenantControlLock({ tenantId: uid }, callback));
    return lock(c.tenantId, operation);
  }
  async function enrollment(c, requireActive = false, allowPaused = false, allowLegacyConsentRead = false) {
    const row = await services.managerStore?.read(c.tenantId);
    if (!row || row.uid !== c.tenantId || row.release_sha !== c.releaseSha) throw new CycleError('maritime_provision_binding_invalid', false);
    if (c.phase !== 'pause' && !allowLegacyConsentRead && !managerConsentCurrent(row)) throw new CycleError('maritime_provision_consent_required', false);
    if (c.phase === 'pause' ? (row.status !== 'paused' || !row.paused_at)
      : ((!allowPaused && (row.status === 'paused' || row.paused_at))
        || (requireActive && row.status !== 'active' && !(allowPaused && (row.status === 'paused' || row.paused_at))))) {
      throw new CycleError('maritime_provision_inactive', false);
    }
    return row;
  }
  function source(c) {
    const value = services.provisionSource?.(c.releaseSha);
    if (!value || typeof value.uploadS3Key !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_./-]{0,1023}$/.test(value.uploadS3Key)
      || !/^[0-9a-f]{64}$/.test(value.archiveSha256 || '')) throw new CycleError('maritime_provision_unconfigured', false);
    return { uid: c.tenantId, releaseSha: c.releaseSha, uploadS3Key: value.uploadS3Key, archiveSha256: value.archiveSha256 };
  }
  function snapshot(c, row) {
    if (c.phase === 'pause') return { schema_version: 1, tenantId: c.tenantId, releaseSha: c.releaseSha, paused: true, schedules: [] };
    const wake = require('./maritime-manager-wake.js');
    const plan = row.consent_v2_at ? wake.buildMaritimeReconsentJobs(row) : wake.buildMaritimeInitialJobs(row);
    const anchor = row.consent_v2_at || row.created_at;
    return require('./maritime-manager-schedules.js').projectMaritimeSchedules({ tenantId: c.tenantId,
      releaseSha: c.releaseSha, status: 'active', nextEligibleAt: plan.cycle.availableAt,
      timezone: row.timezone, nowMs: Date.parse(anchor) });
  }
  function receipt(c, job, agentId, schedule = null, executionSummary = null) {
    if (c.phase === 'pause') {
      const ref = `runtime-stop://${job.job_id.slice('maritime-provision:'.length)}`;
      return { schema_version: 1, kind: 'maritime_manager_pause', status: 'completed', provider: 'runtime',
        tenant_id: c.tenantId, job_id: job.job_id, release_sha: c.releaseSha, phase: 'pause', agent_id: agentId || null,
        consent_revoked: true, schedule_sha256: emptyExecutionDigest,
        checked_execution_count: executionSummary?.count, execution_status_sha256: executionSummary?.digest,
        external_ref: ref, evidence_refs: [ref] };
    }
    return { schema_version: 1, kind: 'maritime_manager_provision', status: 'completed', provider: 'maritime',
      tenant_id: c.tenantId, job_id: job.job_id, release_sha: c.releaseSha, phase: c.phase, agent_id: agentId,
      schedule_sha256: schedule ? createHash('sha256').update(JSON.stringify(schedule.schedules)).digest('hex') : null,
      external_ref: `maritime-agent://${agentId}`, evidence_refs: [`maritime-agent://${agentId}`] };
  }
  function verify(value, job) {
    try {
      const c = provisionContract(job);
      if (c.phase === 'pause') return Boolean(value?.schema_version === 1 && value.kind === 'maritime_manager_pause'
        && value.status === 'completed' && value.provider === 'runtime' && value.tenant_id === c.tenantId
        && value.job_id === job.job_id && value.release_sha === c.releaseSha && value.phase === 'pause'
        && (value.agent_id === null || (typeof value.agent_id === 'string' && EXECUTION_ID.test(value.agent_id)))
        && value.consent_revoked === true && value.schedule_sha256 === emptyExecutionDigest
        && Number.isInteger(value.checked_execution_count) && value.checked_execution_count >= 0
        && value.checked_execution_count <= 32 && /^[0-9a-f]{64}$/.test(value.execution_status_sha256 || '')
        && value.external_ref === `runtime-stop://${job.job_id.slice('maritime-provision:'.length)}`
        && isDeepStrictEqual(value.evidence_refs, [value.external_ref]));
      return Boolean(value?.schema_version === 1 && value.kind === 'maritime_manager_provision' && value.status === 'completed'
        && value.provider === 'maritime' && value.tenant_id === c.tenantId && value.job_id === job.job_id
        && value.release_sha === c.releaseSha && value.phase === c.phase && typeof value.agent_id === 'string'
        && EXECUTION_ID.test(value.agent_id) && value.external_ref === `maritime-agent://${value.agent_id}`
        && isDeepStrictEqual(value.evidence_refs, [value.external_ref])
        && (c.phase === 'create' ? value.schedule_sha256 === null : /^[0-9a-f]{64}$/.test(value.schedule_sha256 || '')));
    } catch { return false; }
  }
  async function pauseExecutionSummary(c, row, cancelRunning) {
    if (!row.agent_id) return { count: 0, digest: emptyExecutionDigest };
    if (typeof services.managerStore?.listRecentCycleDispatches !== 'function') {
      throw new CycleError('maritime_pause_execution_readback_unavailable', false);
    }
    const dispatches = await services.managerStore.listRecentCycleDispatches({
      uid: c.tenantId, agentId: row.agent_id, releaseSha: c.releaseSha,
    });
    if (!Array.isArray(dispatches) || dispatches.length > 32) {
      throw new CycleError('maritime_pause_execution_readback_invalid', false);
    }
    const seen = new Set();
    const outcomes = [];
    for (const dispatch of dispatches) {
      if (!dispatch || dispatch.uid !== c.tenantId || dispatch.agent_id !== row.agent_id
        || dispatch.release_sha !== c.releaseSha
        || typeof dispatch.occurrence_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(dispatch.occurrence_id)
        || seen.has(dispatch.occurrence_id)
        || typeof dispatch.execution_id !== 'string' || !EXECUTION_ID.test(dispatch.execution_id)) {
        throw new CycleError('maritime_pause_execution_untracked', false);
      }
      seen.add(dispatch.occurrence_id);
      if (typeof services.readExecution !== 'function') throw new CycleError('maritime_pause_execution_readback_unavailable', false);
      const identity = { uid: c.tenantId, agentId: row.agent_id, executionId: dispatch.execution_id };
      let result = await services.readExecution(identity);
      if (result?.status === 'running' && cancelRunning) {
        if (typeof services.cancelExecution !== 'function') throw new CycleError('maritime_pause_execution_cancel_unavailable', false);
        result = await services.cancelExecution(identity);
      }
      if (!result || result.executionId !== dispatch.execution_id
        || !terminalExecutionStatuses.has(result.status) || !Number.isInteger(result.exitCode)) {
        throw new CycleError('maritime_pause_execution_still_running');
      }
      outcomes.push({ execution_id_hash: createHash('sha256').update(dispatch.execution_id).digest('hex'), status: result.status });
    }
    outcomes.sort((a, b) => a.execution_id_hash.localeCompare(b.execution_id_hash) || a.status.localeCompare(b.status));
    return { count: outcomes.length, digest: createHash('sha256').update(JSON.stringify(outcomes)).digest('hex') };
  }
  async function inspect(c, job, allowLegacyConsentRead = false) {
    const row = await enrollment(c, c.phase === 'configure', true, allowLegacyConsentRead);
    if (c.phase === 'create') {
      const agent = await services.readAgent(source(c));
      if (agent?.status === 'deploying') return { state: 'pending' };
      if (!['active', 'sleeping'].includes(agent?.status) || !EXECUTION_ID.test(agent?.agentId || '')) throw new CycleError('maritime_provision_result_unknown');
      return { state: 'present', receipt: receipt(c, job, agent.agentId) };
    }
    const expected = snapshot(c, row);
    let executionSummary = null;
    if (c.phase === 'pause') {
      if (typeof services.isConsentRevoked !== 'function' || !await services.isConsentRevoked(c.tenantId)) {
        return { state: 'unknown', errorClass: 'maritime_pause_consent_unconfirmed', nextAction: 'inspect_consent_state', retryable: false };
      }
      executionSummary = await pauseExecutionSummary(c, row, false);
      if (!row.agent_id) return { state: 'present', receipt: receipt(c, job, null, expected, executionSummary) };
    }
    const loaded = await services.readWakeConfiguration({ uid: c.tenantId, agentId: row.agent_id, releaseSha: c.releaseSha });
    if (loaded?.ready && c.phase === 'configure' && (row.status === 'paused' || row.paused_at)) {
      require('./maritime-manager-schedules.js').validateMaritimeScheduleSnapshot({ ...expected, schedules: loaded.schedules }, c.tenantId, c.releaseSha);
      return { state: 'present', receipt: receipt(c, job, row.agent_id, { ...expected, schedules: loaded.schedules }) };
    }
    if (!loaded?.ready || !isDeepStrictEqual(loaded.schedules, expected.schedules)) return { state: 'unknown',
      errorClass: 'maritime_provision_configuration_not_loaded', nextAction: 'inspect_agent_deployment', retryable: false };
    return { state: 'present', receipt: receipt(c, job, row.agent_id, expected, executionSummary) };
  }
  async function reconcilePause(c, job) {
    const row = await enrollment(c);
    try { const proof = await inspect(c, job); if (proof.state === 'present') return proof; } catch { /* Idempotent stop intent remains safe to apply. */ }
    if (typeof services.revokeConsent !== 'function') throw new CycleError('maritime_pause_unconfigured', false);
    await services.revokeConsent(c.tenantId);
    if (row.agent_id) await services.writeScheduleSnapshot({ uid: c.tenantId, agentId: row.agent_id, snapshot: snapshot(c, row) });
    await pauseExecutionSummary(c, row, true);
    return inspect(c, job);
  }
  return Object.freeze({
    plan: async input => [buildMaritimeManagerProvisionJob(input)],
    async execute(job) {
      const c = provisionContract(job);
      const row = await enrollment(c, c.phase === 'configure');
      if (c.phase === 'pause') {
        try { const proof = await controlLock(c, () => reconcilePause(c, job)); if (proof.state === 'present') return { receipt: proof.receipt }; }
        catch { /* Retry only idempotent stop cleanup through reconciliation. */ }
        throw new CycleError('maritime_pause_cleanup_unconfirmed');
      }
      if (c.phase === 'create') await services.ensureAgent(source(c));
      else {
        // Only a freshly claimed configure job writes. Reconciliation never calls execute.
        try {
          const configured = await controlLock(c, async () => {
            const current = await enrollment(c, true);
            const input = { uid: c.tenantId, agentId: current.agent_id, releaseSha: c.releaseSha };
            await services.writeScheduleSnapshot({ ...input, snapshot: snapshot(c, current) });
            await services.configureWake(input);
            const proof = await inspect(c, job);
            return proof.state === 'present' ? { receipt: proof.receipt } : null;
          });
          if (configured) return configured;
        } catch { /* A write may have succeeded; recover by readback, never reconfigure. */ }
        throw new CycleError('maritime_provision_configuration_unconfirmed');
      }
      const proof = await inspect(c, job);
      if (proof.state === 'present') return { receipt: proof.receipt };
      throw new CycleError(proof.state === 'pending' ? 'maritime_provision_pending' : 'maritime_provision_configuration_unconfirmed');
    },
    async reconcile(job) {
      const c = provisionContract(job);
      try { return c.phase === 'pause' ? await controlLock(c, () => reconcilePause(c, job)) : await inspect(c, job, true); }
      catch { return { state: 'unknown', errorClass: c.phase === 'pause' ? 'maritime_pause_cleanup_unconfirmed' : 'maritime_provision_readback_unconfirmed',
        nextAction: c.phase === 'pause' ? 'inspect_paused_schedule' : 'inspect_agent_deployment', retryable: false }; }
    },
    async continuation(job, value) {
      const c = provisionContract(job);
      const row = await services.managerStore?.read(c.tenantId);
      if (!row || row.uid !== c.tenantId || row.status !== 'active' || row.paused_at || row.release_sha !== c.releaseSha
        || !managerConsentCurrent(row)) return null;
      if (!verify(value, job) || row.agent_id !== value.agent_id) throw new CycleError('maritime_provision_receipt_invalid');
      if (c.phase === 'create') return { job: buildMaritimeManagerProvisionJob({ ...c, phase: 'configure' }), availableAt: job.available_at };
      const wake = require('./maritime-manager-wake.js');
      const plans = row.consent_v2_at ? wake.buildMaritimeReconsentJobs(row) : wake.buildMaritimeInitialJobs(row);
      if (typeof services.seedInitialReport !== 'function') throw new CycleError('maritime_provision_unconfigured', false);
      await services.seedInitialReport(plans.report);
      return plans.cycle;
    },
    verify,
    report: value => ({ status: value.status, phase: value.phase }),
  });
}
function reportContract(job) {
  try {
    const normalized = buildRuntimeJob(job);
    const c = { tenantId: normalized.tenant_id,
      periodKey: decodeURIComponent(normalized.input_refs.period_ref.slice('maritime-period://'.length)),
      releaseSha: normalized.input_refs.release_ref.slice('release://git/'.length) };
    if (!isDeepStrictEqual(normalized, buildMaritimeManagerReportJob(c))) throw new Error();
    return c;
  } catch { throw new CycleError('maritime_report_job_invalid', false); }
}
function reportReceipt(c, job, delivery) {
  return { schema_version: 1, kind: 'maritime_manager_report', status: 'completed', provider: 'resend',
    tenant_id: c.tenantId, job_id: job.job_id, period_key: c.periodKey, release_sha: c.releaseSha,
    provider_message_id: delivery.providerMessageId, recipient_hash: delivery.recipientHash,
    snapshot_hash: delivery.snapshotHash, sent_at: delivery.sentAt,
    external_ref: `resend-email://${delivery.providerMessageId}`, evidence_refs: [`resend-email://${delivery.providerMessageId}`] };
}
function verifyReportReceipt(receipt, job) {
  try {
    const c = reportContract(job);
    return Boolean(receipt?.schema_version === 1 && receipt.kind === 'maritime_manager_report'
      && receipt.status === 'completed' && receipt.provider === 'resend' && receipt.tenant_id === c.tenantId
      && receipt.job_id === job.job_id && receipt.period_key === c.periodKey && receipt.release_sha === c.releaseSha
      && EXECUTION_ID.test(receipt.provider_message_id || '') && /^[0-9a-f]{64}$/.test(receipt.recipient_hash || '')
      && /^[0-9a-f]{64}$/.test(receipt.snapshot_hash || '') && typeof receipt.sent_at === 'string'
      && Number.isFinite(Date.parse(receipt.sent_at)) && receipt.external_ref === `resend-email://${receipt.provider_message_id}`
      && isDeepStrictEqual(receipt.evidence_refs, [receipt.external_ref]));
  } catch { return false; }
}
function createMaritimeManagerReportAdapter(services = {}) {
  async function enrollment(c, active = false) {
    if (typeof services.managerStore?.read !== 'function') throw new CycleError('maritime_report_unconfigured', false);
    const row = await services.managerStore.read(c.tenantId);
    if (!row || row.uid !== c.tenantId) throw new CycleError('maritime_report_binding_invalid', false);
    if (active && (row.status !== 'active' || row.paused_at || row.release_sha !== c.releaseSha || !managerConsentCurrent(row))) {
      throw new CycleError('maritime_report_inactive', false);
    }
    return row;
  }
  return Object.freeze({
    plan: async input => [buildMaritimeManagerReportJob(input)],
    async execute(job) {
      const c = reportContract(job);
      const row = await enrollment(c, true);
      if (typeof services.readDailyObservations !== 'function' || typeof services.deliverDailyResult !== 'function') {
        throw new CycleError('maritime_report_unconfigured', false);
      }
      const observations = await services.readDailyObservations({ uid: c.tenantId, periodKey: c.periodKey });
      const result = require('./maritime-manager-report.js').buildMaritimeDailyResult({ ...observations, enrollment: row, periodKey: c.periodKey });
      const observedAt = (services.now || (() => new Date().toISOString()))();
      const delivery = await services.deliverDailyResult({ enrollment: row, result, observedAt });
      const receipt = reportReceipt(c, job, delivery || {});
      if (!['sent', 'duplicate'].includes(delivery?.status) || !verifyReportReceipt(receipt, job)) {
        throw new CycleError('maritime_report_delivery_unknown');
      }
      return { receipt };
    },
    async reconcile(job) {
      const c = reportContract(job);
      try {
        await enrollment(c);
        if (typeof services.readReportDelivery !== 'function') throw new Error();
        const row = await services.readReportDelivery({ uid: c.tenantId, periodKey: c.periodKey });
        if (!row || row.uid !== c.tenantId || row.period_key !== c.periodKey || row.channel !== 'email'
          || row.status !== 'sent' || typeof row.message !== 'string') throw new Error();
        const receipt = reportReceipt(c, job, { providerMessageId: row.provider_message_id,
          recipientHash: row.recipient_hash, snapshotHash: createHash('sha256').update(row.message).digest('hex'), sentAt: row.sent_at });
        if (!verifyReportReceipt(receipt, job)) throw new Error();
        return { state: 'present', receipt };
      } catch { return { state: 'unknown', errorClass: 'maritime_report_delivery_unconfirmed',
        nextAction: 'inspect_email_provider_receipt', retryable: false }; }
    },
    async continuation(job) {
      const c = reportContract(job), row = await enrollment(c);
      if (row.status !== 'active' || row.paused_at || row.release_sha !== c.releaseSha || !managerConsentCurrent(row)) return null;
      const nowMs = Date.parse(job.available_at);
      if (!Number.isFinite(nowMs)) throw new CycleError('maritime_report_schedule_invalid', false);
      const snapshot = require('./maritime-manager-schedules.js').projectMaritimeSchedules({ tenantId: c.tenantId,
        releaseSha: c.releaseSha, status: 'active', nextEligibleAt: null, timezone: row.timezone, nowMs });
      const availableAt = snapshot.schedules.find(entry => entry.prompt === 'lm:report').nextRunAt;
      const { localDay, zoneOffsetHours } = require('./user-tz.js');
      const date = localDay(Date.parse(availableAt), zoneOffsetHours(row.timezone, Date.parse(availableAt)));
      return { job: buildMaritimeManagerReportJob({ ...c, periodKey: `maritime:daily:${date}` }), availableAt };
    },
    verify: verifyReportReceipt,
    report: receipt => ({ status: receipt.status, channel: 'email' }),
  });
}
module.exports = { buildMaritimeManagerProvisionJob, buildMaritimeManagerCycleJob, buildMaritimeManagerReportJob, createMaritimeManagerLoopAdapter, createMaritimeManagerReportAdapter, createMaritimeManagerProvisionAdapter, readMaritimeCycleContract: cycleContract, maritimeArtifactRefsValid: artifactRefsValid };
