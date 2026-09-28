// verify-inflow.mjs — on-chain source of truth for "did an EXTERNAL buyer actually pay us?"
// Scans Base USDC Transfer logs to X402_PAYTO and splits them into self-pay (our own wallets,
// INV-7: never counted as revenue) vs external (real earnings). No API key: public Base RPC.
//   node verify-inflow.mjs [hoursBack=48]
import { SELF_WALLETS } from "./lib/self-wallets.mjs";
import { BASE_LOG_CHUNK_SIZE, chunkBlockRanges } from "./lib/rpc-log-range.mjs";

const USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const PAY_TO = (process.env.X402_PAYTO || "0x810f6d61f7606deee2657d3083e150a222bc29c5").toLowerCase();
// every wallet we control on any instance — a payment from any of these is NOT revenue (INV-7).
// The list itself now lives in lib/self-wallets.mjs (SELF-STORE-1, 2026-07-18) so store-review.mjs
// shares the exact same set instead of drifting its own copy; PAY_TO is added defensively in case
// an X402_PAYTO override isn't already in that list. Must stay a superset of
// founder-loop/record-earn.mjs's SHARED list: an address any judge in the colony calls internal
// has to be internal in EVERY judge, or we overstate what we earned.
// (__tests__/verify-inflow-wallets.test.mjs pins that agreement against lib/self-wallets.mjs.)
const OUR_WALLETS = new Set([PAY_TO, ...SELF_WALLETS]);
const RPC = process.env.X402_RPC_URL || "https://mainnet.base.org";
const HOURS = Number(process.argv[2] || 48);
const BLOCKS_PER_HOUR = 1800; // Base: 2s block time

async function rpc(method, params) {
  const r = await fetch(RPC, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    signal: AbortSignal.timeout(30_000),
  });
  const j = await r.json();
  if (j.error) throw new Error(`${method}: ${JSON.stringify(j.error)}`);
  return j.result;
}

const latest = parseInt(await rpc("eth_blockNumber", []), 16);
const fromBlock = latest - HOURS * BLOCKS_PER_HOUR;
const toTopic = "0x" + PAY_TO.slice(2).padStart(64, "0");
const CHUNK = BASE_LOG_CHUNK_SIZE;
const logs = [];
for (const [start, end] of chunkBlockRanges(fromBlock, latest, CHUNK)) {
  logs.push(...await rpc("eth_getLogs", [{
    address: USDC, fromBlock: "0x" + start.toString(16), toBlock: "0x" + end.toString(16),
    topics: [TRANSFER_TOPIC, null, toTopic],
  }]));
}

const rows = logs.map((l) => ({
  tx: l.transactionHash,
  block: parseInt(l.blockNumber, 16),
  from: "0x" + l.topics[1].slice(26),
  usdc: Number(BigInt(l.data)) / 1e6,
})).map((r) => ({ ...r, external: !OUR_WALLETS.has(r.from.toLowerCase()) }));

// 2026-07-18 harsh audit: "log sender not ours" is NOT sufficient for external. When WE call a
// DeFi protocol, the pool contract sends our own funds back and the Transfer's `from` is the pool
// (measured: claude-p's $0.315362 Aave v3 withdraw + $0.315114 Uniswap swap output were counted
// as "external revenue" and inflated lifetime x402 earnings from ~$0.011 to $0.326). A protocol
// return is self-initiated: the enclosing TRANSACTION's from is one of OUR wallets. Reclassify.
for (const r of rows) {
  if (!r.external) continue;
  const tx = await rpc("eth_getTransactionByHash", [r.tx]);
  if (tx && OUR_WALLETS.has(String(tx.from).toLowerCase())) {
    r.external = false;
    r.protocolReturn = true; // our own funds coming back from a pool/router we called
  }
}

const ext = rows.filter((r) => r.external);
const sum = (a) => Math.round(a.reduce((s, r) => s + r.usdc, 0) * 1e6) / 1e6;
console.log(JSON.stringify({
  payTo: PAY_TO, hoursBack: HOURS, scannedBlocks: [fromBlock, latest],
  inflows: rows.length, selfPay: rows.length - ext.length, selfPayUsdc: sum(rows.filter((r) => !r.external)),
  EXTERNAL: ext.length, externalUsdc: sum(ext),
}, null, 2));
for (const r of ext) console.log("EXTERNAL-TX:", JSON.stringify(r));
