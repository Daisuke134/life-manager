#!/usr/bin/env node

"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { createDigitalOceanRuntimeClient } = require("../lib/digitalocean-runtime-client.js");
const { runDigitalOceanInfrastructureCanary } = require("../lib/digitalocean-infrastructure-canary.js");

const RELEASE_SHA = /^[a-f0-9]{40}$/;

function usage() {
  return "usage: digitalocean-infrastructure-canary.js --release-sha SHA --output ABSOLUTE_PATH --spec ABSOLUTE_PATH --name-prefix NAME";
}

function parseArgs(args) {
  const values = {};
  const allowed = new Set(["--release-sha", "--output", "--spec", "--name-prefix"]);
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index];
    const value = args[index + 1];
    if (!allowed.has(key) || !value || value.startsWith("--")) throw new Error(usage());
    values[key.slice(2).replaceAll("-", "_")] = value;
  }
  if (!RELEASE_SHA.test(String(values.release_sha || "")) || !values.output
      || !values.spec || !values.name_prefix) throw new Error(usage());
  if (!path.isAbsolute(values.output) || !path.isAbsolute(values.spec)) {
    throw new Error("DigitalOcean canary paths must be absolute");
  }
  return values;
}

function writePrivate(pathname, value) {
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
  const temporary = `${pathname}.tmp-${process.pid}-${crypto.randomUUID()}`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode: 0o600, flag: "wx" });
  fs.chmodSync(temporary, 0o600);
  fs.renameSync(temporary, pathname);
  fs.chmodSync(pathname, 0o600);
}

async function runCli(args, injected = {}) {
  const options = parseArgs(args);
  if (!injected.client || typeof injected.runCanary !== "function") {
    throw new Error("DigitalOcean canary runtime unavailable");
  }
  const readback = await injected.runCanary({
    namePrefix: options.name_prefix,
    specPath: options.spec,
  }, { client: injected.client });
  const digest = crypto.createHash("sha256").update(JSON.stringify(readback)).digest("hex");
  const timestamp = typeof injected.now === "function" ? injected.now() : new Date().toISOString();
  const receipt = Object.freeze({
    run_id: `digitalocean-infrastructure:${digest.slice(0, 16)}`,
    owner_id: "life-manager-cloud-promotion",
    occurrence_id: `digitalocean-infrastructure:${digest}`,
    release_sha: options.release_sha,
    phase: "provider_compatibility_canary",
    command: "doctl harness-runtime model-free two-session canary",
    exit_code: 0,
    status: "verified",
    effect: "none",
    readback,
    provider_receipt_id: `digitalocean-infrastructure://sha256/${digest}`,
    evidence_refs: [options.output],
    error_class: null,
    retryable: false,
    next_action: "run_agent_parity_canary",
    verified_at: timestamp,
  });
  writePrivate(options.output, receipt);
  return receipt;
}

function commandBoundary(binary, args) {
  const result = spawnSync(binary, args, {
    encoding: "utf8",
    timeout: 180_000,
    maxBuffer: 2 * 1024 * 1024,
    env: process.env,
  });
  return {
    exitCode: Number.isInteger(result.status) ? result.status : 1,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
  };
}

async function main(args = process.argv.slice(2)) {
  const client = createDigitalOceanRuntimeClient({
    binary: process.env.LM_DOCTL_PATH || "/Users/anicca/.local/bin/doctl",
    run: commandBoundary,
  });
  await runCli(args, { client, runCanary: runDigitalOceanInfrastructureCanary });
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}

module.exports = { commandBoundary, parseArgs, runCli, writePrivate };
