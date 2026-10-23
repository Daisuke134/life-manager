# Public-aggregate collaboration and consent protocol

**Protocol ID:** `MGR-D014-AGG-20261022-v1`. **Status: PROPOSED / NO_PARTNER / NOT_ACTIVATED.** Prepared 2026-10-22 JST / 2026-10-21 UTC. There is no signed collaboration, ethics approval or exemption determination, participant consent, new data collection or study result. This document supplies a concrete proposed agreement and data boundary; external requirements in D014 remain unresolved.

This protocol concerns optional research collaboration using public aggregates. It is not a new dependency for Manager's routine owned-internet publication or a requirement for per-run human permission. Existing public pages can operate under their established standing authority. The restrictions here apply to collecting or sharing human research outcomes and to interpreting them.

## 1. Two permitted research routes

| Route | Allowed material | Responsibility and limit |
|---|---|---|
| A — existing public aggregates | A public agency's or support organization's already published statistics, definitions, population/window, methods and license | Record the exact source and applicable reuse terms. Obtain the appropriate institutional determination if the proposed research use requires one; do not invent a need to re-consent the underlying survey or claim that public availability establishes ethics approval. No microdata, person linkage or intervention is involved. |
| B — newly produced public aggregates | A cooperating operator's consented, appropriately reviewed study results that the operator has approved and actually published | The operator handles private collection, verification, retention and withdrawal. Manager retrieves only the approved public release after disclosure review. A draft private spreadsheet, pseudonymous participant extract or email attachment is not a public aggregate. |

The [D013 map](../docs/research/MENTAL_PUBLIC_AGGREGATE_MAP.md) and [verified source registry](../docs/research/COMPLETION_PRIMARY_SOURCES_20261022.json) identify available sources. England's Community Life Survey can describe its own population; it is not a baseline or comparator for Japanese Manager visitors. The CFPB survey landing page links public-use **individual records**; these are outside this aggregate-only protocol even if direct identifiers were removed. WHO/OECD instrument documentation supplies construct definitions, not participant results. [Community Life Survey](https://www.gov.uk/government/statistics/community-life-survey-202425-annual-publication/community-life-survey-202425-loneliness-and-support-networks) · [CFPB dataset description](https://www.consumerfinance.gov/data-research/financial-well-being-survey-data/)

## 2. Agreement terms ready for partner review

The proposed purpose is to evaluate access to official support and, only where separately authorized and measured, the specified downstream outcome. It excludes diagnosis, benefit eligibility decisions, credit scoring, marketing, personalized persuasion, sale of records, training an AI model on private records and linkage with browsing or social-media traces.

Before Route B starts, the following named roles and signed responsibilities must be entered in the external study record. They are **unappointed** in this proposal; a repository author or automated test cannot stand in for them.

| Role | Required responsibility and independence |
|---|---|
| Operating organization and accountable study lead | Own lawful access, local recruitment, consent, participant support, approved collection, data retention and incident response; identify actual authority and applicable institutional requirements |
| Records custodian | Hold identity keys and private evidence in the organization's approved environment; prohibit transfers to Manager; implement withdrawal and retention decisions |
| Independent outcome analyst | Freeze the analysis before unblinding; verify source evidence under authorized access; retain missingness, negative outcomes and deviations; document conflicts |
| Independent safety reviewer | Be qualified for the intended population and mental-health concerns, able to stop the study, and independent of product shipping and success incentives |
| Institutional/ethics reviewer | Provide the applicable written approval, exemption or other determination for the actual protocol and jurisdiction; a proposed designation is not a determination |
| Public-release approver | Review confidentiality, source rights, cell disclosure and consistency with consent; sign the exact aggregate output and publication version |
| Manager maintainer | Ingest only the approved public aggregate schema; preserve provenance, units, limits and corrections; make no private-person inference |

The agreement fixes purpose, geography, population, authorized measures, contact channels, protocol/hash, incident deadlines, publication policy, retention schedule and withdrawal process. Each party may end new collection; neither may suppress an already consented null or negative result because it is unfavorable. Public disclosure may be delayed or reduced for a documented confidentiality or rights reason, with that limitation reported. Publication obligations never override participant protections.

## 3. Consent and recruitment package for Route B

Recruitment uses a public, neutral invitation from the cooperating operator, not scraped contacts or inferred vulnerability. Ordinary support, eligibility and service priority remain unchanged for nonparticipants. No enrollment, questionnaire or follow-up is enabled on the currently anonymous Manager page by this document. Compensation is absent in the current JPY 0 proposal; a later compensation arrangement requires its own lawful budget, consent wording and prospective amendment.

