# Life Manager Maritime 初週・獲得・提出 Atomic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Daisの指示に従いprimaryが単独で順に実装する。独立作業は待ち依存を作らず進める。

**Goal:** メール登録からManager自身の仕事選択・Cloudでの既存Capafy業務・公式結果確認・日次メールまでを接続し、初週提出を完了して、配布から実利用者1,000人へ進める。

**Architecture:** Railwayの既存HTTP入口とSupabase Auth/状態を再利用し、Maritime custom containerへ同じrepoの既存factoryを載せる。Maritimeのscheduled wakeはtenant限定tokenでRailwayへ通知する。Railwayの既存runtime job/leaseがMaritimeの公式detached execでfactoryを実行し、結果/公式receiptを回収して既存CFO/Resendへ渡す。VMへSupabase service-role keyを渡さない。Keikiは選択肢として調査済みだが、既存emailを置換する必須依存にしない。

**Tech Stack:** 既存Node CommonJS、Node >=20.19.0、Python/Bash、Supabase/Postgres、maritime-sdk 0.9.0、公式Maritime REST（custom create・detached exec/result）、Resend、既存agent-runner/Capafy CLI/CloakBrowser・Steel adapter。

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` の「Keiki × Maritime — 初週Top 30と実利用者1,000人」。実行順・現在cursorの正本は同節。本書は各IDの実装手順を所有し、状態一覧を二重管理しない。

## Global Constraints

- 利用者に目標・予算の設定や毎日の指示を求めない。Managerが仕事と優先順位を決める。
- 完成形はメール登録→自律実行→日次メール。Telegramは任意。providerの本人確認/account所有権は架空にしない。
- 初週の動く製品とTop30、最終の実在1,000人を区別。利益額は公表された競技順位条件ではなく、利用継続のための事業指標。
- 家族・友人3人の返答・利用・feedbackを、開発、配布素材、demo、提出準備、正式提出の開始条件にしない。DM送信はDaisが担当。
- source→登録→開始→業務完了→再利用→provider売上/費用を測る。signupだけを公式実利用数としない。
- 新しいpublisher、model router、scheduler、email provider、汎用workflow engineを作らない。既存部品をhost adapterで接続する。
- distribution費用は0。既存方針・登録済みcap内で実行し、ユーザー入力の予算画面を新設しない。ホスト/model費用は公式billingで確認する。
- founderのaccount・商品ID・売上・private stateを新規利用者へコピーしない。同じ売上を全員へ配賦しない。
- runtime stateはGit外。Cloud stateは`/data`以下、secretはprovider管理のtenant単位、analyticsにemail/本文/tokenを入れない。
- 公開・送信の結果が不明なら同じeffectを再送しない。既存job/receipt/provider readbackで回収する。
- 各taskは実行手順を記す。実行済み・未実行の判定はSpec正本だけに記録し、コード統合をdeploy・投稿・正式提出の完了へ読み替えない。

## 現状と選定理由

計画改訂の基準main=`286e982bfe`。T02–T04のsourceは統合済み。状態・cursorはSpec正本だけで管理する。既存`maritime-pilot.js`はOpenClaw chat-onlyで、factory接続ではない。`mail-resend.js`と`cfo-cloud-delivery.js`は存在するので再利用する。Capafy factoryにはHOME、認証、browser、mutable sourceの依存が残るため、T07–T10で具体的に移す。既存売上のあるfactoryを第一候補にするが、全ての新利用者が接続なしで販売可能とは仮定しない。

**採用:** 既存factory + Maritime custom runtime + 既存メール。最短で同じ業務を移せ、競技platform usageも残る。
**棄却した最強案:** Keikiだけで新しい収益agentを組めば入口は速い。ただし既存factory/経費/receiptを別実装にしてしまうため主経路にしない。Keikiが必要なchannelを短縮すると確認できた場合だけ追加adapterにする。
**最も外れ得る前提:** Capafyのpublish認証・CP1/CP2/CP3がLinuxの既存browser adapterで再現できるか。T08で先に実測し、失敗境界を具体化する。

**best/base/worst（予測ではなく対応分岐）:** best=既存browser/sessionでfactory完走し、そのまま公開。base=host pathとtenant credentialの修正をして完走。worst=provider側の本人手続きが残る。その場合もCloud上でoriginal商品生成・継続作業・日次報告は進め、販売未接続/売上未確認を明示して提出するが、これは収益業務完走の完了扱いにはしない。別業務を完成済みと偽装しない。

## 構成・ファイル責務

`[既存]`は再利用/限定修正、`[追加]`はこの計画で作る最小境界。後続実行者は独自の別フォルダを増やさない。

```text
life-manager/
├── .dockerignore                                   [既存: credential/state除外を確認]
├── .agents/startup-context.json                     [既存: 製品定義]
├── .agents/product-marketing-context.md             [既存: copyの意味定義、#8395]
├── apps/life-manager/
│   ├── server.js                                   [既存: 下記専用handlerをmount]
│   ├── config/
│   │   ├── loop-adapters.json                      [既存: manager.cycleを登録]
│   │   └── product-loop-catalog.json               [既存: 実証後にCapafy readinessを更新]
│   ├── migrations/
│   │   ├── 2026-10-18-lm-maritime-distribution.sql [既存: participant cap/consent]
│   │   ├── 2026-10-20-lm-maritime-manager.sql       [追加: enrollment/binding/unique claim]
│   │   └── 2026-10-20-lm-maritime-runtime-executions.sql [追加: 一occurrence一dispatchのbinding]
│   ├── lib/
│   │   ├── maritime-manager-store.js               [追加: enrollmentとagent binding]
│   │   ├── maritime-manager-auth.js                [追加: email auth専用handler]
│   │   ├── maritime-manager-runtime.js             [追加: 既存jobからfactoryを呼ぶadapter]
│   │   ├── maritime-manager-report.js              [追加: tenant結果→既存CFO email]
│   │   ├── maritime-manager-store.test.js           [store境界]
│   │   ├── maritime-manager-auth.test.js            [auth/activate/page/stop境界]
│   │   ├── maritime-manager-runtime.test.js         [queue/dispatch/reconcile境界]
│   │   ├── maritime-manager-report.test.js          [結果/email境界]
│   │   ├── maritime-distribution.js                [既存: email登録入口/計測へ変更]
│   │   ├── web-auth.js                             [既存: UID/CSRF関数を再利用、Google guard維持]
│   │   ├── runtime-job-store.js                    [既存: queue/lease/receipt]
│   │   ├── cfo-cloud-delivery.js                    [既存: 日次emailの永続receipt]
│   │   ├── mail-resend.js                          [既存: send、再実装しない]
│   │   ├── financial-record-capafy.js              [既存: Capafy公式数値変換]
│   │   ├── web-funnel-events.js                    [既存: manager用milestoneを追加]
│   │   └── transport/
│   │       ├── maritime-pilot.js                   [既存: chat-onlyを収益実装と呼ばない]
│   │       ├── maritime-manager.js                 [追加: custom create/list/secrets adapter]
│   │       └── maritime-manager.test.js            [追加予定]
│   ├── maritime/
│   │   ├── server.js                               [追加: health/chat/schedules、短いHTTP]
│   │   ├── server.test.js                          [追加予定]
│   │   ├── Dockerfile                              [追加: 専用image、repo直下へ置かない]
│   │   └── build-context.py                        [追加: tracked SHAからsecret抜きZIP]
│   └── scripts/
│       ├── runtime-up.js                           [既存: adapter services wiring]
│       ├── maritime-manager-readback.js            [追加: sanitizeしたdeploy/usage/result確認]
│       └── maritime-week1-export.js                [追加: 提出用aggregateを生成]
├── skills/
│   ├── capafy/catalog-icons.json                   [既存: 現在のCI blockerの宣言漏れ修正候補]
│   ├── capafy-autopublish/
│   │   ├── scripts/daily_loop.sh                   [既存: factoryを維持、pathを注入可能に]
│   │   ├── scripts/cloud_cycle.py                  [追加: tenant envで既存entryを一度呼ぶ]
│   │   ├── scripts/publish_prepare.sh              [既存: CP1前半]
│   │   ├── scripts/publish_finish.sh               [既存: CP2/CP3/readback]
│   │   ├── vendor/                                [既存: publisher/market API]
│   │   └── test/
│   │       ├── test_cloud_paths.py                 [追加: HOME非依存]
│   │       ├── test_cloud_cycle.py                 [追加: 既存factoryの呼出し]
│   │       └── test_maritime_build_context.py       [追加: ZIP境界]
│   ├── self/capafy-loop/capafy-loop-daily.sh        [既存: 自律の商品生成/改善を再利用]
│   └── earn/
│       ├── marketing-engine/run_agent.sh           [既存: model判断]
│       └── capafy-marketing/scripts/
│           ├── capafy_hourly_reconcile.py          [既存: 公式sales/cost readback]
│           └── capafy_distribute_ledger.py         [既存: 配布effectのreceipt]
└── docs/
    ├── research/maritime/2026-10-20-source-map.md    [本計画の出典・模倣箇所]
    ├── superpowers/specs/2026-09-25-life-manager-unified-ssot.md
    ├── superpowers/plans/2026-10-20-maritime-week1-atomic-execution.md
    └── distribution/maritime/week1/
        ├── channel-copy.md                         [DM/X/IG文案、送信は未実施]
        ├── demo-script.md                          [撮影台本/素材/実装前claimの制限]
        ├── overview.png                            [生成済み: 全体設計の説明図]
        ├── submission-checklist.md                 [提出packetと受付証拠]
        ├── requirements.json                       [T01で公式提出条件を保存]
        ├── readiness.json                          [T08でhost/provider依存を記録]
        └── submission.json                         [T23で実測だけをexport]
```

`requirements.json`と`readiness.json`は観測済み。`submission.json`はT23で実測から作る。未観測をfalse/0/完了へ置換しない。図は説明用artifactで、実装の代わりにしない。

## コマンドの作業場所

`node --test lib/...`と`node --test maritime/...`は`apps/life-manager`をcwdとして実行する。それ以外はrepo root。全taskで、そのtaskの失敗assertionを先に実行し、失敗理由が対象契約であることを確認してから実装する。実装のない段階で全suiteを走らせない。実行済み状態はSpec正本を参照する。

## 固定する境界

- `Enrollment = {uid, auth_subject, email, timezone, status, source, consent_version, agent_id, release_sha}`。emailはprivate storeだけ。`status`は`pending|provisioning|active|paused|effect_unknown`。
- `CycleInput = {tenantId, occurrenceId, dateKey, releaseSha}`。利用者入力goal/budgetはない。
- `CycleResult = {status, tenantId, occurrenceId, artifactRefs, providerSnapshotRef, providerReceiptRefs, nextEligibleAt, errorClass}`。`status`は`completed|deferred|effect_unknown`。completedは選んだactionの完了で、売上発生とは別。
- `BusinessBinding = {tenantId, provider:'capafy', subjectId, credentialRef, browserSessionRef}`。他tenantを指定したbindingは実行前にreject。
- `DailyResult = {uid, periodKey, actions, grossByCurrency, refundsByCurrency, knownCostsByCurrency, netStatus, providerReceiptRefs, failures, nextActions}`。費用欠落時はnetStatus=`unknown`、金額を0にしない。
- wake relay: POST `/api/internal/maritime/wake`、header `X-LM-Agent-Token`、body `{occurrenceId,kind:'cycle'|'report'}`。uidはtoken bindingから解決する。VMはこれでenqueueを依頼するだけでDBの強い鍵を持たない。kind=cycleはcycle job、kind=reportはreport jobへ変換し、reportはRailway側で実行する。
- execution: `transport.dispatchCycle({uid,agentId,occurrenceId,dateKey,releaseSha}) -> {executionId,status}`、`transport.readExecution({agentId,executionId}) -> {status,exitCode,stdout,stderr}`。公式exec APIを使う。
- 日次`periodKey`は`maritime:daily:<timezoneのYYYY-MM-DD>`とし、既存CFOのhourly/daily keyへ衝突させない。
- 新規signatureは以下のtask記載を正とする。既存`enqueueJob`/`claimJobs`/`completeJob`/`deliverCloudCfoEmail`の既存APIは変えない。

## Review Focus

1. 確認メールのリンクscanner/prefetchで本人の利用やfactory実行を水増ししない（T04/T05:確認後POST activateのみ開始）。
2. custom agentのcreate response喪失で2台目を作らない（T16:list/readback→同一externalId、不確実なら保持）。
3. sleep/wake後の同一occurrenceで二重publishしない（T14/T15:既存lease/receiptを使う）。
4. founderのsession・既存seller・売上が別tenantへ漏れない（T08/T10/T19:所有者不一致はreject）。
5. timezone日付またぎ・provider送信後timeoutで日次メールを二重送信しない（T19/T20:periodKeyと永続receipt、24h超blind retryなし）。

## 実行順と並行性

- **提出経路確認T01、配布文案T24、台本T25は即着手可能。友人・利用実績を待たない。**
- T32（実メール設定）はT04後から独立して進め、T22公開前に閉じる。数字順ではなく依存順で実行する。
- T12は専用Dockerfile+sanitized ZIPへ訂正する。旧=root Dockerfile、新=`apps/life-manager/maritime/Dockerfile`。理由はRailwayの自動検出が既存サービスを変更するため。現在cursorはSpec正本を参照する。
- 旧T12→T13はCMD対象server未作成のままbuildする逆依存だったため、T13→T14→T12へ訂正する。各taskの成果条件は保持する。
- 開発critical path: T02→T03→T04→T05→T06→T07→T08→T09→T10→T11→T13→T14→T12→T15→T16→T17→T18→T19→T20→T21→T22→T23。
- T24/T25/T26の素材準備は開発の外部待ち時間に進める。投稿は公開URLと真実のdemoが揃えば進め、3人feedback待ちにしない。
- T23の正式提出は公開製品・公式指定必須項目が揃った時点で行う。友人3人、売上、7日継続、1,000人、豪華な動画を待たない。
- T27/T28/T29で獲得・再利用・経済性を改善する。T31でLM自身の任意課金とStripe実売上を別に確認する。社内目標demo=10/23 18:00 JST、packet=10/24。公式deadlineがそれより早ければ公式を優先し前倒す。上記は公式締切ではない。
- 各taskのcommit対象はそのtaskのowned filesだけ。fetch→focused acceptance→commit/push→exact-head checks完了→main統合。未登録/null checkをgreenと見なさない。

## Task T01: 公式の提出先・初週期限を一つのファイルへ確定する

**Files:** Create `docs/distribution/maritime/week1/requirements.json`。Read kickoff threadと公式Terms、既存参加Slack/Discordのpinned案内。
**Interfaces:** Produces `{source_urls, first_week_deadline, timezone, submission_url, required_fields, top30_rules, observed_at}`。未公表fieldはnullと理由。
**Depends:** なし。

- [ ] T01.1 Gmailで`after:2026/10/18 (from:0.email OR from:maritime.sh OR from:orchid.ai OR from:onkeiki.com)`を検索し、最新主催者本文を読む。invite/promo codeを出力しない。
- [ ] T01.2 private credential SSOT全体とbrowser registry/leaseを確認した既存CloakBrowserで、参加済みcommunityのannouncement/pinを読む。新しいworkspace/accountを作らない。
- [ ] T01.3 見つかった正式formのlabel・必須field・締切/timezone・受付形式を上記JSONへ記録する。formがなければURLを捏造しない。
- [ ] T01.4 JSONをparseし、全fieldに出典かnull理由があることを確認してcommit/push。未公表条件は提出作業T23だけの依存で、開発/配布準備を止めない。

## Task T02: 既存mainのCI blockerとcopy訂正を閉じる

**Files:** Modify `skills/capafy/catalog-icons.json`（必要な一行のみ）、正本Maritime節。Read PR #8395。
**Interfaces:** Produces source統合可能なmain SHA。新しいgateは作らない。
**Depends:** なし。

- [ ] T02.1 #8395のexact headでStartup context drift結果を読む。既知head`575628491d`ではSUCCESSで、残る既知失敗はOSS画像宣言漏れ。
- [ ] T02.2 `skills/capafy/catalog/tiktok-series-continuity-planner/icon.png`が商品sourceであることと現在のSHA256を読み、`catalog-icons.json.icons`の既存形式で欠落digestだけを登録する。画像本体・seller・gateを変更しない。他ownerの進行中diffは上書きしない。
- [ ] T02.3 `node scripts/verify-oss-self-contained.mjs`の`generated_artifact`該当が消えることを確認し、差分をcommit/push。新しい失敗は自分の差分との関係を診断する。
- [ ] T02.4 #8395と依存修正の全checksをexact SHAで読み、全件登録済み・completed・successを確認して通常統合する。既知の`merge-when-green`未登録通過問題を使わない。

## Task T03: email Manager enrollmentを永続化する

**Files:** Create migration `2026-10-20-lm-maritime-manager.sql`、`lib/maritime-manager-store.js`、同test。
**Interfaces:** `createMaritimeManagerStore(deps) -> {enroll,read,claimProvision,bindAgent,pause}`。同uidのenrollは同じrow。`claimProvision(uid)`は一ownerだけtrue。
**Depends:** T02。

- [ ] T03.1 test `enrollment_is_idempotent_and_tenant_scoped`を定義し、同uid二回で一row、別uidのread/agent bind拒否をassertする。
- [ ] T03.2 migrationに`lm_maritime_manager_enrollments`を作る。uid/auth_subject unique、agent_id unique、status check、service-role経由のみ、raw credentialのcolumnなし。既存participant tableを再作成しない。
- [ ] T03.3 storeに上記五methodを実装する。`read`はservice-owner用で、public handlerはverified sessionのuidからのみ呼ぶ。provision claimはconditional update、paused/unknownの再claimをしない。
- [ ] T03.4 `cd apps/life-manager && node --test lib/maritime-manager-store.test.js`。一row/一claim/所有者分離をPASSにしcommit/push。

## Task T04: email認証を既存Supabaseへ追加する

**Files:** Create `lib/maritime-manager-auth.js`とtest。Modify `server.js`、`web-auth.js`は既存UID/CSRF helperのexportが必要な場合だけ。
**Interfaces:** `handleMaritimeManagerAuth(req,res,deps)`。POST `/auth/maritime/email`、GET `/auth/maritime/confirm`。Produces verified Supabase session、private uid/email。
**Depends:** T03。

- [ ] T04.1 test `email_auth_does_not_require_google_calendar_goal_budget_or_telegram`と`unverified_email_cannot_activate`を定義。fake verified authをinjectしてUID以外の必須入力がないこと、未確認メールはrejectをassert。
- [ ] T04.2 公式例の`signInWithOtp({email,options:{shouldCreateUser:true,emailRedirectTo:...}})`と既存SSR PKCEの`exchangeCodeForSession(code)`を使う。token_hash単独callbackはlogin CSRFになるため受け付けず、開始browserのPKCE cookieを必須にする。user確認は`getUser()`で行い、request本文のuidは信頼しない。
- [ ] T04.3 Google専用`resolveWebUser`/`hasVerifiedGoogleIdentity`を緩めず、専用email resolverで`ensureWebUser`の既存tenant分離を再利用する。confirm GETではfactoryを起動せず、登録継続画面へredirectする。
- [ ] T04.4 rate-limit/expired-token/open-redirect/source cookieのfocused casesを同testに含め、`node --test lib/maritime-manager-auth.test.js lib/web-auth.test.js`で既存Google経路も維持してcommit/push。

## Task T05: 登録後の一度だけのactivateを接続する

**Files:** Modify auth/store/server、`lib/maritime-distribution.js`、各test。
**Interfaces:** POST `/maritime/activate`はverified session+CSRF+consentで`store.enroll`→provision jobを一度enqueue。GETでは起動しない。
**Depends:** T04。

- [ ] T05.1 test `activate_post_enqueues_once_but_get_prefetch_does_not`を定義。POST二回=一job、GET=0job、CSRF不一致=0job。
- [ ] T05.2 既存consent/participant capをemail uidにも適用し、sourceとtimezoneを保存する。goal/budget fieldを要求せず、timezone未指定はUTC。3人のallowlistをpublic登録の必須条件にしない。
- [ ] T05.3 既存`runtime-job-store.enqueueJob`を使い`maritime.manager.provision`のstable job keyをuidから作る。DB commit前にはMaritimeへ送信しない。
- [ ] T05.4 focused testとmigrationの重複適用/同時claimを確認しcommit/push。受付は`provisioning`であり、未実行をactiveにしない。

## Task T06: email登録ページを公開入口にする

**Files:** Modify `maritime-distribution.js`、`server.js`、既存distribution test。
**Interfaces:** GET `/maritime?source=...`→email form、登録継続/状態表示。Telegram linkは任意。
**Depends:** T04/T05。

- [ ] T06.1 test `landing_primary_cta_is_email_and_never_requires_telegram`を定義。main form action、保持条件、停止入口、必須fieldがemailだけであることをassert。
- [ ] T06.2 現在の「短い相談をTelegramへ」copyを、現在実行可能な業務と開発状況を示すemail入口へ変更する。未接続売上を保証せず、trial終了後の自動課金を導入しない。
- [ ] T06.3 既存source normalizationとUTMを保持し、送信済み個人情報/認証tokenをpage HTMLやanalyticsへ反映しない。
- [ ] T06.4 `node --test lib/maritime-distribution.test.js lib/maritime-manager-auth.test.js`で確認しcommit/push。

## Task T07: Capafy factoryのhost pathを注入可能にする

**Files:** Modify `skills/self/capafy-loop/capafy-loop-daily.sh`、`skills/capafy-autopublish/scripts/daily_loop.sh`、`skills/capafy-autopublish/scripts/key_health_gate.sh`。Create `skills/capafy-autopublish/test/test_cloud_paths.py`。子gateのdotenv読取/owner通知もCloud境界に従わせ、実runnerのCLI workdirをtenant workspaceへbindする。`.github/python-security-tests.txt`へ同focused testを登録し、既存Linux CIで同じ境界を実行する。
**Interfaces:** Consume `LIFE_MANAGER_REPO`（immutable source）、`LIFE_MANAGER_STATE_HOME`、`CAPAFY_STATE_DIR`、`AGENT_RUNNER_WORKDIR`、`LIFE_MANAGER_BUILD_WORKSPACE`。Cloud callerはstate/buildを`/data/<tenant>`へbind。`LM_RUNTIME_HOST=maritime`、`LM_RUNTIME_TENANT_ID`、`LIFE_MANAGER_OCCURRENCE_ID`、`LM_RUNTIME_DATE_KEY`を渡す。Local専用wrapperは個人env読込前にT09のcloud_cycle.pyへdelegateし、T09未実装なら実行不可を明示する。
**Depends:** T02。

- [ ] T07.1 既存scriptの`HOME/.local/state`、`.env`読込、mutable source要求、`/opt/homebrew`、Browser CDP呼出しを列挙し、変更対象行だけを`readiness.json.host_dependencies`へ記録する。
- [ ] T07.2 `test_cloud_paths.py::test_cloud_state_and_notifications_are_tenant_scoped`を追加する。temporary HOMEとtenant A/Bを使い、A実行でB/private .env/親HOMEへのwrite=0、DaisのTelegram送信=0、source repo mutation=0をassertする。provider/model呼出しはstubする。既存Localのdefaultは維持する。
- [ ] T07.3 上記path/envを先に尊重する最小変更をする。Cloud callerは`LM_RUNTIME_HOST=maritime`、`LIFE_MANAGER_RELEASE_ROOT=/app`、`LIFE_MANAGER_STATE_HOME=/data/<tenant>`、`LIFE_MANAGER_BUILD_WORKSPACE=/data/<tenant>/build`を指定する。Cloudではprivate .env読込・Dais宛Telegram・owner sourceへのcommit/push/selfhealを実行しない。Localの`LIFE_MANAGER_SOURCE_REPO`書込み/固定origin検査はLocal経路に残し、Cloudは指定tenant build workspaceだけを書込み先にする。業務判断にはtenantのbinding/receiptだけを渡し、publish_prepare/finish、frozen_guard、売上証拠の既存契約を維持する。
- [ ] T07.4 repo rootで`python3 -m unittest discover -s skills/capafy-autopublish/test -p test_cloud_paths.py`、`bash -n skills/self/capafy-loop/capafy-loop-daily.sh skills/capafy-autopublish/scripts/daily_loop.sh`を実行する。期待=全assertion PASS、syntax exit0。対象差分をcommit/pushする。

## Task T08: account・browserのCloud準備を実測する

**Files:** `docs/distribution/maritime/week1/readiness.json`、Modify `lib/browser-auth-session-store.js`/既存browser adapterは不足する注入箇所だけ。
**Interfaces:** `BusinessBinding`をtenantのprovider accountへjoin。Produces `{linux_runtime,browser_attach,provider_auth,prepare,finish,readback}`の結果と証拠参照。
**Depends:** T07。実行者のcredential SSOT/registry事前確認が必要。

- [ ] T08.1 private SSOTでservice完全一致を調べ、登録済みCapafy/browser/Maritime/model/Resendの有無とownerをsecret値を出さず確認する。specにないことを未登録の根拠にしない。
- [ ] T08.2 founder用と新利用者用のbindingを別々に作り、既存Steel/CDP adapterへ同じtenantのsessionだけを渡す。Macの`:9222`をCloudのlocalhostと解釈しない。
- [ ] T08.3 Linux隔離環境でread-onlyのinventory/statusまでを一回通す。認証切れ、macOS必須処理、provider本人手続きはfield別に記録し、別tenant sessionへfallbackしない。
- [ ] T08.4 focused isolation case `tenant_b_cannot_use_tenant_a_capafy_session`をPASSにしてcommit/push。provider認証未完の人も商品生成と報告は開始できるが、販売済みと表示しない。

## Task T09: tenantごとに既存factoryを一度呼ぶwrapperを作る

**Files:** Create `skills/capafy-autopublish/scripts/cloud_cycle.py`、`skills/capafy-autopublish/test/test_cloud_cycle.py`。既存factory/runnerを呼ぶ。
**Interfaces:** CLI `python3 .../cloud_cycle.py --tenant <uid> --occurrence <id> --date YYYY-MM-DD`。envにstate/build workspace/binding参照。stdoutは`CycleResult`一件、raw prompt/secretなし。
**Depends:** T07/T08。T08の認証待ち中はsourceを先行し、実環境受入をT08より先に完了扱いしない。`run_cycle(tenant_id,occurrence_id,date_key,*,env,data_root,runner)`を定義し、Cloud専用`AGENT_RUNNER_CONFIG`を必須にする。既存Local configへfallbackしない。

- [ ] T09.1 test `cycle_calls_existing_factory_once_and_scopes_workspace`を定義。spawn先が既存entry、cwd/stateがtenant以下、timeout後の外部effectはunknownというassertを置く。
- [ ] T09.2 wrapperは既存`run_agent.sh`へ`--task-class application-lane-agent --evidence-dir /data/<tenant>/evidence/<occurrence> --task-label maritime:<occurrence> --loop capafy --schema /data/<tenant>/receipts/<occurrence>/pass.schema.json --workdir /data/<tenant>/build --print-result`を渡す。stdinには既存factory skillと同tenant binding/receiptから作る業務promptを渡す。modelによる案件選択・original商品生成を既存runnerへ任せ、第二のpublisher/固定ニッチ選択器を作らない。pass.schema.jsonは既存capafy-loop-pass.schema.jsonを読み、Cloudのevidence項目だけをtenant workspace内のliteral absolute pathに制約して作る。説明文＋パスを許可しない。パスの実在・tenant境界は受信時にも確認する。既存pass JSONをwrapperでCycleResultへ変換し、stdoutへraw runner logを混ぜない。child envはOS最小値とtenant専用`LM_CLOUD_MODEL_API_KEY`だけを許可し、既存runner configのenv_keyを同名へbindする。親のsecret/台帳を丸ごと継承しない。HOME/CODEX_HOME/CLAUDE_CONFIG_DIR/evidence/tmp/台帳/factory stateはresolve後もtenant以下であることをdispatch前に確認する。保存済みreceiptの再生でも許可field・型・status・artifact境界を検査し、破損時はunknownを返して再実行しない。
- [ ] T09.3 provider未接続ならoriginal artifact生成を継続し、publish未実行をreceiptへ明記する。founder catalog/seller ID/売上を新規利用者へ複製しない。接続済みではsplit publishの正規経路へ進む。
- [ ] T09.4 `python3 -m unittest discover -s skills/capafy-autopublish/test -p 'test_cloud_cycle.py'`でfocused casesを確認しcommit/push。

## Task T10: provider売上をtenantのFinancialRecordへ結合する

**Files:** Modify `apps/life-manager/lib/financial-record-capafy.js`/`financial-record-capafy.test.js`、`cloud_cycle.py`、既存`capafy_hourly_reconcile.py`は明示binding注入が必要な箇所のみ。
**Interfaces:** T10Aは`readCapafyFinancialRecords({binding,periodStart,periodEnd},{readOfficialSnapshot})`を既存financial moduleへ追加する。trusted collectorを必須にし、tenant/provider subject/期間/complete/金額/証拠を検査してから既存`capafyRowsToFinancialRecords`へ渡す。FinancialRecord.subject_idはtenantId、binding.subjectIdはprovider所有者参照として分離する。T10Bは既存Python reconcileへ`read_owned_sales_snapshot(binding,period_start,period_end,*,access_token,web_token,observed_at)`と`--tenant-snapshot`を追加する。credentialはstdinのみで渡す。GET /agent/account/profileのuserIdとweb tokenのsubを照合し、同tokenの公式seller trend成功・指定期間・日別coverage・合計一致を確認する。中央worker以外へ認証を渡さない。
**Depends:** T09。

- [ ] T10.1 test `incomplete_or_foreign_provider_snapshot_never_becomes_verified_revenue`を定義。所有者不一致/欠落/不正金額は0にもverifiedにもならない。
- [ ] T10.2 既存reconcileの公式HTTP読取と明示された同tenant credentialを使う。`--money --json`は月次aggregateで日別rows/ownerを返さないため、そのままdaily snapshotとして変換しない。公式snapshotのowner・期間・receipt referenceを保持し、推定model費用と請求済み費用を分ける。
- [ ] T10.3 中央workerのtrusted collectorが`{tenantId,provider:"capafy",subjectId,observedAt,periodStart,periodEnd,complete,rows,evidenceRefs}`を公式APIから作る。モデルが書込み可能なVM provider.jsonをverified売上の根拠にしない。factoryのartifact receiptと公式会計snapshotを分離し、中央NodeがtenantId/subjectId/期間/complete=trueを照合してからverified gross/refundを既存FinancialRecordへ変換する。入金はpayout receiptがある時だけ、費用欠落時のnetはunknown。同じprovider売上を複数利用者へ付けない。
- [ ] T10.4 focused conversion testとfixture readbackを確認してcommit/push。catalogのmissing表示はT22の実証後まで変更しない。

## Task T11: Managerのcycleを既存runtime jobへ登録する

**Files:** Modify `lib/maritime-manager-runtime.js`/test、`lib/maritime-manager-store.js`/test、`config/loop-adapters.json`、`scripts/runtime-up.js`、`lib/effect-reconciler.js`/test。Create `migrations/2026-10-20-lm-maritime-runtime-executions.sql`。
**Interfaces:** `buildMaritimeManagerCycleJob({tenantId,occurrenceId,dateKey,releaseSha})`、`createMaritimeManagerLoopAdapter(services)`。capability=`maritime.manager.cycle`、既存adapterのplan/execute/reconcile/verify/reportを実装。同fileに`buildMaritimeManagerProvisionJob({tenantId,releaseSha})`/`createMaritimeManagerProvisionAdapter(services)`と`buildMaritimeManagerReportJob({tenantId,periodKey,releaseSha})`/`createMaritimeManagerReportAdapter(services)`を置き、`maritime.manager.provision`/`maritime.manager.report`を中央workerだけに登録する。provisionはT15 transport、reportはT19配信をinjectし、未注入なら実行前に失敗させる。
**Depends:** T09/T10。

**Source依存の区別:** T11A=store/SQL・stable builders・cycle契約（main統合済み）。T11B=provision/cycle/report adapterと中央worker wiring（T15/T16、reportはT18/T19のsourceを消費）。T13/T12がT11Bを待つ循環は作らない。実VM/自然実行の受入は全wiring後に確認する。

- [ ] T11.1 test `same_occurrence_is_one_runtime_job`を定義。stable job/effect keyがtenant+occurrenceにbindし、別tenantでは異なることをassert。
- [ ] T11.2 `buildRuntimeJob`と既存queue/leaseを使う。factoryを長時間HTTP request内で実行せず、中央jobからMaritime公式detached execへ一度dispatchし、executionIdを既存jobのreceipt/stateへpersistしてpollする。既存workerのlease heartbeatを維持し、次wakeをpersistする。T11Aとして、既存storeへ`claimCycleDispatch({uid,agentId,occurrenceId,dateKey,releaseSha}) -> {claimed,row}`、`readCycleDispatch(identity)`、`bindCycleExecution({...identity,executionId})`を追加する。専用tableはuid+occurrenceにagent/date/releaseと不変のexecution IDだけを保存し、終端state/receiptは既存runtime queueに残す。新規claim成功の同じ呼出しだけがdispatch可能。既存rowでexecution IDが未記録ならunknownを保持して再dispatchせず、記録済みなら同IDをpollする。SQL claimはactiveで停止されていない同tenant/agent/releaseだけを許可する。cycle adapterのexecuteは既存checkpointを先に読み、fresh claimだけdispatch、直後にexecution IDを保存して一回だけ状態を読む。実行中はpending codeで既存queueのreconcilingへ戻し、単一workerを長時間占有しない。停止後も既存executionの読取は継続する。reconcile(job)はread-onlyでpresent/pending/unknownを返し、pendingをunknown agingや再dispatchへ変換しない。完了はexitCode=0と同tenant/occurrence/date/releaseの保存済みcycle envelopeを照合し、売上は別の公式collectorだけから取得する。
- [ ] T11.3 `runtime-up.js`のservicesByAdapterへ`dispatchCycle/readExecution/readCycleReceipt`を注入する。storeに`listPending(limit)`を追加し、enroll後enqueue前に落ちたpending rowを既存stable provision jobへ戻す有限reconcileをworkerの既存pollで行う。同じjob keyで再enqueueし、paused/effect_unknownは新規実行へ戻さない。同workerの有限reconcileでcycle adapterを呼び、pendingはagingせず、presentは既存resolveReconciliationへ渡す。unknownは安全なerrorClass/nextActionを保存して公式readbackを続ける。factory wrapperの実行場所はMaritime VMだけとし、Railwayで同じfactoryを二重実行しない。adapter manifestにprovision/cycle/reportの三capabilityを別entryで追加し、既存capabilityを置換しない。provision/reportを実行できないままqueueへ入れる穴を残さない。日次金融aggregateは最新の検証済みsnapshotとして読み、更新時刻ごとにimmutable取引storeへappendしない。同じ日を別取引として重複加算しない。
- [ ] T11.4 T11Aは`node --test lib/maritime-manager-store.test.js`（既存server binariesがある環境では隔離PostgreSQLも起動し、並行claim・FK・権限・migration再適用を検証する）。adapter追加後は`node --test lib/maritime-manager-runtime.test.js lib/loop-adapter-registry.test.js`で再claim/unknown/replayのfocused casesを確認しcommit/push。

## Task T12: custom imageを同じrepoから作る

**Files:** Create `apps/life-manager/maritime/Dockerfile`、`apps/life-manager/maritime/build-context.py`、`skills/capafy-autopublish/test/test_maritime_build_context.py`。repo直下のDockerfileを新設しない。
**Interfaces:** CMDはexec形式`["node","apps/life-manager/maritime/server.js"]`。immutable code=/app、mutable state=/data。既存Node/Python/runner/browser依存だけを含める。base=node:22.23.3-bookworm-slim、Codex CLI=0.160.0、Pythonは既存requirements-runtime.txtのfactory関連locked依存を使う。browser binaryの実attachはT08で別途確認し、インストール済みと偽らない。
**Depends:** T09/T13のsource。T11全worker wiringの完了待ちは不要。先にHTTP serverのsourceを完成させ、存在しないCMDをbuildしない。

- [ ] T12.1 Docker daemonのread-only preflightを`docker info`で確認する。現在はCLIあり・socketなしを観測済み。代替buildは公式Maritime dashboardのDeploy sourceでZIPの受付field/送信先/build statusを確認し、`readiness.json.build_route`へ契約を保存する。公式CLI文書の`--source`はtemplate/github/dockerのみなので、`--source zip`など未確認flagを作らない。実UI/APIがZIPを受け付けない場合はそのexact応答を記録し、既存GitHub CIで専用Dockerfileをbuildしてpublic GHCR digestを供給する最小workflowへT12だけを更新する。primaryがこの境界を閉じ、他taskの完了を偽装しない。
- [ ] T12.2 `test_maritime_build_context.py::test_zip_contains_only_tracked_release_and_root_dockerfile`を追加する。指定commitのtracked fileのみ、archive直下Dockerfileは専用Dockerfileと同一、.env/credential/profile/state/.git/worktreeは0件、通常repo直下には新Dockerfileなしをassertする。
- [ ] T12.3 `build_context(repo: Path, release_sha: str, output_zip: Path) -> dict`を`build-context.py`へ実装する。`git archive <verified-main-sha>`から展開対象を取り、専用Dockerfileだけをarchive直下へ複製する。CLI=`python3 apps/life-manager/maritime/build-context.py --release <main-sha> --output <private-build-dir>/maritime.zip`。ZIPは500,000,000 bytes compressed/2,000,000,000 bytes unpacked未満を検証し、secret/state/private profile/memory・env・credential・symlinkをarchiveへ含めない。公開vendorの`packaging/publish/profiles`のPython sourceと`packaging/runtime/profiles`のPython source/4宣言JSONは実装なので保持し、展開ZIPで既存publisher importを確認する。既存outputは上書きしない。未merge commitをorigin/main ancestry検査で拒否し、working tree/untracked fileを読まない。ZIP deployでは.dockerignoreが無視されるため、これに除外を任せない。
- [ ] T12.4 公式ZIP buildがagent作成時に始まる場合は、既存Auth userとensureWebUserで同じowned web UIDを解決し、Freeの既定2GB/5GB・追加課金resource指定なしのowned preflight VMを一件だけ作る。UID/SHA/relay URLとunbound bootstrap tokenだけをinitialEnvVarsへ渡し、customのuseMaritimeLlm:trueを明示。create前にowned end-user/agent一覧とprivate fenceを確認し、応答喪失は同externalId GETで回収する。未bind bootstrap tokenは中央wakeに使えず、T16でagent-bound tokenへ更新する。public flag/利用者計測は有効化しない。専用DockerfileへNode floor、Python、Bash、ca-certificates、既存locked dependencies、exec形式CMDを定義する。`docker build -f apps/life-manager/maritime/Dockerfile -t life-manager-maritime:<sha> <sanitized-context>`を実行する。Docker daemonが使えない場合は、T12.1で確認した公式ZIP build経路に同じZIPを渡す。private registry未対応なので、private image URLを架空に設定しない。
- [ ] T12.5 repo rootで`python3 -m unittest discover -s skills/capafy-autopublish/test -p test_maritime_build_context.py`を実行し、PASSを確認する。build receiptへsource SHA/archive SHA256/image digest/loaded CMDを残してcommit/pushする。既存RailwayのRailpack/rootDirectory/startCommandを変えない。

## Task T13: Maritime health/chatの薄いHTTP入口を作る

**Files:** Create `apps/life-manager/maritime/server.js`/test、`runtime-env.js`/test、`run-cycle.js`。`prepareMaritimeRuntime({env,baseConfig,dataRoot,releaseRoot})`をserver起動とdetached execの両方で呼ぶ。server内のprocess.env変更だけでは別exec processへ伝わらないため、`run-cycle.js`で同じtenant config/envを構成して既存Python wrapperへexecする。
**Interfaces:** `createMaritimeManagerServer({config:{tenantId,releaseSha,modelReady},relayWake,relayTimeoutMs})`。固定prompt=`lm:cycle`/`lm:report`かつsource=`scheduled`だけ`relayWake({tenantId,releaseSha,kind},{signal})->{accepted}`へ通知する。default10秒・最大25秒、8KiB入力上限。requestのtenant/release/shellは採用しない。GET `/health`、POST `/chat`、GET `/schedules`。bind `0.0.0.0:Number(process.env.PORT)`。healthは外部作用なし。
**Depends:** T11A（store/builder/cycle契約）のsource。T11のprovider/worker wiringやT12の実image buildを待たず、handlerのsource/fixtureを完成させる。

- [ ] T13.1 test `health_is_pure_and_chat_returns_before_factory_finishes`を定義。factory promiseが未完でもchatが30秒未満で受付応答し、healthではjob0件。
- [ ] T13.2 startup時に、このagentへMaritimeが注入した`OPENAI_API_KEY`/`OPENAI_BASE_URL`を既存runner用のtenant configと`LM_CLOUD_MODEL_API_KEY`へbindする。既存config schemaを再利用し、現在のapplication-lane先頭Codex candidateのmodel/effortを保持してcloud profileだけを割り当てる。meteredと記録しsubscription quotaを複製しない。既存runnerが要求するauth_fileはtenant以下の空JSON markerに向け、key値はconfigにもmarkerにも保存しない。Macの認証/profileや第二のmodel routerを持ち込まない。必須値欠落はhealthのreadinessへ明記し、Local routeへfallbackしない。POST `/chat`のscheduled promptはkind=`cycle|report`の内部wakeへ変換し、同tenant tokenでRailwayの`/api/internal/maritime/wake`へ通知して受付状態を返す。VMへDB credentialを渡さず、requestに任意tenantや任意shell commandを指定させない。
- [ ] T13.3 envにbindしたtenantとrelease、`LM_WAKE_RELAY_URL`/tenant限定`LM_WAKE_RELAY_TOKEN`だけを使い、GET `/health`は`{ok:true,releaseSha}`を返す。公開bodyにsecretや他tenantを含めない。`/schedules`を除く外部操作へユーザー指定shellを通さない。
- [ ] T13.4 `node --test maritime/server.test.js`と実port health確認を行いcommit/push。

## Task T14: 休眠しても起きるscheduleを公開する

**Files:** Create `lib/maritime-manager-schedules.js`/test、Modify `maritime/server.js`/test、runtime adapter/test。既存`user-tz.js`と`honne-ja-shadow-schedule.js::zonedSlotInstant`でtimezoneを扱い、別schedulerは作らない。
**Interfaces:** `/schedules` returns `{id,nextRunAt,prompt,enabled}`の配列。永続snapshotは`/data/<tenant>/maritime-schedules.json`。`transport.writeScheduleSnapshot({uid,agentId,snapshot})`は公式files/writeでこのpathだけを更新し、serverは各GETで読み直す。ID=`lm-cycle:<uid>`/`lm-report:<uid>`。nextRunAtはpersisted UTC instant。保存envelope=`{schema_version:1,tenantId,releaseSha,paused,schedules}`、最大cycle/report各1件。`projectMaritimeSchedules({tenantId,releaseSha,status,pausedAt,nextEligibleAt,timezone,nowMs})`が投影を返し、`readMaritimeSchedules({tenantId,releaseSha,dataRoot})`は毎回同tenantのfileを読んで配列だけを返す。未作成は空配列、破損・別tenant・symlinkは503として既存wakeを誤解除しない。
**Depends:** T13。

- [ ] T14.1 test `schedules_publish_persisted_next_occurrence_and_pause_removes_it`を定義。server再起動後も同じnextRunAt、pausedは配列から消える。
- [ ] T14.2 既存loopのnextEligibleAtをscheduleへ投影する。日次reportは利用者のtimezoneの19:00、既存zonedSlotInstantで次のUTC instantを計算して保存する（入力を追加しない）。setIntervalだけで定期稼働を保証しない。
- [ ] T14.3 scheduled requestを受けた後、同じoccurrenceは既存job/receiptでdedupし、処理結果から次のscheduleを更新する。失敗時は既存retry/backoffを再利用。
- [ ] T14.4 focused sleep/resume fixtureをPASSにしcommit/push。実際の休眠wakeはT22で確認する。

## Task T15: custom containerのcreateをidempotentにする

**Files:** Create `lib/transport/maritime-manager.js`/test、Modify manager storeのbinding。
**Interfaces:** `createMaritimeManagerTransport({env,fetchImpl,client,managerStore,getWakeBinding,loadSdk})`は`ensureAgent({uid,uploadS3Key,archiveSha256,releaseSha}) -> {agentId,status}`、`readAgent({uid,uploadS3Key,archiveSha256,releaseSha}) -> {agentId,status}`（provider読取と既存binding回収のみ、POST createなし）、`configureWake({uid,agentId,releaseSha})->{agentId,status}`（active bindingだけSDK setEnv secret/reload、health検証とは分離）、`dispatchCycle/readExecution`（固定する境界参照）、`readCycleReceipt({uid,agentId,occurrenceId}) -> {dateKey,releaseSha,result}`（保存envelope。`result`は公式executionのcaptured stdoutのJSONと一致させる。providerSnapshotは中央collectorから別取得）、`writeScheduleSnapshot({uid,agentId,snapshot}) -> {ok}`をproduces。receipt/schedule pathはtenant/occurrenceから構成し、request指定の任意absolute pathを受けない。`managerStore`は既存read/claimProvision/bindAgent、`getWakeBinding({uid,releaseSha})->{url,token}`はT16のtenant固定relay設定をinjectする。初期envにUID/SHA/relayを渡し、custom framework/HMAC externalIdと非secret UID/source SHA/archive SHA256の公式env readbackを照合してからbindする。SDKが持つagents.get/listEnv/files.download/writeを再利用し、SDK未対応のend-user custom createとdetached execだけ公式RESTを直接呼ぶ。
**配備契約:** 公式Agent応答とdeployment履歴はimageName/image digestを公開しない。実運用で成功したZIP buildを使い、private uploadS3Keyとarchive SHA256をsource SHAへ固定する。archive hashをimage digestとは呼ばない。env readbackは配備設定の確認であり、実コードの確認はT16/T22のhealthとsource-byte probeを別に行う。
**Depends:** T03/T12/T13。

- [ ] T15.1 test `custom_create_never_uses_default_openclaw_and_lost_response_does_not_recreate`を定義。POST body `framework:'custom'`、main由来ZIPの`uploadS3Key`（private）と`archiveSha256`、HMAC externalId、response喪失後はlistのみをassert。
- [ ] T15.2 custom createは公式RESTのidempotent `POST /api/v1/end-users/{external_id}/agents`を最小fetchで呼ぶ（初回201、再呼出200）。external_idはtenantからHMACで導出し、lost responseは同end-userのGETで回収する。Maritime metered modelを使うpilotでは`useMaritimeLlm:true`を明示する（customの既定ではmodel keyが注入されない）。既存SDKのprovision defaultへcustom imageを混在させない。list/secrets等の対応済みmethodはSDK再利用、maxRetries=0。公式execは`POST /api/agents/{id}/exec`へ`{command:["node","/app/apps/life-manager/maritime/run-cycle.js","--tenant",uid,"--occurrence",occurrenceId,"--date",dateKey],detached:true,timeout:3720}`。202のexecutionIdを保存し、`GET /api/agents/{id}/exec/{executionId}`で終端を読む。
- [ ] T15.3 create前にstore.claimProvisionを取り、同externalIdの既存agentを読む。通信喪失時は`effect_unknown`を保存し、readbackで同agentをbindするまで再createしない。exec POSTのresponse喪失も再POSTせず、`/data`の同occurrence receiptとprovider readbackへ進む。execution 404は実行失敗の証明にしない。
- [ ] T15.4 `node --test lib/transport/maritime-manager.test.js lib/maritime-manager-store.test.js`を確認してcommit/push。

## Task T16: secretと初回wakeを同tenantへ配線する

**Files:** Create `lib/maritime-manager-wake.js`/test。Modify `server.js`、transport/runtime/authのservices wiring、`scripts/runtime-up.js`。
**Interfaces:** `createMaritimeWakeBinding({uid,releaseSha,agentId}, {secret,publicOrigin})->{url,token}`、`verifyMaritimeWakeToken(token,secret)->{uid,agentId,releaseSha}|null`、`buildMaritimeInitialJobs(enrollment)->{cycle:{job,availableAt},report:{job,availableAt}}`、`handleMaritimeManagerWake(req,res,options)->boolean`。POST `/api/internal/maritime/wake`は署名headerからuid/agent/releaseを解決し、bodyはkindだけを使う。初回jobのID/date/availableAtはenrollment.created_atから固定し、繰返しwakeで新しいcycleを増やさない。継続仕事/次日報はT11Bの既存queue continuationで直列化する。activate→provision→setEnv(secret)→health→initial cycle enqueue。relay tokenは一tenant/agent/releaseへbindし、中央endpointで照合する。専用`LM_MARITIME_MANAGER_ID_SECRET`をprivate SSOTからserver/workerへ注入し、既存global LM_UID_SECRETは置換しない。作成時はunbound bootstrap token、bind後は署名にagentIdを含むtokenへ更新してreloadする。VM image source SHAは中央app SHAと別に`LM_MARITIME_MANAGER_IMAGE_RELEASE_SHA`で明示し、image receiptと同じ値をenrollment/jobへ渡す。bind済みagent以外へsetEnvしない。
**Depends:** T05/T08/T14/T15。

- [ ] T16.1 test `activate_to_first_cycle_binds_one_user_one_agent_without_goal_budget`を定義。二回activateしても一agent/一initial occurrence。
- [ ] T16.2 暗号化per-agent envへtenant-specific参照と必要最小credentialを設定しreloadする。共通service-role key/全credential fileを利用者VMへ配らず、上記wake relayだけを許可する。新しいtokenはprivate credential SSOTへ保存し、repo/chatへ出さない。
- [ ] T16.3 healthのloaded source SHAと配備ZIPのarchive SHA256設定を読んで、正しいbindingへ初回cycleをenqueueする。`server.js`にrelay handlerをmountし、header tokenのhash照合→同bindingのuid/agent解決→allowed kind/occurrence検証→既存queueへのenqueueのみを行う。request bodyのuidは受け付けない。public URLを知るだけで他tenantのcycleを呼べない認証を維持する。
- [ ] T16.4 focused end-to-end fixtureを確認しcommit/push。fixture成功は本番業務完了と呼ばない。

## Task T17: browser実行とprovider公開を一件完走する

**Files:** 既存browser/session adapterとCapafy split scripts。ModifyはT08で特定した不足箇所だけ。
**Interfaces:** CycleResultにofficial `agentId/version/status/receiptRef`を結合。provider作用のownerを一つにする。
**Depends:** T16/T11 worker wiringとT22.1の非公開foundation deploy。

- [ ] T17.1 自分がownerの接続済みtenantで新規original商品を一つ選び、既存frozen_guard/duplicate_gateを通す。既存sellerを編集しない。
- [ ] T17.2 既存prepare→CP1→finish→CP2/CP3を一回実行する。途中で応答不明ならofficial readbackへ進み、publishを再送しない。
- [ ] T17.3 同じagent/versionのofficial status、公開URL、申請中/公開済みの区別をreceiptへ記録する。審査待ちを販売可能と呼ばない。
- [ ] T17.4 receiptとsource差分を分離して保存し、自己所有の不足修正だけをcommit/push。provider審査は進行中でも他taskを進める。

## Task T18: 初日から役立つ日次結果を組み立てる

**Files:** Create `lib/maritime-manager-report.js`/test。Reuse financial conversion、`cfo-result-summary.js`、既存action receipts。
**Interfaces:** `buildMaritimeDailyResult({enrollment,periodKey,actionReceipts,financialRecords,costs}) -> DailyResult`、`renderMaritimeDailyEmail(result) -> string`。
**Depends:** T10/T11Aのsource。T17の売上発生は待たない。

- [ ] T18.1 test `daily_result_separates_artifact_publish_sales_payout_and_unknown_cost`を定義。商品作成だけなら売上0の観測がある場合のみ0、未取得は未確認、費用欠落で利益unknownをassert。
- [ ] T18.2 action receiptから「何を作った/公開した/保留中か」を構成し、gross/refund/known cost/payoutを別表示する。私用Moneytree/Dais balanceは参照しない。
- [ ] T18.3 日次copyを「今日実行したこと／確認できた成果と売上／費用／未完・失敗／次に進めること」に固定し、URLは同tenantのartifact/provider evidenceだけにする。
- [ ] T18.4 focused report testと二通貨/日付またぎを確認しcommit/push。

## Task T19: 日次メールを既存CFO配信へ接続する

**Files:** Modify `maritime-manager-report.js`、`runtime-up.js`。Reuse `cfo-cloud-delivery.js`/`mail-resend.js`。
**Interfaces:** `deliverMaritimeDailyResult({enrollment,result,observedAt},deps)`→既存`deliverCloudCfoEmail({uid,periodKey,message,observedAt,recipient})`。
**Depends:** sourceはT18。実送信の受入はT16のtenant binding/worker wiring後。

- [ ] T19.1 test `daily_email_replay_returns_original_provider_id`を定義。同uid+periodKeyを二回実行してResend send1回、異なるrecipientへpending receiptを再利用しない。
- [ ] T19.2 既存永続receipt、provider idempotency、23h guardをそのまま使う。新しいメールoutbox/別providerを作らない。
- [ ] T19.3 送信後timeoutはprovider message/receiptをreadbackし、24hを超えた送信再試行はしない。API acceptedと受信箱着信を区別する。
- [ ] T19.4 `node --test lib/maritime-manager-report.test.js lib/cfo-cloud-delivery.test.js lib/mail-resend.test.js`で確認しcommit/push。

## Task T20: 停止が次の仕事と配信に効くようにする

**Files:** Modify auth/store/runtime/report、existing consent/stop経路。
**Interfaces:** authenticated POST `/maritime/stop`→paused、schedule除去、未claim job停止。進行済みeffectは公式readback継続。
**Depends:** T14/T19。

- [ ] T20.1 test `pause_blocks_next_job_and_report_but_preserves_inflight_receipt`を定義。他tenant停止不可、停止後新規publish/send0件、進行済みreceiptは保持。
- [ ] T20.2 既存consent revokeとenrollment.pauseを接続し、中央のjob claim/dispatch/report直前にもpausedを読む。停止を既送信データ削除と表示しない。
- [ ] T20.3 provider側に保存済みデータ・VMの削除は停止と分け、削除を勝手に実施しない。scheduled wake snapshotから停止分を外す。
- [ ] T20.4 focused stop testを確認してcommit/push。

## Task T21: 登録・実業務・再利用を既存funnelへ記録する

**Files:** Modify `apps/life-manager/lib/web-funnel-events.js`/`web-funnel-events.test.js`、`maritime-distribution.js`/test、auth/runtime/report call sites。
**Interfaces:** events=`maritime_email_verified|maritime_manager_activated|maritime_work_completed|maritime_report_sent|maritime_returned`。source_object_id=既存HMAC participant ID。
**Depends:** T05/T11/T19。

- [ ] T21.1 test `manager_usage_is_not_signup_and_analytics_has_no_email_or_body`を定義。signupだけではwork_completed0、再送はmilestone1件、email/token/本文なし。
- [ ] T21.2 既存WEB_FUNNEL_EVENTSへevent名を追加し、既存record関数で記録する。true sourceのDM/X/IG/community別UTMを維持する。
- [ ] T21.3 founder/team/fixtureを外部userと別集計し、公式Keiki/Maritime project usageへの対応キーをprivate receiptで保持する。
- [ ] T21.4 focused event/distribution testを確認しcommit/push。独自analyticsサービスや新dashboardは作らない。

## Task T22: main由来の実環境で一人分を閉じる

**Files:** Create `scripts/maritime-manager-readback.js`/focused test。Modify catalogのCapafy readinessは確認できた項目のみ。
**Interfaces:** sanitizeされた`{releaseSha,imageDigest,agentId,uidHash,loadedSha,workReceipt,emailReceipt,nextWake,usage,costStatus}`。
**Depends:** T22.1は各taskのsource統合（T11B/T12/T15/T16/T19/T20/T21/T32）後。T22の完了はT17とメール/停止/計測の自然readback後。T17をT22.1 deployより先に要求しない。

- [ ] T22.1 全source acceptanceとexact-head CIを確認しmainへ統合する。immutable imageをmain SHAから作り、DB migration履歴とapply結果を読む。公開flagをoffに保ち、central worker/relayとowned tenantの非公開foundationを先にdeployし、その後T17の実業務とT19の着信を確認する。
- [ ] T22.2 登録→自律job→provider結果→日次メールを自分の別Cloud tenantで一回実行する。Macのloopやbrowserを止める破壊的検証はせず、Cloudのargv/state/network evidenceでMac非依存を確かめる。
- [ ] T22.3 正規sleep後のscheduled wakeを一回観測し、同occurrenceの公開/送信が増えないことを読む。メール着信/送信provider ID、official usageとloaded SHAを結合する。
- [ ] T22.4 readiness/capacity/費用/未接続条件を正本へ更新。全14loopsをCloud完成扱いにせず、実証したCapafy範囲だけcatalogへ反映する。

## Task T23: 動く製品を正式経路へ提出し受付を保存する

**Files:** Create `scripts/maritime-week1-export.js`/focused test、`docs/distribution/maritime/week1/submission.json`、submission-checklistの状態更新。
**Interfaces:** aggregate-only export。`{product_url,demo_url,release_sha,official_required_fields,user_counts,work_receipts,costs,limitations,submission_receipt}`。個人データなし。
**Depends:** T01/T22。T25の豪華な完成動画/3人feedback/売上/7日継続は待たない。

- [ ] T23.1 export test `packet_uses_measured_counts_and_excludes_private_users`を定義し、公式必須項目と実測項目だけをJSONへ出す。未測定はnull+理由。
- [ ] T23.2 審査者が試せるURL、最小画面録画、Cloud実行receipt、現状の人数、制約を揃える。内部2–3分動画は推奨で、公式指定と混同しない。
- [ ] T23.3 正式form/channelのduplicate submission状態を読み、確定したpayloadを一回提出する。未送信draftを提出済みと呼ばない。正式経路が不明ならその不足だけを保持し他taskを続ける。
- [ ] T23.4 confirmation画面/受信メール/受付IDを保存し、本文・提出時刻・release SHAをjoinする。UI timeout時はreadbackし再submitしない。これで初週提出を完了とする。

## Task T24: Daisがすぐ使える配布copyを作る（開発と並行）

**Files:** `docs/distribution/maritime/week1/channel-copy.md`、source-map。
**Interfaces:** 家族/友人DM、X日英、IG DM/Story caption、返信テンプレ。公開URL確定前/後でclaimを分ける。
**Depends:** なし。最初の文案は本計画と同時に作成する。

- [ ] T24.1 source-mapのArc/Panda/Pokeを読み、模倣する導入・成果の見せ方・CTAと、同じ対象でない証拠の限界を記録する。
- [ ] T24.2 「Managerが自分で仕事を進める」「無料pilot」「試せる一つの業務」「一つのURL」を含むDM/X/IG文案を日英で用意する。利益保証/架空testimonial/架空実績を書かない。
- [ ] T24.3 source別URLを`/maritime?source=referral|x|other`+既存UTMで指定する。IGは現source allowlistではotherにし、utm_source=instagramで詳細を残す。emailや知人名をURLへ入れない。
- [ ] T24.4 DaisへのDM用文案を成果物として渡す。送信/友人の返事を待たずT25/T26へ進む。最終URLを確認してplaceholderがない版を保存しcommit/push。

## Task T25: demoとプロモーション動画の撮影単位を作る（開発と並行）

**Files:** `docs/distribution/maritime/week1/demo-script.md`、実行時に既存video workspaceへBRIEF。新video rendererは作らない。
**Interfaces:** 30秒縦動画と2分審査demo。共通captureから切り出す。UI mockとlive画面は明確に区別。
**Depends:** なしで台本。撮影は該当実装が動いた時点。

- [ ] T25.1 台本を「メール登録→指示なしで仕事開始→成果物/公開結果→日次メール→試すURL」の5shotへ固定する。
- [ ] T25.2 各shotの対象route/receipt・画面に出してよい情報・未実装時の表示をshot listへ書く。ユーザー売上がない時にfounder売上をユーザー実績として置かない。
- [ ] T25.3 実装が動いたshotから順次captureし、既存HyperFramesのskill/CLIで字幕・縦動画へ編集する。新撮影のために友人3人を待たない。
- [ ] T25.4 音なしでも理解できる30秒版、音声付き2分版、サムネイル、投稿captionを一packageにし、CTA・正しいURL・実画面の確認後commit/pushまたは既存artifact storeへ保存する。

## Task T26: 入口と公開説明を同じ製品へ揃える

**Files:** Modify `apps/landing/marketing/pages/life-manager-en.html`、`life-manager.html`、`route-manifest.json`、既存publish-overlay。
**Interfaces:** marketing CTA→稼働中`/maritime`のemail入口。既存Calendar有料導線は別で保持。
**Depends:** T06。原稿は先に用意し、実URLへの切替はT22後。

- [ ] T26.1 mainのREADME/生成正本/サイト原稿に、目標/予算入力必須・Telegram必須の主張がないことを検索する。過去submission履歴は現行sourceへ逆輸入しない。
- [ ] T26.2 Cloud無料pilotの範囲と現在動く業務をcopyへ反映する。既存Calendarの$29 trialをMaritime無料pilotの課金条件へ混ぜない。
- [ ] T26.3 既存full site exportへapproved overlayとして反映し、他商品/blog/legal/functionを保持する。manifest hashとpublished revisionを更新する。
- [ ] T26.4 公開URLのemail CTA/認証/停止/localeをreadbackし、source commitとpublished SHAを結合する。source変更だけを公開完了と呼ばない。

## Task T27: 公開配布を開始する

**Files:** channel-copyの公開版、demo artifact refs、既存distribution ledger。
**Interfaces:** Dais=家族/友人DM。LM=許可済みowned X/IG等の投稿。全channelはsource別URL付き。
**Depends:** T22/T24/T26。T25完成動画は後追い可、3人の利用は待たない。

- [ ] T27.1 Daisへ実URL入りDM文案を渡し、送信はDaisの担当とする。知人リストを要求したり勝手に取得しない。
- [ ] T27.2 owner/account/既存送信ledgerを確認し、owned Xに実画面とCTAを一件投稿する。投稿不可ならexact blockerを記録し、別の準備済みchannelを進める。
- [ ] T27.3 IGのStory/Reelと関連community向けに同じ事実を媒体の形式へ変換する。community rulesと重複投稿を確認し、無差別DMを行わない。
- [ ] T27.4 permalink/provider receipt/source/copy SHAを既存ledgerへ保存し、投稿数ではなく登録→完了をT28で読む。

## Task T28: source別の最大離脱を一つ直す

**Files:** Modify `scripts/maritime-week1-export.js`、既存funnel report、該当する入口一箇所。
**Interfaces:** source cohort=`visit→verified→activated→work_completed→returned`、費用/人、time-to-first-work。
**Depends:** T21/T27。

- [ ] T28.1 source別aggregateを読み、team/test/重複を除いて最初の実利用を公式project usageへ照合する。人数が未取得なら0にしない。
- [ ] T28.2 最も人数を落としている一段を選び、route・error・滞留時間で原因を特定する。例: email着信、activate失敗、VM準備遅延、最初の成果が不明。
- [ ] T28.3 その境界のfocused回帰case→最小修正→公開readbackを一回行う。friend feedbackや7日データがなくても観測可能な不具合を直す。
- [ ] T28.4 修正前後の完了率/費用を同じwindowで保存し、完了が多いsourceへ次の配布枠を寄せる。

## Task T29: 1,000人までの運用と利益を改善する

**Files:** source-map、正本Maritime節、既存funnel/export/readiness。変更コードは実測で必要な箇所だけ。
**Interfaces:** source別実利用、official count、gross/refund/known cost/netStatus、capacity、継続。
**Depends:** T28。売上発生自体は保証しない。

- [ ] T29.1 capacityは現在のbilling/awake制限/利用者あたり費用から読み、既存capを25→100→1,000へ段階更新する。特定人数が揃うまで提出や素材制作を止めない。
- [ ] T29.2 完了・再利用・費用が良いsourceを増やす。販売対象商品の成果はCapafy official visits/orders/refund等で確認し、SNS表示回数だけで施策を増やさない。
- [ ] T29.3 費用の高いwake/無成果taskを既存model判断とbackoffで減らし、実際のnetが確認できる業務へ資源を寄せる。利益不明を黒字と報告しない。
- [ ] T29.4 1,000人到達時に公式project usageと本人/重複確認を提出し、winner通知をreadbackする。SF日本発旅費/credit条件/YCは別の確認事項として保持する。

## Task T30: 稼働URLをDaisへメールで届ける

**Files:** 既存mail送信経路と`submission.json`のprivate delivery receipt参照。個人宛先/secretはrepoに保存しない。
**Interfaces:** T23の受付済みentryとT22の稼働URLをconsumes。送信先はprivate profile/credential SSOTから解決する。
**Depends:** T23直後。長期獲得T29やwinner通知を待たない。

- [ ] T30.1 稼働中のemail登録URLと無料pilotの範囲を再度GETで確認し、Dais宛先をprivate SSOTから解決する。
- [ ] T30.2 URL、できること、未接続部分、家族/友人へ転送できる短い紹介文を日本語の一通にまとめ、送信payloadを独立read-only検証する。
- [ ] T30.3 許可済みの既存メール経路でDaisへ一回送信する。provider message IDを保存し、応答不明時は再送せずreadbackする。
- [ ] T30.4 送信済みの宛先・件名・本文URLとprovider receiptを照合し、正本を更新する。API受付と着信は区別し、着信未確認ならその範囲を残す。

## Task T31: Cloud Life Manager自身の課金と利益をつなぐ

**Files:** Modify `apps/life-manager/lib/web-billing.js`/同test、`server.js`、Manager UI。Reuse既存Stripe checkout/portal/webhook、web funnel/financial records。
**Interfaces:** 既存`handleWebBillingRequest`の`resolveWebUserImpl`へ、Managerのverified email identityを専用経路で渡す。CalendarのGoogle guardは変えない。既存の価格/商品設定を公式Stripeでreadbackし、顧客の任意checkoutと署名済みwebhookだけでpaid状態を更新する。
**Depends:** T23の無料pilot提出を先行。LM自身の収益と、利用者のCapafy等の収益を混同しない。

- [ ] T31.1 既存checkout/portal価格・trial条件・支払済みinvoiceと返金を公式Stripeから読む。現在の『Stripe売上なし』はDaisの申告であり、再取得前に確認済み0/MRRと書かない。
- [ ] T31.2 email-only利用者のcheckout/portalを同じuid/CSRF/originへbindするfocused caseを書き、既存web-billingのresolver injectionを使う。任意uid/customer/priceの入力は拒否し、Calendar identityは拡張しない。
- [ ] T31.3 無料pilotを自動課金へ変えず、価値を確認した利用者が自ら選ぶupgrade入口を接続する。test modeでcheckout→webhook→本人のpaid状態を確認してから、既存価格のlive checkoutを公開する。自分のcardで架空の売上を作らない。
- [ ] T31.4 正規利用者のpaid invoice・refund・Stripe手数料・Cloud/model/mail費用をjoinし、LMの実売上/確認できる利益を報告する。free signup×価格をMRRとしない。未取得費用があれば利益は未確認とする。

## Task T32: 既存SupabaseとResendで確認メールを実際に届ける

**Files:** Read `docs/evidence/maritime/smtp-preflight.json`。Create `docs/evidence/maritime/smtp-readback.json`（設定名/成否/receipt hashのみ）。実設定はSupabase production Auth、secret値はprivate credential SSOTのみ。
**Interfaces:** T04のPKCE handlerとT22のowned inboxをconsumes。設定readbackと実メール到着をproduces。公開appのfeature flagはこのtaskでは有効化しない。
**Depends:** T04。T07–T21とは独立して進める。初回の変更前観測はemail provider=false、custom SMTPなし、送信limit2/hour。これは現状値ではない。実環境の現在状態と着信証拠はSpec正本/T32とsmtp-readback.jsonを参照する。

- [ ] T32.1 private SSOT全体と`supabase-life-manager-production`/`resend-life-manager-production`/`agentmail-life-manager-production`完全一致を読む。新key/account/inboxを作らず、既存設定をManagement API GET `/v1/projects/<ref>/config/auth`で再取得する。秘密の値を出力しない。
- [ ] T32.2 Python標準`email.utils.parseaddr(from_address)`でmailboxとdisplay nameを分ける。smtp_admin_emailにはmailboxのみ、smtp_sender_nameにはdisplay nameまたは`Life Manager`を使う。空mailboxなら設定を送信せず、既存Resendのsender設定を確認する。
- [ ] T32.3 既存uri_allow_listを全保持し、`https://life-call-production.up.railway.app/auth/maritime/confirm`だけを追記したpatchを構成する。smtp_host=`smtp.resend.com`、smtp_port=`"465"`（Management APIはstring）、smtp_user=`resend`、smtp_pass=既存key、external_email_enabled=true、mailer_autoconfirm=false、rate_limit_email_sent=30。site_url/Google/OTP limitは保持する。
- [ ] T32.4 patchの変更keyとallowlist保持をread-only検証者へ渡す。secret値は渡さない。宣言後に上記Management APIへ一回PATCHする。新しいkeyの再作成・auto-confirm有効化を修正方法にしない。
- [ ] T32.5 同じGETで全変更fieldとGoogle/site_url/旧allowlistの保持を確認し、safe JSONへ保存する。レスポンス内smtp_passは出力・保存しない。
- [ ] T32.6 既存owned AgentMail inboxへSupabaseの確認メールを一通送り、新規messageの時刻/送信元/件名で着信を確認する。OTP/リンク/本文はlog/chat/repoへ出さない。この内部testを競技利用者に数えない。
- [ ] T32.7 `smtp-readback.json`へsmtp_auth_verified/email_arrived/observed_at/provider_receipt_hash、失敗ならexact error classと次操作を書く。API acceptedやSMTP AUTHだけではemail_arrived=trueにしない。
- [ ] T32.8 `python3 -m json.tool docs/evidence/maritime/smtp-readback.json >/dev/null`とsecret混入なしを確認し、safe evidenceのみcommit/pushする。実browser PKCEからactivateまでの受入はT22で行う。

## 一件のtaskを実装するときの共通手順

1. IDとowned filesを読む。最新mainから専用worktree/leaseを取り、他ownerの差分を保つ。
2. そのtaskの最小の失敗caseを先に書く。plan中のtest名/期待値が実装契約であり、広いsuiteを無条件追加しない。
3. 既存部品を接続しfocused acceptanceを通す。sourceとprovider成果を分ける。
4. fetch→対象fileだけadd→commit→push。必要reviewとexact-head CI後にmainへ統合する。未登録checkは待つ。
5. そのtaskに含まれる実環境結果だけをreadbackし、正本の同IDを更新する。plan完了と実装完了と提出済みを分ける。

## 完了判定を混ぜない

- 計画完了: 本書・Spec・出典・配布文案がremoteへ保存され、file/署名/依存/検証の穴をself-review済み。
- source完了: taskのfocused acceptance、review、CI、main統合。公開・売上とは別。
- 初週提出完了: T22の稼働製品とT23の正式受付receipt。Top30通過は主催者通知を別途確認する。
- 競技優勝: T29で実在1,000人と公式検証・winner通知。最高利益は公式順位条件にない。
- 商業成果: 利用者のprovider事業売上はT10/T29、LM自身のStripe売上はT31、費用不明時は利益未確認。

## Coverage/self-review

- email-only/目標予算不要=T04–T06、Manager自律選択=T07/T09/T11、既存再利用=T07–T20。
- 実emailのSMTP/確認着信=T32、LM自身のStripe売上=T31。
- Cloud/port/state/sleep=T12–T17、tenant ownership/consent/stop=T03/T08/T10/T20。
- 完了/売上/費用/日次email=T10/T18/T19、source/実利用/1,000=T21/T27–T29。
- 初週form/期限/提出/receipt=T01/T23、配布文案/動画/LP=T24–T27。
- 五つのReview FocusはT04/T05/T15/T14/T08/T10/T19/T20のassertionに対応。
- 未確定の外部事実はT01/T08/T22の観測taskに限定し、曖昧な「調べる」「Cloud化する」で後続へ渡さない。
- 作成済み資料を確認しただけでproduct実装/友人利用/売上/提出済みにはしない。
