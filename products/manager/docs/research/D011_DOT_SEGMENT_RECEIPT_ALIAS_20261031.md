# D011 — Dot-segment receipt URL alias review (2026-10-31 JST)

## Canonical source and state
`products/manager/docs/roadmap/tasks.json` (SHA `ad26ddcde0a091aaa7224414bc0e1b635b96d58c`) is the sole progress authority: 113 items, 69 done, 41 todo, 3 blocked. D011 depends on completed D010; it remains `todo`. H005 remains `blocked` due to missing original 2019 HeartSteps study-day exclusions; F004 and F007 remain permission-blocked. No fabricated outcomes.

## Imozuru: question / competing explanations / primary sources
Question: Can a claimed payment URL be cosmetically changed with complete `.` or `..` path segments to avoid duplicate or earlier-stage-document screening?
Unsafe hypothesis: `https://example.org/path/../approval` and `https://example.org/approval` are independent evidence of payment. URI syntax normalization instead requires a conservative collision review; it never authenticates payment or proves fraud.
Counter-hypothesis: a shared ledger URL may legitimately contain different transactions; syntactic collision is only a REVIEW flag. Preserve genuinely distinct query text, double slashes, percent-encoded slashes, non-dot segments and nested encoded `%252e` sequences.
Primary sources:
- IETF RFC 3986 §5.2.4: algorithm to remove complete path dot-segments: https://www.rfc-editor.org/rfc/rfc3986.html#section-5.2.4
- IETF RFC 3986 §6.2.2.2–3: unreserved percent decoding and dot-segment normalization: https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2.2.3
- IETF RFC 9110 §4.2.3: normalization for HTTPS; equivalence is not transaction identity: https://www.rfc-editor.org/rfc/rfc9110.html#section-4.2.3

## Atomic code and falsification
- `manager_core/opportunity_outcomes.py`: `_remove_dot_segments` applies RFC path-only algorithm after one unreserved-percent decoding pass in `_resource_url`. The shared review key affects both record reconciliation and cross-opportunity preflight. No dereference, network or user data.
- `tests/test_opportunity_outcomes.py`: 3 new synthetic regression methods: same approval relabelled, RFC alias cases, and dissimilar paths/query not merged.
- `tests/test_opportunity_receipt_portfolio.py`: 3 new methods for cross-opportunity receipt aliases, other-job earlier-stage reuse and query-preserving negative case.
- Local independent algorithm harness: 27 dot-path + 7 equal URI + 6 unequal URI cases passed (40 semantic checks). These do not replace repository tests or GitHub CI.
Repository verification commands: `python3 -m unittest tests.test_opportunity_outcomes tests.test_opportunity_receipt_portfolio -v`; `python3 -m unittest discover -s tests`; `python3 scripts/check_boundaries.py`; `python3 scripts/make_roadmap.py --check .`.

## Scientific and authorization limits
P0 engineering and synthetic simulation only. Syntactic alias detection does not independently verify a transfer, actual income, causal impact, or reduced human/animal suffering. D011 remains TODO until independent settlement evidence exists. No main branch edits, personal data, payments, facility control, unapproved messages or credentials. No Human in the Loop only within lawfully authorized, bounded routine tasks.
