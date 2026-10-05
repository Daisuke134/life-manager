# Anicca eBook Revenue Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. TODO order and cursor live only in the Life Manager unified SSOT.

**Goal:** eBookを最優先で実装し、既存の英日checkoutと自社SNSから一回購入と任意登録のLetter/Tegami MRRを生み、最初の有料注文とPDF配信を同じreceiptで確認してからCapafy Instagramへ引き継ぐ。

**Architecture:** Stripe checkout・receipt・PDF配信は`anicca-products`に残す。Letter webhookはDB発番のreadback generationをStripe GET前に予約し、最新generationだけをsubscription stateへ適用する。既存subscriber pointerはmigrationでstate mappingへ引き継ぎ、複数subscriptionのactive/trialingからtierを集計する。pointer更新はStripe `Subscription.created`の順で決め、created timeを未照合のlegacy pointerは保持する。pointerなしの既存paid tierも公式readback対象として別flagで保持する。Life Managerは既存render receipt・marketing adapter・account registryを一つのpublication ownerへ接続する。Capafy Instagramは`life-manager-capafy-ig` Postiz laneを使い、別担当所有のCapafy開発コードを変更しない。OpenClaw cronは追加で動かさない。

**Tech Stack:** Next.js、Netlify Functions、Stripe Checkout/webhook、Resend、Supabase、Python marketing-engine、Life Manager loop registry、既存の video generation/publication adapters。

**Spec:** docs/superpowers/specs/2026-10-05-ebook-revenue-loop-design.md

## Global Constraints

- Life Manager unified SSOT 以外に実行順・current status TODO を作らない。
- eBook は one-time sale、Letter/Tegami subscription は MRR として集計する。
- page price/listing/views/render は売上ではない。sale/refund/fees/cost/payout/bank を同じ期間で read back する。
- Account status は provider official readback と owner registry を照合する。restriction/unknown 時は投稿・再送・replacement account creation を行わない。
- No automated engagement, anti-detection, proxy/fingerprint workaround, or account creation to evade a platform restriction.
- 既存のユーザー所有IG/TikTok accountだけを使う。registryとprovider official identity/statusが合わない場合は`setup_required`/`review_required`で止め、別accountを作らない。
- Capafy Instagram marketingはeBookで最初の自然な有料決済とPDF配信が同じreceiptに結び付いた後に開始する。eBookの14日間測定はその後も続ける。
- Capafy Instagramは`life-manager-capafy-ig` Postiz laneだけをpublish ownerとして使う。旧`capafy-ig-marketing-daily`の同一occurrence effect-unknownと二重owner状態をread backするまでどちらからも投稿しない。
- Capafy code/build/account-lifecycleは別担当の境界。Marketing laneは既存Postiz skeletonのaccount/creative/attribution/readbackだけを扱う。
- OpenClaw cron と Life Manager owner を二重に enable しない。
- Customer emailはverified domainの`RESEND_FROM_EMAIL`だけを使う。値が無い場合はResendを呼ばずretryable receiptにする。

## Review Focus

- Stripe GETの遅い応答が解約stateを上書きせず、pending generationでsupersedeされたCheckoutはWelcome receiptを終端確定せず再試行する。
- 古いCheckout eventの再配信が、新しいStripe subscription pointerを奪わない。
- migration前からあるsubscriberのsubscription eventをmapping missingにしない。
- 既存の別active subscriptionがあるとき、一つのcanceled eventでtierをexpiredにしない。
- migration直後、公式readback前の既存paid tierを誤って失効させない。

---

### Task 1: Product offer, locale, and checkout contract

**Files**
- Modify: Daisuke134/anicca-products/apps/landing/app/monk/page.tsx
- Modify: Daisuke134/anicca-products/apps/landing/app/achan/page.tsx
- Modify: Daisuke134/anicca-products/apps/landing/app/letter/page.tsx
- Modify: Daisuke134/anicca-products/apps/landing/app/tegami/page.tsx
- Create: Daisuke134/anicca-products/apps/landing/lib/checkout-attribution.js
- Modify: Daisuke134/anicca-products/apps/landing/netlify/functions/checkout.js
- Test: Daisuke134/anicca-products/apps/landing/netlify/functions/_lib/__tests__/ebook-checkout.test.js
- Create: Daisuke134/anicca-products/.github/workflows/landing-pr-build.yml

**Interfaces**
- Request: `lang`, `product`, `mode`, optional `attribution_token` copied from the existing `utm_campaign` query parameter.
- Response: Stripe hosted checkout URL.
- Stripe metadata: `lang`, `product`, `attribution_token`; for subscription mode the token also goes into Subscription metadata. The existing locale Price remains the payment source.