Use the following plain-language content in the operator's reviewed accessible consent material. Actual operator, contact and withdrawal details must be supplied before use; until then it is **not a deployable consent form**.

> We are studying whether a way of finding official support information helps people reach support. Taking part is optional. Saying no or leaving will not change your ordinary access to support or decisions about benefits. If you join the navigation study, chance assigns you to the original navigation or an official-support directory. Both retain ordinary support routes. We will explain the follow-up schedule and the financial information we ask you to verify before you decide.
>
> The operating organization keeps your identity and private records. Manager will not receive your application, bank statement, questionnaire answers or individual study history. Results may be published as reviewed group statistics, including negative or inconclusive findings. Small or identifying groups will be withheld. Published anonymous statistics may not be removable after release; the operator will explain the withdrawal cutoff and what can still be deleted or stopped.
>
> You may skip a question, report a concern or stop contact at any time. Potential burdens include time, unsuitable referrals, disappointment or distress, and the privacy risks explained in the study information. This is not clinical care, emergency monitoring, a benefit application or a promise of financial improvement. Contact the named operator for study questions or concerns and use the normal local urgent-help routes when needed.

Obtain separate, recorded choices for participation, approved local evidence verification, follow-up contact and any optional questionnaire. Explain exactly which group statistics are intended for public release and any lawful limits on deletion. Do not bundle consent with benefit access or present public reporting as consent to disclose individual records. The operator verifies understanding through an accessible explanation; no product acceptance checkbox or model inference substitutes for informed consent. The consent record and withdrawal ledger stay with the operator.

## 4. Collection, minimization and retention

Only the cooperating operator collects the minimal fields required by the frozen study protocol. An identity/contact key is separated from the analysis file. Private files never enter this Git repository, issue trackers, model prompts, telemetry, public build logs or Manager storage. No free-text participant narratives, fine-grained locations, exact personal event timestamps, contact lists, private screenshots, financial account identifiers or item-level questionnaire responses are ingested by Manager.

The proposed operational schedule is: contact data kept only through follow-up and resolution of participant requests; destroy the study contact/identity link within 90 days after the final follow-up unless the documented applicable retention requirement prevents it. The partner must freeze the actual local evidence-retention and deletion schedule before consent, including any mandatory longer retention; do not promise deletion that the operator cannot perform. Manager retains only the public aggregate version, source URL, retrieval time, content hash, methods and correction history. Ending collaboration ends new collection and study-specific contact, not ordinary public service access.

## 5. Public release schema and disclosure review

The operator publishes a static, versioned aggregate release on its authorized public research or institutional surface. Manager reads that public URL and verifies the recorded hash. It never requests unpublished rows to reconcile an aggregate. A public release must carry these fields or explicitly explain why one is withheld:

| Field group | Required content |
|---|---|
| Provenance | Release ID/version/date, official URL, publisher, content SHA-256, protocol/registration reference and applicable reuse terms |
| Scope | Population, geography at an approved coarse level, inclusion/exclusion criteria, recruitment and observation window; `context_only` or `study_outcome` relation to Manager |
| Units | Assignment/analysis unit, group label, exact outcome definition, original unit and direction, instrument/version/mode where applicable |
| Denominators | Assigned, observed and missing counts, with withdrawal and unresolved verification distinguished when safely reportable; source weights and coverage for surveys |
| Result | Prespecified estimate and uncertainty/method; missing-data sensitivity; costs and harms; no conversion into an invented common welfare score |
| Integrity | Allocation/comparator limitations, contamination, deviations, operator and independent-review attestations, conflicts and analysis-code reference |
| Disclosure | Applied suppression/rounding, reason for withheld cells, public correction/retraction contact and relation to any earlier release |

**Proposed minimum disclosure rules:** do not release a sensitive subgroup with fewer than 10 observed units or a sensitive nonzero event cell of 1–9; suppress complementary cells when totals would reveal the suppressed value. These are minimum operational rules, **not an anonymity guarantee**. The independent release reviewer may require larger cells, coarser units or full withholding for rare events, outliers, geography, external linkage or overlapping releases. Zero cells also require review when they expose membership or sensitive attributes.

Publish only the two preregistered overall arms in the first study; no location, age, diagnosis or financial-hardship cross-tabs. Financial mean/interval display may be rounded to JPY 100 after the independent analysis, with the rounding method stated; rounding never cures an otherwise identifying release. Do not publish extrema, individual histories, dates, small-sample breakdowns or continuous dashboards. Use one final outcome release and a versioned correction process rather than repeated overlapping extracts that enable differencing. Safety-state notices may appear immediately without case counts or identifying details.

