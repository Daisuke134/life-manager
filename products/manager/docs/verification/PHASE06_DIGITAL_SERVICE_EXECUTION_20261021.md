# Phase06 digital environment — actual public delivery and independent verification

**Verified 2026-10-21, 14:36 UTC.** The owned public digital environment is now served at **[Manager official-support navigation](https://daisuke134.github.io/life-manager/manager-support/)**. This is real internet delivery, not a local mock or only a GitHub Markdown file. Human mental, physical and financial outcomes remain **NOT_MEASURED**. This record does not claim Phase06 is fully complete.

## Immutable publication and independent evidence

| Evidence | Verified value |
|---|---|
| Source PR | [#8513](https://github.com/Daisuke134/life-manager/pull/8513), merged |
| Tested source merge | `098aedca454228e29f5261554cbb0848cb646fe7` |
| Previous public hosting state | `db229a38ba2374c4b67517b2d61e46282c46cd91` |
| Actual published Pages commit | `9160eb265cdd232e534df49b51c2e9a7aa1a2dfb` |
| Source build / additive publish / external readback | [Manager CI #39617848783](https://github.com/Daisuke134/life-manager/actions/runs/39617848783) |
| Existing sole Pages deploy workflow | [Deploy Pages #39618047098](https://github.com/Daisuke134/life-manager/actions/runs/39618047098), reported SUCCESS |
| Live independent readback | 2026-10-21T14:36:24.113933Z; all six served HTML files match immutable tested SHA256 values |
| Real public browser verification | 16 expected, 0 unexpected, 0 skipped, 0 flaky; actual public URL, desktop Chromium plus mobile-emulated Chromium |
| Saved public proof/screenshots | [artifact 12353871656](https://github.com/Daisuke134/life-manager/actions/runs/39617848783/artifacts/12353871656), ZIP SHA256 `c262e0b427aeda1bd821613208c92ef73dd1c856a6e32f3f21e722e701dee0c0` |
| Delivery classification | `VERIFIED_BYTES_ONLY`, `P2_ARTIFACT_ONLY` |
| Real beneficiary effect | `NOT_MEASURED`; `causal_effect_verified=false` |

The native GitHub compare of previous hosting commit to the published one shows **only seven new files under `manager-support/`**, no other changes: index, finance, mental, physical, control, proof HTML and manifest JSON. The prior root homepage, `articles/`, `.nojekyll` and existing deployment workflow were preserved. No main-branch or Life Manager production runtime changes were made.

## What changed in the environment

One shared source schema and renderer deliver six pages: a topic-based starting point, financial-assistance navigation, mental-support navigation, physical-health information, an ordinary flat list of the same official resources, and a public explanation of evidence/limits. The aim is to make official information easier to find; **actual reduction of user friction or hardship has not yet been measured**.

All four destinations are existing MHLW/FSA pages, checked by actual bounded HTTPS requests. Content is short original navigation text and links, not copied clinical questionnaires, therapy instructions, financial-product recommendations or government forms. No account, personal-data form, JavaScript, analytics, cookies, targeted messages, hidden randomization, user mental-state inference or medical diagnosis. The rendered pages explicitly state that users choose whether to use the information, no human experiment is running, and outcome evidence is absent.

- [Financial navigation](https://daisuke134.github.io/life-manager/manager-support/finance.html)
- [Mental-support navigation](https://daisuke134.github.io/life-manager/manager-support/mental.html)
- [Physical-health information](https://daisuke134.github.io/life-manager/manager-support/physical.html)
- [Unchanged-source flat-list option](https://daisuke134.github.io/life-manager/manager-support/control.html)
- [Proof and limitations](https://daisuke134.github.io/life-manager/manager-support/proof.html)

The list and topic views are available for inspection, not assigned to real users in a randomized trial. Two public layouts do not establish a causal comparison or improvement.

## Implemented source and reused systems

| File / component | Responsibility |
|---|---|
| `public_goods/service/catalog.json` | Four official source identities, domains, exact URLs, review dates and link-only rights |
| `manager_core/digital_environment.py` | Common semantic HTML generation, date/URL/rights validation, escaping, deterministic bundle, public byte checks, existing outcome-ladder reuse |
| `scripts/phase06_digital_service.py` | Build, read-only source audit, missing-outcome report and bounded exact live readback |
| `scripts/phase06_release_guard.py` | Admit only a validated bundle and four matching current source-audit results; stage exactly seven allowlisted files; same content replay gives NO_ACTION |
| `tests/e2e/` | Existing Playwright 1.56.1 and axe-core engine, locked upstream dependency versions; actual browser journeys and accessibility tests |
| `.github/workflows/manager-phase06-service.yml` | Read-only verification; separate canonical-branch-only static publisher; explicit dispatch to the ONE existing protected Pages deployment workflow; independent live verifier |
| `docs/product/DIGITAL_ENVIRONMENT_SURFACE_INVENTORY.md` | Actual owned surface and permitted additive scope |

No new A/B allocator, generalized agent marketplace, token or welfare score was invented. Existing GrowthBook research preparation is unchanged; no real-user trial was enabled. Existing `manager_core/outcome_ladder.py` labels evidence, not self-reported model claims.

## Test-first failures and fixes

1. [Initial RED #39610388045](https://github.com/Daisuke134/life-manager/actions/runs/39610388045): eight contracts failed before the source/render/release interface existed.
2. [First code #39610893592](https://github.com/Daisuke134/life-manager/actions/runs/39610893592): **295 Python tests passed**, 14/16 actual browser cases passed. Two selectors matched both header and main links. Fixed by selecting the main-content journey without removing assertions.
3. [Browser GREEN #39611635613](https://github.com/Daisuke134/life-manager/actions/runs/39611635613): all 16 browser cases and four official-source HTTP audits passed. Screenshots retained and mobile layout visually inspected.
4. [Release RED #39612228459](https://github.com/Daisuke134/life-manager/actions/runs/39612228459): four new release contracts failed before bounded staging existed.
5. [Release GREEN #39612789143](https://github.com/Daisuke134/life-manager/actions/runs/39612789143): **299 Python tests**, 16 browser cases, safe stage/replay and unrelated-root/article preservation passed.
6. Independent CodeRabbit review identified (a) a competing full-site Pages deployment could overwrite newer unrelated content, and (b) date-sensitive fixtures would expire. Added RED regressions [#39615676203](https://github.com/Daisuke134/life-manager/actions/runs/39615676203), then fixed both in `e407ed6955f7c9009341eac0c1f96c411debffe2`.
7. [Reviewed-fix GREEN #39616122858](https://github.com/Daisuke134/life-manager/actions/runs/39616122858): **301 Python tests**, all 16 browser cases, freshness/authority/source boundaries and dry-run release passed. Codex review could not run because its usage allowance was exhausted; it is not counted as an approval. CodeRabbit's initial two findings were fixed and documented; its later successful status is not represented as unlimited fresh independent review.
8. [Merged source #39617848783](https://github.com/Daisuke134/life-manager/actions/runs/39617848783): the same full validation, actual restricted publish, existing Pages deployment and independent public readback ran. The actual public URL then passed **another 16 browser cases**, with screenshots and no unexpected/flaky results.

The suite includes 2030-wall-clock regressions. Only the test clock is fixed. Production continues to reject source review dates older than 45 days or future-dated inputs. No production safety bypass or test-only grant was added.

## Actual release boundary and concurrency repair

The Manager publisher does not deploy a full-site snapshot. It commits only seven tested Manager paths to the existing `gh-pages` branch using the owner-configured short-lived GitHub Actions capability, with a non-force push; a conflicting advance fails rather than overwriting another author. It dispatches the **pre-existing Pages workflow ID 307239134** using `workflow_dispatch` because a GITHUB_TOKEN push alone does not trigger another push workflow. That existing deployment authority owns the `pages` concurrency policy and the protected `github-pages` environment. No environment/admin/branch-policy setting was changed or bypassed.

A separate unprivileged live verification job waits only by bounded GET attempts; it never repeats a write or deployment because an outcome is unknown. Its exact-byte check passed at 14:36:24Z. Following public Chromium checks passed; 12 screenshots were retained and the mobile home rendering was visually inspected for clipping/overflow. Automatic accessibility testing does not prove all WCAG requirements or all disabilities/browsers are supported, and mobile Chromium emulation is not real Safari validation.

## Truthful relationship to Phase05, Phase06 and the mission

- This implementation **does** establish a real, owner-scoped, automatically published and independently verified internet environment. No NPO or room owner was needed, no person manually approved each release step after the reviewed source merge, and existing infrastructure was reused.
- It **does not** show the general Phase05 `ManagerKernel` independently selecting, causally predicting, authorizing and executing a live intervention. That kernel still admits offline fixture adapters only. The narrowly constrained deterministic CI publisher is a separate release plane, not a hidden expansion of its authority.
- Financial, mental and physical pages share implementation, but they are not three independent causal intervention studies or measured human outcomes.
- There are no actual participant counts, baseline/follow-up wellbeing measurements, realized financial benefits, treatment effects, confidence intervals, clinical outcomes, harms/attrition estimates or validated counterfactual. Missing is not zero and is not a completed but inconclusive RCT.
- Original Phase06 F004/F007 refer to actual funds and indoor facilities; those optional legacy scopes remain recorded as blocked. The internet-first scope needs a visible same-registry amendment before replacing those requirements. No task was marked done merely to change the completion percentage.
- **Canonical registry remains 113 tasks: 63 done, 47 todo, 2 blocked, 1 scientific skip. Phase06 original acceptance is 3/9 done. Scientific Gate1 UNMET; actual net welfare NOT_MEASURED.**

## What remains to complete the true loop

1. Apply the already requested digital-first scope as an explicit versioned amendment to the SAME canonical task registry, preserving original finance/facility conditions and not weakening independent human-outcome criteria.
2. Connect the reviewed bounded digital executor to the common kernel's real authority, idempotency, reconciliation and versioned learning path; do not pass a fixture flag or forge an HMAC grant to turn it live.
3. Freeze a valid noncoercive digital environmental intervention and its real independent task/beneficiary outcome before any study. Use the existing GrowthBook allocation, NICE/SPIRIT/CONSORT reporting, and rights-cleared WHO/CFPB/WHODAS measures only if their administration and meaningful voluntary observations are actually available.
4. Observe genuine usage/beneficiary data and a credible comparison without scraping private profiles or guessing mental states. Current nontracking public pages deliberately do not produce these measurements.
5. Evaluate real costs, harms, attrition and displacement with existing valid causal tooling, and publish negative/null/unknown outcomes. No finite software test can replace these absent observations.
6. Demonstrate the same live kernel safely across independent domains/populations, including revocation, replay, unknown effects, real rollback and held-out learning. Then update only the task acceptances truly met.

## Reproduction and provenance

```sh
cd products/manager
python3 -m unittest discover -s tests -v
python3 -m manager_core
python3 scripts/check_boundaries.py
python3 scripts/make_roadmap.py --check
python3 scripts/phase06_digital_service.py build --commit 098aedca454228e29f5261554cbb0848cb646fe7
(cd tests/e2e && npm ci --ignore-scripts --no-audit --no-fund && npx playwright install chromium && npm test)
python3 scripts/phase06_digital_service.py audit
python3 scripts/phase06_digital_service.py outcomes
python3 scripts/phase06_digital_service.py readback
# Match the actual deployed source commit when newer releases exist.
```

Hosted GitHub CI and remote source APIs were used. The user's Mac checkout was unavailable; its Mac-only source-boundary script was not run. Manager's own static boundary and entire test suite were executed. Actual artifact ZIP digest, readback JSON and browser JSON were downloaded and checked; no private participant information was involved.

Primary upstream implementations: [Playwright accessibility](https://playwright.dev/docs/accessibility-testing), [GitHub Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [GrowthBook preparation](../../requirements-internet-eval.txt), [existing evidence ladder](../../manager_core/outcome_ladder.py).
