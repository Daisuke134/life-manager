# DD05 Publication Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make the existing scheduled truth pipeline preserve and attribute instrumented publications using exact publication and native receipts, while reporting unsupported attribution, cost, and intervention evidence as unknown.

**Architecture:** Keep `marketing-owner-events` as the sole scheduled measurement owner. Preserve immutable publisher-intent fields in the canonical publication identity ledger, sweep only exact resolved publication identities into the existing experiment-attribution builder, and write daily idempotent snapshots from the existing native metrics and business ledgers. Do not backfill legacy posts by fuzzy matching; do not add publisher or scheduler routes.

**Tech Stack:** Python 3.14, stdlib SQLite/JSONL, existing Marketing Engine modules and unit tests.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` — DD05.

## Global Constraints

- Only the existing `marketing-owner-events` owner writes its state and attribution ledger.
- Exact `publish_key`, Postiz ID, experiment/product/account identity, and native receipt are required; missing or conflicting identity stays unknown/unattributed.
- Capafy account or agent aggregates never become per-publication orders or revenue.
- `actual_cost_usd` and `human_interventions` are separate metrics; missing exact publication-scoped evidence stays unknown, never zero.
- No publisher route, account, cadence, provider state, or external post changes in DD05.
- No new package or scheduler.

## Review Focus

- Legacy provider refresh omits intent fields: retain the previous exact intent binding for the same Postiz ID.
- Conflicting publish key, experiment, creative, product, account, integration/platform, token, or native receipt on a Postiz ID: fail closed rather than overwrite.
- Unresolved or duplicate native receipt: do not emit a deterministic attribution snapshot.
- Missing click, sales/order, cost, or intervention evidence: preserve explicit unavailable/unknown reasons.
- Repeated hourly sweep: append at most one snapshot per `publish_key` per UTC date.
- The business metrics become mature at 24 hours in the existing builder; do not create a publication's first daily snapshot before that age. Later daily snapshots can capture the existing 72-hour and 168-hour native checkpoints.
- The owner-state pipeline has no publication-scoped actual-cost or complete human-intervention evidence source today. Emit those two metrics as `unknown` with separate reasons until exact evidence exists; do not infer zero from missing data or count the required visual approval as the full intervention total.

## Sweep Contract

`run_sweep(identity_path, post_metrics_path, business_path, attribution_path, report_path, observed_at)` reads the owner's canonical publication identity ledger, native post-metrics ledger, existing read-only business-outcomes ledger, and attribution ledger. It writes only the attribution ledger and the sanitized report under the existing owner's state root. It does not open the publisher intent database, call a publisher, or make a post.

An eligible row must be `PUBLISHED`, have `identity_status=resolved`, contain the complete immutable intent fields (`publish_key`, experiment, creative and asset hash, product, account, hook, renderer, attribution token, scheduled time), and have one unique Postiz/native receipt. Any conflicting duplicate or identity field fails closed. Rows without exact metadata remain in coverage counts and do not produce snapshots. Exact rows younger than 24 hours are counted as `not_mature_yet`, not eligible.

The sweep waits until a publication is at least 24 hours old, then appends no more than one snapshot for that `publish_key` on each UTC date. It checks the attribution ledger before building a same-day snapshot, so a later hourly invocation skips it instead of trying to replay a different `observed_at`. Native metrics must match the exact native post and experiment and be observed no later than the snapshot. Click queries use the exact product/token; business snapshots use the exact product/date. Missing inputs retain the builder's explicit unavailable/unknown reason.

The report is `evidence/metrics/attribution-sweep-latest.json` with `schema_version`, `observed_at`, `status`, `eligible_publications` (mature exact rows), `snapshots_written`, `snapshots_already_present`, `excluded` counts by reason (including `not_mature_yet`), and unknown metric counts. The command exits 0 when at least one mature exact publication is eligible (including an idempotent no-op), 3 when none is eligible (attention), and 1 on an execution or data-integrity error. The truth pipeline classifies exit 3 as attention, not failure.

Gate 13 `gate_pass` means the snapshot is structurally complete, contains no fabricated zero, and agrees with the exact click query. It does not mean revenue, cost, or human-intervention evidence is known or that the publication was profitable; unknown metrics and their reasons remain visible.

---

### Task 1: Preserve the intent-bound identity row

**Files:**
- Modify: `skills/earn/marketing-engine/identity/publication_ledger.py`
- Modify: `skills/earn/marketing-engine/publish/reconcile.py`
- Test: `skills/earn/marketing-engine/identity/test_publication_ledger.py`
- Test: `skills/earn/marketing-engine/publish/test_reconcile.py`

**Interface:** `reconcile.identity_row()` emits `publish_key`, `experiment_id`, `creative_id`, `product_id`, `account_id`, `integration_id`, `platform`, `hook_id`, `renderer_id`, `attribution_token`, `scheduled_at`, Postiz identity, and native receipt. `merge_rows()` retains these fields when a later provider-list row for the same Postiz ID omits them, and rejects conflicting non-null values, including a changed native receipt.

- [x] Add a regression test proving a provider refresh preserves intent-bound metadata and the exact native receipt.
- [x] Add a regression test proving conflicting identity metadata fails closed.
- [x] Run the two test files against the old implementation and confirm the intended RED failures.
- [x] Implement the minimal metadata-preserving merge and complete identity row.
- [x] Run both focused test files and `git diff --check` (28 passed, 9 subtests passed).

### Task 2: Make attribution snapshots complete and truthful

**Files:**
- Modify: `skills/earn/marketing-engine/measure/experiment_attribution.py`
- Modify: `skills/earn/marketing-engine/measure/verify_gate13.py`
- Test: `skills/earn/marketing-engine/measure/test_experiment_attribution.py`
- Test: `skills/earn/marketing-engine/measure/test_verify_gate13.py`
- Test: `skills/earn/marketing-engine/report/test_owner_report.py`

**Interface:** `build_snapshot()` accepts only an exact identity whose `publish_key`, experiment, creative/hash, product, account, integration/platform, token, scheduled time, Postiz ID, native ID, and native URL agree with the enriched intent context. The result schema advances to v2 and includes separate `actual_cost_usd` and `human_interventions` metric rows. Because no publication-scoped source exists today, DD05 always emits these metrics as null/unknown with distinct reasons and adds no cost/intervention input source. Existing Capafy aggregate sales remain unknown for per-publication revenue.

- [x] Add failing tests for a mismatched publish key/native receipt and for separate `unknown` cost/intervention metrics with explicit reasons. No publication-scoped source exists today, so DD05 does not invent one or claim measured values.
- [x] Verify those tests fail for the expected missing contract behavior.
- [x] Implement v2 snapshot validation and exact identity checks.
- [x] Update Gate 13 and owner-report fixtures for the expanded result set.
- [x] Run the focused attribution, Gate 13, and owner-report tests (17 passed, 22 subtests; owner report 3 passed).

### Task 3: Sweep exact publications from the canonical ledger

**Files:**
- Create: `skills/earn/marketing-engine/measure/attribution_sweep.py`
- Test: `skills/earn/marketing-engine/measure/test_attribution_sweep.py`

**Interface:** `run_sweep(...)` follows the Sweep Contract above. It reads source JSONL without modifying it, reports legacy/unresolved/ambiguous/mismatched coverage separately, and returns `attention` when no exact publication is eligible.

- [x] Add local JSONL fixtures for exact, legacy, unresolved, duplicate, and mismatched identity rows.
- [x] Add RED tests for exact selection, no snapshot before 24 hours, daily deduplication, and explicit attention on no eligible rows.
- [x] Implement the bounded sweep by calling the existing `build_snapshot()` and click-receipt reader.
- [x] Run the focused sweep tests and verify no test contacts a real provider (6 passed; all click queries use test callbacks).

### Task 4: Wire the sweep into the existing truth owner

**Files:**
- Modify: `skills/earn/marketing-engine/report/truth_pipeline.py`
- Test: `skills/earn/marketing-engine/report/test_truth_pipeline.py`

- [x] Add the attribution sweep after publication identity reconciliation and native metric collection, using only `marketing-owner-events` state plus the existing read-only business-outcomes source.
- [x] Treat sweep return code 3 as `attention`, like a publication-identity coverage gap; hard errors remain pipeline failures.
- [x] Add tests for command order, owner state paths, attention handling, and continued owner reporting.
- [x] Run focused truth-pipeline tests, source-boundary verification, and `git diff --check` (58 tests, 31 subtests; owner-report 3 tests).

### Task 5: Integrate and verify production adoption

**Merged source and documentation**

- [x] DD05 source tasks 1–4 are merged in PR #8009 (`ec0ff40b44b6b453132d36388615277158bc5dc6`); exact-head CI and CodeRabbit passed.
- [x] Post-merge cursor PR #8016 is merged (`b76d6df9a49fce8c1c09a618feb6902b4678d48b`).
- [x] Capafy fence reconciliation and fail-closed Postiz readbacks are merged in PR #8022 (`8b2f8686d71b288dd8a5ea0cbe8bc132283c244a`).
- [x] DD05 cursor cleanup is merged in PR #8020 (`6c569277bf52d25db39f36fbc1c1d5467be26688`); latest main also contains the Capafy runtime checkpoint PR #8023 (`0ecf503a7ea21913652db85d86279c76ffabc09d`).
- [x] `lm-loop doctor` reports 191 registry entries, with no missing, unmanaged, or installed-retired labels.

**Live evidence, read-only capture `2026-10-14T06:55Z`**

- Current main is `0ecf503a7ea21913652db85d86279c76ffabc09d`; `/Users/anicca/loops/current` remains release `20261014T150809-87f2425e`, SHA `87f2425ed209f00a3a0174b1b798e580917752b1`, cut 06:08:45Z. PR #8022 is source-only until a newer release is cut and applied.
- `life-manager-release-reconciler` terminal `18de52ad97952188-52792` ended 06:51:24Z with exit 1. The bounded log for the same interval shows the 87f fleet pass was partial (11 changed, 11 skipped, 0 errors), followed by `cut-loop-release` failing with `release_capacity_measurement_failed`.
- **Root-cause evidence:** the release-capacity calculator in `runtime/host/disk_admission.py::release_capacity_bytes` runs `git merge-base --is-ancestor <current-release-sha> origin/main` to validate its immutable dependency-bundle donor. The source checkout is shallow (`git rev-parse --is-shallow-repository=true`); this local ancestry check returns 1 for donor `87f2425e`. GitHub's compare of `87f2425e...0ecf503a` returns `status=ahead`, `ahead_by=17`, `behind_by=0`, with merge base `87f2425e`. Calling the measurement function directly reproduces `CalledProcessError` at that local ancestry check. **Inference:** the shallow local graph prevents proof of a valid remote ancestor; it is not evidence that the release is actually outside main.
- Host storage was `558219264` bytes free at 06:52Z and `capacity_recovered=false`. The last exact release requirement (`2394329088` bytes, 15:30 JST) predates PR #8022; it is historical only. A fresh requirement for current main is not yet measured. The RRC log also records `scratch_enospc` while writing terminal events.
- `marketing-owner-events` remains on old SHA `52f33c67c3da765af516209e35c394b47e2e6f13`; its latest terminal `18de51a57c57e5a8-26311` ended 06:36:49Z, exit 1 in `report` (`reconcile=attention/3`, `collect=pass`, `report:action=fail`, `report:checkpoint=fail`; remaining report stages passed). The output includes two `delivery_unknown` keys; this run is not DD05-source evidence.
- `capafy-distribute-daily` remains safely fenced on `a299acc04573ab916fb261ad7ff94b1d3f79a119`. Latest occurrence `18de52a169f44300-51572` ended 06:49:16Z with `effect_status=unknown`, no provider receipt, and no official readback. The main fix is not deployed.

**Cursor reorder, 2026-10-14T10:43Z:** Old: DD05 production adoption, then DD06 Writer. New: finish Writer fence integration; add CTA-lineage-to-paid measurement; resume DD05 after current-main capacity recovery; then run a controlled Writer experiment and DD07–DD12. The local capacity check fails because the checkout is shallow; GitHub compare verifies donor 9c71a1a is a 49d9858 ancestor. The verified read-only requirement is 252653568 bytes, with 141164 KiB free at 10:43Z. The cleanup owner passed at 10:39Z but no fresh receipt is persisted; release reconciliation failed at 10:41Z.

**Current cursor readback, 2026-10-14T11:08Z (supersedes prior capacity numbers):** Current remote/local `origin/main` is `dfb8213c4a51dcbc74d925d4ee8ee136a1978e64`; the task worktree is at `7e8e37f39a886801ac2e4bddb76026c5e64d5b33`, based on `13f59bca114e48e284b3b55fee1c1f450c66b2c0` (current main is 15 commits ahead, 0 behind that base). `df` reports 168508 KiB available at 11:08Z; a 2-byte scratch-file write now succeeds, but the volume still reports 100% full. The cleanup owner failed at 11:08:06Z (`life-manager-disk-cleanup:18de60c1a2f71ed8-55795`, `storage_write_failed_pre_effect` / `scratch_enospc`, no evidence refs); its last successful terminal was 10:58:44Z and there is no fresh receipt. The capacity requirement for `dfb8213` is unmeasured; do not reuse the 252653568-byte figure measured for `49d9858`. The dirty worktree still has four tracked edits; preserve its untracked `.DS_Store`.

**Cursor/order change, 2026-10-14T11:08Z:** Old cursor: integrate the Writer fence patch, then build CTA-to-paid measurement. New order: (1) restore scratch writes through the registered cleanup owner and synchronize the task branch to current main; (2) rerun fence tests and complete review/CI/integration; (3) implement CTA lineage and destination identity using the existing Web funnel/Writer join; (4) resume DD05 release adoption after a fresh capacity gate; (5) establish a mature outcome baseline, then run a controlled experiment; (6) continue DD07–DD12. Reason: current main advanced beyond the branch base and the cleanup receipt remains stale. Do not manually clear the active cleanup owner or any effect fence.

**Writer cursor**

1. [x] Add resumed-run RED case; expected inconclusive/run_reached_publication was observed.
2. [x] Pair publication rows with attempt starts from valid run directories; validate IDs and refuse symlink paths. AST and diff checks pass.
3. [x] Real read-only reconcile returns effected with 4 HTTP 200 URLs and closed=false; resolver test double passes without production mutation.
4. [x] Run the focused fence suite (24 passed); real read-only reconcile returns four HTTP 200 URLs, effected/closed=false; injected resolver test did not mutate the fence.
5. [x] Push dedicated PR #8037, synchronize it with latest main, pass all 11 automated checks on exact head `8e7df3c`, and merge as `e0a53f1`. The post-merge spec/plan cursor PR #8044 also merged as `1d1c012` after all 11 automated checks passed. This completes source integration only; production release/apply remains a separate DD05 gate. Never resolve manually or replay.
6. [x] Classify all 8 retained runs; 14/439 ledger rows join. Dispatch, prepublication ambiguity, identity-gate block, pending run state, and outcome-coverage gap are distinct.

**Writer CTA outcome measurement — required before experimentation**

1. [x] Preserve `product_id`, `run_id`, `artifact_id`, `variant_id`, and `click_id` from `/lm` through the signed auth cookie, `lm_users.web_first_touch`, funnel events, and report grouping. Task 6 verified OAuth first-touch and paid/refund report fallback by exact identity; no new table or migration was needed.
2. [ ] Rewrite the CTA at each publisher boundary so every actual publisher pair (`note/ja`, `substack/ja`, `substack/en`, `x-article/ja`) has a distinct `click_id`; keep the frozen article-level `artifact_id=article-ja|article-en` unchanged and add no new tracking field.
3. [ ] Reuse `lm_web_funnel_events`, `lm_users.web_first_touch`, `lm-web-funnel-report`, and Writer `product_lineages`/`money_artifacts`. Map only exact publisher click IDs to the existing `run_id__platform__lang` artifact key; keep request counts separate from unique people.
4. [ ] Verify per-artifact views/landing requests, activation, paid invoices, refunds/net, production cost, and intervention from exact receipts. Keep missing values unknown and do not run an experiment before the join works.

**DD05 remains open**

1. [x] Merge Writer DD06 source fix PR #8037 as `e0a53f1` after current-main synchronization; all 11 automated checks passed on exact head `8e7df3c`. CodeRabbit skipped manual review. Source integration does not establish production release/adoption or revenue.
2. [ ] Obtain a fresh exact release-capacity measurement for then-current `origin/main`. The requirement for `dfb8213` is unmeasured; the 252653568-byte result is historical for `49d9858` only.
3. [ ] Recover only the newly measured shortfall through the registered cleanup owner; preserve protected and unknown paths. Do not treat a passing process terminal without a fresh receipt as capacity recovery.
4. [ ] Cut/apply a main-derived immutable release only after the exact gate; verify installed SHA and natural owner terminal.
5. [ ] Inspect the persisted attribution sweep. The 08:36Z artifact has 0 eligible rows, 0 snapshots, 1323 legacy-uninstrumented and 31 unpublished rows.
6. [ ] Verify a unique exact-identity publication after 24h maturity or keep DD05 open. Revenue/cost/intervention remain unknown without exact sources.

HTTP 200 proves publication only; resolver test double left fence open.

**Separate operational cursors**

- [ ] Adopt the merged PR #8022 source only after the standard release gate passes, then reconcile `capafy-distribute-daily:18de4680b4bcfe18-18857` with occurrence-bound official evidence; do not clear or replay it.
- [ ] Reconcile the two `delivery_unknown` rows only from exact history/receipt evidence; never resend or edit the ledger manually.
- [ ] Continue capacity diagnosis through the registered cleanup owner; preserve protected and unknown paths.

DD05 is shared publication-measurement infrastructure. The first agent-level EDD vertical slice remains Writer as recorded in the SSOT; Capafy distribution reuses this evidence path when exact per-publication outcomes exist.


**Verification attempt, 2026-10-14T11:11Z:** The focused Writer command `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider skills/writer-agent/tests/test_article_fence_reconcile.py` exited 1 before collection: pytest reported no usable temporary directory while creating capture files. This is not a test failure or pass. The 11:08 two-byte scratch probe did not restore pytest temp-file capability; DD06 verification remains open, and no current-main test result is claimed.


**Verification update, 2026-10-14T11:15Z:** `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider skills/writer-agent/tests/test_article_fence_reconcile.py` passed 24/24 on worktree HEAD `7e8e37f`; AST and `git diff --check` also pass. This is source-only; latest-main sync, CI/review, integration, release, and natural readback remain open. Git-reported orphan packs totaling 15990784 bytes were reclaimed after confirming no open handles. The cleanup owner still has no receipt after its 11:08Z `scratch_enospc` failure; exact capacity for `dfb8213` remains unmeasured. The current pytest temp `pytest-505` was removed; older temp dirs were preserved.

**Current branch state, 2026-10-14T11:56Z:** GitHub `main=72ff5f9` is integrated locally by merge `6418770`; branch `fix/writer-resumed-publication-fence-20261014` has a four-file diff. The focused Writer suite passes 24/24 on the merged 72ff tree. PR #8037 is open with remote head `1c9c553` and base `72ff5f9`; its merge conflict is resolved locally, but the updated head is not pushed yet. CodeRabbit passed on the previous head and skipped manual review; exact-head checks remain pending. At 11:56Z, `df` showed 184236 KiB free; cleanup last passed at 11:45Z but `last-receipt.json` remains dated 2026-10-10. Exact release capacity is unmeasured. Production release, owner adoption, and natural readback remain open. Preserve `.DS_Store` as untracked.


**PR readback, 2026-10-14T12:12Z:** PR #8037 is OPEN and CLEAN on `main=72ff5f9`, head `553e882`; all automated checks pass. CodeRabbit skipped manual review, and self-review found no Critical or Important issue. The merged-main Writer suite is 24/24. This doc update creates a new head and requires fresh exact-head checks. After checks pass, merge using the authorized no-human-loop path; CTA lineage, DD05 production adoption, baseline/experiment, and DD07–DD12 remain open. Exact release capacity and natural business outcome remain unverified.

**Latest-main synchronization, 2026-10-14T21:32Z:** main `70a9ead` is integrated with a non-force merge commit whose parents are the prior PR head `10301b7` and current main. The local fetch failed with ENOSPC; this server-side Git Data merge preserves the latest main tree and the four intended PR files. The new head reruns CI. Exact release capacity remains unmeasured; no production apply or provider effect is claimed.


**DD06 closeout, 2026-10-14T14:15Z:** PR #8037 merged as `e0a53f1`; tested head `8e7df3c` passed all 11 automated checks. PR #8044 merged the post-merge cursor update as `1d1c012`; its tested head `f281cdb` also passed all 11 automated checks. Writer source integration and its status update are complete. Next EDD atom: preserve Writer CTA lineage and destination identity through the existing funnel. Production release/adoption, natural publication, per-artifact outcomes, revenue, cost, and intervention remain unverified.

### Task 6: Preserve Writer CTA identity through the existing Web funnel

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`, EDD DD06 closeout and current cursor.

