'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createHmac, createHash } = require('node:crypto');
const { createMaritimeManagerTransport } = require('./maritime-manager.js');
const { createMaritimeWakeBinding } = require('../maritime-manager-wake.js');
const { projectMaritimeSchedules } = require('../maritime-manager-schedules.js');
const { createMaritimeManagerLoopAdapter, buildMaritimeManagerCycleJob } = require('../maritime-manager-runtime.js');
const { MANAGER_CONSENT_VERSION } = require('../maritime-distribution.js');
const UID = 'lm_11111111-1111-4111-8111-111111111111';
const SHA = 'a'.repeat(40);
const ARCHIVE = 'b'.repeat(64);
const UPLOAD = 'uploads/fixture/source.zip';
const env = { MARITIME_API_KEY: 'mk_fixture_key_only', LM_UID_SECRET: 'fixture-global-identity-is-different', LM_MARITIME_MANAGER_ID_SECRET: 'fixture-manager-identity-secret-32-bytes-long' };
const externalId = 'lm-manager-' + createHmac('sha256', env.LM_MARITIME_MANAGER_ID_SECRET).update(`agent:v1:${UID}`).digest('hex').slice(0,32);
function fixture() {
  const row = { uid: UID, auth_subject: UID.slice(3), status: 'pending', consent_version: MANAGER_CONSENT_VERSION,
    paused_at: null, release_sha: SHA, agent_id: null };
  let agent = null; let failCreate = false; let missingExecution = false; let checkpoint = null;
  let download = new TextEncoder().encode('original product');
  let oversized = false; let cancelled = 0;
  const calls = [];
  const envelope = { dateKey: '2026-10-20', releaseSha: SHA, result: { tenantId: UID, occurrenceId: 'cycle-1', artifactRefs:['artifact://original/product.md'], providerSnapshotRef:null,providerReceiptRefs:[],nextEligibleAt:null,status:'completed',errorClass:null } };
  const sdk = { agents: {
    start: async id => { calls.push(['start',id]); return {id,status:'active'}; },
    exec: async () => ({status:'completed',exitCode:0,stdout:JSON.stringify({health:{ok:true,releaseSha:SHA,
      relayBindingHash:createHash('sha256').update(createMaritimeWakeBinding({uid:UID,agentId:'agent-1',releaseSha:SHA},{secret:env.LM_MARITIME_MANAGER_ID_SECRET,publicOrigin:'https://manager.example'}).token).digest('hex')},schedules:[]})}),
    get: async id => { calls.push(['sdk.get',id]); return structuredClone(agent); },
    listEnv: async id => { calls.push(['sdk.env',id]); return [{ key:'LM_RUNTIME_TENANT_ID',value:UID,isSecret:false }, { key:'LM_RELEASE_SHA',value:SHA,isSecret:false }, { key:'LM_SOURCE_ARCHIVE_SHA256',value:ARCHIVE,isSecret:false }]; },
    files: {
      download: async (id, filename) => { calls.push(['download', id, filename]); return new TextEncoder().encode(JSON.stringify(envelope)); },
      write: async (...args) => { calls.push(['write',...args]); },
    },
  } };
  const managerStore = {
    read: async uid => uid === UID ? structuredClone(row) : null,
    readCycleDispatch: async () => checkpoint && structuredClone(checkpoint),
    claimCycleDispatch: async input => { if(checkpoint)return {claimed:false,row:structuredClone(checkpoint)};checkpoint={uid:input.uid,agent_id:input.agentId,occurrence_id:input.occurrenceId,date_key:input.dateKey,release_sha:input.releaseSha,execution_id:null};return {claimed:true,row:structuredClone(checkpoint)}; },
    bindCycleExecution: async input => {checkpoint.execution_id=input.executionId;return structuredClone(checkpoint);},
    claimProvision: async uid => { calls.push(['claim',uid]); if(row.status!=='pending')return false;row.status='provisioning';return true; },
    bindAgent: async input => { calls.push(['bind',input]); row.agent_id=input.agentId;row.status=row.paused_at?'paused':'active';return structuredClone(row); },
  };
  const fetchImpl = async (url, options) => {
    calls.push(['http',url,options]);
    const data = options.body && JSON.parse(options.body);
    if(url.includes('/end-users/') && options.method==='GET') return { ok:true,status:200,json:async()=>agent?[structuredClone(agent)]:[] };
    if(url.includes('/end-users/') && options.method==='POST') {
      agent = { id:'agent-1',externalId:data.externalId,framework:data.framework,status:'deploying' };
      if(failCreate)throw new Error('private-provider-error');
      return {ok:true,status:201,json:async()=>structuredClone(agent)};
    }
    if(url.endsWith('/exec') && options.method==='POST'&&data.command[0]==='python3')return {ok:true,status:200,json:async()=>({status:'completed',exitCode:0,stdout:JSON.stringify({tenantId:UID,artifactRef:data.command.at(-1),size:16,sha256:createHash('sha256').update('original product').digest('hex')})})};
    if(url.includes('/files/download?'))return {ok:true,status:200,headers:new Headers(oversized?{'content-length':String(20*1024*1024+1)}:{}),body:new ReadableStream({start(c){c.enqueue(download);if(!oversized)c.close();},cancel(){cancelled++;}})};
    if(url.endsWith('/exec') && options.method==='POST') return {ok:true,status:202,json:async()=>(missingExecution?{}:{executionId:'exec-1',status:'running'})};
    if(url.endsWith('/exec/exec-1')&&options.method==='DELETE')return {ok:true,status:200,json:async()=>({executionId:'exec-1',status:'cancelled',exitCode:-1,stdout:'partial private output',stderr:'private-stderr'})};
    if(url.endsWith('/exec/exec-1')) return {ok:true,status:200,json:async()=>({executionId:'exec-1',status:'completed',exitCode:0,stdout:JSON.stringify(envelope.result),stderr:'private-stderr'})};
    throw new Error('unexpected-test-http');
  };
  const transport = createMaritimeManagerTransport({ env,fetchImpl,client:sdk,managerStore,
    getWakeBinding: async input => createMaritimeWakeBinding(input,{secret:env.LM_MARITIME_MANAGER_ID_SECRET,publicOrigin:'https://manager.example'}) });
  return {transport,row,calls,envelope,sdk,managerStore,ready(){agent.status='active';},loseCreate(){failCreate=true;},invalidExecution(){missingExecution=true;},agent:()=>agent,changeArtifact(){download=new TextEncoder().encode('changed');},oversizeArtifact(){oversized=true;},cancelled:()=>cancelled};
}
const provision = {uid:UID,uploadS3Key:UPLOAD,archiveSha256:ARCHIVE,releaseSha:SHA};
test('custom create seeds a scoped VM and binds only after official ready and env readback', async () => {
  const f=fixture();
  assert.deepEqual(await f.transport.ensureAgent(provision),{agentId:'agent-1',status:'deploying'});
  assert.equal(f.row.agent_id,null);
  const post=f.calls.find(x=>x[0]==='http'&&x[2].method==='POST');
  assert.equal(post[1],`https://api.maritime.sh/api/v1/end-users/${externalId}/agents`);
  const body=JSON.parse(post[2].body);
  assert.equal(body.framework,'custom');assert.equal(body.templateId,undefined);assert.equal(body.imageName,undefined);assert.equal(body.uploadS3Key,UPLOAD);assert.equal(body.healthCheckPath,'/health');assert.equal(body.useMaritimeLlm,true);
  assert.equal(body.initialEnvVars.find(x=>x.key==='LM_RUNTIME_TENANT_ID').value,UID);
  assert.equal(body.initialEnvVars.find(x=>x.key==='LM_WAKE_RELAY_TOKEN').isSecret,true);
  assert.equal(post[2].redirect,'error');
  f.ready();
  assert.deepEqual(await f.transport.ensureAgent(provision),{agentId:'agent-1',status:'active'});
  assert.equal(f.row.agent_id,'agent-1');
  assert.equal(f.calls.filter(x=>x[0]==='http'&&x[2].method==='POST').length,1);
});
test('lost create response is recovered read-only and never creates another VM', async () => {
  const f=fixture();f.loseCreate();
  await assert.rejects(f.transport.ensureAgent(provision),e=>e.unknownEffect===true&&!e.message.includes('private-provider-error'));
  f.ready();
  assert.deepEqual(await f.transport.readAgent(provision),{agentId:'agent-1',status:'active'});
  assert.equal(f.calls.filter(x=>x[0]==='http'&&x[2].method==='POST').length,1);
  assert.equal(f.row.agent_id,'agent-1');
});
test('foreign provider metadata cannot become an active enrollment', async () => {
  const f=fixture();await f.transport.ensureAgent(provision);f.ready();f.agent().externalId='foreign';
  await assert.rejects(f.transport.readAgent(provision),/binding/);
  assert.equal(f.row.agent_id,null);
});
test('detached cycle executes the fixed wrapper only for an active same-tenant binding', async () => {
  const f=fixture();await f.transport.ensureAgent(provision);f.ready();await f.transport.readAgent(provision);
  assert.deepEqual(await f.transport.dispatchCycle({uid:UID,agentId:'agent-1',occurrenceId:'cycle-1',dateKey:'2026-10-20',releaseSha:SHA}),{executionId:'exec-1'});
  const post=f.calls.find(x=>x[0]==='http'&&x[1].endsWith('/exec'));
  assert.deepEqual(JSON.parse(post[2].body),{command:['node','/app/apps/life-manager/maritime/run-cycle.js','--tenant',UID,'--occurrence','cycle-1','--date','2026-10-20'],detached:true,timeout:3720});
  assert.deepEqual(await f.transport.readExecution({uid:UID,agentId:'agent-1',executionId:'exec-1'}),{status:'completed',exitCode:0,stdout:JSON.stringify(f.envelope.result)});
  f.row.paused_at='2026-10-20T00:00:00Z';f.row.status='paused';
  await assert.rejects(f.transport.dispatchCycle({uid:UID,agentId:'agent-1',occurrenceId:'cycle-2',dateKey:'2026-10-20',releaseSha:SHA}),/paused/);
  assert.equal(f.calls.filter(x=>x[0]==='http'&&x[1].endsWith('/exec')).length,1);
  assert.deepEqual(await f.transport.readCycleReceipt({uid:UID,agentId:'agent-1',occurrenceId:'cycle-1'}),f.envelope);
  assert.equal(f.calls.at(-1)[2],`/data/${UID}/receipts/cycle-1/cycle.json`);
});
test('schedule write uses the validated own-tenant envelope and fixed filename', async () => {
  const f=fixture();await f.transport.ensureAgent(provision);f.ready();await f.transport.readAgent(provision);
  const snapshot=projectMaritimeSchedules({tenantId:UID,releaseSha:SHA,status:'active',pausedAt:null,nextEligibleAt:null,timezone:'UTC',nowMs:Date.parse('2026-10-20T00:00:00Z')});
  assert.deepEqual(await f.transport.writeScheduleSnapshot({uid:UID,agentId:'agent-1',snapshot}),{ok:true});
  assert.equal(f.calls.at(-1)[2],`/data/${UID}/maritime-schedules.json`);
  await assert.rejects(f.transport.writeScheduleSnapshot({uid:UID,agentId:'foreign',snapshot}),/binding/);
  await assert.rejects(f.transport.writeScheduleSnapshot({uid:UID,agentId:'agent-1',snapshot:{...snapshot,tenantId:'foreign'}}),/schedule/);
});
test('invalid image, tenant and missing configuration fail before provision claim or POST', async () => {
  const f=fixture();
  await assert.rejects(f.transport.ensureAgent({...provision,archiveSha256:'invalid'}),/invalid/);
  await assert.rejects(f.transport.ensureAgent({...provision,uid:'../foreign'}),/invalid/);
  assert.equal(f.calls.length,0);
  const transport=createMaritimeManagerTransport();
  await assert.rejects(transport.ensureAgent(provision),/unconfigured/);
});

