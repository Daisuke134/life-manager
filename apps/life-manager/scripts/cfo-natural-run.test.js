"use strict";

const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { financialRecordId } = require("../../../runtime/contracts/common-record.cjs");
const { createJsonlFinancialRecordStore } = require("../lib/financial-record-store.js");
const { MONEYTREE_OBSERVATION } = require("../lib/moneytree-local-adapter.js");
const { runHourlyCfo } = require("./cfo-hourly-local.js");

function verifiedBalance() {
  const sourceRef = `moneytree:${"c".repeat(64)}`;
  const externalRef = `moneytree:${createHash("sha256").update(`dais-local\n${sourceRef}`).digest("hex")}`;
  return {
    schema_version: 1, record_type: "financial_record", record_id: financialRecordId("dais-local", "moneytree:legacy"),
    subject_id: "dais-local", scope: "personal", kind: "asset_balance", direction: "snapshot",
    amount_minor: 504302, currency: "JPY", occurred_at: "2026-08-26T03:09:37.000Z",
    recorded_at: "2026-08-26T03:09:37.000Z", idempotency_key: "moneytree:legacy",
    source: { provider: "moneytree", source_type: "moneytree", external_ref: externalRef },
    verification: { status: "verified", observed_at: "2026-08-26T03:09:37.000Z", evidence_refs: ["moneytree://legacy"] },
  };
}

function observed(records, observation) {
  Object.defineProperty(records, MONEYTREE_OBSERVATION, { value: observation });
  return records;
}

test("natural-run fixture proves stale cash, source gaps, cost unknown, delivery, and replay-zero", async (t) => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cfo-natural-run-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({ directoryPath: path.join(stateDir, "records") });
  await store.append(verifiedBalance());
  const partialObservation = (tool, coverage) => ({
    provider: "moneytree", mcp_server: "codex_apps", tool,
    retrieved_at: "2026-10-02T07:00:00.000Z", payload_sha256: (tool.endsWith("accounts") ? "a" : "b").repeat(64),
    source_status: "partial", source_reason: tool.endsWith("transactions") ? "transaction_completeness_unknown" : "source_freshness_unknown",
    source_updated_at: null, transaction_coverage: coverage,
    requested_start: tool.endsWith("transactions") ? "2026-10-01" : null,
    requested_end: tool.endsWith("transactions") ? "2026-10-02" : null,
  });
  const messages = [];
  const options = {
    stateDir, subjectId: "dais-local", store, now: "2026-10-02T07:00:00.000Z", reportCadence: "daily",
    readMoneytreeAccounts: async () => observed([{
      id: "moneytree:current", source: "moneytree", source_ref: `moneytree:${"c".repeat(64)}`,
      name: "Moneytree account", kind: "savings", balance_jpy: 504302, observed_at: "2026-10-02T07:00:00.000Z",
    }], partialObservation("moneytree.show-accounts", "not_applicable")),
    readMoneytreeTransactions: async () => observed([], partialObservation("moneytree.show-transactions", "unknown")),
    readBusinessReadback: async () => ({
      status: "partial", observedAt: "2026-10-03T00:00:00.000Z", sourceReceiptRefs: [`loop-pnl://sha256/${"d".repeat(64)}`],
      coverageGaps: [{ product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "source_unconnected" }],
      businessSourceCoverage: [{ source: "loop-pnl", state: "partial", observedAt: "2026-10-03T00:00:00.000Z", receiptCount: 1, gapReason: "source_unconnected" }],
      table: { reporting_date: "2026-10-02" },
    }),
    readGoogleBilling: async () => ({ status: "unknown", rows: [], receiptRef: null, totals: null, observedAt: "2026-10-02T07:00:00.000Z" }),
    providerBudget: { state: "degraded", totalUsd: 10, unknownCount: 1, reasons: ["unknown_cost"] },
    notify: async ({ message }) => { messages.push(message); return { delivery: "delivered", provider_message_id: "natural-1" }; },
  };
  const first = await runHourlyCfo(options);
  const replay = await runHourlyCfo(options);
  assert.equal(first.status, "sent");
  assert.equal(replay.status, "quiet");
  assert.equal(messages.length, 1);
  assert.deepEqual(first.report.personal.staleAssets, [{ currency: "JPY", amountMinor: 504302 }]);
  assert.equal(first.report.personal.assets.length, 0);
  assert.equal(first.report.businessSourceCoverage[0].state, "partial");
  assert.equal(first.report.providerCostSettlement.status, "unknown");
  assert.equal(first.report.providerBudget.state, "degraded");
  assert.match(messages[0], /前回観測残高（stale）/);
  assert.match(messages[0], /moneytree:partial/);
  assert.match(messages[0], /Google請求: 未確認/);
  assert.match(messages[0], /Provider予算: degraded/);
  assert.match(first.digest, /^[a-f0-9]{64}$/);
});
