"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runResultCfo } = require("./cfo-result-local.js");
function setup(t) {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "cfo-result-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  let value = "1";
  const messages = [];
  const options = { stateDir, subjectId: "owner", reportEmail: "owner@example.test",
    occurrenceId: "life-manager-cfo-hourly:run-1",
    env: { LIFE_MANAGER_RELEASE_SHA: "a".repeat(40), API_TOKEN: "fixture-secret",
      Authorization: "Bearer fixture-secret" },
    collect: async date => ({ reporting_date: date, rows: [{ loop_id: "capafy",
      revenue: { status: "verified", amounts: { USD: value }, receipts: ["receipt:1"] } }] }),
    notify: async input => { messages.push(input); return { delivery: "delivered", provider_message_id: "id",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 }; } };
  return { options, messages, change: v => { value = v; } };
}

function b7Table(reportingDate) {
  const snapshotAt = `${reportingDate}T12:00:00.000Z`;
  const trailingStart = "2026-08-31T12:00:00.000Z";
  return {
    reporting_date: reportingDate,
    timezone: "Asia/Tokyo",
    snapshot_at: snapshotAt,
    trailing_start: trailingStart,
    economic_attribution: {
      snapshot_at: snapshotAt,
      trailing_start: trailingStart,
      historical: { company: { status: "unknown" }, loops: {
        capafy: { status: "unknown", coverage_gaps: [{ reason: "missing_coverage" }] },
      } },
      trailing: { company: { status: "unknown" }, loops: {
        capafy: { status: "unknown", coverage_gaps: [{ reason: "stale_readback" }] },
      } },
      mrr: { company: { status: "unknown" }, loops: {} },
      runway: { status: "unknown" },
      duplicate_receipts: [],
    },
  };
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function readbackFile(stateDir, occurrenceId) {
  return path.join(stateDir, "b7-readbacks", `${occurrenceId}.json`);
}

function readbackFiles(stateDir) {
  const directory = path.join(stateDir, "b7-readbacks");
  return fs.existsSync(directory) ? fs.readdirSync(directory).filter(name => name.endsWith(".json")) : [];
}

function writePrivateJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const body = `${JSON.stringify(value)}\n`;
  fs.writeFileSync(file, body, { mode: 0o600 });
  fs.chmodSync(file, 0o600);
  return body;
}

test("new occurrence persists the normalized B7 source bound to its delivered report receipt", async t => {
  const { options, messages } = setup(t);
  const table = b7Table("2026-09-30");
  options.collect = async () => table;
  options.notify = async input => {
    messages.push(input);
    return { delivery: "delivered", provider_message_id: "provider-message-1",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0,
      raw: { Authorization: "do-not-save" } };
  };

  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

  const file = readbackFile(options.stateDir, options.occurrenceId);
  const snapshot = JSON.parse(fs.readFileSync(file, "utf8"));
  assert.equal(snapshot.schemaVersion, 4);
  assert.deepEqual(snapshot.deliveryCounters, {
    attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0,
  });
  assert.deepEqual(snapshot.projection, table);
  assert.equal(snapshot.ownerId, "life-manager-cfo-hourly");
  assert.equal(snapshot.runId, "run-1");
  assert.equal(snapshot.occurrenceId, options.occurrenceId);
  assert.equal(snapshot.releaseSha, "a".repeat(40));
  assert.equal(snapshot.subjectId, options.subjectId);
  assert.equal(snapshot.channel, "email");
  assert.equal(snapshot.recipientHash, crypto.createHash("sha256").update(options.reportEmail).digest("hex"));
  assert.equal(snapshot.eventKey, "cfo-result:owner:email:2026-09-30:12");
  assert.equal(Object.hasOwn(snapshot, "recipient"), false);
  assert.deepEqual(snapshot.reportingPeriod, {
    key: "2026-09-30:12", reportingDate: "2026-09-30", timezone: "Asia/Tokyo",
    snapshotAt: table.snapshot_at, trailingStart: table.trailing_start,
  });
  assert.equal(snapshot.projectionSha256, crypto.createHash("sha256").update(canonicalJson(table)).digest("hex"));
  assert.equal(snapshot.messageSha256, crypto.createHash("sha256").update(messages[0].message).digest("hex"));
  assert.equal(snapshot.status, "sent");
  assert.equal(snapshot.sourceProvenance.status, "unavailable");
  assert.equal(snapshot.sourceProvenance.reason, "asc_packet_path_missing");
  assert.equal(snapshot.providerMessageId, "provider-message-1");
  assert.equal(snapshot.resolutionKind, "sent");
  assert.equal(snapshot.deliveryOccurrenceId, options.occurrenceId);
  assert.ok(snapshot.sentAt);
  assert.equal(fs.statSync(path.dirname(file)).mode & 0o777, 0o700);
  assert.equal(fs.statSync(file).mode & 0o777, 0o600);
  assert.doesNotMatch(fs.readFileSync(file, "utf8"), /fixture-secret|do-not-save|API_TOKEN|Authorization|owner@example\.test/);
  assert.doesNotMatch(fs.readFileSync(path.join(options.stateDir, "last-result-report.json"), "utf8"), /fixture-secret|do-not-save/);
});

test("default email adapter persists a sent report with the required delivery counters", async t => {
  const { options } = setup(t);
  options.notify = undefined;
  options.sendEmail = async input => {
    assert.equal(input.to, options.reportEmail);
    assert.equal(input.idempotencyKey, "cfo-result:owner:email:2026-09-30:12");
    return { sent: true, id: "provider-email-1" };
  };

  const result = await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

  const report = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json"), "utf8"));
  assert.equal(result.status, "sent");
  assert.equal(report.status, "sent");
  assert.equal(report.providerMessageId, "provider-email-1");
  assert.deepEqual(report.deliveryCounters, {
    attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0,
  });
});

