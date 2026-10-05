# Anicca eBook Revenue Loop — Design

> この文書は設計参照です。Life Manager の実行順・current cursor・TODO state は docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md だけを正本にします。

## 目的

既存の The Anicca Reset と自社 Stripe checkout を使い、既存の自社SNSアカウントから一回購入と任意の継続購読につながる収益 loop を整えます。eBook の一回購入と subscription MRR を分離し、同じ期間の公式 sale/refund/fee/cost/settlement receipt で成果を判定します。

## 優先度と担当境界

- Dais が指定した実行順は、(1) eBook を一件の自然な有料checkout・PDF配信receiptまで通す、(2) Capafy Instagram marketing を開始する、です。eBook の14日計測は2へ進んだ後も継続し、次の仕事を止めません。
- eBook配信loopは未登録で、現在の担当者もいません。このspecとplanの最初の実装対象です。
- Capafyの商品・listing・account lifecycleのコードは別の担当者が所有します。この作業はCapafy Instagram marketingだけを担当し、既存の`life-manager-capafy-ig` Postiz laneを利用します。Capafy側のコードを重複修正しません。
- eBookとCapafyの両方で、新規・代替アカウントは作成しません。registryにある既存アカウントをprovider公式状態と照合し、ユーザー所有とgood-standingを確認できたものだけ使います。対応が無いlocale/platformは`setup_required`のままにし、投稿を止めます。
- eBookの有料購入、Letter/Tegami subscription、Capafyの注文は別の商品・別のcampaign tokenで追跡します。subscriberへの登録は明示opt-inの結果だけです。

## 現在の根拠（read-only、2026-10-05）

- Daisuke134/anicca-products main に /monk、/achan、Stripe checkout、checkout.session.completed webhook、PDF assets があります。公開ページ表示は EN $10.99、JA ¥1,580 です。ページやコードの存在は購入・売上の証明ではありません。
- /monk と /achan は eBook の一回購入です。/letter $9.99/月、/tegami ¥980/月は別の subscription 商品で、MRR を生む経路です。
- /letter と /tegami は14日trial後に請求するsubscription checkoutです。trialing状態やsubscription作成だけをpaid MRRに数えず、最初の`invoice.paid`後にactive paid subscriptionとして数えます。
- 既存`/go/<token>` routeはclick receiptを書き、ebook token `ee_...`/`ej_...`を`utm_campaign`として`/monk`/`/achan`へ渡します。4つのlanding CTAとcheckoutは現在tokenをStripeに渡していません。
- 現行`/monk` checkout requestは`lang`だけを渡し、Stripe metadataにcampaign idを持ちません。`checkout.js`はebookをone-time payment、Letterをsubscriptionとして扱います。
- `webhook.js`はbuyer/subscriber記録とメールを処理しますが、Supabase write failureを`.catch(()=>{})`で隠し、同じStripe eventの再配信でメールを再送し得ます。
- eBook配信メールは現在PDF linkだけを含みます。optional CTAから同じ`utm_campaign`付きで`/letter`/`/tegami`へ進めますが、購読は別のcheckoutを本人が完了した場合だけ成立します。
- 公開MarkdownはEN/JAともH2章見出しが49個です。各章本文はEN平均76.8語（55–123語）、JA平均178.9文字（空白除外、127–280文字）で、ページの「各章約150語/字」と一致しません。HTMLとJSON-LDから章ごとの長さのclaimを外し、「49の短章」に揃えます。
- checkout attribution helper とStripe Checkout metadataはproduct PR #419（merge `6c52d4cc13`）でmainへ反映済み。focused tests 7/7、telemetry suite 336/336、GitHub Actions Next build PASS。Life Manager の marketing-engine/ebook_runner.py は receipt 付き render と awaiting_visual_approval の配信 intent を作りますが、Stripe 売上や公開投稿は行いません。
- Task 2の初回product PR #420 (`f712eacec4`) はdurable receipt、同一session replay防止、Resend ID/409 effect fence、campaign CTA、trial/invoice/status receiptを実装し、PR telemetry/buildはPASSした。fresh reviewsでtimestamp CAS、late-delivered旧Checkout、既存mapping欠落、superseded CheckoutのWelcome終端化、legacy pointer再選出欠落、test-only Resend senderの問題が判明した。修正commit `b8ea8f0c2e` は同じPR #420へpush済み。最終diffはDB generation reserve→Stripe GET→generation一致apply、superseded Checkout receiptのretryable化、legacy mapping/paid flag seed、全subscription stateのtier集計、公式readback後の最大`Subscription.created`pointer再選出を実装する。メール送信元はrequired env `RESEND_FROM_EMAIL`で、未設定時はResend呼び出し前にretryable receiptを返す。eBook/Writer tests 27/27、telemetry 358/358、PostgreSQL 18 fixture、独立source reviewはPASS。最終commit headのPR CIと手動metadata probeは現在実行中。本番schema/type/constraint、migration適用、schema cache、verified senderは未確認。
- production schema readbackは`buyers`/`subscribers`の列のみで型・制約は不明、`ebook_webhook_receipts`は前回未公開。Resend `GET /domains`は401、`onboarding@resend.dev`はtest-only sender。migration未適用・送信元未確認のためmain deployは保留。workflow_dispatchでは`next/font`のnull-regex errorでbuildが失敗し、manual-only provider metadata probeがskipされた。probeをbuildより前へ移動して再取得する。
- `ebook-distribute-daily`は`config/loop-registry.json`にありません。EN packはTikTok accountを登録しInstagramを`setup_required`にします。JA packにはTikTokとInstagramが登録されていますが、packの記載自体はprovider login/statusの証拠ではありません。
- OpenClaw local jobs.json では monk 関連 cron が無効です。Gateway が切断しているため loaded schedule は未確認です。Life Manager の CFO readback でも eBook の sale/net/settlement は unknown です。
- Capafyには旧`capafy-ig-marketing-daily`と新`life-manager-capafy-ig`のscheduled ownerがあります。新laneのruntime fix PR #6663とeffect-reconcile PR #6668はmainにmerge済みですが、installed releaseは未反映でpost receiptもありません。旧ownerの最新readbackは`18dba3f8c5d30d00-93546`（effect unknown）で、`18db7caff1178a88-68028`もofficial readback待ちです。二重ownerと未解決effectを閉じるまでCapafy投稿を開始しません。
- 新Postiz laneは09:00/14:00/20:00の3回/日です。最初のマーケティングcanaryは1回/24時間に制限し、その制御ができるまでscheduleをliveにしません。