The partner analyst can examine authorized private records for safety and inference while Manager receives only the public disposition and approved aggregate. An independently attested calculation is not full public reproducibility of private data; the final report must state that limit. If privacy protection prevents adequate uncertainty or denominators from being published, Manager labels the result **INSUFFICIENT_PUBLIC_EVIDENCE**, not zero benefit or zero harm.

## 6. Interpretation and instrument boundary

A public survey aggregate describes its stated population and window. It cannot be joined to Manager traffic to infer an individual's loneliness, disability or financial distress. Cross-population before/after comparisons are descriptive unless a separately defensible causal design exists. Service uptake, perceived support, financial receipt, loneliness and mental wellbeing are separate outcomes. Preserve question versions, scale direction and source weighting; do not pool incompatible scores.

WHO-5's official 2024 instrument describes a two-week self-report construct and a raw 0–25 scale or transformed 0–100 score; the document's CC BY-NC-SA 3.0 IGO conditions do not establish permission for commercial electronic use here. ONS distinguishes the direct loneliness item from the three-item score; the OECD guidelines distinguish life evaluation, affect and related constructs. These distinctions determine what a collaborator may report, not a license to administer forms or infer scores from behavior. [WHO-5](https://www.who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01) · [ONS guidance](https://www.ons.gov.uk/peoplepopulationandcommunity/wellbeing/methodologies/measuringlonelinessguidanceforuseofthenationalindicatorsonsurveys) · [OECD 2025](https://www.oecd.org/en/publications/oecd-guidelines-on-measuring-subjective-well-being-2025-update_9203632a-en.html)

Questionnaire deployment requires the exact instrument/version, localization validity, rights, administration mode, scoring and consent to be cleared within the actual study. This protocol reproduces no instrument items and grants no clinical screening authority. The [safety protocol](MENTAL_OUTCOME_SAFETY_AND_INDEPENDENT_REVIEW.md) governs uncertainty, harm and independent assessment.

## 7. Activation, rejection and corrections

Route B remains inactive until the operator agreement, appropriate ethics determination, consent package, local data plan, independent reviewer, protocol freeze and disclosure-approved release plan exist. The actual registration must record their dates and scope without publishing private participant records. This is a single prospective research activation, not per-run approval for routine digital operations.

Reject an incoming asset if it contains private or individual-level data, lacks a legitimate public publisher or reuse basis, has an unclear unit/denominator, conflicts with consent, has inadequate disclosure control, or invites unsupported mental/financial inference. Do not download the records first to see whether they can be anonymized. On discovery of an accidental private disclosure, stop ingestion and publication, restrict further exposure, notify the operator through the agreed incident channel and follow the independent incident response. Do not mirror the material in an issue or model prompt.

Corrections preserve the prior public version identifier, explain the changed result or provenance, and propagate a retraction or qualification to Manager's claims. Safety concerns trigger **NO_ACTION** for the optional study while independent assessment is pending. Current state remains **NO_PARTNER / NO_CONSENTED_COHORT / NO_NEW_PUBLIC_OUTCOME_DATA**. This document does not update task status or claim D014's external conditions are satisfied.

## 8. Offline metadata preflight (2026-10-23)

[`preflight_public_aggregate`](../manager_core/public_aggregate_preflight.py) is a self-contained **offline metadata-only** reject/review gate; [15 synthetic regression cases](../tests/test_public_aggregate_preflight.py) cover small/sensitive cells, zero cells, suppressed complements, table consistency, microdata rejection, source rights and unverified Route B consent. The code uses the existing `Source` rights/privacy contract and never fetches, caches or publishes a human record, public aggregate or individual response. It returns fixed reason codes without group labels, counts or source text. One suppressed cell can be reconstructed by subtracting the other cells from an exact total, so a size threshold alone is insufficient. See the [2026-10-23 primary-source and counterexample trace](../docs/research/D014_METADATA_GATE_RESEARCH_20261023.md).

A `PRELIMINARY_METADATA_ONLY` output **never** sets `can_ingest`, `can_publish`, `can_execute`, `disclosure_certified`, `source_bytes_verified`, `publisher_identity_verified`, `consent_or_ethics_approved` or `causal_effect_verified` to true. Independent verification of actual publisher, rights, entire overlapping publication history, disclosure and (for Route B) real institutional ethics/consent obligations is required. The original D014 task remains `todo`; the additional code is engineering preparation, not collaborator activation, not a new authority and not evidence of reduced human or animal suffering.
