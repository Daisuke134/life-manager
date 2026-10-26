"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { Readable } = require("node:stream");
let handleMaritimeManagerAuth, resolveMaritimeManagerUser, handleMaritimeManagerActivate, handleMaritimeManagerPage, handleMaritimeManagerStop, handleMaritimeManagerCapafyConnection;
try { ({ handleMaritimeManagerAuth, resolveMaritimeManagerUser, handleMaritimeManagerActivate, handleMaritimeManagerPage, handleMaritimeManagerStop,
  handleMaritimeManagerCapafyConnection } = require("./maritime-manager-auth.js")); }
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
  const f=fixture({user});const rows=new Map();const jobs=new Map();const provisionStates=new Map();
  f.deps.env.LM_MARITIME_MANAGER_IMAGE_RELEASE_SHA="a".repeat(40);
  f.deps.readCommonReceipt=async()=>null;
  f.deps.withControlLock=async(_uid,operation)=>operation();
  f.deps.managerStore={read:async uid=>rows.get(uid)||null,enroll:async input=>{
    if(!rows.has(input.uid))rows.set(input.uid,{uid:input.uid,auth_subject:input.authSubject,email:input.email,status:"pending",
      consent_version:input.consentVersion,release_sha:input.releaseSha});
    return rows.get(input.uid);},reconsent:async input=>{
      const row=rows.get(input.uid);
      if(!row||row.auth_subject!==input.authSubject||!["pending","provisioning","active"].includes(row.status)||row.paused_at)return null;
      row.consent_version=input.consentVersion;row.consent_v2_at ||= "2026-10-26T02:00:00.000Z";return row;
    }};
  f.deps.distributionStore={accept:async()=>capacityFull?{ok:false,status:"capacity_full"}:{ok:true,status:"consented"}};
  f.deps.enqueueJob=async job=>{
    const existing=jobs.get(job.job_id);
    if(existing)assert.deepEqual(job,existing);else jobs.set(job.job_id,job);
    return {created:!existing,job:{...job,status:"queued"}};};
  f.deps.enqueueJobAt=async (job,availableAt)=>{
    const existing=jobs.get(job.job_id);
    if(existing){assert.equal(job.job_id,existing.job_id);assert.equal(job.tenant_id,existing.tenant_id);assert.equal(existing.available_at,availableAt);}
    else jobs.set(job.job_id,{...job,available_at:availableAt});
    return {created:!existing,job:{...job,available_at:availableAt,status:"queued"}};
  };
  f.deps.readProvisionJobState=async ({job})=>provisionStates.get(job.job_id)||null;
  f.deps.nowMs=Date.parse("2026-10-26T02:00:00.000Z");
  f.rows=rows;f.jobs=jobs;f.provisionStates=provisionStates;return f;
}
function activateRequest(deps,method="POST",csrf=true){
  const {createWebCsrfToken}=require("./web-auth.js");
  return request("/maritime/activate",method,{consentVersion:"maritime-manager-v2",source:"referral"},{
    "x-lm-web-csrf":csrf?createWebCsrfToken(`lm_${SUBJECT}`,deps.env.LM_UID_SECRET):"invalid"});
}
test("activate_post_enqueues_once_but_get_prefetch_does_not",async()=>{
  assert.equal(typeof handleMaritimeManagerActivate,"function");const {deps,jobs,rows}=activationFixture();let res=response();
  await handleMaritimeManagerActivate(activateRequest(deps,"GET"),res,deps);assert.equal(res.statusCode,405);assert.equal(jobs.size,0);
  for(let i=0;i<2;i++){res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);assert.equal(res.statusCode,202);}
  assert.equal(jobs.size,1);const job=[...jobs.values()][0];assert.equal(job.tenant_id,`lm_${SUBJECT}`);assert.equal(job.capability,"maritime.manager.provision");
  assert.equal([...rows.values()][0].email, USER.email);
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

test("legacy_active_enrollment_requires_new_consent_without_reprovisioning",async()=>{
  const {deps,rows,jobs}=activationFixture();const uid=`lm_${SUBJECT}`;let accepted=0,reconsented=0;
  rows.set(uid,{uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",source:"direct",
    consent_version:"maritime-manager-v1",agent_id:"agent-a",release_sha:"a".repeat(40),paused_at:null});
  deps.distributionStore.accept=async()=>{accepted++;return {ok:true,status:"consented"};};
  const reconsent=deps.managerStore.reconsent;
  deps.managerStore.reconsent=async input=>{reconsented++;return reconsent(input);};
  deps.readCommonReceipt=async()=>({outcome:"verified",provider:"maritime",loop_id:"maritime.manager",
    external_ref:"maritime-agent://agent-a",evidence_refs:["maritime-agent://agent-a"]});
  const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
  assert.equal(res.statusCode,200);assert.equal(JSON.parse(res.body).status,"active");
  assert.equal(rows.get(uid).consent_version,"maritime-manager-v2");
  assert.equal(accepted,1);assert.equal(reconsented,1);assert.equal(jobs.size,2);
  assert.deepEqual(new Set([...jobs.values()].map(job=>job.capability)),new Set(["maritime.manager.cycle","maritime.manager.report"]));
  assert.equal([...jobs.values()].every(job=>job.tenant_id===uid&&job.input_refs.release_ref===`release://git/${"a".repeat(40)}`),true);
});

test("active_v2_retry_recreates_both_resume_jobs_from_the_persisted_anchor_after_partial_enqueue",async()=>{
 const {deps,rows,jobs}=activationFixture();const uid=`lm_${SUBJECT}`;let fail=true;
 rows.set(uid,{uid,auth_subject:SUBJECT,email:USER.email,timezone:"Asia/Tokyo",status:"active",source:"direct",
  consent_version:"maritime-manager-v1",agent_id:"agent-a",release_sha:"a".repeat(40),paused_at:null});
 deps.readCommonReceipt=async()=>({outcome:"verified",provider:"maritime",loop_id:"maritime.manager",
  external_ref:"maritime-agent://agent-a",evidence_refs:["maritime-agent://agent-a"]});
 const enqueueAt=deps.enqueueJobAt;deps.enqueueJobAt=async(job,at)=>{
  if(job.capability==="maritime.manager.cycle"&&fail){fail=false;throw new Error("temporary queue failure");}
  return enqueueAt(job,at);
 };
 let res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
 assert.equal(res.statusCode,503);assert.equal(rows.get(uid).consent_version,"maritime-manager-v2");
 assert.equal(jobs.size,1);const anchor=rows.get(uid).consent_v2_at;const reportId=[...jobs.keys()][0];
 deps.nowMs=Date.parse("2026-10-27T00:30:00.000Z");
 res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
 assert.equal(res.statusCode,200);assert.equal(rows.get(uid).consent_v2_at,anchor);assert.equal(jobs.size,2);
 assert.equal(jobs.has(reportId),true);assert.deepEqual(new Set([...jobs.values()].map(job=>job.capability)),new Set(["maritime.manager.cycle","maritime.manager.report"]));
});

test("legacy_pending_or_provisioning_enrollment_requires_consent_refresh_before_retrying_one_provision_job",async()=>{
 for(const status of ["pending","provisioning"]){
  const {deps,rows,jobs}=activationFixture();const uid=`lm_${SUBJECT}`;let accepted=0,reconsented=0;
  rows.set(uid,{uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status,source:"direct",
   consent_version:"maritime-manager-v1",agent_id:null,release_sha:"c".repeat(40),paused_at:null});
  const accept=deps.distributionStore.accept;deps.distributionStore.accept=async(...args)=>{accepted++;return accept(...args);};
  const reconsent=deps.managerStore.reconsent;deps.managerStore.reconsent=async input=>{reconsented++;return reconsent(input);};
  const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
  assert.equal(res.statusCode,202,status);assert.equal(rows.get(uid).consent_version,"maritime-manager-v2",status);
  assert.equal(rows.get(uid).release_sha,"c".repeat(40),status);assert.equal(accepted,1,status);assert.equal(reconsented,1,status);
  assert.equal(jobs.size,1,status);assert.equal([...jobs.values()][0].input_refs.release_ref,`release://git/${"c".repeat(40)}`,status);
 }
});

test("legacy_pending_reconsent_restarts_only_a_known_no_effect_dead_letter_with_a_new_stable_job",async()=>{
 const {deps,rows,jobs,provisionStates}=activationFixture();const uid=`lm_${SUBJECT}`,releaseSha="c".repeat(40);
 rows.set(uid,{uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"pending",source:"direct",
  consent_version:"maritime-manager-v1",agent_id:null,release_sha:releaseSha,paused_at:null});
 const runtime=require("./maritime-manager-runtime.js");
 const original=runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha});
 provisionStates.set(original.job_id,{job_id:original.job_id,tenant_id:uid,status:"dead_letter",attempt:1,
  last_error_code:"MARITIME_PROVISION_CONSENT_REQUIRED"});
 const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
 assert.equal(res.statusCode,202);assert.equal(jobs.size,1);
 const resumed=[...jobs.values()][0];assert.notEqual(resumed.job_id,original.job_id);
 assert.equal(resumed.input_refs.provision_resume_ref,`maritime-provision-resume://${encodeURIComponent("2026-10-26T02:00:00.000Z")}`);
 assert.notEqual(resumed.effect_key,original.effect_key);
});

