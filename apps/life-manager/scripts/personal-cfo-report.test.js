"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

test("personal CFO fixture report does not render incomplete empty transactions as zero", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "personal-cfo-report-"));
  try {
    const fixture = path.join(root, "fixture.json");
    fs.writeFileSync(fixture, JSON.stringify({
      accounts: [{ balance_jpy: 504302, observed_at: "2026-10-02T06:00:00.000Z" }],
      transactions: [],
      source: { status: "partial", reason: "transaction_completeness_unknown" },
    }));
    const result = spawnSync(process.execPath, [path.join(__dirname, "personal-cfo-report.js"), "--fixture", fixture], {
      encoding: "utf8",
    });
    assert.equal(result.status, 1);
    assert.match(result.stdout, /確認済み資産: ¥504,302/);
    assert.match(result.stdout, /支出: 未確認/);
    assert.doesNotMatch(result.stdout, /支出 ¥0/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
