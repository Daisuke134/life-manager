# LM-EAB Outcome Prediction Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic prediction track to the existing LM-EAB benchmark: loops pre-register outcome probabilities before acting, receipts resolve them afterwards, and a pure scorer reports Brier score and skill over the naive base rate.

**Architecture:** A sibling package `apps/life-manager/eval/prediction/` that copies the LM-EAB contract style (exact-key validators, frozen records, fail-closed reason codes, fixture runner with SHA-256 pinned inputs). It is fixture-only in this plan; wiring predictions into live loops is roadmap item AG2 and a separate plan.

**Tech Stack:** Node.js (repo uses v25; LM-EAB targets 20.19+), CommonJS, `node:test`, `node:crypto`, existing `apps/life-manager/lib/evidence-ref.js`.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-agi-roadmap-design.md` §11.2 and §11.4 row AG1

## Global Constraints

- Work in a worktree cut from fresh `origin/main`; run `bash scripts/verify-source-boundary.sh` before editing and before pushing.
- No network, browser, provider, credential, production-state, or runtime (`runtime/loop/`) change. Fixture-only.
- Money is not scored here; LM-EAB's economic scorer stays the only money authority.
- Probabilities are integers in parts per million (`0..1000000`); no floating-point probabilities in records.
- Any integrity violation makes the result ineligible and nulls every metric (no partial score claim), matching LM-EAB.
- Refs go through `validateEvidenceRefs` (rejects `file://`, local paths, secrets).
- Run each test file separately with `node --test <file>`; passing a directory prints no summary in this repo.

## File Structure

| File | Responsibility |
|---|---|
| `apps/life-manager/eval/prediction/records.js` | Exact-key validators for prediction, resolution, case, expected block; closed vocabularies |
| `apps/life-manager/eval/prediction/records.test.js` | Validator tests |
| `apps/life-manager/eval/prediction/score.js` | `scorePredictions()` pairing, integrity reason codes, Brier/base-rate/skill in ppm |
| `apps/life-manager/eval/prediction/score.test.js` | Scorer tests (perfect, 50/50, wrong, pending, integrity, hindsight, bad input) |
| `apps/life-manager/eval/prediction/run.js` | Fixture runner: SHA-256 check, score, compare to expected |
| `apps/life-manager/eval/prediction/run.test.js` | Corpus 4/4, determinism, tamper rejection |
| `apps/life-manager/eval/prediction/fixtures/*.json` | Four pinned inputs |
| `apps/life-manager/eval/prediction/cases.jsonl` | Four cases (2 tuning, 2 held_out; 2 eligible, 2 ineligible) |

---

### Task 1: Prediction record contracts

**Files:**
- Create: `apps/life-manager/eval/prediction/records.js`
- Test: `apps/life-manager/eval/prediction/records.test.js`

**Interfaces:**
- Consumes: `validateEvidenceRefs(value, label, {min,max})` from `apps/life-manager/lib/evidence-ref.js`.
- Produces: `PPM`, `MAX_PREDICTIONS`, `DOMAINS`, `SPLITS`, `CATEGORIES`, `REASON_CODES`, `validatePrediction(v)`, `validateResolution(v)`, `validateExpected(v)`, `validateCase(v)` — each returns a frozen normalized record or throws `PredictionRecord <label> invalid`.

- [ ] **Step 1: Write the failing test** — create `apps/life-manager/eval/prediction/records.test.js`:

```js
"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  DOMAINS,
  REASON_CODES,
  validateCase,
  validatePrediction,
  validateResolution,
} = require("./records.js");

function prediction(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "outcome_prediction",
    prediction_id: "pred-1",
    loop_id: "coconala",
    occurrence_id: "occ-1",
    domain: "economic",
    action_ref: "lm-occurrence://coconala/occ-1",
    outcome_key: "provider_readback_present",
    probability_ppm: 700000,
    predicted_at: "2026-10-01T00:00:00.000Z",
    resolve_by: "2026-10-02T00:00:00.000Z",
    evidence_refs: [],
    ...overrides,
  };
}

function resolution(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "outcome_resolution",
    prediction_id: "pred-1",
    observed: true,
    resolved_at: "2026-10-01T06:00:00.000Z",
    receipt_refs: ["lm-receipt://coconala/occ-1"],
    ...overrides,
  };
}

test("vocabularies are closed and sorted", () => {
  assert.deepEqual(DOMAINS, [...DOMAINS].sort());
  assert.deepEqual(REASON_CODES, [...REASON_CODES].sort());
});

test("prediction accepts an exact record and normalizes instants", () => {
  const value = validatePrediction(prediction({ predicted_at: "2026-10-01T09:00:00+09:00" }));
  assert.equal(value.predicted_at, "2026-10-01T00:00:00.000Z");
  assert.ok(Object.isFrozen(value));
});

test("prediction rejects extra keys, out-of-range probability and inverted deadline", () => {
  assert.throws(() => validatePrediction({ ...prediction(), note: "x" }), /prediction invalid/u);
  assert.throws(() => validatePrediction(prediction({ probability_ppm: 1000001 })), /probability_ppm invalid/u);
  assert.throws(() => validatePrediction(prediction({ probability_ppm: 0.5 })), /probability_ppm invalid/u);
  assert.throws(
    () => validatePrediction(prediction({ resolve_by: "2026-10-01T00:00:00.000Z" })),
    /resolve_by order invalid/u,
  );
  assert.throws(() => validatePrediction(prediction({ domain: "karma" })), /domain invalid/u);
});

test("prediction rejects local paths and secrets in refs", () => {
  assert.throws(() => validatePrediction(prediction({ action_ref: "file:///Users/x" })), /action_ref invalid/u);
  assert.throws(
    () => validatePrediction(prediction({ evidence_refs: ["lm://api_key/1"] })),
    /evidence_refs invalid/u,
  );
});

test("resolution requires at least one receipt and a boolean outcome", () => {
  assert.ok(validateResolution(resolution()));
  assert.throws(() => validateResolution(resolution({ receipt_refs: [] })), /receipt_refs invalid/u);
  assert.throws(() => validateResolution(resolution({ observed: "yes" })), /observed invalid/u);
});

test("case expected block requires sorted known reason codes", () => {
  const base = {
    schema_version: 1,
    record_type: "outcome_prediction_case",
    case_id: "calibrated-pass",
    split: "tuning",
    category: "canonical",
    fixture_ref: "fixture://prediction/calibrated-pass.json",
    input_sha256: "a".repeat(64),
    expected: {
      eligible: false,
      resolved_count: 0,
      brier_ppm: null,
      base_rate_brier_ppm: null,
      brier_skill_ppm: null,
      reason_codes: ["insufficient_sample", "duplicate_prediction"],
    },
  };
  assert.throws(() => validateCase(base), /expected reason_codes invalid/u);
  base.expected.reason_codes = ["duplicate_prediction", "insufficient_sample"];
  assert.equal(validateCase(base).case_id, "calibrated-pass");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test apps/life-manager/eval/prediction/records.test.js`
Expected: FAIL — `Cannot find module './records.js'`

- [ ] **Step 3: Write minimal implementation** — create `apps/life-manager/eval/prediction/records.js`:

```js
"use strict";

const { validateEvidenceRefs } = require("../../lib/evidence-ref.js");

const SCHEMA_VERSION = 1;
const PPM = 1000000;
const MAX_PREDICTIONS = 5000;
const DOMAINS = Object.freeze(["economic", "mental", "operational", "physical"]);
const SPLITS = Object.freeze(["held_out", "tuning"]);
const CATEGORIES = Object.freeze(["adversarial", "boundary", "canonical", "regression"]);
const REASON_CODES = Object.freeze([
  "duplicate_prediction",
  "duplicate_resolution",
  "insufficient_sample",
  "resolution_before_prediction",
  "resolution_without_prediction",
  "unresolved_after_deadline",
]);

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const HASH = /^[a-f0-9]{64}$/u;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/u;

function invalid(label) {
  throw new Error(`PredictionRecord ${label} invalid`);
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid(label);
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) invalid(label);
}

function identifier(value, label) {
  if (typeof value !== "string" || !ID.test(value)) invalid(label);
  return value;
}

function token(value, label) {
  if (typeof value !== "string" || !TOKEN.test(value)) invalid(label);
  return value;
}

function instant(value, label) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))
    || !/[zZ]|[+-]\d\d:\d\d$/u.test(value)) invalid(label);
  return new Date(value).toISOString();
}

function nonNegativeInteger(value, label, max = Number.MAX_SAFE_INTEGER) {
  if (!Number.isSafeInteger(value) || value < 0 || value > max) invalid(label);
  return value;
}

function refs(value, label, { min = 0, max = 64 } = {}) {
  try {
    return validateEvidenceRefs(value, label, { min, max });
  } catch {
    invalid(label);
  }
}

function validatePrediction(value) {
  exactKeys(value, [
    "schema_version", "record_type", "prediction_id", "loop_id", "occurrence_id", "domain",
    "action_ref", "outcome_key", "probability_ppm", "predicted_at", "resolve_by", "evidence_refs",
  ], "prediction");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "outcome_prediction") {
    invalid("prediction version");
  }
  identifier(value.prediction_id, "prediction_id");
  identifier(value.loop_id, "loop_id");
  identifier(value.occurrence_id, "occurrence_id");
  if (!DOMAINS.includes(value.domain)) invalid("domain");
  const actionRef = refs([value.action_ref], "action_ref", { min: 1, max: 1 })[0];
  token(value.outcome_key, "outcome_key");
  nonNegativeInteger(value.probability_ppm, "probability_ppm", PPM);
  const predictedAt = instant(value.predicted_at, "predicted_at");
  const resolveBy = instant(value.resolve_by, "resolve_by");
  if (Date.parse(resolveBy) <= Date.parse(predictedAt)) invalid("resolve_by order");
  return Object.freeze({
    ...value,
    action_ref: actionRef,
    predicted_at: predictedAt,
    resolve_by: resolveBy,
    evidence_refs: refs(value.evidence_refs, "evidence_refs"),
  });
}

function validateResolution(value) {
  exactKeys(value, [
    "schema_version", "record_type", "prediction_id", "observed", "resolved_at", "receipt_refs",
  ], "resolution");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "outcome_resolution") {
    invalid("resolution version");
  }
  identifier(value.prediction_id, "prediction_id");
  if (typeof value.observed !== "boolean") invalid("observed");
  return Object.freeze({
    ...value,
    resolved_at: instant(value.resolved_at, "resolved_at"),
    receipt_refs: refs(value.receipt_refs, "receipt_refs", { min: 1 }),
  });
}

function validateExpected(value) {
  exactKeys(value, [
    "eligible", "resolved_count", "brier_ppm", "base_rate_brier_ppm", "brier_skill_ppm", "reason_codes",
  ], "expected");
  if (typeof value.eligible !== "boolean") invalid("expected eligible");
  nonNegativeInteger(value.resolved_count, "expected resolved_count", MAX_PREDICTIONS);
  for (const key of ["brier_ppm", "base_rate_brier_ppm"]) {
    if (value[key] !== null) nonNegativeInteger(value[key], `expected ${key}`, PPM);
  }
  if (value.brier_skill_ppm !== null
    && (!Number.isSafeInteger(value.brier_skill_ppm) || Math.abs(value.brier_skill_ppm) > PPM)) {
    invalid("expected brier_skill_ppm");
  }
  if (!Array.isArray(value.reason_codes)
    || value.reason_codes.some((code) => !REASON_CODES.includes(code))
    || value.reason_codes.some((code, index) => index > 0
      && value.reason_codes[index - 1].localeCompare(code) >= 0)) {
    invalid("expected reason_codes");
  }
  return Object.freeze({ ...value, reason_codes: Object.freeze([...value.reason_codes]) });
}

function validateCase(value) {
  exactKeys(value, [
    "schema_version", "record_type", "case_id", "split", "category",
    "fixture_ref", "input_sha256", "expected",
  ], "case");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "outcome_prediction_case") {
    invalid("case version");
  }
  identifier(value.case_id, "case_id");
  if (!SPLITS.includes(value.split)) invalid("split");
  if (!CATEGORIES.includes(value.category)) invalid("category");
  const fixtureRef = refs([value.fixture_ref], "fixture_ref", { min: 1, max: 1 })[0];
  if (typeof value.input_sha256 !== "string" || !HASH.test(value.input_sha256)) invalid("input_sha256");
  return Object.freeze({ ...value, fixture_ref: fixtureRef, expected: validateExpected(value.expected) });
}

module.exports = {
  SCHEMA_VERSION,
  PPM,
  MAX_PREDICTIONS,
  DOMAINS,
  SPLITS,
  CATEGORIES,
  REASON_CODES,
  validatePrediction,
  validateResolution,
  validateExpected,
  validateCase,
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test apps/life-manager/eval/prediction/records.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/life-manager/eval/prediction/records.js apps/life-manager/eval/prediction/records.test.js
git commit -m "feat(eval): add LM-EAB outcome prediction record contracts"
```

### Task 2: Pure prediction scorer

**Files:**
- Create: `apps/life-manager/eval/prediction/score.js`
- Test: `apps/life-manager/eval/prediction/score.test.js`

**Interfaces:**
- Consumes: Task 1 `PPM`, `MAX_PREDICTIONS`, `validatePrediction`, `validateResolution`.
- Produces: `scorePredictions({now, min_sample, predictions, resolutions})` → frozen `{eligible, resolved_count, brier_ppm, base_rate_brier_ppm, brier_skill_ppm, reason_codes}`; metrics are `null` when ineligible. Pending predictions (deadline not reached) are excluded, not failed.

- [ ] **Step 1: Write the failing test** — create `apps/life-manager/eval/prediction/score.test.js`:

```js
"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { scorePredictions } = require("./score.js");

function prediction(id, probabilityPpm, overrides = {}) {
  return {
    schema_version: 1,
    record_type: "outcome_prediction",
    prediction_id: id,
    loop_id: "coconala",
    occurrence_id: `occ-${id}`,
    domain: "economic",
    action_ref: `lm-occurrence://coconala/${id}`,
    outcome_key: "provider_readback_present",
    probability_ppm: probabilityPpm,
    predicted_at: "2026-10-01T00:00:00.000Z",
    resolve_by: "2026-10-02T00:00:00.000Z",
    evidence_refs: [],
    ...overrides,
  };
}

function resolution(id, observed, overrides = {}) {
  return {
    schema_version: 1,
    record_type: "outcome_resolution",
    prediction_id: id,
    observed,
    resolved_at: "2026-10-01T06:00:00.000Z",
    receipt_refs: [`lm-receipt://coconala/${id}`],
    ...overrides,
  };
}

