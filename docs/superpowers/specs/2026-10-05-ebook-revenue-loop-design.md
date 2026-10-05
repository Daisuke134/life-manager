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

## 現状（2026-10-06 04:15 JST Product PR readback / Capafy 04:06 JST runtime readback）

### eBook商品・売上経路

- anicca-products PR #419 はmain commit 6c52d4cc13へ統合済み。EN /monk $10.99、JA /achan ¥1,580のone-time checkout、/go token、checkout metadataの接続がある。/letter $9.99/月と/tegami ¥980/月は別のsubscription商品で14日trial後に請求する。
- PR #420はOPEN、head `85116e29aceb3d951e65f125fb3473fcb17d2b99`。signed webhook receipt、PDF retry fence、subscription generation/readback、legacy mapping、trial/paid-MRR分離、normalized-email shared RPC、verified sender、canonical base64url token checkを含む。Focused eBook/Writer/lead-magnet tests 31/31とwriter-entitlement 6/6、PostgreSQL 18.6 fixture、syntax/diff checksはPASS。Landing check `37356856068`はこのheadでSUCCESS。
- PR #420では同一normalized emailのlead-magnet signupとStripe reservationを共通RPCへ直列化し、existing Stripe mappingを優先する。既存行の`signed_up_at`を更新しないため、signup retryでduplicate-emailの選択対象を入れ替えない。PostgreSQL fixtureで、email UNIQUEなしの並行writerでもsubscriber rowが1件、duplicate legacy rowsでも既存subscription mappingを維持することを確認済み。
- Production provider metadata workflow `37353322073`はPASS。`buyers`/`subscribers`のOpenAPI columns/typesはmigrationと整合。email data scanは9 subscriber rows、9 normalized emails、duplicate groups 0、empty rows 0。`pg_indexes`とebook tables/RPCsはPostgRESTで非公開（PGRST205）。PR #420のsourceはemail unique indexの有無に依存せずshared RPCを使うため、email index追加はしない。Supabase CLIはproject ref未link、GitHub/Netlify環境にDB URLやSupabase management tokenはなく、SQL migrationは未適用。main pushは自動deployするため、DDL migrationとpost-migration table/RPC/schema-cache readbackまでPRをmergeしない。
- `RESEND_FROM_EMAIL`はproductionで設定済み、sender domainは`aniccaai.com`。このrunのResend API keyは`GET /domains`に401 `restricted_api_key`を返したため、domain statusはAPIで再確認できていない。過去のdashboard readbackではVerified。購入者へのemailはまだ送っていない。
- PR #420のsourceではlead-magnet.jsがshared normalized-email RPCを呼び、DB write成功後にだけ`RESEND_FROM_EMAIL`からDay-0 emailを送る。missing config/write/send failureをsuccessにせず、provider response bodyをcallerへ返さない。このsourceはまだproductionへdeployされていない。
- 同一occurrenceに結び付いた自然なpaid sessionと正しいPDF delivery receiptはまだ確認できていない。売上とsettlementはunknownであり、ゼロとは扱わない。

### eBook marketing

- Marketing Engineの`ebook_runner.py`はrender receiptとpublication intentを作るが、intentは`awaiting_visual_approval`で、live eBook publication ownerはloop registryにない。
- Cross-repo source contractはgolden vector `creative.contract.1`で固定した: EN `ee_hcp4v5pifa2ovj47rsir`、JA `ej_cs6k5hu42kvx65x66imw`。Life Managerの`stage_intents`からProduct `/go`, `utm_campaign`, Checkout metadata、webhook durable receipt、locale PDF payloadまで同じJP tokenを使うlocal integration probeがPASS（provider callsはfake、production effect 0）。PR #6704のLife Manager testはmainへmerge済み。Productの対応testsはPR #420 head `85116e29`にあり、PRはOPEN。
- 既存account registryでは`instagram.obou_anicca`のPostiz routeが`route_ready=true`と読み戻されている（02:15 JST）。これはroute設定の証拠であり、現アカウントの本人所有・good-standing・Instagram側の投稿receiptの証拠ではない。EN packはTikTokのみ、JA packはTikTokとInstagram integrationを登録している。pack登録だけではprovider login/statusを証明しない。

