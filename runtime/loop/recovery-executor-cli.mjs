#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildRecoveryApplyPlan } from './recovery-apply-plan.mjs';
import { executeRecoveryPlan } from './recovery-executor.mjs';

function usage() {
  return 'usage: recovery-executor-cli.mjs --intent PATH [--release-root PATH] [--registry PATH] [--output PATH]';
}

function parseArgs(args) {
  const values = {};
  for (let i = 0; i < args.length; i += 1) {
    const key = args[i];
    if (!['--intent', '--release-root', '--registry', '--output'].includes(key)) throw new Error(usage());
    const value = args[i + 1];
    if (!value || value.startsWith('--')) throw new Error(usage());
    values[key.slice(2).replaceAll('-', '_')] = value;
    i += 1;
  }
  if (!values.intent) throw new Error(usage());
  return values;
}

function writeOutput(file, value) {
  const content = `${JSON.stringify(value, null, 2)}\n`;
  if (!file) process.stdout.write(content);
  else {
    fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    fs.writeFileSync(file, content, { encoding: 'utf8', mode: 0o600 });
  }
}

async function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const releaseRoot = path.resolve(
    options.release_root || process.env.LIFE_MANAGER_RELEASE_ROOT || path.join(os.homedir(), 'loops', 'current'),
  );
  const registryPath = path.resolve(options.registry || path.join(releaseRoot, 'config', 'loop-registry.json'));
  const intent = JSON.parse(fs.readFileSync(path.resolve(options.intent), 'utf8'));
  const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
  const plan = buildRecoveryApplyPlan({ intent, registry });
  const result = await executeRecoveryPlan({ plan, registry, releaseRoot });
  writeOutput(options.output, result);
  return result.ok ? 0 : 1;
}

try {
  process.exitCode = await main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
