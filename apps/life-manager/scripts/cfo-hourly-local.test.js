"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { financialRecordId } = require("../../../runtime/contracts/common-record.cjs");
const { createJsonlFinancialRecordStore } = require("../lib/financial-record-store.js");
const {
  agentReceiptPathsFromEnv, affiliateReadbackPathFromEnv, main, runHourlyCfo, selectCfoRunner,
} = require("./cfo-hourly-local.js");

function revenue(overrides = {}) {
  const subjectId = overrides.subject_id || "dais-local";
  const key = overrides.idempotency_key || "stripe:payment:1";
  return {
    schema_version: 1, record_type: "financial_record",
    record_id: financialRecordId(subjectId, key), subject_id: subjectId,
    scope: "business", kind: "business_revenue", direction: "credit",
    amount_minor: 12500, currency: "JPY",
    occurred_at: "2026-09-07T00:00:00.000Z",
    recorded_at: "2026-09-07T00:01:00.000Z",
    idempotency_key: key,
    source: { provider: "stripe", source_type: "payment_processor", external_ref: "payment-1" },
    verification: {
      status: "verified", observed_at: "2026-09-07T00:01:00.000Z",
      evidence_refs: ["stripe://payment/payment-1"],
    },
    ...overrides,
  };
}

test("CFO reports verified records once and stays quiet on exact replay", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({
    directoryPath: path.join(stateDir, "financial-records"),
  });
  await store.append(revenue());
  const deliveries = [];
  const options = {
    stateDir, subjectId: "dais-local", store,
    ingest: async () => ({ observed: 0, created: 0, sources: {} }),
    now: () => new Date("2026-09-07T06:00:00.000Z"),
    notify: async (input) => {
      deliveries.push(input);
      return { delivery: "delivered", provider_message_id: "telegram-1" };
    },
  };

  const first = await runHourlyCfo(options);
  assert.equal(first.status, "sent");
  assert.equal(first.recordCount, 1);
  assert.equal(deliveries.length, 1);
  assert.match(deliveries[0].message, /今日の確認済み売上: ¥12,500/);
  assert.match(deliveries[0].message, /stripe: ¥12,500/);
  assert.doesNotMatch(deliveries[0].message, /個人資産|直近7日|今月|根拠プロバイダー/);
  await store.append(revenue({
    idempotency_key: "stripe:unverified:2",
    record_id: financialRecordId("dais-local", "stripe:unverified:2"),
    verification: {
      status: "unverified", observed_at: "2026-09-07T01:01:00.000Z",
      evidence_refs: [],
    },
  }));
  assert.equal((await runHourlyCfo(options)).status, "quiet");
  assert.equal(deliveries.length, 1);
});

test("CFO sends at most one consolidated snapshot per local reporting day", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-daily-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({ directoryPath: path.join(stateDir, "financial-records") });
  await store.append(revenue());
  const deliveries = [];
  const base = {
    stateDir, subjectId: "dais-local", store,
    ingest: async () => ({ observed: 0, created: 0, sources: {} }),
    notify: async (input) => (deliveries.push(input),
      { delivery: "delivered", provider_message_id: String(deliveries.length) }),
  };
  assert.equal((await runHourlyCfo({ ...base, now: () => new Date("2026-09-07T06:00:00Z") })).status, "sent");
  await store.append(revenue({
    idempotency_key: "stripe:payment:2",
    record_id: financialRecordId("dais-local", "stripe:payment:2"),
    source: { provider: "stripe", source_type: "payment_processor", external_ref: "payment-2" },
  }));
  assert.equal((await runHourlyCfo({ ...base, now: () => new Date("2026-09-07T10:00:00Z") })).status, "quiet");
  assert.equal((await runHourlyCfo({ ...base, now: () => new Date("2026-09-08T06:00:00Z") })).status, "sent");
  assert.equal(deliveries.length, 2);
  assert.equal(deliveries[0].eventKey, "cfo:dais-local:injected:2026-09-07");
  assert.equal(deliveries[1].eventKey, "cfo:dais-local:injected:2026-09-08");
});

test("CFO recognizes the previous snapshot format and does not resend on release day", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-legacy-snapshot-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({ directoryPath: path.join(stateDir, "financial-records") });
  await store.append(revenue());
  fs.writeFileSync(path.join(stateDir, "last-delivered-snapshot.json"), JSON.stringify({
    schemaVersion: 1, digest: "a".repeat(64), report: { reportingDate: "2026-09-07" },
  }));
  let sends = 0;
  const result = await runHourlyCfo({
    stateDir, subjectId: "dais-local", store,
    ingest: async () => ({ observed: 0, created: 0, sources: {} }),
    now: () => new Date("2026-09-07T10:00:00Z"),
    notify: async () => { sends += 1; return { delivery: "delivered", provider_message_id: "new" }; },
  });
  assert.equal(result.status, "quiet");
  assert.equal(sends, 0);
});