test('an accepted dispatch without an execution ID retains an unknown external effect', async () => {
  const f=fixture();await f.transport.ensureAgent(provision);f.ready();await f.transport.readAgent(provision);f.invalidExecution();
  await assert.rejects(f.transport.dispatchCycle({uid:UID,agentId:'agent-1',occurrenceId:'cycle-1',dateKey:'2026-10-20',releaseSha:SHA}),error=>error.unknownEffect===true);
});

test('existing cycle adapter consumes real transport contracts and replays the persisted execution only', async () => {
  const f=fixture();await f.transport.ensureAgent(provision);f.ready();await f.transport.readAgent(provision);
  const adapter=createMaritimeManagerLoopAdapter({managerStore:f.managerStore,prepareCycle:f.transport.readWakeConfiguration,
    withControlLock:async(_uid,operation)=>operation(),dispatchCycle:f.transport.dispatchCycle,
    readExecution:f.transport.readExecution,readCycleReceipt:f.transport.readCycleReceipt});
  const job=buildMaritimeManagerCycleJob({tenantId:UID,occurrenceId:'cycle-1',dateKey:'2026-10-20',releaseSha:SHA});
  const first=await adapter.execute(job);assert.equal(adapter.verify(first.receipt,job),true);
  assert.deepEqual(await adapter.execute(job),first);
  assert.equal(f.calls.filter(x=>x[0]==='http'&&x[1].endsWith('/exec')&&x[2].method==='POST').length,1);
});

