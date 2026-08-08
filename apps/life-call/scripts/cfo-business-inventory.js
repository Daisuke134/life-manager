"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { randomUUID: generateUUID } = require("node:crypto");

const { validateRegistry } = require("../lib/cfo-registry.js");
const {
  normalizeLaunchctlList,
  collectSourceObservations,
  collectLedgerObservations,
  buildInventory,
} = require("../lib/cfo-inventory.js");

const REGISTRY_PATH = path.join(__dirname, "../config/cfo-financial-units.json");
const REPO_ROOT = path.resolve(__dirname, "../../..");

function stateHome(env) {
  return env && env.LIFE_MANAGER_STATE_HOME
    ? env.LIFE_MANAGER_STATE_HOME
    : path.join(os.homedir(), ".local", "state", "life-manager");
}

function receiptPath(home, generatedAt, inventoryId) {
  const safeTime = generatedAt.replace(/[^a-zA-Z0-9._-]/g, "-");
  return path.join(home, "cfo", "business-inventory", `${safeTime}--${inventoryId}.json`);
}

function repoEvidenceExists(evidenceRef, existsSync = fs.existsSync) {
  const resolved = path.resolve(REPO_ROOT, evidenceRef);
  const relative = path.relative(REPO_ROOT, resolved);
  if (relative.startsWith(`..${path.sep}`) || relative === ".." || path.isAbsolute(relative)) return false;
  return existsSync(resolved);
}

function publishReceipt(finalPath, receipt, randomUUID) {
  const temporaryPath = `${finalPath}.${randomUUID()}.tmp`;
  let created = false;
  let fd;
  try {
    fs.mkdirSync(path.dirname(finalPath), { recursive: true, mode: 0o700 });
    fd = fs.openSync(temporaryPath, "wx", 0o600);
    created = true;
    try {
      fs.writeFileSync(fd, `${JSON.stringify(receipt)}\n`, "utf8");
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
      fd = undefined;
    }
    fs.linkSync(temporaryPath, finalPath);
    fs.unlinkSync(temporaryPath);
  } catch (error) {
    if (fd !== undefined) {
      try { fs.closeSync(fd); } catch (_) {}
    }
    if (created) {
      try { fs.unlinkSync(temporaryPath); } catch (_) {}
    }
    throw error;
  }
}

function summaryFor(inventory, receiptPathValue, resultOverride) {
  return {
    result: resultOverride || inventory.result,
    receipt_path: receiptPathValue || null,
    registry_sha256: inventory ? inventory.registry_sha256 : null,
    observation_hash: inventory ? inventory.observation_hash : null,
    unit_count: inventory ? inventory.financial_units.length : 0,
    unmapped_count: inventory ? inventory.unmapped_relevant_labels.length : 0,
    ambiguous_count: inventory ? inventory.ambiguous_labels.length : 0,
  };
}

function main({
  env = process.env,
  now = () => new Date(),
  randomUUID = generateUUID,
  launchctlList,
  ledgerProbe,
  existsSync = fs.existsSync,
  stdout = (line) => process.stdout.write(`${line}\n`),
} = {}) {
  let inventory;
  let finalPath;
  try {
    const registry = validateRegistry(JSON.parse(fs.readFileSync(REGISTRY_PATH, "utf8")));
    const generatedAt = new Date(now()).toISOString();
    const inventoryId = String(randomUUID());
    if (typeof launchctlList !== "function") throw new Error("launchctl_list_required");
    const runtimeObservations = normalizeLaunchctlList(launchctlList());
    const sourceObservations = collectSourceObservations(registry, (evidenceRef) => (
      repoEvidenceExists(evidenceRef, existsSync)
    ));
    const ledgerObservations = collectLedgerObservations(registry, ledgerProbe);
    inventory = buildInventory({
      registry,
      runtimeObservations,
      sourceObservations,
      ledgerObservations,
      generatedAt,
      inventoryId,
    });
    finalPath = receiptPath(stateHome(env), generatedAt, inventoryId);
    publishReceipt(finalPath, inventory, randomUUID);
    const summary = summaryFor(inventory, finalPath);
    stdout(JSON.stringify(summary));
    return { exitCode: inventory.result === "pass" ? 0 : 1, summary };
  } catch (_) {
    const summary = summaryFor(inventory, finalPath, "fail");
    stdout(JSON.stringify(summary));
    return { exitCode: 1, summary };
  }
}

if (require.main === module) {
  const result = main({
    env: process.env,
    now: () => new Date(),
    randomUUID: generateUUID,
    launchctlList: () => execFileSync("launchctl", ["list"], { encoding: "utf8", timeout: 10000 }),
    stdout: (line) => process.stdout.write(`${line}\n`),
  });
  process.exitCode = result.exitCode;
}

module.exports = { main, repoEvidenceExists };
