"use strict";

const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createJsonlFinancialRecordStore } = require("../lib/financial-record-store.js");
const moneytree = require("../lib/moneytree-local-adapter.js");
const {
  buildMoneytreeObservation, createMoneytreeObservationStore,
} = require("../lib/moneytree-observation-store.js");
const { ingestFinancialRecords, splitPaths } = require("../lib/financial-manager-ingest.js");
const {
  runFinancialManager,
} = require("../lib/financial-manager-runtime.js");
const { renderFinancialManagerTelegram } = require("../lib/financial-manager-report.js");
const { notifyCfoReport, reportDestination } = require("../lib/cfo-report-delivery.js");

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function reportingDate(now) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(now);
}

function agentReceiptPathsFromEnv(env) {
  const agentStateRoot = env.LM_AGENT_ECONOMY_STATE_ROOT
    || path.join(os.homedir(), ".local/state/life-manager/agent-economy");
  const defaultJournal = path.join(agentStateRoot, "revenue-receipts.jsonl");
  return splitPaths(
    env.LM_CFO_AGENT_ECONOMY_RECEIPTS || env.REVENUE_RECEIPT_JOURNAL || defaultJournal,
  );
}

function lifeManagerStateRoot(env) {
  return env.LIFE_MANAGER_STATE_HOME
    || path.join(os.homedir(), ".local/state/life-manager");
}

function capafyAnalyticsPathFromEnv(env) {
  return env.LM_CFO_CAPAFY_ANALYTICS
    || path.join(lifeManagerStateRoot(env), "state/capafy-skill-analytics.json");
}

function mobileAppsBusinessOutcomesPathFromEnv(env) {
  return env.LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES
    || path.join(lifeManagerStateRoot(env), "marketing-metrics-daily/state/business-outcomes.jsonl");
}

function affiliateReadbackPathFromEnv(env) {
  return env.LM_CFO_AFFILIATE_READBACK
    || env.LM_CFO_AFFILIATE_LEDGER
    || path.join(lifeManagerStateRoot(env), "affiliate/provider-reports/partnerstack/latest.json");
}

function readSnapshot(file) {
  try {
    const value = JSON.parse(fs.readFileSync(file, "utf8"));
    return value && value.schemaVersion === 1 && /^[a-f0-9]{64}$/.test(value.digest)
      ? value : null;
  }
  catch (error) {
    if (error && error.code === "ENOENT") return null;
    return null;
  }
}

function writeSnapshot(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  fs.chmodSync(path.dirname(file), 0o700);
  const temporary = `${file}.${crypto.randomUUID()}.tmp`;
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, `${JSON.stringify(value)}\n`);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.renameSync(temporary, file);
    fs.chmodSync(file, 0o600);
    const directory = fs.openSync(path.dirname(file), "r");
    try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    try { fs.unlinkSync(temporary); } catch (error) {
      if (!error || error.code !== "ENOENT") throw error;
    }
  }
}

const PERSONAL_CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const MONEYTREE_TRANSACTION_LIMIT = 1000;
const CASH_MOVEMENT_CATEGORIES = new Set(["振替", "カード返済", "ATM引き出し"]);

function isoDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)
    || new Date(`${value}T00:00:00.000Z`).toISOString().slice(0, 10) !== value) {
    throw new Error("CFO report date invalid");
  }
  return value;
}

function shiftMonths(value, amount) {
  const [year, month, day] = isoDate(value).split("-").map(Number);
  const first = new Date(Date.UTC(year, month - 1 + amount, 1));
  const lastDay = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
  first.setUTCDate(Math.min(day, lastDay));
  return first.toISOString().slice(0, 10);
}

