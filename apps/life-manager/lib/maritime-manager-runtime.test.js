'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { buildMaritimeManagerCycleJob, buildMaritimeManagerReportJob, createMaritimeManagerLoopAdapter, createMaritimeManagerReportAdapter, createMaritimeManagerProvisionAdapter, buildMaritimeManagerProvisionJob } = require('./maritime-manager-runtime.js');
const { MANAGER_CONSENT_VERSION } = require('./maritime-distribution.js');
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
  const enrollment = { uid: UID, agent_id: 'agent-a', release_sha: SHA, status: 'active', consent_version: MANAGER_CONSENT_VERSION, paused_at: null };
  let checkpoint = null;
  const calls = [];
  const envelope = { dateKey: cycle.dateKey, releaseSha: SHA, result: { tenantId: UID, occurrenceId: 'cycle-1',
    artifactRefs: ['artifact://original/product.md'], providerSnapshotRef: null, providerReceiptRefs: [],
    nextEligibleAt: null, status: 'completed', errorClass: null } };
  const capturedOutput = JSON.stringify(envelope.result);
  const services = {
    withControlLock: async (_uid, operation) => operation(),
    managerStore: {
      read: async () => structuredClone(enrollment),
      readCycleDispatch: async (input) => checkpoint
        && checkpoint.uid === input.uid && checkpoint.agent_id === input.agentId
        && checkpoint.occurrence_id === input.occurrenceId && checkpoint.date_key === input.dateKey
        && checkpoint.release_sha === input.releaseSha ? structuredClone(checkpoint) : null,
      claimCycleDispatch: async (input) => {
        if (checkpoint) return { claimed: false, row: structuredClone(checkpoint) };
        checkpoint = { uid: input.uid, agent_id: input.agentId, occurrence_id: input.occurrenceId,
          date_key: input.dateKey, release_sha: input.releaseSha, execution_id: null };
        return { claimed: true, row: structuredClone(checkpoint) };
      },
      bindCycleExecution: async (input) => { checkpoint.execution_id = input.executionId; return structuredClone(checkpoint); },
    },
    prepareCycle: async () => ({ready:true}),
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

test('outdated consent blocks new Capafy work and result email without dispatching', async () => {
  const f = executionFixture();
  f.enrollment.consent_version = 'maritime-manager-v1';
  const cycleAdapter = createMaritimeManagerLoopAdapter(f.services);
  const cycleJob = buildMaritimeManagerCycleJob(cycle);
  await assert.rejects(cycleAdapter.execute(cycleJob), /consent_required/);
  assert.equal(f.calls.length, 0);
  assert.equal(await cycleAdapter.continuation(cycleJob), null);

  let sends = 0;
  const reportAdapter = createMaritimeManagerReportAdapter({ managerStore: { read: async () => f.enrollment },
    readDailyObservations: async () => ({ actionReceipts: [], financialRecords: [] }),
    deliverDailyResult: async () => { sends++; return { status: 'sent' }; } });
  const reportJob = buildMaritimeManagerReportJob({ tenantId: UID, releaseSha: SHA, periodKey: 'maritime:daily:2026-10-20' });
  await assert.rejects(reportAdapter.execute(reportJob), /inactive/);
  assert.equal(await reportAdapter.continuation(reportJob), null);
  assert.equal(sends, 0);
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


test('daily report adapter sends through existing delivery and reconciles without sending again', async () => {
  const enrollment = { uid: UID, release_sha: SHA, status: 'active', consent_version: MANAGER_CONSENT_VERSION, paused_at: null, timezone: 'America/New_York' };
  const job = { ...buildMaritimeManagerReportJob({ tenantId: UID, releaseSha: SHA, periodKey: 'maritime:daily:2026-10-31' }), available_at: '2026-10-31T23:00:00.000Z' };
  let sends = 0, stored = null;
  const adapter = createMaritimeManagerReportAdapter({
    managerStore: { read: async () => enrollment },
    readDailyObservations: async input => { assert.equal(input.uid, UID); return { actionReceipts: [], financialRecords: [] }; },
    deliverDailyResult: async ({ result }) => {
      sends++;
      assert.equal(result.financial.profit, null);
      stored = { uid: UID, period_key: result.periodKey, status: 'sent', channel: 'email',
        provider_message_id: 'email-a', recipient_hash: 'b'.repeat(64), message: 'frozen report', sent_at: '2026-10-31T23:00:01.000Z' };
      return { status: 'sent', providerMessageId: stored.provider_message_id, recipientHash: stored.recipient_hash,
        snapshotHash: require('node:crypto').createHash('sha256').update(stored.message).digest('hex'), sentAt: stored.sent_at };
    },
    readReportDelivery: async () => stored,
    now: () => '2026-10-31T23:00:01.000Z',
  });
  const missing = await adapter.reconcile(job);
  assert.equal(missing.state, 'unknown');
  const { receipt } = await adapter.execute(job);
  assert.equal(adapter.verify(receipt, job), true);
  assert.equal((await adapter.reconcile(job)).state, 'present');
  assert.equal(sends, 1);
  const next = await adapter.continuation(job);
  assert.equal(next.availableAt, '2026-11-02T00:00:00.000Z');
  assert.equal(next.job.input_refs.period_ref, 'maritime-period://maritime%3Adaily%3A2026-11-01');
  stored.status = 'pending'; stored.provider_message_id = null;
  assert.equal((await adapter.reconcile(job)).state, 'unknown');
  assert.equal(sends, 1);
  enrollment.status = 'paused';
  assert.equal(await adapter.continuation(job), null);
  await assert.rejects(() => adapter.execute(job), /inactive/);
  assert.equal(sends, 1);
});


test('provision create and configure are separate stable jobs with read-only reconciliation',async()=>{
 const row={uid:UID,agent_id:'agent-a',release_sha:SHA,status:'active',consent_version:MANAGER_CONSENT_VERSION,paused_at:null,created_at:'2026-10-21T00:00:00.000Z',timezone:'Asia/Tokyo'};
 const calls=[];let status='deploying',ready=false,schedules=[];
 const services={withControlLock:async(_uid,operation)=>operation(),managerStore:{read:async()=>row},
  ensureAgent:async()=>{calls.push('create');return {agentId:'agent-a',status};},
  readAgent:async()=>{calls.push('readAgent');return {agentId:'agent-a',status};},
  writeScheduleSnapshot:async input=>{calls.push('schedule');schedules=input.snapshot.schedules;},
  configureWake:async()=>{calls.push('configure');ready=true;},
  readWakeConfiguration:async()=>{calls.push('readWake');return {ready,schedules};},
  seedInitialReport:async plan=>{calls.push('seedReport');assert.equal(plan.job.capability,'maritime.manager.report');},
  provisionSource:()=>({uploadS3Key:'uploads/fixture.zip',archiveSha256:'b'.repeat(64)}),
 };
 const adapter=createMaritimeManagerProvisionAdapter(services);
 const create={...buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA}),available_at:row.created_at};
 await assert.rejects(()=>adapter.execute(create),error=>error.code==='MARITIME_PROVISION_PENDING'&&error.unknownEffect);
 assert.equal((await adapter.reconcile(create)).state,'pending');
 assert.equal(calls.filter(x=>x==='create').length,1);
 status='active';const created=await adapter.reconcile(create);assert.equal(created.state,'present');
 const configure=await adapter.continuation(create,created.receipt);
 assert.notEqual(configure.job.job_id,create.job_id);
 const job={...configure.job,available_at:configure.availableAt};
 const {receipt}=await adapter.execute(job);
 assert.equal(adapter.verify(receipt,job),true);
 const before=calls.filter(x=>['create','configure','schedule'].includes(x)).length;
 assert.equal((await adapter.reconcile(job)).state,'present');
 assert.equal(calls.filter(x=>['create','configure','schedule'].includes(x)).length,before);
 const first=await adapter.continuation(job,receipt);
 assert.equal(first.job.capability,'maritime.manager.cycle');assert.equal(calls.includes('seedReport'),true);
 ready=false;assert.equal((await adapter.reconcile(job)).state,'unknown');ready=true;
 row.status='paused';assert.equal(await adapter.continuation(job,receipt),null);
 await assert.rejects(()=>adapter.execute(job),/inactive/);
});

test('consent recovery provision jobs are anchored and preserve their stable identity across phases',async()=>{
 const resumeAt='2026-10-26T02:00:00.000Z';
 const base=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA});
 const create=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,resumeAt});
 const configure=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'configure',resumeAt});
 assert.notEqual(create.job_id,base.job_id);assert.notEqual(create.effect_key,base.effect_key);
 assert.equal(create.input_refs.provision_resume_ref,`maritime-provision-resume://${encodeURIComponent(resumeAt)}`);
 assert.equal(configure.job_id,buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'configure',resumeAt}).job_id);
 const row={uid:UID,agent_id:'agent-a',release_sha:SHA,status:'active',consent_version:MANAGER_CONSENT_VERSION,
  consent_v2_at:resumeAt,paused_at:null,created_at:'2026-10-21T00:00:00.000Z',timezone:'UTC'};
 const adapter=createMaritimeManagerProvisionAdapter({managerStore:{read:async()=>row},readAgent:async()=>({agentId:'agent-a',status:'active'}),
  provisionSource:()=>({uploadS3Key:'uploads/fixture.zip',archiveSha256:'b'.repeat(64)})});
 const proof=await adapter.reconcile({...create,available_at:row.created_at});assert.equal(proof.state,'present');
 const next=await adapter.continuation({...create,available_at:row.created_at},proof.receipt);
 assert.equal(next.job.job_id,configure.job_id);assert.equal(next.job.input_refs.provision_resume_ref,create.input_refs.provision_resume_ref);
});