function writeMobileProvenanceFixture(options, { mutatePacket, mutateMobile } = {}) {
  const financialSha = "f".repeat(64);
  const detailSha = "d".repeat(64);
  const relationshipsSha = "b".repeat(64);
  const packet = {
    schema_version: 1,
    observed_at: "2026-09-30T11:59:00.000Z",
    financial: {
      metadata: { reportType: "FINANCIAL", regionCode: "ZZ", reportDate: "2026-12", vendorNumber: "private-vendor",
        filePath: "/private/financial.gz", decompressed: true, decompressedPath: "/private/financial.tsv",
        fileSize: 20, decompressedSize: 100 },
      artifact_path: "/private/financial.tsv", artifact_sha256: financialSha,
      period: { start: "08/30/2026", end: "09/26/2026" },
    },
    detail: {
      metadata: { reportType: "FINANCE_DETAIL", regionCode: "Z1", reportDate: "2026-12", vendorNumber: "private-vendor",
        filePath: "/private/detail.gz", decompressed: true, decompressedPath: "/private/detail.tsv",
        fileSize: 20, decompressedSize: 100 },
      artifact_path: "/private/detail.tsv", artifact_sha256: detailSha,
      period: { start: "08/30/2026", end: "09/26/2026" },
    },
    relationships: { artifact_path: "/private/relationships.json", artifact_sha256: relationshipsSha },
  };
  const packetPath = path.join(options.stateDir, "asc-input", "asc-financial-packet.json");
  const receiptId = `app-store-connect-financial:normalized:${detailSha}:12`;
  const revenuecatRows = [];
  const revenuecatSnapshots = [];
  for (let index = 0; index < 6; index++) {
    const productId = `product-${index + 1}`;
    const businessDate = `2026-09-${String(25 + index).padStart(2, "0")}`;
    const observedAt = `${businessDate}T00:00:00.000Z`;
    const evidenceSha256 = crypto.createHash("sha256").update(`revenuecat:${productId}:${businessDate}`).digest("hex");
    const querySha256 = crypto.createHash("sha256").update(`query:${productId}`).digest("hex");
    const chartResponseSha256 = crypto.createHash("sha256").update(`chart:${productId}`).digest("hex");
    revenuecatRows.push({
      product_id: productId, availability: "available", reason: null, observed_at: observedAt,
      query_scope: { chart: "mrr", chart_endpoint: "/v2/projects/{project_id}/charts/mrr",
        options_endpoint: "/v2/projects/{project_id}/charts/mrr/options", project_id_sha256: "c".repeat(64),
        start_date: "2026-09-10", end_date: "2026-09-30", resolution: "daily",
        filters: [{ name: "app_id", values: [productId] }] },
      query_sha256: querySha256, evidence_sha256: evidenceSha256, chart_response_sha256: chartResponseSha256,
    });
    revenuecatSnapshots.push({
      schema_version: 1, record_type: "subscription_snapshot", snapshot_id: `revenuecat:${productId}:mrr:${businessDate}`,
      subscription_id: `revenuecat:${productId}:mrr`, product_loop_id: "mobile-apps", provider: "revenuecat",
      currency: "USD", normalized_monthly_amount: "20.34", normalization_basis: "provider_monthly",
      status: "active", observed_at: observedAt, verification_state: "verified",
      evidence_refs: [`revenuecat://charts/mrr/${productId}/${businessDate}/${evidenceSha256}`],
    });
  }
  const ascReceipt = {
    schema_version: 1, record_type: "receipt", provider: "app-store-connect-financial",
    product_loop_id: "mobile-apps", receipt_id: receiptId, currency: "JPY",
    occurred_at: "2026-09-12T00:00:00Z", settled_at: "2026-09-12T00:00:00Z",
    verification_state: "verified", revenue_class: "other_recurring",
    evidence_refs: [
      `appstoreconnect://financial-reports/sha256/${financialSha}#rows/1`,
      `appstoreconnect://finance-detail/sha256/${detailSha}#row/12`,
      `appstoreconnect://subscription-relationships/sha256/${relationshipsSha}#data/1`,
      `appstoreconnect://subscription-relationships/sha256/${relationshipsSha}#included/1`,
    ],
    components: [{ category: "settled_external_revenue", amount: "4250" }],
  };
  const mobileReadback = {
    schema_version: 1, owner_id: "life-manager-cfo-hourly", run_id: "run-1",
    occurrence_id: options.occurrenceId, release_sha: "a".repeat(40), live_readback_enabled: true,
    revenuecat: {
      started_at: "2026-09-30T11:58:00.000Z", completed_at: "2026-09-30T11:59:00.000Z",
      latest_observed_at: "2026-09-30T00:00:00.000Z", availability: "available", rows: revenuecatRows,
    },
    mobile_records: [...revenuecatSnapshots, ascReceipt],
    projection: { duplicate_receipts: [], coverage: {}, mobile_mrr: { status: "verified", amounts: { USD: "20.34" } } },
  };
  mutatePacket?.(packet);
  mutateMobile?.(mobileReadback);
  const packetText = writePrivateJson(packetPath, packet);
  options.env = { ...options.env, LM_CFO_MOBILE_APPS_ASC_FINANCIAL_PACKET: packetPath };
  const mobilePath = path.join(options.stateDir, "mobile-readbacks", `${options.occurrenceId}.json`);
  const mobileText = writePrivateJson(mobilePath, mobileReadback);
  return { packet, packetText, mobileReadback, mobileText, financialSha, detailSha, relationshipsSha, receiptId };
}

