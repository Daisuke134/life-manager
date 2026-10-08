# English Monk eBook Instagram: verified launch and recurring owner

**Goal:** Publish the user's intended Hadrian video to the English Monk Instagram account, then run three unique posts per day through the canonical Life Manager/Postiz owner.

**Scope:** English eBook distribution only. Capafy remains with its separate owner. Keep English TikTok and Japanese eBook owners separate. Do not publish a different clip as the Hadrian video. Do not buy a HeyGen plan unless a later production-cost check shows it is needed.

**Current evidence (rechecked 2026-10-09 00:40 JST):**

- HeyGen official `video get db2dab0924e19b88c14e03a6a7849069` returns `completed` (13.4008 seconds). The matching local MP4 exists at `~/.local/state/life-manager/marketing/ebook/renders/ebook-run.571924dc4e4867349fc6fd13.mp4`, is 1080×1920 H.264, and has SHA-256 `132d9b326059f9b74d6020e4bca50f0a77d2f2f5ca0595d2f2feb56449c12183`.
- That MP4 is **not verified as the requested Hadrian clip**. Its script-ledger hook is “When a mistake follows you” and its body does not identify Hadrian. The four local eBook runs and their script records contain no Hadrian/Adrian item. HeyGen `video list --limit 100` currently returns zero rows. Do not publish this MP4 under the Hadrian request.
- Postiz official `GET /public/v1/integrations` returned HTTP 200, 31 integrations, and 9 Instagram integrations; none is the English Monk account. The dedicated account registry remains `setup_required` with `publisher_integration_id=null`.
- The credential SSOT entry for `instagram-english-monk` matches the intended `monk_anicca` handle but remains `phone_verification_pending`. The visible Instagram signup page is still at `/accounts/emailsignup/` and shows a phone prompt; no CAPTCHA is present. The latest `read_sms_otp.py` probe returns `sqlite3.OperationalError: unable to open database file`; metadata confirms `~/Library/Messages/chat.db` exists and is user-readable, while a previous probe returned macOS `Operation not permitted`. This points to protected Messages access, not a missing file. iPhone Mirroring still needs the selected device reconnected. Do not change privacy settings or bypass verification.
- PR #7173 is merged to `main` as `0f7cfb616dcb585a42868f2a5092c8cd9951675e`; the `ebook-en-instagram-daily` source owner is in main. Production has not caught up: `~/loops/current` still points to `20261009T000957-1fe7db3b`, and runtime health reports the Instagram loop as unknown. Its registry priority is `revenue`; current host `df` shows `1,579,312 KiB` free (about 1.51 GiB), above the 512 MiB floor.
- The separate English TikTok owner remains loaded on SHA `25bee172` and safely fenced on its old 2 GiB admission rule; do not use it as a substitute or change it in this Instagram task. The release reconciler runs on old SHA `e1b061f1`; latest status occurrence `18dc97c7aa1d0750-49084` is `entrypoint_exit_1`. The last recorded fleet apply on release `25bee172` was partial (73 changed, 90 skipped, 3 errors, budget exceeded). Latest main `9abbdb9d` contains the retry fix, but that code is not installed yet. Do not stop/restart the reconciler or launch a fleet-wide apply.
- Existing `lm-loop apply` already supports an owner-targeted path through `LIFE_MANAGER_APPLY_TARGET` and `--loaded-idle-only`; its source calls `apply_registry(..., target=...)`. The focused target contract passes 2/2. Once the main-derived release contains this owner and the exact target is ready, use only `LIFE_MANAGER_APPLY_TARGET=ebook-en-instagram-daily ~/loops/current/bin/lm-loop apply --loaded-idle-only`; never use `--all` for this work.
- Local focused acceptance passes Node 20/20, Python 4/4, runtime loop bounds 138/138, targeted apply contract 2/2, fleet retry contract 34/34, loop contract 18 loops/188 registry jobs, and `git diff --check`. PR #7173 merged with `--admin`; its source owner remains setup-required until the exact Instagram integration is live.
- Last verified Stripe readback (19:37 JST) showed `/monk` at `$10.99` one-time, Daily Anicca Letter at `$9.99/month`, and 0 active paid subscriptions. This is historical, not a current readback. At that price 1,002 active subscribers yield `$10,009.98` gross MRR before fees/refunds; one-time eBook orders do not count as MRR.
- The user authorized a HeyGen monthly plan if needed. It is not needed to post the already completed MP4, so no purchase was made. Reassess only after the exact asset, target account, and recurring video cost are known.

## Ideal flow

```mermaid
flowchart LR
  A[Approved English eBook script] --> B[Exact Hadrian video ID + MP4 receipt]
  B --> C[Verified English Monk Instagram account]
  C --> D[Account warmup complete]
  D --> E[Enabled matching Postiz integration]
  E --> F[English Instagram owner, 08:00 / 14:00 / 21:00 JST]
  H[Revenue owner admission at 512 MiB] --> F
  F --> G[PUBLISHED receipt + native Reel URL]
  G --> I[/monk: $10.99 one-time eBook]
  I --> J[Paid order + matching PDF receipt]
  J --> K[Optional $9.99/month Letter]
  K --> L[Stripe invoice.paid + active subscription]
  L --> M[MRR ledger: 1,002 active subscribers ≈ $10K gross]
```

The one-time eBook is an acquisition purchase; only active paid Letter subscriptions count toward MRR. Current status: the exact Hadrian clip and Instagram route are unresolved. Current free space clears the new revenue-owner floor; the installed release still needs to include that policy and the new owner.

## Atomic TODO

