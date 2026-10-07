"use strict";
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { notifyCfoReport, reportDestination } = require("../lib/cfo-report-delivery.js");
const { renderResultSummary } = require("../lib/cfo-result-summary.js");

const OCCURRENCE_ID = /^life-manager-cfo-hourly:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const RELEASE_SHA = /^(?:[a-f0-9]{40}|[a-f0-9]{64})$/;

function occurrenceId(value) {
  const text = String(value || "").trim();
  if (!OCCURRENCE_ID.test(text)) throw new Error("cfo_occurrence_invalid");
  return text;
}

function messageSha256(message) {
  return crypto.createHash("sha256").update(String(message), "utf8").digest("hex");
}

function canonicalJson(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number" && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  throw new Error("cfo_b7_projection_invalid");
}

function b7Identity(value, env) {
  const separator = value.indexOf(":");
  const releaseSha = String(env?.LIFE_MANAGER_RELEASE_SHA || "").trim();
  if (separator < 1 || !RELEASE_SHA.test(releaseSha)) throw new Error("cfo_b7_identity_invalid");
  return {
    ownerId: value.slice(0, separator),
    runId: value.slice(separator + 1),
    releaseSha,
  };
}

function resultEventKey(subjectId, channel, periodKey) {
  return `cfo-result:${subjectId}:${channel}:${periodKey}`;
}

function reportingPeriodFor(projection, periodKey) {
  return {
    key: periodKey,
    reportingDate: projection.reporting_date,
    timezone: projection.timezone || "Asia/Tokyo",
    snapshotAt: projection.snapshot_at || projection.economic_attribution?.snapshot_at || null,
    trailingStart: projection.trailing_start || projection.economic_attribution?.trailing_start || null,
  };
}

function b7Reference(location, snapshot) {
  return {
    path: location.relativePath,
    projectionSha256: snapshot.projectionSha256,
    messageSha256: snapshot.messageSha256,
  };
}

function b7ReadbackLocation(stateDir, value, createDirectory) {
  const stateStat = fs.lstatSync(stateDir);
  if (stateStat.isSymbolicLink() || !stateStat.isDirectory()) throw new Error("cfo_b7_readback_path_invalid");
  const stateRoot = fs.realpathSync(stateDir);
  const directory = path.join(stateRoot, "b7-readbacks");
  if (createDirectory) {
    try { fs.mkdirSync(directory, { mode: 0o700 }); } catch (error) {
      if (error.code !== "EEXIST") throw error;
    }
  }
  const directoryStat = fs.lstatSync(directory);
  if (directoryStat.isSymbolicLink() || !directoryStat.isDirectory()
    || fs.realpathSync(directory) !== directory) throw new Error("cfo_b7_readback_path_invalid");
  const directoryFlags = fs.constants.O_RDONLY | (fs.constants.O_DIRECTORY || 0) | (fs.constants.O_NOFOLLOW || 0);
  const directoryFd = fs.openSync(directory, directoryFlags);
  try {
    if (!fs.fstatSync(directoryFd).isDirectory()) throw new Error("cfo_b7_readback_path_invalid");
    fs.fchmodSync(directoryFd, 0o700);
  } finally { fs.closeSync(directoryFd); }
  const file = path.resolve(directory, `${value}.json`);
  if (path.dirname(file) !== directory || path.relative(stateRoot, directory) !== "b7-readbacks") {
    throw new Error("cfo_b7_readback_path_invalid");
  }
  return { directory, file, relativePath: `b7-readbacks/${value}.json` };
}

