import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  appendUniqueSaleCandidates,
  normalizeClawMerchantSales,
  normalizeImageSales,
  normalizeRailwaySettlements,
  normalizeThe402Sales,
} from '../lib/sale-observer.mjs';
import { pollSaleSources } from '../sale-observer.mjs';

const PAY_TO = '0x1111111111111111111111111111111111111111';
const TX = `0x${'a'.repeat(64)}`;
const RAILWAY_PAY_TO = '0x6592EB8EF820aBC092e8C3474fb2042dffCCEDc7';
const RAILWAY_URL = 'https://x402-agents-production.up.railway.app';

test('image adapter emits only a settled successful sale and strips unapproved fields', () => {
  const rows = [
    {
      ts: '2026-07-23T02:00:00.000Z',
      route: '/image',
      price: '$0.03',
      payer: '0x2222222222222222222222222222222222222222',
      tx: TX.toUpperCase(),
      settled: true,
      status: 200,
      prompt: 'must not persist',
      paymentHeader: 'must not persist',
    },
    { ts: '2026-07-23T02:01:00.000Z', route: '/image', price: '$0.03', tx: null, settled: false, status: 402 },
    { ts: '2026-07-23T02:02:00.000Z', route: '/other', price: '$0.03', tx: TX, settled: true, status: 200 },
    { ts: '2026-07-23T02:03:00.000Z', route: '/image', price: '$0.03', tx: `0x${'b'.repeat(64)}`, settled: true, status: 502 },
  ];

  assert.deepEqual(normalizeImageSales(rows, { payTo: PAY_TO }), [{
    source: 'x402-image',
    source_sale_id: `x402-image:${TX}`,
    offer_id: '/image',
    tx: TX,
    expected_pay_to: PAY_TO,
    expected_usdc_atomic: '30000',
    observed_at: '2026-07-23T02:00:00.000Z',
  }]);
});

test('ClawMerchants adapter accepts only delivered transactions for the pinned asset and amount', () => {
  const assetId = '54a0fabf-a95a-47bd-b2cc-81f3189430cb';
  const rows = [
    { id: 'cm-sale-1', assetId, amountUsdc: 0.03, status: 'delivered', txHash: TX.toUpperCase(), createdAt: '2026-07-23T02:10:00.000Z', buyer: 'secret' },
    { id: 'cm-sale-2', assetId, amountUsdc: 0.03, status: 'pending', txHash: `0x${'b'.repeat(64)}`, createdAt: '2026-07-23T02:11:00.000Z' },
    { id: 'cm-sale-3', assetId: 'another-asset', amountUsdc: 0.03, status: 'delivered', txHash: `0x${'c'.repeat(64)}`, createdAt: '2026-07-23T02:12:00.000Z' },
    { id: 'cm-sale-4', assetId, amountUsdc: 0.04, status: 'delivered', txHash: `0x${'d'.repeat(64)}`, createdAt: '2026-07-23T02:13:00.000Z' },
  ];

  assert.deepEqual(normalizeClawMerchantSales(rows, {
    assetId,
    payTo: PAY_TO,
    priceUsd: '0.03',
  }), [{
    source: 'clawmerchants',
    source_sale_id: 'clawmerchants:cm-sale-1',
    offer_id: assetId,
    tx: TX,
    expected_pay_to: PAY_TO,
    expected_usdc_atomic: '30000',
    observed_at: '2026-07-23T02:10:00.000Z',
  }]);
});

