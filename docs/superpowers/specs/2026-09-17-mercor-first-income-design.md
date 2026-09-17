# Mercor first income: profile, fit, and learning design

**Status:** design and implementation handoff. No first Mercor contract, work trial, or payout is claimed. This document supplements the [Mercor integration SSOT](./2026-08-22-mercor-life-manager-consolidation.md) and the [shared marketplace learning contract](./2026-08-22-life-manager-gig-economy-loop-design.md); those retain runtime ownership.

## Outcome and scope

The first outcome is one **official Mercor offer or paid work trial**, followed by one **official paid/settled Mercor earnings row and payout receipt**. A profile view, application, assessment, interview, trial invitation, or contract alone is an intermediate stage. USD 10,000 net received in a complete calendar month is the later scale outcome, never a promise or a reason to delay the first payment. Hourly rates are not monthly recurring revenue: project hours and continuity must be observed.

This design covers truthful operator onboarding, Mercor profile and résumé quality, listing selection, human assessment handoff, funnel attribution, and bounded external learning. Existing `mercor-revenue-application`, `mercor-revenue-reply`, and `mercor-revenue-paid` retain all effects. No second Mercor executor, scraper, browser, scheduler, or money ledger is created. The seven user-supplied voice recordings are a one-off Japanese Voice Actor application input; assessment or interview responses remain the operator's own work.

## Research and evidence weight