**Goal:** Carry `product_id`, `run_id`, `artifact_id`, `variant_id`, and `click_id` from the Writer `/lm` CTA through signed attribution, Google OAuth first touch, Web funnel events, and report grouping. Keep landing-request counts separate from unique authenticated people. Stripe paid/refund rows resolve attribution through the existing `lm_users.web_first_touch` join.

**Constraints:** reuse `web_first_touch` and `lm_web_funnel_events`; accept the complete five-field lineage tuple or omit the tuple, never persist a partial identity. No new table, scheduler, provider call, production release, or external publication. Invalid, duplicate, or oversized IDs fail closed without blocking sign-in. Per-publisher click IDs are Task 7.

- [x] Add failing tests for `/lm` → OAuth forwarding, signed-cookie/first-touch/event propagation, and per-lineage report grouping with distinct click IDs.
- [x] Observe RED at each boundary: the OAuth link omitted five IDs, the signed cookie/first-touch retained only UTM, and two click IDs collapsed to one report bucket.
- [x] Extend the existing allowlist and report identity key with an all-or-nothing bounded tuple; preserve legacy UTM behavior and the JSONB schema.
- [x] Run the focused Web CTA suite (69/69), related non-database Web unit suite (281/281), report CLI tests (5/5), `git diff --check`, and source-boundary (PASS).
- [x] Mark Writer CTA outcome measurement item 1 complete. Keep destination identity, Writer artifact joining, exact outcome receipts, revenue/cost/intervention unknown, and experiments held.
- [x] Update PR #8046 with `/lm` link forwarding, report CLI regression, and focused Web CTA CI coverage; sync to main `328bb607`, pass all 13 required exact-head checks, merge as `be10731`, and read back main. Source integration only; no production release or provider action is part of Task 6.

