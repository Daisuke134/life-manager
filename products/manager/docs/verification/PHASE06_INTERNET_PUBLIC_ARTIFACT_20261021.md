# Manager Phase06 — First actually published internet public good / independent readback

**Verified 2026-10-21 (UTC hosted GitHub).** **Task SSOT:** [113 tasks](../roadmap/tasks.json), unchanged: 63 DONE / 47 TODO / 2 BLOCKED / 1 scientifically skipped. Phase05 offline kernel = 14/14 engineering scope, Phase06 original F001–F003 = done and F004/F007 = blocked under original charity/facility acceptance. **No authentic Manager-caused human welfare net benefit has yet been measured.**

## What really changed (not a mock)

An **actual publicly readable** Japanese support-resource directory now exists on the owner's public Manager research branch:
- [Published public resource artifact](../../public_goods/RESOURCE_DIRECTORY_JA.md)
- Immutable baseline HEAD before the file existed: `c16660f9c6d5c1a79a801f0587dc7cc0355df1b3`
- Verified published HEAD: `8707422df46fb647d1f29d2982912efda98654f2`
- SHA-256 of exact published file: `7d3cba81efb9f0fc832c4f67961b4931867bea6d4bedc64e3fedd6e54ed07e60`
- [Independent public GitHub Contents API response](https://api.github.com/repos/Daisuke134/life-manager/contents/products/manager/public_goods/RESOURCE_DIRECTORY_JA.md?ref=8707422df46fb647d1f29d2982912efda98654f2)
- [Real hosted CI run](https://github.com/Daisuke134/life-manager/actions/runs/39603999651) independently reads both versions by unauthenticated `GET` and validates exact bytes against working source and Git blob SHA; returns `PUBLIC_ARTIFACT_CHANGED`.
- **Proof is `P2_ARTIFACT_ONLY`**: a reproducible change in a public digital artifact, NOT that a person read it, received aid, became healthier or escaped distress.

The directory is intentionally a zero-account, nontracking collection of official Japanese public sources for financial hardship, mental support and physical wellbeing. There is no fake user, forged testimonial, onchain transfer, private survey profile, DM spam, third-party page mutation or paid service purchase.

## First-source live URL plausibility check

Official live pages used as source links were checked at the provider origin (some crawler captures may be older than this code release; provider terms/content can change):
- [MHLW living difficulty support](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000059425.html)
- [MHLW consultations and relief](https://www.mhlw.go.jp/stf/newpage_08152.html)
- [FSA debt and money-lending guidance](https://www.fsa.go.jp/policy/kashikin/)
- [MHLW mental-health consultation routes](https://www.mhlw.go.jp/mamorouyokokoro/soudan/)
- [MHLW public physical-activity guidance](https://kennet.mhlw.go.jp/information/information/exercise)

An official resource link cannot prove eligibility, successful application, symptom improvement or an actual increase in material resources.

## Reused existing components instead of inventing another system

| Component | Existing implementation reused | Verification | Limitation |
|---|---|---|---|
| Public publish/readback | Public GitHub repository + official Contents REST API (GET only) | External pre- and post-SHA response, content exact hash | Digital source availability, not beneficiary outcome |
| Online A/B preparation | [GrowthBook Python SDK](https://github.com/growthbook/growthbook-python) pinned `3.2.2` | 512 deliberately **synthetic** assignment IDs: 254 NO_ACTION / 258 resource directory; no custom randomization algorithm | Real participants 0; not a live randomized trial |
| Outcome proof gate | Existing `manager_core.outcome_ladder.proof_level` (no new metric) | P2 artifact technically distinct from mental/physical/financial P3 | No patient/beneficiary readings |
| Standard mental outcome | [WHO-5](https://www.who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01) official instrument | [Existing-source crosswalk](../../pilot/INTERNET_WELFARE_EVIDENCE_CROSSWALK.json) and regression tests | No rights-cleared administered participant responses |
| Standard physical outcome | [WHO WHODAS 2.0](https://www.who.int/classifications/international-classification-of-functioning-disability-and-health/who-disability-assessment-schedule) | Same crosswalk and no false promotion tests | No physical-function measurement |
| Standard finance outcome | [CFPB Financial Well-Being Scale](https://www.consumerfinance.gov/data-research/research-reports/financial-well-being-scale/) | Same crosswalk and missing data tests | No benefit payout/net resources independently measured |

Source licensing is evaluated per tool and instrument. The original respondent items are not embedded or silently copied into the public repository.

## Hosted test-first evidence and regression

1. [RED test-first run](https://github.com/Daisuke134/life-manager/actions/runs/39602345877): 279 unit cases, 5 expected new-component errors; old 273 tests continued passing.
2. [GREEN initial actual public-world readback](https://github.com/Daisuke134/life-manager/actions/runs/39602997635): 279 tests, GrowthBook 512 synthetic fixture allocation, independent public GitHub source readback, prior real public finance and indoor *read-only* data probes, product boundary, backlog consistency all SUCCESS.
3. [GREEN final three-domain proof firewall](https://github.com/Daisuke134/life-manager/actions/runs/39603999651): **282 tests OK**; semantic original instrument crosswalk checks, proof gate, same external artifact readback and synthetic A/B procedure; no fabricated users or outcomes.

## Reproduce on a public repository clone

```bash
cd products/manager
python3 -m unittest discover -s tests -v
python3 -m manager_core
python3 scripts/check_boundaries.py
python3 scripts/make_roadmap.py --check
python3 scripts/phase06_public_good_readback.py --baseline-sha c16660f9c6d5c1a79a801f0587dc7cc0355df1b3

# Optional additional dependency; no real user experiment:
python3 -m pip install -r requirements-internet-eval.txt
python3 scripts/phase06_growthbook_existing_sdk.py
python3 scripts/phase06_welfare_proof_gate.py
```

On Github Actions, the source readback uses the actual checked out `GITHUB_SHA`. It intentionally rejects changed/missing baseline, mismatching content/Git SHA, wrong path, forged and untrusted response, network timeout, invalid commit ID and bad source bytes. There is no external write outside normal source commits.

## What still makes this an unfinished Phase06

The remaining significant **REAL** milestones are not more synthetic runs:
1. Establish an actual Manager-controlled public website *visitor experience* (beyond the GitHub source file) with valid publish rights and independent public URL readback. No need for a partner charity, clinic or facility, but the route must be legitimately owned and already set up.
2. Compare a real opt-in, appropriately scoped original/no-action experience to a transparently sourced, improved experience using the **existing** GrowthBook experiment design; measure participation and avoid false claims about manipulated mental states. Do not optimize clicks over welfare or track vulnerable people without consent.
3. Acquire legitimate, privacy-preserving, voluntarily reported and licensed domain-relevant outcomes (WHO-5, WHODAS, CFPB or verified resources/functional outcomes) if practical; pre-register sample/power/windows/harms before live trial.
4. Use existing DoWhy/EconML/OBP where identification assumptions actually hold. Report negative/unknown and broad CIs; failure to measure remains `NOT_MEASURED`.
5. Maintain original F004/F007 blocked statuses until *their own* written funded-finance/physical-site acceptances are verified or the same canonical task registry is explicitly version-amended for the digital lane. Source publication alone cannot mark those tasks done or F009 complete.
6. Use external real-world data only with actual rights; no personal profile scraping, no covert psychological persuasion, no independent human approval needed for each permitted Manager run.

## Verified proof, by domain

| Dimension | What changed | What is NOT yet measured |
|---|---|---|
| Digital public resource | Real public GitHub file exists, exact bytes externally confirmed | Whether a person used or benefited |
| MENTAL | Public official MHLW mental-support link available | WHO-5 symptom/wellbeing change, harms, control group |
| PHYSICAL | Public official activity information link available | WHODAS functioning/clinical outcome |
| FINANCIAL | Public MHLW/FSA aid and debt information links available | Confirmed aid/resource increase, CFPB financial security |
| Causal net welfare | No field comparator/outcome measured | All P3/P4 claims remain NOT_MEASURED |

**Bottom line:** Internet is the real world. A public artifact state change is real and reproducible, but it is not an endpoint for the 'End suffering' mission. No LLM-generated self-praise, simulated token balance or artificial audience score may cross that boundary.
