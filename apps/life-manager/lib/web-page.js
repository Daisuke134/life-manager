"use strict";

const { paymentLink } = require("./payment-link.js");

const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function timeMarkup(value, timezone) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const iso = date.toISOString();
  let label = iso;
  let useLocalTime = !timezone;
  if (timezone) try {
    label = new Intl.DateTimeFormat("ja-JP", {
      dateStyle: "medium", timeStyle: "short", timeZone: timezone,
    }).format(date);
  } catch { useLocalTime = true; }
  return `<time datetime="${escapeHtml(iso)}"${useLocalTime ? ' data-local-time="true"' : ""}>${escapeHtml(label)}</time>`;
}

function calendarMarkup(snapshot) {
  const state = snapshot && snapshot.calendarState;
  const status = snapshot && snapshot.enablePending === true ? "接続を確認中"
    : state === "connected" ? "接続済み" : state === "unavailable" ? "接続状況を確認できません" : "未接続";
  return `<section class="card calendar-card"><div class="card-heading"><h2>Google カレンダー</h2><span id="calendar-status" class="status">${status}</span></div></section>`;
}

function eventMarkup(event, displayTimeZone, missingLocationCount) {
  if (!event) return `<section class="card"><h2>次の予定</h2><p>今後の予定は見つかりませんでした。</p></section>`;
  const location = String(event.location || "").trim();
  const summary = escapeHtml(event.summary || "名称のない予定");
  const missingCount = Number.isSafeInteger(missingLocationCount) && missingLocationCount > 0 ? missingLocationCount : 0;
  const locationState = location
    ? `<p class="event-location">${escapeHtml(location)}</p>`
    : `<p class="notice">${missingCount ? `今後7日間に場所が未設定の予定が${missingCount}件あります。` : "この予定には場所がありません。"}Google カレンダーで「${summary}」を開き、場所を追加してください。保存後に「今日を更新」を押してください。</p><button id="today-refresh" type="button" class="button secondary" data-action="refresh">今日を更新</button>`;
  return `<section class="card"><h2>次の予定</h2><p class="event-title">${summary}</p>${timeMarkup(event.startIso, displayTimeZone)}${locationState}</section>`;
}

function locationCountMarkup(snapshot) {
  const count = snapshot && snapshot.missingLocationCount;
  if (!Number.isSafeInteger(count) || count <= 0
    || snapshot.nextEvent && !String(snapshot.nextEvent.location || "").trim()) return "";
  return `<p class="notice">今後7日間に場所が未設定の予定が${count}件あります。Google カレンダーで各予定を開いて場所を追加してください。保存後に「今日を更新」を押してください。</p><button id="today-refresh" type="button" class="button secondary" data-action="refresh">今日を更新</button>`;
}

function todayMarkup(snapshot) {
  const travel = snapshot && snapshot.travelBlock;
  const displayTimeZone = snapshot && snapshot.displayTimeZone;
  let travelMarkup = "";
  if (travel) {
    const departure = snapshot.departureAt || travel.startIso;
    const minutes = Number.isFinite(travel.startMs) && Number.isFinite(travel.endMs)
      ? Math.max(0, Math.round((travel.endMs - travel.startMs) / 60_000)) : null;
    travelMarkup = `<section class="card departure-card"><p class="eyebrow">次の出発</p><h2 class="departure-time">${timeMarkup(departure, displayTimeZone)}</h2><p class="event-title">${escapeHtml(travel.summary || "Travel")}</p>${minutes == null ? "" : `<p class="muted">移動時間の予定: ${minutes} 分</p>`}</section>`;
  } else if (snapshot && snapshot.setupState === "sync_pending"
    && !(snapshot.nextEvent && !snapshot.nextEvent.location)) {
    travelMarkup = `<section class="card"><h2>Travel の確認中</h2><p>予定表の読み取り結果を確認しています。少し待ってから更新してください。</p><button type="button" class="button secondary" data-action="refresh">今日を更新</button></section>`;
  } else if (snapshot && snapshot.nextEvent && snapshot.nextEvent.location) {
    travelMarkup = `<section class="card"><h2>出発時刻</h2><p>この予定には Travel の予定は必要ありません。</p></section>`;
  }
  return `${travelMarkup}${eventMarkup(snapshot && snapshot.nextEvent, displayTimeZone, snapshot && snapshot.missingLocationCount)}${locationCountMarkup(snapshot)}<p class="reminder-note">通知は Google カレンダーのデフォルトリマインダー設定に従います。Life Manager は通知設定を変更しません。</p>`;
}

