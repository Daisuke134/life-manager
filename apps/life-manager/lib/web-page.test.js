"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const { renderWebPage } = require("./web-page.js");

const verifiedUid = "lm_123e4567-e89b-12d3-a456-426614174000";
const user = { uid: verifiedUid, csrf: "csrf-token" };

function snapshot(overrides = {}) {
  return {
    setupState: "trial_offer",
    calendarState: "connected",
    calendarBound: true,
    initialScanCompletedAt: "2030-01-01T00:00:00.000Z",
    firstTravelAt: "2030-01-01T00:00:00.000Z",
    confirmedTravelBlockCount: 1,
    scanState: "complete",
    checkoutAvailable: true,
    trialExpiresAt: null,
    paid: false,
    planStatus: null,
    stripeSubscriptionId: null,
    ...overrides,
  };
}

function visibleHtml(html) {
  return html.replace(/<script>[\s\S]*?<\/script>/g, "");
}

function mountClient(html, responses = {}, href = "https://life.example/lm") {
  const handlers = {};
  const requests = [];
  const redirects = [];
  const replacements = [];
  const feedback = { textContent: "" };
  const signIn = {
    href: "/auth/google",
    getAttribute(name) { return name === "href" ? this.href : null; },
  };
  const stateMatch = html.match(/id="lm-flow"[^>]*data-setup-state="([^"]*)"/);
  const root = {
    dataset: { setupState: stateMatch ? stateMatch[1] : "" },
    addEventListener(name, handler) { handlers[name] = handler; },
    querySelector(selector) {
      if (selector === "button[type='submit']" || selector === 'button[type="submit"]') {
        return { disabled: false };
      }
      return null;
    },
  };
  const window = {
    location: {
      href,
      assign(value) {
        redirects.push(value);
        this.href = new URL(value, this.href).toString();
      },
    },
    history: {
      replaceState(_state, _title, value) {
        replacements.push(value);
        window.location.href = new URL(value, window.location.href).toString();
      },
    },
  };
  const script = html.match(/<script>([\s\S]*?)<\/script>/);
  assert.ok(script);
  const execution = vm.runInNewContext(script[1], {
    document: {
      getElementById(id) {
        if (id === "lm-sign-in") return signIn;
        if (id === "lm-flow") return root;
        if (id === "lm-feedback") return feedback;
        return null;
      },
      querySelector() { return { content: user.csrf }; },
      querySelectorAll() { return []; },
    },
    URL,
    Intl,
    Date,
    fetch: async (path, init = {}) => {
      requests.push({ path, init });
      const response = responses[path] || { ok: true };
      return {
        ok: response._ok !== false,
        json: async () => response,
      };
    },
    window,
  });
  return { handlers, requests, redirects, replacements, feedback, root, signIn, window, execution };
}

test("signed-out page starts with one Google Calendar connection CTA instead of a Life Manager login", () => {
  const html = visibleHtml(renderWebPage({}));
  assert.match(html, /Google Calendarに接続/);
  assert.doesNotMatch(html, /Google で続ける|Life Managerのパスワード|<form/i);
  assert.doesNotMatch(html, /telegram/i);
});

test("connected state and seven-day trial offer share one screen with exact $29 terms", () => {
  const html = renderWebPage({
    user,
    snapshot: snapshot({ setupState: "trial_offer" }),
    trialOffer: { firstChargeAt: "2030-01-08T00:00:00.000Z", timezone: "Asia/Tokyo" },
  });
  const visible = visibleHtml(html);

  assert.match(visible, /Google Calendarに接続しました/);
  assert.match(visible, /移動時間はCalendarに自動登録済みです/);
  assert.match(visible, /本日のお支払いは\$0です/);
  assert.match(visible, /7日間/);
  assert.match(visible, /2030年1月8日/);
  assert.match(visible, /9:00/);
  assert.match(visible, /\$29\/月/);
  assert.match(visible, /カード登録が必要/);
  assert.match(visible, /その後は解約まで毎月自動更新/);
  assert.match(visible, /請求を避けるには2030年1月8日.*9:00.*までに解約/);
  assert.match(visible, /7日間の無料トライアルを始める/);
  assert.doesNotMatch(visible, /lm-dashboard|今日の予定|次の出発|homeAddress|chat thread/i);
  assert.doesNotMatch(visible, /Messages|sms:/i);
});