test('official ZIP agent response without imageName binds only after matching archive configuration', async () => {
  const f=fixture();await f.transport.ensureAgent(provision);f.ready();
  assert.equal(Object.hasOwn(f.agent(),'imageName'),false);
  assert.deepEqual(await f.transport.readAgent(provision),{agentId:'agent-1',status:'active'});
  const other=fixture();await other.transport.ensureAgent(provision);other.ready();
  const list=other.sdk.agents.listEnv;
  other.sdk.agents.listEnv=async id=>(await list(id)).map(v=>v.key==='LM_SOURCE_ARCHIVE_SHA256'?{...v,value:'c'.repeat(64)}:v);
  await assert.rejects(other.transport.readAgent(provision),/binding/);
  assert.equal(other.row.agent_id,null);
});

test('bound wake secret is configured and reloaded only for its active tenant agent', async () => {
  const f=fixture();await f.transport.ensureAgent(provision);f.ready();await f.transport.readAgent(provision);
  const effects=[];
  f.sdk.agents.setEnv=async (...args)=>{effects.push(['env',...args]);return {key:args[1],isSecret:true};};
  f.sdk.agents.reloadEnv=async id=>{effects.push(['reload',id]);return {id,status:'active'};};
  assert.deepEqual(await f.transport.configureWake({uid:UID,agentId:'agent-1',releaseSha:SHA}),{agentId:'agent-1',status:'active'});
  assert.deepEqual(effects,[['env','agent-1','LM_WAKE_RELAY_TOKEN',createMaritimeWakeBinding({uid:UID,agentId:'agent-1',releaseSha:SHA},{secret:env.LM_MARITIME_MANAGER_ID_SECRET,publicOrigin:'https://manager.example'}).token,{secret:true}],['reload','agent-1']]);
  await assert.rejects(f.transport.configureWake({uid:UID,agentId:'foreign',releaseSha:SHA}),/binding/);
  f.row.status='paused';f.row.paused_at='2026-10-20T01:00:00Z';
  await assert.rejects(f.transport.configureWake({uid:UID,agentId:'agent-1',releaseSha:SHA}),/paused/);
  assert.equal(effects.length,2);
});
test('artifact bytes require bound no-follow proof, fixed workspace path and matching hash',async()=>{
 const f=fixture();await f.transport.ensureAgent(provision);f.ready();await f.transport.readAgent(provision);
 const ref='artifact://original/商品 % ready\\copy.md';
 f.row.status='paused';f.row.paused_at='2026-10-21T01:00:00Z';
 const bytes=await f.transport.readArtifact({uid:UID,agentId:'agent-1',artifactRef:ref});
 assert.equal(new TextDecoder().decode(bytes),'original product');
 const probe=f.calls.find(c=>c[0]==='http'&&c[1].endsWith('/exec'));
 assert.deepEqual(JSON.parse(probe[2].body),{command:['python3','/app/apps/life-manager/maritime/artifact-proof.py','--tenant',UID,'--artifact',ref],detached:false,timeout:20});
 const request=f.calls.find(c=>c[0]==='http'&&c[1].includes('/files/download?'));
 assert.equal(new URL(request[1]).searchParams.get('path'),`/data/${UID}/build/original/商品 % ready\\copy.md`);
 assert.equal(request[2].redirect,'error');
 f.changeArtifact();await assert.rejects(f.transport.readArtifact({uid:UID,agentId:'agent-1',artifactRef:ref}),/artifact/);
 f.oversizeArtifact();await assert.rejects(f.transport.readArtifact({uid:UID,agentId:'agent-1',artifactRef:ref}),/artifact/);assert.equal(f.cancelled(),1);
 const before=f.calls.length;
 for(const input of [{uid:UID,agentId:'foreign',artifactRef:ref},{uid:UID,agentId:'agent-1',artifactRef:'artifact://../private'}])await assert.rejects(f.transport.readArtifact(input));
 assert.equal(f.calls.length,before);
});


