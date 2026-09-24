"use strict";

const assert = require("node:assert/strict");
const { mkdtempSync, readFileSync, statSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");
const test = require("node:test");

const {
  appendPayoutReceipt,
  payoutIdFor,
  payoutReceiptText,
  readPayoutTenant,
  readWalletLedger,
  runtimeOccurrenceId,
  runPayout,
} = require("./payout-runtime.js");

const WALLET = "0x477EeE969ccfdc0e959F38cE8B83e372FC0262ad";
const DESTINATION = "0x6592AA47ccAC10031253551D3CC30fC64Ba7edc7";
const TX = `0x${"a".repeat(64)}`;
const NOW = Date.parse("2026-07-27T12:00:00.000Z");

test("payout receipt journal is occurrence-bound and mode 0600", () => {
  const stateDir = mkdtempSync(join(tmpdir(), "lm-payout-receipt-"));
  const occurrenceId = "life-manager-payout:fixture-1";
  const row = {
    occurrence_id: occurrenceId,
    provider_receipt_id: TX,
    official_readback_ref: `base://tx/${TX}`,
    proof_kind: "base_provider_settlement_receipt",
    verified: true,
    tx_hash: TX,
    amount_atomic: "7000000",
    from: WALLET.toLowerCase(),
    to: DESTINATION.toLowerCase(),
    block_number: "123",
    status: "transferred",
    effect_status: "submitted",
  };
  assert.equal(runtimeOccurrenceId(occurrenceId), occurrenceId);
  assert.equal(runtimeOccurrenceId("bad value"), null);
  assert.equal(appendPayoutReceipt(row, stateDir), true);
  const path = join(stateDir, "payout-receipts.jsonl");
  assert.equal(statSync(path).mode & 0o777, 0o600);
  assert.deepEqual(JSON.parse(readFileSync(path, "utf8")), row);
  assert.equal(appendPayoutReceipt({ ...row, occurrence_id: null }, ""), false);
});

function earning(kind, amountMinor, suffix) {
  return {
    entry_key: `${kind}:${suffix || amountMinor}`,
    wallet_address: WALLET,
    kind,
    amount_minor: amountMinor,
    currency: "USD",
    occurred_at: "2026-07-27T10:00:00.000Z",
  };
}

function harness(overrides = {}) {
  const events = [];
  const rows = overrides.rows || [earning("financial_external_income", 10_000)];
  const deps = {
    readTenant: async (uid) => {
      events.push(`read-tenant:${uid}`);
      return {
        uid,
        telegram_chat_id: "chat-1",
        payout_destination: {
          type: "wallet",
          status: "usable",
          address: DESTINATION,
        },
      };
    },
    readLedger: async () => {
      events.push("read-ledger");
      return rows;
    },
    readBalance: async () => {
      events.push("read-balance");
      return "42000000";
    },
    readOperatingCostMinor: async () => 0,
    readPrivateWallet: async () => {
      events.push("read-key");
      return { address: WALLET, privateKey: "11".repeat(32) };
    },
    settle: async (request) => {
      events.push("settle");
      return {
        txHash: TX,
        amountAtomic: request.amountAtomic,
        from: WALLET,
        to: DESTINATION,
        blockNumber: "123",
      };
    },
    recordTransfer: async (entry) => {
      events.push("record-transfer");
      return { ok: true, duplicate: false, entry };
    },
    sendTelegram: async (_token, chatId, text) => {
      events.push("send-telegram");
      return { ok: true, chatId, text };
    },
    telegramToken: "telegram-token",
    ...overrides,
  };
  delete deps.rows;
  return { deps, events, rows };
}

test("uid is mandatory and no broad tenant lookup is attempted", async () => {
  const { deps, events } = harness();
  await assert.rejects(() => runPayout({ walletAddress: WALLET }, deps), /uid/i);
  assert.deepEqual(events, []);
});

test("a fractional-cent USDC surplus settles and records without rounding", async () => {
  const { deps } = harness({
    rows: [{
      entry_key: "taskmarket:award",
      wallet_address: WALLET,
      kind: "financial_external_income",
      amount_minor: null,
      amount_atomic: "2312500",
      amount_decimals: 6,
      currency: "USD",
      occurred_at: "2026-07-27T10:00:00.000Z",
    }],
    readBalance: async () => "38000000",
  });
  let recorded = null;
  deps.recordTransfer = async (entry) => {
    recorded = entry;
    return { ok: true, duplicate: false, entry };
  };

  const result = await runPayout({
    uid: "u1",
    walletAddress: WALLET,
    nowMs: NOW,
  }, deps);

  assert.equal(result.amountAtomic, "2312500");
  assert.equal(recorded.amount_minor, undefined);
  assert.equal(recorded.amount_atomic, "2312500");
  assert.equal(recorded.amount_decimals, 6);
  assert.match(payoutReceiptText("2312500", TX), /\$2\.3125/);
});

test("production tenant lookup is one UID-scoped row with only the payout fields", async () => {
  const calls = [];
  const tenant = {
    uid: "u1",
    telegram_chat_id: "chat-1",
    payout_destination: { type: "wallet", status: "usable", address: DESTINATION },
  };
  const fetchImpl = async (url, init) => {
    calls.push({ url: String(url), init });
    return { ok: true, status: 200, json: async () => [tenant] };
  };
  const result = await readPayoutTenant("u1", {
    supaUrl: "https://db.example",
    supaKey: "service-key",
    fetchImpl,
  });

  assert.deepEqual(result, tenant);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /lm_users\?uid=eq\.u1/);
  assert.match(calls[0].url, /select=uid,telegram_chat_id,payout_destination/);
  assert.match(calls[0].url, /limit=1/);
  assert.doesNotMatch(calls[0].url, /telegram_chat_id=not|paid=|select=\*/);
});

