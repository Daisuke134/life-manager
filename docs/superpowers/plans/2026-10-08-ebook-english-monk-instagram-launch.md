# English Monk Instagram: immediate publish and recurring owner

**Goal:** Publish the already completed English Monk HeyGen video to its dedicated Instagram account immediately, then run three unique posts per day through the canonical Life Manager/Postiz owner.

**Scope:** English eBook distribution only. Capafy remains with its separate owner. Keep English TikTok and Japanese eBook owners separate. Do not render another video or buy a HeyGen plan for the existing asset.

**Current evidence:**

- HeyGen video `db2dab0924e19b88c14e03a6a7849069` is officially `completed`. Run receipt `ebook-run.571924dc4e4867349fc6fd13` points to a 1080×1920 H.264 MP4 with SHA-256 `132d9b326059f9b74d6020e4bca50f0a77d2f2f5ca0595d2f2feb56449c12183`.
- Postiz currently has 31 integrations and 9 Instagram routes. `monk_anicca` TikTok is enabled; no English Monk Instagram integration exists. Do not use TikTok or the iOS `@anicca.en` lane as a substitute.
- Instagram account signup is pending phone verification. Messages DB access fails with macOS TCC; the currently authenticated iPhone mirror needs a device reconnect. Existing Gmail addresses fail Instagram's “already used by another account” check. No CAPTCHA is shown.
- `ebook-en-tiktok-daily` is blocked below the 2 GiB admission floor (`df` last readback: 224,212 KiB free). The canonical shared-state cleanup pass reclaimed 6,411 bytes; three allowlisted caches are open and nine old releases contain protected `state/*.jsonl`. Old occurrence `18dc6de8dcf3a0e8-75262` remains claimed/effect-unknown on the separate existing English owner. Its Loop event lacks a receipt, while the HeyGen sidecar now has the completed video receipt. The release reconciler is loaded-running; do not stop or restart it.
- Last verified Stripe readback at 19:37 JST: The Anicca Reset is `$10.99` one-time; Daily Anicca Letter is `$9.99/month`; active paid subscriptions are 0. 1,002 paid active Letter subscribers are required for `$10K` gross MRR before fees/refunds. One-time eBook sales are not MRR.

## Ideal flow

```mermaid
flowchart LR
  A[Approved English baseline] --> B[Completed HeyGen MP4 + durable render receipt]
  B --> C[English Monk Instagram owner]
  C --> D[Postiz enabled Instagram integration]
  D --> E[PUBLISHED receipt + native Reel URL]
  E --> F[/go campaign token]
  F --> G[$10.99 one-time eBook checkout]
  G --> H[Paid order + matching PDF receipt]
  H --> I[Optional $9.99/month Letter]
  I --> J[Stripe invoice.paid + active subscription]
  J --> K[MRR ledger]
  C -. 08:00 / 14:00 / 21:00 JST .-> C
```

The one-time eBook is an acquisition purchase; only active paid Letter subscriptions count toward MRR.

## Atomic TODO

### 1. Complete the legitimate Instagram verification

- Continue the existing `instagram-english-monk` signup using its owner phone verification.
- Use the installed `ig-account-create` flow and official Instagram screen. Do not change macOS privacy settings, evade identity checks, create a disposable mailbox, or reuse a different product's account.
- **Completion evidence:** live profile with the selected English Monk handle; account credential status updated in `~/.local/share/anicca/credentials.json` with mode 600.
- **Current blocker detail:** `read_sms_otp.py` receives `Operation not permitted` opening `~/Library/Messages/chat.db`; iPhone Mirroring shows a reconnect prompt. Stop at that exact device/security gate if no already-authorized local read path works.

### 2. Connect that exact profile to Postiz

- Use the account's normal Postiz connection flow.
- Read back `/public/v1/integrations`; require the exact Instagram profile and `disabled=false`.
- **Completion evidence:** integration ID and profile match stored English account registry; Postiz GET confirms enabled.

### 3. Add an English Instagram publisher owner

**Files and contracts:**

