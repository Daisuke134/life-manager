"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const script = path.join(__dirname, "instagram-metrics-production-boot.sh");

test("Instagram metrics boot retains the immutable release binding after loading mutable env", (t) => {
  const directory = fs.mkdtempSync(path.join(__dirname, ".instagram-boot-release-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const calls = path.join(directory, "python-calls.txt");
  const python = path.join(directory, "python");
  const envFile = path.join(directory, "instagram.env");
  const boundReleaseSha = "a".repeat(40);
  const staleReleaseSha = "b".repeat(40);
  fs.writeFileSync(python, `#!/bin/sh\nprintf '%s|release=%s\\n' "$*" "\${LIFE_MANAGER_RELEASE_SHA-unset}" >> "${calls}"\n`, { mode: 0o700 });
  fs.writeFileSync(envFile, `LM_POSTIZ_API_KEY=test-token\nLIFE_MANAGER_RELEASE_SHA=${staleReleaseSha}\n`, { mode: 0o600 });

  const result = spawnSync(script, [], {
    env: {
      ...process.env,
      HOME: directory,
      LIFE_MANAGER_ENV_FILE: envFile,
      LIFE_MANAGER_PYTHON: python,
      PYTHON_BIN: python,
      NODE_BIN: python,
      LIFE_MANAGER_RELEASE_SHA: boundReleaseSha,
    },
    encoding: "utf8",
  });

  assert.equal(result.status, 0, result.stderr);
  assert.match(fs.readFileSync(calls, "utf8"), new RegExp(`release=${boundReleaseSha}`));
});
