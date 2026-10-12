// treasury-policy.mjs — pure money-safety policy shared by future signers and compute adapters.
import { isNormalizedRevenueReceipt } from "./revenue-receipt.mjs";

const GRADUATION_MULTIPLIER = 1.5;
const MIN_RUNWAY_DAYS = 30;
const finite = (value) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
const round = (value) => Math.round(Number(value) * 1e6) / 1e6;
const SETTLED = new Set(["settled", "paid", "received", "completed"]);
const NEGATIVE_TERMINAL = new Set(["refunded", "charged_back", "chargeback", "reversed"]);

/** Liquid funds that may be spent after reserve and already-committed liabilities. */
export function computeSpendable({ liquidUsdc, reserveUsdc, committedUsdc = 0 } = {}) {
  if (!finite(liquidUsdc) || !finite(reserveUsdc) || !finite(committedUsdc)) return 0;
  if (Number(liquidUsdc) < 0 || Number(reserveUsdc) < 0 || Number(committedUsdc) < 0) return 0;
  return round(Math.max(0, Number(liquidUsdc) - Number(reserveUsdc) - Number(committedUsdc)));
}

/** Authorize one proposed spend without signing or broadcasting it. */
export function authorizeSpend({
  amountUsdc,
  liquidUsdc,
  reserveUsdc,
  committedUsdc = 0,
  sessionSpentUsdc = 0,
  sessionCapUsdc,
} = {}) {
  if (!finite(amountUsdc) || Number(amountUsdc) <= 0
    || !finite(liquidUsdc) || Number(liquidUsdc) < 0
    || !finite(reserveUsdc) || Number(reserveUsdc) < 0
    || !finite(committedUsdc) || Number(committedUsdc) < 0
    || !finite(sessionSpentUsdc) || Number(sessionSpentUsdc) < 0
    || !finite(sessionCapUsdc) || Number(sessionCapUsdc) <= 0) {
    return { allowed: false, reason: "invalid-input" };
  }
  const spendableUsdc = computeSpendable({ liquidUsdc, reserveUsdc, committedUsdc });
  const sessionRemainingUsdc = round(Number(sessionCapUsdc) - Number(sessionSpentUsdc));
  if (Number(amountUsdc) > spendableUsdc + Number.EPSILON) {
    return { allowed: false, reason: "reserve-floor", spendableUsdc, sessionRemainingUsdc };
  }
  if (Number(amountUsdc) > sessionRemainingUsdc + Number.EPSILON) {
    return { allowed: false, reason: "session-cap", spendableUsdc, sessionRemainingUsdc };
  }
  return {
    allowed: true,
    reason: "ok",
    spendableUsdc,
    sessionRemainingUsdc: round(sessionRemainingUsdc - Number(amountUsdc)),
  };
}

/** Authorize from selected, independently verified outside revenue only. */
export function authorizeEarnedSpend({
  amountUsdc,
  fundingReceiptIds,
  revenueReceipts,
  recipient,
  fundingSpentUsdc = 0,
  reserveUsdc = 0,
  sessionSpentUsdc = 0,
  sessionCapUsdc,
} = {}) {
  if (!Array.isArray(fundingReceiptIds) || fundingReceiptIds.length === 0
    || !Array.isArray(revenueReceipts) || typeof recipient !== "string" || !recipient
    || !finite(fundingSpentUsdc) || Number(fundingSpentUsdc) < 0) {
    return { allowed: false, reason: "invalid-funding-provenance" };
  }
  const selected = new Map();
  for (const row of revenueReceipts) {
    const id = row?.receipt_id || row?.idempotency_key;
    if (typeof id === "string" && fundingReceiptIds.includes(id)) selected.set(id, row);
  }
  if (selected.size !== new Set(fundingReceiptIds).size) {
    return { allowed: false, reason: "invalid-funding-provenance" };
  }
  let earnedUsdc = 0;
  for (const id of new Set(fundingReceiptIds)) {
    const row = selected.get(id);
    if (!isNormalizedRevenueReceipt(row)
      || String(row.recipient).toLowerCase() !== recipient.toLowerCase()
      || String(row.payer).toLowerCase() === recipient.toLowerCase()
      || row.asset !== "USDC" || row.proof?.chain_id !== 8453
      || row.proof?.verified !== true
      || !SETTLED.has(String(row.terminal_state || "").toLowerCase())
      || !finite(row.signed_net) || Number(row.signed_net) <= 0) {
      return { allowed: false, reason: "invalid-funding-provenance" };
    }
    earnedUsdc += Number(row.signed_net);
  }
  // A later refund/chargeback has its own immutable proof and therefore its own
  // receipt id.  Funding selectors name the positive provenance, but they must
  // never act as a revocation allowlist: every verified negative correction for
  // this resident reduces the currently earned balance before any signature.
  const selectedIds = new Set(fundingReceiptIds);
  for (const row of revenueReceipts) {
    if (!finite(row?.signed_net) || Number(row.signed_net) >= 0) continue;
    const id = row?.receipt_id || row?.idempotency_key;
    if (typeof id !== "string" || selectedIds.has(id)
      || !isNormalizedRevenueReceipt(row)
      || String(row.recipient).toLowerCase() !== recipient.toLowerCase()
      || String(row.payer).toLowerCase() === recipient.toLowerCase()
      || row.asset !== "USDC" || row.proof?.chain_id !== 8453
      || row.proof?.verified !== true
      || !NEGATIVE_TERMINAL.has(String(row.terminal_state || "").toLowerCase())) {
      return { allowed: false, reason: "invalid-funding-provenance" };
    }
    earnedUsdc += Number(row.signed_net);
  }
  earnedUsdc = round(earnedUsdc);
  const result = authorizeSpend({
    amountUsdc, liquidUsdc: earnedUsdc, reserveUsdc, committedUsdc: fundingSpentUsdc,
    sessionSpentUsdc, sessionCapUsdc,
  });
  return { ...result, earnedUsdc, fundingSpentUsdc: round(fundingSpentUsdc), fundingReceiptIds: [...new Set(fundingReceiptIds)] };
}

/** Proposed graduation gate: external net covers compute+shelter with margin and no human fuel. */
export function graduationGate({
  externalRealizedNet30d,
  computeCost30d,
  shelterCost30d,
  liquidRunwayDays,
  humanPaidInference30d,
} = {}) {
  if (!finite(externalRealizedNet30d) || !finite(computeCost30d) || !finite(shelterCost30d)
    || !finite(liquidRunwayDays) || !finite(humanPaidInference30d)
    || Number(externalRealizedNet30d) < 0 || Number(computeCost30d) < 0
    || Number(shelterCost30d) < 0 || Number(liquidRunwayDays) < 0
    || Number(humanPaidInference30d) < 0) {
    return { eligible: false, reason: "invalid-input", coverage: null };
  }
  if (Number(humanPaidInference30d) > 0) {
    return { eligible: false, reason: "human-paid-inference", coverage: null };
  }
  const totalCost = Number(computeCost30d) + Number(shelterCost30d);
  if (totalCost <= 0) return { eligible: false, reason: "insufficient-cost-data", coverage: null };
  const coverage = round(Number(externalRealizedNet30d) / totalCost);
  if (Number(liquidRunwayDays) < MIN_RUNWAY_DAYS) {
    return { eligible: false, reason: "insufficient-runway", coverage };
  }
  if (coverage < GRADUATION_MULTIPLIER) {
    return { eligible: false, reason: "insufficient-coverage", coverage };
  }
  return { eligible: true, reason: "ok", coverage };
}
