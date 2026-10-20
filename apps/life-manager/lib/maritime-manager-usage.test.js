'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const runtime=require('./maritime-manager-runtime.js');
const UID='lm_11111111-1111-4111-8111-111111111111',SHA='a'.repeat(40);
function options(){const events=[];return {events,managerStore:{read:async()=>({uid:UID,status:'active',paused_at:null,agent_id:'agent-a',source:'instagram'})},readFirstTouch:async()=>({utm_source:'instagram',utm_medium:'dm'}),distributionStore:{participantId:()=> 'b'.repeat(64),recordManagerEvent:async(...args)=>{events.push(args);return true;}},now:()=>Date.parse('2026-10-23T01:00:00Z')};}
function completedCycle(){const job={...runtime.buildMaritimeManagerCycleJob({tenantId:UID,releaseSha:SHA,occurrenceId:'first',dateKey:'2026-10-21'}),status:'completed',completed_at:'2026-10-21T01:00:00.000Z'};const ref='maritime-execution://agent-a/exec-a';return {job,receipt:{schema_version:1,kind:'maritime_manager_cycle',tenant_id:UID,job_id:job.job_id,occurrence_id:'first',date_key:'2026-10-21',release_sha:SHA,agent_id:'agent-a',execution_id:'exec-a',status:'completed',artifact_refs:['artifact://original/product.md'],error_class:null,provider:'maritime',external_ref:ref,evidence_refs:[ref]}};}
test('manager usage is not signup or a deferred job and does not include private content',async()=>{
 const usage=require('./maritime-manager-usage.js'),deps=options();
 await usage.recordMaritimeEmailVerified(UID,deps);assert.equal(deps.events[0][0],'maritime_email_verified');
 const {job,receipt}=completedCycle();await usage.recordMaritimeManagerCompletion(job,receipt,deps);
 assert.equal(deps.events[1][0],'maritime_work_completed');assert.equal(deps.events[1][2].eventKey,job.job_id);assert.equal(deps.events[1][2].attribution.utm_medium,'dm');
 assert.doesNotMatch(JSON.stringify(deps.events),/example.invalid|private-body|private-token/);
 const before=deps.events.length;
 await usage.recordMaritimeManagerCompletion({...job,status:'running'},receipt,deps);assert.equal(deps.events.length,before);
 const deferred={...receipt,status:'deferred',artifact_refs:[],error_class:'no_work'};
 await usage.recordMaritimeManagerCompletion(job,deferred,deps);assert.equal(deps.events.length,before);
});
test('return requires a prior completed work day and skips authenticated prefetch',async()=>{
 const usage=require('./maritime-manager-usage.js'),deps=options();
 deps.env={SUPABASE_URL:'https://fixture.invalid',SUPABASE_SERVICE_ROLE_KEY:'fixture'};
 let fetches=0;deps.fetchImpl=async url=>{fetches++;const u=new URL(url);assert.equal(u.searchParams.get('source_object_id'),'eq.'+'b'.repeat(64));assert.equal(u.searchParams.get('select'),'occurred_at');return new Response(JSON.stringify([{occurred_at:'2026-10-21T01:00:00Z'}]));};
 await usage.recordMaritimeManagerReturn(UID,{...deps,request:{headers:{'sec-purpose':'prefetch'}}});assert.equal(fetches,0);assert.equal(deps.events.length,0);
 await usage.recordMaritimeManagerReturn(UID,{...deps,now:()=>Date.parse('2026-10-21T02:00:00Z')});assert.equal(deps.events.length,0);
 await usage.recordMaritimeManagerReturn(UID,deps);assert.equal(deps.events[0][0],'maritime_returned');
});


test('activation and accepted email use their own verified completion receipts',async()=>{
 const usage=require('./maritime-manager-usage.js'),deps=options(),time='2026-10-21T01:00:00.000Z';
 const provision={...runtime.buildMaritimeManagerProvisionJob({tenantId:UID,releaseSha:SHA,phase:'configure'}),status:'completed',completed_at:time};
 const ref='maritime-agent://agent-a';const configured={schema_version:1,kind:'maritime_manager_provision',status:'completed',provider:'maritime',tenant_id:UID,job_id:provision.job_id,release_sha:SHA,phase:'configure',agent_id:'agent-a',schedule_sha256:'b'.repeat(64),external_ref:ref,evidence_refs:[ref]};
 assert.equal(await usage.recordMaritimeManagerCompletion(provision,configured,deps),true);
 assert.equal(deps.events[0][0],'maritime_manager_activated');
 const report={...runtime.buildMaritimeManagerReportJob({tenantId:UID,releaseSha:SHA,periodKey:'maritime:daily:2026-10-21'}),status:'completed',completed_at:time};
 const mail={schema_version:1,kind:'maritime_manager_report',status:'completed',provider:'resend',tenant_id:UID,job_id:report.job_id,period_key:'maritime:daily:2026-10-21',release_sha:SHA,provider_message_id:'mail-a',recipient_hash:'a'.repeat(64),snapshot_hash:'b'.repeat(64),sent_at:time,external_ref:'resend-email://mail-a',evidence_refs:['resend-email://mail-a']};
 assert.equal(await usage.recordMaritimeManagerCompletion(report,mail,deps),true);assert.equal(deps.events[1][0],'maritime_report_sent');
 assert.equal(await usage.recordMaritimeManagerCompletion(report,{...mail,tenant_id:'foreign'},deps),false);assert.equal(deps.events.length,2);
});
