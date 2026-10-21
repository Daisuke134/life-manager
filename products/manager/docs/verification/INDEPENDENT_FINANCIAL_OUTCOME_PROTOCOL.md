# Independent financial-outcome verification procedure

**Protocol ID:** `MGR-F006-OUTCOME-20261022-v1`. **Status: PROPOSED / NO_OBSERVED_COHORT. Human financial outcome: NOT_MEASURED. Harms completeness: UNKNOWN_HARMS.** Prepared 2026-10-22 JST / 2026-10-21 UTC. This supplies the procedure requested by F006.E05 and F006.E07 in the [detailed Phase06 map](../roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md). It is not a financial result or a completion of F006.

The procedure applies when an independently observable human financial outcome exists. It does not restrict routine owned-internet releases under standing authority or make a partner mandatory for digital delivery. A navigation artifact can continue to be built, released and independently read back without a human study. P3/P4 claims require a different evidence record.

## 1. Reuse the defined protocols

The optional [FIRST_STUDY](../../pilot/FIRST_STUDY.md) specifies the proposed population, N=120 household assumption, 1:1 NO_ACTION contrast, 14-day baseline, 28-day navigation exposure, 30-day settlement/follow-up, primary net-receipt formula and missing-data analysis. It is **NOT_REGISTERED**, has **0 participants**, and does not replace the frozen F002 campaign design.

The [public-aggregate collaboration protocol](../../pilot/PUBLIC_AGGREGATE_COLLABORATION_PROTOCOL.md) governs voluntary consent, private evidence custody and release of disclosure-reviewed aggregates. The [independent safety protocol](../../pilot/MENTAL_OUTCOME_SAFETY_AND_INDEPENDENT_REVIEW.md) governs adverse experiences, uncertain harm and study stopping. This document specifies verification and economic accounting; it introduces no competing consent process or second task registry.

## 2. Admissible outcome routes and source authenticity

| Route | Necessary independent evidence | What it can establish | Reject or qualify when |
|---|---|---|---|
| Official program or payment settlement | The lawful operator verifies final receipt, recipient/household linkage, program, currency, amount, date, status, refunds and cutoff using authorized official records | A defined received-support observation; comparison and costs remain separate | Approval only, pending transfer, authorization without settlement, duplicated ledger sides, unverified recipient receipt or transaction outside the window |
| Voluntarily supplied financial receipt | The participant permits the independent operator to corroborate a genuine receipt locally against the program/provider and record its verification method | A verified receipt if corroborated; otherwise explicitly participant-reported, unverified support | Image or claim cannot be authenticated, identity/consent mismatches, missing date/currency, edited evidence, unresolved refund or duplicate receipt |
| Voluntarily administered valid financial-wellbeing measure | The operator verifies informed consent, rights, exact instrument/version, appropriate language/setting, administration mode, scoring and observation window | That construct in its original scale; it is not cash receipt or income | Model-generated answers, inferred score, wrong scoring table, unsupported translation, unknown mode/version or unapproved electronic use |
| Public official aggregate | Authentic agency/organization release, population/window, denominators, methods, version, uncertainty and reuse terms | Its stated aggregate; `context_only` unless it is actually linked to the registered study | Population mismatch, unsupported ecological comparison, unobserved exposure or claims that a national trend is Manager's effect |

A matching URL or content hash establishes retrieved-byte identity, not the truth of settlement or the independence of the publisher. The verifier must confirm the publisher's official role, the record's origin and final state, the subject/program relationship, and separation from the Manager execution log. A separately named endpoint operated by the same actor is not automatically independent. Record conflicts and unavailable checks.

For the optional study, private verification stays with the cooperating operator. Manager receives only a signed or institutionally attributable, disclosure-approved public aggregate and its verification-method description. Manager never acquires participant bank statements, application records, contact details or item-level questionnaire answers. If public disclosure cannot support the claimed verification, label the evidence limit; do not request the private rows as a workaround.