test('the402 adapter accepts only settled transactions for an allowlisted offer and amount range', () => {
  const serviceId = 'svc_1c7ca3dd9de841b1';
  const body = {
    earnings: { settled_usd: 0.95 },
    recent_settlements: [
      { settlement_id: 'set_1', service_id: serviceId, provider_amount_usd: '0.95', status: 'settled', tx_hash: TX.toUpperCase(), settled_at: '2026-07-23T02:20:00.000Z', buyer_brief: 'must not persist' },
      { settlement_id: 'set_2', service_id: serviceId, provider_amount_usd: '0.95', status: 'pending', tx_hash: `0x${'b'.repeat(64)}`, settled_at: '2026-07-23T02:21:00.000Z' },
      { settlement_id: 'set_3', service_id: 'svc_unknown', provider_amount_usd: '0.95', status: 'settled', tx_hash: `0x${'c'.repeat(64)}`, settled_at: '2026-07-23T02:22:00.000Z' },
      { settlement_id: 'set_4', service_id: serviceId, provider_amount_usd: '26', status: 'settled', tx_hash: `0x${'d'.repeat(64)}`, settled_at: '2026-07-23T02:23:00.000Z' },
    ],
  };

  assert.deepEqual(normalizeThe402Sales(body, {
    payTo: PAY_TO,
    allowedOffers: {
      [serviceId]: { minUsd: '0.50', maxUsd: '25' },
    },
  }), [{
    source: 'the402',
    source_sale_id: 'the402:set_1',
    offer_id: serviceId,
    tx: TX,
    expected_pay_to: PAY_TO,
    expected_usdc_atomic: '950000',
    observed_at: '2026-07-23T02:20:00.000Z',
  }]);
});

test('Railway adapter emits allowlisted GET and POST mainnet settlements and strips payer claims', () => {
  const rows = [
    {
      id: 'f738b171-fb73-48b0-b386-aa391def62f4',
      observed_at: '2026-07-27T22:42:00.000Z',
      route: '/intent-router',
      method: 'POST',
      scheme: 'exact',
      network: 'eip155:8453',
      asset: '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',
      amount_atomic: '5000',
      pay_to: RAILWAY_PAY_TO,
      transaction: TX.toUpperCase(),
      payer: '0x2222222222222222222222222222222222222222',
      success: true,
      payment_header: 'must not persist',
    },
    {
      id: '61ad32a4-2d70-42f2-bca4-8a9241acd720',
      observed_at: '2026-07-28T04:30:00.000Z',
      route: '/funding-rates',
      method: 'GET',
      scheme: 'exact',
      network: 'eip155:8453',
      asset: '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',
      amount_atomic: '10000',
      pay_to: RAILWAY_PAY_TO,
      transaction: `0x${'b'.repeat(64)}`,
      success: true,
    },
    {
      id: 'wrong-amount',
      observed_at: '2026-07-27T22:42:01.000Z',
      route: '/intent-router',
      method: 'POST',
      scheme: 'exact',
      network: 'eip155:8453',
      asset: '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',
      amount_atomic: '9999',
      pay_to: RAILWAY_PAY_TO,
      transaction: `0x${'b'.repeat(64)}`,
      success: true,
    },
  ];

  assert.deepEqual(normalizeRailwaySettlements(rows, {
    payTo: RAILWAY_PAY_TO,
    allowedOffers: {
      '/intent-router': '5000',
      '/funding-rates': '10000',
    },
  }), [
    {
      source: 'x402-railway',
      source_sale_id: 'x402-railway:f738b171-fb73-48b0-b386-aa391def62f4',
      offer_id: '/intent-router',
      tx: TX,
      expected_pay_to: RAILWAY_PAY_TO.toLowerCase(),
      expected_usdc_atomic: '5000',
      observed_at: '2026-07-27T22:42:00.000Z',
    },
    {
      source: 'x402-railway',
      source_sale_id: 'x402-railway:61ad32a4-2d70-42f2-bca4-8a9241acd720',
      offer_id: '/funding-rates',
      tx: `0x${'b'.repeat(64)}`,
      expected_pay_to: RAILWAY_PAY_TO.toLowerCase(),
      expected_usdc_atomic: '10000',
      observed_at: '2026-07-28T04:30:00.000Z',
    },
  ]);
});

