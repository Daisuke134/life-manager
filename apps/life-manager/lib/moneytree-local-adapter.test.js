"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const {
  MONEYTREE_OBSERVATION,
  accountToFinancialRecord,
  normalizeAccounts,
  normalizeTransactions,
  readAccounts,
  readTransactions,
  transactionToFinancialRecord,
} = require("./moneytree-local-adapter.js");

const observedAt = "2026-09-07T06:00:00.000Z";

test("normalizeAccounts preserves the bank label without account identifiers", () => {
  const [account] = normalizeAccounts({ structuredContent: { data: {
    baseCurrency: "JPY",
    accountGroups: {
      banks: [{
        institutionKey: "provider-bank-key-501",
        institutionName: "三菱UFJ銀行",
        accounts: [{
          id: "provider-account-id-901",
          nickname: "普通",
          account_number: "1234567",
          account_subtype: "ordinary",
          current_balance_in_base: 26800,
        }],
      }],
      investments: [],
    },
  } } }, observedAt);

  assert.equal(account.name, "三菱UFJ銀行 普通");
  for (const identifier of ["provider-bank-key-501", "provider-account-id-901", "1234567"]) {
    assert.equal(account.name.includes(identifier), false);
  }
});

test("Moneytree balances and transactions project to distinct personal FinancialRecords", () => {
  const [account] = normalizeAccounts({ structuredContent: { data: {
    baseCurrency: "JPY",
    accountGroups: { banks: [{ institutionKey: "bank", accounts: [{ id: "a1", current_balance: -5000 }] }] },
  } } }, observedAt);
  const [expense, transfer] = normalizeTransactions({ structuredContent: { data: { transactions: [
    { id: "t1", account_id: "a1", amount: -1200, date: "2026-09-06", description: "Shop", category_name: "Food" },
    { id: "t2", account_id: "a1", amount: 3000, date: "2026-09-06", description: "Transfer", category_name: "振替" },
  ] } } });
  const options = { subjectId: "user-1", recordedAt: observedAt };

  assert.deepEqual(
    { kind: accountToFinancialRecord(account, options).kind, amount: accountToFinancialRecord(account, options).amount_minor },
    { kind: "liability_balance", amount: 5000 },
  );
  assert.deepEqual(
    { kind: transactionToFinancialRecord(expense, options).kind, direction: transactionToFinancialRecord(expense, options).direction },
    { kind: "personal_expense", direction: "debit" },
  );
  assert.deepEqual(
    { kind: transactionToFinancialRecord(transfer, options).kind, direction: transactionToFinancialRecord(transfer, options).direction },
    { kind: "transfer", direction: "credit" },
  );
  for (const record of [accountToFinancialRecord(account, options), transactionToFinancialRecord(expense, options)]) {
    assert.equal(record.scope, "personal");
    assert.equal(record.source.source_type, "moneytree");
    assert.equal(record.verification.status, "unverified");
    assert.deepEqual(record.verification.evidence_refs, []);
  }
  assert.deepEqual(accountToFinancialRecord(account, options), accountToFinancialRecord(account, options));
  assert.deepEqual(
    transactionToFinancialRecord(expense, options),
    transactionToFinancialRecord(expense, {
      ...options, recordedAt: "2026-09-07T07:00:00.000Z",
    }),
  );
  const otherSubject = accountToFinancialRecord(account, { ...options, subjectId: "user-2" });
  assert.notEqual(otherSubject.record_id, accountToFinancialRecord(account, options).record_id);
  assert.notEqual(otherSubject.source.external_ref, accountToFinancialRecord(account, options).source.external_ref);
  assert.notEqual(
    accountToFinancialRecord({ ...account, balance_jpy: -5001 }, options).record_id,
    accountToFinancialRecord(account, options).record_id,
  );
  assert.notEqual(
    accountToFinancialRecord({ ...account, observed_at: "2026-09-07T07:00:00.000Z" }, {
      ...options, recordedAt: "2026-09-07T07:00:00.000Z",
    }).record_id,
    accountToFinancialRecord(account, options).record_id,
  );
});

