import { append, readRows } from "./journal.mjs";

const EXIT_ACTIONS = new Set(["mirror_exit", "stop_exit", "time_exit"]);

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
  if (!intent || typeof intent !== "object" || intent.mode !== "paper"
    || (intent.action !== "copy_entry" && !EXIT_ACTIONS.has(intent.action))) {
    return rejected("paper_intent_invalid", intent);
  }
  if (typeof intent.intentId !== "string" || !intent.intentId
    || typeof intent.sourceSignature !== "string" || !intent.sourceSignature
    || typeof intent.mint !== "string" || !intent.mint
    || (intent.action === "copy_entry" && Number(intent.amountUsd) !== 2)
    || (intent.action === "copy_entry"
      && (!Number.isFinite(Number(intent.sourceAmountUsd))
        || Number(intent.sourceAmountUsd) <= 0
        || Number(intent.sourceAmountUsd) > 2))
    || (EXIT_ACTIONS.has(intent.action) && (!intent.position || typeof intent.position !== "object"))) {
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
    action: intent.action,
    mint: intent.mint,
    amountUsd: Number.isFinite(Number(intent.amountUsd)) ? Number(intent.amountUsd) : null,
    sourceAmountUsd: numberOrNull(intent.sourceAmountUsd),
    sourceSignature: intent.sourceSignature,
    targetAddress: intent.targetAddress || null,
    sourceMint: intent.sourceMint || intent.position?.mint || quote?.inputMint || null,
    destinationMint: intent.destinationMint || intent.position?.exitMint || quote?.outputMint || null,
    sourceRawAmount: intent.sourceRawAmount || intent.position?.amountRaw || quote?.inAmount || null,
    destinationRawAmount: intent.destinationRawAmount || quote?.outAmount || quote?.outputAmount || null,
    createdAtMs: intent.createdAtMs || null,
  });

  const receipt = {
    kind: "receipt",
    intentId: intent.intentId,
    status: "paper",
    effect: "none",
    action: intent.action,
    sourceSignature: intent.sourceSignature,
    mint: intent.mint,
    amountUsd: Number.isFinite(Number(intent.amountUsd)) ? Number(intent.amountUsd) : null,
    sourceAmountUsd: numberOrNull(intent.sourceAmountUsd),
    ...(intent.action === "copy_entry" ? {
      position: {
        mint: intent.destinationMint || intent.mint,
        amountRaw: String(intent.destinationRawAmount || outAmount),
        entryPriceUsd: numberOrNull(quote?.priceUsd),
        amountUsd: numberOrNull(intent.amountUsd),
        entryAtMs: intent.createdAtMs || null,
        sourceSignature: intent.sourceSignature,
        exitMint: intent.sourceMint || quote?.inputMint || null,
        targetAddress: intent.targetAddress || null,
      },
    } : {}),
    quotedOutAmount: outAmount,
    priceImpactPct,
    simulatedFeeUsd,
    simulatedSlippageUsd,
    netPnlUsd: -(simulatedFeeUsd + simulatedSlippageUsd),
  };
  return append(journalPath, receipt);
}