test('candidate store is 0600, strips extra fields, and dedupes by sale ID and tx', () => {
  const dir = mkdtempSync(join(tmpdir(), 'x402-sale-observer-'));
  const path = join(dir, 'sale-candidates.jsonl');
  const base = {
    source: 'x402-image',
    source_sale_id: `x402-image:${TX}`,
    offer_id: '/image',
    tx: TX,
    expected_pay_to: PAY_TO,
    expected_usdc_atomic: '30000',
    observed_at: '2026-07-23T02:00:00.000Z',
    prompt: 'must not persist',
  };
  const otherTx = `0x${'b'.repeat(64)}`;
  const other = { ...base, source: 'clawmerchants', source_sale_id: 'clawmerchants:cm-sale-2', offer_id: 'asset-2', tx: otherTx };

  assert.deepEqual(appendUniqueSaleCandidates(path, [
    base,
    { ...base, tx: `0x${'c'.repeat(64)}` },
    { ...other, source_sale_id: 'clawmerchants:another-sale', tx: TX },
    other,
    { ...other, source_sale_id: 'bad', tx: 'not-a-tx' },
  ]), { recorded: 2, duplicates: 2, invalid: 1 });
  assert.equal(statSync(path).mode & 0o777, 0o600);
  assert.deepEqual(readFileSync(path, 'utf8').trim().split('\n').map(JSON.parse), [
    {
      source: 'x402-image',
      source_sale_id: `x402-image:${TX}`,
      offer_id: '/image',
      tx: TX,
      expected_pay_to: PAY_TO,
      expected_usdc_atomic: '30000',
      observed_at: '2026-07-23T02:00:00.000Z',
    },
    {
      source: 'clawmerchants',
      source_sale_id: 'clawmerchants:cm-sale-2',
      offer_id: 'asset-2',
      tx: otherTx,
      expected_pay_to: PAY_TO,
      expected_usdc_atomic: '30000',
      observed_at: '2026-07-23T02:00:00.000Z',
    },
  ]);
  assert.deepEqual(appendUniqueSaleCandidates(path, [base, other]), { recorded: 0, duplicates: 2, invalid: 0 });
});

test('runner polls all live sources without sending the402 credentials to ClawMerchants', async () => {
  const assetId = '54a0fabf-a95a-47bd-b2cc-81f3189430cb';
  const serviceId = 'svc_1c7ca3dd9de841b1';
  const productId = 'prod_653429e9dd234895';
  const calls = [];
  const bodies = new Map([
    ['https://api.the402.ai/v1/jobs', { data: { jobs: [] } }],
    ['https://api.the402.ai/v1/threads', { data: { threads: [] } }],
    ['https://api.the402.ai/v1/provider/earnings', { data: { earnings: { settled_usd: 0.95, held_usd: 0, pending_usd: 0 }, recent_settlements: [{ settlement_id: 'set_1', service_id: serviceId, provider_amount_usd: '0.95', status: 'settled', tx_hash: TX, settled_at: '2026-07-23T02:20:00.000Z' }] } }],
    [`https://api.the402.ai/v1/products/${productId}`, { data: { product_id: productId, total_purchases: 1 } }],
    [`https://clawmerchants.com/api/v1/assets/${assetId}`, { id: assetId, totalPurchases: 1, discoveryCount: 5 }],
    ['https://clawmerchants.com/api/v1/transactions?limit=100', { transactions: [{ id: 'cm-sale-1', assetId, amountUsdc: 0.03, status: 'delivered', txHash: `0x${'b'.repeat(64)}`, createdAt: '2026-07-23T02:30:00.000Z' }] }],
    [`${RAILWAY_URL}/settlements?limit=100`, { settlements: [{
      id: 'railway-sale-1',
      observed_at: '2026-07-23T02:40:00.000Z',
      route: '/intent-router',
      method: 'POST',
      scheme: 'exact',
      network: 'eip155:8453',
      asset: '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',
      amount_atomic: '5000',
      pay_to: RAILWAY_PAY_TO,
      transaction: `0x${'e'.repeat(64)}`,
      success: true,
    }] }],
  ]);
  const fetchFn = async (url, init = {}) => {
    calls.push({ url, headers: init.headers || {} });
    const body = bodies.get(url);
    return { ok: body !== undefined, status: body === undefined ? 404 : 200, json: async () => body };
  };

  const result = await pollSaleSources({
    fetchFn,
    imageSources: [{
      payTo: PAY_TO,
      offers: [
        { route: '/image', priceUsd: '0.03' },
        { route: '/base-usdc-balance', priceUsd: '0.003' },
      ],
      rows: [
        { ts: '2026-07-23T02:00:00.000Z', route: '/image', price: '$0.03', tx: `0x${'c'.repeat(64)}`, settled: true, status: 200 },
        { ts: '2026-07-23T02:01:00.000Z', route: '/base-usdc-balance', price: '$0.003', tx: `0x${'d'.repeat(64)}`, settled: true, status: 200 },
      ],
    }],
    the402: { apiKey: 'the402-secret', payTo: PAY_TO, productId, allowedOffers: { [serviceId]: { minUsd: '0.50', maxUsd: '25' }, [productId]: { minUsd: '0.50', maxUsd: '0.50' } } },
    claw: { assetId, payTo: PAY_TO, priceUsd: '0.03' },
    railway: { baseUrl: RAILWAY_URL, payTo: RAILWAY_PAY_TO, allowedOffers: { '/intent-router': '5000' } },
  });

  assert.deepEqual(result.candidates.map((row) => row.source), ['x402-image', 'x402-image', 'x402-railway', 'the402', 'clawmerchants']);
  assert.equal(result.candidates[1].offer_id, '/base-usdc-balance');
  assert.equal(result.candidates[1].expected_usdc_atomic, '3000');
  assert.deepEqual(result.metrics, {
    image: { settled_candidates: 2 },
    railway: { settlement_candidates: 1 },
    the402: { jobs: 0, threads: 0, settled_usd: 0.95, held_usd: 0, pending_usd: 0, product_purchases: 1, settlement_candidates: 1 },
    clawmerchants: { purchases: 1, discovery_count: 5, transaction_candidates: 1 },
  });
  assert.deepEqual(result.errors, []);
  assert.equal(calls.filter((call) => call.url.startsWith('https://api.the402.ai/')).every((call) => call.headers['X-API-Key'] === 'the402-secret'), true);
  assert.equal(calls.filter((call) => call.url.startsWith('https://clawmerchants.com/')).every((call) => call.headers['X-API-Key'] === undefined), true);
});

