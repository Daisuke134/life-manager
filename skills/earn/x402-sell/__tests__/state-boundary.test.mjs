import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { resolveX402StateDir } from '../state-paths.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');

test('x402 state precedence is explicit, loop root, then shared default', () => {
  assert.equal(resolveX402StateDir({
    HOME: '/tmp/home',
    LIFE_MANAGER_STATE_ROOT: '/tmp/loop',
    X402_STATE_DIR: '/tmp/x402',
  }), '/tmp/x402');
  assert.equal(resolveX402StateDir({
    HOME: '/tmp/home',
    LIFE_MANAGER_STATE_ROOT: '/tmp/loop',
  }), '/tmp/loop');
  assert.equal(resolveX402StateDir({ HOME: '/tmp/home' }),
    '/tmp/home/.local/state/life-manager/x402-sell');
});

test('shell entrypoints source the shared runtime environment', () => {
  for (const name of [
    'acquisition-controller-boot.sh',
    'sale-observer-boot.sh',
    'settlement-recorder-boot.sh',
  ]) {
    const source = readFileSync(join(ROOT, name), 'utf8');
    assert.match(source, /\. "\$DIR\/runtime-env\.sh"/);
    assert.doesNotMatch(source, /\.anicca\/state/);
  }
  const runtime = readFileSync(join(ROOT, 'runtime-env.sh'), 'utf8');
  assert.match(runtime, /X402_STATE_DIR:-\$\{LIFE_MANAGER_STATE_ROOT:-\$HOME\/\.local\/state\/life-manager\/x402-sell\}/);
});

test('active state readers and writers do not default beside the release', () => {
  for (const name of [
    'acquisition-controller.mjs',
    'sale-observer.mjs',
    'settlement-recorder.mjs',
    'scout-market.mjs',
    'product-gaps.mjs',
    'store-experiment.mjs',
    'store-improve.mjs',
    'store-review.mjs',
    'serve.mjs',
    'serve-v2.mjs',
  ]) {
    const source = readFileSync(join(ROOT, name), 'utf8');
    assert.doesNotMatch(source, /join\([^\n]*(?:HERE|import\.meta|fileURLToPath)[^\n]*['"]state['"]/);
    assert.doesNotMatch(source, /\.anicca['"], ['"]state/);
  }
});
