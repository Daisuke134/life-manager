function toBigInt(value) {
  if (typeof value === "bigint") return value;
  if (typeof value === "number" && Number.isSafeInteger(value)) return BigInt(value);
  if (typeof value === "string" && /^-?\d+$/.test(value)) {
    try { return BigInt(value); } catch { return null; }
  }
  return null;
}

function rowAmount(row) {
  return row?.rawAmount ?? row?.amount ?? row?.uiTokenAmount?.amount;
}

function collectBalances(rows, owner) {
  if (!Array.isArray(rows)) return null;
  const result = new Map();
  for (const row of rows) {
    if (!row || row.owner !== owner || typeof row.mint !== "string" || !row.mint) continue;
    const amount = toBigInt(rowAmount(row));
    if (amount == null) return null;
    result.set(row.mint, (result.get(row.mint) || 0n) + amount);
  }
  return result;
}

function tokenDeltasFromTransaction(transaction, owner) {
  if (Array.isArray(transaction?.tokenDeltas)) {
    const result = new Map();
    for (const row of transaction.tokenDeltas) {
      if (!row || row.owner !== owner || typeof row.mint !== "string") continue;
      const delta = toBigInt(row.deltaRaw ?? row.delta);
      if (delta == null) return null;
      result.set(row.mint, (result.get(row.mint) || 0n) + delta);
    }
    return result;
  }
  const before = collectBalances(transaction?.meta?.preTokenBalances, owner);
  const after = collectBalances(transaction?.meta?.postTokenBalances, owner);
  if (!before || !after) return null;
  const result = new Map();
  for (const mint of new Set([...before.keys(), ...after.keys()])) {
    const delta = (after.get(mint) || 0n) - (before.get(mint) || 0n);
    if (delta !== 0n) result.set(mint, delta);
  }
  return result;
}

function balanceDeltas(beforeRows, afterRows, owner) {
  const before = collectBalances(beforeRows, owner);
  const after = collectBalances(afterRows, owner);
  if (!before || !after) return null;
  const result = new Map();
  for (const mint of new Set([...before.keys(), ...after.keys()])) {
    const delta = (after.get(mint) || 0n) - (before.get(mint) || 0n);
    if (delta !== 0n) result.set(mint, delta);
  }
  return result;
}

function mapToJson(map) {
  return Object.fromEntries([...map.entries()].map(([mint, delta]) => [mint, delta.toString()]));
}

function confirmed(transaction) {
  return transaction?.confirmed === true
    || transaction?.confirmationStatus === "confirmed"
    || transaction?.confirmationStatus === "finalized";
}

function result(status, reason, fields = {}) {
  return {
    verified: status === "verified",
    status,
    reason,
    netUsd: null,
    feeLamports: fields.feeLamports ?? null,
    evidence: fields.evidence || {},
  };
}

export function verifyReceipt(intent, transaction, beforeBalances, afterBalances) {
  if (!transaction || typeof transaction !== "object") return result("effect_unknown", "receipt_missing");
  if (!confirmed(transaction)) return result("rejected", "receipt_not_confirmed");
  if (transaction.meta?.err != null) return result("rejected", "transaction_failed");

  const owner = intent?.owner;
  const sourceMint = intent?.sourceMint;
  const destinationMint = intent?.destinationMint || intent?.mint;
  const expectedSource = toBigInt(intent?.sourceRawAmount);
  const expectedDestination = toBigInt(intent?.destinationRawAmount);
  const feeLamports = toBigInt(transaction.meta?.fee ?? transaction.feeLamports);
  if (!owner || !sourceMint || !destinationMint || expectedSource == null || expectedDestination == null || expectedSource <= 0n || expectedDestination <= 0n) {
    return result("rejected", "receipt_intent_incomplete", { feeLamports: feeLamports == null ? null : Number(feeLamports) });
  }
  if (feeLamports == null || feeLamports < 0n || feeLamports > BigInt(Number.MAX_SAFE_INTEGER)) {
    return result("effect_unknown", "fee_unknown", { evidence: { signature: transaction.signature || null } });
  }

  const transactionDeltas = tokenDeltasFromTransaction(transaction, owner);
  const observedDeltas = balanceDeltas(beforeBalances, afterBalances, owner);
  if (!transactionDeltas || !observedDeltas) {
    return result("effect_unknown", "token_delta_unknown", { feeLamports: Number(feeLamports) });
  }
  const expected = new Map([[sourceMint, -expectedSource], [destinationMint, expectedDestination]]);
  const matches = (actual) => actual.size === expected.size
    && [...expected.entries()].every(([mint, delta]) => actual.get(mint) === delta);
  const evidence = {
    signature: transaction.signature || null,
    owner,
    sourceMint,
    destinationMint,
    expectedDeltas: mapToJson(expected),
    transactionDeltas: mapToJson(transactionDeltas),
    observedDeltas: mapToJson(observedDeltas),
  };
  if (!matches(transactionDeltas) || !matches(observedDeltas)) {
    return result("effect_unknown", "token_delta_mismatch", { feeLamports: Number(feeLamports), evidence });
  }
  return {
    ...result("verified", "confirmed_matching_swap", { feeLamports: Number(feeLamports), evidence }),
    netUsd: Number.isFinite(Number(intent.realizedNetUsd)) ? Number(intent.realizedNetUsd) : null,
  };
}

