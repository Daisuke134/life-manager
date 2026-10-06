# Anicca eBook Revenue Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. TODO order and current cursor live only in the Life Manager unified SSOT.

**Goal:** 既存の英日eBook checkout・PDF納品と任意のLetter/Tegami paid subscriptionを同じcampaignに結び、最初の自然なpaid orderとmatching PDF receiptの後にCapafy Instagram marketingへ引き継ぐ。

**Architecture:** Checkout・durable buyer receipt・PDF delivery・subscription stateは既存のanicca-productsに置く。Life ManagerのMarketing Engineが既存account registryとpublication adapterからeBookを配信し、同じtokenでclick・Stripe・buyer receiptを結ぶ。初回receipt後はCapafy開発を変更せず、既存D5の単一Instagram ownerへ移る。

**Tech Stack:** Next.js、Netlify Functions、Stripe、Resend、Supabase、Python Marketing Engine、Life Manager loop registry、既存Postiz/publication adapter。

**Spec:** docs/superpowers/specs/2026-10-05-ebook-revenue-loop-design.md

## Global Constraints

- Life Manager unified SSOTだけが実行順とcurrent cursorを持つ。
- eBook one-time sales、Letter/Tegami paid MRR、Capafy banked net contributionは別metric。
- main pushでanicca-products production deployが始まる。DB migration/schema-cache readiness前にPR #420をmergeしない。
- 既存の本人所有accountとofficial provider statusが合うものだけ使う。account creation・automated engagement・anti-detection・proxy/fingerprint workaroundでrestrictionを避けない。
- effect_unknownの投稿は同一occurrenceのofficial readbackが終わるまで再送しない。1 accountにpublisher ownerは一つだけ。
- Resendはverified RESEND_FROM_EMAILを使う。email purchase/subscriptionは明示Checkout以外から作らない。
- 外部public postは依頼済みmarketing workstreamの範囲・approved creative・owner route内でのみ実行する。
- Capafy product/listing/account-lifecycleのsourceは別担当。D5 marketingだけを扱う。
- source evidence・production natural run・provider readbackは別のproofとして記録する。

## Review Focus

- 古いCheckout webhookが新しいsubscription stateやpointerを戻さず、superseded receiptをretry可能に保つ。
- unique email constraintがないschemaでも同一RPC内の同じemail予約を1 rowに収束させる。
- 別writerのlead-magnet POSTが同じsubscriber identityを重複作成しない。
- PDF/Day-0 emailで未verified senderを使わず、provider outcome unknown時に成功や再送を推測しない。
- Capafy旧・新laneのeffect_unknownをofficial readbackなしに再生せず、二重publishしない。
- EN/JA packのaccount・locale・claimとprovider identityを一致させる。

## Design ruling

- **Reason:** A separate scheduled render owner duplicates lifecycle state and can race with the two platform publishers. The eBook receipt is already keyed by product and exact slot, so the smallest ownership model is one publisher job per account, both reading the same locked receipt.
- **Old Task 5 design:** `ebook-ja-generate-daily` plus TikTok and Instagram publisher jobs.
- **New Task 5 design:** three account owners share locale-scoped product/slot renders: English HeyGen Avatar IV to the existing TikTok integration, and Japanese Watercolor Mark Factory to existing TikTok and Instagram integrations. Each owner performs at most one Postiz effect per occurrence; each locale has three scheduled slots per day.
- **Execution cursor and current host state:** → `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`.

---

### Task 1: Checkout attribution and offer contract — DONE

**Files**
- anicca-products/apps/landing/app/monk/page.tsx
- anicca-products/apps/landing/app/achan/page.tsx
- anicca-products/apps/landing/app/letter/page.tsx
- anicca-products/apps/landing/app/tegami/page.tsx
- anicca-products/apps/landing/lib/checkout-attribution.js
- anicca-products/apps/landing/netlify/functions/checkout.js
- anicca-products/apps/landing/netlify/functions/_lib/__tests__/ebook-checkout.test.js

