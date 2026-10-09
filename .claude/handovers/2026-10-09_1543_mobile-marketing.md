# Mobile marketing handover — 2026-10-09 15:43 JST

このhandoverはチャットから再開するための短い索引です。TODOの正本は統合SSOTのみです。

- Repo: `/Users/anicca/Projects/life-manager-main`
- Remote: `origin=https://github.com/Daisuke134/life-manager.git`
- 正本spec: `/Users/anicca/Projects/life-manager-main/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` の末尾「2026-10-09 15:43 JST — Mobile distribution readback and handoff cursor」
- Spec/handover branch: `docs/mobile-marketing-cursor-20261009`; spec commit `60e4c65b29c59aaa4ab4f0bf017d04a5baccc00f`; fetch branch to read the handover commit at its current tip.
- Intended local spec worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/mobile-marketing-cursor-20261009` (not created; local temp/worktree writes currently fail with ENOSPC).
- Implementation source PR: [#7369](https://github.com/Daisuke134/life-manager/pull/7369), branch `fix/mobile-prior-fence-current-occurrence-20261009-1448`, head `ff26ea6bb1bf865148731b7d98f34e2e0cc90012`, base `4dbf029551f660ae293bdd912c398f96f14d4a12`. All listed checks passed on that head; it is open and not merged. Main is now `770cbde0de01936a3ac09917cb2352debbf54330`.
- Shared root worktree is dirty on `capafy/annual-report-risk-change-brief-20261009` (unrelated `.claude/skills/`, `.codex/`, `skills/capafy/catalog/tiktok-shop-hook-lab/`); do not use it for this work.

## Verified state and limits

At 15:43 JST, read-only Postiz GET for the 10/09 JST day window matched all 18 Anicca/Honne integrations: 30 PUBLISHED, 0 SCHEDULED, 0 other mobile states. Per-account counts and the 29 account-level placements still needed for 3 each are in the spec. `@anicca.affirmation` already has 8 (5 over target), so do not add to it today. This is not proof of native views/engagement.

At 15:41 JST, all 18 configured mobile owners were loaded-idle with `admission_effect_unknown=true`; installed SHAs were mixed. `~/loops/current` pointed to `20261009T151254-a6e03757`, not all-owner adoption of current main. Unknown effects require exact identity/readback; never replay the same occurrence without proof. PR #7369 lets a separately admitted occurrence continue past an unresolved owner-wide prior claim; it does not release the same occurrence fence.

Disk showed 140,604 KiB available. Zsh here-doc creation failed with `ENOSPC`; Python reported no usable temp directory across its configured locations. No local worktree was created. This session made only GitHub branch/content commits; it did not post, change production config, restart owners, or alter credentials. Previously verified assets are 26 persistent PNG backgrounds reused without per-post image generation; this count was not refreshed in this checkpoint. ASC/RevenueCat/in-app metrics were not refreshed; $10K net MRR remains an unverified target.

## Remaining TODO order

1. Update PR #7369 to latest main `770cbde0`, run checks on the exact new head, and merge only when green.
2. Restore safe local write/temp capacity through the existing disk-cleanup owner. Preserve protected files/assets; do not delete by age or retry the failed here-doc.
3. Create clean latest-main implementation worktree at `/Users/anicca/Projects/life-manager-main/.worktrees/mobile-prior-fence-current-occurrence-20261009`, then build a main-derived immutable release and read back the release pointer and every target owner’s loaded SHA.
4. Read current-day Postiz and owner state again. Reconcile old unknown occurrences only with exact evidence; keep same-occurrence fences closed. Use the merged occurrence-scoped path for a distinct safe occurrence without waiting for a future slot.
5. For accounts below 3, catch up only the due deficit through their existing owner/API, with deterministic slot identity and stored PNGs. Do not exceed 3 for an account or count SCHEDULED as PUBLISHED. After the first receipt, continue independent TODOs without waiting for 3/day or day-close.
6. Record each Postiz PUBLISHED receipt and permalink. Read native per-post views/reach/engagement from an available official source; preserve unavailable values as unknown and include the permalink in Telegram reports.
7. Refresh ASC impressions/product-page views/installs, RevenueCat subscription/purchase/refund evidence, and the existing Mixpanel/PostHog onboarding/paywall funnel. Determine from current source whether missing events require an app release.
8. Iterate marketing copy/hooks/slide order with stored assets, then refine onboarding/paywall and notification-to-quote behavior from measured funnel evidence.
9. Calculate progress to $10K using verified active paid subscriptions and net settled receipts after refunds/fees. Do not report the target as reached without evidence.

## First safe resume action

Fetch and verify `origin/main`, PR #7369 head/base/checks, disk capacity, current release pointer, 18 owner statuses, and a fresh Postiz readback before any edit, apply, or post. Do not use the dirty root worktree. If disk/temp remains unavailable, diagnose the existing disk-cleanup owner and continue read-only source/PR work; do not remove protected state or assets.
