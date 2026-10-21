# Baseline digital journey: anonymous official-support navigation

**Prepared 2026-10-22 JST / 2026-10-21 UTC.** This document indexes the actual six-page source and the recorded public-browser evidence. It defines reproducible navigation tasks without treating a browser scenario as a person. **Human task time, success rate, support receipt and wellbeing: NOT_MEASURED.**

## 1. Versioned baseline and existing captures

The historical public baseline for comparison with a later change is the release recorded in [PHASE06_DIGITAL_SERVICE_EXECUTION_20261021.md](../verification/PHASE06_DIGITAL_SERVICE_EXECUTION_20261021.md), verified at **2026-10-21T14:36:24.113933Z**:

| Evidence | Exact recorded reference |
|---|---|
| Tested source | `098aedca454228e29f5261554cbb0848cb646fe7`; [source PR #8513](https://github.com/Daisuke134/life-manager/pull/8513) |
| Prior hosting state | `db229a38ba2374c4b67517b2d61e46282c46cd91` |
| Published Pages state | `9160eb265cdd232e534df49b51c2e9a7aa1a2dfb` |
| Build, additive publish and independent readback | [run 39617848783](https://github.com/Daisuke134/life-manager/actions/runs/39617848783) |
| Existing Pages deployment | [run 39618047098](https://github.com/Daisuke134/life-manager/actions/runs/39618047098) |
| Public proof and screenshots | [artifact 12353871656](https://github.com/Daisuke134/life-manager/actions/runs/39617848783/artifacts/12353871656); recorded ZIP SHA-256 `c262e0b427aeda1bd821613208c92ef73dd1c856a6e32f3f21e722e701dee0c0` |
| Recorded result | Six exact HTML hashes matched; 16 expected browser cases, 0 unexpected, 0 skipped, 0 flaky; `VERIFIED_BYTES_ONLY` / `P2_ARTIFACT_ONLY` |

These are dated observations, not a fresh readback of the current live version. A later release needs its own source commit, manifest, receipt, captures and timestamp. The original prior hosting state had no `manager-support/` pages; **no prepublication Manager-page screenshots are available**. The existing 12 images are postpublication captures of the recorded release and may serve as a historical baseline for a subsequent change. They are not invented “before” images of the initial intervention or a record of real users.

The screenshot writer in [environment.spec.cjs](../../tests/e2e/environment.spec.cjs) saves `products/manager/output/service/screenshots/<project>-<page>.png`. The recorded artifact contains the public capture set; its naming convention is:

| Page | Desktop capture | Mobile-emulated capture |
|---|---|---|
| Home | `desktop-index.html.png` | `mobile-index.html.png` |
| Finance | `desktop-finance.html.png` | `mobile-finance.html.png` |
| Mental | `desktop-mental.html.png` | `mobile-mental.html.png` |
| Physical | `desktop-physical.html.png` | `mobile-physical.html.png` |
| Flat-list control | `desktop-control.html.png` | `mobile-control.html.png` |
| Evidence explanation | `desktop-proof.html.png` | `mobile-proof.html.png` |

`output/service/browser-results.json` and `output/service/public-readback.json` are the associated generated reports. They are workflow artifacts, not fabricated tracked photographs. If the hosted artifact is no longer retained, mark that capture unavailable and cite the surviving dated report; do not regenerate a current page and label it the historical image.

## 2. Exact surfaces and sources

The public base is [https://daisuke134.github.io/life-manager/manager-support/](https://daisuke134.github.io/life-manager/manager-support/). The six paths come from one [renderer](../../manager_core/digital_environment.py) and one [source catalog](../../public_goods/service/catalog.json).

| Owned path | Public URL and role |
|---|---|
| `index.html` | [Home](https://daisuke134.github.io/life-manager/manager-support/index.html): choose a topic |
| `finance.html` | [Finance](https://daisuke134.github.io/life-manager/manager-support/finance.html): livelihood and debt information |
| `mental.html` | [Mental support](https://daisuke134.github.io/life-manager/manager-support/mental.html): official consultation information and an urgent-help notice |
| `physical.html` | [Physical information](https://daisuke134.github.io/life-manager/manager-support/physical.html): official physical-activity information |
| `control.html` | [NO_ACTION reference list](https://daisuke134.github.io/life-manager/manager-support/control.html): the same four official links in one ordinary list |
| `proof.html` | [Evidence and limits](https://daisuke134.github.io/life-manager/manager-support/proof.html): technical verification versus unmeasured human outcomes |

The catalog's four exact outbound destinations and labels are:

| Topic / source ID | Link label | Official destination |
|---|---|---|
| Finance / `livelihood` | 生活費・仕事・住まいの相談 | [MHLW livelihood support](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000059425.html) |
| Finance / `debt` | 借入・多重債務の相談窓口 | [FSA borrowing/debt information](https://www.fsa.go.jp/policy/kashikin/) |
| Mental / `mental-support` | 電話・SNS・地域の相談先を探す | [MHLW まもろうよ こころ](https://www.mhlw.go.jp/mamorouyokokoro/soudan/) |
| Physical / `physical-activity` | 身体活動・運動の公的情報 | [MHLW physical-activity information](https://kennet.mhlw.go.jp/information/information/exercise) |

Source rights are `LINK_ONLY`. At the recorded release the catalog review date was 2026-10-21 and the separate bounded HTTPS source audit passed for all four destinations. This establishes dated reachability, not current program capacity, individual eligibility or an actual service transaction. Fresh source status must be checked before a new release.

## 3. Reproducible anonymous journey protocol

Start with a fresh browser context without a login, cookies or local storage. Record the exact Manager source/manifest version, browser, viewport and observation time. Do not enter personal details, fill a government form or contact a provider while performing this technical task.

| Task | Start and first choice in the main content | Next choice / bounded technical endpoint |
|---|---|---|
| Finance livelihood | `index.html` → **生活費・仕事・借入** | `finance.html` → **生活費・仕事・住まいの相談**, exact MHLW URL above |
| Finance debt | `index.html` → **生活費・仕事・借入** | `finance.html` → **借入・多重債務の相談窓口**, exact FSA URL above |
| Mental support | `index.html` → **こころの相談** | `mental.html` → **電話・SNS・地域の相談先を探す**, exact MHLW consultation URL above |
| Physical information | `index.html` → **健康づくり** | `physical.html` → **身体活動・運動の公的情報**, exact MHLW physical-activity URL above |
| Same-information reference | Home footer → **同じ情報を一覧で見る（NO_ACTION参照版）** | `control.html` → the chosen one of the same four official links |

These source-defined paths require two content-link activations from the home page: topic then official link, or reference list then official link. Directly loading `control.html` leaves one outbound activation. These are structural path counts, **not observed completion time, measured effort or an improvement estimate**. Scroll distance, keyboard actions and comprehension are separate observations. Different entry points cannot be compared as if their starting conditions were equal.

**Keyboard procedure:** load the page, press Tab once and confirm focus on **本文へ移動** (`href="#main"`); press Enter and confirm `main` receives focus. Continue Tab through the main-content links, confirming visible focus, and activate the intended labeled link with Enter. On the topic page, repeat the skip-to-main sequence and inspect the exact official link before activation. Record actual focus behavior rather than assuming a universal Tab count. Browser Back or the **ホーム** link provides a return route; the reference list remains available in the footer.

**Mobile procedure:** use the existing `mobile` Playwright project, which selects the iPhone 13 device profile but runs **Chromium**, and tap the same main-content labels. Confirm no horizontal overflow, readable links and visible navigation; use normal browser Back or the home link to exit. This is emulation, not a physical iPhone or Safari result. A manual external-navigation check can open the final official link and record its actual response/final URL without proceeding into a service; that step must receive its own observation if performed.

The currently recorded automated journey test opens the Manager topic page and checks its official `href` and limitations text. **It does not click through and complete an external service.** The independent source-audit GETs check the official pages separately. Neither evidence source proves a completed application, consultation, benefit receipt or health improvement.

## 4. What the 16 existing browser cases cover

The [Playwright config](../../tests/e2e/playwright.config.cjs) runs two projects with one worker and no retries. [The locked package](../../tests/e2e/package.json) uses Playwright 1.56.1 and `@axe-core/playwright` 4.10.2.

| Test definition | Two-project case count | Scope |
|---|---:|---|
| One test for each of six pages | 12 | HTTP 200, Japanese language, one `h1`/`main`, explicit NOT_MEASURED, axe tags, no form/input/script/iframe, no overflow, skip-link focus, allowed outbound hosts, no cookies/local storage, screenshot |
| One test containing all three topic journeys | 2 | Main-content topic links reach the matching Manager page; first official href and scope disclaimer are present |
| One no-hidden-experiment test | 2 | Mental page makes only same-origin requests and explicitly says no user experiment is running |
| **Total** | **16** | Technical browser cases; not 16 participants or independent interventions |

Automated axe success does not certify all WCAG requirements, screen-reader usability, translation quality or comprehension. The source language is Japanese. No multilingual or real assistive-technology evaluation is evidenced here.

## 5. Reproduction without changing the public surface

Use a clean checkout of the exact source version being evaluated. A `--commit` value labels a build; it does not itself prove the worktree matches that revision. From `products/manager`, the existing read-only/local commands are:

```sh
python3 scripts/phase06_digital_service.py build --commit "$(git rev-parse HEAD)"
python3 scripts/phase06_digital_service.py audit
python3 scripts/phase06_digital_service.py outcomes
```

From `products/manager/tests/e2e`, install the locked packages/browser if absent and run the existing test:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npx playwright install chromium
npm test
```

That default uses a local static server. For a public-browser run, select the public base explicitly:

```sh
MANAGER_BASE_URL=https://daisuke134.github.io/life-manager/manager-support/ npm test
```

Before running `python3 scripts/phase06_digital_service.py readback`, independently inspect the public `manifest.json` and use a clean source checkout/build matching its exact `source_commit`; a different release is supposed to fail the byte comparison. Retain the readback and browser reports with their time and source. The current renderer rejects stale/future source review dates, so a historical checkout may no longer build under a later clock; do not disable that safeguard or relabel newly reviewed content as the old release. None of these commands authorizes or performs a deployment.

The public flat list is a transparent **NO_ACTION reference view**, not an assigned human control group. An optional future evaluation must separately establish consent, assignment, eligibility, outcome measurement and a prospective freeze. See [FIRST_STUDY](../../pilot/FIRST_STUDY.md) and the [second-environment safety boundary](../../pilot/SECOND_DIGITAL_ENVIRONMENT_SAFETY.md).
