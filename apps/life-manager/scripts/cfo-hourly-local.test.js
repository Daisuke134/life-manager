"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { financialRecordId } = require("../../../runtime/contracts/common-record.cjs");
const { createJsonlFinancialRecordStore } = require("../lib/financial-record-store.js");
const { MONEYTREE_OBSERVATION } = require("../lib/moneytree-local-adapter.js");
const { createMoneytreeObservationStore } = require("../lib/moneytree-observation-store.js");
const {
  agentReceiptPathsFromEnv, affiliateReadbackPathFromEnv, collectCfoProjection, runHourlyCfo,
} = require("./cfo-hourly-local.js");
const { runResultCfo } = require("./cfo-result-local.js");

function businessTable(reportingDate) {
  return {
    reporting_date: reportingDate,
    timezone: "Asia/Tokyo",
    rows: [{ loop_id: "capafy", revenue: { status: "unknown", reason: "no_receipt" } }],
  };
}

function fakePython(root, table) {
  const tablePath = path.join(root, "business.json");
  const callsPath = path.join(root, "business-calls.jsonl");
  const pythonBin = path.join(root, "python");
  fs.writeFileSync(tablePath, JSON.stringify(table));
  fs.writeFileSync(pythonBin, `#!/usr/bin/env node
const fs = require("node:fs");
fs.appendFileSync(${JSON.stringify(callsPath)}, JSON.stringify({
  args: process.argv.slice(2), marker: process.env.CFO_TEST_MARKER,
}) + "\\n");
process.stdout.write(fs.readFileSync(${JSON.stringify(tablePath)}, "utf8"));
`, { mode: 0o700 });
  return { pythonBin, callsPath };
}

function observedRows(rows, tool, payloadHash, query = {}) {
  Object.defineProperty(rows, MONEYTREE_OBSERVATION, {
    enumerable: false,
    value: Object.freeze({
      provider: "moneytree", mcp_server: "codex_apps", tool,
      retrieved_at: "2026-10-07T07:00:00.000Z", payload_sha256: payloadHash,
      ...(tool === "moneytree.show-transactions" ? {
        query_start_date: query.startDate, query_end_date: query.endDate,
        provider_total_count: query.providerTotalCount ?? rows.length,
        returned_count: rows.length, limit: query.limit ?? 1000,
      } : {}),
    }),
  });
  return rows;
}

function collectorFixture(root, {
  date = "2026-10-07", rowsForWindow = () => [], providerCounts = [], failWindow = null,
} = {}) {
  const business = businessTable(date);
  const python = fakePython(root, business);
  const counters = { accountReads: 0, transactionReads: 0, ranges: [] };
  const accounts = observedRows([{
    name: "三菱UFJ銀行 普通", balance_jpy: 42000, observed_at: "2026-10-07T07:00:00.000Z",
  }], "moneytree.show-accounts", "a".repeat(64));
  const options = {
    stateDir: root,
    pythonBin: python.pythonBin,
    env: { ...process.env, CFO_TEST_MARKER: "preserved" },
    now: new Date("2026-10-07T07:30:00.000Z"),
    readAccounts: async () => { counters.accountReads += 1; return accounts; },
    readTransactions: async ({ startDate, endDate, limit }) => {
      const index = counters.transactionReads++;
      counters.ranges.push({ startDate, endDate });
      if (index === failWindow) throw new Error("fixture Moneytree unavailable");
      const rows = rowsForWindow({ index, startDate, endDate });
      return observedRows(rows, "moneytree.show-transactions", String(index + 1).repeat(64), {
        startDate, endDate, limit, providerTotalCount: providerCounts[index] ?? rows.length,
      });
    },
    moneytreeEvidenceStore: createMoneytreeObservationStore({
      directoryPath: path.join(root, "evidence", "moneytree"),
    }),
  };
  return { business, python, counters, options };
}

