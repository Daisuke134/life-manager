/**
 * self-eval.mjs — Pure: selfEval(earnLedgerLines, opts) → { bySlot, steer }
 *
 * THE SELF-IMPROVEMENT SIGNAL (spec §10 H2). The loop already shows the AI its recent ACTION history
 * and over-use counts, but NOT the realised P&L per action — so the AI cannot see that "hl-close ETH"
 * has returned $0 twelve times and is a DEAD action. This reads the earn ledger (the outcome trace, H1)
 * and produces a per-action money verdict the prompt injects (H3), letting the AI judge for itself
 * (no hardcoded "stop hl_trade" rule — we give it the data, it decides). Pure: no I/O.
 *
 * A ledger line (earn-ledger.jsonl) looks like:
 *   { ts, wallet, source, task, earn_usdc, cost_usdc, net_usdc, wake }
 * `source` is the earn channel (hl-trade, x402-serve, yield-*, gig, …); `task` the specific action.
 */

/**
 * @param {Array<object>} lines  recent earn-ledger rows (newest last)
 * @param {object} [opts]
 * @param {number} [opts.window=25]  how many recent rows to consider
 * @param {number} [opts.deadCount=4] same source with ~$0 net this many times → flag DEAD
 * @returns {{ bySlot: Record<string,{count:number,net:number|null,unknownCount:number,dead:boolean,lastTask:string}>, steer: string }}
 */
export function selfEval(lines, opts = {}) {
  const window = Number.isFinite(opts.window) ? opts.window : 25;
  const deadCount = Number.isFinite(opts.deadCount) ? opts.deadCount : 4;
  const rows = (Array.isArray(lines) ? lines : []).slice(-window);

  const bySlot = {};
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue;
    const slot = String(r.source || r.slot || 'unknown');
    const value = Object.hasOwn(r, 'net_usdc') ? r.net_usdc : r.net;
    const net = (typeof value === 'number' || (typeof value === 'string' && value.trim()))
      ? Number(value) : NaN;
    const task = String(r.task || '');
    const b = bySlot[slot] || (bySlot[slot] = { count: 0, net: 0, unknownCount: 0, dead: false, lastTask: '' });
    b.count += 1;
    const total = round4((b.net ?? 0) + net);
    if (!Number.isFinite(net) || !Number.isFinite(total)) b.unknownCount += 1;
    b.net = b.unknownCount ? null : total;
    b.lastTask = task || b.lastTask;
  }

  // DEAD = used >= deadCount times, net is ~zero-or-negative, and it isn't compounding (no positive run).
  for (const [slot, b] of Object.entries(bySlot)) {
    if (!b.unknownCount && b.count >= deadCount && b.net <= 0) b.dead = true;
  }

  const lines2 = [];
  const winners = [];
  const deads = [];
  for (const [slot, b] of Object.entries(bySlot)) {
    const tag = b.dead ? ' ← DEAD (stop)' : (b.net > 0 ? ' ← WORKS' : '');
    const amount = b.unknownCount ? `UNKNOWN (${b.unknownCount} unverified net rows)` : `$${b.net}${tag}`;
    lines2.push(`  ${slot} ×${b.count} → net ${amount}`);
    if (b.net > 0) winners.push(slot);
    if (b.dead) deads.push(slot);
  }

  let steer = '';
  if (lines2.length) {
    steer = `Your realised P&L by action (recent):\n${lines2.join('\n')}`;
    if (deads.length) {
      steer += `\n⛔ ${deads.join(', ')} = repeated for ~$0 realised — these are DEAD actions, do NOT pick them again this wake.`;
    }
    if (winners.length) {
      steer += `\n✅ ${winners.join(', ')} actually made money — do more of what works, or try a genuinely NEW earner (cook a new path).`;
    } else if (!Object.values(bySlot).some((b) => b.unknownCount)) {
      steer += `\nNothing has realised positive yet — try a genuinely different earner rather than repeating a dead one.`;
    }
    if (Object.values(bySlot).some((b) => b.unknownCount)) {
      steer += `\nSome net results are UNKNOWN — reconcile their evidence before judging those actions profitable or dead.`;
    }
  }

  return { bySlot, steer };
}

function round4(n) { return Math.round(n * 1e4) / 1e4; }
