"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { Readable } = require("node:stream");
let handleMaritimeManagerAuth, resolveMaritimeManagerUser, handleMaritimeManagerActivate, handleMaritimeManagerPage, handleMaritimeManagerStop;
try { ({ handleMaritimeManagerAuth, resolveMaritimeManagerUser, handleMaritimeManagerActivate, handleMaritimeManagerPage, handleMaritimeManagerStop } = require("./maritime-manager-auth.js")); }
catch (error) { if (error.code !== "MODULE_NOT_FOUND") throw error; }
let createMaritimeManagerDependencies;
try { ({ createMaritimeManagerDependencies } = require("./maritime-manager-dependencies.js")); }
catch (error) { if (error.code !== "MODULE_NOT_FOUND") throw error; }
const ORIGIN = "https://manager.example.invalid";
const SUBJECT = "11111111-1111-4111-8111-111111111111";
const USER = { id: SUBJECT, email: "person@example.invalid", email_confirmed_at: "2026-10-20T00:00:00Z",
  app_metadata: { provider: "google", providers: ["google"] }, identities: [{ provider: "google" }] };
function response() {
  const headers = {}; return { headers, statusCode: null, body: "", headersSent: false,
    setHeader(k,v) { headers[k.toLowerCase()] = v; }, getHeader(k) { return headers[k.toLowerCase()]; },
    writeHead(status, values={}) { this.statusCode=status;Object.assign(headers,values);this.headersSent=true; },
    end(body="") { this.body=String(body);this.headersSent=true; } };
}
function request(url, method="GET", body, headers={}) {
  const req=Readable.from(body===undefined?[]:[JSON.stringify(body)]);
  req.url=url;req.method=method;req.headers={origin:ORIGIN,"content-type":"application/json",...headers};return req;
}
function fixture({ user=USER }={}) {
  assert.equal(typeof handleMaritimeManagerAuth,"function","email auth handler must exist");
  const calls=[];
  const client={auth:{
    async getUser() { calls.push(["getUser"]);return {data:{user},error:null}; },
  }};
  const deps={env:{LM_MARITIME_MANAGER_EMAIL_ENABLED:"1",LM_UID_SECRET:"fixture-only-secret"},publicOrigin:ORIGIN,
    createClient:()=>client,ssr:{parseCookieHeader:s=>s.split(";").filter(Boolean).map(x=>({name:x.trim().split("=")[0],value:x.split("=")[1]}))},
    ensureWebUserImpl:async id=>{calls.push(["ensure",id]);return `lm_${id}`;}};
  return {calls,deps};
}
test("legacy_email_auth_endpoints_are_retired_even_when_legacy_flag_is_set",async()=>{
  for(const [path,method,body] of [["/auth/maritime/email","POST",{email:USER.email}],
    ["/auth/maritime/confirm?code=fixture-code","GET",undefined]]){
    const {deps,calls}=fixture();const res=response();
    await handleMaritimeManagerAuth(request(path,method,body),res,deps);
    assert.equal(res.statusCode,410);assert.deepEqual(JSON.parse(res.body),{error:"google_sign_in_required"});
    assert.deepEqual(calls,[]);
  }
});
test("the actual application server keeps both legacy email paths closed",async()=>{
  const {server}=require("../server.js");
  for(const [path,method] of [["/auth/maritime/email","POST"],["/auth/maritime/confirm?code=fixture-code","GET"]]){
    const req=request(path,method,method==="POST"?{email:USER.email}:undefined),res=response();
    let finish;const completed=new Promise(resolve=>{finish=resolve;});const end=res.end.bind(res);
    res.end=body=>{end(body);finish();};server.emit("request",req,res);await completed;
    assert.equal(res.statusCode,410);assert.deepEqual(JSON.parse(res.body),{error:"google_sign_in_required"});
  }
});
test("unverified_email_cannot_resolve_a_manager_user",async()=>{
  const {deps,calls}=fixture({user:{...USER,email_confirmed_at:null}});
  assert.equal(await resolveMaritimeManagerUser(request("/maritime/activate","POST"),response(),deps),null);
  assert.equal(calls.some(x=>x[0]==="ensure"),false);
});
test("confirmed_email_without_google_identity_cannot_resolve_or_activate_a_manager",async()=>{
  const emailOnly={...USER,app_metadata:{provider:"email",providers:["email"]},identities:[{provider:"email"}]};
  const {deps,calls}=fixture({user:emailOnly});
  assert.equal(await resolveMaritimeManagerUser(request("/maritime/activate","POST"),response(),deps),null);
  assert.equal(calls.some(x=>x[0]==="ensure"),false);
});
test("verified_identity_is_derived_from_auth_not_request_uid",async()=>{
  const {deps}=fixture();const req=request("/maritime?uid=other","POST",{uid:"other"});
  const user=await resolveMaritimeManagerUser(req,response(),deps);
  assert.equal(user.uid,`lm_${SUBJECT}`);assert.equal(user.subject,SUBJECT);assert.equal(user.email,USER.email);assert.match(user.csrf,/^[a-f0-9]{64}$/);
});
test("manager_session_requires_a_confirmed_google_provider_identity",async()=>{
  for(const user of [
    {...USER,app_metadata:{provider:"email",providers:["email"]},identities:[{provider:"email"}]},
    {...USER,app_metadata:{provider:"github",providers:["github"]},identities:[{provider:"github"}]},
  ]){
    const {deps,calls}=fixture({user});
    assert.equal(await resolveMaritimeManagerUser(request("/maritime/activate","POST"),response(),deps),null);
    assert.equal(calls.some(x=>x[0]==="ensure"),false);
  }
});

