"use strict";

const { createHmac, createHash } = require("node:crypto");
const { recordWebFunnelEvent } = require("./web-funnel-events.js");
const { sanitizeWebAttribution } = require("./web-attribution.js");

const DEFAULT_PUBLIC_MAX_USERS = 25;
const MAX_PUBLIC_USERS = 1000;
const CONSENT_VERSION = "maritime-retention-v1";
const MANAGER_CONSENT_VERSION = "maritime-manager-v1";
const PARTICIPANT_ID_RE = /^[a-f0-9]{64}$/;
const SOURCES = new Set([
  "landing", "aniccaai", "x", "instagram", "reddit", "discord", "telegram", "community", "referral", "hackathon", "direct", "other",
]);
const ANONYMOUS_EVENTS = new Set(["maritime_landing_view", "maritime_cta_click"]);
const MANAGER_EVENTS = new Set(["maritime_email_verified", "maritime_manager_activated", "maritime_work_completed", "maritime_report_sent", "maritime_returned"]);
const USER_EVENTS = new Set([
  "maritime_start", "maritime_consent", "maritime_consent_revoked",
  "maritime_first_response", "maritime_7day_return", ...MANAGER_EVENTS,
]);

function parseMaritimeMaxUsers(value) {
  if (value == null || String(value).trim() === "") return DEFAULT_PUBLIC_MAX_USERS;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 1 && parsed <= MAX_PUBLIC_USERS ? parsed : null;
}

function normalizeMaritimeSource(value) {
  const source = String(value || "").trim().toLowerCase();
  return SOURCES.has(source) ? source : "other";
}

function parseMaritimeStartPayload(value) {
  const text = String(value || "").trim();
  const match = /^\/start(?:@[A-Za-z0-9_]+)?\s+maritime_([a-z0-9_-]{1,40})$/i.exec(text);
  return match ? { source: normalizeMaritimeSource(match[1]) } : null;
}

function sourceAttribution(source, medium = "telegram") {
  return {
    utm_source: `maritime-${normalizeMaritimeSource(source)}`,
    utm_medium: medium,
    utm_campaign: "the-first-1000",
  };
}

