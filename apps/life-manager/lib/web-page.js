"use strict";

const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DAY_MS = 24 * 60 * 60 * 1000;

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function firstChargeDate(trialOffer = {}) {
  const date = new Date(trialOffer.firstChargeAt || "");
  if (!Number.isFinite(date.getTime())) return "";
  const timezone = String(trialOffer.timezone || "Asia/Tokyo");
  try {
    return new Intl.DateTimeFormat("ja-JP", {
      year: "numeric", month: "long", day: "numeric", hour: "numeric", minute: "2-digit",
      hourCycle: "h23", timeZoneName: "short", timeZone: timezone,
    }).format(date);
  } catch {
    return "";
  }
}

function validMessagesUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return url.protocol === "sms:" && url.pathname ? url.toString() : "";
  } catch {
    return "";
  }
}

function portalMarkup(available) {
  if (!available) return "";
  return `<button type="button" class="button secondary" data-action="billing-portal">サブスクリプションを管理</button>`;
}

function checkoutPendingMarkup() {
  return `<section class="card" aria-live="polite"><h1>お申し込みを確認しています</h1><p>Stripeでのカード登録を確認しています。反映後にもう一度このページを開くと状態を表示します。</p><a class="text-link" href="/lm">状態を再確認</a></section>`;
}

function telegramLinkButton(enabled) {
  return enabled === true
    ? `<button class="text-link" type="button" data-action="link-telegram">Telegramで質問に答える（任意）</button>`
    : "";
}

function pageState(snapshot, model = {}) {
  if (!snapshot || snapshot.setupState === "sync_pending" && snapshot.calendarState === "unavailable") {
    return `<section class="card"><h1>Calendarの接続を確認しています</h1><p>接続状態を読み込めません。しばらくしてからページを再読み込みしてください。</p></section>`;
  }

  if (model.checkoutPending === true && snapshot.stripeSubscriptionId
    && (!snapshot.planStatus || snapshot.planStatus === "incomplete")) {
    return checkoutPendingMarkup();
  }

  if (snapshot.setupState === "needs_calendar") {
    return `<section class="card"><h1>Google Calendarに接続</h1><p>予定の移動時間を自動でCalendarに登録します。</p><button class="button" type="button" data-action="calendar-start">Google Calendarに接続</button></section>`;
  }

  if (snapshot.setupState === "trial_offer"
    || snapshot.checkoutAvailable === true && ["needs_initial_scan", "no_eligible_events"].includes(snapshot.setupState)) {
    if (model.checkoutPending === true) return checkoutPendingMarkup();
    const offer = model.trialOffer || {};
    const chargeDate = firstChargeDate(offer);
    const messagesUrl = validMessagesUrl(model.messagesContactUrl);
    const messageLink = messagesUrl
      ? `<a class="text-link" href="${escapeHtml(messagesUrl)}" rel="nofollow">Messagesで問い合わせ</a>`
      : "";
    const chargeCopy = chargeDate
      ? `本日のお支払いは$0です。無料期間は7日間で、${escapeHtml(chargeDate)}に$29/月を初回請求します。その後は解約まで毎月自動更新します。請求を避けるには${escapeHtml(chargeDate)}までに解約してください。`
      : `お申し込み条件を確認しています。初回請求日を表示できるまでトライアルは開始できません。`;
    const checkoutButton = snapshot.checkoutAvailable && chargeDate
      ? `<button class="button" type="button" data-action="checkout">7日間の無料トライアルを始める</button>`
      : "";
    return `<section class="card offer-card"><p class="eyebrow">Google Calendarに接続しました</p><h1>対象の予定に移動時間を自動で追加します</h1><p class="muted">Calendarを開くと、予定と出発時刻を確認できます。</p><h2>7日間無料で試す</h2><p class="terms">${chargeCopy}</p><p class="muted">開始にはカード登録が必要です。トライアル終了前のメール通知は送りません。</p>${checkoutButton}${messageLink}${telegramLinkButton(model.telegramLinkAvailable)}</section>`;
  }

  if (snapshot.setupState === "trial_active" || snapshot.setupState === "subscribed") {
    return `<section class="card"><p class="eyebrow">Google Calendarに接続しました</p><h1>移動時間はCalendarに自動登録されます</h1><p>出発時刻の確認はCalendarの通知で受け取れます。このページは閉じても大丈夫です。</p>${portalMarkup(model.customerPortalAvailable === true)}${telegramLinkButton(model.telegramLinkAvailable)}</section>`;
  }

  if (snapshot.setupState === "billing_inactive") {
    const restart = snapshot.subscriptionCheckoutAvailable === true
      ? `<p>この再開には無料トライアルは適用されません。開始時に$29/月を請求し、その後は解約まで毎月自動更新します。</p><button class="button" type="button" data-action="checkout">月額$29で再開する</button>`
      : "";
    return `<section class="card"><h1>自動Travelは停止しています</h1><p>解約手続き中、またはお支払い状態を確認できないため、新しい移動時間の登録を停止しました。既存のCalendar予定は残っています。</p>${restart}${portalMarkup(model.customerPortalAvailable === true)}</section>`;
  }

  return `<section class="card"><h1>Calendarの状態を確認しています</h1><p>状態を確認できません。あとで再読み込みしてください。</p></section>`;
}

