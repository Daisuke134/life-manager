# English Monk eBook Instagram: verified launch and recurring owner

**Goal:** Publish the user's intended Hadrian video to the English Monk Instagram account, then run three unique posts per day through the canonical Life Manager/Postiz owner.

**Scope:** English eBook distribution only. Capafy remains with its separate owner. Keep English TikTok and Japanese eBook owners separate. Do not publish a different clip as the Hadrian video. Do not buy a HeyGen plan unless a later production-cost check shows it is needed.

**Disk admission:** PR #7179 supersedes numeric free-space floors in this plan. The old 512 MiB revenue floor is not an owner prerequisite; cleanup's 2 GiB recovery value is diagnostic only.

**Current evidence (rechecked 2026-10-09 03:44 JST):**

- `~/loops/current` points to `20261009T034745-e75c7f7a`; latest source main is `e75c7f7a` (including PR #7217). The English Instagram owner is registered in source and reports `loaded-idle`, but remains installed on older SHA `ee25a794751917116f6558e2cde798dcd5c5b5a2`. It has no occurrence or provider receipt; its diagnostic is incomplete and health is `telemetry_gap`. The English TikTok owner is also on `ee25a794`; its old unresolved occurrence remains fenced, so do not replay or use TikTok as a fallback.
- The current account registry has `publisher_integration_id=null` and `status=setup_required`; `marketing-destinations.json` has no active `ebook-en-instagram` target and keeps `@monk_anicca` under `english_monk_instagram_not_connected` with `target_daily_limit=0`. This hold must remain until the exact profile is normally verified and its enabled Postiz integration is read back.
- A completed HeyGen video does exist: direct `video get` for `db2dab0924e19b88c14e03a6a7849069` returns `completed`, 13.4 seconds. Its local file is `~/.local/state/life-manager/marketing/ebook/renders/ebook-run.571924dc4e4867349fc6fd13.mp4`, 1080x1920 H.264, SHA-256 `132d9b326059f9b74d6020e4bca50f0a77d2f2f5ca0595d2f2feb56449c12183`; the receipt records `$0.52` cost. The read-only script ledger identifies the copy as “When a mistake follows you,” not Hadrian. Do not publish it as Hadrian. The HeyGen list endpoint returns empty pages even though this exact ID lookup succeeds.
- The prior `Loop control contracts` failure is fixed upstream in PR #7200: the byte-stable macOS registry fixture now contains the `line-sticker-factory-hourly.effect_reconcile` field. Latest main includes that commit, and the focused byte-stable fixture test passes there. No line-sticker runtime behavior was changed in this task.
- Fresh authenticated Postiz GET at 03:44 JST returned 31 integrations / 9 Instagram integrations. The only `monk_anicca` row is TikTok integration `cmo5rwq2p00twn10yrsdglng3`, `disabled=false`; no matching Instagram integration exists. Postiz `posts:list` returned 242 records for 2026-10-01 through 2026-10-10 and zero records for that TikTok integration. This is not native Instagram history; no English Monk Instagram `PUBLISHED` receipt is verified. Evidence: `/Users/anicca/.local/state/life-manager/ebook/evidence/postiz-readback-english-monk-instagram-20261008T1844Z.json`.
- `instagram-english-monk` remains `phone_verification_pending`. Reading Messages through the existing host path is blocked by macOS privacy access, and the selected iPhone needs reconnecting for normal SMS verification. Use the normal Messages flow; do not change privacy settings or bypass verification. After verification, confirm whether the account is already ready/warmed; the seven-day warmup applies only if it is a fresh account.
- English TikTok and Instagram share the same eBook render receipt for matching product/slot times. The English three-slot cadence therefore targets 90 shared renders/month. HeyGen CLI reports `billing_type=wallet`, `$11.78` remaining, and `$10` auto-reload below `$5`; a prior eBook receipt measured `$0.52` per render, implying `$46.80` wallet usage/month at that cadence. The official [HeyGen pricing page](https://www.heygen.com/pricing) currently lists Creator at `$29/month` with 600 credits and Pro at `$49/month` with 1,000 credits, but does not prove these subscription credits cover this API wallet or specify credits per Avatar IV render. The user authorized a monthly plan if official API entitlement and 90-render coverage show it is needed; no plan was bought.
- The registry defines four distinct eBook social owners, each with three daily slots: English TikTok and English Instagram at 08:00/14:00/21:00 JST; Japanese TikTok and Japanese Instagram at 07:00/12:30/20:00 JST. That is 12 scheduled posts/day across four accounts, not proof of 12 successful posts. This task owns only the English Instagram lane's three posts/day; the other owners remain separate.
- `/monk` is a `$10.99` one-time eBook purchase; Daily Anicca Letter is `$9.99/month`. The last Stripe readback (19:37 JST) was 0 active paid Letter subscriptions and is historical; current live count remains unknown. 1,002 active subscriptions equal `$10,009.98` gross MRR before fees/refunds/costs, not the `$10K` net goal. Completion requires portfolio-wide settled revenue less refunds and measured costs with payout/bank readback.

## Ideal flow

```mermaid
flowchart LR
  A[Approved English baseline script] --> B[HeyGen Avatar IV render + SHA/cost receipt]
  B --> C[Verified and warmed English Monk Instagram]
  C --> D[Enabled matching Postiz integration]
  E[No numeric free-space floor] --> F[Owner: 08:00 / 14:00 / 21:00 JST]
  D --> F
  F --> G[Postiz PUBLISHED receipt + native Reel URL]
  G --> H[Tracked /go/ee campaign link]
  H --> I[/monk: $10.99 one-time eBook]
  I --> J[Paid order + delivered PDF]
  J --> K[Daily Anicca Letter: $9.99/month]
  K --> L[Stripe paid invoice + active subscription]
  L --> M[Net ledger subtracts fees, HeyGen, email/API costs]
  M --> N[$10K monthly net target]
  O[Hadrian existing video: exact ID, file, script and render receipt] -. one-off .-> P[Durable Postiz intent and no-duplicate check]
  P --> G
```

The recurring owner creates new clips from its approved baseline; it does not ingest the old Hadrian clip. That one-off needs a matching asset/script receipt and a supported Postiz intent before publication. Each of the four configured eBook accounts has three scheduled slots, for a 12/day portfolio schedule target; this workstream must prove only its English Instagram lane's three daily receipts. The one-time eBook is not MRR. 1,002 active $9.99 subscriptions equal $10,009.98 gross MRR before fees and costs; the net target needs a larger count based on actual unit margin and portfolio-wide reconciliation. Current Hadrian asset, Instagram verification, and Postiz binding remain unresolved.

## Acceptance detail (canonical order and status live in the unified SSOT)

The sections below define completion evidence for the English Monk Instagram work. Their order and live status are authoritative only in the unified SSOT. Capafy remains outside this plan.

### Source owner implementation

- PR #7173 is merged to `main` as `0f7cfb616dcb585a42868f2a5092c8cd9951675e`. Owner code, fail-closed `setup_required` behavior, exact-render slot reuse, three daily slots, and owner-scoped publication identity are in main.
- Focused acceptance before merge: Node 20/20; Python distribution owner 4/4; runtime loop bounds 138/138; targeted apply contract 2/2; fleet retry contract 34/34; loop contract 18 loops/188 jobs; `git diff --check`. Fresh read-only source review found no merge blocker.
- **Completion evidence:** source is in main. The owner is currently loaded-idle on installed SHA `ee25a794751917116f6558e2cde798dcd5c5b5a2`, behind current pointer `20261009T034745-e75c7f7a`. The exact Instagram integration remains a separate eligibility gate before publishing.

### Requested Hadrian asset

- HeyGen title searches for `Hadrian` and `Adrian` returned no matches. Exact ID `db2dab0924e19b88c14e03a6a7849069` is completed, but the script ledger identifies its clip as “When a mistake follows you,” not Hadrian. Monk Factory's two older completed IDs contain a different emotion script. The exact user-requested asset remains unidentified.
- Do not substitute `ebook-run.571924dc4e4867349fc6fd13`: its completed MP4 maps to hook “When a mistake follows you”, not Hadrian.
- For the exact candidate, require a matching English script/run ID, HeyGen completed video ID, local MP4 path and SHA-256, plus official publication-history lookup showing no prior post on the intended target.
- **Completion evidence:** the requested Hadrian script, video ID, MP4 hash, render-cost receipt, and target-specific no-duplicate evidence all point to one asset. If no such asset exists in the account/library, the missing input is the exact video ID or file; do not render a duplicate from an unknown script.

### Account verification and readiness

- Continue only the existing `instagram-english-monk` signup with the exact `monk_anicca` handle using Instagram's normal phone verification. The owner-side operation needed now is reconnecting the selected iPhone in System Settings so its SMS can be read through Messages.
- The current status is `phone_verification_pending`. The prior SMS reader hit macOS TCC on `~/Library/Messages/chat.db`, and iPhone Mirroring requested reconnecting the selected iPhone. The required owner-side action is to reconnect that iPhone in System Settings so its verification SMS can be read through the normal Messages app.
- Do not change privacy settings, bypass phone verification, create a disposable address, or reuse another product account. After normal verification, confirm whether the existing account is already ready/warmed; use the installed warmer only if the account is fresh or not yet warmed.
- If fresh, run one installed warmup session per day for seven days before commercial posting. Keep content prep, release prep, and Postiz binding moving during that period.
- **Completion evidence:** live exact handle and profile; account status updated in the mode-600 credential SSOT; existing readiness or, if this is a fresh account, a warmup record meeting the installed skill's seven-day window.

### Postiz integration

- Use the normal Postiz account connection after the exact profile is live.
- Read back `/public/v1/integrations`; require the matching Instagram profile, stable integration ID, and `disabled=false`; update the single account registry row and English eBook pack with that ID.
- Do not reuse English TikTok integration `cmo5rwq2p00twn10yrsdglng3` or historical Instagram integration IDs.
- **Completion evidence:** Postiz official GET and the registry point to the same English Monk profile and enabled integration.

### Owner release apply

- Build only a main-derived immutable release containing this owner. When `~/loops/current` points to that release, inspect target status and the apply lock, then run `LIFE_MANAGER_APPLY_TARGET=ebook-en-instagram-daily ~/loops/current/bin/lm-loop apply --loaded-idle-only`; verify the one-owner result, loaded SHA, and argv. Do not pass `--all`, delete open/protected paths, or stop/restart the active release reconciler.
- If the shared release reconciler moves `~/loops/current` first, read back its release SHA and use the same owner-targeted apply only after the apply lock is free.
- Free-space measurements are diagnostic; neither the old 512 MiB owner floor nor cleanup's 2 GiB recovery target is an apply prerequisite. Keep the account fail-closed until phone verification, warmup, and Postiz binding are complete.
- **Completion evidence:** installed release SHA/argv match `main`, the owner is registered and eligible, and owner/effect/apply-lock gates pass. Actual write errors remain attributable to the operation that failed.

### One-time publication

- First check whether the exact Hadrian asset has a canonical eBook render receipt. The current owner accepts only its matching `ebook-run.*` receipt for manual-slot reuse; it does not import an arbitrary old MP4.
- If the asset is outside canonical state, implement only the minimal owner-scoped import path in `apps/life-manager/scripts/ebook-distribute-daily.js`, reusing `createMarketingVideoPublicationLoopAdapter` and the existing publication receipt/identity checks. Add a focused contract to `apps/life-manager/scripts/ebook-distribute-daily.test.js`; verify with `node --test apps/life-manager/scripts/ebook-distribute-daily.test.js`. The imported record must bind the exact script, HeyGen ID, MP4 SHA, cost receipt, English Monk profile, caption, and one-off publication identity.
- The Hadrian one-off counts as one of this account's three posts for that Asia/Tokyo date. If it runs outside a scheduled slot, reserve/consume one slot in the durable owner ledger and make the scheduled runner skip that slot.
- Once the account is warmed and Postiz reads back the exact enabled Instagram profile, publish the exact asset immediately through this durable Postiz path. Do not wait for the next 08:00/14:00/21:00 slot and do not replay an uncertain effect.
- **Completion evidence:** Postiz `PUBLISHED`, matching integration/profile, provider receipt ID, native Reel URL, matching MP4 hash, and durable local receipt.

### Recurring cadence and revenue proof

- After the Hadrian one-off, apply/start only `ebook-en-instagram-daily` from a main-derived release. Verify the one-off plus remaining slots total exactly three unique `PUBLISHED` receipts and public URLs for English Monk Instagram on that day; subsequent natural 08:00, 14:00, and 21:00 JST occurrences each produce one fresh approved baseline clip.
- Verify each settled $10.99 eBook order against its delivered PDF, refunds, and payout/bank readback. Count one-time eBook net separately from Letter MRR.
- Connect optional $9.99/month Daily Anicca Letter enrollment and count only active paid subscriptions with official paid-invoice readback. Reconcile settled customer revenue minus refunds and measured costs, plus payout/bank readback.
- The $10K completion gate is portfolio-wide verified net MRR in the canonical CFO ledger. This lane contributes a measured amount; 1,002 Letter subscriptions are $10,009.98 gross MRR before fees/costs, not $10K net. Include the other portfolio lanes in the final $10K calculation.
- **Completion evidence:** three unique official post receipts per day for English Monk Instagram; separately reconciled paid orders/PDFs, active paid subscriptions, refunds, measured costs, payout/bank readback, and portfolio-wide net MRR. No current $10K revenue claim until official evidence supports it.

## Live order and cursor

See the [Life Manager unified SSOT](../specs/2026-09-25-life-manager-unified-ssot.md) for the current atomic TODO, status, and cursor.
