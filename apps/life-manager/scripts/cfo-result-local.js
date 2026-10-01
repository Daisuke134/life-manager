"use strict";
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { notifyCfoReport, reportDestination } = require("../lib/cfo-report-delivery.js");
const { renderResultSummary } = require("../lib/cfo-result-summary.js");

async function runResultCfo(options) {
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(options.subjectId || "")) throw new Error("cfo_subject_invalid");
  const subjectId = options.subjectId;
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
  if (previous?.status === "sent" && previous.periodKey === periodKey) {
    if (previous.subjectId !== subjectId) throw new Error("cfo_sent_subject_changed");
    if (!previous.providerMessageId) throw new Error("cfo_sent_provider_receipt_missing");
    return { status: "quiet", reason: "unchanged", reportingDate: date, delivered: false };
  }
  const persist = value => {
    const temporary = `${file}.${crypto.randomUUID()}.tmp`;
    const fd = fs.openSync(temporary, "wx", 0o600);
    try { fs.writeFileSync(fd, JSON.stringify(value)); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(temporary, file);
    const directory = fs.openSync(stateDir, "r");
    try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
  };
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
    pending = { status: "pending", subjectId, periodKey, reportingDate: date, channel: destination.channel, recipientHash,
      eventKey: `cfo-result:${options.subjectId}:${destination.channel}:${periodKey}`, message, createdAt: now.toISOString() };
    persist(pending);
  }
  const delivery = await (options.notify || (input => notifyCfoReport(input, options)))({
    eventKey: pending.eventKey, observedAt: now.toISOString(), message: pending.message,
  });
  if (delivery?.delivery !== "delivered" || !delivery.provider_message_id) {
    throw new Error("cfo_provider_receipt_missing");
  }
  persist({ ...pending, status: "sent", providerMessageId: String(delivery.provider_message_id), sentAt: now.toISOString() });
  return { status: "sent", reportingDate: pending.reportingDate, delivered: true };
}
module.exports = { runResultCfo };
