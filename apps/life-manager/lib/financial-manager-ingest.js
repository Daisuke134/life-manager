"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const moneytree = require("./moneytree-local-adapter.js");
const {
  buildAgentEconomyEconomicSourceBundle,
} = require("./agent-economy-economic-source.js");
const { buildMoneytreeObservation } = require("./moneytree-observation-store.js");
const { readGoogleBillingCsv } = require("./google-billing-readback.js");
const { readProviderLanes: readProviderLanesFromSupabase } = require("./provider-lane-readback.js");
const { buildEconomicSourceCoverage } = require("./economic-source-contract.js");
const { readProductLoopCatalog } = require("./product-onboarding.js");
const { capafyRowsToFinancialRecords } = require("./financial-record-capafy.js");
const { mobileAppsRowsToFinancialRecords } = require("./financial-record-mobile-apps.js");

async function readJsonl(file) {
  if (!file) return [];
  const text = await fs.readFile(file, "utf8");
  return text.split("\n").filter(Boolean).map((line, index) => {
    try { return JSON.parse(line); }
    catch { throw new Error(`financial source JSONL invalid at ${file}:${index + 1}`); }
  });
}

function splitPaths(value) {
  return String(value || "").split(path.delimiter).map((item) => item.trim()).filter(Boolean);
}

function projectMarketplace(receipts, { subjectId, pythonBin, script }) {
  if (receipts.length === 0) return [];
  const result = spawnSync(pythonBin, [script, "--subject-id", subjectId], {
    input: JSON.stringify(receipts), encoding: "utf8", timeout: 30_000,
  });
  if (result.status !== 0) throw new Error("marketplace FinancialRecord projection failed");
  const projected = JSON.parse(String(result.stdout || ""));
  if (!Array.isArray(projected)) throw new Error("marketplace FinancialRecord projection invalid");
  return projected;
}

function moneytreeSourceFreshness(snapshot) {
  const reads = [snapshot && snapshot.accountRead, snapshot && snapshot.transactionRead].filter(Boolean);
  if (reads.length !== 2) {
    return { status: "partial", reason: "observation_provenance_missing", reads: [] };
  }
  const statuses = reads.map((read) => String(read.source_status || "unknown"));
  if (statuses.includes("stale")) {
    return { status: "stale", reason: reads.find((read) => read.source_status === "stale")?.source_reason || "source_stale", reads };
  }
  if (!statuses.every((status) => status === "fresh")) {
    return { status: "partial", reason: reads.find((read) => read.source_reason)?.source_reason || "source_completeness_unknown", reads };
  }
  return { status: "fresh", reason: null, reads };
}

function moneytreeDateWindow(now) {
  const endDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(now);
  const [year, month, day] = endDate.split("-").map(Number);
  const start = new Date(Date.UTC(year, month - 1, day));
  start.setUTCDate(start.getUTCDate() - 91);
  const startDate = start.toISOString().slice(0, 10);
  return { startDate, endDate };
}

