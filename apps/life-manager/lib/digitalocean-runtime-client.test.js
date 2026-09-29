"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const YAML = require("yaml");
const { createDigitalOceanRuntimeClient } = require("./digitalocean-runtime-client.js");

function fixture(overrides = {}) {
  const calls = [];
  const responses = [...(overrides.responses || [])];
  const client = createDigitalOceanRuntimeClient({
    binary: "/safe/doctl",
    async run(binary, args) {
      calls.push({ binary, args });
      return responses.shift() || { exitCode: 0, stdout: "{}" };
    },
  });
  return { calls, client };
}

test("checked-in canary policy contains no ask and denies bounded dangerous commands", () => {
  const file = path.join(__dirname, "../agentcore/digitalocean-canary.yaml");
  const text = fs.readFileSync(file, "utf8");
  const spec = YAML.parse(text);
  assert.equal(spec.agent, "codex");
  assert.equal(spec.keep_warm, undefined);
  assert.equal(spec.permissions.default, "allow");
  assert.equal(spec.permissions.rules.every((rule) => rule.action === "deny" && rule.enforcement === "strict"), true);
  assert.doesNotMatch(text, /\bask\b|action:\s*approve|resume.on.topoff/i);
  assert.deepEqual(spec.egress, ["api.openai.com"]);
});

test("checked-in infrastructure canary is a model-free sandbox with no outbound network", () => {
  const file = path.join(__dirname, "../agentcore/digitalocean-infrastructure-canary.yaml");
  const text = fs.readFileSync(file, "utf8");
  const spec = YAML.parse(text);
  assert.equal(spec.agent, "none");
  assert.deepEqual(spec.egress, []);
  assert.equal(spec.secrets, undefined);
  assert.doesNotMatch(text, /\bask\b|approve|resume.on.topoff|API_KEY/i);
});

test("canary is unattended reject-on-HITL, injects the model key by file reference, and returns only provider session identity", async () => {
  const f = fixture({ responses: [{ exitCode: 0, stdout: JSON.stringify({ id: "sess_canary1", status: "ready" }) }] });
  assert.deepEqual(await f.client.createCanary({
    name: "lm-canary-a", specPath: "/release/agents.yaml", prompt: "Run read-only proof",
    secretPath: "/private/openai.key",
  }), {
    session_id: "sess_canary1", raw: { id: "sess_canary1", status: "ready" },
  });
  assert.equal(f.calls[0].binary, "/safe/doctl");
  assert.deepEqual(f.calls[0].args, ["harness-runtime", "create", "--spec", "/release/agents.yaml", "--name", "lm-canary-a",
    "--prompt", "Run read-only proof", "--secret", "OPENAI_API_KEY=@/private/openai.key",
    "--on-hitl", "reject", "--interactive=false", "-o", "json"]);
  assert.doesNotMatch(JSON.stringify(f.calls), /approve|resume-on-topoff|sk-/i);
});

test("canary refuses to create without an absolute secret-file reference", async () => {
  for (const secretPath of [undefined, "relative.key", "/private/key\n--access-token=bad"]) {
    const f = fixture();
    await assert.rejects(f.client.createCanary({
      name: "lm-canary-a", specPath: "/release/agents.yaml", prompt: "Run read-only proof", secretPath,
    }), /input invalid/i);
    assert.equal(f.calls.length, 0);
  }
});

test("bare canary creates without a model credential and exec binds the exact session", async () => {
  const f = fixture({ responses: [
    { exitCode: 0, stdout: JSON.stringify({ id: "sess_bare1", status: "ready" }) },
    { exitCode: 0, stdout: JSON.stringify({ exit_code: 0, stdout: "LM_OK\n", stderr: "" }) },
  ] });
  assert.deepEqual(await f.client.createBareCanary({ name: "lm-bare-a", specPath: "/release/bare.yaml" }), {
    session_id: "sess_bare1", raw: { id: "sess_bare1", status: "ready" },
  });
  assert.deepEqual(await f.client.exec("sess_bare1", ["sh", "-lc", "printf LM_OK"]), {
    exit_code: 0, stdout: "LM_OK\n", stderr: "",
  });
  assert.deepEqual(f.calls[0].args, ["harness-runtime", "create", "--spec", "/release/bare.yaml",
    "--name", "lm-bare-a", "--interactive=false", "-o", "json"]);
  assert.deepEqual(f.calls[1].args, ["harness-runtime", "exec", "sess_bare1", "--timeout", "120",
    "-o", "json", "--", "sh", "-lc", "printf LM_OK"]);
});

test("bare exec rejects foreign identity, unsafe argv shape, and nonzero guest exit", async () => {
  const badArgv = fixture();
  await assert.rejects(badArgv.client.exec("sess_bare1", ["sh", "-lc", "x\0y"]), /input invalid/i);
  assert.equal(badArgv.calls.length, 0);
  const failed = fixture({ responses: [{ exitCode: 0, stdout: JSON.stringify({ exit_code: 7, stdout: "", stderr: "bad" }) }] });
  await assert.rejects(failed.client.exec("sess_bare1", ["false"]), /guest command failed/i);
});

test("show binds exact session and teardown requires list readback zero", async () => {
  const f = fixture({ responses: [
    { exitCode: 0, stdout: JSON.stringify({ session_id: "sess_canary1", status: "paused" }) },
    { exitCode: 0, stdout: "{}" },
    { exitCode: 0, stdout: "[]" },
  ] });
  assert.equal((await f.client.show("sess_canary1")).status, "paused");
  assert.deepEqual(await f.client.remove("sess_canary1"), { removed: true, session_id: "sess_canary1" });
  assert.deepEqual(f.calls.map(({ args }) => args.slice(0, 2)), [
    ["harness-runtime", "show"], ["harness-runtime", "remove"], ["harness-runtime", "list"],
  ]);
});

test("malformed provider output, foreign identity, failed command, and lingering teardown fail closed", async () => {
  const cases = [
    async () => fixture({ responses: [{ exitCode: 0, stdout: "not-json" }] }).client.balance(),
    async () => fixture({ responses: [{ exitCode: 0, stdout: JSON.stringify({ id: "sess_other" }) }] }).client.show("sess_expected"),
    async () => fixture({ responses: [{ exitCode: 1, stdout: "" }] }).client.logs("sess_expected"),
    async () => fixture({ responses: [{ exitCode: 0, stdout: "{}" }, { exitCode: 0, stdout: JSON.stringify([{ id: "sess_expected" }]) }] }).client.remove("sess_expected"),
  ];
  for (const run of cases) await assert.rejects(run, /DigitalOcean/i);
});
