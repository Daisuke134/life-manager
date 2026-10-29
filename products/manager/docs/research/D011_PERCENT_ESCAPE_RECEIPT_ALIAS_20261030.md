# D011 — Percent-encoded receipt alias preflight (2026-10-30 JST)

## Canonical scope
Read research branch products/manager/docs/roadmap/tasks.json (blob SHA ad26ddcde0a091aaa7224414bc0e1b635b96d58c): 113 tasks = 69 done / 41 todo / 3 blocked. D011 depends on completed D010 and remains TODO. This is an offline P0 engineering atom, NOT authenticated payment, proven income, welfare improvement or real-world intervention. H005 remains blocked pending original 2019 HeartSteps study-day exclusion information; no fitted or invented paper values. F004 and F007 remain blocked for external permission.

## Imozuru: question → hypotheses → original sources → falsifiers
Question: Can the same public payment-document URL be relabeled with percent-encoded unreserved characters and evade duplicate-evidence screening?

Unsafe hypothesis: https://example.org/%72eceipt?tx=%41 and https://example.org/receipt?tx=A are independently verified proof of payment merely because URI strings differ.

Counter-hypothesis: normalize only URI-syntax equivalences as a conservative REVIEW flag, never payment confirmation. A shared ledger page can legitimately describe separate transactions; overlap must be reviewed independently and does not prove fraud.

Primary documents:
- IETF RFC 3986 §2.3, §6.2.2.1–6.2.2.2: unreserved characters are ALPHA/DIGIT/-._~; unreserved percent encoding should be decoded; hex digits in percent octets are case-insensitive. https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2.2.2
- IETF RFC 9110 §4.2.3: default HTTPS port, host case and empty-root path normalization. https://www.rfc-editor.org/rfc/rfc9110.html#section-4.2.3

Adversarial counterexamples: reserved slash %2F is not literal slash /; do not double decode %252F, sort query parameters, case-fold literal path/query, dereference URLs or infer distinct settlement identities. Malformed percent escapes must not silently pass validation.

## Implementation and falsification tests
- manager_core/opportunity_outcomes.py: new _normalize_percent_unreserved normalizes a single pass over path and query percent triplets, uppercases retained reserved escapes, rejects malformed escapes. _resource_url uses it after host/default-port handling.
- tests/test_opportunity_receipt_portfolio.py: four synthetic regression methods: cross-job unreserved aliases; reserved hex case; preserve reserved/literal/double-encoded distinctions; malformed escapes rejected when receipts are absent.
- tests/test_opportunity_outcomes.py: two synthetic regression methods: relabeled approval not a receipt; invalid escapes rejected with pending receipt.
- A local standalone normalization harness ran 3/3 passing tests. This is only helper verification and is NOT a claim that the complete Manager suite or GitHub CI passed.
- Expected repository commands: python3 -m unittest tests.test_opportunity_outcomes tests.test_opportunity_receipt_portfolio -v ; python3 -m unittest discover -s tests ; python3 scripts/check_boundaries.py ; python3 scripts/make_roadmap.py --check .
- Files committed in research branch only. Tasks.json progress stays unchanged. No private records, execution credentials, account transfers, outbound messages, permission changes, or facility control.

## Scientific and product limits
Source: official URI specification. Synthetic experiment: URL equality and declared payment-source consistency only. No real-world readback, no independent transaction authentication, no verified income, no P1–P4 causal effect, no measured relief of human/animal suffering. No Human in the Loop applies only to bounded standing-authorized routine work.

## Remaining work
D011 still needs independently verifiable settlement evidence linked to approved delivery; URL and hash metadata are necessary but insufficient. D014 needs ethics/appropriate public aggregations. U002 needs consenting interviewees. Y003/Y005 need authorized submissions or contact. Blocked tasks are not prerequisites to this offline technical check.
