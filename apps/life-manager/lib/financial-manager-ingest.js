"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const moneytree = require("./moneytree-local-adapter.js");
const {
  buildAgentEconomyEconomicSourceBundle,
} = require("./agent-economy-economic-source.js");
const { buildMoneytreeObservation } = require("./moneytree-observation-store.js");
const { buildEconomicSourceCoverage } = require("./economic-source-contract.js");
const { readProductLoopCatalog } = require("./product-onboarding.js");

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
  let agentReceipts = [];
  let agentRevenueRecords = [];
  let agentRevenueReadState = "not_configured";

  try {
    const readAccounts = options.readMoneytreeAccounts || moneytree.readAccounts;
    const readTransactions = options.readMoneytreeTransactions || moneytree.readTransactions;
    const startDate = `${new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit",
    }).format(now)}-01`;
    const endDate = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(now);
    const snapshot = await readMoneytreeSnapshot(
      readAccounts, readTransactions, { startDate, endDate },
    );
    const [accounts, transactions] = snapshot;
    let evidenceRef = null;
    if (snapshot.accountRead && snapshot.transactionRead && options.moneytreeEvidenceStore) {
      const observation = buildMoneytreeObservation({
        accounts, transactions, accountRead: snapshot.accountRead,
        transactionRead: snapshot.transactionRead,
        observedAt: [snapshot.accountRead.retrieved_at, snapshot.transactionRead.retrieved_at]
          .sort().at(-1),
      });
      evidenceRef = options.moneytreeEvidenceStore.record(observation);
      snapshot.evidenceObservedAt = observation.document.observed_at;
    }
    records.push(
      ...accounts.map((row) => moneytree.accountToFinancialRecord(
        row, { subjectId, recordedAt, evidenceRef, evidenceObservedAt: snapshot.evidenceObservedAt },
      )),
      ...transactions.map((row) => moneytree.transactionToFinancialRecord(
        row, { subjectId, recordedAt },
      )),
    );
    sources.moneytree = evidenceRef ? "observed_verified" : "observed_unverified";
  } catch {
    sources.moneytree = "unavailable";
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
    }
  } catch {
    agentReceipts = [];
    agentRevenueRecords = [];
    agentRevenueReadState = "unavailable";
    sources.agentEconomy = "unavailable";
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
    }
  } catch {
    sources.marketplace = "unavailable";
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
    observed: records.length, created, sources, economicSourceCoverage,
    economicFunnelObservations: agentEconomySources.funnelObservations,
  };
}

module.exports = { ingestFinancialRecords, readJsonl, readMoneytreeSnapshot, splitPaths };