test("legacy provision recovery refuses dead letters without the exact no-effect consent guard",async()=>{
 const {deps,rows,jobs,provisionStates}=activationFixture();const uid=`lm_${SUBJECT}`,releaseSha="c".repeat(40);
 rows.set(uid,{uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"pending",source:"direct",
  consent_version:"maritime-manager-v1",agent_id:null,release_sha:releaseSha,paused_at:null});
 const original=require("./maritime-manager-runtime.js").buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha});
 provisionStates.set(original.job_id,{job_id:original.job_id,tenant_id:uid,status:"dead_letter",attempt:1,last_error_code:"MARITIME_PROVISION_UNCONFIGURED"});
 const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
 assert.equal(res.statusCode,503);assert.equal(jobs.size,0);
});

test("active legacy reconsent resumes a consent-guarded configure job before scheduling work",async()=>{
 const {deps,rows,jobs,provisionStates}=activationFixture();const uid=`lm_${SUBJECT}`,releaseSha="a".repeat(40);
 const active={uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",source:"direct",
  consent_version:"maritime-manager-v1",agent_id:"agent-a",release_sha:releaseSha,paused_at:null};rows.set(uid,active);
 const runtime=require("./maritime-manager-runtime.js");
 const original=runtime.buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha,phase:"configure"});
 provisionStates.set(original.job_id,{job_id:original.job_id,tenant_id:uid,status:"dead_letter",attempt:1,
  last_error_code:"MARITIME_PROVISION_CONSENT_REQUIRED"});
 deps.readCommonReceipt=async()=>null;
 const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
 assert.equal(res.statusCode,202);assert.equal(jobs.size,1);
 const resumed=[...jobs.values()][0];assert.notEqual(resumed.job_id,original.job_id);
 assert.equal(resumed.capability,"maritime.manager.provision");
 assert.equal(resumed.input_refs.provision_phase_ref,"maritime-provision-phase://configure");
 assert.ok(resumed.input_refs.provision_resume_ref);
});

