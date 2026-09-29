"use strict";

const crypto = require("node:crypto");
const { canonicalJson } = require("./cloud-edition-kernel.js");

const SHA40 = /^[a-f0-9]{40}$/;
const SHA256 = /^[a-f0-9]{64}$/;

function validateExpected(value) {
  if (!value || value.schema_version !== "life-manager.cloud-kernel-parity.v1"
      || !SHA256.test(String(value.business_kernel_sha || ""))
      || !SHA256.test(String(value.receipt_hash || ""))
      || !SHA256.test(String(value.evidence_hash || ""))
      || value.official_readback !== true || value.replay_zero !== true
      || value.effect !== "none" || value.human_input_count !== 0) {
    throw new Error("DigitalOcean expected parity invalid");
  }
  return value;
}

async function runDigitalOceanAgentParity(input = {}, injected = {}) {
  const client = injected && injected.client;
  if (!client || typeof client.balance !== "function" || typeof client.createAgentCanary !== "function"
      || typeof client.show !== "function" || typeof client.prompt !== "function"
      || typeof client.remove !== "function") {
    throw new Error("DigitalOcean agent parity dependencies unavailable");
  }
  const releaseSha = String(input.releaseSha || "");
  if (!SHA40.test(releaseSha)) throw new Error("DigitalOcean agent parity release invalid");
  const expected = validateExpected(input.expected);
  const prompt = [
    "Work only inside the already cloned Life Manager repository.",
    `Checkout the exact immutable commit ${releaseSha} in detached state.`,
    "Run exactly: node apps/life-manager/scripts/cloud-kernel-parity-fixture.js",
    "Do not modify files, contact external services, request approval, or perform any external effect.",
    "Return only the command's single-line JSON stdout, with no Markdown or explanation.",
  ].join(" ");

  const before = await client.balance();
  let sessionId = null;
  let promptReceipt = null;
  let proof = null;
  let primaryError = null;
  try {
    const created = await client.createAgentCanary({
      name: input.name, specPath: input.specPath, secretPath: input.secretPath, repo: input.repo,
    });
    sessionId = created.session_id;
    await client.show(sessionId);
    promptReceipt = await client.prompt(sessionId, prompt);
    try {
      proof = JSON.parse(promptReceipt.text);
    } catch {
      throw new Error("DigitalOcean agent parity JSON invalid");
    }
    if (canonicalJson(proof) !== canonicalJson(expected)) {
      throw new Error("DigitalOcean agent parity mismatch");
    }
  } catch (error) {
    primaryError = error;
  }

  let teardown = null;
  let after = null;
  let cleanupError = null;
  if (sessionId) {
    try { teardown = await client.remove(sessionId); } catch (error) { cleanupError = error; }
  }
  try { after = await client.balance(); } catch (error) { cleanupError ||= error; }
  if (primaryError) throw primaryError;
  if (cleanupError) throw cleanupError;

  const digest = crypto.createHash("sha256").update(canonicalJson({
    release_sha: releaseSha,
    session_id: sessionId,
    run_id: promptReceipt.run_id,
    proof,
    before_balance: before,
    after_balance: after,
    teardown,
  })).digest("hex");
  return Object.freeze({
    status: "verified",
    release_sha: releaseSha,
    provider_receipt_id: `digitalocean-agent-parity://sha256/${digest}`,
    receipt_hash: proof.receipt_hash,
    evidence_hash: proof.evidence_hash,
    business_kernel_sha: proof.business_kernel_sha,
    replay_zero: true,
    human_input_count: 0,
    effect: "none",
    before_balance: before,
    after_balance: after,
    teardown,
  });
}

module.exports = { runDigitalOceanAgentParity };
