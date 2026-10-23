# Optional first human-outcome study: official financial-support navigation

**Protocol ID:** `MGR-U004-NAV-20261022-v1.1`. **Status: PROPOSED / NOT_REGISTERED. Participants enrolled: 0. Randomized units: 0.** Prepared 2026-10-22 JST / 2026-10-21 UTC; metadata corrected 2026-10-23 UTC. There is no appointed study operator, partner, ethics determination, participant consent, registration receipt or human-outcome dataset. All sample sizes and windows below are proposed design parameters, not observations.

This is a preregistration-ready **optional human-outcome evaluation** of the [first use](../docs/product/FIRST_WEDGE.md), whose technical selection is accepted but whose human value remains unvalidated. It creates no additional requirement for routine releases on the already authorized owned internet surface. Ordinary publication continues under the existing standing authority, scope and release controls without a partner or per-run human approval. Recruiting people, collecting private outcomes and claiming human effects are separate activities; none is authorized by this document.

U002 is accepted for five published historical interview findings, and U003 is accepted for the bounded technical maintenance selection. Neither acceptance establishes current local demand, human-study cooperation or participant consent. U004 is not completed by writing this proposal. This document does not replace the [F002 campaign protocol](PREREGISTRATION.md), its JSON, or its frozen hash: that design has 40 hypothetical campaign clusters and a donation outcome. Here the unit is one household represented by one consenting adult, the proposed N is 120, and the outcome is net received support. These differences are a versioned proposal for the supplemental internet lane, not a silent amendment of F002 or the original financial-transfer and indoor-environment roadmap.

