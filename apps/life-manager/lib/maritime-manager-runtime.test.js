'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { buildMaritimeManagerCycleJob, buildMaritimeManagerReportJob, createMaritimeManagerLoopAdapter } = require('./maritime-manager-runtime.js');
const UID = 'lm_11111111-1111-4111-8111-111111111111';
const SHA = 'a'.repeat(40);
const cycle = { tenantId: UID, occurrenceId: 'cycle-1', dateKey: '2026-10-20', releaseSha: SHA };

test('same_occurrence_is_one_runtime_job', () => {
  const first = buildMaritimeManagerCycleJob(cycle);
  assert.deepEqual(buildMaritimeManagerCycleJob(cycle), first);
  assert.notEqual(buildMaritimeManagerCycleJob({ ...cycle, occurrenceId: 'cycle-2' }).job_id, first.job_id);
  assert.notEqual(buildMaritimeManagerCycleJob({ ...cycle, tenantId: 'lm_22222222-2222-4222-8222-222222222222' }).job_id, first.job_id);
  assert.equal(first.effect_class, 'money');
  assert.equal(first.max_attempts, 1);
  assert.equal(first.capability, 'maritime.manager.cycle');
  assert.equal(first.input_refs.enrollment_ref, `maritime-enrollment://${UID}`);
  assert.equal(first.input_refs.date_ref, 'date://2026-10-20');
});

test('date or release updates cannot bypass the existing occurrence effect fence', () => {
  const first = buildMaritimeManagerCycleJob(cycle);
  const changed = buildMaritimeManagerCycleJob({ ...cycle, dateKey: '2026-10-21', releaseSha: 'b'.repeat(40) });
  assert.equal(changed.job_id, first.job_id);
  assert.equal(changed.effect_key, first.effect_key);
  assert.notDeepEqual(changed.input_refs, first.input_refs);
});

test('daily email jobs use a separate tenant and period message fence', () => {
  const input = { tenantId: UID, periodKey: 'maritime:daily:2026-10-20', releaseSha: SHA };
  const first = buildMaritimeManagerReportJob(input);
  assert.deepEqual(buildMaritimeManagerReportJob(input), first);
  assert.notEqual(buildMaritimeManagerReportJob({ ...input, periodKey: 'maritime:daily:2026-10-21' }).job_id, first.job_id);
  assert.equal(first.effect_class, 'message');
  assert.equal(first.max_attempts, 1);
  assert.notEqual(first.effect_key, buildMaritimeManagerCycleJob(cycle).effect_key);
});

test('invalid dates and path-like occurrence ids cannot enter the queue', () => {
  for (const patch of [{ dateKey: '2026-02-30' }, { occurrenceId: '../other-user' }, { releaseSha: 'invalid' }]) {
    assert.throws(() => buildMaritimeManagerCycleJob({ ...cycle, ...patch }), /invalid/);
  }
  assert.throws(() => buildMaritimeManagerReportJob({ tenantId: UID, periodKey: 'maritime:daily:2026-02-30', releaseSha: SHA }), /invalid/);
});

function executionFixture() {
  const enrollment = { uid: UID, agent_id: 'agent-a', release_sha: SHA, status: 'active', paused_at: null };
  let checkpoint = null;
  const calls = [];
  const envelope = { dateKey: cycle.dateKey, releaseSha: SHA, result: { tenantId: UID, occurrenceId: 'cycle-1',
    artifactRefs: ['artifact://original/product.md'], providerSnapshotRef: null, providerReceiptRefs: [],
    nextEligibleAt: null, status: 'completed', errorClass: null } };
  const capturedOutput = JSON.stringify(envelope.result);
  const services = {
    managerStore: {
      read: async () => structuredClone(enrollment),
      readCycleDispatch: async () => checkpoint && structuredClone(checkpoint),
      claimCycleDispatch: async (input) => {
        if (checkpoint) return { claimed: false, row: structuredClone(checkpoint) };
        checkpoint = { uid: input.uid, agent_id: input.agentId, occurrence_id: input.occurrenceId,
          date_key: input.dateKey, release_sha: input.releaseSha, execution_id: null };
        return { claimed: true, row: structuredClone(checkpoint) };
      },
      bindCycleExecution: async (input) => { checkpoint.execution_id = input.executionId; return structuredClone(checkpoint); },
    },
    dispatchCycle: async () => { calls.push('dispatch'); return { executionId: 'exec-1' }; },
    readExecution: async () => { calls.push('read'); return { status: 'completed', exitCode: 0, stdout: capturedOutput }; },
    readCycleReceipt: async () => structuredClone(envelope),
  };
  return { services, calls, enrollment, envelope,
    checkpoint: () => checkpoint, setCheckpoint: (value) => { checkpoint = value; } };
}

