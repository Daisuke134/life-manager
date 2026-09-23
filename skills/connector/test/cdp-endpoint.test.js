"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const REPO_ROOT = path.resolve(__dirname, "../../..");
const RESOLVER = path.join(REPO_ROOT, "skills", "connector", "lib", "resolve-cdp-endpoint.sh");

function runResolver(endpoint) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "connector-cdp-endpoint-"));
  const ownerBin = path.join(directory, "browser-port-owner.py");
  const python = path.join(directory, "python-fixture");
  fs.writeFileSync(ownerBin, "# fixture\n", { mode: 0o600 });
  fs.writeFileSync(python, `#!/bin/sh\nprintf '%s\\n' '${JSON.stringify({ endpoint, ok: true, owner: "life-manager-daily-driver", port: 9222 })}'\n`, { mode: 0o700 });
  try {
    return spawnSync("bash", [RESOLVER], {
      encoding: "utf8",
      env: {
        ...process.env,
        BROWSER_PORT_OWNER_BIN: ownerBin,
        BROWSER_PORT_OWNER_PYTHON: python,
      },
    });
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

test("shared Connector resolver preserves the registered IPv6 daily-driver endpoint", () => {
  const result = runResolver("http://[::1]:9222");
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, "http://[::1]:9222\n");
});

test("shared Connector resolver fails closed outside concrete loopback port 9222", () => {
  for (const endpoint of ["http://localhost:9222", "http://127.0.0.1:9228", "https://127.0.0.1:9222"]) {
    const result = runResolver(endpoint);
    assert.notEqual(result.status, 0, endpoint);
    assert.equal(result.stdout, "", endpoint);
  }
});

test("run, healthcheck, and install share the registered endpoint resolver", () => {
  for (const relative of ["run.sh", "healthcheck.sh", "install.sh"]) {
    const source = fs.readFileSync(path.join(REPO_ROOT, "skills", "connector", relative), "utf8");
    assert.match(source, /resolve-cdp-endpoint\.sh/, relative);
    assert.doesNotMatch(source, /http:\/\/127\.0\.0\.1:9222\/json\/version/, relative);
  }
});
