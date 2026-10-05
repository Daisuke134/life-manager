"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
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
    trialExpiresAt: null,
    paid: null,
    ...overrides,
  };
}

test("renders sign-in and each missing setup step", () => {
  const anonymous = renderWebPage({});
  assert.match(anonymous, /href="\/auth\/google"/);
  assert.match(anonymous, /name="viewport" content="width=device-width, initial-scale=1/);
  assert.doesNotMatch(anonymous, /telegram/i);

  const needsCalendar = renderWebPage({ user, snapshot: snapshot({ setupState: "needs_calendar", calendarState: "action_required" }) });
  assert.match(needsCalendar, /id="calendar-connect"/);
  assert.doesNotMatch(needsCalendar, /name="homeAddress"/);

  const needsHome = renderWebPage({ user, snapshot: snapshot({ setupState: "needs_home" }) });
  assert.match(needsHome, /name="homeAddress"/);
  assert.doesNotMatch(needsHome, /id="calendar-connect"/);
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
