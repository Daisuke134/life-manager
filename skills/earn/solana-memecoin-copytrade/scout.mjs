const DEFAULT_MAX_AGE_MS = 15 * 60 * 1000;
const DEFAULT_MIN_LIQUIDITY_USD = 1_000;
const DEFAULT_MAX_PRICE_IMPACT_PCT = 2;
const DEFAULT_MAX_PROVIDER_DEVIATION_PCT = 20;

function finiteNumber(value) {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

function amountFromBalance(row) {
  const raw = row?.uiTokenAmount?.amount;
  const decimals = row?.uiTokenAmount?.decimals;
  if (typeof raw !== "string" || !/^\d+$/.test(raw) || !Number.isInteger(decimals) || decimals < 0 || decimals > 30) {
    return null;
  }
  try {
    return { raw: BigInt(raw), decimals };
  } catch {
    return null;
  }
}

function addBalance(map, row, targetAddress) {
  if (!row || row.owner !== targetAddress || typeof row.mint !== "string" || row.mint.length === 0) return true;
  const amount = amountFromBalance(row);
  if (!amount) return false;
  const key = `${row.accountIndex ?? "?"}:${row.mint}`;
  const existing = map.get(key);
  if (existing && existing.decimals !== amount.decimals) return false;
  map.set(key, {
    mint: row.mint,
    decimals: amount.decimals,
    raw: (existing?.raw || 0n) + amount.raw,
  });
  return true;
}

function decimalAmount(raw, decimals) {
  const value = Number(raw) / (10 ** decimals);
  return Number.isFinite(value) ? value : null;
}

function rowLooksMalformed(row) {
  return !row || typeof row !== "object"
    || typeof row.signature !== "string" || !row.signature
    || !Number.isInteger(row.slot)
    || !Number.isFinite(row.blockTime)
    || !row.meta || typeof row.meta !== "object"
    || !Array.isArray(row.meta.preTokenBalances)
    || !Array.isArray(row.meta.postTokenBalances);
}

export function parseTargetTransactions(rpcRows, targetAddress) {
  if (!Array.isArray(rpcRows) || typeof targetAddress !== "string" || !targetAddress) return [];
  const events = [];
  for (const row of rpcRows) {
    if (rowLooksMalformed(row) || row.meta.err != null) continue;
    const balances = new Map();
    let valid = true;
    for (const balance of row.meta.preTokenBalances) valid &&= addBalance(balances, balance, targetAddress);
    for (const balance of row.meta.postTokenBalances) valid &&= addBalance(balances, balance, targetAddress);
    if (!valid) continue;

    const byMint = new Map();
    for (const item of balances.values()) {
      const existing = byMint.get(item.mint);
      if (existing && existing.decimals !== item.decimals) {
        valid = false;
        break;
      }
      byMint.set(item.mint, {
        mint: item.mint,
        decimals: item.decimals,
        preRaw: (existing?.preRaw || 0n) + 0n,
        postRaw: (existing?.postRaw || 0n) + 0n,
      });
    }
    if (!valid) continue;

    const pre = new Map();
    const post = new Map();
    for (const balance of row.meta.preTokenBalances) {
      if (balance?.owner !== targetAddress) continue;
      const amount = amountFromBalance(balance);
      if (!amount) { valid = false; break; }
      const item = pre.get(balance.mint) || { raw: 0n, decimals: amount.decimals };
      if (item.decimals !== amount.decimals) { valid = false; break; }
      item.raw += amount.raw;
      pre.set(balance.mint, item);
    }
    if (!valid) continue;
    for (const balance of row.meta.postTokenBalances) {
      if (balance?.owner !== targetAddress) continue;
      const amount = amountFromBalance(balance);
      if (!amount) { valid = false; break; }
      const item = post.get(balance.mint) || { raw: 0n, decimals: amount.decimals };
      if (item.decimals !== amount.decimals) { valid = false; break; }
      item.raw += amount.raw;
      post.set(balance.mint, item);
    }
    if (!valid) continue;

    const mintDeltas = new Map([...new Set([...pre.keys(), ...post.keys()])].map((mint) => {
      const preItem = pre.get(mint) || { raw: 0n, decimals: post.get(mint).decimals };
      const postItem = post.get(mint) || { raw: 0n, decimals: pre.get(mint).decimals };
      return [mint, {
        decimals: preItem.decimals,
        deltaRaw: postItem.raw - preItem.raw,
      }];
    }));
    const spent = [...mintDeltas.entries()].filter(([, item]) => item.deltaRaw < 0n);
    const received = [...mintDeltas.entries()].filter(([, item]) => item.deltaRaw > 0n);
    if (spent.length !== 1 || received.length !== 1 || spent[0][0] === received[0][0]) continue;
    const [sourceMint, sourceDelta] = spent[0];
    const [destinationMint, destinationDelta] = received[0];
    const sourceRawAmount = -sourceDelta.deltaRaw;
    const destinationRawAmount = destinationDelta.deltaRaw;
    const sourceAmount = decimalAmount(sourceRawAmount, sourceDelta.decimals);
    const destinationAmount = decimalAmount(destinationRawAmount, destinationDelta.decimals);
    if (!sourceAmount || !destinationAmount || sourceAmount <= 0 || destinationAmount <= 0) continue;

    events.push(Object.freeze({
      sourceSignature: row.signature,
      slot: row.slot,
      observedAtMs: row.blockTime * 1000,
      observedOwner: targetAddress,
      sourceMint,
      destinationMint,
      mint: destinationMint,
      sourceRawAmount: sourceRawAmount.toString(),
      destinationRawAmount: destinationRawAmount.toString(),
      sourceDecimals: sourceDelta.decimals,
      destinationDecimals: destinationDelta.decimals,
      sourceAmount,
      destinationAmount,
    }));
  }
  return events;
}

function evidence(reason, fields = {}) {
  return { ...fields, reason };
}

function errorReason(error, fallback) {
  return typeof error?.message === "string" && error.message ? error.message : fallback;
}

function unwrap(value) {
  return value?.data?.token || value?.data || value?.token || value;
}

function normalizeGmgn(value, mint) {
  const row = unwrap(value);
  const rowMint = row?.mint || row?.address || row?.tokenAddress;
  const priceUsd = finiteNumber(row?.priceUsd ?? row?.price_usd ?? row?.price);
  const liquidityUsd = finiteNumber(row?.liquidityUsd ?? row?.liquidity_usd ?? row?.liquidity?.usd ?? row?.liquidity);
  if (rowMint !== mint || priceUsd == null || priceUsd <= 0 || liquidityUsd == null || liquidityUsd <= 0) return null;
  return { mint, priceUsd, liquidityUsd };
}

function normalizeDex(value, mint) {
  const pairs = Array.isArray(value) ? value : value?.pairs;
  if (!Array.isArray(pairs)) return null;
  const pair = pairs.find((row) => row?.baseToken?.address === mint);
  if (!pair) return null;
  const priceUsd = finiteNumber(pair.priceUsd);
  const liquidityUsd = finiteNumber(pair.liquidity?.usd);
  if (priceUsd == null || priceUsd <= 0 || liquidityUsd == null || liquidityUsd <= 0) return null;
  return { mint, priceUsd, liquidityUsd, pairAddress: pair.pairAddress || null, dexId: pair.dexId || null };
}

function normalizeJupiter(value) {
  const row = value?.data?.quote || value?.quote || value;
  const outAmount = finiteNumber(row?.outAmount ?? row?.outputAmount);
  const priceImpactPct = finiteNumber(row?.priceImpactPct ?? row?.priceImpact);
  if (outAmount == null || outAmount <= 0 || priceImpactPct == null || priceImpactPct < 0) return null;
  return { outAmount, priceImpactPct };
}

function marketCandidate(event, gmgn, dex, jupiter, sourcePriceUsd, sourceAmountUsd) {
  return {
    ...event,
    sourcePriceUsd,
    sourceAmountUsd,
    market: { gmgn, dexscreener: dex, jupiter },
    evidenceIds: [event.sourceSignature, `gmgn:${event.destinationMint}`, `dex:${event.destinationMint}`],
  };
}

export async function scout(targets, adapters, nowMs = Date.now(), options = {}) {
  const evidenceRows = [];
  const candidates = [];
  const seenSignatures = new Set();
  let hardUnknown = false;
  const maxAgeMs = options.maxAgeMs ?? DEFAULT_MAX_AGE_MS;
  const minLiquidityUsd = options.minLiquidityUsd ?? DEFAULT_MIN_LIQUIDITY_USD;
  const maxPriceImpactPct = options.maxPriceImpactPct ?? DEFAULT_MAX_PRICE_IMPACT_PCT;
  const maxProviderDeviationPct = options.maxProviderDeviationPct ?? DEFAULT_MAX_PROVIDER_DEVIATION_PCT;

  if (!Array.isArray(targets) || !adapters?.rpc || !adapters?.gmgn || !adapters?.dexscreener || !adapters?.jupiter) {
    return { status: "scout_unknown", candidates: [], evidence: [evidence("adapters_invalid")] };
  }

  for (const target of targets) {
    if (!target || typeof target.address !== "string" || !target.address) {
      evidenceRows.push(evidence("target_invalid"));
      hardUnknown = true;
      continue;
    }
    let summaries;
    try {
      summaries = await adapters.rpc.getSignatures(target.address);
    } catch (error) {
      evidenceRows.push(evidence("rpc_signatures_unavailable", { target: target.address, detail: errorReason(error, "rpc_error") }));
      hardUnknown = true;
      continue;
    }
    if (!Array.isArray(summaries)) {
      evidenceRows.push(evidence("rpc_signatures_malformed", { target: target.address }));
      hardUnknown = true;
      continue;
    }

    for (const summary of summaries) {
      const signature = summary?.signature;
      if (typeof signature !== "string" || !signature) {
        evidenceRows.push(evidence("rpc_signature_malformed", { target: target.address }));
        hardUnknown = true;
        continue;
      }
      if (seenSignatures.has(signature)) {
        evidenceRows.push(evidence("source_signature_duplicate", { sourceSignature: signature }));
        hardUnknown = true;
        continue;
      }
      seenSignatures.add(signature);

      let row;
      try {
        row = await adapters.rpc.getTransaction(signature);
      } catch (error) {
        evidenceRows.push(evidence("rpc_transaction_unavailable", { sourceSignature: signature, detail: errorReason(error, "rpc_error") }));
        hardUnknown = true;
        continue;
      }
      if (row && typeof row === "object" && !row.signature) row = { ...row, signature };
      if (rowLooksMalformed(row)) {
        evidenceRows.push(evidence("rpc_transaction_malformed", { sourceSignature: signature }));
        hardUnknown = true;
        continue;
      }
      if (row.meta.err != null) {
        evidenceRows.push(evidence("source_transaction_failed", { sourceSignature: signature }));
        continue;
      }
      const [event] = parseTargetTransactions([row], target.address);
      if (!event) {
        evidenceRows.push(evidence("source_event_not_swap", { sourceSignature: signature, target: target.address }));
        continue;
      }
      const ageMs = nowMs - event.observedAtMs;
      if (!Number.isFinite(ageMs) || ageMs < 0) {
        evidenceRows.push(evidence("source_event_time_invalid", { sourceSignature: signature }));
        hardUnknown = true;
        continue;
      }
      if (ageMs > maxAgeMs) {
        evidenceRows.push(evidence("source_event_stale", { sourceSignature: signature, ageMs }));
        continue;
      }

      let gmgnRaw;
      let dexRaw;
      let sourceDexRaw;
      let jupiterRaw;
      try {
        gmgnRaw = await adapters.gmgn.readToken(event.destinationMint);
        dexRaw = await adapters.dexscreener.readPairs(event.destinationMint);
        sourceDexRaw = event.sourceMint === event.destinationMint
          ? dexRaw
          : await adapters.dexscreener.readPairs(event.sourceMint);
        jupiterRaw = await adapters.jupiter.quote(event);
      } catch (error) {
        evidenceRows.push(evidence("market_provider_unavailable", { sourceSignature: signature, detail: errorReason(error, "provider_error") }));
        hardUnknown = true;
        continue;
      }
      const gmgn = normalizeGmgn(gmgnRaw, event.destinationMint);
      const dex = normalizeDex(dexRaw, event.destinationMint);
      const sourceDex = normalizeDex(sourceDexRaw, event.sourceMint);
      const jupiter = normalizeJupiter(jupiterRaw);
      if (!gmgn || !dex || !sourceDex) {
        evidenceRows.push(evidence("market_provider_missing", { sourceSignature: signature, mint: event.destinationMint }));
        hardUnknown = true;
        continue;
      }
      const sourceAmountUsd = event.sourceAmount * sourceDex.priceUsd;
      if (!Number.isFinite(sourceAmountUsd) || sourceAmountUsd <= 0) {
        evidenceRows.push(evidence("source_amount_value_unknown", { sourceSignature: signature, mint: event.sourceMint }));
        hardUnknown = true;
        continue;
      }
      const midpoint = (gmgn.priceUsd + dex.priceUsd) / 2;
      const deviationPct = Math.abs(gmgn.priceUsd - dex.priceUsd) / midpoint * 100;
      if (!Number.isFinite(deviationPct) || deviationPct > maxProviderDeviationPct) {
        evidenceRows.push(evidence("market_provider_disagreement", { sourceSignature: signature, mint: event.destinationMint }));
        hardUnknown = true;
        continue;
      }
      if (!jupiter || gmgn.liquidityUsd < minLiquidityUsd || dex.liquidityUsd < minLiquidityUsd || jupiter.priceImpactPct > maxPriceImpactPct) {
        evidenceRows.push(evidence("quote_or_liquidity_invalid", { sourceSignature: signature, mint: event.destinationMint }));
        hardUnknown = true;
        continue;
      }
      candidates.push(marketCandidate(event, gmgn, dex, jupiter, sourceDex.priceUsd, sourceAmountUsd));
      evidenceRows.push(evidence("candidate_market_confirmed", {
        sourceSignature: signature,
        mint: event.destinationMint,
        evidenceIds: candidates.at(-1).evidenceIds,
      }));
    }
  }

  return {
    status: hardUnknown ? "scout_unknown" : "ok",
    candidates: hardUnknown ? [] : candidates,
    evidence: evidenceRows,
  };
}
