"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { financialRecordId } = require("./financial-record-contract.js");
const { createLocalFinancialTransitionStore, localTransitionOptions } = require("./financial-transition-local.js");

function record() {
  const subjectId = "local-user";
  const key = "local:test:1";
  return {
    schema_version: 1, record_type: "financial_record",
    record_id: financialRecordId(subjectId, key), subject_id: subjectId,
    scope: "business", kind: "business_revenue", direction: "credit",
    amount_minor: 2500000, currency: "USDC",
    occurred_at: "2026-09-11T05:00:00.000Z", recorded_at: "2026-09-11T05:00:01.000Z",
    idempotency_key: key,
    source: { provider: "taskmarket", source_type: "marketplace", external_ref: "award-1" },
    verification: { status: "verified", observed_at: "2026-09-11T05:00:01.000Z",
      evidence_refs: ["taskmarket://receipt/1"] },
  };
}

test("Local store routes a record through the durable outbox identity and replay sends zero", async () => {
  const raw = record();
  const seen = new Map();
  let sends = 0;
  const store = createLocalFinancialTransitionStore({
    store: { append: async () => ({ created: sends === 0, record: raw }), read: async () => [raw] },
    notify: async ({ eventKey, message }) => {
      assert.equal(eventKey, `agent-economy:financial:${raw.record_id}`);
      assert.match(message, /収益を受け取りました/);
      if (seen.has(eventKey)) return { delivery: "delivered", provider_message_id: seen.get(eventKey), attempted: 0 };
      sends += 1;
      seen.set(eventKey, "501");
      return { delivery: "delivered", provider_message_id: "501", attempted: 1 };
    },
    now: () => new Date("2026-09-11T05:01:00.000Z"),
  });
  assert.equal((await store.append(raw)).notification.status, "sent");
  const replay = await store.append(raw);
  assert.deepEqual([replay.notification.status, replay.notification.reason], ["quiet", "duplicate"]);
  assert.equal(sends, 1);
});

test("Local options reuse the CFO SQLite outbox and existing Telegram binding", () => {
  const options = localTransitionOptions({
    CFO_STATE_DIR: "/state/cfo", LM_CFO_TELEGRAM_CHAT_ID: "private", LIFE_MANAGER_ENV_FILE: "/state/.env",
  });
  assert.deepEqual(options, {
    pythonBin: "python3", database: "/state/cfo/telegram-outbox.sqlite3",
    chatId: "private", envFile: "/state/.env",
  });
});

test("Local store treats sending and delivery-uncertain states as unknown effects", async () => {
  for (const delivery of ["sending", "delivery_uncertain"]) {
    const raw = record();
    const store = createLocalFinancialTransitionStore({
      store: { append: async () => ({ created: false, record: raw }), read: async () => [raw] },
      notify: async () => ({ delivery, provider_message_id: null, attempted: 0 }),
    });
    await assert.rejects(store.append(raw), (error) => (
      error.code === "FINANCIAL_TRANSITION_DELIVERY_FAILED" && error.unknownEffect === true
    ));
  }
});


test("A bounded multi-chunk helper finishes without a premature parent interruption", { timeout: 45_000 }, () => {
  const fs = require("node:fs");
  const os = require("node:os");
  const path = require("node:path");
  const { notifyViaLocalOutbox } = require("./financial-transition-local.js");
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "cfo-helper-budget-"));
  try {
    const helper = path.join(fixture, "fake-python");
    fs.writeFileSync(helper, '#!/bin/sh\ncat >/dev/null\nfor delay in 11 11 9; do sleep "$delay"; done\nprintf \'%s\\n\' \'{"delivery":"delivered","provider_message_id":"501","attempted":1,"delivered":1}\'\n', { mode: 0o700 });
    const result = notifyViaLocalOutbox({ eventKey: "fixture:three-chunks", observedAt: "2026-10-12T00:00:00Z", message: "fixture report" }, {
      pythonBin: helper, database: path.join(fixture, "outbox.sqlite3"), chatId: "fixture-only", envFile: path.join(fixture, "missing.env"),
    });
    assert.equal(result.delivery, "delivered");
    assert.equal(result.provider_message_id, "501");
  } finally { fs.rmSync(fixture, { recursive: true, force: true }); }
});