test("Moneytree FinancialRecord projection fails closed without portable identity and observation", () => {
  assert.throws(() => accountToFinancialRecord({
    id: "bad id", source: "moneytree", source_ref: `moneytree:${"a".repeat(64)}`,
    name: "Account", kind: "bank", balance_jpy: 1, observed_at: observedAt,
  }, { subjectId: "user-1", recordedAt: observedAt }), /common ID/);
  assert.throws(() => transactionToFinancialRecord({
    id: "moneytree:t1", source_ref: `moneytree:${"b".repeat(64)}`,
    account_id: "moneytree:a1", amount_jpy: 1, occurred_at: "bad",
  }, { subjectId: "user-1", recordedAt: observedAt }), /transaction time is invalid/);
  assert.throws(() => transactionToFinancialRecord({
    id: "moneytree:t1", source_ref: {}, account_id: "moneytree:a1",
    amount_jpy: 1, occurred_at: observedAt,
  }, { subjectId: "user-1", recordedAt: observedAt }), /source_ref is invalid/);
});

test("Moneytree records become verified only with an attached observation receipt", () => {
  const [account] = normalizeAccounts({ structuredContent: { data: {
    baseCurrency: "JPY",
    accountGroups: { banks: [{ institutionKey: "bank", accounts: [{ id: "a1", current_balance: 5000 }] }] },
  } } }, observedAt);
  const evidenceRef = `moneytree-observation://sha256/${"a".repeat(64)}`;
  const record = accountToFinancialRecord(account, {
    subjectId: "user-1", recordedAt: observedAt, evidenceRef,
    evidenceObservedAt: "2026-09-07T06:01:00.000Z",
  });
  assert.equal(record.verification.status, "verified");
  assert.deepEqual(record.verification.evidence_refs, [evidenceRef]);
  assert.equal(record.verification.observed_at, "2026-09-07T06:01:00.000Z");
});

test("readTransactions records requested range and returned coverage", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "moneytree-app-server-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const log = path.join(root, "lifecycle.log");
  const request = path.join(root, "request.json");
  const fake = path.join(root, "fake-codex");
  fs.writeFileSync(fake, `#!/usr/bin/env node
const fs = require("node:fs");
const readline = require("node:readline");
const log = ${JSON.stringify(log)};
const request = ${JSON.stringify(request)};
process.on("SIGTERM", () => setTimeout(() => {
  fs.appendFileSync(log, "exited\\n"); process.exit(0);
}, 50));
readline.createInterface({ input: process.stdin }).on("line", (line) => {
  const message = JSON.parse(line);
  if (message.id === 1) process.stdout.write(JSON.stringify({ id: 1, result: {} }) + "\\n");
  if (message.id === 2) process.stdout.write(JSON.stringify({ id: 2, result: { thread: { id: "thread-1" } } }) + "\\n");
  if (message.id === 3) {
    fs.writeFileSync(request, JSON.stringify(message.params.arguments));
    process.stdout.write(JSON.stringify({ id: 3, result: {
      isError: false,
      structuredContent: { data: {
        total_count: 4,
        transactions: [
          { id: "provider-transaction-id-001", account_id: "provider-account-id-017", amount: -1200, date: "2026-08-30", description: "RAW_TRANSACTION_PAYLOAD_MARKER", category_name: "食費" },
          { id: "provider-transaction-id-002", account_id: "provider-account-id-017", amount: 45000, date: "2026-08-12", description: "給料", category_name: "給与" }
        ]
      } }
    } }) + "\\n");
  }
});
`, { mode: 0o700 });

  const records = await readTransactions({
    startDate: "2026-08-01",
    endDate: "2026-08-31",
    limit: 17,
    codexBin: fake,
    cwd: root,
    timeoutMs: 1_000,
  });
  const observation = records[MONEYTREE_OBSERVATION];

  assert.equal(records.length, 2);
  assert.deepEqual({
    query_start_date: observation.query_start_date,
    query_end_date: observation.query_end_date,
    provider_total_count: observation.provider_total_count,
    returned_count: observation.returned_count,
    limit: observation.limit,
  }, {
    query_start_date: "2026-08-01",
    query_end_date: "2026-08-31",
    provider_total_count: 4,
    returned_count: 2,
    limit: 17,
  });
  assert.deepEqual(Object.keys(observation).sort(), [
    "limit",
    "mcp_server",
    "payload_sha256",
    "provider",
    "provider_total_count",
    "query_end_date",
    "query_start_date",
    "returned_count",
    "retrieved_at",
    "tool",
  ].sort());
  assert.match(observation.payload_sha256, /^[a-f0-9]{64}$/);
  assert.equal(JSON.stringify(observation).includes("provider-transaction-id-001"), false);
  assert.equal(JSON.stringify(observation).includes("provider-account-id-017"), false);
  assert.equal(JSON.stringify(observation).includes("RAW_TRANSACTION_PAYLOAD_MARKER"), false);
  for (const rawField of ["query", "arguments", "key", "api_key", "payload", "transactions"]) {
    assert.equal(Object.hasOwn(observation, rawField), false);
  }
  assert.deepEqual(JSON.parse(fs.readFileSync(request, "utf8")), {
    locale: "ja",
    start_date: "2026-08-01",
    end_date: "2026-08-31",
    limit: 17,
    sort_key: "date",
    sort_order: "desc",
  });
  assert.equal(fs.readFileSync(log, "utf8"), "exited\n");
});

