import { test } from 'node:test';
import assert from 'node:assert/strict';
import { selfEval } from '../self-eval.mjs';

test('flags a repeated ~$0 action as DEAD and names it in the steer', () => {
  const lines = Array.from({ length: 12 }, () => ({ source: 'hl-trade', task: 'hl-close ETH', net_usdc: 0 }));
  const { bySlot, steer } = selfEval(lines, { deadCount: 4 });
  assert.equal(bySlot['hl-trade'].dead, true);
  assert.match(steer, /hl-trade.*DEAD/);
  assert.match(steer, /do NOT pick them again/);
});

test('does NOT flag a profitable action; marks it WORKS', () => {
  const lines = [
    { source: 'yield', task: 'deposit', net_usdc: 0.12 },
    { source: 'yield', task: 'deposit', net_usdc: 0.03 },
  ];
  const { bySlot, steer } = selfEval(lines);
  assert.equal(bySlot['yield'].dead, false);
  assert.ok(bySlot['yield'].net > 0);
  assert.match(steer, /yield.*WORKS/);
});

test('empty ledger → empty steer, no crash', () => {
  const { bySlot, steer } = selfEval([]);
  assert.deepEqual(bySlot, {});
  assert.equal(steer, '');
});

test('a few uses below deadCount is not DEAD even at $0', () => {
  const lines = [ { source: 'x402-serve', net_usdc: 0 }, { source: 'x402-serve', net_usdc: 0 } ];
  const { bySlot } = selfEval(lines, { deadCount: 4 });
  assert.equal(bySlot['x402-serve'].dead, false);
});

test('tolerates malformed rows and alt field names (slot/net)', () => {
  const lines = [ null, 'garbage', { slot: 'gig', net: 0.3 }, { source: 'gig', net_usdc: -0.1 } ];
  const { bySlot } = selfEval(lines);
  assert.equal(bySlot['gig'].count, 2);
  assert.equal(bySlot['gig'].net, 0.2);
});


test('missing or invalid money stays UNKNOWN instead of becoming a DEAD zero', () => {
  for (const net of [undefined, null, '', ' ', false, [], {}, 'bad', NaN, Infinity, -Infinity, 1e308]) {
    const { bySlot, steer } = selfEval(Array.from({ length: 4 }, () => ({ source: 'gig', net_usdc: net, net: 10 })));
    assert.equal(bySlot.gig.net, null, `net=${String(net)}`);
    assert.equal(bySlot.gig.unknownCount, 4);
    assert.equal(bySlot.gig.dead, false);
    assert.match(steer, /UNKNOWN/);
    assert.doesNotMatch(steer, /DEAD|WORKS|Nothing has realised positive|net \$0/);
  }
  const { bySlot } = selfEval(Array.from({ length: 4 }, () => ({ source: 'missing' })));
  assert.equal(bySlot.missing.net, null);
  assert.equal(bySlot.missing.dead, false);
});

test('a mixed incomplete slot never claims profit or a losing verdict', () => {
  for (const known of [1, -1, 0]) {
    const { bySlot, steer } = selfEval([
      { source: 'mixed', net_usdc: known },
      { source: 'mixed' },
      { source: 'mixed', net_usdc: known },
      { source: 'mixed', net_usdc: known },
    ]);
    assert.equal(bySlot.mixed.count, 4);
    assert.equal(bySlot.mixed.unknownCount, 1);
    assert.equal(bySlot.mixed.net, null);
    assert.equal(bySlot.mixed.dead, false);
    assert.doesNotMatch(steer, /DEAD|WORKS|Nothing has realised positive/);
  }
});

test('finite numeric strings and explicit zero remain known values', () => {
  const { bySlot, steer } = selfEval([
    { source: 'paid', net_usdc: '0.30' },
    { source: 'paid', net_usdc: '-0.10' },
    ...Array.from({ length: 4 }, () => ({ source: 'zero', net_usdc: 0 })),
  ]);
  assert.equal(bySlot.paid.net, 0.2);
  assert.equal(bySlot.paid.unknownCount, 0);
  assert.equal(bySlot.zero.dead, true);
  assert.match(steer, /paid.*WORKS/);
  assert.match(steer, /zero.*DEAD/);
});