const NOW = "2026-10-03T00:00:00.000Z";

test("perfect forecaster beats the base rate", () => {
  const result = scorePredictions({
    now: NOW,
    min_sample: 4,
    predictions: [prediction("a", 1000000), prediction("b", 1000000), prediction("c", 0), prediction("d", 0)],
    resolutions: [resolution("a", true), resolution("b", true), resolution("c", false), resolution("d", false)],
  });
  assert.deepEqual(result, {
    eligible: true,
    resolved_count: 4,
    brier_ppm: 0,
    base_rate_brier_ppm: 250000,
    brier_skill_ppm: 250000,
    reason_codes: [],
  });
});

test("always-50% forecaster has zero skill over a 50% base rate", () => {
  const result = scorePredictions({
    now: NOW,
    min_sample: 2,
    predictions: [prediction("a", 500000), prediction("b", 500000)],
    resolutions: [resolution("a", true), resolution("b", false)],
  });
  assert.equal(result.brier_ppm, 250000);
  assert.equal(result.base_rate_brier_ppm, 250000);
  assert.equal(result.brier_skill_ppm, 0);
});

test("confidently wrong forecaster has negative skill", () => {
  const result = scorePredictions({
    now: NOW,
    min_sample: 2,
    predictions: [prediction("a", 0), prediction("b", 1000000)],
    resolutions: [resolution("a", true), resolution("b", false)],
  });
  assert.equal(result.brier_ppm, 1000000);
  assert.equal(result.brier_skill_ppm, -750000);
});

test("pending predictions before deadline are excluded, not failed", () => {
  const result = scorePredictions({
    now: "2026-10-01T12:00:00.000Z",
    min_sample: 1,
    predictions: [prediction("a", 900000), prediction("b", 900000)],
    resolutions: [resolution("a", true)],
  });
  assert.equal(result.eligible, true);
  assert.equal(result.resolved_count, 1);
});

test("integrity violations fail closed with no partial score", () => {
  const result = scorePredictions({
    now: NOW,
    min_sample: 1,
    predictions: [prediction("a", 900000), prediction("a", 100000), prediction("late", 500000)],
    resolutions: [
      resolution("a", true),
      resolution("a", false),
      resolution("ghost", true),
    ],
  });
  assert.deepEqual(result, {
    eligible: false,
    resolved_count: 1,
    brier_ppm: null,
    base_rate_brier_ppm: null,
    brier_skill_ppm: null,
    reason_codes: [
      "duplicate_prediction",
      "duplicate_resolution",
      "resolution_without_prediction",
      "unresolved_after_deadline",
    ],
  });
});

test("hindsight resolution before the prediction is rejected", () => {
  const result = scorePredictions({
    now: NOW,
    min_sample: 1,
    predictions: [prediction("a", 900000)],
    resolutions: [resolution("a", true, { resolved_at: "2026-09-30T00:00:00.000Z" })],
  });
  assert.deepEqual(result.reason_codes, ["insufficient_sample", "resolution_before_prediction", "unresolved_after_deadline"]);
});