**Interfaces**
- Request: lang, product, mode, optional attribution_token copied from utm_campaign.
- Stripe Checkout and Subscription metadata: lang, product, attribution_token.
- eBook uses one-time payment; Letter/Tegami use subscription mode with a 14-day trial.

- [x] Add failing contract tests for locale price, checkout mode, and token propagation; RED observed before implementation.
- [x] Implement EN/JA offer routing and campaign metadata. Preserve verified 49 short chapter claim; remove unsupported chapter-length claims.
- [x] Run focused tests and telemetry/build. Product PR #419 merged to main as 6c52d4cc13.

### Task 2: Replay-safe purchase receipt, PDF delivery, and subscription state — SOURCE READY / DDL ADMIN PATH REQUIRED

**Files**
- Modify: anicca-products/apps/landing/netlify/functions/webhook.js
- Create: anicca-products/apps/landing/netlify/functions/_migrations/2026-10-05-ebook-webhook-receipts.sql
- Test: anicca-products/apps/landing/netlify/functions/_lib/__tests__/ebook-webhook.test.js
- Test: anicca-products/apps/landing/netlify/functions/_lib/__tests__/writer-webhook.test.js

**Interfaces**
- Reserve/apply RPCs: reserve_ebook_subscription_readback(subscription_id,email?,customer_id?) returns subscriber_id + DB-issued generation; apply_ebook_subscription_state(...) changes state only for current generation.
- Stripe buyer session receipt and Resend provider message ID join by session_id and attribution_token.
- Required env: RESEND_FROM_EMAIL. Missing sender configuration causes retryable receipt before any Resend call.
- Existing subscriber mappings and legacy-paid state are preserved; access aggregates across subscription states. The compatibility pointer follows max Stripe Subscription.created, with stable ID tie-break.

- [x] Implement signed durable webhook receipts, PDF delivery fence, DB-issued subscription generation, legacy mapping preservation, stale-readback rejection, and paid-MRR separation.
- [x] Route both Stripe reservation and lead-magnet signup through one normalized-email advisory-lock RPC; prefer existing Stripe mapping and preserve `signed_up_at` on signup replay.
- [x] Run focused eBook/Writer/lead-magnet tests 31/31, writer-entitlement tests 6/6, and PostgreSQL 18.6 fixture; verify concurrent email writers leave one subscriber row without email UNIQUE and preserve legacy mapping.
- [x] Fix non-canonical base64url signature aliases in the existing entitlement verifier; the new targeted regression was RED before the guard and the complete focused file passes 6/6.
- [x] Extend the existing manual-only metadata workflow to report ebook schema/RPC visibility, PostgREST unique-index access, and normalized subscriber duplicate counts without logging addresses.
- [x] Push source-ready changes to PR #420 head `85116e29aceb3d951e65f125fb3473fcb17d2b99`; exact-head Landing check `37356856068` is SUCCESS.
- [x] Read production metadata in manual workflow run `37353322073`: buyers/subscribers column shapes match migration assumptions; 9 subscriber rows, 0 normalized-email duplicate groups, 0 empty emails. `ebook_webhook_receipts` and `ebook_subscription_states` are not exposed; ebook RPCs are absent from OpenAPI; `pg_indexes` returns 404/PGRST205. The email unique index remains unknown, but current subscriber writers use the shared advisory-lock RPC and migration logic does not require a new email index.
- [ ] Obtain a direct Supabase DDL-capable admin path and apply the migration. Local CLI has no project link; production env has no `DATABASE_URL`/`SUPABASE_DB_URL`; Supabase management token/admin credential is absent from configured env, GitHub secrets, and credential SSOT.
- [ ] Read back `ebook_webhook_receipts`, `ebook_subscription_states`, RPC signatures/ACLs, required columns, and PostgREST schema cache after migration.
- [ ] Reconfirm sender readiness, merge PR #420 only after migration readback, then verify deployed SHA and health. Main push triggers production deploy.

**Current production blocker:** the production REST service-role key permits schema/data readback, but no direct DDL route is available. Do not merge or claim production readiness before migration application and post-migration table/RPC/schema-cache readback.

### Task 3: Make lead-magnet signup compatible with the verified production sender — SOURCE DONE IN PR #420

