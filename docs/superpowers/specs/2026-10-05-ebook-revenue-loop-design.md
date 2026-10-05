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
- checkout attribution helper とStripe Checkout metadataはproduct PR #419（`a36098a209`）で実装済み。focused tests 7/7、telemetry suite 336/336 PASS。Next buildは`ENOSPC`で未確認、GitHub PRにbuild/deploy checkなし。Life Manager の marketing-engine/ebook_runner.py は receipt 付き render と awaiting_visual_approval の配信 intent を作りますが、Stripe 売上や公開投稿は行いません。
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

## 要件

1. Public page copy、registry、Stripe Price、locale route、checkout mode、PDF delivery が同じ商品内容を示す。
2. 既存`/go/<token>`→`utm_campaign` routeを使い、`attribution_token`をeBook checkout・Letter/Tegami checkout・Stripe metadata・buyer/subscriber receiptまで保持します。clickはpaid orderに数えません。
3. eBook配信メールの任意subscription CTAはlocaleに合った`/letter`または`/tegami`へ同じ`utm_campaign`を付けて案内します。本人がcheckoutしない限り購読を作りません。
4. webhook retryでbuyer entitlementやemail deliveryを二重計上しません。DB write/email failureは成功として隠しません。Resend idempotencyとdurable event/delivery receiptを併用し、unknown deliveryを無条件に再送しません。
5. MRRは`invoice.paid`とsubscription active状態の両方で数え、trialingは除外します。eBook gross、refund、fee、actual model cost、payout、bank receiptも分けます。
6. Life Managerのloop registryが配信scheduleとeffect fenceを所有し、同一Instagram accountをpublishするownerは常に一つにします。OpenClawと二重scheduleにしません。
7. 既存のユーザー所有accountのみ使い、registry identityとprovider公式good-standing readbackを一致させます。restrictionはofficial appeal/status flowで扱い、別accountで回避しません。
8. effect_unknownのpublish/retryは同一occurrenceのofficial provider readbackまで止めます。
9. Original/licensed contentとrequired AI disclosuresを使い、copy/research claimはpublic assetと一致させます。

## 一次資料

- checkout/PDF source: Daisuke134/anicca-products main, apps/landing
- existing campaign route: `apps/landing/netlify/functions/marketing-go.js`, `/go/<token>` → `utm_campaign`
- 実行順: Life Manager unified SSOT
- [Resend Send Email API idempotency](https://resend.com/docs/api-reference/emails/send-email)（keyの有効期間は24時間。長期dedupeはdurable receiptで行う）
- [TikTok Integrity and Authenticity](https://www.tiktok.com/community-guidelines/en/integrity-authenticity/)
- [Meta Spam Policy](https://transparency.meta.com/policies/community-standards/spam/)
- [Instagram disabled account help](https://help.instagram.com/366993040048856/)
