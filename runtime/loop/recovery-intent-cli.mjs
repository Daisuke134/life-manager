#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { buildRecoveryIntent } from './recovery-intent.mjs';

function usage() {
  return 'usage: recovery-intent-cli.mjs --input PATH [--output PATH]';
}

function parseArgs(args) {
  const values = {};
  for (let i = 0; i < args.length; i += 1) {
    const key = args[i];
    if (!['--input', '--output'].includes(key)) throw new Error(usage());
    const value = args[i + 1];
    if (!value || value.startsWith('--')) throw new Error(usage());
    values[key.slice(2)] = value;
    i += 1;
  }
  if (!values.input) throw new Error(usage());
  return values;
}

function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const intent = buildRecoveryIntent(JSON.parse(fs.readFileSync(options.input, 'utf8')));
  const content = `${JSON.stringify(intent, null, 2)}\n`;
  if (options.output) {
    fs.mkdirSync(path.dirname(options.output), { recursive: true, mode: 0o700 });
    fs.writeFileSync(options.output, content, { encoding: 'utf8', mode: 0o600 });
  } else process.stdout.write(content);
  return 0;
}

try { process.exitCode = main(); }
catch (error) { process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`); process.exitCode = 1; }