function renderMaritimeLanding({ source = "direct", language = "en", user = null, state = null, telegramAvailable = false,
  capafyStatus = null } = {}) {
  const campaignSource = normalizeMaritimeSource(source);
  const ja = String(language).toLowerCase().startsWith("ja");
  const escape = value => String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const copy = ja ? {
    title: "あなたの人生を先回りして支える、Life Manager Cloud。",
    intro: "仕事、お金、日々の用事、身体、心。Life Managerは必要な仕事を選び、実行して結果を確かめる汎用エージェントです。Cloud版はMaritime上のテナント別環境で動くよう設計されています。目標・予算の入力は必須ではありません。Telegramは任意です。",
    scope: "Cloudの商品作成からCapafy公開までの接続は開発中です。公式の公開レシートが確認されるまでは、商品公開・売上・入金を完了済みとは表示しません。",
    notice: "開始後、業務に必要な入力・結果をMaritimeへ送信します。Maritime AI credits経由のmodel callは、同社Privacy Policy上、account削除後も無期限保持の対象です。停止は送信済みデータの削除ではありません。",
    email: "メールアドレス", signup: "確認メールを受け取る", check: "確認メールを送信しました。このブラウザでリンクを開いてください。",
    consent: "Maritimeのデータ保持条件を確認し、Life Manager Cloudの自律実行を許可します。", activate: "Life Manager Cloudを開始する",
    queued: "Cloud環境の準備を受け付けました。公開や収益は公式レシートで確認できた場合だけ表示します。",
    failed: "開始できませんでした。しばらくしてから状態を確認してください。", signedIn: "確認済みメール",
    stop: "Life Managerを停止する", stopped: "新しい仕事と今後のメールを停止しました。", stopPending: "新しい仕事と今後のメールは停止済みです。一部の停止設定は確認待ちです。", stopFailed: "停止を確認できませんでした。もう一度お試しください。",
    stopNote: "進行中の処理は完了する場合があります。その結果確認は続けます。既存データは削除しません。",
    capafyTitle: "収益ワークフロー · Capafy",
    capafyDescription: "ご本人の検証済みCapafy開発者アカウントを接続できます。トークンはテナントごとに暗号化して保存され、画面には返しません。切断するとLife Manager内のトークンを削除しますが、Capafy側のセッションは失効しません。接続だけでは公開されず、売上も保証されません。",
    capafyEmail: "Capafyアカウントのメールアドレス", capafyStart: "確認コードを送信", capafyCode: "Capafyから届いた確認コード",
    capafyConsent: "Capafyの公式確認手順に従い、今後の商品準備・公開にこのアカウントを使うことを許可します。",
    capafyVerify: "アカウントを確認して接続", capafyConnected: "Capafy開発者アカウントを接続済み（接続時に本人確認済み）",
    capafyDisconnect: "Capafyを切断する", capafyUnavailable: "アカウント接続状態を確認できません。時間をおいて再読み込みしてください。",
    capafyDisabled: "このCloud環境ではCapafy接続はまだ有効化されていません。",
    capafyCheck: "Capafyから届いたコードを入力し、利用許可を確認してください。", capafySaved: "Capafyアカウントを接続しました。",
    capafyRemoved: "Capafyアカウントを切断しました。", capafyFailed: "Capafyとの接続を確認できませんでした。状態を確認して再試行してください。",
    states: { pending: "開始準備中", provisioning: "開始準備中", active: "稼働中", paused: "停止中", effect_unknown: "実行結果を確認中" },
  } : {
    title: "Your whole life. A manager that takes initiative.",
    intro: "Work, money, everyday tasks, body, and mind. Life Manager is a proactive general agent designed to choose useful work, act, and verify results. Life Manager Cloud is designed to run in a tenant-isolated Maritime environment. Goal and budget setup are not required. Telegram is optional.",
    scope: "The Cloud path from product creation to Capafy publication is still being connected. We show publication, sales, and payouts only after official provider receipts confirm them.",
    notice: "Starting Life Manager Cloud sends necessary work inputs and results to Maritime. Its Privacy Policy says model calls through Maritime AI credits are retained indefinitely, including after account deletion. Stopping does not delete previously sent data.",
    email: "Email address", signup: "Continue with email", check: "Check your email and open the link in this browser.",
    consent: "I have reviewed Maritime's data-retention terms and authorize Life Manager Cloud to run work autonomously.", activate: "Start Life Manager Cloud",
    queued: "Your Cloud environment is being prepared. Publications and earnings appear only after official receipts confirm them.",
    failed: "We could not start the manager. Please check the status again shortly.", signedIn: "Verified email",
    stop: "Stop Life Manager", stopped: "New work and future emails are paused.", stopPending: "New work and future emails are paused. Some stop settings are awaiting confirmation.", stopFailed: "We could not confirm the stop. Please try again.",
    stopNote: "Work already in progress may finish. Its result checks continue. Existing data is retained.",
    capafyTitle: "Money workflow · Capafy",
    capafyDescription: "Connect your own verified Capafy developer account. Its access token is encrypted for your tenant and is never returned to this page. Disconnecting removes Life Manager's stored token but does not revoke your Capafy sessions. Connecting alone does not publish anything or guarantee sales.",
    capafyEmail: "Email on your Capafy account", capafyStart: "Send verification code", capafyCode: "Verification code from Capafy",
    capafyConsent: "I authorize Life Manager to use this account for future product preparation and publication, following Capafy's required confirmation steps.",
    capafyVerify: "Verify and connect account", capafyConnected: "Capafy developer account connected (verified when linked)",
    capafyDisconnect: "Disconnect Capafy", capafyUnavailable: "We could not verify the connection status. Reload and try again later.",
    capafyDisabled: "Capafy account connection is not enabled on this Cloud environment yet.",
    capafyCheck: "Enter the code Capafy emailed you and confirm the account authorization.", capafySaved: "Capafy account connected.",
    capafyRemoved: "Capafy account disconnected.", capafyFailed: "We could not confirm the Capafy connection. Check the status and try again.",
    states: { pending: "Preparing your manager", provisioning: "Preparing your manager", active: "Active", paused: "Paused", effect_unknown: "Checking execution results" },
  };
  const ready = user && state == null;
  const controls = !user
    ? `<form id="signup" method="post" action="/auth/maritime/email"><label for="email">${copy.email}</label><input id="email" name="email" type="email" autocomplete="email" required maxlength="320"><button type="submit">${copy.signup}</button></form>`
    : `<p>${copy.signedIn}: <strong>${escape(user.email)}</strong></p>${ready
      ? `<label class="consent"><input id="consent" type="checkbox">${copy.consent}</label><button type="button" data-action="activate" data-csrf="${escape(user.csrf)}" data-consent="${MANAGER_CONSENT_VERSION}" disabled>${copy.activate}</button>`
      : `<p role="status" data-manager-state>${copy.states[state] || copy.failed}</p>`}`;
  const capafyPanel = user && state === "active" && capafyStatus != null ? `<section id="capafy-account"><h2>${copy.capafyTitle}</h2><p>${copy.capafyDescription}</p>${capafyStatus === "connected"
    ? `<p role="status">${copy.capafyConnected}</p><button type="button" data-action="capafy-disconnect" data-csrf="${escape(user.csrf)}">${copy.capafyDisconnect}</button>`
    : capafyStatus === "not_connected" ? `<form data-action="capafy-connect" data-csrf="${escape(user.csrf)}"><label for="capafy-email">${copy.capafyEmail}</label><input id="capafy-email" name="email" type="email" autocomplete="email" required maxlength="320"><button type="submit">${copy.capafyStart}</button><div id="capafy-verification" hidden><label for="capafy-code">${copy.capafyCode}</label><input id="capafy-code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{4,8}" required><label class="consent"><input id="capafy-consent" type="checkbox">${copy.capafyConsent}</label><button id="capafy-verify" type="button" data-csrf="${escape(user.csrf)}" data-consent="maritime-capafy-autonomy-v1" disabled>${copy.capafyVerify}</button></div></form><p id="capafy-feedback" role="status" aria-live="polite"></p>`
      : `<p role="status">${capafyStatus === "disabled" ? copy.capafyDisabled : copy.capafyUnavailable}</p>`}</section>` : "";
  const stopControl = user ? `<button type="button" data-action="stop" data-csrf="${escape(user.csrf)}"${state == null ? " hidden" : ""}>${copy.stop}</button><p>${copy.stopNote}</p>` : "";
  const telegram = telegramAvailable ? `<p><a href="/maritime/start?source=${campaignSource}">Telegram (${ja ? "任意" : "optional"})</a></p>` : "";
  return `<!doctype html><html lang="${ja ? "ja" : "en"}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Life Manager Cloud</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:760px;margin:8vh auto;padding:0 24px;color:#17222d}h1{font-size:clamp(2rem,6vw,3.4rem);line-height:1.1}section{border:1px solid #d6d6d0;border-radius:12px;padding:16px 20px;margin:24px 0}.notice{border-left:3px solid #b9832e;padding:12px 16px;background:#fbf7ef}input[type=email],input[inputmode]{display:block;width:min(95%,420px);padding:12px;margin:8px 0;font:inherit}button{display:block;margin:16px 0;padding:12px 20px;border:0;border-radius:28px;background:#c99439;font:inherit;font-weight:700;cursor:pointer}button:disabled{opacity:.5;cursor:default}button[hidden]{display:none}[hidden]{display:none!important}.consent{display:block;margin-top:20px}</style><main data-source="${campaignSource}"><p>Life Manager Cloud</p><h1>${copy.title}</h1><p>${copy.intro}</p><p>${copy.scope}</p><p class="notice">${copy.notice}</p><p><a href="https://maritime.sh/privacy" rel="noreferrer">Maritime Privacy Policy</a></p>${controls}${capafyPanel}${stopControl}<p id="feedback" role="status" aria-live="polite"></p>${telegram}<noscript>${ja ? "メール登録後の開始にはJavaScriptを有効にしてください。" : "Enable JavaScript to activate Life Manager Cloud after email confirmation."}</noscript></main><script>
const feedback=document.getElementById('feedback');
const main=document.querySelector('main');
let source=main.dataset.source;
let attribution={};
try{const params=new URLSearchParams(location.search);for(const key of ['utm_source','utm_medium','utm_campaign','utm_content','utm_term']){const values=params.getAll(key);if(values.length===1&&new TextEncoder().encode(values[0]).length<=200)attribution[key]=values[0];}const key='lm-maritime-first-source';const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved&&typeof saved.source==='string'&&Date.now()-saved.at<30*86400000){source=saved.source;attribution=saved.attribution&&typeof saved.attribution==='object'&&!Array.isArray(saved.attribution)?saved.attribution:{};}else localStorage.setItem(key,JSON.stringify({source,attribution,at:Date.now()}));}catch{}
const form=document.getElementById('signup');
if(form)form.addEventListener('submit',async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;try{const result=await fetch(form.action,{method:'POST',headers:{'content-type':'application/json'},credentials:'same-origin',body:JSON.stringify({email:form.elements.email.value,attribution})});feedback.textContent=result.ok?${JSON.stringify(copy.check)}:${JSON.stringify(copy.failed)};}catch{feedback.textContent=${JSON.stringify(copy.failed)};}finally{button.disabled=false;}});
const activate=document.querySelector('[data-action="activate"]');
if(activate){const consent=document.getElementById('consent');consent.addEventListener('change',()=>{activate.disabled=!consent.checked;});activate.addEventListener('click',async()=>{if(!consent.checked)return;activate.disabled=true;try{const result=await fetch('/maritime/activate',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-lm-web-csrf':activate.dataset.csrf},body:JSON.stringify({consentVersion:activate.dataset.consent,source,attribution,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC'})});if(result.ok){feedback.textContent=${JSON.stringify(copy.queued)};activate.remove();consent.disabled=true;const stop=document.querySelector('[data-action="stop"]');if(stop)stop.hidden=false;}else{feedback.textContent=${JSON.stringify(copy.failed)};activate.disabled=false;}}catch{feedback.textContent=${JSON.stringify(copy.failed)};activate.disabled=false;}});}
const capafyForm=document.querySelector('[data-action="capafy-connect"]');
if(capafyForm){let challengeRef='';const capafyFeedback=document.getElementById('capafy-feedback'),verify=document.getElementById('capafy-verify'),verifyConsent=document.getElementById('capafy-consent'),code=document.getElementById('capafy-code');capafyForm.addEventListener('submit',async event=>{event.preventDefault();const button=capafyForm.querySelector('button[type="submit"]');button.disabled=true;try{const result=await fetch('/maritime/capafy/connect/start',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-lm-web-csrf':capafyForm.dataset.csrf},body:JSON.stringify({email:capafyForm.elements.email.value})});const data=await result.json();if(result.ok&&data.status==='check_email'&&typeof data.challengeRef==='string'){challengeRef=data.challengeRef;document.getElementById('capafy-verification').hidden=false;capafyFeedback.textContent=${JSON.stringify(copy.capafyCheck)};}else capafyFeedback.textContent=${JSON.stringify(copy.capafyFailed)};}catch{capafyFeedback.textContent=${JSON.stringify(copy.capafyFailed)};}finally{button.disabled=false;}});const updateVerify=()=>{verify.disabled=!challengeRef||!(/^[0-9]{4,8}$/.test(code.value))||!verifyConsent.checked;};code.addEventListener('input',updateVerify);verifyConsent.addEventListener('change',updateVerify);verify.addEventListener('click',async()=>{if(verify.disabled)return;verify.disabled=true;try{const result=await fetch('/maritime/capafy/connect/verify',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-lm-web-csrf':verify.dataset.csrf},body:JSON.stringify({challengeRef,code:code.value,autonomyConsentVersion:verify.dataset.consent})});if(result.ok){capafyFeedback.textContent=${JSON.stringify(copy.capafySaved)};location.reload();}else capafyFeedback.textContent=${JSON.stringify(copy.capafyFailed)};}catch{capafyFeedback.textContent=${JSON.stringify(copy.capafyFailed)};}finally{verify.disabled=false;}});}
const capafyDisconnect=document.querySelector('[data-action="capafy-disconnect"]');
if(capafyDisconnect)capafyDisconnect.addEventListener('click',async()=>{capafyDisconnect.disabled=true;try{const result=await fetch('/maritime/capafy/connect/disconnect',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-lm-web-csrf':capafyDisconnect.dataset.csrf},body:'{}'});if(result.ok)location.reload();else{const node=document.createElement('p');node.setAttribute('role','status');node.textContent=${JSON.stringify(copy.capafyFailed)};document.getElementById('capafy-account').append(node);}}catch{const node=document.createElement('p');node.setAttribute('role','status');node.textContent=${JSON.stringify(copy.capafyFailed)};document.getElementById('capafy-account').append(node);}finally{capafyDisconnect.disabled=false;}});
const stopControl=document.querySelector('[data-action="stop"]');
if(stopControl)stopControl.addEventListener('click',async()=>{stopControl.disabled=true;try{const result=await fetch('/maritime/stop',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-lm-web-csrf':stopControl.dataset.csrf},body:'{}'});const body=await result.json();if(body.status==='paused'){feedback.textContent=body.cleanupPending?${JSON.stringify(copy.stopPending)}:${JSON.stringify(copy.stopped)};const state=document.querySelector('[data-manager-state]');if(state)state.textContent=${JSON.stringify(copy.states.paused)};}else feedback.textContent=${JSON.stringify(copy.stopFailed)};}catch{feedback.textContent=${JSON.stringify(copy.stopFailed)};}finally{stopControl.disabled=false;}});
</script></html>`;
}