test("collectCfoProjection preserves business data and binds Moneytree evidence", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-personal-collect-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const date = "2026-10-07";
  const business = businessTable(date);
  const python = fakePython(root, business);
  const accountRead = observedRows([{
    name: "三菱UFJ銀行 普通", balance_jpy: 42000, observed_at: "2026-10-07T07:00:00.000Z",
  }], "moneytree.show-accounts", "a".repeat(64));
  let accountReads = 0;
  const ranges = [];
  const result = await collectCfoProjection(date, {
    stateDir: root,
    pythonBin: python.pythonBin,
    env: { ...process.env, CFO_TEST_MARKER: "preserved" },
    readAccounts: async () => { accountReads += 1; return accountRead; },
    readTransactions: async ({ startDate, endDate, limit }) => {
      ranges.push({ startDate, endDate });
      return observedRows([], "moneytree.show-transactions", String(ranges.length).repeat(64), { startDate, endDate, limit });
    },
    moneytreeEvidenceStore: createMoneytreeObservationStore({
      directoryPath: path.join(root, "evidence", "moneytree"),
    }),
  });

  const { personal_moneytree: personal, ...businessResult } = result;
  assert.deepEqual(businessResult, business);
  assert.equal(accountReads, 1);
  assert.equal(ranges.length, 5);
  assert.equal(personal.windows.length, 5);
  assert.ok(personal.windows.every((window) => window.evidence_ref.startsWith("moneytree-observation://sha256/")));
  assert.equal(fs.readdirSync(path.join(root, "evidence", "moneytree")).length, 5);
  const [collectorCall] = fs.readFileSync(python.callsPath, "utf8").trim().split("\n").map(JSON.parse);
  assert.deepEqual(collectorCall.args.slice(1), ["--date", date, "--json"]);
  assert.equal(collectorCall.marker, "preserved");
});

test("Moneytree reads cover inclusive bounded windows and dedupe boundary rows", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-personal-windows-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const duplicate = { id: "tx-boundary", occurred_at: "2025-10-08", amount_jpy: -1000, category: "食費", merchant: "Market" };
  const fixture = collectorFixture(root, {
    providerCounts: [2, 2, 1001, 0, 1],
    rowsForWindow: ({ index }) => [
      [duplicate, { id: "tx-before-range", occurred_at: "2025-10-01", amount_jpy: -900, category: "食費", merchant: "Old Market" }],
      [duplicate, { id: "tx-feb", occurred_at: "2026-02-02", amount_jpy: -200, category: "交通", merchant: "Train" }],
      [{ id: "tx-may", occurred_at: "2026-05-03", amount_jpy: -300, category: "食費", merchant: "Market" }],
      [],
      [{ id: "tx-latest", occurred_at: "2026-10-07", amount_jpy: 50000, category: "給与", merchant: "Salary" }],
    ][index],
  });

  const result = await collectCfoProjection("2026-10-07", fixture.options);
  const personal = result.personal_moneytree;

  assert.deepEqual(fixture.counters.ranges, [
    { startDate: "2025-10-07", endDate: "2026-01-06" },
    { startDate: "2026-01-07", endDate: "2026-04-06" },
    { startDate: "2026-04-07", endDate: "2026-07-06" },
    { startDate: "2026-07-07", endDate: "2026-10-06" },
    { startDate: "2026-10-07", endDate: "2026-10-07" },
  ]);
  assert.equal(personal.status, "partial");
  assert.equal(personal.windows[0].coverage_status, "partial");
  assert.equal(personal.windows[0].range_mismatch_count, 1);
  assert.equal(personal.windows[1].range_mismatch_count, 1);
  assert.equal(personal.windows[2].coverage_status, "partial");
  assert.equal(personal.latest_transaction_date, "2026-10-07");
  assert.equal(personal.monthly.find((month) => month.month === "2025-10").expense_jpy, 1000);
});

test("inclusive Moneytree chunks stay within three months at month-end and leap day", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-personal-date-edges-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const cases = [
    ["2026-03-31", [
      ["2025-03-31", "2025-06-29"], ["2025-06-30", "2025-09-29"],
      ["2025-09-30", "2025-12-29"], ["2025-12-30", "2026-03-29"], ["2026-03-30", "2026-03-31"],
    ]],
    ["2024-02-29", [
      ["2023-02-28", "2023-05-27"], ["2023-05-28", "2023-08-27"],
      ["2023-08-28", "2023-11-27"], ["2023-11-28", "2024-02-27"], ["2024-02-28", "2024-02-29"],
    ]],
  ];
  for (const [index, [date, expected]] of cases.entries()) {
    const caseRoot = path.join(root, String(index));
    fs.mkdirSync(caseRoot);
    const fixture = collectorFixture(caseRoot, { date });
    await collectCfoProjection(date, fixture.options);
    assert.deepEqual(fixture.counters.ranges.map(({ startDate, endDate }) => [startDate, endDate]), expected);
  }
});

