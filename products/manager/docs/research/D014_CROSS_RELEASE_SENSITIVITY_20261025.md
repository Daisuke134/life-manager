# D014 — Category sensitivity consistency across public aggregate releases (2026-10-25 JST)

**Status and scope:** A read-only, synthetic Manager D014 engineering atom, **not** D014 task completion. Canonical progress is `docs/roadmap/tasks.json`: D014 remains `todo`; H005, F004 and F007 remain `blocked`. No real participants, nonpublic records, publisher writes, permissions, outreach, transfers, equipment actions or outcomes were involved.

## Question → hypotheses → falsifier (imozuru)

**Question:** Can two apparent releases with the same population, labels and total be combined arithmetically when they *disagree about which category is sensitive*?

- **Unsafe shortcut (H0):** A sensitive flag merely means `count is None` in each release, so flags may vary whenever publication suppresses a value; equal labels and totals are sufficient to perform a cross-release subtraction.
- **Safer hypothesis (H1):** Sensitivity describes the risk/classification of a *category*, not the display status of a count. If sensitivity declarations conflict across releases, identical strings do not prove equivalent category semantics. Fail closed to independent review, without deriving an inferred hidden count.
- **Falsifier:** Fully fictional two-release partitions, each individually screenable but not approved. Release A declares alpha 60, beta/gamma withheld, all categories sensitive. Release B declares gamma 35, alpha/beta withheld, *gamma nonsensitive*. Under H1, return `CROSS_RELEASE_SENSITIVITY_NOT_COMPARABLE` and **do not** generate `CROSS_RELEASE_SINGLE_HIDDEN_CELL` or `CROSS_RELEASE_SUPPRESSION_UNDONE`. A matched-sensitivity control with the same published counts must still flag reconstruction. Neither test contains real human data.

**Implementation:** `manager_core/public_aggregate_cross_release.py` now compares same-category `sensitive` declarations before arithmetic. The existing test fixture previously derived sensitivity from suppression state; it was corrected to keep intrinsic category sensitivity fixed, plus adversarial conflict/control tests. The family-of-three-or-more screen already prevented arithmetic on inconsistent sensitivity declarations; this patch makes pair and family behavior consistent.

## Official primary-source checks (accessed 2026-10-25)

1. UK Office for National Statistics, *Policy on protecting confidentiality in tables of birth and death statistics*, https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/disclosurecontrol/policyonprotectingconfidentialityintablesofbirthanddeathstatistics — Sections on disclosure assessment and linked outputs require sensitivity-aware, contextual assessment of other released data. This official UK births/deaths policy is methodological context, **not** a universal Japanese legal threshold or a requirement that UK-specific classifications apply to Manager.
2. UK Information Commissioner's Office, *How do we ensure anonymisation is effective?*, https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/how-do-we-ensure-anonymisation-is-effective/ — Identification risk includes singling out/linkability, context and other available information. ICO marks the guidance as under review. The page does **not** certify a numeric small-cell threshold as safe.

These sources support caution and review; the specific flag-consistency rule is **our conservative engineering assumption**, not text attributed to ONS/ICO. Even matching declared sensitivity does not prove actual cohort equality or safe disclosure.

## Evidence levels and remaining original acceptance

- P0: only static/fixture evidence that a screening program detects and avoids a narrow class of false arithmetic assumptions. Unit and hosted CI results must be recorded separately after execution.
- P1/P2: no real Manager execution receipt, no independently observed external state change.
- P3/P4/P5: no independently measured human or animal welfare gain, no causal net benefit, no replication.
- Always `can_ingest=false`, `can_publish=false`, `can_execute=false`, `disclosure_certified=false`, `beneficiary_effect=NOT_MEASURED`. No automatic rights, consent, ethics, publisher identity, or release authenticity certification.
- **D014 remains todo:** externally authenticated public aggregates, applicable publisher rights, ethically approved collaboration/consent where required, and independent disclosure review are missing. **H005 remains blocked**: the original HeartSteps trial-day mapping required for exact replication is unavailable; no paper numbers are fitted or imputed. This atom neither changes Life Manager runtime nor `main`.

**Product philosophy:** End suffering by improving public non-personal macro environments, without a human in the routine permitted execution loop; avoid reliance on others' credentials/equipment and never conflate technical tests with relief from suffering.

## Hosted CI and external readback (verified 2026-10-25)

- Implementation commit: https://github.com/Daisuke134/life-manager/commit/9ee5f207a0ee4f36adc6c83066cac7d37483dc22
- Follow-up regression fixture fix: https://github.com/Daisuke134/life-manager/commit/badf014dbad669634c38e93bda4965f69bf00df2 — initially two existing tests failed because their fictional categories changed sensitivity whenever counts changed. We corrected these fixtures so that count-conflict and total-conflict tests do not inadvertently test sensitivity mismatches.
- Hosted [Manager Independent Offline Research](https://github.com/Daisuke134/life-manager/actions/runs/40145649801): **success**, 525 unit tests, 5 skipped; canonical 113-task registry consistency **PASS**. The new conflicting-sensitivity test passed.
- Hosted [Manager Phase06 Digital Environment](https://github.com/Daisuke134/life-manager/actions/runs/40145649797): **success**; no assertion of a human-impact field trial.
- Hosted [Manager EBA v0 Open Benchmark](https://github.com/Daisuke134/life-manager/actions/runs/40145649791): **success**; this is not evidence of real beneficiary impact.
- We read the four changed blobs back through the independent GitHub connector, including the new reason code, tests, source note and canonical states (69 done, 41 todo, 3 blocked). The final follow-up is docs/registry metadata only, not a new behavior claim.

Do not interpret a passing test suite as a completed D014 collaboration, a valid disclosure certificate, actual cohort identity, or a causal reduction in suffering.