- [x] Step 1: Add failing tests for the page URL helper, EN/JA price selection, eBook payment mode, Letter subscription mode, locale-matched `utm_campaign` → `attribution_token` propagation, and subscription metadata. RED observed before implementation.
- [x] Step 2: Run apps/landing: `npm run test:telemetry`. The new eBook cases failed before implementation as expected.
- [x] Step 3: Read `utm_campaign` on `/monk`, `/achan`, `/letter`, and `/tegami`; pass it as `attribution_token` in the checkout request and into Checkout/Subscription metadata. Keep `/go/<token>` as the existing click-receipt entrypoint. Remove the unsupported per-chapter length claims from EN/JA HTML and JSON-LD; retain the verified claim of 49 short chapters.
- [x] Step 4: `npm run test:telemetry` passes 336/336 and `npm run build` passes in GitHub Actions run `37315148621`. The PR workflow uses a localhost dashboard snapshot URL and performs no deploy.
- [x] Step 5: Commit and push the focused checkout/content change (`a36098a209`, build workflow `c6614243ee`); PR #419 merged to main as `6c52d4cc13`.

### Task 2: Make buyer receipt and PDF fulfillment retry-safe

**Files**
- Modify: Daisuke134/anicca-products/apps/landing/netlify/functions/webhook.js
- Create: Daisuke134/anicca-products/apps/landing/netlify/functions/_migrations/2026-10-05-ebook-webhook-receipts.sql
- Test: Daisuke134/anicca-products/apps/landing/netlify/functions/_lib/__tests__/ebook-webhook.test.js
- Modify: Daisuke134/anicca-products/apps/landing/netlify/functions/_lib/__tests__/writer-webhook.test.js
- Modify: Daisuke134/anicca-products/.github/workflows/landing-pr-build.yml

**Interfaces**
- Input: signature-verified Checkout, invoice, and subscription lifecycle events.
- Output: durable event/session receipt joined by Stripe session ID/attribution token, plus delivery status for the correct EN/JA PDF. The eBook email has an optional locale subscription CTA with the same `utm_campaign`.
- Letter subscription events preserve the token, separate trial access from paid MRR, and never enter eBook delivery. Count MRR only after the first paid invoice and active status.
- `reserve_ebook_subscription_readback(subscription_id,email?,customer_id?)` returns `{generation,subscriber_id}` before Stripe GET. `apply_ebook_subscription_state(subscription_id,subscriber_id,generation,status,subscription_created_at,event_id)` applies only if generation is still current.
- `RESEND_FROM_EMAIL` is mandatory for eBook/Letter delivery. There is no test-domain fallback; missing sender configuration returns a retryable receipt before provider send.
- Existing `subscribers.stripe_subscription_id` rows seed subscription mappings. `subscriber.tier` is recomputed from all mapped active/trialing states and preserves migration-carried paid access until mapped subscriptions receive official Stripe readback. A paid legacy row without a Stripe pointer retains a separate pending-readback flag. Pointer ordering uses Stripe `Subscription.created`; an old pointer without created-time readback remains until reconciled. Once reconciled, the pointer is reselected from all saved states by maximum `created` (subscription ID breaks equal-second ties).

- [x] Step 1: Add failing tests for signature, locale PDF/CTA, event/session replay, DB/email failure, stale same-subscription readback, and delayed cross-subscription Checkout. RED for the two delayed-readback cases was observed before the timestamp-CAS implementation; fresh review then showed that late-delivered old Checkout and legacy subscriber mappings require a generation-based redesign.
- [x] Step 2: Add failing tests for delayed active response with worker clock skew, late old Checkout, existing migrated lifecycle event, pending generation racing Welcome, legacy pointer re-election, and missing verified sender. RED was observed on the previous timestamp/single-state/fallback implementations.
- [x] Step 3: Add DB-issued per-subscription readback generations before Stripe GET; apply only the current generation. Keep superseded Checkout receipt retryable. Seed legacy subscription mappings and paid-preservation flags, aggregate access from all mapped states, reselect pointer by maximum Stripe `Subscription.created`, and require configured `RESEND_FROM_EMAIL` before sending.
- [x] Step 4: Focused eBook/Writer tests pass 27/27. The migration and RPC pass on a local PostgreSQL 18 fixture containing legacy pointer, no-pointer paid, and new subscriber rows; verified stale generation rejection, Welcome retry after supersession, lifecycle mapping, pointer re-election, multiple active state aggregation, and legacy paid preservation.
- [x] Step 5: `npm run test:telemetry` passes 358/358; `node --check`, `git diff --check`, PostgreSQL 18 fixture, and fresh read-only source review PASS. Commit `b8ea8f0c2e` is pushed to PR #420. PR CI has not appeared yet; manual workflow run `37329324798` is in progress with provider metadata probe before build. Previous PR build passed at `f712eacec4`; workflow_dispatch at that head failed in `next/font` after dashboard snapshot fetch failed, before the old probe position.
- [ ] Step 6: Read production schema constraints and verified sender before applying SQL or allowing customer delivery. Prior Netlify OpenAPI exposed `buyers` columns (`amount_paid,currency,email,id,lang,product,purchased_at,stripe_session_id`) and `subscribers` columns (`email,id,lang,signed_up_at,source,stripe_customer_id,stripe_subscription_id,tier,unsubscribed_at`) but not types/constraints; `ebook_webhook_receipts` was not exposed. Resend `GET /domains` returned 401. Runtime now requires `RESEND_FROM_EMAIL`; its production presence and verified domain remain unconfirmed. Do not merge while migration, PostgREST schema cache, or sender readiness is missing because main push auto-deploys.
- [x] Step 7: Initial source PR #420 head `f712eacec4` is superseded by pushed source commit `b8ea8f0c2e`; final source PR remains open and production merge is held on migration/sender readiness.