const CLIENT_SCRIPT = String.raw`(async () => {
  const signIn = document.getElementById("lm-sign-in");
  if (signIn) {
    try {
      const source = new URL(window.location.href);
      const destination = new URL(signIn.getAttribute("href") || "/auth/google", source.origin);
      for (const key of ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]) {
        const values = source.searchParams.getAll(key);
        if (values.length === 1 && values[0]) destination.searchParams.set(key, values[0]);
      }
      signIn.href = destination.pathname + destination.search;
    } catch { /* retain the fixed auth route */ }
  }

  const root = document.getElementById("lm-flow");
  if (!root) return;
  const feedback = document.getElementById("lm-feedback");
  const csrf = document.querySelector('meta[name="lm-web-csrf"]')?.content || "";

  async function api(path, method, body, options = {}) {
    const headers = { Accept: "application/json" };
    const request = { method: method || "GET", credentials: "same-origin", headers };
    if (options.keepalive === true) request.keepalive = true;
    if (method === "POST") {
      headers["content-type"] = "application/json";
      headers["x-lm-web-csrf"] = csrf;
      request.body = JSON.stringify(body || {});
    }
    const response = await fetch(path, request);
    const result = await response.json().catch(() => null);
    if (!response.ok || !result) throw new Error(result && result.error || "request_failed");
    return result;
  }

  function say(message) {
    if (feedback) feedback.textContent = message || "";
  }

  function clearQueryFlag(name) {
    const url = new URL(window.location.href);
    url.searchParams.delete(name);
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  }

  async function startCalendar() {
    say("Google Calendarへの接続を開いています…");
    const result = await api("/api/lm-web/calendar/start", "POST", {});
    if (typeof result.redirectUrl === "string" && result.redirectUrl) {
      window.location.assign(result.redirectUrl);
      return;
    }
    if (result.connected === true) {
      window.location.assign("/lm?initial_scan=1");
      return;
    }
    throw new Error("calendar_start_failed");
  }

  async function startInitialProcessing() {
    await api("/api/lm-web/setup", "POST", {}, { keepalive: true });
  }

  async function beginCheckout() {
    say("Stripe Checkoutを開いています…");
    const result = await api("/api/lm-web/checkout", "POST", {});
    const target = new URL(String(result.url || ""));
    if (target.protocol !== "https:" || target.hostname !== "checkout.stripe.com") {
      throw new Error("checkout_url_invalid");
    }
    window.location.assign(target.toString());
  }

  async function openBillingPortal() {
    say("サブスクリプション管理を開いています…");
    const result = await api("/api/lm-web/billing/portal", "POST", {});
    const target = new URL(String(result.url || ""));
    if (target.protocol !== "https:" || target.hostname !== "billing.stripe.com") {
      throw new Error("billing_portal_url_invalid");
    }
    window.location.assign(target.toString());
  }

  async function linkTelegram() {
    say("Telegramを開いています…");
    const result = await api("/api/lm-web/message-link", "POST", { channel: "telegram" });
    const target = new URL(String(result.url || ""));
    if (target.protocol !== "https:" || target.hostname !== "t.me") {
      throw new Error("telegram_link_invalid");
    }
    window.location.assign(target.toString());
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    button.disabled = true;
    try {
      if (button.dataset.action === "calendar-start") await startCalendar();
      else if (button.dataset.action === "checkout") await beginCheckout();
      else if (button.dataset.action === "billing-portal") await openBillingPortal();
      else if (button.dataset.action === "link-telegram") await linkTelegram();
      else button.disabled = false;
    } catch {
      say("操作を完了できませんでした。接続状態を確認してから再度お試しください。");
      button.disabled = false;
    }
  });

  const location = new URL(window.location.href);
  if (location.searchParams.get("start_calendar") === "1") {
    clearQueryFlag("start_calendar");
    try { await startCalendar(); }
    catch { say("Calendar接続を開始できませんでした。もう一度お試しください。"); }
    return;
  }
  const startInitialPass = location.searchParams.get("initial_scan") === "1"
    || root.dataset.initialScanNeeded === "true";
  if (location.searchParams.get("initial_scan") === "1") {
    clearQueryFlag("initial_scan");
  }
  if (startInitialPass) void startInitialProcessing().catch(() => {});
})();`;

