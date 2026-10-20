"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { capafyRowsToFinancialRecords, readCapafyFinancialRecords } = require("./financial-record-capafy.js");
const { projectFinancialRecord } = require("./financial-record-contract.js");

test("capafy daily revenue and refunds become verified business records", () => {
  const records = capafyRowsToFinancialRecords([
    { date: "2026-09-26", revenue: 3.98, refundAmount: 0 },
    { date: "2026-09-25", revenue: 0, refundAmount: 1.5 },
    { date: "2026-09-24", revenue: 0, refundAmount: 0 },
  ], { subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z" });

  const projected = records.map(projectFinancialRecord);
  assert.equal(records.length, 2);
  const revenue = projected.find((r) => r.kind === "business_revenue");
  assert.equal(revenue.amount_minor, 398);
  assert.equal(revenue.direction, "credit");
  assert.equal(revenue.currency, "USD");
  assert.equal(revenue.occurred_at, "2026-09-26T00:00:00.000Z");
  assert.equal(revenue.source.provider, "capafy");
  const refund = projected.find((r) => r.kind === "business_cost");
  assert.equal(refund.amount_minor, 150);
  assert.equal(refund.direction, "debit");
});

test("capafy rows without a date or with malformed input are skipped, not fabricated", () => {
  assert.deepEqual(capafyRowsToFinancialRecords([{ revenue: 5 }, null, {}], {
    subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z",
  }), []);
  assert.deepEqual(capafyRowsToFinancialRecords(null, {
    subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z",
  }), []);
});

test("re-running the same day is idempotent (stable record_id)", () => {
  const opts = { subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z" };
  const first = capafyRowsToFinancialRecords([{ date: "2026-09-26", revenue: 3.98 }], opts);
  const second = capafyRowsToFinancialRecords([{ date: "2026-09-26", revenue: 3.98 }], opts);
  assert.equal(first[0].record_id, second[0].record_id);
});

const binding = { tenantId: 'lm_11111111-1111-4111-8111-111111111111',
  provider: 'capafy', subjectId: 'seller-owner-hash', credentialRef: 'private://tenant-capafy' };
const window = { periodStart: '2026-10-19', periodEnd: '2026-10-20' };
function officialSnapshot() {
  return { tenantId: binding.tenantId, provider: 'capafy', subjectId: binding.subjectId,
    ...window, observedAt: '2026-10-20T12:00:00Z', complete: true, currency: 'USD',
    rows: [{ date: '2026-10-19', revenue: '3.98', refundAmount: '1.50' }],
    evidenceRefs: ['capafy://readback/official-1'] };
}

test('trusted collector binds verified revenue to the tenant and official evidence', async () => {
  const records = await readCapafyFinancialRecords({ binding, ...window }, {
    readOfficialSnapshot: async () => officialSnapshot(),
  });
  assert.equal(records.length, 2);
  assert.equal(records[0].subject_id, binding.tenantId);
  assert.equal(records[0].amount_minor, 398);
  assert.equal(records[1].amount_minor, 150);
  assert.deepEqual(records[0].verification.evidence_refs, ['capafy://readback/official-1']);
  records.forEach(projectFinancialRecord);
});

test('incomplete_or_foreign_provider_snapshot_never_becomes_verified_revenue', async () => {
  for (const patch of [ { complete: false }, { complete: 'true' }, { tenantId: 'other-tenant' },
    { subjectId: 'other-seller' }, { provider: 'other-provider' }, { currency: 'EUR' },
    { periodStart: '2026-10-18' }, { periodEnd: '2026-10-21' }, { observedAt: null },
    { evidenceRefs: [] }, { evidenceRefs: ['not-a-receipt'] }, { rows: null } ]) {
    await assert.rejects(readCapafyFinancialRecords({ binding, ...window }, {
      readOfficialSnapshot: async () => ({ ...officialSnapshot(), ...patch }),
    }), /capafy_snapshot_invalid/);
  }
});

test('invalid amounts dates and duplicate days reject the whole snapshot without partial revenue', async () => {
  for (const row of [ { revenue: null }, { revenue: '' }, { revenue: true },
    { revenue: 'NaN' }, { revenue: '-1' }, { revenue: '1.001' },
    { revenue: '9007199254740992' }, { refundAmount: null },
    { date: '2026-02-30' }, { date: '2026-10-18' } ]) {
    const snapshot = officialSnapshot();
    snapshot.rows.push({ date: '2026-10-20', revenue: '1.00', refundAmount: '0.00', ...row });
    await assert.rejects(readCapafyFinancialRecords({ binding, ...window }, {
      readOfficialSnapshot: async () => snapshot,
    }), /capafy_snapshot_invalid/);
  }
  const duplicate = officialSnapshot();
  duplicate.rows.push({ ...duplicate.rows[0] });
  await assert.rejects(readCapafyFinancialRecords({ binding, ...window }, {
    readOfficialSnapshot: async () => duplicate,
  }), /capafy_snapshot_invalid/);
});

test('missing collector cannot promote a model supplied snapshot and provider failure stays unknown', async () => {
  await assert.rejects(readCapafyFinancialRecords({ binding, ...window, snapshot: officialSnapshot() }), /capafy_collector_unconfigured/);
  await assert.rejects(readCapafyFinancialRecords({ binding, ...window }, {
    readOfficialSnapshot: async () => { throw new Error('fixture-token-must-not-leak'); },
  }), (error) => error.message === 'capafy_snapshot_unavailable');
});

test('observed zero is empty records but malformed zero rows are not fabricated', async () => {
  const snapshot = officialSnapshot();
  snapshot.rows = [{ date: '2026-10-19', revenue: 0, refundAmount: 0 }];
  assert.deepEqual(await readCapafyFinancialRecords({ binding, ...window }, {
    readOfficialSnapshot: async () => snapshot,
  }), []);
});
