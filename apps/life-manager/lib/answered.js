"use strict";

function amdEnabled(env = process.env) {
  return String((env || {}).LM_AMD || "").trim().toLowerCase() !== "off";
}

function shouldMarkAnswered({ amdEnabled: enabled, signal, result } = {}) {
  if (enabled === false) return signal === "media-start";
  return signal === "amd" && (result === "human" || result === "not_sure");
}

module.exports = { amdEnabled, shouldMarkAnswered };
