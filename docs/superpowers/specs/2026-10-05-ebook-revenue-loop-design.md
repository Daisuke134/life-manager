# Anicca eBook Revenue Loop — Design

> この設計文書は商品・配布間の契約を定めます。全体の実行順と現在cursorの正本は Life Manager unified SSOT です。

## 成果

1. eBookを既存の自社アカウントで配信し、最初の自然な有料Stripe注文と正しいlocaleのPDF納品を同一campaignに結び付ける。
2. Letter/Tegamiの有料subscriptionだけをMRRに数える。trialやeBook一回購入はMRRではない。
3. その最初のeBook注文・PDF receipt後に、Capafy Instagram marketingだけを開始する。Capafyの商品、listing、account lifecycleの開発は別担当の所有範囲に置く。
4. eBookの14日間readbackはCapafy開始後も継続し、後続の収益作業を止めない。

## 範囲と担当

- eBook checkout/webhook/PDF fulfillmentは anicca-products の既存Stripe・Netlify・Supabase・Resend経路を使う。
- eBookとCapafyのcreative・投稿ownerはLife Managerの既存Marketing Engine、account registry、publication adapterへ接続する。OpenClawにschedulerを追加しない。
- eBook marketingは既存の本人所有Instagram/TikTok accountだけを使う。registryとprovider readbackでidentity・good-standingを確認できないaccountは使わず、代替accountも作らない。
- Capafyは既存の life-manager-capafy-ig Postiz laneを唯一のpublish ownerにする。Capafy product code・価格・listing・account lifecycleは変更しない。
- Daisが直接編集したcopyや投稿を、確認なく書き換え・公開しない。通常の技術判断やloop内部のmarketing creativeは既存ownerの権限内で進める。

## 現状（2026-10-06に確認した証拠）

### eBook商品・売上経路

- anicca-products PR #419 はmain commit 6c52d4cc13へ統合済み。EN /monk $10.99、JA /achan ¥1,580のone-time checkout、/go token、checkout metadataの接続がある。/letter $9.99/月と/tegami ¥980/月は別のsubscription商品で14日trial後に請求する。
- PR #420はOPEN。最新head bc34edb14bでは、signature-verified webhook receipt、PDF delivery retry fence、Stripe subscription readback generation、legacy subscriber mapping、trialとpaid MRRの分離、必須RESEND_FROM_EMAILを実装済み。eBook/Writer 27/27、telemetry 358/358、PostgreSQL 18 fixture、source reviewはPASS。head bc34のLanding PR check run 37339391128はPASS。
- PR #420のPostgreSQL fixtureはemail UNIQUEなしでも、同一正規化emailの2つの購読予約を1 subscriber rowへ収束させる。独立reviewもこの差分をPASSした。ただしこれは同じRPCへ来るwriter間の直列化で、lead-magnet.jsの別writerはまだadvisory lockを使わない。
- Production PostgREST readbackでbuyersとsubscribersの列型は確認済み。buyersはuuid/text/integer/timestamptz、subscribersはuuid/text/timestamptzを使う。unique index・constraintはPostgRESTから確認できていない。ebook_webhook_receiptsは未作成（PGRST205）。SQL adminでのmigration適用とschema-cache/RPC readbackは未完了。
- ProductionのRESEND_FROM_EMAIL設定は存在し、送信元domain aniccaai.comはResend dashboardでVerifiedを確認済み。Resend API keyはGET /domainsを許可しないため、API経由のdomain readbackではない。購入者へのemailはまだ送っていない。
- lead-magnet.jsはsubscribersへ直接PostgREST POSTし、成功状態を検査せず、Day-0 emailにはonboarding@resend.devを固定使用する。登録制約とproduction send readinessを解決してから大規模なlead acquisitionに使う。
- 同一occurrenceに結び付いた自然なpaid sessionと正しいPDF delivery receiptはまだ確認できていない。売上とsettlementはunknownであり、ゼロとは扱わない。

### eBook marketing

- Marketing Engineのebook_runner.pyはrender receiptとpublication intentを作るが、intentはawaiting_visual_approvalで、live publication ownerはloop registryにない。
- attribution.pyはebook-ja/enのee_/ej_ tokenを生成する。anicca-productsの/go endpointは同形式を受け付け、marketing_click_receiptsへ記録して/achan・/monkへutm_campaignを渡す。checkout metadataへのpropagationはPR #419にある。renderからpaid order receiptまでを結ぶcross-repo contract/readbackは未完了。
- 現行EN packはTikTok accountのみを登録し、Instagramをsetup_requiredとしている。JA packはTikTokとInstagram integrationを登録している。pack登録はprovider login、本人所有、good-standingの証拠ではない。

