"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { runConnectorAgenticRegistration } = require("./connector-agentic-registration.js");

const formSchema = Object.freeze({
  kind: "luma_registration_form",
  fields: Object.freeze([Object.freeze({
    key: "registration_answers.0.value",
    label: "What brings you to this event?",
    control: "textarea",
    required: true,
    options: Object.freeze([]),
  })]),
});

test("uses one Terra turn for form decisions without exposing any browser route", async () => {
  let invocation;
  let calls = 0;
  const value = await runConnectorAgenticRegistration({
    canonicalUrl: "https://luma.com/event-a",
    schema: formSchema,
    profile: { full_name: "Private Person" },
    unresolved: [{ key: "registration_answers.0.value", label: "What brings you to this event?" }],
    evidenceDir: "/tmp/connector-evidence",
    repoRoot: "/tmp/repo",
    runnerPath: "/tmp/runner",
  }, {
    async runAgentRunner(input) {
      calls += 1;
      invocation = input;
      return {
        summary: { selected_model: "gpt-6-luna" },
        value: {
          status: "ready",
          answers: [{
            key: "registration_answers.0.value",
            value: "I build useful Life Manager and AI agent systems.",
          }],
        },
      };
    },
  });

  assert.equal(calls, 1);
  assert.deepEqual(value, {
    status: "ready",
    answers: [{
      key: "registration_answers.0.value",
      control: "textarea",
      value: "I build useful Life Manager and AI agent systems.",
    }],
  });
  assert.equal(invocation.taskClass, "connector-agent");
  assert.match(invocation.prompt, /What brings you to this event/);
  assert.doesNotMatch(invocation.prompt, /9222|9223|endpoint|page_websocket|target_id|owner_token/i);
  assert.doesNotMatch(invocation.prompt, /Playwright|connectOverCDP|browser\.close|context\.pages|require\(/i);
});

test("rejects incomplete, unknown, duplicate, or option-invalid Terra answers", async () => {
  const base = {
    canonicalUrl: "https://luma.com/event-a",
    schema: formSchema,
    profile: {},
    unresolved: [{ key: "registration_answers.0.value", label: "What brings you to this event?" }],
    evidenceDir: "/tmp/connector-evidence",
    repoRoot: "/tmp/repo",
    runnerPath: "/tmp/runner",
  };
  for (const answers of [
    [],
    [{ key: "other", value: "no" }],
    [{ key: "registration_answers.0.value", value: "one" }, { key: "registration_answers.0.value", value: "two" }],
  ]) {
    await assert.rejects(runConnectorAgenticRegistration(base, {
      runAgentRunner: async () => ({
        summary: { selected_model: "gpt-6-luna" },
        value: { status: "ready", answers },
      }),
    }), /unavailable/);
  }
});
