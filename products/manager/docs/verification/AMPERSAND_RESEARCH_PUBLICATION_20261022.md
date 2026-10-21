# Ampersand bilingual research and publication preparation

Date: 2026-10-22 JST. This record covers source preparation and verification.
Live publication requires the existing canonical-source PR, publishing-bridge PR,
deployment, and independent public readback; a local package is not that receipt.

## Authorized scope and provenance

The user requested a detailed English and Japanese explanation of humans&
Ampersand, including foundational teaching, primary-source research, comparisons
with Simile, Aaru and Andon Labs, and a practical attempt to use the release.
The existing instruction to publish Manager articles remains applicable.

- Canonical source: `Daisuke134/life-manager`.
- Base branch: `research/manager-product-r006-20261020`.
- Base commit: `20828fc55f66d2ed8681d6bac4a9d2461ebec91a`.
- Work branch: `research/manager-ampersand-20261022` in an isolated worktree.
- Scope: two new manuscripts, four original explanatory PNGs, a public aggregate
  reanalysis, additive publication-builder support, and the reviewed blog package.
- Manager roadmap statuses and Life Manager runtime are outside this change.

The root and remote were checked before changes and before promotion. The
unmodified source-boundary script reports that its Mac host checkout
`/root/Projects/life-manager-main` is unavailable in this cloud workspace. The
host-specific guard was not edited. The previously authorized isolated Manager
scope is preserved. Astra Advisor orchestration is not exposed in this harness;
the available Superpowers workflow and bounded research/review agents were used.

Skills read for this task include Firecrawl, using-superpowers,
using-git-worktrees, verification-before-completion, and
finishing-a-development-branch. The user's existing completion/publication
authorization determines the integration action, without another approval menu.

## What was actually observed

- Primary materials: Ampersand release/model card/developer documentation;
  Persimmon release/model card; underlying benchmark papers and repositories;
  Simile confidence research; Aaru's September population-simulation research;
  Andon Labs publications on AI-managed businesses and Pion.
- Public numeric data were downloaded as text and parsed without executing the
  JavaScript. The source hashes, retrieval times and calculations are recorded in
  `../research/ampersand-20261022/observations.json`.
- Recalculation covers nine published model aggregates. At cost weight 0.2,
  Fable minus Ampersand is 0.00254 points. Weight changes reuse fixed aggregates;
  they are not new simulations, significance tests, or human-effect estimates.
- The unauthenticated `GET https://ampersand.humansand.ai/v1/models` returned
  HTTP 401 at 2026-10-21 23:33:45 UTC. The console showed a sign-in requirement.
  No Ampersand credential was configured for this investigation.
- Authenticated model inference calls: **0**. New simulation runs: **0**.
  Human participants recruited: **0**. No output-quality trial is claimed.
- The recurring Mika/Ren/Aki example is original fiction, explicitly labeled in
  both languages. No company dialogue, company illustration, participant record,
  private source link or credential was copied into the deliverables.

## Editorial and independent review

A fresh-context, read-only reviewer checked the builder, focused tests,
manuscripts, reanalysis and all four figures. Result: **1 finding, 0 blocking**.
The finding requested that the official model card's tentative-results condition
be retained. It was added to both manuscripts. The review also checked the
boundary between simulated outcomes, arithmetic reanalysis and real effects;
the 401/inference-zero account; and the central meaning across both languages.

The four figures were inspected for legibility, Japanese rendering and numeric
agreement. Their source code is in the reanalysis script. They distinguish the
user simulator, reward/evaluation rule, assistant policy and independent
real-world evaluation rather than asserting undisclosed model internals.

## Source-side verification

The parent executed these checks on the prepared source tree:

- `recompute.py` against the two hash-pinned public files and independent numeric
  extract: **PASS**; output byte-identical to `observations.json`, SHA-256
  `02ab2fcab6313fdd9ddbef7d5e07e10073ab17e44e2f500bb9bd1cdf51acd464`.
- Full Manager suite with the existing real optional dependencies: **467 tests,
  0 failures/errors/skips**. Command from `products/manager`:
  `PYTHONPATH=/tmp/manager-causal-deps:/tmp/manager-growthbook-deps:. MPLCONFIGDIR=/tmp/manager-matplotlib python -m unittest discover -s tests -v`.
- Existing publication renderer/installer Node tests: **4 test files PASS**.
- Existing package baseline: **63 articles / 29 media verified**.
- Independent in-memory rebuild preserved all baseline article/media records.
- `git diff --check`: **PASS**.

An initial parent full-suite invocation from the repository root omitted the
documented product import path and failed with missing `manager_core` imports.
The command was corrected to the product directory and real dependency paths;
the full result above is the corrected run. No dependency stub was substituted.

The builder change supports explicit English/Japanese metadata, an immutable
source commit for each new article, and reviewed hash-bound additive PNGs. Its
focused tests cover invalid language/slug combinations, immutable source pins,
changed hashes, media collisions, path escapes and reproducible rebuilding.
The original global source pin is retained so earlier article citations remain
byte-for-byte stable. No existing publication verdict is re-judged.

The publication adapter and installer remain unchanged. The expected next
package contains **65 articles / 33 media**, retaining all previous 63 article
and 29 media hashes. The final package, dry run and public readback are verified
separately at promotion time.

## Generated package verification

The two new articles are pinned to source commit
`767a0da9bc17067e780d7fcff9ac0f519b9d2dd0`. The package builder and its `--check`
mode produced and verified **65 articles / 33 media**. Every prior article and
media record, including metadata, and every prior file's SHA-256 matched the
63/29 baseline. The resulting language counts are 37 English and 28 Japanese.

The parent reran the full suite on this generated tree: **467 tests PASS**, with
0 failures/errors/skips; all four Node test files and package verification also
passed. Product boundary and unchanged 113-task roadmap checks passed. The
installer SHA-256 remains
`c0908ffa9f899138f3f342140063b595e3b7bcab72f6e516d704290d3207e141`.

The fresh reviewer then examined only the added configuration/package and
editorial fixes: **0 findings, 0 blocking**. Source links, figure hashes,
per-article revision, language placement and complete baseline preservation
were confirmed.

The checkout does not contain the root guide's named `bin/merge-when-green`.
Promotion therefore uses the existing GitHub PR/checks path, waits for every
applicable check to finish successfully, and passes the exact expected PR head
to the merge operation. No check, publication verdict, or branch protection is
disabled. The publishing bridge remains limited to the two existing revision
pins and their source-authority note.
