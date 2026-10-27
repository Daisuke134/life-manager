# D014 — fragment-insensitive and SHA256-case-insensitive source-alias preflight

**Date:** 2026-10-27 JST. **Scope:** D014 atomic offline engineering / synthetic P0. **Status:** new hosted CI verification pending at initial commit; original D014 acceptance remains `todo`. Exactly 113 canonical tasks: 69 done, 41 todo, 3 blocked. H005 remains `blocked` (unrecoverable 2019 study-day mapping). No real participant data, external grants, messaging, purchases, facility control or welfare intervention.

## Question → competing hypotheses → falsifier (imozuru)

**Question.** If two published statistical aggregate metadata packets identify different `source_id` and `content_sha256` values, are their URL strings necessarily different source origins even when only `#fragment` differs? Can SHA-256 hex letter case make two identical content digests appear distinct?

- **Unsafe assumption H0:** compare exact full URL strings and exact digest strings to assess overlap. This misses `https://host/release#chart-a` vs `https://host/release#chart-b`, and uppercase vs lowercase SHA-256 hexadecimal strings.
- **Conservative implementation hypothesis H1:** to screen *possible* provenance reuse, compare source IDs literally, URI references after stripping *only the fragment*, or content digests case-insensitively. Keep the URL query string distinct. This does not prove that the underlying source bytes, census population or publisher are identical.
- **Falsifiers / synthetic controls:** different source ID and different hashes with a fragment-only URL difference should raise `RELEASE_SOURCE_OVERLAP`; same hash encoded as uppercase vs lowercase should also raise it; differing `?period=...` queries with distinct source ID/hash should not trigger that particular reason; any pair in a family of 3 should propagate `FAMILY_SOURCE_OVERLAP`. All results should remain static codes without URLs, counts, person rows or authorization.

## Original sources / locator (checked 2026-10-27)

1. **IETF RFC 3986 §3.5, Fragment**, https://www.rfc-editor.org/rfc/rfc3986#section-3.5. A fragment identifies secondary content of a primary resource and is separated before the resource is dereferenced. This directly supports fragment-insensitive *possible origin* comparison, not universal payload equality.
2. **UK Office for National Statistics, Policy on protecting confidentiality in tables of birth and death statistics, R5 disclosure by differencing**, https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/disclosurecontrol/policyonprotectingconfidentialityintablesofbirthanddeathstatistics. Separate releases may interact to reveal suppressed values; independent release review is necessary. UK-specific statistical policy is methodological context, not a universally applicable legal safe threshold.

**Engineering inference rather than an official requirement:** RFC does not prescribe this Manager code; ONS does not certify source authenticity or an arbitrary `MIN_CELL=10`. URL equality (even without fragments) or SHA string equality cannot verify real bytes without fetching legally permitted data, and even equal URL origins may have changed over time. Query parameters may select distinct data and are therefore preserved; URL normalization does not follow redirects or coalesce percent encoding, hostname aliases, ports, or signed URLs.

## Code, tests and original acceptance boundary

- `manager_core/public_aggregate_cross_release.py`: `urldefrag(...).url` for public HTTPS source origin alias, case-insensitive SHA-256 metadata alias, still no network, person data, counts in output, or effect.
- `tests/test_public_aggregate_cross_release.py`: three adversarial tests for different fragments, mixed-case digest, and query-string negative control.
- `tests/test_public_aggregate_release_family.py`: one propagation test across three independent-looking releases.
- Check: `cd products/manager && python -m unittest tests.test_public_aggregate_cross_release tests.test_public_aggregate_release_family -v && python -m unittest discover -s tests -v && python scripts/check_boundaries.py && python scripts/make_roadmap.py --check`. Hosted CI result must be obtained independently, not assumed from this document.

All preflight results preserve `can_ingest=false`, `can_publish=false`, `can_execute=false`, `disclosure_certified=false`, `cross_release_independence_verified=false`, `beneficiary_effect=NOT_MEASURED`. P1–P5 evidence remains absent. D014 requires independent source/publisher verification, formal disclosure/rights review, and actual partner ethics/consent and public aggregate availability, so original acceptance is **not** satisfied. This work does not modify Life Manager runtime or main.

**Philosophy:** End suffering through lawful public non-personal macro-environment evidence; no human in the routine *authorized* loop; no dependency on other people's credentials or physical systems; distinguish engineering simulation from measured real-world changes.
