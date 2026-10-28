# D011 — HTTPS receipt-source aliases (2026-10-29 JST)

One offline, nonpersonal P0 engineering atom under canonical D011 (accepted deliverable vs independently confirmed actual receipt). D011 stays TODO; the canonical tasks.json registry remains 69 done, 41 todo, 3 blocked / 113 total.

## Imozuru: question, adversarial hypotheses, falsification

Question: Could different spelling of the same HTTPS source URL evade the existing independent-payment-evidence preflight?
Unsafe hypothesis: removing only fragments makes hostname capitalization, :443 and empty-vs-root paths look independent.
Conservative hypothesis: normalize only standard HTTPS equivalences (scheme/host case, default 443, empty path = slash, ignore fragment). Preserve path/query case and nondefault ports. Any apparent overlap requires review; it is neither proof of fraud nor a verified receipt.
Falsifiers: two job receipts using those aliases return RECEIPT_URL_REUSED; relabeled cross-job posting or same-job approval returns the earlier-stage evidence-reuse code. Different query/path case and :8443 remain distinct for this limited screen, yet are still PRELIMINARY_ONLY. Malformed, zero and out-of-range ports raise constant ValueError even if a source ID collides or the payment is pending.

## Primary-source evidence

- IETF RFC 9110 sections 4.2.2 and 4.2.3: HTTPS default 443, scheme/host case-insensitivity, default-port, root path and query/path comparison. https://www.rfc-editor.org/rfc/rfc9110.html#section-4.2.3
- IETF RFC 3986 sections 6.2.2.1 and 6.2.3: generic case normalization and scheme-based normalization. https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2.3

These standards explain URL equivalence, not payment provider authorization, settlement authenticity, source rights, receipts, welfare outcomes, or income.

## Changes / verifications

- manager_core/opportunity_outcomes.py: deterministic HTTPS primary-resource comparison and eager syntax validation for declared sources.
- manager_core/opportunity_receipt_portfolio.py: validate every declared stage including missing-receipt settlement stage; validate receipt port before comparison short-circuit.
- tests/test_opportunity_outcomes.py: 2 synthetic regression methods.
- tests/test_opportunity_receipt_portfolio.py: 5 synthetic regression methods.
- Expected checks: python3 -m unittest tests.test_opportunity_outcomes tests.test_opportunity_receipt_portfolio -v; python3 -m unittest discover -s tests; python3 scripts/check_boundaries.py; python3 scripts/make_roadmap.py --check.

External CI and GitHub readback must be checked after commit; this research note is not a claim of passing CI or independently verified payment.

## Evidence boundaries

No accounts, private data, network transactions, outbound messages, external permission grants, publication actions, or live effects. Every result remains NOT_VERIFIED for income and NOT_MEASURED for human/animal welfare. H005 HeartSteps strict 2019 replication remains BLOCKED because public data cannot recover the exact excluded study dates, and original paper numbers were neither interpolated nor fitted. F004 and F007 remain blocked on legitimate independent authorization. No Human in the Loop applies to bounded standing-authorized routine work only.
