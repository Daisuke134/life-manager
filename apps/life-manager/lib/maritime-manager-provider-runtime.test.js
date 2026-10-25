"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { buildMaritimeManagerCycleJob } = require("./maritime-manager-runtime.js");
const runtime = () => require("./maritime-manager-provider-runtime.js");
const UID = "lm_11111111-1111-4111-8111-111111111111";
const SHA = "a".repeat(40);
function fixture() {
  const cycle = {...buildMaritimeManagerCycleJob({tenantId:UID,releaseSha:SHA,occurrenceId:"first",dateKey:"2026-10-23"}),status:"completed"};
  const cycleRef="maritime-execution://vm-1/exec-1";
  const cycleReceipt={schema_version:1,kind:"maritime_manager_cycle",tenant_id:UID,job_id:cycle.job_id,
    occurrence_id:"first",date_key:"2026-10-23",release_sha:SHA,agent_id:"vm-1",execution_id:"exec-1",
    status:"completed",artifact_refs:["artifact://original/listing.md"],error_class:null,provider:"maritime",
    external_ref:cycleRef,evidence_refs:[cycleRef]};
  const args={tenantId:UID,releaseSha:SHA,occurrenceId:"first",cycleJobId:cycle.job_id,
    artifactRef:cycleReceipt.artifact_refs[0],accountRef:`account://capafy/${UID}/seller-1`};
  const prepare={...runtime().buildMaritimeCapafyPrepareJob(args),attempt:1,status:"running"};
  const prepareReceipt=receipt(prepare,"prepared",{agent_id:"123",agent_version_id:"456"});
  const publish={...runtime().buildMaritimeCapafyPublishJob({...args,sourceCycleJobId:cycle.job_id,
    prepareJobId:prepare.job_id,agentId:"123",agentVersionId:"456"}),attempt:1,status:"running"};
  const publishReceipt=receipt(publish,"under_review");
  let prepares=0,publishes=0;
  const proof = r => ({state:"present",receipt:r});
  const provider={
    readAccountBinding:async ({tenantId,accountRef})=>({provider:"capafy",tenantId,accountRef,
      providerSubject:"019d3c7f-fe51-7c57-aa2e-8e1055bb36a5",autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
    withAccessToken:async ({tenantId,accountRef},operation)=>operation("am_sk_"+"t".repeat(32),
      {provider:"capafy",tenantId,accountRef,providerSubject:"019d3c7f-fe51-7c57-aa2e-8e1055bb36a5",
        autonomyConsentVersion:"maritime-capafy-autonomy-v1"}),
    guardArtifact:async ()=>({original:true,frozen:false,duplicate:false}),
    prepare:async ()=>{prepares++;},publish:async ()=>{publishes++;},
    readPrepare:async ()=>proof(prepareReceipt),readPublish:async ()=>proof(publishReceipt),
  };
  const services={managerStore:{read:async()=>({uid:UID,release_sha:SHA,status:"active",paused_at:null})},
    readCompletedCycle:async()=>({job:cycle,receipt:cycleReceipt}),
    readPrepareReceipt:async()=>({job:{...prepare,status:"completed"},receipt:prepareReceipt}),
    provider,now:()=>"2026-10-23T12:00:00.000Z"};
  return {cycle,cycleReceipt,args,prepare,prepareReceipt,publish,publishReceipt,provider,services,
    counts:()=>({prepares,publishes})};
}
function receipt(job,status,extra={}) {
  const ref=`capafy-action://${job.job_id}/1`;
  return {schema_version:1,kind:job.capability.endsWith(".prepare")?"maritime_capafy_prepare":"provider_action_receipt",
    tenant_id:job.tenant_id,job_id:job.job_id,attempt:1,effect_key:job.effect_key,provider:"capafy",
    ...job.input_refs,...extra,status,url:"https://capafy.ai/agents/123",
    external_ref:ref,evidence_refs:[ref],observed_at:"2026-10-23T12:00:00.000Z"};
}
test("provider jobs carry the exact immutable source chain and stable single-attempt effect",()=>{
  assert.doesNotThrow(()=>runtime());
  const f=fixture();
  assert.deepEqual(Object.keys(f.prepare.input_refs).sort(),["account_ref","artifact_ref","occurrence_id","release_ref","source_cycle_job_id"]);
  assert.deepEqual(Object.keys(f.publish.input_refs).sort(),["account_ref","agent_id","agent_version_id","artifact_ref","occurrence_id","prepare_job_id","release_ref","source_cycle_job_id"]);
  assert.equal(f.publish.effect_key,`maritime-capafy-publish://${UID}/first`);
  assert.equal(f.publish.max_attempts,1);assert.equal(f.publish.effect_class,"publish");
  assert.equal(runtime().buildMaritimeCapafyPrepareJob({...f.args,releaseSha:"b".repeat(40)}).job_id,f.prepare.job_id);
});
test("trusted cycle, prepare and publish receipts reject every mismatched chain identity",()=>{
  const f=fixture(),r=runtime();
  assert.equal(r.verifyMaritimeCapafyPrepareReceipt(f.prepareReceipt,f.prepare,f.cycle,f.cycleReceipt),true);
  assert.equal(r.verifyMaritimeCapafyPublishReceipt(f.publishReceipt,f.publish,f.services?{...f.prepare,status:"completed"}:null,f.prepareReceipt,f.cycle,f.cycleReceipt),true);
  for(const key of ["source_cycle_job_id","artifact_ref","account_ref","occurrence_id","release_ref","agent_id","agent_version_id","job_id","effect_key"]){
    const bad={...f.publishReceipt,[key]:"other"};
    assert.equal(r.verifyMaritimeCapafyPublishReceipt(bad,f.publish,{...f.prepare,status:"completed"},f.prepareReceipt,f.cycle,f.cycleReceipt),false,key);
  }
  assert.equal(r.verifyMaritimeCapafyPublishReceipt({...f.publishReceipt,attempt:2},f.publish,{...f.prepare,status:"completed"},f.prepareReceipt,f.cycle,f.cycleReceipt),false);
  assert.equal(r.verifyMaritimeCapafyPrepareReceipt(f.prepareReceipt,f.prepare,{...f.cycle,tenant_id:"foreign"},f.cycleReceipt),false);
  assert.equal(r.verifyMaritimeCapafyPrepareReceipt(f.prepareReceipt,f.prepare,f.cycle,{...f.cycleReceipt,artifact_refs:["artifact://other"]}),false);
});
test("prepare continuation accepts only its immutable official receipt and enqueues the bound publish job",async()=>{
  const f=fixture(),adapter=runtime().createMaritimeManagerCapafyPrepareAdapter(f.services);
  const next=await adapter.continuation(f.prepare,f.prepareReceipt);
  assert.deepEqual(next.job,f.publish && runtime().buildMaritimeCapafyPublishJob({...f.args,sourceCycleJobId:f.cycle.job_id,
    prepareJobId:f.prepare.job_id,agentId:"123",agentVersionId:"456"}));
  assert.equal(next.availableAt,"2026-10-23T12:00:00.000Z");
  await assert.rejects(adapter.continuation(f.prepare,{...f.prepareReceipt,account_ref:"other"}),/invalid/);
});
test("missing account binding, inactive tenant, non-original, frozen or duplicate artifacts never dispatch",async()=>{
  for(const kind of ["unconfigured","foreign","paused","frozen","duplicate","not-original","cycle"]){
    const f=fixture();
    if(kind==="unconfigured")delete f.services.provider;
    if(kind==="foreign")f.provider.readAccountBinding=async()=>({tenantId:"other",accountRef:f.args.accountRef,provider:"capafy"});
    if(kind==="paused")f.services.managerStore.read=async()=>({uid:UID,status:"paused",release_sha:SHA});
    if(kind==="cycle")f.services.readCompletedCycle=async()=>({job:f.cycle,receipt:{...f.cycleReceipt,artifact_refs:[]}});
    if(["frozen","duplicate","not-original"].includes(kind))f.provider.guardArtifact=async()=>({original:kind!=="not-original",frozen:kind==="frozen",duplicate:kind==="duplicate"});
    await assert.rejects(runtime().createMaritimeManagerCapafyPrepareAdapter(f.services).execute(f.prepare));
    assert.deepEqual(f.counts(),{prepares:0,publishes:0},kind);
  }
});
test("unknown publish readback keeps the effect uncertain and reconciliation never dispatches",async()=>{
  const f=fixture();f.provider.readPublish=async()=>({state:"unknown"});
  const adapter=runtime().createMaritimeManagerCapafyPublishAdapter(f.services);
  await assert.rejects(adapter.execute(f.publish),error=>error.unknownEffect===true);
  assert.deepEqual(f.counts(),{prepares:0,publishes:1});
  for(let n=0;n<3;n++)assert.equal((await adapter.reconcile({...f.publish,status:"reconciling"})).state,"unknown");
  assert.deepEqual(f.counts(),{prepares:0,publishes:1});
});
test("unknown prepare readback keeps the effect uncertain and reconciliation never dispatches again",async()=>{
  const f=fixture();f.provider.readPrepare=async()=>({state:"unknown"});
  const adapter=runtime().createMaritimeManagerCapafyPrepareAdapter(f.services);
  await assert.rejects(adapter.execute(f.prepare),error=>error.unknownEffect===true);
  assert.deepEqual(f.counts(),{prepares:1,publishes:0});
  for(let n=0;n<3;n++)assert.equal((await adapter.reconcile({...f.prepare,status:"reconciling"})).state,"unknown");
  assert.deepEqual(f.counts(),{prepares:1,publishes:0});
});
test("Capafy host actions receive only the matching tenant token from the encrypted binding",async()=>{
 const f=fixture(),calls=[],token="am_sk_"+"t".repeat(32);
 f.provider.withAccessToken=async(identity,operation,options)=>{
  calls.push(["token",options?.mode]);
  return operation(token,{provider:"capafy",tenantId:UID,accountRef:f.args.accountRef,
    providerSubject:"019d3c7f-fe51-7c57-aa2e-8e1055bb36a5",autonomyConsentVersion:"maritime-capafy-autonomy-v1"});
 };
 const assertBound=input=>{
  assert.equal(input.accessToken,token);
  assert.equal(input.identity.tenantId,UID);
  assert.equal(input.identity.accountRef,f.args.accountRef);
 };
 f.provider.guardArtifact=async input=>{assertBound(input);calls.push(["guard"]);return {original:true,frozen:false,duplicate:false};};
 f.provider.prepare=async input=>{assertBound(input);calls.push(["prepare"]);};
 f.provider.readPrepare=async input=>{assertBound(input);calls.push(["read"]);return {state:"present",receipt:f.prepareReceipt};};
 await runtime().createMaritimeManagerCapafyPrepareAdapter(f.services).execute(f.prepare);
 assert.deepEqual(calls,[ ["token","action"],["guard"],["token","action"],["prepare"],["token","readback"],["read"] ]);
});
test("Capafy host action refuses a token callback whose resolved identity crosses tenants",async()=>{
 const f=fixture();let externalCalls=0;
 f.provider.withAccessToken=async(_identity,operation)=>operation("am_sk_"+"t".repeat(32),{
  provider:"capafy",tenantId:"lm_22222222-2222-4222-8222-222222222222",accountRef:f.args.accountRef,
  providerSubject:"019d3c7f-fe51-7c57-aa2e-8e1055bb36a5",autonomyConsentVersion:"maritime-capafy-autonomy-v1"});
 f.provider.guardArtifact=async()=>{externalCalls++;return {original:true,frozen:false,duplicate:false};};
 f.provider.prepare=async()=>{externalCalls++;};
 await assert.rejects(runtime().createMaritimeManagerCapafyPrepareAdapter(f.services).execute(f.prepare),/identity|binding|tenant/i);
 assert.equal(externalCalls,0);
});
test("read-only reconcile preserves present, authoritative absent and invalid/unknown states",async()=>{
  for(const phase of ["prepare","publish"]){
    const f=fixture(),adapter=runtime()[phase==="prepare"?"createMaritimeManagerCapafyPrepareAdapter":"createMaritimeManagerCapafyPublishAdapter"](f.services);
    const job=f[phase],saved=f[phase+"Receipt"],method=phase==="prepare"?"readPrepare":"readPublish";
    assert.equal((await adapter.reconcile(job)).state,"present");
    f.provider[method]=async()=>({state:"absent",receipt:{...saved,status:"absent"}});
    assert.equal((await adapter.reconcile(job)).state,"absent");
    f.provider[method]=async()=>({state:"absent",receipt:{...saved,status:"absent",account_ref:"foreign"}});
    assert.equal((await adapter.reconcile(job)).state,"unknown");
    f.provider[method]=async()=>({state:"present",receipt:{...saved,agent_version_id:"other"}});
    if(phase==="publish")assert.equal((await adapter.reconcile(job)).state,"unknown");
    assert.deepEqual(f.counts(),{prepares:0,publishes:0});
  }
});
test("publisher rejects missing prepare receipt, forged target, second attempt and invalid official URL",async()=>{
  for(const kind of ["no-prepare","target","attempt","url"]){
    const f=fixture();
    if(kind==="no-prepare")f.services.readPrepareReceipt=async()=>null;
    if(kind==="target")f.publish.input_refs.agent_version_id="other";
    if(kind==="attempt")f.publish.attempt=2;
    if(kind==="url")f.provider.readPublish=async()=>({state:"present",receipt:{...f.publishReceipt,url:"https://evil.example"}});
    const adapter=runtime().createMaritimeManagerCapafyPublishAdapter(f.services);
    await assert.rejects(adapter.execute(f.publish));
    if(kind!=="url")assert.deepEqual(f.counts(),{prepares:0,publishes:0});
  }
});
module.exports={fixture,receipt};

test("completed central cycle selects one guarded original artifact and idempotently queues prepare",async()=>{
  const f=fixture(),saved=new Map();
  const services={...f.services,provider:{...f.provider,readAccountBinding:async()=>({provider:"capafy",tenantId:UID,
      accountRef:f.args.accountRef,providerSubject:"019d3c7f-fe51-7c57-aa2e-8e1055bb36a5",
      autonomyConsentVersion:"maritime-capafy-autonomy-v1"})},
    enqueueJob:async job=>{const prior=saved.get(job.job_id);if(!prior)saved.set(job.job_id,job);return {created:!prior,job:prior||job};}};
  const input={job:f.cycle,receipt:f.cycleReceipt};
  const first=await runtime().enqueueMaritimeCapafyPrepareFromCycle(input,services);
  assert.equal(first.created,true);assert.equal(first.job.capability,"maritime.manager.capafy.prepare");
  assert.equal((await runtime().enqueueMaritimeCapafyPrepareFromCycle(input,services)).created,false);
  assert.equal(saved.size,1);assert.deepEqual(f.counts(),{prepares:0,publishes:0});
  await assert.rejects(runtime().enqueueMaritimeCapafyPrepareFromCycle({...input,job:{...f.cycle,status:"running"}},services));
  await assert.rejects(runtime().enqueueMaritimeCapafyPrepareFromCycle({...input,receipt:{...f.cycleReceipt,providerReceiptRefs:["fake"]}},services));
});

test("pause after successful prepare persists the known receipt without a publish successor",async()=>{
 const f=fixture();f.services.managerStore.read=async()=>({uid:UID,status:"paused",paused_at:"2026-10-23T12:00:01.000Z",release_sha:SHA});
 const adapter=runtime().createMaritimeManagerCapafyPrepareAdapter(f.services);
 assert.equal((await adapter.reconcile(f.prepare)).state,"present");
 assert.equal(await adapter.continuation(f.prepare,f.prepareReceipt),null);
 let commits=0;
 await require("../scripts/runtime-up.js").reconcileMaritimeCapabilityJobs([f.prepare.capability],{
  registry:{getByCapability:()=>adapter},store:{
   claimReconcilingJobs:async()=>[{...f.prepare,status:"reconciling"}],
   recordUnknownReconciliation:async()=>{throw new Error("known success must not age");},
   resolveReconciliationAndEnqueue:async()=>{throw new Error("paused tenant cannot publish");},
   resolveReconciliation:async input=>{assert.equal(input.decision,"present");assert.deepEqual(input.receipt,f.prepareReceipt);commits++;},
  },
 });
 assert.equal(commits,1);assert.deepEqual(f.counts(),{prepares:0,publishes:0});
});
