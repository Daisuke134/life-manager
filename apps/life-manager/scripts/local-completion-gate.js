#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");

const {
  buildProductLoopCompletionManifest,
  evaluateLocalCompletionGate,
} = require("../lib/product-onboarding.js");

function usage() {
  return "usage: local-completion-gate.js --manifest PATH [--runtime-status PATH] [--output PATH]";
}

function parseArgs(args) {
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (!["--manifest", "--runtime-status", "--output"].includes(key)) throw new Error(usage());
    const value = args[index + 1];
    if (!value || value.startsWith("--")) throw new Error(usage());
    values[key.slice(2).replaceAll("-", "_")] = value;
    index += 1;
  }
  if (!values.manifest) throw new Error(usage());
  return values;
}

function writePrivate(pathname, content) {
  const parent = path.dirname(pathname);
  let parentExisted = true;
  try {
    if (!fs.statSync(parent).isDirectory()) throw new Error("output parent is not a directory");
  } catch (error) {
    if (error && error.code === "ENOENT") parentExisted = false;
    else throw error;
  }
  fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
  if (!parentExisted) fs.chmodSync(parent, 0o700);
  const temporary = `${pathname}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, content, { encoding: "utf8", mode: 0o600 });
  fs.chmodSync(temporary, 0o600);
  fs.renameSync(temporary, pathname);
  fs.chmodSync(pathname, 0o600);
}

function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const manifest = JSON.parse(fs.readFileSync(options.manifest, "utf8"));
  const runtimeRows = options.runtime_status
    ? JSON.parse(fs.readFileSync(options.runtime_status, "utf8")) : undefined;
  const effectiveManifest = runtimeRows === undefined ? manifest : buildProductLoopCompletionManifest({
    host: manifest.host,
    release_sha: manifest.release_sha,
    observations: manifest.loops,
    runtime_rows: runtimeRows,
  });
  const gate = evaluateLocalCompletionGate(effectiveManifest);
  const content = `${JSON.stringify(gate, null, 2)}\n`;
  if (options.output) writePrivate(options.output, content);
  else process.stdout.write(content);
  return gate.decision === "pass" ? 0 : 1;
}

try {
  process.exitCode = main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