test('reconsented configure continuation seeds the persisted resume occurrence instead of the old enrollment date',async()=>{
 const resumeAt='2026-10-26T02:00:00.000Z';
 const row={uid:UID,agent_id:'agent-a',release_sha:SHA,status:'active',consent_version:MANAGER_CONSENT_VERSION,
  consent_v2_at:resumeAt,paused_at:null,created_at:'2026-09-01T00:00:00.000Z',timezone:'UTC'};
 let ready=false,schedules=[],seededReport=null;
 const adapter=createMaritimeManagerProvisionAdapter({managerStore:{read:async()=>row},withControlLock:async(_uid,operation)=>operation(),
  writeScheduleSnapshot:async input=>{schedules=input.snapshot.schedules;},configureWake:async()=>{ready=true;},
  readWakeConfiguration:async()=>({ready,schedules}),seedInitialReport:async plan=>{seededReport=plan;}});
 const job={...buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'configure',resumeAt}),available_at:resumeAt};
 const {receipt}=await adapter.execute(job);const next=await adapter.continuation(job,receipt);
 const expected=require('./maritime-manager-wake.js').buildMaritimeReconsentJobs(row);
 assert.equal(require('./maritime-manager-runtime.js').readMaritimeCycleContract(next.job).occurrenceId,'consent-v2-resume');
 assert.equal(next.job.job_id,expected.cycle.job.job_id);assert.equal(next.availableAt,expected.cycle.availableAt);
 assert.deepEqual(seededReport,expected.report);
});