**Files**
- Modify: anicca-products/apps/landing/netlify/functions/lead-magnet.js
- Modify: anicca-products/apps/landing/netlify/functions/_migrations/2026-10-05-ebook-webhook-receipts.sql or a follow-up migration only if Task 2 schema readback requires it
- Test: anicca-products/apps/landing/netlify/functions/_lib/__tests__/lead-magnet.test.js

**Interfaces**
- Input: normalized email and lang en/jp.
- Subscriber write: use the unique email constraint if confirmed; otherwise use one DB RPC that applies the same normalized-email advisory lock as the Checkout webhook.
- Day-0 sender: RESEND_FROM_EMAIL, never onboarding@resend.dev. Return success only after the subscriber write and provider send succeed; never echo provider response bodies to the caller.

- [x] Add focused tests for missing sender, subscriber write failure, provider failure, and normalized-email replay; observe RED before implementation.
- [x] Use the same normalized-email RPC as Stripe reservation; send only after confirmed DB write and use `RESEND_FROM_EMAIL`, never `onboarding@resend.dev`.
- [x] Run the focused tests as part of PR #420: lead-magnet plus eBook/Writer total 31/31 PASS.
- [ ] After Task 2 deploys, verify the production function uses the configured verified sender. Free signup remains separate from paid MRR.

### Task 4: Join the creative token to the natural purchase receipt — SOURCE CONTRACT DONE

**Files**
- Modify: life-manager/skills/earn/marketing-engine/ebook_runner.py only if a contract fails
- Existing: life-manager/skills/earn/marketing-engine/measure/attribution.py
- Existing: anicca-products/apps/landing/netlify/functions/marketing-go.js
- Existing: anicca-products/apps/landing/lib/checkout-attribution.js
- Test: focused Marketing Engine attribution contract and anicca-products checkout/webhook contract

**Interfaces**
- Product token prefixes: ebook-en → ee_, ebook-ja → ej_, followed by the existing 20-character lowercase base32 token.
- Existing flow: render/creative receipt → owned /go/<token> → marketing_click_receipts → utm_campaign → Stripe metadata → buyer/subscriber receipt.
- Keep creative_id distinct from attribution_token; do not create a second attribution ledger. A click receipt is not a paid order.

- [x] Pin cross-repo golden vectors for `creative.contract.1`: EN `ee_hcp4v5pifa2ovj47rsir`, JA `ej_cs6k5hu42kvx65x66imw`. The Life Manager generator test and Product redirect/checkout/webhook fixtures use these same values.
- [x] Run a local source-chain probe using the actual `stage_intents`, `/go` click receipt/redirect, checkout request/Stripe metadata, and signed webhook durable receipt/PDF payload. The Japanese vector stayed identical through every stage; all provider calls were faked.
- [x] Run Life Manager attribution tests 8/8 and Product marketing-go/checkout/webhook tests 39/39. Product Landing check `37356856068` passes at PR #420 head `85116e29`.
- [x] Keep render, click, and checkout-session creation distinct from a paid order; no attribution step marks them as a sale.
- [ ] Record one natural paid Checkout and matching locale PDF provider receipt under Task 6. The source probe is not a sale or production receipt.

### Task 5: Add the eBook Product Loop with account-scoped publishing owners

