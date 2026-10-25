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
const USER = { id: SUBJECT, email: "person@example.invalid", email_confirmed_at: "2026-10-20T00:00:00Z" };
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
function fixture({ user=USER, signInError=null, exchangeError=null }={}) {
  assert.equal(typeof handleMaritimeManagerAuth,"function","email auth handler must exist");
  const calls=[];
  const client={auth:{
    async signInWithOtp(input) { calls.push(["otp",input]);return {data:{},error:signInError}; },
    async verifyOtp(input) { calls.push(["verify",input]);return {data:{session:{}},error:null}; },
    async exchangeCodeForSession(input) { calls.push(["exchange",input]);return {data:exchangeError?{}:{session:{}},error:exchangeError}; },
    async getUser() { calls.push(["getUser"]);return {data:{user},error:null}; },
    async signOut() { calls.push(["signOut"]);return {error:null}; },
  }};
  const deps={env:{LM_MARITIME_MANAGER_EMAIL_ENABLED:"1",LM_UID_SECRET:"fixture-only-secret"},publicOrigin:ORIGIN,
    createClient:()=>client,ssr:{parseCookieHeader:s=>s.split(";").filter(Boolean).map(x=>({name:x.trim().split("=")[0],value:x.split("=")[1]}))},
    ensureWebUserImpl:async id=>{calls.push(["ensure",id]);return `lm_${id}`;}};
  return {calls,deps};
}
test("email_auth_does_not_require_google_calendar_goal_budget_or_telegram",async()=>{
  const {deps,calls}=fixture();const res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/email","POST",{email:USER.email}),res,deps);
  assert.equal(res.statusCode,202);assert.deepEqual(calls,[["otp",{email:USER.email,options:{shouldCreateUser:true,emailRedirectTo:`${ORIGIN}/auth/maritime/confirm`}}]]);
  assert.doesNotMatch(res.body,/person@|goal|budget|telegram|calendar/i);
});
test("cross_origin_signup_is_rejected_before_provider_dispatch",async()=>{
  const {deps,calls}=fixture();const res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/email","POST",{email:USER.email},{origin:"https://foreign.invalid"}),res,deps);
  assert.equal(res.statusCode,403);assert.equal(calls.length,0);
});
test("confirmation_only_authenticates_and_redirects_to_activation_page",async()=>{
  const {deps,calls}=fixture();const res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/confirm?code=fixture-authorization-code","GET",undefined,{cookie:"lm-web-auth-code-verifier=fixture-verifier"}),res,deps);
  assert.equal(res.statusCode,302);assert.equal(res.headers.location,"/maritime?verified=1");
  assert.deepEqual(calls.map(x=>x[0]),["exchange","getUser","ensure"]);
  assert.equal(res.headers["referrer-policy"],"no-referrer");
});
test("unverified_email_cannot_resolve_a_manager_user",async()=>{
  const {deps,calls}=fixture({user:{...USER,email_confirmed_at:null}});
  assert.equal(await resolveMaritimeManagerUser(request("/maritime/activate","POST"),response(),deps),null);
  assert.equal(calls.some(x=>x[0]==="ensure"),false);
});
test("verified_identity_is_derived_from_auth_not_request_uid",async()=>{
  const {deps}=fixture();const req=request("/maritime?uid=other","POST",{uid:"other"});
  const user=await resolveMaritimeManagerUser(req,response(),deps);
  assert.equal(user.uid,`lm_${SUBJECT}`);assert.equal(user.subject,SUBJECT);assert.equal(user.email,USER.email);assert.match(user.csrf,/^[a-f0-9]{64}$/);
});
test("provider_rate_limit_is_returned_without_raw_provider_message",async()=>{
  const {deps}=fixture({signInError:{status:429,message:"private provider detail"}});const res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/email","POST",{email:USER.email}),res,deps);
  assert.equal(res.statusCode,429);assert.doesNotMatch(res.body,/private provider/);
});
test("code_confirmation_requires_pkce_cookie_and_does_not_exchange_without_it",async()=>{
  const {deps,calls}=fixture();const res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/confirm?code=fixture-authorization-code"),res,deps);
  assert.equal(res.statusCode,302);assert.match(res.headers.location,/auth_error/);assert.equal(calls.length,0);
});
test("default_magic_link_pkce_code_is_supported_without_changing_global_email_template",async()=>{
  const {deps,calls}=fixture();const res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/confirm?code=fixture-authorization-code","GET",undefined,{cookie:"lm-web-auth-code-verifier=fixture-verifier"}),res,deps);
  assert.equal(res.headers.location,"/maritime?verified=1");assert.equal(calls[0][0],"exchange");
});
test("feature_is_disabled_without_explicit_config",async()=>{
  const {deps,calls}=fixture();deps.env={};const res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/email","POST",{email:USER.email}),res,deps);
  assert.equal(res.statusCode,503);assert.equal(calls.length,0);
});

