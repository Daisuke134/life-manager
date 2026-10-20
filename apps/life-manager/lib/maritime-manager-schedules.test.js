'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { projectMaritimeSchedules, readMaritimeSchedules } = require('./maritime-manager-schedules.js');
const UID = 'lm_11111111-1111-4111-8111-111111111111';
const SHA = 'a'.repeat(40);
const input = { tenantId: UID, releaseSha: SHA, status: 'active', pausedAt: null,
  nextEligibleAt: '2026-10-20T10:15:00.000Z', timezone: 'Asia/Tokyo', nowMs: Date.parse('2026-10-20T09:30:00Z') };
function fileFixture(t) {
  const dataRoot = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'lm-schedules-')));
  t.after(() => fs.rmSync(dataRoot, { recursive: true, force: true }));
  const home = path.join(dataRoot, UID); fs.mkdirSync(home);
  return { dataRoot, home, filename: path.join(home, 'maritime-schedules.json') };
}
test('persisted next occurrences survive readers and a pause removes every wake', t => {
  const fixture = fileFixture(t);
  const snapshot = projectMaritimeSchedules(input);
  assert.deepEqual(snapshot.schedules, [
    { id: `lm-cycle:${UID}`, nextRunAt: input.nextEligibleAt, prompt: 'lm:cycle', enabled: true },
    { id: `lm-report:${UID}`, nextRunAt: '2026-10-20T10:00:00.000Z', prompt: 'lm:report', enabled: true },
  ]);
  fs.writeFileSync(fixture.filename, JSON.stringify(snapshot));
  const read = () => readMaritimeSchedules({ tenantId: UID, releaseSha: SHA, dataRoot: fixture.dataRoot });
  assert.deepEqual(read(), snapshot.schedules);
  assert.deepEqual(read(), snapshot.schedules);
  fs.writeFileSync(fixture.filename, JSON.stringify(projectMaritimeSchedules({ ...input, status: 'paused' })));
  assert.deepEqual(read(), []);
  assert.deepEqual(projectMaritimeSchedules({ ...input, pausedAt: '2026-10-20T09:00:00.000Z' }).schedules, []);
  assert.deepEqual(projectMaritimeSchedules({ ...input, status: 'pending' }).schedules, []);
});
test('daily report uses the registered user timezone across DST rather than adding 24 hours', () => {
  for (const [now, expected] of [
    ['2026-11-01T01:00:00Z', '2026-11-02T00:00:00.000Z'],
    ['2026-03-08T02:00:00Z', '2026-03-08T23:00:00.000Z'],
  ]) {
    const snapshot = projectMaritimeSchedules({ ...input, timezone: 'America/New_York', nowMs: Date.parse(now), nextEligibleAt: null });
    assert.equal(snapshot.schedules.length, 1);
    assert.equal(snapshot.schedules[0].nextRunAt, expected);
  }
});
test('missing snapshot is empty while corruption and foreign identity never clear registered wakes', t => {
  const fixture = fileFixture(t);
  const read = () => readMaritimeSchedules({ tenantId: UID, releaseSha: SHA, dataRoot: fixture.dataRoot });
  assert.deepEqual(read(), []);
  for (const value of ['{', JSON.stringify({ ...projectMaritimeSchedules(input), tenantId: 'other' }),
    JSON.stringify({ ...projectMaritimeSchedules(input), releaseSha: 'b'.repeat(40) }),
    JSON.stringify({ ...projectMaritimeSchedules(input), schedules: [{ id: `lm-cycle:${UID}`, nextRunAt: input.nextEligibleAt, prompt: 'run shell', enabled: true }] })]) {
    fs.writeFileSync(fixture.filename, value);
    assert.throws(read, /schedule/);
  }
});
test('schedule snapshots cannot read through another tenant symlink', t => {
  const fixture = fileFixture(t);
  const foreign = path.join(fixture.dataRoot, 'foreign.json'); fs.writeFileSync(foreign, JSON.stringify(projectMaritimeSchedules(input)));
  fs.symlinkSync(foreign, fixture.filename);
  assert.throws(() => readMaritimeSchedules({ tenantId: UID, releaseSha: SHA, dataRoot: fixture.dataRoot }), /schedule/);
});
test('projection rejects malformed times and ambiguous tenant identity', () => {
  for (const change of [{ nextEligibleAt: 'tomorrow' }, { tenantId: '../foreign' }, { timezone: 'not-a-zone' }, { nowMs: NaN }]) {
    assert.throws(() => projectMaritimeSchedules({ ...input, ...change }), /schedule/);
  }
});

test('projection consumes PostgreSQL timestamp offsets and emits canonical persisted instants', () => {
  assert.equal(projectMaritimeSchedules({ ...input, nextEligibleAt: '2026-10-20T10:15:00+00:00' }).schedules[0].nextRunAt, input.nextEligibleAt);
  assert.deepEqual(projectMaritimeSchedules({ ...input, pausedAt: '2026-10-20T09:00:00+00:00' }).schedules, []);
});
