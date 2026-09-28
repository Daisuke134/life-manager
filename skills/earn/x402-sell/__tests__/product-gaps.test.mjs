import test from 'node:test';
import assert from 'node:assert/strict';

import { CORE_PATHS, computeGaps } from '../product-gaps.mjs';

const scout = {
  byCategory: [
    { category: 'data', count: 5, medianPriceUsd: 2, calls30d: 2, payerSignals30d: 2 },
    { category: 'llm', count: 4, medianPriceUsd: 3, calls30d: 10, payerSignals30d: 5 },
    { category: 'image', count: 3, medianPriceUsd: 2, calls30d: 50, payerSignals30d: 20 },
    { category: 'audio', count: 1, medianPriceUsd: 100, calls30d: 1, payerSignals30d: 1 },
    { category: 'search', count: 10, medianPriceUsd: 1, calls30d: 0, payerSignals30d: 0 },
    { category: 'other', count: 100, medianPriceUsd: 100, calls30d: 1_000, payerSignals30d: 500 },
    { category: 'calc', count: 200, medianPriceUsd: 200, calls30d: 1_000, payerSignals30d: 500 },
  ],
};
const ourCategories = new Set(['search', 'data']);

test('the gap scout knows the live LLM route is already served', () => {
  assert.equal(CORE_PATHS.includes('/llm'), true);
});

test('the gap scout catalog matches the five routes served by serve-v2 core mode', () => {
  assert.deepEqual(CORE_PATHS, [
    '/web-search',
    '/funding-rates',
    '/funding-rate-arb',
    '/research',
    '/llm',
  ]);
});

test('computeGaps ranks opportunities by supply-adjusted observed revenue', () => {
  const result = computeGaps(scout, ourCategories, 1_700_000_000.9);

  assert.equal(result.ts, 1_700_000_000);
  assert.deepEqual(result.opportunities.map(({ category, opportunityScore }) => ({ category, opportunityScore })), [
    { category: 'image', opportunityScore: 33.333333 },
    { category: 'llm', opportunityScore: 7.5 },
    { category: 'data', opportunityScore: 0.8 },
  ]);
});

test('computeGaps excludes other and calc categories', () => {
  const result = computeGaps(scout, ourCategories, 1_700_000_000);

  assert.deepEqual(result.opportunities.map(({ category }) => category), ['image', 'llm', 'data']);
});

test('computeGaps marks categories already served by our shop', () => {
  const result = computeGaps(scout, ourCategories, 1_700_000_000);

  assert.deepEqual(result.ourCategories, ['search', 'data']);
  assert.equal(result.opportunities.find(({ category }) => category === 'data').weServe, true);
  assert.equal(result.opportunities.find(({ category }) => category === 'llm').weServe, false);
});

test('computeGaps excludes categories below the default market-count floor', () => {
  const result = computeGaps(scout, ourCategories, 1_700_000_000);

  assert.equal(result.opportunities.some(({ category }) => category === 'audio'), false);
});

test('computeGaps accepts a custom market-count floor', () => {
  const result = computeGaps(scout, ourCategories, 1_700_000_000, { minMarketCount: 1 });

  assert.equal(result.opportunities[0].category, 'audio');
});

test('computeGaps excludes categories with no observed calls', () => {
  const result = computeGaps(scout, ourCategories, 1_700_000_000);

  assert.equal(result.opportunities.some(({ category }) => category === 'search'), false);
});

test('computeGaps excludes apparent calls with no payer signals', () => {
  const result = computeGaps({
    byCategory: [
      { category: 'llm', count: 5, medianPriceUsd: 2, calls30d: 100, payerSignals30d: 0 },
    ],
  }, new Set(), 1_700_000_000);

  assert.deepEqual(result.opportunities, []);
});

test('computeGaps returns no opportunities for empty scout data', () => {
  assert.deepEqual(computeGaps({}, ourCategories, 1_700_000_000), {
    ts: 1_700_000_000,
    ourCategories: ['search', 'data'],
    opportunities: [],
  });
});
