import { append, readRows } from "./journal.mjs";

function numberOrNull(value) {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

function rejected(reason, intent = {}) {
  return {
    kind: "receipt",
    status: "rejected",
    effect: "none",
    reason,
    intentId: intent.intentId || null,
    sourceSignature: intent.sourceSignature || null,
  };
}

export async function paperApply(intent, quote, journalPath) {
  if (!intent || typeof intent !== "object" || intent.action !== "copy" || intent.mode !== "paper") {
    return rejected("paper_intent_invalid", intent);
  }
  if (typeof intent.intentId !== "string" || !intent.intentId
    || typeof intent.sourceSignature !== "string" || !intent.sourceSignature
    || typeof intent.mint !== "string" || !intent.mint
    || Number(intent.amountUsd) !== 2) {
    return rejected("paper_intent_invalid", intent);
  }
  const outAmount = numberOrNull(quote?.outAmount ?? quote?.outputAmount);
  const priceImpactPct = numberOrNull(quote?.priceImpactPct ?? quote?.priceImpact);
  const simulatedFeeUsd = numberOrNull(quote?.simulatedFeeUsd);
  const simulatedSlippageUsd = numberOrNull(quote?.simulatedSlippageUsd);
  if (outAmount == null || outAmount <= 0 || priceImpactPct == null || priceImpactPct < 0
    || simulatedFeeUsd == null || simulatedFeeUsd < 0
    || simulatedSlippageUsd == null || simulatedSlippageUsd < 0) {
    return rejected("paper_quote_invalid", intent);
  }

  const rows = await readRows(journalPath);
  if (rows.some((row) => row.sourceSignature === intent.sourceSignature)) {
    return rejected("source_signature_duplicate", intent);
  }
  const existingIntent = rows.find((row) => row.kind === "intent" && row.intentId === intent.intentId);
  if (existingIntent) return rejected("open_intent_exists", intent);

  await append(journalPath, {
    kind: "intent",
    intentId: intent.intentId,
    mode: "paper",
    action: "copy",
    mint: intent.mint,
    amountUsd: 2,
    sourceSignature: intent.sourceSignature,
    createdAtMs: intent.createdAtMs || null,
  });

  const receipt = {
    kind: "receipt",
    intentId: intent.intentId,
    status: "paper",
    effect: "none",
    sourceSignature: intent.sourceSignature,
    mint: intent.mint,
    amountUsd: 2,
    quotedOutAmount: outAmount,
    priceImpactPct,
    simulatedFeeUsd,
    simulatedSlippageUsd,
    netPnlUsd: -(simulatedFeeUsd + simulatedSlippageUsd),
  };
  return append(journalPath, receipt);
}