test("B7 snapshot joins the official ASC packet and same-occurrence RevenueCat readback", async t => {
  const { options } = setup(t);
  const table = b7Table("2026-09-30");
  options.collect = async () => table;
  const fixture = writeMobileProvenanceFixture(options);

  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

  const snapshot = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
  const provenance = snapshot.sourceProvenance;
  assert.equal(provenance.status, "verified");
  assert.equal(provenance.occurrenceId, options.occurrenceId);
  assert.equal(provenance.asc.packetSha256, crypto.createHash("sha256").update(fixture.packetText).digest("hex"));
  assert.equal(provenance.asc.observedAt, fixture.packet.observed_at);
  assert.deepEqual(provenance.asc.financial, {
    reportType: "FINANCIAL", regionCode: "ZZ", reportDate: "2026-12",
    sourcePeriod: { start: "08/30/2026", end: "09/26/2026" },
    period: { start: "2026-08-30", end: "2026-09-26" }, artifactSha256: fixture.financialSha,
    nativeReportId: { status: "not_returned", endpoint: "GET /v1/financeReports" },
  });
  assert.deepEqual(provenance.asc.detail, {
    reportType: "FINANCE_DETAIL", regionCode: "Z1", reportDate: "2026-12",
    sourcePeriod: { start: "08/30/2026", end: "09/26/2026" },
    period: { start: "2026-08-30", end: "2026-09-26" }, artifactSha256: fixture.detailSha,
    nativeReportId: { status: "not_returned", endpoint: "GET /v1/financeReports" },
  });
  assert.equal(provenance.asc.relationshipsSha256, fixture.relationshipsSha);
  assert.deepEqual(provenance.asc.receipts, [{
    receiptId: fixture.receiptId, currency: "JPY", occurredAt: "2026-09-12T00:00:00Z",
    settledAt: "2026-09-12T00:00:00Z", category: "settled_external_revenue",
  }]);
  assert.equal(provenance.revenuecat.status, "available");
  assert.equal(provenance.revenuecat.snapshotCount, 6);
  assert.equal(provenance.revenuecat.matchedSnapshotCount, 6);
  assert.deepEqual(provenance.revenuecat.currencies, ["USD"]);
  const rawRc = fixture.mobileReadback.revenuecat.rows[0];
  assert.deepEqual(provenance.revenuecat.snapshots[0], {
    productIdSha256: crypto.createHash("sha256").update(rawRc.product_id).digest("hex"),
    businessDate: "2026-09-25", evidenceSha256: rawRc.evidence_sha256,
    querySha256: rawRc.query_sha256, chartResponseSha256: rawRc.chart_response_sha256,
    observedAt: rawRc.observed_at, currency: "USD",
  });
  assert.equal(provenance.revenuecat.observedAtStart, "2026-09-25T00:00:00.000Z");
  assert.equal(provenance.revenuecat.observedAtEnd, "2026-09-30T00:00:00.000Z");
  assert.equal(provenance.revenuecat.mobileReadbackSha256, crypto.createHash("sha256").update(fixture.mobileText).digest("hex"));
  assert.equal(provenance.duplicateReceiptCount, 0);
  assert.equal(snapshot.sourceProvenanceSha256,
    crypto.createHash("sha256").update(canonicalJson(provenance)).digest("hex"));
  const resultState = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json"), "utf8"));
  assert.equal(resultState.b7ReadbackRef.sourceProvenanceSha256, snapshot.sourceProvenanceSha256);
  const stored = fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8");
  assert.doesNotMatch(stored, /private-vendor|private-subscription|product-[1-6]|\/private\//);
});

test("B7 provenance accepts a six-artifact ASC relationship bundle", async t => {
  const { options } = setup(t);
  options.collect = async () => b7Table("2026-09-30");
  const relationshipHashes = ["a", "b", "c", "d", "e", "f"].map(value => value.repeat(64));
  writeMobileProvenanceFixture(options, {
    mutatePacket: packet => {
      packet.relationships = { artifacts: relationshipHashes.map((artifactSha256, index) => ({
        artifact_path: `/private/relationships/${index + 1}.json`, artifact_sha256: artifactSha256,
      })) };
    },
    mutateMobile: mobile => {
      const receipt = mobile.mobile_records.find(row => row.provider === "app-store-connect-financial");
      receipt.evidence_refs[2] = `appstoreconnect://subscription-relationships/sha256/${relationshipHashes[1]}#data/1`;
      receipt.evidence_refs[3] = `appstoreconnect://subscription-relationships/sha256/${relationshipHashes[1]}#included/1`;
    },
  });

  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

  const snapshot = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
  assert.equal(snapshot.sourceProvenance.status, "verified");
  assert.equal(snapshot.sourceProvenance.asc.relationshipsSha256,
    "1a141a77e5da256ec7828216e93eacb33223ff29911e494efb495013bef9e6a7");
  assert.deepEqual(snapshot.sourceProvenance.asc.relationshipArtifactSha256s, relationshipHashes);
  assert.equal(snapshot.sourceProvenance.asc.receipts.length, 1);
  assert.doesNotMatch(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"),
    /\/private\/relationships\//);
});

test("B7 provenance rejects relationship data and included refs from different bundle artifacts", async t => {
  const { options } = setup(t);
  options.collect = async () => b7Table("2026-09-30");
  const relationshipHashes = ["a", "b", "c", "d", "e", "f"].map(value => value.repeat(64));
  writeMobileProvenanceFixture(options, {
    mutatePacket: packet => {
      packet.relationships = { artifacts: relationshipHashes.map((artifactSha256, index) => ({
        artifact_path: `/private/relationships/${index + 1}.json`, artifact_sha256: artifactSha256,
      })) };
    },
    mutateMobile: mobile => {
      const receipt = mobile.mobile_records.find(row => row.provider === "app-store-connect-financial");
      receipt.evidence_refs[2] = `appstoreconnect://subscription-relationships/sha256/${relationshipHashes[1]}#data/1`;
      receipt.evidence_refs[3] = `appstoreconnect://subscription-relationships/sha256/${relationshipHashes[2]}#included/1`;
    },
  });

  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

  const snapshot = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
  assert.equal(snapshot.sourceProvenance.status, "partial");
  assert.equal(snapshot.sourceProvenance.reason, "asc_receipt_evidence_mismatch");
  assert.deepEqual(snapshot.sourceProvenance.asc.receipts, []);
});

test("ASC packet in a non-private parent directory cannot be marked verified", async t => {
  const { options } = setup(t);
  options.collect = async () => b7Table("2026-09-30");
  writeMobileProvenanceFixture(options);
  fs.chmodSync(path.join(options.stateDir, "asc-input"), 0o755);

  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

  const snapshot = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
  assert.equal(snapshot.sourceProvenance.status, "unavailable");
  assert.equal(snapshot.sourceProvenance.reason, "asc_packet_unavailable");
});

test("same-count RevenueCat summaries require exact product, time, availability and evidence matches", async t => {
  const mutations = [
    ["product identity", row => { row.product_id = "unrelated-product"; }],
    ["provider availability", row => { row.availability = "unavailable"; }],
    ["observation time", row => { row.observed_at = "2026-09-25T00:01:00.000Z"; }],
    ["evidence hash", row => { row.evidence_sha256 = "0".repeat(64); }],
  ];
  for (const [name, mutateRow] of mutations) {
    const { options } = setup(t);
    options.collect = async () => b7Table("2026-09-30");
    writeMobileProvenanceFixture(options, { mutateMobile: mobile => mutateRow(mobile.revenuecat.rows[0]) });

    await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

    const snapshot = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
    assert.equal(snapshot.sourceProvenance.status, "partial", name);
    assert.equal(snapshot.sourceProvenance.reason, "revenuecat_snapshot_identity_mismatch", name);
    assert.equal(snapshot.sourceProvenance.revenuecat.matchedSnapshotCount, 5, name);
  }
});

test("noncanonical ASC receipt IDs and evidence refs are not persisted", async t => {
  const mutations = [
    ["receipt ID", receipt => { receipt.receipt_id = `private-canary:${receipt.receipt_id}`; }],
    ["evidence reference", receipt => { receipt.evidence_refs[0] = `private-canary:${receipt.evidence_refs[0]}`; }],
  ];
  for (const [name, mutateReceipt] of mutations) {
    const { options } = setup(t);
    options.collect = async () => b7Table("2026-09-30");
    writeMobileProvenanceFixture(options, { mutateMobile: mobile => {
      mutateReceipt(mobile.mobile_records.find(row => row.provider === "app-store-connect-financial"));
    } });

    await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

    const file = readbackFile(options.stateDir, options.occurrenceId);
    const snapshot = JSON.parse(fs.readFileSync(file, "utf8"));
    assert.equal(snapshot.sourceProvenance.status, "partial", name);
    assert.equal(snapshot.sourceProvenance.reason, "asc_receipt_evidence_mismatch", name);
    assert.deepEqual(snapshot.sourceProvenance.asc.receipts, [], name);
    assert.doesNotMatch(fs.readFileSync(file, "utf8"), /private-canary/, name);
  }
});

test("duplicate ASC receipts prevent verified provenance", async t => {
  const { options } = setup(t);
  options.collect = async () => b7Table("2026-09-30");
  writeMobileProvenanceFixture(options, { mutateMobile: mobile => {
    mobile.projection.duplicate_receipts = [{ provider: "app-store-connect-financial", receipt_id: "duplicate" }];
  } });

  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

  const snapshot = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
  assert.equal(snapshot.sourceProvenance.status, "partial");
  assert.equal(snapshot.sourceProvenance.reason, "duplicate_receipts_present");
  assert.equal(snapshot.sourceProvenance.duplicateReceiptCount, 1);
});

test("orphan B7 snapshot recovers after pending state rename failure without recollecting", async t => {
  const { options, messages } = setup(t);
  const table = b7Table("2026-09-30");
  let collects = 0;
  let successfulNotifies = 0;
  options.collect = async () => { collects += 1; return table; };
  options.notify = async input => {
    messages.push(input);
    successfulNotifies += 1;
    return { delivery: "delivered", provider_message_id: "recovered-after-crash",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 };
  };

  const reportFile = path.join(options.stateDir, "last-result-report.json");
  const renameSync = fs.renameSync;
  let failedPendingRename = false;
  fs.renameSync = function (source, target) {
    if (!failedPendingRename && target === reportFile) {
      failedPendingRename = true;
      throw new Error("injected pending state rename failure");
    }
    return renameSync.call(fs, source, target);
  };
  try {
    await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" }), /injected pending state rename failure/);
  } finally {
    fs.renameSync = renameSync;
  }

  assert.equal(failedPendingRename, true);
  assert.equal(collects, 1);
  assert.equal(successfulNotifies, 0);
  assert.equal(JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8")).status, "pending");

  const recovered = await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });
  assert.equal(recovered.status, "sent");
  assert.equal(collects, 1);
  assert.equal(successfulNotifies, 1);
  assert.equal(messages.length, 1);
  assert.deepEqual(JSON.parse(fs.readFileSync(reportFile, "utf8")).deliveryCounters, {
    attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0,
  });
  assert.deepEqual(JSON.parse(fs.readFileSync(reportFile, "utf8")).b7ReadbackRef, {
    path: `b7-readbacks/${options.occurrenceId}.json`,
    projectionSha256: crypto.createHash("sha256").update(canonicalJson(table)).digest("hex"),
    messageSha256: crypto.createHash("sha256").update(messages[0].message).digest("hex"),
    sourceProvenanceSha256: JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8")).sourceProvenanceSha256,
  });
});

test("late pending retry restores a sent sidecar receipt after sent-state rename failure", async t => {
  const { options, messages } = setup(t);
  let collects = 0;
  let notifyCalls = 0;
  options.collect = async date => { collects += 1; return b7Table(date); };
  options.notify = async input => {
    messages.push(input);
    notifyCalls += 1;
    return { delivery: "delivered", provider_message_id: "sent-before-state-crash",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 };
  };

  const reportFile = path.join(options.stateDir, "last-result-report.json");
  const sidecarFile = readbackFile(options.stateDir, options.occurrenceId);
  const renameSync = fs.renameSync;
  let reportRenames = 0;
  fs.renameSync = function (source, target) {
    if (target === reportFile && ++reportRenames === 2) {
      throw new Error("injected sent state rename failure");
    }
    return renameSync.call(fs, source, target);
  };
  try {
    await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" }), /injected sent state rename failure/);
  } finally {
    fs.renameSync = renameSync;
  }

  assert.equal(reportRenames, 2);
  assert.equal(collects, 1);
  assert.equal(notifyCalls, 1);
  assert.equal(JSON.parse(fs.readFileSync(reportFile, "utf8")).status, "pending");
  const sentSource = JSON.parse(fs.readFileSync(sidecarFile, "utf8"));
  assert.equal(sentSource.status, "sent");
  assert.equal(sentSource.providerMessageId, "sent-before-state-crash");

  const recovered = await runResultCfo({ ...options, occurrenceId: "life-manager-cfo-hourly:late-retry",
    now: "2026-10-01T12:01:00Z" });
  assert.equal(recovered.status, "quiet");
  assert.equal(recovered.resolutionKind, "duplicate");
  assert.equal(recovered.providerMessageId, "sent-before-state-crash");
  assert.equal(collects, 1);
  assert.equal(notifyCalls, 1);
  const finalState = JSON.parse(fs.readFileSync(reportFile, "utf8"));
  assert.equal(finalState.status, "sent");
  assert.equal(finalState.resolutionKind, "duplicate");
  assert.deepEqual(finalState.deliveryCounters, {
    attempted: 0, delivered: 0, delivery_uncertain: 0, pre_send_failed: 0,
  });
  assert.equal(finalState.providerMessageId, "sent-before-state-crash");
  assert.equal(finalState.occurrenceId, "life-manager-cfo-hourly:late-retry");
});

test("sent orphan snapshot restores its receipt without recollecting or notifying", async t => {
  const { options, messages } = setup(t);
  let collects = 0;
  options.collect = async date => { collects += 1; return b7Table(date); };
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" })).status, "sent");
  const reportFile = path.join(options.stateDir, "last-result-report.json");
  fs.unlinkSync(reportFile);

  await assert.rejects(runResultCfo({ ...options, env: { ...options.env, LIFE_MANAGER_RELEASE_SHA: "b".repeat(40) },
    now: "2026-09-30T12:00:00Z" }), /cfo_b7_snapshot_invalid/);
  await assert.rejects(runResultCfo({ ...options, reportEmail: "other@example.test",
    now: "2026-09-30T12:00:00Z" }), /cfo_b7_snapshot_invalid/);
  assert.equal(collects, 1);
  assert.equal(messages.length, 1);

  const recovered = await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });
  assert.equal(recovered.status, "sent");
  assert.equal(recovered.providerMessageId, "id");
  assert.equal(collects, 1);
  assert.equal(messages.length, 1);
  assert.equal(JSON.parse(fs.readFileSync(reportFile, "utf8")).providerMessageId, "id");
});

