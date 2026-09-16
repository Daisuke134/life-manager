"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createMinimalProductionOperations } = require("./connector-minimal-operations.js");

test("operations persist safe history and a positive every-wake Telegram receipt", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-operations-"));
  const sent = [];
  const claimFile = path.join(stateDir, "wake-report-send-claims.jsonl");
  const originalFsync = fs.fsyncSync;
  let fsyncs = 0;
  fs.fsyncSync = (fd) => { fsyncs += 1; return originalFsync(fd); };
  try {
    const operations = createMinimalProductionOperations({
      stateDir,
      wakeId: "wake-20260807-001",
      telegramTarget: "private-target",
      now: () => new Date("2026-08-07T08:30:00.000Z"),
      async sendMessage(message, options) {
        sent.push({ message, options });
        assert.equal(fs.existsSync(claimFile), true);
        assert.deepEqual(JSON.parse(fs.readFileSync(claimFile, "utf8").trim()), {
          schema_version: 1,
          wake_id: "wake-20260807-001",
          claimed_at: "2026-08-07T08:30:00.000Z",
        });
        return { ok: true, result: { message_id: 7001 } };
      },
    });

    await operations.recordAction({
      purpose: "readback",
      method: "provider_state",
      timestamp: "2026-08-07T08:29:59.000Z",
      result: "success",
      duration_ms: 25,
    });
    const first = await operations.reportWake({
      status: "circuit_open",
      safe_reason: "consecutive_failure_limit",
      consecutive_failure_count: 3,
    });
    const duplicate = await operations.reportWake({
      status: "circuit_open",
      safe_reason: "consecutive_failure_limit",
      consecutive_failure_count: 3,
    });

    assert.deepEqual(first, { telegram_provider_id: "7001" });
    assert.deepEqual(duplicate, first);
    assert.equal(sent.length, 1);
    assert.equal(sent[0].options.telegramTarget, "private-target");
    assert.equal(sent[0].options.idempotencyKey, "wake-20260807-001");
    assert.match(sent[0].message, /^Connector:::/);
    assert.match(sent[0].message, /circuit_open/);
    assert.doesNotMatch(sent[0].message, /private-target/);

    const historyFile = path.join(stateDir, "action-history.jsonl");
    const reportFile = path.join(stateDir, "wake-reports.jsonl");
    const deliveryFile = path.join(stateDir, "wake-report-deliveries.jsonl");
    const history = JSON.parse(fs.readFileSync(historyFile, "utf8").trim());
    const report = JSON.parse(fs.readFileSync(reportFile, "utf8").trim());
    const delivery = JSON.parse(fs.readFileSync(deliveryFile, "utf8").trim());
    assert.deepEqual(Object.keys(history).sort(), [
      "duration_ms", "method", "purpose", "result", "schema_version", "timestamp", "wake_id",
    ]);
    assert.deepEqual(Object.keys(report).sort(), [
      "consecutive_failure_count", "created_at", "safe_reason", "schema_version", "status", "wake_id",
    ]);
    assert.deepEqual(Object.keys(delivery).sort(), [
      "delivered_at", "schema_version", "telegram_provider_id", "wake_id",
    ]);
    assert.equal(JSON.stringify({ history, report, delivery }).includes("private-target"), false);
    assert.equal(fs.statSync(historyFile).mode & 0o777, 0o600);
    assert.equal(fs.statSync(reportFile).mode & 0o777, 0o600);
    assert.equal(fs.statSync(deliveryFile).mode & 0o777, 0o600);
    assert.equal(fs.statSync(claimFile).mode & 0o777, 0o600);
    assert.ok(fsyncs >= 1);
  } finally {
    fs.fsyncSync = originalFsync;
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("recordAction persists provider and stage safe_reason for a failed discovery action", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-action-context-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir,
      wakeId: "wake-20260816-connpass",
      telegramTarget: "private-target",
      now: () => new Date("2026-08-16T14:03:56.454Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7002 } }; },
    });

    await operations.recordAction({
      purpose: "observe",
      method: "provider_discovery",
      timestamp: "2026-08-16T14:03:56.454Z",
      result: "failed",
      duration_ms: 45971,
      provider: "connpass",
      safe_reason: "connpass_calendar_navigation_failed",
    });

    const historyFile = path.join(stateDir, "action-history.jsonl");
    const row = JSON.parse(fs.readFileSync(historyFile, "utf8").trim());
    assert.deepEqual(row, {
      schema_version: 1,
      wake_id: "wake-20260816-connpass",
      purpose: "observe",
      method: "provider_discovery",
      timestamp: "2026-08-16T14:03:56.454Z",
      result: "failed",
      duration_ms: 45971,
      provider: "connpass",
      safe_reason: "connpass_calendar_navigation_failed",
    });

    await assert.rejects(() => operations.recordAction({
      purpose: "observe",
      method: "provider_discovery",
      timestamp: "2026-08-16T14:03:56.454Z",
      result: "success",
      duration_ms: 100,
      provider: "connpass",
      safe_reason: "connpass_calendar_navigation_failed",
    }), "a success row must not carry provider/safe_reason context");

    await assert.rejects(() => operations.recordAction({
      purpose: "observe",
      method: "provider_discovery",
      timestamp: "2026-08-16T14:03:56.454Z",
      result: "failed",
      duration_ms: 100,
      provider: "Connpass",
      safe_reason: "connpass_calendar_navigation_failed",
    }), "an uppercase provider must be rejected");
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("recordAction persists a bounded error_class and rejects malformed or oversized values", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-error-class-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir,
      wakeId: "wake-20260817-connpass-class",
      telegramTarget: "private-target",
      now: () => new Date("2026-08-17T09:00:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7003 } }; },
    });

    await operations.recordAction({
      purpose: "observe",
      method: "provider_discovery",
      timestamp: "2026-08-17T09:00:00.000Z",
      result: "failed",
      duration_ms: 30021,
      provider: "connpass",
      safe_reason: "provider_discovery_failed",
      error_class: "TimeoutError",
    });

    const historyFile = path.join(stateDir, "action-history.jsonl");
    const row = JSON.parse(fs.readFileSync(historyFile, "utf8").trim());
    assert.deepEqual(row, {
      schema_version: 1,
      wake_id: "wake-20260817-connpass-class",
      purpose: "observe",
      method: "provider_discovery",
      timestamp: "2026-08-17T09:00:00.000Z",
      result: "failed",
      duration_ms: 30021,
      provider: "connpass",
      safe_reason: "provider_discovery_failed",
      error_class: "TimeoutError",
    });

    await assert.rejects(() => operations.recordAction({
      purpose: "observe",
      method: "provider_discovery",
      timestamp: "2026-08-17T09:00:01.000Z",
      result: "failed",
      duration_ms: 100,
      provider: "connpass",
      safe_reason: "provider_discovery_failed",
      error_class: "Type Error: boom",
    }), "an error_class containing spaces or a colon must be rejected");

    await assert.rejects(() => operations.recordAction({
      purpose: "observe",
      method: "provider_discovery",
      timestamp: "2026-08-17T09:00:02.000Z",
      result: "failed",
      duration_ms: 100,
      provider: "connpass",
      safe_reason: "provider_discovery_failed",
      error_class: "A".repeat(65),
    }), "an oversized error_class must be rejected");

    await assert.rejects(() => operations.recordAction({
      purpose: "observe",
      method: "provider_discovery",
      timestamp: "2026-08-17T09:00:03.000Z",
      result: "success",
      duration_ms: 100,
      error_class: "TimeoutError",
    }), "error_class must not appear on a success row");

    const rows = fs.readFileSync(historyFile, "utf8").trim().split("\n");
    assert.equal(rows.length, 1, "rejected rows must never be appended");
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("duplicate report uses stored created_at and rejects business-field drift", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-duplicate-"));
  let clock = Date.parse("2026-08-08T08:30:00.000Z"); const sent = [];
  const input = { status: "completed_no_effect", safe_reason: "providers_exhausted", consecutive_failure_count: 0 };
  const make = () => createMinimalProductionOperations({
    stateDir, wakeId: "wake-20260808-duplicate", telegramTarget: "private-target",
    now: () => new Date(clock += 1000), async sendMessage() { sent.push(true); return { ok: true, result: { message_id: 9201 } }; },
  });
  try {
    const operations = make(); await operations.reportWake(input); await operations.reportWake(input);
    assert.equal(sent.length, 1);
    const row = JSON.parse(fs.readFileSync(path.join(stateDir, "wake-reports.jsonl"), "utf8").trim());
    assert.equal(row.created_at, "2026-08-08T08:30:01.000Z");
    await assert.rejects(() => operations.reportWake({ ...input, safe_reason: "consecutive_failure_limit" }));
    assert.equal(sent.length, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("reportWake fails closed before send on malformed delivery rows", async () => {
  const report = { schema_version: 1, wake_id: "wake-20260808-delivery", status: "completed_no_effect", safe_reason: "providers_exhausted", consecutive_failure_count: 0, created_at: "2026-08-08T08:30:00.000Z" };
  const valid = { schema_version: 1, wake_id: report.wake_id, telegram_provider_id: "9301", delivered_at: report.created_at };
  const variants = [
    { ...valid, schema_version: 2 }, { ...valid, telegram_provider_id: "0" }, { ...valid, telegram_provider_id: 9 },
    { ...valid, wake_id: "x" }, { ...valid, delivered_at: "not-an-instant" },
  ];
  for (const delivery of variants) {
    const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-delivery-invalid-")); let sends = 0;
    try {
      fs.writeFileSync(path.join(stateDir, "wake-reports.jsonl"), `${JSON.stringify(report)}\n`, { mode: 0o600 });
      fs.writeFileSync(path.join(stateDir, "wake-report-deliveries.jsonl"), `${JSON.stringify(delivery)}\n`, { mode: 0o600 });
      const operations = createMinimalProductionOperations({ stateDir, wakeId: report.wake_id, telegramTarget: "private-target", now: () => new Date(report.created_at), async sendMessage() { sends += 1; return { ok: true, result: { message_id: 9302 } }; } });
      await assert.rejects(() => operations.reportWake(report)); assert.equal(sends, 0);
    } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
  }
});

test("claim-only wake is delivery-uncertain and never sends", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-claim-only-"));
  const wakeId = "wake-20260808-claim-only";
  const report = {
    schema_version: 1, wake_id: wakeId, status: "completed_no_effect", safe_reason: "providers_exhausted",
    consecutive_failure_count: 0, created_at: "2026-08-08T08:30:00.000Z",
  };
  const claim = { schema_version: 1, wake_id: wakeId, claimed_at: report.created_at };
  fs.writeFileSync(path.join(stateDir, "wake-reports.jsonl"), `${JSON.stringify(report)}\n`, { mode: 0o600 });
  fs.writeFileSync(path.join(stateDir, "wake-report-send-claims.jsonl"), `${JSON.stringify(claim)}\n`, { mode: 0o600 });
  let sends = 0;
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId, telegramTarget: "private-target", now: () => new Date(report.created_at),
      async sendMessage() { sends += 1; return { ok: true, result: { message_id: 7004 } }; },
    });
    await assert.rejects(() => operations.reportWake({
      status: report.status, safe_reason: report.safe_reason, consecutive_failure_count: report.consecutive_failure_count,
    }), /Telegram report delivery uncertain/);
    assert.equal(sends, 0);
    assert.equal(fs.existsSync(path.join(stateDir, "wake-report-deliveries.jsonl")), false);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("a later wake never resends one pending historical report", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-retry-"));
  try {
    const failed = createMinimalProductionOperations({
      stateDir,
      wakeId: "wake-20260807-failed",
      telegramTarget: "private-target",
      now: () => new Date("2026-08-07T08:30:00.000Z"),
      async sendMessage() { throw new Error("temporary transport failure"); },
    });
    await assert.rejects(() => failed.reportWake({
      status: "completed_no_effect",
      safe_reason: "providers_exhausted",
      consecutive_failure_count: 0,
    }));
    const reportFile = path.join(stateDir, "wake-reports.jsonl");
    const oldReport = fs.readFileSync(reportFile, "utf8").trim().split("\n")[0];

    const sent = [];
    const recovered = createMinimalProductionOperations({
      stateDir,
      wakeId: "wake-20260808-recovered",
      telegramTarget: "private-target",
      now: () => new Date("2026-08-08T08:30:00.000Z"),
      async sendMessage(message, options) {
        sent.push({ message, options });
        if (message.includes("providers_exhausted")) throw new Error("historical transport failure");
        return { ok: true, result: { message_id: 8001 } };
      },
    });
    const result = await recovered.reportWake({
      status: "circuit_open",
      safe_reason: "consecutive_failure_limit",
      consecutive_failure_count: 3,
    });

    assert.equal(sent.length, 1);
    assert.equal(sent[0].message.includes("consecutive_failure_limit"), true);
    assert.deepEqual(sent.map(({ options }) => options.idempotencyKey), ["wake-20260808-recovered"]);
    assert.deepEqual(result, { telegram_provider_id: "8001" });
    const deliveries = fs.readFileSync(
      path.join(stateDir, "wake-report-deliveries.jsonl"), "utf8",
    ).trim().split("\n").map(JSON.parse);
    assert.deepEqual(deliveries.map((row) => row.wake_id), ["wake-20260808-recovered"]);
    const reportLines = fs.readFileSync(reportFile, "utf8").trim().split("\n");
    assert.equal(reportLines[0], oldReport);
    assert.equal(reportLines.length, 2);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("uncertain wake report is durably quarantined and never retried", async () => {
  const cases = [
    ["transport", "transport", async () => { throw new Error("private transport failure"); }],
    ["delivery_unknown", "delivery_unknown", async () => ({ ok: false, delivery_unknown: true })],
    ["provider_rejection", "provider_rejection", async () => ({ ok: false, error_code: 400, description: "private provider detail" })],
    ["missing_message_id", "missing_message_id", async () => ({ ok: true, result: {} })],
    ["legacy_message_id", "missing_message_id", async () => ({ messageId: 7005 })],
  ];
  for (const [wakeLabel, reason, sendMessage] of cases) {
    const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-uncertain-"));
    let sends = 0;
    try {
      const operations = createMinimalProductionOperations({
        stateDir,
        wakeId: `wake-20260808-${wakeLabel}`,
        telegramTarget: "private-target",
        now: () => new Date("2026-08-08T08:30:00.000Z"),
        async sendMessage(message, options) {
          sends += 1;
          return sendMessage(message, options);
        },
      });
      const report = { status: "completed_no_effect", safe_reason: "providers_exhausted", consecutive_failure_count: 0 };
      await assert.rejects(() => operations.reportWake(report), /Telegram report delivery uncertain/);
      await assert.rejects(() => operations.reportWake(report), /Telegram report delivery uncertain/);
      assert.equal(sends, 1, reason);

      const uncertainFile = path.join(stateDir, "wake-report-uncertain.jsonl");
      const uncertain = JSON.parse(fs.readFileSync(uncertainFile, "utf8").trim());
      assert.equal(uncertain.wake_id, `wake-20260808-${wakeLabel}`);
      assert.equal(uncertain.reason, reason);
      assert.equal(uncertain.schema_version, 1);
      assert.doesNotMatch(JSON.stringify(uncertain), /private/);
      assert.equal(fs.existsSync(path.join(stateDir, "wake-report-deliveries.jsonl")), false);
    } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
  }
});

test("reportWake rejects duplicate or malformed historical report, delivery, claim, and quarantine rows", async () => {
  const currentWakeId = "wake-20260809-ledger-validation";
  const timestamp = "2026-08-09T08:30:00.000Z";
  const report = {
    schema_version: 1, wake_id: currentWakeId, status: "completed_no_effect", safe_reason: "providers_exhausted",
    consecutive_failure_count: 0, created_at: timestamp,
  };
  const delivery = { schema_version: 1, wake_id: currentWakeId, telegram_provider_id: "7006", delivered_at: timestamp };
  const claim = { schema_version: 1, wake_id: currentWakeId, claimed_at: timestamp };
  const uncertain = { schema_version: 1, wake_id: currentWakeId, reason: "transport", quarantined_at: timestamp };
  const cases = [
    ["wake-reports.jsonl", [report, report]],
    ["wake-reports.jsonl", [{ ...report, wake_id: "wake-20260809-old-schema", schema_version: 2 }]],
    ["wake-reports.jsonl", [{ ...report, wake_id: "wake-20260809-old", status: "not_a_status" }]],
    ["wake-report-deliveries.jsonl", [delivery, delivery]],
    ["wake-report-send-claims.jsonl", [claim, claim]],
    ["wake-report-uncertain.jsonl", [uncertain, uncertain]],
  ];
  for (const [fileName, rows] of cases) {
    const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-ledger-validation-"));
    let sends = 0;
    try {
      fs.writeFileSync(path.join(stateDir, fileName), `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, { mode: 0o600 });
      const operations = createMinimalProductionOperations({
        stateDir, wakeId: currentWakeId, telegramTarget: "private-target", now: () => new Date(timestamp),
        async sendMessage() { sends += 1; return { ok: true, result: { message_id: 7007 } }; },
      });
      await assert.rejects(() => operations.reportWake({
        status: report.status, safe_reason: report.safe_reason, consecutive_failure_count: report.consecutive_failure_count,
      }), /Connector minimal operations invalid/);
      assert.equal(sends, 0, fileName);
    } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
  }
});

test("reportWake keeps current failure hard without recovering historical reports", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-priority-"));
  const report = { status: "completed_no_effect", safe_reason: "providers_exhausted", consecutive_failure_count: 0 };
  const make = (wakeId, sendMessage) => createMinimalProductionOperations({
    stateDir, wakeId, telegramTarget: "private-target", now: () => new Date("2026-08-08T08:30:00.000Z"), sendMessage,
  });
  try {
    for (const wakeId of ["wake-20260807-old-1", "wake-20260807-old-2"]) {
      await assert.rejects(() => make(wakeId, async () => { throw new Error("transport failure"); }).reportWake(report));
    }
    const sent = [];
    const current = make("wake-20260808-current", async (message) => {
      sent.push(message); return { ok: true, result: { message_id: 9000 + sent.length } };
    });
    const first = await current.reportWake({ status: "circuit_open", safe_reason: "consecutive_failure_limit", consecutive_failure_count: 3 });
    assert.deepEqual(first, { telegram_provider_id: "9001" });
    assert.equal(sent.length, 1);

    const duplicateSent = [];
    const duplicate = make("wake-20260808-current", async (message) => {
      duplicateSent.push(message); return { ok: true, result: { message_id: 9100 + duplicateSent.length } };
    });
    assert.deepEqual(await duplicate.reportWake({ status: "circuit_open", safe_reason: "consecutive_failure_limit", consecutive_failure_count: 3 }), first);
    assert.equal(duplicateSent.length, 0);

    const hard = make("wake-20260808-hard", async () => { throw new Error("current transport failure"); });
    await assert.rejects(() => hard.reportWake(report));
    const deliveries = fs.readFileSync(path.join(stateDir, "wake-report-deliveries.jsonl"), "utf8").trim().split("\n").map(JSON.parse);
    assert.equal(deliveries.some((row) => row.wake_id === "wake-20260808-hard"), false);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("operations persist only safe Luma discovery aggregate counts", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-discovery-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir,
      wakeId: "wake-20260807-discovery",
      telegramTarget: "private-target",
      now: () => new Date("2026-08-07T08:30:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    await operations.recordDiscoveryAudit({
      observed_count: 37,
      normalized_count: 36,
      window_count: 12,
      free_open_count: 4,
      calendar_free_count: 2,
    });

    const file = path.join(stateDir, "luma-discovery-audits.jsonl");
    const row = JSON.parse(fs.readFileSync(file, "utf8").trim());
    assert.deepEqual(Object.keys(row).sort(), [
      "calendar_free_count", "free_open_count", "normalized_count", "observed_count",
      "recorded_at", "schema_version", "wake_id", "window_count",
    ]);
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.equal(JSON.stringify(row).includes("https://"), false);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("operations persist only safe Connpass discovery aggregate counts", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-connpass-discovery-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir,
      wakeId: "wake-20260810-connpass-discovery",
      telegramTarget: "private-target",
      now: () => new Date("2026-08-10T08:30:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    await operations.recordConnpassDiscoveryAudit({
      observed_count: 41,
      normalized_count: 40,
      window_count: 11,
      free_open_count: 3,
      calendar_free_count: 1,
    });

    const file = path.join(stateDir, "connpass-discovery-audits.jsonl");
    const row = JSON.parse(fs.readFileSync(file, "utf8").trim());
    assert.deepEqual(Object.keys(row).sort(), [
      "calendar_free_count", "free_open_count", "normalized_count", "observed_count",
      "recorded_at", "schema_version", "wake_id", "window_count",
    ]);
    assert.equal(row.wake_id, "wake-20260810-connpass-discovery");
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.equal(JSON.stringify(row).includes("https://"), false);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("operations persist only bounded ranking timing aggregates", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-ranking-audit-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-ranking-audit", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T05:00:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    const input = {
      schema_version: 1, request_count: 31, retry_count: 8, bisect_count: 4,
      total_request_ms: 571_020, max_request_ms: 45_000, elapsed_ms: 589_180,
    };
    await operations.recordRankingAudit(input);
    const file = path.join(stateDir, "ranking-audits.jsonl");
    const row = JSON.parse(fs.readFileSync(file, "utf8").trim());
    assert.deepEqual(row, {
      schema_version: 1, wake_id: "wake-ranking-audit", ...input,
      recorded_at: "2026-08-27T05:00:00.000Z",
    });
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    for (const malformed of [
      { ...input, prompt: "private" },
      { ...input, request_count: -1 },
      { ...input, retry_count: 32 },
      { ...input, max_request_ms: input.total_request_ms + 1 },
    ]) await assert.rejects(() => operations.recordRankingAudit(malformed));
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("Connpass discovery audit accepts a busy Tokyo listing and still bounds the count", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-connpass-busy-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir,
      wakeId: "wake-20260816-connpass-busy",
      telegramTarget: "private-target",
      now: () => new Date("2026-08-16T14:04:21.714Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    const busy = { observed_count: 767, normalized_count: 40, window_count: 40, free_open_count: 29, calendar_free_count: 7 };
    await operations.recordConnpassDiscoveryAudit(busy);

    const file = path.join(stateDir, "connpass-discovery-audits.jsonl");
    const row = JSON.parse(fs.readFileSync(file, "utf8").trim());
    assert.deepEqual(
      [row.observed_count, row.normalized_count, row.window_count, row.free_open_count, row.calendar_free_count],
      [767, 40, 40, 29, 7],
      "a real, measured 767-observed listing must be accepted and written",
    );

    await assert.rejects(() => operations.recordConnpassDiscoveryAudit({
      ...busy, window_count: 41,
    }), "window_count exceeding normalized_count must still be rejected");

    await assert.rejects(() => operations.recordConnpassDiscoveryAudit({
      ...busy, observed_count: 5_001,
    }), "a count above the new ceiling must still be rejected");
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("operations persist only safe Peatix discovery aggregate counts", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-peatix-discovery-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-20260810-peatix-discovery", telegramTarget: "private-target",
      now: () => new Date("2026-08-10T08:30:00.000Z"), async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    await operations.recordPeatixDiscoveryAudit({
      observed_count: 41, normalized_count: 40, window_count: 11, free_open_count: 3, calendar_free_count: 1,
    });
    await assert.rejects(() => operations.recordPeatixDiscoveryAudit({
      observed_count: 1, normalized_count: 2, window_count: 1, free_open_count: 1, calendar_free_count: 1,
    }));

    const file = path.join(stateDir, "peatix-discovery-audits.jsonl");
    const lines = fs.readFileSync(file, "utf8").trim().split("\n");
    const row = JSON.parse(lines[0]);
    assert.equal(lines.length, 1);
    assert.deepEqual(Object.keys(row).sort(), [
      "calendar_free_count", "free_open_count", "normalized_count", "observed_count",
      "recorded_at", "schema_version", "wake_id", "window_count",
    ]);
    assert.equal(row.wake_id, "wake-20260810-peatix-discovery");
    assert.equal(row.recorded_at, "2026-08-10T08:30:00.000Z");
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.doesNotMatch(JSON.stringify(row), /https?:\/\/|5075819|title|ticket|profile/i);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("operations persist only safe Meetup discovery aggregate counts", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-meetup-discovery-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-20260811-meetup-discovery", telegramTarget: "private-target",
      now: () => new Date("2026-08-11T08:30:00.000Z"), async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    await operations.recordMeetupDiscoveryAudit({
      observed_count: 48, normalized_count: 47, window_count: 14, free_open_count: 12, calendar_free_count: 0,
    });
    await assert.rejects(() => operations.recordMeetupDiscoveryAudit({
      observed_count: 48, normalized_count: 49, window_count: 14, free_open_count: 12, calendar_free_count: 0,
    }));

    const file = path.join(stateDir, "meetup-discovery-audits.jsonl");
    const lines = fs.readFileSync(file, "utf8").trim().split("\n");
    const row = JSON.parse(lines[0]);
    assert.equal(lines.length, 1);
    assert.deepEqual(Object.keys(row).sort(), [
      "calendar_free_count", "free_open_count", "normalized_count", "observed_count",
      "recorded_at", "schema_version", "wake_id", "window_count",
    ]);
    assert.equal(row.schema_version, 1);
    assert.equal(row.wake_id, "wake-20260811-meetup-discovery");
    assert.deepEqual([row.observed_count, row.normalized_count, row.window_count, row.free_open_count, row.calendar_free_count], [48, 47, 14, 12, 0]);
    assert.equal(row.recorded_at, "2026-08-11T08:30:00.000Z");
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.doesNotMatch(JSON.stringify(row), /https?:\/\/|event|title|profile|ticket|auth|private|attendee/i);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("operations persist only safe Doorkeeper discovery aggregate counts", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-doorkeeper-discovery-"));
  const valid = {
    discovered_count: 100,
    within_window_count: 12,
    eligible_count: 8,
    calendar_free_count: 0,
    selected_count: 0,
  };
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-20260811-doorkeeper-discovery", telegramTarget: "private-target",
      now: () => new Date("2026-08-11T08:30:00.000Z"), async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    assert.equal(Object.isFrozen(operations), true);
    await operations.recordDoorkeeperDiscoveryAudit(valid);

    const file = path.join(stateDir, "doorkeeper-discovery-audits.jsonl");
    const lines = fs.readFileSync(file, "utf8").trim().split("\n");
    const row = JSON.parse(lines[0]);
    assert.equal(lines.length, 1);
    assert.deepEqual(Object.keys(row).sort(), [
      "calendar_free_count", "discovered_count", "eligible_count", "recorded_at", "schema_version",
      "selected_count", "wake_id", "within_window_count",
    ]);
    assert.deepEqual(row, {
      schema_version: 1,
      wake_id: "wake-20260811-doorkeeper-discovery",
      discovered_count: 100,
      within_window_count: 12,
      eligible_count: 8,
      calendar_free_count: 0,
      selected_count: 0,
      recorded_at: "2026-08-11T08:30:00.000Z",
    });
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.doesNotMatch(JSON.stringify(row), /https?:\/\/|private-target|attendee|email|title/i);

    const { selected_count: _selectedCount, ...missingKey } = valid;
    const invalidInputs = [
      { ...valid, calendar_free_count: 9 },
      { ...valid, private_url: "https://private.example/fixture" },
      missingKey,
      { ...valid, selected_count: 0.5 },
      { ...valid, discovered_count: -1 },
      { ...valid, discovered_count: 801 },
      { ...valid, selected_count: "0" },
      [],
      null,
    ];
    for (const input of invalidInputs) {
      await assert.rejects(() => operations.recordDoorkeeperDiscoveryAudit(input));
    }
    assert.equal(fs.readFileSync(file, "utf8").trim().split("\n").length, 1);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("operations persist only safe Eventbrite discovery aggregate counts", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-eventbrite-discovery-"));
  const valid = { discovered_count: 100, within_window_count: 12, eligible_count: 8, calendar_free_count: 2, selected_count: 1 };
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-20260811-eventbrite-discovery", telegramTarget: "private-target",
      now: () => new Date("2026-08-11T08:30:00.000Z"), async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    assert.equal(typeof operations.recordEventbriteDiscoveryAudit, "function");
    await operations.recordEventbriteDiscoveryAudit(valid);
    const file = path.join(stateDir, "eventbrite-discovery-audits.jsonl");
    const lines = fs.readFileSync(file, "utf8").trim().split("\n");
    const row = JSON.parse(lines[0]);
    assert.equal(lines.length, 1);
    assert.deepEqual(Object.keys(row).sort(), ["calendar_free_count", "discovered_count", "eligible_count", "recorded_at", "schema_version", "selected_count", "wake_id", "within_window_count"]);
    assert.deepEqual(row, { schema_version: 1, wake_id: "wake-20260811-eventbrite-discovery", ...valid, recorded_at: "2026-08-11T08:30:00.000Z" });
    assert.equal(row.schema_version, 1);
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.doesNotMatch(JSON.stringify(row), /https?:\/\/|private-target|attendee|email|title/i);

    const { selected_count: _selectedCount, ...missingKey } = valid;
    for (const input of [
      { ...valid, calendar_free_count: 9 }, { ...valid, private_url: "https://private.example/fixture" }, missingKey,
      { ...valid, selected_count: 0.5 }, { ...valid, discovered_count: -1 }, { ...valid, discovered_count: 801 },
      { ...valid, selected_count: "1" }, [], null,
    ]) await assert.rejects(() => operations.recordEventbriteDiscoveryAudit(input));
    assert.equal(fs.readFileSync(file, "utf8").trim().split("\n").length, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("operations persist only safe TECH PLAY discovery aggregate counts", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-techplay-discovery-"));
  const valid = { discovered_count: 50, rss_count: 50, processed_count: 20, pending_count: 30,
    saturated_count: 0, within_window_count: 12, eligible_count: 8,
    calendar_free_count: 2, selected_count: 1 };
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-20260812-techplay-discovery", telegramTarget: "private-target",
      now: () => new Date("2026-08-12T08:30:00.000Z"), async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    assert.equal(Object.isFrozen(operations), true);
    assert.equal(typeof operations.recordTechPlayDiscoveryAudit, "function");
    await operations.recordTechPlayDiscoveryAudit(valid);
    const file = path.join(stateDir, "techplay-discovery-audits.jsonl");
    const lines = fs.readFileSync(file, "utf8").trim().split("\n");
    const row = JSON.parse(lines[0]);
    assert.equal(lines.length, 1);
    assert.deepEqual(row, { schema_version: 1, wake_id: "wake-20260812-techplay-discovery", ...valid, recorded_at: "2026-08-12T08:30:00.000Z" });
    assert.deepEqual(Object.keys(row).sort(), ["calendar_free_count", "discovered_count", "eligible_count", "pending_count", "processed_count", "recorded_at", "rss_count", "saturated_count", "schema_version", "selected_count", "wake_id", "within_window_count"]);
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.doesNotMatch(JSON.stringify(row), /https?:\/\/|private-target|title|ticket|profile|auth|email/i);

    const { selected_count: _selectedCount, ...missingKey } = valid;
    for (const input of [
      { ...valid, private_url: "https://private.example/fixture" }, missingKey,
      { ...valid, selected_count: 0.5 }, { ...valid, discovered_count: -1 }, { ...valid, discovered_count: 801 },
      { ...valid, processed_count: 51 }, { ...valid, pending_count: 51 },
      { ...valid, rss_count: 51 },
      { ...valid, saturated_count: 2 },
      { ...valid, calendar_free_count: 9 }, { ...valid, within_window_count: 51 }, [], null,
    ]) await assert.rejects(() => operations.recordTechPlayDiscoveryAudit(input));
    assert.equal(fs.readFileSync(file, "utf8").trim().split("\n").length, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("Connector durably records exact host occurrence target before an effect", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-effect-intent-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-effect-intent-123", telegramTarget: "private-target",
      occurrenceId: "life-manager-connector-native:run-123",
      now: () => new Date("2026-08-12T08:30:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    await operations.recordEffectIntent({ effect_kind: "registration",
      effect_url: "https://techplay.jp/event/999180",
      candidate: { provider: "techplay", event_ref: "techplay-event://event/999180",
        canonical_url: "https://techplay.jp/event/999180", title: "Tokyo event",
        starts_at: "2026-08-20T09:00:00.000Z", ends_at: "2026-08-20T10:00:00.000Z",
        ticket_id: "12345", registration_status: "available",
        ticket_price_status: "free", ticket_price_minor: 0,
        talk_pack: { private_bio: "must-not-persist" } } });
    await operations.recordEffectIntent({ effect_kind: "registration",
      effect_url: "https://luma.com/second",
      candidate: { provider: "luma", event_ref: "luma-event://event/second",
        canonical_url: "https://luma.com/second", title: "Another event",
        starts_at: "2026-08-20T09:00:00.000Z", ends_at: "2026-08-20T10:00:00.000Z" } });
    const [name] = fs.readdirSync(path.join(stateDir, "effect-intents"));
    const file = path.join(stateDir, "effect-intents", name);
    const rows = fs.readFileSync(file, "utf8").trim().split("\n").map(JSON.parse);
    const row = rows[0];
    assert.deepEqual(row, {
      schema_version: 1, occurrence_id: "life-manager-connector-native:run-123",
      wake_id: "wake-effect-intent-123", provider: "techplay",
      event_ref: "techplay-event://event/999180",
      canonical_url: "https://techplay.jp/event/999180",
      effect_kind: "registration", effect_url: "https://techplay.jp/event/999180",
      readback_candidate: { provider: "techplay", event_ref: "techplay-event://event/999180",
        canonical_url: "https://techplay.jp/event/999180", title: "Tokyo event",
        starts_at: "2026-08-20T09:00:00.000Z", ends_at: "2026-08-20T10:00:00.000Z",
        ticket_id: "12345", registration_status: "available",
        ticket_price_status: "free", ticket_price_minor: 0 },
      recorded_at: "2026-08-12T08:30:00.000Z",
    });
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.equal(rows.length, 2);
    assert.equal(rows[1].occurrence_id, row.occurrence_id);
    assert.equal(rows[1].event_ref, "luma-event://event/second");
    assert.deepEqual(await operations.listEffectIntents(row.occurrence_id), rows);
    assert.deepEqual(await operations.listEffectIntents("life-manager-connector-native:other"), []);
    assert.doesNotMatch(JSON.stringify(row), /private-target|must-not-persist|token|password|email/i);
    fs.appendFileSync(file, '{"unexpected":"row"}\n');
    await assert.rejects(() => operations.listEffectIntents(row.occurrence_id));
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("Connector freezes every intent only after exact outer terminal", async () => {
  const hostRoot = fs.mkdtempSync(path.join(os.tmpdir(), "connector-closed-intents-"));
  const stateDir = path.join(hostRoot, "connector-native");
  const priorHostRoot = process.env.LIFE_MANAGER_STATE_ROOT;
  process.env.LIFE_MANAGER_STATE_ROOT = hostRoot;
  const occurrenceId = "life-manager-connector-native:run-closed-123";
  const releaseSha = "b".repeat(40);
  const terminal = { version: 1, event_id: "a".repeat(24), timestamp: "2026-08-12T08:31:00.000Z",
    loop_id: "life-manager-connector-native", run_id: "run-closed-123",
    release_sha: releaseSha, phase: "report", status: "fail",
    domain: "system", effect_class: "none", effect_status: "not_applicable",
    blocker: "wake_deadline", provider: "deterministic", profile_alias: null,
    evidence_refs: ["lm-loop://life-manager-connector-native/run-closed-123/summary.json"] };
  try {
    fs.writeFileSync(path.join(hostRoot, "events.jsonl"), `${JSON.stringify(terminal)}\n`, "utf8");
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-closed-123", occurrenceId,
      telegramTarget: "private-target", now: () => new Date("2026-08-12T08:30:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    await assert.rejects(() => operations.prepareEffectFence(occurrenceId, releaseSha));
    assert.equal(fs.existsSync(path.join(stateDir, "effect-fences")), false);
    for (const event of ["first", "second"]) {
      await operations.recordEffectIntent({ effect_kind: "registration",
        effect_url: `https://luma.com/${event}`,
        candidate: { provider: "luma", event_ref: `luma-event://event/${event}`,
          canonical_url: `https://luma.com/${event}` } });
    }
    const redirected = path.join(hostRoot, "redirected-fences");
    fs.mkdirSync(redirected);
    const directory = path.join(stateDir, "effect-fences");
    fs.symlinkSync(redirected, directory);
    await assert.rejects(() => operations.prepareEffectFence(occurrenceId, releaseSha));
    assert.deepEqual(fs.readdirSync(redirected), []);
    fs.unlinkSync(directory);
    const [receipt, parallelReceipt] = await Promise.all([
      operations.prepareEffectFence(occurrenceId, releaseSha),
      operations.prepareEffectFence(occurrenceId, releaseSha),
    ]);
    assert.deepEqual(parallelReceipt, receipt);
    assert.equal(receipt?.occurrence_id, occurrenceId);
    assert.equal(receipt?.intents_count, 2);
    assert.equal(receipt?.terminal_event_id, terminal.event_id);
    assert.match(receipt?.intents_sha256, /^[0-9a-f]{64}$/);
    const files = fs.readdirSync(directory);
    assert.equal(files.length, 1);
    const stored = JSON.parse(fs.readFileSync(path.join(directory, files[0]), "utf8"));
    assert.equal(stored.status, "active");
    assert.deepEqual(stored.intents.map((row) => row.event_ref), [
      "luma-event://event/first", "luma-event://event/second",
    ]);
    assert.deepEqual(await operations.prepareEffectFence(occurrenceId, releaseSha), receipt);
    await assert.rejects(() => operations.recordEffectIntent({ effect_kind: "registration",
      effect_url: "https://luma.com/late",
      candidate: { provider: "luma", event_ref: "luma-event://event/late",
        canonical_url: "https://luma.com/late" } }));
    const fenceFile = path.join(directory, files[0]);
    fs.writeFileSync(fenceFile, "null\n", "utf8");
    await assert.rejects(() => operations.prepareEffectFence(occurrenceId, releaseSha));
    assert.equal(fs.readFileSync(fenceFile, "utf8"), "null\n");
  } finally {
    if (priorHostRoot == null) delete process.env.LIFE_MANAGER_STATE_ROOT;
    else process.env.LIFE_MANAGER_STATE_ROOT = priorHostRoot;
    fs.rmSync(hostRoot, { recursive: true, force: true });
  }
});

test("Connector cannot activate a fence from an injected terminal claim", async () => {
  const hostRoot = fs.mkdtempSync(path.join(os.tmpdir(), "connector-false-terminal-"));
  const priorHostRoot = process.env.LIFE_MANAGER_STATE_ROOT;
  process.env.LIFE_MANAGER_STATE_ROOT = hostRoot;
  const occurrenceId = "life-manager-connector-native:run-no-terminal";
  const releaseSha = "b".repeat(40);
  try {
    const operations = createMinimalProductionOperations({
      stateDir: path.join(hostRoot, "connector-native"), occurrenceId,
      wakeId: "wake-no-terminal", telegramTarget: "private-target",
      now: () => new Date("2026-08-12T08:30:00.000Z"),
      readOuterTerminal: async () => ({ ok: true, terminal: {
        event_id: "a".repeat(24), timestamp: "2026-08-12T08:31:00.000Z",
        loop_id: "life-manager-connector-native", run_id: "run-no-terminal",
        release_sha: releaseSha, phase: "report", status: "fail",
        provider: "deterministic", profile_alias: null,
        evidence_refs: ["lm-loop://life-manager-connector-native/run-no-terminal/summary.json"],
      } }),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    await operations.recordEffectIntent({ effect_kind: "registration",
      effect_url: "https://luma.com/no-terminal",
      candidate: { provider: "luma", event_ref: "luma-event://event/no-terminal",
        canonical_url: "https://luma.com/no-terminal" } });
    await assert.rejects(() => operations.prepareEffectFence(occurrenceId, releaseSha));
    assert.equal(fs.existsSync(path.join(hostRoot, "connector-native", "effect-fences")), false);
  } finally {
    if (priorHostRoot == null) delete process.env.LIFE_MANAGER_STATE_ROOT;
    else process.env.LIFE_MANAGER_STATE_ROOT = priorHostRoot;
    fs.rmSync(hostRoot, { recursive: true, force: true });
  }
});

test("Connector's next occurrence is not blocked by an oversized older intent journal", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-intent-isolation-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-new-occurrence", telegramTarget: "private-target",
      occurrenceId: "life-manager-connector-native:run-new-occurrence",
      now: () => new Date("2026-08-12T08:30:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    const legacyJournal = path.join(stateDir, "effect-intents.jsonl");
    fs.writeFileSync(legacyJournal, "x", { mode: 0o600 });
    fs.truncateSync(legacyJournal, 5_000_001);
    await operations.recordEffectIntent({ effect_kind: "registration",
      effect_url: "https://luma.com/new-occurrence",
      candidate: { provider: "luma", event_ref: "luma-event://event/new-occurrence",
        canonical_url: "https://luma.com/new-occurrence" } });
    const rows = await operations.listEffectIntents("life-manager-connector-native:run-new-occurrence");
    assert.equal(rows.length, 1);
    assert.equal(rows[0].event_ref, "luma-event://event/new-occurrence");
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("Connector can reopen a valid fence larger than one megabyte", async () => {
  const hostRoot = fs.mkdtempSync(path.join(os.tmpdir(), "connector-large-fence-"));
  const priorHostRoot = process.env.LIFE_MANAGER_STATE_ROOT;
  process.env.LIFE_MANAGER_STATE_ROOT = hostRoot;
  const occurrenceId = "life-manager-connector-native:run-large-fence";
  const releaseSha = "b".repeat(40);
  try {
    fs.writeFileSync(path.join(hostRoot, "events.jsonl"), `${JSON.stringify({
      version: 1, event_id: "a".repeat(24), timestamp: "2026-08-12T08:31:00.000Z",
      loop_id: "life-manager-connector-native", run_id: "run-large-fence",
      release_sha: releaseSha, phase: "report", status: "fail", domain: "system",
      effect_class: "none", effect_status: "not_applicable", blocker: "wake_deadline",
      provider: "deterministic", profile_alias: null,
      evidence_refs: ["lm-loop://life-manager-connector-native/run-large-fence/summary.json"],
    })}\n`, "utf8");
    const stateDir = path.join(hostRoot, "connector-native");
    const operations = createMinimalProductionOperations({
      stateDir, occurrenceId, wakeId: "wake-large-fence", telegramTarget: "private-target",
      now: () => new Date("2026-08-12T08:30:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    await operations.recordEffectIntent({ effect_kind: "registration",
      effect_url: "https://luma.com/large-fence",
      candidate: { provider: "luma", event_ref: "luma-event://event/large-fence",
        canonical_url: "https://luma.com/large-fence", venue_address: "A".repeat(2000) } });
    const intentDir = path.join(stateDir, "effect-intents");
    const intentFile = path.join(intentDir, fs.readdirSync(intentDir)[0]);
    const row = fs.readFileSync(intentFile, "utf8");
    fs.appendFileSync(intentFile, row.repeat(510));
    const first = await operations.prepareEffectFence(occurrenceId, releaseSha);
    assert.ok(first.intents_count > 500);
    assert.deepEqual(await operations.prepareEffectFence(occurrenceId, releaseSha), first);
  } finally {
    if (priorHostRoot == null) delete process.env.LIFE_MANAGER_STATE_ROOT;
    else process.env.LIFE_MANAGER_STATE_ROOT = priorHostRoot;
    fs.rmSync(hostRoot, { recursive: true, force: true });
  }
});

test("Connector stops before effect when one occurrence journal reaches its bound", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-intent-bound-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-intent-bound", telegramTarget: "private-target",
      occurrenceId: "life-manager-connector-native:run-intent-bound",
      now: () => new Date("2026-08-12T08:30:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    const input = { effect_kind: "registration", effect_url: "https://luma.com/bound",
      candidate: { provider: "luma", event_ref: "luma-event://event/bound",
        canonical_url: "https://luma.com/bound" } };
    await operations.recordEffectIntent(input);
    const directory = path.join(stateDir, "effect-intents");
    const file = path.join(directory, fs.readdirSync(directory)[0]);
    fs.truncateSync(file, 4_999_900);
    await assert.rejects(() => operations.recordEffectIntent(input));
    assert.equal(fs.statSync(file).size, 4_999_900);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("Connector refuses a first effect intent when its directory sync fails", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-intent-dir-sync-"));
  const originalFsync = fs.fsyncSync;
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-intent-dir-sync", telegramTarget: "private-target",
      occurrenceId: "life-manager-connector-native:run-dir-sync",
      now: () => new Date("2026-08-12T08:30:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    fs.fsyncSync = (fd) => {
      if (fs.fstatSync(fd).isDirectory()) throw new Error("directory sync unavailable");
      return originalFsync(fd);
    };
    await assert.rejects(() => operations.recordEffectIntent({
      effect_kind: "registration", effect_url: "https://luma.com/durable",
      candidate: { provider: "luma", event_ref: "luma-event://event/durable",
        canonical_url: "https://luma.com/durable" },
    }), /directory sync unavailable/);
    await assert.rejects(() => operations.recordEffectIntent({
      effect_kind: "registration", effect_url: "https://luma.com/durable",
      candidate: { provider: "luma", event_ref: "luma-event://event/durable",
        canonical_url: "https://luma.com/durable" },
    }), /directory sync unavailable/);
  } finally {
    fs.fsyncSync = originalFsync;
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("Connector refuses a state directory whose parent cannot be synced", () => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), "connector-state-parent-sync-"));
  const stateDir = path.join(parent, "connector-native");
  const parentInode = fs.statSync(parent).ino;
  const originalFsync = fs.fsyncSync;
  try {
    fs.fsyncSync = (fd) => {
      const stat = fs.fstatSync(fd);
      if (stat.isDirectory() && stat.ino === parentInode) throw new Error("state parent sync unavailable");
      return originalFsync(fd);
    };
    const create = () => createMinimalProductionOperations({
      stateDir, wakeId: "wake-state-parent-sync", telegramTarget: "private-target",
      occurrenceId: "life-manager-connector-native:run-parent-sync",
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    assert.throws(create, /state parent sync unavailable/);
    assert.throws(create, /state parent sync unavailable/);
  } finally {
    fs.fsyncSync = originalFsync;
    fs.rmSync(parent, { recursive: true, force: true });
  }
});

test("Connector refuses recursively created state ancestors without durable parent entries", () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "connector-state-ancestor-sync-"));
  const stateDir = path.join(base, "new-parent", "connector-native");
  const baseInode = fs.statSync(base).ino;
  const originalFsync = fs.fsyncSync;
  try {
    fs.fsyncSync = (fd) => {
      const stat = fs.fstatSync(fd);
      if (stat.isDirectory() && stat.ino === baseInode) throw new Error("ancestor sync unavailable");
      return originalFsync(fd);
    };
    assert.throws(() => createMinimalProductionOperations({
      stateDir, wakeId: "wake-state-ancestor-sync", telegramTarget: "private-target",
      occurrenceId: "life-manager-connector-native:run-ancestor-sync",
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    }), /ancestor sync unavailable/);
  } finally {
    fs.fsyncSync = originalFsync;
    fs.rmSync(base, { recursive: true, force: true });
  }
});

test("TECH PLAY audit keeps a retained candidate visible after RSS eviction", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-techplay-retained-audit-"));
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-techplay-retained-audit", telegramTarget: "private-target",
      now: () => new Date("2026-08-12T08:30:00.000Z"),
      async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    await operations.recordTechPlayDiscoveryAudit({
      discovered_count: 1, rss_count: 0, processed_count: 1, pending_count: 1,
      saturated_count: 0, within_window_count: 1, eligible_count: 1,
      calendar_free_count: 1, selected_count: 1,
    });
    const row = JSON.parse(fs.readFileSync(path.join(stateDir, "techplay-discovery-audits.jsonl"), "utf8"));
    assert.equal(row.rss_count, 0);
    assert.equal(row.pending_count, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("operations persist only safe KokuchPro discovery aggregate counts", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connector-minimal-kokuchpro-discovery-"));
  const valid = { discovered_count: 100, within_window_count: 12, eligible_count: 8, calendar_free_count: 2, selected_count: 1 };
  try {
    const operations = createMinimalProductionOperations({
      stateDir, wakeId: "wake-20260812-kokuchpro-discovery", telegramTarget: "private-target",
      now: () => new Date("2026-08-12T06:00:00.000Z"), async sendMessage() { return { ok: true, result: { message_id: 7001 } }; },
    });
    assert.equal(Object.isFrozen(operations), true);
    assert.equal(typeof operations.recordKokuchProDiscoveryAudit, "function");
    await operations.recordKokuchProDiscoveryAudit(valid);
    const file = path.join(stateDir, "kokuchpro-discovery-audits.jsonl");
    const lines = fs.readFileSync(file, "utf8").trim().split("\n");
    const row = JSON.parse(lines[0]);
    assert.equal(lines.length, 1);
    assert.deepEqual(row, { schema_version: 1, wake_id: "wake-20260812-kokuchpro-discovery", ...valid, recorded_at: "2026-08-12T06:00:00.000Z" });
    assert.deepEqual(Object.keys(row).sort(), ["calendar_free_count", "discovered_count", "eligible_count", "recorded_at", "schema_version", "selected_count", "wake_id", "within_window_count"]);
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.doesNotMatch(JSON.stringify(row), /https?:\/\/|private-target|title|ticket|profile|auth|email/i);

    const { selected_count: _selectedCount, ...missingKey } = valid;
    for (const input of [
      { ...valid, private_url: "https://private.example/fixture" }, missingKey,
      { ...valid, selected_count: 0.5 }, { ...valid, discovered_count: -1 }, { ...valid, discovered_count: 801 },
      { ...valid, selected_count: "1" }, { ...valid, calendar_free_count: 9 }, { ...valid, eligible_count: 13 },
      { ...valid, within_window_count: 101 }, [], null,
    ]) await assert.rejects(() => operations.recordKokuchProDiscoveryAudit(input));
    assert.equal(fs.readFileSync(file, "utf8").trim().split("\n").length, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});