function travelControlsMarkup(snapshot) {
  if (!snapshot || snapshot.calendarBound !== true) return "";
  if (snapshot.disconnectPending === true) {
    return `<section class="card"><h2>Travel 自動化</h2><p>接続解除の確認中のため自動Travelは再開できません。</p><button type="button" class="button secondary" data-action="travel-control" data-control="disconnect">接続解除を再試行</button></section>`;
  }
  if (snapshot.enablePending === true) {
    return `<section class="card"><h2>Travel 自動化</h2><p>Calendarの接続確認中です。自動Travelは再開できません。</p><button type="button" class="button secondary" data-action="calendar-start">Calendar接続を再確認</button></section>`;
  }
  const automationControl = typeof snapshot.dailyAutomationEnabled === "boolean"
    ? `<button type="button" class="button secondary" data-action="travel-control" data-control="${snapshot.dailyAutomationEnabled ? "pause" : "resume"}">${snapshot.dailyAutomationEnabled ? "自動Travelを一時停止" : "自動Travelを再開"}</button>`
    : "";
  return `<section class="card"><h2>Travel 自動化</h2><div class="card-heading">${automationControl}<button type="button" class="button secondary" data-action="travel-control" data-control="disconnect">Google カレンダーの接続を解除</button></div></section>`;
}

function dashboardMarkup(snapshot, homeAddress = "") {
  if (!snapshot || snapshot.setupState === "sync_pending" && snapshot.calendarState === "unavailable") {
    return `<section class="card"><h2>Calendar の状態を確認中</h2><p>接続状況を確認できません。あとで更新してください。</p><button type="button" class="button secondary" data-action="refresh">今日を更新</button></section>${travelControlsMarkup(snapshot)}`;
  }
  if (snapshot.setupState === "needs_calendar") {
    return `${calendarMarkup(snapshot)}<section class="card setup-card"><p class="eyebrow">設定 1 / 2</p><h2>Google カレンダーを接続</h2><p>予定を読み取り、出発時刻を確認します。</p><button id="calendar-connect" type="button" class="button" data-action="calendar-start">Google カレンダーを接続</button></section>${travelControlsMarkup(snapshot)}`;
  }
  if (snapshot.setupState === "needs_home") {
    return `${calendarMarkup(snapshot)}<section class="card setup-card"><p class="eyebrow">設定 2 / 2</p><h2>いつもの出発場所を入力</h2><p>住所は移動時間の計算に使います。</p><form id="home-address-form"><label for="homeAddress">自宅の住所</label><input id="homeAddress" name="homeAddress" type="text" maxlength="240" autocomplete="street-address" required value="${escapeHtml(homeAddress)}"><button type="submit" class="button">保存して予定を確認</button></form></section>${travelControlsMarkup(snapshot)}`;
  }
  return `${calendarMarkup(snapshot)}${todayMarkup(snapshot)}${travelControlsMarkup(snapshot)}`;
}

const CLIENT_SCRIPT = String.raw`(() => {
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
    } catch { /* keep the fixed sign-in path if the incoming URL cannot be parsed */ }
  }
  for (const time of document.querySelectorAll?.('time[data-local-time]') || []) {
    const date = new Date(time.getAttribute("datetime") || "");
    if (!Number.isFinite(date.getTime())) continue;
    time.textContent = new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium", timeStyle: "short" }).format(date);
  }
  const root = document.getElementById("lm-dashboard");
  const feedback = document.getElementById("lm-feedback");
  const csrf = document.querySelector('meta[name="lm-web-csrf"]')?.content || "";
  if (!root) return;
  async function api(path, method, body) {
    const headers = { Accept: "application/json" };
    const request = { method: method || "GET", credentials: "same-origin", headers };
    if (method === "POST") {
      headers["content-type"] = "application/json";
      headers["x-lm-web-csrf"] = csrf;
      request.body = JSON.stringify(body);
    }
    const response = await fetch(path, request);
    const result = await response.json().catch(() => null);
    if (!response.ok || !result) {
      const error = new Error("request_failed");
      error.automationPaused = Boolean(result && result.automationPaused === true);
      throw error;
    }
    return result;
  }
  function say(message) { feedback.textContent = message || ""; }
  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "refresh") {
      window.location.assign("/lm");
      return;
    }
    if (button.dataset.action === "travel-control") {
      const action = button.dataset.control;
      button.disabled = true;
      try {
        await api("/api/lm-web/travel/control", "POST", { action });
        window.location.assign("/lm");
      } catch (error) {
        say(action === "disconnect" && error.automationPaused === true
          ? "接続解除を確認できませんでした。自動Travelは停止したままです。ページを再読み込みして状態を確認してください。"
          : "Travel の設定を更新できませんでした。ページを再読み込みして状態を確認してください。");
        button.disabled = false;
      }
      return;
    }
    if (button.dataset.action !== "calendar-start") return;
    button.disabled = true;
    try {
      say("Google カレンダーを開いています…");
      const result = await api("/api/lm-web/calendar/start", "POST", {});
      if (typeof result.redirectUrl === "string" && result.redirectUrl) {
        window.location.assign(result.redirectUrl);
        return;
      }
      if (result.connected !== true) throw new Error("calendar_start_failed");
      window.location.assign("/lm");
    } catch {
      say("Calendar 接続を開始できませんでした。もう一度お試しください。");
      button.disabled = false;
    }
  });
  root.addEventListener("submit", async (event) => {
    if (!event.target || event.target.id !== "home-address-form") return;
    event.preventDefault();
    const button = event.target.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const homeAddress = String(event.target.elements.homeAddress.value || "").trim();
      await api("/api/lm-web/setup", "POST", { homeAddress });
      window.location.assign("/lm");
    } catch {
      say("住所を保存できませんでした。入力内容を確認して、もう一度お試しください。");
      button.disabled = false;
    }
  });
  api("/api/lm-web/calendar/status", "GET").then((status) => {
    const label = document.getElementById("calendar-status");
    if (label) label.textContent = status.connected === true ? "接続済み" : status.state === "enable_pending" ? "接続を確認中" : status.state === "unavailable" ? "接続状況を確認できません" : "未接続";
  }).catch(() => say("Calendar の状態を確認できません。あとで更新してください。"));
})();`;

