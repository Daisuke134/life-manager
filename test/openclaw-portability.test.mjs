import assert from 'node:assert/strict';
import test from 'node:test';
import {resolveHarnessPaths} from '../runtime/openclaw/paths.mjs';

test('portable paths retain the existing LM data root and never global OpenClaw', () => {
  for (const home of ['/home/alice', '/Users/bob', '/srv/lm']) {
    const p = resolveHarnessPaths({}, home);
    assert.equal(p.stateRoot, `${home}/.local/state/life-manager/openclaw`);
    assert.equal(p.credentialFile, `${home}/.local/share/anicca/credentials.json`);
  }
  assert.throws(() => resolveHarnessPaths({LM_DATA_DIR: 'relative'}, '/home/alice'));
  assert.throws(() => resolveHarnessPaths({LM_CREDENTIALS_FILE: 'relative'}, '/home/alice'));
});
