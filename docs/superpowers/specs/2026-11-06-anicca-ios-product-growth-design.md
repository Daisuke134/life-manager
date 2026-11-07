# Anicca iOS — 初回改善から全アプリの継続成長までの仕様

## 正本・今回の境界

目的は、英語市場を中心にAniccaの獲得・初回価値体験・課金・継続を改善し、配信から製品へ学習が戻る運営を作ること。世界最大・$10K MRRは目標であり、達成済みの事実や今回リリースの保証とは扱わない。

**順序・TODO・状態の唯一の正本:** [統合SSOTの ANICCA-PRODUCT-GROWTH](2026-09-25-life-manager-unified-ssot.md#anicca-product-growth--ios初回改善から全アプリ継続改善まで)。この文書は詳細な要求・契約、[実装計画](../plans/2026-11-06-anicca-ios-product-growth.md)は実行手順。進捗を別台帳へ二重管理しない。

G2（swipe戻り・通知本文/遷移・Free/Pro通知設定）は完了。現在の実行順は**G4（Mixpanel一本化・全画面計測の実受信確認）→G4.1（Anicca計測を既存Openへ表示）→G5（build 820の全体Maestro動画、TestFlight失敗と審査中buildの整理、全受入条件後にASC CLIで提出）**。ASC公式readbackでは1.9.8 submissionは`WAITING_FOR_REVIEW`、latest build 820は`VALID`。Xcode Cloud run #820はArchive成功だがTestFlight External TestingがAppleのbeta review submission failureで失敗した。画面別の実数はOpen側で`missing_service_account`。画面離脱、Mixpanel実受信、Open集計、build 820の全体E2E動画が未実証のため、追加提出はしない。build 820動画はG5のリリース受入条件であり、G2を未完へ戻すものではない。G6/G7の全アプリ計測拡張とG8〜G10の自動改善/他アプリ展開は後続として保持する。

## 出所と現在の観測

コード正本は `Daisuke134/life-manager` の `apps/mobile/anicca-ios`。current main=`d567f6b6d211c4a4d8f38ad1b8b98c6774088a2e`。PR #9289 merge SHA `1555a020ece274ee68bc2587d161f44f019e1ac4`はMixpanel一本化・18画面tracking、purchase dedupを含み、Xcode Cloud run #820/build 820のsource。PR #9305はIntel x86_64 Security Scan jobを削除してarm64のみへ絞り、14 checks PASSでmain統合済み。OpenのHTML/静的公開物は`Daisuke134/anicca-products`が所有し、PR #905統合後のmain=`6aea3804295aea27addab0f3c81582fc56c16587`。

| 対象 | 観測した事実 | 未確認・注意 |
|---|---|---|
| Apple | App=`6755129214`、bundle=`ai.anicca.app.ios`。ASC latest 1.9.8 build 820=`VALID`、App Store submission `9fa35898-1eee-44ce-942b-630780d9133b`=`WAITING_FOR_REVIEW`、`inFlight=true`（CLI readback 2026-11-07 22:15 JST） | Xcode Cloud run #820はArchive成功、TestFlight External Testing actionは`Beta app review submission failed (Please try again later.)`で失敗。build 820の同一build E2E動画は未作成。既存審査中submissionを重複作成しない |
| 計測 | PR #9289のsource/build 820ではMixpanel Swift 7.1.0一本、PostHog経路を外し、18 screen IDとScreenVisitLedger、purchase dedupを実装。 | **選定はMixpanel一本**。コードはmainにあるが、production Mixpanelの実receipt・identity/property・重複0・screen-level funnelは未確認。build 818は旧sourceで両SDKと一部`screen_viewed`を含む |
| Onboarding | 9つの列挙stepと別の2段paywallが存在 | コメントの「10/20-step」と実際の画面数を混同しない |
| 課金 | 閉じると無料利用へ進めるsoft paywall。`variant: "b"` 呼び出し | フラグの存在だけでA/B稼働としない |
| 価格 | 事前調査の米国公開IAP一覧は月$14.99・年$59.99・買切$59.99。週$6.99も登録 | 公開一覧・現行Offering・対象国・無料体験資格を別に照合。モック値を本番へ固定しない |
| フィード | 縦 `UIPageViewController`、固定カタログEN/JA/ES各200件、8背景、いいねはローカル保存 | swipeの戻りはユーザー報告。原因未確定、端末・操作条件・実版で再現する |
| 通知 | APNs起動処理、通知本文/IDの遷移coordinator、cold-start保留処理と既存回帰が存在 | 1.9.6の公開履歴にも同文言修正あり。再現確認なく同じ修正を作り直さない |
| 設定 | 現在の `ReminderSchedule.slots(isPro:)` はFree 09:00/14:00/20:00、Pro 08:00/12:30/17:30/21:30を表示し、端末タイムゾーンも表示する。APNs token登録ではtimezone/langを送る。`Daisuke134/anicca-products` の確認済み `origin/main` (`0f2cd20b`) のaffirmation senderも同じFree/Pro枠を定義し、remote APNsを単一送信元として記述する | ソース上の予定時刻は一致。稼働中deploymentのcommit/readback、実端末APNs、Free/Pro実配信、登録/送信receiptは未確認 |
| 売上計測 | build 818の購入eventは`displayed_price`を`amount_source=store_product_quote_not_settled_revenue`として送る。transaction IDはローカルledgerで重複観測を抑止 | 表示価格は決済済み収益ではない。RevenueCat/Apple receipt・renewal・refund・proceedsの公式照合、restore結果event、service側重複0は未確認 |
| Open | PR #904でMixpanel collector・screen table・validator、PR #905でmissing-credential fail-safeを実装してmainへ統合。#905のlocal 41/41とLanding CI 2/2がPASS。main deploy run `42361224893`もSUCCESS | 2026-11-07 22:15 JSTの公開JSON readbackではtop-level `updated_at=2026-11-07 21:37 JST`、Anicca `observed_at=2026-11-07T13:15:33.369Z`。`status=unavailable`, `error_code=missing_service_account`、`screens=[]`, `breakdowns=[]`。画面別実数はunknownで0ではない。`updated_at`と`observed_at`の時刻差は要確認 |
| 継続処理 | Life Managerの`marketing-product-summary.js`はproduct-pack内のactivation/retention観測JSONを読む | G4.1 collectorはOpen ownerのanicca-products側に実装中。実データ取得・snapshot・公開deployを別々にreadbackする |

公開feedの観測例: `https://aniccaai.com/open/data.json` の期間10/29〜11/04、Aniccaは新規3件、JP2/CO1、取得行はApp Store検索。download coverageは7日中4日。米国0・SNS0や「全期間3件」とは断定しない。取得期間と欠測を保持し、別collectorの「行無し→0」と不整合があれば集計境界を直す。

2026-11-07 G4.1取得経路と認証preflightの過去確認（18:37 JST）: repository secret名`MIXPANEL_SERVICE_ACCOUNT`は存在（GitHub上の最終更新表示2026-05-24）し、main workflowも`${{ secrets.MIXPANEL_SERVICE_ACCOUNT }}`をcollector stepへ渡す。値はGitHubから再表示できないが、main run `42359464576`ではcollectorが有効値を受け取らず、Mixpanel Raw Event Export APIを呼ぶ前に停止した。値が空か、実行時に使えない理由まではreadbackできていない。repo vars `MIXPANEL_PROJECT_ID=3970220`、`MIXPANEL_SERVER=data`は設定済み。Mixpanel Export service accountはcredential SSOTに未登録。接続済みGoogle profileはowner-authorized Google credential rowと一致したが、それはGoogle account identityの確認だけでMixpanel project accessの証明ではない。registered browser registryにMixpanel routeはなく、`interactive:dais` CDPは到達不能・leaseなし。当時は開いているChromeがClaude認証フローと多数のタブを表示していたため、認証操作はしていない。既存Anicca projectへ登録済み専用routeでログインし、project/regionと既存Export service accountを確認する必要がある。Mixpanel公式Raw Event Export APIはBasic Authorizationを要求する（[公式API資料](https://developer.mixpanel.com/reference/raw-event-export)）。PR #904はmainへ統合済み。PR #905 (`713868cae19038e12590050919c5b17696905077`)はmissing credentialを`unavailable`/unknownとして扱うfail-safeを追加し、local 41/41・Landing CI 2/2 PASS後にmain commit `6aea3804295aea27addab0f3c81582fc56c16587`へ統合。main deploy run `42361224893`はSUCCESSし、公開feed `https://aniccaai.com/open/data.json`を`2026-11-07 18:37 JST`でreadback。Aniccaは`status=unavailable`, `error_code=missing_service_account`, 空screen/breakdownsであり、実Export API request/receiptはない。実データ受信、preview/liveの数値照合、hydrated dashboardの実表示確認までG4.1を完了扱いしない。

### G4.1 取得・認証の実測

Mixpanel公式GitHubの[`mixpanel-headless`](https://github.com/mixpanel/mixpanel-headless)を発見し、`uvx --from mixpanel-headless mp --version`で`0.4.0`を実行した。公式QuickstartはユーザーOAuth（PKCE）とservice accountの両方を案内する。初回`mp login --no-browser`はPTYなしで起動したためstdinが閉じ、`OAUTH_PASTE_ERROR: Empty paste`で終了。PTY付きで再起動した現在のCLIは`127.0.0.1:19284`でLISTENし、OAuth callbackを待受中。`mp session`はAccount/Project none、`mp inspect events --format json`は`No account configured`で、認証・数値取得は未完了。URL/PKCE stateはrepoへ保存しない。OAuth tokenが生成された場合はcredential SSOTへ直ちに保管し、CLI既定`~/.mp/accounts/{name}/tokens.json`の重複を除く。公式GitHub組織内で公式MCPは見つからず、現セッションに呼出可能なMixpanel MCP/connectorもない。

GitHub Actions run [`42365669499`](https://github.com/Daisuke134/anicca-products/actions/runs/42365669499) の`Collect Anicca Mixpanel screen funnel` stepでは、`MIXPANEL_PROJECT_ID=3970220`、`MIXPANEL_SERVER=data`に対し`MIXPANEL_SERVICE_ACCOUNT`のruntime値が空で、ログは`unavailable (missing_service_account); no export request was made`と記録した。workflowは同secretをstep envへ渡す設定で、GitHub secret名自体は存在するが、secret値はproviderから再表示できない。よって確定した直接原因はcollectorへの空env、secret保存値が空になった理由は未確定。公開feedの最新readbackは`updated_at=2026-11-07 20:37 JST`、`observed_at=2026-11-07T11:46:20.291Z`、`unavailable/missing_service_account`、空screens/breakdowns。これは欠測であり、実測0ではない。

**直近readback（2026-11-07 22:15 JST）:** `uvx --from mixpanel-headless mp session`はAccount/Project none。OAuth callback `127.0.0.1:19284`はLISTENしておらず、登録済みGoogle browser route `interactive:dais`は`reachable=false`。現Codex sessionはMixpanelへログインしておらずevent数値を取得していない。Open `https://aniccaai.com/open/data.json`ではtop-level `updated_at=2026-11-07 21:37 JST`、`product_analytics.anicca_ios`はsource `Mixpanel Raw Event Export API`、`observed_at=2026-11-07T13:15:33.369Z`、`status=unavailable`、`error_code=missing_service_account`、`screens=[]`、`breakdowns=[]`。`updated_at`と`observed_at`の時刻順も一致していないため、collectorの鮮度表示を実データ取得後に照合する。画面数値はunknownであり0ではない。Open collectorへ実効Export認証を渡し、Mixpanel実event receipt→Open集計/分母/期間/成熟窓/privacy/hydrated UIを照合する。

### G5 現在のApp Store Connect readback（2026-11-07 22:15 JST）

ASC CLI公式readback: App `6755129214`のlatest 1.9.8 build 820（ID `7ea0e0e5-6b3d-4b9e-ba87-299736144571`）=`VALID`、App Store version 1.9.8=`WAITING_FOR_REVIEW`、submission `9fa35898-1eee-44ce-942b-630780d9133b`=`WAITING_FOR_REVIEW`、`inFlight=true`、blocking issues 0。Xcode Cloud run #820（source `1555a020ece274ee68bc2587d161f44f019e1ac4`）のArchive actionは成功しbuild 820がASCでVALIDになった。一方、TestFlight External Testing actionは`Beta app review submission failed (Please try again later.)`で失敗した。これはArchive/build validationの失敗ではない。App Store review submissionがどのbuildを参照しているかは、このreadback単体では断定しない。G4/G4.1とbuild 820の同一candidate E2E/videoが未完了なので別submissionは作成しない。

## 1.9.7 / 1.9.8 のAs-Is

| 版 | build/source | 含まれる変更 | 現在の状態 |
|---|---|---|---|
| 1.9.7 | 816、source `9cc3d6e1bee952fa3f73659cc28c48529b1e2ca3`、PR #9272 | 初回目的選択→最初のaffirmation→任意通知→soft paywall、affirmation catalog/保存/like/推薦、swipe/通知遷移と一部画面/購入event | 旧提出は取り下げ済み。現行App Store version recordは1.9.8へ更新済み |
| 1.9.8 | build 818 source `6cc7c4a777be017e2d1ed4c50c439e02c2375d2e`（PR #9282）; build 820 source `1555a020ece274ee68bc2587d161f44f019e1ac4`（PR #9289） | build 818: notification text fix. build 820: prior changes plus Mixpanel-only 18-screen analytics and purchase dedup | ASC latest build 820=`VALID`; App Store submission `9fa35898-1eee-44ce-942b-630780d9133b` remains `WAITING_FOR_REVIEW`/`inFlight=true`. Xcode Cloud TestFlight External Testing failed; same-build E2E/video not done |

build 820はscreen-level analyticsがMixpanelで受信されたこと、全画面の離脱率、MixpanelからOpenへのfunnel、paid restore event、同一buildのE2E動画をまだ証明しない。限定公開動画3本（うち1本は6-flow E2E）はSimulator build 819の録画であり、build 820とのsource/build一致は未証明。

## 勝ち筋の参照と採用範囲

| 一次資料 | 観測・模倣する仕組み | 当社で測る指標 |
|---|---|---|
| [Monkey Taps](https://monkeytaps.app/) / [I am](https://iamaffirmations.app/) | 運営元はI amの年600万downloadを自己申告。カテゴリ・テーマ・reminderによる日常の価値体験 | 初回文言表示までの時間、保存、通知からの再訪、D7継続 |
| [TikTokのMonkey Taps事例](https://ads.tiktok.com/business/es/inspiration/monkeytaps) | 複数creativeを試し、Start Trialまで最適化。有料広告の事例 | 当社の無料配信では到達→クリック→install→trial/paid。広告の成果を無料配信へ外挿しない |
| [RevenueCat調査](https://www.revenuecat.com/state-of-subscription-apps-2026/) | 初回価値体験、地域別比較、売上/インストール、課金と継続の両方を見る | 英語圏別RPI、課金率、成熟コホート継続、返金 |
| [Mixpanel Swift SDK](https://docs.mixpanel.com/docs/tracking-methods/sdks/swift) / [Feature Flags and Experiments](https://docs.mixpanel.com/docs/experiments) | 既存event historyを保ったまま一つのSDKで計測・割付・露出・実験結果を読む | 割付整合、露出人数、主指標とguardrail |
| [RevenueCat Experiments](https://www.revenuecat.com/docs/tools/experiments-v1) | Offering/価格/提示を比較する既製機能。現行契約で利用できるか確認 | 価格別net RPI、refund/renewal。利用料・無料枠は導入前に再確認 |

勝者の構造を当社の素材・事実へ置き換える。競合の文章・画像・商標、裏付けのない健康効果、捏造social proofは流用しない。公開download・ratings・自己申告売上とverified profitを区別する。特定onboardingの因果効果を証明する同条件の資料が無い箇所は、**当社仮説**として小さく検証する。

## G1 — 初回利用・onboarding・課金画面

対象は英語市場を主軸にし、現行対応言語の操作・購入を壊さない。新規状態は隔離simulator/Sandboxで作り、Daisの本番契約や既存ユーザーデータをresetしない。

新規flowは「目的選択 → 関連する言葉を読む/保存 → reminderの説明/任意設定 → Proの実価値と価格 → 購入または無料feed」。最初の言葉を読むまでにaccount作成・通知許可・不要な質問・待ち時間演出を挟まない。冗長な比較/processing画面は現在の契約を確認して整理する。通知拒否でも進める。途中復帰は有効なstepへ戻り、既存の完了/有料ユーザーへ初回質問を再強制しない。

feedは全文を中心にし、保存・共有・カテゴリ・背景・reminderを読みやすい位置に置く。大きい文字、VoiceOver、Reduce Motionを確認する。背景は既存素材とnative表現を先に再利用する。動画背景の追加を今回の必須条件にはしない。

soft paywallを初回版の基準にする。閉じる・無料継続・復元・規約/Privacyへの導線、総請求額・請求周期・更新・無料体験資格を正確に表示する。国/通貨が変わる場合は最新StoreKitとOfferingを再取得し、不一致商品を購入できない。買切をMRRや自動更新契約として数えない。既存購入者の権限を維持する。

Pro特典・free/proの通知上限は、実際に権限で分かれる動作を調べて文言へ反映する。mockにある「全カテゴリ」「テーマ」等は未確定の表示案であり、未実装特典の販売・独断のfree機能削除を許可しない。価格変更・hard paywall・trial変更はG8で別実験とする。

## G2 — swipeと通知を確実にする（完了）

**完了:** PR #9272のswipe戻り、通知本文/遷移、Free/Pro通知設定のsource修正とSimulator回帰・通知routing確認を完了した。実端末APNs試験はスコープ外。build 820の全画面E2E動画はG5の提出前検証として残るが、G2の実装完了を取り消す条件ではない。

swipeはユーザー報告の約10回に1回の戻りを、連続上下・短/長/高速操作・逆方向・保存/テーマ更新・通知遷移の重なりで再現する。pagerの対話遷移とprogrammatic更新、index、catalog mutation、hosting stateを観測して根本原因を限定する。完了したswipeの後に古いindexへ戻らず、隣の全文を一度だけ表示する。短く戻す意図的gesture cancellationは不具合と数えない。

通知は、タップされた本文を表示の根拠とし、安定した `quote_id` と本文・言語・catalog version・notification IDを照合する。catalog照合で大文字小文字や空白を正規化しても、表示文字列は受信した `alertBody` を保つ。未知ID・欠落ID・本文のみ・古いcatalog・同じ通知の再tapでも別文言へ置換しない。payload不正で空なら無関係なquoteへ飛ばさず通常feedへ戻す。アプリ終了/背景/前面、onboarding中、catalog準備前で要求を保持し、準備後に一度だけ解決する。

配信の現在owner・caller・APNs token・timezone・時刻選択・authorization・有料権限・配信receiptを調べ、予定件数と実件数を分ける。設定の固定4件を実設定へ接続する。ローカル通知かremoteかは既存設計で毎日安定供給できる最小案を採り、同じoccurrenceを二重配信しない。OS通知許可、端末offline、Focus等のため「必ず毎日表示」を保証しない。APNs受付は端末表示・開封の証拠ではない。

### 配信経路の実確認による決定

Railway公式readbackで本番APIは `Daisuke134/anicca-products` / `apps/api`、deployment `a4699e00-907b-45be-8d8a-3a46fba90282` / commit `4e7885b` を確認する。同commitのsenderはfree=`09:00/14:00/20:00`、Pro=`08:00/12:30/17:30/21:30`（登録timezone）。今回のアプリはこれを予定として表示し、OS許可と配信済み件数を区別する。iOSの既存時間帯選択は保存されず、現在のAPIに任意時刻変更の接続がないため、反映されない選択を除いて予定確認＋任意通知許可にする。任意時刻の編集を提供する際はbackend契約も変更する。remote-onlyを維持し、二重local配信を追加しない。別repoの稼働backendや既存cronはこのUI修正で置換しない。

通知解決後、同じquote IDが現在のpersonalized feedにある場合は、その既存要素も受信 `alertBody` を保持する解決済みquoteで置き換えてから遷移する。Coordinatorの戻り値だけでなく、Feedカードの実表示文字列を受け入れ対象にする。

## G3 — 文言・いいね・個人化

既存200件/言語を無条件に捨てない。英語は初回版の暫定受入目標を**重複しない600件以上、12カテゴリ以上**とし、数量目標は業界の最適値とは主張しない。カテゴリ・タグ・出所/編集version・言語をstable IDへ結び、意味の重複・不自然な英語・危険な断定を確認する。JA/ESは利用可能な文言を維持し、未翻訳文を翻訳済みとして数えない。

目的選択を最初の推薦へ反映する。いいねは保存と次の推薦候補のカテゴリ重みに反映し、既に見ているページや次ページの内容をgesture中に並べ替えない。最近の20件は十分な候補があれば再表示を避け、探索候補も残す。カテゴリ変更、好みのreset、少数catalog、全件閲覧済みでも空feedにしない。個人化はまず既存モデル/ローカル規則を使い、新しいML基盤を作らない。

通知から受け取ったcatalog外文言も保存後に読める。like解除は保存と推薦重みへ反映し、他の保存内容を消さない。onboarding目的・表示・like・notificationのIDを揃える。健康・悩みの自由入力や本文を無差別に分析/リプレイへ送らない。

## G4 — Mixpanel一本の画面別プロダクト計測

### 選択する分析基盤

**Mixpanelだけをプロダクト行動分析の正本にする。** build 818の既存`AnalyticsManager.swift`はMixpanel送信を実装済みで、PostHogは設定次第で同じeventを受け取り、paywallでは直接PostHog captureも行う。二重経路を残すとevent数・ID・実験割当が二つの画面へ分かれ、離脱率や売上の比較を一つの答えにできない。既存のMixpanel event historyを保つ方が移行と照合が小さいため、PostHog SDK/設定/直接呼出しを除去し、実験もMixpanel Feature Flags/Experimentsへ寄せる。

根拠は公式[Mixpanel Swift SDK](https://docs.mixpanel.com/docs/tracking-methods/sdks/swift)、[iOS Feature Flags](https://docs.mixpanel.com/docs/tracking-methods/sdks/swift/swift-flags)、[Experiments](https://docs.mixpanel.com/docs/experiments)、[PostHog iOS SDK](https://posthog.com/docs/libraries/ios)。Mixpanel Feature FlagsはSDK 6.4.0以上が必要。初回調査時の`Package.resolved`は`master` branch revision `6e2a786b…`とPostHog 3.49.0を含んでいたが、現candidate sourceはMixpanel Swift 7.1.0 stable revision `38e63de7d71a2b6787bbd190ef8fcc04d053f259`へpinし、PostHog Package/config/captureを除去済み。契約や上限を推測せず、Mixpanel accountのFeature Flags/Experiments entitlement・MEU allowance・project regionは公式account readback後にのみ有効化する。

### build 818 baseline / PR #9289候補のAs-Is

build 818はsource SHA `6cc7c4a777be017e2d1ed4c50c439e02c2375d2e`で、PR #9289のAnalytics変更を含まない。以下のscreen inventory・Mixpanel一本化・購入計測のsource実装はPR #9289の候補sourceを指し、build 818や本番event受信の証拠とは扱わない。

| 領域 | 実装済み | 未完/問題 |
|---|---|---|
| 初期化・送信 | `AppDelegate.swift`で`AnalyticsManager.configure()`、`AnalyticsManager.swift`でMixpanelを初期化。`track`はcontextを付けてMixpanelへ送り、PostHog設定時は同じeventも送る | 本番Mixpanelへのtest/live event受信、project region、安定anonymous IDからaccount IDへの移行、logout reset、offline再送/重複はservice側readbackしていない |
| 画面 | 18個の`AnalyticsScreenID`をOnboarding/Feed/Settings/Paywallのproduction callerへ対応付け済み。候補branchでbackground復帰時の新visit再開と次画面exit、サインアウト時のvisit消去/session ID更新を実装し、純Swift regressionを確認。shared modifierとOnboardingは同じscreen/flowのdedupeを通す | Mixpanel service受信・全実画面coverage・実ユーザーの重複率、および実機での`didBecomeActive`とSwiftUI route更新の順序は未確認。現行onboardingはlinearで戻る操作がなく、`onboarding_step_back`はenum定義のみでcallerがない |
| 二重送信 | `AnalyticsManager.track`のPostHog conditional send | `PlanSelectionStepView.swift`は直接PostHog captureし、paywall view時に`paywall_plan_selection_viewed`相当を複数経路から呼ぶ。画面再描画を含め重複の実測が必要 |
| 購入 | `PurchaseObservationLedger`がtransaction IDの観測をローカルdedup。trialとpurchase eventを分け、`displayed_price`には`amount_source=store_product_quote_not_settled_revenue`を付ける | 表示価格はApple/RevenueCatで決済済みの純収益ではない。restore完了eventがなく、transaction callback・renewal/refund/proceedsをprovider実績と統合していない |
| Open | 現行`aniccaai.com/open/`は会社指標、ASCのstore discovery/downloads、RevenueCat等の集計を読む | iOSのscreen funnel/離脱/cohort/experimentをMixpanelから表示していない |

対象sourceはbuild 818 SHA `6cc7c4a777be017e2d1ed4c50c439e02c2375d2e`。イベント名の存在だけでcoverage・本番受信・分析可能性を完了にしない。

**固定SDKのローカル挙動（Mixpanel service receiptとは別）:** `Package.resolved`はMixpanel Swift 7.1.0 / revision `38e63de7d71a2b6787bbd190ef8fcc04d053f259`を固定する。公式sourceの[`Track.swift`](https://github.com/mixpanel/mixpanel-swift/blob/38e63de7d71a2b6787bbd190ef8fcc04d053f259/Sources/Track.swift#L84-L89)はSDK identityから`distinct_id`と利用可能なanonymous/user IDをpayloadへ設定し、[`SessionMetadata.swift`](https://github.com/mixpanel/mixpanel-swift/blob/38e63de7d71a2b6787bbd190ef8fcc04d053f259/Sources/SessionMetadata.swift#L33-L42)はevent ID・session ID・sequence metadataを生成する。`Track.swift`はpayloadをflush前にローカル永続化し、[`MixpanelInstance.swift`](https://github.com/mixpanel/mixpanel-swift/blob/38e63de7d71a2b6787bbd190ef8fcc04d053f259/Sources/MixpanelInstance.swift#L1399-L1410)はflush結果が`sent`または`dropped`ならqueueから除去し、`failed`なら保持する。これは固定SDKのclient-side実装根拠であり、Mixpanelがeventを受理した証拠、service-side重複0、実ユーザーIDの安定性を証明しない。test identity・event/property・時刻・releaseのservice readbackは未完了。

### 現行AnalyticsScreenIDとproduction caller

次表はsource上の配線inventoryであり、純Swift `ScreenVisitLedgerTests`はlocal transition stateだけを検証する。どちらもMixpanel受信・実ユーザーcoverageのreadbackではない。画面entryと明示的遷移だけで`screen_exited`を送り、backgroundでは訪問を終了扱いせず一時停止し、foreground復帰で画面visitを再開する。サインアウトではactive/suspended visitを破棄し、匿名IDへ引き継がない新しい`session_id`へ切り替える。

| 画面ID | production caller | source上のevent |
|---|---|---|
| `onboarding.welcome` | `OnboardingFlowView.recordStepView` → `AnalyticsScreenID.onboarding(.welcome)` | `screen_viewed`, `onboarding_step_viewed` |
| `onboarding.goal` | `OnboardingFlowView.recordStepView` → `.goal` | `screen_viewed`, `onboarding_step_viewed` |
| `onboarding.pain_points` | `OnboardingFlowView.recordStepView` → `.painPoints` | `screen_viewed`, `onboarding_step_viewed` |
| `onboarding.struggle_frequency` | `OnboardingFlowView.recordStepView` → `.struggleFreq` | `screen_viewed`, `onboarding_step_viewed` |
| `onboarding.reminder_schedule` | `OnboardingFlowView.recordStepView` → `.nudgeTimes` | `screen_viewed`, `onboarding_step_viewed` |
| `onboarding.processing` | `OnboardingFlowView.recordStepView` → `.processing` | `screen_viewed`, `onboarding_step_viewed` |
| `onboarding.first_affirmation` | `OnboardingFlowView.recordStepView` → `.planReveal` | `screen_viewed`, `onboarding_step_viewed` |
| `onboarding.comparison` | `OnboardingFlowView.recordStepView` → `.comparison` | `screen_viewed`, `onboarding_step_viewed` |
| `onboarding.notifications` | `OnboardingFlowView.recordStepView` → `.notifications` | `screen_viewed`, `onboarding_step_viewed` |
| `paywall` | `PaywallFlowContainer.analyticsScreen`; active paywall return from retention | `screen_viewed`, `paywall_shown` |
| `paywall.retention_offer` | `RetentionOfferSheet.analyticsScreen` | `screen_viewed` |
| `feed` | `FeedRootView.analyticsScreen` | `screen_viewed` |
| `feed.collections` | `FeedRootView.showCollections` change | `screen_viewed` |
| `feed.saved` | `LikedQuotesView.analyticsScreen` | `screen_viewed` |
| `feed.reminders` | `NotificationsSettingsView.analyticsScreen` | `screen_viewed` |
| `feed.themes` | `ThemePickerView.analyticsScreen` | `screen_viewed` |
| `feed.settings` | `SettingsSheet.analyticsScreen` | `screen_viewed` |
| `settings.subscription` | `SettingsSheet` subscription navigation destination | `screen_viewed` |

`onboarding_step_back`はevent enumにあるが、現行linear onboardingには戻るbutton/gestureもemitting callerもない。計測のためだけに戻るUIを増やさず、back操作が製品に追加された時点でsource contractとtestを追加する。`screen_exited`は明示的に画面を移る時だけ発火し、screen viewから30分以内に定義済みnext screenへ進まない割合をdrop-offとして推定する。OS killやbackgroundは画面終了として送らない。

### To-Beイベント契約と分析方法

| 問いたいこと | 計測契約 | Mixpanelで見るもの |
|---|---|---|
| どの画面で止まるか | `screen_viewed`へ`screen_id`,`screen_instance_id`,`flow_id`,`flow_version`,`session_id`,`app_version`,`app_build`,`locale`,`storefront/country`。明示的な画面遷移時だけ`screen_exited`と`next_screen_id`,`observed_duration_ms`を送る | screen viewから定義済みnext screenへ30分以内に進まないunique user率。分母=そのscreenに到達したunique user、母集団/cohort/観測窓を表示。強制終了瞬間の完全捕捉とは言わない |
| 初回価値へ届くか | `onboarding_started`,`onboarding_step_viewed`,`onboarding_step_completed`,`first_affirmation_viewed`,`onboarding_completed`。開始からの経過とstep順を保持。`onboarding_step_back`はback affordanceがあるversionでだけ計測する | start→各step→最初のaffirmation→完了のconversion、最大drop-off、first valueまでの時間 |
| affirmationが役立つか | `first_affirmation_viewed`,`affirmation_viewed`,`affirmation_liked`,`affirmation_unliked`,`affirmation_shared`。現UIではfavorite toggleがLikedQuotesへ保存するため、like/unlikeを保存操作にも使い、同じtapに`affirmation_saved`を重ねない。`quote_id`,`category`,`source`のみ | 初回価値後の保存/再閲覧/like率、category別の成熟cohort再訪。本文全文は送らない |
| 通知が戻りを作るか | 現iOS callerは`notification_permission_requested/result`,`notification_registration_result`,`notification_received`（foreground観測のみ）,`notification_opened`,`notification_destination_resolved`を送る。iOSに`notification_scheduled`/`nudge_scheduled`のcallerはないため、server owner/sourceが確認されるまで予定済みとして数えない。To-Beでは`notification_id`,`quote_id`,`permission`,`flow_id`を付け、既存propertyのcoverageはfocused testで確認する | 許可・token登録・foreground受信観測・開封・目的画面到達を分離。APNs受理を端末配達やserver scheduleと呼ばない |
| Paywall/課金 | candidate paywallのscreen entryは`screen_viewed`と`paywall_shown`。旧`PlanSelectionStepView`は`paywall_plan_selection_viewed`を含むが、current `PaywallFlowContainer`のactive entryとは分ける。無料閉じは`onboarding_paywall_dismissed_free`、画面遷移は`screen_exited`。purchase/trial/restoreは`product_selected`,`purchase_started/result`,`trial_started`,`restore_started/result`。`flow_id`は付与済み。`transaction_id`はclient analytics payloadへ送らない | paywall→商品選択→購入/無料継続/restoreのファネル。transaction observationはlocal dedupし、settled revenueはApple/RevenueCat receiptで照合する。displayed priceを収益へ足さない |
| 変更が効いたか | `experiment_exposure`はvariant割付・実表示を結ぶcallerができた場合に一度だけ送り、`experiment_id`,`variant`,`assignment_version`,`assignment_source`を付ける。現sourceにemitting callerはなく、account entitlementも未確認 | 稼働experimentが存在しない間はresultを表示しない。Mixpanel Experimentでactivation/retention/paid conversionとcrash/refund/notification guardrailを比較する場合、仮説・baseline・必要人数・期間・停止規則を開始前に固定 |
| どの入口が効いたか | providerが観測した場合のみ`campaign_id`,`content_id`,`source`,`medium`。不明ならnull＋reason | source別のinstall→activation/paywall/paid。ただしApple privacy thresholdやATTで識別不能な流入を推測で埋めない |

全event共通で`event_id`,`event_timestamp`,`app_version`,`app_build`,`flow_version`,`locale`,`session_id`,`distinct_id`を正規化する。匿名IDはSDKが維持し、認証IDが存在する場合だけ公式のidentify/reset契約に沿って接続する。email・通知本文・affirmation自由入力・token・個人単位データは送らない。画面遷移の連続発火、background/resume、同じ購入callback再送、offline再送を隔離fixtureで検証し、同一event/transaction重複0をMixpanel側で確認する。

購入eventは行動分析用。実収益はRevenueCat/Appleのtransaction・renewal・refund・proceedsを正本とし、通貨/対象期間/分母を揃えてOpenへ出す。trial、restore、買切、subscriptionは別々に数える。未取得は0にしない。

### G4.1 — Aniccaのfunnelを既存Openへ出す（G5前提）

公開UI ownerは`Daisuke134/anicca-products`。現行`apps/landing/public/open/index.html`は`data.json`,`metrics.json`,`capafy.json`等のsnapshotを読み、ASC store discovery/downloadと会社/RevenueCat指標を表示する。screen-level Mixpanel funnelは存在しない。`apps/landing/scripts/open-app-store-analytics.mjs`はASC公開データを`data.json`へまとめ、Netlify workflowで公開する。`scripts/open-startup/build_open_metrics.py`/`update_open.sh`は別のcompany/portfolio `metrics.json`経路。これらは現在Mixpanel eventを取らない。

Life Manager側の`apps/life-manager/scripts/marketing-product-summary.js`はproduct-packを読むが、Mixpanel collectorではなく、Openへの公開経路もない。G4.1はOpen snapshot ownerの`anicca-products`で、既存の hourly Netlify workflowからMixpanel Raw Event Export APIを取得し、既存`data.json`へ集計する。認証はGitHub Actionsの`MIXPANEL_SERVICE_ACCOUNT` secretだけを使い、project IDとregionはprovider APIで検証して設定する。API secretやevent-level dataは公開JSON/browserへ含めない。

Aniccaの既存Open画面に、各screenの観測view数、次screenへ進んだ数、24時間の成熟窓で次screen eventが観測されなかった数、率、分母、取得期間、release/locale/国のaggregateを表示する。開始/完了、通知、購入eventはG4のevent contractを保持し、G4.1の最初のsliceはscreen-level view/transitionへ絞る。単一screen unloadや離脱の瞬間を観測したとは表現しない。全体dashboard改修(G6/G7)と分け、別dashboardを作らない。個人ID・本文・少数cohortを公開しない。

G4/G4.1完了条件は、candidate appからのtest eventをMixpanelでreadbackし、event名・property・時刻・releaseと重複なしを確認すること。Open collectorの取得値とMixpanel aggregate、Open preview/live readbackの数・期間・denominator・freshnessを照合する。SDK設定、PR、fixture JSONだけでは完了にしない。Production、sandbox、simulatorのeventは環境を分け、test trafficをproduction cohortへ混ぜない。provider account/権限が不明なら具体的な不足物を記録し、0や成功へ置き換えない。

## G5 — 検証・実製品動画・提出

1. 変更に対応する最小の回帰を先に失敗させ、実装修正後にpassを確認する。既存のnavigation・onboarding・paywall・tokenテストを再利用する。
2. Release相当のsimulator buildでMaestroを動かす。fresh EN/JA、初回flow、soft close、settingsからの再購入、価格/Offering失敗、購入cancel/restore、連続上下swipe、like/保存/テーマ保持、cold/warm notification本文一致を確認する。
3. 成功した同一runを `xcrun simctl io <UDID> recordVideo` 等の既存録画機能でMP4保存し、Maestro log・screenshots・flow version・device/OS・commit/build・実行結果・動画内の主要時刻を付ける。モック動画や失敗runの編集で成功を装わない。Daisへ再生できるMP4と実画面を提示する。
4. notification injectionのrouting成功、APNs受付、実機表示/タップは別証拠にする。Maestroだけでフレームの滑らかさや実購入を証明しない。ユーザー指示で実端末APNs試験は省略し、Simulator routing結果と区別する。変更した購入権限はSandbox購入/paid restoreで確認し、未検証を明示する。
5. **提出禁止ゲート:** G1〜G4とG4.1がすべて完了し、Mixpanel service receipt・二重発火0・Openの公開readback・全画面screen inventoryが揃うまで`asc review submissions submit`を呼ばない。候補buildはその同一source SHAで全screen/flow Maestro E2Eを通し、録画をユーザーが見られるYouTube限定公開動画として提示する。動画build SHAとASC build source SHAを照合する。
6. 条件ごとの証拠を記録し、ユーザーへ動画・結果を共有する。ユーザーの最新指示により、すべての完了条件がPASSした後は追加承認を挟まず提出へ進む。
7. 正本main由来の署名済みartifact、privacy/metadata/review notesと実商品を照合し、既存ASC CLI経路で一度だけ提出する。`VALID`/upload/CIだけでは終了せず、対象version/build/submissionの公式`WAITING_FOR_REVIEW`を読む。subscription metadata/price/territoryのwarningが残れば、対象商品が正しく審査可能か解消・照合する。
8. Appleの承認・公開は提出完了とは別に追う。却下時は指摘と対象buildを取得→原因修正→影響する検証/必要なら再録画→一意な次build→再提出。同じ不明submissionを再送しない。

動画・provider receipt・生ログはGit外のprivate evidence storeへ置く。source/specには秘密を含まないartifact refと結果だけ残す。録画は自分のtest simulatorを対象にし、他人の端末状態・本番account情報を含めない。

## G6 — 全出荷アプリ・国別・課金の観測を揃える

公式ASCアプリ一覧と製品registry、RevenueCat project/app、公開URL、source path、ownerを照合する。少なくともAnicca/Honne/Dhamma/Thankful/Sleep Reset/Cherieを対象候補として確認し、未出荷・廃止・未接続を区別する。5アプリfeedを全出荷アプリ扱いしない。

国はASC storefront/territory、言語はapp localeとして別軸。install/new SDK customer/active customer/paid subscriberは別metric。ASCのprivacy threshold・report delay・部分日を保持する。downloadのauto/manual update・再download・restoreをfirst-time installへ混ぜない。アプリごとにsource failureを隔離し、Honneの欠測がAniccaの集計を止めない。

まず取得可能な公式ASC・RevenueCatを修復し、product analyticsのactivation/retention/funnelを接続する。新しいpaid分析toolや追加hostingを前提にしない。SDK設定・API権限・既存契約はprivate SSOT/公式readbackから確認し、不足を具体化する。

## G7 — Openダッシュボード・日次履歴

新しいdashboardを並立させず、既存 `https://aniccaai.com/open/` を使う。HTML/公開snapshot ownerは`Daisuke134/anicca-products`。`apps/landing/public/open/index.html`は静的`data.json`/`metrics.json`等を読み、ASC store discovery/download、会社/portfolio指標を表示する。Mixpanelのscreen-level funnelは現行page/snapshotにない。`apps/landing/scripts/open-app-store-analytics.mjs`とNetlify workflowはASC analytics、`scripts/open-startup/build_open_metrics.py`/`update_open.sh`は会社metricsの経路で、どちらもMixpanel product eventを収集しない。Life Managerの`apps/life-manager/scripts/marketing-product-summary.js`は既存product-pack snapshotを読むがMixpanel collectorではなくOpenにも未接続。G4.1ではAniccaだけを既存sectionへ追加し、G6/G7で全app・履歴・広いdashboardを拡張する。snapshot writer/ownerとNetlify公開contractは実装時に最新mainで照合し、Open内にAPI secretや個人eventを出さない。

アプリ/国・言語/流入元/期間7日・30日/実験variantで絞れる。上段は新規install・onboarding完了・D7継続・MRR。日次線と7日移動平均、release/experiment注記を表示する。funnelは人数と率・分母を併記し、最大離脱、国別、流入元、実験の結果/未判定、free/pro通知設定と実配信のcoverageを確認できる。

| 指標 | 定義 |
|---|---|
| 完了率 | 対象flowを開始したunique userのうち同flowを完了した割合 |
| 画面離脱 | screen_view後、同session内30分以内に定義した次stepを完了しない割合。強制終了の瞬間を完全観測したとは言わない |
| activation | 最初の関連文言を表示し、保存または次の文言閲覧まで到達。価値との関係は後の継続で検証 |
| D1/D7/D30 | 初回cohort日から1/7/30日後に再利用した割合。UTC日付基準、成熟cohortのみ、地域別表示も分母を維持 |
| paid conversion | 初回cohort後35日以内の初回有料購入人数/first-time install。trialとは分け、同一取得範囲で照合できる場合のみ率を出す |
| RPI | 同一獲得cohortのD14/D35実収益/取得install。未成熟値は暫定表示、返金・fees控除前後を分ける |
| MRR | active recurringの月換算額。年額/12、月額そのまま、週額は公式provider定義に従い出所を示す。買切・trial・累計売上は除外 |
| profit | 実売上からrefund・platform fee・production/distribution/inference/VM等実費を控除。欠費用があればunknown/partial |

日次snapshotは上書きだけにせず履歴保存し、後日修正は原値・revision・理由を保持する。`observed_at/data_from/data_to/source/status/coverage`、numerator/denominator/cohortを付ける。null+reasonを0へ置換しない。public pageのheader更新だけでsource鮮度を主張しない。グラフ・最終取得時刻・日付境界・狭幅描画まで公開readbackで確認する。

## G8 — 配信と製品を一つの実験へ結ぶ

投稿/SEO記事/landingの `content_id/category/campaign_id/platform/account/locale` を登録し、当社所有のquote catalogへ結び付ける。SNSで反応したテーマをonboarding選択・app collection・通知の編集候補へ戻す。ユーザーの同意や文脈と無関係な単一SNS人気順へ置換しない。

既存のApple campaign tokenやUniversal Linkを優先する。インストール済みなら該当quote/collectionを開く。未インストールなら対応landing/storeへ送り、post-install同一quote復帰はsupported経路で検証できた範囲のみ約束する。UTM・投稿時刻だけで人ごとのinstall/paid attributionを捏造しない。iOSのprivacy制約/未判定sourceを残す。

実験は「onboarding順序→paywall表現/位置→地域別価格・trial/hard対soft→推薦/通知」の候補から、最大損失と十分な流入に基づき一つを選ぶ。順序はSSOTで理由付き更新。価格・配置・文言を同時に変えて単一要因の効果とは呼ばない。

割付は安定user単位で保持し、experiment/versionと実露出を記録。既存購読価格を上書きしない。開始前に仮説・主指標・最小検出効果・baseline・有意水準/検出力または採用Bayesian規則・必要人数・最短期間・停止条件を記録する。原則、一つの対象cohortで一つの主実験。標本不足の週は「未判定」であり勝者を作らない。

日次閲覧で繰り返し有意判定をしない。予定した固定終了判定か、選んだ統計方式の正式な逐次規則を使う。少なくとも曜日一巡と対象metricの成熟を待つ。SRM・重複・欠測・急な流入構成差を検出し、crash・権限破損・返金悪化等のguardrailは統計的勝者判定と別に安全停止する。

## G9 — 日次分析・週次改善・審査回復loop

新しいharnessを先に作らない。既存 `config/loop-registry.json`、日次集計、週次review、release経路を読み、固定の一製品ownerと既存schedulerのsupported設定を再利用する。OpenFaaS/Hermes等は既存経路の具体的不足がある場合だけ、公式機能・費用・認証・動画を含むiOS実行適性を比較して採用する。独自browser/scheduler/vault/万能API proxyを穴埋めで新作しない。

| 頻度/trigger | 実行すること | 成果物 |
|---|---|---|
| 日次 | 公式獲得/課金、product event、SNS指標の取得、欠測・異常・guardrail診断、履歴保存、Open更新 | source別freshness/coverageと日次差分、原因と次の1手 |
| 週次 | 英語市場の勝者/一次資料を更新、cohortと実験を評価、最大の改善候補を一つ選ぶ | 仮説、対象ファイル、期待metric、実験/通常bugfixの区分、SSOT cursor |
| 修正着手 | 最新main→専用worktree→spec更新→失敗回帰→最小実装→focused検証→独立review→CI/main | SHAと受入証拠、依存や他ownerへ影響しない差分 |
| リリース可能 | 同一成果物のMaestro録画、署名、metadata照合、ASC提出 | MP4、build/version/submission ID、公式状態 |
| Apple却下 | 正式理由と対象buildを取得、原因を修正、影響する検証後に再提出 | 指摘→修正→検証→新submissionの対応関係 |
| Apple承認/公開 | 状態/公開版を照合し、次の変更がreadyなら次版へ | 公開版・release注記と次cursor。変更無しの空updateは出さない |

毎日調べること、毎週改善すること、毎週実験が確定すること、毎日App Store承認されることは別。Apple審査時間を制御できるとは扱わない。審査待ち中に次候補の準備は進め、同じversionのsubmission/不明effectを重複しない。

運営ownerは「Mobile Product Growth Owner」、primaryはSSOT/受入/統合を所有する。Muse/Grok等の既存teamは同じspec・台帳を参照し、配信ownerは配信、製品ownerはapp source、dashboard ownerは公開exportを所有する。共有browser/profile/stateのleaseを尊重し、登録memberやsendだけを着手証拠にしない。

最初のlive実行でwake→receipt→start→分析結果→変更/提出または根拠付きno-change→dashboardを測る。自然な2回目の実行で同じ投稿・購入・提出・集計の二重effectが無いことを確認する。継続計測はprocess/PIDでなくprovider結果とfreshnessを監視する。業務の自然レポートは既存経路を維持し、対話agentがTelegramへ自発送信しない。

各runは `run_id/owner_id/occurrence_id/release_sha/loaded argv-env(秘密値除外)/phase/command/exit_code/effect/readback/provider_receipt_id/evidence_refs/error_class/retryable/next_action` を既存形式で記録する。原因不明を0・成功に置換しない。再試行は同一effectの公式照合後に行い、自己所有の修正可能な原因を先に直す。

spend-capは既存の範囲を維持。追加広告・有料tool・新規資金移動を自動で有効化しない。秘密はprivate SSOTに置き、dashboard/public動画へ個人単位の行動やcredentialを出さない。無人運営のために認証/権限を迂回しない。

## G10 — 他アプリ展開と終点

Anicca初回版がMaestro動画・審査提出まで通ってから、共通metric schema・collector・dashboard・release経路をHonne等へ再利用する。全アプリで同じonboarding文言や同じactivationを強制せず、製品ごとの初回価値とpaid eventを定義する。日次集計で一製品の失敗を他製品へ伝播させない。

全体完了は、全出荷アプリのinventoryとcoverageが明確、Openの日次履歴が実データから更新され、実験が有効な統計とguardrailで運用され、自然実行で改善→検証→動画→審査/却下回復→公開照合を一巡し、次の巡回にも同じ台帳と二重effect防止が効くこと。売上成長・$10K MRR・profitはその後も公式収益で追い、pipeline稼働を収益達成と呼ばない。

## 共有する画面案

- [ダッシュボード案](../../design/anicca-product-growth/growth-dashboard.html)
- [英語アプリ5画面案](../../design/anicca-product-growth/affirmation-app.html)

両方とも会話で提示した操作可能なmockのsource。全指標、価格の提示、特典、通知許可はデモであり、稼働済み機能や実収益の証明ではない。実装はnative SwiftUI/既存UIKitで行う。動画による完成確認はG5の実製品runで置き換える。

## 保管・復旧

spec/plan/designはrepoの永続pathへcommit/pushし、remote objectまで確認する。容量不足は診断開始点とし、対象・owner・稼働利用・再生成可能性を確認して自分の不要build/cache/録画の重複などを整理し、保存/pushを再試行する。他者の進行中worktree、不可侵store、秘密・固有成果物を一括削除しない。認証不足は既存private SSOTと公式経路を確認し、通常判断や容量整理をDaisへの承認質問へしない。

### 分析service・Openの現在readback

build 818はMixpanelとPostHog両方のSDK/pipelineを含み、`AnalyticsManager.track`は同じeventを両方へ送る。PR #9289の未merge sourceではMixpanel Swift 7.1.0へ固定し、PostHog経路を除去して18画面IDを配線する。CI/focused testsは通過しているが、Mixpanel service上の受信・identity/property・重複0・experiment plan/region/MEUは未readbackで、完了扱いにしない。

2026-11-07 18:37 JST時点のOpen public main `Daisuke134/anicca-products@6aea3804295aea27addab0f3c81582fc56c16587`はMixpanel collector・screen tableを含む。PR #904のcollector/API workflow接続、PR #905のfail-safeはmainへ統合済み。main deploy run `42361224893` SUCCESS後、live `/open/data.json`は`product_analytics.anicca_ios.status=unavailable`、`error_code=missing_service_account`、`screens=[]`、`breakdowns=[]`を返した。JSONへのunknown状態反映は確認済みだが実Export API request/receipt、実funnel aggregate、preview/liveの実数値照合、hydrated Open UI表示は未確認。G4.1は実event receipt→aggregate→preview/live snapshot→既存Open表示の一連readbackをまだ満たしていない。

### 通知許可の回復導線

初回で通知をスキップした場合、Remindersから初回OS許可を要求できる。既に拒否済みならOS設定を開く。許可後は既存remote登録経路へ戻り、local配信を追加しない。Maestroでskip→設定→許可→通知本文表示を確認する。

許可要求の直後はアプリ内へ戻し、OS設定を自動で開かない。要求前のOS状態を読んで分岐し、要求後の実状態を読み直す。処理中の再タップを防ぎ、後から明示的に管理ボタンを押した場合だけOS設定を開く。

### MaestroのOS許可ダイアログ境界

Maestro 2.8.0 / iOS 26.5の実行では、OS許可が完了した後にも取得済みのAllow要素が返ることを観測する。アプリの状態ログと入力時刻の照合で、古い座標への再tapが背面の管理ボタンを押すと確認する。OSダイアログの座標再tapは行わず、アプリ側の許可済み表示・操作可能状態・フィード復帰を必須assertにする。focused許可回復flowのPASSを先に確認し、全体flowを再実行する。

### 通知のOS操作とアプリ検証の分担

iOS 26.5 / Maestro 2.8.0では、通知センターの合成touchは文言を表示できてもアプリを起動しないことを観測する。同一通知のSimulator native AXボタン操作では、終了中のアプリが起動し本文が一致する。通知試験はsimctlによる配送→Maestroで通知表示確認→native AXで実通知カードを一度操作→Maestroでquote-text/本文/保存/フィード復帰を必須assertにする。launchAppやdeeplinkで通知受信を代替しない。coldは操作前PIDなし→操作後PIDあり、warmは同一PID継続を記録する。実APNs配送や実機の合成touch成功へ読み替えない。

### 初回改善の検証証拠

実装はPR #9272でmain `9cc3d6e1bee952fa3f73659cc28c48529b1e2ca3`へ統合する。検証版は通常Release 1.9.7/817、アプリruntime treeは `e59cf7dcf1cd715f6443b5519947dd18b6db86c2`。mainとruntime・Xcode project・CI scriptsのtree一致を確認する。Xcode Cloudのbuild番号は独立採番で816、run=`ec24cda3-c88e-4b67-9a5c-091593a35f7f`、sourceは同じmain commitである。

検証済み: production-source native fixture（journey、notification、saved、catalog/recommendation、purchase dedup）、購入package選択22件、Python21件、UIKit6件、通常Release build。Maestro13は初回目的→実文言→保存→soft paywall→上25/下5 swipe→許可回復→theme/relaunchをPASSする。11/12は初回/設定の3プランとStoreKitキャンセル・復元後復帰、15は日本語、16は選択themeの再起動保持、18は通知許可回復をPASSする。通知14はbody-only cold、warm、同ID別本文の一致・保存を必須assertし、OSカード操作のみnative AXを使う。fresh read-only reviewはCritical/Importantなし、PR CI15件PASS。

動画・JUnit・xcresult・provider JSONはprivate永続path `/Users/anicca/.local/state/anicca-ios-initial-polish-20261106` に置く。`anicca-197-product-demo.mp4` は初回全体、`anicca-197-maestro-purchases.mp4` は購入キャンセル/復元、`anicca-197-maestro-japanese.mp4` は日本語、`anicca-197-notifications-verified.mp4` は実OSカード→アプリ本文/保存である。通知録画のcold前PIDなし、cold後とwarm後のPID一致を `notification-video-receipt.json` へ記録する。通知許可をリセットするclearState試験の後は許可済み表示を再確認してから配送する。

未確認の境界は分析サービス側event受信、実端末APNs配送、実購入/有料restore成功。StoreKitキャンセル・empty restore・Simulator配送をそれらの成功へ読み替えない。現在価格は米国storefrontで月$14.99・年$59.99・買い切り$59.99、trialなし、soft close可能を確認する。今回価格変更は行わない。提出状態と後続TODOは統合SSOTを参照する。

### 初回App Review提出の公式照合（取下げ前の履歴）

この項は1.9.7提出の取下げ前に確認した公式状態。現在の最終状態は本書末尾のApp Review実施記録を参照。

App=`6755129214` / bundle=`ai.anicca.app.ios` / version=`1.9.7` / build=`816`、build ID=`41ac019d-6fbe-489a-8382-40a62d1fd9c9`。Xcode CloudはArchiveが成功し、後段のTestFlight外部テスト審査への自動送信だけが `Please try again later.` で失敗する。Cloud全体を成功と呼ばず、run→公式buildの関連付けでVALIDを確認し、再ビルドは起動しない。

本番App Reviewへ既存VALID buildをattachし、doctor errors0/blocking0とfresh read-onlyの対象照合を経て提出する。submission ID=`cb6fa5a3-c350-482d-9ca7-369be6785249`、submittedDate=`2026-11-06T06:33:40.507Z`。`asc status` とversion GETで **WAITING_FOR_REVIEW**、version/build/submission一致を確認する。承認と公開は未確認で、審査待ちを公開完了へ読み替えない。成果manifestは [validation](../evidence/anicca-ios-1.9.7-validation.json)。通知動画の視聴用は `anicca-197-notification-demo.mp4`（録画開始時の準備待ちを除いたもの）、無編集元録画は保持する。


### 1.9.8通知修正フォローアップの旧記録（2026-11-06）

PR #9282（merge SHA `6cc7c4a777be017e2d1ed4c50c439e02c2375d2e`）はmainへ統合済み。latest main `bf71e15223e8e5dca71a7a79e773c8863c58c1ef`のAnicca iOS runtime/project/ci treeはそれぞれ`0931c01b8a78887a9291dfce74abf21bfa8007d8` / `060b64ccbeb15e360ac64e21c66ad17573236b92` / `b0e8b63afd146f8ba8e925971aebbd008046de8e`で、ASC build 818のsource commitはmerge SHA。Mac MiniのiOS 26.5 Simulatorでは候補build 817に対するMaestro 13（初回体験、1/1）と14（通知本文→feed→保存）がPASSしたが、候補binaryはbuild 818/merge sourceと同一である証拠がない。通知動画/source receiptもmerge SHAに結び付かないため、PR #9282の通知修正E2E証拠とは扱わない。通知試験のSimulator配送は`simctl push`と実OSカードのnative AX操作を使い、実端末APNs配送の証拠ではない。

実画面の動画は `/Users/anicca/.local/state/anicca-ios-initial-polish-20261106/Anicca-iOS-1.9.8-initial-UX-2026-11-06.mp4`（141秒、1206×2622）と `/Users/anicca/.local/state/anicca-ios-initial-polish-20261106/Anicca-iOS-1.9.8-notification-2026-11-06.mp4`（78秒、1206×2622）。両方H.264として再生検査済み。

ASC公式readbackでは1.9.7/816が`WAITING_FOR_REVIEW`のまま。1.9.8 version objectは未作成。Xcode Cloud run `98a7613c-898d-4d7c-8bda-62ef850a5403`のArchive由来build 818（`7cfb4f37-680c-447d-873a-7f8eb54a0baf`）は`VALID`/`APP_STORE_ELIGIBLE`。TestFlight外部テスト審査の自動送信だけが`Please try again later.`で失敗し、新しいApp Review提出はない。既存1.9.7提出は変更・取消しない。

**旧cursor（ユーザーの最新指示前）:** 旧案は1.9.7の提出を保全して待つものだった。ユーザーが1.9.7の取下げと1.9.8提出を明示したため、現在の実行順は本書末尾の「1.9.7・1.9.8の内容と再提出方針」を優先する。

### 1.9.7・1.9.8の内容とApp Review実施記録（2026-11-06）

| App Store版 | ASC build / source | 含まれる変更 |
|---|---|---|
| 1.9.7 | build 816、`VALID` / `APP_STORE_ELIGIBLE`。Xcode Cloud run `ec24cda3-c88e-4b67-9a5c-091593a35f7f`、source SHA `9cc3d6e1bee952fa3f73659cc28c48529b1e2ca3`、PR #9272 | 目的選択後すぐ最初のaffirmationを表示し、任意通知の後にsoft paywallを出す初回体験。affirmationの追加・カテゴリ/好みによる推薦・保存/likeの保持、スワイプ/通知遷移、通知許可後の復帰、画面/購入イベント計測と購入観測の重複排除。 |
| 1.9.8 | build 818、`VALID` / `APP_STORE_ELIGIBLE`。Xcode Cloud run `98a7613c-898d-4d7c-8bda-62ef850a5403`、source SHA `6cc7c4a777be017e2d1ed4c50c439e02c2375d2e`、PR #9282 | 1.9.7の改善を含むsourceへ通知修正を追加。通知本文のaffirmationを、同じIDの項目がpersonalized feedに既にあっても通知から開いた画面に保持する。 |

対応付けはASC build/runのsource commitとGitHub PRのmerge SHAを基準にする。当時のreadbackでは1.9.8 App Store version objectは未作成で、build 818は未添付の有効な署名済み候補だった。run 818はArchive後のTestFlight外部審査への自動送信が失敗した一方、ASC build 818自体は`VALID`/`APP_STORE_ELIGIBLE`。その後、Appleの指示で既存version objectを1.9.8へ更新してbuild 818を添付した。

UX動画 `/Users/anicca/.local/state/anicca-ios-initial-polish-20261106/Anicca-iOS-1.9.8-initial-UX-2026-11-06.mp4`（141秒）と通知動画 `/Users/anicca/.local/state/anicca-ios-initial-polish-20261106/Anicca-iOS-1.9.8-notification-2026-11-06.mp4`（78秒）は、どちらもiOS 26.5 Simulatorの候補build 817を録画したもの。YouTube限定公開で`PUBLISHED`をreadbackし、App Review提出前にリンクを提示した。初回体験: https://www.youtube.com/watch?v=88N3zsKZUJM、通知: https://www.youtube.com/watch?v=J005BFtO88U。動画説明にbuild 817と明記し、build 818やPR #9282の通知修正を実行した証拠とは扱わない。通知試験はSimulator配送であり、実端末APNsの証拠ではない。

**当時のASC snapshot（後続の公式状態は本節末尾に記録）:** 1.9.7/816は取下げ前に`WAITING_FOR_REVIEW`、1.9.8 version objectは未作成、build 818は`VALID`/`APP_STORE_ELIGIBLE`。ユーザー指示後、指定提出だけを取り下げて1.9.8を提出した。Appleが未公開1.9.7 version objectの存在を理由に1.9.8の新規作成を拒否し、既存objectの番号更新を指定したため、同じversion IDを1.9.8へ更新してbuild 818を添付した。

**G5の過去実施:** YouTube限定公開動画2本の後、1.9.7提出を取り下げ、同じApp Store version recordを1.9.8へ更新してbuild 818をattach・submitした。版validateは当時errors=0/blocking=0/warnings=15だったが、screen analytics/Openの受入前に提出したため、現在のユーザー合意の完了条件を満たさない。動画はcandidate Simulator build 817でありbuild 818と同じbinaryの証明ではない。

**状態と現在cursor:** 実行順・各ゲート状態・最新PR/ASC/Open readback・残TODOの唯一の正本は統合SSOTの [ANICCA-PRODUCT-GROWTH](2026-09-25-life-manager-unified-ssot.md#anicca-product-growth--ios初回改善から全アプリ継続改善まで)。
