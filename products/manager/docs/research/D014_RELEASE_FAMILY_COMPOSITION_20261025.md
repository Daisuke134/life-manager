# D014 — Multiple-release arithmetic composition screening (2026-10-25 JST)

**Scope:** Manager independent product; metadata-only source screening, no participant records. **SSOT:** products/manager/docs/roadmap/tasks.json remains unchanged. D014 remains todo because original collaboration, consent/ethics, genuine publisher release and independent disclosure review are missing. H005 remains blocked because the original HeartSteps 2019 study-day mapping cannot be verified; no paper results were fitted.

## Question → hypotheses → falsification (imozuru method)

Question: Can three or more nominally consistent aggregate releases reconstruct a suppressed value even if no single pair leaves exactly one suppressed category?

- H0 (unsafe shortcut): checking each publication, or each pair's final residual alone, is enough to clear a family of tables.
- H1 (synthetic arithmetic counterexample): the union of three or more compatible partition tables can disclose the final withheld category, despite each table separately hiding multiple cells and each pair still hiding two categories. Our prior pairwise screen already detects some suppression exposure, but not the additional unique three-way residual.
- Alternative: labels, time frames, denominators and sensitivity may differ despite similar appearance. Declared equality is not proof of the same underlying cohort. When scopes, categories, totals, counts or sensitivity flags disagree, do not subtract.

## Official primary-source locators (reviewed 2026-10-25)

1. UK Office for National Statistics, *Policy on protecting confidentiality in tables of birth and death statistics*: https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/disclosurecontrol/policyonprotectingconfidentialityintablesofbirthanddeathstatistics . Official policy discusses linked tables undoing suppression and secondary suppression to prevent inference from totals. This is a UK birth/death policy, not a universal Japanese legal rule.
2. ONS, *Statistical disclosure control*: https://www.ons.gov.uk/aboutus/transparencyandgovernance/datastrategy/datapolicies/statisticaldisclosurecontrol . The official policy requires contextual examination of output disclosure and audit trails across datasets. This is external methodological guidance, not a Manager approval.
3. UK Information Commissioner's Office, *How do we ensure anonymisation is effective?*: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/how-do-we-ensure-anonymisation-is-effective/ . Official guidance describes linkability and mosaic/jigsaw risks; does not specify a safe universal cell threshold and may be revised.

## Technical atom + synthetic falsifier

- New pure function manager_core/public_aggregate_release_family.py::preflight_release_family checks a bounded list of 3–8 metadata packets. It reuses the existing exact-schema, public-source validation and pairwise risk screens, then checks consistent category/denominator declarations and whether combining all compatible releases can reconstruct a remaining suppressed category. It emits fixed reason codes only.
- Five **fictional** categories have counts 15, 15, 20, 10 and 40. Release A hides alpha, beta, gamma. Release B hides alpha, beta, delta. Release C hides alpha, gamma, delta. Each individual release hides three categories, each pair still hides at least two, yet the three combined leave just alpha suppressed. The code detects the reconstructable residual but NEVER prints that value.
- New tests/test_public_aggregate_release_family.py adds 12 adversarial tests for this arithmetic, unresolved hidden cells, cross-cohort differences, categories, totals, counts, sensitivity, source overlap, prior member/pair risk, untrusted input and no side-effect authority. All inputs are synthetic and contain no participant rows.

## Limits and follow-ups

Narrow algebraic screening is not disclosure certification. MIN_CELL=10 is a heuristic, not a legal or scientific anonymity guarantee. Real releases, auxiliary datasets, person-level linkage, publisher identity, applicable law, partner consent and ethics are not assessed. All authority flags remain false and beneficiary_effect is NOT_MEASURED. No live intervention, financial effect, animal or human welfare effect or new publishing is claimed. D014 remains todo; H005, F004, F007 remain blocked as in canonical tasks.json. The purpose remains End suffering through public non-personal macro-environment work without a human in the routine execution loop.