test("active legacy reconsent leaves an unknown configure effect fenced",async()=>{
 const {deps,rows,jobs,provisionStates}=activationFixture();const uid=`lm_${SUBJECT}`,releaseSha="a".repeat(40);
 rows.set(uid,{uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",source:"direct",
  consent_version:"maritime-manager-v1",agent_id:"agent-a",release_sha:releaseSha,paused_at:null});
 const configure=require("./maritime-manager-runtime.js").buildMaritimeManagerProvisionJob({tenantId:uid,releaseSha,phase:"configure"});
 provisionStates.set(configure.job_id,{job_id:configure.job_id,tenant_id:uid,status:"reconciling",attempt:1,last_error_code:"PROVIDER_RESULT_UNKNOWN"});
 deps.readCommonReceipt=async()=>null;
 const res=response();await handleMaritimeManagerActivate(activateRequest(deps),res,deps);
 assert.equal(res.statusCode,409);assert.equal(jobs.size,0);
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
test("active Cloud page never asks for separate Capafy credentials after first-party consent", async () => {
  const { deps } = fixture(), uid = `lm_${SUBJECT}`;
  deps.managerStore = { read: async () => ({ uid, auth_subject: SUBJECT, status: "active", consent_version: "maritime-manager-v2",
    agent_id: "agent-a", release_sha: "a".repeat(40) }) };
  deps.readCommonReceipt = async () => ({ outcome: "verified", provider: "maritime", loop_id: "maritime.manager",
    external_ref: "maritime-agent://agent-a", evidence_refs: ["maritime-agent://agent-a"] });
  deps.distributionStore = { recordAnonymousEvent: async () => true };
  deps.capafyBindingStore = { readStatus: async () => { throw new Error("customer page must not require a separate provider login"); } };
  const res = response();
  await handleMaritimeManagerPage(request("/maritime?lang=en"), res, deps);
  assert.equal(res.statusCode, 200);
  assert.match(res.body, /Life Manager is active/);
  assert.doesNotMatch(res.body, /capafy-connect|capafy-disconnect|Capafy developer account|type="email"/i);
  assert.match(res.body, /uses that address for authorized platform contact and result reports/i);
});

test("paused Cloud page offers Stop state without a separate Capafy credential prompt", async () => {
  const { deps } = fixture(), uid = `lm_${SUBJECT}`;
  deps.managerStore = { read: async () => ({ uid, auth_subject: SUBJECT, status: "paused", paused_at: "2026-10-25T11:00:00.000Z" }) };
  deps.distributionStore = { recordAnonymousEvent: async () => true };
  deps.capafyBindingStore = { readStatus: async () => { throw new Error("customer page must not require a separate provider login"); } };
  const res = response();
  await handleMaritimeManagerPage(request("/maritime?lang=en"), res, deps);
  assert.equal(res.statusCode, 200);
  assert.match(res.body, /data-action="stop"/);
  assert.doesNotMatch(res.body, /capafy-connect|capafy-disconnect|Capafy developer account|type="email"/i);
});

test("legacy_active_page_requires_consent_refresh_instead_of_showing_active_work",async()=>{
 const {deps}=fixture();const uid=`lm_${SUBJECT}`,sha="a".repeat(40);
 deps.distributionStore={recordAnonymousEvent:async()=>true};
 deps.managerStore={read:async()=>({uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",source:"direct",
   consent_version:"maritime-manager-v1",agent_id:"agent-a",release_sha:sha})};
 deps.readCommonReceipt=async()=>({outcome:"verified",provider:"maritime",loop_id:"maritime.manager",
   external_ref:"maritime-agent://agent-a",evidence_refs:["maritime-agent://agent-a"]});
 const res=response();await handleMaritimeManagerPage(request("/maritime?lang=en"),res,deps);
 assert.equal(res.statusCode,200);assert.match(res.body,/data-action="activate"/);
 assert.match(res.body,/data-consent="maritime-manager-v2"/);
 assert.match(res.body,/register or sign in to my authorized Publisher account/i);
 assert.doesNotMatch(res.body,/Verified work|Work in progress/);
});

test("legacy_pending_and_provisioning_pages_require_updated_consent_before_work_resumes",async()=>{
 for(const state of ["pending","provisioning"]){
  const {deps}=fixture();const uid=`lm_${SUBJECT}`;deps.distributionStore={recordAnonymousEvent:async()=>true};
  deps.managerStore={read:async()=>({uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:state,source:"direct",
   consent_version:"maritime-manager-v1",agent_id:null,release_sha:"a".repeat(40),paused_at:null})};
  const res=response();await handleMaritimeManagerPage(request("/maritime?lang=en"),res,deps);
  assert.equal(res.statusCode,200,state);assert.match(res.body,/data-action="activate"/,state);
  assert.match(res.body,/data-consent="maritime-manager-v2"/,state);assert.match(res.body,/updated authorization before work continues/i,state);
  assert.doesNotMatch(res.body,/Preparing your manager/,state);
 }
});

test("active_cloud_page_shows_only_verified_work_and_email_receipts",async()=>{
 const {deps}=fixture();const uid=`lm_${SUBJECT}`,sha="a".repeat(40);
 deps.distributionStore={recordAnonymousEvent:async()=>true};
 deps.managerStore={read:async()=>({uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",source:"direct",consent_version:"maritime-manager-v2",agent_id:"agent-a",release_sha:sha})};
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
 deps.managerStore={read:async()=>({uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",source:"direct",consent_version:"maritime-manager-v2",agent_id:"agent-a",release_sha:sha})};
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
 deps.managerStore={read:async()=>({uid,auth_subject:SUBJECT,email:USER.email,timezone:"UTC",status:"active",source:"direct",consent_version:"maritime-manager-v2",agent_id:"agent-a",release_sha:sha})};
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
 rows.set(uid,{uid,status:"active",auth_subject:SUBJECT,consent_version:"maritime-manager-v2",agent_id:"agent-a",release_sha:"a".repeat(40)});
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
 await handleMaritimeManagerActivate(request('/maritime/activate','POST',{consentVersion:'maritime-manager-v2',source:'instagram',attribution:{utm_source:'instagram',utm_medium:'dm',email:'private@example.invalid',token:'private-token'}},{'x-lm-web-csrf':csrf}),res,deps);
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

function capafyConnectionFixture() {
  const f = fixture();
  const uid = `lm_${SUBJECT}`;
  f.deps.env.LM_MARITIME_CAPAFY_CONNECTION_ENABLED = "1";
  const bindingWrites = [], calls = [];
  f.deps.now = () => "2026-10-25T12:00:00.000Z";
  f.deps.managerStore = { read: async tenantId => tenantId === uid
    ? { uid, auth_subject: SUBJECT, email: USER.email, status: "active", paused_at: null } : null };
  f.deps.capafyBindingStore = {
    readStatus: async () => ({ connected: false }),
    save: async input => { bindingWrites.push(input); return { provider: "capafy", tenantId: uid,
      providerSubject: "019d3c7f-fe51-7c57-aa2e-8e1055bb36a5", accountRef: `account://capafy/${uid}/019d3c7f-fe51-7c57-aa2e-8e1055bb36a5`,
      autonomyConsentVersion: "maritime-capafy-autonomy-v1" }; },
    disconnect: async input => { calls.push(["disconnect", input]); return true; },
  };
  f.deps.capafyConnector = {
    startLogin: async email => { f.deps.capafyLoginEmail = email; calls.push(["start", email]); return { challengeId: "challenge-1", expiresInSec: 300 }; },
    verifyLogin: async input => { calls.push(["verify", input]); return { provider: "capafy",
      providerSubject: "019d3c7f-fe51-7c57-aa2e-8e1055bb36a5", accountEmail: f.deps.capafyLoginEmail || "seller@example.com",
      developerVerified: true, accessToken: "am_sk_" + "x".repeat(32) }; },
  };
  f.deps.capafyPublisherConsentStore = {
    record: async input => ({ tenantId: input.tenantId, authSubject: input.authSubject,
      agreementVersion: "v1.2", effectiveDate: "2026-09-28", agreementUrl: "https://capafy.ai/publisher-agreement/",
      acceptedAt: f.deps.now() }),
    readCurrent: async input => ({ tenantId: input.tenantId, authSubject: input.authSubject.toLowerCase(),
      agreementVersion: "v1.2", effectiveDate: "2026-09-28", agreementUrl: "https://capafy.ai/publisher-agreement/",
      acceptedAt: f.deps.now() }),
  };
  return { ...f, uid, bindingWrites, calls, csrf: require("./web-auth.js").createWebCsrfToken(uid, f.deps.env.LM_UID_SECRET) };
}

function publisherConsentInput() {
  return { agreementVersion: "v1.2", publisherType: "individual", legalName: "Test Publisher",
    jurisdiction: "Japan", publicSupportEmail: "support@example.test", ageOfMajorityAttested: true,
    entityAuthorityAttested: false, supportedRegionAttested: true, sanctionsEligibilityAttested: true,
    identityContactAccurateAttested: true, singlePublisherAccountAttested: true,
    certificationFeeNonRefundableAcknowledged: true, dataDisclosuresAccepted: true,
    supportObligationsAccepted: true, agreementAccepted: true };
}

function mailboxChallengeLifecycle() {
  let active = null;
  return {
    reserveCapafyChallenge: async input => {
      if (active && (active.status === "verifying"
        ? Date.parse(active.verificationLeaseExpiresAt) > Date.parse(input.startedAt)
        : Date.parse(active.expiresAt) > Date.parse(input.startedAt))) return false;
      active = { status: "starting", attemptId: input.attemptId, expiresAt: input.leaseExpiresAt };
      return true;
    },
    bindCapafyChallenge: async input => {
      if (active?.status !== "starting" || active.attemptId !== input.attemptId) return false;
      active = { status: "pending", challengeId: input.challengeId, expiresAt: input.expiresAt,
        verificationLeaseExpiresAt: null };
      return true;
    },
    claimCapafyChallengeVerification: async input => {
      if (active?.status !== "pending" || active.challengeId !== input.challengeId
        || Date.parse(active.expiresAt) <= Date.parse(input.now)) return false;
      active.status = "verifying";
      active.verificationLeaseExpiresAt = new Date(Date.parse(input.now) + 120_000).toISOString();
      return true;
    },
    renewCapafyChallengeVerification: async input => {
      if (active?.status !== "verifying" || active.challengeId !== input.challengeId
        || Date.parse(active.expiresAt) <= Date.parse(input.now)
        || Date.parse(active.verificationLeaseExpiresAt) <= Date.parse(input.now)) return false;
      active.verificationLeaseExpiresAt = input.leaseExpiresAt;
      return true;
    },
    releaseCapafyChallengeVerification: async input => {
      if (active?.status !== "verifying" || active.challengeId !== input.challengeId) return false;
      active.status = "pending";
      active.verificationLeaseExpiresAt = null;
      return true;
    },
    completeCapafyChallenge: async input => {
      if (active?.status !== "verifying" || active.challengeId !== input.challengeId) return false;
      active = null;
      return true;
    },
  };
}

test("Capafy connection routes stay disabled until the explicit Cloud provider flag is enabled", async () => {
  const f = capafyConnectionFixture();
  delete f.deps.env.LM_MARITIME_CAPAFY_CONNECTION_ENABLED;
  const res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    {}, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 503);
  assert.equal(JSON.parse(res.body).error, "capafy_connection_unavailable");
  assert.deepEqual(f.calls, []);
  assert.deepEqual(f.bindingWrites, []);
});

test("Capafy consent record uses the authenticated tenant and returns no identity or credential facts", async () => {
  const f = capafyConnectionFixture(), res = response();
  let recorded = null, emails = 0, logs = 0;
  f.deps.capafyPublisherConsentStore.record = async input => {
    recorded = input;
    return { tenantId: input.tenantId, authSubject: input.authSubject, agreementVersion: "v1.2",
      effectiveDate: "2026-09-28", acceptedAt: f.deps.now() };
  };
  f.deps.email = async () => { emails++; };
  f.deps.log = () => { logs++; };
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/publisher-consent", "POST",
    publisherConsentInput(), { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 201);
  assert.deepEqual(recorded, { tenantId: f.uid, authSubject: SUBJECT,
    verifiedContactEmail: USER.email, consent: publisherConsentInput() });
  assert.deepEqual(JSON.parse(res.body), { status: "recorded", agreementVersion: "v1.2",
    effectiveDate: "2026-09-28", acceptedAt: f.deps.now() });
  assert.doesNotMatch(res.body, /Test Publisher|support@example\.test|person@example\.invalid|am_sk_/i);
  assert.equal(emails, 0);
  assert.equal(logs, 0);
  assert.deepEqual(f.calls, []);
});

test("missing or stale Publisher Agreement consent blocks Capafy login before any provider call", async () => {
  for (const current of [null, { tenantId: `lm_${SUBJECT}`, authSubject: SUBJECT,
    agreementVersion: "v1.1", effectiveDate: "2026-09-28", acceptedAt: "2026-10-27T00:00:00.000Z" }]) {
    const f = capafyConnectionFixture(), res = response();
    f.deps.capafyPublisherConsentStore.readCurrent = async () => current;
    await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
      { termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
    assert.equal(res.statusCode, 409);
    assert.deepEqual(JSON.parse(res.body), { error: "capafy_publisher_agreement_consent_required" });
    assert.deepEqual(f.calls, []);
    assert.deepEqual(f.bindingWrites, []);
  }
});

test("a connected Publisher binding is reused without starting a new login or duplicate account", async () => {
  const f = capafyConnectionFixture(), res = response();
  const accountRef = `account://capafy/${f.uid}/019d3c7f-fe51-7c57-aa2e-8e1055bb36a5`;
  f.deps.capafyBindingStore.readStatus = async input => {
    assert.deepEqual(input, { tenantId: f.uid, authSubject: SUBJECT });
    return { connected: true, provider: "capafy", tenantId: f.uid, accountRef };
  };
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 200);
  assert.deepEqual(JSON.parse(res.body), { status: "connected", provider: "capafy", accountRef,
    autonomyConsentVersion: "maritime-capafy-autonomy-v1" });
  assert.deepEqual(f.calls, []);
  assert.deepEqual(f.bindingWrites, []);
});

test("Capafy OTP connect is authenticated, CSRF protected, and returns only a tenant-bound short-lived challenge", async () => {
  assert.equal(typeof handleMaritimeManagerCapafyConnection, "function");
  const f = capafyConnectionFixture(), res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 202);
  const result = JSON.parse(res.body);
  assert.equal(result.status, "check_email");
  assert.equal(result.expiresInSec, 300);
  assert.equal(typeof result.challengeRef, "string");
  assert.equal(res.body.includes(USER.email), false);
  assert.doesNotMatch(res.body, /accessToken|am_sk_/i);
  assert.deepEqual(f.calls, [["start", USER.email]]);
  const opened = require("./maritime-manager-capafy-binding.js").openChallenge(result.challengeRef, {
    tenantId: f.uid, authSubject: SUBJECT, secret: require("./web-auth.js").csrfSecret(f.deps), now: f.deps.now(),
  });
  assert.deepEqual(opened, { challengeId: "challenge-1", expiresAt: "2026-10-25T12:05:00.000Z",
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: "2026-10-25T12:00:00.000Z",
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy",
    mailboxVerification: false });
  const rejected = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    {}, { origin: "https://foreign.invalid", "x-lm-web-csrf": f.csrf }), rejected, f.deps);
  assert.equal(rejected.statusCode, 403);
  assert.equal(f.calls.length, 1);
});

test("Capafy OTP is not sent until the publisher explicitly accepts both current policies", async () => {
  for (const body of [
    {},
    { termsAccepted: true, privacyAccepted: false },
    { termsAccepted: false, privacyAccepted: true },
    { termsAccepted: "true", privacyAccepted: true },
  ]) {
    const f = capafyConnectionFixture(), res = response();
    await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
      body, { "x-lm-web-csrf": f.csrf }), res, f.deps);
    assert.equal(res.statusCode, 400);
    assert.deepEqual(JSON.parse(res.body), { error: "capafy_policy_consent_required" });
    assert.deepEqual(f.calls, []);
    assert.deepEqual(f.bindingWrites, []);
  }
});

test("Capafy policy acceptance is bound to the signed challenge before verification", async () => {
  const f = capafyConnectionFixture(), res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { termsAccepted: true, privacyAccepted: true },
    { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 202);
  const challenge = require("./maritime-manager-capafy-binding.js").openChallenge(JSON.parse(res.body).challengeRef, {
    tenantId: f.uid, authSubject: SUBJECT, secret: require("./web-auth.js").csrfSecret(f.deps), now: f.deps.now(),
  });
  assert.deepEqual(challenge, { challengeId: "challenge-1", expiresAt: "2026-10-25T12:05:00.000Z",
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: "2026-10-25T12:00:00.000Z",
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy",
    mailboxVerification: false });
  assert.deepEqual(f.calls, [["start", USER.email]]);
});

test("tenant mailbox setup reads only its Capafy OTP and verifies it server-side", async () => {
  const f = capafyConnectionFixture(), mailboxCalls = [];
  f.deps.managerMailboxStore = {
    ...mailboxChallengeLifecycle(),
    ensure: async identity => {
      mailboxCalls.push(["ensure", identity]);
      return { connected: true, provider: "agentmail", tenantId: f.uid, inboxId: "inbox-tenant-a",
        email: "lm-agent-a@agentmail.to", clientId: `life-manager-${f.uid}` };
    },
    readCapafyVerificationCode: async input => {
      mailboxCalls.push(["readCode", input]);
      return { status: "code", code: "004219" };
    },
  };
  const start = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST", {
    useTenantMailbox: true, tenantMailboxConsent: true, termsAccepted: true, privacyAccepted: true,
  }, { "x-lm-web-csrf": f.csrf }), start, f.deps);
  assert.equal(start.statusCode, 202);
  const started = JSON.parse(start.body);
  assert.equal(started.mailboxEmail, "lm-agent-a@agentmail.to");
  assert.doesNotMatch(start.body, /004219|accessToken|am_sk_/i);
  assert.deepEqual(mailboxCalls, [["ensure", { tenantId: f.uid, authSubject: SUBJECT }]]);
  assert.deepEqual(f.calls, [["start", "lm-agent-a@agentmail.to"]]);

  const challenge = require("./maritime-manager-capafy-binding.js").openChallenge(started.challengeRef, {
    tenantId: f.uid, authSubject: SUBJECT, secret: require("./web-auth.js").csrfSecret(f.deps), now: f.deps.now(),
  });
  assert.equal(challenge.mailboxVerification, true);
  const done = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST", {
    challengeRef: started.challengeRef, autonomyConsentVersion: "maritime-capafy-autonomy-v1",
  }, { "x-lm-web-csrf": f.csrf }), done, f.deps);
  assert.equal(done.statusCode, 200);
  assert.doesNotMatch(done.body, /004219|agentmail|accessToken|am_sk_/i);
  assert.deepEqual(mailboxCalls[1], ["readCode", { tenantId: f.uid, authSubject: SUBJECT,
    afterMs: Date.parse("2026-10-25T12:00:00.000Z") }]);
  assert.deepEqual(f.calls[1], ["verify", { challengeId: "challenge-1", code: "004219" }]);
});