test('first configure readback failure happens after settings and recovers read-only',async()=>{
 const row={uid:UID,agent_id:'agent-a',release_sha:SHA,status:'active',consent_version:MANAGER_CONSENT_VERSION,paused_at:null,created_at:'2026-10-21T00:00:00.000Z',timezone:'UTC'};
 let writes=0,reloads=0,reads=0,schedules=[];
 const adapter=createMaritimeManagerProvisionAdapter({withControlLock:async(_uid,operation)=>operation(),managerStore:{read:async()=>row},
  writeScheduleSnapshot:async input=>{writes++;schedules=input.snapshot.schedules;},configureWake:async()=>{reloads++;},
  readWakeConfiguration:async()=>{if(++reads===1)throw new Error('temporary read failure');return {ready:reloads>0,schedules};},seedInitialReport:async()=>{},
 });
 const job={...buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'configure'}),available_at:row.created_at};
 await assert.rejects(()=>adapter.execute(job),error=>error.unknownEffect===true);
 assert.equal(writes,1);assert.equal(reloads,1);
 const proof=await adapter.reconcile(job);assert.equal(proof.state,'present');
 assert.equal((await adapter.continuation(job,proof.receipt)).job.capability,'maritime.manager.cycle');
 assert.equal(writes,1);assert.equal(reloads,1);
});


