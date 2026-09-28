import { append, openIntent, readRows } from "./journal.mjs";
import { verifyReceipt } from "./receipt.mjs";

function rejected(reason, intent = {}) {
  return {
    kind: "receipt",
    status: "rejected",
    effect: "none",
    verified: false,
    reason,
    retry: false,
    intentId: intent.intentId || null,
    sourceSignature: intent.sourceSignature || null,
    signature: null,
  };
}

function confirmationSucceeded(value) {
  return value === true || value?.confirmed === true || value?.status === "confirmed" || value?.status === "finalized";
}

function sentSignature(value) {
  if (typeof value === "string" && value) return value;
  if (typeof value?.signature === "string" && value.signature) return value.signature;
  if (typeof value?.hash === "string" && value.hash) return value.hash;
  return null;
}

function journalIntent(intent, owner) {
  return {
    kind: "intent",
    intentId: intent.intentId,
    mode: "live",
    action: "copy",
    owner,
    mint: intent.destinationMint || intent.mint,
    sourceMint: intent.sourceMint,
    destinationMint: intent.destinationMint || intent.mint,
    sourceRawAmount: intent.sourceRawAmount,
    destinationRawAmount: intent.destinationRawAmount,
    amountUsd: 2,
    sourceSignature: intent.sourceSignature,
    createdAtMs: intent.createdAtMs || null,
  };
}

async function appendReceipt(journalPath, intent, fields) {
  return append(journalPath, {
    kind: "receipt",
    intentId: intent.intentId || null,
    sourceSignature: intent.sourceSignature || null,
    retry: false,
    ...fields,
  });
}

export async function executeCanary(intent, quote, wallet, clients, journalPath) {
  if (!intent || typeof intent !== "object" || intent.mode !== "live") return rejected("live_mode_required", intent);
  if (process.env.SOL_COPY_LIVE !== "1") return rejected("live_gate_missing", intent);
  if (intent.liveGate !== true) return rejected("live_double_gate_missing", intent);
  if (Number(intent.amountUsd) !== 2) return rejected("fixed_notional_required", intent);
  const owner = wallet?.publicKey;
  const destinationMint = intent.destinationMint || intent.mint;
  if (!owner || !intent.intentId || !intent.sourceSignature || !intent.sourceMint || !destinationMint) {
    return rejected("live_intent_invalid", intent);
  }
  if (intent.owner && intent.owner !== owner) return rejected("wallet_owner_mismatch", intent);
  if (quote?.inputMint !== intent.sourceMint || quote?.outputMint !== destinationMint
    || String(quote?.inAmount) !== String(intent.sourceRawAmount)
    || String(quote?.outAmount ?? quote?.outputAmount) !== String(intent.destinationRawAmount)) {
    return rejected("quote_intent_mismatch", intent);
  }
  if (!clients || typeof clients.build !== "function" || typeof clients.send !== "function"
    || typeof clients.confirm !== "function" || typeof clients.readTransaction !== "function"
    || typeof clients.readBalances !== "function" || typeof wallet.signTransaction !== "function") {
    return rejected("live_clients_invalid", intent);
  }

  const rows = await readRows(journalPath);
  if (rows.some((row) => row.sourceSignature === intent.sourceSignature)) return rejected("source_signature_duplicate", intent);
  if ((await openIntent(journalPath)).length > 0) return rejected("open_intent_exists", intent);

  let intentRecorded = false;
  let sendAttempted = false;
  let signature = null;
  try {
    const beforeBalances = await clients.readBalances({ owner, phase: "before", intent });
    await append(journalPath, journalIntent(intent, owner));
    intentRecorded = true;
    const unsigned = await clients.build(quote, { owner, intent });
    const signed = await wallet.signTransaction(unsigned);
    sendAttempted = true;
    signature = sentSignature(await clients.send(signed));
    if (!signature) throw new Error("provider_signature_missing");
    const confirmation = await clients.confirm(signature);
    if (!confirmationSucceeded(confirmation)) {
      return await appendReceipt(journalPath, intent, {
        status: "rejected",
        effect: "none",
        verified: false,
        reason: "confirmation_failed",
        signature,
      });
    }
    const rawTransaction = await clients.readTransaction(signature);
    const afterBalances = await clients.readBalances({ owner, phase: "after", intent, signature });
    const verification = verifyReceipt(intent, { ...rawTransaction, signature, confirmed: true }, beforeBalances, afterBalances);
    return await appendReceipt(journalPath, intent, {
      ...verification,
      effect: verification.status === "verified" ? "verified" : "unknown",
      signature,
    });
  } catch (error) {
    if (!intentRecorded) return rejected(sendAttempted ? "live_effect_unknown" : "live_preflight_failed", intent);
    return appendReceipt(journalPath, intent, {
      status: sendAttempted ? "effect_unknown" : "rejected",
      effect: sendAttempted ? "unknown" : "none",
      verified: false,
      reason: sendAttempted ? "live_effect_unknown" : "live_preflight_failed",
      signature,
      feeLamports: null,
      evidence: { errorClass: error?.name || "Error" },
    });
  }
}

