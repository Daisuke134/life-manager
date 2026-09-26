#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createGhIssueClient } = require("../lib/feedback-to-issue.js");
const { processRecoveryOutcomeJournal } = require("../lib/recovery-self-build-bridge.js");

// Same relative layout as self-build-daily.js's readLoopRegistry(): repo root is three levels
// above this file whether it runs from the source checkout or a cut release.
const REPO_DIR = path.resolve(__dirname, "..", "..", "..");

function readLoopRegistry() {
  try {
    return JSON.parse(fs.readFileSync(path.join(REPO_DIR, "config", "loop-registry.json"), "utf8"));
  } catch {
    return null;
  }
}

async function main(env = process.env) {
  const home = env.HOME || os.homedir();
  const recoveryRoot = path.join(home, ".local", "state", "life-manager", "recovery");
  const journalPath = env.LIFE_MANAGER_RECOVERY_SUPERVISOR_JOURNAL_PATH
    || path.join(recoveryRoot, "supervisor.jsonl");
  const cursorPath = env.LM_RECOVERY_SELF_BUILD_CURSOR
    || path.join(recoveryRoot, "self-build-issued.jsonl");
  const result = await processRecoveryOutcomeJournal({
    journalPath,
    cursorPath,
    issueClient: createGhIssueClient(),
    registry: readLoopRegistry(),
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
  return 0;
}

if (require.main === module) {
  main().then((code) => { process.exitCode = code; }).catch((error) => {
    process.stderr.write(`recovery-self-build-bridge failed: ${error?.message || error}\n`);
    process.exitCode = 1;
  });
}

module.exports = { main };
