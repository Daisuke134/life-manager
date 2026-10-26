# D011 — Fragment-alias receipt evidence preflight (2026-10-26 JST)

**Scope:** one independent, offline D011 atomic engineering step. This note does **not** close D011's original acceptance. The only Manager progress source is `products/manager/docs/roadmap/tasks.json` (69 done / 41 todo / 3 blocked). **H005 stays blocked:** exact 2019 HeartSteps analysis-day mapping is not established by the public release. F004 and F007 still need independent authority.

## 1. Question → competing explanations → falsifier (imozuru)

**Question:** Can an apparent settlement evidence URL be made "unique" merely by adding a `#fragment`, causing an internal accounting preflight to miss reuse of the same publicly linked resource?

- **Unsafe H0:** Full receipt URL strings are distinct, so the settlement sources must be independent even when they differ only after `#`.
- **Narrow H1:** The same primary URI *without* its fragment is a potential evidence-source collision. Send it to review; never call it independently paid or add income. This is a conservative **necessary screen**, not sufficient evidence of actual transaction identity.
- **Falsifier (all fictional):** (i) two distinct jobs with different source IDs and content digests cite `https://example.org/ledger?tx=shared#receipt-a` and `...#receipt-b`; (ii) a job's receipt points at its approval URL with only a new fragment. Both must fail the respective preflight/reconciliation, even with unique declared digests and labels.
- **Negative control:** Legitimately different query identifiers (`?tx=one` vs `?tx=two`) are **not** collapsed by this narrow rule. They remain `PRELIMINARY_ONLY`, **not verified income**.
- **Caveat:** Client-side fragment routes can represent different views or details. A shared primary URL is a *review reason* and **not proof that two actual provider payments are the same**. Conversely, different primary URLs are no proof of payment independence.

## 2. Original sources (read-only locators)

1. **RFC 3986 §3.5, fragment identifier**, RFC Editor: https://www.rfc-editor.org/rfc/rfc3986#section-3.5 — Fragments reference secondary resources of a primary URI and are separated before dereferencing. That motivates comparing the declared underlying resource; it does not prove any bank payment.
2. **Stripe Webhooks, "Handle duplicate events"**, official documentation: https://docs.stripe.com/webhooks — Genuine event deduplication requires provider event/object identifiers. URL equality or URL differencing is not a substitute for authenticated signed provider receipts.
3. **Stripe refunds API**, official documentation: https://docs.stripe.com/api/refunds — Reversal/refund state and actual settlement must be verified independently; a static `settled` claim is not sufficient.

**Alternative interpretation recorded:** A legitimate ledger page can refer to multiple transactions, and two different fragments may identify different portions of it. This offline guard intentionally favors a false-positive **review** over misleading an unverified accounting system. There is no universal receipt URL normalization across providers; this atom preserves path and query bytes and does not assume fragment equality means transaction equality.

## 3. Implementation / reproducible checks

- `manager_core/opportunity_outcomes.py`: add `_resource_url` using standard-library `urllib.parse.urldefrag`; reject earlier-stage `#fragment`-aliased receipt evidence as `RECEIPT_EVIDENCE_REUSED`, with no declared settled amount.
- `manager_core/opportunity_receipt_portfolio.py`: reuse the helper for cross-opportunity URL resource collisions (`RECEIPT_URL_REUSED`) and same-job earlier-stage evidence (`RECEIPT_REUSES_EARLIER_STAGE_EVIDENCE`).
- `tests/test_opportunity_outcomes.py` and `tests/test_opportunity_receipt_portfolio.py`: all-synthetic alias, reversal-order, query-distinct, missing payout and fail-closed outcome assertions. No real bank, beneficiary, personal record or third-party API is accessed.
- Hosted **Manager Independent Offline Research CI** on code/test head `3190575bab6fd492c5855ed4b36e4501b9f1793f`: https://github.com/Daisuke134/life-manager/actions/runs/40249039414 — **539 tests, 5 skipped**, success; boundary and backlog consistency checks succeeded. This note is a later documentation-only commit; verify its own CI independently.

## 4. Claims and untouched boundaries

**Proved:** P0 deterministic handling of syntactically different fragment aliases for declared public evidence metadata; an internally inconsistent receipt declaration no longer flows to even *declared* arithmetic through this route.

**NOT proved:** Receipt URL authenticity, Stripe transaction ID identity, independent settlement, bank funds received, refunds/disputes reconciled, real human or animal benefit, a causal intervention, or a real-world release. No P1–P5 welfare evidence is granted. `verified_income_minor=None`, `income_status=NOT_VERIFIED`, `independent_payment_verified=False`, `can_execute=False` and `can_publish=False` remain fail-closed.

**Original D011 still TODO:** reconcile authentic, appropriately public and authorized third-party receipt/transaction identity and reversal evidence. No external accounts, credentials, wallets, outreach, live effects, operator equipment, `main`, or Life Manager runtime touched.

**Philosophy:** End suffering; improve macro environments from public nonpersonal evidence, with no human in the **routine authorized** loop. A model simulation or metadata check must never masquerade as measured reduction of suffering.
