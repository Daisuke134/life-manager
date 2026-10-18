import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('acquisition controller keeps a private action log (label retired with the402)', () => {
  const runner = readFileSync(new URL('../acquisition-controller.mjs', import.meta.url), 'utf8');
  const boot = readFileSync(new URL('../acquisition-controller-boot.sh', import.meta.url), 'utf8');

  assert.match(runner, /runAcquisitionCycle/);
  assert.match(runner, /the402-inbox\.sqlite/);
  assert.match(runner, /x402-acquisition-actions\.jsonl/);
  assert.match(runner, /0o600/);
  assert.doesNotMatch(runner, /Moltbook|posts\/.*comments|create.*post/i);
  assert.match(boot, /exec \/usr\/bin\/env node "\$DIR\/acquisition-controller\.mjs"/);
});
