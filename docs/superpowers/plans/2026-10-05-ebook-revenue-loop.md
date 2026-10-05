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

### Task 2: Replay-safe purchase receipt, PDF delivery, and subscription state — SOURCE READY

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

- [x] Add failing cases for replay, storage/email failures, stale subscription GET, late Checkout, legacy mapping/pointer, missing sender, and delayed Welcome receipt.
- [x] Implement durable receipt, one-time PDF delivery, DB generation reserve/apply, subscription aggregation, and retryable superseded Checkout.
- [x] Add normalized-email advisory locking and lookup-before-insert so same-RPC reservations reuse one subscriber even when email has no unique index. PostgreSQL 18 no-unique fixture confirms two reservations leave one row.
- [x] Run focused eBook/Writer 27/27, telemetry 358/358, PostgreSQL 18 fixtures, syntax/diff checks; latest independent SQL review PASS.
- [x] Push SQL lookup fix as bc34edb14b to PR #420.
- [x] Confirm Landing PR check at exact head bc34edb14b. GitHub Actions run 37339391128 completed PASS.
- [ ] Read authoritative production schema constraints and duplicate-email status using DB admin access. PostgREST types are known, unique constraints are not. The lead-magnet writer currently bypasses the new advisory lock.
- [ ] If email has no unique constraint, add one shared DB-owned normalized-email upsert and route every subscriber writer through it before migration/deploy.
- [ ] Apply the migration; read back ebook_webhook_receipts, ebook_subscription_states, RPC signatures, required columns, and schema cache on production.
- [ ] Reconfirm verified sender configuration, then merge PR #420. Main push auto-deploys; read back loaded production SHA/health after deploy.

### Task 3: Make lead-magnet signup compatible with the verified production sender

**Files**
- Modify: anicca-products/apps/landing/netlify/functions/lead-magnet.js
- Modify: anicca-products/apps/landing/netlify/functions/_migrations/2026-10-05-ebook-webhook-receipts.sql or a follow-up migration only if Task 2 schema readback requires it
- Test: anicca-products/apps/landing/netlify/functions/_lib/__tests__/lead-magnet.test.js

**Interfaces**
- Input: normalized email and lang en/jp.
- Subscriber write: use the unique email constraint if confirmed; otherwise use one DB RPC that applies the same normalized-email advisory lock as the Checkout webhook.
- Day-0 sender: RESEND_FROM_EMAIL, never onboarding@resend.dev. Return success only after the subscriber write and provider send succeed; never echo provider response bodies to the caller.

- [ ] Add failing tests for missing sender, subscriber write failure, provider failure, and normalized-email replay.
- [ ] Run the focused lead-magnet tests and observe the expected failures.
- [ ] Implement the minimal verified-sender/write-status fix and shared upsert only if the authoritative schema shows the unique constraint is absent.
- [ ] Run focused tests. Do not use this free-signup endpoint as proof of paid MRR.

### Task 4: Join the creative token to the natural purchase receipt

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

- [ ] Add one cross-repo contract proving the same token survives intent creation, redirect validation, checkout metadata, and durable purchase receipt.
- [ ] Reuse existing campaign_token and click receipt code; change the smallest failing interface only.
- [ ] Record first natural paid session, correct locale PDF message receipt, refund/fee/cost status, and exact occurrence in unified SSOT. Do not self-purchase with personal funds.

### Task 5: Register one eBook publishing owner using existing accounts

**Files**
- Create: life-manager/skills/earn/marketing-engine/ebook-distribute-daily.sh only if no current entrypoint can own the occurrence
- Modify: life-manager/config/loop-registry.json
- Modify: life-manager/apps/life-manager/config/loop-adapters.json only if required by the existing route
- Reuse: life-manager/skills/earn/marketing-engine/ebook_runner.py
- Reuse: life-manager/skills/earn/marketing-engine/publish/publish_cli.py
- Reuse: existing Marketing Video Publication Adapter

**Interfaces**
- Owner ID: ebook-distribute-daily; one occurrence/state root per product campaign; no OpenClaw scheduler.
- Input: render receipt, deterministic ee_/ej_ token, exact asset hash, matching locale, registry-verified existing account.
- Output: provider post receipt/public URL or effect_unknown fence; never infer post success from process exit alone.

- [ ] Add focused failing contract cases for registry identity mismatch, setup_required account, duplicate publish key, and unknown-effect fence.
- [ ] Connect the runner to the existing publisher; preserve awaiting_visual_approval until the current approval contract passes.
- [ ] Use only a matching existing account whose official identity/status and allowed locale are read back. Current English pack has TikTok only; Japanese pack registers TikTok and Instagram.
- [ ] Confirm render cost/approval before using a paid renderer. Keep unverified spend behind the existing spend cap.
- [ ] Publish one natural eBook canary through the selected existing account and record the provider receipt. Do not create accounts or automated engagement.

### Task 6: Capafy Instagram handoff — reference the existing D5 plan

- Start only after Task 4 records one natural eBook paid Checkout receipt and the matching PDF delivery receipt.
- Continue eBook 14-day readback in parallel; it is not a Capafy start gate after the first complete receipt.
- Execute docs/superpowers/plans/2026-10-04-capafy-10k-mrr-recipe.md, Task D5, in its existing order: reconcile both publisher effect_unknowns; install/read back the latest single owner; verify the existing account and Postiz identity; gate at no more than one canary per 24 hours; publish one Reel with official receipt; join ct clicks to available Capafy order/payout evidence; measure 14 days.
- Change only the D5 Instagram marketing implementation. Do not edit the separate Capafy product/listing/account-lifecycle source.
- If a visible CAPTCHA appears on the authenticated existing account, inspect the rendered challenge and use only the registered supported challenge path; then verify the expected identity/provider state. Identity, suspension, or appeal screens remain in the provider's official process.

**Economic target math (not a forecast):** 1,002 paid active subscriptions at $9.99/month are about $10,000 gross MRR before fees/refunds/cost. A one-time eBook order is never MRR. Capafy acceptance remains the existing 30-day banked-net contribution definition.
