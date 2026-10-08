# English Monk eBook Instagram: verified launch and recurring owner

**Goal:** Publish the user's intended Hadrian video to the English Monk Instagram account, then run three unique posts per day through the canonical Life Manager/Postiz owner.

**Scope:** English eBook distribution only. Capafy remains with its separate owner. Keep English TikTok and Japanese eBook owners separate. Do not publish a different clip as the Hadrian video. Do not buy a HeyGen plan unless a later production-cost check shows it is needed.

**Current evidence (rechecked 2026-10-09 01:26 JST):**

- HeyGen title searches for `Hadrian` and `Adrian` return no matches. Monk Factory contains two completed HeyGen IDs (`f4ce3e44217e4844b988e501414cf199` and `2f6c427ce4bc460eb07d17bd7da67d2f`). I downloaded and transcribed both locally; both contain the same 90-second emotion script, not Hadrian. Neither is safe to label as the requested video.
- The known Life Manager MP4 `ebook-run.571924dc4e4867349fc6fd13.mp4` is also different: its script-ledger hook is “When a mistake follows you.” Do not substitute either video.
- Monk Factory's old morning log reports a Postiz post to integration `cmo5rwq2p00twn10yrsdglng3`. The current product/account registry maps that ID to English TikTok, not Instagram. Its old Instagram ID is historical and is not the current `instagram.monk_anicca` profile. The last official Postiz GET (00:37 JST) returned 31 integrations / 9 Instagram integrations and no English Monk match; the current account registry has `publisher_integration_id=null` and `status=setup_required`.
- The credential SSOT entry for `instagram-english-monk` remains `phone_verification_pending`. Instagram's signup page showed its normal phone prompt and no CAPTCHA. Reading the SMS through `~/Library/Messages/chat.db` is blocked by macOS privacy access; iPhone Mirroring requested reconnecting the selected device. Do not change privacy settings or bypass verification.
- PR #7173 is merged to `main` as `0f7cfb616dcb585a42868f2a5092c8cd9951675e`. The source owner is in main, but `~/loops/current` still points to `20261009T000957-1fe7db3b`; `lm-loop health --loop ebook-en-instagram-daily` returns `unknown health loop`. At 00:57 JST, `df -k /` reports `1,340,980 KiB` free (about 1.28 GiB), above the owner's 512 MiB floor. Do not run a fleet-wide apply or stop/restart the shared reconciler.
- The English Instagram owner generates a fresh approved baseline script and HeyGen render for each scheduled slot before posting through Postiz. Its manual-slot path only accepts a matching canonical render receipt; it cannot publish an arbitrary old Monk Factory MP4. A loaded owner can be kickstarted with `lm-loop start`, but outside a due slot the normal entrypoint returns `no_due_slot`. The Hadrian one-off needs its exact asset and a supported durable Postiz receipt path.
- The registry defines four distinct eBook social owners, each with three daily slots: English TikTok and English Instagram at 08:00/14:00/21:00 JST; Japanese TikTok and Japanese Instagram at 07:00/12:30/20:00 JST. That is 12 scheduled posts/day across four accounts, not proof of 12 successful posts. This task owns only the English Instagram lane's three posts/day; the other owners remain separate.
- The last Stripe readback (19:37 JST) was 0 active paid Letter subscriptions and is historical; current live subscription count remains unknown. `/monk` is a $10.99 one-time eBook purchase; Daily Anicca Letter is $9.99/month. The canonical $10K goal is monthly bank net after fees and costs, so 1,002 active subscriptions (= $10,009.98 gross MRR) is only a pre-fee reference, not the goal. No HeyGen plan was purchased; the user authorized one if the actual rendering budget requires it.

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

Order update: old order=`merge owner → wait for scheduled slot → publish a completed MP4 → call 1,002 gross subscribers $10K MRR`. New order=`(parallel) identify exact Hadrian asset and finish normal phone verification → begin account warmup and connect the exact profile to Postiz → add a supported one-off Postiz receipt path only if the Hadrian asset is outside canonical render state → build a main-derived release and apply only ebook-en-instagram-daily → publish the Hadrian clip immediately once eligible → prove this English Instagram lane's three daily receipts → reconcile eBook orders/PDFs, Letter net contribution, payouts, and portfolio MRR`. Reason: the old factory evidence is TikTok-only, the Instagram identity is not verified or connected, and the canonical loop cannot accept an arbitrary old MP4. The four configured eBook owners schedule 12 posts/day in total; current live receipts are not established. User's $10K target is portfolio net, not gross. No Capafy work is in this order.

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
- Read back `/public/v1/integrations`; require the matching Instagram profile, stable integration ID, and `disabled=false`; update the single account registry row and English eBook pack with that ID.
- Do not reuse English TikTok integration `cmo5rwq2p00twn10yrsdglng3` or historical Instagram integration IDs.
- **Completion evidence:** Postiz official GET and the registry point to the same English Monk profile and enabled integration.