test('loaded wake configuration verifies the binding without reconfiguration',async()=>{
 const binding=createMaritimeWakeBinding({uid:UID,agentId:'agent-1',releaseSha:SHA},{secret:env.LM_MARITIME_MANAGER_ID_SECRET,publicOrigin:'https://panel.invalid'});
 const calls=[];let stale=false;
 const managerStore={read:async()=>({uid:UID,agent_id:'agent-1',release_sha:SHA,status:'active',paused_at:null}),claimProvision:async()=>{},bindAgent:async()=>{}};
 const client={agents:{start:async id=>({id,status:'active'}),exec:async(id,command,options)=>{calls.push([id,command,options]);return {status:'completed',exitCode:0,stdout:JSON.stringify({health:{ok:true,releaseSha:SHA,relayBindingHash:stale?'0'.repeat(64):createHash('sha256').update(binding.token).digest('hex')},schedules:[]})};}}};
 const transport=createMaritimeManagerTransport({env,managerStore,client,getWakeBinding:async()=>binding});
 assert.deepEqual(await transport.readWakeConfiguration({uid:UID,agentId:'agent-1',releaseSha:SHA}),{ready:true,schedules:[]});
 assert.equal(calls[0][1],'node /app/apps/life-manager/maritime/runtime-status.js');
 assert.equal(calls[0][2].detached,false);
 stale=true;
 assert.equal((await transport.readWakeConfiguration({uid:UID,agentId:'agent-1',releaseSha:SHA})).ready,false);
});


