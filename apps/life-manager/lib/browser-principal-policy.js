"use strict";

const crypto = require("node:crypto");

const HUMAN_GATE = /(?:captcha|oauth|2fa|two[- ]factor|3ds|kyc|human(?:[- ]only)? login|interview|signature|user[- ]provided|enter (?:a )?(?:code|password|credential)|identity verification)/i;
const ID = /^[a-z0-9][a-z0-9._:-]{0,199}$/i;

function evaluateBrowserPrincipal(input = {}) {
  const principal = String(input.principal_kind || "none");
  const humanInput = principal === "user_provided"
    || input.handoff_required === true
    || HUMAN_GATE.test(String(input.goal || input.reason || ""));
  if (humanInput) {
    return Object.freeze({
      allowed: false,
      status: "not_applicable",
      reason: "requires_human_principal",
      external_effect: "none",
    });
  }
  if (input.requires_login === true && principal !== "agent_owned") {
    return Object.freeze({
      allowed: false,
      status: "not_applicable",
      reason: "requires_human_principal",
      external_effect: "none",
    });
  }
  return Object.freeze({ allowed: true, principal_kind: principal });
}

function createBrowserObservationBroker(options = {}) {
  if (typeof options.secret !== "string" || options.secret.length < 32) {
    throw new Error("browser observation secret invalid");
  }
  for (const name of ["readActivity", "emergencyStop"]) {
    if (typeof options[name] !== "function") throw new Error(`browser observation ${name} unavailable`);
  }
  const refs = new Map();
  const digest = (token) => crypto.createHmac("sha256", options.secret).update(token).digest("hex");
  const resolve = (tenantId, viewerRef) => {
    const token = String(viewerRef || "").replace(/^lm-viewer:/, "");
    const record = refs.get(digest(token));
    if (!record || record.tenantId !== String(tenantId || "")) {
      throw new Error("browser observation tenant mismatch");
    }
    return record;
  };
  return Object.freeze({
    issue(input = {}) {
      const tenantId = String(input.tenantId || "");
      const sessionId = String(input.sessionId || "");
      const leaseGeneration = Number(input.leaseGeneration);
      if (!ID.test(tenantId) || !ID.test(sessionId)
          || !Number.isSafeInteger(leaseGeneration) || leaseGeneration < 1) {
        throw new Error("browser observation identity invalid");
      }
      const token = crypto.randomBytes(32).toString("base64url");
      refs.set(digest(token), Object.freeze({
        tenantId,
        sessionId,
        leaseGeneration,
      }));
      return Object.freeze({ viewer_ref: `lm-viewer:${token}`, mode: "read_only" });
    },
    async activity(input = {}) {
      return options.readActivity(resolve(input.tenantId, input.viewerRef));
    },
    async stop(input = {}) {
      const stopped = await options.emergencyStop(resolve(input.tenantId, input.viewerRef));
      if (stopped !== true) throw new Error("browser emergency stop failed");
      return Object.freeze({ status: "stopped", external_effect: "none" });
    },
    async breakGlass(input = {}) {
      if (options.allowBreakGlass !== true || typeof options.recordManualExternal !== "function") {
        throw new Error("browser break glass disabled");
      }
      const record = resolve(input.tenantId, input.viewerRef);
      const stopped = await options.emergencyStop(record);
      if (stopped !== true) throw new Error("browser emergency stop failed");
      await options.recordManualExternal(record);
      return Object.freeze({
        status: "manual_external",
        automated_success: false,
        revenue_eligible: false,
      });
    },
  });
}

module.exports = { evaluateBrowserPrincipal, createBrowserObservationBroker };
