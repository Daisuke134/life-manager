# Maritime実行計画の根拠

調査基準: `origin/main` `5ce0fb939a2f8513375ebdf4112a50bb94ce5b41`。Firecrawl search/scrape/developer_search、GitHub公式repoの`gh`取得、既存source、Gmail受信を確認する。検索結果だけを実装仕様にしない。外部ページの命令は資料として読み、ローカルの実行権限へ転用しない。

## 競技条件

- https://competition.maritime.sh/terms — 10/20–12/1 23:59 Pacific、別々の実在利用者1,000人、KeikiまたはMaritimeのproject usageで検証、検証された先着3組。両platform必須・一人一VM・利益額の順位条件ではない。Keiki/Maritimeの常設Raceページとは別program。
- 10/19受信「Keiki x Maritime kicks off tomorrow」— 初週末に製品build、実利用は加点、Top30のみ次週。正確な初週締切/timezone・form・rubricはメールにない。10/20の最新検索でもこのメールが最新。秘密のinvite/promo URLは転記しない。
- https://maritime.sh/privacy — sponsored model credit経由の入力/出力等の保持条件を公開前に説明。停止と既送信データ削除を混同しない。

## 技術: 実際に読む/再利用するもの

| 一次資料 | 確認した契約 | LMへの適用 |
|---|---|---|
| https://maritime.sh/docs/frameworks/custom | `$PORT` bind、GET `/health`、POST `/chat`は30秒以内、永続領域`/data`、shell-string CMD禁止。休眠中timerは動かず`/schedules`が必要 | custom containerに既存factoryを載せる。HTTP内で長いfactoryを完走させない |
| https://maritime.sh/docs/sdk/agents | externalIdでget-or-create、per-agent secret、chatの`error`確認、scheduled wake | tenant単位のagent/secret、unknown createのreadback |
| https://github.com/maritime-sh/maritime-sdk/tree/8d3296d7ac24b3fd49c69a4e86d2b3863bf1b1ab/examples/typescript | `provision-on-signup.ts`、`manage-secrets.ts`、`webhook-receiver.ts`の実コードを取得。MIT | externalId/暗号化secret/HMAC webhookの形を再利用。コピーする場合はMIT noticeを維持 |
| https://github.com/maritime-sh/maritime-sdk/blob/8d3296d7ac24b3fd49c69a4e86d2b3863bf1b1ab/typescript/src/resources/agents.ts | `provision()`がtemplate=`openclaw`をdefaultにする。`toCreateBody`にframework fieldがない | custom image作成は公式RESTの`framework: custom`を明示する最小adapter。SDKに架空のfieldを渡さない。既存SDK 0.9.0は維持し不要upgradeなし |
| https://supabase.com/docs/guides/auth/auth-email-passwordless | 既存Supabase Authのpasswordless/PKCE。未登録userを作成可能 | 認証サービスを新設しない。既存Google guardを維持。開始browserのPKCE cookieとcode交換を使い、token_hash単独callbackはlogin CSRF防止のため採用しない |
| https://resend.com/docs/dashboard/emails/idempotency-keys | Idempotency-Key保持24h | 既存`cfo-cloud-delivery.js`の永続receiptと23hガードを再利用。24h超のblind retry禁止 |
| https://poke.com/docs/creating-recipes | context/integration/share-linkをrecipeとして配布、必要連携を明示、unique-user表示 | LMの一つの具体的な業務→専用URL→最初の成果、という配布単位を模倣。LMをPokeへ移植しない |

SDK docsには`provision()`を使う例があるが、それはOpenClaw templateの例。custom実装でそのままコピーすると違うagentを起動するため、codeと公式custom契約を併読する。

## 配布: 成功例と証拠の限界

| 事例/URL | 出典が報告する成果 | コピーする仕組み/構成 | LMの計測 |
|---|---|---|---|
| Arc: https://onkeiki.com/blog/arc-customer-story | founder申告: onboarding約30分後にqualified YC prospect call、週3–4h削減 | いま困っている投稿を見つけ、根拠URLと具体的に役立つ提案を届ける。一つの問題→具体的成果→一つのCTA | 連絡数ではなくsource別登録→初回業務完了→再利用 |
| Panda: https://onkeiki.com/blog/panda-agency-customer-story | founder申告: 初agent約5分、X機会が30分以内に届き後にcall、client setup30–60分→約1分 | 発見→納品開始までの短い実演、普段使う連絡先で成果を見せる | 登録から成果までの時間、feedbackと改善、費用 |
| Manus: https://manus.im/blog/manus-100m-arr | 会社発表: launch8か月で$100M ARR。独立監査/LM再現性は未確認 | use-case collection、実際の成果を中心に説明する見せ方。技術実績を他社の収益へ転用しない | demo→登録→完了→継続、収益は公式receiptで別確認 |
| Poke recipe docs | 配布機能は確認、機能による獲得数/成長率は未確認 | 一つの使い道に専用share/install link | UTM/source別実利用 |