**Files**
- Create: life-manager/apps/life-manager/scripts/ebook-distribute-daily.sh
- Create: life-manager/apps/life-manager/scripts/ebook-distribute-daily.js
- Create: life-manager/skills/earn/marketing-engine/ebook_distribute_daily.py
- Modify: life-manager/skills/earn/marketing-engine/render_eval/heygen_candidate.py to record verified wallet-cost evidence per render
- Modify: life-manager/skills/earn/marketing-engine/registry/ebook-packs/ebook-en-anicca-monk.json with the selected existing private avatar look and English voice IDs
- Modify: life-manager/skills/earn/marketing-engine/registry/accounts/tiktok.monk_anicca.json only after official Postiz enabled/account readback
- Modify: life-manager/config/loop-registry.json
- Modify: life-manager/config/marketing-destinations.json to add the English target only after its existing Postiz integration reads back enabled; preserve its current `provider_disabled` hold until then
- Modify: life-manager/apps/life-manager/config/product-loop-catalog.json with Product Loop id ebook and three account owners
- Modify: life-manager/apps/life-manager/lib/product-onboarding.js and the existing count assertions in its test files, economic-source-contract.test.js, and financial-manager-ingest.test.js; modify repository-root README.md and README.ja.md to update the public catalog from 14 to 15
- Modify: life-manager/runtime/loop/lm_loop_run.py and runtime/loop/tests/test_lm_loop_run_bounds.py to authorize exact result/pre-effect hints from this entrypoint
- Modify: life-manager/apps/life-manager/lib/marketing-video-publication-adapter.js and skills/video/lm-distribution/postiz_video.py to carry and clear the exact pre-effect marker at upload; modify `distribute.py` to serialize ledger appends, and `mobile-postiz-provider-reconcile.py` to persist exact recovered receipts before resolving a fence
- Create: life-manager/skills/earn/marketing-engine/ebook_distribute_daily.py to select deterministic baselines and serialize product-slot rendering across the two account owners
- Add: life-manager/skills/earn/marketing-engine/ebook-asset-packs/watercolor-mark-factory-v1/manifest.json with SHA-256 pins for the existing 11 Watercolor Monk Factory Kling scenes; copy those assets once into the Life Manager-owned asset root
- Modify: life-manager/skills/earn/marketing-engine/ebook_runner.py and test_ebook_portability.py to verify and use that asset pack, and to fail closed if it is missing or differs
- Reuse: life-manager/skills/earn/marketing-engine/ebook_runner.py
- Reuse: life-manager/skills/earn/marketing-engine/brain/baseline_queue.py
- Reuse: existing Marketing Video Publication Adapter and mobile-postiz-provider-reconcile.py
- Test: life-manager/apps/life-manager/scripts/ebook-distribute-daily.test.js, life-manager/skills/earn/marketing-engine/test_ebook_distribution_owner.py, and life-manager/skills/video/lm-distribution/test_postiz_video_pre_effect.py
- Test: focused runner replay/pre-effect contracts, product catalog tests, and ./bin/lm-loop-contract

**Interfaces**
- Product Loop: ebook; jobs: `ebook-en-tiktok-daily`, `ebook-ja-tiktok-daily`, and `ebook-ja-instagram-daily`. Each publisher job owns one existing account, so one LM occurrence causes at most one provider post.
- Render input: the locale's current product pack and one approved baseline script selected by date/slot. English uses `heygen-avatar-iv`; Japanese uses the 11 existing Watercolor Monk Factory Kling scenes, copied to Life Manager's versioned asset root and SHA-256 verified. Distribution runtime does not call or depend on the legacy OpenClaw checkout. All publishers for one product/slot reuse the exact render receipt and campaign token.
- Cadence: English `08:00`, `14:00`, `21:00` JST; Japanese `07:00`, `12:30`, `20:00` JST. Japanese TikTok/Instagram share each of the three daily Watercolor renders. English is scoped to its existing TikTok integration; its Postiz destination remains in a disabled hold until a channel slot is available. No English Instagram account is registered.
- Publisher input: exact rendered asset, approved-claims-compatible caption and ee_/ej_ token, account/integration resolved from the eBook pack, and the product-scoped standing policy authorized by this eBook marketing request.
- Output: durable render receipt, then one Postiz provider receipt/public URL or a typed effect_unknown fence. The owner never retries an unknown provider effect.
- The existing English TikTok Postiz integration is in a `provider_disabled` hold; official readback showed 30 enabled channels and one disabled. Keep the owner effect-free until a no-cost slot is confirmed and the exact integration reads back enabled. English Instagram remains setup-required; do not create or repurpose an account.
- HeyGen CLI v0.5.0 is available and API-key authenticated. Its existing `Wise Buddhist Monk` avatar and English `Simon - Calm & Gentle` voice are selected. Current wallet readback is USD 12.30 with USD 10 auto-reload at USD 5 threshold; preserve these settings. Do not start another render unless the prior render's exact wallet/cost receipt is reconciled.
- The current distribution renderer was found to use six generated solid-color placeholders, not Watercolor Monk Factory. Replace those inputs with the 11 pinned existing Kling scenes. Copy assets only; do not edit or run the legacy factory publisher.
- Official Postiz readback now returns 30 enabled integrations and one disabled. Keep English TikTok in `provider_disabled` until an existing no-cost slot is confirmed. Japanese Instagram/TikTok integrations are enabled.
- Product PR #420 is still OPEN and the Supabase CLI has no linked project ref. Do not publish until the production Checkout/PDF fulfillment route is deployed and verified. Cleanup owner is disabled by Dais's instruction; do not restart it.
- Task 5 is source work and does not publish. After merge/release, Task 6 owns production activation and official post receipts.

