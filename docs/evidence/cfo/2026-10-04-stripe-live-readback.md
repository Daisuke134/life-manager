# Stripe live read-only financial readback — 2026-10-04 18:13 JST

## Credentials and effect boundary

- The private Life Manager runtime env contains a nonempty `STRIPE_SECRET_KEY` (mode 600). The separate canonical credential SSOT has no Stripe entry; no credential was created or copied. The key value was never printed or saved.
- Stripe official API GETs used Basic authentication through the existing `business_outcomes.py` helper. All list endpoints completed pagination; no charge, refund, subscription, payout, bank, state, ledger, report, or Telegram write was performed.
- The key reports live mode. Stripe API responses were summarized in memory; raw provider objects and IDs were not persisted.

## Current Stripe balance and account history

- Current `/v1/balance`: live mode; available JPY 0, pending JPY 0.
- Full list reads returned: balance_transactions 20 rows, charges 19, refunds 3, payouts 2, subscriptions 7, all pagination complete. Subscription status counts: 7 canceled; no active Stripe subscription MRR was observed.
- Balance transaction history spans 2025-10-01..2026-05-14 UTC. All observed transactions have status `available`.

| Balance transaction type | Count | Amount (JPY) | Fee (JPY) | Net (JPY) |
|---|---:|---:|---:|---:|
| charge | 8 | 5,796 | 209 | 5,587 |
| payment | 1 | 1,685 | 67 | 1,618 |
| refund | 3 | -2,204 | 0 | -2,204 |
| stripe_fee | 5 | -40 | 6 | -46 |
| adjustment | 1 | 1 | 0 | 1 |
| payout | 2 | -4,956 | 0 | -4,956 |
| **Net balance movement** | **20** |  |  | **0** |

The net arithmetic reconciles to the reported current Stripe balance: `5,587 + 1,618 - 2,204 - 46 + 1 - 4,956 = 0`.
Use `net` for account movement. The `fee` column is the Balance Transaction field per row; do not sum both `amount`, `fee`, and `net` as independent cash movements.

## Charges and configured Ebook product attribution

- Charge list: 19 live-mode charges. Nine succeeded/captured charges total USD 50.99; three successful refunds total USD 15.00. Ten failed charges total USD 50.00 with zero captured amount; failures are not revenue.
- No charge contained an allowed `lm_economic_category`; all 19 remain unclassified to product/owner in the CFO B2 contract. The eight succeeded charges not matched to either configured Ebook product total USD 40.00 gross; refund activity exists among this unmatched group.
- Complete Checkout Sessions read: 231 sessions across 3 pages. Matching the configured Ebook product IDs identified one paid Ebook EN order, USD 10.99 gross, zero refund, before fees. Ebook JA had zero paid matching sessions. The other eight succeeded charges (USD 40.00 gross including the USD 15.00 refunds) do not match those Ebook products; do not attribute them to Life Manager without owner/product evidence.
- USD Checkout/Charge amounts and JPY Stripe balance transactions reflect different provider currency layers. No exchange rate was inferred and the USD/JPY amounts were not added together.

## Payout-to-MUFG readback

- Stripe returned two live-mode payouts with status `paid`: JPY 3,338 arriving 2026-04-13 and JPY 1,618 arriving 2026-05-18; combined payout JPY 4,956.
- The read-only Moneytree window 2026-04-01..2026-05-31 returned 190 rows. Each payout had exactly one incoming JPY transaction matching its arrival date and amount; both matched rows had Stripe text in the description. Raw descriptions, account number, transaction IDs, and personal bank amounts are omitted here. This confirms the two historical payout deposits; it does not establish that all Stripe charge activity belongs to Life Manager.

## Provider response digests

These are SHA-256 digests of canonicalized API JSON page responses, not provider receipt IDs. They support future re-read comparison without retaining raw payloads.

| Endpoint | Rows / pages | Digest |
|---|---:|---|
| `/v1/balance` | 1 | `91ec1463e99ab519224ffa65d7a03eba221596a02ab32b6a8529111b9d4080eb` |
| `/v1/balance_transactions` | 20 / 1 | `c41a6ca3266a29653dd5e7cc1bc49925ca41967e017eaf57e42801564afe5c86` |
| `/v1/charges` | 19 / 1 | `efe0df1d141fd85d8ba3ba49f5999cfc4f6bc4fbb4c41031ef8893255e6be7dc` |
| `/v1/refunds` | 3 / 1 | `41cd6faa6e1211dfdfcc001259c7625ce5ce203a212383c1b407938a0b9bc957` |
| `/v1/payouts` | 2 / 1 | `6b2365f4da89ab17e09c5b080de6b84866dcdd101144f3f9c49b2711887ba657` |
| `/v1/subscriptions` | 7 / 1 | `fbc85f400d53af7a37a3cb3b3dbfc0f37cb61eaaa38c2b19acfe6a24e383d46` |
| `/v1/checkout/sessions` | 231 / 3 | `37ad29a5a69059648557f71ef661a3098a9ca9b38f79aa4bec914fcafdb5769` |

## CFO boundary and remaining proof

- The readback proves Stripe account activity and two historical Stripe-to-MUFG payout matches. It does not prove Life Manager ownership for the eight unclassified succeeded charges, does not complete the CFO B2 adapter/receipt join, and is not a company-wide settled-net P&L.
- The latest local B7 projection and daily CFO report were not updated by this direct read; Stripe evidence remains outside the persisted production CFO ledger until the source gate is cleared.
- TODO/status source of truth → [Unified SSOT](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md).
