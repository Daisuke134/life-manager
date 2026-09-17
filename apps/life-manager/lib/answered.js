"use strict";

function amdEnabled(env = process.env) {
  return String((env || {}).LM_AMD || "").trim().toLowerCase() === "on";
}

function shouldMarkAnswered({ amdEnabled: enabled, signal, result } = {}) {
  if (enabled === false) return signal === "media-start";
  return signal === "amd" && result === "human";
}

module.exports = { amdEnabled, shouldMarkAnswered };
