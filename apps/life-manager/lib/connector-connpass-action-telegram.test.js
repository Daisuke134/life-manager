"use strict";

const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createConnpassActionTelegram } = require("./connector-connpass-action-telegram.js");

function candidate(overrides = {}) {
  return {
    provider: "connpass",
    event_ref: "connpass-event://event/901",
    canonical_url: "https://tokyo-ai.connpass.com/event/901/",
    title: "Tokyo AI Builders LT",
    participation_slot_status: "available",
    lightning_talk_status: "unknown",
    participant_limit: 100,
    accepted_count: 20,
    waiting_count: 0,
    application_deadline_at: null,
    priority_class: "ai",
    preference_reason: "AI buildersとの接点に合います。",
    ...overrides,
  };
}

test("connpass action boundary sends normalized candidate fields and persists a positive provider receipt", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-telegram-"));
  const sent = [];
  try {
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-1", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async (message, options) => { sent.push({ message, options }); return { messageId: "7711" }; },
    });
    const result = await reporter.report({ candidates: [candidate()] });
    assert.equal(result.telegram_provider_id, "7711");
    assert.match(sent[0].message, /参加枠: available/);
    assert.match(sent[0].message, /LT: unknown/);
    assert.match(sent[0].message, /補欠: 0人/);
    assert.match(sent[0].message, /締切: provider未提供/);
    assert.match(sent[0].message, /https:\/\/tokyo-ai\.connpass\.com\/event\/901\//);
    assert.match(sent[0].message, /自動申込: 0件/);
    assert.match(sent[0].message, /理由: AI buildersとの接点/);
    const rows = fs.readFileSync(path.join(stateDir, "connpass-action-boundary-deliveries.jsonl"), "utf8").trim().split("\n").map(JSON.parse);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].telegram_provider_id, "7711");
    assert.doesNotMatch(JSON.stringify(rows), /private-target|api.?key|cookie|password/i);
    const reused = await reporter.report({ candidates: [candidate()] });
    assert.equal(reused.completion_disposition, "reused");
    assert.equal(sent.length, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("questionnaire report sends public questions once and reuses its durable receipt", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-questionnaire-telegram-"));
  const sent = [];
  try {
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-questionnaire-1", telegramTarget: "private-target",
      now: () => new Date("2026-09-17T08:00:00.000Z"),
      send: async (message, options) => { sent.push({ message, options }); return { messageId: "8811" }; },
    });
    const input = {
      candidate: candidate({ event_ref: "connpass-event://event/404531", canonical_url: "https://findy.connpass.com/event/404531/" }),
      questions: ["注意事項への同意", "Xアカウント（なければ「なし」）"],
    };
    const result = await reporter.reportQuestionnaire(input);
    assert.equal(result.telegram_provider_id, "8811");
    assert.match(sent[0].message, /自動申込: 0件/);
    assert.match(sent[0].message, /404531/);
    assert.match(sent[0].message, /注意事項への同意/);
    assert.match(sent[0].message, /回答を保存後/);
    assert.match(sent[0].options.idempotencyKey, /connpass-questionnaire/);
    const reused = await reporter.reportQuestionnaire(input);
    assert.equal(reused.completion_disposition, "reused");
    assert.equal(sent.length, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("missing provider message ID and malformed candidate never write a receipt", async () => {
  for (const candidates of [[candidate()], [candidate({ canonical_url: "https://evil.example/event/901/" })]]) {
    const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-reject-"));
    try {
      const reporter = createConnpassActionTelegram({
        stateDir, wakeId: "wake-connpass-reject", telegramTarget: "private-target",
        now: () => new Date("2026-08-27T01:00:00.000Z"), send: async () => ({}),
      });
      await assert.rejects(reporter.report({ candidates }));
      assert.equal(fs.existsSync(path.join(stateDir, "connpass-action-boundary-deliveries.jsonl")), false);
    } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
  }
});

test("action boundary exposes only stable stage codes for send and provider receipt failures", async () => {
  const cases = [
    { send: async () => { throw new Error("private transport detail"); }, code: "CONNPASS_ACTION_BOUNDARY_SEND_FAILED" },
    { send: async () => ({}), code: "CONNPASS_ACTION_BOUNDARY_PROVIDER_ID_FAILED" },
  ];
  for (const row of cases) {
    const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-stage-"));
    try {
      const reporter = createConnpassActionTelegram({
        stateDir, wakeId: "wake-connpass-stage", telegramTarget: "private-target",
        now: () => new Date("2026-08-27T01:00:00.000Z"), send: row.send,
      });
      await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
        assert.equal(error.code, row.code);
        assert.equal(error.message, row.code);
        return true;
      });
      assert.equal(fs.existsSync(path.join(stateDir, "connpass-action-boundary-deliveries.jsonl")), false);
    } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
  }
});