- [x] Cover account/locale resolution, disabled live gate, one platform per publication job, shared same-slot render replay, approved baseline claim scope, and exact Postiz pre-effect boundary.
- [x] Add Product Loop id ebook and the two Japanese publisher job mappings; update current catalog-count assertions and the public English/Japanese catalog rows.
- [x] Add eBook-specific Postiz targets for the existing Japanese Instagram/TikTok accounts and remove only their matching hold rows; keep English account routes disabled/setup-required.
- [x] Implement one account-scoped publisher entrypoint using baseline_queue, ebook_runner, the existing publication adapter, the existing Postiz readback reconciler, and the product-scoped standing policy for system-generated eBook baseline content.
- [x] Add a same-slot render lock so concurrent account owners reuse one exact video receipt; keep effect identity separate per owner/occurrence.
- [x] Add this entrypoint to the loop runner's result/pre-effect hint allowlists; classify setup/readiness gates before upload and carry official provider receipts after reconciliation.
- [x] Make official Postiz lookup reachable for an eBook identity sidecar whose local published row is missing; require one unique post matching integration, exact caption hash, bounded slot window, and published public URL.
- [x] Persist the recovered provider receipt in `distribution.jsonl` before resolving the effect fence. A same-slot replay must reuse the durable receipt and make zero provider publish calls.
- [x] Add focused regressions for missing-local-receipt recovery, ambiguous/no-match fail-closed behavior, durable receipt persistence, and same-slot replay-zero.
- [x] Extend the publisher owner to `ebook-en`/`ebook-ja`; pin locale, renderer, claims, CTA token prefix, and approved pack. Share one render per product/slot across active platform owners.
- [x] Add `ebook-en-tiktok-daily` with the existing 08:00/14:00/21:00 JST pack slots. Keep English Instagram setup-required. The Monk Anicca Postiz integration remains in a provider-disabled hold until an existing no-cost slot and `disabled=false` readback are confirmed. Do not upgrade Postiz or disable another product's integration.
- [x] Replace Japanese solid-color placeholders with the 11 existing Watercolor Monk Factory Kling scenes: pin source hashes, copy once into Life Manager asset state, verify clips before each render, and return `setup_required` without falling back if an asset is missing or mismatched.
- [x] Add regressions for Watercolor Factory scene selection and missing/hash-mismatched assets; copy and verify the 48,810,971-byte asset pack. Local preview run `ebook-run.8fb24a21e077a2a9c210ac0f` rendered 11.933 seconds at 720×1280 from the copied pack with Japanese captions and provider effects zero. Legacy publisher was not invoked.
- [x] Record HeyGen wallet before/after every Avatar IV render and persist the observed delta/reload state in its durable effect receipt. Refuse create without a USD wallet readback; if cost cannot be reconciled, keep the render fenced and block the next one. Preserve the $10 reload / $5 threshold. No live HeyGen render was used to calibrate cost because English Postiz is disabled and checkout/PDF fulfillment is not live.
- [x] Add a no-libass fallback using the installed Japanese font, Pillow PNG overlays, and FFmpeg `overlay`; add a focused regression for the missing `subtitles` filter path.
- [x] Add regressions for English-vs-Japanese renderer selection, three daily slots per locale, disabled English integration zero-effect behavior, and shared English render receipt across its Postiz owner.
- [x] Rerun focused reconciler/publisher/pre-effect, eBook owner/asset/HeyGen/Watercolor, product routing, loop bounds and catalog tests after the review fixes: Python 175/175, Node 54/54, `./bin/lm-loop-contract` PASS (`15` catalog loops, `184` registry jobs, `107` mapped), source-boundary PASS. The registry snapshot contract initially failed because the three new eBook jobs were absent; after updating the byte-stable fixture, its focused test passed. The full runtime suite cannot be accepted from this sparse worktree: 744 tests ran with 16 failures/29 errors because test-required paths are marked skip-worktree; use full-checkout CI for that gate.
- [x] Fetch latest `origin/main` `e842309e59d9065fd6e2005d4e8027ead0beea97`, rebase the dedicated feature branch, and rerun source acceptance: Python 172/172, Node 54/54, loop contract, source-boundary, and diff checks passed.
- [x] Commit `5d68435a3d71b8f72019cf778589b7872cfcbedd` and push `feat/ebook-publisher-source-20261006` to origin.
- [x] Obtain a fresh read-only review on head `6f7395bf6f`; fix the Postiz recovered-receipt caption hash, serialize English HeyGen renders and hold unresolved prior wallet receipts, clear the pre-effect hint before paid HeyGen create, and use the selected remote post's video hash. Regression tests pass for each behavior.
- [x] PR #6729 merged with all required checks PASS at `0ba957af5405bfbea5f1d6e9ce6ca78deb66b421`. At the 15:19 JST readback, main-derived immutable release `/Users/anicca/loops/releases/20261006T150708-0ba957af` was selected by `~/loops/current` and read-only. The three eBook owners were registered but unloaded; production publishing remains closed.

