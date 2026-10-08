# English Monk eBook Instagram: verified launch and recurring owner

**Goal:** Publish the user's intended Hadrian video to the English Monk Instagram account, then run three unique posts per day through the canonical Life Manager/Postiz owner.

**Scope:** English eBook distribution only. Capafy remains with its separate owner. Keep English TikTok and Japanese eBook owners separate. Do not publish a different clip as the Hadrian video. Do not buy a HeyGen plan unless a later production-cost check shows it is needed.

**Current evidence (rechecked 2026-10-09 02:10 JST):**
- The installed `config/marketing-destinations.json` has no active `ebook-en-instagram` target. Its only `@monk_anicca` entry is in `holds` with reason `english_monk_instagram_not_connected` and `target_daily_limit=0`; `selectTarget` therefore returns `setup_required`. That zero is a fail-closed hold, not the desired cadence.

- `~/loops/current` points to `20261009T014034-aba80c99`, which contains the source owner. Fresh health readback is `telemetry_gap` / runtime `degraded`, with no run, occurrence, receipt, or owner-specific LaunchAgent plist. `df -k /` reports `488,420 KiB` free (about 477 MiB), `35,868 KiB` below the 512 MiB revenue floor. Do not apply this owner yet or run a fleet-wide apply.
- HeyGen CLI title queries for `Hadrian` and `Adrian` both return zero videos; a filename search of the eBook/Monk Factory trees also returns no Hadrian asset. The two older completed Monk Factory HeyGen IDs (`f4ce3e44217e4844b988e501414cf199` and `2f6c427ce4bc460eb07d17bd7da67d2f`) were locally transcribed earlier and contain the same 90-second emotion script, not Hadrian. Neither is safe to label as the requested video. The HeyGen app connection currently requires reauthentication, while the local CLI read works.
- The known Life Manager MP4 `ebook-run.571924dc4e4867349fc6fd13.mp4` is also different: its script-ledger hook is “When a mistake follows you.” Do not substitute either video.
- Monk Factory's old morning log reports a Postiz post to integration `cmo5rwq2p00twn10yrsdglng3`. The product/account registry maps that ID to English TikTok, not Instagram. The last official Postiz GET (00:37 JST) returned 31 integrations / 9 Instagram integrations and no English Monk match. A new GET is unavailable: `postiz auth:status` reports unauthenticated and integration/post list calls fail before contacting Postiz. The current account registry still has `publisher_integration_id=null` and `status=setup_required`; this session has no official PUBLISHED receipt for the requested video.
- The credential SSOT entry for `instagram-english-monk` remains `phone_verification_pending`. Instagram's signup page showed its normal phone prompt and no CAPTCHA. Reading the SMS through `~/Library/Messages/chat.db` is blocked by macOS privacy access; iPhone Mirroring requested reconnecting the selected device. Do not change privacy settings or bypass verification.
- The English Instagram owner renders an approved baseline by product and slot, then publishes through Postiz. English TikTok and Instagram share the same English render receipt for matching slots, so the budget target is 90 shared English renders/month at three slots/day. Its manual-slot path accepts only a matching canonical receipt; an arbitrary old Monk Factory MP4 needs an owner-scoped import and durable publication receipt. A loaded owner started outside a due slot returns `no_due_slot`.
- The registry defines four distinct eBook social owners, each with three daily slots: English TikTok and English Instagram at 08:00/14:00/21:00 JST; Japanese TikTok and Japanese Instagram at 07:00/12:30/20:00 JST. That is 12 scheduled posts/day across four accounts, not proof of 12 successful posts. This task owns only the English Instagram lane's three posts/day; the other owners remain separate.
- The last Stripe readback (19:37 JST) was 0 active paid Letter subscriptions and is historical; current live subscription count remains unknown. `/monk` is a $10.99 one-time eBook purchase; Daily Anicca Letter is $9.99/month. The canonical $10K goal is monthly bank net after fees and costs, so 1,002 active subscriptions (= $10,009.98 gross MRR) is only a pre-fee reference, not the goal.
- HeyGen CLI reports `billing_type=wallet`, `$11.78` remaining, and auto-reload enabled (`$10` refill below `$5`). A prior eBook render receipt measured `$0.52` per video; at 90 shared English renders/month that sample implies `$46.80` wallet usage. The official pricing page currently lists Creator at `$29/month` with 600 credits and Pro at `$49/month` with 1,000 credits, but the local API reports wallet billing and neither credits-per-render nor subscription coverage of this API wallet is confirmed. Do not buy a plan based on the comparison yet; the user has authorized purchase if a plan is shown to cover the required API usage.
- PR #7173 is merged. PR #7194 is still open at head `dde8182a1f97e3e8bd95e2299b954fdf2d31cc17`, based on `ba39c13a`; all checks on that old head pass, but `origin/main` advanced to `9449e1c7` and GitHub reports the PR merge state `DIRTY`. Rebase/sync this docs branch to latest `main`, then rerun exact-head review and CI.

## Ideal flow