test('guest readiness is checked before the irreversible cycle dispatch claim',async()=>{
 const f=executionFixture();let prepared=0;
 f.services.prepareCycle=async input=>{prepared++;assert.equal(input.uid,UID);assert.equal(f.checkpoint(),null);return {ready:false};};
 const adapter=createMaritimeManagerLoopAdapter(f.services),job=buildMaritimeManagerCycleJob(cycle);
 const deferred=await adapter.execute(job);assert.equal(deferred.receipt.status,'deferred');assert.equal(deferred.receipt.error_class,'cloud_runtime_not_ready');assert.equal(adapter.verify(deferred.receipt,job),true);
 assert.equal(prepared,1);assert.equal(f.checkpoint(),null);assert.equal(f.calls.filter(x=>x==='dispatch').length,0);
});


test('transient preflight defers through the existing worker without consuming a dispatch claim',async()=>{
 const f=executionFixture();f.services.prepareCycle=async()=>{throw new Error('temporary guest unavailable');};
 f.services.now=()=> '2026-10-21T01:00:00.000Z';
 const job={...buildMaritimeManagerCycleJob(cycle),available_at:'2026-10-20T00:00:00.000Z',attempt:1};
 const adapter=createMaritimeManagerLoopAdapter(f.services);
 const execution=await adapter.execute(job);
 assert.equal(execution.receipt.status,'deferred');assert.equal(execution.receipt.error_class,'cloud_runtime_not_ready');
 assert.equal(execution.receipt.provider,'runtime');assert.equal(execution.receipt.execution_id,null);
 assert.equal(adapter.verify(execution.receipt,job),true);
 const next=await adapter.continuation(job,execution.receipt);assert.equal(next.availableAt,'2026-10-21T01:15:00.000Z');
 assert.equal(f.checkpoint(),null);assert.equal(f.calls.filter(x=>x==='dispatch').length,0);
 let completed=0;
 await require('../scripts/runtime-up.js').executeCapabilityJob(job,{workerId:'worker-a',
  handlers:{[job.capability]:async()=>({...execution,continuation:next})},
  completeJobAndEnqueue:async input=>{assert.equal(input.nextJob.job_id,next.job.job_id);completed++;},
  failJob:async()=>{throw new Error('preflight must not dead-letter');},
 });
 assert.equal(completed,1);
 const report=require('./maritime-manager-report.js').buildMaritimeDailyResult({enrollment:{uid:UID,timezone:'UTC'},periodKey:'maritime:daily:2026-10-21',actionReceipts:[{receipt:execution.receipt,completedAt:'2026-10-21T01:00:00.000Z'}]});
 assert.equal(report.actions.deferredCycles,1);assert.equal(report.actions.completedCycles,0);
 assert.match(require('./maritime-manager-report.js').renderMaritimeDailyEmail(report),/実行環境の準備待ち/);
});


test('pause cleanup revokes consent and clears schedules while retaining inflight data and no successors',async()=>{
 for(const bound of [true,false]){
  const row={uid:UID,agent_id:bound?'agent-a':null,release_sha:SHA,status:'paused',paused_at:'2026-10-21T00:00:00.000Z'};
  let revoked=false,revokeCalls=0,writes=0,schedules=[{id:'old'}];
  const adapter=createMaritimeManagerProvisionAdapter({withControlLock:async(_uid,operation)=>operation(),managerStore:{read:async()=>row,listRecentCycleDispatches:async()=>[]},
   isConsentRevoked:async()=>revoked,revokeConsent:async()=>{revoked=true;revokeCalls++;},
   writeScheduleSnapshot:async input=>{assert.equal(input.snapshot.paused,true);assert.deepEqual(input.snapshot.schedules,[]);writes++;schedules=[];},
   readWakeConfiguration:async()=>({ready:true,schedules}),
   ensureAgent:()=>{throw new Error('no provision');},configureWake:()=>{throw new Error('no configure');},seedInitialReport:()=>{throw new Error('no report');},
  });
  const job=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'pause'});
  const proof=await adapter.reconcile(job);assert.equal(proof.state,'present');assert.equal(adapter.verify(proof.receipt,job),true);
  assert.equal(revokeCalls,1);assert.equal(writes,bound?1:0);assert.equal(await adapter.continuation(job,proof.receipt),null);
  await adapter.reconcile(job);assert.equal(revokeCalls,1);assert.equal(writes,bound?1:0);
  assert.equal(row.agent_id,bound?'agent-a':null);
 }
});

