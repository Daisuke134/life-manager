'use strict';
const test=require('node:test');const assert=require('node:assert/strict');
const {buildMaritimeManagerCycleJob,createMaritimeManagerLoopAdapter}=require('./maritime-manager-runtime.js');
const {buildMaritimeArtifactPath,handleMaritimeManagerArtifact}=require('./maritime-manager-artifacts.js');
const UID='lm_11111111-1111-4111-8111-111111111111';
const SHA='a'.repeat(40);
function fixture(){
 const job=buildMaritimeManagerCycleJob({tenantId:UID,occurrenceId:'first',dateKey:'2026-10-21',releaseSha:SHA});
 const ref='artifact://original/商品 % ready\\copy.md',external='maritime-execution://agent-1/exec-1';
 const receipt={schema_version:1,kind:'maritime_manager_cycle',tenant_id:UID,job_id:job.job_id,occurrence_id:'first',date_key:'2026-10-21',release_sha:SHA,
  agent_id:'agent-1',execution_id:'exec-1',status:'completed',artifact_refs:[ref],error_class:null,provider:'maritime',external_ref:external,evidence_refs:[external]};
 const calls=[];let identity={uid:UID};
 const options={env:{LM_MARITIME_MANAGER_EMAIL_ENABLED:'1'},resolveUser:async()=>identity,
  readCommonJob:async input=>{calls.push(['job',input]);return job;},
  cycleAdapter:{reconcile:async()=>({state:'present',receipt}),verify:createMaritimeManagerLoopAdapter().verify},
  transport:{readArtifact:async input=>{calls.push(['file',input]);return new TextEncoder().encode('original product');}}};
 return {job,ref,receipt,calls,options,signOut(){identity=null;}};
}
function response(){return {writeHead(status,headers){this.status=status;this.headers=headers;},end(body){this.body=body;}};}
test('authenticated artifact download preserves raw POSIX names and binds the official completed receipt',async()=>{
 const f=fixture(),res=response();const path=buildMaritimeArtifactPath({jobId:f.job.job_id,artifactRef:f.ref});
 assert.equal(await handleMaritimeManagerArtifact({method:'GET',url:path},res,f.options),true);
 assert.equal(res.status,200);assert.equal(new TextDecoder().decode(res.body),'original product');
 assert.equal(res.headers['content-type'],'application/octet-stream');assert.match(res.headers['content-disposition'],/^attachment;/);
 assert.equal(res.headers['cache-control'],'no-store');assert.equal(res.headers['x-content-type-options'],'nosniff');
 assert.deepEqual(f.calls.at(-1),['file',{uid:UID,agentId:'agent-1',artifactRef:f.ref}]);
});
test('unauthenticated, foreign, unverified and unlisted artifacts never reach the file reader',async()=>{
 for(const kind of ['signed-out','foreign','pending','unlisted']){
  const f=fixture(),res=response();
  if(kind==='signed-out')f.signOut();
  if(kind==='foreign')f.options.readCommonJob=async()=>({...f.job,tenant_id:'lm_22222222-2222-4222-8222-222222222222'});
  if(kind==='pending')f.options.cycleAdapter.reconcile=async()=>({state:'pending'});
  const ref=kind==='unlisted'?'artifact://private.txt':f.ref;
  await handleMaritimeManagerArtifact({method:'GET',url:buildMaritimeArtifactPath({jobId:f.receipt.job_id,artifactRef:ref})},res,f.options);
  assert.ok([401,404,503].includes(res.status),kind);assert.equal(f.calls.some(c=>c[0]==='file'),false);
 }
});
test('path traversal, NUL, encoded separators and unsupported methods cannot read files',async()=>{
 const f=fixture();for(const ref of ['artifact://../x','artifact:///x','artifact://a/./b','artifact://a\0b'])assert.throws(()=>buildMaritimeArtifactPath({jobId:f.job.job_id,artifactRef:ref}),/invalid/);
 const base=buildMaritimeArtifactPath({jobId:f.job.job_id,artifactRef:'artifact://safe.txt'});
 for(const url of [base.replace('safe.txt','a%2Fb'),base.replace('safe.txt','%00'),base.replace('safe.txt','%ZZ')]){
  const res=response();await handleMaritimeManagerArtifact({method:'GET',url},res,f.options);assert.equal(res.status,404);
 }
 const res=response();await handleMaritimeManagerArtifact({method:'POST',url:base},res,f.options);assert.equal(res.status,405);
 assert.equal(f.calls.length,0);
});
test('HTTP artifact response is an attachment and preserves verified bytes',async t=>{
 const http=require('node:http');const {once}=require('node:events');const f=fixture();
 const server=http.createServer((req,res)=>{handleMaritimeManagerArtifact(req,res,f.options).catch(()=>{res.writeHead(500);res.end();});});
 server.listen(0,'127.0.0.1');await once(server,'listening');t.after(()=>new Promise(resolve=>server.close(resolve)));
 const response=await fetch('http://127.0.0.1:'+server.address().port+buildMaritimeArtifactPath({jobId:f.job.job_id,artifactRef:f.ref}));
 assert.equal(response.status,200);assert.match(response.headers.get('content-disposition'),/^attachment;/);
 assert.equal(await response.text(),'original product');
});


test('default artifact reconciliation does not require a new-work readiness dependency',async()=>{
 const f=fixture(),result={tenantId:UID,occurrenceId:'first',artifactRefs:[f.ref],providerSnapshotRef:null,providerReceiptRefs:[],nextEligibleAt:null,status:'completed',errorClass:null};
 delete f.options.cycleAdapter;
 f.options.managerStore={read:async()=>({uid:UID,agent_id:'agent-1'}),
  readCycleDispatch:async()=>({uid:UID,agent_id:'agent-1',occurrence_id:'first',date_key:'2026-10-21',release_sha:SHA,execution_id:'exec-1'}),
  claimCycleDispatch:async()=>{throw new Error('claim forbidden');},bindCycleExecution:async()=>{throw new Error('bind forbidden');}};
 Object.assign(f.options.transport,{dispatchCycle:async()=>{throw new Error('dispatch forbidden');},
  readExecution:async()=>({status:'completed',exitCode:0,stdout:JSON.stringify(result)}),
  readCycleReceipt:async()=>({dateKey:'2026-10-21',releaseSha:SHA,result})});
 const res=response();await handleMaritimeManagerArtifact({method:'GET',url:buildMaritimeArtifactPath({jobId:f.job.job_id,artifactRef:f.ref})},res,f.options);
 assert.equal(res.status,200);
});
