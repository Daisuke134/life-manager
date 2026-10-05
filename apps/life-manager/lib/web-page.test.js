"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const { renderWebPage } = require("./web-page.js");

const verifiedUid = "lm_123e4567-e89b-12d3-a456-426614174000";
const user = { uid: verifiedUid, csrf: "csrf-token" };

function snapshot(overrides = {}) {
  return {
    setupState: "ready",
    calendarState: "connected",
    nextEvent: null,
    travelBlock: null,
    departureAt: null,
    displayTimeZone: null,
    missingLocationCount: 0,
    trialExpiresAt: null,
    paid: null,
    ...overrides,
  };
}

function visibleHtml(html) {
  return html.replace(/<script>[\s\S]*?<\/script>/g, "");
}

function mountClient(html, responses) {
  const handlers = {};
  const requests = [];
  const redirects = [];
  const feedback = { textContent: "" };
  const root = {
    innerHTML: "",
    addEventListener(name, handler) { handlers[name] = handler; },
    querySelector() { return null; },
  };
  const script = html.match(/<script>([\s\S]*?)<\/script>/);
  assert.ok(script);
  vm.runInNewContext(script[1], {
    document: {
      getElementById(id) { return id === "lm-dashboard" ? root : id === "lm-feedback" ? feedback : null; },
      querySelector() { return { content: user.csrf }; },
    },
    fetch: async (path, init) => {
      requests.push({ path, init });
      const result = responses[path];
      return { ok: !(result && result._ok === false), json: async () => result };
    },
    window: { location: { assign(value) { redirects.push(value); } } },
  });
  return { handlers, requests, redirects, feedback, root };
}

