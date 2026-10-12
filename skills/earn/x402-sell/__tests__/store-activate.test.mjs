import test from 'node:test';
import assert from 'node:assert/strict';
import childProcess from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';

import { activateExperiment, sellerLabelFor } from '../store-activate.mjs';

test('sellerLabelFor maps each isolated agent home to its own launchd seller', () => {
  assert.equal(sellerLabelFor({ ANICCA_HOME: '/tmp/x402-activation-fixture/.blockrun' }), 'ai.anicca.x402-franklin1');
  assert.equal(sellerLabelFor({ ANICCA_HOME: '/tmp/x402-activation-fixture/.franklin2-home/.blockrun' }), 'ai.anicca.x402-franklin2');
  assert.equal(sellerLabelFor({ ANICCA_HOME: '/tmp/x402-activation-fixture/.anicca-founder' }), 'ai.anicca.x402-claude-p');
  assert.equal(sellerLabelFor({ ANICCA_HOME: '/tmp/unknown' }), null);
});

test('activateExperiment restarts only the matching seller then re-registers', async () => {
  const calls = [];
  const out = await activateExperiment(
    { ANICCA_HOME: '/tmp/x402-activation-fixture/.blockrun', X402_PUBLIC_URL: 'https://seller.example' },
    {
      restart: async (label) => calls.push(['restart', label]),
      wait: async () => calls.push(['wait']),
      update: async () => { calls.push(['update']); return { registered: true, productCount: 5 }; },
    },
  );

  assert.deepEqual(calls, [
    ['restart', 'ai.anicca.x402-franklin1'],
    ['wait'],
    ['update'],
  ]);
  assert.deepEqual(out, { activated: true, restarted: true, registered: true, productCount: 5 });
});

test('activateExperiment fails honestly for an unknown home and performs no side effect', async () => {
  let called = false;
  const out = await activateExperiment({ ANICCA_HOME: '/tmp/unknown' }, {
    restart: async () => { called = true; },
    update: async () => { called = true; },
  });
  assert.equal(called, false);
  assert.deepEqual(out, { activated: false, restarted: false, reason: 'unknown seller instance' });
});


test('default activation delegates to the matching canonical owner before registration', async () => {
  const original = childProcess.execFile;
  const calls = [];
  childProcess.execFile = (command, args, options, callback) => {
    calls.push({ command, args });
    callback(null, '', '');
  };
  syncBuiltinESMExports();
  try {
    const out = await activateExperiment({ ANICCA_HOME: '/tmp/x402-activation-fixture/.blockrun' }, {
      wait: async () => {},
      update: async () => ({ registered: true }),
    });
    assert.equal(calls.length, 1);
    assert.match(calls[0].command, /\/bin\/lm-loop$/);
    assert.deepEqual(calls[0].args, ['restart', 'x402-franklin1']);
    assert.equal(out.activated, true);
  } finally {
    childProcess.execFile = original;
    syncBuiltinESMExports();
  }
});


test('canonical lifecycle failure stops activation before registration', async () => {
  const original = childProcess.execFile;
  let registered = false;
  childProcess.execFile = (_command, _args, _options, callback) => {
    callback(new Error('GUI preflight rejected'));
  };
  syncBuiltinESMExports();
  try {
    const out = await activateExperiment({ ANICCA_HOME: '/tmp/x402-activation-fixture/.blockrun' }, {
      wait: async () => assert.fail('must not wait after rejected restart'),
      update: async () => { registered = true; return { registered: true }; },
    });
    assert.equal(registered, false);
    assert.equal(out.activated, false);
    assert.equal(out.restarted, false);
    assert.match(out.reason, /GUI preflight rejected/);
  } finally {
    childProcess.execFile = original;
    syncBuiltinESMExports();
  }
});