### Task 6: Publish the first eBook campaign and record its natural order

**Prerequisites:** Task 5 source owners merged; Product PR #422 deployed with checkout GET `405` and both locale PDF URLs `200 application/pdf`; Japanese TikTok and Instagram identities and enabled Postiz routes verified; `lm-loop doctor` green before any owner apply. The completed cleanup and Product PR #420 receipt-table DDL do not gate the first one-time eBook post. PR #420 remains separate hardening before durable webhook/subscription receipt claims and 14-day receipt-based measurement. English stays held until its existing TikTok integration reads back `disabled=false`; no English Instagram route is registered.

- [x] PR #6739 merged at `78c55432421dbe821773a96f7a7deb9646ee7599`; immutable release `20261006T160404-78c55432` is selected and `lm-loop doctor` returns `ok=true`. The active `upwork:dais` owner was preserved.
- [x] Run the canonical cleanup one-shot at 16:30 JST: reclaimed 56,844,145 bytes; `errors=0`; `protected_deletions=0`; six open candidates preserved; 21 inventory gaps. Both disk policy markers are absent; the 11 GiB level is the preventive cleanup tier.
- [x] Extend the existing `apps/landing/scripts/money-path-smoke.mjs` with a read-only GET to `/.netlify/functions/checkout` that expects the handler's `405 method not allowed`; keep the assertion inside the current post-deploy smoke/rollback flow.
- [x] Run `node apps/landing/scripts/money-path-smoke.mjs https://aniccaai.com` before source changes; it failed specifically at checkout GET with `502` after the site/Stripe-link checks passed.
- [x] In `/Users/anicca/Projects/anicca-products-worktrees/ebook-checkout-module-runtime-20261006` on `fix/ebook-checkout-module-runtime-20261006` (main base `7ca532244`), commit `21293ac4` makes checkout module-safe by moving the shared token validator to `.cjs`; the ESM landing helper reuses that module through a facade. Prices, locale handling, attribution metadata, and response shape remain covered by existing focused checkout tests.
- [x] Run focused eBook/Writer checkout tests (17/17), `node --check apps/landing/scripts/money-path-smoke.mjs`, and `git diff --check`.
- [x] Product PR #422 at `21293ac4` passes `Landing PR build` (`npm ci`, full telemetry tests, Next.js build); the fresh read-only verifier reports no Critical/Important findings.
- [x] Product PR #422 merged at 45bba82e; Netlify workflow 37432940639 completed and production money-path smoke passed: checkout GET 405, both locale PDFs 200 application/pdf.
- [x] PR #6744 source review found no Critical/Important findings; all required checks passed and it merged at main SHA aed62f3bb8d736d8f323939dd4d2240bb4551c63.
- [x] Authenticated Postiz readback: Japanese TikTok obou_anicca and Instagram obou.anicca are enabled, and public profile pages identify those handles. This confirms routing/profile presence, not a provider good-standing badge. English monk_anicca is disabled; aniccaen2 is excluded from the eBook route.
- [x] Main-derived release 20261006T172318-aed62f3b passes doctor; all three eBook owners were target-applied one at a time and read back on exact SHA/argv/state path. Publishing was closed during apply, then enabled through launchctl-safe in the active Aqua manager.
- [x] Local 20:00 Watercolor preview, scene manifest (11/11 hashes), exact Japanese copy/claims, CTA token/destination, and both enabled Postiz routes passed fresh read-only review. Preview SHA-256 1e6ac82267640c2f5bfc21aa83c39958e8f37d126c3fa16790bdfa82f349d0cf; external cost/effects 0.
- [x] CTA verification GET wrote reviewer click receipt 13faac90-8154-47f8-a45d-bbb3ec93cebf for token ej_lkbfh5nprxsjxnd3ec57 at 17:22 JST; exclude this QA click from natural click/conversion outcomes.
- [x] 20:00 JST natural attempt verified no Postiz post: official GET /public/v1/posts returned zero slot-token matches. Two owners produced 71 entrypoint failures, each error_detail LM_DATA_DIR is required, before Postiz/render. Do not replay this slot.
- [x] TDD root-cause fix: _child_environment_for_owner now sets canonical LM_DATA_DIR for the three registered eBook owners before the publish gate and overrides inherited values. No other owner receives this value.
- [x] Verification: focused regression 2/2, test_lm_loop_run_bounds.py 121/121, full runtime/loop unittest 765/765, registry Node tests 15/15, doctor 184 entries PASS, git diff --check PASS. The full suite emitted pre-existing ResourceWarnings for SQLite connections; no tests failed.
- [x] Commit and push the LM_DATA_DIR child-environment fix; fresh read-only review passed and all required PR #6766 checks passed. PR #6766 merged to main as `345fe64f5cfffa10e108404f70aec1d84414db1c`.
- [x] Merge PR #6771 at main `57e09ccf0d5ba84eadf7fabcfff9120ac3aff2e1` and select immutable release
  `20261006T214226-57e09ccf`.