test("orphan snapshot with a changed projection fails closed before recollecting", async t => {
  const { options, messages } = setup(t);
  let collects = 0;
  options.collect = async date => { collects += 1; return b7Table(date); };
  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });
  fs.unlinkSync(path.join(options.stateDir, "last-result-report.json"));
  const file = readbackFile(options.stateDir, options.occurrenceId);
  const snapshot = JSON.parse(fs.readFileSync(file, "utf8"));
  snapshot.projection.economic_attribution.trailing.loops.capafy.coverage_gaps[0].reason = "changed";
  fs.writeFileSync(file, `${JSON.stringify(snapshot)}\n`, { mode: 0o600 });

  await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" }), /cfo_b7_snapshot_invalid/);

  assert.equal(collects, 1);
  assert.equal(messages.length, 1);
  assert.equal(fs.existsSync(path.join(options.stateDir, "last-result-report.json")), false);
});

test("pending notification keeps its B7 source pending and retry reuses it without recollecting", async t => {
  const { options, messages, change } = setup(t);
  const table = b7Table("2026-09-30");
  let collects = 0;
  options.collect = async () => { collects += 1; return table; };
  let attempts = 0;
  const beforeNotify = [];
  options.notify = async input => {
    messages.push(input);
    const snapshot = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
    beforeNotify.push({ status: snapshot.status, messageSha256: snapshot.messageSha256 });
    return ++attempts === 1
      ? { delivery: "pending", provider_message_id: null }
      : { delivery: "delivered", provider_message_id: "provider-message-2", attempted: 0,
        delivered: 0, delivery_uncertain: 0, pre_send_failed: 0 };
  };

  await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" }), /receipt_missing/);
  const file = readbackFile(options.stateDir, options.occurrenceId);
  const pending = JSON.parse(fs.readFileSync(file, "utf8"));
  assert.equal(pending.status, "pending");
  assert.equal(pending.providerMessageId, undefined);
  assert.equal(pending.resolutionKind, undefined);
  change("999");
  const retryOccurrence = "life-manager-cfo-hourly:retry-run";
  assert.equal((await runResultCfo({ ...options, occurrenceId: retryOccurrence,
    now: "2026-09-30T13:00:00Z" })).status, "quiet");

  const resolved = JSON.parse(fs.readFileSync(file, "utf8"));
  assert.equal(collects, 1);
  assert.deepEqual(beforeNotify, [
    { status: "pending", messageSha256: resolved.messageSha256 },
    { status: "pending", messageSha256: resolved.messageSha256 },
  ]);
  assert.deepEqual(resolved.projection, table);
  assert.equal(resolved.occurrenceId, options.occurrenceId);
  assert.equal(resolved.runId, "run-1");
  assert.equal(resolved.status, "pending");
  assert.equal(resolved.providerMessageId, undefined);
  assert.equal(resolved.resolutionKind, undefined);
  const currentReport = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json"), "utf8"));
  assert.equal(currentReport.occurrenceId, retryOccurrence);
  assert.equal(currentReport.status, "sent");
  assert.equal(currentReport.providerMessageId, "provider-message-2");
  assert.equal(currentReport.resolutionKind, "duplicate");
  assert.deepEqual(currentReport.deliveryCounters, {
    attempted: 0, delivered: 0, delivery_uncertain: 0, pre_send_failed: 0,
  });
  assert.equal(messages[0].message, messages[1].message);
  assert.equal(messages[0].eventKey, messages[1].eventKey);
});

