"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  parseArgs,
  formatTokyoRange,
  findBlockingInterval,
  buildRows,
  buildTotals,
  renderOutput,
  validBrowserBaseUrl,
} = require("../discover.js");

test("parseArgs accepts --provider luma and --provider connpass, with optional --json", () => {
  assert.deepEqual(parseArgs(["--provider", "luma"]), { provider: "luma", json: false });
  assert.deepEqual(parseArgs(["--provider", "connpass", "--json"]), { provider: "connpass", json: true });
  assert.deepEqual(parseArgs(["--json", "--provider", "luma"]), { provider: "luma", json: true });
});

test("parseArgs fails closed on unknown provider, missing provider, and unknown flags", () => {
  assert.throws(() => parseArgs([]), /Usage: discover\.js/);
  assert.throws(() => parseArgs(["--provider", "meetup"]), /Usage: discover\.js/);
  assert.throws(() => parseArgs(["--provider", "luma", "--rsvp"]), /Unknown argument: --rsvp/);
});

test("browser endpoint validation accepts the registry-resolved IPv6 endpoint and rejects public hosts", () => {
  assert.equal(validBrowserBaseUrl("http://[::1]:9222"), "http://[::1]:9222");
  assert.equal(validBrowserBaseUrl("http://localhost:9222"), "http://localhost:9222");
  assert.throws(() => validBrowserBaseUrl("http://example.com:9222"), /browser endpoint invalid/);
});

test("formatTokyoRange converts UTC instants to Asia/Tokyo date and HH:mm", () => {
  // 2026-08-22T10:00:00Z is 2026-08-22 19:00 JST (UTC+9), ends 21:00 JST.
  const range = formatTokyoRange("2026-08-22T10:00:00Z", "2026-08-22T12:00:00Z");
  assert.deepEqual(range, { date: "2026-08-22", start: "19:00", end: "21:00" });
});

test("formatTokyoRange rejects an unparsable instant", () => {
  assert.throws(() => formatTokyoRange("not-a-date", "2026-08-22T12:00:00Z"));
});

test("findBlockingInterval returns the overlapping timed busy interval, or null when free", () => {
  const candidate = { starts_at: "2026-08-22T10:00:00Z", ends_at: "2026-08-22T12:00:00Z" };
  const busy = [
    { kind: "timed", start_at: "2026-08-22T11:00:00Z", end_at: "2026-08-22T11:30:00Z" },
    { kind: "all_day", start_at: "2026-08-22T00:00:00Z", end_at: "2026-08-23T00:00:00Z" },
  ];
  assert.equal(findBlockingInterval(candidate, busy), busy[0]);
  assert.equal(findBlockingInterval(candidate, []), null);
  assert.equal(findBlockingInterval(candidate, { busy_intervals: [] }), null);
  assert.equal(findBlockingInterval(candidate, { busy_intervals: busy }), busy[0]);
});

test("buildRows reports pass/fail with the blocking interval for calendar-checked candidates", () => {
  const free = {
    starts_at: "2026-08-22T10:00:00Z", ends_at: "2026-08-22T12:00:00Z",
    title: "Free Event", canonical_url: "https://luma.com/free",
  };
  const blocked = {
    starts_at: "2026-08-25T09:00:00Z", ends_at: "2026-08-25T11:00:00Z",
    title: "Blocked Event", canonical_url: "https://luma.com/blocked",
  };
  const blockingInterval = { kind: "timed", start_at: "2026-08-25T09:30:00Z", end_at: "2026-08-25T10:00:00Z" };
  const rows = buildRows({
    spyEntries: [
      { candidate: free, passed: true, blocking: null },
      { candidate: blocked, passed: false, blocking: blockingInterval },
    ],
  });
  assert.equal(rows.length, 2);
  assert.equal(rows[0].title, "Free Event");
  assert.equal(rows[0].free_open, "pass");
  assert.equal(rows[0].calendar_free, "pass");
  assert.equal(rows[0].blocked_by, null);
  assert.equal(rows[1].title, "Blocked Event");
  assert.equal(rows[1].calendar_free, "fail");
  assert.deepEqual(rows[1].blocked_by, { date: "2026-08-25", start: "18:30", end: "19:00" });
});