- [x] Official Postiz `GET /public/v1/posts` readback at 21:50 JST returned zero target rows for the Japanese TikTok 20:00
  window and Japanese Instagram 21:47 occurrence. Sanitized evidence is
  `/Users/anicca/.local/state/life-manager/ebook/evidence/postiz-readback-ebook-occurrences-20261006T2150.json`.
- [x] Resolve only the proven pre-effect Japanese TikTok occurrence `ebook-ja-tiktok-daily:18dbed383f505970-22876`; the
  current-main CLI wrote a `HOST_PRE_EFFECT_RECONCILIATION` receipt with `resolution=RESOLVED` and zero unprovable rows.
- [ ] Run `lm-loop doctor` from the latest main-derived release and confirm zero missing/unmanaged/retired labels. The selected
  57e release currently returns `ok=false` because live retired label `ai.anicca.provision-browser.capafy.kosuke` is PID 91210.
  It belongs to the separate Capafy owner; do not stop/reload it from this eBook task.
- [ ] After doctor passes, apply `ebook-ja-instagram-daily`, `ebook-ja-tiktok-daily`, and `ebook-en-tiktok-daily` one at a time
  under each owner lock, only while idle. Read back each install receipt, release SHA, argv, state path, and rollback receipt.
- [ ] Allow the next natural Japanese 07:00 JST occurrence; verify official Postiz receipts and public URLs for Instagram and
  TikTok. The failed 20:00 slot is verified no-effect and must not be replayed.