function b7SnapshotStat(file) {
  try {
    const stat = fs.lstatSync(file);
    if (stat.isSymbolicLink() || !stat.isFile() || (stat.mode & 0o777) !== 0o600) {
      throw new Error("cfo_b7_readback_path_invalid");
    }
    return stat;
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

function writeB7Snapshot(stateDir, value, snapshot, create) {
  const location = b7ReadbackLocation(stateDir, value, true);
  const existing = b7SnapshotStat(location.file);
  if (create ? existing : !existing) throw new Error(create ? "cfo_b7_snapshot_exists" : "cfo_b7_snapshot_missing");
  const temporary = path.join(location.directory, `.${value}.${crypto.randomUUID()}.tmp`);
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.fchmodSync(descriptor, 0o600);
    fs.writeFileSync(descriptor, `${JSON.stringify(snapshot)}\n`, "utf8");
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    const beforeRename = b7SnapshotStat(location.file);
    if (create ? beforeRename : !beforeRename) throw new Error(create ? "cfo_b7_snapshot_exists" : "cfo_b7_snapshot_missing");
    fs.renameSync(temporary, location.file);
    const directoryFd = fs.openSync(location.directory,
      fs.constants.O_RDONLY | (fs.constants.O_DIRECTORY || 0) | (fs.constants.O_NOFOLLOW || 0));
    try { fs.fsyncSync(directoryFd); } finally { fs.closeSync(directoryFd); }
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    try { fs.unlinkSync(temporary); } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  return location;
}

function readB7SnapshotFile(stateDir, sourceOccurrenceId, allowMissing) {
  let location;
  try { location = b7ReadbackLocation(stateDir, sourceOccurrenceId, false); } catch (error) {
    if (allowMissing && error.code === "ENOENT") return null;
    throw error;
  }
  const stat = b7SnapshotStat(location.file);
  if (!stat) {
    if (allowMissing) return null;
    throw new Error("cfo_b7_snapshot_missing");
  }
  const descriptor = fs.openSync(location.file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0));
  let snapshot;
  try {
    const opened = fs.fstatSync(descriptor);
    if (!opened.isFile() || (opened.mode & 0o777) !== 0o600) throw new Error("cfo_b7_readback_path_invalid");
    snapshot = JSON.parse(fs.readFileSync(descriptor, "utf8"));
  } finally { fs.closeSync(descriptor); }
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)
    || !snapshot.projection || typeof snapshot.projection !== "object" || Array.isArray(snapshot.projection)
    || !snapshot.reportingPeriod || typeof snapshot.reportingPeriod !== "object" || Array.isArray(snapshot.reportingPeriod)) {
    throw new Error("cfo_b7_snapshot_invalid");
  }
  const separator = sourceOccurrenceId.indexOf(":");
  let projectionSha;
  let renderedMessage;
  try {
    projectionSha = crypto.createHash("sha256").update(canonicalJson(snapshot.projection), "utf8").digest("hex");
    renderedMessage = renderResultSummary(snapshot.projection);
  } catch { throw new Error("cfo_b7_snapshot_invalid"); }
  if (snapshot.schemaVersion !== 2 || !["pending", "sent"].includes(snapshot.status)
    || snapshot.ownerId !== sourceOccurrenceId.slice(0, separator)
    || snapshot.runId !== sourceOccurrenceId.slice(separator + 1)
    || snapshot.occurrenceId !== sourceOccurrenceId || !RELEASE_SHA.test(String(snapshot.releaseSha || ""))
    || snapshot.projection.reporting_date !== snapshot.reportingPeriod.reportingDate
    || canonicalJson(snapshot.reportingPeriod) !== canonicalJson(reportingPeriodFor(snapshot.projection, snapshot.reportingPeriod.key))
    || !SHA256.test(String(snapshot.projectionSha256 || "")) || projectionSha !== snapshot.projectionSha256
    || !SHA256.test(String(snapshot.messageSha256 || ""))
    || messageSha256(renderedMessage) !== snapshot.messageSha256
    || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(snapshot.subjectId || "")
    || typeof snapshot.channel !== "string" || !snapshot.channel
    || !SHA256.test(String(snapshot.recipientHash || ""))
    || snapshot.eventKey !== resultEventKey(snapshot.subjectId, snapshot.channel, snapshot.reportingPeriod.key)
    || !Number.isFinite(Date.parse(snapshot.createdAt))) throw new Error("cfo_b7_snapshot_invalid");
  if (snapshot.status === "sent") {
    let deliveryOccurrence;
    try { deliveryOccurrence = occurrenceId(snapshot.deliveryOccurrenceId); }
    catch { throw new Error("cfo_b7_snapshot_invalid"); }
    const deliverySeparator = deliveryOccurrence.indexOf(":");
    if (typeof snapshot.providerMessageId !== "string" || !snapshot.providerMessageId
      || !Number.isFinite(Date.parse(snapshot.sentAt)) || !["sent", "duplicate"].includes(snapshot.resolutionKind)
      || deliveryOccurrence.slice(0, deliverySeparator) !== snapshot.ownerId
      || snapshot.deliveryRunId !== deliveryOccurrence.slice(deliverySeparator + 1)) {
      throw new Error("cfo_b7_snapshot_invalid");
    }
  } else if (snapshot.providerMessageId !== undefined || snapshot.sentAt !== undefined
    || snapshot.resolutionKind !== undefined || snapshot.deliveryOccurrenceId !== undefined
    || snapshot.deliveryRunId !== undefined) throw new Error("cfo_b7_snapshot_invalid");
  return { location, snapshot };
}

