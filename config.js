"use strict";
// Self-contained config for Life Manager. ONE place resolves env, data dir, profile, bins.
// No dependency on any external host runtime — runs anywhere (local OR cloud).
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

function loadEnv() {
  const out = {};
  const file = process.env.LIFE_ENV_FILE || path.join(__dirname, ".env");
  let raw = "";
  try { raw = fs.readFileSync(file, "utf8"); } catch { return out; }
  for (const line of raw.split("\n")) {
    const m = line.match(/^(?:export\s+)?([A-Z_][A-Z0-9_]*)=(.*)$/);
    if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return out;
}
const ENV = loadEnv();
function env(k, d = "") { return process.env[k] || ENV[k] || d; }

// Resolved at CALL time so tests can isolate via LIFE_DATA_DIR / HOME without a re-require.
function dataDir() {
  return process.env.LIFE_DATA_DIR || path.join(process.env.HOME || os.homedir(), ".life-manager");
}
const DATA_DIR = dataDir();
function dataPath(...p) {
  const f = path.join(dataDir(), ...p);
  fs.mkdirSync(path.dirname(f), { recursive: true });
  return f;
}
const profile = {
  account: () => env("GOG_ACCOUNT") || env("LIFE_GOOGLE_ACCOUNT"),
  ownerEmail: () => env("LIFE_OWNER_EMAIL") || env("GOG_ACCOUNT") || env("LIFE_GOOGLE_ACCOUNT"),
  homeAddress: () => env("LIFE_HOME_ADDRESS"),
  phone: () => env("LIFE_PHONE"),
  calId: () => env("LIFE_CAL_ID") || env("GCAL_ID", "primary"),
};
const bins = {
  gog: () => env("GOG_BIN", "gog"),
  scheduler: () => env("LIFE_SCHEDULER_BIN", "openclaw"),
  cloudflared: () => env("CLOUDFLARED_BIN", "cloudflared"),
};
module.exports = { ENV, env, DATA_DIR, dataPath, profile, bins };
