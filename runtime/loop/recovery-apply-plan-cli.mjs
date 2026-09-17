#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { buildRecoveryApplyPlan } from './recovery-apply-plan.mjs';

function usage() { return 'usage: recovery-apply-plan-cli.mjs --intent PATH [--registry PATH]'; }
function parseArgs(args) {
  const values = {};
  for (let i = 0; i < args.length; i += 1) {
    const key = args[i];
    if (!["--intent", "--registry"].includes(key)) throw new Error(usage());
    const value = args[i + 1];
    if (!value || value.startsWith('--')) throw new Error(usage());
    values[key.slice(2)] = value;
    i += 1;
  }
  if (!values.intent) throw new Error(usage());
  return values;
}

function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const root = process.cwd();
  const registryPath = path.resolve(options.registry || path.join(root, 'config/loop-registry.json'));
  const intent = JSON.parse(fs.readFileSync(path.resolve(options.intent), 'utf8'));
  const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
  process.stdout.write(`${JSON.stringify(buildRecoveryApplyPlan({ intent, registry }), null, 2)}\n`);
  return 0;
}

try { process.exitCode = main(); }
catch (error) { process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`); process.exitCode = 1; }