test("tenant mailbox is not created or read without explicit mailbox consent", async () => {
  const f = capafyConnectionFixture(); let provisioned = 0;
  f.deps.managerMailboxStore = { ensure: async () => { provisioned += 1; throw new Error("must not provision"); },
    readCapafyVerificationCode: async () => { throw new Error("must not read"); } };
  const res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST", {
    useTenantMailbox: true, termsAccepted: true, privacyAccepted: true,
  }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 400);
  assert.deepEqual(JSON.parse(res.body), { error: "tenant_mailbox_consent_required" });
  assert.equal(provisioned, 0);
  assert.deepEqual(f.calls, []);
});

test("verified signup address starts the platform challenge without reading an inbox", async () => {
  const f = capafyConnectionFixture(); let mailboxReads = 0;
  f.deps.managerMailboxStore = {
    read: async () => { mailboxReads += 1; throw new Error("standard address must not read mailbox state"); },
    readCapafyVerificationCode: async () => { mailboxReads += 1; return { status: "code", code: "004219" }; },
  };
  const start = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST", {
    termsAccepted: true, privacyAccepted: true,
  }, { "x-lm-web-csrf": f.csrf }), start, f.deps);
  const done = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST", {
    challengeRef: JSON.parse(start.body).challengeRef, autonomyConsentVersion: "maritime-capafy-autonomy-v1",
  }, { "x-lm-web-csrf": f.csrf }), done, f.deps);
  assert.equal(done.statusCode, 400);
  assert.deepEqual(JSON.parse(done.body), { error: "verification_code_required" });
  assert.equal(mailboxReads, 0);
  assert.deepEqual(f.calls, [["start", USER.email]]);
});