test("returning from Stripe shows a pending state without a second checkout button", () => {
  const html = visibleHtml(renderWebPage({
    user,
    snapshot: snapshot({ setupState: "trial_offer" }),
    checkoutPending: true,
  }));
  assert.match(html, /お申し込みを確認しています/);
  assert.doesNotMatch(html, /data-action="checkout"/);
});

test("successful Checkout return waits for the webhook when only the session link is stored", () => {
  for (const planStatus of [null, "incomplete"]) {
    const html = visibleHtml(renderWebPage({
      user,
      snapshot: snapshot({ setupState: "billing_inactive", stripeSubscriptionId: "sub-pending", planStatus }),
      checkoutPending: true,
    }));
    assert.match(html, /お申し込みを確認しています/);
    assert.doesNotMatch(html, /data-action="checkout"|月額\$29で再開する/);
  }
});

test("the trial action calls the server Checkout and redirects only to Stripe", async () => {
  const page = renderWebPage({
    user,
    snapshot: snapshot({ setupState: "trial_offer" }),
    trialOffer: { firstChargeAt: "2030-01-08T00:00:00.000Z", timezone: "Asia/Tokyo" },
  });
  const client = mountClient(page, {
    "/api/lm-web/checkout": { url: "https://checkout.stripe.com/c/pay/cs_test_123" },
  });
  const button = { dataset: { action: "checkout" }, disabled: false };
  await client.handlers.click({ target: { closest: () => button } });
  assert.equal(client.requests[0].path, "/api/lm-web/checkout");
  assert.equal(client.requests[0].init.headers["x-lm-web-csrf"], user.csrf);
  assert.deepEqual(JSON.parse(client.requests[0].init.body), {});
  assert.deepEqual(client.redirects, ["https://checkout.stripe.com/c/pay/cs_test_123"]);
});

test("zero-block state shows a rescan action but no trial checkout", () => {
  const html = visibleHtml(renderWebPage({
    user,
    snapshot: snapshot({
      setupState: "no_eligible_events",
      firstTravelAt: null,
      confirmedTravelBlockCount: 0,
      checkoutAvailable: false,
      scanState: "zero_blocks",
    }),
  }));

  assert.match(html, /Calendarに接続しました/);
  assert.match(html, /移動時間を追加できる予定はまだありません/);
  assert.match(html, /data-action="rescan"/);
  assert.doesNotMatch(html, /無料トライアル|Checkout|data-action="checkout"/);
  assert.doesNotMatch(html, /lm-dashboard|homeAddress|chat thread/i);
});

test("trial-active state confirms automation without rendering a daily dashboard", () => {
  const html = visibleHtml(renderWebPage({
    user,
    snapshot: snapshot({ setupState: "trial_active", paid: true, planStatus: "trialing", checkoutAvailable: false }),
  }));

  assert.match(html, /Google Calendarに接続しました/);
  assert.match(html, /移動時間はCalendarに自動登録されます/);
  assert.match(html, /このページは閉じても大丈夫です/);
  assert.doesNotMatch(html, /lm-dashboard|今日の予定|次の出発|homeAddress|data-action="checkout"/);
});

test("active and billing-inactive states can open Stripe's customer portal", async () => {
  for (const setupState of ["trial_active", "billing_inactive"]) {
    const page = renderWebPage({
      user,
      snapshot: snapshot({ setupState, paid: setupState === "trial_active", planStatus: setupState === "trial_active" ? "trialing" : "canceled" }),
      customerPortalAvailable: true,
    });
    const visible = visibleHtml(page);
    assert.match(visible, /サブスクリプションを管理/);
    const client = mountClient(page, {
      "/api/lm-web/billing/portal": { url: "https://billing.stripe.com/p/session/test" },
    });
    const button = { dataset: { action: "billing-portal" }, disabled: false };
    await client.handlers.click({ target: { closest: () => button } });
    assert.equal(client.requests[0].path, "/api/lm-web/billing/portal");
    assert.deepEqual(client.redirects, ["https://billing.stripe.com/p/session/test"]);
  }
});

