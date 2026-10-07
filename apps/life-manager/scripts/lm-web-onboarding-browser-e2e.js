"use strict";

const assert = require("node:assert/strict");
const http = require("node:http");
const { chromium } = require("playwright-core");
const { renderWebPage } = require("../lib/web-page.js");

const CHROME = process.env.CHROME_BIN || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const USER = { uid: "lm_123e4567-e89b-12d3-a456-426614174000", csrf: "e2e-csrf" };
const trialOffer = { firstChargeAt: "2030-01-08T00:00:00.000Z", timezone: "Asia/Tokyo" };
const state = { authenticated: false, calendarConnected: false, scanComplete: false, trialActive: false,
  travelReady: false, calendarStarts: 0, scans: 0, checkouts: 0 };

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "cache-control": "no-store", ...headers });
  res.end(body);
}

function json(res, body) {
  send(res, 200, JSON.stringify(body), { "content-type": "application/json; charset=utf-8" });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      try { resolve(raw ? JSON.parse(raw) : {}); } catch (error) { reject(error); }
    });
    req.on("error", reject);
  });
}

async function startServer() {
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url || "/", "http://127.0.0.1");
    if (url.pathname === "/auth/google") {
      state.authenticated = true;
      return send(res, 303, "", { location: "/lm?start_calendar=1" });
    }
    if (url.pathname === "/lm") {
    const snapshot = !state.authenticated
      ? null
      : !state.calendarConnected
        ? { setupState: "needs_calendar", calendarState: "action_required", checkoutAvailable: false }
        : !state.scanComplete
          ? { setupState: "needs_initial_scan", calendarState: "connected", checkoutAvailable: false }
          : !state.travelReady
            ? { setupState: "no_eligible_events", calendarState: "connected", paid: false,
                checkoutAvailable: false, confirmedTravelBlockCount: 0, scanState: "zero_blocks" }
            : state.trialActive
              ? { setupState: "trial_active", calendarState: "connected", paid: false, planStatus: "trialing" }
              : { setupState: "trial_offer", calendarState: "connected", paid: false, checkoutAvailable: true,
                  confirmedTravelBlockCount: 1, firstTravelAt: "2030-01-01T00:00:00.000Z" };
      const html = renderWebPage({
        user: state.authenticated ? USER : null,
        authError: url.searchParams.get("auth_error") === "connection" ? "connection" : "",
        snapshot,
        trialOffer: state.scanComplete ? trialOffer : null,
        customerPortalAvailable: state.trialActive,
      });
      return send(res, 200, html, { "content-type": "text/html; charset=utf-8" });
    }
    if (url.pathname === "/api/lm-web/calendar/start" && req.method === "POST") {
      const body = await readBody(req);
      assert.deepEqual(body, {});
      state.calendarStarts++;
      state.calendarConnected = true;
      return json(res, { redirectUrl: "https://accounts.google.com/e2e-calendar-consent" });
    }
    if (url.pathname === "/api/lm-web/setup" && req.method === "POST") {
      const body = await readBody(req);
      if (body.rescan === true) {
        assert.equal(state.scanComplete, true);
        assert.equal(state.travelReady, false);
        state.travelReady = true;
      } else {
        assert.deepEqual(body, {});
        state.scanComplete = true;
      }
      state.scans++;
      return json(res, { setupState: state.travelReady ? "trial_offer" : "no_eligible_events",
        scanState: state.travelReady ? "complete" : "zero_blocks", checkoutAvailable: state.travelReady });
    }
    if (url.pathname === "/api/lm-web/checkout" && req.method === "POST") {
      const body = await readBody(req);
      assert.deepEqual(body, {});
      state.checkouts++;
      return json(res, { url: "https://checkout.stripe.com/c/pay/lm-e2e" });
    }
    if (url.pathname === "/test/activate-trial") {
      state.trialActive = true;
      return send(res, 303, "", { location: "/lm" });
    }
    return send(res, 404, "not found", { "content-type": "text/plain" });
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  return { server, base: "http://127.0.0.1:" + address.port };
}

async function assertNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  assert.equal(overflow, false, "page must fit the viewport without horizontal scrolling");
}

