"use strict";

const path = require("node:path");
const { runLocalAgentRunner } = require("./connector-luna-judgment.js");

const SECRET_KEY = /(?:api[_-]?key|access[_-]?token|password|secret|cookie|session)/i;
const SECRET_VALUE = /(?:api[_ -]?key|access[_ -]?token|\btoken|password|secret|cookie|session)\s*[:=]/i;

function unavailable() { throw new Error("Connector agentic registration unavailable"); }

function safeProfile(value, depth = 0) {
  if (depth > 4 || value == null || typeof value === "boolean" || typeof value === "number") return value;
  if (typeof value === "string") {
    const text = value.trim();
    if (text.length > 2_000 || SECRET_VALUE.test(text)) unavailable();
    return text;
  }
  if (Array.isArray(value)) return value.slice(0, 20).map((item) => safeProfile(item, depth + 1));
  if (typeof value !== "object") unavailable();
  return Object.fromEntries(Object.entries(value).filter(([key]) => !SECRET_KEY.test(key))
    .map(([key, item]) => [key, safeProfile(item, depth + 1)]));
}

function verifiedInput(input) {
  const canonicalUrl = String(input.canonicalUrl || "").trim();
  if (!/^https:\/\/luma\.com\/[A-Za-z0-9_-]+(?:[/?#].*)?$/.test(canonicalUrl)) unavailable();
  const schema = input.schema;
  if (!schema || schema.kind !== "luma_registration_form" || !Array.isArray(schema.fields)) unavailable();
  const fields = new Map(schema.fields.map((field) => [field.key, field]));
  const unresolved = input.unresolved;
  if (!Array.isArray(unresolved) || unresolved.length < 1 || unresolved.length > 50) unavailable();
  const keys = new Set();
  for (const item of unresolved) {
    const field = item && fields.get(item.key);
    if (!field || field.required !== true || field.label !== item.label || keys.has(item.key)) unavailable();
    if (["checkbox"].includes(field.control)) unavailable();
    keys.add(item.key);
  }
  return { canonicalUrl, schema, unresolved, fields, profile: safeProfile(input.profile || {}) };
}

function verifiedAnswer(field, raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw) || raw.key !== field.key) unavailable();
  if (field.control === "multi_select") {
    if (!Array.isArray(raw.value) || raw.value.length < 1 || raw.value.length > 3) unavailable();
    const values = raw.value.map((value) => String(value).trim());
    if (new Set(values).size !== values.length || values.some((value) => !field.options.includes(value))) unavailable();
    return { key: field.key, control: field.control, value: values };
  }
  const value = String(raw.value == null ? "" : raw.value).trim();
  if (!value || value.length > 2_000 || SECRET_VALUE.test(value)) unavailable();
  if (["select", "radio"].includes(field.control) && !field.options.includes(value)) unavailable();
  if (!["phone", "text", "email", "url", "textarea", "select", "radio"].includes(field.control)) unavailable();
  return { key: field.key, control: field.control, value };
}

async function runConnectorAgenticRegistration(input = {}, deps = {}) {
  const verified = verifiedInput(input);
  const result = await (deps.runAgentRunner || runLocalAgentRunner)({
    prompt: [
      "You are the Connector loop's bounded Luma form-answer planner. Return answers only; do not operate a browser, run commands, edit code, or ask the human.",
      "Answer every listed required ordinary question truthfully from the supplied private profile and purpose. Never invent contact details, identities, social handles, credentials, or consent.",
      "For ordinary purpose questions: the user builds Life Manager and AI agents, wants to meet founders, engineers, and users, learn, and make useful connections.",
      `Observed form schema: ${JSON.stringify(verified.schema)}`,
      `Required unresolved questions: ${JSON.stringify(verified.unresolved)}`,
      `Private profile for answer judgment only: ${JSON.stringify(verified.profile)}`,
    ].join("\n"),
    schema: {
      type: "object", additionalProperties: false,
      required: ["status", "answers"],
      properties: {
        status: { type: "string", const: "ready" },
        answers: {
          type: "array", minItems: verified.unresolved.length, maxItems: verified.unresolved.length,
          items: {
            type: "object", additionalProperties: false, required: ["key", "value"],
            properties: {
              key: { type: "string" },
              value: { anyOf: [
                { type: "string", minLength: 1, maxLength: 2_000 },
                { type: "array", minItems: 1, maxItems: 3, items: { type: "string", minLength: 1, maxLength: 200 } },
              ] },
            },
          },
        },
      },
    },
    taskClass: "connector-agent",
    taskLabel: "connector-event-registration",
    timeoutMs: 90_000,
    evidenceDir: path.join(String(input.evidenceDir), "agentic-registration"),
    repoRoot: input.repoRoot,
    runnerPath: input.runnerPath,
  });
  if (!result || !result.summary || result.summary.selected_model !== "gpt-6-luna"
    || !result.value || result.value.status !== "ready" || !Array.isArray(result.value.answers)) unavailable();
  const seen = new Set();
  const answers = result.value.answers.map((answer) => {
    if (!answer || seen.has(answer.key) || !verified.fields.has(answer.key) || !verified.unresolved.some((item) => item.key === answer.key)) unavailable();
    seen.add(answer.key);
    return verifiedAnswer(verified.fields.get(answer.key), answer);
  });
  if (seen.size !== verified.unresolved.length) unavailable();
  return Object.freeze({ status: "ready", answers: Object.freeze(answers) });
}

module.exports = { runConnectorAgenticRegistration };