function createMaritimeDistributionStore({
  env = process.env,
  supaUrl,
  supaKey,
  fetchImpl = globalThis.fetch,
  recordEventImpl = recordWebFunnelEvent,
  now = () => Date.now(),
} = {}) {
  const base = String(supaUrl || env.SUPABASE_URL || "").replace(/\/$/, "");
  const key = String(supaKey || env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  const uidSecret = String(env.LM_UID_SECRET || "");
  const maxUsers = parseMaritimeMaxUsers(env.MARITIME_PILOT_MAX_USERS);
  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  };

  function ready() {
    return Boolean(base && key && uidSecret && typeof fetchImpl === "function");
  }

  function participantId(uid) {
    const value = String(uid || "");
    if (!value || value.length > 128 || !uidSecret) return null;
    return createHmac("sha256", uidSecret).update(`maritime:participant:${value}`).digest("hex");
  }

  async function writeEvent(eventName, { uid, source = "other", medium = "telegram", eventKey = "once", attribution, audienceKind, occurredAt } = {}) {
    if (!ANONYMOUS_EVENTS.has(eventName) && !USER_EVENTS.has(eventName)) return false;
    if (typeof recordEventImpl !== "function") return false;
    const id = uid == null ? null : participantId(uid);
    if (uid != null && !id) return false;
    const event = {
      eventName,
      uid: null,
      sourceObjectId: id,
      ...(id ? { sourceEventId: MANAGER_EVENTS.has(eventName) ? 'maritime:' + createHash('sha256').update(`${id}:${eventName}:${eventKey}`).digest('hex') : `maritime:${id}:${eventName}` } : {}),
      ...(audienceKind ? { audienceKind } : {}),
      attribution: { ...sourceAttribution(source, medium), ...sanitizeWebAttribution(attribution) },
      occurredAt: occurredAt || new Date(Number(now())).toISOString(),
    };
    try {
      return (await recordEventImpl(event, {
        supaUrl: base,
        supaKey: key,
        fetchImpl,
        nowMs: Number(now()),
      })) !== false;
    } catch { return false; }
  }

  async function recordManagerEvent(eventName, uid, options = {}) {
    const uidPattern = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const internal = String(env.LM_MARITIME_INTERNAL_UIDS || "").split(/[\s,]+/).filter(Boolean);
    const eventKey = options.eventKey || "once";
    if (!MANAGER_EVENTS.has(eventName) || !uidPattern.test(uid || "") || internal.some(value => !uidPattern.test(value))
      || typeof eventKey !== "string" || !/^[A-Za-z0-9._:-]{1,200}$/.test(eventKey)
      || (options.occurredAt !== undefined && (typeof options.occurredAt !== "string" || !Number.isFinite(Date.parse(options.occurredAt))))) return false;
    return writeEvent(eventName, { uid, source: normalizeMaritimeSource(options.source || "other"), medium: "web",
      eventKey, attribution: options.attribution, occurredAt: options.occurredAt,
      audienceKind: internal.some(value => value.toLowerCase() === uid.toLowerCase()) ? "internal" : "external" });
  }
  async function recordAnonymousEvent(eventName, source) {
    if (!ANONYMOUS_EVENTS.has(eventName)) return false;
    return writeEvent(eventName, { source, medium: "web" });
  }

  async function recordConsentEvent(uid, source, medium = "telegram") {
    if (typeof uid !== "string" || !uid || uid.length > 128) return false;
    return writeEvent("maritime_consent", { uid, source: normalizeMaritimeSource(source), medium });
  }

  async function recordConsentRevokedEvent(uid, source, medium = "telegram") {
    if (typeof uid !== "string" || !uid || uid.length > 128) return false;
    return writeEvent("maritime_consent_revoked", { uid, source: normalizeMaritimeSource(source), medium });
  }

  async function recordStart(uid, source) {
    return writeEvent("maritime_start", { uid, source });
  }

  async function startSource(uid) {
    const id = participantId(uid);
    if (!ready() || !id) return null;
    const url = new URL(`${base}/rest/v1/lm_web_funnel_events`);
    url.searchParams.set("source_object_id", `eq.${id}`);
    url.searchParams.set("event_name", "eq.maritime_start");
    url.searchParams.set("select", "attribution,occurred_at");
    url.searchParams.set("order", "occurred_at.asc");
    url.searchParams.set("limit", "1");
    let response;
    try { response = await fetchImpl(url.toString(), { headers }); }
    catch { return null; }
    if (!response || !response.ok) return null;
    const rows = await response.json().catch(() => null);
    if (!Array.isArray(rows) || rows.length !== 1) return null;
    const source = String(rows[0]?.attribution?.utm_source || "");
    return source.startsWith("maritime-") ? normalizeMaritimeSource(source.slice("maritime-".length)) : null;
  }

  async function getParticipant(uid) {
    const id = participantId(uid);
    if (!ready() || !id || !PARTICIPANT_ID_RE.test(id)) return { ok: false, participant: null };
    const url = new URL(`${base}/rest/v1/lm_maritime_pilot_participants`);
    url.searchParams.set("participant_id", `eq.${id}`);
    url.searchParams.set("select", "participant_id,source,consent_version,consented_at,revoked_at,first_response_at,returned_at");
    url.searchParams.set("limit", "2");
    let response;
    try { response = await fetchImpl(url.toString(), { headers }); }
    catch { return { ok: false, participant: null }; }
    if (!response || !response.ok) return { ok: false, participant: null };
    const rows = await response.json().catch(() => null);
    if (!Array.isArray(rows) || rows.length > 1) return { ok: false, participant: null };
    return { ok: true, participant: rows[0] || null };
  }

  async function callRpc(name, body) {
    if (!ready()) return { ok: false, result: null };
    let response;
    try {
      response = await fetchImpl(`${base}/rest/v1/rpc/${name}`, {
        method: "POST", headers, body: JSON.stringify(body),
      });
    } catch { return { ok: false, result: null }; }
    if (!response || !response.ok) return { ok: false, result: null };
    return { ok: true, result: await response.json().catch(() => null) };
  }

  async function accept(uid, source) {
    const id = participantId(uid);
    const campaignSource = normalizeMaritimeSource(source);
    if (!ready() || !id || maxUsers == null) return { ok: false, status: "unavailable" };
    const result = await callRpc("claim_lm_maritime_participant_v1", {
      p_participant_id: id,
      p_source: campaignSource,
      p_consent_version: CONSENT_VERSION,
      p_max_users: maxUsers,
      p_now: new Date(Number(now())).toISOString(),
    });
    if (!result.ok || !["consented", "already_consented", "capacity_full"].includes(result.result)) {
      return { ok: false, status: "unavailable" };
    }
    if (result.result === "capacity_full") return { ok: false, status: "capacity_full" };
    await recordConsentEvent(uid, campaignSource);
    return { ok: true, status: result.result };
  }

  async function isConsentActive(uid) {
    const result = await getParticipant(uid);
    const row = result.participant;
    return result.ok && Boolean(row && row.consent_version === CONSENT_VERSION && row.consented_at && !row.revoked_at);
  }

  async function revoke(uid) {
    const existing = await getParticipant(uid);
    const row = existing.participant;
    if (!existing.ok || !row || row.consent_version !== CONSENT_VERSION || !row.consented_at || row.revoked_at) return false;
    const id = participantId(uid);
    const revokedAt = new Date(Number(now())).toISOString();
    const url = new URL(`${base}/rest/v1/lm_maritime_pilot_participants`);
    url.searchParams.set("participant_id", `eq.${id}`);
    url.searchParams.set("revoked_at", "is.null");
    let response;
    try {
      response = await fetchImpl(url.toString(), {
        method: "PATCH",
        headers: { ...headers, Prefer: "return=representation" },
        body: JSON.stringify({ revoked_at: revokedAt, updated_at: revokedAt }),
      });
    } catch { return false; }
    if (!response || !response.ok) return false;
    const rows = await response.json().catch(() => null);
    if (!Array.isArray(rows) || rows.length !== 1) return false;
    await recordConsentRevokedEvent(uid, row.source);
    return true;
  }

  async function recordSuccessfulUse(uid) {
    const id = participantId(uid);
    if (!id) return false;
    const result = await callRpc("mark_lm_maritime_pilot_milestone_v1", {
      p_participant_id: id,
      p_milestone: "successful_use",
      p_at: new Date(Number(now())).toISOString(),
    });
    // The RPC updates the participant row and appends the corresponding funnel event
    // in one PostgreSQL transaction. A successful state write therefore cannot leave
    // an unrepairable gap in the append-only event ledger.
    return result.ok && result.result === true;
  }

  return Object.freeze({
    maxUsers,
    participantId,
    getParticipant,
    recordAnonymousEvent,
    recordConsentEvent,
    recordConsentRevokedEvent,
    recordManagerEvent,
    recordStart,
    startSource,
    accept,
    isConsentActive,
    revoke,
    recordSuccessfulUse,
  });
}

module.exports = {
  CONSENT_VERSION,
  MANAGER_CONSENT_VERSION,
  DEFAULT_PUBLIC_MAX_USERS,
  MAX_PUBLIC_USERS,
  parseMaritimeMaxUsers,
  normalizeMaritimeSource,
  parseMaritimeStartPayload,
  renderMaritimeLanding,
  createMaritimeDistributionStore,
};
