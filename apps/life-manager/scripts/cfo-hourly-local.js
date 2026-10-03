"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createJsonlFinancialRecordStore } = require("../lib/financial-record-store.js");
const { createMoneytreeObservationStore } = require("../lib/moneytree-observation-store.js");
const { ingestFinancialRecords, splitPaths } = require("../lib/financial-manager-ingest.js");
const { readBusinessReadback } = require("../lib/financial-business-readback.js");
const {
  runFinancialManager,
} = require("../lib/financial-manager-runtime.js");
const { renderFinancialManagerTelegram } = require("../lib/financial-manager-report.js");
const { notifyCfoReport, reportDestination } = require("../lib/cfo-report-delivery.js");
const { evaluateCfoObservationPeriods } = require("../lib/cfo-observation-gate.js");

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

function businessReadbackEnv(options) {
  const sourceEnv = { ...(options.env || process.env) };
  if (options.affiliateReadbackPath) sourceEnv.LM_CFO_AFFILIATE_READBACK = String(options.affiliateReadbackPath);
  if (options.capafyAnalyticsPath) sourceEnv.LM_CFO_CAPAFY_ANALYTICS = String(options.capafyAnalyticsPath);
  if (options.mobileAppsBusinessOutcomesPath) {
    sourceEnv.LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES = String(options.mobileAppsBusinessOutcomesPath);
  }
  if (Array.isArray(options.agentReceiptPaths) && options.agentReceiptPaths.length) {
    sourceEnv.LM_CFO_AGENT_ECONOMY_RECEIPTS = options.agentReceiptPaths.join(path.delimiter);
  }
  if (Array.isArray(options.marketplaceReceiptPaths) && options.marketplaceReceiptPaths.length) {
    sourceEnv.LM_CFO_MARKETPLACE_RECEIPTS = options.marketplaceReceiptPaths.join(path.delimiter);
  }
  return sourceEnv;
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

function readObservationPeriods(file) {
  try {
    const value = JSON.parse(fs.readFileSync(file, "utf8"));
    return value && value.schemaVersion === 1 && Array.isArray(value.periods) ? value.periods : [];
  } catch (error) {
    if (error && error.code === "ENOENT") return [];
    return [];
  }
}

function recordObservationGate(stateDir, result, options) {
  if (!result || !result.report || !result.reportingDate) return null;
  const file = path.join(stateDir, "cfo-observation-periods.json");
  const previous = readObservationPeriods(file).filter((row) => row.reportingDate !== result.reportingDate);
  const deliveryStatus = result.status === "sent" ? "sent" : result.status === "quiet" ? "duplicate" : "failed";
  const providerMessageId = result.providerMessageId
    || result.duplicate?.providerMessageId
    || result.duplicate?.delivery?.provider_message_id
    || null;
  const row = {
    reportingDate: result.reportingDate,
    delivery: { status: deliveryStatus, providerMessageId },
    sourceFreshness: result.report.sourceFreshness || {},
    providerCostSettlement: result.report.providerCostSettlement || null,
    providerLanes: result.ingestion?.providerLanes || result.report.providerLanes || null,
  };
  const periods = [...previous, row].sort((a, b) => String(a.reportingDate).localeCompare(String(b.reportingDate)));
  writeSnapshot(file, { schemaVersion: 1, periods });
  return evaluateCfoObservationPeriods(periods, {
    requiredDays: Number(options.requiredObservationDays || 7),
    latestDate: result.reportingDate,
    requiredProviderLanes: options.requiredProviderLanes || ["poi", "transit", "geocoder"],
  });
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
    const retryResult = { status: duplicate ? "quiet" : "sent", reason: duplicate ? "unchanged" : null,
      reportingDate: date, recordCount: pending.report.verifiedRecordCount || 0,
      delivered: !duplicate, providerMessageId: String(delivery.provider_message_id),
      report: pending.report, digest: pending.digest,
      personal: pending.report.personal, business: pending.report.business,
      sourceFreshness: pending.report.sourceFreshness || {},
      economicSourceCoverage: pending.report.economicSourceCoverage || null,
      providerCostSettlement: pending.report.providerCostSettlement || null,
      providerBudget: pending.report.providerBudget || null,
    };
    retryResult.providerLanes = pending.report.providerLanes || null;
    retryResult.providerLaneReadback = pending.report.providerLaneReadback || null;
    retryResult.observationGate = recordObservationGate(stateDir, {
      ...retryResult,
      ingestion: { providerLanes: retryResult.providerLanes, providerLaneReadback: retryResult.providerLaneReadback },
    }, options);
    return retryResult;
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
      affiliateReadbackPath: options.affiliateReadbackPath,
      googleBillingCsvPath: options.googleBillingCsvPath,
      googleBillingInvoiceMonth: options.googleBillingInvoiceMonth,
      providerBudget: options.providerBudget,
      readMoneytreeAccounts: options.readMoneytreeAccounts,
      readMoneytreeTransactions: options.readMoneytreeTransactions,
      readProviderLanes: options.readProviderLanes,
      supaUrl: options.supaUrl,
      supaKey: options.supaKey,
      readGoogleBilling: options.readGoogleBilling,
      pythonBin: options.pythonBin || "python3",
      capafyAnalyticsPath: options.capafyAnalyticsPath,
      mobileAppsBusinessOutcomesPath: options.mobileAppsBusinessOutcomesPath,
      readBusinessReadback: options.readBusinessReadback || ((input) => readBusinessReadback({
        ...input, pythonBin: options.pythonBin || "python3", env: businessReadbackEnv(options),
      })),
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
  const { duplicate, ...publicResult } = result;
  publicResult.observationGate = recordObservationGate(stateDir, result, options);
  if (publicResult.report) {
    publicResult.personal = publicResult.report.personal;
    publicResult.business = publicResult.report.business;
    publicResult.sourceFreshness = publicResult.report.sourceFreshness || {};
    publicResult.economicSourceCoverage = publicResult.report.economicSourceCoverage || null;
    publicResult.providerCostSettlement = publicResult.report.providerCostSettlement || null;
    publicResult.providerLanes = publicResult.report.providerLanes || null;
    publicResult.providerLaneReadback = publicResult.ingestion?.providerLaneReadback || null;
    publicResult.providerBudget = publicResult.report.providerBudget || null;
  }
  return publicResult;
}

function selectCfoRunner(env = process.env, deps = {}) {
  if (env.LM_CFO_LEGACY_RESULT_COMPAT === "1") {
    return deps.runResultCfo || require("./cfo-result-local.js").runResultCfo;
  }
  return deps.runHourlyCfo || runHourlyCfo;
}

async function main(env = process.env, deps = {}) {
  const stateDir = env.CFO_STATE_DIR || env.LIFE_MANAGER_STATE_ROOT
    || path.join(os.homedir(), ".local/state/life-manager/life-manager-cfo-hourly");
  try {
    const runner = selectCfoRunner(env, deps);
    const result = await runner({
      stateDir,
      subjectId: env.LM_CFO_SUBJECT_ID || env.LM_CFO_UID || env.LM_UID,
      pythonBin: env.CFO_PYTHON_BIN || "python3",
      reportChannel: env.LM_CFO_REPORT_CHANNEL || "email",
      reportCadence: env.LM_CFO_REPORT_CADENCE || "daily",
      reportEmail: env.LM_CFO_REPORT_EMAIL,
      resendKey: env.RESEND_API_KEY,
      database: env.CFO_TELEGRAM_OUTBOX || path.join(stateDir, "telegram-outbox.sqlite3"),
      chatId: env.TELEGRAM_ALERT_CHAT_ID || env.LM_CFO_TELEGRAM_CHAT_ID || env.LM_ADMIN_TELEGRAM_CHAT_ID,
      envFile: env.LIFE_MANAGER_ENV_FILE || path.join(os.homedir(), ".local/state/life-manager/.env"),
      agentReceiptPaths: agentReceiptPathsFromEnv(env),
      marketplaceReceiptPaths: splitPaths(env.LM_CFO_MARKETPLACE_RECEIPTS),
      capafyAnalyticsPath: capafyAnalyticsPathFromEnv(env),
      mobileAppsBusinessOutcomesPath: mobileAppsBusinessOutcomesPathFromEnv(env),
      affiliateReadbackPath: affiliateReadbackPathFromEnv(env),
      googleBillingCsvPath: env.LM_CFO_GOOGLE_BILLING_CSV,
      googleBillingInvoiceMonth: env.LM_CFO_GOOGLE_BILLING_INVOICE_MONTH,
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
  affiliateReadbackPathFromEnv, businessReadbackEnv, selectCfoRunner,
  main, runHourlyCfo,
};