function activationFixture({capacityFull=false,user=USER}={}) {
  const f=fixture({user});const rows=new Map();const jobs=new Map();
  f.deps.env.LM_MARITIME_MANAGER_IMAGE_RELEASE_SHA="a".repeat(40);
  f.deps.readCommonReceipt=async()=>null;
  f.deps.withControlLock=async(_uid,operation)=>operation();
  f.deps.managerStore={read:async uid=>rows.get(uid)||null,enroll:async input=>{
    if(!rows.has(input.uid))rows.set(input.uid,{uid:input.uid,auth_subject:input.authSubject,email:input.email,status:"pending",release_sha:input.releaseSha});
    return rows.get(input.uid);}};
  f.deps.distributionStore={accept:async()=>capacityFull?{ok:false,status:"capacity_full"}:{ok:true,status:"consented"}};
  f.deps.enqueueJob=async job=>{
    const existing=jobs.get(job.job_id);
    if(existing)assert.deepEqual(job,existing);else jobs.set(job.job_id,job);
    return {created:!existing,job:{...job,status:"queued"}};};
  f.rows=rows;f.jobs=jobs;return f;
}
function activateRequest(deps,method="POST",csrf=true){
  const {createWebCsrfToken}=require("./web-auth.js");
  return request("/maritime/activate",method,{consentVersion:"maritime-manager-v1",source:"referral"},{
    "x-lm-web-csrf":csrf?createWebCsrfToken(`lm_${SUBJECT}`,deps.env.LM_UID_SECRET):"invalid"});
}
test("activate_post_enqueues_once_but_get_prefetch_does_not",async()=>{
  assert.equal(typeof handleMaritimeManagerActivate,"function");const {deps,jobs}=activationFixture();let res=response();
  await handleMaritimeManagerActivate(activateRequest(deps,"GET"),res,deps);assert.equal(res.statusCode,405);assert.equal(jobs.size,0);
  for(let i=0;i<2;i++){res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);assert.equal(res.statusCode,202);}
  assert.equal(jobs.size,1);const job=[...jobs.values()][0];assert.equal(job.tenant_id,`lm_${SUBJECT}`);assert.equal(job.capability,"maritime.manager.provision");
});
test("activation_requires_verified_identity_and_correct_csrf",async()=>{
  assert.equal(typeof handleMaritimeManagerActivate,"function");let f=activationFixture({user:null});let res=response();
  await handleMaritimeManagerActivate(activateRequest(f.deps),res,f.deps);assert.equal(res.statusCode,401);assert.equal(f.jobs.size,0);
  f=activationFixture();res=response();await handleMaritimeManagerActivate(activateRequest(f.deps,"POST",false),res,f.deps);
  assert.equal(res.statusCode,403);assert.equal(f.jobs.size,0);assert.equal(f.rows.size,0);
});
test("capacity_full_does_not_enroll_or_enqueue",async()=>{
  assert.equal(typeof handleMaritimeManagerActivate,"function");const {deps,jobs,rows}=activationFixture({capacityFull:true});const res=response();
  await handleMaritimeManagerActivate(activateRequest(deps),res,deps);assert.equal(res.statusCode,429);assert.equal(jobs.size,0);assert.equal(rows.size,0);
});
test("repeat_activation_uses_original_enrollment_release_for_stable_job",async()=>{
  assert.equal(typeof handleMaritimeManagerActivate,"function");const {deps,jobs}=activationFixture();
  await handleMaritimeManagerActivate(activateRequest(deps),response(),deps);deps.env.LM_MARITIME_MANAGER_IMAGE_RELEASE_SHA="b".repeat(40);
  const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
  assert.equal(res.statusCode,202);assert.equal(jobs.size,1);assert.equal([...jobs.values()][0].input_refs.release_ref,`release://git/${"a".repeat(40)}`);
});

