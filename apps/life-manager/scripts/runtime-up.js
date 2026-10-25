#!/usr/bin/env node
"use strict";

const path = require("node:path");
const http = require("node:http");
const os = require("node:os");
const dns = require("node:dns");
const { isDeepStrictEqual } = require("node:util");

function requiredEnv(env, name) {
  const value = String(env[name] || "").trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function createHealthServer(port, state) {
  const server = http.createServer((request, response) => {
    if (request.url !== "/health") {
      response.writeHead(404).end("not found");
      return;
    }
    const ok = state.ready === true && state.error == null;
    response.writeHead(ok ? 200 : 503, { "content-type": "application/json" });
    response.end(JSON.stringify({
      ok,
      role: state.role,
      worker_id: state.workerId,
      capabilities: state.capabilities,
      last_poll_at: state.lastPollAt,
    }));
  });
  server.listen(port, "0.0.0.0");
  return server;
}

function createScopedEnvironmentSecretProvider(env = process.env) {
  const { createSecretProvider } = require("../lib/secret-provider.js");
  const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
  const bindings = new Map([
    ["secret://telegram/bot-token", "LM_TELEGRAM_BOT_TOKEN"],
    ["secret://postiz/api-key", "LM_POSTIZ_API_KEY"],
  ]);
  return createSecretProvider({
    mode: "local",
    keychain: {
      async get(requestTenantId, ref) {
        if (requestTenantId !== tenantId) {
          throw new Error("environment secret tenant scope mismatch");
        }
        const envName = bindings.get(ref);
        if (!envName) throw new Error("environment secret reference is not declared");
        return requiredEnv(env, envName);
      },
      async health() {
        return { ok: true };
      },
    },
  });
}

async function observeMaritimeCompletion(job, receipt, services, durable = job) {
  if (typeof services.onJobCompleted !== "function" || !job?.capability?.startsWith("maritime.manager.")) return;
  try {
    if (!durable || durable.tenant_id !== job.tenant_id || durable.job_id !== job.job_id || durable.attempt !== job.attempt) throw new Error("completion scope invalid");
    const completed = durable.status === "completed" ? durable
      : durable.outcome === "completed" && isDeepStrictEqual(durable.receipt, receipt)
        ? { ...job, status: "completed", completed_at: durable.created_at } : null;
    if (completed) {
      await require("../lib/maritime-manager-usage.js").observeMaritimeUsage("completion", job.tenant_id, signal => services.onJobCompleted(completed, receipt, { signal }), services);
      return;
    }
  } catch { /* Telemetry cannot change a durable business completion. */ }
  process.stderr.write(JSON.stringify({ kind: "maritime_usage_unconfirmed", job_id: job.job_id,
    phase: "completion", error_class: "usage_store_unconfirmed", retryable: true,
    next_action: "backfill_from_runtime_receipt" }) + "\n");
}

async function executeCapabilityJob(job, services) {
  const {
    workerId,
    handlers = {},
    heartbeatJob,
    completeJob,
    completeJobAndEnqueue,
    failJob,
    storeOptions,
    leaseSeconds = 300,
    setIntervalFn,
    clearIntervalFn,
  } = services;
  const identity = {
    tenantId: job.tenant_id,
    jobId: job.job_id,
    attempt: job.attempt,
    workerId,
  };
  const handler = handlers[job.capability];
  if (typeof handler !== "function") {
    if (job.effect_class === "none") {
      await completeJob({
        ...identity,
        receipt: {
          kind: "runtime_noop",
          worker_id: workerId,
          completed_at: new Date().toISOString(),
        },
      }, storeOptions);
      return;
    }
    await failJob({
      ...identity,
      errorCode: "CAPABILITY_ADAPTER_UNAVAILABLE",
      unknownEffect: true,
    }, storeOptions);
    return;
  }
  let leaseHeartbeat;
  if (typeof heartbeatJob === "function") {
    const {
      startRuntimeLeaseHeartbeat,
    } = require("../lib/runtime-lease-heartbeat.js");
    leaseHeartbeat = startRuntimeLeaseHeartbeat({
      ...identity,
      leaseSeconds,
    }, {
      heartbeatJob,
      storeOptions,
      setIntervalFn,
      clearIntervalFn,
    });
  }

  let execution;
  let executionError;
  let heartbeatFailed = false;
  let unknownEffect = false;
  try {
    execution = await handler(job);
    if (!execution || !execution.receipt) {
      throw new Error("capability adapter returned no receipt");
    }
    if (job.capability === "outbound.event.apply") {
      const {
        assertVerifiedOutboundReceipt,
      } = require("../lib/outbound-success.js");
      assertVerifiedOutboundReceipt(execution.receipt, job);
    }
  } catch (error) {
    executionError = error;
    unknownEffect = error && error.unknownEffect === true;
  }
  if (leaseHeartbeat) {
    try {
      await leaseHeartbeat.stop();
    } catch (error) {
      executionError = executionError || error;
      heartbeatFailed = true;
      unknownEffect = unknownEffect || job.effect_class !== "none";
    }
  }
  if (executionError) {
    const connectorCoverageCode = job.capability === "connector.coverage.refresh"
      && /^CONNECTOR_COVERAGE_[A-Z_]+$/.test(String(executionError.code || ""))
      ? executionError.code
      : null;
    const outboundLumaCode = job.capability === "outbound.event.apply"
      && new Set([
        "LUMA_LOGIN_REQUIRED",
        "LUMA_RSVP_UNAVAILABLE",
        "LUMA_EFFECT_UNKNOWN",
      ]).has(String(executionError.code || ""))
      ? executionError.code
      : null;
    const maritimeCode = job.capability.startsWith("maritime.manager.")
      && /^MARITIME_[A-Z_]{1,160}$/.test(String(executionError.code || "")) ? executionError.code : null;
    await failJob({
      ...identity,
      errorCode: heartbeatFailed
        ? "CAPABILITY_HEARTBEAT_FAILED"
        : connectorCoverageCode || outboundLumaCode || maritimeCode || "CAPABILITY_EXECUTION_FAILED",
      unknownEffect,
    }, storeOptions);
    return;
  }
  if (execution.receipt.status === "blocked") return;
  let completed;
  if (execution.continuation) {
    if (typeof completeJobAndEnqueue !== "function") throw new Error("runtime continuation store unavailable");
    completed = await completeJobAndEnqueue({ ...identity, receipt: execution.receipt,
      nextJob: execution.continuation.job, availableAt: execution.continuation.availableAt }, storeOptions);
  } else {
    completed = await completeJob({ ...identity, receipt: execution.receipt }, storeOptions);
  }
  await observeMaritimeCompletion(job, execution.receipt, services, completed);
}

async function reconcileMaritimeCapabilityJobs(capabilities, dependencies = {}) {
  const scoped = capabilities.filter(value => ["maritime.manager.provision", "maritime.manager.cycle", "maritime.manager.report",
    "maritime.manager.capafy.prepare", "maritime.manager.capafy.publish"].includes(value));
  if (!scoped.length) return;
  const { registry, store, storeOptions = {}, observe } = dependencies;
  const { reconcileUnknownEffect } = require("../lib/effect-reconciler.js");
  const jobs = await store.claimReconcilingJobs({ capabilities: scoped, limit: 1 }, storeOptions);
  for (const job of jobs) {
    const adapter = registry.getByCapability(job.capability);
    await reconcileUnknownEffect(job, {
      adapter: { inspectEffect: async () => {
        let proof = await adapter.reconcile(job);
        if (proof?.state === "present" && !await adapter.verify(proof.receipt, job)) {
          proof = { state: "unknown", errorClass: "maritime_receipt_invalid", nextAction: "inspect_provider_execution", retryable: false };
        }
        if (typeof observe === "function") observe({ kind: "maritime_reconciliation", job_id: job.job_id,
          tenant_id: job.tenant_id, attempt: job.attempt, state: proof?.state,
          error_class: /^[a-z_]{1,180}$/.test(proof?.errorClass || "") ? proof.errorClass : null,
          next_action: /^[a-z_]{1,180}$/.test(proof?.nextAction || "") ? proof.nextAction : null,
          retryable: proof?.retryable === true });
        return proof;
      } },
      store: {
        recordUnknownReconciliation: input => /^maritime\.manager\.capafy\.(prepare|publish)$/.test(job.capability)
          // Keep provider action fences eligible for a later official readback.
          // claimReconcilingJobs still enforces the existing 30-second readback seat.
          ? Promise.resolve({ status: "reconciling" }) : store.recordUnknownReconciliation(input, storeOptions),
        resolveReconciliation: async input => {
          const next = input.decision === "present" && typeof adapter.continuation === "function"
            ? await adapter.continuation(job, input.receipt) : null;
          const completed = next ? await store.resolveReconciliationAndEnqueue({ ...input, nextJob: next.job, availableAt: next.availableAt }, storeOptions)
            : await store.resolveReconciliation(input, storeOptions);
          if (input.decision === "present") await observeMaritimeCompletion(job, input.receipt, dependencies, completed);
          return completed;
        },
      },
    });
  }
}

function validateMaritimeProvisionState(state, job, tenantId) {
  if (!state) return null;
  if (state.job_id !== job.job_id || state.tenant_id !== tenantId
    || !["queued", "running", "reconciling", "completed", "dead_letter"].includes(state.status)
    || !Number.isInteger(state.attempt) || state.attempt < 0 || state.attempt > job.max_attempts
    || (state.last_error_code != null && (typeof state.last_error_code !== "string"
      || state.last_error_code.length < 1 || state.last_error_code.length > 200))) {
    throw new Error("maritime_provision_recovery_state_invalid");
  }
  return state;
}

async function enqueueMaritimeProvisionRecovery(row, phase, { enqueueJob, readProvisionJobState, storeOptions = {} } = {}) {
  const runtime = require("../lib/maritime-manager-runtime.js");
  const { MANAGER_CONSENT_VERSION } = require("../lib/maritime-distribution.js");
  const readState = readProvisionJobState || require("../lib/runtime-job-store.js").readRuntimeJobState;
  const enqueue = enqueueJob || require("../lib/runtime-job-store.js").enqueueJob;
  const read = async job => validateMaritimeProvisionState(
    await readState({ tenantId: row.uid, job }, storeOptions), job, row.uid,
  );
  const base = runtime.buildMaritimeManagerProvisionJob({ tenantId: row.uid, releaseSha: row.release_sha, phase });
  const canResume = state => state?.status === "dead_letter"
    && state.last_error_code === "MARITIME_PROVISION_CONSENT_REQUIRED" && state.attempt === 1
    && row.consent_version === MANAGER_CONSENT_VERSION
    && typeof row.consent_v2_at === "string" && Number.isFinite(Date.parse(row.consent_v2_at));

  let job = base;
  let state = await read(base);
  if (canResume(state)) {
    job = runtime.buildMaritimeManagerProvisionJob({ tenantId: row.uid, releaseSha: row.release_sha, phase,
      resumeAt: new Date(row.consent_v2_at).toISOString() });
    state = await read(job);
  }
  if (state) return { created: false, job: { ...job, status: state.status } };

  const queued = await enqueue(job, storeOptions);
  if (!queued || typeof queued.created !== "boolean" || queued.job?.job_id !== job.job_id
    || queued.job?.tenant_id !== row.uid
    || !["queued", "running", "reconciling", "completed", "dead_letter"].includes(queued.job.status)) {
    throw new Error("maritime_provision_recovery_enqueue_invalid");
  }
  // Close the read-then-enqueue race: the legacy job may dead-letter on its
  // no-effect consent guard between our first state read and the idempotent enqueue.
  if (job.job_id === base.job_id && queued.job.status === "dead_letter") {
    const terminal = await read(base);
    if (canResume(terminal)) {
      const resume = runtime.buildMaritimeManagerProvisionJob({ tenantId: row.uid, releaseSha: row.release_sha, phase,
        resumeAt: new Date(row.consent_v2_at).toISOString() });
      const resumedState = await read(resume);
      if (resumedState) return { created: false, job: { ...resume, status: resumedState.status } };
      const resumed = await enqueue(resume, storeOptions);
      if (!resumed || typeof resumed.created !== "boolean" || resumed.job?.job_id !== resume.job_id
        || resumed.job?.tenant_id !== row.uid
        || !["queued", "running", "reconciling", "completed", "dead_letter"].includes(resumed.job.status)) {
        throw new Error("maritime_provision_recovery_enqueue_invalid");
      }
      return resumed;
    }
  }
  return queued;
}

async function recoverMaritimeEnrollments(capabilities, { managerStore, enqueueJob, readProvisionJobState,
  storeOptions = {}, pausedCursor = null } = {}) {
  if (!capabilities.includes("maritime.manager.provision")) return;
  const { MANAGER_CONSENT_VERSION } = require("../lib/maritime-distribution.js");
  for (const row of await managerStore.listPending(1)) {
    // The legacy customer must explicitly accept v2 before any new provisioning job can be created.
    if (row.consent_version !== MANAGER_CONSENT_VERSION) continue;
    const queued = await enqueueMaritimeProvisionRecovery(row, "create", { enqueueJob, readProvisionJobState, storeOptions });
    if (["dead_letter", "completed"].includes(queued?.job?.status)) {
      await managerStore.quarantinePendingProvision(row.uid);
    }
  }
  const { buildMaritimeManagerProvisionJob } = require("../lib/maritime-manager-runtime.js");
  const paused = await managerStore.listPaused(20, pausedCursor);
  for (const row of paused) {
    await enqueueJob(buildMaritimeManagerProvisionJob({ tenantId: row.uid, releaseSha: row.release_sha, phase: "pause" }), storeOptions);
  }
  return paused.length === 20 ? paused.at(-1).uid : null;
}

function maritimeCapafyHostProviderConfigured(provider) {
  return Boolean(provider && typeof provider.readAccountBinding === "function"
    && typeof provider.withAccessToken === "function" && typeof provider.guardArtifact === "function"
    && typeof provider.prepare === "function" && typeof provider.readPrepare === "function"
    && typeof provider.readPublisherConfirmation === "function" && typeof provider.readPublish === "function");
}

async function enqueueMaritimeCapafyPrepareAfterCompletion(job, receipt, dependencies = {}) {
  if (job?.capability !== "maritime.manager.cycle" || job.status !== "completed"
    || receipt?.kind !== "maritime_manager_cycle" || receipt.status !== "completed"
    || receipt.job_id !== job.job_id || receipt.tenant_id !== job.tenant_id) return { status: "skipped" };
  const { provider, managerStore, enqueueJob, storeOptions = {} } = dependencies;
  if (!maritimeCapafyHostProviderConfigured(provider) || !managerStore || typeof enqueueJob !== "function") {
    return { status: "skipped", reason: "host_executor_unavailable" };
  }
  try {
    const result = await require("../lib/maritime-manager-provider-runtime.js").enqueueMaritimeCapafyPrepareFromCycle(
      { job, receipt }, { provider, managerStore, enqueueJob: next => enqueueJob(next, storeOptions) });
    return { status: "queued", created: result?.created === true,
      job_id: result?.job?.job_id || null, tenant_id: job.tenant_id };
  } catch (error) {
    const errorClass = /^[a-z0-9_]{1,120}$/i.test(String(error?.code || error?.message || ""))
      ? String(error.code || error.message).toLowerCase() : "maritime_capafy_admission_unconfirmed";
    dependencies.observe?.({ kind: "maritime_capafy_admission", job_id: job.job_id,
      tenant_id: job.tenant_id, status: "deferred", error_class: errorClass });
    return { status: "deferred", error_class: errorClass };
  }
}

function createMaritimeCapafyCompletionObserver({ onJobCompleted, provider, managerStore, enqueueJob,
  storeOptions = {}, observe } = {}) {
  return async (job, receipt, telemetry = {}) => {
    if (job?.capability === "maritime.manager.cycle") {
      await enqueueMaritimeCapafyPrepareAfterCompletion(job, receipt, { provider, managerStore,
        enqueueJob, storeOptions, observe });
    }
    return onJobCompleted?.(job, receipt, telemetry);
  };
}

async function recoverMaritimeCapafyCycleAdmissions(capabilities, { enabled = false, provider,
  managerStore, enqueueJob, query, storeOptions = {}, observe } = {}) {
  if (enabled !== true || !capabilities.includes("maritime.manager.capafy.prepare")
    || !maritimeCapafyHostProviderConfigured(provider) || !managerStore
    || typeof enqueueJob !== "function" || typeof query !== "function") return { status: "disabled", queued: 0 };
  const cursorKey = "cycle_admission";
  const cursorRows = (await query(`
    SELECT completed_at::text AS completed_at, tenant_id, job_id
    FROM private.lm_maritime_manager_capafy_recovery_cursor
    WHERE cursor_key=$1 LIMIT 2
  `, [cursorKey])).rows;
  if (!Array.isArray(cursorRows) || cursorRows.length !== 1) throw new Error("maritime_capafy_admission_cursor_unavailable");
  const currentCursor = cursorRows[0];
  let cursor = currentCursor.completed_at == null && currentCursor.tenant_id == null && currentCursor.job_id == null
    ? null : { completed_at: currentCursor.completed_at, tenant_id: currentCursor.tenant_id, job_id: currentCursor.job_id };
  if (cursor && (!Number.isFinite(Date.parse(cursor.completed_at))
    || !/^lm_[0-9a-f-]{36}$/i.test(cursor.tenant_id || "")
    || !/^maritime-cycle:[0-9a-f]{64}$/i.test(cursor.job_id || ""))) {
    throw new Error("maritime_capafy_admission_cursor_invalid");
  }
  const persistCursor = async value => {
    const result = await query(`
      UPDATE private.lm_maritime_manager_capafy_recovery_cursor
      SET completed_at=$2::timestamptz, tenant_id=$3, job_id=$4, updated_at=clock_timestamp()
      WHERE cursor_key=$1 RETURNING cursor_key
    `, [cursorKey, value?.completed_at ?? null, value?.tenant_id ?? null, value?.job_id ?? null]);
    if (!Array.isArray(result?.rows) || result.rows.length !== 1) throw new Error("maritime_capafy_admission_cursor_write_unconfirmed");
  };
  const readCandidates = async after => {
    const result = await query(`
      SELECT jobs.completed_at::text AS completed_at, jobs.tenant_id, jobs.job_id,
        row_to_json(jobs) AS job, receipts.receipt
      FROM public.lm_runtime_jobs AS jobs
      JOIN public.lm_runtime_job_receipts AS receipts
        ON receipts.job_id=jobs.job_id AND receipts.tenant_id=jobs.tenant_id
         AND receipts.attempt=jobs.attempt
      JOIN public.lm_maritime_manager_enrollments AS managers
        ON managers.uid=jobs.tenant_id AND jobs.input_refs->>'release_ref'=('release://git/' || managers.release_sha)
      JOIN private.lm_maritime_manager_capafy_bindings AS bindings
        ON bindings.uid=managers.uid AND bindings.auth_subject=managers.auth_subject
      WHERE jobs.capability='maritime.manager.cycle' AND jobs.status='completed'
        AND jobs.completed_at >= clock_timestamp() - interval '24 hours'
        AND receipts.outcome IN ('completed','reconciled_present')
        AND receipts.receipt->>'kind'='maritime_manager_cycle'
        AND receipts.receipt->>'status'='completed'
        AND managers.status='active' AND managers.paused_at IS NULL
        AND NOT EXISTS (
          SELECT 1 FROM public.lm_runtime_jobs AS prepares
          WHERE prepares.tenant_id=jobs.tenant_id AND prepares.capability='maritime.manager.capafy.prepare'
            AND prepares.input_refs->>'source_cycle_job_id'=jobs.job_id
        )
        AND ($1::timestamptz IS NULL OR (jobs.completed_at, jobs.tenant_id, jobs.job_id) > ($1::timestamptz, $2::text, $3::text))
      ORDER BY jobs.completed_at ASC, jobs.tenant_id ASC, jobs.job_id ASC
      LIMIT 20
    `, [after?.completed_at ?? null, after?.tenant_id ?? null, after?.job_id ?? null]);
    if (!Array.isArray(result?.rows) || result.rows.length > 20) throw new Error("maritime_capafy_admission_read_invalid");
    return result.rows;
  };
  let rows = await readCandidates(cursor);
  if (rows.length === 0 && cursor) {
    // Wrap to the start after reaching the end. Persisted keyset pagination
    // ensures deferred/refused rows cannot permanently occupy the first batch.
    await persistCursor(null);
    cursor = null;
    rows = await readCandidates(cursor);
  }
  let queued = 0;
  for (const row of rows) {
    const result = await enqueueMaritimeCapafyPrepareAfterCompletion(row?.job, row?.receipt,
      { provider, managerStore, enqueueJob, storeOptions, observe });
    if (result.status === "queued") queued += Number(result.created === true);
    const completedAt = row?.completed_at;
    const tenantId = row?.tenant_id || row?.job?.tenant_id;
    const jobId = row?.job_id || row?.job?.job_id;
    if (!Number.isFinite(Date.parse(completedAt)) || typeof tenantId !== "string" || typeof jobId !== "string") {
      throw new Error("maritime_capafy_admission_candidate_invalid");
    }
    cursor = { completed_at: completedAt, tenant_id: tenantId, job_id: jobId };
    await persistCursor(cursor);
  }
  return { status: "checked", queued, candidates: rows.length };
}

async function recoverReconsentedMaritimeConfigurations(capabilities, { managerStore, enqueueJob, readProvisionJobState,
  storeOptions = {}, activeCursor = null } = {}) {
  if (!capabilities.includes("maritime.manager.provision") || typeof managerStore?.listReconsentedActive !== "function") return null;
  const rows = await managerStore.listReconsentedActive(20, activeCursor);
  for (const row of rows) {
    await enqueueMaritimeProvisionRecovery(row, "configure", { enqueueJob, readProvisionJobState, storeOptions });
  }
  return rows.length === 20 ? rows.at(-1).uid : null;
}

function createMaritimeManagerWorkerDependencies({ pgPool, env = process.env, recordMaritimeManagerCompletion } = {}) {
  const managerDependencies = require("../lib/maritime-manager-dependencies.js").createMaritimeManagerDependencies({ pgPool, env });
  const recordCompletion = recordMaritimeManagerCompletion
    || require("../lib/maritime-manager-usage.js").recordMaritimeManagerCompletion;
  return Object.freeze({
    ...managerDependencies,
    onJobCompleted: (job, receipt, telemetry = {}) => recordCompletion(job, receipt,
      { env, ...telemetry, ...managerDependencies }),
  });
}

function createMaritimeCapafyAccountBinding({ query, managerStore, env = process.env, fetchImpl = globalThis.fetch } = {}) {
  if (typeof query !== "function" || !managerStore) throw new Error("maritime_capafy_binding_unavailable");
  const binding = require("../lib/maritime-manager-capafy-binding.js");
  const bindingStore = binding.createMaritimeCapafyBindingStore({ query,
    encryptionKey: requiredEnv(env, "LM_MARITIME_CAPAFY_ENCRYPTION_KEY") });
  const connector = binding.createCapafyAccountConnector({ fetchImpl });
  return binding.createMaritimeCapafyAccountBinding({ bindingStore, managerStore, connector });
}

function createWorkerHandlers(env, capabilities, dependencies = {}) {
  const handlers = {};
  const servicesByAdapter = {};
  if (capabilities.some(value => value.startsWith("maritime.manager."))) {
    const managerDependencies = dependencies.maritimeManagerDependencies;
    const managerStore = dependencies.maritimeManagerStore || managerDependencies?.managerStore;
    if (!managerStore) throw new Error("maritime_manager_postgres_store_unavailable");
    const getWakeBinding = identity => require("../lib/maritime-manager-wake.js").createMaritimeWakeBinding(identity, {
      secret: env.LM_MARITIME_MANAGER_ID_SECRET, publicOrigin: env.LM_PANEL_BASE_URL,
    });
    const transport = dependencies.maritimeTransport
      || require("../lib/transport/maritime-manager.js").createMaritimeManagerTransport({ env, managerStore,
        getWakeBinding, fetchImpl: dependencies.fetchImpl });
    const withControlLock = dependencies.withControlLock
      || ((uid, operation) => require("../lib/runtime-job-store.js").withRuntimeTenantControlLock({ tenantId: uid }, operation, { connect: dependencies.connect }));
    if (capabilities.includes("maritime.manager.provision")) {
      const distribution = dependencies.maritimeDistributionStore
        || managerDependencies?.distributionStore;
      if (!distribution) throw new Error("maritime_manager_postgres_distribution_unavailable");
      const isConsentRevoked = async uid => {
        const state = await distribution.getParticipant(uid);
        if (state?.ok !== true) throw new Error("maritime_consent_readback_unavailable");
        return state.participant == null || Boolean(state.participant.revoked_at);
      };
      servicesByAdapter["maritime-manager-provision"] = { managerStore, withControlLock,
        isConsentRevoked,
        revokeConsent: async uid => {
          if (await isConsentRevoked(uid)) return;
          await distribution.revoke(uid);
          if (!await isConsentRevoked(uid)) throw new Error("maritime_consent_revoke_unconfirmed");
        },
        ensureAgent: transport.ensureAgent, readAgent: transport.readAgent,
        configureWake: transport.configureWake, readWakeConfiguration: transport.readWakeConfiguration,
        writeScheduleSnapshot: transport.writeScheduleSnapshot,
        readExecution: transport.readExecution, cancelExecution: transport.cancelExecution,
        provisionSource: releaseSha => {
          if (releaseSha !== env.LM_MARITIME_MANAGER_IMAGE_RELEASE_SHA) throw new Error("maritime source release unavailable");
          return { uploadS3Key: env.LM_MARITIME_MANAGER_SOURCE_S3_KEY, archiveSha256: env.LM_MARITIME_MANAGER_SOURCE_ARCHIVE_SHA256 };
        },
        seedInitialReport: plan => require("../lib/runtime-job-store.js").enqueueJobAt(plan.job, plan.availableAt,
          { query: dependencies.query }),
      };
    }
    servicesByAdapter["maritime-manager-cycle"] = { managerStore, withControlLock,
      prepareCycle: input => transport.readWakeConfiguration({ ...input, activeOnly: true }), dispatchCycle: transport.dispatchCycle,
      readExecution: transport.readExecution, readCycleReceipt: transport.readCycleReceipt };
    if (capabilities.some(value => /^maritime\.manager\.capafy\.(prepare|publish)$/.test(value))) {
      if (typeof dependencies.query !== "function") throw new Error("maritime provider database unavailable");
      const accountBinding = dependencies.maritimeCapafyAccountBinding;
      const provider = dependencies.maritimeCapafyProvider
        ? Object.freeze({ ...dependencies.maritimeCapafyProvider,
          ...(accountBinding ? { readAccountBinding: accountBinding.readAccountBinding,
            withAccessToken: accountBinding.withAccessToken } : {}) })
        : accountBinding;
      const readPredecessor = async ({ tenantId, jobId }) => {
        const rows = (await dependencies.query(`
          SELECT row_to_json(jobs) AS job, receipts.receipt
          FROM public.lm_runtime_jobs AS jobs
          JOIN public.lm_runtime_job_receipts AS receipts ON receipts.job_id=jobs.job_id
           AND receipts.tenant_id=jobs.tenant_id AND receipts.attempt=jobs.attempt
           AND receipts.outcome IN ('completed','reconciled_present')
          WHERE jobs.tenant_id = $1 AND jobs.job_id = $2 AND jobs.status='completed'
          LIMIT 2`, [tenantId, jobId])).rows;
        if (!Array.isArray(rows) || rows.length > 1) throw new Error("maritime provider predecessor invalid");
        return rows[0] || null;
      };
      // Host provider binding is explicit. Never fall back to founder credentials
      // or model-controlled VM state when T08/T16 setup is still unavailable.
      const services = { managerStore, provider,
        readCompletedCycle: readPredecessor, readPrepareReceipt: readPredecessor, now: dependencies.now };
      servicesByAdapter["maritime-manager-capafy-prepare"] = services;
      servicesByAdapter["maritime-manager-capafy-publish"] = services;
    }
    if (capabilities.includes("maritime.manager.report")) {
      if (typeof dependencies.query !== "function") throw new Error("maritime report database unavailable");
      const report = require("../lib/maritime-manager-report.js");
      const deliveryDeps = { env, managerStore, resendKey: env.RESEND_API_KEY,
        fetchImpl: dependencies.fetchImpl };
      const io = dependencies.maritimeReportReceiptIO
        || managerDependencies?.cfoReceiptIO;
      if (!io) throw new Error("maritime_manager_postgres_cfo_receipt_io_unavailable");
      servicesByAdapter["maritime-manager-report"] = {
        managerStore,
        readDailyObservations: input => report.readMaritimeDailyObservations(input, { query: dependencies.query }),
        deliverDailyResult: input => report.deliverMaritimeDailyResult(input, { ...deliveryDeps, cfoReceiptIO: io }),
        readReportDelivery: identity => io.read(identity), now: dependencies.now,
      };
    }

  }

  if (capabilities.includes("agent-economy.start")) {
    if (typeof dependencies.query !== "function") {
      throw new Error("Agent Economy Cloud citizen store unavailable");
    }
    const { createCloudCitizenStore } = require("../lib/cloud-citizen-store.js");
    const createWakeRunner = dependencies.createAgentEconomyCloudWakeRunner
      || require("../lib/agent-economy-cloud-wake.js").createAgentEconomyCloudWakeRunner;
    const citizenStore = createCloudCitizenStore({
      query: dependencies.query,
      encryptionKey: requiredEnv(env, "LM_CLOUD_CITIZEN_ENCRYPTION_KEY"),
    });
    const { createAgentEconomyControlStore } = require("../lib/agent-economy-control.js");
    const economyControl = createAgentEconomyControlStore({ query: dependencies.query });
    const { createPostgresFinancialRecordStore } = require("../lib/financial-record-store.js");
    const { createCloudFinancialTransitionStore } = require("../lib/agent-economy-telegram.js");
    const financialStore = createCloudFinancialTransitionStore({
      store: createPostgresFinancialRecordStore({ query: dependencies.query }),
      query: dependencies.query,
      readTenant: dependencies.readFinancialTenant || ((uid) => (
        require("../lib/financial-report-runtime.js").readFinancialTenant(uid, {
          supaUrl: env.SUPABASE_URL,
          supaKey: env.SUPABASE_SERVICE_ROLE_KEY,
          fetchImpl: dependencies.fetchImpl || globalThis.fetch,
        })
      )),
      telegramToken: env.LM_TELEGRAM_BOT_TOKEN,
      sendTelegram: dependencies.sendTelegram,
      now: dependencies.now,
    });
    servicesByAdapter["agent-economy-cloud"] = {
      citizenStore,
      isPaused: (tenantId) => economyControl.isPaused(tenantId),
      runSharedWake: createWakeRunner({
        citizenStore,
        dataDir: requiredEnv(env, "LM_DATA_DIR"),
        repoRoot: String(env.LM_REPO_ROOT || "").trim() || path.resolve(__dirname, "../../.."),
        financialStore,
        now: dependencies.now,
      }),
      now: dependencies.now,
    };
  }
  if (capabilities.includes("general-agent.work")) {
    const {
      createMoneyPrinterRuntimeStore,
    } = require("../lib/money-printer-runtime-store.js");
    const {
      createMoneyPrinterSpecialist,
    } = require("../lib/money-printer-specialist.js");
    let specialist = dependencies.moneyPrinterSpecialist || dependencies.runBoundedSpecialist;
    if (!specialist) {
      const runAgentRunner = typeof dependencies.runAgentRunner === "function"
        ? dependencies.runAgentRunner
        : typeof dependencies.runLocalAgentRunner === "function"
          ? dependencies.runLocalAgentRunner
          : null;
      const geminiKey = String(env.GEMINI_API_KEY || "").trim();
      if (!geminiKey && !runAgentRunner) throw new Error("GEMINI_API_KEY is required");
      const runtimeStore = typeof dependencies.query === "function"
        ? createMoneyPrinterRuntimeStore({ query: dependencies.query })
        : null;
      const readOpportunity = dependencies.readOpportunity || (runtimeStore && runtimeStore.readOpportunity);
      const updateOpportunity = dependencies.updateOpportunity || (runtimeStore && runtimeStore.updateOpportunity);
      if (typeof readOpportunity !== "function" || typeof updateOpportunity !== "function") {
        throw new Error("money printer runtime opportunity store unavailable");
      }
      const configuredRepoRoot = String(env.LM_REPO_ROOT || "").trim();
      specialist = (dependencies.createMoneyPrinterSpecialist || createMoneyPrinterSpecialist)({
        dataDir: path.resolve(requiredEnv(env, "LM_DATA_DIR")),
        repoRoot: configuredRepoRoot
          ? path.resolve(configuredRepoRoot)
          : dependencies.repoRoot || path.resolve(__dirname, "../../.."),
        fetchImpl: dependencies.fetchImpl || globalThis.fetch,
        geminiKey,
        runAgentRunner,
        readOpportunity,
        updateOpportunity,
        humanTaskStore: runtimeStore,
      });
    }
    if (typeof specialist !== "function") {
      throw new Error("money printer specialist unavailable");
    }
    servicesByAdapter["general-agent-work"] = {
      runBoundedSpecialist: specialist,
    };
  }
  if (capabilities.includes("money-printer.scout")) {
    const {
      createMoneyPrinterRuntimeStore,
    } = require("../lib/money-printer-runtime-store.js");
    const {
      createMoneyPrinterScout,
    } = require("../lib/money-printer-scout.js");
    const geminiKey = requiredEnv(env, "GEMINI_API_KEY");
    const tenantId = requiredEnv(env, "LM_MONEY_SCOUT_TENANT_ID");
    if (typeof dependencies.query !== "function") {
      throw new Error("money printer scout runtime store unavailable");
    }
    const runtimeStore = createMoneyPrinterRuntimeStore({ query: dependencies.query });
    const configuredRepoRoot = String(env.LM_REPO_ROOT || "").trim();
    const scout = (dependencies.createMoneyPrinterScout || createMoneyPrinterScout)({
      apiKey: geminiKey,
      tenantId,
      dataDir: path.resolve(requiredEnv(env, "LM_DATA_DIR")),
      repoRoot: configuredRepoRoot
        ? path.resolve(configuredRepoRoot)
        : dependencies.repoRoot || path.resolve(__dirname, "../../.."),
      fetchImpl: dependencies.fetchImpl || globalThis.fetch,
      readOpportunityBySource: runtimeStore.readOpportunityBySource,
      createOpportunity: runtimeStore.createOpportunity,
    });
    if (typeof scout !== "function") throw new Error("money printer scout unavailable");
    servicesByAdapter["money-printer-scout"] = { runScout: scout };
  }
  if (capabilities.includes("connector.coverage.refresh")) {
    const factory = dependencies.createConnectorCoverageRuntimeServices || (
      require("../lib/connector-coverage-runtime-services.js")
        .createConnectorCoverageRuntimeServices
    );
    const services = dependencies.connectorCoverageServices || factory(env, {
      query: dependencies.query,
      connect: dependencies.connect,
    });
    if (!services || typeof services !== "object" || Array.isArray(services)) {
      throw new Error("Connector coverage refresh services are unavailable");
    }
    servicesByAdapter["connector-coverage-refresh"] = services;
  }
  if (capabilities.includes("report.financial.telegram")) {
    const secretProvider = createScopedEnvironmentSecretProvider(env);
    const readBalance = dependencies.readBalance || ((walletAddress) => {
      const { readUsdcBalance } = require("../lib/base-usdc-balance.js");
      return readUsdcBalance(walletAddress, {
        rpcUrl: String(env.BASE_RPC_URL || "https://mainnet.base.org"),
        fetchImpl: globalThis.fetch,
      });
    });
    servicesByAdapter["financial-report-telegram"] = {
      secretProvider,
      supaUrl: requiredEnv(env, "SUPABASE_URL"),
      supaKey: requiredEnv(env, "SUPABASE_SERVICE_ROLE_KEY"),
      fetchImpl: globalThis.fetch,
      query: dependencies.query,
      readBalance,
    };
  }
  if (capabilities.includes("marketing.life-manager.daily.publish")) {
    const secretProvider = createScopedEnvironmentSecretProvider(env);
    const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
    const dataDir = path.resolve(requiredEnv(env, "LM_DATA_DIR"));
    const runtimeOwnedPath = (name) => {
      const resolved = path.resolve(requiredEnv(env, name));
      if (resolved !== dataDir && !resolved.startsWith(`${dataDir}${path.sep}`)) {
        throw new Error(`${name} must be beneath LM_DATA_DIR`);
      }
      return resolved;
    };
    servicesByAdapter["marketing-life-manager-daily"] = {
      secretProvider,
      profileProvider: {
        async get(requestTenantId, ref) {
          if (requestTenantId !== tenantId || ref !== "profile://instagram/life-manager") {
            throw new Error("Instagram profile tenant scope mismatch");
          }
          return {
            handle: requiredEnv(env, "LM_INSTAGRAM_HANDLE"),
            accountsPath: runtimeOwnedPath("LM_INSTAGRAM_ACCOUNTS_PATH"),
            settingsPath: runtimeOwnedPath("LM_INSTAGRAM_SETTINGS_PATH"),
            credentialsPath: runtimeOwnedPath("LM_INSTAGRAM_CREDENTIALS_PATH"),
            stateDir: runtimeOwnedPath("LM_INSTAGRAM_PROFILE_STATE_DIR"),
          };
        },
      },
      integrationProvider: {
        async get(requestTenantId, ref) {
          if (
            requestTenantId !== tenantId
            || ref !== "integration://postiz/tiktok/life-manager"
          ) {
            throw new Error("TikTok integration tenant scope mismatch");
          }
          return requiredEnv(env, "LM_TIKTOK_INTEGRATION");
        },
      },
    };
  }
  if (capabilities.includes("marketing.life-manager.daily.generate")) {
    servicesByAdapter["marketing-life-manager-daily-generation"] = {
      dataDir: path.resolve(requiredEnv(env, "LM_DATA_DIR")),
      pythonBin: String(env.PYTHON_BIN || "python3"),
    };
  }
  if (capabilities.includes("marketing.video.generate")) {
    const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
    const query = dependencies.query;
    if (typeof query !== "function") {
      throw new Error("marketing video generation receipt store is unavailable");
    }
    servicesByAdapter["marketing-video-generation"] = {
      dataDir: path.resolve(requiredEnv(env, "LM_DATA_DIR")),
      historyProvider: {
        async list(request) {
          if (
            !request
            || request.tenantId !== tenantId
            || !request.productId
            || !request.formatId
            || !request.locale
          ) {
            throw new Error("marketing video generation history scope mismatch");
          }
          const result = await query(`
            SELECT r.receipt
            FROM public.lm_runtime_job_receipts r
            JOIN public.lm_runtime_jobs j
              ON j.job_id = r.job_id
              AND j.tenant_id = r.tenant_id
            WHERE r.tenant_id = $1
              AND j.capability = 'marketing.video.generate'
              AND r.outcome = 'completed'
              AND r.receipt->>'kind' = 'marketing_video_artifact'
              AND r.receipt->>'product_id' = $2
              AND r.receipt->>'format_id' = $3
              AND r.receipt->>'locale' = $4
            ORDER BY r.created_at ASC
            LIMIT 500
          `, [
            tenantId,
            request.productId,
            request.formatId,
            request.locale,
          ]);
          return result.rows.map((row) => row.receipt);
        },
      },
      now: dependencies.now || (() => new Date().toISOString()),
    };
  }
  if (capabilities.includes("marketing.video.publish")) {
    const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
    const dataDir = path.resolve(requiredEnv(env, "LM_DATA_DIR"));
    const runtimeOwnedPath = (name) => {
      const resolved = path.resolve(requiredEnv(env, name));
      if (resolved !== dataDir && !resolved.startsWith(`${dataDir}${path.sep}`)) {
        throw new Error(`${name} must be beneath LM_DATA_DIR`);
      }
      return resolved;
    };
    const profileRef = requiredEnv(env, "LM_HONNE_EN_INSTAGRAM_PROFILE_REF");
    const integrationRef = requiredEnv(env, "LM_HONNE_EN_TIKTOK_INTEGRATION_REF");
    servicesByAdapter["marketing-video-publication"] = {
      secretProvider: createScopedEnvironmentSecretProvider(env),
      profileProvider: {
        async get(requestTenantId, ref) {
          if (requestTenantId !== tenantId || ref !== profileRef) {
            throw new Error("marketing video publication Instagram profile scope mismatch");
          }
          return {
            handle: requiredEnv(env, "LM_INSTAGRAM_HANDLE"),
            accountsPath: runtimeOwnedPath("LM_INSTAGRAM_ACCOUNTS_PATH"),
            settingsPath: runtimeOwnedPath("LM_INSTAGRAM_SETTINGS_PATH"),
            credentialsPath: runtimeOwnedPath("LM_INSTAGRAM_CREDENTIALS_PATH"),
            stateDir: runtimeOwnedPath("LM_INSTAGRAM_PROFILE_STATE_DIR"),
          };
        },
      },
      integrationProvider: {
        async get(requestTenantId, ref) {
          if (requestTenantId !== tenantId || ref !== integrationRef) {
            throw new Error("marketing video publication TikTok integration scope mismatch");
          }
          return requiredEnv(env, "LM_TIKTOK_INTEGRATION");
        },
      },
    };
  }
  if (capabilities.includes("marketing.liveness.telegram")) {
    servicesByAdapter["marketing-liveness-telegram"] = {
      secretProvider: {
        async get(requestTenantId, ref) {
          if (
            requestTenantId !== requiredEnv(env, "LM_RUNTIME_TENANT_ID")
            || ref !== "secret://telegram/bot-token"
          ) throw new Error("marketing liveness Telegram secret scope mismatch");
          return requiredEnv(env, "LM_TELEGRAM_BOT_TOKEN");
        },
      },
      chatProvider: {
        async get(requestTenantId, ref) {
          if (
            requestTenantId !== requiredEnv(env, "LM_RUNTIME_TENANT_ID")
            || ref !== "telegram-chat://owner"
          ) {
            throw new Error("marketing liveness Telegram chat scope mismatch");
          }
          return requiredEnv(env, "LM_TELEGRAM_ALERT_CHAT_ID");
        },
      },
      now: dependencies.now,
    };
  }
  if (capabilities.includes("marketing.observation.collect")) {
    const tenantId = requiredEnv(env, "LM_RUNTIME_TENANT_ID");
    const query = dependencies.query;
    if (typeof query !== "function") {
      throw new Error("marketing observation receipt store is unavailable");
    }
    const fetchImpl = dependencies.fetchImpl || globalThis.fetch;
    const secretProvider = createScopedEnvironmentSecretProvider(env);
    const {
      normalizePostizMetrics,
    } = require("../lib/marketing-observation-adapter.js");
    const unavailablePlatform = () => ({
      views: { status: "unavailable", value: null, reason: "metric_not_supported" },
      likes: { status: "unavailable", value: null, reason: "metric_not_supported" },
      comments: { status: "unavailable", value: null, reason: "metric_not_supported" },
      shares: { status: "unavailable", value: null, reason: "metric_not_supported" },
    });
    servicesByAdapter["marketing-platform-observation"] = {
      receiptProvider: {
        async get(requestTenantId, ref) {
          const match = /^runtime-receipt:\/\/(marketing-daily:[0-9a-f]{64})$/.exec(
            String(ref || ""),
          );
          if (requestTenantId !== tenantId || !match) {
            throw new Error("marketing observation receipt scope mismatch");
          }
          const rows = (await query(`
            SELECT r.receipt
            FROM public.lm_runtime_job_receipts r
            JOIN public.lm_runtime_jobs j
              ON j.job_id = r.job_id
              AND j.tenant_id = r.tenant_id
            WHERE r.tenant_id = $1
              AND r.job_id = $2
              AND r.outcome = 'completed'
              AND j.capability = 'marketing.life-manager.daily.publish'
            ORDER BY r.attempt DESC
            LIMIT 1
          `, [requestTenantId, match[1]])).rows;
          if (rows.length !== 1) {
            throw new Error("marketing publication receipt is unavailable");
          }
          return rows[0].receipt;
        },
      },
      platformMetricProvider: {
        async collect({ publication, window }) {
          if (publication.provider_route !== "postiz") {
            return unavailablePlatform();
          }
          const token = await secretProvider.get(
            tenantId,
            "secret://postiz/api-key",
          );
          const days = { "2h": 1, "24h": 1, "72h": 3, "7d": 7 }[window];
          const response = await fetchImpl(
            `https://api.postiz.com/public/v1/analytics/post/${
              encodeURIComponent(publication.provider_post_id)
            }?date=${days}`,
            {
              headers: { Authorization: token },
              signal: AbortSignal.timeout(30_000),
            },
          );
          if (!response || response.ok !== true) {
            throw new Error("Postiz metric request failed");
          }
          return normalizePostizMetrics(await response.json());
        },
      },
      productMetricProvider: {
        async collect() {
          const value = {
            status: "unavailable",
            value: null,
            reason: "attribution_not_configured",
          };
          return {
            installs: { ...value },
            activations: { ...value },
            trials: { ...value },
            paid: { ...value },
            proceeds_minor: { ...value },
          };
        },
      },
      now: dependencies.now || (() => new Date().toISOString()),
    };
  }
  if (capabilities.includes("outbound.event.apply")) {
    const { createLumaEvidenceStore } = require("../lib/luma-evidence-store.js");
    const evidenceStore = dependencies.lumaEvidenceStore || createLumaEvidenceStore({
      dataDir: path.resolve(requiredEnv(env, "LM_DATA_DIR")),
    });
    let provider = dependencies.lumaProvider;
    if (!provider) {
      const { chromium } = require("playwright-core");
      const {
        createCloakBrowserDailyDriver,
      } = require("../lib/cloakbrowser-daily-driver.js");
      const lookup = dependencies.lookupHost || dns.promises.lookup;
      const dailyDriver = dependencies.lumaDailyDriver || createCloakBrowserDailyDriver({
        connectOverCDP: dependencies.connectOverCDP
          || ((endpoint) => chromium.connectOverCDP(endpoint)),
        resolveEndpoint: dependencies.resolveCloakEndpoint || (async () => {
          const resolved = await lookup("host.docker.internal", { family: 4 });
          const address = typeof resolved === "string" ? resolved : resolved.address;
          return `http://${address}:9222`;
        }),
      });
      const {
        createReadOnlyLumaSessionAuth,
      } = require("../lib/luma-daily-driver-auth.js");
      const {
        createConnectorEventsPack,
      } = require("../lib/connector-events-pack.js");
      const { readLumaFormProfile } = require("../lib/luma-form-profile.js");
      const auth = dependencies.lumaAuth || createReadOnlyLumaSessionAuth({ dailyDriver });
      const readPrivateLumaFormProfile = dependencies.readPrivateLumaFormProfile || readLumaFormProfile;
      const readTrustedLumaFormProfile = dependencies.readLumaFormProfile || (() => (
        readPrivateLumaFormProfile({
          path: path.join(requiredEnv(env, "LM_DATA_DIR"), "private", "connector-luma-form-profile.json"),
        })
      ));
      const pack = (dependencies.createConnectorEventsPack || createConnectorEventsPack)({
        dailyDriver,
        auth,
        evidenceStore,
        readLumaFormProfile: readTrustedLumaFormProfile,
        now: dependencies.now,
      });
      provider = pack.provider;
    }
    servicesByAdapter["outbound-luma-rsvp"] = {
      provider,
      readExternalReceipt: evidenceStore.readExternalReceipt,
      readArtifact: evidenceStore.readArtifact,
      fetchImpl: dependencies.fetchImpl || globalThis.fetch,
      now: dependencies.now,
    };
  }
  const createRegistry = dependencies.createRegistry || (
    require("../lib/loop-adapter-registry.js").createConfiguredLoopAdapterRegistry
  );
  const registry = createRegistry({ servicesByAdapter });
  if (typeof dependencies.onRegistry === "function") dependencies.onRegistry(registry);
  for (const capability of capabilities) {
    if (!registry.hasCapability(capability)) continue;
    const adapter = registry.getByCapability(capability);
    handlers[capability] = async (job) => {
      const execution = await adapter.execute(job);
      if (capability.startsWith("maritime.manager.") && !execution.continuation && typeof adapter.continuation === "function") {
        try {
          if (!await adapter.verify(execution.receipt, job)) throw new Error("maritime_receipt_invalid");
          const continuation = await adapter.continuation(job, execution.receipt);
          if (continuation) return { ...execution, continuation };
        } catch {
          const error = new Error("maritime_completion_unconfirmed");
          error.code = "MARITIME_COMPLETION_UNCONFIRMED"; error.unknownEffect = true; throw error;
        }
      }
      return execution;
    };
  }
  return handlers;
}

function observeWorkerPoll(state, active, now = () => new Date().toISOString()) {
  const observedAt = String(now());
  if (!Number.isFinite(Date.parse(observedAt))) {
    throw new Error("worker poll timestamp is invalid");
  }
  state.lastPollAt = observedAt;
  return active !== true;
}

async function runCapabilityWorker(env = process.env, runtimeDependencies = {}) {
  const { Pool } = require("pg");
  const runtimeStore = require("../lib/runtime-job-store.js");
  const {
    claimJobs,
    heartbeatJob,
    completeJob,
    completeJobAndEnqueue,
    failJob,
  } = require("../lib/runtime-job-store.js");
  const connectionString = requiredEnv(env, "LM_RUNTIME_DATABASE_URL");
  const capabilities = requiredEnv(env, "LM_WORKER_CAPABILITIES")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (capabilities.length < 1) throw new Error("LM_WORKER_CAPABILITIES is empty");
  const workerId = String(env.LM_WORKER_ID || os.hostname()).trim();
  const pool = new Pool({ connectionString, max: 2 });
  const opts = { query: pool.query.bind(pool), connect: pool.connect.bind(pool) };
  let registry;
  const maritimeManagerDependencies = capabilities.some(value => value.startsWith("maritime.manager."))
    ? createMaritimeManagerWorkerDependencies({ pgPool: pool, env }) : null;
  const maritimeManagerStore = maritimeManagerDependencies?.managerStore || null;
  const capafyCapabilitiesPresent = capabilities.some(value => /^maritime\.manager\.capafy\.(prepare|publish)$/.test(value));
  const capafyConnectionEnabled = env.LM_MARITIME_CAPAFY_CONNECTION_ENABLED === "1";
  const capafyProviderEnabled = env.LM_MARITIME_CAPAFY_PROVIDER_ENABLED === "1";
  if (capafyProviderEnabled && !capafyConnectionEnabled) throw new Error("maritime_capafy_connection_must_be_enabled");
  const maritimeCapafyAccountBinding = capafyCapabilitiesPresent && capafyConnectionEnabled
    ? createMaritimeCapafyAccountBinding({ query: pool.query.bind(pool), managerStore: maritimeManagerStore, env }) : null;
  const maritimeCapafyProvider = capafyProviderEnabled ? Object.freeze({
    ...runtimeDependencies.maritimeCapafyProvider,
    readAccountBinding: maritimeCapafyAccountBinding?.readAccountBinding,
    withAccessToken: maritimeCapafyAccountBinding?.withAccessToken,
  }) : null;
  if (capafyProviderEnabled && !maritimeCapafyHostProviderConfigured(maritimeCapafyProvider)) {
    throw new Error("maritime_capafy_host_executor_unavailable");
  }
  const onJobCompleted = createMaritimeCapafyCompletionObserver({
    onJobCompleted: maritimeManagerDependencies?.onJobCompleted,
    provider: capafyProviderEnabled ? maritimeCapafyProvider : null,
    managerStore: maritimeManagerStore,
    enqueueJob: runtimeStore.enqueueJob,
    storeOptions: opts,
    observe: event => process.stderr.write(JSON.stringify(event) + "\n"),
  });
  let nextMaritimeRecoveryMs = 0;
  let maritimePausedCursor = null;
  let maritimeReconsentCursor = null;
  const handlers = createWorkerHandlers(env, capabilities, {
    maritimeManagerDependencies,
    maritimeManagerStore,
    maritimeCapafyAccountBinding,
    maritimeCapafyProvider,
    onRegistry: value => { registry = value; },
    query: opts.query,
    connect: pool.connect.bind(pool),
  });
  const scoutCycle = capabilities.includes("money-printer.scout")
    ? {
      enqueue: require("../lib/money-printer-scout.js").enqueueMoneyPrinterScoutCycle,
      tenantId: requiredEnv(env, "LM_MONEY_SCOUT_TENANT_ID"),
      intervalMs: env.LM_MONEY_SCOUT_INTERVAL_MS == null || env.LM_MONEY_SCOUT_INTERVAL_MS === ""
        ? undefined : Number(env.LM_MONEY_SCOUT_INTERVAL_MS),
    }
    : null;
  const state = {
    role: "worker",
    workerId,
    capabilities,
    ready: false,
    error: null,
    lastPollAt: null,
  };
  const health = createHealthServer(Number(env.LM_WORKER_HEALTH_PORT || 8790), state);
  const leaseSeconds = Number(env.LM_WORKER_LEASE_SECONDS || 300);
  let active = false;

  async function tick() {
    if (!observeWorkerPoll(state, active)) return;
    active = true;
    try {
      await pool.query("SELECT 1");
      if (scoutCycle) {
        await scoutCycle.enqueue({
          query: opts.query, tenantId: scoutCycle.tenantId, nowMs: Date.now(), intervalMs: scoutCycle.intervalMs,
        });
      }
      if (maritimeManagerStore && Date.now() >= nextMaritimeRecoveryMs) {
        maritimePausedCursor = await recoverMaritimeEnrollments(capabilities, { managerStore: maritimeManagerStore,
          enqueueJob: runtimeStore.enqueueJob, readProvisionJobState: runtimeStore.readRuntimeJobState,
          storeOptions: opts, pausedCursor: maritimePausedCursor });
        maritimeReconsentCursor = await recoverReconsentedMaritimeConfigurations(capabilities, { managerStore: maritimeManagerStore,
          enqueueJob: runtimeStore.enqueueJob, readProvisionJobState: runtimeStore.readRuntimeJobState,
          storeOptions: opts, activeCursor: maritimeReconsentCursor });
        await recoverMaritimeCapafyCycleAdmissions(capabilities, { enabled: capafyProviderEnabled,
          provider: maritimeCapafyProvider, managerStore: maritimeManagerStore, enqueueJob: runtimeStore.enqueueJob,
          query: opts.query, storeOptions: opts,
          observe: event => process.stderr.write(JSON.stringify(event) + "\n") });
        nextMaritimeRecoveryMs = Date.now() + 30000;
      }
      await reconcileMaritimeCapabilityJobs(capabilities, { registry, store: runtimeStore, storeOptions: opts, onJobCompleted,
        observe: event => process.stdout.write(JSON.stringify(event) + "\n") });
      const jobs = await claimJobs({
        workerId,
        capabilities,
        limit: 1,
        leaseSeconds,
      }, opts);
      for (const job of jobs) {
        await executeCapabilityJob(job, {
          workerId,
          handlers,
          heartbeatJob,
          completeJob,
          completeJobAndEnqueue,
          failJob,
          storeOptions: opts,
          leaseSeconds,
          onJobCompleted,
        });
      }
      state.ready = true;
      state.error = null;
      state.lastPollAt = new Date().toISOString();
    } catch (error) {
      state.error = error;
    } finally {
      active = false;
    }
  }

  await tick();
  const timer = setInterval(tick, Number(env.LM_WORKER_POLL_MS || 1000));
  const stop = async () => {
    clearInterval(timer);
    health.close();
    await pool.end();
  };
  process.once("SIGTERM", () => stop().finally(() => process.exit(0)));
  process.once("SIGINT", () => stop().finally(() => process.exit(0)));
}

async function main(argv = process.argv.slice(2)) {
  if (argv.length !== 1 || argv[0] !== "internal-worker") {
    throw new Error("usage: runtime-up.js internal-worker");
  }
  return runCapabilityWorker();
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  createScopedEnvironmentSecretProvider,
  createMaritimeManagerWorkerDependencies,
  createMaritimeCapafyAccountBinding,
  enqueueMaritimeCapafyPrepareAfterCompletion,
  createMaritimeCapafyCompletionObserver,
  recoverMaritimeCapafyCycleAdmissions,
  createWorkerHandlers,
  observeWorkerPoll,
  executeCapabilityJob,
  reconcileMaritimeCapabilityJobs,
  recoverMaritimeEnrollments,
  recoverReconsentedMaritimeConfigurations,
  runCapabilityWorker,
};
