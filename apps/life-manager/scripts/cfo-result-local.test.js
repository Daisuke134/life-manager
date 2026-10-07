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
    notify: async input => { messages.push(input); return { delivery: "delivered", provider_message_id: "id" }; } };
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

test("new occurrence persists the normalized B7 source bound to its delivered report receipt", async t => {
  const { options, messages } = setup(t);
  const table = b7Table("2026-09-30");
  options.collect = async () => table;
  options.notify = async input => {
    messages.push(input);
    return { delivery: "delivered", provider_message_id: "provider-message-1", raw: { Authorization: "do-not-save" } };
  };

  await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });

  const file = readbackFile(options.stateDir, options.occurrenceId);
  const snapshot = JSON.parse(fs.readFileSync(file, "utf8"));
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
  assert.equal(snapshot.providerMessageId, "provider-message-1");
  assert.equal(snapshot.resolutionKind, "sent");
  assert.equal(snapshot.deliveryOccurrenceId, options.occurrenceId);
  assert.ok(snapshot.sentAt);
  assert.equal(fs.statSync(path.dirname(file)).mode & 0o777, 0o700);
  assert.equal(fs.statSync(file).mode & 0o777, 0o600);
  assert.doesNotMatch(fs.readFileSync(file, "utf8"), /fixture-secret|do-not-save|API_TOKEN|Authorization|owner@example\.test/);
  assert.doesNotMatch(fs.readFileSync(path.join(options.stateDir, "last-result-report.json"), "utf8"), /fixture-secret|do-not-save/);
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
    return { delivery: "delivered", provider_message_id: "recovered-after-crash" };
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
  assert.deepEqual(JSON.parse(fs.readFileSync(reportFile, "utf8")).b7ReadbackRef, {
    path: `b7-readbacks/${options.occurrenceId}.json`,
    projectionSha256: crypto.createHash("sha256").update(canonicalJson(table)).digest("hex"),
    messageSha256: crypto.createHash("sha256").update(messages[0].message).digest("hex"),
  });
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
      : { delivery: "delivered", provider_message_id: "provider-message-2", attempted: 0 };
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
  assert.equal(resolved.deliveryOccurrenceId, retryOccurrence);
  assert.equal(resolved.deliveryRunId, "retry-run");
  assert.equal(resolved.status, "sent");
  assert.equal(resolved.providerMessageId, "provider-message-2");
  assert.equal(resolved.resolutionKind, "duplicate");
  assert.equal(messages[0].message, messages[1].message);
  assert.equal(messages[0].eventKey, messages[1].eventKey);
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
    notify: async input => { messages.push(input); return { delivery: "delivered", provider_message_id: "legacy-id" }; } })).status, "sent");

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
    ? { delivery: "pending" } : { delivery: "delivered", provider_message_id: "recovered" }; };
  await assert.rejects(runResultCfo({ ...options, notify, reportCadence: "daily", now: "2026-09-30T12:00:00Z" }), /receipt_missing/);
  change("999");
  assert.equal((await runResultCfo({ ...options, notify, reportCadence: "daily", now: "2026-09-30T13:00:00Z" })).status, "sent");
  assert.equal(messages[0].message, messages[1].message);
  assert.equal(messages[0].eventKey, messages[1].eventKey);
  assert.equal((await runResultCfo({ ...options, reportCadence: "daily", now: "2026-09-30T14:00:00Z" })).status, "quiet");
});
test("pending receipt cannot be silently retargeted", async t => {
  const { options } = setup(t);
  await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z", notify: async () => ({}) }));
  await assert.rejects(runResultCfo({ ...options, reportEmail: "other@example.test", now: "2026-09-30T13:00:00Z" }), /destination_changed/);
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
  assert.match(state.messageSha256, /^[a-f0-9]{64}$/);
  await assert.rejects(
    runResultCfo({ ...options, subjectId: "other-owner", now: "2026-09-30T12:00:00Z" }),
    /subject_changed/,
  );
  assert.equal(messages.length, 1);
});

test("pending retry with an already-delivered outbox receipt is duplicate, not sent", async t => {
  const { options, messages } = setup(t);
  let attempt = 0;
  const notify = async input => {
    messages.push(input);
    attempt += 1;
    return attempt === 1
      ? { delivery: "pending", provider_message_id: null }
      : { delivery: "delivered", provider_message_id: "id", attempted: 0 };
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
