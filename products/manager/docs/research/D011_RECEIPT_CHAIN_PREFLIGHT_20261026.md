# D011 — Declared receipt-chain binding before portfolio accounting (2026-10-26 JST)

**Scope:** One independent Manager research-branch engineering atom. **Canonical progress:** `products/manager/docs/roadmap/tasks.json` remains unchanged (69 done, 41 todo, 3 blocked). D011 remains **todo** until authentic external receipt/readback evidence exists. H005 HeartSteps 2019 remains **blocked**; this work does not substitute or fabricate its original trial-day mapping.

## Question → competing hypotheses → falsifier (imozuru)

**Question:** If each opportunity lists a supposedly settled receipt, is checking for duplicate receipt URLs across opportunities enough for the portfolio preflight to report no issues?

- **Unsafe hypothesis:** Every individual claim with a unique receipt source can be treated as internally bound to its job, beneficiary group, currency, approved artifact and public evidence chain without checking those links.
- **Alternative hypothesis:** A portfolio must check both **cross-record reuse** and **within-record chain binding**; missing or mismatched declarations require review even when the receipt URL is unique.
- **Synthetic falsifier:** Two entirely fictional jobs show different receipt URLs. One record carries a receipt for the other job, a mismatched currency, a missing delivery hash, a nonpublic approval, or a reused posting page masquerading as a settlement receipt. The previous portfolio preflight could return `PRELIMINARY_ONLY` despite these known contradictions. The new checks must return `REVIEW_REQUIRED` with fixed reason codes and no leaked identifiers or amounts.
- **Negative control:** A fictional, internally consistent claim with unique stage sources remains `PRELIMINARY_ONLY`, **not verified earnings**.

## Primary official evidence reviewed

1. **Stripe — PaymentIntents API**: https://docs.stripe.com/api/payment_intents . Official contract describes a PaymentIntent per order or customer session, with stable object identity, multiple states and amount/currency fields. Our separate `opportunity_id`, group, artifact, currency and receipt references are a **Manager engineering policy**, not a claim that Stripe natively proves those fields or that a Stripe intent implies bank receipt.
2. **Stripe — Refunds API**: https://docs.stripe.com/api/refunds . Refunds have their own objects, status and links to earlier payment objects. A claimed `settled` state can later be qualified by reversal or refund evidence; this static preflight does not observe those events.
3. **Open Collective — Transaction pairs, groups and perspectives**: https://documentation.opencollective.com/advanced/ledger/transaction-pairs-groups-and-perspectives . One underlying transaction may produce multiple debit/credit and fee lines. Conversely, multiple legitimate transactions may share a public ledger page. Neither line counts nor source URL uniqueness proves independent receipt.

These URLs are **source locators**, not imported text/code or permission to retrieve private payment records. Provider-specific authenticity, exact transaction IDs, reversals and account settlement require independent permitted evidence. No credentials or payment APIs are used.

## Implementation & tests

- Extend `manager_core/opportunity_receipt_portfolio.py::preflight_receipt_portfolio` to detect missing public posting/delivery/approval stages, receipt scope or currency mismatches, missing/nonmatching delivery/approval/receipt artifact hashes, and reused earlier-stage evidence under the settlement source ID, URL or content SHA-256.
- Preserve 1–128-record bounded input, duplicate checks, no source bytes, no network, no amount summation and fixed diagnostic codes only.
- Add all-fictional adversarial regression tests in `tests/test_opportunity_receipt_portfolio.py`. Commands from `products/manager`: `python -m unittest tests.test_opportunity_receipt_portfolio -v`, `python -m unittest discover -s tests -v`, `python scripts/check_boundaries.py`, `python scripts/make_roadmap.py --check`.
- An internally consistent declaration is still **preliminary metadata only**; all outputs preserve `verified_income_minor=None`, `income_status=NOT_VERIFIED`, `independent_payment_verified=False`, `can_execute=False`, `can_publish=False`, `beneficiary_effect=NOT_MEASURED`.

## Boundary & remaining original acceptance

Only **P0 software/fixture evidence** is testable here. No P1 authorized action, P2 independent external change, P3 beneficiary gain, P4 causal net suffering reduction or P5 replication is established for people or animals. No personal accounts, IDs, credentials, facility equipment, donations, outreach or live effects are touched. Life Manager runtime and `main` remain outside the change. D011 still needs authorized authentic public settlement evidence with transaction identity, beneficiary/recipient linkage and reversals reconciled over time before its original criterion can be marked done.

**Product direction:** End suffering through legal public, nonpersonal macro-environment improvements; No Human in the Loop for routinely authorized operations, never silent self-expansion of authority.