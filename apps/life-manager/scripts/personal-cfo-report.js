#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { readAccounts, readTransactions, MONEYTREE_OBSERVATION } = require("../lib/moneytree-local-adapter.js");
const { summarizeTransactions } = require("../lib/financial-ledger.js");
const { sendMessage } = require("../lib/telegram.js");

function ymd(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function renderSection(label, rows, sourceStatus = { status: "fresh" }) {
  if (sourceStatus.status !== "fresh") {
    return `${label}: 収入: 未確認 / 支出: 未確認 / 差引: 未確認`;
  }
  const total = summarizeTransactions(rows);
  return `${label}: 収入 ¥${total.income_jpy.toLocaleString("ja-JP")} / 支出 ¥${total.spending_jpy.toLocaleString("ja-JP")} / 差引 ¥${total.net_jpy.toLocaleString("ja-JP")}`;
}

function combineSourceStatus(accounts, transactions, explicit = null) {
  if (explicit && typeof explicit === "object") return explicit;
  const reads = [accounts[MONEYTREE_OBSERVATION], transactions[MONEYTREE_OBSERVATION]].filter(Boolean);
  const statuses = reads.map((read) => String(read.source_status || "unknown"));
  if (statuses.length === 2 && statuses.every((status) => status === "fresh")) return { status: "fresh", reason: null };
  if (statuses.includes("stale")) {
    const stale = reads.find((read) => read.source_status === "stale");
    return { status: "stale", reason: stale && stale.source_reason || "source_stale" };
  }
  return { status: "partial", reason: "source_completeness_unknown" };
}

function renderPersonalCfoReport({ accounts, transactions, sourceStatus, observedAt }) {
  const cash = accounts.reduce((sum, row) => sum + row.balance_jpy, 0);
  const now = new Date(observedAt || Date.now());
  const today = ymd(now);
  const weekStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6);
  weekStart.setHours(0, 0, 0, 0);
  const daily = transactions.filter((row) => String(row.occurred_at).slice(0, 10) === today);
  const weekly = transactions.filter((row) => new Date(row.occurred_at) >= weekStart);
  return [
    "CFO · 実データ",
    `確認済み資産: ¥${cash.toLocaleString("ja-JP")}`,
    `残高観測: ${sourceStatus.status}${sourceStatus.reason ? ` (${sourceStatus.reason})` : ""}`,
    `観測時刻: ${observedAt || "未確認"}`,
    "負債: 未接続",
    renderSection("今日", daily, sourceStatus),
    renderSection("7日", weekly, sourceStatus),
    renderSection("今月", transactions, sourceStatus),
    "出所: Moneytree read-only",
  ].join("\n");
}

async function main() {
  const now = new Date();
  const fixtureIndex = process.argv.indexOf("--fixture");
  let fixture = null;
  if (fixtureIndex >= 0) {
    const fixturePath = process.argv[fixtureIndex + 1];
    if (!fixturePath) throw new Error("personal_cfo_fixture_missing");
    fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  }
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
  const today = ymd(now);
  const [accounts, transactions] = fixture
    ? [fixture.accounts || [], fixture.transactions || []]
    : await Promise.all([
      readAccounts(),
      readTransactions({ startDate: ymd(monthStart), endDate: today }),
    ]);
  const sourceStatus = combineSourceStatus(accounts, transactions, fixture && fixture.source);
  const message = renderPersonalCfoReport({ accounts, transactions, sourceStatus, observedAt: now.toISOString() });
  if (sourceStatus.status !== "fresh") {
    process.stdout.write(message);
    process.exitCode = 1;
    return;
  }
  if (!process.argv.includes("--send")) {
    process.stdout.write(message);
    return;
  }
  const credentialPath = path.join(process.env.HOME, ".local/share/anicca/credentials.json");
  const credential = JSON.parse(fs.readFileSync(credentialPath, "utf8")).credentials
    .find((row) => row.service === "telegram-life-manager");
  if (!credential?.bot_token || !credential?.chat_id) throw new Error("Life Manager Telegram credential is unavailable");
  const sent = await sendMessage(credential.bot_token, String(credential.chat_id), `Codex::: ${message}`);
  if (!sent?.ok || !Number.isInteger(sent.result?.message_id)) throw new Error("Life Manager Telegram send failed");
  process.stdout.write(`${JSON.stringify({ sent: true, message_id: sent.result.message_id })}\n`);
}

if (require.main === module) main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});

module.exports = { combineSourceStatus, renderPersonalCfoReport, renderSection };
