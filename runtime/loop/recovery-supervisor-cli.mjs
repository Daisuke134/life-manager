#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildRecoveryApplyPlan } from './recovery-apply-plan.mjs';
import { executeRecoveryPlan } from './recovery-executor.mjs';
import { consumeRecoveryIntentQueue } from './recovery-supervisor.mjs';

function usage() {
  return 'usage: recovery-supervisor-cli.mjs [--queue PATH] [--journal PATH] [--release-root PATH] [--registry PATH]';
}

function parseArgs(args) {
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (!['--queue', '--journal', '--release-root', '--registry'].includes(key)) throw new Error(usage());
    const value = args[index + 1];
    if (!value || value.startsWith('--')) throw new Error(usage());
    values[key.slice(2).replaceAll('-', '_')] = value;
    index += 1;
  }
  return values;
}

async function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const recoveryRoot = path.join(os.homedir(), '.local', 'state', 'life-manager', 'recovery');
  const queuePath = path.resolve(
    options.queue || process.env.LIFE_MANAGER_RECOVERY_INTENTS_PATH || path.join(recoveryRoot, 'intents.jsonl'),
  );
  const journalPath = path.resolve(
    options.journal || process.env.LIFE_MANAGER_RECOVERY_SUPERVISOR_JOURNAL_PATH
      || path.join(recoveryRoot, 'supervisor.jsonl'),
  );
  const releaseRoot = path.resolve(
    options.release_root || process.env.LIFE_MANAGER_RELEASE_ROOT || path.join(os.homedir(), 'loops', 'current'),
  );
  const registryPath = path.resolve(options.registry || path.join(releaseRoot, 'config', 'loop-registry.json'));
  const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
  const result = await consumeRecoveryIntentQueue({
    queuePath,
    journalPath,
    executeIntent: async (intent) => {
      const plan = buildRecoveryApplyPlan({ intent, registry });
      return executeRecoveryPlan({ plan, registry, releaseRoot });
    },
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  return result.ok ? 0 : 1;
}

try {
  process.exitCode = await main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
