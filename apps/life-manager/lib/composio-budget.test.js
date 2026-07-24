"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { ComposioBudgetGuard, intervalForCount } = require("./composio-budget.js");
const { makeComposioCalendar } = require("./transport/calendar-composio.js");

test("Composio budget boundaries: alert at 18,000 and soft-degrade only at 19,500", () => {
  assert.deepEqual(intervalForCount(17999), { alert: false, intervalMs: 60000 });
  assert.deepEqual(intervalForCount(18000), { alert: true, intervalMs: 60000 });
  assert.deepEqual(intervalForCount(19499), { alert: true, intervalMs: 60000 });
  assert.deepEqual(intervalForCount(19500), { alert: true, intervalMs: 300000 });
});

test("Composio admin alert is throttled for six hours", async () => {
  const sent = [];
  const guard = new ComposioBudgetGuard({ sendAlert: async (count) => sent.push(count) });
  await guard.update(18000, 0);
  await guard.update(19000, 6 * 60 * 60 * 1000 - 1);
  await guard.update(19001, 6 * 60 * 60 * 1000);
  assert.deepEqual(sent, [18000, 19001]);
});

test("Composio soft-degrade recovers when the monthly count resets", async () => {
  const guard = new ComposioBudgetGuard({ sendAlert: async () => {} });
  assert.equal((await guard.update(19500, 0)).intervalMs, 300000);
  assert.equal((await guard.update(0, 1)).intervalMs, 60000);
});

test("each real Composio execution records one composio_call without making ledger failure fatal", async () => {
  const original = global.fetch;
  const records = [];
  global.fetch = async () => ({ json: async () => ({ successful: true, data: { items: [] } }) });
  try {
    const calendar = makeComposioCalendar({ apiKey: "k", recordCall: async (uid, tool) => records.push({ uid, tool }) });
    assert.deepEqual(await calendar.listEventsRaw("u1", {}), []);
    assert.deepEqual(records, [{ uid: "u1", tool: "GOOGLECALENDAR_EVENTS_LIST" }]);
    const resilient = makeComposioCalendar({ apiKey: "k", recordCall: async () => { throw new Error("ledger down"); } });
    assert.deepEqual(await resilient.listEventsRaw("u1", {}), []);
  } finally { global.fetch = original; }
});

test("calendar provider timeout is aborted and returns the closed read result", async () => {
  let aborted = false;
  const calendar = makeComposioCalendar({
    apiKey: "k",
    timeoutMs: 1,
    fetchImpl: async (_url, { signal }) => await new Promise((_, reject) => {
      signal.addEventListener("abort", () => {
        aborted = true;
        reject(signal.reason);
      }, { once: true });
    }),
  });

  assert.deepEqual(await calendar.listEventsRaw("u1", {}), []);
  assert.equal(aborted, true);
});
