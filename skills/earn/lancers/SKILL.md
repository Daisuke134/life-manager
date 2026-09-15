---
name: lancers
description: Use when operating, diagnosing, or extending the canonical Lancers acquisition, storefront, sales, fulfillment, finance, reporting, or revenue loop.
---

# Lancers Money Loop

Operate Lancers from the Life Manager exact-release source. Public/provider readback and durable receipts are truth; process health,
listing count, proposals, forecasts, and unpaid contracts are not revenue.

## Architecture

- Apply: `scripts/application_loop.py` discovers, judges, applies at most once per tick, and requires an official proposal ID.
- Storefront: `scripts/storefront_offer.py` owns one canonical package, one matching public portfolio proof, official inventory, demand counters, and one-variable improvements.
- Negotiate / Reply: `scripts/work_sync.py` owns buyer-last messages, replies, Storefront estimates, client-offer verification/acceptance, and funded ContractReceipt handoff.
- Paid: owns funded work, requirements, production, QA, delivery, payment, provider settlement, and bank reconciliation. This owner is not implemented yet.
- Reporting: `scripts/telegram_report.py` is the four-lane control plane, not a fifth revenue lane. It renders every wake, effect, skip, blocker, failure, official readback, and verified payment in natural Japanese.
- Product: `products/monthly-sns-content-ops-v1.json` is the single offer definition. Its image is in `assets/`.

All Lancers lanes use the same 9227 CDP endpoint and browser profile. Per-lane state locks do not
serialize page navigation; every production browser client must pass through
`application_tick._default_browser_factory`, which holds the shared browser-session lease until
page cleanup. A held lease returns `browser_session_busy` for the next wake; never bypass the lease,
open a second profile, or treat a process exit as a provider effect.

The exact four-lane ownership, Coconala copy boundary, Telegram human-message contract, $10K plan, and active TODO order live only in the
design SSOT §18. Do not add a fifth lane or duplicate those rules here.

Do not add another scheduler, DB, state file, checkout, browser profile, or mutable runtime copy. Deploy only an immutable commit reachable
from `origin/main`. Preserve provider-native spot/3-month/6-month contract routes.

## Storefront commands

From an installed exact release:

```bash
python3 skills/earn/lancers/scripts/storefront_offer.py --inspect
python3 skills/earn/lancers/scripts/storefront_offer.py --apply
```

`--inspect` is read-only. `--apply` makes at most one official mutation per wake: it first pauses one explicitly declared
`superseded_listing_ids` entry, then aligns only `listing_external_id`, then creates the declared portfolio only when the offer is already aligned. It writes the canonical listing receipt only after official
status/public readback. If readback is incomplete, the next wake re-observes before any effect; never repeat a blind save. Product changes
require updating the design SSOT first.

## Money truth

Follow one funnel: search impression → view → inquiry → official ContractReceipt → funded work → DeliveryReceipt → PaymentReceipt → bank
reconciliation → net MRR. Keep application and storefront as parallel acquisition entrances into the same sales, fulfillment, and finance
lanes. Never report gross package price or proposal value as earned money.