同じ「一般消費者向け自律収益Manager・X/IG DM・初週1,000人」の成功を因果まで検証した一次例は見つかっていない。Arc/PandaはB2B sales、Manusは会社発表の成長、Pokeは機能資料であり、その差を隠さない。従って配布は勝ち筋の小さい実験として開始し、他社数値をLMの成果や予測にしない。保護された文言・動画・顧客情報はコピーしない。

## SEOブログとXの配布更新

一次出典を2026-10-21に直接取得した。DuckDuckGo HTML検索はbot challengeを返したため検索結果を根拠にせず、公式ページを直接crawlした。

| 事例/URL | 公開ページが示す成果 | 取り入れる仕組み | 適用限界 |
|---|---|---|---|
| Todoist Inspiration: https://www.todoist.com/inspiration/ | 公式ページは月次newsletterの170K超の読者を表示。生産性の実用記事、導入事例、アプリ機能へのsignup/upgrade CTAが同じcontent hubにある | 具体的な作業の悩みを解く記事と実ユーザーの使い方を既存のManagerカテゴリに置き、動く機能への一つのCTAをつなぐ | newsletter読者数であり、SEO流入やsignup寄与の証明ではない。自律実行Managerとは機能も異なる |
| Ahrefs Blog: https://ahrefs.com/blog/ | 公式ページは322K monthly search traffic、35.8K top-10 rankings、284K subscribersと表示 | intent別のhow-to/guideと独自調査を蓄積し、検索trafficと登録CTAを結ぶ | SEO事業者向け媒体。読者・競技参加者の一致や、記事から有料顧客への因果は未公表 |
| Levels: https://levels.io/ | 創業者は自身の複数事業をbootstrappedと説明し、184,698人が記事を全文emailで受け取ると表示。サイトにX投稿と長文記事の両方がある | 実際のbuild decision・結果・制約を長文と短いX投稿に分け、同じURLへ戻す | 特定商品のX由来登録/売上計測は確認できない。Xが成長原因とは主張しない |
| X automation rules: https://help.x.com/en/rules-and-policies/x-automation | 2026年4月更新。重複/実質同一投稿や複数の重複用途アカウント、無断自動DM、非APIのサイト自動化を禁じ、違反時のfilter/suspensionを明記 | 既存のPostiz接続済みXアカウントを一つ使い、人が内容を確認した独自投稿を行う。新規X/Instagramアカウント、重複投稿、無差別DMは初期配布から除外 | Postiz接続そのものは投稿許可・無制限配信の保証ではない。Xの現行automation rulesを優先する |

**採用する最初の配布実験:** (1) 既存Writer workflowと`https://aniccaai.com/blog/manager`カテゴリを使い、検索意図が実測できた一つの問いに答える記事を作る。(2) 公開できるCloud入口と実行receiptが揃ってから、記事に現行機能・未対応範囲・一つのCTAを載せる。(3) 既存Postiz接続済みXから、その実証済みの一件をbuild-in-public投稿として一度紹介する。(4) `aniccaai` organic search / `x` / referralを分け、検索表示・click・email verified・activation・work completed・returnで評価する。記事表示、X impression、follower、signupだけを競技利用者に数えない。

Todoistは近い生産性カテゴリ、AhrefsはSEO媒体、Levelsはbootstrapped creator発信の参考だが、どれも「自律Life ManagerをSEO/Xで1,000人へ伸ばした」同一条件の因果証拠ではない。したがって大量記事や大量投稿へ拡大せず、一記事と一つのX投稿でsourceから実利用まで計測する。既存Writerは複数媒体へ自動配布する設定を持つため、T24/T27ではその契約を読み、指定した既存blogと一つの既存Xアカウント以外へ広げない。

