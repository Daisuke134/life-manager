import assert from 'node:assert/strict';
import test from 'node:test';
import {connectGateway, submitRun, waitRun, abortRun, readSession} from '../gateway-client.mjs';
const request={prompt:'draft',timeout_seconds:60,attachments:[],owned_resume_ref:null};
const identity={sessionKey:'agent:manager:lm:abc',idempotencyKey:'a'.repeat(64)};
class Client {
  static last;
  constructor(options){this.options=options;this.calls=[];Client.last=this;}
  start() {if(this.options.token==='bad')this.options.onConnectError(new Error('secret bad'));}
  async stopAndWait(){this.stopped=true;}
  async request(...args){this.calls.push(args);if(this.error)throw this.error;return this.reply;}
}
async function ready(){const p=connectGateway({url:'ws://127.0.0.1:12345',token:'private'},Client);await Promise.resolve();Client.last.options.onHelloOk({});return p;}
test('no requests before hello; handshake failure stops its client and conceals token',async()=>{
 const connecting=connectGateway({url:'ws://127.0.0.1:12345',token:'private'},Client);
 await Promise.resolve();const c=Client.last;
 await assert.rejects(submitRun(c,request,identity,'manager'),/not_ready/);
 assert.equal(c.calls.length,0);c.options.onHelloOk({});assert.equal(await connecting,c);
 assert.equal(c.options.minProtocol,4);assert.equal(c.options.maxProtocol,4);
 await assert.rejects(connectGateway({url:'ws://127.0.0.1:12345',token:'bad'},Client),e=>e.message==='gateway_connect_failed');
 assert.equal(Client.last.stopped,true);
 await assert.rejects(connectGateway({url:'ws://foreign.example:12345',token:'private'},Client));
});
test('submit uses one idempotent RPC and never retries a lost ACK',async()=>{
 const c=await ready();c.reply={runId:'upstream-1'};
 assert.deepEqual(await submitRun(c,request,identity,'manager'),{runId:'upstream-1'});
 assert.deepEqual(c.calls[0],[ 'agent', {message:'draft',agentId:'manager',sessionKey:identity.sessionKey,idempotencyKey:identity.idempotencyKey,deliver:false,timeout:60}, {expectFinal:false,timeoutMs:5000} ]);
 c.error=new Error('secret private');await assert.rejects(submitRun(c,request,identity,'manager'),/dispatch_unknown/);
 assert.equal(c.calls.length,2);
});
test('wait preserves timeout and rejects foreign IDs or new unknown status fields',async()=>{
 const c=await ready();c.reply={runId:'upstream-1',status:'timeout'};
 assert.equal((await waitRun(c,'upstream-1')).status,'timeout');
 assert.deepEqual(c.calls[0][1],{runId:'upstream-1',timeoutMs:1000});
 for(const reply of [{runId:'other',status:'ok'},{runId:'upstream-1',status:'success'},{runId:'upstream-1',status:'ok',surprise:true}]){
 c.reply=reply;await assert.rejects(waitRun(c,'upstream-1'),/provider_status_unknown/);
 }
});
test('abort is scoped to exactly its named run and does not assert termination',async()=>{
 const c=await ready();c.reply={ok:true};assert.deepEqual(await abortRun(c,{runId:'upstream-1',sessionKey:identity.sessionKey,agentId:'manager'}),{ok:true});
 assert.deepEqual(c.calls[0][1],{key:identity.sessionKey,runId:'upstream-1',agentId:'manager'});
 await assert.rejects(abortRun(c,{runId:'upstream-1',sessionKey:'agent:foreign:lm:abc',agentId:'manager'}));
 assert.equal(c.calls.length,1);
});
test('exact session read rejects foreign rows and keeps missing liveness unknown',async()=>{
 const c=await ready();c.reply={sessions:[{key:identity.sessionKey,agentId:'manager'}]};
 assert.equal((await readSession(c,{sessionKey:identity.sessionKey,agentId:'manager'})).liveness,'unknown');
 c.reply={sessions:[{key:identity.sessionKey,agentId:'foreign'}]};await assert.rejects(readSession(c,{sessionKey:identity.sessionKey,agentId:'manager'}));
});
test('SDK reconnect restores observation of the same run without resubmitting it',async()=>{
 const c=await ready();c.reply={runId:'upstream-1',status:'timeout'};
 await waitRun(c,'upstream-1');c.options.onClose();
 await assert.rejects(waitRun(c,'upstream-1'),/not_ready/);
 c.options.onHelloOk({});await waitRun(c,'upstream-1');
 assert.deepEqual(c.calls.map(call=>call[0]),['agent.wait','agent.wait']);
});
test('close immediately after first hello cannot leave a disconnected client ready',async()=>{
 const connecting=connectGateway({url:'ws://127.0.0.1:12345',token:'private'},Client);
 await Promise.resolve();const c=Client.last;c.options.onHelloOk({});c.options.onClose();
 assert.equal(await connecting,c);
 await assert.rejects(submitRun(c,request,identity,'manager'),/not_ready/);
 assert.equal(c.calls.length,0);
});
