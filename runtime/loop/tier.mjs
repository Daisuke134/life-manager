/**
 * tier.mjs — Pure: selectTier(balanceUsdc, env) → { tier, model }
 *
 * REQ-002: Survival-tier context based on USDC balance; the brain remains Codex at every tier.
 * No I/O. Deterministic. Formally verifiable.
 *
 * PROP-001: selectTier(0)       → { tier: 'broke',  model: ANICCA_FREE_MODEL   }
 * PROP-002: selectTier(0..1.00) → { tier: 'lean',   model: ANICCA_LEAN_MODEL   }
 * PROP-003: selectTier(>1.00)   → { tier: 'funded', model: ANICCA_FUNDED_MODEL }
 * PROP-004: NaN / Infinity / -Infinity / negative → { tier: 'broke', ... }
 */

const CODEX_MODEL = 'gpt-5.6-terra';
const DEFAULT_LEAN_THRESHOLD = 1.00;

/**
 * @param {number} balanceUsdc - USDC balance (may be NaN, Infinity, negative)
 * @param {object} env - key-value map (subset of process.env)
 * @returns {{ tier: 'broke'|'lean'|'funded', model: string }}
 */
export function selectTier(balanceUsdc, env) {
  const threshold   = parseFloat((env && env.LEAN_TIER_THRESHOLD) || DEFAULT_LEAN_THRESHOLD);
  const effectiveThreshold = Number.isFinite(threshold) ? threshold : DEFAULT_LEAN_THRESHOLD;

  // Non-finite or negative balance → broke (PROP-004)
  if (!Number.isFinite(balanceUsdc) || balanceUsdc < 0) {
    return { tier: 'broke', model: CODEX_MODEL };
  }

  if (balanceUsdc === 0) {
    return { tier: 'broke', model: CODEX_MODEL };
  }

  if (balanceUsdc <= effectiveThreshold) {
    return { tier: 'lean', model: CODEX_MODEL };
  }

  return { tier: 'funded', model: CODEX_MODEL };
}
