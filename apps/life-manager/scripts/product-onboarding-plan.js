#!/usr/bin/env node
"use strict";

const { planProductOnboarding, readProductLoopCatalog } = require("../lib/product-onboarding.js");
const { hasTelegramCredentials } = require("../lib/telegram-credentials.js");

function parse(argv) {
  let host = "";
  let envFile = "";
  let all = false;
  const selected = [];
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (key === "--all") {
      if (all) throw new Error("--all may only be specified once");
      all = true;
      continue;
    }
    if (key === "--host" && value) host = value;
    else if (key === "--loop" && value) selected.push(value);
    else if (key === "--env-file" && value) envFile = value;
    else throw new Error("usage: product-onboarding-plan --host local|cloud (--all | --loop ID [--loop ID]) [--env-file FILE]");
    index += 1;
  }
  if (all && selected.length) throw new Error("--all cannot be combined with --loop");
  const verified = host === "local" && hasTelegramCredentials(envFile)
    ? ["telegram_credentials"] : [];
  return { host, selected_loop_ids: all ? readProductLoopCatalog().loops.map((loop) => loop.id) : selected,
    verified_requirements: verified };
}

function main() {
  process.stdout.write(`${JSON.stringify(planProductOnboarding(parse(process.argv.slice(2))), null, 2)}\n`);
}

if (require.main === module) {
  try { main(); } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { parse };