test("billing-inactive state explains scheduled cancellation without deleting existing blocks", () => {
  const html = visibleHtml(renderWebPage({
    user,
    snapshot: snapshot({ setupState: "billing_inactive", paid: false, planStatus: "trialing" }),
  }));
  assert.match(html, /解約手続き中/);
  assert.match(html, /既存のCalendar予定は残っています/);
});

test("billing-inactive legacy or canceled customer can restart at $29 without another trial", () => {
  const html = visibleHtml(renderWebPage({
    user,
    snapshot: snapshot({ setupState: "billing_inactive", paid: false,
      planStatus: "canceled", subscriptionCheckoutAvailable: true }),
  }));
  assert.match(html, /この再開には無料トライアルは適用されません/);
  assert.match(html, /開始時に\$29\/月を請求/);
  assert.match(html, /data-action="checkout"/);
  assert.match(html, /月額\$29で再開する/);
});

test("verified Messages contact link is omitted unless the server supplies one", () => {
  const hidden = visibleHtml(renderWebPage({ user, snapshot: snapshot({ setupState: "trial_offer" }) }));
  const shown = visibleHtml(renderWebPage({
    user,
    snapshot: snapshot({ setupState: "trial_offer" }),
    messagesContactUrl: "sms:+12025550123",
  }));

  assert.doesNotMatch(hidden, /Messagesで問い合わせ|sms:/i);
  assert.match(shown, /href="sms:\+12025550123"/);
  assert.match(shown, /Messagesで問い合わせ/);
});

test("Google auth return automatically starts Calendar OAuth using the server redirect", async () => {
  const page = renderWebPage({
    user,
    snapshot: snapshot({ setupState: "needs_calendar", calendarState: "action_required", checkoutAvailable: false }),
  });
  const redirectUrl = "https://accounts.google.com/o/oauth2/v2/auth?state=server-value";
  const client = mountClient(page, {
    "/api/lm-web/calendar/start": { redirectUrl },
  }, "https://life.example/lm?start_calendar=1");

  await client.execution;
  const start = client.requests.find((request) => request.path === "/api/lm-web/calendar/start");
  assert.equal(start.init.method, "POST");
  assert.equal(start.init.headers["x-lm-web-csrf"], user.csrf);
  assert.deepEqual(JSON.parse(start.init.body), {});
  assert.deepEqual(client.redirects, [redirectUrl]);
  assert.deepEqual(client.replacements, ["/lm"]);
});

test("Calendar return automatically runs one initial scan with an empty request body", async () => {
  const page = renderWebPage({
    user,
    snapshot: snapshot({ setupState: "needs_initial_scan", checkoutAvailable: false }),
  });
  const client = mountClient(page, {
    "/api/lm-web/setup": { setupState: "trial_offer", checkoutAvailable: true },
  }, "https://life.example/lm?initial_scan=1");

  await client.execution;
  const setup = client.requests.find((request) => request.path === "/api/lm-web/setup");
  assert.equal(setup.init.method, "POST");
  assert.equal(setup.init.headers["x-lm-web-csrf"], user.csrf);
  assert.deepEqual(JSON.parse(setup.init.body), {});
  assert.deepEqual(client.redirects, ["/lm"]);
  assert.deepEqual(client.replacements, ["/lm"]);
});

test("the signed-out CTA preserves one source UTM through the auth start URL", async () => {
  const page = renderWebPage({});
  const client = mountClient(page, {}, "https://life.example/lm?utm_source=ig&utm_campaign=founder-diary");

  await client.execution;

  assert.equal(client.signIn.href, "/auth/google?utm_source=ig&utm_campaign=founder-diary");
});
