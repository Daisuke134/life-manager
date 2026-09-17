#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { decideCandidatePromotion } = require("../eval/agent-contract/gate.js");

function usage() {
  return "usage: candidate-promotion-gate.js --input PATH [--output PATH]";
}

function parseArgs(args) {
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (key !== "--input" && key !== "--output") throw new Error(usage());
    const value = args[index + 1];
    if (!value || value.startsWith("--")) throw new Error(usage());
    values[key.slice(2)] = value;
    index += 1;
  }
  if (!values.input) throw new Error(usage());
  return values;
}

function writeResult(file, result) {
  const content = `${JSON.stringify(result, null, 2)}\n`;
  if (!file) process.stdout.write(content);
  else {
    fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    fs.writeFileSync(file, content, { encoding: "utf8", mode: 0o600 });
  }
}

function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const input = JSON.parse(fs.readFileSync(path.resolve(options.input), "utf8"));
  const result = decideCandidatePromotion(input);
  writeResult(options.output, result);
  return result.promote ? 0 : 1;
}

try {
  process.exitCode = main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
