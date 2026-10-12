#!/usr/bin/env node
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

import { SELF_WALLETS } from './lib/self-wallets.mjs';
import {
  appendUniqueExternalInflows,
  collectVerifiedSaleCandidates,
  walletLedgerPath,
} from './lib/external-inflow-recorder.mjs';
import { resolveX402StateDir } from './state-paths.mjs';
import { projectRevenueReceipts } from '../../agent-economy/lib/revenue-adapters.mjs';
import { resolveStatusPaths } from '../../agent-economy/status.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const OWN_PAY_TOS = [
  '0x3EcCAD24794ca298D25378E9902A251322ea8749',
  '0xe7747Fd899D8987821Bb4CB3D6aDf22565F87ce9',
  '0x810F6D61F7606dEEE2657d3083E150a222Bc29C5',
  '0x6592EB8EF820aBC092e8C3474fb2042dffCCEDc7',
].map((wallet) => wallet.toLowerCase());

function readCandidates(path) {
  if (!existsSync(path)) return [];
  return readFileSync(path, 'utf8').split('\n').filter(Boolean).flatMap((line) => {
    try { return [JSON.parse(line)]; } catch { return []; }
  });
}

async function rpcCall(method, params) {
  const response = await fetch('https://mainnet.base.org', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
    signal: AbortSignal.timeout(30_000),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.error || body?.result === undefined) throw new Error('Base RPC failure');
  return body.result;
}

function toAgentEconomyRevenueRow(row) {
  return {
    source_record_id: row.source_sale_id,
    provider: 'x402',
    settled: row.status === 'success' && row.finalized === true,
    amount_atomic: row.usdc_atomic,
    decimals: 6,
    asset: 'USDC',
    payer: row.from,
    recipient: row.payTo,
    transaction: row.tx,
    chain_id: 8453,
    network: 'eip155:8453',
    terminal_state: row.status === 'success' && row.finalized === true ? 'settled' : row.status,
    occurred_at: row.observed_at,
    ...(row.fee !== undefined && row.fee !== null ? { fee: row.fee } : {}),
    ...(row.refund !== undefined && row.refund !== null ? { refund: row.refund } : {}),
  };
}

async function projectAgentEconomyRevenue(rows, { journalPath, rejectionPath } = {}) {
  if (rows.length === 0) return null;
  const resolvedJournal = journalPath || resolveStatusPaths({ env: process.env }).journalPath;
  const result = await projectRevenueReceipts({
    journalPath: resolvedJournal,
    rejectionPath: rejectionPath || `${resolvedJournal}.rejections.jsonl`,
    provider: 'x402',
    rows: rows.map(toAgentEconomyRevenueRow),
    options: { configuredNetwork: 'eip155:8453' },
  });
  return {
    accepted: result.accepted,
    duplicates: result.duplicates,
    rejected: result.rejected,
    rejection_persisted: result.rejection_persisted,
    rejection_duplicates: result.rejection_duplicates,
  };
}

export async function recordSaleCandidates({
  candidates,
  rpc = rpcCall,
  stateDir = resolveX402StateDir(),
  revenueJournalPath,
  revenueRejectionPath,
} = {}) {
  if (!Array.isArray(candidates) || candidates.length === 0) {
    return {
      chain_id: null,
      finalized_block: null,
      candidates_seen: 0,
      verified: 0,
      recorded: 0,
      duplicates: 0,
      revenue_projection: null,
    };
  }
  const verified = await collectVerifiedSaleCandidates({
    candidates,
    rpcCall: rpc,
    selfWallets: SELF_WALLETS,
    allowedPayTos: OWN_PAY_TOS,
  });
  let recorded = 0;
  let duplicates = 0;
  for (const payTo of OWN_PAY_TOS) {
    const rows = verified.rows.filter((row) => row.payTo === payTo);
    if (rows.length === 0) continue;
    const write = appendUniqueExternalInflows(walletLedgerPath(payTo, { stateDir }), rows);
    recorded += write.recorded;
    duplicates += write.duplicates;
  }
  const revenueProjection = await projectAgentEconomyRevenue(verified.rows, {
    journalPath: revenueJournalPath,
    rejectionPath: revenueRejectionPath,
  });
  return {
    chain_id: verified.chainId,
    finalized_block: verified.finalizedBlock,
    candidates_seen: candidates.length,
    verified: verified.rows.length,
    recorded,
    duplicates,
    revenue_projection: revenueProjection,
  };
}

async function main() {
  const stateDir = resolveX402StateDir();
  const candidatePath = join(stateDir, 'x402-sale-candidates.jsonl');
  const result = await recordSaleCandidates({ candidates: readCandidates(candidatePath), stateDir });
  const isRevenue = result.recorded > 0;
  process.stdout.write(`${JSON.stringify({
    observed_at: new Date().toISOString(),
    ...result,
    verified_external_revenue: isRevenue,
    agent_economy_revenue_accepted: result.revenue_projection?.accepted ?? 0,
  })}\n`);
  if (isRevenue) {
    spawnSync('/usr/bin/osascript', ['-e', 'display notification "Finalized external USDC sale recorded." with title "x402 verified revenue" sound name "Glass"'], {
      stdio: 'ignore',
      timeout: 5_000,
    });
  }
}

const isEntry = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isEntry) {
  main().catch(() => {
    process.stderr.write('{"ok":false,"error":"settlement_recorder_failed"}\n');
    process.exitCode = 1;
  });
}