**Version 1.1 correction:** the prior v1 bytes remain available at [research commit 29aebf021](https://github.com/Daisuke134/life-manager/blob/29aebf021e141eceded574d1831fab90fcadd5e6/products/manager/pilot/FIRST_STUDY.md), SHA-256 `4051aa793c52eca2cec2e10f1bad0d037d86d248e111b28d8c8d7ac8a80139dd`. This correction updates only the U002/U003 status and version metadata. The study design, success definition, proposed N and windows are unchanged. No assignments have occurred and no human-outcome dataset has been viewed. The updated local manifest is not an external registration receipt; U004 remains todo.

## 1. Question, contrast and estimand

Among eligible adults seeking financial-support information in one operator's agreed Japanese service area, does access to Manager's attributed official-support directory change the mean net legitimate financial support received over 58 days, compared with the original navigation?

The primary estimand is the intention-to-treat difference, in **JPY per randomized household over 58 days**, between assignment to the directory and assignment to the original navigation. It concerns the enrolled population and this one intervention version. It is not a population poverty estimate, a mental-health effect, an agent-revenue measure, or a universal welfare score.

The intervention follows [INTERNET_FIRST_TRIAL_DESIGN.md](INTERNET_FIRST_TRIAL_DESIGN.md): ordinary navigation is the **NO_ACTION** comparator and the treatment is official-support navigation. This proposal preserves the earlier 14-day baseline, 28-day exposure and 30-day settlement/follow-up windows. A longer settlement window would require a new prospective version before assignment; unresolved benefits at day 58 are not retrospectively counted as received.

| Parameter | Proposed fixed value |
|---|---|
| Target | 120 households; one consenting adult per household; 60 assigned to each arm |
| Geography/currency | One Japanese service area documented in the prospective registration; JPY only |
| Recruitment | At most 28 consecutive days from a prospectively dated opening; stop at 120 eligible assignments or day 28, whichever comes first; do not extend because results look uncertain |
| Baseline | Days −14 through −1 relative to assignment, obtained retrospectively with consent before assignment |
| Intervention | Day 0 through day 27; 28 days of access to assigned navigation |
| Settlement/follow-up | Day 28 through day 57; final assessment at 58 elapsed days, with a ±3-day contact window that does not extend the eligible transaction window |
| Maximum planned calendar span | 28-day recruitment plus 58-day follow-up for the last entrant; baseline records precede each assignment |
| Paid-spend authority | Incremental paid spending ceiling JPY 0 under the current wedge; this is not a claim of zero research, compute or human-time cost |
| Human-facing implementation | No study feature is enabled by this document; only a separately authorized, consented study wrapper may use assignment or follow-up |

## 2. Eligibility, allocation and equal access

An eligible participant is aged 18 or older, is resident in the registered service area, states that they are presently seeking official financial-support information, can understand the approved consent material, and is not already enrolled through the same household. Administrative benefit eligibility is not assumed from their statement and is not decided by Manager. The independent operator checks inclusion without sending identities, address details, account details or household records to Manager.

Exclude **before randomization**: lack of valid consent, duplicate household enrollment, residence outside the registered service area, inability to use any offered accessible consent format, or an immediate support need that the responsible professional determines makes research participation inappropriate. Such a person retains ordinary service access and receives the operator's normal support process. Do not use a model-generated diagnosis, browsing history, inferred poverty or a questionnaire score as an eligibility rule. Record aggregate exclusion reasons without private case narratives.

Use one persistent operator-issued study ID per household, with the identity key held only by the operator. An independent allocator generates a concealed 1:1 randomized sequence in permuted blocks of undisclosed size 4 or 6 and sets the existing GrowthBook assignment mechanism to that sequence. The allocator's sealed seed, sequence hash and implementation version are lodged before first exposure; the seed remains undisclosed during recruitment. Do not assume the existing synthetic SDK demonstration is this real allocation. Repeat visits and multiple devices keep the original assignment through the operator's consented mechanism; no fingerprinting or cross-site identity inference is introduced.

| Arm | Offered experience | What remains available |
|---|---|---|
| Directory, n=60 proposed | The frozen, clearly attributed official-support navigation and its ordinary accessibility features | Original services, official destinations, urgent-help information and the right to leave |
| **NO_ACTION**, n=60 proposed | The frozen original navigation, with the same study contact and consent surfaces | All ordinary support and urgent-help routes; no service, benefit or eligibility decision is withheld |

Freeze the exact two page versions, catalog, official destination list and assignment implementation in the actual registration. Treatment does not include applications, transfers, personalized persuasion, repeated nudges, clinical advice or third-party account writes. Safety-critical corrections may occur under existing release authority; record them as a protocol deviation and assess whether the contrast remains interpretable. The study must never prevent a necessary correction. Crossovers and outside help are recorded voluntarily and retained in the assigned arm; they are not post hoc exclusions.

## 3. Primary endpoint and verification

For household *i*, define `Y_i = eligible_support_received − refunds − verified_access_expenses − documented_displacement`, in JPY during the 58-day window. The **primary denominator is every randomized household**, including nonusers, crossovers and participants who stop using the page. One household appears once.

- **Eligible support received:** actually settled, legitimate public or nonprofit financial grants/benefits from the prospectively frozen service catalog. Count eligible receipts from any route in both arms, including routes found without Manager. Exclude pending approvals, loans, the study sponsor's own payments, research compensation, agent revenue, private gifts and hypothetical future savings. The registration must identify catalog programs and treatment of recurring payments before enrollment.
- **Refunds:** returned, reversed or recovered amounts from those receipts during the same window; unresolved recovery risk remains separately flagged at cutoff.
- **Verified access expenses:** actual out-of-pocket fees, transport, document costs and other predeclared access expenses supported by the operator's approved verification procedure. Do not price time using an invented wage; report time separately in minutes.
- **Documented displacement:** amounts of previously received financial support actually lost during the window because of the newly received support, as confirmed by the responsible operator. Uncertain interactions are reported as unknown and in sensitivity analysis, not silently set to zero.

The independent operator verifies evidence locally using consented administrative records or appropriately redacted participant evidence. Manager receives no statements, account records, applications, screenshots, names or private event rows. A no-receipt value of zero requires a completed ascertainment indicating no eligible receipt in the window. Absence of a reply or receipt is **missing**, not zero. If an expense or displacement component is unknown, the net endpoint is incomplete even when a gross receipt is verified. Report gross receipts and component completeness separately.

The official [MHLW overview](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000059425.html) supports the choice of a service landscape; it supplies neither participant eligibility nor Manager outcomes. The distinction between a defined transaction and an intermediate click follows the [GOV.UK completion-rate guidance](https://www.gov.uk/service-manual/measuring-success/measuring-completion-rate). These sources do not validate the numerical assumptions in this proposed trial.

## 4. Secondary observations and harms

Secondary outcomes are exploratory and reported separately: a verified completed support step by day 28 and day 58; accepted referral or completed application, each with its own definition; navigation-task completion and time; actual out-of-pocket expenses; participant time; unresolved claims; and implementation/research resource use. A click, application, accepted referral and received benefit are different endpoints. For rates, publish the assigned denominator, observed denominator, numerator and missing count where disclosure review permits.

Collect voluntary safety reports at days 7, 28 and 58 through the operator, with the same contact opportunities in both arms. Track unsuitable or inaccessible referrals, avoidable delay, unexpected charges, fraud exposure, privacy incidents, distress, perceived pressure, service displacement and complaints. Participants may report a concern or stop at any time. Contact burden is capped at these three planned follow-ups plus one neutral reminder per missed follow-up; no automated persuasion or repeated prompts. Report nonresponse and unknown harm ascertainment explicitly.

Mental-health scales and other questionnaires are **not administered in version 1**. The [measurement map](../docs/research/MENTAL_PUBLIC_AGGREGATE_MAP.md) identifies possible constructs, including WHO-5 and CFPB financial wellbeing, but rights, local validity and a separate consented protocol are unresolved. A financial receipt does not establish improvement in either construct.

## 5. Analysis and sample-size limits

The analysis unit is the randomized household. The one primary comparison is the difference in unadjusted arm means of `Y`, with a two-sided 95% Welch confidence interval, descriptive distributions and arm sample sizes. Perform a prespecified two-sided randomization test using the actual blocked allocation scheme and 100,000 valid reallocations; retain the seed in the analysis record. The independent analyst uses established statistical software and freezes its version and analysis script before outcome unblinding. No model-selected adjustment, subgroup search or alternative endpoint becomes the primary result after inspection.

If all primary outcomes are complete and the allocation remains valid, report the intention-to-treat estimate, confidence interval and test. Otherwise label the full primary estimand **NOT_IDENTIFIED_FROM_COMPLETE_OUTCOMES** and report why. Available-case means and intervals are explicitly secondary and are not relabeled as the complete intention-to-treat effect. With fewer than 120 assignments, analyze the actual enrolled cohort after the fixed recruitment window and report the shortfall; do not add fictitious units.

For missing outcomes, publish counts and reasons by arm, including withdrawal, no response, unverifiable receipt, unresolved expense and unresolved displacement. Provide a prespecified sensitivity table assigning each arm's missing outcomes its observed mean plus offsets of JPY −100,000, −50,000, −10,000, 0, +10,000, +50,000 and +100,000, taking every pair of arm offsets. Recompute the all-assigned mean contrast with those assumed values. This is an assumption grid, not imputation proof or an identified bound. If an arm has no observed mean, omit the grid and report the primary effect as unestimable. Missingness due to harm or withdrawal must not be treated as random by default. No last-observation-carried-forward and no replacement of missing net benefit with a verified gross amount.

**N=120 is a feasibility assumption, not an evidence-based powered sample size.** With 60 independent units per arm, a normal approximation for two-sided alpha .05 and 80% power gives a detectable standardized difference of `(1.96 + 0.84) × sqrt(1/60 + 1/60) ≈ 0.51` outcome standard deviations. At 20% outcome loss, 48 observed units per arm would give about 0.57 standard deviations under the same simplified assumptions. These are calculations, not claims about the actual distribution: the baseline JPY variance, skew, service capacity, interference and plausible effect are unknown. The design is likely unable to resolve modest financial effects. No JPY detectable effect, successful efficacy trial or no-harm conclusion is promised.

Any power revision based on independently obtained, outcome-blinded feasibility information must produce a new protocol version and public hash **before first assignment**. No efficacy or futility looks alter N or duration. Secondary outcomes and exploratory subgroups carry no confirmatory claim; small or identifying cells are withheld. A positive estimate still requires scrutiny of missingness, harms, costs, interference and external validity. It is not automatic P4/P5 completion. Null, negative and inconclusive results receive the same release process.

## 6. Stops, deviations and study oversight

The [mental-outcome safety protocol](MENTAL_OUTCOME_SAFETY_AND_INDEPENDENT_REVIEW.md) controls study pauses and independent review. For this optional study, pause further assignment and study-specific exposure on: invalid or withdrawn study authority; inability to obtain consent; a material privacy or security incident; one serious event plausibly related to study participation; materially misleading or inaccessible support information; allocation corruption; or outcome verification becoming unavailable. Preserve ordinary access to verified services. A participant-requested stop is immediate for that person and never affects benefits.

A trained independent reviewer evaluates possible harm; Manager cannot diagnose, dismiss the event or approve its own restart. If causality or safety cannot be determined, study-specific action remains **NO_ACTION**. Suspension is not suppression of a negative result. Publish a redacted deviation and disposition record with the final report. Details, timelines and resumption criteria are in the linked safety protocol, which does not govern unrelated routine digital releases.

## 7. Prospective freeze and operational record

The proposal's exact bytes are bound in [RESEARCH_PROTOCOLS_20261022.sha256](RESEARCH_PROTOCOLS_20261022.sha256). From the repository root, verify with:

```sh
sha256sum -c products/manager/pilot/RESEARCH_PROTOCOLS_20261022.sha256
```

A local hash is not an external preregistration receipt. Before optional human enrollment, the responsible study operator must publish a dated registration containing this protocol/version/hash and the linked protocol documents, operator and independent-review roles, appropriate ethics determination, exact recruitment/consent materials, locale/program catalog, two frozen surfaces, sealed allocation commitment, outcome-verification specification, analysis code/version, and actual calendar opening/cutoff dates. The [collaboration protocol](PUBLIC_AGGREGATE_COLLABORATION_PROTOCOL.md) specifies who may handle private records. Missing required operational facts mean **NO_HUMAN_STUDY**, not a placeholder approval.

Publish corrections as a new version linked to the prior hash, with reason and whether assignment or outcome viewing had occurred. Preserve the original and report deviations; never rewrite the success definition after viewing results. The existing F002 preregistration and canonical task registry are unchanged. Current truthful outputs remain **NOT_REGISTERED / 0 participants / human outcomes NOT_MEASURED**.

## Source provenance

The source-specific claims above derive from the already verified [primary-source registry](../docs/research/COMPLETION_PRIMARY_SOURCES_20261022.json), principally `MHLW-SUPPORT`, `GOVUK-COMPLETION`, `CFPB-SCALE` and the WHO/OECD measurement entries, retrieved 2026-10-21 UTC. The population, numerical design, analysis choices and operational thresholds here are explicit Manager research proposals; no cited organization has endorsed this trial.