test('cold artifact guest wakes only its bound VM before proof and never dispatches business work',async()=>{
 const f=fixture();await f.transport.ensureAgent(provision);f.ready();await f.transport.readAgent(provision);f.agent().status='sleeping';
 let wakes=0;f.sdk.agents.start=async id=>{assert.equal(id,'agent-1');wakes++;f.agent().status='active';return {id,status:'active'};};
 const bytes=await f.transport.readArtifact({uid:UID,agentId:'agent-1',artifactRef:'artifact://original/product.md'});
 assert.equal(bytes.toString(),'original product');assert.equal(wakes,1);
 const execs=f.calls.filter(x=>x[0]==='http'&&x[1].endsWith('/exec'));
 assert.equal(execs.length,1);assert.equal(JSON.parse(execs[0][2].body).detached,false);
 await assert.rejects(()=>f.transport.readArtifact({uid:UID,agentId:'foreign',artifactRef:'artifact://original/product.md'}));assert.equal(wakes,1);
});


test('pending execution lifecycle is tenant bound and never replays the accepted command',async()=>{
 const row={uid:UID,agent_id:'agent-1',release_sha:SHA,status:'active',paused_at:null};let wakes=0,reads=0;
 const managerStore={read:async uid=>uid===UID?row:null,claimProvision:async()=>{},bindAgent:async()=>{}};
 const client={agents:{start:async id=>{wakes++;return {id,status:'active'};}}};
 const transport=createMaritimeManagerTransport({env,managerStore,client,fetchImpl:async(url,options)=>{
  assert.equal(options.method,'GET');reads++;return {ok:true,json:async()=>({executionId:'exec-1',status:'running'})};
 }});
 const input={uid:UID,agentId:'agent-1',executionId:'exec-1'};
 assert.deepEqual(await transport.readExecution(input),{status:'running'});assert.equal(wakes,1);
 row.status='paused';row.paused_at='2026-10-21T00:00:00.000Z';
 assert.deepEqual(await transport.readExecution(input),{status:'running'});assert.equal(wakes,1);
 await assert.rejects(()=>transport.readExecution({...input,agentId:'foreign'}),/binding/);assert.equal(reads,2);assert.equal(wakes,1);
});

