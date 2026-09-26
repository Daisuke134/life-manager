"use strict";

// Regression fixture for the d0 self-heal repair-scope wiring (see
// apps/life-manager/lib/dev-merge-guard.js's repairScopeForOwner and
// apps/life-manager/scripts/life-manager-dev-d0.sh's REPAIR_SCOPE block).
//
// d0 is a linear bash script, not a Node module, so this file does NOT re-implement its logic (a
// second implementation would drift). Instead it extracts the ACTUAL `REPAIR_SCOPE_NODE` heredoc
// out of the committed script text and executes it against a temp fixture worktree that mirrors
// the shape d0 hands it: a copy of the real guard + recovery classifier, plus a throwaway
// config/loop-registry.json. This proves the exact code the script runs, without running gh,
// npm ci, or any other production command — every path here is a fresh os.tmpdir() fixture.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const SCRIPT_PATH = path.join(__dirname, "life-manager-dev-d0.sh");
const SCRIPT_TEXT = fs.readFileSync(SCRIPT_PATH, "utf8");
const GUARD_SRC = path.join(__dirname, "../lib/dev-merge-guard.js");
const RECOVERY_CLASS_SRC = path.join(__dirname, "../../../runtime/loop/recovery-class.cjs");

function extractHeredoc(scriptText, marker) {
  const re = new RegExp(`<<'${marker}'\\n([\\s\\S]*?)\\n${marker}\\n`);
  const match = scriptText.match(re);
  assert.ok(match, `expected a <<'${marker}' heredoc in ${SCRIPT_PATH}`);
  return match[1];
}

function tempWorktree(registry) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-d0-repair-scope-"));
  fs.mkdirSync(path.join(dir, "apps/life-manager/lib"), { recursive: true });
  fs.mkdirSync(path.join(dir, "runtime/loop"), { recursive: true });
  fs.mkdirSync(path.join(dir, "config"), { recursive: true });
  fs.copyFileSync(GUARD_SRC, path.join(dir, "apps/life-manager/lib/dev-merge-guard.js"));
  fs.copyFileSync(RECOVERY_CLASS_SRC, path.join(dir, "runtime/loop/recovery-class.cjs"));
  fs.writeFileSync(path.join(dir, "config/loop-registry.json"), JSON.stringify(registry));
  return dir;
}

function runRepairScopeNode(worktree, ownerId) {
  const nodeSource = extractHeredoc(SCRIPT_TEXT, "REPAIR_SCOPE_NODE");
  const scriptFile = path.join(worktree, "repair-scope.mjs.tmp.js");
  fs.writeFileSync(scriptFile, nodeSource);
  return execFileSync("node", [
    scriptFile,
    path.join(worktree, "apps/life-manager/lib/dev-merge-guard.js"),
    path.join(worktree, "config/loop-registry.json"),
    ownerId,
  ], { encoding: "utf8" });
}


test("d0's REPAIR_SCOPE_NODE heredoc derives the scope from the worktree's own registry", () => {
  const dir = tempWorktree({ loops: {
    "fake-owner": {
      label: "ai.anicca.fake-owner",
      effect_class: "none",
      provider_route: "deterministic",
      entrypoint: "skills/earn/fake-owner/scripts/browser-owner",
      cadence: { start_interval_seconds: 30 },
    },
    "effectful-owner": {
      label: "ai.anicca.effectful-owner",
      effect_class: "publish",
      provider_route: "deterministic",
      entrypoint: "skills/earn/effectful-owner/scripts/paid-owner",
      cadence: { start_interval_seconds: 30 },
    },
  } });
  try {
    assert.equal(runRepairScopeNode(dir, "fake-owner"), "skills/earn/fake-owner/");
    // An effect-bearing owner never gets a scope, even though it is otherwise well-formed.
    assert.equal(runRepairScopeNode(dir, "effectful-owner"), "");
    // Unknown owner id (e.g. a PR body that named something not actually in the registry).
    assert.equal(runRepairScopeNode(dir, "no-such-owner"), "");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});


test("d0 wires REPAIR_SCOPE into the agent prompt, the git add, and the candidate preflight", () => {
  assert.match(
    SCRIPT_TEXT,
    /SCOPE_SENTENCE="[^"]*\$\{REPAIR_SCOPE\}/,
    "the agent prompt must mention REPAIR_SCOPE when set",
  );
  assert.match(
    SCRIPT_TEXT,
    /PROMPT="[\s\S]*\$\{SCOPE_SENTENCE\}/,
    "SCOPE_SENTENCE must actually be interpolated into PROMPT",
  );
  assert.match(
    SCRIPT_TEXT,
    /ADD_PATHS\+=\("\$REPAIR_SCOPE"\)/,
    "git add must include REPAIR_SCOPE alongside apps/life-manager and runtime/loop",
  );
  assert.match(
    SCRIPT_TEXT,
    /git -C "\$WT" add "\$\{ADD_PATHS\[@\]\}"/,
    "the ADD_PATHS array (not a hardcoded path list) must be what gets added",
  );
  assert.match(
    SCRIPT_TEXT,
    /PREFLIGHT_JSON="\$\(node - "\$APP_DIR\/lib\/dev-merge-guard\.js" "\$APP_DIR\/lib\/self-build-daily\.js" "\$WT" "\$REPAIR_SCOPE"/,
    "the candidate preflight must be handed REPAIR_SCOPE as an argv token",
  );
  const preflightNode = extractHeredoc(SCRIPT_TEXT, "PREFLIGHT_NODE");
  assert.match(preflightNode, /repairScope,\s*\}\) \}\)\)/, "classifyChangedPath must receive repairScope");
  assert.match(preflightNode, /isRetainedRegressionFixture\(file, \{ repairScope \}\)/, "isRetainedRegressionFixture must receive repairScope");
});
