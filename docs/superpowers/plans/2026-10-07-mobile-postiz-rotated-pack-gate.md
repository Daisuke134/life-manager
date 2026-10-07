# Mobile Postiz Rotated-Pack Gate Plan

> **For agentic workers:** Use the TDD steps below in this worktree. Promote only through main and an immutable release.

**Goal:** Restore three natural daily posts on every configured Mobile/Honne target lane by varying slide text over the existing approved backgrounds, while preserving unresolved publication effects.

**Architecture:** Keep Postiz, account/integration IDs, and all three Asia/Tokyo slots. Reuse the cached approved backgrounds and generate fresh text/caption variants; the internal pack hash updates automatically. Set `approved_pack_ref=gate-approved` only for the six rotation-enabled Anicca native-carousel destinations; the existing slide-pack gate and `assertApproval` continue to verify each post's exact pack, ordered media, caption, account, and integration. Deploy one lane as a natural canary before staging the other five.

**Tech Stack:** Node.js tests, JSON destination contract, existing Mobile Postiz adapters, `lm-loop`, immutable release tooling.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`; `docs/superpowers/specs/2026-09-18-mobile-postiz-admission-recovery-design.md`.

## Global Constraints

- The current destination contract has 19 targets: 17 Mobile/Honne lanes and two eBook lanes owned separately. Keep all 13 held integrations held.
- **Ruling:** Treat “all accounts” as all 19 configured targets, with the two eBook lanes handled by their existing separate owner. Keep the 13 explicitly held integrations out because they are disabled, unsupported, unretained, or lack an integration. Cost if this scope is wrong: those 13 remain unposted until they receive a valid owner and provider mapping.
- Keep account IDs, integration IDs, format IDs, pack names, and cadence slots unchanged.
- Do not clear or replay historical `effect_unknown` without exact official Postiz proof. The exact JP1 9/27 receipt is resolved; unrelated or ambiguous occurrences remain fenced.
- `gate-approved` delegates only pack choice to the per-job approval artifact. It does not skip `assertPack` or `assertApproval`.
- Use only a pushed main-derived immutable release, a loaded-idle owner-scoped apply, and each lane's existing owner. When Dais explicitly requests catch-up for missed slots, use the existing slot-scoped path only after exact effect checks; never call Postiz directly or bypass an unknown-effect fence.
- Evaluate Postiz self-hosting separately; it cannot bypass Life Manager's publication fence.

## Review Focus

- Only the six native-carousel lanes that set `rotationEnabled` receive `gate-approved`; static lanes remain pinned.
- Each generated pack has a matching per-job approval artifact with exact ordered media and caption hashes.
- The exact JP1 historical receipt is resolved only after matching PUBLISHED state, integration/profile, caption, and six image hashes; other ambiguous historical effects stay fenced.
- A published local receipt for the same integration+slot blocks a second rotated pack, even if its pack/text hashes differ.
- The destination contract distinguishes 17 Mobile/Honne routes, two eBook routes, and 13 held integrations.
- A canary requires an exact official Postiz `PUBLISHED` receipt, identity match, and replay-zero before rollout to the remaining five lanes.

---

### Task 1: Preserve platform-specific integration references in video fanout

**Files:**
- Modify: `apps/life-manager/lib/marketing-video-publication-chain.js`
- Test: `apps/life-manager/lib/marketing-video-publication-chain.test.js`

- [x] Pass optional `instagramIntegrationRef` from the chain's options into the Instagram publication job.
- [x] Keep the TikTok job on `tiktokIntegrationRef`; do not infer that an Instagram account exists when its integration is absent.
- [x] Assert the generated Instagram and TikTok jobs carry distinct integration refs. RED showed TikTok's integration used twice; `node --test apps/life-manager/lib/marketing-video-publication-chain.test.js` now passes 7/7.

### Task 2: Pin the rotating-lane approval contract in tests

**Files:**
- Modify: `apps/life-manager/lib/marketing-destination-contract.test.js`

- [x] Correct the stale inventory assertions to match 19 total targets (17 Mobile/Honne plus two eBook), while preserving 13 holds.
- [x] Add a regression test that enumerates the six `rotationEnabled` native-carousel lanes, resolves each exact destination, and requires `approved_pack_ref === GATE_APPROVED`.
- [x] Update the JA-main launcher assertion to require `anicca-larry-ja-rotating.js`, the registered path that generates fresh creative variants.
- [x] Keep a static non-rotating lane pinned to its exact object reference.
- [x] Watch the rotation assertion fail against the current pinned values before applying the configuration.

### Task 3: Allow fresh approved packs on the six rotating lanes

**Files:**
- Modify: `config/marketing-destinations.json`
- Test: `apps/life-manager/lib/marketing-destination-contract.test.js`

- [x] Change only `approved_pack_ref` for EN affirmation Instagram, EN affirmation TikTok, EN slideshow TikTok, JA main TikTok, JP1 TikTok, and JA Buddha TikTok to `gate-approved`.
- [x] Leave all profiles, integrations, pack names, formats, three daily slots, eBook destinations, and held integrations unchanged.
- [x] Run destination-contract, local-ledger, native-carousel, video-chain, and launcher tests: 70/70 pass. Full `npm test` passes 1,455/1,455.
- [x] Run `git diff --check` and `./bin/lm-loop-contract` (18 catalog loops, 186 registry jobs, 111 mapped jobs, zero errors).

### Task 4: Repair the Postiz profile/native-handle join and complete the first TikTok canary

- [x] The rotation and video-integration source fix passed acceptance and review; PR #6867 is merged at main `62ebd9b1b7dff499099ce62231435c902c04427d`.
- [x] The provider reconciliation fix passed TDD/review; PR #6900 is merged at main `069e580a2a567b9305f1d936d85f21bee5510ec8`. It compares the official integration profile with `postiz_profile` and binds identity `account_id` to `native_handle`.
- [x] Main-derived immutable release `80ea586cfa61b50d360f3627cc13320731efaf6d` was applied only to `life-manager-anicca-en-affirmation-tiktok`; loaded argv and `lm-loop status` both read that SHA, loaded-idle. The shared `publication-effect-fence.json` remained closed.
- [x] The first natural TikTok post is verified: `@aniccaaffirmation` / integration `cmp93bkpu01uvoh0yd3aj560g`, Postiz ID `cmuy0i4sb05qrqh0ygx0g2u6w`, PUBLISHED at 20:16 JST for the 20:15 slot. The local identity, six media hashes/order, base caption, CTA-adjusted caption hash, and receipt match. The exact occurrence is `released` with `effect_unknown=0`; an independent read-only review passed.
- [x] At 20:15 the first wake was deferred with `resource_capacity_busy` while `lancers-revenue-application` held the only agent reservation. That exact occurrence remained queued with `effect_unknown=0`; the existing queue resumed after capacity freed and produced the verified post. No manual Postiz request was sent.
- [x] Fresh Postiz list readback at 20:29 JST returned 29 rows below limit 500. The 19 active targets had 25 `PUBLISHED` posts against 57/day: TikTok 9/30, Instagram 10/21, YouTube 6/6. Two targets met 3/day; five had zero. TikTok profiles at zero: `@anicca_slideshow`, `@anicca.jp`, `@anicca.jpx`, `@honne_reveal`; Instagram profile at zero: `@ani.cca1234`.
- [x] Later official `GET /public/v1/posts` readback at 20:44 JST returned HTTP 200 / 32 rows. The ten TikTok targets had 11/30 `PUBLISHED` today: `@aniccaaffirmation` 1, `@anicca_slideshow` 0, `@anicca_buddha` 3, `@anicca.he` 2, `@anicca.jpx` 0, `@anicca.jp4` 1, `@anicca.jp` 0, `@obou_anicca` 2, `@honne_reveal` 0, `@honnevideo` 2. Nine of ten are below 3/day; four are at zero.

### Task 5: Fix post-success liveness and bound one publication per slot

- [x] RED: reproduce the live case with `public_url=null`, `PUBLISHED`, `DIRECT_POST`, base caption hash different from provider caption hash, and provider hash equal to `caption_with_cta_sha256`.
- [x] Accept only the exact final caption hash in `caption_with_cta_sha256`; no base-caption fallback is allowed because the verified photo receipt requires the CTA hash. Provider state, direct-post method, lane, local media hashes, and order checks remain required.
- [x] Keep the alternate-pack test aligned with the current rotation contract: a gate-approved pack with matching per-job approval proceeds; mismatched pack/approval remains covered by native-carousel contract tests.
- [x] Runner-level regression test reproduced the old failure as `marketing liveness ref is invalid`, then passed with one mocked Postiz publish and one mocked liveness receipt; replay produced zero additional provider or Telegram calls. The canary suite now passes 16/16.
- [x] Fresh independent read-only review passed the exact CTA fix and the JP1 receipt. The reviewer confirmed the exact JP1 PUBLISHED post and six remote media hashes/order; it did not resolve any other occurrence.
- [x] TDD RED/GREEN proves an existing local PUBLISHED receipt for the same integration+slot returns `already_published` both before pack generation and after the generation await. The rotating wrapper skips the canary and returns the existing provider ID with `created:false`, so the loop records a reconciled no-op receipt rather than retrying. The standalone picker CLI also exits 75 for an already-published slot instead of dereferencing an empty selection.
- [x] TDD RED/GREEN proves `mobile-app` exits 75 before the publishing runner when exact prior-effect reconciliation is unresolved. The reconciler now returns `clean` only when the admission DB has no pending unknown occurrences; `no_match`, `inconclusive`, and remaining unknowns fail closed.
- [x] Focused checks pass: rotating/generator/mobile-wrapper Node tests 30/30; `test_mobile_postiz_provider_reconcile.py` 9/9.
- [x] After slot-fence/reconcile changes: full `npm test` exit 0; `./bin/lm-loop-contract` pass (18 catalog loops, 186 registry jobs, 111 mapped, zero errors); OSS verifier `ok=true`; `git diff --check` pass; provider-reconcile Python tests 9/9.
- [x] Fresh independent read-only review passed the latest slot fence/reconciliation diff and official Postiz readback for all eight Buddha posts. It confirmed the same 20:00 JST slot hash and no later post after the 21:08 JST bootout.
- [x] PR's first `OSS self-contained boundary` run exposed a stale main-branch 242-file digest for `skills/capafy-autopublish` (changed in merged #6902). Updated only the root inventory digest in `docs/manifests/oss-merge-1-sources.json`; the local canonical verifier now returns `{"ok":true,"violations":[]}`.
- [ ] After review, commit/push the slot/reconcile fix, rerun PR checks, merge to main, and cut a full main-derived immutable release.
- [ ] After the release, first re-enable one stopped carousel owner with no unresolved exact effect, then require exact PUBLISHED receipt, liveness success, local receipt, and replay-zero on its next scheduled slot. Keep other carousel owners stopped until they pass the same gate.

### Task 6: Roll out by platform priority and restore the daily target

- [x] At 20:46 JST, the existing reconciler re-read and resolved only JP1 occurrence `life-manager-anicca-jp1-tiktok:18d93079c413bdd8-4465` to exact official Postiz post `cmukc2o0j069ipr0y2gduabj9`; status `resolved`, proof kind `postiz_official_readback`. This historical post is not counted toward today's `@anicca.jpx` target.
- [x] Current official readback at 21:34 JST: 46 rows; ten TikTok accounts total 21/30 `PUBLISHED`: `@aniccaaffirmation` 1, `@anicca_slideshow` 3, `@anicca_buddha` 8, `@anicca.he` 2, `@anicca.jpx` 0, `@anicca.jp4` 2, `@anicca.jp` 0, `@obou_anicca` 2, `@honne_reveal` 0, `@honnevideo` 3. Seven accounts remain below target by 14 posts combined; Buddha is five over. Excess Buddha posts do not count toward another account's goal.
- [x] Eight Buddha posts were PUBLISHED from 20:27–20:54 JST. The local distribution ledger has all eight official post IDs, and every `effect_key` ends with the SHA-256 for the same 20:00 JST slot (`101d082e…d89471`). Each receipt has a different caption hash/text pack. This proves one due slot produced eight posts.
- [x] Root cause: the photo publication receipt is persisted, then the runner's base-vs-CTA caption hash comparison makes liveness parsing fail. Retry wakes re-enter the same due slot every 1–2 minutes. `marketingVideoDueSlot` returns the same slot; rotation selects another unposted text pack, whose changed pack/caption hashes make a new effect key, so each retry posts again. `target_daily_limit=3` only arms the lane; it does not enforce the count. `mobile-app` also logged and continued after unresolved prior-effect reconciliation because `--auto-owner` returned exit 0 for `no_match`.
- [x] After a fresh Aqua preflight, `lm-loop stop` booted out all five native-carousel TikTok owners: Buddha, EN affirmation, EN slideshow, JP1, and JA main (each `return_code=0`). The 21:23 JST Postiz readback shows no Buddha post after 20:54 JST. Do not delete the eight public posts.
- [x] The fresh reviewer confirmed the managed production route uses same-owner admission locking; the residual check/use race only applies to unsupported parallel direct runners or a second unregistered owner sharing the same integration. The lane manifest enforces one configured owner per integration; direct publication bypasses remain unsupported.
- [x] An EN slideshow historical unknown search found four PUBLISHED candidates with the same base caption in its slot window; the first candidate's six remote image bytes/order match, but its publish time is slot+6h and multiple duplicate captions/assets exist. This cannot uniquely bind the effect to one occurrence, so keep it fenced.
- [ ] Resolve the active host admission stop through its owner. `state/disk-writers.stop` still names `host-disk-recovery-installing` and `install_and_verify_all_finite_disk_guards_before_arming_recovery`. At 20:43 JST `df -Pk /` showed 12,134,996 KiB free, but current EN affirmation and Buddha owners still returned `disk_headroom_low`; free space alone does not authorize clearing the stop. The SSOT's last guard inventory was 120/149 installed at 17:47 JST, so refresh the guard receipt and reach the owner's full condition before publishing runs.
- [ ] Merge/release the CTA liveness fix, same-slot ledger guard, and fail-closed prior-effect gate. After exact-effect recovery and host stop are clear, re-apply the five stopped owners one at a time and verify exact Postiz receipt, liveness, local receipt, and replay-zero before each next owner. The three configured JST slots then enforce the 3/day ceiling.
- [ ] Bring the remaining static TikTok targets and the separate eBook TikTok owner to three `PUBLISHED` receipts per Asia/Tokyo day. Keep queued/scheduled rows separate from published counts and keep the 13 held integrations held.
- [ ] Then raise Instagram to 3/day, preserve YouTube's verified 3/day, and verify all 19 active targets at 57 `PUBLISHED` posts/day. Report any remaining target shortfall by exact account and owner.
