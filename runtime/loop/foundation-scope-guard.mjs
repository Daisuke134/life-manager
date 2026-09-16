#!/usr/bin/env node

/**
 * foundation-scope-guard.mjs — read-only commit-boundary guard for the six foundation TODOs.
 *
 * It reads a versioned allowlist, inspects the actual Git worktree (staged, unstaged, and
 * untracked files), and exits non-zero when a change is outside the selected atomic task or inside
 * a globally forbidden provider/test tree. It never edits files, starts a loop, opens a browser, or
 * contacts a provider. The guard is deliberately separate from test/effect evidence: passing it
 * proves only scope hygiene.
 *
 * Usage:
 *   node runtime/loop/foundation-scope-guard.mjs \
 *     --task FOUNDATION-01-RECEIPT-MANIFEST \
 *     [--worktree /absolute/worktree] [--base HEAD]
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_MANIFEST = path.join(HERE, 'foundation-scope.json');
const SAFE_TASK = /^[A-Z0-9][A-Z0-9-]{0,63}$/;

function usage() {
  return 'usage: foundation-scope-guard.mjs --task TASK [--worktree PATH] [--base REF]';
}

function parseArgs(args) {
  const result = { worktree: path.resolve(HERE, '..', '..'), base: 'HEAD' };
  for (let i = 0; i < args.length; i += 1) {
    const key = args[i];
    if (!['--task', '--worktree', '--base'].includes(key)) throw new Error(usage());
    const value = args[i + 1];
    if (!value || value.startsWith('--')) throw new Error(usage());
    if (key === '--task') result.task = value;
    if (key === '--worktree') result.worktree = path.resolve(value);
    if (key === '--base') result.base = value;
    i += 1;
  }
  if (!result.task || !SAFE_TASK.test(result.task)) throw new Error(usage());
  return result;
}

function readManifest(worktree) {
  const manifestPath = path.resolve(worktree, path.relative(worktree, DEFAULT_MANIFEST));
  let value;
  try {
    value = JSON.parse(readFileSync(manifestPath, 'utf8'));
  } catch (error) {
    throw new Error(`scope manifest unreadable: ${error.message}`);
  }
  if (!value || value.schema_version !== 1 || value.scope !== 'life-manager-foundation'
    || !Array.isArray(value.global_forbidden_prefixes) || !value.tasks
    || typeof value.tasks !== 'object' || Array.isArray(value.tasks)) {
    throw new Error('scope manifest invalid');
  }
  return value;
}

function runGit(worktree, args) {
  const result = spawnSync('git', ['-C', worktree, ...args], { encoding: 'utf8' });
  if (result.error) throw new Error(`git unavailable: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`git ${args[0]} failed`);
  return result.stdout;
}

function changedPaths(worktree, base) {
  const tracked = runGit(worktree, ['diff', '--name-only', '--relative', base])
    .split('\n').map((item) => item.trim()).filter(Boolean);
  const untracked = runGit(worktree, ['ls-files', '--others', '--exclude-standard'])
    .split('\n').map((item) => item.trim()).filter(Boolean);
  return [...new Set([...tracked, ...untracked])].sort();
}

function matches(pathname, pattern) {
  return pattern.endsWith('/') ? pathname.startsWith(pattern) : pathname === pattern;
}

function checkScope({ task, worktree, base }, manifest) {
  const taskSpec = manifest.tasks[task];
  if (!taskSpec || !Array.isArray(taskSpec.allowed_paths)) {
    throw new Error(`unknown foundation task: ${task}`);
  }
  const paths = changedPaths(worktree, base);
  const forbidden = paths.filter((pathname) => manifest.global_forbidden_prefixes.some((prefix) => matches(pathname, prefix)));
  const outOfScope = paths.filter((pathname) => !taskSpec.allowed_paths.some((pattern) => matches(pathname, pattern)));
  const result = {
    schema_version: 'foundation.scope.check.v1',
    scope: manifest.scope,
    task,
    base,
    decision: forbidden.length || outOfScope.length ? 'block' : 'pass',
    changed_paths: paths,
    forbidden_paths: [...new Set(forbidden)].sort(),
    out_of_scope_paths: [...new Set(outOfScope)].sort(),
  };
  return Object.freeze(result);
}

try {
  const options = parseArgs(process.argv.slice(2));
  const manifest = readManifest(options.worktree);
  const result = checkScope(options, manifest);
  process.stdout.write(`${JSON.stringify(result)}\n`);
  process.exitCode = result.decision === 'pass' ? 0 : 1;
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 2;
}

