# Manager Phase06 — Internet-first public-good experiment design (not a trial)

**2026-10-21; stage: DESIGN_ONLY.** This is a preparation and an actual public artifact engineering demonstration, not a randomized human field trial, earned beneficiary wealth, measured mental health change, or P4 proof. **One official source registry and one canonical task SSOT remain.**

## Reuse → Connect → Evaluate: actual existing primitives

- Existing official public information: [MHLW financial support](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000059425.html), [FSA debt advice](https://www.fsa.go.jp/policy/kashikin/), [MHLW mental support](https://www.mhlw.go.jp/mamorouyokokoro/soudan/), [MHLW physical activity](https://kennet.mhlw.go.jp/information/information/exercise).
- Official public hosted *actual-world artifact* publication: GitHub repository + unauthenticated [GET Contents REST API](https://docs.github.com/en/rest/repos/contents). A public `GET` must independently corroborate content SHA256 and prove file did not exist at frozen baseline HEAD. This is **P2_ARTIFACT_ONLY**, not a human-world welfare P2/P3.
- Existing A/B experimentation: [GrowthBook Python SDK](https://github.com/growthbook/growthbook-python), pinned 3.2.2 under MIT license in `requirements-internet-eval.txt`. CI demonstrates deterministic allocation of **synthetic** anonymous cohort IDs, not a real enrolled randomized group. [GrowthBook main](https://github.com/growthbook/growthbook) is open core; enterprise licensing and rights of any rollout host must be checked before deployment.
- Existing browser accessibility evaluation: [Playwright + axe](https://playwright.dev/docs/accessibility-testing) when a real owned deployed website with source/rights and accessibility baseline exists. Do not invent an axe competitor.
- Existing causal effect estimators: [DoWhy](https://github.com/py-why/dowhy), [EconML](https://www.microsoft.com/research/project/econml/), [OBP](https://github.com/st-tech/zr-obp). No novel causal algorithm or regression API was coded for this stage.
- Existing wellbeing measurement: MENTAL: WHO-5/OECD; PHYSICAL: WHODAS/rights-cleared PROMIS; FINANCIAL: CFPB financial wellbeing scale plus genuinely settled income and food security. All require valid voluntary/independent outcome measurement, appropriate rights, baseline and comparison; no auto-derived suffering score.

## Pilot contrast and outcomes

**Controlled artifact:** `public_goods/RESOURCE_DIRECTORY_JA.md` under this independent Manager research branch; links only official public resources, no form, tracking code, private-person profile, spam or third-party write.

**Prepublication baseline:** git `c16660f9c6d5c1a79a801f0587dc7cc0355df1b3` does not contain this public document. The current public research-branch commit should contain it. GitHub public HTTP GET confirms real accessible content, hash and absence at prior baseline.

**Software primary outcome:** boolean accessible/published officially sourced links on public GitHub (no simulated host), with exact SHA and baseline readback; this measures digital artifact availability. **It cannot be a proxy for confirmed benefit claims.**

**Prospective human experiment (NOT RUN):** On an owner-controlled live site, after permitted deployment and opt-in rights, GrowthBook can assign consenting eligible sessions to two conditions: retained **NO_ACTION** original navigation versus a clearly attributed official-support-directory navigation. Randomization unit, version, holdout, ethical consent, duration, sample size/power, outcome and instrumentation MUST be frozen before exposure. Risk: selection, interference, multiple devices, attrition, users unable to reach programs, perceived distress from unsuitable content. Do not invent a conversion-based proxy for mental wellbeing.

**Meaningful primary FINANCIAL endpoint:** net money retained or legitimate benefits received within defined follow-up, including costs, fees, displacement, fraud, and beneficiary evidence with explicit denominator. Voluntary CFPB aggregate score can be secondary with license, not silently inferred from traffic.

**Meaningful MENTAL endpoint:** voluntary WHO-5/OECD self-report where legitimately collected and scored with validated instrument and reporting terms; distress and adverse outcomes, dropout, access to support. No targeted psychological persuasion or unconsented mental inference.

**Meaningful PHYSICAL endpoint:** voluntary WHODAS/PROMIS functioning if legally instrumented, or another explicit real clinical/function outcome; link availability or page reads are not physical improvement.

**Statistical plan:** existing GrowthBook experiment engine for assignment and SRM/variance; use DoWhy/EconML on a preregistered valid causal estimand and account for harms/costs. If no valid comparator, outcome, consent, treatment, or confidence interval: NOT_MEASURED/INCONCLUSIVE. Report null/negative and externally challenged findings. Never claim P4 because clicks or self-reported model success increased.

**Permissions:** Manager owns its research branch and public documentation (developer authority). A website deployment requires genuine control over that site and its policies; public repo content being readable does not authorize mutation on Facebook, X, health care provider accounts, someone else's money or property. No per-run human approval of routine actions once standing authority is established, but no pretending permissions are universal.

**Phase06 canonical task correspondence:** F001–F003 remain done under the original scope; F004 original funding authority and F007 original indoor facility control remain blocked. This public digital artifact is a new evidence route, **not** a false completion of original F004/F007/F005/F006/F008/F009. Completion requires a versioned amendment to the SAME tasks.json before scope migration, and real P1/P2 then P3/P4 outcome study afterward. Existing `manager_core/config.py` deny-live switches are unchanged.

**Existing test:** `python -m unittest discover -s tests -v`; standalone `python scripts/phase06_growthbook_existing_sdk.py` after installing the pinned official SDK; external readback `python scripts/phase06_public_good_readback.py --baseline-sha c16660f9c6d5c1a79a801f0587dc7cc0355df1b3` with valid GitHub HEAD. Public Source/Publishing contract: [GitHub API Contents](https://docs.github.com/en/rest/repos/contents).
