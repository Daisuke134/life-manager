#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const ALLOWED_QUERY_KEYS = new Set(["lang", "source", "utm_source", "utm_medium", "utm_campaign"]);
const RECEIPT_STATUSES = new Set(["completed", "deferred", "failed", "effect_unknown"]);

function safeTimestamp(value) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return null;
  return value;
}

function safeCount(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function safeSha256(value) {
  return typeof value === "string" && /^[a-f0-9]{64}$/i.test(value) ? value.toLowerCase() : null;
}

function safeReleaseSha(value) {
  return typeof value === "string" && /^[a-f0-9]{40}$/i.test(value) ? value.toLowerCase() : null;
}

function safeLabel(value) {
  return typeof value === "string" && /^[a-z0-9_.-]{1,64}$/i.test(value) ? value : null;
}

function safeHttpsUrl(value, expectedHost = null) {
  if (typeof value !== "string") return null;
  try {
    const source = new URL(value);
    if (source.protocol !== "https:" || source.username || source.password) return null;
    if (expectedHost && source.hostname !== expectedHost) return null;
    const safe = new URL(`${source.origin}${source.pathname}`);
    for (const [key, queryValue] of source.searchParams.entries()) {
      if (ALLOWED_QUERY_KEYS.has(key) && /^[a-z0-9._-]{1,80}$/i.test(queryValue)) {
        safe.searchParams.set(key, queryValue);
      }
    }
    return safe.toString();
  } catch {
    return null;
  }
}

function safeRequiredFieldNames(fields) {
  if (!Array.isArray(fields)) return null;
  return [...new Set(fields.map(field => {
    if (typeof field === "string") return field;
    if (field && typeof field === "object") return field.name;
    return null;
  }).filter(value => typeof value === "string" && /^[a-z][a-z0-9_.-]{0,79}$/i.test(value)))].sort();
}

function safeWorkReceipts(receipts) {
  if (!Array.isArray(receipts)) return [];
  return receipts.flatMap(receipt => {
    if (!receipt || typeof receipt !== "object") return [];
    const provider = safeLabel(receipt.provider);
    const kind = safeLabel(receipt.kind);
    const status = RECEIPT_STATUSES.has(receipt.status) ? receipt.status : null;
    const observedAt = safeTimestamp(receipt.observed_at);
    const proofSha256 = safeSha256(receipt.proof_sha256);
    if (!provider || !kind || !status || !observedAt || !proofSha256) return [];
    return [{ provider, kind, status, observed_at: observedAt, proof_sha256: proofSha256 }];
  });
}

function safeCosts(costs) {
  if (!costs || typeof costs !== "object" || costs.measured !== true) return null;
  const currency = typeof costs.currency === "string" && /^[a-z]{3}$/.test(costs.currency)
    ? costs.currency : null;
  const amountMinor = safeCount(costs.amount_minor);
  const observedAt = safeTimestamp(costs.observed_at);
  const proofSha256 = safeSha256(costs.proof_sha256);
  if (!currency || amountMinor === null || !observedAt || !proofSha256) return null;
  return { currency, amount_minor: amountMinor, observed_at: observedAt, proof_sha256: proofSha256 };
}

function safeChannelEntry(entry) {
  if (!entry || typeof entry !== "object") return null;
  const permalink = safeHttpsUrl(entry.permalink, "keikixmaritime.slack.com");
  const postedAt = safeTimestamp(entry.posted_at);
  const channel = entry.channel === "#competition-submissions" ? entry.channel : null;
  if (!permalink || !postedAt || !channel) return null;
  return { channel, posted_at: postedAt, permalink };
}

function safeFormalReceipt(receipt) {
  if (!receipt || typeof receipt !== "object") return null;
  const status = new Set(["submitted", "received", "accepted"]).has(receipt.status) ? receipt.status : null;
  const receivedAt = safeTimestamp(receipt.received_at);
  const providerReceiptId = typeof receipt.provider_receipt_id === "string"
    && /^[a-z0-9._:-]{1,128}$/i.test(receipt.provider_receipt_id)
    ? receipt.provider_receipt_id : null;
  if (!status || !receivedAt || !providerReceiptId) return null;
  return { status, received_at: receivedAt, provider_receipt_id: providerReceiptId };
}

function buildMaritimeWeek1Packet({ status, requirements, generatedAt } = {}) {
  if (!status || typeof status !== "object" || !requirements || typeof requirements !== "object") {
    throw new TypeError("current status and requirements readbacks are required");
  }
  const runtime = status.runtime_database_readback || {};
  const submission = status.submission || {};
  const verifiedExternalUsers = safeCount(runtime.verified_external_manager_users);
  const externalWorkEvents = safeCount(runtime.external_work_events);
  const externalWorkUsers = safeCount(runtime.external_work_users);
  const workReceipts = safeWorkReceipts(status.verified_work_receipts);
  const costs = safeCosts(status.verified_costs);
  const officialRequiredFields = safeRequiredFieldNames(requirements.required_fields);
  const channelEntry = safeChannelEntry(submission.channel_entry_readback);
  const submissionReceipt = safeFormalReceipt(submission.formal_submission_receipt);
  const hasCompletedWorkReceipt = workReceipts.some(receipt => receipt.status === "completed");
  const releaseSha = safeReleaseSha(status.production?.life_call?.loaded_source_sha);
  const limitations = [];

  if (!officialRequiredFields) limitations.push("Official form fields are unpublished in the supplied requirements readback.");
  if (verifiedExternalUsers === 0) limitations.push("The supplied Runtime PG readback shows zero verified external Manager users.");
  if (!hasCompletedWorkReceipt) limitations.push("No completed hosted work receipt is verified.");
  if (!costs) limitations.push("Costs are unmeasured; the packet does not report USD 0.");
  if (!channelEntry) limitations.push("No read-back project entry is attached.");
  if (!submissionReceipt) limitations.push("Formal submission receipt is unconfirmed; a channel entry is not a formal receipt.");

  return {
    schema_version: 1,
    packet_status: "draft",
    generated_at: safeTimestamp(generatedAt) || safeTimestamp(status.observed_at),
    product_url: safeHttpsUrl(status.public_product?.pilot_url),
    demo_url: safeHttpsUrl(status.public_product?.verified_demo_url),
    release_sha: releaseSha,
    official_required_fields: officialRequiredFields,
    user_counts: {
      verified_external_manager_users: verifiedExternalUsers,
      external_work_events: externalWorkEvents,
      completed_external_work_users: externalWorkUsers,
      readback_at: safeTimestamp(runtime.observed_at),
    },
    work_receipts: workReceipts,
    costs,
    channel_entry_share: channelEntry,
    submission_receipt: submissionReceipt,
    limitations,
  };
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    throw new Error(`submission input unavailable: ${path.basename(filePath)}`);
  }
}

function exportCurrentDraft({ root = path.resolve(__dirname, "../../.."), generatedAt = new Date().toISOString() } = {}) {
  const statusPath = path.join(root, "docs/evidence/maritime/current-status-20261021.json");
  const requirementsPath = path.join(root, "docs/distribution/maritime/week1/requirements.json");
  const outputPath = path.join(root, "docs/distribution/maritime/week1/submission.json");
  const packet = buildMaritimeWeek1Packet({
    status: readJson(statusPath),
    requirements: readJson(requirementsPath),
    generatedAt,
  });
  fs.writeFileSync(outputPath, `${JSON.stringify(packet, null, 2)}\n`, { mode: 0o600 });
  return { packet, outputPath };
}

if (require.main === module) {
  try {
    const { packet, outputPath } = exportCurrentDraft();
    process.stdout.write(`${JSON.stringify({ status: packet.packet_status, output_path: path.relative(process.cwd(), outputPath), generated_at: packet.generated_at })}\n`);
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = { buildMaritimeWeek1Packet, exportCurrentDraft };
