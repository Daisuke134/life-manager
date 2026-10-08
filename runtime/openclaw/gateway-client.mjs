// Thin RPC boundary. OpenClaw owns sockets, reconnect, sessions and execution.
const readyClients = new WeakSet();
const waitFields = new Set(['runId','status','startedAt','endedAt','error','stopReason',
  'livenessState','yielded','pendingError','timeoutPhase','providerStarted',
  'terminalDelivery','terminalReceipt','terminalReply']);
function required(value) { if(typeof value!=='string'||!value.trim())throw new Error('invalid_identity'); }
function scope(sessionKey,agentId) {
  required(sessionKey);required(agentId);
  if(!sessionKey.startsWith(`agent:${agentId}:lm:`))throw new Error('foreign_session');
}
function ready(client) {if(!readyClients.has(client))throw new Error('gateway_not_ready');}
export async function connectGateway({url,token,onEvent}, Client) {
  const target = new URL(url);
  if(target.protocol!=='ws:' || !['127.0.0.1','[::1]'].includes(target.hostname) || target.username || target.password || target.search || target.hash)throw new Error('invalid_gateway_url');
  required(token);
  if(!Client) ({GatewayClient:Client}=await import('@openclaw/gateway-client'));
  let client;let timer;
  try {
    await new Promise((resolve,reject)=>{
      timer=setTimeout(()=>reject(new Error('deadline')),5000);
      client=new Client({url,token,minProtocol:4,maxProtocol:4,onEvent,
        hostDeps:{logDebug:()=>{},logError:()=>{},redactForLog:()=> '[redacted]'},
        onHelloOk:()=>resolve(),onConnectError:()=>reject(new Error('connect_failed')),
        onClose:()=>{if(client)readyClients.delete(client);}});
      client.start();
    });
    readyClients.add(client);return client;
  } catch {
    if(client) {try{await client.stopAndWait({timeoutMs:1000});}catch{}}
    throw new Error('gateway_connect_failed');
  } finally {clearTimeout(timer);}
}
export async function submitRun(client,request,identity,agentId) {
  ready(client);scope(identity.sessionKey,agentId);required(identity.idempotencyKey);
  // Approved image encoding and owned thread fork must be implemented first.
  if(request.attachments.length || request.owned_resume_ref!==null)throw new Error('input_binding_not_ready');
  const params={message:request.prompt,agentId,sessionKey:identity.sessionKey,
    idempotencyKey:identity.idempotencyKey,deliver:false,timeout:request.timeout_seconds};
  let result;
  try {result=await client.request('agent',params,{expectFinal:false,timeoutMs:5000});}
  catch {throw new Error('dispatch_unknown');}
  if(!result || typeof result.runId!=='string' || !result.runId)throw new Error('dispatch_unknown');
  return {runId:result.runId};
}
export async function waitRun(client,runId) {
  ready(client);required(runId);
  let result;
  try {result=await client.request('agent.wait',{runId,timeoutMs:1000},{timeoutMs:5000});}
  catch {throw new Error('provider_status_unknown');}
  if(!result || result.runId!==runId || !['ok','error','timeout','pending'].includes(result.status) || Object.keys(result).some(k=>!waitFields.has(k)))throw new Error('provider_status_unknown');
  // A wait result is neither official provider readback nor claim release proof.
  return result;
}
export async function abortRun(client,{runId,sessionKey,agentId}) {
  ready(client);required(runId);scope(sessionKey,agentId);
  try{return await client.request('sessions.abort',{key:sessionKey,runId,agentId},{timeoutMs:5000});}
  catch{throw new Error('abort_unknown');}
}
export async function readSession(client,{sessionKey,agentId}) {
  ready(client);scope(sessionKey,agentId);
  let result;
  try {result=await client.request('sessions.list',{agentId,search:sessionKey,limit:100},{timeoutMs:5000});}
  catch {throw new Error('session_status_unknown');}
  const rows=result?.sessions?.filter(row=>row.key===sessionKey);
  if(!rows || rows.length!==1 || rows[0].agentId!==agentId)throw new Error('session_status_unknown');
  // The pinned public row schema has no authoritative activeRunIds. Do not
  // invent stop proof from absence; OC020 needs a supported lifecycle source.
  return {session:rows[0],liveness:'unknown'};
}