test("Capafy connection start rejects a caller-supplied contact address", async () => {
  const f = capafyConnectionFixture();
  const res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST", {
    email: "attacker@example.invalid", termsAccepted: true, privacyAccepted: true,
  }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 400);
  assert.deepEqual(JSON.parse(res.body), { error: "invalid_request" });
  assert.deepEqual(f.calls, []);
});

test("tenant mailbox challenge waits for a recent code without submitting or exposing stale content", async () => {
  const f = capafyConnectionFixture();
  f.deps.managerMailboxStore = {
    ...mailboxChallengeLifecycle(),
    ensure: async () => ({ connected: true, provider: "agentmail", tenantId: f.uid, inboxId: "inbox-tenant-a",
      email: "lm-agent-a@agentmail.to", clientId: `life-manager-${f.uid}` }),
    readCapafyVerificationCode: async input => { f.mailboxReadInput = input; return { status: "not_found" }; },
  };
  const start = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST", {
    useTenantMailbox: true, tenantMailboxConsent: true, termsAccepted: true, privacyAccepted: true,
  }, { "x-lm-web-csrf": f.csrf }), start, f.deps);
  const done = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST", {
    challengeRef: JSON.parse(start.body).challengeRef, autonomyConsentVersion: "maritime-capafy-autonomy-v1",
  }, { "x-lm-web-csrf": f.csrf }), done, f.deps);
  assert.equal(done.statusCode, 202);
  assert.deepEqual(JSON.parse(done.body), { status: "waiting_for_email" });
  assert.deepEqual(f.mailboxReadInput, { tenantId: f.uid, authSubject: SUBJECT,
    afterMs: Date.parse("2026-10-25T12:00:00.000Z") });
  assert.deepEqual(f.calls, [["start", "lm-agent-a@agentmail.to"]]);
  assert.deepEqual(f.bindingWrites, []);
});