test("action boundary identifies malformed ranked candidates before transport", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-candidate-stage-"));
  try {
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-candidate-stage", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { throw new Error("transport must not run"); },
    });
    await assert.rejects(
      reporter.report({ candidates: [candidate({ lightning_talk_status: undefined })] }),
      (error) => error.code === "CONNPASS_ACTION_BOUNDARY_CANDIDATE_FAILED",
    );
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("public security vocabulary and example credential strings remain reportable public event text", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-crypto-"));
  try {
    const messages = [];
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-crypto", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async (message) => { messages.push(message); return { messageId: "7722" }; },
    });
    const result = await reporter.report({ candidates: [candidate({
      title: "API Key and Secret Management",
      preference_reason: `Passwordless auth demo with access_${"tok"}${"en="}${"0123456789abcdef"} is public event text.`,
    })] });
    assert.equal(result.telegram_provider_id, "7722");
    assert.match(messages[0], /Secret Management/);
    assert.match(messages[0], /Passwordless auth demo/);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("action boundary truncates a valid ranked title only for Telegram display", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-title-"));
  try {
    let delivered = "";
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-title", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async (message) => { delivered = message; return { messageId: "7733" }; },
    });
    const result = await reporter.report({ candidates: [candidate({ title: "t".repeat(200) })] });
    assert.equal(result.telegram_provider_id, "7733");
    assert.match(delivered, new RegExp(`1\\. ${"t".repeat(160)}\\n`));
    assert.doesNotMatch(delivered, new RegExp("t".repeat(161)));
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("action boundary sends the longest ranked prefix that fits Telegram", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-prefix-"));
  try {
    let delivered = "";
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-prefix", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async (message) => { delivered = message; return { messageId: "7744" }; },
    });
    const candidates = Array.from({ length: 5 }, (_, index) => candidate({
      event_ref: `connpass-event://event/${920 + index}`,
      canonical_url: `https://${"a".repeat(700)}.connpass.com/event/${920 + index}/`,
      title: `${index + 1}-${"t".repeat(158)}`,
      preference_reason: "r".repeat(500),
    }));
    const result = await reporter.report({ candidates });
    assert.equal(result.telegram_provider_id, "7744");
    assert.equal(delivered.length <= 4_096, true);
    assert.match(delivered, /1-tttt/);
    assert.doesNotMatch(delivered, /5-tttt/);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("action boundary requires an explicit sender and never falls back to OpenClaw", () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-sender-required-"));
  try {
    const source = fs.readFileSync(path.join(__dirname, "connector-connpass-action-telegram.js"), "utf8");
    assert.doesNotMatch(source, /outbound-guardian|notifyOpenClawGateway|parseOpenClawMessageId/);
    assert.throws(() => createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-sender-required", telegramTarget: "private-target",
    }), /invalid/i);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("action boundary durably claims before sending and quarantines every uncertain result", async () => {
  const scenarios = [
    { name: "transport", send: async () => { throw new Error("transport detail"); }, reason: "transport", code: "CONNPASS_ACTION_BOUNDARY_SEND_FAILED" },
    { name: "provider rejection", send: async () => ({ ok: false }), reason: "provider_rejection", code: "CONNPASS_ACTION_BOUNDARY_PROVIDER_ID_FAILED" },
    { name: "invalid provider receipt", send: async () => ({ messageId: 0 }), reason: "missing_message_id", code: "CONNPASS_ACTION_BOUNDARY_PROVIDER_ID_FAILED" },
    { name: "unknown provider result", send: async () => ({ delivery_unknown: true }), reason: "delivery_unknown", code: "CONNPASS_ACTION_BOUNDARY_PROVIDER_ID_FAILED" },
  ];
  for (const scenario of scenarios) {
    const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), `connpass-action-${scenario.name.replace(/\s+/g, "-")}-`));
    let sends = 0;
    try {
      const reporter = createConnpassActionTelegram({
        stateDir, wakeId: `wake-connpass-${scenario.name.replace(/\s+/g, "-")}`, telegramTarget: "private-target",
        now: () => new Date("2026-08-27T01:00:00.000Z"),
        send: async (...args) => { sends += 1; return scenario.send(...args); },
      });
      await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
        assert.equal(error.code, scenario.code);
        assert.equal(error.message, scenario.code);
        return true;
      });
      const claimFile = path.join(stateDir, "connpass-action-boundary-send-claims.jsonl");
      const uncertainFile = path.join(stateDir, "connpass-action-boundary-uncertain.jsonl");
      const deliveryFile = path.join(stateDir, "connpass-action-boundary-deliveries.jsonl");
      const claims = fs.readFileSync(claimFile, "utf8").trim().split("\n").map(JSON.parse);
      const uncertain = fs.readFileSync(uncertainFile, "utf8").trim().split("\n").map(JSON.parse);
      assert.equal(claims.length, 1);
      assert.deepEqual(Object.keys(claims[0]).sort(), [
        "candidate_snapshot_sha256", "claimed_at", "schema_version", "wake_id",
      ]);
      assert.equal(claims[0].schema_version, 1);
      assert.equal(uncertain.length, 1);
      assert.deepEqual(Object.keys(uncertain[0]).sort(), [
        "candidate_snapshot_sha256", "quarantined_at", "reason", "schema_version", "wake_id",
      ]);
      assert.equal(uncertain[0].reason, scenario.reason);
      assert.equal(fs.existsSync(deliveryFile), false);
      assert.equal((fs.statSync(claimFile).mode & 0o777), 0o600);
      assert.equal((fs.statSync(uncertainFile).mode & 0o777), 0o600);
      await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
        assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
        assert.equal(error.message, "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
        return true;
      });
      assert.equal(sends, 1);
    } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
  }
});

