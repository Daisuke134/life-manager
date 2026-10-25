'use strict';
const test=require('node:test');const assert=require('node:assert/strict');const {Readable}=require('node:stream');
const {createMaritimeWakeBinding,verifyMaritimeWakeToken,buildMaritimeInitialJobs,buildMaritimeReconsentJobs,handleMaritimeManagerWake}=require('./maritime-manager-wake.js');
const {MANAGER_CONSENT_VERSION}=require('./maritime-distribution.js');
const UID='lm_11111111-1111-4111-8111-111111111111';const SHA='a'.repeat(40);const SECRET='private-fixture-signing-key'.repeat(3);
const config={secret:SECRET,publicOrigin:'https://manager.example'};
const identity={uid:UID,agentId:'agent-1',releaseSha:SHA};
const enrollment={uid:UID,agent_id:'agent-1',release_sha:SHA,status:'active',consent_version:MANAGER_CONSENT_VERSION,paused_at:null,timezone:'Asia/Tokyo',created_at:'2026-10-20T09:30:00+00:00'};
function request(body,token=createMaritimeWakeBinding(identity,config).token){const req=Readable.from([typeof body==='string'?body:JSON.stringify(body)]);req.url='/api/internal/maritime/wake';req.method='POST';req.headers={'content-type':'application/json',authorization:`Bearer ${token}`};return req;}
function response(){return {writeHead(status,headers){this.status=status;this.headers=headers;},end(data){this.body=JSON.parse(data);}};}
function fixture(){const jobs=new Map();const calls=[];return {jobs,calls,options:{env:{LM_MARITIME_MANAGER_ID_SECRET:SECRET},managerStore:{read:async uid=>{calls.push(['read',uid]);return structuredClone(enrollment);}},isCapabilityRegistered:()=>true,enqueueJobAt:async(job,at)=>{calls.push(['enqueue',job,at]);const created=!jobs.has(job.job_id);if(created)jobs.set(job.job_id,{...job,status:'queued'});return {created,job:jobs.get(job.job_id)};}}};}

