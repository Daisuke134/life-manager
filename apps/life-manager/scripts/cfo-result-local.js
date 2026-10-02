"use strict";
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { notifyCfoReport, reportDestination } = require("../lib/cfo-report-delivery.js");
const { renderResultSummary } = require("../lib/cfo-result-summary.js");

const OCCURRENCE_ID = /^life-manager-cfo-hourly:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SHA256 = /^[a-f0-9]{64}$/;

function occurrenceId(value) {
  const text = String(value || "").trim();
  if (!OCCURRENCE_ID.test(text)) throw new Error("cfo_occurrence_invalid");
  return text;
}

function messageSha256(message) {
  return crypto.createHash("sha256").update(String(message), "utf8").digest("hex");
}

function validateStoredResult(value) {
  if (!value || typeof value !== "object") throw new Error("cfo_result_state_invalid");
  if (!["pending", "sent"].includes(value.status)) throw new Error("cfo_result_state_invalid");
  occurrenceId(value.occurrenceId);
  if (!SHA256.test(String(value.messageSha256 || ""))) throw new Error("cfo_result_state_invalid");
  if (value.status === "sent") {
    if (!value.providerMessageId || !["sent", "duplicate"].includes(value.resolutionKind)) {
      throw new Error("cfo_result_state_invalid");
    }
  }
  return value;
}

async function runResultCfo(options) {
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(options.subjectId || "")) throw new Error("cfo_subject_invalid");
  const subjectId = options.subjectId;
  const currentOccurrenceId = occurrenceId(options.occurrenceId);
  const now = new Date(options.now || new Date());
  if (!Number.isFinite(now.getTime())) throw new Error("cfo_clock_invalid");
  const date = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  const destination = reportDestination(options);
  const recipientHash = crypto.createHash("sha256").update(destination.recipient).digest("hex");
  const cadence = options.reportCadence || "hourly";
  if (!["hourly", "daily"].includes(cadence)) throw new Error("cfo_cadence_invalid");
  const periodKey = cadence === "hourly" ? `${date}:${now.toISOString().slice(11, 13)}` : date;
  const stateDir = path.resolve(options.stateDir);
  const file = path.join(stateDir, "last-result-report.json");
  fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });
  let previous;
  try { previous = JSON.parse(fs.readFileSync(file, "utf8")); } catch (error) {
    if (error.code !== "ENOENT") throw new Error("cfo_result_state_invalid");
  }
  if (previous) validateStoredResult(previous);
  if (previous?.status === "sent" && previous.subjectId !== subjectId) throw new Error("cfo_sent_subject_changed");
  const persist = value => {
    const temporary = `${file}.${crypto.randomUUID()}.tmp`;
    const fd = fs.openSync(temporary, "wx", 0o600);
    try { fs.writeFileSync(fd, JSON.stringify(value)); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(temporary, file);
    const directory = fs.openSync(stateDir, "r");
    try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
  };
  if (previous?.status === "sent" && previous.periodKey === periodKey) {
    if (!previous.providerMessageId) throw new Error("cfo_sent_provider_receipt_missing");
    persist({ ...previous, occurrenceId: currentOccurrenceId, resolutionKind: "duplicate" });
    return {
      status: "quiet", reason: "unchanged", reportingDate: date, delivered: false,
      providerMessageId: String(previous.providerMessageId), resolutionKind: "duplicate",
    };
  }
  let pending = previous?.status === "pending" ? previous : null;
  if (pending && pending.subjectId !== subjectId) throw new Error("cfo_pending_subject_changed");
  if (pending && (pending.channel !== destination.channel || pending.recipientHash !== recipientHash)) {
    throw new Error("cfo_pending_destination_changed");
  }
  if (pending && now.getTime() - Date.parse(pending.createdAt) >= 23 * 60 * 60 * 1000) {
    throw new Error("cfo_pending_receipt_requires_reconcile");
  }
  if (!pending) {
    let table;
    if (options.collect) table = await options.collect(date);
    else {
      const script = path.resolve(__dirname, "../../../skills/cfo/loop_pnl.py");
      const args = [script, "--date", date, "--json"];
      if (options.snapshotAt) args.push("--snapshot-at", String(options.snapshotAt));
      if (options.trailingStart) args.push("--trailing-start", String(options.trailingStart));
      const sourceEnv = { ...(options.env || process.env) };
      if (options.capafyAnalyticsPath) sourceEnv.LM_CFO_CAPAFY_ANALYTICS = String(options.capafyAnalyticsPath);
      if (options.mobileAppsBusinessOutcomesPath) sourceEnv.LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES = String(options.mobileAppsBusinessOutcomesPath);
      if (options.affiliateReadbackPath) sourceEnv.LM_CFO_AFFILIATE_READBACK = String(options.affiliateReadbackPath);
      if (Array.isArray(options.agentReceiptPaths) && options.agentReceiptPaths.length) {
        sourceEnv.LM_CFO_AGENT_ECONOMY_RECEIPTS = options.agentReceiptPaths.join(path.delimiter);
      }
      if (Array.isArray(options.marketplaceReceiptPaths) && options.marketplaceReceiptPaths.length) {
        sourceEnv.LM_CFO_MARKETPLACE_RECEIPTS = options.marketplaceReceiptPaths.join(path.delimiter);
      }
      const result = spawnSync(options.pythonBin || "python3", args,
        { encoding: "utf8", timeout: 120_000, env: sourceEnv });
      if (result.status !== 0) throw new Error("cfo_source_read_failed");
      table = JSON.parse(result.stdout);
    }
    if (table.reporting_date !== date) throw new Error("cfo_source_date_mismatch");
    const message = renderResultSummary(table);
    const messageSha256Value = messageSha256(message);
    pending = { status: "pending", subjectId, periodKey, reportingDate: date, channel: destination.channel, recipientHash,
      eventKey: `cfo-result:${options.subjectId}:${destination.channel}:${periodKey}`, message,
      messageSha256: messageSha256Value, occurrenceId: currentOccurrenceId, createdAt: now.toISOString() };
    persist(pending);
  }
  const delivery = await (options.notify || (input => notifyCfoReport(input, options)))({
    eventKey: pending.eventKey, observedAt: now.toISOString(), message: pending.message,
    occurrenceId: currentOccurrenceId,
  });
  if (delivery?.delivery !== "delivered" || !delivery.provider_message_id) {
    throw new Error("cfo_provider_receipt_missing");
  }
  const duplicate = delivery.attempted === 0;
  const resolutionKind = duplicate ? "duplicate" : "sent";
  persist({ ...pending, status: "sent", occurrenceId: currentOccurrenceId,
    messageSha256: pending.messageSha256 || messageSha256(pending.message),
    resolutionKind, providerMessageId: String(delivery.provider_message_id), sentAt: now.toISOString() });
  return {
    status: duplicate ? "quiet" : "sent", reason: duplicate ? "unchanged" : null,
    reportingDate: pending.reportingDate, delivered: !duplicate,
    providerMessageId: String(delivery.provider_message_id), resolutionKind,
  };
}

module.exports = { messageSha256, occurrenceId, runResultCfo };
