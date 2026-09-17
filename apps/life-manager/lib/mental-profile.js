"use strict";

const KINDS = Object.freeze(["theme", "tone", "goal", "avoid"]);
const BASE_TAGS = new Set([
  "self-worth", "self-compassion", "confidence", "mindfulness", "rest", "courage", "growth",
  "action", "body-awareness", "breath", "future-direction", "peace", "boundaries",
]);
const TONES = new Set(["gentle", "direct", "spiritual-neutral"]);
const BASES = new Set(["explicit_user_statement", "explicit_goal", "explicit_correction"]);
const HASH = /^[a-f0-9]{64}$/i;

function fail(message) { throw new Error(`profile tag ${message}`); }

function validateProfileTag(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) fail("must be an object");
  const allowed = ["uid", "kind", "tag", "weight", "basis", "explicit", "sourceRefHash", "observedAt", "expiresAt", "supersededBy"];
  if (Object.keys(input).some((key) => !allowed.includes(key))) fail("contains unknown fields");
  const uid = String(input.uid || "").trim();
  const kind = String(input.kind || "");
  const tag = String(input.tag || "").trim();
  const weight = Number(input.weight);
  if (!uid || !KINDS.includes(kind) || !Number.isFinite(weight) || weight <= 0 || weight > 10) fail("identity invalid");
  if (!BASES.has(input.basis) || input.explicit !== true) fail("must cite an explicit basis");
  if (!HASH.test(String(input.sourceRefHash || ""))) fail("source reference invalid");
  if (!Number.isFinite(Date.parse(input.observedAt))) fail("observedAt invalid");
  if (input.expiresAt !== null && input.expiresAt !== undefined && !Number.isFinite(Date.parse(input.expiresAt))) fail("expiresAt invalid");
  if (input.supersededBy !== null && input.supersededBy !== undefined && typeof input.supersededBy !== "string") fail("supersededBy invalid");
  if (kind === "tone" ? !TONES.has(tag) : !BASE_TAGS.has(tag)) fail("tag is not allowlisted");
  return Object.freeze({
    uid, kind, tag, weight, basis: input.basis, explicit: true, sourceRefHash: String(input.sourceRefHash).toLowerCase(),
    observedAt: new Date(input.observedAt).toISOString(),
    expiresAt: input.expiresAt ? new Date(input.expiresAt).toISOString() : null,
    supersededBy: input.supersededBy || null,
  });
}

function projectMentalProfile(rows, nowMs = Date.now()) {
  if (!Array.isArray(rows)) throw new Error("profile rows must be an array");
  const themes = new Map();
  const tones = new Map();
  const avoid = new Map();
  const goals = new Map();
  for (const row of rows) {
    const value = validateProfileTag({
      uid: row.uid, kind: row.kind, tag: row.tag, weight: row.weight, basis: row.basis,
      explicit: row.explicit, sourceRefHash: row.source_ref_hash || row.sourceRefHash,
      observedAt: row.observed_at || row.observedAt, expiresAt: row.expires_at || row.expiresAt || null,
      supersededBy: row.superseded_by || row.supersededBy || null,
    });
    if (value.supersededBy || (value.expiresAt && Date.parse(value.expiresAt) <= nowMs)) continue;
    const target = value.kind === "tone" ? tones : value.kind === "avoid" ? avoid : value.kind === "goal" ? goals : themes;
    target.set(value.tag, (target.get(value.tag) || 0) + value.weight);
  }
  const ordered = (map) => [...map.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return Object.freeze({
    themes: ordered(themes).map(([tag]) => tag),
    tones: ordered(tones).map(([tag]) => tag),
    avoidThemes: ordered(avoid).map(([tag]) => tag),
    goals: ordered(goals).map(([tag]) => tag),
    weights: Object.fromEntries(ordered(themes)),
  });
}

module.exports = { KINDS, BASES, validateProfileTag, projectMentalProfile };