- [ ] Re-enable only the existing English TikTok Postiz integration through its supported account flow; require official
  `disabled=false` readback and a successful identity preflight before the English owner can render or publish. English
  Instagram remains unregistered; do not create an account or upgrade Postiz.
- [ ] Keep the intended three daily slots per locale: English 08:00/14:00/21:00 JST; Japanese 07:00/12:30/20:00 JST. Japanese
  shares each Watercolor video across TikTok and Instagram; each owner still requires its own provider receipt/public URL.
- [ ] Continue per-occurrence Postiz readback and replay-zero. A schedule, HeyGen CLI completion, Watercolor render, or QA CTA
  click is not a public post or a sale.
- [ ] Continue Product PR #420's DDL hardening through an authorized Supabase management route; read back tables/RPC signatures/ACLs/schema cache before merging the migration. The current one-time eBook main flow uses existing Checkout metadata and direct PDF email fulfillment; PR #420's new receipt/subscription tables are separate hardening.
- [ ] Record a natural paid Checkout with matching locale PDF delivery under the same product/campaign occurrence only after durable receipt readback; record refunds, fees, and measured costs. Do not self-purchase.
- [ ] Start the 14-day eBook measurement after that matched receipt and keep it running during later Capafy work.

- Current cursor (2026-10-06 22:03 JST): PR #6771 is merged and release 57e is selected, but no eBook owner is applied to it.
  Full doctor is blocked by the live Capafy retired label above. JA TikTok exact pre-effect fence is resolved; the English
  TikTok route is disabled in Postiz. All three owners remain installed on 345fe64f. Latest readback has all three idle.
  First the Capafy owner must reconcile its label; next cut from current main 2cf, pass doctor, apply owners one at a time,
  and read the natural Japanese post receipts before continuing with English reconnection and its three slots.

### Task 7: Capafy Instagram marketing handoff — existing D5 plan only

- [ ] Start only after Task 6 records one natural eBook paid Checkout receipt and its matching PDF delivery receipt.
- [ ] Continue eBook 14-day measurement in parallel; it is not a Capafy start gate after that first complete receipt.
- [ ] Reconcile both existing Capafy publisher effects by official readback before any retry. Latest 2026-10-06 06:56 JST status: old owner remains effect-unknown with active fence `18db7caff1178a88-68028`; latest occurrence `18dbbe2a2b66f258-49164` exited 75 with no receipt/readback. New owner remains installed at `4eb6bbba`; latest occurrence `18dbc04f9ffa3f18-5828` exited 1 (`capafy ig reel loop requires node`) with effect unknown and no receipt/readback. Do not retry either lane before exact official readback.
- [ ] The Node/Python launchd lookup repair is already in Life Manager main at `9e3fb448b6` (PR #6663); build and load a current main-derived immutable release only after the eBook start gate. Verify account identity/status and Postiz integration through provider readback; current source comment says `@capafy.hooklab` is not connected.
- [ ] Follow the single source of Capafy marketing order in `docs/superpowers/plans/2026-10-04-capafy-10k-mrr-recipe.md`, Task D5: use one Life Manager Instagram owner; enforce at most one canary per 24 hours; publish one Reel with provider receipt; join `ct` clicks to available paid-order/payout evidence; measure 14 days.
- [ ] Keep the work limited to Capafy Instagram marketing. Do not change Capafy product, listing, pricing, or account-lifecycle code owned by the other developer. Do not switch to TikTok/YouTube or create a replacement account.
- [ ] Runtime errors do not prove that a CAPTCHA exists; no authenticated challenge screen was observed in the latest refresh. If a supported challenge is actually present, use the registered challenge path and read back account identity/provider state afterward. Identity, suspension, or appeal screens stay in the provider's official process.

**Economic target math (not a forecast):** 1,002 paid active subscriptions at $9.99/month are about $10,000 gross MRR before fees/refunds/cost. A one-time eBook order is never MRR. Capafy acceptance remains the existing 30-day banked-net contribution definition.