test('pause cleanup cancels recent tenant executions and confirms the terminal provider readback',async()=>{
 const row={uid:UID,agent_id:'agent-a',release_sha:SHA,status:'paused',paused_at:'2026-10-21T00:00:00.000Z'};
 let revoked=false,schedules=[{id:'old'}],cancelled=[];
 const dispatches=[
  {uid:UID,agent_id:'agent-a',release_sha:SHA,occurrence_id:'cycle-queued',date_key:'2026-10-21',execution_id:'exec-queued'},
  {uid:UID,agent_id:'agent-a',release_sha:SHA,occurrence_id:'cycle-pending',date_key:'2026-10-21',execution_id:'exec-pending'},
  {uid:UID,agent_id:'agent-a',release_sha:SHA,occurrence_id:'cycle-running',date_key:'2026-10-21',execution_id:'exec-running'},
  {uid:UID,agent_id:'agent-a',release_sha:SHA,occurrence_id:'cycle-completed',date_key:'2026-10-21',execution_id:'exec-completed'},
 ];
 const initialStatus={'exec-queued':'queued','exec-pending':'pending','exec-running':'running','exec-completed':'completed'};
 const adapter=createMaritimeManagerProvisionAdapter({withControlLock:async(_uid,operation)=>operation(),
  managerStore:{read:async()=>row,listRecentCycleDispatches:async input=>{assert.deepEqual(input,{uid:UID,agentId:'agent-a',releaseSha:SHA});return dispatches;}},
  isConsentRevoked:async()=>revoked,revokeConsent:async()=>{revoked=true;},
  writeScheduleSnapshot:async input=>{assert.deepEqual(input.snapshot.schedules,[]);schedules=[];},
  readWakeConfiguration:async()=>({ready:true,schedules}),
  readExecution:async input=>({executionId:input.executionId,status:cancelled.includes(input.executionId)?'cancelled':initialStatus[input.executionId],exitCode:0}),
  cancelExecution:async input=>{cancelled.push(input.executionId);return {executionId:input.executionId,status:'cancelled',exitCode:-1};},
 });
 const job=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'pause'});
 const proof=await adapter.reconcile(job);
 assert.equal(proof.state,'present');assert.equal(adapter.verify(proof.receipt,job),true);
 assert.equal(proof.receipt.checked_execution_count,4);
 assert.match(proof.receipt.execution_status_sha256,/^[0-9a-f]{64}$/);
 assert.deepEqual(cancelled,['exec-queued','exec-pending','exec-running']);
 assert.equal((await adapter.reconcile(job)).state,'present');
 assert.deepEqual(cancelled,['exec-queued','exec-pending','exec-running']);
});

test('pause cleanup remains unconfirmed while an execution survives provider cancellation',async()=>{
 const row={uid:UID,agent_id:'agent-a',release_sha:SHA,status:'paused',paused_at:'2026-10-21T00:00:00.000Z'};
 let revoked=false,schedules=[{id:'old'}];
 const adapter=createMaritimeManagerProvisionAdapter({withControlLock:async(_uid,operation)=>operation(),
  managerStore:{read:async()=>row,listRecentCycleDispatches:async()=>[{uid:UID,agent_id:'agent-a',release_sha:SHA,
   occurrence_id:'cycle-running',date_key:'2026-10-21',execution_id:'exec-running'}]},
  isConsentRevoked:async()=>revoked,revokeConsent:async()=>{revoked=true;},
  writeScheduleSnapshot:async()=>{schedules=[];},readWakeConfiguration:async()=>({ready:true,schedules}),
  readExecution:async()=>({status:'running'}),
  cancelExecution:async input=>({executionId:input.executionId,status:'running'}),
 });
 const job=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'pause'});
 const proof=await adapter.reconcile(job);
 assert.equal(proof.state,'unknown');assert.equal(proof.retryable,false);
 assert.equal(proof.errorClass,'maritime_pause_cleanup_unconfirmed');
});


