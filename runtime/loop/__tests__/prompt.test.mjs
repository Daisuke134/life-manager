/**
 * prompt.test.mjs — spec 25 O1: the LLM must see EACH live skill as a pickable
 * flat tool (not just an opaque run_skill('earn')).
 *
 * Contract:
 *  - liveSlotNames(registry) → string[] of slots whose status === 'live'
 *  - getToolDefinitions(slots) → run_skill's `slot` param carries enum=slots
 *  - buildSystemPrompt(ctx) lists each active slot (with its summary if given)
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getToolDefinitions, buildSystemPrompt, liveSlotNames, buildUserMessage } from '../prompt.mjs';
import { assembleContext } from '../context.mjs';

// #7 AUT: low-liquid → the wake message must steer "replenish first" so the agent never strands itself.
const baseCtx = (over) => ({ wakeId: 'W', balanceUsdc: 0.06, tier: 'broke', reserveUsdc: 5, recentSlots: [], ...over });

test('buildUserMessage: liquid below the instance buffer → REPLENISH-FIRST directive present', () => {
  const m = buildUserMessage(baseCtx());
  assert.match(m, /BELOW COMPUTE BUFFER/);
  assert.match(m, /close/i);
  assert.match(m, /withdraw/i);
});

test('buildUserMessage: healthy liquid (>= buffer) → no low-liquid directive', () => {
  const m = buildUserMessage(baseCtx({ balanceUsdc: 12, tier: 'funded' }));
  assert.doesNotMatch(m, /BELOW COMPUTE BUFFER/);
});

// REAL-PATH regression (FIND-001/006): the directive must reflect the REAL liquid that flows through
// assembleContext — not a hand-built ctx. A funded $12 agent must NOT be told it's stranded; a $0.06
// agent MUST be. This catches index.mjs passing broke?0:undefined (which made everyone look like $0).
test('assembleContext → buildUserMessage: REAL low balance triggers the directive', () => {
  const ctx = assembleContext({ wakeId: 'W', balanceUsdc: 0.06, tier: 'broke', reserveUsdc: 5, recentSlots: [] });
  assert.match(buildUserMessage(ctx), /BELOW COMPUTE BUFFER.*\$0\.06/s);
});

test('assembleContext → buildUserMessage: REAL healthy balance does NOT trigger the directive', () => {
  const ctx = assembleContext({ wakeId: 'W', balanceUsdc: 12, tier: 'funded', reserveUsdc: 5, recentSlots: [] });
  assert.doesNotMatch(buildUserMessage(ctx), /BELOW COMPUTE BUFFER/);
});

test('assembleContext keeps avoidSlot + recentSlots (FIND-005: they were being dropped)', () => {
  const ctx = assembleContext({ wakeId: 'W', balanceUsdc: 1, avoidSlot: 'cook', recentSlots: ['cook', 'cook', 'cook'] });
  assert.equal(ctx.avoidSlot, 'cook');
  assert.deepEqual(ctx.recentSlots, ['cook', 'cook', 'cook']);
  const m = buildUserMessage(ctx);
  assert.match(m, /FORBIDDEN/); // the avoid steer now actually fires
});

test('assembleContext carries a compiled context capsule without rebuilding it', () => {
  const capsule = Object.freeze({ capsule_id: 'capsule-1', content_sha256: 'a'.repeat(64) });
  const ctx = assembleContext({ wakeId: 'W', contextCapsule: capsule });
  assert.equal(ctx.contextCapsule, capsule);
});


const REGISTRY = {
  slots: {
    report: { status: 'live', summary: 'per-wake report' },
    earn: { status: 'live', summary: 'earn USDC' },
    'self/spawn': { status: 'declared', summary: 'spawn child' },
    'economy/ubi': { status: 'declared', summary: 'ubi' },
  },
};

test('liveSlotNames returns only status==="live" slots', () => {
  assert.deepEqual(liveSlotNames(REGISTRY).sort(), ['earn', 'report']);
});

test('liveSlotNames is safe on empty/garbage input', () => {
  assert.deepEqual(liveSlotNames(null), []);
  assert.deepEqual(liveSlotNames({}), []);
  assert.deepEqual(liveSlotNames({ slots: {} }), []);
});

test('getToolDefinitions(slots) puts the live slots in the run_skill enum', () => {
  const tools = getToolDefinitions(['earn', 'report']);
  const runSkill = tools.find(t => t.function.name === 'run_skill');
  assert.ok(runSkill, 'run_skill tool present');
  assert.deepEqual(runSkill.function.parameters.properties.slot.enum, ['earn', 'report']);
  assert.ok(tools.find(t => t.function.name === 'sleep'), 'sleep tool still present');
});

test('getToolDefinitions() with no slots still works (backward compat, no enum)', () => {
  const tools = getToolDefinitions();
  const runSkill = tools.find(t => t.function.name === 'run_skill');
  assert.ok(runSkill);
  assert.equal(runSkill.function.parameters.properties.slot.enum, undefined);
});

test('buildSystemPrompt lists each active slot with its summary', () => {
  const ctx = {
    walletAddress: '0xabc', balanceUsdc: 1.23, tier: 'lean', model: 'auto',
    wakeId: 'W1', recentLedgerLines: [],
    activeSkillSlots: ['earn', 'report'],
    skillCatalog: { earn: 'earn USDC', report: 'per-wake report' },
  };
  const p = buildSystemPrompt(ctx, ctx.activeSkillSlots);
  assert.ok(p.includes('earn'), 'lists earn');
  assert.ok(p.includes('report'), 'lists report');
  assert.ok(p.includes('earn USDC'), 'includes earn summary');
});

// ── GAP-C regression guards (FIND-IMPL-004) ──────────────────────────────────
test('GAP-C: getToolDefinitions description does NOT deny a generic earn slot + mentions earn/<sub>', () => {
  const defs = getToolDefinitions(['earn/gig', 'yield']);
  const desc = defs[0].function.description;
  assert.ok(!/no generic\s+"?earn"?\s+slot/i.test(desc), 'must not deny a generic earn slot');
  assert.ok(/earn\/<sub>|gig/i.test(desc), 'must mention earn/<sub> (gig/clip/…) are valid');
});
test('GAP-C: buildUserMessage surfaces live earn/<sub> slots from ctx.activeSkillSlots', () => {
  const msg = buildUserMessage({ wakeId: 'W', balanceUsdc: 1, tier: 'free', recentSlots: [], activeSkillSlots: ['yield', 'earn/gig', 'earn/clip'] });
  assert.ok(msg.includes('earn/gig'), 'menu includes earn/gig');
  assert.ok(!/there is no generic\s+"?earn"?/i.test(msg), 'no denial in user message');
});