test("expired_link_does_not_sign_out_an_existing_session",async()=>{
  const {deps,calls}=fixture({exchangeError:{status:403,message:"expired"}});const res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/confirm?code=fixture-expired-code","GET",undefined,{cookie:"lm-web-auth-code-verifier=fixture-verifier"}),res,deps);
  assert.match(res.headers.location,/auth_error/);assert.equal(calls.some(x=>x[0]==="signOut"),false);
});
test("native_email_form_is_supported",async()=>{
  const {deps,calls}=fixture();const res=response();const req=Readable.from([new URLSearchParams({email:USER.email}).toString()]);
  req.url="/auth/maritime/email";req.method="POST";req.headers={origin:ORIGIN,"content-type":"application/x-www-form-urlencoded"};
  await handleMaritimeManagerAuth(req,res,deps);assert.equal(res.statusCode,202);assert.equal(calls[0][1].email,USER.email);
});
test("duplicate_confirmation_and_oversize_signup_do_not_reach_provider",async()=>{
  const {deps,calls}=fixture();let res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/confirm?token_hash=one&type=email&token_hash=two"),res,deps);
  assert.match(res.headers.location,/auth_error/);assert.equal(calls.length,0);res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/email","POST",{email:"a".repeat(5000)+"@example.invalid"}),res,deps);
  assert.equal(res.statusCode,400);assert.equal(calls.length,0);
});

test("unbound_token_hash_cannot_replace_an_existing_session",async()=>{
  const {deps,calls}=fixture();const res=response();
  await handleMaritimeManagerAuth(request("/auth/maritime/confirm?token_hash=attacker-owned-valid-token&type=email"),res,deps);
  assert.match(res.headers.location,/auth_error/);assert.deepEqual(calls,[]);
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
  await handleMaritimeManagerPage(request("/maritime?source=referral&lang=en"),res,deps);assert.equal(res.statusCode,200);assert.match(res.body,/action="\/auth\/maritime\/email"/);assert.equal(events,1);assert.equal(calls.some(x=>x[0]==="ensure"),false);
});
test("verified_campaign_page_displays_activation_or_persisted_state_without_dispatch",async()=>{
  assert.equal(typeof handleMaritimeManagerPage,"function");const {deps}=fixture();deps.distributionStore={recordAnonymousEvent:async()=>true};deps.managerStore={read:async()=>null};let res=response();
  await handleMaritimeManagerPage(request("/maritime?lang=ja"),res,deps);assert.match(res.body,/<button[^>]+data-action="activate"/);
  deps.managerStore.read=async()=>({status:"effect_unknown"});res=response();await handleMaritimeManagerPage(request("/maritime?lang=ja"),res,deps);
  assert.doesNotMatch(res.body,/<button[^>]+data-action="activate"/);assert.match(res.body,/実行結果を確認中/);
});
test("active Life Manager page reads only safe Capafy connection metadata for its signed-in tenant",async()=>{
 const {deps}=fixture(),uid=`lm_${SUBJECT}`,calls=[];
 deps.env.LM_MARITIME_CAPAFY_CONNECTION_ENABLED="1";
 deps.managerStore={read:async()=>({uid,auth_subject:SUBJECT,status:"active",agent_id:"agent-a",release_sha:"a".repeat(40)})};
 deps.readCommonReceipt=async()=>({outcome:"verified",provider:"maritime",loop_id:"maritime.manager",
   external_ref:"maritime-agent://agent-a",evidence_refs:["maritime-agent://agent-a"]});
 deps.capafyBindingStore={readStatus:async identity=>{calls.push(identity);return {connected:true,provider:"capafy",tenantId:uid,
   accountRef:`account://capafy/${uid}/019d3c7f-fe51-7c57-aa2e-8e1055bb36a5`,autonomyConsentVersion:"maritime-capafy-autonomy-v1"};}};
 deps.distributionStore={recordAnonymousEvent:async()=>true};
 const res=response();await handleMaritimeManagerPage(request("/maritime?lang=en"),res,deps);
 assert.equal(res.statusCode,200);assert.match(res.body,/Capafy developer account connected/);
 assert.doesNotMatch(res.body,/account:\/\/capafy\/|019d3c7f|am_sk_/i);
 assert.deepEqual(calls,[{tenantId:uid,authSubject:SUBJECT}]);
 delete deps.env.LM_MARITIME_CAPAFY_CONNECTION_ENABLED;
 const disabled=response();await handleMaritimeManagerPage(request("/maritime?lang=en"),disabled,deps);
 assert.match(disabled.body,/automated work is currently disabled/i);
 assert.match(disabled.body,/data-action="capafy-disconnect"/);assert.equal(calls.length,2);
});