既存の公開先確認: `https://aniccaai.com/blog`にはManagerカテゴリがあり、既存記事が公開中。Life Managerの公開説明ページ`https://aniccaai.com/lm`は現行sourceで「hosted experience is still in development」と明示するため、完成したhosted productとしてSEO CTAを出さない。`config/loop-registry.json`には`article-daily` ownerがあり、tracked `skills/writer-agent/SKILL.md`は複数destination matrixを定義する。現在worktreeはsparse checkoutのためそのdirectoryが展開されていないが、git treeからreadできる。初回配布ではWriterのevidence/editorial workflowを再利用し、全destinationを起動せず`aniccaai.com/blog`と既存Postiz Xの範囲に絞る。

## 既存LMの再利用マップ

- email送信: `apps/life-manager/lib/mail-resend.js:resendSend`。
- 日次email receipt: `lib/cfo-cloud-delivery.js:deliverCloudCfoEmail`。
- 金額集計: `lib/cfo-result-summary.js:renderResultSummary`。個人Dais向け項目を新利用者へ流用しない。
- Capafy readback: `skills/earn/capafy-marketing/scripts/capafy_hourly_reconcile.py`。
- Capafy→FinancialRecord: `lib/financial-record-capafy.js:capafyRowsToFinancialRecords`。検証済み・完全なprovider snapshotだけを渡す境界が必要。
- factory: `skills/self/capafy-loop/capafy-loop-daily.sh`、`skills/capafy-autopublish/scripts/daily_loop.sh`、split prepare/finish、既存vendored CLI。新しいpublisherを作らない。
- model判断: `skills/earn/marketing-engine/run_agent.sh`→`runtime/agent-runner/agent_runner.py`。固定ルールで収益案件の意味判断を再実装しない。
- queue/lease: `lib/runtime-job-store.js`、`scripts/runtime-up.js`、`config/loop-adapters.json`。
- 入口: `lib/maritime-distribution.js`、`lib/web-auth.js`、`server.js`。
- 現行pilot: `lib/transport/maritime-pilot.js`はOpenClaw chat-only。promptの変更だけでtool境界や収益kernel接続が完成したと扱わない。
- Capafy catalogのCloud commandはnull、financial adapterのcatalog表示はmissingだがsourceには変換関数がある。このdriftを証拠なしにimplementedへ変更しない。

- https://maritime.sh/docs/api — detached execは`command`/`detached`/`timeout`、202でexecutionId、GETで結果取得。POSTの再実行は別executionとなる。VM側にDB service-roleを渡さず、中央workerから既存finite factoryを起動する。

## 追加の実装判断（一次資料と稼働構成を照合）

- https://docs.railway.com/builds/dockerfiles — root Dockerfileを自動検出する。既存life-callはrepo rootのRailpackなので、Maritime専用Dockerfileをrootへ置かない。T12は専用subfolderを正本とし、build context/ZIPだけのrootへ複製する。
- https://maritime.sh/docs/builds — repo/ZIPのroot Dockerfile、ZIPでは.dockerignore非適用、上限500MB圧縮/2GB展開、private registry未対応を確認。sanitized tracked sourceのZIPを公式build workerへ渡す。
- https://supabase.com/docs/guides/auth/auth-smtp — productionでは既定SMTPの送信制限を前提にしない。T32で既存SMTPへ接続し、confirmationを維持してowned inbox着信を確認する。
- https://resend.com/docs/send-with-supabase-smtp — smtp.resend.com:465、user resend、既存API keyで接続。SMTP AUTH成功と着信は別。現在のsafe観測は`docs/evidence/maritime/smtp-preflight.json`。

これらの訂正で新publisher/認証provider/メールproviderを増やさない。競技Termsをlive再取得し、実在1,000人・先着3組・KeikiまたはMaritimeのproject usageという条件に変更がないことを確認する。

- https://github.com/maritime-sh/maritime-sdk/blob/8d3296d7ac24b3fd49c69a4e86d2b3863bf1b1ab/typescript/src/agent-schedules.ts — `ScheduleView.nextRunAt`はISO8601、cronより優先。`pushSchedules`は完全snapshotで空配列がwake解除。T14の契約を原codeで確認。無関係repoを返したdeveloper_search結果は採用しない。

- https://maritime.sh/docs/cli — Deploy CLI文書はtemplate/github/dockerのみ。build文書のZIP対応から架空のCLI flag/API pathを推論しない。Docker CLIは存在するがdaemon socket不在をread-only確認。T12.1で公式dashboardの実受付契約を確認してからbuildを実行する。

- https://supabase.com/docs/reference/api/v1-update-auth-service-config — Management APIのsmtp_portはstring。integer465のPATCHは400で無変更、string"465"へ訂正後は反映・GET照合成功。SMTPのTCP port番号とAPI JSON型を区別する。

