import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const ENTRY = path.join(HERE, 'foundation-scope-guard.mjs');

test('scope guard passes for the real worktree when every current change belongs to its atomic task', () => {
  const result = spawnSync(process.execPath, [
    ENTRY,
    '--task', 'FOUNDATION-SCOPE-GUARD',
    '--worktree', ROOT,
  ], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  const output = JSON.parse(result.stdout);
  assert.equal(output.schema_version, 'foundation.scope.check.v1');
  assert.equal(output.decision, 'pass');
  assert.deepEqual(output.forbidden_paths, []);
  assert.deepEqual(output.out_of_scope_paths, []);
  assert.ok(output.changed_paths.includes('runtime/loop/foundation-scope.json'));
  assert.ok(output.changed_paths.includes('runtime/loop/foundation-scope-guard.mjs'));
});

test('scope guard rejects an unknown task before inspecting any external system', () => {
  const result = spawnSync(process.execPath, [
    ENTRY,
    '--task', 'NOT-A-FOUNDATION-TASK',
    '--worktree', ROOT,
  ], { encoding: 'utf8' });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /unknown foundation task|usage/u);
});