- `apps/life-manager/scripts/ebook-distribute-daily.js`: add `ebook-en-instagram-daily` to `JOBS`, resolve the exact Instagram account/integration in `selectTarget`, and preserve the existing verified baseline-claim and pre-effect gates. Add strict `--slot-at <UTC ISO>` one-shot support: accept only an exact pack slot with a matching existing `rendered` receipt; reject malformed, future, or receipt-less overrides.
- `apps/life-manager/scripts/ebook-distribute-daily.js`: suffix the existing product/slot publication ID with the owner ID. Keep the campaign token shared per product/slot so cross-platform attribution remains a single campaign while provider intents/caption files stay owner-specific.
- Update the English eBook pack, one Instagram account registry file, `config/marketing-destinations.json`, `config/loop-registry.json`, and `apps/life-manager/config/product-loop-catalog.json` with the verified integration and 08:00/14:00/21:00 JST cadence.
- Add the smallest focused regression to `apps/life-manager/scripts/ebook-distribute-daily.test.js` and the existing Python eBook distribution-owner test. Assert route identity, setup fail-closed behavior, exact-slot validation and receipt reuse with zero HeyGen create calls, unique owner-scoped publication IDs, and exactly three daily slots.
- **Focused commands:** `node --test apps/life-manager/scripts/ebook-distribute-daily.test.js`; `python3 -m pytest skills/earn/marketing-engine/test_ebook_distribution_owner.py`; `./bin/lm-loop-contract`.
- **Completion evidence:** all focused checks pass; the exact new owner maps to one verified Postiz integration and no effect occurs while setup is incomplete.

### 4. Promote and apply the owner

- Commit and push the dedicated branch from current `origin/main`; pass required CI and review; merge using the repository's main process; build a main-derived immutable release.
- Recover disk headroom using the canonical disk-cleanup governor so host admission reaches at least 2 GiB. Preserve protected and open paths.
- Let the current release reconciler finish naturally. Apply only the English Instagram owner when its lock is free; read back installed SHA and argv.
- Keep old occurrence `18dc6de8dcf3a0e8-75262` fenced for the existing English TikTok owner until its exact receipt/no-effect proof resolves it. It does not authorize a TikTok retry and is not the new Instagram owner's provider identity.
- **Completion evidence:** current immutable release, Instagram owner loaded-idle with exact SHA/argv, and disk admission clear. If cleanup still reports only open/protected candidates, preserve them and report that exact admission blocker; do not delete protected state or close an unrelated application.

### 5. Publish the existing video now

- Use run `ebook-run.571924dc4e4867349fc6fd13` and its exact MP4/hash at recorded slot `2026-10-07T23:00:00.000Z` (08:00 JST). The owner accepts this exact pack slot through `--slot-at`; it reuses the existing `rendered` receipt and makes zero HeyGen create calls. Do not allow future, malformed, or receipt-less overrides.
- Publish through the canonical English Instagram owner and Postiz adapter. Keep one effect per owner occurrence.
- **Completion evidence:** official Postiz `PUBLISHED`, matching integration/profile, provider receipt ID, native Instagram Reel URL, matching MP4 hash, and local durable receipt. Recheck Postiz before any resend.

### 6. Prove the recurring cadence and MRR path

- Confirm the natural 08:00, 14:00, and 21:00 JST owner slots each yield one unique `PUBLISHED` receipt and public URL; a single post does not prove recurrence.
- Map the existing Daily Anicca Letter price into the marketing product/attribution registry and connect it to the eBook buyer journey with user-initiated enrollment.
- Verify paid eBook order ↔ PDF delivery separately from Stripe active paid Letter subscriptions. Count no trial, click, view, render, or one-time eBook order as MRR.
- **Completion evidence:** 3 unique official post receipts per day; separately verified paid order/PDF and active subscription receipts. `$10K MRR` requires 1,002 active `$9.99/month` subscribers gross before fees/refunds and remains a target.

## Current cursor

`legitimate Instagram verification → Postiz integration readback → English IG owner/source and exact-slot reuse → disk admission → immediate publication of the existing MP4 → 3/day receipts → reconcile the separate TikTok fence before any TikTok retry → paid PDF and Letter MRR funnel`.
