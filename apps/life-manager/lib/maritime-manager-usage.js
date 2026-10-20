'use strict';
const {createMaritimeManagerLoopAdapter,createMaritimeManagerReportAdapter,createMaritimeManagerProvisionAdapter}=require('./maritime-manager-runtime.js');
async function observeMaritimeUsage(event,uid,operation,options={}){
 const controller=new AbortController();let timer;
 try{
  const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new Error('usage_timeout'));},options.usageTimeoutMs||2000);});
  const result=await Promise.race([Promise.resolve().then(()=>operation(controller.signal)),timeout]);
  if(result!==false)return true;
  throw new Error('usage_store_unconfirmed');
 }catch(error){
  const secret=(options.env||process.env).LM_UID_SECRET;
  const row={kind:'maritime_usage_unconfirmed',event,occurred_at:new Date().toISOString(),
   ...(secret&&uid?{participant_id:require('node:crypto').createHmac('sha256',secret).update(uid).digest('hex')} : {}),
   error_class:error?.message==='usage_timeout'?'usage_timeout':'usage_store_unconfirmed',retryable:true,next_action:'backfill_from_durable_evidence'};
  try{if(options.writeUsageDiagnostic)options.writeUsageDiagnostic(row);else process.stderr.write(JSON.stringify(row)+'\n');}catch{}
  return false;
 }finally{clearTimeout(timer);}
}
function scopedUsageOptions(options){
 if(!options.signal)return options;
 const fetchImpl=options.fetchImpl||globalThis.fetch;
 return {...options,fetchImpl:(url,init={})=>fetchImpl(url,{...init,signal:init.signal?AbortSignal.any([options.signal,init.signal]):options.signal})};
}
const UID=/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
async function context(uid,options){
 if(!UID.test(uid||''))throw new Error('maritime_usage_uid_invalid');
 const env=options.env||process.env;
 const managerStore=options.managerStore||require('./maritime-manager-store.js').createMaritimeManagerStore({env,fetchImpl:options.fetchImpl});
 const enrollment=await managerStore.read(uid,{signal:options.signal});
 options.signal?.throwIfAborted();
 if(enrollment&&enrollment.uid!==uid)throw new Error('maritime_usage_scope_invalid');
 let attribution=require('./web-attribution.js').sanitizeWebAttribution(options.attribution);
 try{const stored=await (options.readFirstTouch||require('./web-auth.js').readWebFirstTouchValue)(uid,{env,fetch:options.fetchImpl});if(Object.keys(stored||{}).length)attribution=stored;}catch{/* First-touch missing is not a fabricated conversion. */}
 const distributionStore=options.distributionStore||require('./maritime-distribution.js').createMaritimeDistributionStore({...options,env});
 return {env,enrollment,attribution,distributionStore,source:enrollment?.source||'other'};
}
async function emit(eventName,uid,ctx,{eventKey='once',occurredAt}={}){
 return ctx.distributionStore.recordManagerEvent(eventName,uid,{eventKey,occurredAt,source:ctx.source,attribution:ctx.attribution});
}
async function recordMaritimeEmailVerified(uid,options={}){
 options=scopedUsageOptions(options);
 try{const ctx=await context(uid,options);return await emit('maritime_email_verified',uid,ctx);}catch{return false;}
}
async function recordMaritimeManagerCompletion(job,receipt,options={}){
 options=scopedUsageOptions(options);
 try{
  if(job?.status!=='completed'||!UID.test(job.tenant_id||'')||job.completed_at==null)return false;
  const at=new Date(job.completed_at).toISOString();
  let eventName,eventKey='once';
  if(job.capability==='maritime.manager.cycle'){
   if(!createMaritimeManagerLoopAdapter().verify(receipt,job))return false;
   if(receipt.status!=='completed')return true;
   eventName='maritime_work_completed';eventKey=job.job_id;
  }else if(job.capability==='maritime.manager.report'){
   if(!createMaritimeManagerReportAdapter().verify(receipt,job))return false;
   eventName='maritime_report_sent';eventKey=receipt.period_key;
  }else if(job.capability==='maritime.manager.provision'){
   if(!createMaritimeManagerProvisionAdapter().verify(receipt,job))return false;
   if(receipt.phase!=='configure')return true;
   eventName='maritime_manager_activated';
  }else return true;
  const ctx=await context(job.tenant_id,options);
  if(!ctx.enrollment)return false;
  if(eventName==='maritime_manager_activated'&&(ctx.enrollment.status!=='active'||ctx.enrollment.paused_at||ctx.enrollment.agent_id!==receipt.agent_id))return true;
  return await emit(eventName,job.tenant_id,ctx,{eventKey,occurredAt:eventName==='maritime_report_sent'?new Date(receipt.sent_at).toISOString():at});
 }catch{return false;}
}
async function recordMaritimeManagerReturn(uid,options={}){
 options=scopedUsageOptions(options);
 try{
  if(/prefetch/i.test(String(options.request?.headers?.purpose||'')+' '+String(options.request?.headers?.['sec-purpose']||'')))return true;
  const ctx=await context(uid,options);if(!ctx.enrollment)return true;
  const base=String(ctx.env.SUPABASE_URL||'').replace(/\/$/,''),key=ctx.env.SUPABASE_SERVICE_ROLE_KEY;
  if(!base||!key)return false;
  const id=ctx.distributionStore.participantId(uid);if(!/^[0-9a-f]{64}$/.test(id||''))return false;
  const query=new URLSearchParams({source_object_id:'eq.'+id,event_name:'eq.maritime_work_completed',select:'occurred_at',order:'occurred_at.asc',limit:'1'});
  const response=await (options.fetchImpl||globalThis.fetch)(base+'/rest/v1/lm_web_funnel_events?'+query,{headers:{apikey:key,Authorization:'Bearer '+key},signal:AbortSignal.timeout(10000)});
  if(!response?.ok)return false;
  const rows=await response.json();if(!Array.isArray(rows)||rows.length>1)return false;
  if(!rows.length)return true;
  const first=Date.parse(rows[0].occurred_at),rawNow=(options.now||Date.now)(),nowMs=typeof rawNow==='string'?Date.parse(rawNow):Number(rawNow);
  if(!Number.isFinite(first)||!Number.isFinite(nowMs))return false;
  if(nowMs-first<86400000)return true;
  return await emit('maritime_returned',uid,ctx);
 }catch{return false;}
}
module.exports={observeMaritimeUsage,recordMaritimeEmailVerified,recordMaritimeManagerCompletion,recordMaritimeManagerReturn};