## 指標の定義

- MRR は有料invoiceが支払われ、Stripe subscription stateがactiveのLetter/Tegami subscriptionだけの月額recurring revenueです。trialing、invoice未払い、一回のeBook purchaseはMRRに含めません。fees/refunds/actual cost/bank settlement後のnet profitは別metricとして報告します。
- $9.99/月で$10,000 gross MRRには1,002 active paid subscribersが必要です。fees、refunds、costを引いたnet targetにはそれ以上必要です。
- $10.99 の eBook 一回購入で月 $10,000 gross には910件の paid orders が必要ですが、これは monthly one-time sales であって MRR ではありません。
- Life Manager の既存 $10,000 target は30日維持の banked net profit です。Capafy seller earnings、eBook gross、subscription MRR、banked net は別 metric のまま保持します。算数は規模の目安で、予測ではありません。
- Daisの目標は、eBook subscriptionで$10,000のgross MRR、Capafy marketingでmanagerへ$10,000を加えることです。Capafy contributionは既存CFO定義に従い、手数料・実費・出金・銀行着金を照合した30日banked netで数えます。既存portfolio planのCapafy配分$5,000とは差があるため、実測前のforecastには使いません。

## データフロー

```mermaid
flowchart LR
  subgraph E[1. eBookを先に実装]
    EC[原文に基づくeBook実演動画] --> EA[所有と状態を確認した既存IG/TikTok]
    EA --> GO[/go/<token> click receipt]
    GO --> EP[/monk または /achan?utm_campaign=<token>]
    EP --> ES[Stripe一回購入 metadata.attribution_token]
    ES --> EW[署名検証済み・冪等なwebhook]
    EW --> ED[購入とPDF配信receipt]
    ED --> EM[同じtoken付きの任意購読CTAメール]
    EM -. 本人が選択 .-> LT[/letter または /tegami?utm_campaign=<token>]
    LT --> TS[14日trial subscription]
    TS --> PAY[初回 invoice.paid]
    PAY --> LR[active paid subscription MRR]
  end
  subgraph C[2. eBook初回receipt後にCapafy Instagram]
    CD[別担当が承認したCapafy skill] --> CS[公開中・利益のあるskill選定]
    CS --> CC[実際のlisting例を使った独自Reel]
    CI[所有と状態を確認した既存Capafy IG] --> CP[Postiz配信ownerを一つにする]
    CC --> CP
    CP --> CR[Postiz receiptと公開Reel URL]
    CR --> CT[ct=capafy-reel-slug]
    CT --> CO[Capafy有料注文receipt]
  end
  ES --> CFO[同一期間の返金・手数料・実費・出金・銀行着金readback]
  LR --> CFO
  CO --> CFO
  GATE[owner registry + 公式account状態 + 単一ownerのeffect fence] --> EA
  GATE --> CI
```