function readB7Snapshot(stateDir, reference, pending) {
  const sourceOccurrenceId = occurrenceId(pending.occurrenceId);
  let stored;
  try { stored = readB7SnapshotFile(stateDir, sourceOccurrenceId, false); } catch (error) {
    if (error.code === "ENOENT") throw new Error("cfo_b7_snapshot_missing");
    throw error;
  }
  const { location, snapshot } = stored;
  if (!reference || reference.path !== location.relativePath
    || !SHA256.test(String(reference.projectionSha256 || ""))
    || reference.messageSha256 !== pending.messageSha256
    || messageSha256(pending.message) !== pending.messageSha256
    || snapshot.reportingPeriod.key !== pending.periodKey
    || snapshot.messageSha256 !== pending.messageSha256
    || snapshot.subjectId !== pending.subjectId || snapshot.channel !== pending.channel
    || snapshot.recipientHash !== pending.recipientHash || snapshot.eventKey !== pending.eventKey
    || snapshot.projectionSha256 !== reference.projectionSha256) throw new Error("cfo_b7_snapshot_invalid");
  return snapshot;
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
  const eventKey = resultEventKey(subjectId, destination.channel, periodKey);
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
  const newSourceIdentity = pending ? null : b7Identity(currentOccurrenceId, options.env || process.env);
  let sourceSnapshot = null;
  let sourceSnapshotMissing = false;
  if (pending?.b7ReadbackRef) {
    try { sourceSnapshot = readB7Snapshot(stateDir, pending.b7ReadbackRef, pending); } catch (error) {
      if (error.message !== "cfo_b7_snapshot_missing") throw error;
      sourceSnapshotMissing = true;
    }
  }
  if (!pending) {
    const orphan = readB7SnapshotFile(stateDir, currentOccurrenceId, true);
    if (orphan) {
      const { location, snapshot } = orphan;
      if (snapshot.ownerId !== newSourceIdentity.ownerId || snapshot.runId !== newSourceIdentity.runId
        || snapshot.releaseSha !== newSourceIdentity.releaseSha
        || snapshot.reportingPeriod.key !== periodKey || snapshot.reportingPeriod.reportingDate !== date
        || snapshot.subjectId !== subjectId || snapshot.channel !== destination.channel
        || snapshot.recipientHash !== recipientHash || snapshot.eventKey !== eventKey
        || (snapshot.status === "sent" && (snapshot.deliveryOccurrenceId !== currentOccurrenceId
          || snapshot.deliveryRunId !== newSourceIdentity.runId))) throw new Error("cfo_b7_snapshot_invalid");
      pending = { status: "pending", subjectId, periodKey, reportingDate: date,
        channel: destination.channel, recipientHash, eventKey,
        message: renderResultSummary(snapshot.projection), messageSha256: snapshot.messageSha256,
        occurrenceId: currentOccurrenceId, createdAt: snapshot.createdAt,
        b7ReadbackRef: b7Reference(location, snapshot) };
      sourceSnapshot = snapshot;
      if (snapshot.status === "pending") {
        if (now.getTime() - Date.parse(snapshot.createdAt) >= 23 * 60 * 60 * 1000) {
          throw new Error("cfo_pending_receipt_requires_reconcile");
        }
        persist(pending);
      }
    }
  }
  if (sourceSnapshot?.status === "sent") {
    const recovered = { ...pending, status: "sent", occurrenceId: currentOccurrenceId,
      resolutionKind: sourceSnapshot.resolutionKind, providerMessageId: sourceSnapshot.providerMessageId,
      sentAt: sourceSnapshot.sentAt };
    persist(recovered);
    const duplicate = sourceSnapshot.resolutionKind === "duplicate";
    return { status: duplicate ? "quiet" : "sent", reason: duplicate ? "unchanged" : null,
      reportingDate: pending.reportingDate, delivered: !duplicate,
      providerMessageId: sourceSnapshot.providerMessageId, resolutionKind: sourceSnapshot.resolutionKind };
  }
  if (pending && now.getTime() - Date.parse(pending.createdAt) >= 23 * 60 * 60 * 1000) {
    throw new Error("cfo_pending_receipt_requires_reconcile");
  }
  if (sourceSnapshotMissing) throw new Error("cfo_b7_snapshot_missing");
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
    let projection;
    try { projection = JSON.parse(JSON.stringify(table)); } catch { throw new Error("cfo_b7_projection_invalid"); }
    if (!projection || typeof projection !== "object" || Array.isArray(projection)) throw new Error("cfo_b7_projection_invalid");
    const message = renderResultSummary(projection);
    const messageSha256Value = messageSha256(message);
    let projectionSha256;
    try { projectionSha256 = crypto.createHash("sha256").update(canonicalJson(projection), "utf8").digest("hex"); }
    catch { throw new Error("cfo_b7_projection_invalid"); }
    const reportingPeriod = reportingPeriodFor(projection, periodKey);
    sourceSnapshot = { schemaVersion: 2, ...newSourceIdentity, occurrenceId: currentOccurrenceId,
      subjectId, channel: destination.channel, recipientHash, eventKey,
      reportingPeriod, projection, projectionSha256, messageSha256: messageSha256Value,
      status: "pending", createdAt: now.toISOString() };
    const sourceLocation = writeB7Snapshot(stateDir, currentOccurrenceId, sourceSnapshot, true);
    const b7ReadbackRef = b7Reference(sourceLocation, sourceSnapshot);
    pending = { status: "pending", subjectId, periodKey, reportingDate: date, channel: destination.channel, recipientHash,
      eventKey, message,
      messageSha256: messageSha256Value, occurrenceId: currentOccurrenceId, createdAt: now.toISOString(), b7ReadbackRef };
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
  const sentAt = now.toISOString();
  if (sourceSnapshot) {
    const sourceOccurrenceId = sourceSnapshot.occurrenceId;
    sourceSnapshot = { ...sourceSnapshot, status: "sent", resolutionKind,
      providerMessageId: String(delivery.provider_message_id), sentAt,
      deliveryOccurrenceId: currentOccurrenceId,
      deliveryRunId: currentOccurrenceId.slice(currentOccurrenceId.indexOf(":") + 1) };
    writeB7Snapshot(stateDir, sourceOccurrenceId, sourceSnapshot, false);
  }
  persist({ ...pending, status: "sent", occurrenceId: currentOccurrenceId,
    messageSha256: pending.messageSha256 || messageSha256(pending.message),
    resolutionKind, providerMessageId: String(delivery.provider_message_id), sentAt });
  return {
    status: duplicate ? "quiet" : "sent", reason: duplicate ? "unchanged" : null,
    reportingDate: pending.reportingDate, delivered: !duplicate,
    providerMessageId: String(delivery.provider_message_id), resolutionKind,
  };
}

module.exports = { messageSha256, occurrenceId, runResultCfo };
