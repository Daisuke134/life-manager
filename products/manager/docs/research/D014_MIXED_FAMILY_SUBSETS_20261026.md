# D014 — mixed-family comparable-subset disclosure screening (2026-10-26 JST)

## Question → competing hypotheses → falsifier (imozuru)

Question: If a batch of 4–8 public aggregate tables contains an unrelated release, can this unrelated member hide an arithmetic disclosure among three or more otherwise comparable releases?

- Unsafe H0: once the *whole* batch differs in cohort, total or category declaration, no multi-table reconstruction check is meaningful.
- Narrow H1: unrelated members must not authorize subtraction across cohorts, but they also must not prevent a separately compatible subset from being screened for reconstructable suppressed categories.
- Synthetic falsifier: three fictional same-cohort releases with total 100 each reveal different subsets of five cells. Any pair leaves two cells suppressed, while the triple leaves exactly one suppressed. An unrelated fourth release has a different time window or denominator. The prior full-family scan reported that the four tables were incomparable and never evaluated the valid three-member subset.
- Counterexample guard: if the only candidate third release conflicts in a visible cell, it must NOT be used to derive a suppressed count. Two compatible releases plus two unrelated releases do not form a valid three-member subset.

## Primary-source locators (official publications, reviewed 2026-10-26)

1. UK Office for National Statistics, Policy on protecting confidentiality in tables of birth and death statistics: https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/disclosurecontrol/policyonprotectingconfidentialityintablesofbirthanddeathstatistics . The summary and practical recommendations warn about combining outputs with other information, differencing, and maintaining a release audit trail. The document applies specifically to births/deaths in England and Wales; it is NOT a Japanese universal law or a Manager disclosure certification.
2. UK Information Commissioner's Office, How do we ensure anonymisation is effective?: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/how-do-we-ensure-anonymisation-is-effective/ . Its linkability and mosaic/jigsaw discussion explains how separate releases may increase identification risk. It does NOT establish that a minimum published-cell count is universally safe.

## Implementation atom

- In manager_core/public_aggregate_release_family.py, preserve existing whole-batch and pair checks; add bounded enumeration of proper subsets containing at least three releases. Within each subset, perform arithmetic ONLY when population, outcome, route, categories, total, sensitivity and all shared observed counts agree as declarations.
- Refuse arithmetic for noncomparable declarations; emit fixed reasons for suppressed cells exposed, uniquely reconstructable final hidden cell, small hidden remainder and inconsistent totals. Never output numerical reconstructions, sensitive categories, source identifiers, counts or URLs.
- Add four all-fictional regression tests: unrelated cohort, different denominator, contradictory released values and fewer than three comparable releases. Exercise release-order invariance and no disclosure or publication authority.
- Max family size remains eight; there is no new network access, participant data, execution capability, payment verification or publisher review.

## Evidence levels / explicit non-achievements

Only P0 synthetic software behavior is being tested. No real human/animal welfare effect (P3), causal intervention benefit (P4), authorized real action (P1), independently measured external change (P2), identity clearance, consent, ethics approval or public aggregate publication is asserted. Screening does not establish that apparently equal population descriptions refer to the same underlying records. All can_publish, can_ingest and can_execute flags remain false; outcome stays NOT_MEASURED.

Canonical tasks.json is intentionally unchanged: D014 original collaboration/ethics and public evidence acceptance remains todo; H005 original HeartSteps 2019 exact reproduction remains blocked, as do F004 and F007. No changes to main, Life Manager runtime, credentials, personal records or equipment.

Verification command on Manager branch: python -m unittest discover -s tests -v, python scripts/check_boundaries.py and python scripts/make_roadmap.py --check. Record actual hosted CI outcome and commit SHA separately rather than preclaiming test success.

Mission: End suffering via lawful public non-personal macro-environment improvements, no human required for routine actions within standing authorization. Privacy checks are a necessary safeguard, not proof of an actual blessing.
