'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { runMaritimeCycle } = require('./run-cycle.js');
const UID = 'lm_11111111-1111-4111-8111-111111111111';
const args = ['--tenant', UID, '--occurrence', 'cycle-1', '--date', '2026-10-20'];
test('detached exec prepares its own runtime and invokes only the existing Python wrapper', () => {
  const calls = [];
  const prepared = { config: { tenantId: UID }, env: { AGENT_RUNNER_CONFIG: '/data/tenant/runner.json', LM_CLOUD_MODEL_API_KEY: 'fixture' } };
  const code = runMaritimeCycle(args, { env: { LM_RUNTIME_TENANT_ID: UID },
    prepareRuntime: input => { calls.push(['prepare', input]); return prepared; },
    spawnImpl: (...input) => { calls.push(['spawn', ...input]); return { status: 0 }; } });
  assert.equal(code, 0);
  assert.equal(calls[0][0], 'prepare');
  assert.deepEqual(calls[1], ['spawn', 'python3', ['/app/skills/capafy-autopublish/scripts/cloud_cycle.py', ...args],
    { cwd: '/app', env: prepared.env, stdio: 'inherit' }]);
  assert.equal(JSON.stringify(calls[1].slice(1,3)).includes('fixture'), false);
});
test('caller cannot change tenant, inject options, duplicate arguments, or supply invalid dates', () => {
  for (const argv of [ ['--tenant', '../other', ...args.slice(2)], [...args, '--shell', 'unsafe'],
    [...args, '--date', '2026-10-21'], [...args.slice(0,-1), '2026-02-30'],
    ['--tenant', 'lm_22222222-2222-4222-8222-222222222222', ...args.slice(2)] ]) {
    let calls = 0;
    assert.throws(() => runMaritimeCycle(argv, { env: { LM_RUNTIME_TENANT_ID: UID }, prepareRuntime: () => { calls++; } }), /invalid/);
    assert.equal(calls, 0);
  }
});
test('child failures remain nonzero and never get rewritten as completed', () => {
  for (const result of [{ status: 2 }, { status: null, signal: 'SIGTERM' }, { error: new Error('private') }]) {
    assert.notEqual(runMaritimeCycle(args, { env: { LM_RUNTIME_TENANT_ID: UID },
      prepareRuntime: () => ({ env: {} }), spawnImpl: () => result }), 0);
  }
});
