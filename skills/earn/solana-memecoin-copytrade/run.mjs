import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

import { append, readRows } from "./journal.mjs";
import { executeCanary } from "./execute.mjs";
import { createLiveClients, createPublicAdapters } from "./sources.mjs";
import { scout } from "./scout.mjs";
import { decide } from "./policy.mjs";
import { paperApply } from "./paper.mjs";
import { loadOrCreateAgentWallet, readTargets } from "./wallet.mjs";

const VALID_MODES = new Set(["read_only", "paper", "live"]);
const EXIT_ACTIONS = new Set(["mirror_exit", "stop_exit", "time_exit"]);

function dayUtc(nowMs) {
  return new Date(nowMs).toISOString().slice(0, 10);
}

function makeIntent(mode, liveGate, candidate, decision, quote, nowMs, owner) {
  const destinationMint = candidate.destinationMint || decision.mint;
  return {
    intentId: `${mode}-${candidate.sourceSignature}`,
    mode,
    liveGate,
    action: decision.action,
    owner: owner || candidate.observedOwner || null,
    targetAddress: candidate.observedOwner || null,
    mint: destinationMint,
    sourceMint: candidate.sourceMint,
    destinationMint,
    sourceRawAmount: candidate.sourceRawAmount,
    destinationRawAmount: String(quote.outAmount ?? quote.outputAmount ?? candidate.destinationRawAmount ?? ""),
    amountUsd: decision.amountUsd,
    sourceSignature: candidate.sourceSignature,
    createdAtMs: nowMs,
  };
}

function positionFromRows(rows) {
  for (const row of [...rows].reverse()) {
    if (row.kind !== "receipt" || row.status !== "paper") continue;
    if (row.action === "copy_entry" && row.position) return row.position;
    if (EXIT_ACTIONS.has(row.action)) return null;
  }
  return null;
}

function makeExitIntent(mode, liveGate, position, decision, quote, nowMs, owner) {
  return {
    intentId: `${mode}-${decision.sourceSignature}`,
    mode,
    liveGate,
    action: decision.action,
    owner: owner || null,
    mint: position.mint,
    sourceMint: position.mint,
    destinationMint: position.exitMint || quote?.outputMint || null,
    sourceRawAmount: position.amountRaw,
    destinationRawAmount: String(quote?.outAmount ?? quote?.outputAmount ?? ""),
    amountUsd: decision.amountUsd,
    sourceSignature: decision.sourceSignature,
    createdAtMs: nowMs,
    position,
  };
}

function defaultExitQuote(position, exitSnapshot = {}) {
  const quote = exitSnapshot.quote || {};
  return {
    inputMint: position.mint,
    outputMint: position.exitMint,
    inAmount: position.amountRaw,
    outAmount: String(quote.outAmount ?? quote.outputAmount ?? ""),
    priceImpactPct: quote.priceImpactPct,
    simulatedFeeUsd: quote.simulatedFeeUsd,
    simulatedSlippageUsd: quote.simulatedSlippageUsd,
  };
}

function defaultQuote(candidate) {
  const market = candidate.market?.jupiter || {};
  return {
    inputMint: candidate.sourceMint,
    outputMint: candidate.destinationMint,
    inAmount: candidate.sourceRawAmount,
    outAmount: String(candidate.destinationRawAmount || market.outAmount || market.outputAmount || ""),
    priceImpactPct: market.priceImpactPct,
    priceUsd: market.priceUsd ?? candidate.market?.gmgn?.priceUsd ?? candidate.market?.dexscreener?.priceUsd,
    simulatedFeeUsd: null,
    simulatedSlippageUsd: null,
  };
}

async function dailyReport(journalPath, nowMs, fields) {
  const utcDate = dayUtc(nowMs);
  const rows = await readRows(journalPath);
  const existing = rows.find((row) => row.kind === "daily_report" && row.utcDate === utcDate);
  if (existing) return { ...existing, alreadyPresent: true };
  return append(journalPath, { kind: "daily_report", utcDate, ...fields });
}

async function persistEffectUnknownFence(journalPath, intent, receipt) {
  const rows = await readRows(journalPath);
  if (rows.some((row) => row.kind === "receipt" && row.intentId === intent.intentId && row.status === "effect_unknown")) return;
  await append(journalPath, {
    kind: "receipt",
    intentId: intent.intentId,
    sourceSignature: intent.sourceSignature,
    status: "effect_unknown",
    effect: "unknown",
    verified: false,
    reason: receipt?.reason || "live_effect_unknown",
    retry: false,
  });
}