test("stale pending snapshot without a sent receipt remains fenced", async t => {
  const { options, messages } = setup(t);
  let collects = 0;
  options.collect = async date => { collects += 1; return b7Table(date); };
  options.notify = async input => { messages.push(input); return { delivery: "pending" }; };

  await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" }), /receipt_missing/);
  await assert.rejects(runResultCfo({ ...options, occurrenceId: "life-manager-cfo-hourly:stale-retry",
    now: "2026-10-01T12:00:00Z" }), /cfo_pending_receipt_requires_reconcile/);

  assert.equal(collects, 1);
  assert.equal(messages.length, 1);
  assert.equal(JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8")).status, "pending");
});

test("same-period duplicate creates no new B7 source snapshot", async t => {
  const { options, messages } = setup(t);
  let collects = 0;
  options.collect = async date => { collects += 1; return b7Table(date); };
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" })).status, "sent");
  assert.equal((await runResultCfo({ ...options, occurrenceId: "life-manager-cfo-hourly:run-2",
    now: "2026-09-30T12:00:00Z" })).status, "quiet");
  assert.equal(collects, 1);
  assert.equal(messages.length, 1);
  assert.deepEqual(readbackFiles(options.stateDir), [`${options.occurrenceId}.json`]);
});

test("legacy pending delivery without a source snapshot retries without inventing one", async t => {
  const { options, messages } = setup(t);
  const date = "2026-09-30";
  const now = new Date("2026-09-30T12:00:00Z");
  const destinationHash = crypto.createHash("sha256").update(options.reportEmail).digest("hex");
  const message = "legacy pending report";
  fs.writeFileSync(path.join(options.stateDir, "last-result-report.json"), JSON.stringify({
    status: "pending", subjectId: options.subjectId, periodKey: `${date}:12`, reportingDate: date,
    channel: "email", recipientHash: destinationHash, eventKey: "legacy-event", message,
    messageSha256: crypto.createHash("sha256").update(message).digest("hex"),
    occurrenceId: options.occurrenceId, createdAt: now.toISOString(),
  }));
  let collects = 0;

  assert.equal((await runResultCfo({ ...options, now, collect: async () => { collects += 1; return b7Table(date); },
    notify: async input => { messages.push(input); return { delivery: "delivered", provider_message_id: "legacy-id",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 }; } })).status, "sent");

  assert.equal(collects, 0);
  assert.equal(messages[0].message, message);
  assert.deepEqual(readbackFiles(options.stateDir), []);
});

test("B7 readback directory symlink is rejected before notification", async t => {
  const { options } = setup(t);
  const outside = path.join(options.stateDir, "outside");
  fs.mkdirSync(outside);
  fs.symlinkSync(outside, path.join(options.stateDir, "b7-readbacks"), "dir");
  let notified = false;

  await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z",
    notify: async () => { notified = true; return { delivery: "delivered", provider_message_id: "id" }; } }),
  /cfo_b7_readback_path_invalid/);

  assert.equal(notified, false);
  assert.deepEqual(fs.readdirSync(outside), []);
});
test("hourly report has one receipt per hour, reflects new income next hour", async t => {
  const { options, messages, change } = setup(t);
  const first = await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });
  assert.equal(first.status, "sent");
  assert.equal(first.resolutionKind, "sent");
  const firstState = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json")));
  assert.equal(firstState.occurrenceId, options.occurrenceId);
  assert.match(firstState.messageSha256, /^[a-f0-9]{64}$/);
  assert.equal(firstState.resolutionKind, "sent");
  change("2");
  assert.equal((await runResultCfo({ ...options, occurrenceId: "life-manager-cfo-hourly:run-2",
    now: "2026-09-30T12:57:00Z" })).status, "quiet");
  assert.equal((await runResultCfo({ ...options, occurrenceId: "life-manager-cfo-hourly:run-3",
    now: "2026-09-30T13:00:00Z" })).status, "sent");
  assert.equal(messages.length, 2); assert.match(messages[1].message, /USD 2/);
  assert.notEqual(messages[0].eventKey, messages[1].eventKey);
});
test("daily cadence stays quiet; ambiguous send freezes text and original key", async t => {
  const { options, messages, change } = setup(t);
  let attempt = 0;
  const notify = async input => { messages.push(input); return ++attempt === 1
    ? { delivery: "pending" } : { delivery: "delivered", provider_message_id: "recovered",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 }; };
  await assert.rejects(runResultCfo({ ...options, notify, reportCadence: "daily", now: "2026-09-30T12:00:00Z" }), /receipt_missing/);
  change("999");
  assert.equal((await runResultCfo({ ...options, notify, reportCadence: "daily", now: "2026-09-30T13:00:00Z" })).status, "sent");
  assert.equal(messages[0].message, messages[1].message);
  assert.equal(messages[0].eventKey, messages[1].eventKey);
  await assert.rejects(
    runResultCfo({ ...options, reportCadence: "daily", now: "2026-09-30T14:00:00Z" }),
    /cfo_same_occurrence_replay_requires_reconcile/,
  );
  assert.equal(messages.length, 2);
});