test("tenant mailbox allows one active Capafy challenge and binds each OTP read to that challenge", async () => {
  const f = capafyConnectionFixture(), lifecycle = mailboxChallengeLifecycle(), readCalls = [];
  let releaseRead;
  const readGate = new Promise(resolve => { releaseRead = resolve; });
  f.deps.managerMailboxStore = {
    ...lifecycle,
    ensure: async () => ({ connected: true, provider: "agentmail", tenantId: f.uid, inboxId: "inbox-tenant-a",
      email: "lm-agent-a@agentmail.to", clientId: `life-manager-${f.uid}` }),
    readCapafyVerificationCode: async input => { readCalls.push(input); await readGate; return { status: "code", code: "004219" }; },
  };
  const startBody = { useTenantMailbox: true, tenantMailboxConsent: true, termsAccepted: true, privacyAccepted: true };
  const start = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST", startBody,
    { "x-lm-web-csrf": f.csrf }), start, f.deps);
  assert.equal(start.statusCode, 202);
  const duplicateStart = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST", startBody,
    { "x-lm-web-csrf": f.csrf }), duplicateStart, f.deps);
  assert.equal(duplicateStart.statusCode, 409);
  assert.deepEqual(JSON.parse(duplicateStart.body), { error: "capafy_challenge_in_progress" });
  assert.equal(f.calls.filter(call => call[0] === "start").length, 1);

  const challengeRef = JSON.parse(start.body).challengeRef;
  const binding = require("./maritime-manager-capafy-binding.js");
  const secret = require("./web-auth.js").csrfSecret(f.deps);
  const staleRef = binding.sealChallenge({ tenantId: f.uid, authSubject: SUBJECT,
    challengeId: "challenge-2", expiresInSec: 300, now: f.deps.now(),
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: f.deps.now(),
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy",
    mailboxVerification: true }, secret);
  const stale = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST", {
    challengeRef: staleRef, autonomyConsentVersion: "maritime-capafy-autonomy-v1",
  }, { "x-lm-web-csrf": f.csrf }), stale, f.deps);
  assert.equal(stale.statusCode, 409);
  assert.deepEqual(JSON.parse(stale.body), { error: "capafy_challenge_in_progress" });
  assert.equal(readCalls.length, 0);

  const verifyInput = { challengeRef, autonomyConsentVersion: "maritime-capafy-autonomy-v1" };
  const verifyOne = response();
  const verifyOnePending = handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST", verifyInput,
    { "x-lm-web-csrf": f.csrf }), verifyOne, f.deps);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(readCalls.length, 1);
  const verifyTwo = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST", verifyInput,
    { "x-lm-web-csrf": f.csrf }), verifyTwo, f.deps);
  assert.equal(verifyTwo.statusCode, 409);
  assert.deepEqual(JSON.parse(verifyTwo.body), { error: "capafy_challenge_in_progress" });
  assert.equal(readCalls.length, 1);
  releaseRead();
  await verifyOnePending;
  assert.equal(verifyOne.statusCode, 200);
  assert.deepEqual(f.calls.filter(call => call[0] === "verify"), [["verify", { challengeId: "challenge-1", code: "004219" }]]);
});