(async () => {
  const { server, base } = await startServer();
  let browser;
  try {
    browser = await chromium.launch({ executablePath: CHROME, headless: true });
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    page.setDefaultTimeout(8000);
    page.setDefaultNavigationTimeout(8000);
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame()) process.stdout.write("navigated " + frame.url() + "\n");
    });

    await page.route("https://accounts.google.com/**", async (route) => {
      const next = JSON.stringify(base + "/lm?initial_scan=1");
      const body = "<!doctype html><html lang='ja'><meta charset='utf-8'><main><h1>Google Calendar権限</h1>"
        + "<p>テスト用の合成同意画面</p><button id='allow'>Calendar権限を許可</button></main>"
        + "<script>document.getElementById('allow').onclick=()=>location.href=" + next + ";</script></html>";
      await route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body });
    });
    await page.route("https://checkout.stripe.com/**", async (route) => {
      const next = JSON.stringify(base + "/test/activate-trial");
      const body = "<!doctype html><html lang='ja'><meta charset='utf-8'><main><h1>Stripe test checkout</h1>"
        + "<p>合成カードフォーム。実決済は発生しません。</p><label>カード番号 <input aria-label='カード番号'></label>"
        + "<button id='start'>無料トライアルを開始</button></main>"
        + "<script>document.getElementById('start').onclick=()=>location.href=" + next + ";</script></html>";
      await route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body });
    });

    process.stdout.write("stage OAuth retry notice\n");
    await page.goto(base + "/lm?auth_error=connection");
    await page.getByRole("alert").getByText("Google Calendarとの接続を完了できませんでした。もう一度接続してください。").waitFor();
    assert.doesNotMatch(await page.locator("body").innerText(), /callback\.txt|Web sign-in unavailable/i);
    await assertNoHorizontalOverflow(page);
    process.stdout.write("stage signed-out page\n");
    await assertNoHorizontalOverflow(page);
    await page.getByRole("link", { name: "Google Calendarに接続" }).click();
    process.stdout.write("stage Calendar OAuth start\n");
    await page.waitForURL("https://accounts.google.com/e2e-calendar-consent");
    process.stdout.write("stage synthetic Calendar consent\n");
    await page.getByRole("button", { name: "Calendar権限を許可" }).click();
    process.stdout.write("stage initial zero-block scan\n");
    await page.getByRole("heading", { name: "Calendarに接続しました" }).waitFor();
    await page.getByRole("button", { name: "Calendarをもう一度確認" }).waitFor();
    assert.equal(await page.getByRole("button", { name: "7日間の無料トライアルを始める" }).count(), 0);
    await page.getByRole("button", { name: "Calendarをもう一度確認" }).click();
    process.stdout.write("stage explicit zero-block rescan\n");
    await page.getByRole("heading", { name: "移動時間はCalendarに自動登録済みです" }).waitFor();
    await page.getByRole("button", { name: "7日間の無料トライアルを始める" }).waitFor();
    await assertNoHorizontalOverflow(page);
    assert.equal(state.calendarStarts, 1);
    assert.equal(state.scans, 2);

    const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await desktop.goto(base + "/lm");
    await desktop.getByRole("heading", { name: "移動時間はCalendarに自動登録済みです" }).waitFor();
    await assertNoHorizontalOverflow(desktop);

    await page.getByRole("button", { name: "7日間の無料トライアルを始める" }).click();
    await page.waitForURL("https://checkout.stripe.com/c/pay/lm-e2e");
    process.stdout.write("stage synthetic Stripe Checkout\n");
    await page.getByRole("heading", { name: "Stripe test checkout" }).waitFor();
    await page.getByRole("button", { name: "無料トライアルを開始" }).click();
    await page.getByText("このページは閉じても大丈夫です").waitFor();
    await assertNoHorizontalOverflow(page);
    assert.equal(state.checkouts, 1);

    process.stdout.write(JSON.stringify({
      result: "PASS",
      flow: ["OAuth retry notice", "Calendar CTA", "mock Google consent", "zero-block scan", "explicit rescan", "combined trial offer", "mock Stripe checkout", "trial-active confirmation"],
      viewports: ["390x844", "1440x900"],
      calendarStarts: state.calendarStarts,
      scans: state.scans,
      checkouts: state.checkouts,
      providers: "synthetic; no Google sign-in, personal Calendar access, or real payment",
    }) + "\n");
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
})().catch((error) => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 1;
});
