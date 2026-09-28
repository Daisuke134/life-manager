"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { existsSync } = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const APP_ROOT = path.resolve(__dirname, "..");

test("packages the read-only canary with the official AgentCore packager and exits", () => {
  const run = spawnSync(
    process.execPath,
    [path.join(__dirname, "agentcore-cloud-canary-package.js")],
    {
      cwd: APP_ROOT,
      encoding: "utf8",
      timeout: 30_000,
    },
  );

  assert.equal(run.signal, null, run.stderr);
  assert.equal(run.status, 0, run.stderr);

  const result = JSON.parse(run.stdout.trim());
  assert.equal(result.agent_name, "cloud_canary");
  assert.match(result.artifact_path, /agentcore\/cloud_canary\.zip$/);
  assert.ok(result.size_bytes > 0);
  assert.match(result.sha256, /^[a-f0-9]{64}$/);
  assert.equal(existsSync(result.artifact_path), true);
});