### Capafy Instagram marketing

- 現行runtime readback（2026-10-06 01:25 JST）では、旧capafy-ig-marketing-dailyと新life-manager-capafy-igがともにloaded-idleだが、両方にactive effect_unknown fenceが残りprovider receiptはない。旧ownerのactive fenceはcapafy-ig-marketing-daily:18db7caff1178a88-68028（no_pre_effect_terminal）、新ownerの最新occurrence/fenceはlife-manager-capafy-ig:18dbad480e76aff0-21015（entrypoint_exit_1、no_pre_effect_terminal）。新ownerのinstalled SHAは4eb6bbbaで、mainのruntime/effect-reconcile source fixは未反映。旧ownerは28c09277。公式readbackで両effectを閉じ、account identity/statusを確認して一つのownerにするまで公開しない。D5の原子的TODOはdocs/superpowers/plans/2026-10-04-capafy-10k-mrr-recipe.mdを参照する。
- D5の既存正本は docs/superpowers/plans/2026-10-04-capafy-10k-mrr-recipe.md。「eBook first receipt後に開始」「両laneのeffectをreadback」「ownerを一つにする」「1日1回以下のcanary」「14日測定」を既に定義している。このspecではD5のTODOを複製しない。
- CAPTCHA候補をGitHub一次資料で調査した。最近更新された[fiptcha](https://github.com/figranium/fiptcha) (Apache-2.0, 2026-10-05更新)はreCAPTCHA v2 / hCaptcha / Turnstile用のlocal solverで、browserを起動せず既存Playwright-compatible pageを受け取る。Dynamic 3x3 gridは不安定で、registered direct-CDP sessionとの互換性は未検証。DataDome/GeeTestは対象外。[aster-go/Datadome-GeeTest-Captcha-Solver](https://github.com/aster-go/Datadome-GeeTest-Captcha-Solver)はMITだがGeeTest puzzle位置を計算するだけでproviderへchallengeを完了しない。[CapSkip Python SDK](https://github.com/capskip/capskip-python)はMITだが有料desktop appが必要。現行Capafy statusのentrypoint_exit_1/resource_effect_unknownはCAPTCHA表示の証拠ではないため、実画面のchallenge typeを確認する前にsolverを導入・実行しない。
- Capafyの既存landing redirectはInstagram bio clickを記録し、seller analyticsは注文・収益を集計する。1投稿ごとの注文IDが得られない期間の投稿→売上対応はcandidate attributionとして表示し、因果と断定しない。

## 理想の構成

~~~mermaid
flowchart LR
  subgraph E["1. eBookを先に完走"]
    SRC["原文・検証済みclaim"] --> RENDER["Marketing Engine render receipt"]
    RENDER --> CAMP["creative id + ee_/ej_ campaign token"]
    CAMP --> OWNER["本人所有accountをregistry/providerで確認"]
    OWNER --> POST["単一のeBook publication owner"]
    POST --> PRECEIPT["Instagram/TikTok provider receipt"]
    PRECEIPT --> GO["/go/<token> click receipt"]
    GO --> PAGE["/monk または /achan"]
    PAGE --> CHECKOUT["Stripe one-time Checkout + attribution metadata"]
    CHECKOUT --> HOOK["署名検証 + durable webhook receipt"]
    HOOK --> BUYER["buyer/session receipt"]
    BUYER --> PDF["正しいlocaleのPDFをverified senderから納品"]
    PDF --> OPTIONAL["任意のLetter/Tegami CTA"]
    OPTIONAL --> SUBCHECKOUT["本人が選択したsubscription Checkout"]
    SUBCHECKOUT --> TRIAL["14日trial / access state"]
    TRIAL --> PAID["invoice.paid + Stripe active readback"]
    PAID --> MRR["paid MRR receipt"]
  end
  subgraph C["2. 初回eBook paid + PDF receiptの後だけCapafy IG"]
    DEV["別担当が承認した公開listing"] --> DEMO["実物のlistingに沿う独自Reel"]
    DEMO --> CAPOWNER["life-manager-capafy-igの単一owner"]
    ACCOUNT["本人所有・公式status確認済みCapafy IG"] --> CAPOWNER
    CAPOWNER --> CAPPOST["Postiz/Instagram receipt + public Reel URL"]
    CAPPOST --> CTA["Capafy listingへct campaign link"]
    CTA --> ORDERS["Capafy order/fee/refund/payout readback"]
  end
  MRR --> CFO["既存CFO: period・currency・cost・settlementを照合"]
  ORDERS --> CFO
  GATE["account identity + good standing + effect_unknown解消"] --> OWNER
  GATE --> ACCOUNT
  PAID -->|first paid + matching PDF receipt| DEMO
~~~

同じsubscriberに複数のStripe subscriptionを持てるようにし、古いeventの到着順でaccess stateを戻さない。

~~~mermaid
sequenceDiagram
  autonumber
  participant Stripe
  participant Hook as Netlify webhook
  participant DB as Supabase
  Stripe->>Hook: signed Checkout/subscription event
  Hook->>DB: reserve subscription readback generation
  DB-->>Hook: subscriber id + generation
  Hook->>Stripe: GET current subscription
  Stripe-->>Hook: status + immutable Subscription.created
  Hook->>DB: apply only when generation is still current
  alt generation is current
    DB->>DB: aggregate access across mapped subscriptions
    DB->>DB: choose newest created subscription pointer
    DB-->>Hook: applied; record payment/delivery state
  else newer readback has started
    DB-->>Hook: stale
    Hook->>DB: keep Checkout receipt retryable
  end
~~~

## 受入契約

1. /go/<token>のclick receipt、checkout metadata、buyer/subscriber receiptが同じproduct・locale・campaign tokenを持つ。click・view・renderはsaleではない。
2. one-time paymentの署名済みCheckoutだけでbuyer/PDF fulfillmentを行い、同じStripe sessionのretryで購入receiptやemailを重複作成しない。
3. ResendにはverifiedのRESEND_FROM_EMAILだけを渡す。設定不足やDB失敗は成功にせず、durable retry/fenceを残す。
4. Letter/TegamiのsubscriptionはDB generationをStripe GET前に予約し、最新generationだけを適用する。trial/accessはpaid MRRと区別する。MRRは初回invoice.paidとactive paid stateを確認して数える。
5. subscribersのemail一意性をproduction schemaで確認する。unique constraintが無ければ、lead-magnetとStripe webhookの全subscriber writerを同じDB-owned normalized-email upsert/lockへ寄せてからtrafficを拡大する。
6. lead-magnetのDay-0 senderもverified production senderを使い、subscriber writeの失敗を見てから送信する。無料signupをpaid subscriber/MRRとして数えない。
7. distributionは既存ownerとprovider receiptを使い、effect_unknown occurrenceをreadbackなしに再送しない。1 accountにpublish ownerは一つだけ。
8. 既存の本人所有accountと公開statusを照合する。challenge_requiredの場合はchallenge typeを実画面で確認し、既存の認証済みchallenge pathだけを使って、解決後に期待accountとprovider stateまでreadbackする。identity/appeal/suspensionはCAPTCHA solverで回避しない。
9. Capafy marketingは公開中listingと実際の入出力に基づくoriginal Reelを使う。product/listing/account lifecycle codeは別担当の所有に残す。
10. Capafyのct click、売上、refund、fee、実費、payout、bank receiptを分ける。providerがpost単位注文を返さない場合はcampaign-level correlationと明記し、銀行着金なしにnet contributionを確定しない。

## 数値の意味

- $9.99/monthで$10,000 gross MRRに必要な有料active subscriptionは1,002件。fees・refunds・cost前の算数であり、実測や予測ではない。
- $10.99のebook saleは一回売上で、subscription MRRではない。
- Capafyの$10,000は既存CFO定義の同一30日窓banked net contributionと、portfolio計画のchannel allocationを整合させてから測る。seller balanceやviewsを銀行着金とみなさない。

## 正本

- checkout/webhook/PDF implementation: anicca-products PR #419/#420
- eBook/Capafy marketing execution order and cursor: docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md
- eBook implementation tasks: docs/superpowers/plans/2026-10-05-ebook-revenue-loop.md
- Capafy Instagram D5 marketing tasks: docs/superpowers/plans/2026-10-04-capafy-10k-mrr-recipe.md
- Capafy product development cursor: the separate owner's canonical project plan
