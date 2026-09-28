export const CANARY_NOTIONAL_USD = 2;
export const CANARY_MAX_USD = 3;

function finite(value) {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

function decision(action, mint, amountUsd, reason, sourceSignature) {
  return { action, mint: mint || null, amountUsd, reason, sourceSignature: sourceSignature || null };
}

function hasSeen(signatures, signature) {
  if (signatures instanceof Set) return signatures.has(signature);
  return Array.isArray(signatures) && signatures.includes(signature);
}

export function decide(snapshot, risk = {}) {
  const mint = snapshot?.destinationMint || snapshot?.mint;
  const sourceSignature = snapshot?.sourceSignature;
  if (!snapshot || typeof snapshot !== "object" || !mint || !sourceSignature) {
    return decision("halt", mint, 0, "candidate_evidence_incomplete", sourceSignature);
  }
  if (risk.killSwitch === true || risk.terminalEffectUnknown === true) {
    return decision("halt", mint, 0, "risk_fence_active", sourceSignature);
  }
  if (snapshot.unsafe === true || snapshot.security === "unsafe" || risk.tokenSafety === "unsafe") {
    return decision("halt", mint, 0, "candidate_unsafe", sourceSignature);
  }
  if (snapshot.requestedAmountUsd != null && finite(snapshot.requestedAmountUsd) !== CANARY_NOTIONAL_USD) {
    return decision("skip", mint, 0, "fixed_notional_required", sourceSignature);
  }
  if (hasSeen(risk.seenSourceSignatures, sourceSignature)) {
    return decision("skip", mint, 0, "source_signature_duplicate", sourceSignature);
  }
  if (finite(risk.openIntentCount ?? 0) > 0 || risk.openIntent === true) {
    return decision("skip", mint, 0, "open_intent_exists", sourceSignature);
  }

  const nowMs = finite(risk.nowMs ?? Date.now());
  const observedAtMs = finite(snapshot.observedAtMs);
  const maxSourceAgeMs = finite(risk.maxSourceAgeMs ?? 15 * 60 * 1000);
  if (nowMs == null || observedAtMs == null || maxSourceAgeMs == null || nowMs < observedAtMs || nowMs - observedAtMs > maxSourceAgeMs) {
    return decision("skip", mint, 0, "source_event_stale", sourceSignature);
  }

  const quoteObservedAtMs = finite(snapshot.quoteObservedAtMs ?? snapshot.market?.jupiter?.observedAtMs);
  const maxQuoteAgeMs = finite(risk.maxQuoteAgeMs ?? 30_000);
  if (quoteObservedAtMs == null || maxQuoteAgeMs == null || nowMs < quoteObservedAtMs || nowMs - quoteObservedAtMs > maxQuoteAgeMs) {
    return decision("skip", mint, 0, "quote_stale", sourceSignature);
  }

  const gmgnLiquidity = finite(snapshot.market?.gmgn?.liquidityUsd);
  const dexLiquidity = finite(snapshot.market?.dexscreener?.liquidityUsd);
  const minLiquidityUsd = finite(risk.minLiquidityUsd ?? 1_000);
  if (gmgnLiquidity == null || dexLiquidity == null || minLiquidityUsd == null) {
    return decision("halt", mint, 0, "liquidity_unknown", sourceSignature);
  }
  if (gmgnLiquidity < minLiquidityUsd || dexLiquidity < minLiquidityUsd) {
    return decision("skip", mint, 0, "liquidity_below_minimum", sourceSignature);
  }

  const priceImpactPct = finite(snapshot.market?.jupiter?.priceImpactPct);
  const maxPriceImpactPct = finite(risk.maxPriceImpactPct ?? 2);
  if (priceImpactPct == null || maxPriceImpactPct == null) {
    return decision("halt", mint, 0, "price_impact_unknown", sourceSignature);
  }
  if (priceImpactPct < 0 || priceImpactPct > maxPriceImpactPct) {
    return decision("skip", mint, 0, "price_impact_exceeded", sourceSignature);
  }

  const solBalanceLamports = finite(risk.solBalanceLamports);
  const minSolReserveLamports = finite(risk.minSolReserveLamports);
  const estimatedFeeLamports = finite(risk.estimatedFeeLamports);
  if (solBalanceLamports == null || minSolReserveLamports == null || estimatedFeeLamports == null) {
    return decision("halt", mint, 0, "sol_reserve_unknown", sourceSignature);
  }
  if (solBalanceLamports < minSolReserveLamports + estimatedFeeLamports) {
    return decision("skip", mint, 0, "insufficient_sol_reserve", sourceSignature);
  }

  const cumulativeCanaryUsd = finite(risk.cumulativeCanaryUsd ?? 0);
  if (cumulativeCanaryUsd == null || cumulativeCanaryUsd < 0) {
    return decision("halt", mint, 0, "canary_budget_unknown", sourceSignature);
  }
  if (cumulativeCanaryUsd + CANARY_NOTIONAL_USD > CANARY_MAX_USD) {
    return decision("skip", mint, 0, "canary_budget_remaining_below_fixed_notional", sourceSignature);
  }

  return decision("copy", mint, CANARY_NOTIONAL_USD, "eligible_initial_canary", sourceSignature);
}

