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
const TELEGRAM_MESSAGE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const EFFECT_RESULT_HINT_FILENAME = "entrypoint-result.json";
const DELIVERY_COUNTER_FIELDS = ["attempted", "delivered", "delivery_uncertain", "pre_send_failed"];

function persistedDeliveryCounters(delivery) {
  return Object.fromEntries(DELIVERY_COUNTER_FIELDS.map(field => {
    const value = delivery?.[field];
    return [field, Number.isSafeInteger(value) && value >= 0 ? value : null];
  }));
}

function validPersistedDeliveryCounters(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value);
  return keys.length === DELIVERY_COUNTER_FIELDS.length
    && DELIVERY_COUNTER_FIELDS.every(field => Object.prototype.hasOwnProperty.call(value, field)
      && (value[field] === null || (Number.isSafeInteger(value[field]) && value[field] >= 0)));
}

function occurrenceId(value) {
  const text = String(value || "").trim();
  if (!OCCURRENCE_ID.test(text)) throw new Error("cfo_occurrence_invalid");
  return text;
}

function writeRuntimeTelegramEffectHint(env, currentOccurrenceId, destination, delivery, duplicate) {
  if (env?.LIFE_MANAGER_LOOP_ID !== "life-manager-cfo-hourly"
    || destination.channel !== "telegram" || duplicate) return null;
  if (delivery?.delivery !== "delivered" || delivery.attempted !== 1
    || delivery.delivered !== 1 || delivery.delivery_uncertain !== 0
    || delivery.pre_send_failed !== 0) return false;
  const providerReceiptId = delivery.provider_message_id;
  if (typeof providerReceiptId !== "string" || !TELEGRAM_MESSAGE_ID.test(providerReceiptId)) return false;
  let exactOccurrence;
  try { exactOccurrence = occurrenceId(currentOccurrenceId); } catch { return false; }
  const file = String(env.LIFE_MANAGER_RESULT_HINT_PATH || "");
  if (!file || path.basename(file) !== EFFECT_RESULT_HINT_FILENAME) return false;

  const effectResult = {
    schema_version: 1,
    kind: "life_manager_effect_result",
    status: "verified_effect",
    effect: 1,
    owner_id: "life-manager-cfo-hourly",
    occurrence_id: exactOccurrence,
    provider: "telegram",
    provider_receipt_id: providerReceiptId,
    effect_status: "verified",
  };
  let descriptor;
  try {
    descriptor = fs.openSync(file,
      fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL
        | (fs.constants.O_NOFOLLOW || 0), 0o600);
    const opened = fs.fstatSync(descriptor);
    if (!opened.isFile() || opened.nlink !== 1) return false;
    fs.fchmodSync(descriptor, 0o600);
    if ((fs.fstatSync(descriptor).mode & 0o777) !== 0o600) return false;
    fs.writeFileSync(descriptor, `${JSON.stringify(effectResult)}\n`, "utf8");
    fs.fsyncSync(descriptor);
    return true;
  } catch {
    // A missing or pre-existing hint is fail-closed: the runtime keeps the effect unknown.
    return false;
  } finally {
    if (descriptor !== undefined) {
      try { fs.closeSync(descriptor); } catch { /* The provider receipt remains authoritative. */ }
    }
  }
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

function readPrivateJson(file) {
  const resolved = path.resolve(file);
  const parent = path.dirname(resolved);
  const parentStat = fs.lstatSync(parent);
  if (parentStat.isSymbolicLink() || !parentStat.isDirectory() || (parentStat.mode & 0o777) !== 0o700) {
    throw new Error("cfo_source_evidence_invalid");
  }
  const stat = fs.lstatSync(resolved);
  if (stat.isSymbolicLink() || !stat.isFile() || (stat.mode & 0o777) !== 0o600
    || stat.size > 8 * 1024 * 1024) {
    throw new Error("cfo_source_evidence_invalid");
  }
  const descriptor = fs.openSync(resolved, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0));
  try {
    const opened = fs.fstatSync(descriptor);
    if (!opened.isFile() || (opened.mode & 0o777) !== 0o600 || opened.size > 8 * 1024 * 1024) {
      throw new Error("cfo_source_evidence_invalid");
    }
    const raw = fs.readFileSync(descriptor);
    const value = JSON.parse(raw.toString("utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("cfo_source_evidence_invalid");
    }
    return {
      value,
      sha256: crypto.createHash("sha256").update(raw).digest("hex"),
    };
  } finally { fs.closeSync(descriptor); }
}

function sourceDate(value) {
  if (typeof value !== "string") return null;
  let year, month, day;
  let match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (match) [, year, month, day] = match;
  else {
    match = value.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!match) return null;
    [, month, day, year] = match;
  }
  year = Number(year); month = Number(month); day = Number(day);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day) return null;
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function sourceInstant(value) {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function ascReportTuple(report, reportType, regionCode) {
  if (!report || typeof report !== "object" || Array.isArray(report)
    || !report.metadata || typeof report.metadata !== "object" || Array.isArray(report.metadata)) {
    throw new Error("cfo_asc_packet_invalid");
  }
  const { metadata } = report;
  const period = report.period;
  const artifactSha256 = String(report.artifact_sha256 || "");
  const periodStart = sourceDate(period?.start);
  const periodEnd = sourceDate(period?.end);
  if (metadata.reportType !== reportType || metadata.regionCode !== regionCode
    || typeof metadata.reportDate !== "string" || !/^\d{4}-\d{2}$/.test(metadata.reportDate)
    || !metadata.vendorNumber || typeof metadata.vendorNumber !== "string"
    || !period || typeof period !== "object" || Array.isArray(period)
    || !periodStart || !periodEnd || periodStart > periodEnd
    || !SHA256.test(artifactSha256)) throw new Error("cfo_asc_packet_invalid");
  return {
    reportType, regionCode, reportDate: metadata.reportDate,
    sourcePeriod: { start: period.start, end: period.end },
    period: { start: periodStart, end: periodEnd }, artifactSha256,
    nativeReportId: { status: "not_returned", endpoint: "GET /v1/financeReports" },
  };
}

function unavailableSourceProvenance(identity, reportingPeriod, reason) {
  return {
    schemaVersion: 1, status: "unavailable", reason,
    ownerId: identity.ownerId, runId: identity.runId, releaseSha: identity.releaseSha,
    occurrenceId: `${identity.ownerId}:${identity.runId}`, reportingPeriod,
  };
}

function mobileSourceProvenance(stateDir, identity, reportingPeriod, env) {
  const occurrence = `${identity.ownerId}:${identity.runId}`;
  const packetPath = String(env?.LM_CFO_MOBILE_APPS_ASC_FINANCIAL_PACKET || "").trim();
  if (!packetPath) return unavailableSourceProvenance(identity, reportingPeriod, "asc_packet_path_missing");
  let packetFile;
  try { packetFile = readPrivateJson(packetPath); } catch (error) {
    return unavailableSourceProvenance(identity, reportingPeriod,
      error.code === "ENOENT" ? "asc_packet_missing" : "asc_packet_unavailable");
  }
  let asc;
  try {
    const packet = packetFile.value;
    if (packet.schema_version !== 1 || !sourceInstant(packet.observed_at)
      || !packet.relationships || !SHA256.test(String(packet.relationships.artifact_sha256 || ""))) {
      throw new Error("cfo_asc_packet_invalid");
    }
    const financial = ascReportTuple(packet.financial, "FINANCIAL", "ZZ");
    const detail = ascReportTuple(packet.detail, "FINANCE_DETAIL", "Z1");
    if (financial.reportDate !== detail.reportDate
      || financial.period.start !== detail.period.start || financial.period.end !== detail.period.end
      || packet.financial.metadata.vendorNumber !== packet.detail.metadata.vendorNumber) {
      throw new Error("cfo_asc_packet_invalid");
    }
    asc = {
      packetSha256: packetFile.sha256, observedAt: packet.observed_at,
      financial, detail, relationshipsSha256: packet.relationships.artifact_sha256,
    };
  } catch {
    return unavailableSourceProvenance(identity, reportingPeriod, "asc_packet_invalid");
  }

  let mobileDirectory;
  try {
    const state = path.resolve(stateDir);
    const stateStat = fs.lstatSync(state);
    if (stateStat.isSymbolicLink() || !stateStat.isDirectory()) throw new Error("cfo_mobile_readback_path_invalid");
    mobileDirectory = path.join(fs.realpathSync(state), "mobile-readbacks");
    const directoryStat = fs.lstatSync(mobileDirectory);
    if (directoryStat.isSymbolicLink() || !directoryStat.isDirectory()
      || (directoryStat.mode & 0o777) !== 0o700) throw new Error("cfo_mobile_readback_path_invalid");
  } catch (error) {
    return {
      schemaVersion: 1, status: "partial", reason: error.code === "ENOENT"
        ? "mobile_readback_missing" : "mobile_readback_path_invalid",
      ownerId: identity.ownerId, runId: identity.runId, releaseSha: identity.releaseSha,
      occurrenceId: occurrence, reportingPeriod, asc,
    };
  }
  const mobilePath = path.join(mobileDirectory, `${occurrence}.json`);
  let mobileFile;
  try { mobileFile = readPrivateJson(mobilePath); } catch (error) {
    return {
      schemaVersion: 1, status: "partial", reason: error.code === "ENOENT"
        ? "mobile_readback_missing" : "mobile_readback_unavailable",
      ownerId: identity.ownerId, runId: identity.runId, releaseSha: identity.releaseSha,
      occurrenceId: occurrence, reportingPeriod, asc,
    };
  }
  const mobile = mobileFile.value;
  if (mobile.schema_version !== 1 || mobile.owner_id !== identity.ownerId || mobile.run_id !== identity.runId
    || mobile.occurrence_id !== occurrence || mobile.release_sha !== identity.releaseSha
    || mobile.live_readback_enabled !== true) {
    return {
      schemaVersion: 1, status: "partial", reason: "mobile_readback_identity_mismatch",
      ownerId: identity.ownerId, runId: identity.runId, releaseSha: identity.releaseSha,
      occurrenceId: occurrence, reportingPeriod, asc, mobileReadbackSha256: mobileFile.sha256,
    };
  }
  const records = Array.isArray(mobile.mobile_records) ? mobile.mobile_records : [];
  const ascReceipts = records.filter(row => row && row.provider === "app-store-connect-financial"
    && row.record_type === "receipt");
  const rcSnapshots = records.filter(row => row && row.provider === "revenuecat"
    && row.record_type === "subscription_snapshot");
  const financialRefPrefix = `appstoreconnect://financial-reports/sha256/${asc.financial.artifactSha256}#rows/`;
  const detailReceiptPrefix = `app-store-connect-financial:normalized:${asc.detail.artifactSha256}:`;
  const validAscReceipts = ascReceipts.filter(row => {
    const receiptId = String(row.receipt_id || "");
    if (!receiptId.startsWith(detailReceiptPrefix)) return false;
    const detailRow = receiptId.slice(detailReceiptPrefix.length);
    if (!/^\d+$/.test(detailRow) || row.verification_state !== "verified"
      || typeof row.currency !== "string" || !sourceInstant(row.occurred_at) || !sourceInstant(row.settled_at)) return false;
    const refs = Array.isArray(row.evidence_refs) ? row.evidence_refs : [];
    if (refs.length !== 4 || refs.some(ref => typeof ref !== "string")) return false;
    const financialRefs = refs.filter(ref => ref.startsWith(financialRefPrefix)
      && /^\d+(,\d+)*$/.test(ref.slice(financialRefPrefix.length)));
    const detailRef = `appstoreconnect://finance-detail/sha256/${asc.detail.artifactSha256}#row/${detailRow}`;
    const relationshipPrefix = `appstoreconnect://subscription-relationships/sha256/${asc.relationshipsSha256}#`;
    const relationshipDataRefs = refs.filter(ref => ref.startsWith(`${relationshipPrefix}data/`)
      && /^\d+$/.test(ref.slice(`${relationshipPrefix}data/`.length)));
    const relationshipIncludedRefs = refs.filter(ref => ref.startsWith(`${relationshipPrefix}included/`)
      && /^\d+$/.test(ref.slice(`${relationshipPrefix}included/`.length)));
    return financialRefs.length === 1 && refs.filter(ref => ref === detailRef).length === 1
      && relationshipDataRefs.length === 1 && relationshipIncludedRefs.length === 1
      && Array.isArray(row.components) && row.components.length === 1
      && typeof row.components[0].category === "string";
  });
  const receiptRowsValid = ascReceipts.length > 0 && validAscReceipts.length === ascReceipts.length;
  const rcRows = mobile.revenuecat && Array.isArray(mobile.revenuecat.rows)
    ? mobile.revenuecat.rows : [];
  const rawRowsByProduct = new Map();
  let rawRowsUnique = true;
  for (const row of rcRows) {
    if (!row || typeof row.product_id !== "string" || rawRowsByProduct.has(row.product_id)) {
      rawRowsUnique = false;
      continue;
    }
    rawRowsByProduct.set(row.product_id, row);
  }
  const matchedSnapshotProducts = new Set();
  const matchedSnapshots = [];
  for (const row of rcSnapshots) {
    const snapshotId = typeof row.snapshot_id === "string" ? row.snapshot_id : "";
    const marker = snapshotId.lastIndexOf(":mrr:");
    if (!snapshotId.startsWith("revenuecat:") || marker <= "revenuecat:".length) continue;
    const productId = snapshotId.slice("revenuecat:".length, marker);
    const businessDate = sourceDate(snapshotId.slice(marker + ":mrr:".length));
    const raw = rawRowsByProduct.get(productId);
    const query = raw?.query_scope;
    const refs = Array.isArray(row.evidence_refs) ? row.evidence_refs : [];
    if (!raw || !businessDate || raw.availability !== "available" || raw.reason
      || row.verification_state !== "verified" || row.normalization_basis !== "provider_monthly"
      || typeof row.currency !== "string" || !sourceInstant(row.observed_at)
      || raw.observed_at !== row.observed_at || !SHA256.test(String(raw.evidence_sha256 || ""))
      || !SHA256.test(String(raw.query_sha256 || ""))
      || !SHA256.test(String(raw.chart_response_sha256 || ""))
      || !query || query.chart !== "mrr" || !sourceDate(query.start_date) || !sourceDate(query.end_date)
      || businessDate < sourceDate(query.start_date) || businessDate > sourceDate(query.end_date)
      || refs.length !== 1
      || refs[0] !== `revenuecat://charts/mrr/${productId}/${businessDate}/${raw.evidence_sha256}`
      || matchedSnapshotProducts.has(productId)) continue;
    matchedSnapshotProducts.add(productId);
    matchedSnapshots.push({
      productIdSha256: crypto.createHash("sha256").update(productId, "utf8").digest("hex"),
      businessDate, evidenceSha256: raw.evidence_sha256, querySha256: raw.query_sha256,
      chartResponseSha256: raw.chart_response_sha256, observedAt: row.observed_at,
      currency: row.currency,
    });
  }
  const rcRowsValid = mobile.revenuecat?.availability === "available" && rawRowsUnique
    && rcRows.length === rcSnapshots.length && rcSnapshots.length > 0
    && matchedSnapshots.length === rcSnapshots.length;
  const duplicateReceipts = mobile.projection && Array.isArray(mobile.projection.duplicate_receipts)
    ? mobile.projection.duplicate_receipts : null;
  const windowStart = Date.parse(reportingPeriod.trailingStart || "");
  const windowEnd = Date.parse(reportingPeriod.snapshotAt || "");
  const inWindow = value => {
    const time = Date.parse(value || "");
    return Number.isFinite(time) && Number.isFinite(windowStart) && Number.isFinite(windowEnd)
      && windowStart <= time && time <= windowEnd;
  };
  const ascInWindow = ascReceipts.filter(row => inWindow(row.settled_at));
  const rcInWindow = rcSnapshots.filter(row => inWindow(row.observed_at));
  const rcTimes = rcSnapshots.map(row => row.observed_at).filter(sourceInstant).sort();
  const currencies = [...new Set(rcSnapshots.map(row => row.currency).filter(value => typeof value === "string"))].sort();
  const receipts = validAscReceipts.map(row => ({
    receiptId: row.receipt_id, currency: row.currency,
    occurredAt: row.occurred_at, settledAt: row.settled_at,
    category: Array.isArray(row.components)
      ? row.components.find(component => typeof component?.category === "string")?.category || null
      : null,
  }));
  const reason = !receiptRowsValid ? "asc_receipt_evidence_mismatch"
    : !rcRowsValid ? "revenuecat_snapshot_identity_mismatch"
      : !duplicateReceipts ? "mobile_duplicate_projection_missing"
        : duplicateReceipts.length ? "duplicate_receipts_present"
          : !ascInWindow.length ? "asc_receipt_missing_in_reporting_window"
            : rcInWindow.length !== rcSnapshots.length ? "revenuecat_snapshot_outside_reporting_window" : null;
  return {
    schemaVersion: 1, status: reason ? "partial" : "verified", reason,
    ownerId: identity.ownerId, runId: identity.runId, releaseSha: identity.releaseSha,
    occurrenceId: occurrence, reportingPeriod, asc: { ...asc, receipts },
    revenuecat: {
      status: rcRowsValid ? "available" : "unavailable",
      snapshotCount: rcSnapshots.length,
      verifiedSnapshotCount: rcSnapshots.filter(row => row.verification_state === "verified").length,
      matchedSnapshotCount: matchedSnapshots.length,
      currencies, observedAtStart: rcTimes[0] || null, observedAtEnd: rcTimes.at(-1) || null,
      mobileReadbackSha256: mobileFile.sha256, snapshots: matchedSnapshots,
    },
    duplicateReceiptCount: duplicateReceipts ? duplicateReceipts.length : null,
    samePeriodJoin: {
      ascReceiptCount: ascReceipts.length, ascReceiptCountInWindow: ascInWindow.length,
      revenuecatSnapshotCount: rcSnapshots.length, revenuecatSnapshotCountInWindow: rcInWindow.length,
    },
  };
}

function b7Reference(location, snapshot) {
  return {
    path: location.relativePath,
    projectionSha256: snapshot.projectionSha256,
    messageSha256: snapshot.messageSha256,
    sourceProvenanceSha256: snapshot.sourceProvenanceSha256,
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
  let snapshot;
  try { snapshot = readPrivateJson(location.file).value; } catch (error) {
    if (error.code === "ENOENT" && allowMissing) return null;
    if (error.message === "cfo_source_evidence_invalid") throw new Error("cfo_b7_snapshot_invalid");
    throw error;
  }
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)
    || !snapshot.projection || typeof snapshot.projection !== "object" || Array.isArray(snapshot.projection)
    || !snapshot.reportingPeriod || typeof snapshot.reportingPeriod !== "object" || Array.isArray(snapshot.reportingPeriod)) {
    throw new Error("cfo_b7_snapshot_invalid");
  }
  const separator = sourceOccurrenceId.indexOf(":");
  let projectionSha;
  let sourceProvenanceSha;
  let renderedMessage;
  try {
    projectionSha = crypto.createHash("sha256").update(canonicalJson(snapshot.projection), "utf8").digest("hex");
    sourceProvenanceSha = crypto.createHash("sha256").update(canonicalJson(snapshot.sourceProvenance), "utf8").digest("hex");
    renderedMessage = renderResultSummary(snapshot.projection);
  } catch { throw new Error("cfo_b7_snapshot_invalid"); }
  if (![3, 4].includes(snapshot.schemaVersion) || !["pending", "sent"].includes(snapshot.status)
    || snapshot.ownerId !== sourceOccurrenceId.slice(0, separator)
    || snapshot.runId !== sourceOccurrenceId.slice(separator + 1)
    || snapshot.occurrenceId !== sourceOccurrenceId || !RELEASE_SHA.test(String(snapshot.releaseSha || ""))
    || snapshot.projection.reporting_date !== snapshot.reportingPeriod.reportingDate
    || canonicalJson(snapshot.reportingPeriod) !== canonicalJson(reportingPeriodFor(snapshot.projection, snapshot.reportingPeriod.key))
    || !SHA256.test(String(snapshot.projectionSha256 || "")) || projectionSha !== snapshot.projectionSha256
    || !snapshot.sourceProvenance || snapshot.sourceProvenance.schemaVersion !== 1
    || !["verified", "partial", "unavailable"].includes(snapshot.sourceProvenance.status)
    || (snapshot.sourceProvenance.status !== "verified" && typeof snapshot.sourceProvenance.reason !== "string")
    || (snapshot.sourceProvenance.status === "verified" && (snapshot.sourceProvenance.reason !== null
      || !snapshot.sourceProvenance.asc || !snapshot.sourceProvenance.revenuecat
      || snapshot.sourceProvenance.revenuecat.status !== "available"
      || snapshot.sourceProvenance.duplicateReceiptCount !== 0
      || !snapshot.sourceProvenance.samePeriodJoin
      || snapshot.sourceProvenance.samePeriodJoin.ascReceiptCountInWindow < 1
      || snapshot.sourceProvenance.samePeriodJoin.revenuecatSnapshotCountInWindow < 1))
    || snapshot.sourceProvenance.occurrenceId !== snapshot.occurrenceId
    || snapshot.sourceProvenance.ownerId !== snapshot.ownerId
    || snapshot.sourceProvenance.runId !== snapshot.runId
    || snapshot.sourceProvenance.releaseSha !== snapshot.releaseSha
    || canonicalJson(snapshot.sourceProvenance.reportingPeriod) !== canonicalJson(snapshot.reportingPeriod)
    || !SHA256.test(String(snapshot.sourceProvenanceSha256 || ""))
    || sourceProvenanceSha !== snapshot.sourceProvenanceSha256
    || !SHA256.test(String(snapshot.messageSha256 || ""))
    || messageSha256(renderedMessage) !== snapshot.messageSha256
    || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(snapshot.subjectId || "")
    || typeof snapshot.channel !== "string" || !snapshot.channel
    || !SHA256.test(String(snapshot.recipientHash || ""))
    || snapshot.eventKey !== resultEventKey(snapshot.subjectId, snapshot.channel, snapshot.reportingPeriod.key)
    || !Number.isFinite(Date.parse(snapshot.createdAt))) throw new Error("cfo_b7_snapshot_invalid");
  if (snapshot.schemaVersion === 4 && ((snapshot.status === "sent"
    && !validPersistedDeliveryCounters(snapshot.deliveryCounters))
    || (snapshot.status === "pending" && snapshot.deliveryCounters !== undefined))) {
    throw new Error("cfo_b7_snapshot_invalid");
  }
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
    || snapshot.projectionSha256 !== reference.projectionSha256
    || snapshot.sourceProvenanceSha256 !== reference.sourceProvenanceSha256) throw new Error("cfo_b7_snapshot_invalid");
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
  const sourceEnv = options.env || process.env;
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
    persist({ ...previous, occurrenceId: currentOccurrenceId, resolutionKind: "duplicate",
      deliveryCounters: { attempted: 0, delivered: 0, delivery_uncertain: 0, pre_send_failed: 0 } });
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
  const newSourceIdentity = pending ? null : b7Identity(currentOccurrenceId, sourceEnv);
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
      sentAt: sourceSnapshot.sentAt, deliveryCounters: sourceSnapshot.deliveryCounters };
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
      const collectorEnv = { ...sourceEnv };
      if (options.capafyAnalyticsPath) collectorEnv.LM_CFO_CAPAFY_ANALYTICS = String(options.capafyAnalyticsPath);
      if (options.mobileAppsBusinessOutcomesPath) collectorEnv.LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES = String(options.mobileAppsBusinessOutcomesPath);
      if (options.affiliateReadbackPath) collectorEnv.LM_CFO_AFFILIATE_READBACK = String(options.affiliateReadbackPath);
      if (Array.isArray(options.agentReceiptPaths) && options.agentReceiptPaths.length) {
        collectorEnv.LM_CFO_AGENT_ECONOMY_RECEIPTS = options.agentReceiptPaths.join(path.delimiter);
      }
      if (Array.isArray(options.marketplaceReceiptPaths) && options.marketplaceReceiptPaths.length) {
        collectorEnv.LM_CFO_MARKETPLACE_RECEIPTS = options.marketplaceReceiptPaths.join(path.delimiter);
      }
      const result = spawnSync(options.pythonBin || "python3", args,
        { encoding: "utf8", timeout: 120_000, env: collectorEnv });
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
    const sourceProvenance = mobileSourceProvenance(stateDir, newSourceIdentity, reportingPeriod, sourceEnv);
    let sourceProvenanceSha256;
    try { sourceProvenanceSha256 = crypto.createHash("sha256").update(canonicalJson(sourceProvenance), "utf8").digest("hex"); }
    catch { throw new Error("cfo_b7_source_provenance_invalid"); }
    sourceSnapshot = { schemaVersion: 4, ...newSourceIdentity, occurrenceId: currentOccurrenceId,
      subjectId, channel: destination.channel, recipientHash, eventKey,
      reportingPeriod, projection, projectionSha256, sourceProvenance, sourceProvenanceSha256,
      messageSha256: messageSha256Value,
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
  const duplicate = delivery.attempted === 0 && delivery.delivered === 0
    && delivery.delivery_uncertain === 0 && delivery.pre_send_failed === 0;
  const resolutionKind = duplicate ? "duplicate" : "sent";
  const deliveryCounters = persistedDeliveryCounters(delivery);
  const sentAt = new Date().toISOString();
  if (sourceSnapshot) {
    const sourceOccurrenceId = sourceSnapshot.occurrenceId;
    sourceSnapshot = { ...sourceSnapshot, schemaVersion: 4, status: "sent", resolutionKind,
      deliveryCounters,
      providerMessageId: String(delivery.provider_message_id), sentAt,
      deliveryOccurrenceId: currentOccurrenceId,
      deliveryRunId: currentOccurrenceId.slice(currentOccurrenceId.indexOf(":") + 1) };
    writeB7Snapshot(stateDir, sourceOccurrenceId, sourceSnapshot, false);
  }
  persist({ ...pending, status: "sent", occurrenceId: currentOccurrenceId,
    messageSha256: pending.messageSha256 || messageSha256(pending.message),
    resolutionKind, deliveryCounters,
    providerMessageId: String(delivery.provider_message_id), sentAt });
  const runtimeHintWritten = writeRuntimeTelegramEffectHint(
    sourceEnv, currentOccurrenceId, destination, delivery, duplicate);
  if (runtimeHintWritten === false) {
    throw new Error("cfo_runtime_telegram_receipt_hint_missing");
  }
  return {
    status: duplicate ? "quiet" : "sent", reason: duplicate ? "unchanged" : null,
    reportingDate: pending.reportingDate, delivered: !duplicate,
    providerMessageId: String(delivery.provider_message_id), resolutionKind,
  };
}

module.exports = { messageSha256, occurrenceId, runResultCfo };
