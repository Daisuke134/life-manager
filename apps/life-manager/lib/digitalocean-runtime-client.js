"use strict";

const SESSION_ID = /^sess_[A-Za-z0-9_-]+$/;

function parseJson(output, label) {
  let parsed;
  try { parsed = JSON.parse(String(output || "")); } catch { throw new Error(`DigitalOcean ${label} JSON invalid`); }
  return parsed;
}

function sessionId(value) {
  const candidate = value && (value.session_id || value.id || value.SessionID);
  if (!SESSION_ID.test(String(candidate || ""))) throw new Error("DigitalOcean session id invalid");
  return String(candidate);
}

function createDigitalOceanRuntimeClient(options = {}) {
  if (typeof options.run !== "function") throw new Error("DigitalOcean command boundary unavailable");
  const binary = String(options.binary || "/Users/anicca/.local/bin/doctl");
  const invoke = async (args, label) => {
    const result = await options.run(binary, args);
    if (!result || result.exitCode !== 0) throw new Error(`DigitalOcean ${label} failed`);
    return result.stdout;
  };
  return Object.freeze({
    async balance() {
      const value = parseJson(await invoke(["harness-runtime", "balance", "-o", "json"], "balance"), "balance");
      if (!value || typeof value !== "object") throw new Error("DigitalOcean balance receipt invalid");
      return Object.freeze(value);
    },
    async createCanary(input = {}) {
      const name = String(input.name || "");
      const specPath = String(input.specPath || "");
      const prompt = String(input.prompt || "");
      if (!/^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?$/.test(name)) throw new Error("DigitalOcean canary name invalid");
      if (!specPath || !prompt || prompt.length > 2_000) throw new Error("DigitalOcean canary input invalid");
      const output = parseJson(await invoke([
        "harness-runtime", "create", "--spec", specPath, "--name", name,
        "--prompt", prompt, "--on-hitl", "reject", "--interactive=false", "-o", "json",
      ], "create"), "create");
      return Object.freeze({ session_id: sessionId(output), raw: output });
    },
    async show(id) {
      if (!SESSION_ID.test(String(id || ""))) throw new Error("DigitalOcean session id invalid");
      const output = parseJson(await invoke(["harness-runtime", "show", id, "-o", "json"], "show"), "show");
      if (sessionId(output) !== id) throw new Error("DigitalOcean session readback mismatch");
      return Object.freeze(output);
    },
    async logs(id) {
      if (!SESSION_ID.test(String(id || ""))) throw new Error("DigitalOcean session id invalid");
      return parseJson(await invoke(["harness-runtime", "logs", id, "-o", "json"], "logs"), "logs");
    },
    async remove(id) {
      if (!SESSION_ID.test(String(id || ""))) throw new Error("DigitalOcean session id invalid");
      await invoke(["harness-runtime", "remove", id, "-o", "json"], "remove");
      const listed = parseJson(await invoke(["harness-runtime", "list", "-o", "json"], "list"), "list");
      if (!Array.isArray(listed)) throw new Error("DigitalOcean session list invalid");
      if (listed.some((row) => {
        try { return sessionId(row) === id; } catch { return false; }
      })) throw new Error("DigitalOcean session teardown unverified");
      return Object.freeze({ removed: true, session_id: id });
    },
  });
}

module.exports = { createDigitalOceanRuntimeClient };
