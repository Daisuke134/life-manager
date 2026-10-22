# Manager founder-execution specification update — verification

2026-10-22 UTC. Scope: user-authorized primary-source research, specification and derived execution-map updates for the existing draft research PR. No runtime implementation, infrastructure provision, model trial, site/article publication, job/YC application, outreach, event registration, payment, main merge or release apply.

## Source identity and authority

Canonical origin `https://github.com/Daisuke134/life-manager.git`; worktree `/workspace/manager-execution`, local branch `research/manager-e06-cloud-execution-20261022`, common Git directory `/workspace/life-manager/.git`. Baseline and expected remote head `3391f6a5237681ad1166ebaadb38597db1d0c9e6`. Destination is user-named `research/manager-e01-e16-execution-20261022`, draft PR [#8527](https://github.com/Daisuke134/life-manager/pull/8527), base `research/manager-phase06-owned-public-good-20261022`. Keep this worktree while the PR is open.

AGENTS.md and REVIEW.md were read. Mac-specific `bash scripts/verify-source-boundary.sh` failed exit 2: canonical Git root unavailable at `/home/agent/Projects/life-manager-main`. This check did not pass. No HOME override, guard alteration, runtime checkout spoof or Mac runtime action was used. Existing session authorization for cloud source authoring and the GitHub connector's expected-head lease is used; it is not a runtime admission check. Promotion and the original privileged publisher contract remain unchanged.

## Research and decisions

Superpowers using-superpowers, brainstorming, writing-plans and verification-before-completion were read for this research/specification workflow, with Firecrawl deep-research. Three independent read-only lanes examined reusable systems/code/papers, official YC/career/event sources, and publishing/revenue precedents. The parent reconciled the reports and authored repository changes. No worker implemented product code. Existing publication and product plans are reused; the 12-package map is derived and creates no new task authority.

See [integrated report](../research/manager-strategy-20261022/FOUNDER_EXECUTION_UPDATE_JA.md), its three detailed reports and sanitized source metadata. Read depth distinguishes full-page retrieval, selected code or paper passages, search-only links, failures and reused same-day research. Author/vendor statements are not independent effects, financial validation or career guarantees. No third-party full page bodies, private CV or payment records are committed.

Railway access to `life-manager` is verified and the initial target is a dedicated single Python worker plus volume. Existing service purpose remains unconfirmed and is preserved. Dedicated worker/volume and production adapter are not created. Mac is not a deployment prerequisite; E16 remains BLOCKED pending adapter, state, admitted owner/release, real canary/readback/restart/rollback. Original source/ref/7-path gates are not relaxed. Added crash/reconcile acceptance cases are code-reading concerns, not reproduced failures.

## Verification on the authored tree

- `python -m unittest discover -s tests -q`: **Ran 661 tests, OK (skipped=5)**. Optional-library cases remain skipped. No test was added for documentation.
- `python scripts/check_boundaries.py`: **PASS**, no banned Life Manager imports.
- `python scripts/make_roadmap.py --check`: **PASS 113 tasks**; derived backlog regenerated.
- Compared old/new task IDs, statuses, dependencies, technical cursor and completed prefix: unchanged. **69 done / 41 todo / 3 skipped; E16 active; E01–E15 verified within their recorded scope.** Description/verification wording and deployment metadata changed only.
- Parsed changed/new JSON, checked balanced Markdown fences and relative destinations; no newly broken links. One pre-existing README PNG destination remains missing and unchanged.
- `git diff --check`: PASS. Changed paths are product documentation/roadmap only; Python code, tests, workflows, credentials, runtime and frozen trial artifacts are unchanged.

Independent read-only review: 0 Blocking. Three initial Advisory points (YC full-time vs employment, Y005 contacts vs job outcomes, early paid pilot vs original U/G dependencies) were addressed. New-report review found 0 Blocking and one wording Advisory about unknown existing-service purpose; corrected. No outstanding findings. Low-risk docs/SSOT tier applies. Hosted checks and remote file readback are associated with the resulting commit in PR metadata; baseline CI is not reused as new-tree proof.

## State preserved

Customer pilot, targets and publishing/career cadence are plans. Manager revenue is UNKNOWN until authoritative period/product/account coverage is checked; confirmed zero is not inferred. U008 now states this explicitly. Product/consulting/employment/content/other-loop income remain separate. Submitted, accepted, interview, offer, published, paid and beneficiary outcomes require separate evidence. None was advanced by this update.
