"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { formatTravelReminder, travelReminderOnce } = require("./travel-reminder.js");
const { parseTransitPlan } = require("./transit.js");
const { fetchUpcomingEvents } = require("./events.js");
const START = Date.parse("2026-09-05T18:00:00+09:00");
const options = { departureMs: START - 38 * 60000, timezone: "Asia/Tokyo" };
const event = (extra = {}) => ({ id: "detail-event", summary: "予定", location: "目的地", startMs: START, endMs: START + 3600000, ...extra });
const time = (value) => `2026-09-05T${value}:00+09:00`;
const stop = (name, platform = null) => ({ name, platform });
function route() {
  return {
    provider: "transit", durationSeconds: 2280, arrivalAt: time("17:59"),
    accessWalkSeconds: 360, egressWalkSeconds: 420, transferCount: 1,
    fare: { currency: "JPY", ic: 377 },
    steps: [
      { kind: "transit", service: "路線A", headsign: "西行", from: stop("駅A", "1番線"), to: stop("駅B"), departAt: time("17:28"), arriveAt: time("17:36") },
      { kind: "walk", from: stop("駅B"), to: stop("駅C"), departAt: time("17:36"), arriveAt: time("17:40") },
      { kind: "transit", service: "路線B", headsign: "北行", from: stop("駅C", "2番線"), to: stop("駅D"), departAt: time("17:43"), arriveAt: time("17:52") },
    ],
  };
}
function inOrder(text, parts) {
  let previous = -1;
  for (const part of parts) {
    const index = text.indexOf(part, previous + 1);
    assert.ok(index > previous, `missing or out of order: ${part}\n${text}`);
    previous = index;
  }
}

test("CLOUD-01 renders access, every ride, transfer walk, and egress in order", () => {
  const text = formatTravelReminder(event(), route(), options);
  inOrder(text, ["出発地 → 駅A", "徒歩 6分", "17:28 駅A 1番線", "路線A・西行", "駅B → 駅C", "徒歩 4分", "17:43 駅C 2番線", "路線B・北行", "駅D → 目的地", "徒歩 7分"]);
  assert.match(text, /乗換 1回 \/ IC 377円/);
  assert.doesNotMatch(text, /徒歩 13分/); // Access + egress is NOT the complete walking total.
});

test("CLOUD-01 accepts real parser output instead of a formatter-only route shape", () => {
  const seconds = (h, m) => h * 3600 + m * 60;
  const plan = {
    date: "20260905", timezone: "Asia/Tokyo", type: "arrival",
    journeys: [{ departureSecs: seconds(17, 28), arrivalSecs: seconds(17, 59), durationSecs: 1860,
      accessWalkSecs: 360, egressWalkSecs: 420, transferCount: 1,
      legs: route().steps.map((step) => ({
        kind: step.kind, routeName: step.service, headsign: step.headsign,
        from: { name: step.from.name, platformCode: step.from.platform }, to: { name: step.to.name },
        departureSecs: (Date.parse(step.departAt) - Date.parse("2026-09-05T00:00:00+09:00")) / 1000,
        arrivalSecs: (Date.parse(step.arriveAt) - Date.parse("2026-09-05T00:00:00+09:00")) / 1000,
      })),
    }],
  };
  const parsed = parseTransitPlan(plan, { anchorType: "arrival", anchorSecs: seconds(18, 0) });
  assert.ok(parsed);
  const text = formatTravelReminder(event(), parsed, options);
  inOrder(text, ["徒歩 6分", "路線A", "徒歩 4分", "路線B", "徒歩 7分"]);
});

test("CLOUD-01 displays provider arrival separately from Calendar start", () => {
  const text = formatTravelReminder(event(), route(), options);
  assert.match(text, /次は 18:00/);
  assert.match(text, /17:59 到着予定/);
  assert.doesNotMatch(text, /18:00 到着予定/);
  const noArrival = formatTravelReminder(event(), { ...route(), arrivalAt: null }, options);
  assert.doesNotMatch(noArrival, /到着予定/);
});

test("CLOUD-01 walk-only routes use walking copy and do not double-count edge walks", () => {
  const r = { provider: "google", durationSeconds: 600, accessWalkSeconds: 600, egressWalkSeconds: 600,
    steps: [{ kind: "walk", from: stop("出発地"), to: stop("目的地"), departAt: time("17:45"), arriveAt: time("17:55") }] };
  const text = formatTravelReminder(event(), r, options);
  assert.match(text, /^🚶 次は/);
  assert.equal((text.match(/徒歩 10分/g) || []).length, 1);
  assert.doesNotMatch(text, /🚆|番線|乗換/);
});

test("CLOUD-01 full walk steps take precedence over duplicate edge summaries", () => {
  const r = route();
  r.steps.unshift({ kind: "walk", from: stop("出発地"), to: stop("駅A"), departAt: time("17:22"), arriveAt: time("17:28") });
  r.steps.push({ kind: "walk", from: stop("駅D"), to: stop("目的地"), departAt: time("17:52"), arriveAt: time("17:59") });
  const text = formatTravelReminder(event(), r, options);
  assert.equal((text.match(/徒歩 6分/g) || []).length, 1);
  assert.equal((text.match(/徒歩 7分/g) || []).length, 1);
});