test("wallet ledger pagination cannot silently truncate the economic history", async () => {
  const calls = [];
  const first = Array.from({ length: 1000 }, (_, index) =>
    earning("financial_external_income", 1, `page1-${index}`));
  const last = [earning("financial_fee", 1, "page2")];
  const fetchImpl = async (url, init) => {
    calls.push({ url: String(url), init });
    return {
      ok: true,
      status: 200,
      json: async () => (calls.length === 1 ? first : last),
    };
  };
  const rows = await readWalletLedger(WALLET, {
    supaUrl: "https://db.example",
    supaKey: "service-key",
    fetchImpl,
  });

  assert.equal(rows.length, 1001);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].init.headers.Range, "0-999");
  assert.equal(calls[1].init.headers.Range, "1000-1999");
  for (const call of calls) {
    assert.match(call.url, /wallet_address=eq\./);
    assert.match(call.url, /order=occurred_at\.asc,entry_key\.asc/);
  }
});

test("the exact tenant must own one usable wallet destination before any money read", async () => {
  for (const tenant of [
    null,
    { uid: "someone-else", telegram_chat_id: "chat-1", payout_destination: { type: "wallet", status: "usable", address: DESTINATION } },
    { uid: "u1", telegram_chat_id: "", payout_destination: { type: "wallet", status: "usable", address: DESTINATION } },
    { uid: "u1", telegram_chat_id: "chat-1", payout_destination: { type: "wallet", status: "awaiting_address" } },
    { uid: "u1", telegram_chat_id: "chat-1", payout_destination: { type: "bank", status: "usable", address: DESTINATION } },
  ]) {
    const { deps, events } = harness({
      readTenant: async (uid) => {
        events.push(`read-tenant:${uid}`);
        return tenant;
      },
    });
    await assert.rejects(() => runPayout({ uid: "u1", walletAddress: WALLET }, deps), /tenant|destination|wallet/i);
    assert.deepEqual(events, ["read-tenant:u1"]);
  }
});

test("zero surplus stops before the protected key, settlement, ledger write, and Telegram", async () => {
  const { deps, events } = harness({
    rows: [earning("financial_deposit", 100_000)],
  });
  const result = await runPayout({ uid: "u1", walletAddress: WALLET }, deps);

  assert.deepEqual(events, ["read-tenant:u1", "read-ledger", "read-balance"]);
  assert.deepEqual(result, {
    status: "noop",
    reason: "no_verified_surplus",
    amountAtomic: "0",
    verifiedSurplusMinor: 0,
    reserveAtomic: "35000000",
  });
});

test("the live payout path reserves recorded operating cost before settlement", async () => {
  const { deps } = harness({
    readBalance: async () => "100000000",
    readOperatingCostMinor: async () => 125,
  });
  const result = await runPayout({
    uid: "u1",
    walletAddress: WALLET,
    nowMs: NOW,
  }, deps);

  assert.equal(result.status, "transferred");
  assert.equal(result.amountAtomic, "63750000");
});

