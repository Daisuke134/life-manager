import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../../..");
const runnerPath = path.join(repoRoot, "bin", "citizen-refill-launchd");
test("the scheduled refill runner loads the managed environment and executes the real live rail", () => {
  const runner = fs.readFileSync(runnerPath, "utf8");
  assert.match(runner, /LIFE_MANAGER_ENV_FILE=.*\.env/);
  assert.match(runner, /LIFE_MANAGER_WALLET_HOME/);
  assert.match(runner, /agent-economy\/instance/);
  assert.match(runner, /exec "\$NODE_BIN" "\$REPO_ROOT\/bin\/citizen-refill" --live/);
  assert.doesNotMatch(runner, /openclaw|hermes|\/opt\/homebrew/);
  assert.doesNotMatch(runner, /--dry/);
});

test("citizen refill resolves and imports its capped sub-wallet dependency without effects", async () => {
  const packageJson = JSON.parse(fs.readFileSync(path.join(repoRoot, "package.json"), "utf8"));
  const packageLock = JSON.parse(fs.readFileSync(path.join(repoRoot, "package-lock.json"), "utf8"));

  assert.equal(packageJson.dependencies.tweetnacl, "1.0.3");
  assert.equal(packageLock.packages[""].dependencies.tweetnacl, "1.0.3");
  assert.equal(packageLock.packages["node_modules/tweetnacl"].version, "1.0.3");
  assert.doesNotThrow(() => createRequire(import.meta.url).resolve("tweetnacl"));

  const refill = await import("../refill.mjs");
  assert.equal(typeof refill.planRefill, "function");
  assert.equal(
    refill.planRefill({
      subNosBalance: 0.75,
      subSolBalance: 0.005,
      ownerNosBalance: 0,
      ownerSolBalance: 0,
      baseUsdc: 1,
    }).act,
    false,
  );
});
