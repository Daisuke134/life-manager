'use strict';
const {createHmac,timingSafeEqual}=require('node:crypto');
const path=require('node:path');
const {buildMaritimeManagerCycleJob,buildMaritimeManagerReportJob}=require('./maritime-manager-runtime.js');
const {projectMaritimeSchedules}=require('./maritime-manager-schedules.js');
const {zoneOffsetHours,localDay}=require('./user-tz.js');
const {MANAGER_CONSENT_VERSION}=require('./maritime-distribution.js');
const UID=/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const ID=/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const SHA=/^[0-9a-f]{40}$/;
function check(value,pattern){if(typeof value!=='string'||!pattern.test(value))throw new Error('maritime_wake_identity_invalid');return value;}
function signingKey(secret){if(typeof secret!=='string'||secret.length<32||/[\r\n\0]/.test(secret))throw new Error('maritime_wake_config_invalid');return secret;}
function signature(payload,secret){return createHmac('sha256',signingKey(secret)).update('wake:v1:'+payload).digest('hex');}
function createMaritimeWakeBinding({uid,agentId,releaseSha},{secret,publicOrigin}){
 check(uid,UID);check(releaseSha,SHA);signingKey(secret);
 const origin=new URL(publicOrigin);
 if(origin.protocol!=='https:'||origin.username||origin.password||origin.search||origin.hash||origin.pathname!=='/')throw new Error('maritime_wake_origin_invalid');
 const url=origin.origin+'/api/internal/maritime/wake';
 if(agentId===undefined)return {url,token:'lmwb1_'+createHmac('sha256',secret).update(`bootstrap:v1:${uid}:${releaseSha}`).digest('hex')};
 check(agentId,ID);const payload=`${uid}.${agentId}.${releaseSha}`;
 return {url,token:`lmw1.${payload}.${signature(payload,secret)}`};
}
function verifyMaritimeWakeToken(token,secret){
 try{
  signingKey(secret);if(typeof token!=='string'||token.length>512)return null;
  const parts=token.split('.');if(parts.length!==5||parts[0]!=='lmw1')return null;
  const [,uid,agentId,releaseSha,sig]=parts;check(uid,UID);check(agentId,ID);check(releaseSha,SHA);
  if(!/^[0-9a-f]{64}$/.test(sig)||!timingSafeEqual(Buffer.from(sig,'hex'),Buffer.from(signature(`${uid}.${agentId}.${releaseSha}`,secret),'hex')))return null;
  return {uid,agentId,releaseSha};
 }catch{return null;}
}
function buildMaritimeInitialJobs(enrollment){
 const tenantId=check(enrollment?.uid,UID);const releaseSha=check(enrollment.release_sha,SHA);
 if(typeof enrollment.created_at!=='string'||!Number.isFinite(Date.parse(enrollment.created_at)))throw new Error('maritime_wake_enrollment_invalid');
 const createdAt=new Date(enrollment.created_at).toISOString();
 const cycle=buildMaritimeManagerCycleJob({tenantId,releaseSha,occurrenceId:'initial',dateKey:createdAt.slice(0,10)});
 const snapshot=projectMaritimeSchedules({tenantId,releaseSha,status:'active',pausedAt:null,nextEligibleAt:null,timezone:enrollment.timezone,nowMs:Date.parse(createdAt)});
 const reportAt=snapshot.schedules.find(entry=>entry.id===`lm-report:${tenantId}`).nextRunAt;
 const reportMs=Date.parse(reportAt);const day=localDay(reportMs,zoneOffsetHours(enrollment.timezone,reportMs));
 return {cycle:{job:cycle,availableAt:createdAt},report:{job:buildMaritimeManagerReportJob({tenantId,releaseSha,periodKey:`maritime:daily:${day}`}),availableAt:reportAt}};
}
function buildMaritimeReconsentJobs(enrollment){
 const tenantId=check(enrollment?.uid,UID);const releaseSha=check(enrollment.release_sha,SHA);
 if(enrollment.consent_version!==MANAGER_CONSENT_VERSION||typeof enrollment.consent_v2_at!=='string'
  ||!Number.isFinite(Date.parse(enrollment.consent_v2_at)))throw new Error('maritime_wake_reconsent_invalid');
 const consentAt=new Date(enrollment.consent_v2_at).toISOString();
 const cycle=buildMaritimeManagerCycleJob({tenantId,releaseSha,occurrenceId:'consent-v2-resume',dateKey:consentAt.slice(0,10)});
 const snapshot=projectMaritimeSchedules({tenantId,releaseSha,status:'active',pausedAt:null,nextEligibleAt:null,
  timezone:enrollment.timezone,nowMs:Date.parse(consentAt)});
 const reportAt=snapshot.schedules.find(entry=>entry.id===`lm-report:${tenantId}`)?.nextRunAt;
 const reportMs=Date.parse(reportAt);if(!Number.isFinite(reportMs))throw new Error('maritime_wake_reconsent_invalid');
 const day=localDay(reportMs,zoneOffsetHours(enrollment.timezone,reportMs));
 return {cycle:{job:cycle,availableAt:consentAt},report:{job:buildMaritimeManagerReportJob({tenantId,releaseSha,
  periodKey:`maritime:daily:${day}`}),availableAt:reportAt}};
}
function send(response,status,body){if(response.destroyed||response.writableEnded)return;response.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store'});response.end(JSON.stringify(body));}
async function wakeBody(request){
 if(String(request.headers?.['content-type']||'').split(';')[0].trim().toLowerCase()!=='application/json')throw new Error('body_invalid');
 const chunks=[];let bytes=0;
 for await(const chunk of request){const value=Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk);bytes+=value.length;if(bytes>4096){const error=new Error('body_too_large');error.status=413;throw error;}chunks.push(value);}
 const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
 if(!body||Array.isArray(body)||!['cycle','report'].includes(body.kind))throw new Error('body_invalid');
 return body.kind;
}
function registered(capability){
 const {loadLoopAdapterManifest}=require('./loop-adapter-registry.js');
 return loadLoopAdapterManifest(path.join(__dirname,'../config/loop-adapters.json')).adapters.some(entry=>entry.capability===capability);
}
async function handleMaritimeManagerWake(request,response,options={}){
 if(new URL(request.url||'/', 'http://localhost').pathname!=='/api/internal/maritime/wake')return false;
 if(request.method!=='POST'){send(response,405,{accepted:false,error:'method_not_allowed'});return true;}
 const env=options.env||process.env;const secret=env.LM_MARITIME_MANAGER_ID_SECRET;
 try{signingKey(secret);}catch{send(response,503,{accepted:false,error:'wake_unavailable'});return true;}
 const authorization=request.headers?.authorization;
 const identity=typeof authorization==='string'&&authorization.startsWith('Bearer ')?verifyMaritimeWakeToken(authorization.slice(7),secret):null;
 if(!identity){send(response,401,{accepted:false,error:'wake_unauthorized'});return true;}
 let kind;
 try{kind=await wakeBody(request);}catch(error){send(response,error.status===413?413:400,{accepted:false,error:'invalid_wake'});return true;}
 try{
  const store=options.managerStore||require('./maritime-manager-store.js').createMaritimeManagerStore({env});
  const enrollment=await store.read(identity.uid);
  if(!enrollment||enrollment.uid!==identity.uid||enrollment.agent_id!==identity.agentId||enrollment.release_sha!==identity.releaseSha){send(response,403,{accepted:false,error:'wake_binding_rejected'});return true;}
  if(enrollment.status!=='active'||enrollment.paused_at){send(response,409,{accepted:false,error:'manager_inactive'});return true;}
  if(enrollment.consent_version!==MANAGER_CONSENT_VERSION){send(response,409,{accepted:false,error:'manager_consent_required'});return true;}
  const plans=enrollment.consent_v2_at?buildMaritimeReconsentJobs(enrollment):buildMaritimeInitialJobs(enrollment);
  const plan=plans[kind];
  if(!(options.isCapabilityRegistered||registered)(plan.job.capability)){send(response,503,{accepted:false,error:'worker_capability_unavailable'});return true;}
  const queued=await (options.enqueueJobAt||require('./runtime-job-store.js').enqueueJobAt)(plan.job,plan.availableAt,options.storeOptions||{});
  if(typeof queued?.created!=='boolean'||queued.job?.job_id!==plan.job.job_id||queued.job?.tenant_id!==identity.uid
    || !['queued','running','reconciling','completed','dead_letter'].includes(queued.job.status))throw new Error('queue_receipt_invalid');
  if(queued.job.status==='dead_letter'){send(response,409,{accepted:false,error:'manager_reconciling'});return true;}
  send(response,202,{accepted:true,replayed:!queued.created});
 }catch{send(response,503,{accepted:false,error:'wake_unavailable'});}
 return true;
}
module.exports={createMaritimeWakeBinding,verifyMaritimeWakeToken,buildMaritimeInitialJobs,buildMaritimeReconsentJobs,handleMaritimeManagerWake};
