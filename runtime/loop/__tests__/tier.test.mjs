// PROP-001, PROP-002, PROP-003, PROP-004 — tier.mjs unit tests
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { selectTier } from '../tier.mjs';

// PROP-001: balance===0 -> broke, model==ANICCA_FREE_MODEL default
test('PROP-001: selectTier(0) returns broke tier with free model', () => {
  const result = selectTier(0, {});
  assert.equal(result.tier, 'broke');
  assert.equal(result.model, 'gpt-5.6-terra');
});

test('agent reasoning stays on the configured Codex brain despite legacy model env overrides', () => {
  const result = selectTier(0, { ANICCA_FREE_MODEL: 'free/glm-4.7' });
  assert.equal(result.tier, 'broke');
  assert.equal(result.model, 'gpt-5.6-terra');
});

// PROP-002: 0 < balance <= 1.00 -> lean, model==ANICCA_LEAN_MODEL default
test('PROP-002: selectTier(0.5) returns lean tier with lean model', () => {
  const result = selectTier(0.5, {});
  assert.equal(result.tier, 'lean');
  assert.equal(result.model, 'gpt-5.6-terra');
});

// PROP-002: boundary at exactly 1.00 -> lean
test('PROP-002: selectTier(1.00) is still lean (boundary)', () => {
  const result = selectTier(1.00, {});
  assert.equal(result.tier, 'lean');
});

// PROP-003: balance > 1.00 -> funded, model==ANICCA_FUNDED_MODEL default
test('PROP-003: selectTier(5.0) returns funded tier with funded model', () => {
  const result = selectTier(5.0, {});
  assert.equal(result.tier, 'funded');
  assert.equal(result.model, 'gpt-5.6-terra');
});

// PROP-003: just above threshold
test('PROP-003: selectTier(1.01) returns funded', () => {
  const result = selectTier(1.01, {});
  assert.equal(result.tier, 'funded');
});

// PROP-004: NaN -> broke
test('PROP-004: selectTier(NaN) returns broke', () => {
  const result = selectTier(NaN, {});
  assert.equal(result.tier, 'broke');
});

// PROP-004: Infinity -> broke
test('PROP-004: selectTier(Infinity) returns broke', () => {
  const result = selectTier(Infinity, {});
  assert.equal(result.tier, 'broke');
});

// PROP-004: -Infinity -> broke
test('PROP-004: selectTier(-Infinity) returns broke', () => {
  const result = selectTier(-Infinity, {});
  assert.equal(result.tier, 'broke');
});

// PROP-004: negative balance -> broke (edge case)
test('PROP-004: selectTier(-0.5) returns broke', () => {
  const result = selectTier(-0.5, {});
  assert.equal(result.tier, 'broke');
});

// LEAN_TIER_THRESHOLD env override
test('PROP-002/003: LEAN_TIER_THRESHOLD env override shifts boundary', () => {
  const result2 = selectTier(2.0, { LEAN_TIER_THRESHOLD: '5.0' });
  assert.equal(result2.tier, 'lean');
  const result3 = selectTier(6.0, { LEAN_TIER_THRESHOLD: '5.0' });
  assert.equal(result3.tier, 'funded');
});