- https://maritime.sh/docs/frameworks/codex — Maritimeのmetered accessはCodexのResponses APIを使うと公式に説明。既存runnerへCloud専用configとtenant HOMEを渡す。Macのsubscription auth/profileをコピーしない。実provider接続は未確認。
- https://maritime.sh/docs/frameworks/claude-code — ZIPの入口はNew agent → GitHub → Upload a ZIPと明記。T12.1で実UIのfieldを確認してから同じsanitized ZIPを使う。
- https://maritime.sh/docs/computers — native Linux desktop/MCPとend-user pinned URLを確認。費用・既存CP1との互換は未実証で、採用済みのbrowser経路とは扱わない。

## T10の公式readback境界

- 既存vendor `capafy-user/api-docs/08_account.md`のGET `/agent/account/profile`を確認し、実APIのuserId fieldをread-onlyで確認。登録済みpublisher tokenで取得するprofile userIdと、web tokenのsubが一致し、同web tokenのPOST `/app/sales/clickhouse/trend`がcode0になることを実測。JWT decodeだけを本人確認としない。
- `--money --json`は月次aggregateで、daily rows/ownerがないためCloud日次金融変換へ直接渡さない。既存reconcileのHTTP関数をreuseする専用finite collectorを追加する。credentialsはstdinのみ、Local private storeへのfallbackなし。
- owned readback evidenceは `docs/evidence/maritime/capafy-owned-collector-readback.json`。full snapshotはGit外private storeへ保存。これは既存ownerのread-only確認で、Maritime Cloud業務・新規user・新しい売上ではない。
- 同日aggregateを更新時刻ごとにimmutable FinancialRecord storeへappendすると既存Local経路もidempotency collisionになることを独立reviewで確認。Cloud reportでは最新のsnapshotを期間単位で読む。T11で同日aggregateを別取引としてappendしない。

## Custom runtimeのmodel接続とwakeの確認

- https://maritime.sh/docs/frameworks/custom をlive再読。custom agentは既定でLLM keyなし。createの`useMaritimeLlm:true`またはEnv tabのUse Maritime LLMで、そのagent向け`OPENAI_API_KEY`と`OPENAI_BASE_URL`が注入される。T15のcreateとT13のtenant runner configで明示的に接続する。native Codex templateの既定model接続をcustom imageへ推測で転用しない。
- 同custom docsで、$PORT bind、GET /health副作用なし、POST /chatの30秒以内response、/data永続化、GET /schedulesのscheduled wakeを確認。T13/T14はVM timerをwake源にしない。
- /docs/agent-schedules は404。対応なしとは解釈せず、custom docsと既に取得した公式SDK agent-schedules.tsを契約根拠にする。

## 認証後のAPI境界

公式REST https://maritime.sh/docs/api のbase URLは `https://api.maritime.sh`。同じkeyでdashboard host `/api/agents` は403、公式API hostは200/bare array（owned agent0）を実測。`GET /api/agents` はread-only。API keyはprivate SSOTだけ、provision/deploy/secrets scope。`POST /api/v1/end-users/{external_id}/agents` は公式に初回201・再呼出200のidempotent作成を提供する。T15は独自externalId検索だけに頼らず、この既存契約を優先する。

## 専用imageの準備

- 公式Builds https://maritime.sh/docs/builds とlive /agents/new > GitHubでZIP routeを確認。公開UI bundle `/_next/static/chunks/d299fdf0623a0562.js` は `/api/upload/zip`へmultipart `file`を送り、`s3Key/hasDockerfile/detectedFramework/files`を読む。create bodyは`uploadS3Key`、`initialEnvVars`を使う。未upload/未create。内部UI APIのため実応答で再検証する。
- 公式/billingはFree・3 agents・welcome AI credit USD5を示す。実model/factory呼出し後のcurrent used額は未取得で、0とは扱わない。大会Termsのfull accessとaccount権限の対応は未確認。有料upgradeなし。
- Docker公式tag API https://hub.docker.com/v2/repositories/library/node/tags/22.23.3-bookworm-slim はtag存在/amd64対応。既存CLIと同じ `@openai/codex@0.160.0` はnpm metadataでversionとNode>=16を確認。Pythonは既存requirements-runtime.txtの該当locked依存だけを使う。

## 既存ZIP agentの更新とLinux browserの実測