function renderWebPage(model = {}) {
  const user = model.user && WEB_UID_RE.test(String(model.user.uid || "")) ? model.user : null;
  const head = `<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Life Manager</title><style>
    :root{color-scheme:light;--ink:#17231e;--muted:#65736b;--line:#dce5df;--paper:#f4f7f4;--card:#fff;--accent:#19654b}
    *{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:system-ui,-apple-system,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.55}.shell{width:min(100% - 28px,620px);margin:0 auto;padding:28px 0 44px}.brand{font-weight:700;margin:0 0 20px}.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:24px;box-shadow:0 5px 22px #153e2410}h1,h2,p{margin-top:0}h1{font-size:clamp(1.45rem,6vw,2rem);line-height:1.2;margin-bottom:12px}h2{font-size:1.1rem;margin:22px 0 8px}.lead,.muted,.feedback{color:var(--muted)}.eyebrow{font-size:.84rem;font-weight:700;letter-spacing:.06em;color:var(--accent);margin-bottom:8px}.button{appearance:none;border:0;border-radius:12px;background:var(--accent);color:#fff;cursor:pointer;display:inline-flex;justify-content:center;align-items:center;width:100%;min-height:50px;padding:12px 18px;text-decoration:none;font:inherit;font-weight:700;margin:12px 0 4px}.button.secondary{background:#e8efea;color:var(--ink)}.button:disabled{opacity:.6;cursor:wait}.terms{font-size:.97rem}.text-link{display:block;margin-top:12px;color:var(--accent);text-align:center}.text-link[type="button"]{appearance:none;border:0;background:transparent;padding:0;width:100%;font:inherit;text-decoration:underline;cursor:pointer}.feedback{min-height:1.4em;margin:0 2px 12px}@media(min-width:600px){.shell{padding-top:44px}.card{padding:32px}}
  </style>`;

  if (!user) {
    const authError = model.authError === "connection"
      ? `<p class="feedback" role="alert">Google Calendarとの接続を完了できませんでした。もう一度接続してください。</p>`
      : "";
    return `<!doctype html><html lang="ja"><head>${head}</head><body><main class="shell"><p class="brand">Life Manager</p><section class="card">${authError}<h1>予定への移動時間を、自動でCalendarへ</h1><p class="lead">出発時刻を何度も調べなくても、予定に間に合う移動時間をCalendarに追加します。</p><a id="lm-sign-in" class="button" href="/auth/google">Google Calendarに接続</a><p class="muted">Googleアカウントの確認とCalendarの権限許可が必要です。Life ManagerはGmailを読みません。</p></section></main><script>${CLIENT_SCRIPT}</script></body></html>`;
  }

  const snapshotValue = model.snapshot || {};
  const state = String(snapshotValue.setupState || "sync_pending");
  const stateHtml = pageState(snapshotValue, model);
  const csrf = escapeHtml(user.csrf || "");
  const initialScanNeeded = snapshotValue.initialScanNeeded === true
    && snapshotValue.calendarState === "connected";
  return `<!doctype html><html lang="ja"><head>${head}<meta name="lm-web-csrf" content="${csrf}"></head><body><main class="shell"><p class="brand">Life Manager</p><p id="lm-feedback" class="feedback" role="status" aria-live="polite"></p><div id="lm-flow" data-setup-state="${escapeHtml(state)}" data-initial-scan-needed="${initialScanNeeded}">${stateHtml}</div></main><script>${CLIENT_SCRIPT}</script></body></html>`;
}

module.exports = { escapeHtml, renderWebPage };
