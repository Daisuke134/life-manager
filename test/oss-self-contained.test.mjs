import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const VERIFIER = join(REPO_ROOT, "scripts", "verify-oss-self-contained.mjs");
const REQUIRED_SOURCES = [
  "life-manager",
  "life-manager-v0",
  "anicca.ai",
  "anicca-products",
  "profitable-claude",
  "anicca-dais",
  "local-source-folders",
];

function git(root, ...args) {
  return execFileSync("git", args, {
    cwd: root,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function write(root, relativePath, content = "") {
  const path = join(root, relativePath);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content, "utf8");
}

function createFixture() {
  const root = mkdtempSync(join(tmpdir(), "life-manager-oss-contract-"));
  git(root, "init", "-q");
  git(root, "config", "user.email", "fixture@example.com");
  git(root, "config", "user.name", "Fixture");
  write(root, "runtime/agent-runner/agent_runner.py", "print('fixture')\n");
  write(root, "skills/.gitkeep", "");
  write(
    root,
    "docs/manifests/oss-merge-1-sources.json",
    `${JSON.stringify({
      version: 1,
      sources: REQUIRED_SOURCES.map((id) => ({
        id,
        repository: `https://example.com/${id}.git`,
        commit: "0".repeat(40),
        disposition: id === "life-manager" ? "canonical" : "inspected",
      })),
    }, null, 2)}\n`,
  );
  write(root, "apps/life-manager/index.js", "export const portable = true;\n");
  write(root, "runtime/README.md", "Runtime source only.\n");
  git(root, "add", ".");
  git(root, "commit", "-qm", "fixture");
  return root;
}

function verify(root) {
  const result = spawnSync(process.execPath, [VERIFIER, "--root", root, "--json"], {
    cwd: REPO_ROOT,
    encoding: "utf8",
  });
  let payload = { ok: false, violations: [] };
  try {
    payload = JSON.parse(result.stdout);
  } catch {
    // The assertion below reports stderr/stdout without hiding the real failure.
  }
  return { ...result, payload };
}

test("a clean committed fixture passes the OSS self-contained contract", () => {
  const root = createFixture();
  const result = verify(root);

  assert.equal(
    result.status,
    0,
    `verifier failed\nstdout=${result.stdout}\nstderr=${result.stderr}`,
  );
  assert.deepEqual(result.payload, { ok: true, violations: [] });
});

test("an exact legacy baseline passes until the violating file changes", () => {
  const root = createFixture();
  const path = "runtime/legacy.sh";
  write(root, path, 'ROOT="$HOME/anicca/legacy"\n');
  git(root, "add", path);
  const evidenceSha256 = createHash("sha256")
    .update(readFileSync(join(root, path)))
    .digest("hex");
  write(root, ".oss-self-contained-baseline.json", `${JSON.stringify({
    version: 1,
    entries: [{ code: "forbidden_source_root", path, evidence_sha256: evidenceSha256 }],
  }, null, 2)}\n`);
  git(root, "add", ".oss-self-contained-baseline.json");

  const accepted = verify(root);
  assert.equal(accepted.status, 0, accepted.stderr);
  assert.deepEqual(accepted.payload, { ok: true, violations: [] });

  write(root, path, 'ROOT="$HOME/anicca/changed"\n');
  git(root, "add", path);
  const drifted = verify(root);
  assert.equal(drifted.status, 1);
  assert.deepEqual(
    drifted.payload.violations.map(({ code, path: value }) => [code, value]),
    [["forbidden_source_root", path]],
  );
});

test("gitlinks and symlinks escaping the checkout fail with closed codes", () => {
  const root = createFixture();
  const head = git(root, "rev-parse", "HEAD");
  git(root, "update-index", "--add", "--cacheinfo", `160000,${head},vendor/gitlink`);
  symlinkSync("../../outside", join(root, "skills", "escape"));
  git(root, "add", "skills/escape");

  const result = verify(root);

  assert.equal(result.status, 1);
  assert.deepEqual(
    result.payload.violations.map(({ code, path }) => [code, path]),
    [
      ["symlink_escape", "skills/escape"],
      ["gitlink", "vendor/gitlink"],
    ],
  );
});

test("active local-source paths and generated runtime copies fail without echoing contents", () => {
  const root = createFixture();
  const privateLiteral = "/Users/example/private-source-with-token-shaped-value";
  write(root, "apps/life-manager/private.js", `export const source = "${privateLiteral}";\n`);
  write(
    root,
    "apps/life-manager/legacy.js",
    'export const source = "$HOME/anicca/skills/legacy-runner.js";\n',
  );
  write(
    root,
    "apps/life-manager/fixed.js",
    'export const source = "/opt/life-manager/skills/fixed-runner.js";\n',
  );
  write(
    root,
    "runtime/wrapped.sh",
    'REPO="${LIFE_MANAGER_REPO:-$HOME/anicca}"\n',
  );
  write(
    root,
    "runtime/fixed-env.sh",
    'REPO="${LIFE_MANAGER_REPO:-/opt/life-manager}"\n',
  );
  write(root, "apps/life-manager/state/session.json", '{"runtime":true}\n');
  git(root, "add", ".");

  const result = verify(root);

  assert.equal(result.status, 1);
  assert.deepEqual(
    result.payload.violations.map(({ code, path }) => [code, path]),
    [
      ["forbidden_source_root", "apps/life-manager/fixed.js"],
      ["forbidden_source_root", "apps/life-manager/legacy.js"],
      ["forbidden_source_root", "apps/life-manager/private.js"],
      ["runtime_copy", "apps/life-manager/state/session.json"],
      ["forbidden_source_root", "runtime/fixed-env.sh"],
      ["forbidden_source_root", "runtime/wrapped.sh"],
    ],
  );
  assert.equal(result.stdout.includes(privateLiteral), false);
  assert.equal(result.stderr.includes(privateLiteral), false);
});

test("personal mail and messaging destinations fail closed without echoing their values", () => {
  const root = createFixture();
  const privateMail = "owner.person+alerts" + "@gmail.com";
  const privateChat = ["12345", "6789"].join("");
  write(
    root,
    "runtime/personal-defaults.sh",
    `MAIL_TO="${privateMail}"\nopenclaw message send --target ${privateChat} --message ok\n`,
  );
  git(root, "add", ".");

  const result = verify(root);

  assert.equal(result.status, 1);
  assert.deepEqual(
    result.payload.violations.map(({ code, path }) => [code, path]),
    [["personal_runtime_default", "runtime/personal-defaults.sh"]],
  );
  assert.equal(result.stdout.includes(privateMail), false);
  assert.equal(result.stderr.includes(privateMail), false);
  assert.equal(result.stdout.includes(privateChat), false);
  assert.equal(result.stderr.includes(privateChat), false);
});

test("explicit verifier fixtures do not count as runtime dependencies", () => {
  const root = createFixture();
  write(
    root,
    "apps/life-manager/lib/runtime-paths.test.js",
    [
      'const forbidden = "/Users/operator/.openclaw/state";',
      'const personal = "openclaw message send --target 123456789";',
      "",
    ].join("\n"),
  );
  git(root, "add", ".");

  const result = verify(root);

  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.payload, { ok: true, violations: [] });
});

test("unlisted test files and constructed home paths cannot hide active legacy dependencies", () => {
  const root = createFixture();
  write(
    root,
    "skills/example/runtime-dependency.test.py",
    'from pathlib import Path\nROOT = Path.home() / ".openclaw" / "skills"\n',
  );
  write(
    root,
    "skills/example/runtime.py",
    'from pathlib import Path\nROOT = Path.home() / ".openclaw" / "state"\n',
  );
  git(root, "add", ".");

  const result = verify(root);

  assert.equal(result.status, 1);
  assert.deepEqual(
    result.payload.violations.map(({ code, path }) => [code, path]),
    [
      ["forbidden_source_root", "skills/example/runtime-dependency.test.py"],
      ["forbidden_source_root", "skills/example/runtime.py"],
    ],
  );
});

test("a second agent runner fails the single canonical engine contract", () => {
  const root = createFixture();
  write(root, "skills/agent-runner/agent_runner.py", "print('duplicate')\n");
  git(root, "add", ".");

  const result = verify(root);

  assert.equal(result.status, 1);
  assert.deepEqual(
    result.payload.violations.map(({ code, path }) => [code, path]),
    [["duplicate_runner", "skills/agent-runner/agent_runner.py"]],
  );
});

test("source provenance is closed over every inspected repository and local source inventory", () => {
  const root = createFixture();
  write(
    root,
    "docs/manifests/oss-merge-1-sources.json",
    `${JSON.stringify({
      version: 1,
      sources: [{ id: "life-manager", repository: "https://example.com/life-manager.git",
        commit: "0".repeat(40), disposition: "canonical" }],
    })}\n`,
  );
  git(root, "add", ".");

  const result = verify(root);

  assert.equal(result.status, 1);
  assert.deepEqual(
    result.payload.violations.map(({ code, path }) => [code, path]),
    [
      ["manifest_source_missing", "anicca-dais"],
      ["manifest_source_missing", "anicca-products"],
      ["manifest_source_missing", "anicca.ai"],
      ["manifest_source_missing", "life-manager-v0"],
      ["manifest_source_missing", "local-source-folders"],
      ["manifest_source_missing", "profitable-claude"],
    ],
  );
});

test("absorbed source mappings fail closed when the canonical target hash drifts", () => {
  const root = createFixture();
  const manifestPath = "docs/manifests/oss-merge-1-sources.json";
  const manifest = JSON.parse(execFileSync("git", ["show", `:${manifestPath}`], {
    cwd: root, encoding: "utf8",
  }));
  const source = manifest.sources.find(({ id }) => id === "anicca-products");
  source.disposition = "absorbed";
  source.absorbed_files = [{
    source: "upstream/portable.js",
    target: "apps/life-manager/index.js",
    sha256: "0".repeat(64),
  }];
  write(root, manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  git(root, "add", manifestPath);

  const result = verify(root);

  assert.equal(result.status, 1);
  assert.deepEqual(
    result.payload.violations.map(({ code, path }) => [code, path]),
    [["manifest_hash_mismatch", "apps/life-manager/index.js"]],
  );
});

test("fresh-clone verification defaults to canonical main, never a feature branch", () => {
  const source = readFileSync(join(REPO_ROOT, "scripts", "verify-fresh-clone.sh"), "utf8");
  assert.match(source, /LIFE_MANAGER_VERIFY_REF:-main/u);
  assert.doesNotMatch(source, /LIFE_MANAGER_VERIFY_REF:-feature\//u);
});

test("declared third-party runtime adapters may document their own runtime home", () => {
  const root = createFixture();
  write(
    root,
    "skills/capafy-autopublish/vendor/runtime-adapter.py",
    'OPENCLAW_HOME = "~/.openclaw"\n',
  );
  git(root, "add", ".");

  const result = verify(root);

  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.payload, { ok: true, violations: [] });
});