test("Moneytree transfer, card repayment, and ATM withdrawal categories are not consumption", () => {
  const transactions = normalizeTransactions({ structuredContent: { data: { transactions: [
    { id: "tx-transfer", account_id: "account-1", amount: -1200, date: "2026-09-01", description: "振替", category_name: "振替" },
    { id: "tx-card-repayment", account_id: "account-1", amount: -5400, date: "2026-09-02", description: "カード返済", category_name: "カード返済" },
    { id: "tx-atm-withdrawal", account_id: "account-1", amount: -10000, date: "2026-09-03", description: "ATM引き出し", category_name: "ATM引き出し" },
  ] } } });
  const records = transactions.map((transaction) => transactionToFinancialRecord(transaction, {
    subjectId: "user-1",
    recordedAt: observedAt,
  }));

  assert.deepEqual(records.map(({ kind, direction }) => ({ kind, direction })), [
    { kind: "transfer", direction: "debit" },
    { kind: "transfer", direction: "debit" },
    { kind: "transfer", direction: "debit" },
  ]);
  assert.equal(records.some(({ kind }) => kind === "personal_expense"), false);
});

test("Moneytree read waits until its app-server process has exited", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "moneytree-app-server-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const log = path.join(root, "lifecycle.log");
  const fake = path.join(root, "fake-codex");
  fs.writeFileSync(fake, `#!/usr/bin/env node
const fs = require("node:fs");
const readline = require("node:readline");
const log = ${JSON.stringify(log)};
process.on("SIGTERM", () => setTimeout(() => {
  fs.appendFileSync(log, "exited\\n"); process.exit(0);
}, 50));
readline.createInterface({ input: process.stdin }).on("line", (line) => {
  const message = JSON.parse(line);
  if (message.id === 1) process.stdout.write(JSON.stringify({ id: 1, result: {} }) + "\\n");
  if (message.id === 2) process.stdout.write(JSON.stringify({ id: 2, result: { thread: { id: "thread-1" } } }) + "\\n");
  if (message.id === 3) process.stdout.write(JSON.stringify({ id: 3, result: {
    isError: false, structuredContent: { data: { baseCurrency: "JPY", accountGroups: { banks: [], investments: [] } } }
  } }) + "\\n");
});
`, { mode: 0o700 });

  assert.deepEqual(await readAccounts({ codexBin: fake, cwd: root, timeoutMs: 1_000 }), []);
  assert.equal(fs.readFileSync(log, "utf8"), "exited\n");
});
