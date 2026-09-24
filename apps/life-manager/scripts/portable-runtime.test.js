const assert = require("node:assert/strict");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const scripts = __dirname;
const launchers = [
  "financial-report-boot.sh",
  "instagram-metrics-production-boot.sh",
  "tiktok-metrics-production-boot.sh",
  "taskmarket-work-ledger-boot.sh",
  "ugig-invoice-observer-boot.sh",
  "x402-sale-ledger-boot.sh",
];

test("production launchers share portable node and timeout resolution", () => {
  const helper = fs.readFileSync(path.join(scripts, "lib/portable-runtime.sh"), "utf8");
  assert.match(helper, /command -v node/);
  assert.match(helper, /command -v python3/);
  assert.match(helper, /runtime\/run-with-timeout\.py/);
  assert.doesNotMatch(helper, /\/opt\/homebrew\/bin/);
  for (const launcher of launchers) {
    const source = fs.readFileSync(path.join(scripts, launcher), "utf8");
    assert.match(source, /portable-runtime\.sh/, launcher);
    assert.doesNotMatch(source, /\/opt\/homebrew\/bin\/(?:node|timeout)/, launcher);
  }
});

test("portable runtime prefers the launchd-managed node when PATH has no node", () => {
  const helperPath = path.join(scripts, "lib/portable-runtime.sh");
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "lm-portable-runtime-"));
  const fakeNode = path.join(temporary, "managed-node");
  const fakePython = path.join(temporary, "managed-python");
  const repo = path.join(temporary, "repo");
  fs.mkdirSync(path.join(repo, "runtime"), { recursive: true });
  fs.writeFileSync(path.join(repo, "runtime", "run-with-timeout.py"), "");
  for (const executable of [fakeNode, fakePython]) {
    fs.writeFileSync(executable, "#!/bin/sh\nexit 0\n");
    fs.chmodSync(executable, 0o700);
  }
  const result = childProcess.spawnSync(
    "/bin/bash",
    ["-c", `. "${helperPath}"; lm_prepare_portable_runtime "${repo}"; printf '%s\\n' "$LM_NODE"`],
    {
      env: {
        PATH: path.join(temporary, "empty-bin"),
        NODE_BIN: "",
        PYTHON_BIN: fakePython,
        LIFE_MANAGER_RUNTIME_NODE: fakeNode,
      },
      encoding: "utf8",
    },
  );
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), fakeNode);
});