```mermaid
flowchart LR
  A[Approved English baseline script] --> B[HeyGen Avatar IV render + SHA/cost receipt]
  B --> C[Verified and warmed English Monk Instagram]
  C --> D[Enabled matching Postiz integration]
  E[Revenue admission: 512 MiB floor] --> F[Owner: 08:00 / 14:00 / 21:00 JST]
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

## Atomic TODO

Order update: old order=`merge owner → wait for scheduled slot → publish a completed MP4 → call 1,002 gross subscribers $10K MRR`. New order=`(parallel) obtain the exact Hadrian ID/file + reconnect the selected iPhone → complete normal phone verification and warm the account → connect the exact Instagram profile to Postiz and read back enabled integration → update the account/pack and replace only the verified @monk_anicca zero-limit hold with the active three-slot target → confirm API render entitlement/cost and restore disk above 512 MiB → sync the docs branch to latest main and merge → cut a main-derived release and apply only ebook-en-instagram-daily → publish Hadrian once, consuming one of that day's three slots → verify this lane's three daily receipts → reconcile portfolio net revenue, payouts, and bank readback`. Reason: exact Hadrian is not identified, account verification is pending, Postiz has no current local authentication/readback, the active destination and owner plist are absent, and disk is below admission. The user approved a monthly HeyGen plan only if its API entitlement covers the required renders; no purchase is justified before that proof. This $10K goal is net, not gross. No Capafy work is in this order.

### 1. Source owner implementation — complete

- PR #7173 is merged to `main` as `0f7cfb616dcb585a42868f2a5092c8cd9951675e`. Owner code, fail-closed `setup_required` behavior, exact-render slot reuse, three daily slots, and owner-scoped publication identity are in main.
- Focused acceptance before merge: Node 20/20; Python distribution owner 4/4; runtime loop bounds 138/138; targeted apply contract 2/2; fleet retry contract 34/34; loop contract 18 loops/188 jobs; `git diff --check`. Fresh read-only source review found no merge blocker.
- **Completion evidence:** source is in main. Production has not adopted the merged owner yet; the exact Instagram integration is a separate eligibility gate before publishing.

### 2. Identify the exact Hadrian video and prove it is unpublished

- HeyGen title searches for `Hadrian` and `Adrian` returned no matches. Monk Factory's two completed IDs have no script mapping; its historical `en-02` clip is an emotion script. The exact user-requested asset remains unidentified.
- Do not substitute `ebook-run.571924dc4e4867349fc6fd13`: its completed MP4 maps to hook “When a mistake follows you”, not Hadrian.
- For the exact candidate, require a matching English script/run ID, HeyGen completed video ID, local MP4 path and SHA-256, plus official publication-history lookup showing no prior post on the intended target.
- **Completion evidence:** the requested Hadrian script, video ID, MP4 hash, render-cost receipt, and target-specific no-duplicate evidence all point to one asset. If no such asset exists in the account/library, the missing input is the exact video ID or file; do not render a duplicate from an unknown script.

### 3. Complete account verification and required warmup

- Continue only the existing `instagram-english-monk` signup with the exact `monk_anicca` handle using Instagram's normal phone verification. The owner-side operation needed now is reconnecting the selected iPhone in System Settings so its SMS can be read through Messages.
- The current status is `phone_verification_pending`. The prior SMS reader hit macOS TCC on `~/Library/Messages/chat.db`, and iPhone Mirroring requested reconnecting the selected iPhone. The required owner-side action is to reconnect that iPhone in System Settings so its verification SMS can be read through the normal Messages app.
- Do not change privacy settings, bypass phone verification, create a disposable address, or reuse another product account. After signup, finish the profile without a day-zero commercial link and complete the Instagram account warmup before commercial posting.
- Begin the installed account warmup immediately after normal verification. Keep content prep, release prep, and the Postiz binding moving during warmup.
- **Completion evidence:** live exact handle and profile; account status updated in the mode-600 credential SSOT; warmup record meets the installed skill's seven-day window.

### 4. Connect that exact profile to Postiz

- Use the normal Postiz account connection after the exact profile is live.
- Read back `/public/v1/integrations`; require the matching Instagram profile, stable integration ID, and `disabled=false`.
- After normal account verification and warmup, make one source/config update: set `publisher_integration_id` in `registry/accounts/instagram.monk_anicca.json`, set the matching pack account integration in `registry/ebook-packs/ebook-en-anicca-monk.json`, remove only the `@monk_anicca` not-connected hold, and add the active `ebook-en-instagram` target to `config/marketing-destinations.json` with the same integration and 08:00/14:00/21:00 JST cadence. Keep `target_daily_limit=0` while the account is held; it is a fail-closed hold marker, not the active schedule.
- Add/adjust the focused selection contract in `apps/life-manager/scripts/ebook-distribute-daily.test.js`: the held account is effect-free; the exact enabled active target matches account, pack, and owner schedule; the resulting cadence remains three slots/day. Verify with `node --test apps/life-manager/scripts/ebook-distribute-daily.test.js`.
- Do not reuse English TikTok integration `cmo5rwq2p00twn10yrsdglng3` or historical Instagram integration IDs.
- **Completion evidence:** Postiz official GET and the registry point to the same English Monk profile and enabled integration.

### 5. Install the owner on the current revenue admission policy

- Build only a main-derived immutable release containing this owner and the `priority=revenue` 512 MiB floor. When `~/loops/current` points to that release, inspect target status and the apply lock, then run `LIFE_MANAGER_APPLY_TARGET=ebook-en-instagram-daily ~/loops/current/bin/lm-loop apply --loaded-idle-only`; verify the one-owner result, loaded SHA, and argv. Do not pass `--all`, delete open/protected paths, or stop/restart the active release reconciler.
- If the shared release reconciler moves `~/loops/current` first, read back its release SHA and use the same owner-targeted apply only after the apply lock is free.
- At 02:06 JST, disk was `488,420 KiB` (about 477 MiB), `35,868 KiB` below the 512 MiB owner floor. Keep the target fail-closed and defer apply until a fresh read meets admission; do not change protected paths or invoke fleet-wide apply.
- Before enabling three daily posts, measure the actual HeyGen API cost/credit charge for the shared English render and verify whether the `$29/month, 600-credit Creator plan` applies to this API wallet. The current API account is wallet-billed with auto-reload enabled; do not buy a plan or treat `$11.78` as a full-month budget until the entitlement and 90-render coverage are proven.
- **Completion evidence:** installed release SHA/argv match `main`, the owner is registered and eligible, and host admission reports no deferral. The 2 GiB legacy English TikTok fence is separate.

### 6. Publish the exact Hadrian video once

- First check whether the exact Hadrian asset has a canonical eBook render receipt. The current owner accepts only its matching `ebook-run.*` receipt for manual-slot reuse; it does not import an arbitrary old MP4.
- If the asset is outside canonical state, implement only the minimal owner-scoped import path in `apps/life-manager/scripts/ebook-distribute-daily.js`, reusing `createMarketingVideoPublicationLoopAdapter` and the existing publication receipt/identity checks. Add a focused contract to `apps/life-manager/scripts/ebook-distribute-daily.test.js`; verify with `node --test apps/life-manager/scripts/ebook-distribute-daily.test.js`. The imported record must bind the exact script, HeyGen ID, MP4 SHA, cost receipt, English Monk profile, caption, and one-off publication identity.
- The immediate Hadrian post counts as one of this account's three posts for that Asia/Tokyo date. If it runs outside a scheduled slot, reserve/consume one slot in the durable owner ledger and make the scheduled runner skip that slot. Add a contract that proves replay is zero and no day exceeds three official posts for this target.
- Once the account is warmed and Postiz reads back the exact enabled Instagram profile, publish the exact asset immediately through this durable Postiz path. Do not wait for the next 08:00/14:00/21:00 slot and do not replay an uncertain effect.
- **Completion evidence:** Postiz `PUBLISHED`, matching integration/profile, provider receipt ID, native Reel URL, matching MP4 hash, and durable local receipt.

### 7. Prove three posts per day, then close the revenue loop

- After the Hadrian one-off, apply/start only `ebook-en-instagram-daily` from a main-derived release. Verify the one-off plus any remaining slots total exactly three unique `PUBLISHED` receipts and public URLs for English Monk Instagram on that day; subsequent natural 08:00, 14:00, and 21:00 JST occurrences each produce one fresh approved baseline clip.
- Verify each settled $10.99 eBook order against its delivered PDF, refunds, and payout/bank readback. Count one-time eBook net separately from Letter MRR.
- Connect optional $9.99/month Daily Anicca Letter enrollment and count only active paid subscriptions with official paid-invoice readback. Reconcile settled customer revenue minus refunds and measured costs, including HeyGen render receipts, plus payout/bank readback.
- The $10K completion gate is portfolio-wide verified net MRR in the canonical CFO ledger. This lane contributes a measured amount; 1,002 Letter subscriptions are $10,009.98 gross MRR before fees/costs, not $10K net. Include the other portfolio lanes in the final $10K calculation.
- **Completion evidence:** three unique official post receipts per day for English Monk Instagram; separately reconciled paid orders/PDFs, active paid subscriptions, refunds, measured costs, payout/bank readback, and portfolio-wide net MRR. No current $10K revenue claim until official evidence supports it.

## Current cursor

parallel: receive exact Hadrian ID/file and reconnect the selected iPhone → complete phone verification and seven-day warmup → authenticate the Postiz readback route and connect the exact Instagram profile → replace only the verified account's zero-limit hold with an active three-slot target → verify HeyGen API credits/cost cover 90 shared English renders/month and obtain fresh disk admission ≥512 MiB → sync PR #7194 to latest main and merge → cut a main-derived release and apply only ebook-en-instagram-daily → publish Hadrian while consuming one of that day's three posts → verify this lane's 3/day (four configured eBook lanes target 12 scheduled/day total) → reconcile settled revenue, refunds, costs, payout/bank, and portfolio net MRR. Current blockers: exact asset, phone verification, Postiz auth/binding, disk admission, and HeyGen API entitlement. English TikTok and both Japanese owners remain separate.