function renderWebPage(model = {}) {
  const user = model.user && WEB_UID_RE.test(String(model.user.uid || "")) ? model.user : null;
  const head = `<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Life Manager</title><style>
    :root{color-scheme:light;--ink:#17231e;--muted:#65736b;--line:#dce5df;--paper:#f4f7f4;--card:#fff;--accent:#19654b}
    *{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:system-ui,-apple-system,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.55}.shell{width:min(100% - 28px,680px);margin:0 auto;padding:26px 0 48px}.brand{font-weight:700;margin:0 0 24px}.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;margin:0 0 14px;box-shadow:0 5px 22px #153e2410}h1,h2,p{margin-top:0}h1{font-size:clamp(1.6rem,7vw,2.1rem);line-height:1.18;margin-bottom:12px}h2{font-size:1.08rem;margin-bottom:10px}.lead,.status,.muted,.reminder-note{color:var(--muted)}.status,.eyebrow{font-size:.85rem}.eyebrow{font-weight:650;letter-spacing:.07em;margin-bottom:4px}.card-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.card-heading h2{margin:0}.button{appearance:none;border:0;border-radius:12px;background:var(--accent);color:#fff;cursor:pointer;display:inline-flex;justify-content:center;align-items:center;font:inherit;font-weight:650;min-height:48px;padding:12px 18px;text-decoration:none}.button:disabled{opacity:.6;cursor:wait}.button.secondary{background:#e8efea;color:var(--ink)}.event-title{font-size:1.15rem;font-weight:700;margin:6px 0}.event-location{color:var(--muted);margin:8px 0 0}.notice{background:#fff7e6;border-radius:10px;padding:12px;margin:12px 0 0}.departure-card{background:#e8f3eb}.departure-time{font-size:clamp(1.8rem,9vw,3rem);line-height:1.1;margin:4px 0 12px}.reminder-note{font-size:.9rem;margin:18px 4px}.setup-card form{display:grid;gap:10px;margin-top:16px}.setup-card input{width:100%;min-height:48px;border:1px solid #b9c8be;border-radius:10px;padding:10px 12px;font:inherit}.setup-card label{font-weight:650}.setup-card .button,.login-card .button{width:100%}.feedback{min-height:1.5em;color:var(--muted);font-size:.92rem;margin:0 2px 10px}.login-card{padding:28px 24px}.payment{margin-top:14px;text-align:center}.payment .button{background:#fff;color:var(--accent);border:1px solid #b9c8be}
    @media(min-width:600px){.shell{padding-top:40px}.card{padding:26px}.login-card{padding:42px}}
  </style>`;
  if (!user) {
    return `<!doctype html><html lang="ja"><head>${head}</head><body><main class="shell"><p class="brand">Life Manager</p><section class="card login-card"><h1>予定に合わせた出発時刻を確認</h1><p class="lead">Google カレンダーと接続して、次の予定に間に合う出発時刻を確認できます。</p><a id="lm-sign-in" class="button" href="/auth/google">Google で続ける</a></section></main><script>${CLIENT_SCRIPT}</script></body></html>`;
  }
  const snapshot = model.snapshot || null;
  const checkout = snapshot && snapshot.setupState === "ready" && snapshot.paid === false
    ? paymentLink({ stripePaymentLink: model.stripePaymentLink }, { uid: String(user.uid) }) : "";
  const paymentMarkup = checkout ? `<aside class="payment"><a class="button" href="${escapeHtml(checkout)}" rel="nofollow">プランを確認</a></aside>` : "";
  return `<!doctype html><html lang="ja"><head>${head}<meta name="lm-web-csrf" content="${escapeHtml(user.csrf)}"></head><body><main class="shell"><p class="brand">Life Manager</p><h1>今日の予定</h1><p id="lm-feedback" class="feedback" role="status" aria-live="polite"></p><div id="lm-dashboard">${dashboardMarkup(snapshot, model.homeAddress)}</div>${paymentMarkup}</main><script>${CLIENT_SCRIPT}</script></body></html>`;
}

module.exports = { escapeHtml, renderWebPage };