test('runner isolates a the402 outage and continues image and ClawMerchants polling', async () => {
  const assetId = '54a0fabf-a95a-47bd-b2cc-81f3189430cb';
  const fetchFn = async (url) => {
    if (url.startsWith('https://api.the402.ai/')) {
      return { ok: false, status: 503, json: async () => ({ error: 'response body must not leak' }) };
    }
    if (url.endsWith(`/assets/${assetId}`)) {
      return { ok: true, status: 200, json: async () => ({ id: assetId, totalPurchases: 1, discoveryCount: 6 }) };
    }
    return { ok: true, status: 200, json: async () => ({ transactions: [{ id: 'cm-sale-2', assetId, amountUsdc: 0.03, status: 'delivered', txHash: `0x${'b'.repeat(64)}`, createdAt: '2026-07-23T02:30:00.000Z' }] }) };
  };

  const result = await pollSaleSources({
    fetchFn,
    imageSources: [{ payTo: PAY_TO, rows: [{ ts: '2026-07-23T02:00:00.000Z', route: '/image', price: '$0.03', tx: TX, settled: true, status: 200 }] }],
    the402: { apiKey: 'the402-secret', payTo: PAY_TO, productId: 'prod_653429e9dd234895', allowedOffers: { svc: { minUsd: '0.50', maxUsd: '25' } } },
    claw: { assetId, payTo: PAY_TO, priceUsd: '0.03' },
  });

  assert.deepEqual(result.candidates.map((row) => row.source), ['x402-image', 'clawmerchants']);
  assert.deepEqual(result.errors, [{ source: 'the402', code: 'poll_failed' }]);
  assert.deepEqual(result.metrics.the402, {
    jobs: null, threads: null, settled_usd: null, held_usd: null,
    pending_usd: null, product_purchases: null, settlement_candidates: 0,
  });
  assert.deepEqual(result.metrics.railway, { settlement_candidates: 0 });
  assert.equal(JSON.stringify(result).includes('response body must not leak'), false);
});
