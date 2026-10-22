# D014 — Public aggregate disclosure research (2026-10-22)

**Status: research only; no study activation, no participant observations, no verified human impact.**

## Question
Can Manager compare openly published population indicators without treating them as direct measurements of individual suffering or intervention effectiveness?

## Primary official sources and checks
- UK Statistics Authority / ONS statistical disclosure control: https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/disclosurecontrol/policyonprotectingconfidentialityintablesofbirthanddeathstatistics . Relevant finding: publishing overlapping tabulations can disclose low counts by subtracting one table from another; complementary suppression may be required.
- UKHSA statistical data management policy, updated 2026-04-01: https://www.gov.uk/government/publications/ukhsa-official-statistics-compliance-documents/data-management-in-official-statistics-policy . Relevant finding: aggregate publication needs an assessment of re-identification from combinations of releases; table redesign, rounding and suppression are contextual controls.
- UK ICO anonymisation guidance: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/how-do-we-ensure-anonymisation-is-effective/ . Relevant finding: publicly released material must be assessed for linkage and re-identification risk, not merely for direct identifiers.
- US HHS OHRP engagement guidance: https://www.hhs.gov/ohrp/regulations-and-policy/guidance/guidance-on-engagement-of-institutions/index.html . Relevant finding: institutional involvement in human subjects research depends on actual activities and applicable rules; a software test cannot grant ethical approval.

## Distinctions to preserve
1. A public national indicator is contextual information for its stated population and collection window. It is not an estimate of Manager's treatment effect.
2. The published individual records of a public-use survey are still individual records; their availability does not satisfy an aggregate-only policy.
3. A blanket threshold (for example, 10) is a proposed preliminary Manager risk-reduction rule, NOT an anonymity guarantee or legal standard.
4. Unknown disclosure risk, incompatible cohorts, missing denominators and unavailable ethics review remain unknown or NO_ACTION.
5. No new participant collection, external messages, payments, physical actuation or operational authority is granted by this note.

## Falsification and operational next step
An apparently safe aggregate could become disclosive when cross-tabulated with another public release. A valid test therefore checks both small cells and complementary counts, but independent release-level disclosure review remains necessary. Implement a narrowly scoped metadata-only preflight with deny-by-default unknown fields and no live effect authority. Require independent source retrieval and byte verification later, separately. Retain D014 as todo until a real partner or public aggregate route meets its full original acceptance and applicable ethical requirements.

Primary source locations were directly checked on 2026-10-22; all statements are paraphrases, not long reproductions. This is an imozuru-style primary-source claim and counterexample log, not an empirical study.