**Task 6 evidence, 2026-10-14T14:41Z:** the complete five-ID tuple passes through `web-page.js`, the signed HMAC cookie, OAuth first-touch, append-only events, and per-lineage report groups; incomplete or unsafe tuples are dropped. The report keeps landing requests separate from unique people. After integrating the all-or-nothing CTA contract, focused tests pass 69/69, the non-database Web unit suite 281/281, and the report CLI suite 5/5. No provider, database, or external publication call was made. Publisher-specific click IDs and exact Writer artifact joining remain Task 7.

**Dependency ruling, 2026-10-14T14:39Z, superseded by the click-id contract:** the current CTA `artifact_id` is article-level (`article-ja`/`article-en`), while `artifact_attribution.py` derives one key per `run_id + platform + lang`; one CTA is reused across publisher copies. Old order: preserve fields → join Web report to Writer artifacts → assign a separate destination field → verify. New order: preserve fields (Task 6) → generate a distinct existing `click_id` for each publisher pair while preserving the frozen article identity → join each exact click receipt to the existing Writer artifact/money lineage → verify outcomes. `product_lineages.click_id` is already a primary key, so do not add a sixth attribution field. This ruling is recorded in the active SDD ledger; channel-level outcomes remain unscorable until publisher rewriting is verified.

