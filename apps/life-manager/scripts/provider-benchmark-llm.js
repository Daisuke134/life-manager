"use strict";

const { createHash } = require("node:crypto");

function ratio(numerator, denominator) {
  return denominator ? Number((numerator / denominator).toFixed(6)) : null;
}

function resultCorrect(item, result) {
  const expected = item.expected || {};
  if (!result || result.kind !== expected.kind) return false;
  if (expected.kind === "filled") return String(result.location || "") === String(expected.location || "");
  return true;
}

function scoreCandidate(candidate, rows) {
  const total = rows.length;
  const onlineRows = rows.filter((row) => row.expectedKind === "online");
  const askRows = rows.filter((row) => row.resultKind === "ask");
  const expectedAskRows = rows.filter((row) => row.expectedKind === "ask");
  const locationRows = rows.filter((row) => row.expectedKind === "filled");
  const correctLocations = locationRows.filter((row) => row.correct).length;
  const onlineCorrect = onlineRows.filter((row) => row.resultKind === "online").length;
  const asksCorrect = askRows.filter((row) => row.expectedKind === "ask").length;
  const correct = rows.filter((row) => row.correct).length;
  const receiptCount = rows.filter((row) => row.receiptComplete === true && String(row.receiptRef || "").trim()).length;
  const costsComplete = rows.length > 0 && rows.every((row) => (
    row.estimatedCostUsd != null
    && Number.isFinite(Number(row.estimatedCostUsd)) && Number(row.estimatedCostUsd) >= 0
  ));
  const estimatedCostUsd = costsComplete
    ? rows.reduce((sum, row) => sum + Number(row.estimatedCostUsd), 0)
    : null;
  const latencyMs = rows.reduce((sum, row) => sum + (Number(row.latencyMs) || 0), 0);
  const privacy = [...new Set(rows.map((row) => String(row.privacyStatus || "unknown")))].sort();
  return {
    candidate: String(candidate.name),
    accuracy: ratio(correct, total),
    onlineAccuracy: ratio(onlineCorrect, onlineRows.length),
    askPrecision: ratio(asksCorrect, askRows.length),
    askRecall: ratio(asksCorrect, expectedAskRows.length),
    locationAccuracy: ratio(correctLocations, locationRows.length),
    latencyMs: total ? Math.round(latencyMs / total) : null,
    estimatedCostUsd: estimatedCostUsd == null ? null : Number(estimatedCostUsd.toFixed(12)),
    costCompleteness: costsComplete ? 1 : 0,
    privacyStatus: privacy,
    receiptCompleteness: ratio(receiptCount, total),
    totalCases: total,
    eligible: false,
  };
}

function digestScores(scores, observedAt, releaseSha) {
  const canonical = scores.map((score) => ({ ...score, privacyStatus: [...score.privacyStatus] }));
  return createHash("sha256").update(JSON.stringify({ observedAt, releaseSha, scores: canonical })).digest("hex");
}

async function runLlmProviderBenchmark({
  cases = [], candidates = [], runner, now = () => new Date().toISOString(),
  releaseSha = process.env.LIFE_MANAGER_RELEASE_SHA || "unreleased",
} = {}) {
  if (typeof runner !== "function") throw new Error("runner is required");
  const observedAt = String(now());
  const allRows = [];
  for (const candidate of Array.isArray(candidates) ? candidates : []) {
    for (const item of Array.isArray(cases) ? cases : []) {
      const started = Date.now();
      let result;
      try { result = await runner(candidate, item); }
      catch (error) {
        result = { kind: "error", errorClass: String(error && error.name || "runner_error"), receiptComplete: false };
      }
      const value = result && typeof result === "object" ? result : {};
      allRows.push({
        candidate: String(candidate.name), caseId: String(item.caseId), expectedKind: String(item.expected?.kind || "unknown"),
        resultKind: String(value.kind || "error"), correct: resultCorrect(item, value),
        location: value.location == null ? null : String(value.location), latencyMs: Number.isFinite(Number(value.latencyMs)) ? Number(value.latencyMs) : Date.now() - started,
        estimatedCostUsd: Number.isFinite(Number(value.estimatedCostUsd)) && Number(value.estimatedCostUsd) >= 0
          ? Number(value.estimatedCostUsd) : null,
        privacyStatus: String(value.privacyStatus || "unknown"), receiptComplete: value.receiptComplete === true,
        receiptRef: value.receiptRef == null ? null : String(value.receiptRef),
      });
    }
  }
  const scores = (Array.isArray(candidates) ? candidates : []).map((candidate) => scoreCandidate(
    candidate, allRows.filter((row) => row.candidate === String(candidate.name)),
  ));
  const baseline = scores.find((score) => score.candidate === "gemini-current") || scores[0] || null;
  for (const score of scores) {
    if (!baseline || score.candidate === baseline.candidate) continue;
    score.eligible = score.receiptCompleteness === 1
      && baseline.receiptCompleteness === 1
      && score.costCompleteness === 1
      && baseline.costCompleteness === 1
      && (score.accuracy ?? 0) >= (baseline.accuracy ?? 0)
      && (score.onlineAccuracy ?? 0) >= (baseline.onlineAccuracy ?? 0)
      && (score.locationAccuracy ?? 0) >= (baseline.locationAccuracy ?? 0)
      && (score.askPrecision ?? 0) >= (baseline.askPrecision ?? 0)
      && (score.askRecall ?? 0) >= (baseline.askRecall ?? 0)
      && (score.latencyMs ?? Infinity) <= (baseline.latencyMs ?? Infinity)
      && score.estimatedCostUsd != null
      && baseline.estimatedCostUsd != null
      && score.estimatedCostUsd <= baseline.estimatedCostUsd
      && score.privacyStatus.every((value) => ["local", "approved_cloud"].includes(value));
  }
  const recommendation = !baseline ? "no_baseline" : scores.some((score) => score.eligible)
    ? "eligible_for_shadow" : "keep_current";
  return {
    schemaVersion: 1,
    observedAt,
    releaseSha,
    digest: digestScores(scores, observedAt, releaseSha),
    scores,
    recommendation,
  };
}

module.exports = { runLlmProviderBenchmark, resultCorrect, scoreCandidate };