test("confirmed payout records the exact transfer before sending the §9.11 Telegram receipt", async () => {
  const { deps, events } = harness();
  let recorded;
  let sent;
  deps.recordTransfer = async (entry) => {
    events.push("record-transfer");
    recorded = entry;
    return { ok: true, duplicate: false };
  };
  deps.sendTelegram = async (token, chatId, text) => {
    events.push("send-telegram");
    sent = { token, chatId, text };
    return { ok: true };
  };

  const result = await runPayout({
    uid: "u1",
    walletAddress: WALLET,
    nowMs: NOW,
    facilitatorUrl: "http://127.0.0.1:8405",
  }, deps);

  assert.deepEqual(events, [
    "read-tenant:u1",
    "read-ledger",
    "read-balance",
    "read-key",
    "settle",
    "record-transfer",
    "send-telegram",
  ]);
  assert.deepEqual(recorded, {
    entry_key: `payout:${TX}:transfer`,
    wallet_address: WALLET,
    kind: "financial_user_transfer",
    amount_minor: 700,
    currency: "USD",
    occurred_at: "2026-07-27T12:00:00.000Z",
    tx_hash: TX,
    source: "base_usdc_payout",
    meta: {
      chain_id: 8453,
      block_number: "123",
      payout_id: result.payoutId,
    },
  });
  assert.deepEqual(sent, {
    token: "telegram-token",
    chatId: "chat-1",
    text: `💸 $7.00を登録済みのwalletに送金しました。tx: basescan.org/tx/${TX}\n着金まで数分かかることがあります。`,
  });
  assert.equal(result.status, "transferred");
  assert.equal(result.amountAtomic, "7000000");
  assert.equal(result.txHash, TX);
  assert.equal(result.notificationSent, true);
  assert.doesNotMatch(JSON.stringify(result), /private|telegram-token|6592AA/i);
});

test("a confirmed chain transfer whose ledger write fails is surfaced and never announced as recorded", async () => {
  const { deps, events } = harness({
    recordTransfer: async () => {
      events.push("record-transfer");
      throw new Error("database down");
    },
  });

  await assert.rejects(
    () => runPayout({ uid: "u1", walletAddress: WALLET, nowMs: NOW }, deps),
    new RegExp(`confirmed.*${TX.slice(0, 12)}.*ledger`, "i"),
  );
  assert.deepEqual(events, [
    "read-tenant:u1", "read-ledger", "read-balance", "read-key", "settle", "record-transfer",
  ]);
});

test("runtime independently rejects a settlement receipt that changes amount, sender, destination, or tx", async () => {
  const corruptions = [
    { amountAtomic: "6000000" },
    { from: DESTINATION },
    { to: WALLET },
    { txHash: "not-a-hash" },
  ];
  for (const corruption of corruptions) {
    const { deps, events } = harness({
      settle: async (request) => {
        events.push("settle");
        return {
          txHash: TX,
          amountAtomic: request.amountAtomic,
          from: WALLET,
          to: DESTINATION,
          blockNumber: "123",
          ...corruption,
        };
      },
    });
    await assert.rejects(
      () => runPayout({ uid: "u1", walletAddress: WALLET, nowMs: NOW }, deps),
      /settlement receipt/i,
    );
    assert.equal(events.includes("record-transfer"), false);
    assert.equal(events.includes("send-telegram"), false);
  }
});

test("Telegram failure does not erase or mislabel the already confirmed and recorded transfer", async () => {
  const { deps, events } = harness({
    sendTelegram: async () => {
      events.push("send-telegram");
      return { ok: false };
    },
  });
  const result = await runPayout({ uid: "u1", walletAddress: WALLET, nowMs: NOW }, deps);

  assert.equal(result.status, "transferred");
  assert.equal(result.notificationSent, false);
  assert.equal(events.at(-1), "send-telegram");
});

test("payout identity is stable across row order and changes when economic evidence changes", () => {
  const a = earning("financial_external_income", 10_000, "a");
  const b = earning("financial_fee", 500, "b");
  const first = payoutIdFor({
    uid: "u1", walletAddress: WALLET, destination: DESTINATION, amountAtomic: "7000000", rows: [a, b],
  });
  const reordered = payoutIdFor({
    uid: "u1", walletAddress: WALLET, destination: DESTINATION, amountAtomic: "7000000", rows: [b, a],
  });
  const changed = payoutIdFor({
    uid: "u1", walletAddress: WALLET, destination: DESTINATION, amountAtomic: "6000000", rows: [a, b],
  });

  assert.equal(first, reordered);
  assert.notEqual(first, changed);
  assert.match(first, /^tenant-[0-9a-f]{64}$/);
});

test("receipt copy displays exact USDC atomic amounts without rounding", () => {
  assert.equal(
    payoutReceiptText("7000000", TX),
    `💸 $7.00を登録済みのwalletに送金しました。tx: basescan.org/tx/${TX}\n着金まで数分かかることがあります。`,
  );
  assert.match(payoutReceiptText("7000001", TX), /\$7\.000001/);
  assert.throws(() => payoutReceiptText("0", TX), /positive/i);
  assert.throws(() => payoutReceiptText("7.1", TX), /atomic/i);
});