**Task 6 final integration, 2026-10-15 00:40 JST:** PR #8046 merged as `be10731c00a326fdf9ebaf071391cb73efeae522` from tested head `10922cc743cf794b913f5759fb11edcd4ac19e04`, based on main `328bb607ac33668924293942e13c293f00833e8b`. All 13 required automated checks passed, including Web CTA attribution, Writer receipt grading, Loop control, TruffleHog, and Gitleaks; CodeRabbit reported its manual review skipped. Local focused Web tests passed 70/70; report tests passed 5/5 with Stripe intentionally unavailable, proving injected-client isolation. Main readback returned the merge commit. No release, provider, publication, or payment action ran.

**Task 7 acceptance contract:** derive one deterministic outbound CTA copy per active publisher pair (note/ja, substack/ja, substack/en, x-article/ja) from the frozen language draft. New Step 5 manifest rows opt in with ARTICLE_PUBLISH_CTA_V1=1; rows without it retain legacy source behavior. Change only click_id, appending the stable pair slug (note-ja, substack-ja, substack-en, x-article-ja); preserve product_id, run_id, article-level artifact_id, variant_id, all other bytes, and the source draft SHA. Store copies and receipts under ARTICLE_RUN_DIR/gates/publisher-cta/; each receipt binds pair, five-field lineage, source SHA, copy SHA, and copy path. Staging retries reuse byte-identical copies. run.sh and X staging keep quality/safety checks on the frozen source but send the verified copy; X same-ID repair and execute-initialization-pair.py reuse it. publication_remote checks body readback against the pair copy while artifact_sha256 remains the source SHA. Resume code-file fences include publisher_cta_copy.py wherever publication_remote.py is bundled. contract.json distinguishes new v1 runs from historical ones. Missing, duplicate, unsafe, oversized, or ambiguous CTA fields and conflicting receipts fail before publisher calls. Add no query field, table, schema migration, provider call, release, or publication.