### 5. Install the owner on the current revenue admission policy

- Build only a main-derived immutable release containing this owner and the `priority=revenue` 512 MiB floor. When `~/loops/current` points to that release, inspect target status and the apply lock, then run `LIFE_MANAGER_APPLY_TARGET=ebook-en-instagram-daily ~/loops/current/bin/lm-loop apply --loaded-idle-only`; verify the one-owner result, loaded SHA, and argv. Do not pass `--all`, delete open/protected paths, or stop/restart the active release reconciler.
- If the shared release reconciler moves `~/loops/current` first, read back its release SHA and use the same owner-targeted apply only after the apply lock is free.
- The current disk read is above the 512 MiB owner floor, so 2 GiB cleanup is not an eBook prerequisite. Keep the account fail-closed until phone verification, warmup, and Postiz binding are complete.
- **Completion evidence:** installed release SHA/argv match `main`, the owner is registered and eligible, and host admission reports no deferral. The 2 GiB legacy English TikTok fence is separate.

### 6. Publish the exact Hadrian video once

- First check whether the exact Hadrian asset has a canonical eBook render receipt. The current owner accepts only its matching `ebook-run.*` receipt for manual-slot reuse; it does not import an arbitrary old MP4.
- If the asset is outside canonical state, implement only the minimal owner-scoped import path in `apps/life-manager/scripts/ebook-distribute-daily.js`, reusing `createMarketingVideoPublicationLoopAdapter` and the existing publication receipt/identity checks. Add a focused contract to `apps/life-manager/scripts/ebook-distribute-daily.test.js`; verify with `node --test apps/life-manager/scripts/ebook-distribute-daily.test.js`. The imported record must bind the exact script, HeyGen ID, MP4 SHA, cost receipt, English Monk profile, caption, and one-off publication identity.
- Once the account is warmed and Postiz reads back the exact enabled Instagram profile, publish the exact asset immediately through this durable Postiz path. Do not wait for the next 08:00/14:00/21:00 slot and do not replay an uncertain effect.
- **Completion evidence:** Postiz `PUBLISHED`, matching integration/profile, provider receipt ID, native Reel URL, matching MP4 hash, and durable local receipt.

### 7. Prove three posts per day, then close the revenue loop

- After the Hadrian one-off, apply/start only `ebook-en-instagram-daily` from a main-derived release. Verify the natural 08:00, 14:00, and 21:00 JST slots each produce one unique `PUBLISHED` receipt and public URL for English Monk Instagram; each slot renders a fresh approved baseline clip.
- Verify each settled $10.99 eBook order against its delivered PDF, refunds, and payout/bank readback. Count one-time eBook net separately from Letter MRR.
- Connect optional $9.99/month Daily Anicca Letter enrollment and count only active paid subscriptions with official paid-invoice readback. Reconcile settled customer revenue minus refunds and measured costs, plus payout/bank readback.
- The $10K completion gate is portfolio-wide verified net MRR in the canonical CFO ledger. This lane contributes a measured amount; 1,002 Letter subscriptions are $10,009.98 gross MRR before fees/costs, not $10K net. Include the other portfolio lanes in the final $10K calculation.
- **Completion evidence:** three unique official post receipts per day for English Monk Instagram; separately reconciled paid orders/PDFs, active paid subscriptions, refunds, measured costs, payout/bank readback, and portfolio-wide net MRR. No current $10K revenue claim until official evidence supports it.

## Current cursor

parallel: receive exact Hadrian video ID/file and reconnect the selected iPhone → complete phone verification, start seven-day warmup, and bind the exact Instagram profile in Postiz → add the one-off import receipt path only if the video is outside canonical render state → build a main-derived release and apply only ebook-en-instagram-daily with LIFE_MANAGER_APPLY_TARGET → publish Hadrian immediately with one official Postiz receipt → verify this lane's 3/day receipts (the four configured eBook lanes target 12/day total) → reconcile eBook/PDF and Letter net contribution, payouts, and portfolio-wide net MRR. Current blockers: exact Hadrian asset, phone verification, Postiz profile binding, and production release adoption. English TikTok and both Japanese owners remain separate.