Letter subscription stateはStripeのevent到着順やFunction instanceのwall clockに依存させず、同一subscriptionのreadback generationをSupabaseが採番します。

```mermaid
sequenceDiagram
  autonumber
  participant Stripe
  participant Hook as Netlify webhook
  participant DB as Supabase
  Stripe->>Hook: 署名済みCheckout / subscription event
  Hook->>DB: reserve(subscription_id, email?, customer_id?)
  DB-->>Hook: subscriber_id + readback_generation
  Hook->>Stripe: GET current subscription
  Stripe-->>Hook: current status + immutable created
  Hook->>DB: apply(subscription_id, subscriber_id, generation, status, created)
  alt generation is current
    DB->>DB: state更新、全subscriptionからtierを集計
    DB->>DB: 保存済みstateの最大createdからpointerを再選出
    DB-->>Hook: applied
  else a newer readback was reserved
    DB-->>Hook: stale + current state
    Hook->>DB: Checkout receiptをretryable_failureへ
    Hook-->>Stripe: 5xxでCheckoutを再試行
  end
```

## 要件

1. Public page copy、registry、Stripe Price、locale route、checkout mode、PDF delivery が同じ商品内容を示す。
2. 既存`/go/<token>`→`utm_campaign` routeを使い、`attribution_token`をeBook checkout・Letter/Tegami checkout・Stripe metadata・buyer/subscriber receiptまで保持します。clickはpaid orderに数えません。
3. eBook配信メールの任意subscription CTAはlocaleに合った`/letter`または`/tegami`へ同じ`utm_campaign`を付けて案内します。本人がcheckoutしない限り購読を作りません。
4. webhook retryでbuyer entitlementやemail deliveryを二重計上しません。DB write/email failureは成功として隠しません。Resend idempotencyとdurable event/delivery receiptを併用し、unknown deliveryを無条件に再送しません。
5. eBook/Letter emailはverified senderを表す`RESEND_FROM_EMAIL`を必須とし、test-only domainへのfallbackを作りません。値が未設定ならprovider callなしでdelivery receiptを`retryable_failure`にし、`configure_verified_resend_sender`を記録します。
6. 同一subscriptionの状態は、Stripe GET前に予約したDB readback generationがapply時点でも最新の場合だけ更新します。古いgenerationのCheckoutはWelcomeを終端確定せず、receiptをretryableにして再試行します。
7. 既存`subscribers.stripe_subscription_id`をmigration時にstate mappingへseedし、subscription lifecycle eventが既存顧客で`mapping missing`にならないようにします。既存tierがpaidなら`legacy_paid_pending_readback`として保持し、Stripe公式readbackが来た時点で実statusへ置き換えます。pointerなしpaid rowは`stripe_legacy_paid_pending_readback`で保持し、未知の履歴を自動でexpiredにしません。
8. 購入者tierは同じsubscriberに紐づく全subscriptionのactive/trialing状態から集計します。一つを解約しても別の有効購読を失効させません。trialingはpaid MRRに数えません。
9. subscriberの単一互換pointerはStripe `Subscription.created`の最大stateへ収束します。legacy pointerのcreated timeが不明な間は保持し、同じsubscriptionの公式readback後に保存済みstate全体から再選出します。同じ秒はsubscription IDの辞書順で安定化します。
10. Life Managerのloop registryが配信scheduleとeffect fenceを所有し、同一Instagram accountをpublishするownerは常に一つにします。OpenClawと二重scheduleにしません。
11. 既存のユーザー所有accountのみ使い、registry identityとprovider公式good-standing readbackを一致させます。restrictionはofficial appeal/status flowで扱い、別accountで回避しません。
12. effect_unknownのpublish/retryは同一occurrenceのofficial provider readbackまで止めます。
13. Original/licensed contentとrequired AI disclosuresを使い、copy/research claimはpublic assetと一致させます。

## 一次資料

- checkout/PDF source: Daisuke134/anicca-products main, apps/landing
- existing campaign route: `apps/landing/netlify/functions/marketing-go.js`, `/go/<token>` → `utm_campaign`
- 実行順: Life Manager unified SSOT
- [Resend Send Email API idempotency](https://resend.com/docs/api-reference/emails/send-email)（keyの有効期間は24時間。長期dedupeはdurable receiptで行う）
- [TikTok Integrity and Authenticity](https://www.tiktok.com/community-guidelines/en/integrity-authenticity/)
- [Meta Spam Policy](https://transparency.meta.com/policies/community-standards/spam/)
- [Instagram disabled account help](https://help.instagram.com/366993040048856/)