test("CFO freezes and retries the first same-day snapshot after a pre-send failure", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-pending-snapshot-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({ directoryPath: path.join(stateDir, "financial-records") });
  await store.append(revenue());
  const messages = [];
  let attempt = 0;
  const base = {
    stateDir, subjectId: "dais-local", store,
    ingest: async () => ({ observed: 0, created: 0, sources: {} }),
    notify: async ({ message }) => {
      messages.push(message);
      attempt += 1;
      return attempt === 1
        ? { delivery: "pending", provider_message_id: null, attempted: 0 }
        : { delivery: "delivered", provider_message_id: "recovered", attempted: 1 };
    },
  };
  assert.equal((await runHourlyCfo({ ...base, now: () => new Date("2026-09-07T06:00:00Z") })).status, "failed");
  await store.append(revenue({
    idempotency_key: "stripe:payment:after-failure",
    record_id: financialRecordId("dais-local", "stripe:payment:after-failure"),
    amount_minor: 99999,
    source: { provider: "stripe", source_type: "payment_processor", external_ref: "after-failure" },
  }));
  assert.equal((await runHourlyCfo({ ...base, now: () => new Date("2026-09-07T10:00:00Z") })).status, "sent");
  assert.equal(messages.length, 2);
  assert.equal(messages[1], messages[0]);
});

test("CFO suppresses no-data and unverified-only Telegram noise", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({
    directoryPath: path.join(stateDir, "financial-records"),
  });
  await store.append(revenue({
    verification: {
      status: "unverified", observed_at: "2026-09-07T00:01:00.000Z",
      evidence_refs: [],
    },
  }));
  let called = false;
  const result = await runHourlyCfo({
    stateDir, subjectId: "dais-local", store,
    ingest: async () => ({ observed: 0, created: 0, sources: {} }),
    now: () => new Date("2026-09-07T06:00:00.000Z"),
    notify: async () => { called = true; },
  });

  assert.equal(result.status, "quiet");
  assert.equal(result.reason, "no_verified_financial_records");
  assert.equal(result.reportingDate, "2026-09-07");
  assert.equal(result.recordCount, 1);
  assert.equal(result.delivered, false);
  assert.equal(result.ingestion.sources && Object.keys(result.ingestion.sources).length, 0);
  assert.equal(result.report.verifiedRecordCount, 0);
  assert.match(result.digest, /^[a-f0-9]{64}$/);
  assert.equal(called, false);
});

test("CFO excludes old business receipts and does not report historical data as this month", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({
    directoryPath: path.join(stateDir, "financial-records"),
  });
  await store.append(revenue({ occurred_at: "2026-08-31T14:59:59.000Z" }));
  let called = false;
  const result = await runHourlyCfo({
    stateDir, subjectId: "dais-local", store,
    ingest: async () => ({ observed: 0, created: 0, sources: {} }),
    now: () => new Date("2026-09-07T06:00:00.000Z"),
    notify: async () => { called = true; },
  });
  assert.equal(result.status, "quiet");
  assert.equal(result.reason, "no_verified_financial_records");
  assert.equal(called, false);
});

test("CFO fails closed when the shared outbox cannot prove delivery", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({
    directoryPath: path.join(stateDir, "financial-records"),
  });
  await store.append(revenue());

  const result = await runHourlyCfo({
    stateDir, subjectId: "dais-local", store,
    ingest: async () => ({ observed: 0, created: 0, sources: {} }),
    now: () => new Date("2026-09-07T06:00:00.000Z"),
    notify: async () => ({ delivery: "delivery_uncertain", provider_message_id: null }),
  });
  assert.equal(result.status, "failed");
  assert.equal(result.reason, "telegram_delivery_uncertain");
});

test("CFO does not send a stale partial report when a source is unavailable", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({
    directoryPath: path.join(stateDir, "financial-records"),
  });
  await store.append(revenue());
  let called = false;
  const result = await runHourlyCfo({
    stateDir, subjectId: "dais-local", store,
    ingest: async () => ({
      observed: 0, created: 0,
      sources: { moneytree: "unavailable", agentEconomy: "observed_verified" },
    }),
    now: () => new Date("2026-09-07T06:00:00.000Z"),
    notify: async () => { called = true; },
  });
  assert.equal(result.status, "failed");
  assert.equal(result.reason, "financial_source_unavailable");
  assert.deepEqual(result.unavailableSources, ["moneytree"]);
  assert.equal(called, false);
});

test("CFO defaults Agent Economy to its portable Life Manager state and accepts overrides", () => {
  assert.deepEqual(agentReceiptPathsFromEnv({}), [
    path.join(os.homedir(), ".local/state/life-manager/agent-economy/revenue-receipts.jsonl"),
  ]);
  assert.deepEqual(agentReceiptPathsFromEnv({
    LM_AGENT_ECONOMY_STATE_ROOT: "/agent-state",
  }), ["/agent-state/revenue-receipts.jsonl"]);
  assert.deepEqual(agentReceiptPathsFromEnv({
    REVENUE_RECEIPT_JOURNAL: "/state/revenue.jsonl",
  }), ["/state/revenue.jsonl"]);
});

