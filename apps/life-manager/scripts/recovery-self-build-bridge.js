#!/usr/bin/env node
"use strict";

const os = require("node:os");
const path = require("node:path");
const { createGhIssueClient } = require("../lib/feedback-to-issue.js");
const { processRecoveryOutcomeJournal } = require("../lib/recovery-self-build-bridge.js");

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
