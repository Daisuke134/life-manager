"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { Readable } = require("node:stream");
let handleMaritimeManagerAuth, resolveMaritimeManagerUser;
try { ({ handleMaritimeManagerAuth, resolveMaritimeManagerUser } = require("./maritime-manager-auth.js")); }
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