function shiftDays(value, amount) {
  const date = new Date(`${isoDate(value)}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

function moneytreeWindows(reportDate) {
  const windows = [];
  let windowStart = shiftMonths(reportDate, -12);
  while (windowStart <= reportDate) {
    const maxInclusiveEnd = shiftDays(shiftMonths(windowStart, 3), -1);
    const windowEnd = maxInclusiveEnd < reportDate ? maxInclusiveEnd : reportDate;
    windows.push({ startDate: windowStart, endDate: windowEnd });
    windowStart = shiftDays(windowEnd, 1);
  }
  return windows;
}

function readPersonalCache(file, now, reportDate) {
  try {
    const cached = JSON.parse(fs.readFileSync(file, "utf8"));
    if (cached?.schema_version !== 1 || !cached.personal_moneytree
      || cached.personal_moneytree.owner !== "dais_personal") return null;
    if (cached.personal_moneytree.range_start !== shiftMonths(reportDate, -12)
      || cached.personal_moneytree.range_end !== reportDate) return null;
    if (typeof cached.cached_at !== "string") return null;
    const cachedAt = Date.parse(cached.cached_at);
    if (!Number.isFinite(cachedAt) || new Date(cachedAt).toISOString() !== cached.cached_at) return null;
    const age = now.getTime() - cachedAt;
    if (!Number.isFinite(age) || age < 0) return null;
    return {
      personal: cached.personal_moneytree,
      fresh: age < PERSONAL_CACHE_TTL_MS,
    };
  } catch {
    return null;
  }
}

function unavailablePersonal(date, status = "unavailable") {
  const [rangeStart, rangeEnd] = [shiftMonths(date, -12), date];
  return {
    schema_version: 1, owner: "dais_personal", status,
    observed_at: null, provider_sync_at: null,
    freshness_status: status === "stale" ? "stale" : "unknown",
    range_start: rangeStart, range_end: rangeEnd, windows: [], balances: [],
    latest_transaction_date: null, monthly: [], recurring_charge_candidates: [],
  };
}

function addObservedAmount(target, field, amount) {
  const next = (target[field] ?? 0) + amount;
  if (!Number.isSafeInteger(next)) throw new Error("Moneytree total is unsafe");
  target[field] = next;
}

function normalizedMerchant(value) {
  if (typeof value !== "string") return null;
  const label = value.normalize("NFKC").replace(/\d{7,}/g, "[番号]").replace(/\s+/g, " ").trim();
  return label && !label.includes("@") ? label.slice(0, 80) : null;
}

function monthsInRange(startDate, endDate) {
  const months = [];
  let cursor = `${startDate.slice(0, 7)}-01`;
  const last = `${endDate.slice(0, 7)}-01`;
  while (cursor <= last) {
    months.push(cursor.slice(0, 7));
    const [year, month] = cursor.split("-").map(Number);
    cursor = new Date(Date.UTC(year, month, 1)).toISOString().slice(0, 10);
  }
  return months;
}

function monthOverlapsWindow(month, window) {
  const [year, monthNumber] = month.split("-").map(Number);
  const first = `${month}-01`;
  const last = new Date(Date.UTC(year, monthNumber, 0)).toISOString().slice(0, 10);
  return window.startDate <= last && window.endDate >= first;
}

function projectPersonalTransactions(accounts, windowsWithRows, reportDate) {
  const unique = new Map();
  for (const item of windowsWithRows) {
    for (const transaction of item.transactions) {
      if (!transaction || typeof transaction.id !== "string" || !transaction.id
        || !Number.isSafeInteger(transaction.amount_jpy)
        || !Number.isFinite(Date.parse(transaction.occurred_at))) {
        throw new Error("Moneytree normalized transaction invalid");
      }
      if (!unique.has(transaction.id)) {
        unique.set(transaction.id, { transaction, evidence_refs: new Set(), window_statuses: new Set() });
      }
      const entry = unique.get(transaction.id);
      if (item.evidence_ref) entry.evidence_refs.add(item.evidence_ref);
      entry.window_statuses.add(item.coverage_status);
    }
  }

  const months = new Map(monthsInRange(shiftMonths(reportDate, -12), reportDate).map((month) => {
    const overlappingWindows = windowsWithRows.filter((window) => monthOverlapsWindow(month, window));
    return [month, {
      month, income_jpy: null, expense_jpy: null, cash_movement_jpy: null,
      categoryMap: new Map(), hasTransactions: false,
      window_statuses: overlappingWindows.map((window) => window.coverage_status),
      evidence_refs: new Set(overlappingWindows.map((window) => window.evidence_ref).filter(Boolean)),
    }];
  }));
  const recurring = new Map();
  let latestTransactionDate = null;
  for (const { transaction, evidence_refs: transactionEvidenceRefs, window_statuses: transactionStatuses } of unique.values()) {
    const date = new Date(transaction.occurred_at).toISOString().slice(0, 10);
    if (date < shiftMonths(reportDate, -12) || date > reportDate) continue;
    if (!latestTransactionDate || date > latestTransactionDate) latestTransactionDate = date;
    const month = date.slice(0, 7);
    const summary = months.get(month);
    if (!summary) throw new Error("Moneytree transaction is outside its requested range");
    summary.hasTransactions = true;
    for (const receipt of transactionEvidenceRefs) summary.evidence_refs.add(receipt);
    summary.window_statuses.push(...transactionStatuses);
    const category = String(transaction.category || "未分類").trim() || "未分類";
    if (!summary.categoryMap.has(category)) summary.categoryMap.set(category, {
      category, income_jpy: null, expense_jpy: null, cash_movement_jpy: null,
    });
    const categorySummary = summary.categoryMap.get(category);
    const transfer = Boolean(transaction.transfer_id) || CASH_MOVEMENT_CATEGORIES.has(category);
    if (transfer) {
      addObservedAmount(summary, "cash_movement_jpy", transaction.amount_jpy);
      addObservedAmount(categorySummary, "cash_movement_jpy", transaction.amount_jpy);
    } else if (transaction.amount_jpy >= 0) {
      addObservedAmount(summary, "income_jpy", transaction.amount_jpy);
      addObservedAmount(categorySummary, "income_jpy", transaction.amount_jpy);
    } else {
      const amount = Math.abs(transaction.amount_jpy);
      addObservedAmount(summary, "expense_jpy", amount);
      addObservedAmount(categorySummary, "expense_jpy", amount);
      const merchant = normalizedMerchant(transaction.merchant);
      if (merchant) {
        if (!recurring.has(merchant)) recurring.set(merchant, {
          months: new Set(), total_observed_jpy: 0, evidence_refs: new Set(),
        });
        const candidate = recurring.get(merchant);
        candidate.months.add(month);
        candidate.total_observed_jpy += amount;
        for (const receipt of transactionEvidenceRefs) candidate.evidence_refs.add(receipt);
        if (!Number.isSafeInteger(candidate.total_observed_jpy)) throw new Error("Moneytree recurring total is unsafe");
      }
    }
  }

  const accountEvidenceRef = windowsWithRows.find((window) => window.evidence_ref)?.evidence_ref || null;
  const balances = accountEvidenceRef ? accounts.map((account) => {
    if (typeof account.name !== "string" || !account.name.trim() || !Number.isSafeInteger(account.balance_jpy)) {
      throw new Error("Moneytree normalized account invalid");
    }
    return {
      institution: account.name.trim(), balance_jpy: account.balance_jpy,
      observed_at: account.observed_at, evidence_ref: accountEvidenceRef,
    };
  }) : [];
  const hasReceipt = windowsWithRows.some((window) => Boolean(window.evidence_ref));
  const allComplete = windowsWithRows.length > 0
    && windowsWithRows.every((window) => window.coverage_status === "complete");
  return {
    schema_version: 1,
    owner: "dais_personal",
    status: allComplete ? "observed" : hasReceipt ? "partial" : "unavailable",
    observed_at: windowsWithRows.map((item) => item.observed_at).filter(Boolean).sort().at(-1) || null,
    provider_sync_at: null,
    freshness_status: "unknown",
    range_start: shiftMonths(reportDate, -12),
    range_end: reportDate,
    account_evidence_ref: accountEvidenceRef,
    windows: windowsWithRows.map(({ startDate, endDate, provider_total_count, returned_count, limit, coverage_status, evidence_ref, error_class, range_mismatch_count }) => ({
      query_start_date: startDate, query_end_date: endDate,
      provider_total_count, returned_count, limit, coverage_status, evidence_ref, error_class: error_class || null,
      range_mismatch_count: Number.isSafeInteger(range_mismatch_count) ? range_mismatch_count : null,
    })),
    balances,
    latest_transaction_date: latestTransactionDate,
    monthly: [...months.values()].sort((a, b) => a.month.localeCompare(b.month)).map((month) => {
      const { categoryMap, hasTransactions, window_statuses: statuses, evidence_refs: refs, ...summary } = month;
      const status = !hasTransactions ? "unknown"
        : statuses.length && statuses.every((value) => value === "complete") ? "observed" : "partial";
      return {
        ...summary,
        coverage_status: status,
        evidence_refs: [...refs].sort(),
        categories: [...categoryMap.values()].sort((a, b) => a.category.localeCompare(b.category)),
      };
    }),
    recurring_charge_candidates: [...recurring.entries()]
      .filter(([, candidate]) => candidate.months.size >= 2)
      .map(([merchant, candidate]) => ({
        merchant, month_count: candidate.months.size, total_observed_jpy: candidate.total_observed_jpy,
        evidence_refs: [...candidate.evidence_refs].sort(),
      }))
      .sort((a, b) => a.merchant.localeCompare(b.merchant)),
  };
}

async function readPersonalMoneytree(date, options, now, stateDir) {
  const cacheFile = path.join(stateDir, "personal-moneytree-snapshot.json");
  const cached = readPersonalCache(cacheFile, now, date);
  if (cached?.fresh) return cached.personal;

  try {
    const readAccounts = options.readAccounts || moneytree.readAccounts;
    const readTransactions = options.readTransactions || moneytree.readTransactions;
    const accounts = await readAccounts(options.moneytreeOptions || {});
    if (!Array.isArray(accounts)) throw new Error("Moneytree account read invalid");
    const accountRead = accounts[moneytree.MONEYTREE_OBSERVATION];
    const evidenceStore = options.moneytreeEvidenceStore || createMoneytreeObservationStore({
      directoryPath: path.join(stateDir, "evidence", "moneytree"),
    });
    const windowsWithRows = [];
    for (const { startDate, endDate } of moneytreeWindows(date)) {
      try {
        const transactions = await readTransactions({
          startDate, endDate, limit: MONEYTREE_TRANSACTION_LIMIT, ...(options.moneytreeOptions || {}),
        });
        if (!Array.isArray(transactions)) throw new Error("Moneytree transaction read invalid");
        const transactionRead = transactions[moneytree.MONEYTREE_OBSERVATION];
        if (transactionRead?.query_start_date !== startDate || transactionRead?.query_end_date !== endDate
          || transactionRead?.returned_count !== transactions.length) {
          throw new Error("Moneytree transaction coverage metadata invalid");
        }
        for (const transaction of transactions) {
          if (!transaction || typeof transaction.id !== "string" || !transaction.id
            || !Number.isSafeInteger(transaction.amount_jpy)
            || !Number.isFinite(Date.parse(transaction.occurred_at))) {
            throw new Error("Moneytree normalized transaction invalid");
          }
        }
        const rangeStart = shiftMonths(date, -12);
        let rangeMismatchCount = 0;
        const inRangeTransactions = transactions.filter((transaction) => {
          const transactionDate = new Date(transaction.occurred_at).toISOString().slice(0, 10);
          const inReportPeriod = transactionDate >= rangeStart && transactionDate <= date;
          const inRequestedWindow = transactionDate >= startDate && transactionDate <= endDate;
          if (!inReportPeriod || !inRequestedWindow) rangeMismatchCount += 1;
          return inReportPeriod && inRequestedWindow;
        });
        const observedAt = [accountRead?.retrieved_at, transactionRead?.retrieved_at]
          .filter((value) => Number.isFinite(Date.parse(value))).sort().at(-1);
        const receipt = buildMoneytreeObservation({
          accounts, transactions, accountRead, transactionRead, observedAt,
        });
        const evidenceRef = evidenceStore.record(receipt);
        const providerTotal = transactionRead.provider_total_count;
        const limit = transactionRead.limit;
        const complete = Number.isSafeInteger(providerTotal) && providerTotal === transactions.length
          && Number.isSafeInteger(limit) && transactions.length < limit;
        const coverageStatus = !Number.isSafeInteger(providerTotal) ? "unknown"
          : providerTotal === 0 && transactions.length === 0 ? "unknown"
            : complete && rangeMismatchCount === 0 ? "complete" : "partial";
        windowsWithRows.push({
          startDate, endDate,
          provider_total_count: Number.isSafeInteger(providerTotal) ? providerTotal : null,
          returned_count: transactions.length,
          limit: Number.isSafeInteger(limit) ? limit : null,
          coverage_status: coverageStatus,
          evidence_ref: evidenceRef,
          observed_at: observedAt,
          error_class: null,
          range_mismatch_count: rangeMismatchCount,
          transactions: inRangeTransactions,
        });
      } catch (error) {
        windowsWithRows.push({
          startDate, endDate, provider_total_count: null, returned_count: null,
          limit: MONEYTREE_TRANSACTION_LIMIT, coverage_status: "unknown", evidence_ref: null,
          observed_at: null, error_class: error?.name || "Error", range_mismatch_count: null, transactions: [],
        });
      }
    }
    const personal = projectPersonalTransactions(accounts, windowsWithRows, date);
    const cacheable = windowsWithRows.every((window) => Boolean(window.evidence_ref));
    if (cacheable) {
      try {
        writeSnapshot(cacheFile, { schema_version: 1, cached_at: now.toISOString(), personal_moneytree: personal });
      } catch (error) {
        personal.cache_status = "write_failed";
        personal.cache_error_class = error?.name || "Error";
      }
    }
    if (!windowsWithRows.some((window) => window.evidence_ref) && cached?.personal) {
      return {
        ...cached.personal, status: "stale", freshness_status: "stale",
        refresh_windows: personal.windows,
      };
    }
    return personal;
  } catch (error) {
    if (cached?.personal) return {
      ...cached.personal, status: "stale", freshness_status: "stale",
      refresh_windows: moneytreeWindows(date).map(({ startDate, endDate }) => ({
        query_start_date: startDate, query_end_date: endDate,
        coverage_status: "unknown", evidence_ref: null, error_class: error?.name || "Error",
      })),
    };
    return unavailablePersonal(date);
  }
}

function collectBusinessTable(date, options) {
  const script = options.loopPnlScript || path.resolve(__dirname, "../../../skills/cfo/loop_pnl.py");
  const args = [script, "--date", date, "--json"];
  if (options.snapshotAt) args.push("--snapshot-at", String(options.snapshotAt));
  if (options.trailingStart) args.push("--trailing-start", String(options.trailingStart));
  const collectorEnv = { ...(options.env || process.env) };
  if (options.capafyAnalyticsPath) collectorEnv.LM_CFO_CAPAFY_ANALYTICS = String(options.capafyAnalyticsPath);
  if (options.mobileAppsBusinessOutcomesPath) collectorEnv.LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES = String(options.mobileAppsBusinessOutcomesPath);
  if (options.affiliateReadbackPath) collectorEnv.LM_CFO_AFFILIATE_READBACK = String(options.affiliateReadbackPath);
  if (Array.isArray(options.agentReceiptPaths) && options.agentReceiptPaths.length) {
    collectorEnv.LM_CFO_AGENT_ECONOMY_RECEIPTS = options.agentReceiptPaths.join(path.delimiter);
  }
  if (Array.isArray(options.marketplaceReceiptPaths) && options.marketplaceReceiptPaths.length) {
    collectorEnv.LM_CFO_MARKETPLACE_RECEIPTS = options.marketplaceReceiptPaths.join(path.delimiter);
  }
  const result = spawnSync(options.pythonBin || "python3", args, {
    encoding: "utf8", timeout: 120_000, env: collectorEnv,
  });
  if (result.error || result.status !== 0) throw new Error("CFO business source read failed");
  const table = JSON.parse(result.stdout);
  if (!table || typeof table !== "object" || Array.isArray(table) || table.reporting_date !== date) {
    throw new Error("CFO business source date mismatch");
  }
  return table;
}

async function collectCfoProjection(date, options = {}) {
  date = isoDate(date);
  if (typeof options.stateDir !== "string" || !options.stateDir.trim()) throw new Error("CFO state directory invalid");
  const stateDir = path.resolve(options.stateDir);
  if (stateDir === path.parse(stateDir).root) throw new Error("CFO state directory invalid");
  const now = new Date(options.now || new Date());
  if (!Number.isFinite(now.getTime())) throw new Error("CFO clock invalid");
  const business = collectBusinessTable(date, options);
  const personal = await readPersonalMoneytree(date, options, now, stateDir);
  return { ...business, personal_moneytree: personal };
}

async function runHourlyCfo(options = {}) {
  const now = new Date(typeof options.now === "function" ? options.now() : (options.now || new Date()));
  if (!Number.isFinite(now.getTime())) throw new Error("CFO clock invalid");
  const date = reportingDate(now);
  if (typeof options.stateDir !== "string" || !options.stateDir.trim()) {
    throw new Error("CFO configuration invalid");
  }
  const stateDir = path.resolve(options.stateDir);
  const subjectId = String(options.subjectId || "").trim();
  if (!stateDir || stateDir === path.parse(stateDir).root || !ID.test(subjectId)) {
    throw new Error("CFO configuration invalid");
  }
  const store = options.store || createJsonlFinancialRecordStore({
    directoryPath: path.join(stateDir, "financial-records"),
  });
  const ingest = options.ingest || ingestFinancialRecords;
  const snapshotFile = path.join(stateDir, "last-delivered-snapshot.json");
  const destination = options.notify ? { channel: "injected", recipient: subjectId } : reportDestination(options);
  const recipientHash = crypto.createHash("sha256").update(destination.recipient).digest("hex");
  const cadence = options.reportCadence || "daily";
  if (!["hourly", "daily"].includes(cadence)) throw new Error("CFO cadence invalid");
  const periodKey = cadence === "hourly" ? `${date}:${now.toISOString().slice(11, 13)}` : date;
  const eventKey = `cfo:${subjectId}:${destination.channel}:${periodKey}`;
  const notify = options.notify || ((input) => notifyCfoReport(input, options));
  const pending = readSnapshot(snapshotFile);
  if (pending?.status === "pending" && pending.channel && (pending.channel !== destination.channel || pending.recipientHash !== recipientHash)) {
    return { status: "failed", reason: "cfo_pending_channel_changed", reportingDate: date, delivered: false };
  }
  if (pending?.status === "pending" && pending.reportingDate === date && pending.report) {
    if (destination.channel === "email" && now.getTime() - Date.parse(pending.createdAt) >= 23 * 60 * 60 * 1000) {
      return { status: "failed", reason: "cfo_email_idempotency_expired", reportingDate: date, delivered: false };
    }
    const delivery = await notify({ eventKey: pending.eventKey || eventKey,
      observedAt: now.toISOString(), message: renderFinancialManagerTelegram(pending.report) });
    if (delivery?.delivery !== "delivered" || !String(delivery.provider_message_id || "").trim()) {
      return { status: "failed", reason: "telegram_delivery_uncertain", reportingDate: date,
        recordCount: pending.report.verifiedRecordCount || 0, delivered: false };
    }
    writeSnapshot(snapshotFile, { ...pending, status: "delivered",
      delivery: { delivery: "delivered", provider_message_id: String(delivery.provider_message_id) },
      deliveredAt: now.toISOString() });
    const duplicate = Number(delivery.attempted) === 0;
    return { status: duplicate ? "quiet" : "sent", reason: duplicate ? "unchanged" : null,
      reportingDate: date, recordCount: pending.report.verifiedRecordCount || 0,
      delivered: !duplicate, providerMessageId: String(delivery.provider_message_id) };
  }
  const result = await runFinancialManager({
    subjectId, reportingDate: date, timezone: "Asia/Tokyo", now, store,
    ingest: () => ingest({
      store, subjectId, now,
      moneytreeEvidenceStore: options.moneytreeEvidenceStore || createMoneytreeObservationStore({
        directoryPath: path.join(stateDir, "evidence", "moneytree"),
      }),
      agentReceiptPaths: options.agentReceiptPaths || [],
      marketplaceReceiptPaths: options.marketplaceReceiptPaths || [],
      pythonBin: options.pythonBin || "python3",
      capafyAnalyticsPath: options.capafyAnalyticsPath,
      mobileAppsBusinessOutcomesPath: options.mobileAppsBusinessOutcomesPath,
    }),
    deliveryStore: {
      lookup: () => {
        const previous = readSnapshot(snapshotFile);
        const previousDate = previous && (previous.reportingDate || previous.report?.reportingDate);
        const samePeriod = previous?.periodKey ? previous.periodKey === periodKey : cadence === "daily";
        return previousDate === date && samePeriod && previous.status !== "pending" ? previous : null;
      },
      claim: async ({ digest, report, observedAt }) => {
        writeSnapshot(snapshotFile, { schemaVersion: 1, status: "pending", reportingDate: date,
          digest, report, periodKey, eventKey, channel: destination.channel, recipientHash, createdAt: observedAt });
        return { claimed: true };
      },
      markDelivered: ({ digest, report, delivery, observedAt }) => writeSnapshot(snapshotFile, {
        schemaVersion: 1, status: "delivered", digest, report,
        reportingDate: date, periodKey, eventKey, channel: destination.channel, recipientHash,
        delivery: { delivery: "delivered", provider_message_id: delivery.providerMessageId },
        deliveredAt: observedAt,
      }),
    },
    eventKey: () => eventKey,
    notify: async (input) => {
      const delivery = await notify(input);
      return {
        delivered: delivery && delivery.delivery === "delivered",
        providerMessageId: delivery && delivery.provider_message_id,
      };
    },
  });
  // Local callers consume the compact, stable boundary rather than report internals.
  const { report, digest, duplicate, ...publicResult } = result;
  return publicResult;
}

async function main(env = process.env) {
  const stateDir = env.CFO_STATE_DIR || env.LIFE_MANAGER_STATE_ROOT
    || path.join(os.homedir(), ".local/state/life-manager/life-manager-cfo-hourly");
  try {
    const { runResultCfo } = require("./cfo-result-local.js");
    const pythonBin = env.CFO_PYTHON_BIN || "python3";
    const agentReceiptPaths = agentReceiptPathsFromEnv(env);
    const marketplaceReceiptPaths = splitPaths(env.LM_CFO_MARKETPLACE_RECEIPTS);
    const capafyAnalyticsPath = capafyAnalyticsPathFromEnv(env);
    const mobileAppsBusinessOutcomesPath = mobileAppsBusinessOutcomesPathFromEnv(env);
    const affiliateReadbackPath = affiliateReadbackPathFromEnv(env);
    const result = await runResultCfo({
      stateDir,
      subjectId: env.LM_CFO_SUBJECT_ID || env.LM_CFO_UID || env.LM_UID,
      occurrenceId: env.LIFE_MANAGER_OCCURRENCE_ID,
      pythonBin,
      reportChannel: env.LM_CFO_REPORT_CHANNEL || "email",
      reportCadence: env.LM_CFO_REPORT_CADENCE || "hourly",
      reportEmail: env.LM_CFO_REPORT_EMAIL,
      resendKey: env.RESEND_API_KEY,
      database: env.CFO_TELEGRAM_OUTBOX || path.join(stateDir, "telegram-outbox.sqlite3"),
      chatId: env.TELEGRAM_ALERT_CHAT_ID || env.LM_CFO_TELEGRAM_CHAT_ID || env.LM_ADMIN_TELEGRAM_CHAT_ID,
      envFile: env.LIFE_MANAGER_ENV_FILE || path.join(os.homedir(), ".local/state/life-manager/.env"),
      agentReceiptPaths,
      marketplaceReceiptPaths,
      capafyAnalyticsPath,
      mobileAppsBusinessOutcomesPath,
      affiliateReadbackPath,
      collect: (date) => collectCfoProjection(date, {
        stateDir, pythonBin, env, agentReceiptPaths, marketplaceReceiptPaths,
        capafyAnalyticsPath, mobileAppsBusinessOutcomesPath, affiliateReadbackPath,
      }),
    });
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return ["sent", "quiet"].includes(result.status) ? 0 : 1;
  } catch {
    process.stdout.write(`${JSON.stringify({
      status: "failed", reason: "cfo_boundary_failed", reportingDate: null,
      recordCount: 0, delivered: false,
    })}\n`);
    return 1;
  }
}

if (require.main === module) main().then((code) => { process.exitCode = code; });

module.exports = {
  agentReceiptPathsFromEnv, capafyAnalyticsPathFromEnv, mobileAppsBusinessOutcomesPathFromEnv,
  affiliateReadbackPathFromEnv, collectCfoProjection,
  main, runHourlyCfo,
};