test("Moneytree without provider sync keeps freshness and empty flows unknown", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-personal-empty-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const fixture = collectorFixture(root);

  const result = await collectCfoProjection("2026-10-07", fixture.options);
  const personal = result.personal_moneytree;

  assert.equal(personal.status, "partial");
  assert.equal(personal.provider_sync_at, null);
  assert.equal(personal.freshness_status, "unknown");
  assert.equal(personal.latest_transaction_date, null);
  assert.equal(personal.windows.length, 5);
  assert.ok(personal.windows.every((window) => window.coverage_status === "unknown"));
  assert.equal(personal.monthly.length, 13);
  assert.ok(personal.monthly.every((month) => month.coverage_status === "unknown"
    && month.income_jpy === null && month.expense_jpy === null && month.cash_movement_jpy === null));
});

test("Moneytree transfers are excluded and repeated merchants stay candidates", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-personal-categories-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const fixture = collectorFixture(root, {
    rowsForWindow: ({ index }) => index !== 3 ? [] : [
      { id: "tx-transfer", occurred_at: "2026-10-01", amount_jpy: -2000, category: "振替", merchant: "RAW_TRANSFER_DESC", transfer_id: "transfer" },
      { id: "tx-card", occurred_at: "2026-10-01", amount_jpy: -5400, category: "カード返済", merchant: "RAW_CARD_DESC", transfer_id: "card" },
      { id: "tx-atm", occurred_at: "2026-10-01", amount_jpy: -10000, category: "ATM引き出し", merchant: "RAW_ATM_DESC", transfer_id: "atm" },
      { id: "tx-sub-1", occurred_at: "2026-08-05", amount_jpy: -1000, category: "娯楽", merchant: "Video Service" },
      { id: "tx-sub-2", occurred_at: "2026-09-05", amount_jpy: -1200, category: "娯楽", merchant: "Video Service" },
    ],
  });

  const result = await collectCfoProjection("2026-10-07", fixture.options);
  const personal = result.personal_moneytree;
  const october = personal.monthly.find((month) => month.month === "2026-10");

  assert.equal(october.expense_jpy, null);
  assert.equal(october.cash_movement_jpy, -17400);
  assert.deepEqual(personal.recurring_charge_candidates.map(({ merchant, month_count, total_observed_jpy }) => ({
    merchant, month_count, total_observed_jpy,
  })), [{ merchant: "Video Service", month_count: 2, total_observed_jpy: 2200 }]);
  assert.match(personal.recurring_charge_candidates[0].evidence_refs[0], /^moneytree-observation:\/\/sha256\/[a-f0-9]{64}$/);
  const storedCache = fs.readFileSync(path.join(root, "personal-moneytree-snapshot.json"), "utf8");
  assert.doesNotMatch(storedCache, /RAW_TRANSFER_DESC|RAW_CARD_DESC|RAW_ATM_DESC/);
});

test("Moneytree window failure preserves business and successful observations", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-personal-failure-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const fixture = collectorFixture(root, { failWindow: 1 });

  const result = await collectCfoProjection("2026-10-07", fixture.options);
  const { personal_moneytree: personal, ...businessResult } = result;

  assert.deepEqual(businessResult, fixture.business);
  assert.equal(personal.status, "partial");
  assert.equal(personal.freshness_status, "unknown");
  assert.equal(personal.windows.length, 5);
  assert.equal(personal.windows[1].coverage_status, "unknown");
  assert.equal(personal.windows[1].evidence_ref, null);
  assert.equal(personal.windows[1].error_class, "Error");
  assert.ok(personal.windows[0].evidence_ref);
  assert.ok(personal.windows[2].evidence_ref);
  assert.ok(personal.balances[0].evidence_ref);
  assert.equal(fixture.counters.transactionReads, 5);
  assert.equal(fs.existsSync(path.join(root, "personal-moneytree-snapshot.json")), false);
});