test("CFO defaults Affiliate to the PartnerStack report artifact and accepts overrides", () => {
  assert.equal(
    affiliateReadbackPathFromEnv({}),
    path.join(os.homedir(), ".local/state/life-manager/affiliate/provider-reports/partnerstack/latest.json"),
  );
  assert.equal(
    affiliateReadbackPathFromEnv({ LM_CFO_AFFILIATE_READBACK: "/state/partnerstack.json" }),
    "/state/partnerstack.json",
  );
  assert.equal(
    affiliateReadbackPathFromEnv({ LM_CFO_AFFILIATE_LEDGER: "/state/legacy-ledger.json" }),
    "/state/legacy-ledger.json",
  );
});

test("local main selects canonical Financial Manager daily path by default", async () => {
  const canonical = async () => ({ status: "quiet", reportingDate: "2026-09-07", delivered: false });
  const legacy = async () => ({ status: "sent" });
  assert.equal(selectCfoRunner({}, { runHourlyCfo: canonical, runResultCfo: legacy }), canonical);
  assert.equal(
    selectCfoRunner({ LM_CFO_LEGACY_RESULT_COMPAT: "1" }, { runHourlyCfo: canonical, runResultCfo: legacy }),
    legacy,
  );
  const code = await main({
    CFO_STATE_DIR: fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-main-")),
    LM_CFO_SUBJECT_ID: "dais-local", LM_CFO_REPORT_EMAIL: "owner@example.test",
  }, { runHourlyCfo: async (options) => {
    assert.equal(options.reportCadence, "daily");
    assert.equal(options.subjectId, "dais-local");
    assert.equal(options.googleBillingInvoiceMonth, undefined);
    return canonical();
  }, runResultCfo: legacy });
  assert.equal(code, 0);
});

test("canonical local result exposes personal, business, freshness, and digest", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-canonical-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({ directoryPath: path.join(stateDir, "records") });
  await store.append(revenue({
    idempotency_key: "stripe:canonical:1", record_id: financialRecordId("dais-local", "stripe:canonical:1"),
    occurred_at: "2026-10-02T00:00:00.000Z", recorded_at: "2026-10-02T00:01:00.000Z",
  }));
  await store.append(revenue({
    idempotency_key: "moneytree:canonical:balance", record_id: financialRecordId("dais-local", "moneytree:canonical:balance"),
    scope: "personal", kind: "asset_balance", direction: "snapshot", amount_minor: 504302,
    occurred_at: "2026-10-02T00:00:00.000Z", recorded_at: "2026-10-02T00:00:00.000Z",
    source: { provider: "moneytree", source_type: "moneytree", external_ref: "moneytree:canonical:balance" },
  }));
  const result = await runHourlyCfo({
    stateDir, subjectId: "dais-local", store,
    now: "2026-10-02T06:00:00.000Z", reportCadence: "daily",
    ingest: async () => ({ observed: 2, created: 0,
      sources: { moneytree: "observed_verified", stripe: "observed_verified" },
      sourceFreshness: { moneytree: { status: "fresh", reason: null } },
      economicSourceCoverage: { schema_version: 1, subject_id: "dais-local", complete: true, loops: [] },
    }),
    notify: async () => ({ delivery: "delivered", provider_message_id: "canonical-1" }),
  });
  assert.equal(result.status, "sent");
  assert.deepEqual(result.personal.assets, [{ currency: "JPY", amountMinor: 504302 }]);
  assert.deepEqual(result.business.revenue, [{ currency: "JPY", amountMinor: 12500 }]);
  assert.equal(result.sourceFreshness.moneytree.status, "fresh");
  assert.equal(result.economicSourceCoverage.complete, true);
  assert.match(result.digest, /^[a-f0-9]{64}$/);
  assert.equal(result.providerMessageId, "canonical-1");
});

test("partial source report is delivered with an explicit warning and no zero total", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-partial-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({ directoryPath: path.join(stateDir, "records") });
  await store.append(revenue({
    idempotency_key: "stripe:partial:1", record_id: financialRecordId("dais-local", "stripe:partial:1"),
    occurred_at: "2026-10-02T00:00:00.000Z", recorded_at: "2026-10-02T00:01:00.000Z",
  }));
  let message = "";
  const result = await runHourlyCfo({
    stateDir, subjectId: "dais-local", store, now: "2026-10-02T06:00:00.000Z",
    ingest: async () => ({ observed: 1, created: 0, sources: { moneytree: "observed_unverified" },
      sourceFreshness: { moneytree: { status: "partial", reason: "transaction_completeness_unknown" } },
    }),
    notify: async (input) => { message = input.message; return { delivery: "delivered", provider_message_id: "partial-1" }; },
  });
  assert.equal(result.status, "sent");
  assert.match(message, /moneytree:partial/);
  assert.match(message, /未確認/);
  assert.doesNotMatch(message, /今日の確認済み支出: ¥0/);
});
