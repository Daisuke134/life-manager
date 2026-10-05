# Anicca eBook Revenue Loop Implementation Plan

> For agentic workers: この plan は実装時の作業設計です。TODO 順と cursor は Life Manager unified SSOT が所有します。

**Goal:** eBookを最優先で実装し、既存の英日checkoutと自社SNSから一回購入と任意登録のLetter/Tegami MRRを生み、最初の有料注文とPDF配信を同じreceiptで確認してからCapafy Instagramへ引き継ぐ。

**Architecture:** Stripe checkoutとPDF配信は`anicca-products`に残す。Life Managerは現在のeBook render receipt、marketing video adapter、既存account registryを一つのpublication ownerから接続する。Capafy Instagramは別の`life-manager-capafy-ig` Postiz laneを使い、Capafy開発担当者が所有するコードを変更しない。OpenClaw cronは追加で動かさない。

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

## Review Focus

- 表示価格と Stripe Price ID が違う。
- /achan と旧 /jp route が混在する。
- webhook retry が二重 email / buyer row を作る、または DB/email failure を隠す。
- campaign click が checkout metadata / paid order に join しない。
- account registry と provider status がずれ、誤った account に投稿する。
- 旧Capafy IG ownerとPostiz laneが同じaccountへ二重投稿する、または未確認の旧effectを再送する。
- 1日3回のCapafy scheduleが初回canaryの上限1回/24時間を超える。
- eBook one-time gross を MRR と誤算入する。

---

### Task 1: Product offer, locale, and checkout contract

**Files**
- Modify: Daisuke134/anicca-products/apps/landing/app/monk/page.tsx
- Modify: Daisuke134/anicca-products/apps/landing/app/achan/page.tsx
- Modify: Daisuke134/anicca-products/apps/landing/netlify/functions/checkout.js
- Test: Daisuke134/anicca-products/apps/landing/netlify/functions/_lib/__tests__/ebook-checkout.test.js

**Interfaces**
- Request: lang, product=ebook, optional campaign_id from the landing query string.
- Response: Stripe hosted checkout URL.
- Stripe metadata: lang, product, campaign_id; the existing locale Price remains the payment source.

- [ ] Step 1: Add failing tests for EN/JA price selection, eBook payment mode, Letter subscription mode, and campaign token propagation.
- [ ] Step 2: Run apps/landing: npm run test:telemetry. Expected: new eBook cases fail before implementation.
- [ ] Step 3: Pass campaign_id through both Buy buttons to Stripe metadata. Align the EN chapter-length claim with the shipped Markdown; verify the JA chapter claim against its published artifact before retaining it.
- [ ] Step 4: Run npm run test:telemetry and npm run build in apps/landing. Expected: PASS with /monk and /achan working.
- [ ] Step 5: Commit the focused checkout/content change.

### Task 2: Make buyer receipt and PDF fulfillment retry-safe

**Files**
- Modify: Daisuke134/anicca-products/apps/landing/netlify/functions/webhook.js
- Test: Daisuke134/anicca-products/apps/landing/netlify/functions/_lib/__tests__/ebook-webhook.test.js

**Interfaces**
- Input: signature-verified checkout.session.completed event.
- Output: buyer receipt joined by Stripe session ID/campaign ID, plus delivery status for the correct EN/JA PDF.
- Letter subscription events update paid/expired state and never enter eBook delivery.

- [ ] Step 1: Add failing tests for invalid signature, EN/JA PDF selection, subscription separation, replay of the same Stripe event, and DB/email failures.
- [ ] Step 2: Run apps/landing: npm run test:telemetry. Expected: replay and error-path cases fail.
- [ ] Step 3: Read the existing Supabase buyer schema first. Use its unique Stripe session/event key; add the smallest durable idempotency receipt only if no such key exists. Persist delivery state and surface failures so provider retry is observable.
- [ ] Step 4: Run npm run test:telemetry. Expected: one purchase receipt per session and no hidden fulfillment failure.
- [ ] Step 5: Commit the focused webhook change.

### Task 3: Join the campaign token to money

**Files**
- Modify: life-manager/skills/earn/marketing-engine/ebook_runner.py
- Modify: life-manager/skills/earn/marketing-engine/attribution.py
- Modify: life-manager/skills/earn/marketing-engine/registry/ebook-packs/ebook-en-anicca-monk.json
- Modify: life-manager/skills/earn/marketing-engine/registry/ebook-packs/ebook-ja-watercolor.json
- Test: life-manager/skills/earn/marketing-engine/test_ebook_runner_replay.py
- Test: life-manager/skills/earn/marketing-engine/test_ebook_asset_pack.py
- Test: life-manager/skills/earn/marketing-engine/test_ebook_portability.py

**Interfaces**
- Existing render receipt carries product_id, creative_id, script_id, renderer_id, and attribution token.
- The same token goes to the landing URL, Stripe metadata, buyer receipt, and channel report.
- CFO reads paid sessions, refunds, fees, actual costs, and bank receipts; it does not infer revenue from clicks.

- [ ] Step 1: Add failing contract tests for a campaign token surviving render intent → URL → Stripe metadata → buyer receipt.
- [ ] Step 2: Run the focused marketing-engine eBook tests. Expected: the campaign-join case fails.
- [ ] Step 3: Reuse the existing campaign_token helper and receipt schema; do not create a second attribution ledger.
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