test("Moneytree cache reuses a recent snapshot and never upgrades stale data", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-personal-cache-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const first = collectorFixture(root);
  const firstResult = await collectCfoProjection("2026-10-07", first.options);
  const cachePath = path.join(root, "personal-moneytree-snapshot.json");
  assert.equal(fs.statSync(cachePath).mode & 0o777, 0o600);

  const recent = collectorFixture(root);
  recent.options.now = new Date("2026-10-07T08:30:00.000Z");
  const recentResult = await collectCfoProjection("2026-10-07", recent.options);
  assert.deepEqual(recentResult.personal_moneytree, firstResult.personal_moneytree);
  assert.equal(recent.counters.accountReads, 0);
  assert.equal(recent.counters.transactionReads, 0);
  assert.equal(recentResult.personal_moneytree.freshness_status, "unknown");

  const nextDate = collectorFixture(root, { date: "2026-10-08" });
  nextDate.options.now = new Date("2026-10-07T08:30:00.000Z");
  const nextDateResult = await collectCfoProjection("2026-10-08", nextDate.options);
  assert.equal(nextDateResult.personal_moneytree.range_end, "2026-10-08");
  assert.equal(nextDate.counters.accountReads, 1);
  assert.equal(nextDate.counters.transactionReads, 5);

  const mismatchFailure = collectorFixture(root, { date: "2026-10-09" });
  mismatchFailure.options.now = new Date("2026-10-08T09:30:00.000Z");
  mismatchFailure.options.readAccounts = async () => { throw new Error("fixture Moneytree unavailable"); };
  const mismatchResult = await collectCfoProjection("2026-10-09", mismatchFailure.options);
  assert.equal(mismatchResult.personal_moneytree.status, "unavailable");
  assert.equal(mismatchResult.personal_moneytree.range_end, "2026-10-09");
  assert.deepEqual(mismatchResult.personal_moneytree.balances, []);

  const expired = collectorFixture(root, { date: "2026-10-08" });
  expired.options.now = new Date("2026-10-09T08:30:00.000Z");
  expired.options.readAccounts = async () => { throw new Error("fixture Moneytree unavailable"); };
  const staleResult = await collectCfoProjection("2026-10-08", expired.options);
  assert.equal(staleResult.personal_moneytree.status, "stale");
  assert.equal(staleResult.personal_moneytree.freshness_status, "stale");
  assert.equal(staleResult.personal_moneytree.refresh_windows.length, 5);
  assert.ok(staleResult.personal_moneytree.refresh_windows.every((window) => window.error_class === "Error"));
});

test("B7 pending retry reuses the frozen Moneytree report without recollecting", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-personal-b7-retry-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const fixture = collectorFixture(root);
  const messages = [];
  let collectCalls = 0;
  let notifyCalls = 0;
  const options = {
    stateDir: root,
    subjectId: "dais-personal-test",
    reportEmail: "owner@example.test",
    occurrenceId: "life-manager-cfo-hourly:personal-run-1",
    env: { LIFE_MANAGER_RELEASE_SHA: "a".repeat(40) },
    now: "2026-10-07T08:00:00.000Z",
    collect: async (date) => {
      collectCalls += 1;
      return collectCfoProjection(date, fixture.options);
    },
    notify: async (input) => {
      messages.push(input);
      notifyCalls += 1;
      return notifyCalls === 1
        ? { delivery: "pending", provider_message_id: null }
        : { delivery: "delivered", provider_message_id: "personal-report-receipt" };
    },
  };

  await assert.rejects(runResultCfo(options), /cfo_provider_receipt_missing/);
  assert.match(messages[0].message, /個人 Moneytree/);
  const retried = await runResultCfo({
    ...options, occurrenceId: "life-manager-cfo-hourly:personal-run-2", now: "2026-10-07T09:00:00.000Z",
  });

  assert.equal(retried.status, "sent");
  assert.equal(messages.length, 2);
  assert.equal(messages[1].message, messages[0].message);
  assert.equal(collectCalls, 1);
  assert.equal(fixture.counters.accountReads, 1);
  assert.equal(fixture.counters.transactionReads, 5);
});

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

  assert.deepEqual(result, {
    status: "quiet", reason: "no_verified_financial_records",
    reportingDate: "2026-09-07", recordCount: 1, delivered: false,
    ingestion: { observed: 0, created: 0, sources: {} },
  });
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