test("CLOUD-01 missing or malformed walk facts never become invented numbers", () => {
  const r = route();
  r.accessWalkSeconds = null;
  r.egressWalkSeconds = -1;
  r.steps[1].departAt = "not-a-time";
  const text = formatTravelReminder(event(), r, options);
  assert.match(text, /駅B → 駅C/);
  assert.match(text, /所要時間不明/);
  assert.doesNotMatch(text, /徒歩 0分|徒歩 -|NaN|Invalid|出発地 → 駅A|駅D → 目的地/);
});

test("CLOUD-01 online event page is details, not a fabricated meeting link", () => {
  const text = formatTravelReminder(event({ online: true, location: "オンライン: https://events.example/workshop?a=1&b=2" }), null, options);
  assert.match(text, /^💻 次は 18:00/);
  assert.match(text, /イベント詳細: https:\/\/events\.example\/workshop\?a=1&amp;b=2/);
  assert.doesNotMatch(text, /🚆|出発|到着|目的地|経路|参加:|開始5分前/);
});

test("CLOUD-01 online state is authoritative even when a stale route is passed", () => {
  const text = formatTravelReminder(event({ isOnline: true }), route(), options);
  assert.match(text, /^💻/);
  assert.doesNotMatch(text, /出発|到着|徒歩|路線|円/);
});

test("CLOUD-01 online URLs reject unsafe schemes, credentials, and malformed text", () => {
  for (const location of ["オンライン: javascript:alert(1)", "http://events.example", "https://user:secret@events.example", "https://events.example bad", "https://events.example\nInjected", "https://"]) {
    const text = formatTravelReminder(event({ online: true, location }), null, options);
    assert.doesNotMatch(text, /イベント詳細:|secret|Injected|javascript:/);
  }
});

test("CLOUD-01 a locationless event is a reminder, not a train journey", () => {
  const text = formatTravelReminder(event({ location: null }), null, options);
  assert.match(text, /^🔔 次は/);
  assert.doesNotMatch(text, /🚆|出発|到着|目的地|経路/);
});

test("CLOUD-01 failed physical route does not display fabricated departure or arrival", () => {
  const text = formatTravelReminder(event(), null, options);
  assert.match(text, /次は 18:00/);
  assert.match(text, /目的地: 目的地/);
  assert.match(text, /経路を取得できませんでした/);
  assert.doesNotMatch(text, /出発|到着予定|番線|IC/);
});

test("CLOUD-01 escapes all walking and transit text without inventing optional details", () => {
  const r = route();
  r.steps[1].from.name = "<改札>&";
  r.steps[1].to.name = "<出口>";
  r.fare = null;
  r.transferCount = null;
  const text = formatTravelReminder(event({ summary: "<予定>&" }), r, options);
  assert.match(text, /&lt;改札&gt;&amp; → &lt;出口&gt;/);
  assert.doesNotMatch(text, /<改札>|<出口>|<予定>|号車|IC|混雑/);
});

test("CLOUD-01 detailed reminders stay within one Telegram message and retain HTML entities", () => {
  const text = formatTravelReminder(event({ summary: "<長い予定>&".repeat(800) }), route(), options);
  assert.ok(text.length <= 4096);
  assert.match(text, /一部省略/);
  assert.doesNotMatch(text.replace(/&(?:amp|lt|gt|quot|#39);/g, ""), /[<&]/);
  assert.doesNotMatch(text, /[\uD800-\uDBFF]$/);
});

test("CLOUD-01 real event projection skips route calls and preserves send/receipt/replay for online", async () => {
  const events = await fetchUpcomingEvents("detail-tenant", {
    nowMs: START - 300000,
    calendar: { listEventsRaw: async () => [{ id: "detail-online", summary: "オンライン予定", location: "オンライン: https://events.example/workshop", start: { dateTime: time("18:00") }, end: { dateTime: time("19:00") } }] },
  });
  assert.equal(events[0].online, true);
  let routeCalls = 0, sends = 0, claimed = false;
  const order = [];
  const deps = {
    events, home: "基準地点", telegramToken: "test-token", supaUrl: "test-supa", supaKey: "test-key",
    directionsRoute: async () => { routeCalls++; return route(); },
    claimTravel: async () => { order.push("claim"); if (claimed) return false; claimed = true; return true; },
    sendMessage: async (_token, _chat, text) => { sends++; order.push("send"); assert.match(text, /^💻/); return { ok: true, result: { message_id: 902 } }; },
    recordTravelTelegramReceipt: async () => { order.push("receipt"); return { ok: true, matched: 1 }; },
    log: () => {},
  };
  const user = { uid: "detail-tenant", telegram_chat_id: "detail-chat", notifications_enabled: true };
  assert.equal((await travelReminderOnce(user, START - 300000, deps)).status, "sent");
  assert.equal((await travelReminderOnce(user, START - 300000, deps)).reason, "duplicate");
  assert.deepEqual(order, ["claim", "send", "receipt", "claim"]);
  assert.equal(routeCalls, 0);
  assert.equal(sends, 1);
});
