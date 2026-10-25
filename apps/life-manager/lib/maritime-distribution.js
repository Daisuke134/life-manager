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

function renderMaritimeLanding({ source = "direct", language = "en", user = null, state = null, telegramAvailable = false } = {}) {
  const campaignSource = normalizeMaritimeSource(source);
  const ja = String(language).toLowerCase().startsWith("ja");
  const escape = value => String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const copy = ja ? {
    title: "暮らしの仕事を進める、Life Manager Cloud。",
    intro: "Googleログインは本人確認だけに使用し、Calendar接続やGmail受信箱の読み取り権限は求めません。仕事の概要は確認済みのメールアドレスへ送る設計です。Calendarは必要な仕事が出た時に接続できます。目標・予算の入力は不要で、Telegramは任意です。",
    scope: "まずCapafyの制作・配布・収益化ワークフローをCloudへ接続しています。最初のSkill公開前にPublisher Certificationが必要で、本人確認と返金不可のUS$0.99申請料がかかります。必要書類は地域・Publisher種別で異なります。Capafyによると、振込先情報は認証後に追加でき、公開前には不要です。仕事の完了から確認済みの結果、メール報告までの全経路はまだ検証中です。収益は保証されません。",
    notice: "開始後、業務に必要な入力と結果をMaritimeへ送信します。Maritime AI credits経由のmodel callは、MaritimeのPrivacy Policy上、アカウント削除後も無期限保持の対象です。停止しても送信済みデータは削除されません。",
    googleSignin: "Googleアカウントで続ける",
    consent: "データ保持条件を確認し、自律実行と確認済みメールへの状況・結果レポートに同意します。", activate: "Life Manager Cloudを開始する",
    queued: "開始を受け付けました。専用VMの準備を進めています。仕事の完了や収益は、確認できる結果が得られるまで確定扱いしません。",
    failed: "開始できませんでした。しばらくしてから状態を確認してください。", signedIn: "確認済みメール",
    stop: "Life Managerを停止する", stopped: "新しい仕事と今後のメールを停止しました。", stopPending: "新しい仕事と今後のメールは停止済みです。一部の停止設定は確認待ちです。", stopFailed: "停止を確認できませんでした。もう一度お試しください。",
    stopNote: "進行中の処理は完了する場合があります。その結果確認は続けます。既存データは削除しません。",
    states: { pending: "開始準備中", provisioning: "開始準備中", active: "稼働中", paused: "停止中", effect_unknown: "実行結果を確認中" },
  } : {
    title: "Life Manager Cloud gets your work moving.",
    intro: "Google sign-in confirms your identity only; it does not connect Calendar or grant inbox access. Life Manager Cloud is designed to email work summaries to that verified address. Calendar can be connected later if a task needs it. Goals, budgets, and Telegram setup are not required to get started.",
    scope: "We are connecting the first Capafy creation-and-distribution workflow to the Cloud runtime. Capafy requires Publisher Certification before your first Skill can publish, including an identity review and a non-refundable US$0.99 application fee; required documents depend on region and publisher type. Capafy says payout details can be added after certification and are not required to publish. The complete path from work through verified result and email report has not yet been verified. Earnings are not guaranteed.",
    notice: "Starting Life Manager Cloud sends necessary work inputs and results to Maritime. Maritime’s Privacy Policy says model calls through Maritime AI credits can be retained indefinitely, including after account deletion. Stopping does not delete previously sent data.",
    googleSignin: "Continue with Google",
    consent: "I have read the data-retention terms, agree to autonomous work, and agree to receive status and result reports at my verified sign-in email.", activate: "Start Life Manager Cloud",
    queued: "Your start request is queued and your dedicated VM is being prepared. Work and earnings are not treated as complete until results are verified.",
    failed: "We could not start the manager. Please check the status again shortly.", signedIn: "Verified email",
    stop: "Stop Life Manager", stopped: "New work and future emails are paused.", stopPending: "New work and future emails are paused. Some stop settings are awaiting confirmation.", stopFailed: "We could not confirm the stop. Please try again.",
    stopNote: "Work already in progress may finish. Its result checks continue. Existing data is retained.",
    states: { pending: "Preparing your manager", provisioning: "Preparing your manager", active: "Active", paused: "Paused", effect_unknown: "Checking execution results" },
  };
  const ready = user && state == null;
  const controls = !user
    ? `<a class="signin" id="google-signin" href="/auth/google?intent=maritime_cloud&lang=${ja ? "ja" : "en"}">${copy.googleSignin}</a>`
    : `<p>${copy.signedIn}: <strong>${escape(user.email)}</strong></p>${ready
      ? `<label class="consent"><input id="consent" type="checkbox">${copy.consent}</label><button type="button" data-action="activate" data-csrf="${escape(user.csrf)}" data-consent="${MANAGER_CONSENT_VERSION}" disabled>${copy.activate}</button>`
      : `<p role="status" data-manager-state>${copy.states[state] || copy.failed}</p>`}`;
  const stopControl = user ? `<button type="button" data-action="stop" data-csrf="${escape(user.csrf)}"${state == null ? " hidden" : ""}>${copy.stop}</button><p>${copy.stopNote}</p>` : "";
  const telegram = telegramAvailable ? `<p><a href="/maritime/start?source=${campaignSource}">Telegram (${ja ? "任意" : "optional"})</a></p>` : "";
  return `<!doctype html><html lang="${ja ? "ja" : "en"}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Life Manager Cloud</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:760px;margin:8vh auto;padding:0 24px;color:#17222d}h1{font-size:clamp(2rem,6vw,3.4rem);line-height:1.1}.notice{border-left:3px solid #b9832e;padding:12px 16px;background:#fbf7ef}.signin{display:inline-block;margin:16px 0;padding:12px 20px;border-radius:8px;background:#172a23;color:#fff;font:inherit;font-weight:700;text-decoration:none}button{display:block;margin:16px 0;padding:12px 20px;border:0;border-radius:8px;background:#172a23;color:#fff;font:inherit;font-weight:700;cursor:pointer}button:disabled{opacity:.5;cursor:default}button[hidden]{display:none}.consent{display:block;margin-top:20px}</style><main data-source="${campaignSource}"><p>Life Manager Cloud</p><h1>${copy.title}</h1><p>${copy.intro}</p><p>${copy.scope}</p><p class="notice">${copy.notice}</p><p><a href="https://maritime.sh/privacy" rel="noreferrer">${ja ? "Maritimeのプライバシーポリシー" : "Maritime Privacy Policy"}</a></p>${controls}${stopControl}<p id="feedback" role="status" aria-live="polite"></p>${telegram}<noscript>${ja ? "開始と状態確認にはJavaScriptを有効にしてください。" : "Enable JavaScript to start Life Manager Cloud and check its status."}</noscript></main><script>
const feedback=document.getElementById('feedback');
const main=document.querySelector('main');
let source=main.dataset.source;
let attribution={};
try{const keys=['utm_source','utm_medium','utm_campaign','utm_content','utm_term'];const params=new URLSearchParams(location.search);for(const key of keys){const values=params.getAll(key);if(values.length===1&&new TextEncoder().encode(values[0]).length<=200)attribution[key]=values[0];}const key='lm-maritime-first-source';const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved&&typeof saved.source==='string'&&Date.now()-saved.at<30*86400000){source=saved.source;attribution={};if(saved.attribution&&typeof saved.attribution==='object'&&!Array.isArray(saved.attribution))for(const key of keys){const value=saved.attribution[key];if(typeof value==='string'&&new TextEncoder().encode(value).length<=200)attribution[key]=value;}}else localStorage.setItem(key,JSON.stringify({source,attribution,at:Date.now()}));}catch{}
const googleSignin=document.getElementById('google-signin');
if(googleSignin){const params=new URLSearchParams({intent:'maritime_cloud',lang:${JSON.stringify(ja ? "ja" : "en")}});for(const key of ['utm_source','utm_medium','utm_campaign','utm_content','utm_term'])if(typeof attribution[key]==='string')params.set(key,attribution[key]);googleSignin.href='/auth/google?'+params.toString();}
const activate=document.querySelector('[data-action="activate"]');
if(activate){const consent=document.getElementById('consent');consent.addEventListener('change',()=>{activate.disabled=!consent.checked;});activate.addEventListener('click',async()=>{if(!consent.checked)return;activate.disabled=true;try{const result=await fetch('/maritime/activate',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-lm-web-csrf':activate.dataset.csrf},body:JSON.stringify({consentVersion:activate.dataset.consent,source,attribution,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC'})});if(result.ok){feedback.textContent=${JSON.stringify(copy.queued)};activate.remove();consent.disabled=true;const stop=document.querySelector('[data-action="stop"]');if(stop)stop.hidden=false;}else{feedback.textContent=${JSON.stringify(copy.failed)};activate.disabled=false;}}catch{feedback.textContent=${JSON.stringify(copy.failed)};activate.disabled=false;}});}
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