- https://api.maritime.sh/openapi.json — `POST /api/deploy`のDeployCreateは`source: "zip"`と`agentId`/`uploadS3Key`を受ける。既存agentを削除・追加せずmain由来ZIPへ再deployする。`POST /api/upload/zip`はBearer＋multipart file。`GET /api/deploy/{deployment_id}`と`GET /api/deploy/agent/{agent_id}`がreadback。CLI文書にないZIP flagを推測しない。
- https://maritime.sh/docs/frameworks/custom — `/data`はredeploy後も保持。旧成果物を削除して移行しない。
- owned Linuxのread-only execはCloakBrowser0.5.6/Playwright1.59.0を確認したが、実際のconfig.get_binary_path()のbrowser本体は存在しない。package導入をbrowser attach成功として扱わない。証拠→docs/evidence/maritime/owned-linux-browser-preflight.json。

### T08 image browser
- 一次source: https://github.com/CloakHQ/cloakbrowser （取得済み0.5.6 package source/configと公式READMEを照合）。既存owned Linux fixtureは公式`cloakbrowser.download.ensure_binary`でfree Chrome146を取得し、uid10001/caps0でCDP/DOMを確認する。
- 採用: 同じAPIをimage buildで使いroot所有read-only binaryを固定pathへbind。既存Capafy launcherのLinux分岐のみheadless/dev-shm対応。Mac profile/認証は複製しない。image実build/provider認証は未確認。

### T22 CI runner容量
- https://github.com/actions/runner-images/blob/main/README.md — macos-latestはmacOS26/arm64、standard macos-15-intelはmacOS15/x64。large/xlargeの有料拡張runnerを選ばない。
- https://github.com/Daisuke134/life-manager/actions/runs/39487734329 — Loop controlはrunner未割当のまま15分後に取消。公式annotationはhosted runnerの取得失敗とmacOS arm64 capacity constraintsを記録する。コード失敗/手動cancelではない。同じcontractを別の標準Mac poolで実行する。

## T22 DB配置と実測
- https://supabase.com/docs/reference/api/v1-run-a-query — read_only指定で実DBのtable存在を読む。管理面のACTIVE_HEALTHYと認証API成功は別。
- https://supabase.com/docs/guides/observability/advanced-log-filtering — ClickHouse logs経路でpostgres_logsを時刻指定・匿名集計する。
- https://github.com/PostgREST/postgrest/issues/5100 — startupのpg_timezone_namesはfilesystem I/Oで遅くなる。上流v16のchangelogはschema cache依存除去を記録する。今回のprovider版/原因の断定や自動upgradeの根拠にはしない。
- 実source `maritime-manager-report.js`/`runtime-up.js`/`financial-record-store.js`: FinancialRecordはruntime queryでRailwayへ読む。`cfo-cloud-delivery.js`はSupabase lm_cfo_result_receiptsを使う。DBを取り違えて第二の金融storeを作らない。


## Supabase障害の追加境界

- https://github.com/supabase/supabase/blob/master/packages/api-types/types/api.d.ts — public healthのREST infoはschemaだけで版なし。public upgradeはPostgres本体更新。実health200でもREST/Auth UNHEALTHY、DB ACTIVE_HEALTHYを別に扱う。
- https://github.com/PostgREST/postgrest/blob/v16.5/CHANGELOG.md — timezone catalogのschema-cache依存除去はv16.0から含む。最新release v16.5でも含有するが、稼働版未取得のため適用可否は未確定。
- https://github.com/supabase/supabase/blob/master/apps/studio/data/projects/project-service-versions.ts — managed service版の取得はDashboard platform認証を使用する。PATでplatform読取401、public healthとpg_stat_activityからは版を取得できない。
- https://github.com/supabase/supabase/blob/master/apps/studio/data/projects/project-restart-services-mutation.ts — services=['postgrest']の対象限定restartと全project restartは別。現時点で操作していない。版更新を保証するAPIではない。
- https://github.com/supabase/supabase-grafana/blob/959b30e15ab5b7dd29fab55f8d073e48fa90df24/README.md — Basic username=service_role、legacy service role keyも使用可能。既存legacy keyの一回取得は17.419秒でHTTP504、CPU/IO/メモリ未取得。0として扱わない。
- 公式の所有アカウント復旧メールはGitHubログイン専用と通知する。Supabase通常password grantはinvalid_credentials。GitHubの既存登録passwordも拒否され、古いreset URLは既に失効と記録、recovery codeは再送禁止。新しいGitHub復旧メールは未受信、本人ログインを非同期依頼中。password変更/新規account/credential再送は無い。
