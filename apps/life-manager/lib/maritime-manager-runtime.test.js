'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { buildMaritimeManagerCycleJob, buildMaritimeManagerReportJob } = require('./maritime-manager-runtime.js');
const UID = 'lm_11111111-1111-4111-8111-111111111111';
const SHA = 'a'.repeat(40);
const cycle = { tenantId: UID, occurrenceId: 'cycle-1', dateKey: '2026-10-20', releaseSha: SHA };

test('same_occurrence_is_one_runtime_job', () => {
  const first = buildMaritimeManagerCycleJob(cycle);
  assert.deepEqual(buildMaritimeManagerCycleJob(cycle), first);
  assert.notEqual(buildMaritimeManagerCycleJob({ ...cycle, occurrenceId: 'cycle-2' }).job_id, first.job_id);
  assert.notEqual(buildMaritimeManagerCycleJob({ ...cycle, tenantId: 'lm_22222222-2222-4222-8222-222222222222' }).job_id, first.job_id);
  assert.equal(first.effect_class, 'money');
  assert.equal(first.max_attempts, 1);
  assert.equal(first.capability, 'maritime.manager.cycle');
  assert.equal(first.input_refs.enrollment_ref, `maritime-enrollment://${UID}`);
  assert.equal(first.input_refs.date_ref, 'date://2026-10-20');
});

test('date or release updates cannot bypass the existing occurrence effect fence', () => {
  const first = buildMaritimeManagerCycleJob(cycle);
  const changed = buildMaritimeManagerCycleJob({ ...cycle, dateKey: '2026-10-21', releaseSha: 'b'.repeat(40) });
  assert.equal(changed.job_id, first.job_id);
  assert.equal(changed.effect_key, first.effect_key);
  assert.notDeepEqual(changed.input_refs, first.input_refs);
});

test('daily email jobs use a separate tenant and period message fence', () => {
  const input = { tenantId: UID, periodKey: 'maritime:daily:2026-10-20', releaseSha: SHA };
  const first = buildMaritimeManagerReportJob(input);
  assert.deepEqual(buildMaritimeManagerReportJob(input), first);
  assert.notEqual(buildMaritimeManagerReportJob({ ...input, periodKey: 'maritime:daily:2026-10-21' }).job_id, first.job_id);
  assert.equal(first.effect_class, 'message');
  assert.equal(first.max_attempts, 1);
  assert.notEqual(first.effect_key, buildMaritimeManagerCycleJob(cycle).effect_key);
});

test('invalid dates and path-like occurrence ids cannot enter the queue', () => {
  for (const patch of [{ dateKey: '2026-02-30' }, { occurrenceId: '../other-user' }, { releaseSha: 'invalid' }]) {
    assert.throws(() => buildMaritimeManagerCycleJob({ ...cycle, ...patch }), /invalid/);
  }
  assert.throws(() => buildMaritimeManagerReportJob({ tenantId: UID, periodKey: 'maritime:daily:2026-02-30', releaseSha: SHA }), /invalid/);
});
