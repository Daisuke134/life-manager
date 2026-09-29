"use strict";

const crypto = require("node:crypto");

const RELEASE_SHA = /^[a-f0-9]{40}$/;
const TRANSIENT_BEFORE_ACCEPT = new Set([
  "ThrottlingException",
  "ServiceUnavailableException",
  "TooManyRequestsException",
]);

function required(value, label, max = 500) {
  const text = String(value == null ? "" : value).trim();
  if (!text || text.length > max) throw new Error(`AgentCore ${label} invalid`);
  return text;
}

function attempt(value) {
  if (!Number.isSafeInteger(value) || value < 1) throw new Error("AgentCore attempt invalid");
  return value;
}

function runtimeSessionId(input) {
  const tenantId = required(input && input.tenantId, "tenant");
  const jobId = required(input && input.jobId, "job");
  const invocationAttempt = attempt(input && input.attempt);
  const releaseSha = required(input && input.releaseSha, "release SHA", 40);
  if (!RELEASE_SHA.test(releaseSha)) throw new Error("AgentCore release SHA invalid");
  const digest = crypto.createHash("sha256")
    .update(`${tenantId}\n${jobId}\n${invocationAttempt}\n${releaseSha}`)
    .digest("hex");
  return `lm-${digest}`;
}

function timeoutMilliseconds(value) {
  const parsed = value == null ? 30_000 : Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 1_000 || parsed > 120_000) {
    throw new Error("AgentCore timeout invalid");
  }
  return parsed;
}

function errorDisposition(error) {
  if (error && error.accepted === false && TRANSIENT_BEFORE_ACCEPT.has(error.name)) {
    return Object.freeze({
      disposition: "retry",
      retryable: true,
      error_class: String(error.name),
    });
  }
  return Object.freeze({
    disposition: "reconcile",
    retryable: false,
    error_class: required(error && error.name || "AmbiguousInvokeError", "error class", 100),
  });
}

function createAgentCoreRuntimeClient(options = {}) {
  if (typeof options.invoke !== "function") throw new Error("AgentCore invoke boundary unavailable");
  const timeoutMs = timeoutMilliseconds(options.timeoutMs);
  return Object.freeze({
    async invoke(input) {
      const runtimeArn = required(input && input.runtimeArn, "runtime ARN", 1_000);
      if (!input.request || typeof input.request !== "object" || Array.isArray(input.request)) {
        throw new Error("AgentCore request invalid");
      }
      const sessionId = runtimeSessionId(input);
      const controller = new AbortController();
      let timer;
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          const error = new Error("AgentCore invocation timeout");
          error.name = "TimeoutError";
          reject(error);
        }, timeoutMs);
        if (typeof timer.unref === "function") timer.unref();
      });
      try {
        const response = await Promise.race([
          options.invoke({
            runtimeArn,
            runtimeSessionId: sessionId,
            payload: input.request,
            timeoutMs,
            signal: controller.signal,
          }),
          timeout,
        ]);
        if (!response || typeof response !== "object" || !response.response
            || typeof response.response !== "object" || Array.isArray(response.response)) {
          throw Object.assign(new Error("AgentCore response invalid"), { accepted: true });
        }
        return Object.freeze({
          disposition: "completed",
          result: response.response,
          provider_request_id: required(response.provider_request_id, "provider request id"),
        });
      } catch (error) {
        return errorDisposition(error);
      } finally {
        clearTimeout(timer);
      }
    },
  });
}

module.exports = { createAgentCoreRuntimeClient, runtimeSessionId };