test("paused_or_unknown_enrollment_does_not_request_new_provisioning",async()=>{
  for(const status of ["paused","effect_unknown"]){
    const {deps,rows,jobs}=activationFixture();rows.set(`lm_${SUBJECT}`,{uid:`lm_${SUBJECT}`,status,release_sha:"a".repeat(40)});
    let consentCalls=0;deps.distributionStore.accept=async()=>{consentCalls++;return {ok:true};};const res=response();
    await handleMaritimeManagerActivate(activateRequest(deps),res,deps);assert.equal(res.statusCode,409,status);assert.equal(jobs.size,0);assert.equal(consentCalls,0);
  }
});
test("failed_queue_request_preserves_enrollment_and_safe_retry_uses_one_job",async()=>{
  const {deps,rows,jobs}=activationFixture();const enqueue=deps.enqueueJob;let fail=true;
  deps.enqueueJob=async job=>{if(fail){fail=false;throw new Error("private queue failure");}return enqueue(job);};
  let res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
  assert.equal(res.statusCode,503);assert.equal(rows.size,1);assert.equal(jobs.size,0);assert.doesNotMatch(res.body,/private queue/);
  res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);assert.equal(res.statusCode,202);assert.equal(jobs.size,1);
});

test("terminal_or_reconciling_provision_jobs_are_not_reported_as_pending",async()=>{
  for(const [status,expected] of [["dead_letter",503],["reconciling",409],["completed",409]]){
    const {deps}=activationFixture();deps.enqueueJob=async job=>({created:false,job:{...job,status}});const res=response();
    await handleMaritimeManagerActivate(activateRequest(deps),res,deps);assert.equal(res.statusCode,expected,status);assert.doesNotMatch(res.body,/"status":"pending"/,status);
  }
});
test("completed_provision_job_requires_active_enrollment_and_configure_receipt",async()=>{
  const {deps,rows}=activationFixture();deps.enqueueJob=async job=>{const row=rows.get(`lm_${SUBJECT}`);row.status="active";row.agent_id="agent-a";return {created:false,job:{...job,status:"completed"}};};
  deps.readCommonReceipt=async()=>({outcome:"verified",provider:"maritime",loop_id:"maritime.manager",external_ref:"maritime-agent://agent-a",evidence_refs:["maritime-agent://agent-a"]});
  const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);assert.equal(res.statusCode,200);assert.equal(JSON.parse(res.body).status,"active");
});