test("cross-occurrence pending send binds the provider receipt to the delivery release", async t => {
  const { options } = setup(t);
  const deliveryOccurrenceId = "life-manager-cfo-hourly:run-2";
  const deliveryReleaseSha = "b".repeat(40);
  await assert.rejects(runResultCfo({ ...options,
    notify: async () => ({ delivery: "pending" }),
    now: "2026-09-30T12:00:00Z",
  }), /cfo_provider_receipt_missing/);

  await runResultCfo({ ...options,
    occurrenceId: deliveryOccurrenceId,
    env: { ...options.env, LIFE_MANAGER_RELEASE_SHA: deliveryReleaseSha },
    notify: async () => ({ delivery: "delivered", provider_message_id: "delivery-2",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 }),
    now: "2026-09-30T12:57:00Z",
  });

  const source = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
  assert.equal(source.status, "sent");
  assert.equal(source.occurrenceId, options.occurrenceId);
  assert.equal(source.deliveryOccurrenceId, deliveryOccurrenceId);
  assert.equal(source.deliveryReleaseSha, deliveryReleaseSha);
});

test("pending receipt cannot be silently retargeted", async t => {
  const { options } = setup(t);
  await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z", notify: async () => ({}) }));
  await assert.rejects(runResultCfo({ ...options, reportEmail: "other@example.test", now: "2026-09-30T13:00:00Z" }), /destination_changed/);
});