test("action boundary rejects malformed or duplicate identity rows before transport", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-ledger-invalid-"));
  let sends = 0;
  try {
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-ledger-invalid", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { sends += 1; return { messageId: 7711 }; },
    });
    const snapshot = "a".repeat(64);
    const row = {
      schema_version: 1, wake_id: "wake-connpass-ledger-invalid", candidate_snapshot_sha256: snapshot,
      claimed_at: "2026-08-27T01:00:00.000Z",
    };
    const claimFile = path.join(stateDir, "connpass-action-boundary-send-claims.jsonl");
    fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });
    fs.writeFileSync(claimFile, `${JSON.stringify(row)}\n${JSON.stringify(row)}\n`, { mode: 0o600 });
    await assert.rejects(reporter.report({ candidates: [candidate()] }));
    assert.equal(sends, 0);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("action boundary uses one atomic identity claim across independently created reporters", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-atomic-claim-"));
  let sends = 0;
  let releaseSend;
  let sendStarted;
  const started = new Promise((resolve) => { sendStarted = resolve; });
  try {
    const send = async () => {
      sends += 1;
      sendStarted();
      await new Promise((resolve) => { releaseSend = resolve; });
      return { messageId: 7788 };
    };
    const options = {
      stateDir, wakeId: "wake-connpass-atomic-claim", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"), send,
    };
    const first = createConnpassActionTelegram(options);
    const second = createConnpassActionTelegram(options);
    const firstRun = first.report({ candidates: [candidate()] });
    await started;
    await assert.rejects(second.report({ candidates: [candidate()] }), (error) => {
      assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
      return true;
    });
    releaseSend();
    assert.deepEqual(await firstRun, { telegram_provider_id: "7788", completion_disposition: "created" });
    assert.equal(sends, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("two independent Node processes cannot both send one action-boundary identity", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-cross-process-"));
  const startFile = path.join(stateDir, "start-gate");
  const releaseFile = path.join(stateDir, "release-gate");
  const sendsFile = path.join(stateDir, "actual-sends.jsonl");
  const actionModule = path.join(__dirname, "connector-connpass-action-telegram.js");
  const childScript = `
    const fs = require("node:fs");
    const { createConnpassActionTelegram } = require(process.env.ACTION_MODULE);
    const stateDir = process.env.STATE_DIR;
    const wait = (file) => fs.existsSync(file) ? Promise.resolve() : new Promise((resolve) => setTimeout(() => resolve(wait(file)), 5));
    const candidate = JSON.parse(process.env.CANDIDATE_JSON);
    (async () => {
      const ready = process.env.READY_FILE;
      fs.writeFileSync(ready, String(process.pid), { mode: 0o600 });
      await wait(process.env.START_FILE);
      const reporter = createConnpassActionTelegram({
        stateDir, wakeId: process.env.WAKE_ID, telegramTarget: "private-target",
        now: () => new Date("2026-08-27T01:00:00.000Z"),
        send: async () => {
          const fd = fs.openSync(process.env.SENDS_FILE, "a", 0o600);
          try { fs.writeSync(fd, JSON.stringify({ pid: process.pid }) + "\\n"); fs.fsyncSync(fd); }
          finally { fs.closeSync(fd); }
          await wait(process.env.RELEASE_FILE);
          return { messageId: 7800 + Number(process.env.ROLE) };
        },
      });
      try {
        const output = { ok: true, result: await reporter.report({ candidates: [candidate] }) };
        fs.writeFileSync(process.env.RESULT_FILE, JSON.stringify(output), { mode: 0o600 });
        console.log(JSON.stringify(output));
      } catch (error) {
        const output = { ok: false, code: error && error.code };
        fs.writeFileSync(process.env.RESULT_FILE, JSON.stringify(output), { mode: 0o600 });
        console.log(JSON.stringify(output));
      }
    })();
  `;
  const children = [];
  const launch = (role) => new Promise((resolve, reject) => {
    const readyFile = path.join(stateDir, `ready-${role}`);
    const child = spawn(process.execPath, ["-e", childScript], {
      cwd: __dirname,
      env: {
        ...process.env, ACTION_MODULE: actionModule, STATE_DIR: stateDir, START_FILE: startFile, RELEASE_FILE: releaseFile,
        SENDS_FILE: sendsFile, READY_FILE: readyFile, ROLE: String(role), WAKE_ID: "wake-connpass-cross-process",
        RESULT_FILE: path.join(stateDir, `result-${role}`),
        CANDIDATE_JSON: JSON.stringify(candidate()),
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    children.push(child);
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code, signal) => resolve({ code, signal, stdout, stderr, readyFile }));
  });
  try {
    const first = launch(1);
    const second = launch(2);
    const readyAt = Date.now() + 5_000;
    while ((!fs.existsSync(path.join(stateDir, "ready-1")) || !fs.existsSync(path.join(stateDir, "ready-2"))) && Date.now() < readyAt) {
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    assert.equal(fs.existsSync(path.join(stateDir, "ready-1")) && fs.existsSync(path.join(stateDir, "ready-2")), true);
    fs.writeFileSync(startFile, "go\n", { mode: 0o600 });
    const overlapDeadline = Date.now() + 5_000;
    let loserObserved = false;
    while (Date.now() < overlapDeadline) {
      for (const role of [1, 2]) {
        const resultFile = path.join(stateDir, `result-${role}`);
        if (!fs.existsSync(resultFile)) continue;
        try { loserObserved ||= JSON.parse(fs.readFileSync(resultFile, "utf8")).code === "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN"; }
        catch { /* child is still publishing its bounded result */ }
      }
      if (loserObserved) break;
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    assert.equal(loserObserved, true);
    fs.writeFileSync(releaseFile, "release\n", { mode: 0o600 });
    const results = await Promise.all([first, second]);
    const outputs = results.map((result) => JSON.parse(result.stdout.trim()));
    assert.equal(outputs.filter((result) => result.ok).length, 1);
    assert.deepEqual(outputs.filter((result) => !result.ok).map((result) => result.code), [
      "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN",
    ]);
    assert.equal(fs.readFileSync(sendsFile, "utf8").trim().split("\n").length, 1);
  } finally {
    for (const child of children) if (child.exitCode == null) child.kill("SIGTERM");
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("claim-directory creation and marker creation each fsync a real directory", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-directory-fsync-"));
  const originalFsync = fs.fsyncSync;
  const directoryFsyncs = [];
  try {
    fs.fsyncSync = (descriptor) => {
      if (fs.fstatSync(descriptor).isDirectory()) directoryFsyncs.push(descriptor);
      return originalFsync(descriptor);
    };
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-directory-fsync", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"), send: async () => ({ messageId: 7794 }),
    });
    await reporter.report({ candidates: [candidate()] });
    assert.equal(directoryFsyncs.length >= 2, true);
  } finally {
    fs.fsyncSync = originalFsync;
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("a persisted atomic marker blocks replay even when the JSONL claim was interrupted", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-marker-crash-"));
  let sends = 0;
  try {
    const first = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-marker-crash", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { sends += 1; throw new Error("interrupted after marker"); },
    });
    await assert.rejects(first.report({ candidates: [candidate()] }));
    fs.rmSync(path.join(stateDir, "connpass-action-boundary-send-claims.jsonl"));
    fs.rmSync(path.join(stateDir, "connpass-action-boundary-uncertain.jsonl"));
    const second = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-marker-crash", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { sends += 1; return { messageId: 7789 }; },
    });
    await assert.rejects(second.report({ candidates: [candidate()] }), (error) => {
      assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
      return true;
    });
    assert.equal(sends, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("delivery ledger append failure quarantines the identity and never retries", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-delivery-write-"));
  const originalOpen = fs.openSync;
  let sends = 0;
  try {
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-delivery-write", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { sends += 1; return { messageId: 7790 }; },
    });
    fs.openSync = (file, ...args) => {
      if (String(file).endsWith("connpass-action-boundary-deliveries.jsonl") && (args[0] & fs.constants.O_APPEND)) throw new Error("delivery ledger unavailable");
      return originalOpen(file, ...args);
    };
    await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
      assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
      return true;
    });
    fs.openSync = originalOpen;
    await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
      assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
      return true;
    });
    assert.equal(sends, 1);
  } finally {
    fs.openSync = originalOpen;
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("a clean pre-send claim append failure removes the marker and allows one later retry", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-claim-clean-retry-"));
  const originalOpen = fs.openSync;
  let sends = 0;
  try {
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-claim-clean-retry", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { sends += 1; return { messageId: 7795 }; },
    });
    fs.openSync = (file, ...args) => {
      if (String(file).endsWith("connpass-action-boundary-send-claims.jsonl") && (args[0] & fs.constants.O_APPEND)) throw new Error("clean claim append failure");
      return originalOpen(file, ...args);
    };
    await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
      assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_CLAIM_FAILED");
      return true;
    });
    fs.openSync = originalOpen;
    assert.equal(fs.existsSync(path.join(stateDir, "connpass-action-boundary-send-claims.jsonl")), false);
    await reporter.report({ candidates: [candidate()] });
    assert.equal(sends, 1);
  } finally {
    fs.openSync = originalOpen;
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("claim marker cleanup failure remains uncertain and never sends or retries", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-claim-cleanup-failure-"));
  const originalOpen = fs.openSync;
  const originalUnlink = fs.unlinkSync;
  let sends = 0;
  try {
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-claim-cleanup-failure", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { sends += 1; return { messageId: 7796 }; },
    });
    fs.openSync = (file, ...args) => {
      if (String(file).endsWith("connpass-action-boundary-send-claims.jsonl") && (args[0] & fs.constants.O_APPEND)) throw new Error("clean claim append failure");
      return originalOpen(file, ...args);
    };
    fs.unlinkSync = (file) => {
      if (String(file).endsWith(".claim")) throw new Error("marker cleanup failure");
      return originalUnlink(file);
    };
    await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
      assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
      return true;
    });
    fs.openSync = originalOpen;
    fs.unlinkSync = originalUnlink;
    await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
      assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_DELIVERY_UNCERTAIN");
      return true;
    });
    assert.equal(sends, 0);
  } finally {
    fs.openSync = originalOpen;
    fs.unlinkSync = originalUnlink;
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("partial claim JSONL append fails closed on the next run", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-claim-partial-"));
  const originalOpen = fs.openSync;
  const originalWrite = fs.writeSync;
  let claimDescriptor = null;
  let sends = 0;
  try {
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-claim-partial", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { sends += 1; return { messageId: 7797 }; },
    });
    fs.openSync = (file, ...args) => {
      const descriptor = originalOpen(file, ...args);
      if (String(file).endsWith("connpass-action-boundary-send-claims.jsonl")) claimDescriptor = descriptor;
      return descriptor;
    };
    fs.writeSync = (descriptor, ...args) => {
      if (descriptor === claimDescriptor) {
        originalWrite(descriptor, Buffer.from("{"), 0, 1, null);
        throw new Error("partial claim append failure");
      }
      return originalWrite(descriptor, ...args);
    };
    await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
      assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_CLAIM_FAILED");
      return true;
    });
    fs.openSync = originalOpen;
    fs.writeSync = originalWrite;
    await assert.rejects(reporter.report({ candidates: [candidate()] }), (error) => {
      assert.equal(error.code, "CONNPASS_ACTION_BOUNDARY_LEDGER_FAILED");
      return true;
    });
    assert.equal(sends, 0);
  } finally {
    fs.openSync = originalOpen;
    fs.writeSync = originalWrite;
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("action boundary rejects wrong permissions and symlinked state or ledgers before transport", async () => {
  const cases = [
    {
      name: "state permissions",
      prepare(stateDir) { fs.chmodSync(stateDir, 0o755); },
    },
    {
      name: "state symlink",
      prepare(stateDir) {
        const target = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-state-target-"));
        fs.rmSync(stateDir, { recursive: true, force: true });
        fs.symlinkSync(target, stateDir, "dir");
      },
    },
    {
      name: "delivery symlink",
      prepare(stateDir) {
        const target = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-ledger-target-")), "delivery.jsonl");
        fs.writeFileSync(target, "", { mode: 0o600 });
        fs.symlinkSync(target, path.join(stateDir, "connpass-action-boundary-deliveries.jsonl"));
      },
    },
    {
      name: "delivery permissions",
      prepare(stateDir) {
        fs.writeFileSync(path.join(stateDir, "connpass-action-boundary-deliveries.jsonl"), "", { mode: 0o644 });
      },
    },
    {
      name: "claim directory symlink",
      prepare(stateDir) {
        const target = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-claim-target-"));
        fs.symlinkSync(target, path.join(stateDir, "connpass-action-boundary-claims"), "dir");
      },
    },
    {
      name: "claim directory permissions",
      prepare(stateDir) {
        fs.mkdirSync(path.join(stateDir, "connpass-action-boundary-claims"), { mode: 0o755 });
      },
    },
  ];
  for (const row of cases) {
    const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), `connpass-action-fs-${row.name.replace(/\s+/g, "-")}-`));
    let sends = 0;
    try {
      row.prepare(stateDir);
      const reporter = createConnpassActionTelegram({
        stateDir, wakeId: `wake-connpass-fs-${row.name.replace(/\s+/g, "-")}`, telegramTarget: "private-target",
        now: () => new Date("2026-08-27T01:00:00.000Z"), send: async () => { sends += 1; return { messageId: 7791 }; },
      });
      await assert.rejects(reporter.report({ candidates: [candidate()] }));
      assert.equal(sends, 0, row.name);
    } finally {
      const stat = fs.lstatSync(stateDir);
      if (stat.isDirectory() && !stat.isSymbolicLink()) fs.chmodSync(stateDir, 0o700);
      fs.rmSync(stateDir, { recursive: true, force: true });
    }
  }
});