test("invalid inputs throw instead of scoring", () => {
  assert.throws(() => scorePredictions({ now: "x", min_sample: 1, predictions: [], resolutions: [] }), /now invalid/u);
  assert.throws(() => scorePredictions({ now: NOW, min_sample: 0, predictions: [], resolutions: [] }), /min_sample invalid/u);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test apps/life-manager/eval/prediction/score.test.js`
Expected: FAIL — `Cannot find module './score.js'`

- [ ] **Step 3: Write minimal implementation** — create `apps/life-manager/eval/prediction/score.js`:

```js
"use strict";

const {
  PPM,
  MAX_PREDICTIONS,
  validatePrediction,
  validateResolution,
} = require("./records.js");

function scorePredictions({ now, min_sample: minSample, predictions, resolutions }) {
  const nowMs = Date.parse(now);
  if (!Number.isFinite(nowMs)) throw new Error("PredictionScore now invalid");
  if (!Number.isSafeInteger(minSample) || minSample < 1) throw new Error("PredictionScore min_sample invalid");
  if (!Array.isArray(predictions) || !Array.isArray(resolutions)
    || predictions.length > MAX_PREDICTIONS || resolutions.length > MAX_PREDICTIONS) {
    throw new Error("PredictionScore input invalid");
  }

  const reasons = new Set();
  const byId = new Map();
  for (const raw of predictions) {
    const prediction = validatePrediction(raw);
    if (byId.has(prediction.prediction_id)) reasons.add("duplicate_prediction");
    else byId.set(prediction.prediction_id, prediction);
  }

  const resolved = new Map();
  for (const raw of resolutions) {
    const resolution = validateResolution(raw);
    const prediction = byId.get(resolution.prediction_id);
    if (!prediction) {
      reasons.add("resolution_without_prediction");
      continue;
    }
    if (resolved.has(resolution.prediction_id)) {
      reasons.add("duplicate_resolution");
      continue;
    }
    if (Date.parse(resolution.resolved_at) < Date.parse(prediction.predicted_at)) {
      reasons.add("resolution_before_prediction");
      continue;
    }
    resolved.set(resolution.prediction_id, { prediction, resolution });
  }

  for (const prediction of byId.values()) {
    if (!resolved.has(prediction.prediction_id) && nowMs > Date.parse(prediction.resolve_by)) {
      reasons.add("unresolved_after_deadline");
    }
  }

  const pairs = [...resolved.values()];
  if (pairs.length < minSample) reasons.add("insufficient_sample");
  const reasonCodes = Object.freeze([...reasons].sort());
  const eligible = reasonCodes.length === 0;
  if (!eligible) {
    return Object.freeze({
      eligible,
      resolved_count: pairs.length,
      brier_ppm: null,
      base_rate_brier_ppm: null,
      brier_skill_ppm: null,
      reason_codes: reasonCodes,
    });
  }

  // ponytail: integer ppm arithmetic; exact while predictions <= MAX_PREDICTIONS (sum <= 5e15).
  let squaredError = 0;
  let observedCount = 0;
  for (const { prediction, resolution } of pairs) {
    const target = resolution.observed ? PPM : 0;
    const error = prediction.probability_ppm - target;
    squaredError += error * error;
    if (resolution.observed) observedCount += 1;
  }
  const brier = Math.floor(squaredError / (pairs.length * PPM));
  const rate = Math.floor((observedCount * PPM) / pairs.length);
  const baseRateBrier = Math.floor((rate * (PPM - rate)) / PPM);
  return Object.freeze({
    eligible,
    resolved_count: pairs.length,
    brier_ppm: brier,
    base_rate_brier_ppm: baseRateBrier,
    brier_skill_ppm: baseRateBrier - brier,
    reason_codes: reasonCodes,
  });
}

module.exports = { scorePredictions };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test apps/life-manager/eval/prediction/score.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/life-manager/eval/prediction/score.js apps/life-manager/eval/prediction/score.test.js
git commit -m "feat(eval): score outcome predictions with Brier skill over base rate"
```

### Task 3: Fixture corpus and runner

**Files:**
- Create: `apps/life-manager/eval/prediction/fixtures/{calibrated-pass,hindsight-block,overconfident-held-out,duplicate-block}.json`
- Create: `apps/life-manager/eval/prediction/cases.jsonl`
- Create: `apps/life-manager/eval/prediction/run.js`
- Test: `apps/life-manager/eval/prediction/run.test.js`

**Interfaces:**
- Consumes: Task 1 `validateCase`; Task 2 `scorePredictions`.
- Produces: `runCorpus(casesPath)` → frozen `{case_set_sha256, total, passed, results[]}`; CLI `node apps/life-manager/eval/prediction/run.js` prints one JSON line, exit 0 only when all cases pass.

- [ ] **Step 1: Create the four fixtures exactly as below** (byte-exact; the case hashes depend on them, including the trailing newline).

`apps/life-manager/eval/prediction/fixtures/calibrated-pass.json`:

```json
{
  "now": "2026-10-03T00:00:00.000Z",
  "min_sample": 4,
  "predictions": [
    {
      "schema_version": 1,
      "record_type": "outcome_prediction",
      "prediction_id": "a",
      "loop_id": "coconala",
      "occurrence_id": "occ-a",
      "domain": "economic",
      "action_ref": "lm-occurrence://coconala/a",
      "outcome_key": "provider_readback_present",
      "probability_ppm": 900000,
      "predicted_at": "2026-10-01T00:00:00.000Z",
      "resolve_by": "2026-10-02T00:00:00.000Z",
      "evidence_refs": []
    },
    {
      "schema_version": 1,
      "record_type": "outcome_prediction",
      "prediction_id": "b",
      "loop_id": "coconala",
      "occurrence_id": "occ-b",
      "domain": "economic",
      "action_ref": "lm-occurrence://coconala/b",
      "outcome_key": "provider_readback_present",
      "probability_ppm": 800000,
      "predicted_at": "2026-10-01T00:00:00.000Z",
      "resolve_by": "2026-10-02T00:00:00.000Z",
      "evidence_refs": []
    },
    {
      "schema_version": 1,
      "record_type": "outcome_prediction",
      "prediction_id": "c",
      "loop_id": "coconala",
      "occurrence_id": "occ-c",
      "domain": "economic",
      "action_ref": "lm-occurrence://coconala/c",
      "outcome_key": "provider_readback_present",
      "probability_ppm": 200000,
      "predicted_at": "2026-10-01T00:00:00.000Z",
      "resolve_by": "2026-10-02T00:00:00.000Z",
      "evidence_refs": []
    },
    {
      "schema_version": 1,
      "record_type": "outcome_prediction",
      "prediction_id": "d",
      "loop_id": "coconala",
      "occurrence_id": "occ-d",
      "domain": "economic",
      "action_ref": "lm-occurrence://coconala/d",
      "outcome_key": "provider_readback_present",
      "probability_ppm": 100000,
      "predicted_at": "2026-10-01T00:00:00.000Z",
      "resolve_by": "2026-10-02T00:00:00.000Z",
      "evidence_refs": []
    }
  ],
  "resolutions": [
    {
      "schema_version": 1,
      "record_type": "outcome_resolution",
      "prediction_id": "a",
      "observed": true,
      "resolved_at": "2026-10-01T06:00:00.000Z",
      "receipt_refs": [
        "lm-receipt://coconala/a"
      ]
    },
    {
      "schema_version": 1,
      "record_type": "outcome_resolution",
      "prediction_id": "b",
      "observed": true,
      "resolved_at": "2026-10-01T06:00:00.000Z",
      "receipt_refs": [
        "lm-receipt://coconala/b"
      ]
    },
    {
      "schema_version": 1,
      "record_type": "outcome_resolution",
      "prediction_id": "c",
      "observed": false,
      "resolved_at": "2026-10-01T06:00:00.000Z",
      "receipt_refs": [
        "lm-receipt://coconala/c"
      ]
    },
    {
      "schema_version": 1,
      "record_type": "outcome_resolution",
      "prediction_id": "d",
      "observed": false,
      "resolved_at": "2026-10-01T06:00:00.000Z",
      "receipt_refs": [
        "lm-receipt://coconala/d"
      ]
    }
  ]
}
```

`apps/life-manager/eval/prediction/fixtures/hindsight-block.json`:

```json
{
  "now": "2026-10-03T00:00:00.000Z",
  "min_sample": 1,
  "predictions": [
    {
      "schema_version": 1,
      "record_type": "outcome_prediction",
      "prediction_id": "a",
      "loop_id": "coconala",
      "occurrence_id": "occ-a",
      "domain": "economic",
      "action_ref": "lm-occurrence://coconala/a",
      "outcome_key": "provider_readback_present",
      "probability_ppm": 900000,
      "predicted_at": "2026-10-01T00:00:00.000Z",
      "resolve_by": "2026-10-02T00:00:00.000Z",
      "evidence_refs": []
    }
  ],
  "resolutions": [
    {
      "schema_version": 1,
      "record_type": "outcome_resolution",
      "prediction_id": "a",
      "observed": true,
      "resolved_at": "2026-09-30T00:00:00.000Z",
      "receipt_refs": [
        "lm-receipt://coconala/a"
      ]
    }
  ]
}
```

`apps/life-manager/eval/prediction/fixtures/overconfident-held-out.json`:

```json
{
  "now": "2026-10-03T00:00:00.000Z",
  "min_sample": 2,
  "predictions": [
    {
      "schema_version": 1,
      "record_type": "outcome_prediction",
      "prediction_id": "a",
      "loop_id": "coconala",
      "occurrence_id": "occ-a",
      "domain": "economic",
      "action_ref": "lm-occurrence://coconala/a",
      "outcome_key": "provider_readback_present",
      "probability_ppm": 1000000,
      "predicted_at": "2026-10-01T00:00:00.000Z",
      "resolve_by": "2026-10-02T00:00:00.000Z",
      "evidence_refs": []
    },
    {
      "schema_version": 1,
      "record_type": "outcome_prediction",
      "prediction_id": "b",
      "loop_id": "coconala",
      "occurrence_id": "occ-b",
      "domain": "economic",
      "action_ref": "lm-occurrence://coconala/b",
      "outcome_key": "provider_readback_present",
      "probability_ppm": 1000000,
      "predicted_at": "2026-10-01T00:00:00.000Z",
      "resolve_by": "2026-10-02T00:00:00.000Z",
      "evidence_refs": []
    }
  ],
  "resolutions": [
    {
      "schema_version": 1,
      "record_type": "outcome_resolution",
      "prediction_id": "a",
      "observed": true,
      "resolved_at": "2026-10-01T06:00:00.000Z",
      "receipt_refs": [
        "lm-receipt://coconala/a"
      ]
    },
    {
      "schema_version": 1,
      "record_type": "outcome_resolution",
      "prediction_id": "b",
      "observed": false,
      "resolved_at": "2026-10-01T06:00:00.000Z",
      "receipt_refs": [
        "lm-receipt://coconala/b"
      ]
    }
  ]
}
```

`apps/life-manager/eval/prediction/fixtures/duplicate-block.json`:

```json
{
  "now": "2026-10-03T00:00:00.000Z",
  "min_sample": 1,
  "predictions": [
    {
      "schema_version": 1,
      "record_type": "outcome_prediction",
      "prediction_id": "a",
      "loop_id": "coconala",
      "occurrence_id": "occ-a",
      "domain": "economic",
      "action_ref": "lm-occurrence://coconala/a",
      "outcome_key": "provider_readback_present",
      "probability_ppm": 600000,
      "predicted_at": "2026-10-01T00:00:00.000Z",
      "resolve_by": "2026-10-02T00:00:00.000Z",
      "evidence_refs": []
    },
    {
      "schema_version": 1,
      "record_type": "outcome_prediction",
      "prediction_id": "a",
      "loop_id": "coconala",
      "occurrence_id": "occ-a",
      "domain": "economic",
      "action_ref": "lm-occurrence://coconala/a",
      "outcome_key": "provider_readback_present",
      "probability_ppm": 400000,
      "predicted_at": "2026-10-01T00:00:00.000Z",
      "resolve_by": "2026-10-02T00:00:00.000Z",
      "evidence_refs": []
    }
  ],
  "resolutions": [
    {
      "schema_version": 1,
      "record_type": "outcome_resolution",
      "prediction_id": "a",
      "observed": true,
      "resolved_at": "2026-10-01T06:00:00.000Z",
      "receipt_refs": [
        "lm-receipt://coconala/a"
      ]
    }
  ]
}
```

- [ ] **Step 2: Create `cases.jsonl` exactly as below** (hand-checked expectations: calibrated errors 0.1/0.2/0.2/0.1 give Brier 0.025 = 25000 ppm; overconfident 1.0/1.0 against true/false gives 0.5 = 500000 ppm, skill -250000):

```json
{"schema_version":1,"record_type":"outcome_prediction_case","case_id":"calibrated-pass","split":"tuning","category":"canonical","fixture_ref":"fixture://prediction/calibrated-pass.json","input_sha256":"de342f51f4993ce16a989074bf440d407d1a0b50f553c4a42297ea2f5e9a98ce","expected":{"eligible":true,"resolved_count":4,"brier_ppm":25000,"base_rate_brier_ppm":250000,"brier_skill_ppm":225000,"reason_codes":[]}}
{"schema_version":1,"record_type":"outcome_prediction_case","case_id":"hindsight-block","split":"tuning","category":"adversarial","fixture_ref":"fixture://prediction/hindsight-block.json","input_sha256":"d482e4ec58fe0ab70773064c3c762862ce1b474b3c155d5868a68886588caa5d","expected":{"eligible":false,"resolved_count":0,"brier_ppm":null,"base_rate_brier_ppm":null,"brier_skill_ppm":null,"reason_codes":["insufficient_sample","resolution_before_prediction","unresolved_after_deadline"]}}
{"schema_version":1,"record_type":"outcome_prediction_case","case_id":"overconfident-held-out","split":"held_out","category":"boundary","fixture_ref":"fixture://prediction/overconfident-held-out.json","input_sha256":"a806ef0b355e6022b7b26e84e2d3e915cd6bff5a4f5b5393eef70d084a8f3194","expected":{"eligible":true,"resolved_count":2,"brier_ppm":500000,"base_rate_brier_ppm":250000,"brier_skill_ppm":-250000,"reason_codes":[]}}
{"schema_version":1,"record_type":"outcome_prediction_case","case_id":"duplicate-block","split":"held_out","category":"adversarial","fixture_ref":"fixture://prediction/duplicate-block.json","input_sha256":"3419a99006634608fc23c8948b0026c3d24d8cc030ea836591b7f3d25b743aac","expected":{"eligible":false,"resolved_count":1,"brier_ppm":null,"base_rate_brier_ppm":null,"brier_skill_ppm":null,"reason_codes":["duplicate_prediction"]}}
```

- [ ] **Step 3: Verify fixture hashes match the cases**

Run: `for n in calibrated-pass hindsight-block overconfident-held-out duplicate-block; do shasum -a 256 apps/life-manager/eval/prediction/fixtures/$n.json; done`
Expected: each hash equals that case's `input_sha256`. If not, the fixture bytes differ — fix the fixture, never the hash.

- [ ] **Step 4: Write the failing test** — create `apps/life-manager/eval/prediction/run.test.js`:

```js
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { runCorpus } = require("./run.js");

const CASES = path.join(__dirname, "cases.jsonl");

test("committed corpus passes 4/4 with both splits and both verdicts", () => {
  const summary = runCorpus(CASES);
  assert.equal(summary.total, 4);
  assert.equal(summary.passed, 4);
  assert.deepEqual([...new Set(summary.results.map((item) => item.split))].sort(), ["held_out", "tuning"]);
  assert.deepEqual([...new Set(summary.results.map((item) => item.actual.eligible))].sort(), [false, true]);
});

test("two runs are byte-identical", () => {
  assert.equal(JSON.stringify(runCorpus(CASES)), JSON.stringify(runCorpus(CASES)));
});

test("a tampered fixture hash is rejected", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "prediction-cases-"));
  const tampered = fs.readFileSync(CASES, "utf8").replace(/"input_sha256":"[a-f0-9]{64}"/u, `"input_sha256":"${"0".repeat(64)}"`);
  const casesPath = path.join(dir, "cases.jsonl");
  fs.writeFileSync(casesPath, tampered);
  assert.throws(() => runCorpus(casesPath), /hash mismatch/u);
  fs.rmSync(dir, { recursive: true, force: true });
});
```

- [ ] **Step 5: Run test to verify it fails**

Run: `node --test apps/life-manager/eval/prediction/run.test.js`
Expected: FAIL — `Cannot find module './run.js'`

- [ ] **Step 6: Write minimal implementation** — create `apps/life-manager/eval/prediction/run.js`:

```js
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const { validateCase } = require("./records.js");
const { scorePredictions } = require("./score.js");