test("renders sign-in and each missing setup step", () => {
  const anonymous = renderWebPage({});
  assert.match(anonymous, /href="\/auth\/google"/);
  assert.match(anonymous, /name="viewport" content="width=device-width, initial-scale=1/);
  assert.doesNotMatch(anonymous, /telegram/i);

  const needsCalendar = renderWebPage({ user, snapshot: snapshot({ setupState: "needs_calendar", calendarState: "action_required" }) });
  assert.match(visibleHtml(needsCalendar), /id="calendar-connect"/);
  assert.doesNotMatch(visibleHtml(needsCalendar), /name="homeAddress"/);

  const needsHome = renderWebPage({ user, snapshot: snapshot({ setupState: "needs_home" }) });
  assert.match(visibleHtml(needsHome), /name="homeAddress"/);
  assert.doesNotMatch(visibleHtml(needsHome), /id="calendar-connect"/);
});

test("renders next event and verified Travel block", () => {
  const html = renderWebPage({
    user,
    snapshot: snapshot({
      nextEvent: {
        id: "event-1",
        summary: "Dentist",
        location: "Tokyo Station",
        startIso: "2026-10-07T01:00:00.000Z",
        timezone: "Asia/Tokyo",
        startMs: Date.parse("2026-10-07T01:00:00.000Z"),
        endMs: Date.parse("2026-10-07T02:00:00.000Z"),
      },
      travelBlock: {
        id: "travel-1",
        summary: "Travel to Dentist",
        location: "Tokyo Station",
        startIso: "2026-10-07T00:30:00.000Z",
        timezone: "Asia/Tokyo",
        startMs: Date.parse("2026-10-07T00:30:00.000Z"),
        endMs: Date.parse("2026-10-07T01:00:00.000Z"),
      },
      departureAt: "2026-10-07T00:30:00.000Z",
    }),
  });

  assert.match(html, /Dentist/);
  assert.match(html, /Tokyo Station/);
  assert.match(html, /Travel to Dentist/);
  assert.match(html, /2026-10-07T00:30:00\.000Z/);
  assert.match(html, /デフォルトリマインダー設定に従います/);
  assert.doesNotMatch(html, /Travel time added/);
  const script = html.match(/<script>([\s\S]*?)<\/script>/);
  assert.ok(script, "authenticated page includes its inline client script");
  assert.doesNotThrow(() => new Function(script[1]));
});

test("renders departure first and formats both times in the snapshot display timezone", () => {
  const html = renderWebPage({
    user,
    snapshot: snapshot({
      displayTimeZone: "America/Los_Angeles",
      nextEvent: {
        id: "event-1",
        summary: "Dentist",
        location: "Tokyo Station",
        startIso: "2026-10-07T01:00:00.000Z",
        timezone: "Asia/Tokyo",
        startMs: Date.parse("2026-10-07T01:00:00.000Z"),
        endMs: Date.parse("2026-10-07T02:00:00.000Z"),
      },
      travelBlock: {
        id: "travel-1",
        summary: "Travel to Dentist",
        location: "Tokyo Station",
        startIso: "2026-10-07T00:30:00.000Z",
        timezone: "UTC",
        startMs: Date.parse("2026-10-07T00:30:00.000Z"),
        endMs: Date.parse("2026-10-07T01:00:00.000Z"),
      },
      departureAt: "2026-10-07T00:30:00.000Z",
    }),
  });
  const departurePosition = html.indexOf('class="card departure-card"');
  const appointmentPosition = html.indexOf("<h2>次の予定</h2>");
  const labels = [...html.matchAll(/<time\b[^>]*>(.*?)<\/time>/g)].map((match) => match[1]);

  assert.ok(departurePosition >= 0 && departurePosition < appointmentPosition);
  assert.deepEqual(labels, ["2026/10/06 17:30", "2026/10/06 18:00"]);
});

test("missing display timezone uses browser-local times and shows actionable location count", () => {
  const html = renderWebPage({
    user,
    snapshot: snapshot({
      missingLocationCount: 2,
      nextEvent: {
        id: "event-1",
        summary: "Dentist",
        location: "Tokyo Station",
        startIso: "2026-10-07T01:00:00.000Z",
        timezone: "Asia/Tokyo",
        startMs: Date.parse("2026-10-07T01:00:00.000Z"),
        endMs: Date.parse("2026-10-07T02:00:00.000Z"),
      },
      travelBlock: {
        id: "travel-1",
        summary: "Travel to Dentist",
        location: "Tokyo Station",
        startIso: "2026-10-07T00:30:00.000Z",
        timezone: "UTC",
        startMs: Date.parse("2026-10-07T00:30:00.000Z"),
        endMs: Date.parse("2026-10-07T01:00:00.000Z"),
      },
      departureAt: "2026-10-07T00:30:00.000Z",
    }),
  });

  assert.equal((html.match(/data-local-time="true"/g) || []).length, 2);
  assert.match(html, /今後7日間に場所が未設定の予定が2件あります。Google カレンダーで各予定を開いて場所を追加してください。保存後に「今日を更新」を押してください。/);
});

test("location count notice has a working Today refresh when the next event has a location", async () => {
  const html = renderWebPage({
    user,
    snapshot: snapshot({
      missingLocationCount: 2,
      nextEvent: {
        id: "event-located",
        summary: "Office meeting",
        location: "Tokyo Station",
        startIso: "2026-10-07T01:00:00.000Z",
        timezone: "Asia/Tokyo",
        startMs: Date.parse("2026-10-07T01:00:00.000Z"),
        endMs: Date.parse("2026-10-07T02:00:00.000Z"),
      },
    }),
  });
  const visible = visibleHtml(html);

  assert.match(visible, /今後7日間に場所が未設定の予定が2件あります。Google カレンダーで各予定を開いて場所を追加してください。保存後に「今日を更新」を押してください。/);
  assert.match(visible, /<button id="today-refresh" type="button" class="button secondary" data-action="refresh">今日を更新<\/button>/);

  const client = mountClient(html, {
    "/api/lm-web/calendar/status": { connected: true, state: "connected" },
  });
  const button = { dataset: { action: "refresh" }, disabled: false };
  await client.handlers.click({ target: { closest() { return button; } } });

  assert.deepEqual(client.redirects, ["/lm"]);
});

test("missing location gives Google Calendar edit steps and Today refresh", async () => {
  const html = renderWebPage({
    user,
    snapshot: snapshot({
      nextEvent: {
        id: "event-location-missing",
        summary: "Dentist",
        location: "",
        startIso: "2026-10-07T01:00:00.000Z",
        timezone: "Asia/Tokyo",
        startMs: Date.parse("2026-10-07T01:00:00.000Z"),
        endMs: Date.parse("2026-10-07T02:00:00.000Z"),
      },
    }),
  });
  assert.match(html, /Google カレンダーで「Dentist」を開き、場所を追加してください。保存後に「今日を更新」を押してください。/);
  assert.match(html, /id="today-refresh"[^>]*>今日を更新/);

  const client = mountClient(html, {
    "/api/lm-web/calendar/status": { connected: true, state: "connected" },
  });
  const button = { dataset: { action: "refresh" }, disabled: false };
  await client.handlers.click({ target: { closest() { return button; } } });

  assert.deepEqual(client.redirects, ["/lm"]);
  assert.ok(client.requests.every((request) => request.path !== "/api/lm-web/today"));
});

test("escapes event and address text", () => {
  const html = renderWebPage({
    user,
    snapshot: snapshot({
      nextEvent: {
        id: "event-1",
        summary: "<script>alert(1)</script>",
        location: "<img src=x onerror=alert(2)>",
        startIso: "2026-10-07T01:00:00.000Z",
        timezone: "Asia/Tokyo",
        startMs: Date.parse("2026-10-07T01:00:00.000Z"),
        endMs: Date.parse("2026-10-07T02:00:00.000Z"),
      },
    }),
  });
  const addressHtml = renderWebPage({
    user,
    snapshot: snapshot({ setupState: "needs_home" }),
    homeAddress: "\"><svg onload=alert(3)>",
  });

  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(html, /&lt;img src=x onerror=alert\(2\)&gt;/);
  assert.match(addressHtml, /value="&quot;&gt;&lt;svg onload=alert\(3\)&gt;"/);
  assert.doesNotMatch(html + addressHtml, /<script>alert\(1\)<\/script>|<img src=x onerror=alert\(2\)>|<svg onload=alert\(3\)>/);
});

test("payment link uses only verified uid", () => {
  const html = renderWebPage({
    user,
    snapshot: snapshot({ setupState: "ready", paid: false }),
    stripePaymentLink: "https://buy.stripe.com/example",
    query: { uid: "lm_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
  });
  const match = html.match(/href="(https:\/\/buy\.stripe\.com\/[^\"]+)"/);

  assert.ok(match, "renders the configured payment link");
  assert.match(match[1], new RegExp(`client_reference_id=${verifiedUid}`));
  assert.doesNotMatch(match[1], /aaaaaaaa/);
  assert.doesNotMatch(html, /\$29|29\s*\/\s*month|29\s*\/\s*月/i);
});

test("setup posts only the address and reloads server-rendered Today", async () => {
  const page = renderWebPage({ user, snapshot: snapshot({ setupState: "needs_home" }) });
  const client = mountClient(page, {
    "/api/lm-web/calendar/status": { connected: true, state: "connected" },
    "/api/lm-web/setup": { setupState: "ready", syncState: "sync_pending" },
  });
  const form = {
    id: "home-address-form",
    elements: { homeAddress: { value: "1-2-3 Tokyo" } },
    querySelector() { return { disabled: false }; },
  };
  let prevented = false;
  await client.handlers.submit({ target: form, preventDefault() { prevented = true; } });

  const setup = client.requests.find((request) => request.path === "/api/lm-web/setup");
  const calendarStatus = client.requests.find((request) => request.path === "/api/lm-web/calendar/status");
  assert.equal(prevented, true);
  assert.equal(calendarStatus.init.method, "GET");
  assert.equal(calendarStatus.init.body, undefined);
  assert.equal(setup.init.method, "POST");
  assert.equal(setup.init.headers["x-lm-web-csrf"], user.csrf);
  assert.deepEqual(JSON.parse(setup.init.body), { homeAddress: "1-2-3 Tokyo" });
  assert.deepEqual(client.redirects, ["/lm"]);
  assert.ok(client.requests.every((request) => request.path !== "/api/lm-web/today"));
  const reRendered = renderWebPage({
    user,
    snapshot: snapshot({ setupState: "ready", paid: false }),
    stripePaymentLink: "https://buy.stripe.com/example",
  });
  assert.match(reRendered, /プランを確認/);
  assert.doesNotMatch(reRendered, /\$29|29\s*\/\s*month|29\s*\/\s*月/i);
  assert.doesNotMatch(reRendered, /telegram/i);
});

test("Calendar start follows only the server redirect URL", async () => {
  const page = renderWebPage({ user, snapshot: snapshot({ setupState: "needs_calendar", calendarState: "action_required" }) });
  const redirectUrl = "https://accounts.google.com/o/oauth2/v2/auth?state=server-value";
  const client = mountClient(page, {
    "/api/lm-web/calendar/status": { connected: false, state: "action_required" },
    "/api/lm-web/calendar/start": { connected: false, state: "action_required", redirectUrl },
  });
  const button = { dataset: { action: "calendar-start" }, disabled: false };
  await client.handlers.click({ target: { closest() { return button; } } });

  const start = client.requests.find((request) => request.path === "/api/lm-web/calendar/start");
  assert.equal(start.init.method, "POST");
  assert.equal(start.init.headers["x-lm-web-csrf"], user.csrf);
  assert.deepEqual(JSON.parse(start.init.body), {});
  assert.deepEqual(client.redirects, [redirectUrl]);
  assert.ok(client.requests.every(({ init }) => !init.body || !/uid|chat_id|paid/.test(init.body)));
});

test("travel controls use persisted pause state and expose disconnect only for a bound Calendar", async () => {
  const pausedPage = renderWebPage({
    user,
    snapshot: snapshot({ calendarBound: true, dailyAutomationEnabled: false }),
  });
  const runningPage = renderWebPage({
    user,
    snapshot: snapshot({ calendarBound: true, dailyAutomationEnabled: true }),
  });
  const unboundPage = renderWebPage({
    user,
    snapshot: snapshot({ calendarBound: false, dailyAutomationEnabled: false }),
  });

  assert.match(visibleHtml(pausedPage), /data-action="travel-control" data-control="resume">自動Travelを再開<\/button>/);
  assert.match(visibleHtml(pausedPage), /data-action="travel-control" data-control="disconnect">Google カレンダーの接続を解除<\/button>/);
  assert.match(visibleHtml(runningPage), /data-action="travel-control" data-control="pause">自動Travelを一時停止<\/button>/);
  assert.doesNotMatch(visibleHtml(unboundPage), /data-control="disconnect"/);

  const client = mountClient(runningPage, {
    "/api/lm-web/calendar/status": { connected: true, state: "connected" },
    "/api/lm-web/travel/control": { dailyAutomationEnabled: false, calendarBound: true },
  });
  const button = { dataset: { action: "travel-control", control: "pause" }, disabled: false };
  await client.handlers.click({ target: { closest() { return button; } } });
  const request = client.requests.find((item) => item.path === "/api/lm-web/travel/control");

  assert.equal(request.init.method, "POST");
  assert.equal(request.init.headers["x-lm-web-csrf"], user.csrf);
  assert.deepEqual(JSON.parse(request.init.body), { action: "pause" });
  assert.deepEqual(client.redirects, ["/lm"]);
});

test("disconnect failure tells the user automation remains paused", async () => {
  const page = renderWebPage({
    user,
    snapshot: snapshot({ calendarBound: true, dailyAutomationEnabled: true }),
  });
  const client = mountClient(page, {
    "/api/lm-web/calendar/status": { connected: true, state: "connected" },
    "/api/lm-web/travel/control": { _ok: false, error: "control_unavailable", automationPaused: true },
  });
  const button = { dataset: { action: "travel-control", control: "disconnect" }, disabled: false };
  await client.handlers.click({ target: { closest() { return button; } } });

  const request = client.requests.find((item) => item.path === "/api/lm-web/travel/control");
  assert.deepEqual(JSON.parse(request.init.body), { action: "disconnect" });
  assert.match(client.feedback.textContent, /自動Travelは停止したままです/);
  assert.equal(button.disabled, false);
  assert.deepEqual(client.redirects, []);
});
