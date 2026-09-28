import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  experimentExternalCount,
  normalizeVerifiedInflows,
  scoutIsFresh,
  summarizeOwnProducts,
} from '../store-improve.mjs';

const SERVED_PATHS = ['/web-search', '/funding-rates', '/funding-rate-arb', '/research'];
const NOW = Date.parse('2026-07-18T12:00:00.000Z');
const SELF = '0x0000000000000000000000000000000000000abc';
const EXTERNAL = '0x0000000000000000000000000000000000000def';
const HERE = dirname(fileURLToPath(import.meta.url));

test('controller stays dependency-free in the rsynced Franklin runtime body', () => {
  const source = readFileSync(join(HERE, '..', 'store-improve.mjs'), 'utf8');
  assert.doesNotMatch(source, /from ['"]\.\/llm-resale\.mjs['"]/, 'controller must not import paid-runtime dependencies');
  assert.match(source, /from ['"]\.\/llm-offers\.mjs['"]/, 'controller must import the pure offer catalog');
  assert.match(source, /import \{ CORE_PATHS, computeGaps \} from ['"]\.\/product-gaps\.mjs['"];/,
    'controller must share the product-gaps served-path catalog');
  assert.match(source, /external-inflows-\$\{lower\}\.jsonl/,
    'controller must source external rewards from the finalized inflow ledger');
  assert.doesNotMatch(source, /const CORE_PATHS =/,
    'controller must not drift a second served-path catalog');
});

test('summarizeOwnProducts aggregates only served routes with external, attempts, and age wakes', () => {
  const sales = [
    { ts: new Date(NOW - 600_000).toISOString(), route: '/web-search', payer: SELF.toUpperCase(), settled: true },
    { ts: new Date(NOW - 480_000).toISOString(), route: '/web-search', payer: EXTERNAL, settled: true },
    { ts: new Date(NOW - 120_000).toISOString(), route: '/funding-rates', payer: EXTERNAL, settled: true },
    { ts: new Date(NOW - 360_000).toISOString(), route: '/research', payer: EXTERNAL, settled: false },
    { ts: new Date(NOW - 1_200_000).toISOString(), route: '/not-served', payer: EXTERNAL, settled: true },
  ];
  const attempts = [
    { ts: new Date(NOW - 240_000).toISOString(), route: '/web-search' },
    { ts: new Date(NOW - 120_000).toISOString(), route: '/web-search' },
    { ts: new Date(NOW - 360_000).toISOString(), route: '/funding-rates' },
    { ts: new Date(NOW - 60_000).toISOString(), route: '/funding-rate-arb' },
    { ts: new Date(NOW - 1_200_000).toISOString(), route: '/not-served' },
  ];

  assert.deepEqual(summarizeOwnProducts(sales, attempts, SERVED_PATHS, new Set([SELF]), NOW), [
    { path: '/web-search', external: 1, attempts: 2, ageWakes: 5 },
    { path: '/funding-rates', external: 1, attempts: 1, ageWakes: 3 },
    { path: '/funding-rate-arb', external: 0, attempts: 1, ageWakes: 1 },
    { path: '/research', external: 0, attempts: 0, ageWakes: 3 },
  ]);
});

test('scoutIsFresh invalidates the old listing-only cache schema', () => {
  const now = 1_700_000_000_000;
  assert.equal(scoutIsFresh({
    ts: now / 1_000,
    byCategory: [{ category: 'defi', count: 11, medianPriceUsd: 0.007 }],
  }, now), false);
});

test('verified inflow normalization accepts only finalized external settlement rows', () => {
  const rows = normalizeVerifiedInflows([
    {
      observed_at: '2026-07-18T12:00:00.000Z',
      offer_id: '/llm',
      from: EXTERNAL,
      status: 'success',
      finalized: true,
      external: true,
      tx: `0x${'a'.repeat(64)}`,
      usdc_atomic: '3000',
    },
    {
      observed_at: '2026-07-18T12:01:00.000Z',
      offer_id: '/research',
      from: EXTERNAL,
      status: 'success',
      finalized: false,
      external: true,
    },
    {
      observed_at: '2026-07-18T12:02:00.000Z',
      offer_id: '/research',
      from: EXTERNAL,
      status: 'success',
      finalized: true,
      external: false,
    },
  ]);

  assert.deepEqual(rows, [{
    ts: '2026-07-18T12:00:00.000Z',
    route: '/llm',
    payer: EXTERNAL,
    settled: true,
  }]);
});

test('scoutIsFresh accepts a recent demand-aware cache', () => {
  const now = 1_700_000_000_000;
  assert.equal(scoutIsFresh({
    ts: now / 1_000,
    byCategory: [{ category: 'defi', count: 1_014, medianPriceUsd: 0.01, calls30d: 9_398 }],
  }, now), true);
});

test('LLM experiment reward ignores external sales on every other route', () => {
  const products = [
    { path: '/research', external: 4 },
    { path: '/web-search', external: 2 },
    { path: '/llm', external: 0 },
  ];
  assert.equal(experimentExternalCount(products, '/llm'), 0);
  assert.equal(experimentExternalCount([{ path: '/llm', external: 1 }], '/llm'), 1);
});
