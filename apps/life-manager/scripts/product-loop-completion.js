#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");

const {
  buildDefaultProductLoopObservations,
  buildProductLoopCompletionManifest,
} = require("../lib/product-onboarding.js");

function usage() {
  return "usage: product-loop-completion.js --host local|cloud --release-sha SHA [--observations PATH | --runtime-status PATH] [--output PATH]";
}

function parseArgs(args) {
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (!["--host", "--release-sha", "--observations", "--runtime-status", "--output"].includes(key)) {
      throw new Error(usage());
    }
    const value = args[index + 1];
    if (!value || value.startsWith("--")) throw new Error(usage());
    values[key.slice(2).replaceAll("-", "_ ").replaceAll(" ", "")] = value;
    index += 1;
  }
  if (!values.host || !values.release_sha || (!values.observations && !values.runtime_status)) {
    throw new Error(usage());
  }
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
  const runtimeRows = options.runtime_status
    ? JSON.parse(fs.readFileSync(options.runtime_status, "utf8")) : undefined;
  const observations = options.observations
    ? JSON.parse(fs.readFileSync(options.observations, "utf8"))
    : buildDefaultProductLoopObservations({
      host: options.host,
      release_sha: options.release_sha,
      runtime_rows: runtimeRows,
    });
  const manifest = buildProductLoopCompletionManifest({
    host: options.host,
    release_sha: options.release_sha,
    observations,
    ...(runtimeRows === undefined ? {} : { runtime_rows: runtimeRows }),
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