const FIXTURE_PREFIX = "fixture://prediction/";
const FIXTURE_DIR = path.join(__dirname, "fixtures");

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function readFixture(fixtureRef) {
  if (!fixtureRef.startsWith(FIXTURE_PREFIX)) throw new Error("PredictionRun fixture_ref invalid");
  const name = fixtureRef.slice(FIXTURE_PREFIX.length);
  if (!/^[a-z0-9-]+\.json$/u.test(name)) throw new Error("PredictionRun fixture_ref invalid");
  return fs.readFileSync(path.join(FIXTURE_DIR, name));
}

function evaluateCase(rawCase) {
  const testCase = validateCase(rawCase);
  const bytes = readFixture(testCase.fixture_ref);
  if (sha256(bytes) !== testCase.input_sha256) throw new Error(`PredictionRun ${testCase.case_id} hash mismatch`);
  const actual = scorePredictions(JSON.parse(bytes.toString("utf8")));
  const passed = JSON.stringify(actual) === JSON.stringify(testCase.expected);
  return Object.freeze({ case_id: testCase.case_id, split: testCase.split, passed, actual });
}

function runCorpus(casesPath) {
  const text = fs.readFileSync(casesPath, "utf8");
  const cases = text.split("\n").filter((line) => line.trim() !== "").map((line) => JSON.parse(line));
  const ids = new Set(cases.map((item) => item.case_id));
  if (cases.length === 0 || ids.size !== cases.length) throw new Error("PredictionRun corpus invalid");
  const results = cases.map(evaluateCase);
  return Object.freeze({
    case_set_sha256: sha256(Buffer.from(text, "utf8")),
    total: results.length,
    passed: results.filter((item) => item.passed).length,
    results,
  });
}

