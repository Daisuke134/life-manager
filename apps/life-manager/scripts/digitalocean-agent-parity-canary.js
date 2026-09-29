#!/usr/bin/env node

"use strict";

const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { createDigitalOceanRuntimeClient } = require("../lib/digitalocean-runtime-client.js");
const { runDigitalOceanAgentParity } = require("../lib/digitalocean-agent-parity.js");
const { runFixture } = require("./cloud-kernel-parity-fixture.js");
const { commandBoundary, writePrivate } = require("./digitalocean-infrastructure-canary.js");

const SHA40 = /^[a-f0-9]{40}$/;
const ROOT = path.resolve(__dirname, "../../..");

function usage() {
  return "usage: digitalocean-agent-parity-canary.js --release-sha SHA --output ABSOLUTE_PATH --spec ABSOLUTE_PATH --secret-path ABSOLUTE_PATH --name NAME";
}

function parseArgs(args) {
  const values = {};
  const allowed = new Set(["--release-sha", "--output", "--spec", "--secret-path", "--name"]);
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index];
    const value = args[index + 1];
    if (!allowed.has(key) || !value || value.startsWith("--")) throw new Error(usage());
    values[key.slice(2).replaceAll("-", "_")] = value;
  }
  if (!SHA40.test(String(values.release_sha || "")) || !values.output || !values.spec
      || !values.secret_path || !values.name) throw new Error(usage());
  for (const key of ["output", "spec", "secret_path"]) {
    if (!path.isAbsolute(values[key])) throw new Error("DigitalOcean parity paths must be absolute");
  }
  return values;
}

async function runCli(args, injected = {}) {
  const options = parseArgs(args);
  if (injected.localHead !== options.release_sha || injected.originMain !== options.release_sha) {
    throw new Error("DigitalOcean parity release is not main-derived");
  }
  if (!injected.client || typeof injected.runFixture !== "function" || typeof injected.runParity !== "function") {
    throw new Error("DigitalOcean parity runtime unavailable");
  }
  const expected = await injected.runFixture();
  const receipt = await injected.runParity({
    releaseSha: options.release_sha,
    expected,
    name: options.name,
    specPath: options.spec,
    secretPath: options.secret_path,
    repo: "Daisuke134/life-manager",
  }, { client: injected.client });
  writePrivate(options.output, receipt);
  return receipt;
}

function gitSha(ref) {
  return execFileSync("git", ["rev-parse", ref], { cwd: ROOT, encoding: "utf8" }).trim();
}

async function main(args = process.argv.slice(2)) {
  const client = createDigitalOceanRuntimeClient({
    binary: process.env.LM_DOCTL_PATH || "/Users/anicca/.local/bin/doctl",
    run: commandBoundary,
  });
  await runCli(args, {
    localHead: gitSha("HEAD"),
    originMain: gitSha("origin/main"),
    client,
    runFixture,
    runParity: runDigitalOceanAgentParity,
  });
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}

module.exports = { parseArgs, runCli };