test("an expired challenge cannot lose its verifying lease while mailbox retrieval is still active", async () => {
  const f = capafyConnectionFixture(), lifecycle = mailboxChallengeLifecycle();
  let currentTime = "2026-10-25T12:00:00.000Z", readStarted, releaseRead;
  f.deps.now = () => currentTime;
  const reading = new Promise(resolve => { readStarted = resolve; });
  const readGate = new Promise(resolve => { releaseRead = resolve; });
  f.deps.managerMailboxStore = {
    ...lifecycle,
    ensure: async () => ({ connected: true, provider: "agentmail", tenantId: f.uid, inboxId: "inbox-tenant-a",
      email: "lm-agent-a@agentmail.to", clientId: `life-manager-${f.uid}` }),
    readCapafyVerificationCode: async () => { readStarted(); await readGate; return { status: "code", code: "007777" }; },
  };
  const startBody = { useTenantMailbox: true, tenantMailboxConsent: true, termsAccepted: true, privacyAccepted: true };
  const start = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST", startBody,
    { "x-lm-web-csrf": f.csrf }), start, f.deps);
  const challengeRef = JSON.parse(start.body).challengeRef;
  currentTime = "2026-10-25T12:04:50.000Z";
  const verify = response();
  const verifyPending = handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST", {
    challengeRef, autonomyConsentVersion: "maritime-capafy-autonomy-v1",
  }, { "x-lm-web-csrf": f.csrf }), verify, f.deps);
  await reading;
  currentTime = "2026-10-25T12:05:30.000Z";
  const nextStart = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST", startBody,
    { "x-lm-web-csrf": f.csrf }), nextStart, f.deps);
  assert.equal(nextStart.statusCode, 409);
  assert.equal(f.calls.filter(call => call[0] === "start").length, 1);
  releaseRead();
  await verifyPending;
  assert.equal(verify.statusCode, 409);
  assert.deepEqual(JSON.parse(verify.body), { error: "capafy_challenge_in_progress" });
  assert.equal(f.calls.filter(call => call[0] === "verify").length, 0);
});