**Task 7 source sync and acceptance — 2026-10-15 01:38 JST:** Dedicated worktree /Users/anicca/Projects/life-manager-main/.worktrees/writer-publisher-clickid-20261015, branch fix/writer-publisher-clickid-20261015, lease owner codex-dd07-writer-20261015. Task 7 now covers dispatch, Note/Substack/X staging, X same-ID repair, initialization recovery, pair-bound receipts, and copy-aware readback with source artifact hashes preserved. The branch includes latest main c30c552 plus SSOT update 8b7e9d2 via merge commit 7bdf2c8. Focused Writer pytest: 43 passed, 5 subtests; v1/legacy dispatcher and run paths, X staging and repair, initialization recovery, publication readback, source-boundary and syntax checks all pass. Next: update the cursor to this synced state, commit/push, pass exact-head CI, merge, and verify main. No provider read or publication action ran.

**Prior DD07 checkpoint — 2026-10-15:** Main advanced to `a91a31a9beeb61def0d522ec3e3e5e144ab1c49f` during PR #8062 CI and is integrated locally as `20aa8af753774fe570885df995fa820f32f29c8a`. After sync, the focused Writer suite passes 43 tests and 5 subtests; dispatcher, `run.sh`, X copy checks, and source-boundary pass. PR #8062 must be pushed at this new head and exact-head CI rerun. The exploratory full prepublication-recovery selection exposed a main-baseline source-hash mismatch in `quality_repair_control.py`; details and reordered follow-up are recorded in the canonical SSOT. No provider publication or revenue is claimed.