test("email_campaign_page_is_independent_of_telegram_and_get_never_enrolls",async()=>{
  assert.equal(typeof handleMaritimeManagerPage,"function");const {deps,calls}=fixture({user:null});let events=0;deps.distributionStore={recordAnonymousEvent:async()=>{events++;return true;}};const res=response();
  await handleMaritimeManagerPage(request("/maritime?source=referral&lang=en"),res,deps);assert.equal(res.statusCode,200);assert.match(res.body,/href="\/auth\/google\?intent=maritime_cloud&lang=en"/);assert.doesNotMatch(res.body,/auth\/maritime\/email|start_calendar=1/);assert.equal(events,1);assert.equal(calls.some(x=>x[0]==="ensure"),false);
});
test("google_OAuth_failure_is_rendered_on_the_same_localized_Cloud_page",async()=>{
  const {deps}=fixture({user:null});deps.distributionStore={recordAnonymousEvent:async()=>true};const res=response();
  await handleMaritimeManagerPage(request("/maritime?auth_error=connection&lang=ja"),res,deps);
  assert.match(res.body,/Googleログインを完了できませんでした。もう一度お試しください。/);
});
test("verified_campaign_page_displays_activation_or_persisted_state_without_dispatch",async()=>{
  assert.equal(typeof handleMaritimeManagerPage,"function");const {deps}=fixture();deps.distributionStore={recordAnonymousEvent:async()=>true};deps.managerStore={read:async()=>null};let res=response();
  await handleMaritimeManagerPage(request("/maritime?lang=ja"),res,deps);assert.match(res.body,/<button[^>]+data-action="activate"/);
  deps.managerStore.read=async()=>({status:"effect_unknown"});res=response();await handleMaritimeManagerPage(request("/maritime?lang=ja"),res,deps);
  assert.doesNotMatch(res.body,/<button[^>]+data-action="activate"/);assert.match(res.body,/実行結果を確認中/);
});

