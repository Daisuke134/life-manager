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

### Task 2: Replay-safe purchase receipt, PDF delivery, and subscription state — SOURCE READY / PRODUCTION BLOCKED

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
- [x] Run focused eBook/Writer/lead-magnet tests 31/31 and PostgreSQL 18.6 fixture; verify concurrent email writers leave one subscriber row without email UNIQUE and preserve legacy mapping. Syntax/diff checks pass.
- [x] Push source-ready change to PR #420 head `5ca501d335de3f8fdb2bf3f95e87fcf5283f0dfb`; exact-head Landing check run `37345444514` is SUCCESS.
- [ ] Use the existing Supabase admin path to read the production email unique constraint and normalized duplicate count. Current PostgREST column types are known; unique constraint and duplicate count are not.
- [ ] Compare production schema with the checked-in migration. Add a follow-up migration only if this authoritative readback shows an actual schema/data conflict; do not create another subscriber writer.
- [ ] Apply the migration through the authorized production admin path, then read back `ebook_webhook_receipts`, `ebook_subscription_states`, RPC signatures/ACLs, required columns, and PostgREST schema cache.
- [ ] Reconfirm the verified sender setting, merge PR #420 only after the production readback passes, then verify deployed SHA and health. Main push triggers production deploy.

**Current production blocker:** Supabase CLI has no linked project/access token and the credentials SSOT has no Supabase admin credential. The PR body records this exact gate. Do not merge or claim production readiness until an existing admin path is available and the migration/RPC readback is complete.

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

- [ ] Add or update one focused cross-repo contract proving the same `ee_`/`ej_` token survives intent creation, `/go` validation, checkout metadata, and durable buyer receipt.
- [ ] Reuse existing `campaign_token` and click receipt code; change only the interface the focused contract proves is broken.
- [ ] Run that focused contract and the existing checkout/webhook tests; record the exact commands and outcomes in the unified SSOT.
- [ ] Keep render, click, and checkout-session creation distinct from a paid order; no attribution step may mark them as a sale.

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

- [ ] Read back the existing owned account's provider identity/status and match it to the account registry and locale. Japanese Instagram `instagram.obou_anicca` is a candidate because its route was ready; this is not yet proof of account status or ownership.
- [ ] Add focused contract coverage for identity/locale mismatch, setup-required account, duplicate publish key, and unknown-effect fence.
- [ ] Connect `ebook_runner.py` to one existing publisher owner; preserve `awaiting_visual_approval` until its current approval contract passes.
- [ ] Confirm renderer cost against the existing spend cap before rendering paid assets.
- [ ] Publish one eBook canary through the verified existing account, then read back the provider receipt and public URL. Do not create accounts or automate likes/follows.
- [ ] Wait for one natural paid Checkout and its matching locale PDF provider receipt. Join both to the same product, campaign token, and occurrence; record refund/fee/cost status. Do not self-purchase.
- [ ] On the first matching paid/PDF receipt, start the 14-day eBook measurement; continue it while Capafy Instagram begins.

### Task 6: Capafy Instagram marketing handoff — existing D5 plan only

- [ ] Start only after Task 5 records one natural eBook paid Checkout receipt and its matching PDF delivery receipt.
- [ ] Continue eBook 14-day measurement in parallel; it is not a Capafy start gate after that first complete receipt.
- [ ] Follow the single source of Capafy marketing order in `docs/superpowers/plans/2026-10-04-capafy-10k-mrr-recipe.md`, Task D5: reconcile both publisher effects by official readback; make one Life Manager Instagram owner recognizable and loaded; verify the existing owned account and Postiz identity; enforce at most one canary per 24 hours; publish one Reel with provider receipt; join `ct` clicks to available paid-order/payout evidence; measure 14 days.
- [ ] Keep the work limited to Capafy Instagram marketing. Do not change Capafy product, listing, pricing, or account-lifecycle code owned by the other developer. Do not switch to TikTok/YouTube or create a replacement account.
- [ ] Current starting state: old publisher has active `resource_effect_unknown`; the new launchd label is currently `unmanaged_label` and its earlier occurrence is not returned by current `lm-loop` status. Resolve that owner/fence mapping before either lane can publish; never replay an unknown effect.
- [ ] If the authenticated existing page visibly shows a supported CAPTCHA, inspect the rendered challenge first. The latest local/open-source candidate `fiptcha` is Apache-2.0 but direct-CDP compatibility is untested; use it only after a same-session compatibility check. Otherwise use the registered challenge path. After any solve, read back the expected identity and provider state. Identity, suspension, or appeal screens stay in the provider's official process.

**Economic target math (not a forecast):** 1,002 paid active subscriptions at $9.99/month are about $10,000 gross MRR before fees/refunds/cost. A one-time eBook order is never MRR. Capafy acceptance remains the existing 30-day banked-net contribution definition.
