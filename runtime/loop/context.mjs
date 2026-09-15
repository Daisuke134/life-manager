/**
 * context.mjs — Pure: assembleContext(opts) → context object
 *
 * REQ-001: Wake context assembly — wallet address, balance, recent ledger lines,
 * genesis prompt. No I/O performed here; all data passed in as arguments.
 */

/**
 * @typedef {object} WakeContext
 * @property {string} walletAddress
 * @property {number} balanceUsdc
 * @property {string} tier
 * @property {string} model
 * @property {object[]} recentLedgerLines - last 20 lines from ledger
 * @property {string} genesisPrompt - contents of $ANICCA_HOME/identity/genesis.md
 * @property {string} wakeId - ULID for this wake
 * @property {number} ts - unix timestamp
 * @property {object|null} contextCapsule - precompiled, hash-bound context; never rebuilt here
 */

/**
 * Assemble the wake context from pre-loaded data.
 *
 * @param {object} opts
 * @returns {WakeContext}
 */
export function assembleContext({ walletAddress, balanceUsdc, netWorth, tier, model, recentLedgerLines, genesisPrompt, wakeId, ts, activeSkillSlots, skillCatalog, skillToolDocs, positionsSummary, reserveUsdc, avoidSlot, recentSlots, earnSteer, alwaysActEngaged, alwaysActMenu, contextCapsule }) {
  return {
    // franklin-alwaysact-skill-router REQ-504: additive fields set by index.mjs's wake loop only for
    // Franklin-identity, flag-engaged wakes (REQ-501). alwaysActEngaged defaults false (byte-for-byte
    // unaffected for every non-always-act ctx); alwaysActMenu is the STATIC, full-wake menu (REQ-502/
    // 503) — never itself the per-attempt reference REQ-513's dispatch guard checks once a reroute is
    // in flight (index.mjs's own local `currentOfferedSlots` owns that role).
    alwaysActEngaged: alwaysActEngaged === true,
    alwaysActMenu: Array.isArray(alwaysActMenu) ? alwaysActMenu : [],
    walletAddress: walletAddress || 'unknown',
    balanceUsdc: typeof balanceUsdc === 'number' ? balanceUsdc : 0,
    // TOTAL assets across every chain/token/venue (net-worth.mjs). Visibility only — balanceUsdc above
    // remains the capital gate. null when the read failed: the prompt then omits the block entirely
    // rather than showing a fabricated total.
    netWorth: netWorth && typeof netWorth === 'object' ? netWorth : null,
    // loop-break + diversification signals — index.mjs passes these; without them here they were DROPPED,
    // so the FORBID-this-slot / over-use steers never fired in production (the live agent kept looping).
    avoidSlot: avoidSlot || null,
    recentSlots: Array.isArray(recentSlots) ? recentSlots : [],
    // SELF-EVAL steer (H2/H3): per-action realised P&L text so the AI sees which actions are DEAD ($0
    // repeated) vs WORK, and changes course itself. Empty when no earn ledger yet.
    earnSteer: typeof earnSteer === 'string' ? earnSteer : '',
    // the instance's OWN compute buffer (deploy floor) — same source as execute-yield's RESERVE. Used to
    // steer "replenish first" when liquid drops below it. Per-instance via env; never hardcoded per agent.
    reserveUsdc: typeof reserveUsdc === 'number' ? reserveUsdc : (Number(process.env.COMPUTE_RESERVE_USDC) || 5),
    // PATCH 3: surface deployed positions (yield/HL/etc) so the model can DECIDE a strategy from its
    // actual portfolio, not default. Empty string when the bootstrap didn't read positions.
    positionsSummary: typeof positionsSummary === 'string' ? positionsSummary : '',
    tier: tier || 'broke',
    model: model || 'free/gpt-oss-120b',
    recentLedgerLines: Array.isArray(recentLedgerLines) ? recentLedgerLines.slice(-20) : [],
    genesisPrompt: genesisPrompt || '',
    wakeId: wakeId || '',
    ts: ts || Math.floor(Date.now() / 1000),
    // FND-10: context_packet.py compiles and hashes this capsule; the JS wake context only carries it.
    contextCapsule: contextCapsule && typeof contextCapsule === 'object' ? contextCapsule : null,
    // spec 25 O1: the live skill slots the LLM may pick + their summaries
    activeSkillSlots: Array.isArray(activeSkillSlots) ? activeSkillSlots : [],
    skillCatalog: skillCatalog && typeof skillCatalog === 'object' ? skillCatalog : {},
    // TOOL-2 Phase A: optional per-slot { toolDescription, argsExample } (registry.json-sourced).
    // Empty object when the loop didn't pass it — buildSystemPrompt then falls back to skillCatalog's
    // one-line summary for every slot, byte-identical to pre-TOOL-2 behaviour.
    skillToolDocs: skillToolDocs && typeof skillToolDocs === 'object' ? skillToolDocs : {},
  };
}
