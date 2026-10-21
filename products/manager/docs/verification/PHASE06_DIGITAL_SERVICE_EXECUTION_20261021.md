# Phase06 digital environment implementation and execution evidence

## Scope and current scientific status

Manager is changing an owned information environment, not printing money or trying to manipulate vulnerable individuals. The same source schema, HTML renderer, release boundary and verification routine serve financial-support access, mental-support access and physical-health information. These are public official-resource navigation environments, **not financial advice, mental treatment, clinical practice or a human experiment**. Current real beneficiary result remains **NOT_MEASURED** in all three domains.

Canonical task status remains in `docs/roadmap/tasks.json`. Original finance-fund and indoor-facility tasks are not silently relabeled done. The proposed digital-first scope differs; any accepted migration must retain original requirements and evidence. Scientific Gate1 is UNMET. The separate Phase05 kernel's live-effect flags remain false; this deterministic CI release lane is not proof of general autonomous policy deployment.

## What was built

- `public_goods/service/catalog.json`: four current official MHLW/FSA public entrypoints, domains, reviewed date and link-only rights. No private records or questionnaire contents.
- `manager_core/digital_environment.py`: semantic Japanese HTML for home, financial, mental, physical, unchanged-source list and proof page; exact hosts, dates, rights, bounds and escaping; deterministic SHA256 bundle; no JS, forms, trackers, cookies or personalization.
- `scripts/phase06_digital_service.py`: build, bounded official-source HTTP audit, truthful missing-outcome report and independent live bytes readback.
- `scripts/phase06_release_guard.py`: verifies source results and all content hashes before staging exactly seven static files under `manager-support/`. Rejects symlinks, unexpected existing files, forged sources and UNKNOWN. The rest of the existing Pages site is untouched. Same bundle replay gives NO_ACTION.
- `tests/e2e/`: actual Playwright 1.56.1 / axe-core browser tests, pinned npm lockfile; desktop Chromium and mobile Chromium-emulated iPhone viewport; not a claim of actual iOS Safari validation.
- `.github/workflows/manager-phase06-service.yml`: unprivileged test job; separate canonical-branch-only, environment-protected, narrowly scoped Pages publication after all tests/source audits. Existing Pages infrastructure reused, no third-party deployment service, paid ads or new accounts.
- `docs/product/DIGITAL_ENVIRONMENT_SURFACE_INVENTORY.md`: original hosting source and permitted additive destination. No administrator environment/protection bypass.

## Test-first and fault findings

1. [Initial RED](https://github.com/Daisuke134/life-manager/actions/runs/39610388045): eight new tests failed because the implementation did not exist; old tests retained.
2. [First implementation](https://github.com/Daisuke134/life-manager/actions/runs/39610893592): **295 Python tests OK**, 14/16 real-browser cases passed. Two tests failed because a locator matched both header and main navigation. Fixed by selecting the main content's named link; assertions were not removed.
3. [Browser GREEN](https://github.com/Daisuke134/life-manager/actions/runs/39611635613): all 16 desktop/mobile Chromium cases passed. Four official source HTTPS responses returned 200 and content hashes. Screenshots were saved; mobile landing screenshot was visually inspected, with no clipping or horizontal overflow. This is not full accessibility certification.
4. [Release-guard RED](https://github.com/Daisuke134/life-manager/actions/runs/39612228459): four new release contracts failed before the bounded staging helper existed.
5. [Release preparation GREEN](https://github.com/Daisuke134/life-manager/actions/runs/39612789143): **299 Python tests**, all 16 browser cases, immutable build, source audit, safe staging, replay NO_ACTION, original-root/article preservation, existing boundary checks and the 113-task backlog verification passed. Publish job correctly skipped on feature branch.

## Verified before publication

- Both structural navigation and ordinary flat-list option expose the same four official sources.
- Existing inaccessible content is not fabricated as a baseline; the true old public artifact was a GitHub Markdown list, and its actual usability for people has not been measured.
- Axe automatic checks found no violations in the tested rule set; keyboard skip-link focus works and no horizontal overflow at tested desktop/mobile sizes. This does not prove all disabilities/browser combinations are supported.
- No third-party network requests on initial page rendering, cookies, local storage, forms or script execution.
- Data sources return HTTPS 200 but that is only reachability, not entitlement, medical safety or downstream benefit.
- Staging the site twice results in no second file change. Tampered content, absent official source audits, symlink target and extra files are rejected.
- All external posting/money/physical/private-data defaults in the original Manager runtime are preserved. Actual publication, if successful, is a separately scoped static release worker controlled by repository ownership and CI/environment policy.

## Intended delivery and independent readback

URL (not declared live until confirmed): `https://daisuke134.github.io/life-manager/manager-support/`.
Existing `gh-pages` baseline: `db229a38ba2374c4b67517b2d61e46282c46cd91`, with unrelated `index.html`, `articles/`, `.github/workflows/pages.yml`, `.nojekyll`. Only the new Manager prefix may change.

After source PR is merged into the canonical Manager research branch, a dedicated release job is allowed to stage and commit only seven exact paths on the existing owned Pages branch. It must pass the existing `github-pages` environment rules and the official deploy-pages action. No force-push, environment policy changes, bank/private API access or money transfers. Unknown publish/readback must remain UNKNOWN. Independent GET must compare all six served HTML hashes to the same immutable verified source bundle before declaring technical P2 delivery.

## Remaining true Phase06 endpoints

This implementation advances service navigation, accessibility, real internet delivery and technical verification. It does **not** finish:
- live causal behavior prediction or human outcome evidence;
- valid consented controlled real-user study, power/assignment/follow-up;
- measured mental/physical/financial welfare, costs, attrition, displacement and harms;
- the same general ManagerKernel independently deciding, authorizing and executing a real intervention rather than this narrowly scoped developer CI release.

No causal effect or human outcome count is estimated when measurements are absent. It remains necessary to connect genuinely independent appropriate outcomes and a credible counterfactual; no amount of green tests substitutes for them.

## Reproduce

```sh
cd products/manager
python3 -m unittest discover -s tests -v
python3 -m manager_core
python3 scripts/check_boundaries.py
python3 scripts/make_roadmap.py --check
python3 scripts/phase06_digital_service.py build --commit <immutable-source-sha>
(cd tests/e2e && npm ci --ignore-scripts --no-audit --no-fund && npx playwright install chromium && npm test)
python3 scripts/phase06_digital_service.py audit
python3 scripts/phase06_digital_service.py outcomes
# After actual publication and a matching locally built immutable bundle:
python3 scripts/phase06_digital_service.py readback
```

Remote source editing and hosted GitHub CI were used. The user's Mac/local canonical checkout was not available, and the Mac-only source-boundary script was not run. Manager's own static boundary checks were executed in hosted CI.

Reusable primary implementations: [Playwright accessibility](https://playwright.dev/docs/accessibility-testing), [GitHub Pages official workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [existing GrowthBook setup](../../requirements-internet-eval.txt), [existing proof ladder](../../manager_core/outcome_ladder.py).