test('cancel execution uses Maritime DELETE only for its paused tenant agent',async()=>{
 const f=fixture();await f.transport.ensureAgent(provision);f.ready();await f.transport.readAgent(provision);
 f.row.status='paused';f.row.paused_at='2026-10-25T21:00:00.000Z';
 const result=await f.transport.cancelExecution({uid:UID,agentId:'agent-1',executionId:'exec-1'});
 assert.deepEqual(result,{executionId:'exec-1',status:'cancelled',exitCode:-1});
 const cancel=f.calls.find(x=>x[0]==='http'&&x[1].endsWith('/exec/exec-1')&&x[2].method==='DELETE');
 assert.ok(cancel);assert.equal(cancel[2].redirect,'error');
 await assert.rejects(f.transport.cancelExecution({uid:UID,agentId:'foreign',executionId:'exec-1'}),/binding/);
 await assert.rejects(f.transport.cancelExecution({uid:UID,agentId:'agent-1',executionId:'exec-1/foreign'}),/invalid/);
 assert.equal(f.calls.filter(x=>x[0]==='http'&&x[2].method==='DELETE').length,1);
});


test('pause during execution metadata GET prevents the later lifecycle start',async()=>{
 const row={uid:UID,agent_id:'agent-1',release_sha:SHA,status:'active',paused_at:null};let wakes=0;
 const managerStore={read:async()=>structuredClone(row),claimProvision:async()=>{},bindAgent:async()=>{}};
 const transport=createMaritimeManagerTransport({env,managerStore,client:{agents:{start:async id=>{wakes++;return {id,status:'active'};}}},fetchImpl:async()=>{
  row.status='paused';row.paused_at='2026-10-21T00:00:00.000Z';
  return {ok:true,json:async()=>({executionId:'exec-1',status:'running'})};
 }});
 assert.deepEqual(await transport.readExecution({uid:UID,agentId:'agent-1',executionId:'exec-1'}),{status:'running'});assert.equal(wakes,0);
});