test("ledger read stays on its opened fd when the path is swapped to a symlink", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-ledger-swap-"));
  const deliveryFile = path.join(stateDir, "connpass-action-boundary-deliveries.jsonl");
  const backupFile = path.join(stateDir, "delivery-backup.jsonl");
  const originalOpen = fs.openSync;
  const originalFstat = fs.fstatSync;
  let deliveryDescriptor = null;
  let swapped = false;
  let sends = 0;
  try {
    const first = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-ledger-swap", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { sends += 1; return { messageId: 7798 }; },
    });
    await first.report({ candidates: [candidate()] });
    const second = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-ledger-swap", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async () => { sends += 1; return { messageId: 7799 }; },
    });
    fs.openSync = (file, ...args) => {
      const descriptor = originalOpen(file, ...args);
      if (String(file) === deliveryFile && (args[0] & fs.constants.O_WRONLY) === 0) deliveryDescriptor = descriptor;
      return descriptor;
    };
    fs.fstatSync = (descriptor) => {
      const stat = originalFstat(descriptor);
      if (descriptor === deliveryDescriptor && !swapped) {
        fs.renameSync(deliveryFile, backupFile);
        fs.symlinkSync(backupFile, deliveryFile);
        swapped = true;
      }
      return stat;
    };
    const result = await second.report({ candidates: [candidate()] });
    assert.deepEqual(result, { telegram_provider_id: "7798", completion_disposition: "reused" });
    assert.equal(swapped, true);
    assert.equal(sends, 1);
  } finally {
    fs.openSync = originalOpen;
    fs.fstatSync = originalFstat;
    if (fs.existsSync(deliveryFile) && fs.lstatSync(deliveryFile).isSymbolicLink()) fs.unlinkSync(deliveryFile);
    if (fs.existsSync(backupFile)) fs.renameSync(backupFile, deliveryFile);
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("action boundary HTML-escapes provider text before applying the Telegram length bound", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "connpass-action-html-"));
  let delivered = "";
  try {
    const reporter = createConnpassActionTelegram({
      stateDir, wakeId: "wake-connpass-html", telegramTarget: "private-target",
      now: () => new Date("2026-08-27T01:00:00.000Z"),
      send: async (message) => { delivered = message; return { messageId: 7792 }; },
    });
    await reporter.report({ candidates: [candidate({ title: "<&>\"'".repeat(100), preference_reason: "<&>\"'".repeat(100) })] });
    const visible = delivered.replace(/&lt;/g, "<").replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
    assert.equal(visible.length <= 4_096, true);
    assert.match(visible, /[<&>"']/);
    assert.match(delivered, /&lt;|&amp;|&gt;|&quot;|&#39;/);
    assert.doesNotMatch(delivered, /<|>|\"|'/);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});
