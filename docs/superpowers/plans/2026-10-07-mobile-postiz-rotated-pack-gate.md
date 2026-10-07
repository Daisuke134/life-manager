# Mobile Postiz Rotated-Pack Gate Plan

> **For agentic workers:** Use the TDD steps below in this worktree. Promote only through main and an immutable release.

**Goal:** Restore three natural daily posts on every configured Mobile/Honne target lane with distinct, per-job-approved creative variants, while preserving unresolved publication effects.

**Architecture:** Keep Postiz, account/integration IDs, and all three Asia/Tokyo slots. Set `approved_pack_ref=gate-approved` only for the six rotation-enabled Anicca native-carousel destinations; the existing slide-pack gate and `assertApproval` continue to verify the exact pack, media, caption, account, and integration for each post. Deploy one lane as a natural canary before staging the other five.

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

### Task 4: Promote JP1 as the first canary

- [x] Push the branch and open PR #6867. Focused acceptance and required checks are in progress; do not merge until they and the fresh read-only review pass.
- [ ] Cut an immutable release from merged `origin/main`.
- [ ] Read back the JP1 owner lock, loaded-idle state, admission identity, lane manifest, and `launchctl-safe` GUI preflight. Apply the release only to `life-manager-anicca-jp1-tiktok` via the targeted `LIFE_MANAGER_APPLY_TARGET` path.
- [ ] Wait for the next natural Asia/Tokyo slot. Require a terminal pass, exact Postiz `PUBLISHED` readback for `@anicca.jpx` / integration `cmlrv8jq000hun60yy57eaptx`, matching media/caption identity, and replay-zero. Keep the old unknown occurrence unchanged.

### Task 5: Stage the remaining five rotation-enabled lanes

- [ ] Only after the JP1 canary passes, apply the same immutable release one loaded-idle owner at a time to EN affirmation Instagram/TikTok, EN slideshow TikTok, JA main TikTok, and JA Buddha TikTok.
- [ ] Verify each natural receipt against its exact account and integration. Preserve three scheduled slots/day and require distinct approved packs.
- [ ] Read one complete Asia/Tokyo day of official receipts for all 17 Mobile/Honne targets. A lane below three published receipts remains a named shortfall; scheduled or queued posts do not count as published.
