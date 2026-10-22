# Manager whole-product specification update — verification receipt

**Date:** 2026-10-22 UTC. **Scope:** User-authorized research, specification and derived-plan updates. No product-code implementation, new live model trial, site/article deployment, study enrollment, third-party contact, YC submission, merge or production apply.

## Source identity and authority

- Canonical repository: `https://github.com/Daisuke134/life-manager.git`.
- User-named working branch: `research/manager-e01-e16-execution-20261022`; baseline HEAD `1b7a8e5c234e4ce3c66366f34539e55844bcc0e5`.
- Existing draft PR #8527 targets `research/manager-phase06-owned-public-good-20261022`, not main. This update does not merge or retarget it.
- Actual root/branch/common Git directory/origin were inspected before source work. `/workspace/life-manager` is a newly cloned **read-only source cache**, not the canonical Mac runtime checkout. It has no active runtime owner or credentials added by this work.
- The Mac-specific `scripts/verify-source-boundary.sh` was read and invoked. It returned exit 2: canonical `$HOME/Projects/life-manager-main` unavailable. This check **did not pass**. No HOME override, guard modification, production checkout spoofing or runtime command was used.
- Changes were authored in an exact-commit cloud source export under `/workspace/scratch/manager-review` and are published through the existing GitHub connector with expected-head lease. Product source boundaries and source identities are verified separately; they are not represented as the Mac runtime guard.

## Research procedure and limits

Skills read/applied: Superpowers using-superpowers (previous turn), brainstorming, dispatching-parallel-agents, writing-plans, using-git-worktrees (isolation procedure inspected; no canonical local worktree claimed), systematic-debugging (incomplete source export investigation), requesting-code-review, verification-before-completion; Firecrawl deep research; cloud-environment-runtime/networking.

Current environment readiness and enforced network policy were read without inspecting secret values. No Astra Advisor/Ponytail callable tool was found; the applicable Superpowers path and existing-code reuse review were used. Three independent read-only research lanes examined simulation, agent/OSS systems, and welfare/product/YC; the primary agent reconciled their sources and wrote the current spec/plans. No implementer was delegated product-code changes.

37 source records include primary papers, partial PDF or indexed body readings, official vendor methodology, upstream fixed-code interfaces, government/service studies, measurement documents and YC guidance. Records explicitly retain read depth, date/version and limitations. Related pages/versions are not independent experiments. No source benchmark/model was newly executed, and Radiant is documented only, not connected. Dollar retrieval costs are not known settled billing.

The review corrects or records paper-title/version mismatches, Socrates abstract/PDF numeric inconsistency, the OES CI text inconsistency, vendor comparisons on unlike benchmarks, WHO-5 commercial-use limitations, and current vs historical task meanings. It does not repair external source values by inventing them.

## Local verification

Commands from `products/manager` in the exact source export:

```text
python -m unittest discover -s tests -q
Ran 560 tests ... OK (skipped=5)

python scripts/check_boundaries.py
PASS: manager_core has no banned Life Manager imports

python scripts/make_roadmap.py --check
PASS 113 tasks; task JSON untouched
```

Five optional-library tests remain skipped in this standard environment. This is not a new claim that optional dependencies were exercised. The first incomplete export omitted repository-level publication fixtures and one workflow, causing nine FileNotFound errors; the missing unchanged baseline paths were exported, then the complete suite passed. No product implementation or test was changed to hide those errors.

Additional checks compared exported files against the baseline Git objects, verified documentation-only changes, parsed the 37-record JSON source manifest, checked balanced fenced code blocks and new relative links, preserved intentional Markdown hard breaks, and found no new TBD/FIXME. One already-broken historical README PNG link is unchanged and was not counted as a newly introduced link failure.

`tasks.json`, generated `ATOMIC_BACKLOG.md`, Manager Python modules/tests, workflows, frozen trial bytes and published package manifests are unchanged. The Manager state remains 69 done / 41 todo / 3 skipped, E01–E05 completed, E06 next. No original field/science task is advanced by this documentation work.

## Review and remote verification

An independent read-only review checks the current spec/plans against the baseline, primary-source claims, E/F/P ordering and gates. The initial review found 0 introduced findings (0 blocking). It also identified two pre-existing active-label ambiguities in the plans: historical E01 integration described as current, and earlier publication authorization described as the latest request. Both labels were corrected in this update; the founder table was also aligned with current F004/F007 skipped status. The final PR records the review disposition. Hosted CI and source readback must refer to the actual new documentation commit; the old baseline run is not reused as evidence for it.

Remaining product limitations are explicit in the spec: E06 deadline gaps are identified but not fixed; E09 needs task-matched reference evidence; E16 needs verified persistent host/volume/owner; customer demand and actual beneficiary benefit remain unvalidated. A specification commit does not establish deployment or efficacy.