async function report(journalPath, nowMs, mode, decision, receipt, candidateCount) {
  return dailyReport(journalPath, nowMs, {
    stage: mode,
    decision: decision?.action || "halt",
    reason: decision?.reason || null,
    candidateCount,
    receiptStatus: receipt?.status || null,
  });
}

export async function wake({ mode = "read_only", liveGate = false, targets = [], clients = {}, journalPath, nowMs = Date.now() }) {
  if (!journalPath) throw new Error("journal_path_required");
  if (!VALID_MODES.has(mode)) {
    const decision = { action: "halt", reason: "mode_invalid", sourceSignature: null, mint: null, amountUsd: 0 };
    return { stage: "halted", decision, receipt: null, report: await report(journalPath, nowMs, "halted", decision, null, 0) };
  }

  const rows = await readRows(journalPath);
  const terminalUnknown = [...rows].reverse().find((row) => row.kind === "receipt" && row.status === "effect_unknown");
  if (terminalUnknown) {
    const decision = { action: "halt", reason: "effect_unknown_fence", sourceSignature: terminalUnknown.sourceSignature || null, mint: terminalUnknown.mint || null, amountUsd: 0 };
    return { stage: "fenced", decision, receipt: terminalUnknown, report: await report(journalPath, nowMs, "fenced", decision, terminalUnknown, 0) };
  }

  if (mode === "live" && liveGate !== true) {
    const decision = { action: "halt", reason: "live_gate_missing", sourceSignature: null, mint: null, amountUsd: 0 };
    return { stage: mode, decision, receipt: null, report: await report(journalPath, nowMs, mode, decision, null, 0) };
  }

  const scoutFn = clients.scout
    ? clients.scout
    : (candidateTargets, _nowMs) => scout(candidateTargets, clients.adapters, _nowMs, clients.scoutOptions);
  const scoutResult = await scoutFn(targets, nowMs);
  if (mode === "read_only") {
    const decision = scoutResult?.status === "scout_unknown"
      ? { action: "halt", reason: "scout_unknown", sourceSignature: null, mint: null, amountUsd: 0 }
      : { action: "observe", reason: "read_only_scout", sourceSignature: null, mint: null, amountUsd: 0 };
    return {
      stage: mode,
      decision,
      receipt: null,
      report: await report(journalPath, nowMs, mode, decision, null, scoutResult?.candidates?.length || 0),
    };
  }

  if (!scoutResult || scoutResult.status !== "ok") {
    const decision = { action: "halt", reason: "scout_unknown", sourceSignature: null, mint: null, amountUsd: 0 };
    return { stage: mode, decision, receipt: null, report: await report(journalPath, nowMs, mode, decision, null, 0) };
  }

  const position = typeof clients.position === "function"
    ? await clients.position(rows, nowMs)
    : clients.position || positionFromRows(rows);
  if (position) {
    const suppliedExitSnapshot = typeof clients.exitSnapshot === "function"
      ? await clients.exitSnapshot(position, scoutResult, nowMs)
      : clients.exitSnapshot || scoutResult.exitSnapshot || {};
    const exitSnapshot = suppliedExitSnapshot && typeof suppliedExitSnapshot === "object"
      ? suppliedExitSnapshot
      : {};
    const exitRisk = typeof clients.risk === "function"
      ? await clients.risk(position, nowMs)
      : { nowMs, ...(clients.risk || {}) };
    const decideFn = clients.decide || decide;
    const exitDecision = await decideFn({ ...exitSnapshot, position, nowMs }, exitRisk);
    if (!EXIT_ACTIONS.has(exitDecision.action)) {
      return {
        stage: mode,
        decision: exitDecision,
        receipt: null,
        report: await report(journalPath, nowMs, mode, exitDecision, null, scoutResult.candidates?.length || 0),
      };
    }
    if (mode === "live") {
      const receipt = {
        kind: "receipt",
        status: "rejected",
        effect: "none",
        verified: false,
        reason: "live_exit_closed",
        retry: false,
        intentId: null,
        sourceSignature: exitDecision.sourceSignature || null,
      };
      return {
        stage: mode,
        decision: exitDecision,
        receipt,
        report: await report(journalPath, nowMs, mode, exitDecision, receipt, scoutResult.candidates?.length || 0),
      };
    }

    const quote = clients.exitQuoteFor
      ? await clients.exitQuoteFor(position, exitDecision, exitSnapshot)
      : defaultExitQuote(position, exitSnapshot);
    const owner = clients.wallet?.publicKey || null;
    const intent = makeExitIntent(mode, liveGate, position, exitDecision, quote, nowMs, owner);
    const paperFn = clients.paperApply || paperApply;
    const receipt = await paperFn(intent, quote, journalPath);
    return {
      stage: mode,
      decision: exitDecision,
      receipt,
      report: await report(journalPath, nowMs, mode, exitDecision, receipt, scoutResult.candidates?.length || 0),
    };
  }

  const candidate = scoutResult.candidates?.[0];
  if (!candidate) {
    const decision = { action: "skip", reason: "no_candidate", sourceSignature: null, mint: null, amountUsd: 0 };
    return { stage: mode, decision, receipt: null, report: await report(journalPath, nowMs, mode, decision, null, 0) };
  }

  const risk = typeof clients.risk === "function"
    ? await clients.risk(candidate, nowMs)
    : { nowMs, ...(clients.risk || {}) };
  const decideFn = clients.decide || decide;
  const decision = await decideFn(candidate, risk);
  if (decision.action !== "copy_entry") {
    return { stage: mode, decision, receipt: null, report: await report(journalPath, nowMs, mode, decision, null, 1) };
  }

  const quote = clients.quoteFor ? await clients.quoteFor(candidate, mode) : defaultQuote(candidate);
  const owner = clients.wallet?.publicKey || candidate.observedOwner || null;
  const intent = makeIntent(mode, liveGate, candidate, decision, quote, nowMs, owner);
  let receipt;
  if (mode === "paper") {
    const paperFn = clients.paperApply || paperApply;
    receipt = await paperFn(intent, quote, journalPath);
  } else {
    const executeFn = clients.executeCanary || executeCanary;
    receipt = await executeFn(intent, quote, clients.wallet, clients, journalPath);
    if (receipt?.status === "effect_unknown") await persistEffectUnknownFence(journalPath, intent, receipt);
  }
  return {
    stage: mode,
    decision,
    receipt,
    report: await report(journalPath, nowMs, mode, decision, receipt, 1),
  };
}