function main(argv) {
  const casesPath = argv[0] || path.join(__dirname, "cases.jsonl");
  const summary = runCorpus(casesPath);
  process.stdout.write(`${JSON.stringify(summary)}\n`);
  process.exitCode = summary.passed === summary.total ? 0 : 1;
}

if (require.main === module) {
  main(process.argv.slice(2));
}

module.exports = { evaluateCase, runCorpus };
```

- [ ] **Step 7: Run tests and the CLI**

Run: `node --test apps/life-manager/eval/prediction/run.test.js && node apps/life-manager/eval/prediction/run.js`
Expected: 3 tests PASS; CLI prints `"total":4,"passed":4` and exits 0.

- [ ] **Step 8: Commit**

```bash
git add apps/life-manager/eval/prediction/fixtures apps/life-manager/eval/prediction/cases.jsonl apps/life-manager/eval/prediction/run.js apps/life-manager/eval/prediction/run.test.js
git commit -m "feat(eval): add pinned outcome prediction corpus and runner"
```

### Task 4: Full focused verification and integration

**Files:**
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-agi-roadmap-design.md` §11.4 (move cursor from AG1 to AG2 and record the evidence)

- [ ] **Step 1: Run every prediction and LM-EAB test file separately**

Run: `for f in apps/life-manager/eval/prediction/*.test.js apps/life-manager/eval/economic-autonomy/*.test.js apps/life-manager/eval/agent-contract/*.test.js; do echo "$f"; node --test "$f" 2>&1 | grep -E "^ℹ (pass|fail) "; done`
Expected: prediction 6+7+3 = 16 pass; LM-EAB 8+7+26 = 41 pass; agent-contract 2+7+4 = 13 pass; every `fail 0`.

- [ ] **Step 2: Prove determinism**

Run: `node apps/life-manager/eval/prediction/run.js > /tmp/p1.json; node apps/life-manager/eval/prediction/run.js > /tmp/p2.json; cmp /tmp/p1.json /tmp/p2.json && echo identical`
Expected: `identical`

- [ ] **Step 3: Update the spec cursor** — in §11.4 replace `現在の cursor: **AG1**` with `現在の cursor: **AG2**` and add one line under the table: `AG1 完了: prediction 16/16・LM-EAB 41/41・agent-contract 13/13 PASS、corpus 4/4、2回の実行で出力が一致（Task 3 Step 8 の commit）。`

- [ ] **Step 4: Commit, push, PR, merge**

```bash
bash scripts/verify-source-boundary.sh
git add docs/superpowers/specs/2026-09-25-life-manager-agi-roadmap-design.md
git commit -m "docs(agi): record AG1 prediction track evidence and advance cursor"
git push -u origin feat/lm-eab-prediction-track
gh pr create --title "feat(eval): LM-EAB outcome prediction track" --body "Implements roadmap AG1. Fixture-only; no runtime or provider change."
gh pr merge --admin --squash
```