**Task 7 complete:** PR #8062 merged as 5c83b1f113402f18b7700fac91e60c9ed431db61 from exact head 20fab4d3190b684e41ff4bd786bc074d27158429; latest-base first parent is ac6fbab7a4c8112d71b9a5deda144d13027f577e. Run 38620171267 passed all 12 exact-head checks. The branch-local duplicate Capafy asset workaround is removed because main PR #8068 supplies the canonical digest. The detached-child test fix waits for exact marker contents; latest-main loop suite passed 572 tests/144 subtests locally. Stale conflicting PR #3414 is closed as superseded; branch retained. No publication, production release, owner apply, or revenue is claimed.

**Task 8 — historical Writer recovery source authorization**

**Decision:** Keep `QUALITY_SELF_HEAL_ORPHAN_OCCURRENCE_SHA256=42a50…`. Fresh read-only review confirms it matches four historical `quality_self_heal.py` revisions. Current source `ea54ee37…` was introduced by `568a046` and adds unbound editorial receipt rebinding plus `repair-unbound-force`, which may request `force_publish_advisory`. Replacing the pin would broaden historical recovery authorization; passing tests after that replacement is not provenance evidence.

**Local correction:** `quality_repair_control.py` remains unchanged. Recovery success/guard tests for the historical source are skipped unless the checked-in source matches its pinned digest, so they no longer pass vacuously against a different source. An always-on test builds a historical owner-recovery state and verifies current source refuses rearm without changing state, prompt, or receipts. Mutation check: temporarily pinning `ea54…` made the new test fail because `plan()` returned READY. Focused `test_prepublication_adoption.py`: 19 passed, 4 source-specific tests skipped, 21 subtests passed. No production apply, publish, or release occurred.

