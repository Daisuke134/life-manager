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
- Do not clear or replay historical `effect_unknown` occurrences. JP1's old `provider_readback_not_exact` occurrence remains quarantined.
- `gate-approved` delegates only pack choice to the per-job approval artifact. It does not skip `assertPack` or `assertApproval`.
- Use only a pushed main-derived immutable release, a loaded-idle owner-scoped apply, and natural scheduled slots. Never manually start a publishing owner.
- Evaluate Postiz self-hosting separately; it cannot bypass Life Manager's publication fence.

## Review Focus

- Only the six native-carousel lanes that set `rotationEnabled` receive `gate-approved`; static lanes remain pinned.
- Each generated pack has a matching per-job approval artifact with exact ordered media and caption hashes.
- The old JP1 unknown occurrence stays unchanged, while a new slot has a distinct content/slot effect identity.
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

### Task 4: Repair the Postiz profile/native-handle join, then canary the next TikTok slot

- [x] The rotation and video-integration source fix passed acceptance and review; PR #6867 is merged at main `62ebd9b1b7dff499099ce62231435c902c04427d`.
- [x] Main-derived immutable release `67ec029d47a54013ca5838786680c4a700fd5291` contains the six `gate-approved` routes. A loaded-idle, owner-targeted apply to `life-manager-anicca-jp1-tiktok` succeeded and loaded SHA now matches `67ec029d`; the global `disk-writers.stop` remains owned by host recovery and was not cleared.
- [x] Official Postiz `GET /public/v1/posts` for 2026-10-07 JST returned 21 rows below the 100-row limit; 17 were `PUBLISHED` across 19 active targets. TikTok had 6 `PUBLISHED` posts across 10 targets, with 6 accounts at zero; no account reached 3/day.
- [x] Root cause isolated for old JP1 readback: the local receipt and Postiz detail agree on provider post ID, integration, PUBLISHED state, CTA-adjusted caption hash, and local six-image/order hashes. Postiz `/integrations` returns configured `postiz_profile=@anicca.jpx`, while the source identity's `account_id` is the manifest `native_handle=@anicca.jp1`. `mobile-postiz-provider-reconcile.py` compares these different fields and incorrectly rejects the receipt.
- [ ] Add a RED regression test for the JP1 destination mapping, then make reconciliation compare the official profile with the matching destination's `postiz_profile` and bind `identity.account_id` to its `native_handle`. Reject wrong platform, integration, native handle, or unexpected profile.
- [ ] Run the focused Python tests, the relevant native-carousel and publication-contract tests, `./bin/lm-loop-contract`, `npm test`, and `git diff --check`; push and merge only after acceptance/review.
- [ ] Cut a current-main immutable release. The canary order changes from JP1-first to `@aniccaaffirmation` TikTok because its next natural slot is 20:15 JST while JP1's 18:00 slot has passed. Apply only `life-manager-anicca-en-affirmation-tiktok` when loaded-idle; if 20:15 is missed, use its next 09:15 JST natural slot.
- [ ] Require exact Postiz `PUBLISHED` receipt for `@aniccaaffirmation` / `cmp93bkpu01uvoh0yd3aj560g`, matching identity and replay-zero. Keep the 18:00 JP1 occurrence fenced; use the corrected owner-bound resolver to validate its historical receipt before any next JP1 publication.

### Task 5: Stage the other five rotating lanes and restore 3/day TikTok cadence

- [ ] Only after the first TikTok canary passes, apply the same immutable release one loaded-idle owner at a time to EN affirmation Instagram, EN slideshow TikTok, JA main TikTok, JP1 TikTok, and JA Buddha TikTok.
- [ ] For each target, reconcile prior effects against its exact Postiz integration/profile, then verify the next distinct natural slot by official receipt. Keep the six configured media hashes/order and all three JST slots; do not replay ambiguous slots.
- [ ] Restore each of the 10 active TikTok targets to three `PUBLISHED` receipts per Asia/Tokyo day. Continue with the 7 Instagram and 2 YouTube active targets, then verify all 19 active targets (17 Mobile/Honne plus two eBook owners). A shortfall remains named; queued/scheduled posts do not count. Keep the 13 held integrations held.