1. [Mercor profile guide](https://talent.docs.mercor.com/how-to/setup-your-profile): precise identity, PDF résumé, concise role outcomes, 2–4 representative projects, core versus occasional skills, language and availability. Complete profiles are shown more often. Parsed résumé fields must be reviewed; an upload alone is not a successful profile update.
2. [Application Fit Guidance](https://talent.docs.mercor.com/announcements-and-new-releases/application-fit): profile, CV, expertise and listing criteria produce allowed/warning/blocked outcomes. A warning permits an application; a blocked application cannot be overridden. This is a provider signal, not a hiring guarantee.
3. [Apply guide](https://talent.docs.mercor.com/how-to/apply): Explore has Job fit and Newest filters; assessments can be reused; all required steps precede Submit; a confirmation screen proves submission. Changed requirements can make a prior step incomplete.
4. [Assessments](https://talent.docs.mercor.com/how-to/assessments), [AI interview](https://talent.docs.mercor.com/support/ai-interview), and [instant offers](https://talent.docs.mercor.com/new-releases/instant-offer): strong, completed assessments may qualify for multiple roles and surface candidates without a new application. AI may not compose assessment answers unless explicitly allowed. Official interviews evaluate the person's responses and may be reused.
5. [Work trials](https://talent.docs.mercor.com/how-to/work-trial): a work trial is a paid but separate selection stage; it has a deadline and independent-work requirement, and does not guarantee a contract. Only an actual official earnings/payout record proves money.
6. [Japanese Mercor interview firsthand account](https://note.com/hiroelab/n/nd25fe7aac97d): one person describes different domain and Japanese language interview formats. Useful preparation hypothesis; it does not prove hiring or payout.
7. X search: the logged-in daily-driver X tab was absent. Publicly indexed [Japanese platform roundup](https://msbrewwc.twstalker.com/ukauka_s_ai) suggests Japanese search terms, and a [Mercor earnings thread](https://x.com/BillionAireSon/status/2030754733825135028) advertises rates. Neither contains a verifiable author-specific Mercor contract and payout. Treat both as candidate discovery leads only.
8. GitHub search found [a listings scraper](https://github.com/levingtn27/mercor-jobs) that requires a private refresh token, [an interview exercise repo](https://github.com/workfromhome130/mercor-interview-code-review), and a [generic application project](https://github.com/rachitgoel05/mercor-application). None is evidence of a reproducible hiring method. Do not copy the scraper's token extraction or claim it improves conversion.

## As-is, observed and unknown

- The installed application owner is scheduled every 30 minutes; reply and paid owners every five minutes. Their loaded release SHA and terminal events must be checked before any operational change. A previous readback showed authenticated state and session writeback, but this does not prove future continuity.
- Private application state has 2,798 inspection rows as of the observed 2026-09-17 pass. These are repeated observations, not unique listings. `no_reasonable_shot`, incomplete applications, and unrendered details recur. The most recent application owner terminal event was `pass`; reply and paid were `blocked`. Paid reported `official_work_inventory_stale`. These observations do not prove a contract or payment.
- Existing shared Apply policy ranks verified résumé overlap and material contradictions, but its top-level objective is still `maximize_truthful_submissions`. The Mercor prompt uses `high/medium/low` and bounded scans. Neither currently ties profile version and fit decision to a later interview, offer, trial, contract, or payout cohort.
- Candidate facts exist in the private profile; the current Mercor profile's visible fields, résumé parser output, profile visibility, actual unique application statuses, interview outcomes, and provider-side view count have not been audited in this design pass. Do not infer that many people viewed the profile without a provider metric.

## To-be: one causal funnel

```text
verified operator facts + permitted proof
  → reviewed Mercor profile and text PDF résumé
  → live open listing + requirement-to-fact fit judgment
  → official fit allowed/warning/blocked + application step status
  → submitted application or reusable completed assessment
  → interview/trial/instant offer → contract → authorized work
  → official earnings paid/settled → payout received
  → attribute one strategy version and improve one bottleneck
```

The model judges fit from the complete listing and verified facts. `high` requires meaningful overlap without a material required-condition contradiction; `medium` is plausible but has a missing proof or a nonfatal warning; `low` has a material required-condition contradiction. A Mercor `blocked` fit result is never bypassed. `warning` is recorded and may proceed when the model can explain an honest reason to expect selection. Keep provider limits and bounded scans; do not impose an arbitrary application count target. Search Japanese/Japan and domain matches, then inspect all genuinely plausible roles; avoid title-only matching. Do not invent years, credentials, English level, equipment, or outcomes.

The profile loop compares the private fact bank, current résumé text, and official Mercor profile fields. It drafts only claims linked to fact IDs or user-supplied artifacts, selects 2–4 representative projects, distinguishes primary from occasional skills, records availability, saves through the existing owned browser, then reloads and reads the exact fields and résumé parse result. A failed or ambiguous readback leaves the prior profile version active. Contact/email changes are outside routine optimization.

Person-bound interview, identity, and assessment steps become candidate-local pending gates with one Telegram link and exact action. The owner may upload authorized materials and complete ordinary factual fields. It may not answer graded assessments, speak in interviews, or submit an independent-work trial for the person. On the next natural wake it reopens the official application and resumes only after the required step reads complete. Other listings continue. The Japanese Voice Actor one-off maps all seven recordings to the official upload controls if offered; it cannot convert recordings into completion of the English interview or Japanese assessment.

The shared learning record links listing ID, official status, profile and résumé hash, fact IDs, strategy version, fit judgment, provider warning, application receipt, human gate, and later offer/trial/contract/payment IDs. A missing official stage is `unknown`, not zero. One model-led review diagnoses the earliest measured bottleneck and proposes one change to profile proof, listing qualification, assessment preparation logistics, or application presentation. The existing shared learning machinery evaluates later cohorts and emits `keep`, `revert`, `pause`, or `insufficient_evidence`. X, web, and GitHub claims enter only as source-labeled hypotheses; a testimonial never updates a profile fact or proves income.

At each existing learning cadence, the model can search official Mercor updates, X, relevant first-person accounts and GitHub within the current provider goal. Store URL, publication/observation date, author, exact claimed outcome, and evidence grade. Prefer direct official pages and first-person posts with a described application→offer→payout path. If X login or search fails, record `source_unavailable` and continue from official and already indexed sources. No fixed keyword list or platform-wide scraping is needed; the model chooses current queries from the measured funnel bottleneck. A source item is promoted to a strategy test only when it suggests an action that is truthful, allowed by current Mercor policy, and measurable from official receipts.

After the first payment, scale by observed net revenue per available hour, repeat work, and verified project continuity. The USD 10,000 monthly target is reached only when a full calendar month's received net receipts total at least USD 10,000; a quoted hourly rate multiplied by hypothetical hours is a capacity scenario, not revenue.

## Approach decision

**Selected:** extend existing Mercor owner and shared Apply/learning contracts. It minimizes new state and lets other marketplaces reuse source-backed learning only after a second real consumer appears.

**Rejected:** a new Mercor growth agent with its own browser and scheduler. It would compete for the account/profile and split receipts. **Rejected:** copying a GitHub scraper or optimizing for application volume; neither verifies selection, and a token-based scraper adds credential exposure. The strongest argument for broad automation is faster discovery, but the observed constraint is no first offer and the official fit system already uses profile evidence.

## Acceptance and stopping conditions

1. A fresh operator can supply their own private facts, account and materials; no Dais credential or résumé is exported. The guided path produces an authenticated, reloaded profile readback and an accurate PDF parse. A new account still requires that operator's identity and person-bound steps.
2. One natural Mercor application wake ranks real candidates with requirement/fact evidence, records official fit result, makes no false claim, and preserves duplicate fences. A material mismatch is not submitted. A plausible warning can be submitted only with a recorded explanation and official confirmation.
3. A human gate sends one useful Telegram link, rechecks official completion, and resumes the exact application without resubmission. The seven voice files remain a one-off candidate artifact.
4. The funnel report separates unique listings, submitted applications, completed assessments, interviews, work trials, contracts, paid/settled earnings, and received payouts. No denominator is inferred from repeated inspection rows.
5. A source-backed learning proposal changes one strategy variable and later produces `keep`, `revert`, `pause`, or `insufficient_evidence`. A first official paid trial or contract and a first received payout are separate, externally verified business milestones. USD 10,000 per month remains unachieved until a complete month of net received evidence exists.