test('cycle dispatch persists execution id and replay only reads the same execution', async () => {
  const f = executionFixture();
  const adapter = createMaritimeManagerLoopAdapter(f.services);
  const job = buildMaritimeManagerCycleJob(cycle);
  const first = await adapter.execute(job);
  assert.equal(f.checkpoint().execution_id, 'exec-1');
  assert.equal(first.receipt.status, 'completed');
  assert.equal(adapter.verify(first.receipt, job), true);
  assert.deepEqual(await adapter.execute(job), first);
  assert.equal(f.calls.filter(value => value === 'dispatch').length, 1);
});

test('lost dispatch response remains unknown and cannot dispatch again', async () => {
  const f = executionFixture();
  f.services.dispatchCycle = async () => { f.calls.push('dispatch'); throw new Error('fixture-secret'); };
  const adapter = createMaritimeManagerLoopAdapter(f.services);
  const job = buildMaritimeManagerCycleJob(cycle);
  for (let attempt = 0; attempt < 2; attempt++) {
    await assert.rejects(adapter.execute(job), error => error.unknownEffect === true && !error.message.includes('fixture-secret'));
  }
  assert.equal(f.calls.length, 1);
});

test('paused users cannot start new work but an existing execution still reconciles', async () => {
  const f = executionFixture();
  f.enrollment.status = 'paused'; f.enrollment.paused_at = '2026-10-20T00:00:00Z';
  const adapter = createMaritimeManagerLoopAdapter(f.services);
  const job = buildMaritimeManagerCycleJob(cycle);
  await assert.rejects(adapter.execute(job), /paused/);
  assert.equal(f.calls.length, 0);
  f.setCheckpoint({ uid: UID, agent_id: 'agent-a', occurrence_id: 'cycle-1', date_key: cycle.dateKey, release_sha: SHA, execution_id: 'exec-1' });
  const proof = await adapter.reconcile(job);
  assert.equal(proof.state, 'present');
  assert.equal(f.calls.includes('dispatch'), false);
});

test('known running execution releases the worker after one probe and reconciles read-only', async () => {
  const f = executionFixture();
  let reads = 0;
  f.services.readExecution = async () => { reads++; return { status: 'running' }; };
  const adapter = createMaritimeManagerLoopAdapter(f.services);
  const job = buildMaritimeManagerCycleJob(cycle);
  await assert.rejects(adapter.execute(job), error => error.unknownEffect === true);
  assert.equal(reads, 1);
  assert.deepEqual(await adapter.reconcile(job), { state: 'pending' });
  assert.equal(f.calls.filter(value => value === 'dispatch').length, 1);
});

test('foreign or mismatched cycle receipts never become completed work', async () => {
  for (const patch of [{ dateKey: '2026-10-21' }, { releaseSha: 'b'.repeat(40) },
    { result: { ...executionFixture().envelope.result, tenantId: 'other-user' } },
    { result: { ...executionFixture().envelope.result, artifactRefs: ['artifact://../../private.txt'] } }]) {
    const f = executionFixture(); Object.assign(f.envelope, patch);
    const adapter = createMaritimeManagerLoopAdapter(f.services);
    await assert.rejects(adapter.execute(buildMaritimeManagerCycleJob(cycle)), error => error.unknownEffect === true);
  }
});

test('unconfigured adapter and changed job references never dispatch', async () => {
  const f = executionFixture();
  const job = buildMaritimeManagerCycleJob(cycle);
  await assert.rejects(createMaritimeManagerLoopAdapter({}).execute(job), /unconfigured/);
  await assert.rejects(createMaritimeManagerLoopAdapter(f.services).execute({ ...job,
    input_refs: { ...job.input_refs, enrollment_ref: 'maritime-enrollment://other-user' } }), /invalid/);
  assert.equal(f.calls.length, 0);
});

