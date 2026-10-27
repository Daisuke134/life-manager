# D014 — Linked geographic/subpopulation releases require explicit differencing review

**Date:** 2026-10-28 JST. **Task:** D014 independent, offline, synthetic P0 subtask. The canonical `docs/roadmap/tasks.json` remains the only progress registry: 113 tasks / 69 done / 41 todo / 3 blocked. D014 is **todo**, H005 remains **blocked**.

## Question → competing hypotheses → falsifiers (imozuru)

**Question:** If two public aggregate tables describe the same measure, time window and unit, but report different geographic or population scopes, can they safely be treated as wholly unrelated merely because their population metadata are not exactly equal?

- **H0 (unsafe):** exact population inequality ends the risk analysis with a generic incomparability warning. This overlooks the possible disclosure-by-differencing of a larger aggregate and its smaller subset.
- **H1 (limited):** for the same declared route, outcome, population window and unit, differing description/geography receives `CROSS_RELEASE_POSSIBLE_SCOPE_DIFFERENCING`. Families of 3–8 propagate `FAMILY_POSSIBLE_SCOPE_DIFFERENCING`. These flags assert *only a review candidate*, not actual geographic nesting, underlying identity, reconstructed private cells, or a real disclosure. **Never subtract these potentially overlapping tables.**
- **Negative controls:** unrelated window, unit, outcome or release route does *not* trigger this specific reason; identical scoped tables follow existing arithmetic checks. All output contains fixed diagnostic codes only. Permissions and impact remain false/unmeasured.

## Primary-source locators and conflicting interpretations

1. UK Office for National Statistics, *Policy on protecting confidentiality in tables of birth and death statistics*, section **R5: Disclosure by differencing**, https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/disclosurecontrol/policyonprotectingconfidentialityintablesofbirthanddeathstatistics . The original policy explicitly discusses **geographical differencing**, **linking**, and **sub-population differencing** across public tables. **Inference:** differing cohort descriptions do not by themselves eliminate a potential privacy linkage.
2. UK Government Analysis Function, *Statistical Disclosure Control for tables produced from surveys*, https://analysisfunction.civilservice.gov.uk/policy-store/statistical-disclosure-control-for-tables-produced-from-surveys/ . This official guidance warns that suppression by itself does not generally defeat differences across overlapping category definitions.
3. UK Government Analysis Function, *Statistical Disclosure Control for tables produced from administrative data*, **published 2026-08-19**, https://analysisfunction.civilservice.gov.uk/policy-store/sdc-for-tables-produced-from-administrative-data/ . This describes context-dependent disclosure risk rather than a universal threshold.

**Counterinterpretation:** two records with matching outcome/window/unit and different descriptions or geographic grades may be truly disjoint, revised, non-nested or based on different source populations. Our small schema cannot prove geographic containment or respondent identity, so it does not compute a residual, assert an incident, or approve a release. The internal `MIN_CELL=10` heuristic is **not** an ONS privacy guarantee or a legal rule.

## Exact changes and reproducibility

- `manager_core/public_aggregate_cross_release.py`: add one fixed reason code for possible linked scope while retaining `COHORT_OR_CONSTRUCT_NOT_COMPARABLE` and *no* cross-scope arithmetic.
- `manager_core/public_aggregate_release_family.py`: propagate the pairwise fixed warning without upgrading any result to proof or accepting external actions.
- `tests/test_public_aggregate_cross_release.py`: entirely fictitious geography, subpopulation and negative-control scenarios.
- `tests/test_public_aggregate_release_family.py`: entirely fictitious 3-release propagation and non-leakage assertion.

Run from `products/manager`:

```bash
python3 -m unittest tests.test_public_aggregate_cross_release tests.test_public_aggregate_release_family -v
python3 -m unittest discover -s tests -v
python3 scripts/check_boundaries.py
python3 scripts/make_roadmap.py --check
```

Hosted GitHub Actions and post-commit readback are separately verified in the execution report; this note alone does not prove tests passed. No network access, individuals, raw microdata, source download, outbound messages, money transfers, or physical effects are added. No existing task status is promoted.

## Proof boundary and mission

This increment is **P0 software/fixture evidence only**. It does not establish independent source authenticity, ethical approval, anonymisation, human/animal welfare gain, causal intervention effects, field actuation, or autonomous public publication. Original D014 requires a legitimate disclosure and rights review with a cooperating source/operator; it remains `todo`. HeartSteps H005 exact 2019 reproduction remains `blocked` rather than fabricated.

**Manager philosophy:** End suffering; improve lawful public nonpersonal macro environments for humans and animals; No Human in the Loop for routine *standing-authorized* operation, without depending on other people's credentials or facilities. Predictions and simulations are never field impact evidence.
