# Manager full roadmap and homepage source — verification receipt

2026-10-22 UTC. User request: explain every remaining phase through the end, generate a visual, and keep the main website aligned with actual progress. Scope of this update: product documentation and the existing English/Japanese homepage Manager section plus its manifest hashes. No production deployment or task-status promotion.

## Identity and authority

Canonical repository: `https://github.com/Daisuke134/life-manager.git`. Isolated worktree: `/workspace/manager-execution`; local branch: `research/manager-e06-cloud-execution-20261022`; common Git directory: `/workspace/life-manager/.git`. Baseline: `2b9a7b78b4845f6ac7022f969244dc0d1596bddf`. Destination: `research/manager-e01-e16-execution-20261022`, existing draft PR8527, research base unchanged.

AGENTS.md/REVIEW.md were read. The Mac-specific source-boundary command was run before authorship and before publication; both returned exit2 because `/home/agent/Projects/life-manager-main` is unavailable. It did not pass and was not bypassed. Existing user authorization for cloud source editing and GitHub expected-head CAS applies to this source update, not runtime admission. Keep the isolated worktree while the PR is open.

Superpowers using-superpowers and brainstorming were read; the existing writing-plans/verification workflow was reused. Prior P04 source-only copy plan and the user's explicit website-update instruction supply the design direction. Independent read-only agents audited the original task graph, homepage source plan, and final changes. Root authored repository files. Systematic-debugging was used to distinguish the inherited contrast issue from a regression.

## Changes and completion boundaries

- [START_TO_END_20261022.md](../roadmap/START_TO_END_20261022.md) includes all13 original phases, all41 todo IDs with exact change/dependencies/acceptance, the13 phase counts, and the actual dependency joins.
- Product spec, README, founder execution map, completion gates and older roadmap/acceptance entry points now lead to that full view. Old EBA Phase07–11 numbering is mapped to the original task phases rather than silently replacing them.
- Original113 tasks remain69 done/41 todo/3 skipped/0 blocked. `tasks.json` is byte-identical to the baseline. E01–E15 implementation receipts do not finish E16 or the empirical U/D/V/G tasks. H005 is a scientific skip; F004/F007 are retired-not-completed. Optional finance/physical work is not a v0.1 prerequisite, and its original future acceptance is retained.
- English/Japanese homepage changes are confined to the existing `#research` section. Existing layout, stylesheet, navigation, metadata, other products and population-study numbers remain intact. Copy distinguishes current engineering, undeployed E16, the dated public prototype and limited model experiments. It links immutable baseline evidence and the full roadmap on the destination branch.
- Exactly three route-manifest hashes change: `/` and `/en` share English source, `/ja` uses Japanese source. The nine-file allowlist and other entry fields are unchanged.
- Website progress, articles, books, decks/carousels/video, applications and customer/revenue evidence are parallel tracks with separate publication/receipt gates. One model/no routine UI is a direction; universal capability or all suffering ended is not claimed.

## Verification on the authored tree

- `python -m unittest discover -s tests -q`: **661 tests, OK(skipped=5)**. No new copy-only implementation tests.
- `python scripts/check_boundaries.py`: PASS. `python scripts/make_roadmap.py --check`: PASS113 tasks.
- All41 todo rows independently match `tasks.json` for ID, change, depends and verify. All13 phase counts match. DAG has no cycles, no done task depends on unfinished work, and no todo depends on a skipped task. Six graph-ready tasks are distinguished from real-world permissions and the E16 sequence contract.
- Changed Markdown fences/new relative links, manifest JSON and `git diff --check`: PASS. One inherited missing README PNG reference is unchanged.
- Native `apps/landing/marketing/scripts/publish-overlay.mjs` exercised with local allowlisted responses in a temporary export: all9 source/output hashes match, an unrelated product file is preserved, retired route RSC is removed, and tampered Japanese source is rejected before installation. This is a **local fixture**, not publication. No remote deployment script or infrastructure was invoked.
- Playwright preview: English/Japanese at1440×1000 and375×812, all4 views render4 cards, retain one h1 and have no horizontal overflow. Japanese desktop/mobile screenshots were visually inspected. External font/network requests were blocked; this is a local source preview.
- Axe was run on `#research` in all4 views. It reports **one inherited color-contrast finding per view**, at `#research > .eyebrow`, foreground `#d64b2c`, background `#f5f2eb`, ratio3.83 versus4.5 required. The same baseline views reproduce identical rule/target/color/size findings; **zero new findings**, not zero total violations. Stylesheet redesign is outside this copy update.
- Fresh read-only final review: **0 Blocking /0 Advisory** for roadmap/source-copy correctness. The later preview contrast finding is recorded above as an inherited limitation. The new homepage roadmap URL requires this document to land on the destination branch in the same publication.

Scratch artifacts are session-local under `/workspace/scratch/manager-home-preview-20261022/` (four screenshots, axe results, receipt), `/workspace/scratch/manager-home-baseline-preview-20261022/`, and the local overlay temporary directory. A Japanese full-roadmap image was generated and displayed in chat; it is explanatory artwork, not evidence of completed tasks.

## Publication and limits

The previous baseline's Python/browser hosted runs39792814121/39792814160 completed successfully; they do not verify this new tree. New commit identity, exact GitHub file readback and hosted CI status are recorded in PR metadata after source publication. PR remains draft/unmerged. No live homepage GET/render success is claimed: Firecrawl requests to the live EN/JA pages returned internal errors in this turn, and production deployment was not performed.

No runtime/adapter implementation, worker/volume provisioning, model trial, public article/book release, outreach, job/YC submission, payment, customer interview or human-benefit study was executed by this source update. E16 remains reference-only/undeployed; human benefit and Manager revenue remain unmeasured/UNKNOWN.