export async function main() {
  const mode = process.env.SOL_COPY_MODE || "read_only";
  const targetsPath = process.env.SOL_COPY_TARGETS_FILE;
  if (!targetsPath) throw new Error("SOL_COPY_TARGETS_FILE_required");
  const targets = await readTargets(targetsPath);
  const journalPath = process.env.SOL_COPY_JOURNAL
    || path.join(os.homedir(), ".local", "state", "anicca", "solana-memecoin-copytrade", "journal.jsonl");
  const adapters = createPublicAdapters();
  const wallet = mode === "live" ? await loadOrCreateAgentWallet() : null;
  const executionClients = mode === "live" ? await createLiveClients({ adapters, wallet }) : {};
  const quoteFor = async (candidate) => {
    if (mode !== "live") return defaultQuote(candidate);
    const quote = await adapters.jupiter.quote(candidate);
    return {
      ...quote,
      inputMint: quote.inputMint || candidate.sourceMint,
      outputMint: quote.outputMint || candidate.destinationMint,
      inAmount: quote.inAmount || candidate.sourceRawAmount,
      outAmount: quote.outAmount || quote.outputAmount,
    };
  };
  const liveRisk = mode === "live" ? async (_candidate, wakeNowMs) => {
    const asInteger = (value, fallback) => Number.isSafeInteger(Number(value)) && Number(value) >= 0 ? Number(value) : fallback;
    return {
      nowMs: wakeNowMs,
      solBalanceLamports: await adapters.rpc.getBalance(wallet.publicKey),
      minSolReserveLamports: asInteger(process.env.SOL_COPY_MIN_SOL_RESERVE_LAMPORTS, 10_000_000),
      estimatedFeeLamports: asInteger(process.env.SOL_COPY_ESTIMATED_FEE_LAMPORTS, 100_000),
      cumulativeCanaryUsd: 0,
      maxSourceAgeMs: 15 * 60 * 1000,
      maxQuoteAgeMs: 30_000,
      minLiquidityUsd: 1_000,
      maxPriceImpactPct: 2,
    };
  } : undefined;
  const result = await wake({
    mode,
    liveGate: process.env.SOL_COPY_LIVE === "1",
    targets,
    clients: { ...executionClients, adapters, wallet, quoteFor, risk: liveRisk },
    journalPath,
    nowMs: Date.now(),
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
  return result;
}

const entrypoint = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : null;
if (entrypoint && import.meta.url === entrypoint) {
  main().catch((error) => {
    process.stderr.write(`${error?.message || "run_failed"}\n`);
    process.exitCode = 1;
  });
}