test("active_cloud_page_shows_only_verified_work_and_email_receipts",async()=>{
 const {deps}=fixture();const uid=`lm_${SUBJECT}`,sha="a".repeat(40);
 deps.distributionStore={recordAnonymousEvent:async()=>true};
 deps.managerStore={read:async()=>({uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",agent_id:"agent-a",release_sha:sha})};
 deps.readCommonReceipt=async()=>({outcome:"verified",provider:"maritime",loop_id:"maritime.manager",
  external_ref:"maritime-agent://agent-a",evidence_refs:["maritime-agent://agent-a"]});
 const cycle={...require("./maritime-manager-runtime.js").buildMaritimeManagerCycleJob({tenantId:uid,releaseSha:sha,occurrenceId:"cycle-1",dateKey:"2026-10-25"}),status:"completed",attempt:1};
 const cycleReceipt={schema_version:1,kind:"maritime_manager_cycle",tenant_id:uid,job_id:cycle.job_id,occurrence_id:"cycle-1",
  date_key:"2026-10-25",release_sha:sha,agent_id:"agent-a",execution_id:"execution-1",status:"completed",
  artifact_refs:["artifact://cycle-1/result.md","artifact://cycle-1/metrics.json"],error_class:null,provider:"maritime",
  external_ref:"maritime-execution://agent-a/execution-1",evidence_refs:["maritime-execution://agent-a/execution-1"]};
 const report={...require("./maritime-manager-runtime.js").buildMaritimeManagerReportJob({tenantId:uid,releaseSha:sha,periodKey:"maritime:daily:2026-10-25"}),status:"completed",attempt:1};
 const reportReceipt={schema_version:1,kind:"maritime_manager_report",status:"completed",provider:"resend",tenant_id:uid,
  job_id:report.job_id,period_key:"maritime:daily:2026-10-25",release_sha:sha,provider_message_id:"message-1",
  recipient_hash:"b".repeat(64),snapshot_hash:"c".repeat(64),sent_at:"2026-10-25T11:00:00.000Z",
  external_ref:"resend-email://message-1",evidence_refs:["resend-email://message-1"]};
 deps.query=async(sql,values)=>{assert.match(sql,/jobs\.tenant_id\s*=\s*\$1/);assert.match(sql,/PARTITION BY jobs\.capability/);assert.deepEqual(values,[uid,10]);return {rows:[
  {job:report,receipt:reportReceipt,observed_at:"2026-10-25T11:00:00.000Z"},
  {job:cycle,receipt:cycleReceipt,observed_at:"2026-10-25T10:00:00.000Z"},
 ]};};
 const res=response();await handleMaritimeManagerPage(request("/maritime?lang=en"),res,deps);
 assert.equal(res.statusCode,200);assert.match(res.body,/Verified work/);assert.match(res.body,/2 files/);
 assert.match(res.body,/Verified email report sent/);assert.match(res.body,/This activity feed does not verify income earned by Life Manager/);
});

test("active_cloud_page_renders_dead_letter_cycle_as_failed_not_pending",async()=>{
 const {deps}=fixture();const uid=`lm_${SUBJECT}`,sha="a".repeat(40);
 deps.distributionStore={recordAnonymousEvent:async()=>true};
 deps.managerStore={read:async()=>({uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",agent_id:"agent-a",release_sha:sha})};
 deps.readCommonReceipt=async()=>({outcome:"verified",provider:"maritime",loop_id:"maritime.manager",
  external_ref:"maritime-agent://agent-a",evidence_refs:["maritime-agent://agent-a"]});
 const cycle={...require("./maritime-manager-runtime.js").buildMaritimeManagerCycleJob({tenantId:uid,releaseSha:sha,occurrenceId:"cycle-1",dateKey:"2026-10-25"}),status:"dead_letter",attempt:1};
 deps.query=async()=>({rows:[{job:cycle,receipt:null,observed_at:"2026-10-25T10:00:00.000Z"}]});
 const res=response();await handleMaritimeManagerPage(request("/maritime?lang=en"),res,deps);
 assert.equal(res.statusCode,200);assert.match(res.body,/This run did not complete/);assert.doesNotMatch(res.body,/Result confirmation is pending|Verified work/);
});

test("dead_letter_email_report_is_rendered_as_failed_not_pending",async()=>{
 const {deps}=fixture();const uid=`lm_${SUBJECT}`,sha="a".repeat(40);
 deps.distributionStore={recordAnonymousEvent:async()=>true};
 deps.managerStore={read:async()=>({uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",agent_id:"agent-a",release_sha:sha})};
 deps.readCommonReceipt=async()=>({outcome:"verified",provider:"maritime",loop_id:"maritime.manager",
  external_ref:"maritime-agent://agent-a",evidence_refs:["maritime-agent://agent-a"]});
 const report={...require("./maritime-manager-runtime.js").buildMaritimeManagerReportJob({tenantId:uid,releaseSha:sha,
  periodKey:"maritime:daily:2026-10-25"}),status:"dead_letter",attempt:1};
 deps.query=async()=>({rows:[{job:report,receipt:null,observed_at:"2026-10-25T10:00:00.000Z"}]});
 const res=response();await handleMaritimeManagerPage(request("/maritime?lang=en"),res,deps);
 assert.equal(res.statusCode,200);assert.match(res.body,/Email report delivery could not be verified/);
 assert.doesNotMatch(res.body,/Email report delivery is being checked/);
});

test('manager activation pins the VM image release independently of the central app release',async()=>{
  const {deps,rows}=activationFixture();deps.env.LM_RELEASE_SHA='b'.repeat(40);deps.env.LM_MARITIME_MANAGER_IMAGE_RELEASE_SHA='c'.repeat(40);
  const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);assert.equal(res.statusCode,202);assert.equal([...rows.values()][0].release_sha,'c'.repeat(40));
});
test('an app deployment SHA alone cannot label an unconfigured VM image release',async()=>{
  const {deps,rows,jobs}=activationFixture();deps.env.LM_RELEASE_SHA='b'.repeat(40);delete deps.env.LM_MARITIME_MANAGER_IMAGE_RELEASE_SHA;
  const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);assert.equal(res.statusCode,503);assert.equal(rows.size,0);assert.equal(jobs.size,0);
});


test("bound enrollment stays preparing until configure completion is committed",async()=>{
 const {deps,rows}=activationFixture();const uid=`lm_${SUBJECT}`;
 rows.set(uid,{uid,status:"active",agent_id:"agent-a",release_sha:"a".repeat(40)});
 let receipt=null,reads=0;
 deps.readCommonReceipt=async input=>{reads++;assert.equal(input.tenantId,uid);assert.equal(input.attempt,1);return receipt;};
 let res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
 assert.equal(res.statusCode,202);assert.equal(JSON.parse(res.body).status,"pending");assert.equal(reads,1);
 receipt={outcome:"verified",provider:"maritime",loop_id:"maritime.manager",external_ref:"maritime-agent://agent-a",evidence_refs:["maritime-agent://agent-a"]};
 res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
 assert.equal(res.statusCode,200);assert.equal(JSON.parse(res.body).status,"active");
 deps.distributionStore.recordAnonymousEvent=async()=>{};
 receipt=null;res=response();await handleMaritimeManagerPage(request('/maritime?lang=ja'),res,deps);
 assert.equal(res.statusCode,200);assert.doesNotMatch(res.body,/稼働中/);
});


test("stop authenticates the cookie, pauses first and durably queues cleanup without deleting data",async()=>{
 const {deps,rows,jobs}=activationFixture();const uid=`lm_${SUBJECT}`;let pauses=0;
 rows.set(uid,{uid,status:"active",agent_id:"agent-a",release_sha:"a".repeat(40)});
 deps.managerStore.pause=async input=>{assert.equal(input,uid);pauses++;Object.assign(rows.get(uid),{status:"paused",paused_at:"2026-10-21T00:00:00.000Z"});return rows.get(uid);};
 const csrf=require('./web-auth.js').createWebCsrfToken(uid,deps.env.LM_UID_SECRET);
 let res=response();await handleMaritimeManagerStop(request('/maritime/stop','POST',{}),res,deps);assert.equal(res.statusCode,403);assert.equal(pauses,0);
 res=response();await handleMaritimeManagerStop(request('/maritime/stop','POST',{uid:'foreign'},{'x-lm-web-csrf':csrf}),res,deps);assert.equal(res.statusCode,400);assert.equal(pauses,0);
 res=response();await handleMaritimeManagerStop(request('/maritime/stop','POST',{}, {'x-lm-web-csrf':csrf}),res,deps);
 assert.equal(res.statusCode,202);assert.equal(JSON.parse(res.body).status,'paused');assert.equal(JSON.parse(res.body).cleanupPending,true);
 assert.equal(pauses,1);assert.equal(jobs.size,1);assert.equal([...jobs.values()][0].input_refs.provision_phase_ref,'maritime-provision-phase://pause');
 res=response();await handleMaritimeManagerStop(request('/maritime/stop','POST',{}, {'x-lm-web-csrf':csrf}),res,deps);assert.equal(jobs.size,1);assert.equal(rows.has(uid),true);
});


test("late activation cannot restore consent after the serialized stop cleanup",async()=>{
 const {deps,rows}=activationFixture();const uid=`lm_${SUBJECT}`,sha='a'.repeat(40);rows.set(uid,{uid,status:'pending',agent_id:null,release_sha:sha});
 let tail=Promise.resolve();const lock=async(_uid,operation)=>{const previous=tail;let done;tail=new Promise(resolve=>{done=resolve;});await previous;try{return await operation();}finally{done();}};
 deps.withControlLock=lock;let enter,release;const entered=new Promise(resolve=>{enter=resolve;}),gate=new Promise(resolve=>{release=resolve;});let consent=true;
 deps.distributionStore.accept=async()=>{enter();await gate;consent=true;return {ok:true};};
 deps.managerStore.pause=async()=>Object.assign(rows.get(uid),{status:'paused',paused_at:'2026-10-21T00:00:01.000Z'});
 const activation=handleMaritimeManagerActivate(activateRequest(deps),response(),deps);await entered;
 const stop=response(),csrf=require('./web-auth.js').createWebCsrfToken(uid,deps.env.LM_UID_SECRET);
 await handleMaritimeManagerStop(request('/maritime/stop','POST',{}, {'x-lm-web-csrf':csrf}),stop,deps);
 const runtime=require('./maritime-manager-runtime.js');const adapter=runtime.createMaritimeManagerProvisionAdapter({managerStore:deps.managerStore,withControlLock:lock,isConsentRevoked:async()=>!consent,revokeConsent:async()=>{consent=false;}});
 const cleanup=adapter.reconcile(runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha:sha,phase:'pause'}));
 const early=await Promise.race([cleanup.then(()=>true),new Promise(resolve=>setTimeout(()=>resolve(false),15))]);release();await activation;assert.equal((await cleanup).state,'present');assert.equal(early,false);assert.equal(consent,false);
});


test("manager activation forwards only sanitized first touch through the existing writer",async()=>{
 const {deps}=activationFixture(),stored=[];deps.storeFirstTouch=async(uid,attribution)=>{stored.push({uid,attribution});return true;};
 const csrf=require('./web-auth.js').createWebCsrfToken(`lm_${SUBJECT}`,deps.env.LM_UID_SECRET),res=response();
 await handleMaritimeManagerActivate(request('/maritime/activate','POST',{consentVersion:'maritime-manager-v1',source:'instagram',attribution:{utm_source:'instagram',utm_medium:'dm',email:'private@example.invalid',token:'private-token'}},{'x-lm-web-csrf':csrf}),res,deps);
 assert.equal(res.statusCode,202);assert.deepEqual(stored,[{uid:`lm_${SUBJECT}`,attribution:{utm_source:'instagram',utm_medium:'dm'}}]);
});

test('authenticated return failure records an unconfirmed observation without changing HTTP success',async()=>{
 const {deps}=fixture(),logs=[];deps.managerStore={read:async()=>null};
 deps.distributionStore={recordAnonymousEvent:async()=>true};deps.recordReturn=async()=>false;
 deps.writeUsageDiagnostic=row=>logs.push(row);const res=response();
 await handleMaritimeManagerPage(request('/maritime'),res,deps);await new Promise(resolve=>setImmediate(resolve));
 assert.equal(res.statusCode,200);assert.equal(logs[0].event,'returned');assert.equal(logs[0].error_class,'usage_store_unconfirmed');
 assert.doesNotMatch(JSON.stringify(logs),/person@|lm_11111111/);
});

test("server manager dependencies share the supplied Runtime PG pool", async () => {
  assert.equal(typeof createMaritimeManagerDependencies, "function");
  const subject = "11111111-1111-4111-8111-111111111111";
  const uid = require("./web-auth.js").separateWebUidForSubject(subject);
  const queries = [];
  const pgPool = { async query(statement, values = []) {
    queries.push({ statement, values });
    if (statement.includes("SELECT uid,auth_subject FROM public.lm_maritime_manager_identities")) {
      return { rows: [{ uid, auth_subject: subject }] };
    }
    return { rows: [] };
  } };
  const dependencies = createMaritimeManagerDependencies({ pgPool, env: { LM_UID_SECRET: "fixture-only-secret" } });
  assert.equal(typeof dependencies.query, "function");
  assert.deepEqual(await dependencies.query("SELECT 1", []), { rows: [] });
  assert.equal(queries.at(-1).statement, "SELECT 1");
  assert.equal(dependencies.distributionStore, dependencies.managerPersistence);
  assert.equal(dependencies.cfoReceiptIO, dependencies.managerPersistence.cfoReceiptIO);
  assert.equal(await dependencies.managerStore.read(uid), null);
  assert.equal(await dependencies.ensureWebUserImpl(subject), uid);
  assert.equal(queries.length, 4);
  assert.equal(queries[0].statement, "SELECT 1");
  assert.match(queries[1].statement, /lm_maritime_manager_enrollments/);
  assert.deepEqual(queries[1].values, [uid]);
  assert.match(queries[2].statement, /lm_maritime_manager_identities/);
  assert.match(queries[3].statement, /lm_maritime_manager_identities/);
});