test("paused Life Manager keeps the tenant's Capafy disconnect control available", async () => {
  const { deps } = fixture();
  const uid = `lm_${SUBJECT}`, reads = [];
  deps.env.LM_MARITIME_CAPAFY_CONNECTION_ENABLED = "1";
  deps.managerStore = { read: async tenantId => ({ uid: tenantId, auth_subject: SUBJECT,
    status: "paused", paused_at: "2026-10-25T11:00:00.000Z" }) };
  deps.capafyBindingStore = { readStatus: async identity => {
    reads.push(identity);
    return { connected: true, provider: "capafy", tenantId: uid,
      accountRef: `account://capafy/${uid}/019d3c7f-fe51-7c57-aa2e-8e1055bb36a5`,
      autonomyConsentVersion: "maritime-capafy-autonomy-v1" };
  } };
  deps.distributionStore = { recordAnonymousEvent: async () => true };
  const res = response();
  await handleMaritimeManagerPage(request("/maritime?lang=en"), res, deps);
  assert.equal(res.statusCode, 200);
  assert.match(res.body, /data-action="capafy-disconnect"/);
  assert.doesNotMatch(res.body, /<form data-action="capafy-connect"/);
  assert.deepEqual(reads, [{ tenantId: uid, authSubject: SUBJECT }]);
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


test("confirmed email telemetry follows session verification and contains only the derived uid",async()=>{
 const {deps}=fixture(),events=[];deps.recordEmailVerified=async uid=>{events.push(uid);return true;};
 const res=response();await handleMaritimeManagerAuth(request('/auth/maritime/confirm?code=fixture-code','GET',undefined,{cookie:'lm-web-auth-code-verifier=fixture-verifier'}),res,deps);
 assert.equal(res.statusCode,302);assert.deepEqual(events,[`lm_${SUBJECT}`]);
 const unverified=fixture({user:{...USER,email_confirmed_at:null}});unverified.deps.recordEmailVerified=deps.recordEmailVerified;
 await handleMaritimeManagerAuth(request('/auth/maritime/confirm?code=fixture-code','GET',undefined,{cookie:'lm-web-auth-code-verifier=fixture-verifier'}),response(),unverified.deps);assert.equal(events.length,1);
});


test("manager activation forwards only sanitized first touch through the existing writer",async()=>{
 const {deps}=activationFixture(),stored=[];deps.storeFirstTouch=async(uid,attribution)=>{stored.push({uid,attribution});return true;};
 const csrf=require('./web-auth.js').createWebCsrfToken(`lm_${SUBJECT}`,deps.env.LM_UID_SECRET),res=response();
 await handleMaritimeManagerActivate(request('/maritime/activate','POST',{consentVersion:'maritime-manager-v1',source:'instagram',attribution:{utm_source:'instagram',utm_medium:'dm',email:'private@example.invalid',token:'private-token'}},{'x-lm-web-csrf':csrf}),res,deps);
 assert.equal(res.statusCode,202);assert.deepEqual(stored,[{uid:`lm_${SUBJECT}`,attribution:{utm_source:'instagram',utm_medium:'dm'}}]);
});

test('signup keeps signed first-touch until verification before emitting email event',async()=>{
 const {deps}=fixture(),signup=response();deps.serializeCookieHeader=(name,value)=>name+'='+value;
 await handleMaritimeManagerAuth(request('/auth/maritime/email','POST',{email:USER.email,attribution:{utm_source:'instagram',utm_medium:'dm'}}),signup,deps);
 assert.equal(signup.statusCode,202);
 const cookies=signup.headers['set-cookie'];assert.ok(cookies);
 const cookie=Array.isArray(cookies)?cookies.join('; '):cookies;
 const seen=[];deps.storeFirstTouch=async(uid,attribution)=>{seen.push(['stored',attribution]);return true;};
 deps.recordEmailVerified=async(uid,opts)=>{seen.push(['event',opts.attribution]);return true;};
 const confirmed=response();
 await handleMaritimeManagerAuth(request('/auth/maritime/confirm?code=fixture-code','GET',undefined,{cookie:'lm-web-auth-code-verifier=fixture; '+cookie}),confirmed,deps);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(confirmed.headers.location,'/maritime?verified=1');
 assert.deepEqual(seen.map(row=>row[0]),['stored','event']);assert.equal(seen[1][1].utm_source,'instagram');
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
    ? { uid, auth_subject: SUBJECT, status: "active", paused_at: null } : null };
  f.deps.capafyBindingStore = {
    save: async input => { bindingWrites.push(input); return { provider: "capafy", tenantId: uid,
      providerSubject: "019d3c7f-fe51-7c57-aa2e-8e1055bb36a5", accountRef: `account://capafy/${uid}/019d3c7f-fe51-7c57-aa2e-8e1055bb36a5`,
      autonomyConsentVersion: "maritime-capafy-autonomy-v1" }; },
    disconnect: async input => { calls.push(["disconnect", input]); return true; },
  };
  f.deps.capafyConnector = {
    startLogin: async email => { calls.push(["start", email]); return { challengeId: "challenge-1", expiresInSec: 300 }; },
    verifyLogin: async input => { calls.push(["verify", input]); return { provider: "capafy",
      providerSubject: "019d3c7f-fe51-7c57-aa2e-8e1055bb36a5", accountEmail: "seller@example.com",
      developerVerified: true, accessToken: "am_sk_" + "x".repeat(32) }; },
  };
  return { ...f, uid, bindingWrites, calls, csrf: require("./web-auth.js").createWebCsrfToken(uid, f.deps.env.LM_UID_SECRET) };
}

test("Capafy connection routes stay disabled until the explicit Cloud provider flag is enabled", async () => {
  const f = capafyConnectionFixture();
  delete f.deps.env.LM_MARITIME_CAPAFY_CONNECTION_ENABLED;
  const res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { email: "seller@example.com" }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 503);
  assert.equal(JSON.parse(res.body).error, "capafy_connection_unavailable");
  assert.deepEqual(f.calls, []);
  assert.deepEqual(f.bindingWrites, []);
});

test("Capafy OTP connect is authenticated, CSRF protected, and returns only a tenant-bound short-lived challenge", async () => {
  assert.equal(typeof handleMaritimeManagerCapafyConnection, "function");
  const f = capafyConnectionFixture(), res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { email: "Seller@Example.com", termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 202);
  const result = JSON.parse(res.body);
  assert.equal(result.status, "check_email");
  assert.equal(result.expiresInSec, 300);
  assert.equal(typeof result.challengeRef, "string");
  assert.doesNotMatch(res.body, /seller@example.com|accessToken|am_sk_/i);
  assert.deepEqual(f.calls, [["start", "Seller@Example.com"]]);
  const opened = require("./maritime-manager-capafy-binding.js").openChallenge(result.challengeRef, {
    tenantId: f.uid, authSubject: SUBJECT, secret: require("./web-auth.js").csrfSecret(f.deps), now: f.deps.now(),
  });
  assert.deepEqual(opened, { challengeId: "challenge-1", expiresAt: "2026-10-25T12:05:00.000Z",
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: "2026-10-25T12:00:00.000Z",
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy" });
  const rejected = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { email: "Seller@Example.com" }, { origin: "https://foreign.invalid", "x-lm-web-csrf": f.csrf }), rejected, f.deps);
  assert.equal(rejected.statusCode, 403);
  assert.equal(f.calls.length, 1);
});

test("Capafy OTP is not sent until the publisher explicitly accepts both current policies", async () => {
  for (const body of [
    { email: "seller@example.com" },
    { email: "seller@example.com", termsAccepted: true, privacyAccepted: false },
    { email: "seller@example.com", termsAccepted: false, privacyAccepted: true },
    { email: "seller@example.com", termsAccepted: "true", privacyAccepted: true },
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
    { email: "seller@example.com", termsAccepted: true, privacyAccepted: true },
    { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 202);
  const challenge = require("./maritime-manager-capafy-binding.js").openChallenge(JSON.parse(res.body).challengeRef, {
    tenantId: f.uid, authSubject: SUBJECT, secret: require("./web-auth.js").csrfSecret(f.deps), now: f.deps.now(),
  });
  assert.deepEqual(challenge, { challengeId: "challenge-1", expiresAt: "2026-10-25T12:05:00.000Z",
    policyConsentVersion: "capafy-publisher-terms-privacy-v1", termsAcceptedAt: "2026-10-25T12:00:00.000Z",
    termsUrl: "https://api.capafy.ai/terms-of-service", privacyUrl: "https://api.capafy.ai/privacy-policy" });
  assert.deepEqual(f.calls, [["start", "seller@example.com"]]);
});

test("Capafy OTP verify binds the official verified seller to the signed Life Manager tenant and keeps token private", async () => {
  const f = capafyConnectionFixture();
  const started = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { email: "seller@example.com", termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), started, f.deps);
  const challengeRef = JSON.parse(started.body).challengeRef;
  const done = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/verify", "POST", {
    challengeRef, code: "004219", autonomyConsentVersion: "maritime-capafy-autonomy-v1",
  }, { "x-lm-web-csrf": f.csrf }), done, f.deps);
  assert.equal(done.statusCode, 200);
  assert.equal(JSON.parse(done.body).status, "connected");
  assert.doesNotMatch(done.body, /am_sk_|seller@example.com|accessToken/i);
  assert.deepEqual(f.calls, [["start", "seller@example.com"], ["verify", { challengeId: "challenge-1", code: "004219" }]]);
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
    { email: "seller@example.com", termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
  assert.equal(res.statusCode, 409);
  assert.equal(f.calls.length, 0);
  assert.equal(f.bindingWrites.length, 0);
});

test("Capafy OTP is not sent until the cloud encryption key is configured", async () => {
  const f = capafyConnectionFixture();
  f.deps.capafyBindingStore.assertConfigured = () => { throw new Error("maritime_capafy_encryption_unavailable"); };
  const res = response();
  await handleMaritimeManagerCapafyConnection(request("/maritime/capafy/connect/start", "POST",
    { email: "seller@example.com", termsAccepted: true, privacyAccepted: true }, { "x-lm-web-csrf": f.csrf }), res, f.deps);
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
  assert.equal(dependencies.distributionStore, dependencies.managerPersistence);
  assert.equal(dependencies.cfoReceiptIO, dependencies.managerPersistence.cfoReceiptIO);
  assert.equal(await dependencies.managerStore.read(uid), null);
  assert.equal(await dependencies.ensureWebUserImpl(subject), uid);
  assert.equal(queries.length, 3);
  assert.match(queries[0].statement, /lm_maritime_manager_enrollments/);
  assert.deepEqual(queries[0].values, [uid]);
  assert.match(queries[1].statement, /lm_maritime_manager_identities/);
  assert.match(queries[2].statement, /lm_maritime_manager_identities/);
});