function controlMutex(){let tail=Promise.resolve();return async(_uid,operation)=>{const previous=tail;let release;tail=new Promise(resolve=>{release=resolve;});await previous;try{return await operation();}finally{release();}};}
test('Stop serializes with a dispatch in flight and cancels its persisted execution before confirming pause',async()=>{
 const f=executionFixture(),lock=controlMutex();f.services.withControlLock=lock;
 let enterDispatch,releaseDispatch,cancelled=false,revoked=false,schedules=[];
 const entered=new Promise(resolve=>{enterDispatch=resolve;}),gate=new Promise(resolve=>{releaseDispatch=resolve;});
 f.services.dispatchCycle=async()=>{enterDispatch();await gate;return {executionId:'exec-1'};};
 f.services.managerStore.listRecentCycleDispatches=async({uid,agentId,releaseSha})=>{
  assert.deepEqual({uid,agentId,releaseSha},{uid:UID,agentId:'agent-a',releaseSha:SHA});
  const row=f.checkpoint();return row?[{uid,agent_id:agentId,release_sha:releaseSha,occurrence_id:row.occurrence_id,
    date_key:row.date_key,execution_id:row.execution_id}]:[];
 };
 f.services.readExecution=async({executionId})=>({executionId,status:cancelled?'cancelled':'running',exitCode:cancelled?-1:undefined});
 f.services.cancelExecution=async({executionId})=>{cancelled=true;return {executionId,status:'cancelled',exitCode:-1};};
 const cycleAdapter=createMaritimeManagerLoopAdapter(f.services),cycleJob=buildMaritimeManagerCycleJob(cycle);
 const cycleExecution=cycleAdapter.execute(cycleJob).catch(error=>error);
 await entered;
 f.enrollment.status='paused';f.enrollment.paused_at='2026-10-25T21:00:00.000Z';
 const provisionAdapter=createMaritimeManagerProvisionAdapter({withControlLock:lock,
  managerStore:{read:async()=>f.enrollment,listRecentCycleDispatches:f.services.managerStore.listRecentCycleDispatches},
  isConsentRevoked:async()=>revoked,revokeConsent:async()=>{revoked=true;},
  writeScheduleSnapshot:async input=>{assert.deepEqual(input.snapshot.schedules,[]);schedules=[];},
  readWakeConfiguration:async()=>({ready:true,schedules}),
  readExecution:f.services.readExecution,cancelExecution:f.services.cancelExecution,
 });
 const pauseJob=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'pause'});
 const cleanup=provisionAdapter.reconcile(pauseJob);
 const early=await Promise.race([cleanup.then(()=>true),new Promise(resolve=>setTimeout(()=>resolve(false),15))]);
 assert.equal(early,false,'pause waits until the in-flight dispatch has an immutable execution id');
 releaseDispatch();
 const cycleError=await cycleExecution;
 assert.match(cycleError.message,/pending/);
 const proof=await cleanup;
 assert.equal(proof.state,'present');assert.equal(provisionAdapter.verify(proof.receipt,pauseJob),true);
 assert.equal(proof.receipt.checked_execution_count,1);assert.equal(cancelled,true);
 const next=await cycleAdapter.continuation({...cycleJob,available_at:'2026-10-25T21:00:00.000Z'});
 assert.equal(next,null);
 await assert.rejects(cycleAdapter.execute(buildMaritimeManagerCycleJob({...cycle,occurrenceId:'cycle-after-stop'})),/paused/);
});