**Source integration:** PR #8081 merged as `56f63d7ef47db1fc416e444f38ac2e1e9f2c6dac` from tested head `76ab610b80d857a2e97912e4885bc0139a0fd5cd`, based on `b974b916d17312363f2be222511ea32907f3ba32`; exact-head run `38624820774` passed 12/12. PR #8083 merged the post-merge cursor as `f724520b8acbc121db2ec7de14465d6337ad9b60`; PR #8086 merged the active-fence chain update as `38c66a7864ae6cca4d4afddfa54033ed9ed701a2`, also with 12/12 checks. The source pin and production source are unchanged.

**Latest runtime readback, 2026-10-15 05:22 JST:** `article-daily` is loaded-idle, no PID, installed SHA `222d1e1…`. Latest occurrence `article-daily:18de7d96d81e12a0-67445` (event release `222d1e1…`, 19:56:41Z) exited 75 in `report`; event `effect_status=unknown`, provider receipt/readback absent, `official_readback_required`. The matching log line at 04:56:39 JST blocks run `20261014-152454` with `same-jst-day-unclassified-run`. Its bound scratch contains owner-owned mode-0600 `entrypoint-result.json={"status":"pre_effect_failure","effect":0}`, host admission `pass/resource_slot_acquired`, a remaining `.terminal-unrecorded`, and zero stderr bytes. `pre-effect-reconcile --dry-run` returns no resolved or unprovable candidates, and status says `admission_effect_unknown.current=false`. This latest invocation stopped before the model pass; it does not resolve the older run's effect.

**Blocking same-run chain:** `writer/runs/20261014-152454/gates/generation-state.json` is `provider-failed-ambiguous`, attempt 1 returned 1 at 15:34:58Z, and the run has no `publication-state.json` or matching ledger row. The 00:35 JST log explicitly says the same-run generation reconciler owns recovery; later daily wakes keep blocking on that run. No-publication-state/ledger absence is not a no-effect proof.

`article-resume` is that reconciler, but an active host fence remains for `article-resume:18dd959f92920ff0-56630` (event release `6f25bb2e…`, 2026-10-11T21:17:16Z, exit 1). Its error was the old `quality_feedback_recovery.py` sibling import failure plus publication-state file refusals. PR #7705 fixed the sibling import, and the loaded `222d1e1…` release contains that fix. At 21:09:07Z, `article-resume:18de818db72a88d0-76428` remains deferred before entrypoint by the same old fence, with no provider receipt/readback.

The newer `article-daily:18de8131fb8499a0-64801` occurrence ended at 21:02:37Z with exit 75, `effect_status=unknown`, and no provider receipt/readback. Its bound scratch says `pre_effect_failure`/`effect=0`; that describes this wake only and does not classify the older ambiguous `20261014-152454` publication. Do not replay either run.

Direct read-only `article_fence_reconcile.py --occurrence article-resume:18dd959f92920ff0-56630` returns `inconclusive/fence_too_young`. Claim time is `2026-10-11T21:04:08.921756Z`; the 7-day minimum age is `2026-10-18T21:04:08.921756Z`. No manual `--resolve`, wake, replay, or publisher action ran. Existing automation owns the check: `lm-fence-reconciler` runs every 600 seconds, with at most 20 adapter calls per pass, and the registry passes `--resolve` to this adapter. Its append-only call log lacks per-row timestamps; use an observation time from live `lm-loop` readback for freshness. Natural passes at 21:15:49Z, 21:26:28Z, and 21:37:54Z succeed after the 21:06:45Z `sqlite3.OperationalError: database is locked`. The current `article-daily` occurrences `18de8131fb8499a0-64801` (age gate 22:02:33Z) and `18de82fd7de2bf68-26607` (age gate 22:35:33Z) remain absent from the adapter log; both exact run markers say `pre_effect_failure`/`effect=0`, but their publish event classifications remain unknown. The call log has 244 article-daily outcomes across 14 occurrences. For `article-daily:18de6ec41cff5140-87565`, it records a successful `pre_effect` closure without `closure_proof`; the central closed-proof reader recognizes zero article-daily closures, and a later attempt returns `occurrence_not_fenced_or_unreadable`. Root cause: Writer closure output omits `owner_id` and `verified=true`; the resume output uses `proof_ref`, which the central does not accept, and the adapter cannot re-read already-released rows because `_admission_row()` filters for `effect_unknown=1`. This requeues previously closed occurrences and consumes the bounded call budget.

**Cursor correction:** the adapter-to-central proof contract fix is merged and adopted. Release `20261015T065802-a5ea4040` was cut from main SHA `a5ea4040f280571b5ce92cda853ac0923b03ca7b`; `RELEASE.json` records `cut_at=2026-10-14T21:58:31Z` and physical-capacity requirement 253,915,136 bytes. The cutter passed. Owner-targeted `lm-loop apply --loaded-idle-only` succeeded for `lm-fence-reconciler`; installed SHA and loaded argv point to that immutable release. Current cursor: wait for a natural pass on the new SHA and verify a release-bound closure proof and retry suppression for the exact closed occurrence. No provider effect, manual resolve, or wake.

**Atomic TODO, in order:**