test("Capafy OTP verify binds the official verified seller to the signed Life Manager tenant and keeps token private", async () => {
  const f = capafyConnectionFixture(), logs = [], receipts = [], emails = [];
  f.deps.log = value => logs.push(value);
  f.deps.recordReceipt = value => receipts.push(value);
  f.deps.sendEmail = value => emails.push(value);
  const started = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), started, f.deps);
  const challengeRef = JSON.parse(started.body).challengeRef;
  const done = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST", {
    challengeRef, code: "004219", autonomyConsentVersion: "maritime-capafy-autonomy-v1",
  }, { "x-lm-web-csrf": f.csrf }), done, f.deps);
  assert.equal(done.statusCode, 200);
  assert.equal(JSON.parse(done.body).status, "connected");
  assert.doesNotMatch(done.body, /am_sk_|seller@example.com|accessToken/i);
  assert.doesNotMatch(JSON.stringify([started.body, done.body, logs, receipts, emails]), /am_sk_|accessToken/i);
  assert.deepEqual({ logs, receipts, emails }, { logs: [], receipts: [], emails: [] });
  assert.deepEqual(f.calls, [["start", USER.email], ["verify", { challengeId: "challenge-1", code: "004219" }]]);
  assert.equal(f.bindingWrites.length, 1);
  assert.equal(f.bindingWrites[0].tenantId, f.uid);
  assert.equal(f.bindingWrites[0].authSubject, SUBJECT);
  assert.equal(f.bindingWrites[0].autonomyConsentVersion, "maritime-capafy-autonomy-v1");
  assert.equal(f.bindingWrites[0].policyConsentVersion, "capafy-publisher-terms-privacy-v1");
  assert.equal(f.bindingWrites[0].termsAcceptedAt, "2026-10-25T12:00:00.000Z");
  assert.equal(f.bindingWrites[0].termsUrl, "https://api.capafy.ai/terms-of-service");
  assert.equal(f.bindingWrites[0].privacyUrl, "https://api.capafy.ai/privacy-policy");
  assert.equal(f.bindingWrites[0].accessToken.startsWith("am_sk_"), true);
});

test("Capafy connection rejects foreign challenges, missing autonomy consent, and unready tenants before verification", async () => {
  const f = capafyConnectionFixture();
  const foreign = require("./maritime-manager-capafy-binding.js").sealChallenge({ tenantId: "lm_22222222-2222-4222-8222-222222222222",
    authSubject: SUBJECT, challengeId: "challenge-1", expiresInSec: 300, now: f.deps.now(),
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: f.deps.now(),
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy" }, require("./web-auth.js").csrfSecret(f.deps));
  let res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST",
    { challengeRef: foreign, code: "004219", autonomyConsentVersion: "maritime-capafy-autonomy-v1" },
    { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 400);
  res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST",
    { challengeRef: "x", code: "004219" }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 400);
  f.deps.managerStore.read = async uid => ({ uid, auth_subject: SUBJECT, status: "paused", paused_at: "2026-10-25T11:00:00Z" });
  res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 409);
  assert.equal(f.calls.length, 0);
  assert.equal(f.bindingWrites.length, 0);
});

test("Capafy OTP is not sent until the cloud encryption key is configured", async () => {
  const f = capafyConnectionFixture();
  f.deps.capafyBindingStore.assertConfigured = () => { throw new Error("maritime_capafy_encryption_unavailable"); };
  const res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 503);
  assert.equal(JSON.parse(res.body).error, "capafy_login_unavailable");
  assert.equal(f.calls.length, 0);
});

test("Capafy unlink only deletes the signed-in tenant's binding", async () => {
  const f = capafyConnectionFixture(), res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/disconnect", "POST", {},
    { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 200);
  assert.deepEqual(JSON.parse(res.body), { status: "disconnected", disconnected: true });
  assert.deepEqual(f.calls, [["disconnect", { tenantId: f.uid, authSubject: SUBJECT }]]);
});

test("Capafy unlink remains available when its feature flag is disabled", async () => {
  const f = capafyConnectionFixture();
  delete f.deps.env.LM_MARITIME_CAPAFY_CONNECTION_ENABLED;
  delete f.deps.env.LM_MARITIME_CAPAFY_ENCRYPTION_KEY;
  const res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/disconnect", "POST", {},
    { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 200);
  assert.deepEqual(f.calls, [["disconnect", { tenantId: f.uid, authSubject: SUBJECT }]]);
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