test("buildRows appends already-registered Connpass candidates and sorts everything by start time", () => {
  const later = { starts_at: "2026-08-26T09:00:00Z", ends_at: "2026-08-26T10:00:00Z", title: "Later", canonical_url: "https://connpass.com/later" };
  const earlier = { starts_at: "2026-08-22T09:00:00Z", ends_at: "2026-08-22T10:00:00Z", title: "Earlier", canonical_url: "https://connpass.com/earlier" };
  const rows = buildRows({
    spyEntries: [{ candidate: later, passed: true, blocking: null }],
    registeredExisting: [earlier],
  });
  assert.equal(rows.length, 2);
  assert.equal(rows[0].title, "Earlier");
  assert.equal(rows[0].free_open, "registered");
  assert.equal(rows[0].calendar_free, "n/a");
  assert.equal(rows[1].title, "Later");
});

test("buildTotals mirrors a wake's five discovery-audit fields and defaults missing ones to 0", () => {
  assert.deepEqual(
    buildTotals({ observed_count: 12, normalized_count: 10, window_count: 8, free_open_count: 3, calendar_free_count: 1 }),
    { observed_count: 12, normalized_count: 10, window_count: 8, free_open_count: 3, calendar_free_count: 1 },
  );
  assert.deepEqual(
    buildTotals(null),
    { observed_count: 0, normalized_count: 0, window_count: 0, free_open_count: 0, calendar_free_count: 0 },
  );
});

test("renderOutput --json emits provider, rows, and totals as JSON", () => {
  const rows = buildRows({ spyEntries: [{
    candidate: { starts_at: "2026-08-22T10:00:00Z", ends_at: "2026-08-22T12:00:00Z", title: "T", canonical_url: "https://luma.com/t" },
    passed: true, blocking: null,
  }] });
  const totals = buildTotals({ observed_count: 1, normalized_count: 1, window_count: 1, free_open_count: 1, calendar_free_count: 1 });
  const text = renderOutput({ provider: "luma", rows, totals, json: true });
  const parsed = JSON.parse(text);
  assert.equal(parsed.provider, "luma");
  assert.equal(parsed.rows.length, 1);
  assert.equal(parsed.totals.calendar_free_count, 1);
});

test("renderOutput plain-text mode prints a header row, one line per event, and a totals line", () => {
  const rows = buildRows({ spyEntries: [{
    candidate: { starts_at: "2026-08-22T10:00:00Z", ends_at: "2026-08-22T12:00:00Z", title: "T", canonical_url: "https://luma.com/t" },
    passed: true, blocking: null,
  }] });
  const totals = buildTotals({ observed_count: 5, normalized_count: 4, window_count: 3, free_open_count: 2, calendar_free_count: 1 });
  const text = renderOutput({ provider: "connpass", rows, totals, json: false });
  assert.match(text, /^provider: connpass/);
  assert.match(text, /DATE \| START \| END \| FREE\/OPEN \| CAL_FREE \| BLOCKED_BY \| TITLE \| URL/);
  assert.match(text, /2026-08-22 \| 19:00 \| 21:00 \| pass \| pass \| - \| T \| https:\/\/luma\.com\/t/);
  assert.match(text, /totals: observed=5 normalized=4 window=3 free_open=2 calendar_free=1/);
});

test("renderOutput plain-text mode notes an empty row set instead of printing nothing", () => {
  const totals = buildTotals(null);
  const text = renderOutput({ provider: "luma", rows: [], totals, json: false });
  assert.match(text, /no candidate reached/);
});