- [x] Compare source-hash history and current-source changes; obtain fresh read-only provenance review; preserve the historical pin.
- [x] Change current-version acceptance to require fail-closed refusal without state mutation; gate historical-only tests on exact source authorization; verify widened-pin mutation is caught.
- [x] Update canonical SSOT with the ruling and current live readback.
- [x] Commit/push and merge PR #8081; exact-head run 38624820774 passed 12/12 checks; verify merge SHA `56f63d7` on main.
- [x] Merge the post-merge evidence/spec cursor in PR #8083 (`f724520`); preserve the no-effect/unknown distinction.
- [x] Merge the blocked-recovery chain update in PR #8086 (`38c66a7`) with 12/12 exact-head checks.
- [x] Replace the manual fence-run action with monitoring the existing central adapter; PR #8092 merged as `bc4ae57e4559eb158001d7538c14805351829424`, exact-head run `38634783402` passed 12/12 checks.
- [x] Verify the next natural central reconciler pass after the 21:06:45Z SQLite lock failure; the 21:15:49Z pass succeeds with no closures and no repeated lock. Diagnose/repair the query contention if it recurs.
- [x] Correct the log-count and latest Writer/runtime cursor in PR #8096; merge `39d81d52125d8d0f72e24e71e6cad72629ae46cb`, exact-head run `38639040871` passes 12/12 checks.
- [x] Add three RED tests proving active closures emit central-required `owner_id`, `verified`, and evidence fields, resume `proof_ref` is normalized, and released rows are re-read without mutation; observe the three expected failures.
- [x] Implement the minimal Writer response/idempotent readback fix; focused Writer and central suites pass 133 tests/21 subtests, with released admission state unchanged by re-read.
- [x] Merge PR #8099 as `a5ea4040f280571b5ce92cda853ac0923b03ca7b`; exact-head run `38642599971` passed 12/12 checks.
- [x] Cut main-derived immutable release `20261015T065802-a5ea4040` from `a5ea4040f280571b5ce92cda853ac0923b03ca7b`; exact capacity requirement 253,915,136 bytes passed. Apply only `lm-fence-reconciler` with `LIFE_MANAGER_APPLY_TARGET=lm-fence-reconciler` and `--loaded-idle-only`; read back the installed SHA and immutable argv.
- [ ] Wait for a natural `lm-fence-reconciler` pass on SHA `a5ea4040f280571b5ce92cda853ac0923b03ca7b`; verify a release-bound `closure_proof` for the already-released Writer occurrence and that it is no longer retried as `occurrence_not_fenced_or_unreadable`. Do not manually resolve or wake.
- [ ] Let the central adapter classify `article-daily:18de8131fb8499a0-64801` after `2026-10-14T22:02:33Z` and `article-daily:18de82fd7de2bf68-26607` after `2026-10-14T22:35:33Z` using each bound pre-effect proof; keep each `effect_unknown` until its exact occurrence is proven closed and do not replay.
- [ ] Monitor the exact `article-resume:18dd959f92920ff0-56630` result through live `lm-loop` readback, recording observation time; after `2026-10-18T21:04:08.921756Z`, require the automatic adapter's official readback/ledger result to close the occurrence. If still inconclusive, diagnose the returned reason and keep the fence; do not invoke a manual resolve.
- [ ] After exact fence clearance, let `article-resume` naturally recover run `20261014-152454`; verify the loaded sibling-import fix, terminal state, and official provider readback. Do not manually wake or replay.
- [ ] Once that run is safely classified, verify start-control releases the next natural `article-daily` run and count only official publication receipts.
- [ ] Continue the Writer EDD lane by joining exact publisher click receipts to artifact/money lineage, then mature outcome/fee/refund/cost evidence; run a controlled experiment only if sample size supports it. Keep the historical pin unchanged; any current-source recovery feature needs a reviewed release/source/run-bound authorization contract.


**EDD integration checkpoint, 2026-10-14T12:52Z:** Current main is `3de213777ef82996ada82ea6bbc4d898afcee7a9`. Before synchronization PR #8037 was head `04a0b1c4145e4f73d6ca6314bdb7699c2e831c0f`, based on `70a9ead`; its prior-head checks all passed, but main advanced and the branch conflicted. This update creates a non-force merge commit with the current main parent and preserves the PR four intended files. Exact-head checks rerun on the new commit. Writer source/test are unchanged by this sync. No current-main local pytest, capacity measurement, release adoption, natural outcome, or revenue is claimed. After integration, CTA lineage and destination identity are the next EDD implementation atom.


**DD06 status update, 2026-10-14T13:13Z:** PR #8037 is merged as `e0a53f1`; its tested head `8e7df3c` passed all 11 automated checks. Current main is `6f40a0c9c96a91bfc561bbb23a6d905cfb987b93` after PR #8045. PR #8044 carries only the post-merge spec/plan update and has been synchronized with current main; its new exact-head checks are pending. Next EDD atom is CTA lineage/destination identity. Production release, adoption, natural outcome, and publication-level revenue remain unverified.