### Task 3: Join the campaign token to money

**Files**
- Modify: life-manager/skills/earn/marketing-engine/ebook_runner.py
- Modify: life-manager/skills/earn/marketing-engine/registry/ebook-packs/ebook-en-anicca-monk.json
- Modify: life-manager/skills/earn/marketing-engine/registry/ebook-packs/ebook-ja-watercolor.json
- Test: life-manager/skills/earn/marketing-engine/test_ebook_runner_replay.py
- Test: life-manager/skills/earn/marketing-engine/test_ebook_asset_pack.py
- Test: life-manager/skills/earn/marketing-engine/test_ebook_portability.py

**Interfaces**
- Existing render receipt carries `product_id`, `creative_id`, `script_id`, `renderer_id`, and the opaque token from `measure/attribution.py`.
- `/go/<token>` records the click; `utm_campaign` becomes checkout `attribution_token`, Stripe metadata, buyer/subscriber receipt, and channel report. Keep `campaign_id=creative_id` distinct.
- CFO reads paid sessions, refunds, fees, actual costs, and bank receipts; it does not infer revenue from clicks.

- [ ] Step 1: Add failing contract tests for a token surviving render intent → `/go/<token>` → `utm_campaign` → Stripe metadata → buyer/subscriber receipt.
- [ ] Step 2: Run the focused marketing-engine eBook tests. Expected: the campaign-join case fails.
- [ ] Step 3: Reuse the existing `campaign_token` helper and receipt schema; do not modify `measure/attribution.py` or create a second attribution ledger unless a failing test proves a missing contract.
- [ ] Step 4: Run the focused tests. Expected: one token joins to at most one paid session.
- [ ] Step 5: Commit the focused attribution change.

### Task 4: Add one Life Manager distribution owner

**Files**
- Create: life-manager/skills/earn/marketing-engine/ebook-distribute-daily.sh
- Modify: life-manager/config/loop-registry.json
- Modify: life-manager/apps/life-manager/config/loop-adapters.json
- Test: life-manager/apps/life-manager/lib/marketing-video-publication-adapter.test.js
- Test: new eBook distribution-owner contract test

**Interfaces**
- Owner ID: ebook-distribute-daily, one occurrence and one durable state root.
- Consumes: rendered eBook creative receipt and one provider-confirmed account/product pack.
- Produces: stable publish effect key plus either official provider receipt or an effect_unknown fence.

- [ ] Step 1: Add failing tests for disabled-account admission, duplicate slot, and unknown-effect fence.
- [ ] Step 2: Run focused registry/publication tests. Expected: restricted accounts and duplicate publish are rejected.
- [ ] Step 3: Wire ebook_runner receipts through existing marketing-video generation/publication adapters. Keep OpenClaw cron disabled; do not call account factory, warmup automation, or direct-browser bypass.
- [ ] Step 4: Run focused tests plus loop-registry validation. Expected: one publishing owner, replay-zero, no second scheduler.
- [ ] Step 5: Commit and merge to main; deploy only from a main-derived immutable release.

### Task 5: eBook初回canary・有料注文・引き継ぎ

**Files**
- Update: Life Manager unified SSOT at the eBook-to-Capafy handoff.
- Readback: provider post receipt, campaign click, Stripe paid session/refund, PDF delivery, subscription state, actual cost, payout, bank receipt.

- [ ] Step 1: Require official account status and resolve same-owner effect_unknown before any canary. Do not retry or publish while unknown.
- [ ] Step 2: Render one original demo and verify the asset receipt, AI disclosure, campaign token, and PDF source.
- [ ] Step 3: Publish one canary through the approved owner route and record the provider receipt/public URL.
- [ ] Step 4: 同一occurrence内の有料Stripe session、buyer receipt、正しいPDF配信receipt、campaign token、返金・手数料・実費、subscription状態を照合する。一回購入の履行にsubscription購入を要求しない。
- [ ] Step 5: この最初の完結した自然receipt後、unified SSOT cursorをCapafy Task D5へ進める。eBookの有料注文と継続購読は14日間read-onlyで計測し、次のlaneを止めない。

**目標算数（予測ではありません）:** $9.99/月でgross MRR $10,000には、手数料・返金前で有料継続購読者1,002人が必要です。$10.99のeBook一回購入で月$10,000のgross salesを得るには910件必要ですが、MRRではありません。別目標のCapafy $10,000 contributionは、viewやseller gross balance、eBook MRRではなくCFO banked-net receiptで測ります。