test('signed wake identity is bound to one tenant agent and immutable release',()=>{
 const binding=createMaritimeWakeBinding(identity,config);assert.equal(binding.url,'https://manager.example/api/internal/maritime/wake');
 assert.deepEqual(verifyMaritimeWakeToken(binding.token,SECRET),identity);
 assert.equal(binding.token.includes(SECRET),false);
 for(const token of [binding.token+'x',binding.token.replace('agent-1','agent-2'),'x'.repeat(10000)])assert.equal(verifyMaritimeWakeToken(token,SECRET),null);
 assert.equal(verifyMaritimeWakeToken(binding.token,'other-key'.repeat(10)),null);
 const bootstrap=createMaritimeWakeBinding({uid:UID,releaseSha:SHA},config);assert.equal(verifyMaritimeWakeToken(bootstrap.token,SECRET),null);
});
test('initial jobs are stable across wakes and report time uses the existing timezone projection',()=>{
 const plans=buildMaritimeInitialJobs(enrollment);
 assert.equal(plans.cycle.job.capability,'maritime.manager.cycle');
 assert.equal(plans.cycle.availableAt,'2026-10-20T09:30:00.000Z');
 assert.equal(plans.report.availableAt,'2026-10-20T10:00:00.000Z');
 assert.equal(plans.report.job.input_refs.period_ref,'maritime-period://maritime%3Adaily%3A2026-10-20');
 assert.deepEqual(buildMaritimeInitialJobs(enrollment),plans);
});
test('v2 reconsent resume jobs use the persisted consent anchor and tenant-local next report period',()=>{
 const row={...enrollment,consent_version:MANAGER_CONSENT_VERSION,consent_v2_at:'2026-10-25T16:30:00.000Z'};
 const plans=buildMaritimeReconsentJobs(row);
 assert.equal(plans.cycle.availableAt,'2026-10-25T16:30:00.000Z');
 assert.match(plans.cycle.job.input_refs.cycle_ref,/consent-v2-resume/);
 assert.equal(plans.cycle.job.input_refs.date_ref,'date://2026-10-25');
 assert.equal(plans.report.availableAt,'2026-10-26T10:00:00.000Z');
 assert.equal(plans.report.job.input_refs.period_ref,'maritime-period://maritime%3Adaily%3A2026-10-26');
 assert.deepEqual(buildMaritimeReconsentJobs(row),plans);
});
test('authenticated wake seeds one initial cycle and caller identity and commands have no authority',async()=>{
 const f=fixture();
 for(let n=0;n<2;n++){const res=response();await handleMaritimeManagerWake(request({kind:'cycle',uid:'foreign',tenantId:'foreign',releaseSha:'b'.repeat(40),command:'unsafe'}),res,f.options);assert.equal(res.status,202);assert.equal(res.body.accepted,true);}
 assert.equal(f.jobs.size,1);assert.equal([...f.jobs.values()][0].tenant_id,UID);
 assert.equal(f.calls.filter(x=>x[0]==='read').every(x=>x[1]===UID),true);
});
test('invalid or bootstrap token is rejected before looking up an enrollment',async()=>{
 const f=fixture();for(const token of ['bad',createMaritimeWakeBinding({uid:UID,releaseSha:SHA},config).token]){const res=response();await handleMaritimeManagerWake(request({kind:'cycle'},token),res,f.options);assert.equal(res.status,401);}
 assert.equal(f.calls.length,0);
});
test('a paused enrollment or mismatched bound agent cannot enqueue work',async()=>{
 for(const change of [{status:'paused',paused_at:'2026-10-20T00:00:00Z'},{agent_id:'foreign'},{release_sha:'b'.repeat(40)}]){
  const f=fixture();f.options.managerStore.read=async()=>({...enrollment,...change});const res=response();await handleMaritimeManagerWake(request({kind:'cycle'}),res,f.options);
  assert.equal(res.status===403||res.status===409,true);assert.equal(f.jobs.size,0);
 }
});
test('a stale-consent enrollment is rejected at wake admission before it can create dead-letter work',async()=>{
 const f=fixture();f.options.managerStore.read=async()=>({...enrollment,consent_version:'maritime-manager-v1'});
 const res=response();await handleMaritimeManagerWake(request({kind:'cycle'}),res,f.options);
 assert.equal(res.status,409);assert.deepEqual(res.body,{accepted:false,error:'manager_consent_required'});assert.equal(f.jobs.size,0);
});
test('report wake queues the stable first period at its persisted eligible time',async()=>{
 const f=fixture();const res=response();await handleMaritimeManagerWake(request({kind:'report'}),res,f.options);assert.equal(res.status,202);
 assert.equal(f.calls.at(-1)[1].capability,'maritime.manager.report');assert.equal(f.calls.at(-1)[2],'2026-10-20T10:00:00.000Z');
});
test('unregistered capability and a dead letter never claim new accepted work',async()=>{
 const f=fixture();f.options.isCapabilityRegistered=()=>false;let res=response();await handleMaritimeManagerWake(request({kind:'report'}),res,f.options);assert.equal(res.status,503);assert.equal(f.jobs.size,0);
 f.options.isCapabilityRegistered=()=>true;f.options.enqueueJobAt=async job=>({created:false,job:{...job,status:'dead_letter'}});res=response();await handleMaritimeManagerWake(request({kind:'cycle'}),res,f.options);assert.equal(res.status,409);assert.equal(res.body.accepted,false);
});
test('invalid kind malformed or oversized bodies fail safely and never enqueue',async()=>{
 for(const body of [{kind:'publish'},'{','x'.repeat(4097)]){const f=fixture();const res=response();await handleMaritimeManagerWake(request(body),res,f.options);assert.equal([400,413].includes(res.status),true);assert.equal(f.jobs.size,0);}
 const f=fixture();f.options.managerStore.read=async()=>{throw new Error('private-provider-value');};const res=response();await handleMaritimeManagerWake(request({kind:'cycle'}),res,f.options);assert.equal(res.status,503);assert.equal(JSON.stringify(res.body).includes('private-provider-value'),false);
});

test('HTTP mount contract and real requests keep identity private and return a bounded oversized-body error',async t=>{
 const fs=require('node:fs');const path=require('node:path');const http=require('node:http');const {once}=require('node:events');
 const source=fs.readFileSync(path.join(__dirname,'../server.js'),'utf8');assert.equal(/handleMaritimeManagerWake\(req, res/.test(source),true);
 const f=fixture();const server=http.createServer((req,res)=>{handleMaritimeManagerWake(req,res,f.options).catch(()=>res.writeHead(500).end());});
 server.listen(0,'127.0.0.1');await once(server,'listening');t.after(()=>new Promise(resolve=>server.close(resolve)));
 const base=`http://127.0.0.1:${server.address().port}/api/internal/maritime/wake`;
 const headers={'content-type':'application/json',authorization:`Bearer ${createMaritimeWakeBinding(identity,config).token}`};
 const response=await fetch(base,{method:'POST',headers,body:JSON.stringify({kind:'cycle',uid:'foreign'})});assert.equal(response.status,202);assert.equal((await response.text()).includes(SECRET),false);
 const tooLarge=await fetch(base,{method:'POST',headers,body:'x'.repeat(4097)});assert.equal(tooLarge.status,413);
});