test("confirmed provider rejection is not reported as pre-send or sent", async t => {
  const { options } = setup(t);
  await assert.rejects(runResultCfo({
    ...options,
    notify: async () => ({ delivery: "pending", attempted: 1, delivered: 0,
      delivery_uncertain: 0, pre_send_failed: 0, provider_rejected: 1 }),
    now: "2026-09-30T12:00:00Z",
  }), /cfo_provider_rejected/);

  const snapshot = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
  assert.equal(snapshot.status, "pending");
});

test("wrong-day and broken source collection never send", async t => {
  const { options, messages } = setup(t);
  await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z", collect: async () => ({ reporting_date: "2026-09-29" }) }), /date_mismatch/);
  assert.equal(messages.length, 0);
});

test("same-period replay is quiet, keeps provider receipt, and rebinds current occurrence", async t => {
  const { options, messages } = setup(t);
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" })).status, "sent");
  const replay = await runResultCfo({
    ...options,
    occurrenceId: "life-manager-cfo-hourly:run-2",
    now: "2026-09-30T12:00:00Z",
  });
  assert.equal(replay.status, "quiet");
  assert.equal(replay.resolutionKind, "duplicate");
  const state = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json")));
  assert.equal(state.occurrenceId, "life-manager-cfo-hourly:run-2");
  assert.equal(state.providerMessageId, "id");
  assert.equal(state.resolutionKind, "duplicate");
  assert.deepEqual(state.deliveryCounters, {
    attempted: 0, delivered: 0, delivery_uncertain: 0, pre_send_failed: 0,
  });
  assert.match(state.messageSha256, /^[a-f0-9]{64}$/);
  await assert.rejects(
    runResultCfo({ ...options, subjectId: "other-owner", now: "2026-09-30T12:00:00Z" }),
    /subject_changed/,
  );
  assert.equal(messages.length, 1);
});

test("cross-occurrence recovery rejects malformed sent B7 provider IDs before persisting sent", async t => {
  const { options } = setup(t);
  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });
  const reportFile = path.join(options.stateDir, "last-result-report.json");
  const report = JSON.parse(fs.readFileSync(reportFile, "utf8"));
  report.status = "pending";
  delete report.resolutionKind;
  delete report.providerMessageId;
  delete report.sentAt;
  delete report.deliveryCounters;
  fs.writeFileSync(reportFile, JSON.stringify(report));
  const snapshotFile = readbackFile(options.stateDir, options.occurrenceId);
  const snapshot = JSON.parse(fs.readFileSync(snapshotFile, "utf8"));
  snapshot.providerMessageId = "malformed provider id";
  fs.writeFileSync(snapshotFile, JSON.stringify(snapshot));
  let notifications = 0;

  await assert.rejects(runResultCfo({ ...options, occurrenceId: "life-manager-cfo-hourly:run-2",
    notify: async () => { notifications += 1; return { delivery: "delivered", provider_message_id: "unexpected",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 }; },
    now: "2026-09-30T12:00:00Z" }), /cfo_b7_snapshot_invalid/);

  const pending = JSON.parse(fs.readFileSync(reportFile, "utf8"));
  assert.equal(pending.status, "pending");
  assert.equal(pending.occurrenceId, options.occurrenceId);
  assert.equal(notifications, 0);
});

test("B7 v4 with null delivery counters cannot recover as sent", async t => {
  const { options } = setup(t);
  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });
  const reportFile = path.join(options.stateDir, "last-result-report.json");
  const report = JSON.parse(fs.readFileSync(reportFile, "utf8"));
  report.status = "pending";
  delete report.resolutionKind;
  delete report.providerMessageId;
  delete report.sentAt;
  delete report.deliveryCounters;
  fs.writeFileSync(reportFile, JSON.stringify(report));
  const snapshotFile = readbackFile(options.stateDir, options.occurrenceId);
  const snapshot = JSON.parse(fs.readFileSync(snapshotFile, "utf8"));
  snapshot.deliveryCounters.attempted = null;
  fs.writeFileSync(snapshotFile, JSON.stringify(snapshot));
  let notifications = 0;

  await assert.rejects(runResultCfo({ ...options, notify: async () => {
    notifications += 1;
    return { delivery: "delivered", provider_message_id: "must-not-send",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 };
  }, now: "2026-09-30T12:00:00Z" }), /cfo_b7_snapshot_invalid/);

  assert.equal(notifications, 0);
  assert.equal(JSON.parse(fs.readFileSync(reportFile, "utf8")).status, "pending");
});

