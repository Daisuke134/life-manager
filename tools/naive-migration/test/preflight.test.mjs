import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { preflightConfig } from "../src/preflight.mjs";

const fixtureDir = fileURLToPath(new URL("../fixture/", import.meta.url));

test("preflight loads the fixture and does not declare a blueprint", async () => {
  const result = await preflightConfig(fixtureDir);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.config.name, "naive-migration-fixture");
  assert.equal(result.config.blueprint, undefined);
  assert.equal(result.config.template, undefined);
  assert.deepEqual([...result.config.agents], []);
  assert.deepEqual([...result.config.apps], []);
});

test("preflight rejects a config that names a template without a blueprint", async () => {
  const dir = await mkdtemp(join(tmpdir(), "naive-preflight-"));
  try {
    await writeFile(join(dir, "naive.config.json"), JSON.stringify({ name: "invalid-fixture", template: "blank" }));
    const result = await preflightConfig(dir);
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.reason, "invalid");
    assert.match(result.message, /blueprint/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("this package does not depend on the old vetta SDK", async () => {
  const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  const names = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies, ...pkg.optionalDependencies });
  assert.equal(names.includes("@usenaive-sdk/vetta"), false);
  assert.equal(names.includes("@usenaive-sdk/vetta-cli"), false);
  assert.equal(pkg.dependencies["@usenaive-sdk/managed-agents"], "0.12.0");
  assert.equal(pkg.dependencies["@usenaive-sdk/blueprints"], "0.18.0");
  assert.equal(pkg.dependencies["@usenaive-sdk/cli"], "1.0.0");
});