### Capafy Instagram marketing

- 03:42 JST `lm-loop status all --json`: old `capafy-ig-marketing-daily` is managed/loaded-idle at SHA `d091b3bd58aa5f27dbee19c2eab12311b3b0597e`; occurrence `capafy-ig-marketing-daily:18dbb45758667058-79255` is exit 75 / `host_admission_deferred:resource_effect_unknown`, with no provider receipt/readback. Active fence `18db7caff1178a88-68028` remains `no_pre_effect_terminal`; health is `safely_fenced`.
- New `life-manager-capafy-ig` is now returned as managed/loaded-idle at old SHA `4eb6bbbaeb9a8368895e6391e34e8c895908b0ec`; latest occurrence `life-manager-capafy-ig:18dbb4981f9573c8-86990` is exit 1 / `entrypoint_exit_1` / effect unknown / no receipt / `official_readback_required`. `pre-effect-reconcile --dry-run` returns `no_pre_effect_terminal`. The 02:20 `unmanaged_label` snapshot is superseded; neither owner has official readback, so do not repost from either lane.
- **04:06 JST refresh supersedes the 03:42 occurrence IDs above:** old `capafy-ig-marketing-daily` remains loaded-idle; current snapshot SHA is `a09d0ad40b4eddfcaa65ca03b9804604ba692557`, while latest scheduled occurrence `capafy-ig-marketing-daily:18dbb79dd35998c8-25553` used event SHA `d091b3bd58aa5f27dbee19c2eab12311b3b0597e` and exited 75 with `host_admission_deferred:resource_effect_unknown`. Its active fence `18db7caff1178a88-68028` is still unresolved; the adapter reports `active_ig_handle_unresolvable`, not a verified post. New `life-manager-capafy-ig` remains loaded-idle at SHA `4eb6bbbaeb9a8368895e6391e34e8c895908b0ec`; latest occurrence `life-manager-capafy-ig:18dbb7007d247380-97286` failed with `capafy ig reel loop requires node`, provider adapter state `adapter_not_run_yet`, no provider receipt/readback, and an active `effect_unknown` fence.
- The Node/Python launchd lookup repair is already in Life Manager main at commit `9e3fb448b6` (PR #6663), but the installed new-owner release is still `4eb6bbba`; a current immutable release has not been applied to that owner. The source comment also says `@capafy.hooklab` is not connected to Postiz and the integration ID is unset; verify the actual account and Postiz integration through official readback before planning a canary. These runtime errors do not establish that a CAPTCHA exists. No authenticated challenge screen was inspected during this readback.
- 現行sourceのowner pathは`config/loop-registry.json`の`life-manager-capafy-ig` → `apps/life-manager/scripts/capafy-ig-reel` → Postizで、effect reconcilerもPostiz post listingを公式receiptとして読む。entrypointは`LM_POSTIZ_API_KEY`と`CAPAFY_IG_POSTIZ_INTEGRATION_ID`を要求し、source commentは`@capafy.hooklab`がPostiz未接続としている。旧`capafy-ig-marketing-daily`は`instagrapi`経路。`capafy-marketing/SKILL.md`のB4 browser-direct推奨はそのskill directory内で未実装の設計メモであり、この現行Life Manager ownerのrouteではない。新laneのaccount/credential/post statusはprovider readbackで未確認なので、Postizとbrowser-direct/instagrapiを併用せず、D5で一つに収束させる。
- D5の既存正本は docs/superpowers/plans/2026-10-04-capafy-10k-mrr-recipe.md。「eBook first receipt後に開始」「両laneのeffectをreadback」「ownerを一つにする」「1日1回以下のcanary」「14日測定」を既に定義している。このspecではD5のTODOを複製しない。
- 2026-10-06 02:20 JSTのGitHub repository searchでは、最新のlocal/free-code候補は[fiptcha](https://github.com/figranium/fiptcha)（Apache-2.0、2026-10-05 16:42Z更新）。既存のactive Playwright-compatible `page`を受け取りbrowserを起動しない。reCAPTCHA v2 / hCaptcha / Turnstileに対応するが、dynamic 3x3 gridは不安定でdirect-CDP compatibilityは未検証。既存owner helper `skills/fundraiser-agent/runtime/solve-recaptcha-v2.py`は標準reCAPTCHA v2専用で、registered pageのtarget-id、widget site key/response textarea/callbackを必要とする。[Captcha Solver API Python SDK](https://github.com/captcha-solver-api/python-sdk)はrepository licenseがMITのSDKだが、外部API serviceの無料枠/価格はこの調査では確認していないため「無料solver」とは判定しない。Capafy runtime errorはCAPTCHAの証拠ではなく、このturnでは認証済みbrowser画面を未確認。実challengeが現れた場合だけchallenge typeを確認し、既存helperまたはregistered CDP sessionで互換確認できた手段を使う。identity/appeal/suspensionはsolverで回避しない。
- Capafyの既存landing redirectはInstagram bio clickを記録し、seller analyticsは注文・収益を集計する。1投稿ごとの注文IDが得られない期間の投稿→売上対応はcandidate attributionとして表示し、因果と断定しない。

## 現状のarchitecture

~~~mermaid
flowchart LR
  CONTENT["ebook source + verified claims"] --> ENGINE["Marketing Engine render receipt"]
  ENGINE --> INTENT["publication intent: awaiting_visual_approval"]
  INTENT -. "live eBook owner not registered" .-> STOP["no eBook post receipt"]
  TOKEN["ee_/ej_ campaign token"] --> GO["/go click receipt"]
  GO --> CHECKOUT["PR #419 checkout + Stripe metadata: main"]
  CHECKOUT --> WH["PR #420 webhook/PDF/shared subscriber RPC: source ready, not merged"]
  WH -. "production migration/schema cache absent" .-> NOORDER["no verified natural paid + PDF receipt"]
  OLD["Capafy old owner: active effect_unknown fence"] --> HOLD["no retry; provider readback missing"]
  NEW["Capafy new owner: managed, active effect_unknown, old installed SHA"] --> HOLD
~~~

## To-Be architecture

~~~mermaid
flowchart LR
  subgraph E["1. eBookを先に完走"]
    SRC["原文・検証済みclaim"] --> RENDER["Marketing Engine render receipt"]
    RENDER --> CAMP["creative id + ee_/ej_ campaign token"]
    CAMP --> OWNER["本人所有accountをregistry/providerで確認"]
    OWNER --> VISUAL["exact asset hash + existing visual approval"]
    VISUAL --> POST["単一のeBook publication owner"]
    POST --> PRECEIPT["Instagram/TikTok provider receipt"]
    PRECEIPT --> GO["/go/<token> click receipt"]
    GO --> PAGE["/monk または /achan"]
    PAGE --> CHECKOUT["Stripe one-time Checkout + attribution metadata"]
    CHECKOUT --> HOOK["署名検証 + durable webhook receipt"]
    HOOK --> BUYER["buyer/session receipt"]
    BUYER --> PDF["正しいlocaleのPDFをverified senderから納品"]
    MIG["PR #420 migration + RPC/ACL/schema-cache readback"] --> DEPLOY["merge + auto-deploy + deployed SHA/health readback"]
    DEPLOY --> CHECKOUT
    PDF --> OPTIONAL["任意のLetter/Tegami CTA"]
    OPTIONAL --> SUBCHECKOUT["本人が選択したsubscription Checkout"]
    SUBCHECKOUT --> TRIAL["14日trial / access state"]
    TRIAL --> PAID["invoice.paid + Stripe active readback"]
    PAID --> MRR["paid MRR receipt"]
  end
  subgraph C["2. 初回eBook paid + PDF receiptの後だけCapafy IG"]
    DEV["別担当が承認した公開listing"] --> DEMO["実物のlistingに沿う独自Reel"]
    DEMO --> CAPOWNER["life-manager-capafy-igの単一owner"]
    ACCOUNT["本人所有・公式statusとPostiz integration確認済みCapafy IG"] --> CAPOWNER
    FENCES["旧・新ownerのeffect_unknownを公式readbackで解消"] --> CAPOWNER
    RELEASE["Node/Python修正を含むmain由来immutable release"] --> CAPOWNER
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
