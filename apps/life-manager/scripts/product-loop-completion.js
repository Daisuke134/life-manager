#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");

const { buildProductLoopCompletionManifest } = require("../lib/product-onboarding.js");

function usage() {
  return "usage: product-loop-completion.js --host local|cloud --release-sha SHA --observations PATH [--output PATH]";
}

function parseArgs(args) {
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (!["--host", "--release-sha", "--observations", "--output"].includes(key)) {
      throw new Error(usage());
    }
    const value = args[index + 1];
    if (!value || value.startsWith("--")) throw new Error(usage());
    values[key.slice(2).replaceAll("-", "_ ").replaceAll(" ", "")] = value;
    index += 1;
  }
  if (!values.host || !values.release_sha || !values.observations) throw new Error(usage());
  return values;
}

function writePrivate(pathname, content) {
  const parent = path.dirname(pathname);
  fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
  fs.chmodSync(parent, 0o700);
  const temporary = `${pathname}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, content, { encoding: "utf8", mode: 0o600 });
  fs.chmodSync(temporary, 0o600);
  fs.renameSync(temporary, pathname);
  fs.chmodSync(pathname, 0o600);
}

function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const observations = JSON.parse(fs.readFileSync(options.observations, "utf8"));
  const manifest = buildProductLoopCompletionManifest({
    host: options.host,
    release_sha: options.release_sha,
    observations,
  });
  const content = `${JSON.stringify(manifest, null, 2)}\n`;
  if (options.output) writePrivate(options.output, content);
  else process.stdout.write(content);
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