async function readMoneytreeSnapshot(readAccounts, readTransactions, range) {
  let lastError;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      // Each connector call starts a Codex app-server. Launchd background jobs can starve when
      // two app-servers initialize together, so keep the authenticated reads strictly serial.
      // No records are returned or appended until the complete pair succeeds.
      const accountResult = await readAccounts();
      const transactionResult = await readTransactions({ ...range, limit: 1000 });
      const pair = [accountResult, transactionResult];
      Object.defineProperties(pair, {
        accountRead: { value: accountResult[moneytree.MONEYTREE_OBSERVATION] || null },
        transactionRead: { value: transactionResult[moneytree.MONEYTREE_OBSERVATION] || null },
      });
      return pair;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

async function ingestFinancialRecords(options) {
  const {
    store, subjectId, now, agentReceiptPaths = [], marketplaceReceiptPaths = [],
    pythonBin = "python3",
  } = options;
  if (!store || typeof store.append !== "function") throw new Error("FinancialRecord store required");
  const recordedAt = now.toISOString();
  const records = [];
  const sources = {};
  const sourceFreshness = {};
  let businessReadback = null;
  let businessSourceCoverage = [];
  let providerCostSettlement = null;
  let providerLanes = null;
  let providerLaneReadback = null;
  let agentReceipts = [];
  let agentRevenueRecords = [];
  let agentRevenueReadState = "not_configured";

  try {
    const readAccounts = options.readMoneytreeAccounts || moneytree.readAccounts;
    const readTransactions = options.readMoneytreeTransactions || moneytree.readTransactions;
    const { startDate, endDate } = moneytreeDateWindow(now);
    const snapshot = await readMoneytreeSnapshot(
      readAccounts, readTransactions, { startDate, endDate },
    );
    const [accounts, transactions] = snapshot;
    const moneytreeFreshness = moneytreeSourceFreshness(snapshot);
    let evidenceRef = null;
    if (moneytreeFreshness.status === "fresh" && options.moneytreeEvidenceStore) {
      const observation = buildMoneytreeObservation({
        accounts, transactions, accountRead: snapshot.accountRead,
        transactionRead: snapshot.transactionRead,
        observedAt: [snapshot.accountRead.retrieved_at, snapshot.transactionRead.retrieved_at]
          .sort().at(-1),
      });
      evidenceRef = options.moneytreeEvidenceStore.record(observation);
      const storedObservation = typeof options.moneytreeEvidenceStore.read === "function"
        ? options.moneytreeEvidenceStore.read(evidenceRef) : null;
      snapshot.evidenceObservedAt = storedObservation?.document?.observed_at
        || observation.document.observed_at;
    }
    records.push(
      ...accounts.map((row) => moneytree.accountToFinancialRecord(
        row, { subjectId, recordedAt, evidenceRef, evidenceObservedAt: snapshot.evidenceObservedAt,
          verificationStatus: moneytreeFreshness.status === "fresh" ? "unverified" : "stale" },
      )),
      ...transactions.map((row) => moneytree.transactionToFinancialRecord(
        row, { subjectId, recordedAt, evidenceRef, evidenceObservedAt: snapshot.evidenceObservedAt,
          verificationStatus: moneytreeFreshness.status === "fresh" ? "unverified" : "stale" },
      )),
    );
    sources.moneytree = evidenceRef ? "observed_verified"
      : moneytreeFreshness.status === "stale" ? "stale"
        : moneytreeFreshness.status === "partial" && (snapshot.accountRead || snapshot.transactionRead)
          ? "partial" : "observed_unverified";
    sourceFreshness.moneytree = moneytreeFreshness;
  } catch {
    sources.moneytree = "unavailable";
    sourceFreshness.moneytree = { status: "unavailable", reason: "connector_read_failed", reads: [] };
  }

  if (typeof options.readBusinessReadback === "function") {
    const reportingDate = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(now);
    try {
      businessReadback = await options.readBusinessReadback({
        reportingDate, pythonBin,
      });
      businessSourceCoverage = Array.isArray(businessReadback?.businessSourceCoverage)
        ? [...businessReadback.businessSourceCoverage] : [];
      const state = String(businessReadback?.status || "unavailable");
      sources.businessReadback = state === "fresh" ? "observed_verified"
        : state === "partial" ? "partial" : "unavailable";
      sourceFreshness.businessReadback = {
        status: state === "fresh" ? "fresh" : state === "partial" ? "partial" : "unavailable",
        reason: businessReadback?.coverageGaps?.[0]?.reason
          || (state === "fresh" ? null : state === "partial" ? "source_completeness_unknown" : "read_failed"),
        reads: businessSourceCoverage,
      };
    } catch {
      businessReadback = null;
      businessSourceCoverage = [];
      sources.businessReadback = "unavailable";
      sourceFreshness.businessReadback = { status: "unavailable", reason: "read_failed", reads: [] };
    }
  }

  if (typeof options.readGoogleBilling === "function" || options.googleBillingCsvPath) {
    const reportingDate = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(now);
    const invoiceMonth = options.googleBillingInvoiceMonth || reportingDate.slice(0, 7);
    try {
      const read = options.readGoogleBilling || (() => readGoogleBillingCsv(options.googleBillingCsvPath, {
        invoiceMonth, observedAt: recordedAt,
      }));
      providerCostSettlement = await read({
        invoiceMonth, observedAt: recordedAt,
      });
      const settled = providerCostSettlement?.status === "settled";
      sources.googleBilling = settled ? "observed_verified" : "unknown";
      sourceFreshness.googleBilling = {
        status: settled ? "fresh" : "unknown",
        reason: settled ? null : "billing_receipt_missing",
        reads: providerCostSettlement?.receiptRef ? [providerCostSettlement.receiptRef] : [],
      };
    } catch {
      providerCostSettlement = null;
      sources.googleBilling = "unavailable";
      sourceFreshness.googleBilling = { status: "unavailable", reason: "billing_read_failed", reads: [] };
    }
  }

  const laneReader = options.readProviderLanes
    || ((options.supaUrl || process.env.SUPABASE_URL)
      && (options.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY)
      ? ({ subjectId: laneSubjectId, reportingDate, nowMs }) => readProviderLanesFromSupabase({
        supaUrl: options.supaUrl || process.env.SUPABASE_URL,
        supaKey: options.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY,
        tenantId: laneSubjectId, reportingDate, nowMs,
        fetchImpl: options.fetchImpl || globalThis.fetch,
      }) : null);
  if (laneReader) {
    const reportingDate = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(now);
    try {
      providerLaneReadback = await laneReader({
        subjectId, reportingDate, nowMs: now.getTime(), observedAt: recordedAt,
      });
      providerLanes = providerLaneReadback?.lanes || null;
    } catch {
      providerLaneReadback = {
        schemaVersion: 1, status: "partial", reportingDate, observedAt: recordedAt,
        lanes: null, failures: ["provider_lane_readback_failed"],
      };
      providerLanes = null;
    }
  }

  try {
    const readAgentReceipts = options.readAgentReceipts
      || (agentReceiptPaths.length
        ? async () => (await Promise.all(agentReceiptPaths.map(readJsonl))).flat()
        : null);
    if (!readAgentReceipts) {
      sources.agentEconomy = "not_configured";
    } else {
      const receipts = await readAgentReceipts();
      if (!Array.isArray(receipts)) throw new Error("Agent Economy receipts invalid");
      const adapter = await import("../../../skills/agent-economy/lib/financial-record-adapter.mjs");
      agentReceipts = receipts;
      agentRevenueRecords = receipts.flatMap((receipt) => (
        adapter.revenueReceiptToFinancialRecords(receipt, { subjectId })
      ));
      records.push(...agentRevenueRecords);
      agentRevenueReadState = "observed";
      sources.agentEconomy = receipts.length ? "observed_verified" : "empty";
      businessSourceCoverage.push({
        source: "agent-economy", state: receipts.length ? "fresh" : "empty",
        observedAt: recordedAt, receiptCount: agentRevenueRecords.length,
        gapReason: receipts.length ? null : "source_empty",
      });
    }
  } catch {
    agentReceipts = [];
    agentRevenueRecords = [];
    agentRevenueReadState = "unavailable";
    sources.agentEconomy = "unavailable";
    businessSourceCoverage.push({
      source: "agent-economy", state: "unavailable", observedAt: recordedAt,
      receiptCount: 0, gapReason: "read_failed",
    });
  }

  try {
    const readMarketplaceReceipts = options.readMarketplaceReceipts
      || (marketplaceReceiptPaths.length
        ? async () => (await Promise.all(marketplaceReceiptPaths.map(readJsonl))).flat()
        : null);
    if (!readMarketplaceReceipts) {
      sources.marketplace = "not_configured";
    } else {
      const receipts = await readMarketplaceReceipts();
      const projector = options.projectMarketplaceReceipts || ((rows) => projectMarketplace(rows, {
        subjectId, pythonBin,
        script: path.resolve(__dirname, "../../../skills/_shared/marketplace-core/scripts/financial_record.py"),
      }));
      records.push(...await projector(receipts));
      sources.marketplace = receipts.length ? "observed_verified" : "empty";
      businessSourceCoverage.push({
        source: "marketplace", state: receipts.length ? "fresh" : "empty",
        observedAt: recordedAt, receiptCount: receipts.length,
        gapReason: receipts.length ? null : "source_empty",
      });
    }
  } catch {
    sources.marketplace = "unavailable";
    businessSourceCoverage.push({
      source: "marketplace", state: "unavailable", observedAt: recordedAt,
      receiptCount: 0, gapReason: "read_failed",
    });
  }

  try {
    const readCapafyAnalytics = options.readCapafyAnalytics
      || (options.capafyAnalyticsPath
        ? async () => JSON.parse(await fs.readFile(options.capafyAnalyticsPath, "utf8"))
        : null);
    if (!readCapafyAnalytics) {
      sources.capafy = "not_configured";
    } else {
      const analytics = await readCapafyAnalytics();
      const rows = (analytics && analytics.daily_revenue_trend_last_30d) || [];
      const capafyRecords = capafyRowsToFinancialRecords(rows, { subjectId, observedAt: recordedAt });
      records.push(...capafyRecords);
      sources.capafy = capafyRecords.length ? "observed_verified" : "empty";
      businessSourceCoverage.push({
        source: "capafy", state: capafyRecords.length ? "fresh" : "empty",
        observedAt: recordedAt, receiptCount: capafyRecords.length,
        gapReason: capafyRecords.length ? null : "source_empty",
      });
    }
  } catch {
    sources.capafy = "unavailable";
    businessSourceCoverage.push({
      source: "capafy", state: "unavailable", observedAt: recordedAt,
      receiptCount: 0, gapReason: "read_failed",
    });
  }

  try {
    const readMobileAppsRows = options.readMobileAppsRows
      || (options.mobileAppsBusinessOutcomesPath
        ? async () => readJsonl(options.mobileAppsBusinessOutcomesPath)
        : null);
    if (!readMobileAppsRows) {
      sources.mobileApps = "not_configured";
    } else {
      const rows = await readMobileAppsRows();
      const mobileAppsRecords = mobileAppsRowsToFinancialRecords(rows, { subjectId, observedAt: recordedAt });
      records.push(...mobileAppsRecords);
      sources.mobileApps = mobileAppsRecords.length ? "observed_verified" : "empty";
      businessSourceCoverage.push({
        source: "mobile-apps", state: mobileAppsRecords.length ? "fresh" : "empty",
        observedAt: recordedAt, receiptCount: mobileAppsRecords.length,
        gapReason: mobileAppsRecords.length ? null : "source_empty",
      });
    }
  } catch {
    sources.mobileApps = "unavailable";
    businessSourceCoverage.push({
      source: "mobile-apps", state: "unavailable", observedAt: recordedAt,
      receiptCount: 0, gapReason: "read_failed",
    });
  }

  let created = 0;
  for (const record of records) {
    const result = await store.append(record);
    if (result.created) created += 1;
  }
  let agentCostRecords = [];
  let agentCostReadState = "not_configured";
  try {
    const readAgentCosts = options.readAgentEconomyCostRecords
      || (typeof store.read === "function" ? () => store.read({ subjectId }) : null);
    if (readAgentCosts) {
      const rows = await readAgentCosts();
      if (!Array.isArray(rows)) throw new Error("Agent Economy cost records invalid");
      agentCostRecords = rows;
      agentCostReadState = "observed";
    }
  } catch {
    agentCostRecords = [];
    agentCostReadState = "unavailable";
  }
  const agentEconomySources = await buildAgentEconomyEconomicSourceBundle({
    subjectId, observedAt: recordedAt,
    revenueReadState: agentRevenueReadState,
    costReadState: agentCostReadState,
    receipts: agentReceipts,
    revenueRecords: agentRevenueRecords,
    costRecords: agentCostRecords,
  });
  const suppliedObservations = options.readEconomicSourceObservations
    ? await options.readEconomicSourceObservations()
    : (options.economicSourceObservations || []);
  const suppliedKeys = new Set(suppliedObservations.map((observation) => (
    `${observation.product_loop_id}\n${observation.source_kind}`
  )));
  const observations = [
    ...suppliedObservations,
    ...agentEconomySources.sourceObservations.filter((observation) => (
      !suppliedKeys.has(`${observation.product_loop_id}\n${observation.source_kind}`)
    )),
  ];
  const catalogLoops = options.productLoops || readProductLoopCatalog(options.catalogFile).loops;
  const economicSourceCoverage = buildEconomicSourceCoverage({
    catalogLoops, subjectId, observations,
  });
  return {
    observed: records.length, created, sources, sourceFreshness,
    businessReadback, businessSourceCoverage, providerCostSettlement, providerLanes, providerLaneReadback,
    providerBudget: options.providerBudget || null, economicSourceCoverage,
    economicFunnelObservations: agentEconomySources.funnelObservations,
  };
}

module.exports = {
  ingestFinancialRecords, readJsonl, readMoneytreeSnapshot, splitPaths, moneytreeDateWindow, moneytreeSourceFreshness,
};
