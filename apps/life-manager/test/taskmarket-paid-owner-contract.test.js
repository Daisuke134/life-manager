import test from 'node:test';
import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '../..', '..');
const REGISTRY = join(ROOT, 'config/loop-registry.json');
const ENTRYPOINT = join(ROOT, 'skills/earn/taskmarket/scripts/paid-owner');

test('TaskMarket paid owner has a repository entrypoint and production contract row', async () => {
  const registry = JSON.parse(await readFile(REGISTRY, 'utf8'));
  const row = registry.loops['taskmarket-paid-executor'];
  assert.ok(row, 'taskmarket-paid-executor registry row is required');
  assert.equal(row.adapter, 'exec');
  assert.equal(row.domain, 'earn');
  assert.equal(row.effect_class, 'money');
  assert.equal(row.admission_class, 'revenue');
  assert.equal(row.priority, 'critical_paid');
  assert.equal(row.provider_route, 'deterministic');
  assert.equal(row.entrypoint, 'skills/earn/taskmarket/scripts/paid-owner');
  assert.equal(row.state_root, '~/.local/state/life-manager/taskmarket/paid');
  assert.equal(row.log_root, '~/.local/state/life-manager/taskmarket/paid/logs');
  assert.equal(row.cadence.start_interval_seconds, 300);
  await access(ENTRYPOINT, constants.X_OK);
});