The [CFPB scale](https://www.consumerfinance.gov/data-research/research-reports/financial-well-being-scale/) and [official scorecard](https://files.consumerfinance.gov/f/documents/bcfp_fin-well-being_full-scorecard.pdf) distinguish financial wellbeing from income; the full score conversion depends on administration mode and age band. Raw response totals are not currency or percentages. The [MHLW overview](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000059425.html) describes support programs but does not verify an individual receipt. These primary sources and interpretation limits are recorded in the [verified source map](../research/COMPLETION_PRIMARY_SOURCES_20261022.json).

## 3. Mandatory observation record

Before examining results, freeze the outcome definition and its relation to the registered protocol. The public evidence record must retain or explicitly mark withheld/unknown:

- **Population and unit:** geography, inclusion/exclusion, assignment unit, analysis unit, eligible population and actual enrollment; household outcomes cannot be counted again for each member.
- **Denominators:** assigned, exposed, observed and missing units by arm, with nonusers, crossovers, failed applications and dropouts retained in the appropriate counts. No fictional or inferred beneficiary count.
- **Exposure:** frozen page/catalog version, assignment, available access, actual observed use where consented, contamination and implementation deviations. Assignment is not equivalent to use.
- **Time:** baseline, exposure, settlement cutoff and follow-up dates, including pending claims and after-cutoff receipts. Do not stretch the cutoff after seeing an attractive delayed payment.
- **Measurement:** original currency or scale, score version/method, gross components, net formula, costs, missingness, evidence source and verification level.
- **Inference:** comparator, estimator, uncertainty, selection and spillover limits, analysis version, preregistration reference and independent review.

An outward click is a navigation event. An application or approval is a service-process event. A settled payment and a validated wellbeing score are distinct outcomes. Follow the [GOV.UK transaction-definition guidance](https://www.gov.uk/service-manual/measuring-success/measuring-completion-rate) for explicit starts, completions and failed attempts; do not redefine the endpoint as whichever event the site can log.

## 4. Costs, displacement and harms ledger

Maintain a prespecified ledger in the outcome's original units. Report transfers received by a household separately from any economy-wide wealth claim: a benefit can improve recipient resources without creating the transferred amount as new aggregate wealth. No issued token, sponsor promise or agent revenue becomes a beneficiary outcome.

| Component | Required observation and denominator | Treatment when absent or uncertain |
|---|---|---|
| Receipt, refund and fee | Confirmed JPY per assigned household, status/cutoff, net of reversals and declared program/transaction fees; no double counting | Incomplete component makes the net endpoint incomplete; retain verified gross amount separately |
| Displaced support/access | Documented loss of previous benefits, diverted donations/resources, queue or capacity displacement where relevant; distinguish direct measured loss from plausible unobserved externality | Mark unresolved displacement and apply prospective sensitivity assumptions; no default zero |
| False referral or denied access | Wrong program/destination, failed eligibility assumption, denial, repeated application or unnecessary travel; observed affected units / assigned and assessed units | Report unascertained cases and attribution limits; click completion is not successful access |
| Time and effort | Participant and operator minutes for navigation, applications, evidence verification, follow-up and correction; study burden separate from intervention burden | Missing time remains missing; monetary conversion only with a separately justified, prospectively fixed rate |
| Compute and infrastructure | Actual metered usage and attributable provider cost where available; CI/API/hosting units and allocation method; distinguish free-tier price from consumed resources | Unknown use/cost is not zero; avoid charging the same shared cost to every household |
| Research and human review | Staff/reviewer time, recruitment and measurement costs; distinguish fixed study costs from ongoing delivery | Preserve these costs even with JPY 0 incremental spending authority; unpaid time is not zero resource cost |
| Privacy and security | Unauthorized disclosure, excessive collection, inappropriate linkage, complaints, incident response and unresolved risk; no public case detail | `UNKNOWN_HARMS` when ascertainment or required review is incomplete |
| Distress, coercion or delayed help | Participant-reported concern, inappropriate pressure, misleading information or delayed official support, with coverage and independent assessment | Apply the safety stop promptly; missing reports do not demonstrate no harm |

Do not add incommensurable units into a single invented score. The primary financial contrast from FIRST_STUDY is net household JPY; minutes, compute, validated scale values and safety categories remain separate. If cost-benefit analysis is later authorized, freeze valuation choices, perspective and double-counting rules prospectively and show the unconverted components as well.

## 5. Disposition algorithm and reporting

1. **No valid observed human outcome:** report `NOT_MEASURED`. Keep the digital release at its evidenced artifact level. A source map or local fixture does not supply P3.
2. **A human measure exists but authenticity, consent, unit or population linkage fails:** reject the unsupported claim, describe the evidence limitation and use `NOT_VERIFIED`; do not promote it to P3/P4.
3. **A verified observation exists but the comparison or missingness is inadequate:** report the observation in its original units, with `INCONCLUSIVE` for causal effect. Apply the FIRST_STUDY missingness plan when relevant; never zero-fill missing benefit.
4. **Costs or harms are incompletely ascertained:** attach `UNKNOWN_HARMS` even when the gross outcome is favorable. Do not assert verified net improvement or absence of harm.
5. **Valid comparison, authenticated outcomes and sufficiently characterized costs/harms exist:** submit the estimated effect, 95% interval, assumptions and independent review to the existing P3/P4 gates. This procedure is evidence preparation, not automatic proof-level approval. P5 still requires independent replication.

Release positive, null, negative, inconclusive and stopped results through the same public-aggregate procedure. Explain private-data access limits, suppressed cells, underpowered estimates, missingness and deviations. Correction or source retraction must update downstream claims and preserve the earlier result/version history.

**Present disposition:** no observed participant outcomes or independent settlement/scale evidence was collected for this work. Financial outcome = **NOT_MEASURED**; participant count = **0**; harm ascertainment = **UNKNOWN_HARMS**. Source-backed engineering delivery and simulated tests do not alter these values. The protocol's bytes are included in [the research-protocol hash manifest](../../pilot/RESEARCH_PROTOCOLS_20261022.sha256).