Order update: old order=`verify Instagram → connect Postiz → add owner → recover 2 GiB → fleet-wide apply → post the completed MP4 → 3/day → MRR`. New order=`source owner merge (complete) → identify and verify the exact Hadrian asset → complete account verification and warmup → connect Postiz → wait for a main-derived release → target-apply only ebook-en-instagram-daily with LIFE_MANAGER_APPLY_TARGET → publish once → prove 3/day → close paid-order/PDF and Letter attribution`. Reason: source is integrated; the completed English MP4 is a different script, the new owner needs only 512 MiB, and a targeted apply path exists. The exact video/account gates still prevent a safe post.

### 1. Source owner implementation — complete

- PR #7173 is merged to `main` as `0f7cfb616dcb585a42868f2a5092c8cd9951675e`. Owner code, fail-closed `setup_required` behavior, exact-render slot reuse, three daily slots, and owner-scoped publication identity are in main.
- Focused acceptance before merge: Node 20/20; Python distribution owner 4/4; runtime loop bounds 138/138; targeted apply contract 2/2; fleet retry contract 34/34; loop contract 18 loops/188 jobs; `git diff --check`. Fresh read-only source review found no merge blocker.
- **Completion evidence:** source is in main. Production remains uninstalled until the exact Instagram integration is live.

### 2. Identify the exact Hadrian video and prove it is unpublished

- Search HeyGen with `~/.local/bin/heygen video list --title Hadrian --limit 100` and `--title Adrian`; inspect the English eBook script ledger and run receipts under `~/.local/state/life-manager/marketing/ebook/`.
- Do not substitute `ebook-run.571924dc4e4867349fc6fd13`: its completed MP4 maps to hook “When a mistake follows you”, not Hadrian.
- For the exact candidate, require a matching English script/run ID, HeyGen completed video ID, local MP4 path and SHA-256, plus official publication-history lookup showing no prior post on the intended target.
- **Completion evidence:** the requested Hadrian script, video ID, MP4 hash, and target-specific no-duplicate evidence all point to one asset. If no such asset exists in the account/library, the missing input is the exact video ID or file; do not render a duplicate from an unknown script.

### 3. Complete account verification and required warmup

- Continue only the existing `instagram-english-monk` signup with the exact `monk_anicca` handle using Instagram's normal phone verification.
- The current status is `phone_verification_pending`. The prior SMS reader hit macOS TCC on `~/Library/Messages/chat.db`, and iPhone Mirroring requested reconnecting the selected iPhone. The required owner-side action is to reconnect that iPhone in System Settings so its verification SMS can be read through the normal Messages app.
- Do not change privacy settings, bypass phone verification, create a disposable address, or reuse another product account. After signup, finish the profile without a day-zero commercial link and complete the Instagram account warmup before commercial posting.
- **Completion evidence:** live exact handle and profile; account status updated in the mode-600 credential SSOT; warmup record meets the installed skill's window.

### 4. Connect that exact profile to Postiz

- Use the normal Postiz account connection after the exact profile is live.
- Read back `/public/v1/integrations`; require the matching Instagram profile, stable integration ID, and `disabled=false`; update the single account registry row and English eBook pack with that ID.
- **Completion evidence:** Postiz official GET and the registry point to the same English Monk profile and enabled integration.

### 5. Install the owner on the current revenue admission policy

- Build only a main-derived immutable release containing this owner and the `priority=revenue` 512 MiB floor. When `~/loops/current` points to that release, inspect target status and the apply lock, then run `LIFE_MANAGER_APPLY_TARGET=ebook-en-instagram-daily ~/loops/current/bin/lm-loop apply --loaded-idle-only`; verify the one-owner result, loaded SHA, and argv. Do not pass `--all`, delete open/protected paths, or stop/restart the active release reconciler.
- If the shared release reconciler moves `~/loops/current` first, read back its release SHA and use the same owner-targeted apply only after the apply lock is free.
- **Completion evidence:** installed release SHA/argv match `main`, the owner is registered and eligible, and host admission reports no deferral. The 2 GiB legacy English TikTok fence is separate.

### 6. Publish the exact Hadrian video once

- Use the canonical English Instagram owner and Postiz adapter. Reuse an exact completed render receipt; do not call HeyGen create for that asset.
- Require fresh target integration pre-readback, one owner occurrence, and duplicate protection. Do not replay an uncertain effect.
- **Completion evidence:** Postiz `PUBLISHED`, matching integration/profile, provider receipt ID, native Reel URL, matching MP4 hash, and durable local receipt.

### 7. Prove three posts per day, then close the revenue loop

- Verify the natural 08:00, 14:00, and 21:00 JST slots each produce one unique `PUBLISHED` receipt and public URL for English Monk Instagram.
- Verify each paid `$10.99` eBook order against its delivered PDF. Connect optional `$9.99/month` Daily Anicca Letter enrollment and count only active paid subscriptions from current Stripe readback.
- **Completion evidence:** three unique official post receipts per day; separately reconciled paid orders/PDFs and active paid subscriptions. `$10K` gross MRR is a target requiring 1,002 active `$9.99/month` subscribers, not a promised result.

## Current cursor

`identify the exact unpublished Hadrian clip (current completed English clip does not match) → finish owner phone verification and warmup → bind Postiz to that exact profile → wait for a main-derived release and apply only ebook-en-instagram-daily through LIFE_MANAGER_APPLY_TARGET → publish once with receipt → verify three natural posts/day → reconcile paid eBook/PDF and optional Letter MRR`. The English TikTok fence remains separate; do not retry it as part of Instagram work.
