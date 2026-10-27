"use strict";

const { createHmac, createHash } = require("node:crypto");
const { recordWebFunnelEvent } = require("./web-funnel-events.js");
const { sanitizeWebAttribution } = require("./web-attribution.js");

const DEFAULT_PUBLIC_MAX_USERS = 25;
const MAX_PUBLIC_USERS = 1000;
const CONSENT_VERSION = "maritime-retention-v1";
const MANAGER_CONSENT_VERSION = "maritime-manager-v2";
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

function renderMaritimeLanding({ source = "direct", language = "en", user = null, state = null, workbench = null,
  workbenchUnavailable = false, telegramAvailable = false, authError = null, publisherConsent = null,
  publisherConsentAvailable = false } = {}) {
  const campaignSource = normalizeMaritimeSource(source);
  const ja = String(language).toLowerCase().startsWith("ja");
  const escape = value => String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const copy = ja ? {
    title: "暮らしの仕事を進める、Life Manager Cloud。",
    intro: "Googleログインは本人確認とメールアドレスの取得に使用し、Calendar接続や個人Gmail受信箱の読み取り権限は求めません。確認済みメールは連絡先と結果報告に使います。プラットフォームの認証メール確認にはテナント専用の隔離メールボックスを使う予定ですが、自動作成機能はまだ利用できません。個人Gmail受信箱は読み取りません。初回にタスク、目標、予算を入力する必要はありません。Calendarは必要な仕事が出た時に接続できます。Telegramは任意です。",
    scope: "Life Managerは、あなたが承認したPublisherアカウントを使ってCapafyの需要調査・制作・配布・結果確認を自律的に行います。最初のSkill公開前にPublisher Certificationが必要で、本人確認と返金不可のUS$0.99申請料がかかります。必要書類は地域・Publisher種別で異なります。新しいAgentやバージョン更新ごとに、Capafy上で選択したSkillと設定内容を確認・確定する必要があります。規約同意、本人確認、Certification、料金、必要なPublisher確認はご本人が行います。Capafyによると、振込先情報は認証後に追加でき、公開前には不要です。公開や収益を確認できるまで、公開済み・収益発生とは報告しません。仕事から確認済み結果、メール報告までの全経路はまだ検証中です。収益は保証されません。",
    notice: "開始後、業務に必要な入力と結果をMaritimeへ送信します。Maritime AI credits経由のmodel callは、MaritimeのPrivacy Policy上、アカウント削除後も無期限保持の対象です。停止しても送信済みデータは削除されません。",
    googleSignin: "Googleアカウントで続ける",
    signinError: "Googleログインを完了できませんでした。もう一度お試しください。",
    consent: "データ保持条件を確認しました。自律作業を許可し、確認済みサインインメールを使った、承認済みPublisherアカウントの登録・利用に同意します。テナント専用メールボックス機能が利用可能になり、認証メール確認に必要な場合、Life Managerがそれを用意・利用することを許可します。Googleログインだけで個人Gmail受信箱にアクセスすることはなく、読み取りません。確認済みメールへの状況・結果レポートに同意します。規約同意・本人確認・Publisher確認はご本人が行います。", activate: "Life Manager Cloudを開始する", reconsent: "更新内容に同意して続ける",
    queued: "開始を受け付けました。専用VMの準備を進めています。仕事の完了や収益は、確認できる結果が得られるまで確定扱いしません。",
    failed: "開始できませんでした。しばらくしてから状態を確認してください。", signedIn: "確認済みメール",
    stop: "Life Managerを停止する", stopped: "新しい仕事と今後のメールを停止しました。", stopPending: "新しい仕事と今後のメールは停止済みです。一部の停止設定は確認待ちです。", stopFailed: "停止を確認できませんでした。もう一度お試しください。",
    stopNote: "進行中の処理は完了する場合があります。その結果確認は続けます。既存データは削除しません。",
    publisherConsentTitle: "Capafy Publisherの同意",
    publisherAgreement: "Publisher Agreement v1.2",
    publisherEffective: "2026年9月28日発効",
    publisherLanguageNotice: "契約の正式文は英語です。この日本語要約は参考用です。",
    publisherTerms: [
      "個人は居住地の成年年齢に達している必要があります。法人を代表する場合は有効な法人を拘束する権限が必要です。対応地域（Schedule E）に所在し、米国・国連・EUの包括的制裁対象に該当しないことが条件です。",
      "本人、連絡先、振込先、税務情報は最新かつ正確である必要があります。個人・同一支配下の法人は原則Publisherアカウントを一つだけ持てます。公開サポートメールはSkillの掲載ページに表示され、Capafyはあなたに代わって利用者サポートをしません。",
      "初回認証にはUS$0.99の返金不可の認証料がかかり、認証が拒否されても返金されません。ここで料金は請求されません。",
      "データ開示（§§3.4–3.5、8.1–8.7）: Publisher Skillは選択したLLMへ作業ファイルを送り得ます。Capafyも設定済みLLM APIを限定的に審査利用できます。LLM費用はあなた負担です。掲載時はUser Dataの送信先、各社の保持・学習利用を開示し、実行中のUser Dataは機能提供・不具合修正、または利用者の明示同意を得た改善に限って使います。実行ログはinstance cleanup後90日保持され、契約終了時はUser Dataを30日以内に削除または返却します。",
      "サポート義務（§§3.2、4.2–4.3、8.5）: 利用者の問い合わせに合理的な期間内に対応し、既知の不具合・脆弱性を速やかに修正します。Publisher Consoleの紛争を自分で確認し、表示された期限内に回答します（Capafyから別通知はありません）。User Dataを保護し、incidentを知ってから48時間以内にCapafyへ通知します。",
    ],
    publisherRecord: "保存済みの同意",
    publisherAcceptedAt: "同意日時",
    publisherWithdrawnAt: "撤回日時",
    publisherWithdrawn: "この同意は撤回されています。Capafyの操作は停止しています。",
    publisherConsentSubmit: "v1.2を確認して同意する",
    publisherConsentWithdraw: "Publisherの同意を撤回する",
    publisherConsentFailed: "同意を保存できませんでした。内容を確認して再度お試しください。",
    publisherConsentWithdrawFailed: "撤回を確認できませんでした。もう一度お試しください。",
    publisherType: "Publisher種別",
    publisherTypePrompt: "選択してください",
    individual: "個人",
    entity: "法人・組織",
    legalName: "法的氏名または法人名",
    jurisdiction: "居住地または法人の法的管轄地域",
    publicSupportEmail: "公開する利用者サポート用メールアドレス",
    ageAttestation: "私は成人です。",
    entityAuthorityAttestation: "この法人・組織を代表して契約する権限があります。",
    regionAttestation: "私はCapafyが対応する地域の適格なPublisherです。",
    sanctionsAttestation: "私は制裁対象者・地域に該当しません。",
    accurateFactsAttestation: "入力した本人・連絡先情報は正確です。",
    singleAccountAttestation: "私は別のPublisherアカウントを重複して作成・利用しません。",
    feeAttestation: "US$0.99の認証料は返金不可で、認証が拒否されても返金されないことを理解しました。",
    dataAttestation: "上記のデータ処理・共有内容に同意します。",
    supportAttestation: "公開後の利用者サポートと紛争対応の責任を理解しました。",
    agreementAttestation: "Publisher Agreement v1.2を読み、同意します。",
    states: { pending: "開始準備中", provisioning: "開始準備中", consent_required: "同意内容が更新されました。内容を確認して続行してください。", active: "Life Managerは稼働中です。Capafyでの公開と収益はまだ確認できていません。", paused: "停止中", effect_unknown: "実行結果を確認中" },
  } : {
    title: "Life Manager Cloud gets your work moving.",
    intro: "Google sign-in verifies your identity and supplies your verified email address; it does not connect Calendar or grant access to your personal Gmail inbox. Life Manager Cloud uses that address for authorized platform contact and result reports. A tenant-isolated mailbox is the planned path if platform email verification needs inbox access, but automatic mailbox provisioning is not yet available. Life Manager does not read your personal Gmail inbox. No task prompt is needed to start. Calendar can be connected later if a task needs it. Goals, budgets, and Telegram setup are not required to get started.",
    scope: "Life Manager autonomously researches demand, creates work, distributes it through authorized surfaces, and checks outcomes using the Publisher account you authorize. Capafy requires Publisher Certification before your first Skill can publish, including an identity review and a non-refundable US$0.99 application fee; required documents depend on region and publisher type. Capafy requires the publisher to confirm the selected Skills and configuration on Capafy's website for each new or updated version. Terms acceptance, identity checks, certification, fees, and required Publisher confirmations remain yours. Capafy says payout details can be added after certification and are not required to publish. Life Manager will not report a live listing or earnings until Capafy confirms them. The complete path from work through verified result and email report has not yet been verified. Earnings are not guaranteed.",
    notice: "Starting Life Manager Cloud sends necessary work inputs and results to Maritime. Maritime’s Privacy Policy says model calls through Maritime AI credits can be retained indefinitely, including after account deletion. Stopping does not delete previously sent data.",
    googleSignin: "Continue with Google",
    signinError: "Google sign-in did not complete. Please try again.",
    consent: "I have read the data-retention terms. I authorize autonomous work, including using my verified sign-in email to register or sign in to my authorized Publisher account and handle supported platform work. If tenant-mailbox provisioning becomes available and platform email verification needs an inbox, I authorize Life Manager to provision and use a mailbox isolated to my tenant. Google sign-in alone does not grant access to my personal Gmail inbox, and Life Manager will not read it. I agree to receive status and result reports at my verified email. Legal, identity, and Publisher confirmations remain mine.", activate: "Start Life Manager Cloud", reconsent: "Agree to the updated terms and continue",
    queued: "Your start request is queued and your dedicated VM is being prepared. Work and earnings are not treated as complete until results are verified.",
    failed: "We could not start the manager. Please check the status again shortly.", signedIn: "Verified email",
    stop: "Stop Life Manager", stopped: "New work and future emails are paused.", stopPending: "New work and future emails are paused. Some stop settings are awaiting confirmation.", stopFailed: "We could not confirm the stop. Please try again.",
    stopNote: "Work already in progress may finish. Its result checks continue. Existing data is retained.",
    publisherConsentTitle: "Capafy Publisher consent",
    publisherAgreement: "Publisher Agreement v1.2",
    publisherEffective: "Effective September 28, 2026",
    publisherLanguageNotice: "The Agreement's English text is authoritative; this plain-language summary is provided for review.",
    publisherTerms: [
      "An individual must have reached the age of majority where they live. An entity representative must be authorized to bind a valid entity. The Publisher must be in a Schedule E supported region and outside comprehensive U.S., U.N., and E.U. sanctions.",
      "Keep your accurate legal identity and contact facts—legal name, jurisdiction, verified sign-in email, and public support email—plus payout and tax information current. A person or commonly controlled entity may have only one Publisher account unless Capafy approves another in writing. A public support email is required, displayed on your Skill listing, and Capafy does not provide your user support.",
      "The US$0.99 certification fee is non-refundable even if certification is declined. This screen does not charge the fee.",
      "Data disclosures (sections 3.4–3.5 and 8.1–8.7): Publisher Skill may send workspace files through your chosen LLM; Capafy may make limited review calls using the LLM API credential configured in Publisher Console. You bear those LLM costs. Each listing must disclose User Data flows, provider retention, and model-training use. During execution, use User Data only to provide the Skill, fix issues, or improve it with the User's explicit informed consent. Execution logs remain for 90 days after instance cleanup; on termination, delete or return User Data within 30 days.",
      "Customer support and dispute obligations (sections 3.2, 4.2–4.3, and 8.5): Respond to user requests within a reasonable time and promptly fix known defects or vulnerabilities. Monitor Publisher Console and answer disputes within the displayed deadline; Capafy sends no separate dispute notice. Protect User Data and notify Capafy within 48 hours after learning of a data security incident.",
    ],
    publisherRecord: "Recorded consent",
    publisherAcceptedAt: "Accepted at",
    publisherWithdrawnAt: "Withdrawn at",
    publisherWithdrawn: "This consent is withdrawn. Capafy actions are disabled.",
    publisherConsentSubmit: "Review and accept v1.2",
    publisherConsentWithdraw: "Withdraw Publisher consent",
    publisherConsentFailed: "We could not save your consent. Review the terms and try again.",
    publisherConsentWithdrawFailed: "We could not confirm withdrawal. Please try again.",
    publisherType: "Publisher type",
    publisherTypePrompt: "Select one",
    individual: "Individual",
    entity: "Entity or organization",
    legalName: "Legal name or entity name",
    jurisdiction: "Residence or entity jurisdiction",
    publicSupportEmail: "Public customer support email",
    ageAttestation: "I am an adult.",
    entityAuthorityAttestation: "I am authorized to accept for this entity or organization.",
    regionAttestation: "I am eligible as a Publisher in a region supported by Capafy.",
    sanctionsAttestation: "I am not in a sanctioned person or region category.",
    accurateFactsAttestation: "The identity and contact facts I entered are accurate.",
    singleAccountAttestation: "I will not create or use a second Publisher account.",
    feeAttestation: "I understand the US$0.99 certification fee is non-refundable, including if certification is declined.",
    dataAttestation: "I agree to the data processing and sharing described above.",
    supportAttestation: "I understand my customer support and dispute response duties after publication.",
    agreementAttestation: "I have read and agree to Publisher Agreement v1.2.",
    states: { pending: "Preparing your manager", provisioning: "Preparing your manager", consent_required: "Please review and accept the updated authorization before work continues.", active: "Life Manager is active; Capafy listing and earnings are not verified yet.", paused: "Paused", effect_unknown: "Checking execution results" },
  };
  const ready = user && (state == null || state === "consent_required");
  const authFeedback = authError === "connection" ? copy.signinError : "";
  const controls = !user
    ? `<a class="signin" id="google-signin" href="/auth/google?intent=maritime_cloud&lang=${ja ? "ja" : "en"}">${copy.googleSignin}</a>`
    : `<p>${copy.signedIn}: <strong>${escape(user.email)}</strong></p>${ready
      ? `${state === "consent_required" ? `<p role="status">${copy.states.consent_required}</p>` : ""}<label class="consent"><input id="consent" type="checkbox">${copy.consent}</label><button type="button" data-action="activate" data-csrf="${escape(user.csrf)}" data-consent="${MANAGER_CONSENT_VERSION}" disabled>${state === "consent_required" ? copy.reconsent : copy.activate}</button>`
      : `<p role="status" data-manager-state>${copy.states[state] || copy.failed}</p>`}`;
  const stopControl = user ? `<button type="button" data-action="stop" data-csrf="${escape(user.csrf)}"${state == null ? " hidden" : ""}>${copy.stop}</button><p>${copy.stopNote}</p>` : "";
  const telegram = telegramAvailable ? `<p><a href="/maritime/start?source=${campaignSource}">Telegram (${ja ? "任意" : "optional"})</a></p>` : "";
  const workbenchSection = user && state === "active"
    ? require("./maritime-manager-workbench.js").renderMaritimeWorkbench({ language, workbench, unavailable: workbenchUnavailable }) : "";
  const publisherConsentRecord = publisherConsent && publisherConsent.agreementVersion === "v1.2" ? publisherConsent : null;
  const publisherConsentForm = `<form id="publisher-consent-form" data-action="publisher-consent" data-csrf="${escape(user?.csrf || "")}" data-agreement-version="v1.2"><label>${copy.publisherType}<select name="publisherType" required><option value="" selected disabled>${copy.publisherTypePrompt}</option><option value="individual">${copy.individual}</option><option value="entity">${copy.entity}</option></select></label><label>${copy.legalName}<input name="legalName" maxlength="200" autocomplete="name" required></label><label>${copy.jurisdiction}<input name="jurisdiction" maxlength="100" required></label><label>${copy.publicSupportEmail}<input name="publicSupportEmail" type="email" maxlength="320" autocomplete="off" required></label><label><input type="checkbox" name="ageOfMajorityAttested">${copy.ageAttestation}</label><label><input type="checkbox" name="entityAuthorityAttested">${copy.entityAuthorityAttestation}</label><label><input type="checkbox" name="supportedRegionAttested" required>${copy.regionAttestation}</label><label><input type="checkbox" name="sanctionsEligibilityAttested" required>${copy.sanctionsAttestation}</label><label><input type="checkbox" name="identityContactAccurateAttested" required>${copy.accurateFactsAttestation}</label><label><input type="checkbox" name="singlePublisherAccountAttested" required>${copy.singleAccountAttestation}</label><label><input type="checkbox" name="certificationFeeNonRefundableAcknowledged" required>${copy.feeAttestation}</label><label><input type="checkbox" name="dataDisclosuresAccepted" required>${copy.dataAttestation}</label><label><input type="checkbox" name="supportObligationsAccepted" required>${copy.supportAttestation}</label><label><input type="checkbox" name="agreementAccepted" required>${copy.agreementAttestation}</label><button type="submit" disabled>${copy.publisherConsentSubmit}</button></form>`;
  const publisherConsentSaved = publisherConsentRecord ? `<div><p><strong>${copy.publisherRecord}: ${escape(publisherConsentRecord.publisherType === "entity" ? copy.entity : copy.individual)}</strong></p><p>${escape(publisherConsentRecord.legalName)} — ${escape(publisherConsentRecord.jurisdiction)}</p><p>${escape(publisherConsentRecord.verifiedContactEmail)} — ${escape(publisherConsentRecord.publicSupportEmail)}</p><p>${copy.publisherAcceptedAt}: <time>${escape(publisherConsentRecord.acceptedAt)}</time></p><ul><li>${publisherConsentRecord.publisherType === "entity" ? copy.entityAuthorityAttestation : copy.ageAttestation}</li>${["regionAttestation", "sanctionsAttestation", "accurateFactsAttestation", "singleAccountAttestation", "feeAttestation", "dataAttestation", "supportAttestation", "agreementAttestation"].map(key => `<li>${copy[key]}</li>`).join("")}</ul>${publisherConsentRecord.withdrawnAt != null ? `<p role="status">${copy.publisherWithdrawn}</p><p>${copy.publisherWithdrawnAt}: <time>${escape(publisherConsentRecord.withdrawnAt)}</time></p>` : `<button type="button" data-action="publisher-consent-withdraw" data-csrf="${escape(user?.csrf || "")}">${copy.publisherConsentWithdraw}</button>`}</div>` : "";
  const publisherConsentSection = user && publisherConsentAvailable ? `<section class="workbench" aria-labelledby="publisher-consent-title"><h2 id="publisher-consent-title">${copy.publisherConsentTitle}</h2><p><a href="https://capafy.ai/publisher-agreement/" rel="noreferrer">${copy.publisherAgreement}</a> (${copy.publisherEffective})</p><p>${copy.publisherLanguageNotice}</p><ul>${copy.publisherTerms.map(term => `<li>${term}</li>`).join("")}</ul>${publisherConsentSaved}${publisherConsentRecord ? "" : publisherConsentForm}<p id="publisher-consent-feedback" role="status" aria-live="polite"></p></section>` : "";
  return `<!doctype html><html lang="${ja ? "ja" : "en"}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Life Manager Cloud</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:760px;margin:8vh auto;padding:0 24px;color:#17222d}h1{font-size:clamp(2rem,6vw,3.4rem);line-height:1.1}.notice{border-left:3px solid #b9832e;padding:12px 16px;background:#fbf7ef}.signin{display:inline-block;margin:16px 0;padding:12px 20px;border-radius:8px;background:#172a23;color:#fff;font:inherit;font-weight:700;text-decoration:none}button{display:block;margin:16px 0;padding:12px 20px;border:0;border-radius:8px;background:#172a23;color:#fff;font:inherit;font-weight:700;cursor:pointer}button:disabled{opacity:.5;cursor:default}button[hidden]{display:none}.consent{display:block;margin-top:20px}.workbench{margin:32px 0;padding:20px;border:1px solid #d5d9d6;border-radius:12px;background:#fff}.workbench h2{margin-top:0}.workbench ul{padding-left:20px}.workbench li{margin:12px 0}.workbench time{display:block;color:#627069;font-size:.9rem}</style><main data-source="${campaignSource}"><p>Life Manager Cloud</p><h1>${copy.title}</h1><p>${copy.intro}</p><p>${copy.scope}</p><p class="notice">${copy.notice}</p><p><a href="https://maritime.sh/privacy" rel="noreferrer">${ja ? "Maritimeのプライバシーポリシー" : "Maritime Privacy Policy"}</a></p>${controls}${stopControl}${publisherConsentSection}${workbenchSection}<p id="feedback" role="status" aria-live="polite">${authFeedback}</p>${telegram}<noscript>${ja ? "開始と状態確認にはJavaScriptを有効にしてください。" : "Enable JavaScript to start Life Manager Cloud and check its status."}</noscript></main><script>
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
const refreshWorkbench=document.querySelector('[data-action="refresh-workbench"]');
if(refreshWorkbench)refreshWorkbench.addEventListener('click',()=>location.reload());
const publisherConsentForm=document.querySelector('[data-action="publisher-consent"]');
if(publisherConsentForm){const type=publisherConsentForm.elements.publisherType;const adult=publisherConsentForm.elements.ageOfMajorityAttested;const entity=publisherConsentForm.elements.entityAuthorityAttested;const submit=publisherConsentForm.querySelector('button[type="submit"]');const syncPublisherConsent=()=>{adult.required=type.value==='individual';entity.required=type.value==='entity';if(type.value==='individual')entity.checked=false;else adult.checked=false;submit.disabled=!publisherConsentForm.checkValidity();};publisherConsentForm.addEventListener('input',syncPublisherConsent);publisherConsentForm.addEventListener('change',syncPublisherConsent);publisherConsentForm.addEventListener('submit',async event=>{event.preventDefault();if(!publisherConsentForm.reportValidity())return;submit.disabled=true;const individual=type.value==='individual';const payload={agreementVersion:publisherConsentForm.dataset.agreementVersion,publisherType:type.value,legalName:publisherConsentForm.elements.legalName.value,jurisdiction:publisherConsentForm.elements.jurisdiction.value,publicSupportEmail:publisherConsentForm.elements.publicSupportEmail.value,ageOfMajorityAttested:individual&&adult.checked,entityAuthorityAttested:!individual&&entity.checked,supportedRegionAttested:publisherConsentForm.elements.supportedRegionAttested.checked,sanctionsEligibilityAttested:publisherConsentForm.elements.sanctionsEligibilityAttested.checked,identityContactAccurateAttested:publisherConsentForm.elements.identityContactAccurateAttested.checked,singlePublisherAccountAttested:publisherConsentForm.elements.singlePublisherAccountAttested.checked,certificationFeeNonRefundableAcknowledged:publisherConsentForm.elements.certificationFeeNonRefundableAcknowledged.checked,dataDisclosuresAccepted:publisherConsentForm.elements.dataDisclosuresAccepted.checked,supportObligationsAccepted:publisherConsentForm.elements.supportObligationsAccepted.checked,agreementAccepted:publisherConsentForm.elements.agreementAccepted.checked};try{const result=await fetch('/maritime/capafy/publisher-consent',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-lm-web-csrf':publisherConsentForm.dataset.csrf},body:JSON.stringify(payload)});if(result.ok)location.reload();else{document.getElementById('publisher-consent-feedback').textContent=${JSON.stringify(copy.publisherConsentFailed)};syncPublisherConsent();}}catch{document.getElementById('publisher-consent-feedback').textContent=${JSON.stringify(copy.publisherConsentFailed)};syncPublisherConsent();}});syncPublisherConsent();}
const publisherConsentWithdraw=document.querySelector('[data-action="publisher-consent-withdraw"]');
if(publisherConsentWithdraw)publisherConsentWithdraw.addEventListener('click',async()=>{publisherConsentWithdraw.disabled=true;try{const result=await fetch('/maritime/capafy/publisher-consent/withdraw',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-lm-web-csrf':publisherConsentWithdraw.dataset.csrf},body:'{}'});if(result.ok)location.reload();else{document.getElementById('publisher-consent-feedback').textContent=${JSON.stringify(copy.publisherConsentWithdrawFailed)};publisherConsentWithdraw.disabled=false;}}catch{document.getElementById('publisher-consent-feedback').textContent=${JSON.stringify(copy.publisherConsentWithdrawFailed)};publisherConsentWithdraw.disabled=false;}});
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