test("legacy sent B7 without counters cannot recover the same occurrence as sent", async t => {
  const { options } = setup(t);
  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });
  const reportFile = path.join(options.stateDir, "last-result-report.json");
  const report = JSON.parse(fs.readFileSync(reportFile, "utf8"));
  report.status = "pending";
  delete report.resolutionKind;
  delete report.providerMessageId;
  delete report.sentAt;
  delete report.deliveryCounters;
  fs.writeFileSync(reportFile, JSON.stringify(report));
  const snapshotFile = readbackFile(options.stateDir, options.occurrenceId);
  const snapshot = JSON.parse(fs.readFileSync(snapshotFile, "utf8"));
  snapshot.schemaVersion = 3;
  delete snapshot.deliveryCounters;
  fs.writeFileSync(snapshotFile, JSON.stringify(snapshot));
  let notifications = 0;

  await assert.rejects(runResultCfo({ ...options, notify: async () => {
    notifications += 1;
    return { delivery: "delivered", provider_message_id: "must-not-send",
      attempted: 1, delivered: 1, delivery_uncertain: 0, pre_send_failed: 0 };
  }, now: "2026-09-30T12:00:00Z" }), /cfo_b7_delivery_counters_unverified/);

  assert.equal(notifications, 0);
  assert.equal(JSON.parse(fs.readFileSync(reportFile, "utf8")).status, "pending");
});

test("same-occurrence sent report with invalid counters cannot become a quiet duplicate", async t => {
  const { options, messages } = setup(t);
  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });
  const reportFile = path.join(options.stateDir, "last-result-report.json");
  const report = JSON.parse(fs.readFileSync(reportFile, "utf8"));
  report.deliveryCounters.attempted = null;
  fs.writeFileSync(reportFile, JSON.stringify(report));

  await assert.rejects(
    runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" }),
    /cfo_result_delivery_counters_unverified/,
  );

  assert.equal(messages.length, 1);
  assert.equal(JSON.parse(fs.readFileSync(reportFile, "utf8")).resolutionKind, "sent");
});

test("same-occurrence duplicate receipt stays fenced for reconciliation", async t => {
  const { options, messages } = setup(t);
  let notifications = 0;
  const notify = async input => {
    messages.push(input);
    notifications += 1;
    return notifications === 1
      ? { delivery: "pending", provider_message_id: null }
      : { delivery: "delivered", provider_message_id: "id", attempted: 0,
        delivered: 0, delivery_uncertain: 0, pre_send_failed: 0 };
  };

  await assert.rejects(
    runResultCfo({ ...options, notify, now: "2026-09-30T12:00:00Z" }),
    /cfo_provider_receipt_missing/,
  );
  await assert.rejects(
    runResultCfo({ ...options, notify, now: "2026-09-30T12:01:00Z" }),
    /cfo_same_occurrence_duplicate_requires_reconcile/,
  );

  const report = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json"), "utf8"));
  const snapshot = JSON.parse(fs.readFileSync(readbackFile(options.stateDir, options.occurrenceId), "utf8"));
  assert.equal(report.status, "sent");
  assert.equal(report.resolutionKind, "duplicate");
  assert.deepEqual(report.deliveryCounters, {
    attempted: 0, delivered: 0, delivery_uncertain: 0, pre_send_failed: 0,
  });
  assert.equal(snapshot.status, "pending");
  assert.equal(snapshot.deliveryCounters, undefined);
  assert.equal(notifications, 2);
  assert.equal(messages.length, 2);
});

test("pending retry with an already-delivered outbox receipt is duplicate, not sent", async t => {
  const { options, messages } = setup(t);
  let attempt = 0;
  const notify = async input => {
    messages.push(input);
    attempt += 1;
    return attempt === 1
      ? { delivery: "pending", provider_message_id: null }
      : { delivery: "delivered", provider_message_id: "id", attempted: 0,
        delivered: 0, delivery_uncertain: 0, pre_send_failed: 0 };
  };
  await assert.rejects(
    runResultCfo({ ...options, notify, reportCadence: "daily", now: "2026-09-30T12:00:00Z" }),
    /receipt_missing/,
  );
  const result = await runResultCfo({
    ...options,
    notify,
    occurrenceId: "life-manager-cfo-hourly:retry-run",
    reportCadence: "daily",
    now: "2026-09-30T13:00:00Z",
  });
  assert.equal(result.status, "quiet");
  assert.equal(result.resolutionKind, "duplicate");
  const state = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json")));
  assert.equal(state.occurrenceId, "life-manager-cfo-hourly:retry-run");
  assert.equal(state.resolutionKind, "duplicate");
  assert.equal(state.providerMessageId, "id");
});

test("missing or malformed occurrence is rejected before report state is written", async t => {
  const { options } = setup(t);
  await assert.rejects(
    runResultCfo({ ...options, occurrenceId: undefined, now: "2026-09-30T12:00:00Z" }),
    /cfo_occurrence_invalid/,
  );
  await assert.rejects(
    runResultCfo({ ...options, occurrenceId: "wrong-owner:run-1", now: "2026-09-30T12:00:00Z" }),
    /cfo_occurrence_invalid/,
  );
  assert.equal(fs.existsSync(path.join(options.stateDir, "last-result-report.json")), false);
});

test("sent state rejects a different tenant in the next period", async t => {
  const { options, messages } = setup(t);
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" })).status, "sent");
  await assert.rejects(
    runResultCfo({ ...options, subjectId: "other-owner", now: "2026-09-30T13:00:00Z" }),
    /subject_changed/,
  );
  assert.equal(messages.length, 1);
});

test("pending delivery is bound to subjectId and rejects a different tenant", async t => {
  const { options, messages } = setup(t);
  await assert.rejects(
    runResultCfo({ ...options, notify: async input => {
      messages.push(input);
      return { delivery: "pending" };
    }, now: "2026-09-30T12:00:00Z" }),
    /receipt_missing/,
  );
  await assert.rejects(
    runResultCfo({ ...options, subjectId: "other-owner", now: "2026-09-30T13:00:00Z" }),
    /subject_changed/,
  );
  assert.equal(messages.length, 1);
});

test("hourly entrypoint forwards the host occurrence into the current result producer", () => {
  const source = fs.readFileSync(path.join(__dirname, "cfo-hourly-local.js"), "utf8");
  assert.match(source, /occurrenceId:\s*env\.LIFE_MANAGER_OCCURRENCE_ID/);
});