test('completed cycle is readable through the existing common receipt contract', async () => {
  const f = executionFixture();
  const job = buildMaritimeManagerCycleJob(cycle);
  const { receipt } = await createMaritimeManagerLoopAdapter(f.services).execute(job);
  const { readCommonReceipt } = require('./runtime-job-store.js');
  const common = await readCommonReceipt({ tenantId: UID, jobId: job.job_id, attempt: 1 }, {
    query: async () => ({ rows: [{ ...job, attempt: 1, outcome: 'completed', receipt, created_at: '2026-10-20T12:00:00Z' }] }),
  });
  assert.equal(common.provider, 'maritime');
  assert.equal(common.external_ref, 'maritime-execution://agent-a/exec-1');
  assert.deepEqual(common.evidence_refs, ['maritime-execution://agent-a/exec-1']);
});

test('report cannot echo an unverified receipt status', async () => {
  const f = executionFixture(); const adapter = createMaritimeManagerLoopAdapter(f.services);
  const { receipt } = await adapter.execute(buildMaritimeManagerCycleJob(cycle));
  assert.throws(() => adapter.report({ ...receipt, status: 'fixture-secret-status' }), /invalid/);
  assert.equal(adapter.verify({ ...receipt, tenant_id: 'other-user' }, buildMaritimeManagerCycleJob(cycle)), false);
});

test('unknown execution has a safe diagnostic cursor and never requests another dispatch', async () => {
  const f = executionFixture();
  f.setCheckpoint({ uid: UID, agent_id: 'agent-a', occurrence_id: 'cycle-1', date_key: cycle.dateKey, release_sha: SHA, execution_id: null });
  const proof = await createMaritimeManagerLoopAdapter(f.services).reconcile(buildMaritimeManagerCycleJob(cycle));
  assert.equal(proof.state, 'unknown');
  assert.equal(proof.errorClass, 'maritime_cycle_dispatch_unconfirmed');
  assert.equal(proof.nextAction, 'inspect_provider_execution');
  assert.equal(proof.retryable, false);
  assert.equal(f.calls.length, 0);
});

test('dispatch follows the fixed transport uid contract', async () => {
  const f = executionFixture(); let dispatched;
  f.services.dispatchCycle = async input => { dispatched = input; return { executionId: 'exec-1' }; };
  await createMaritimeManagerLoopAdapter(f.services).execute(buildMaritimeManagerCycleJob(cycle));
  assert.deepEqual(dispatched, { uid: UID, agentId: 'agent-a', occurrenceId: 'cycle-1', dateKey: '2026-10-20', releaseSha: SHA });
});

test('producer Japanese and space-containing artifact references remain recoverable', async () => {
  const f = executionFixture();
  f.envelope.result.artifactRefs = ['artifact://原稿/商品説明.md', 'artifact://original/product spec.md'];
  f.services.readExecution = async () => ({ status: 'completed', exitCode: 0, stdout: JSON.stringify(f.envelope.result) });
  const { receipt } = await createMaritimeManagerLoopAdapter(f.services).execute(buildMaritimeManagerCycleJob(cycle));
  assert.deepEqual(receipt.artifact_refs, ['artifact://原稿/商品説明.md', 'artifact://original/product spec.md']);
});

test('a mutable cycle file cannot override the official captured execution output', async () => {
  const f = executionFixture();
  f.envelope.result.artifactRefs = ['artifact://forged.md'];
  await assert.rejects(createMaritimeManagerLoopAdapter(f.services).execute(buildMaritimeManagerCycleJob(cycle)),
    error => error.unknownEffect === true);
});


test('cycle continuation preserves stable due identity and stops when enrollment pauses', async () => {
  const f = executionFixture();
  const adapter = createMaritimeManagerLoopAdapter(f.services);
  const job = { ...buildMaritimeManagerCycleJob(cycle), available_at: '2026-10-20T23:55:00.000Z' };
  const next = await adapter.continuation(job);
  assert.equal(next.availableAt, '2026-10-21T00:10:00.000Z');
  assert.equal(next.job.input_refs.date_ref, 'date://2026-10-21');
  assert.equal(next.job.input_refs.cycle_ref, `maritime-cycle://${UID}/slot%3A${Date.parse(next.availableAt)}`);
  assert.deepEqual(await adapter.continuation(job), next);
  f.enrollment.status = 'paused';
  assert.equal(await adapter.continuation(job), null);
  f.enrollment.status = 'active'; f.enrollment.paused_at = '2026-10-20T23:59:00.000Z';
  assert.equal(await adapter.continuation(job), null);
  f.enrollment.paused_at = null; f.enrollment.release_sha = 'b'.repeat(40);
  assert.equal(await adapter.continuation(job), null);
});