test('pause final confirmation waits for the older configure writer before clearing schedules',async()=>{
 const row={uid:UID,agent_id:'agent-a',release_sha:SHA,status:'active',consent_version:MANAGER_CONSENT_VERSION,paused_at:null,created_at:'2026-10-21T00:00:00.000Z',timezone:'UTC'};
 let enter,release;const entered=new Promise(resolve=>{enter=resolve;}),gate=new Promise(resolve=>{release=resolve;});let schedules=[],revoked=false;
 const adapter=createMaritimeManagerProvisionAdapter({managerStore:{read:async()=>structuredClone(row),listRecentCycleDispatches:async()=>[]},withControlLock:controlMutex(),
  writeScheduleSnapshot:async input=>{if(!input.snapshot.paused){enter();await gate;}schedules=input.snapshot.schedules;},
  configureWake:async()=>{},readWakeConfiguration:async()=>({ready:true,schedules}),isConsentRevoked:async()=>revoked,revokeConsent:async()=>{revoked=true;},
 });
 const configure=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'configure'});
 const execution=adapter.execute(configure).catch(()=>null);await entered;
 row.status='paused';row.paused_at='2026-10-21T00:00:01.000Z';
 const pause=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'pause'});
 const cleanup=adapter.reconcile(pause);const early=await Promise.race([cleanup.then(()=>true),new Promise(resolve=>setTimeout(()=>resolve(false),15))]);release();await execution;
 const proof=await cleanup;assert.equal(early,false);assert.equal(proof.state,'present');assert.deepEqual(schedules,[]);assert.equal(revoked,true);
});

test('paused accepted provision still reads the official result without creating a successor',async()=>{
 const row={uid:UID,agent_id:null,release_sha:SHA,status:'provisioning',consent_version:MANAGER_CONSENT_VERSION,paused_at:null,created_at:'2026-10-21T00:00:00.000Z',timezone:'UTC'};let reads=0,creates=0,status='deploying';
 const adapter=createMaritimeManagerProvisionAdapter({managerStore:{read:async()=>row},provisionSource:()=>({uploadS3Key:'uploads/fixture.zip',archiveSha256:'b'.repeat(64)}),ensureAgent:async()=>{creates++;},
 readAgent:async()=>{reads++;if(status==='active')row.agent_id='agent-a';return {agentId:'agent-a',status};}});
 const job=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA});await assert.rejects(()=>adapter.execute(job),/pending/);
 row.status='paused';row.paused_at='2026-10-21T00:00:01.000Z';status='active';const before=reads;
 const proof=await adapter.reconcile(job);assert.equal(proof.state,'present');assert.equal(reads,before+1);assert.equal(creates,1);assert.equal(await adapter.continuation(job,proof.receipt),null);
 let loaded=0;const configured=createMaritimeManagerProvisionAdapter({managerStore:{read:async()=>row},readWakeConfiguration:async()=>{loaded++;return {ready:true,schedules:[]};}});
 const configJob=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'configure'});const configProof=await configured.reconcile(configJob);
 assert.equal(configProof.state,'present');assert.equal(loaded,1);assert.equal(await configured.continuation(configJob,configProof.receipt),null);
 await assert.rejects(()=>configured.execute(configJob),/inactive/);assert.equal(loaded,1);
});

test('stale-consent provision jobs allow read-only provider reconciliation but cannot repeat create effects',async()=>{
 const row={uid:UID,agent_id:null,release_sha:SHA,status:'provisioning',consent_version:'maritime-manager-v1',paused_at:null,
  created_at:'2026-10-21T00:00:00.000Z',timezone:'UTC'};let reads=0,creates=0;
 const adapter=createMaritimeManagerProvisionAdapter({managerStore:{read:async()=>row},
  provisionSource:()=>({uploadS3Key:'uploads/fixture.zip',archiveSha256:'b'.repeat(64)}),
  ensureAgent:async()=>{creates++;},readAgent:async()=>{reads++;return {agentId:'agent-a',status:'active'};}});
 const job=buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA});
 await assert.rejects(()=>adapter.execute(job),/consent_required/);assert.equal(creates,0);
 const proof=await adapter.reconcile(job);assert.equal(proof.state,'present');assert.equal(adapter.verify(proof.receipt,job),true);
 assert.equal(reads,1);assert.equal(creates,0);
});
