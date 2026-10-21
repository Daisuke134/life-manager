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
│   │   ├── maritime-manager-artifacts.js           [追加: 認証cookie/検証済み成果download]
│   │   ├── maritime-manager-artifacts.test.js      [download/tenant/HTTP境界]
│   │   ├── maritime-manager-wake.js               [追加: agent-bound wake→既存queue]
│   │   ├── maritime-manager-wake.test.js          [署名/停止/initial dedup]
│   │   ├── maritime-manager-schedules.js          [追加: 既存timezoneからnextRunAt投影]
│   │   ├── maritime-manager-schedules.test.js     [永続snapshot/欠損/隔離]
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
│   │   ├── server.test.js                          [health/chat/schedules HTTP]
│   │   ├── runtime-env.js                         [追加: 専用model config/tenant OS所有権]
│   │   ├── runtime-env.test.js                    [実runner profile契約]
│   │   ├── run-cycle.js                           [追加: 非root factory child]
│   │   ├── run-cycle.test.js                      [argv/環境/失敗時fallbackなし]
│   │   ├── artifact-proof.py                      [追加: no-follow/size/hashのread-only proof]
│   │   ├── artifact-proof.test.js                 [POSIX名/越境/リンク/size境界]
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
    ├── evidence/maritime/
    │   ├── current-status-20261021.json                [本番/競技/配信のreadback、未確認はnull]
    │   ├── seo-baseline-20261021.json                 [sitewide GSC baselineとquery caveat]
    │   └── stripe-life-manager-readback-20261021.json  [live prices/subscriptions、account invoice attribution caveat]
    ├── research/maritime/2026-10-20-source-map.md    [本計画の出典・模倣箇所]
    ├── superpowers/specs/2026-09-25-life-manager-unified-ssot.md
    ├── superpowers/plans/2026-10-20-maritime-week1-atomic-execution.md
    └── distribution/maritime/week1/
        ├── channel-copy.md                         [DM/X文案。Instagram配布なし]
        ├── seo-article-draft-en.md                 [未公開の検索記事草稿、CTA HOLD]
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
- [ ] T08.1a Docker image内でpin済みCloakBrowserの公式ensure_binaryを使いfree Linux binaryを/optへ導入する。root所有read-only binaryを固定/usr/local/bin/lm-cloud-chromiumへbindし、cloud_cycleは存在する固定binaryだけをchildへ渡す。既存browser-ownerのLinux起動だけheadless/dev-shm制約へ対応する。Mac profileや親browser変数を継承しない。
- [ ] T08.2 founder用と新利用者用のbindingを別々に作り、既存Steel/CDP adapterへ同じtenantのsessionだけを渡す。Macの`:9222`をCloudのlocalhostと解釈しない。
- [ ] T08.3 Linux隔離環境でread-onlyのinventory/statusまでを一回通す。認証切れ、macOS必須処理、provider本人手続きはfield別に記録し、別tenant sessionへfallbackしない。
- [ ] T08.4 focused isolation case `tenant_b_cannot_use_tenant_a_capafy_session`をPASSにしてcommit/push。provider認証未完の人も商品生成と報告は開始できるが、販売済みと表示しない。

## Task T09: tenantごとに既存factoryを一度呼ぶwrapperを作る

**Files:** Create `skills/capafy-autopublish/scripts/cloud_cycle.py`、`skills/capafy-autopublish/test/test_cloud_cycle.py`。既存factory/runnerを呼ぶ。
**Interfaces:** CLI `python3 .../cloud_cycle.py --tenant <uid> --occurrence <id> --date YYYY-MM-DD`。envにstate/build workspace/binding参照。stdoutは`CycleResult`一件、raw prompt/secretなし。
**Depends:** T07/T08。T08の認証待ち中はsourceを先行し、実環境受入をT08より先に完了扱いしない。`run_cycle(tenant_id,occurrence_id,date_key,*,env,data_root,runner)`を定義し、Cloud専用`AGENT_RUNNER_CONFIG`を必須にする。既存Local configへfallbackしない。

- [ ] T09.1 test `cycle_calls_existing_factory_once_and_scopes_workspace`を定義。spawn先が既存entry、cwd/stateがtenant以下、timeout後の外部effectはunknownというassertを置く。
- [ ] T09.2 wrapperは既存`run_agent.sh`へ`--task-class application-lane-agent --evidence-dir /data/<tenant>/evidence/<occurrence> --task-label maritime:<occurrence> --loop capafy --schema /data/<tenant>/receipts/<occurrence>/pass.schema.json --workdir /data/<tenant>/build/occurrences/<occurrence> --print-result`を渡す。`LIFE_MANAGER_BUILD_WORKSPACE`は既存catalog参照用のbuild rootに残し、`AGENT_RUNNER_WORKDIR`はoccurrence dirへ向ける。stdinには既存factory skillと同tenant binding/receiptから作る業務promptを渡す。modelによる案件選択・original商品生成を既存runnerへ任せ、第二のpublisher/固定ニッチ選択器を作らない。pass.schema.jsonは既存capafy-loop-pass.schema.jsonを読み、Cloudのevidence項目だけを新規occurrence dir内のliteral absolute pathに制約して作る。説明文＋パスを許可しない。パスの実在・tenant境界は受信時にも確認する。既存pass JSONをwrapperでCycleResultへ変換し、stdoutへraw runner logを混ぜない。child envはOS最小値とtenant専用`LM_CLOUD_MODEL_API_KEY`だけを許可し、既存runner configのenv_keyを同名へbindする。親のsecret/台帳を丸ごと継承しない。HOME/CODEX_HOME/CLAUDE_CONFIG_DIR/evidence/tmp/台帳/factory stateはresolve後もtenant以下であることをdispatch前に確認する。保存済みreceiptの再生でも許可field・型・status・artifact境界を検査し、破損時はunknownを返して再実行しない。
- [ ] T09.3 provider未接続ならoriginal artifact生成を継続する。no_opでも排他receipt claim後に新規作成したoccurrence dir内のregular・single-link・実行UID所有fileが一件以上あればdraft作成はcompletedとしてrefsをreceiptへ記録する。共有build直下の既存file/証拠なしはno_work/deferredのままとする。mtimeでは判定しない。publish/sale/入金は別の公式receiptなしにclaimしない。founder catalog/seller ID/売上を新規利用者へ複製しない。接続済みではsplit publishの正規経路へ進む。
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
- [ ] T11.3a `runtime-job-store.js`へ`claimReconcilingJobs({capabilities,tenantId?,limit})`を追加する。既存updated_atの30秒窓と同一SQLのFOR UPDATE SKIP LOCKEDで有限のreadback席を取得し、pending一件による他tenantの飢餓と複数workerの同時pollを避ける。available_atは変更しない（既存enqueue identityと継続時刻を保持）。外部effectの再実行を許可するclaimではない。
- [ ] T11.3b 同storeへ`resolveReconciliationAndEnqueue`を追加する。専用connectionのBEGIN/COMMITで既存resolveReconciliationとenqueueJobAtを原子的に呼び、同tenant/presentのみ許可する。失敗はROLLBACK/release、pool.queryでtransactionを開始しない。
- [ ] T11.3c cycle adapterのcontinuationは既存Capafy同様15分を使う。次occurrence=`slot:<UTC epoch milliseconds>`、次dueは親available_at+15分に固定し、retryでDate.nowを使わない。paused/inactive/release mismatchは新規successorなし。中央workerはreceipt verify後に既存completeJobAndEnqueueを使い、reconcile時も同じcontinuationを呼ぶ。cycle transportをservicesByAdapterへ注入してmanifestへ登録する。
- [ ] T11.3d report adapterは既存runtime queueの同tenant cycle receiptと既存FinancialRecord storeを読み、T18 builder→T19 deliveryを呼ぶ。金融は接続先アカウント明細として示し、Cloudが作った売上への帰属を断定しない。未接続/coverage不明は未確認、aggregateを新しい取引としてappendしない。reconcileはCFOのsent/provider ID/hashをread-only確認、pendingを再送しない。次の現地19時は既存DST対応projectorから決め、親dueを基準に固定する。
- [ ] T11.3e provisionは同じcapabilityのcreate/configure二つのstable jobへ分ける。createは既存ensureAgent、reconcileはreadAgentのみ。ready後のconfigure jobがschedule snapshot→bound wake reloadを行い、read-only runtime-statusがloaded healthのrelay SHA256とscheduleを照合する。reconcile内でprovider設定を変更しない。configure確認後のcontinuationが同じ初回reportをidempotent enqueueし、既存atomic completionで初回cycleへ進む（report seedは確認済みready後のみ、親再処理でも同key）。追加capability/table/schedulerなし。
- [ ] T11.3f fresh reviewのImportant4件を一回のRED→GREEN修正passで閉じる。receipt取得後のcontinuation例外はreconcilingへ戻す。configureは先読み失敗を設定前gateにしない。pending recoveryは既存terminal jobのrowを既存effect_unknownへ隔離して次tenantへ進む。画面のactiveはconfigureのcommon receipt（初回cycle/reportの永続化後）を必要にし、enrollment.activeだけでは準備中を表示する。
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

**T15追加の実測修正:** owned VMのauto-sleepでexecが503/guest_command_unavailable/execution_started:falseを返すことを確認する。公式POST startはidempotentで同VMをactiveへ戻す。追加VM/alwaysOn/addon/課金変更はしない。

- [ ] T15.5 transportの同tenant guest操作（成果物/receipt/loaded health/schedules）前に既存SDK startで復帰し、返却ID/activeを確認する。foreign入力はstart前に拒否する。
- [ ] T15.6 cycle adapterはfresh dispatch claim前にprepareCycle（loaded wake readback）を確認する。未準備ならclaim/model callなしの中央preflight receiptとしてdeferredを保存し、既存atomic continuationで観測時刻の15分後へ回す。provider実行/仕事完了として数えない。実行中のreadExecutionはuid/agent bindingを確認し、同active tenantのaccepted executionだけstartで維持する。business execの再送はしない。pausedなら新たに実行を維持せずmetadata readを続ける。これはresource lifecycle操作であり、reconcileのbusiness read-only境界を変更しない。
- [ ] T15.7 native sleeping→start→nonroot CDP/DOM成功を証拠へ記録し、cold guest/foreign/pending/no-repost回帰を確認してcommit/pushする。

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

**Files:** Create `lib/maritime-manager-report.js`/test、`lib/maritime-manager-artifacts.js`/test。Modify `lib/financial-manager-report.js`（既存formatter export）、`lib/maritime-manager-runtime.js`（既存契約parser/参照validator export）、`lib/transport/maritime-manager.js`/test、`maritime/artifact-proof.py`/test（read-onlyのdirfd/no-follow/size/hash）、`server.js`（download route）。既存金融集計・認証cookie・queue/receiptを再利用する。
**Interfaces:** `buildMaritimeDailyResult({enrollment,periodKey,actionReceipts,financialRecords,financialCoverage,costs}) -> DailyResult`、`renderMaritimeDailyEmail(result) -> string`。
**入力契約:** actionReceiptsは中央queueの`{receipt,completedAt}`で、VM自己申告時刻を使わない。未確定jobは`{job,status,observedAt}`に中央で観測した時刻を渡し、架空の完了receiptを作らない。financialRecordsは同tenantのbusiness FinancialRecordのみ。financialCoverage/costsのcompleteは中央collectorの同tenant/period/timezone/evidence付き観測だけに付与する。欠落はunknownで、空配列だけから0を出さない。費用は観測小計とcoverageを分け、両coverage完備までprofitはunknown。既存Financial Managerの日付・通貨集計とformatterを再利用する。
**Depends:** T10/T11Aのsource。T17の売上発生は待たない。

- [ ] T18.1 test `daily_result_separates_artifact_publish_sales_payout_and_unknown_cost`を定義。商品作成だけなら売上0の観測がある場合のみ0、未取得は未確認、費用欠落で利益unknownをassert。
- [ ] T18.2 action receiptから「何を作った/公開した/保留中か」を構成し、gross/refund/known cost/payoutを別表示する。私用Moneytree/Dais balanceは参照しない。
- [ ] T18.3 日次copyを「今日実行したこと／確認できた成果と売上／費用／未完・失敗／次に進めること」に固定し、URLは同tenantのartifact/provider evidenceだけにする。
- [ ] T18.4 focused report testと二通貨/日付またぎを確認しcommit/push。
- [ ] T18.5 `buildMaritimeArtifactPath({jobId,artifactRef})`と`handleMaritimeManagerArtifact(req,res,options)`を新artifact moduleへ定義。URLは`/maritime/artifacts/<encoded jobId>/<各segmentをencodeしたrelative artifact path>`。uidは既存resolveMaritimeManagerUserの認証cookieからのみ解決する。新しいdownload token/secret/storeは作らない。
- [ ] T18.6 同uid+jobIdで既存readCommonJobを読み、既存cycle adapter.reconcile/verifyで公式captured stdoutと保存receiptが一致したcompleted jobだけを許可する。要求refがそのreceipt.artifact_refsに存在することを確認し、他tenant/任意file/未確認結果は返さない。pause後も既存成果は読める。
- [ ] T18.6a rootのproof verifierをmodelが書き換えられないよう、`maritime/run-cycle.js`はLinux root時にnative setprivでPython factoryをuid/gid10001・groups空・全capability削除・no-new-privsへ落とす。失敗はnonzero、root fallbackなし。`runtime-env.js`が/data parentをroot所有/書込不可にし、tenantの既知write dirsとgenerated configだけをfd経由でuid10001へ渡す。Dockerfileはutil-linux/専用userとroot所有readonly /appを含める。Localのagent-runner全体は変更しない。既存root Codex profileはコピーせず、Cloud専用agent-codex/agent-ledgersを使い旧データは保持する。rootrelay tokenはmodel子のenvから除外。focused argv/envと既存runtime profile、owned Linuxの非root/書込拒否/capabilityなしのread-only probeで確認する。
- [ ] T18.7 transportへreadArtifact({uid,agentId,artifactRef})を追加。先に公式read-only execでimmutable sourceのartifact-proof.pyを呼び、固定 `/data/<uid>/build/<raw relative>`をdirfd/O_NOFOLLOW/regular-fileだけで開いてsize/hashを取得する。公式files/downloadを同じ固定pathで読み、metadataのsize/hashと一致したbytesだけを返す。これによりworkspace途中のsymlinkや、proof後の差替えでprivate pathを配信しない。20MiBまでstreamを蓄積して超過時cancelする（中央HTTPのmemory bound）。SDKの無制限arrayBuffer downloadをこの経路では使わない。redirect禁止/20秒。返却はattachment/octet-stream/nosniff/no-store、SVG等を同originで実行しない。
- [ ] T18.8 serverへGET routeをmount。認証なしはログインへの案内、他tenant/不在は404。日報builderが既存publicOriginで実routeのlinkを作り、利用者がcookieで取得する。相対refだけをクリック可能URLと偽装しない。Unicode/空白/%/literal backslashをround-trip、dot/NUL/encoded separatorを拒否、foreign/未完/oversize/no-dispatchをfocused testしcommit/push。

## Task T19: 日次メールを既存CFO配信へ接続する

**Files:** Modify `maritime-manager-report.js`、`runtime-up.js`。Reuse `cfo-cloud-delivery.js`/`mail-resend.js`。
**Interfaces:** `deliverMaritimeDailyResult({enrollment,result,observedAt},deps)`→既存`deliverCloudCfoEmail({uid,periodKey,message,observedAt,recipient})`。送信直前にmanagerStore.read(uid)でactive/非停止/同timezoneを読み直し、recipientは最新enrollment.emailだけから取得する。resultのtenant/period/dateとobservedAtを検証し、呼出側のrecipient上書きを受けない。成果物メールのoriginは明示したLM_PANEL_BASE_URLまたはpublicOriginだけとし、worker自身のRAILWAY_PUBLIC_DOMAINを推測で使わない。
**Depends:** sourceはT18。実送信の受入はT16のtenant binding/worker wiring後。

- [ ] T19.1 test `daily_email_replay_returns_original_provider_id`を定義。同uid+periodKeyを二回実行してResend send1回、異なるrecipientへpending receiptを再利用しない。
- [ ] T19.2 既存永続receipt、provider idempotency、23h guardをそのまま使う。新しいメールoutbox/別providerを作らない。
- [ ] T19.3 送信後timeoutはprovider message/receiptをreadbackし、24hを超えた送信再試行はしない。API acceptedと受信箱着信を区別する。
- [ ] T19.4 `node --test lib/maritime-manager-report.test.js lib/cfo-cloud-delivery.test.js lib/mail-resend.test.js`で確認しcommit/push。

## Task T20: 停止が次の仕事と配信に効くようにする

**Files:** Modify `lib/maritime-manager-auth.js`/test、`lib/maritime-manager-store.js`/test、`lib/maritime-manager-runtime.js`/test、`lib/runtime-job-store.js`/test、`lib/maritime-distribution.js`/test、`scripts/runtime-up.js`/test、`server.js`。既存consent/report guardを再利用する。
**Interfaces:** authenticated POST `/maritime/stop`→paused、schedule除去、未claim job停止。進行済みeffectは公式readback継続。
**Depends:** T14/T19。

- [ ] T20.1 test `pause_blocks_next_job_and_report_but_preserves_inflight_receipt`を定義。他tenant停止不可、停止後新規publish/send0件、進行済みreceiptは保持。
- [ ] T20.1a `/maritime/stop`は既存verified-cookie/Origin/CSRFでuidを解決し、空JSONだけを受ける。最初に既存store.pauseで新規job/model/sendを遮断し、既存provision capabilityのstable phase=pause jobをenqueueする。HTTPはpaused/cleanupPendingを返し、queued cleanupを完了と偽装しない。
- [ ] T20.1b provision pause phaseは既存consent revokeとpaused schedule snapshotを実行する。bound agentなしはlocal control receipt、ありはloaded empty schedulesを確認する。reconcileは停止状態を照合し、未反映時だけ同じconsent revoke/empty snapshotをidempotentに再適用する。business/model/sendは再送せず、続きの仕事/日報をenqueueしない。新capability/table/schedulerを増やさず、既存inflight receiptは保持する。
- [ ] T20.1d pause保存→cleanup enqueue間のcrashを回収する。store.listPaused(limit20,afterUid)をuid順で有限pagingし、既存workerの30秒recoveryが同じpause jobをidempotent enqueueする。ローカルcursorを進めて古いcompleted cleanupが新tenantを飢餓させない。新table/cronは作らない。
- [ ] T20.1c landingへCSRF付き停止ボタンを追加し、停止は新しい仕事/今後のメールを止め、進行中の結果確認と既送信データは残ると明記する。中央queueの既存行は残し、dispatch/report直前のpaused guardで新規外部作用を拒否する。
- [ ] T20.1e review実測の競合を閉じる。`runtime-job-store.withRuntimeTenantControlLock({tenantId},operation,opts)`が既存PostgreSQL connectionで20秒lock_timeout付きtenant advisory transaction lockを使い、activateのconsent/enrollとconfigure/pauseの設定変更＋最終確認を同uidで直列化する。local pauseは先に即保存する。accepted create/configureのinspectはpausedでもreadbackを許し、execute/continuationの禁止は維持する。既存poolを使い、新lock table/providerを作らない。
- [ ] T20.2 既存consent revokeとenrollment.pauseを接続し、中央のjob claim/dispatch/report直前にもpausedを読む。停止を既送信データ削除と表示しない。
- [ ] T20.3 provider側に保存済みデータ・VMの削除は停止と分け、削除を勝手に実施しない。scheduled wake snapshotから停止分を外す。
- [ ] T20.4 focused stop testを確認してcommit/push。

## Task T21: 登録・実業務・再利用を既存funnelへ記録する

**Files:** Modify `apps/life-manager/lib/web-funnel-events.js`/test、`maritime-distribution.js`/test、`web-auth.js`/既存attribution test、`maritime-manager-auth.js`/test、`maritime-manager-artifacts.js`/test、`scripts/runtime-up.js`/test。Create `lib/maritime-manager-usage.js`/test、`migrations/2026-10-21-lm-maritime-manager-usage.sql`。
**Interfaces:** events=`maritime_email_verified|maritime_manager_activated|maritime_work_completed|maritime_report_sent|maritime_returned`。source_object_id=既存HMAC participant ID。
**Depends:** T05/T11/T19。

- [ ] T21.1 test `manager_usage_is_not_signup_and_analytics_has_no_email_or_body`を定義。signupだけではwork_completed0、再送はmilestone1件、email/token/本文なし。
- [ ] T21.1a `recordMaritimeManagerCompletion(job,receipt,options)`は中央completed rowと既存adapter.verifyを照合し、configure完了/実cycle完了/Resend受付だけをそれぞれactivated/work_completed/report_sentへ渡す。deferred/preflight/unknownは実業務完了に数えない。既存workerのSQL完了後とreconcile完了後にだけhookし、計測失敗で仕事/メールを再送しない。中央immutable receiptを再集計の正本として残す。
- [ ] T21.1b `createMaritimeDistributionStore.recordManagerEvent(eventName,uid,{eventKey,source,attribution,occurredAt})`を追加。source_object_idは既存HMAC、source_event_idはHMAC participant+event+job/periodのSHA256で128文字以内。本文/email/token/生uidを送らない。new eventだけ`audience_kind=internal|external`を付け、`LM_MARITIME_INTERNAL_UIDS`のfounder/team/fixtureを外部集計から除く。email account数を実在人間数と断定しない。
- [ ] T21.1c migrationは既存funnel event allowlist/audience_kindだけを追加する。既存`lm_users.web_first_touch`と`web-auth.storeWebFirstTouch`を再利用し、enrollmentに第二のattribution列を作らない。activationのhidden metadataへ既存sanitizeWebAttributionを使い、first-touch localStorageのUTMを引き継ぐ。emailだけ必須のformは維持し、source=instagramを追加して配布draftのIG source=otherを修正する。
- [ ] T21.1e review修正: 計測observerは共通2秒deadline/AbortSignalとfalse/例外/timeoutの匿名化診断を持つ。signupで既存署名cookieへ初回UTMを保存し、確認callbackで既存first-touchへ保存してからemitする。業務・認証を再送せず、永続receiptをbackfill正本とする。
- [ ] T21.1d `recordMaritimeEmailVerified(uid,options)`は確認済みsession成立後だけ。`recordMaritimeManagerReturn(uid,options)`は認証済み非prefetch GETで初回verified workから24時間以上後だけ。既存funnel読取+安定event IDで重複を防ぐ。計測障害は未確認として記録し、signupをreal useへ変換しない。
- [ ] T21.2 既存WEB_FUNNEL_EVENTSへevent名を追加し、既存record関数で記録する。true sourceのDM/X/IG/community別UTMを維持する。
- [ ] T21.3 founder/team/fixtureを外部userと別集計し、公式Keiki/Maritime project usageへの対応キーをprivate receiptで保持する。
- [ ] T21.4 focused event/distribution testを確認しcommit/push。独自analyticsサービスや新dashboardは作らない。

## Task T22: main由来の実環境で一人分を閉じる

**Files:** Create `scripts/maritime-manager-readback.js`/focused test。Modify catalogのCapafy readinessは確認できた項目のみ。
**Interfaces:** sanitizeされた`{releaseSha,imageDigest,agentId,uidHash,loadedSha,workReceipt,emailReceipt,nextWake,usage,costStatus}`。
**Depends:** T22.1は各taskのsource統合（T11B/T12/T15/T16/T19/T20/T21/T32）後。T22の完了はT17とメール/停止/計測の自然readback後。T17をT22.1 deployより先に要求しない。

- [ ] T22.0 GitHubがMac arm64 runnerを15分確保できず取消したannotationを確認する。公式actions/runner-imagesのstandard `macos-15-intel`へLoop control jobのrunnerだけをpinし、同じ契約テストを実行する。検証内容を削減せずexact HEADの14checkを再確認する。
- [ ] T22.0a Intel CIの既存release-bytecode testがcompute-proxyのnpm10 lock不整合で失敗する。既存npm10.9.4の隔離dry-runでREDを再現し、jayson/ws用の既存pinned utf-8-validate5 metadataを不足するnested lock entryへ補う。bytecode testのrelease allowlistは対象のruntime/loopへ絞り、無関係なNode packageのnetwork installに依存させない。bytecode/readonly/runtime Pythonのassertionは保持し、同じfocused testとnpm10 dry-runを通す。
- [ ] T22.0b CEO外部state境界のtestが191-loopの実registry全件を処理しIntel CIで30秒timeoutになる。実shell entry/CLI/libを使う一つのloopのsource fixtureへ分離し、30秒制限とsource registry不変・外部snapshot・state配下にregistryを複製しないassertionを保持する。production light-passと191-loop registryは変更しない。CI RED→focused GREENを確認する。
- [ ] T22.1 全source acceptanceとexact-head CIを確認しmainへ統合する。immutable imageをmain SHAから作り、DB migration履歴とapply結果を読む。公開flagをoffに保ち、central worker/relayとowned tenantの非公開foundationを先にdeployし、その後T17の実業務とT19の着信を確認する。
- [ ] T22.1a main由来commitでRailway Runtime PGのmigration history・6 Manager tables/RPC/ACL、既存runtime jobs/receipts/reconcile aging、worker用`2026-09-09-lm-financial-records-worker.sql`のtableを照合する。同じRuntime PG接続から`session_user/current_user`、login roleの`rolsuper/rolbypassrls`、6表のownerと`service_role` membershipをreadbackし、Poolが実際に使用するroleで認証済みidentity/enrollment/RPCを一件だけ非公開fixture検証する。owner/superuser/BYPASSRLS/service_role membershipのいずれでもない場合は、flagをoffのままにして正確なruntime roleだけへ必要最小のgrant/policyを追加する。Supabase側はAuth動作と過去のCFO/distribution/Manager/usage stateをread-onlyで確認し、既存データがあれば件数と用途を記録する。Manager stateの正本はRuntime PGとし、SupabaseへManager table migrationを適用せず、二重writeもしない。不足分だけ対象Runtime PGへ一回適用し、同じ接続でschema/ACL/readbackする。新FinancialRecord storeは作らない。
- [ ] T22.1b SupabaseのAuth/認証RESTを実測する。project ACTIVE_HEALTHYや未認証401だけでPASSにしない。503 PGRST002時は直近postgres_logsをerror/query classで集計し、本文/SQL本文/email/tokenを取得しない。過去の適用済みtimezone migrationを未適用と断定せず、既存の全体restart/restore禁止を守る。
- [ ] T22.1c `build-context.py`で統合mainからZIPを作る。owned external identityは現行HMACと一致するため、既存agentへ公式ZIP redeployを一回行い、新agentを作らない。既存VMの`LM_RELEASE_SHA`/`LM_SOURCE_ARCHIVE_SHA256`を新main/ZIPへ更新し、`LM_RUNTIME_TENANT_ID`は同値維持する。source SHA/ZIP hashとprovider deployment/image digestを区別し、実source file hashとloaded healthも照合する。envのSHAだけで新版採用と判定しない。upload/agent ID/tokenはprivate SSOTへ保存する。
- [ ] T22.1d0 Maritime platform account access: use the already registered identity only. Before browser/auth interaction, read the complete private credential SSOT, exact-match service row, browser registry, and current profile lease; use the registered CloakBrowser session. Do not create a second account. A prior readiness record says authenticated_agents_dashboard and API HTTP 200, but no current session readback exists; Gmail has a generic Welcome and an unused Verify email notice. Read the live dashboard/API and plan entitlement; if email verification is required, complete the existing flow without printing or storing the code anywhere except its credential SSOT. Record only session/entitlement/API status in docs/distribution/maritime/week1/readiness.json. Do not treat an email receipt or prior API 200 as current access.
- [x] T22.1d Runtime PG/identity/tenant/source/wake baseとservice configurationを準備し、main由来でdeployした。b.6-01〜26のschema/ACL/worker wiringは既存evidenceに記録済み。公開flag/capabilityのenableは後続b.6-27a/bで分離する。
- [x] T22.1e.1 worker capabilityとlife-call email入口を順に有効化しloaded readbackした。b.6-27a/bの証拠と現在値はcurrent-status-20261021.jsonにある。
- [ ] T22.1e.2 / b.6-28 owned participantがメールPKCEを完了し、Maritimeのretention条件へ明示同意した後に、PG identity/enrollment/CSRF bindingを照合する。現状confirmと同意は未確認。OTP再送や同意の代行をしない。
- [ ] T22.2 登録→自律job→provider結果→日次メールを自分の別Cloud tenantで一回実行する。Macのloopやbrowserを止める破壊的検証はせず、Cloudのargv/state/network evidenceでMac非依存を確かめる。
- [ ] T22.3 正規sleep後のscheduled wakeを一回観測し、同occurrenceの公開/送信が増えないことを読む。メール着信/送信provider ID、official usageとloaded SHAを結合する。
- [ ] T22.4 readiness/capacity/費用/未接続条件を正本へ更新。全14loopsをCloud完成扱いにせず、実証したCapafy範囲だけcatalogへ反映する。

## Task T23: 動く製品を正式経路へ提出し受付を保存する

**Files:** Create `scripts/maritime-week1-export.js`/focused test、`docs/distribution/maritime/week1/submission.json`、submission-checklistの状態更新。
**Interfaces:** aggregate-only export。`{product_url,demo_url,release_sha,official_required_fields,user_counts,work_receipts,costs,limitations,submission_receipt}`。個人データなし。
**Depends:** T01/T22。T25の豪華な完成動画/3人feedback/売上/7日継続は待たない。

- [x] T23.0a `#competition-submissions`でLife Manager entryを一度共有。2026-10-21T06:44:12Z readbackで同内容entryは1件。permalink `https://keikixmaritime.slack.com/archives/C0C9PEL45JA/p1792559347988839`、posted_at=2026-10-21T05:09:07.988839Z。channel descriptionは必要formを置き換えないと明記。
- [x] T23.0b 2026-10-21T06:44Zにofficial home/TermsとSlack announcementsを再確認したがform・Week 1 cutoff・rubricは未公表。contact@maritime.shへroute/deadline/demo fieldを一通問い合わせ、Gmail SENT/readback id=1a15d3141c56ee22。06:43Z時点でreplyなし。
- [x] T23.1 `packet_uses_measured_counts_and_excludes_private_users`を実装し、`node --test apps/life-manager/scripts/maritime-week1-export.test.js`が1/1 PASS。
  exporterは公式必須項目と実測値だけを出し、未測定はnull+理由とする。
  `docs/distribution/maritime/week1/submission.json`を2026-10-21T08:11:36.468Zにdraft生成。
  users/work receipts=0、costs=null、formal receipt=null。
  作業時mode=0600、SHA256=`fa891f6e8ed9410a0bb7c6249a0a698c259557578a6816dfaaf5c4f756ca9865`。
  このdraftは正式提出ではない。
- [x] T23.1-R1 review findingを修正。apps/life-manager/scripts/maritime-week1-export.jsでcompleted statusのreceiptがある場合だけmissing-work caveatを外す。failed/deferred/effect_unknownだけでは注意書きを維持する。
  入力境界は`safeWorkReceipts`、出力境界は`limitations`。`apps/life-manager/scripts/maritime-week1-export.test.js`へfailed/effect_unknownのみのケースを追加し、completed receiptが1件以上ある場合に限り注意書きを外す。
  DONE: RED reproduced before fix; node --test apps/life-manager/scripts/maritime-week1-export.test.js passes 2/2 including non-completed-only regression. Packet regenerated at 2026-10-21T08:34:34.541Z, SHA256=68024002e69d0c591dbb1614223a61697fd40d21ea7752330c2f22337bf6f4e1, mode=0600, status=draft, work_receipts=0, costs=null. T23.2 is next.
- [ ] T23.2 審査者が試せるURL、最小画面録画、Cloud実行receipt、現状の人数、制約を揃える。内部2–3分動画は推奨で、公式指定と混同しない。
- [ ] T23.3 channel entryの重複投稿は行わない。organizer replyまたは公開formから正式な必須項目を確認したら、現entry shareとは別のrequired formだけを一回提出し、正式経路が不明な間はformal status=unconfirmedのまま維持する。
- [ ] T23.4 confirmation画面/受信メール/受付IDを保存し、本文・提出時刻・release SHAをjoinする。UI timeout時はreadbackし再submitしない。これで初週提出を完了とする。

## Task T24: 既存ブログSEOと既存X用の初週配布を準備する（開発と並行）

**Files:** `docs/distribution/maritime/week1/channel-copy.md`、`docs/distribution/maritime/week1/seo-article-draft-en.md`、`docs/evidence/maritime/seo-baseline-20261021.json`、`docs/research/maritime/2026-10-20-source-map.md`、既存`apps/landing/marketing/pages/life-manager-en.html`のCTA参照。
**Interfaces:** Dais向けDM、既存`aniccaai.com/blog/manager`の記事brief、identity/connectionをreadbackした既存の広いX account向け1投稿、source別UTM。Instagramは初期配布に含めない。
**Depends:** T24.1-3に依存せず成功事例/briefを準備。SEO記事はpilot pageがHTTP 200で、limitations/retention/no-earnings-guaranteeを明記する場合はT22完全cycle前でも公開可。実行/収益claimはT22 official receipts後だけ。X投稿は既存identityのlive readback後。

- [x] T24.1 source-map.mdのTodoist/Ahrefs/Levels/X policy記録を読み、各社が表示する数値と対象・獲得因果の確認範囲を分けた。同一の自律Life Manager獲得例は未確認と記録。模倣機構は「具体的な悩み→使い方/実結果→一つのCTA」「intent別how-to/独自調査」「実際のbuild decision/result/constraintをblogからXへ展開」。適用限界もsource-mapに記録済み。
- [x] T24.2 `skills/writer-agent/SKILL.md`のreader-job/evidence/editorial契約と複数destination matrix、`config/loop-registry.json`の`article-daily` entry、`apps/landing/manager-blog/README.md`のcanonical source (`Daisuke134/life-manager`) とpublisher bridge (`Daisuke134/anicca-products`) を確認した。既存Writerを別媒体へ一括起動せず、記事draftだけを本repoへ保存する。
- [x] T24.3 `AI assistant vs AI agent: who chooses the next task?`を一つのreader-query仮説として選んだ。GSCのサイト全体28日間は0 clicks / 7 impressions、記事需要は未計測。基準値とpage-row不一致の注意は`docs/evidence/maritime/seo-baseline-20261021.json`に保存し、検索量/順位は主張しない。
- [x] T24.4a channel-copy.mdへ記事briefとearly-pilot CTA条件を記録し、seo-article-draft-en.mdをbriefへ更新する。検索量は未測定。completed hosted work / user earnings / profit claimはreceipt gateに残す。
- [ ] T24.4b docs/research/manager/articles/2026-10-21-ai-assistant-vs-agent-next-task-en.mdをcanonical sourceとして確定し、docs/research/manager/publication/2026-10-19/en/へ同じ本文を追加、manifest.jsonへslug/title/description/word_count/source hash/package hash/series_order=56を登録する。pilot URLのGET 200とretention noticeを記録し、CTAはearly pilot案内、full hosted work/report cycle未検証、収益保証なしと明記。DONE: source/package hash一致、JSON parse、required CI/review、公開URL 200とbody hash readback。
- [ ] T24.5 X案は既存の広いprofile向けに一つだけ保持する。Postiz connectorは09:32Z groups/integrations=0のため、post前に既存account owner/integrationを再読取し、target profileと重複投稿なしを確認する。新規accountは作らない。DONE: exact identityとPUBLISHED receiptを照合。identity未確認の間は未投稿。
- [ ] T24.6 docs/distribution/maritime/week1/channel-copy.mdのDMへpilot URL、hosted cycle未検証、Maritime retention、収益非保証を入れる。placeholder/PIIなしを確認し、Daisが送るcopyとして保存する。DM送信/既読/signupは実利用の証拠にしない。

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

- [x] T26.1 main原稿・README・startup/product contextと公開/lmを照合した。goal/budgetの入力は必須でなくTelegramは任意。hostedはCalendar中心、proactive cloudは開発中と明記。route-manifest.json内の全source hashがMATCHし、ライブ公開ページも同じ説明を返す。以前の「Set your goals and delegated boundaries」は過去のcrawl記録で、現行表示ではない。
- [x] T26.2 Cloud無料pilotの対象範囲と現在動く業務をchannel-copy/SEO draftへ反映した。既存Calendarの$29 trialとMaritime無料pilotは別と明記し、利益保証を加えていない。
- [ ] T26.3 既存full site exportへapproved overlayとして反映し、他商品/blog/legal/functionを保持する。manifest hashとpublished revisionを更新する。
- [ ] T26.4 公開URLのemail CTA/認証/停止/localeをreadbackし、source commitとpublished SHAを結合する。source変更だけを公開完了と呼ばない。

## Task T27: 公開配布を開始する

**Files:** channel-copy公開版、`aniccaai.com/blog/manager`記事、既存Postiz/X publisher receipt、既存distribution/funnel ledger。
**Interfaces:** Dais=家族/友人DM。LM=既存ブログ1記事→既存X profile 1投稿。source別URLとcanonical permalinkを保存。
**Depends:** T24 article package and current pilot-route URL/retention/limitations readback. Article publication may precede full T22 cycle. T22 is required before asserting completed execution or revenue. T25 video, three-person feedback and Instagram are not gates.

- [ ] T27.1 pilot URL GET、現行signup文言、Maritime retention notice、収益非保証をreadbackする。本文をearly pilot、full hosted work/report cycle未検証と一致させる。T22未完をCTAの隠れた前提にしない。
- [ ] T27.2 Life Manager source article packageを既存Daisuke134/anicca-products Manager bridgeへpinし、latest main worktreeからPR/CI/review/merge/deployする。canonical URL・HTTP 200・slug/canonical/body hashを保存。DONE: production bodyがsource/packageと一致。T22の収益/完了work claimは追加しない。
- [ ] T27.3 current Postiz integration listから既存広いX profile owner/IDを確認してから、一意のbuild-in-public postを一件だけpublishする。Current connectorが空なら外部投稿は行わず、readbackを再試行する。DONE: exact PUBLISHED receipt/permalinkとUTMを保存。
- [ ] T27.4 Daisへ最終URL入りDMを渡す。送信はDaisの担当とし、送ったcopyだけをsignup/userに数えない。
- [ ] T27.5 Article canonical、X permalink/provider receipt、copy SHA、UTM sourceを既存ledgerに記録し、blog/Xからverified email→activation→completed work→returnまで読む。初期waveでInstagramは使わない。

## Task T28: source別の最大離脱を一つ直す

**Files:** Modify `scripts/maritime-week1-export.js`、既存funnel report、該当する入口一箇所。
**Interfaces:** source cohort=`search impression/click or X click→visit→verified→activated→work_completed→returned`、費用/人、time-to-first-work。Blog readers、followers、impressions、signupだけを競技の実利用者にしない。
**Depends:** T21/T27。

- [ ] T28.1 source別aggregateを読み、team/test/重複を除いて最初の実利用を公式project usageへ照合する。人数が未取得なら0にしない。
- [ ] T28.2 最も人数を落としている一段を選び、route・error・滞留時間で原因を特定する。例: email着信、activate失敗、VM準備遅延、最初の成果が不明。
- [ ] T28.3 その境界のfocused回帰case→最小修正→公開readbackを一回行う。friend feedbackや7日データがなくても観測可能な不具合を直す。
- [ ] T28.4 修正前後の完了率/費用を同じwindowで保存し、完了が多いsourceへ次の配布枠を寄せる。

## Task T29: 1,000人までの運用と利益を改善する

**Files:** source-map、正本Maritime節、既存funnel/export/readiness。変更コードは実測で必要な箇所だけ。
**Interfaces:** source別実利用、official count、gross/refund/known cost/netStatus、capacity、継続。
**Depends:** T28。売上発生自体は保証しない。

- [ ] T29.1 capacityは現在のbilling/awake制限/利用者あたり費用から読み、稼働cap3を起点に、請求条件と単価の確認後10→100→1,000へ段階更新する。特定人数が揃うまで提出や素材制作を止めない。
- [ ] T29.2 完了・再利用・費用が良いsourceを増やす。販売対象商品の成果はCapafy official visits/orders/refund等で確認し、SNS表示回数だけで施策を増やさない。
- [ ] T29.3 費用の高いwake/無成果taskを既存model判断とbackoffで減らし、実際のnetが確認できる業務へ資源を寄せる。利益不明を黒字と報告しない。
- [ ] T29.4 1,000人到達時に公式project usageと本人/重複確認を提出し、winner通知をreadbackする。SF日本発旅費/credit条件/YCは別の確認事項として保持する。

## Task T30: 稼働URLをDaisへメールで届ける

**Files:** 既存mail送信経路とprivate delivery receipt。個人宛先/secretはrepoに保存しない。提出packetの作成を送信の前提にしない。
**Interfaces:** T22の稼働URLと準備済み配布copyをconsumes。T23受付済みならその事実も記す。送信先はprivate profile/credential SSOTから解決する。
**Depends:** T22直後。正式提出先の公表、長期獲得T29、winner通知を待たない。

- [x] T30.1 稼働中のemail登録URLと無料pilot範囲をGETでreadbackし、送信時にDaisの宛先をprivate SSOTから解決した。2026-10-21 06:07Zの再GETもHTTP 200。
- [x] T30.2 紹介文とURLを送信前に確認し、送信後のGmail Sent readbackでもURLと内容を照合した。
- [x] T30.3 許可済みの既存メール経路で一回送信し、provider message ID `1a15cc8791911599`を保存した。再送していない。
- [x] T30.4 Gmail Sent/readbackとmessage IDを正本へ保存した。受信者inboxへの到達は別readbackしておらず、competition project submissionでもない。

## Task T31: Cloud Life Manager自身の課金と利益をつなぐ

**As-Is:** `web-billing.js`は`readWebBillingUser()`とcustomer保存がSupabase lm_usersへ直接依存し、`createWebCheckoutSession()`が`requireActiveCalendar()`を必ず呼ぶ。metadataもlife_manager_web_travel、戻り先も/lm。`billing.js`のevent claim/applyもSupabase直接依存。verified identity resolverを替えるだけではManager課金にならない。

**Files:** Modify `lib/web-billing.js`/同test、`lib/billing.js`/同test、`server.js`、Manager UI。Create `lib/maritime-manager-billing.js`/同testとManager用billing migration（実装開始時に確定した入出力を同節へ反映する）。Reuse既存Stripe client/session/portal/署名検証/FinancialRecord。
**Depends:** 無料pilotの提供/初週提出を先行する。価格・商品・支払実績の読取は独立して進められる。任意upgradeとして実装し、Calendar guardや無料pilotの条件を変えない。

- [x] **T31.1a:** Exact credential-SSOT-matched live Stripe accountをread-onlyで照合。Anicca Life Managerのactive monthly pricesはUSD 29/20、Anicca CloudはUSD 30だが、各product priceにactive subscription=0、Life Manager active MRR=USD 0。Account-wide paid invoice historyは9件/USD 40.00だが、Life Managerへのproduct attributionは未確認。証拠→`docs/evidence/maritime/stripe-life-manager-readback-20261021.json`。
- [ ] **T31.1b:** paid invoice line itemsをLife Manager product/priceへjoinし、refund/fee/settlementを公式readbackする。Account-wide paid invoice rowsをLife Manager売上へ付け替えない。Stripe Sigmaはaccountに未契約のため、direct API readで続ける。
**T31.1 acceptance:** Stripe product/price/trial, paid invoices, refunds, fees, and settled cash are read back and attributable to Life Manager. Never infer MRR/net revenue from Dais's statement or account-wide totals alone.
- [ ] **T31.2:** web-billing.jsの`readWebBillingUser`、customer保存、`requireActiveCalendar`、metadata、戻り先をManagerの差替箇所として固定する。既存Calendarのeligibilityを残し、共通Stripe session/portal組立てを再利用できる境界へ分ける。
- [ ] **T31.3:** native Runtime PGにManager本人とStripe customer/subscriptionを結ぶ保存先、およびStripe event一回処理のfenceを定義する。一般lm_users/旧Stripe ledgerは移行しない。
- [ ] **T31.4:** maritime-manager-billing.jsでverified Manager UIDのbilling read/customer一回保存を接続する。任意uid/customer/price入力・他人のcustomer・claim上書きを拒否する。
- [ ] **T31.5:** 同fileのcheckout/portalを本人UID/CSRF/origin/許可priceへbindし、Manager起動と課金状態を区別する。Calendar接続をManagerのcheckout条件にしない。
- [ ] **T31.6:** server.jsの署名確認済みStripe eventからManagerのproduct metadataだけを専用handlerへ振り分ける。billing.jsの既存parserを再利用し、PGのevent claim→subscription/paid/refund/cancel状態を結ぶ。旧Calendar/Telegram handlerへ二重適用しない。
- [ ] **T31.7:** 関連fixtureとStripe test modeでcheckout→署名webhook→本人paid状態、portal、重複eventを確認する。自己cardでliveの架空売上を作らない。
- [ ] **T31.8:** 任意upgrade UI、review/CI/main/既存backend反映、live checkout入口のreadbackを行う。無料pilotを自動課金に変えない。
- [ ] **T31.9:** 実利用者のpaid invoice/refund/Stripe手数料とCloud/model/mail費用を既存FinancialRecordへ結び、実売上と確認できる純利益を報告する。未取得費用は未確認、free signup×価格はMRRにしない。

## Task T32: 既存SupabaseとResendで確認メールを実際に届ける

**Files:** Read `docs/evidence/maritime/smtp-preflight.json`。Create `docs/evidence/maritime/smtp-readback.json`（設定名/成否/receipt hashのみ）。実設定はSupabase production Auth、secret値はprivate credential SSOTのみ。
**Interfaces:** T04のPKCE handlerとT22のowned inboxをconsumes。設定readbackと実メール到着をproduces。公開appのfeature flagはこのtaskでは有効化しない。
**Depends:** T04。T07–T21とは独立して進める。初回の変更前観測はemail provider=false、custom SMTPなし、送信limit2/hour。これは現状値ではない。実環境の現在状態と着信証拠はSpec正本/T32とsmtp-readback.jsonを参照する。

- [x] T32.1 private credential SSOTから既存Supabase/Resend/Mail inboxを完全一致で確認。新key/account/inboxを作らず、現行Auth configをread-only取得。秘密の値は出力していない。Evidence→docs/evidence/maritime/smtp-preflight.json。
- [x] T32.2 sender mailbox/display nameを分離し、sender形式をreadbackで確認。Evidence→docs/evidence/maritime/smtp-readback.json。
- [x] T32.3 既存Google/redirect/site設定を保持し、Manager callbackだけを追加。SMTP host/port/sender、email enabled、confirm必須、hourly limit 30を適用。secret再作成なし。
- [x] T32.4 minimal Auth patchを確認後一度適用。auto-confirmを有効化せず、application feature flagは変更していない。Evidence→docs/evidence/maritime/smtp-readback.json。
- [x] T32.5 provider GETで設定と既存allowlist保持をreadback。smtp_passは出力・保存していない。
- [x] T32.6 owned inboxで一通の確認メールを受信し、時刻/送信元/件名/宛先を照合。内部probeで競技利用者に数えていない。
- [x] T32.7 smtp-readback.jsonへSMTP auth/email deliveryのreceipt hashと時刻を保存。delivery_status=owned_inbox_received、2026-10-20T12:28Z。
- [x] T32.8 safe JSON parseとsecret非混入を確認し、safe evidenceのみ保存。T22のbrowser PKCE→activate受入は別途未完。

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

### T22前のCI環境依存修正

- 実測: Intel hosted runnerで `test_full_inventory_gives_homebrew_a_longer_bounded_probe` が `/opt/homebrew` 不在により失敗。他609件成功。
- 対象: `skills/self/disk-cleanup/tests/test_host_inventory.py` の同テストだけ。`_children` のHomebrewメタデータを既存tmp_pathの実ディレクトリから作り、実環境のHomebrew有無に依存させない。
- 保持: 本物のcollect/size-probe/30秒assertion。production inventory、root一覧、timeout、削除処理は変更しない。
- 受入: 関連test module成功→commit/push→exact HEAD全14checks→main統合。現在cursorはこのCI差分、T22以降の順序は維持する。

### T22 foundation実行カーソル

- source最終d13e1b8d7fの全14check→#8424/main0c559693へ統合する。既存VMとWeb/workerはmain0cのimageを採用、safe evidenceはcloud-foundation-preflight.jsonとowned-image-adoption.jsonを参照する。
- DBのenrollment/execution/distribution/usageは公式apply success。CFO/financialは既存tableを再利用し、二重storeや新schedulerは作らない。
- **先頭未完T22.1b:** service-roleのREST `/rest/v1/lm_maritime_manager_enrollments?select=uid&limit=0` と `/rest/v1/lm_web_funnel_events?select=audience_kind&limit=0`、owned Auth subjectの読取を実測する。HTTP200/JSON/subject一致とelapsedを記録し、401やproject ACTIVE_HEALTHYを合格にしない。直近実験はREST503 PGRST002、owned Auth Adminは200/subject・email一致。
- 直近15分の公式分類はPGRST002707件/PG timezone取消5件/他取消7件。role readbackはanon3s/authenticated8s/authenticator15s・lock8s、service_role個別未設定。schema-cache startupと通常requestを区別し、blindなtimeout増量/全体restart/課金変更をしない。原因を特定する次probeはこの境界へ限定する。
- T22.1b通過後、既存worker capabilityを読み直し3つのMaritime capabilityを追加、両appのemail flagを1にして、privateに保存したfoundation deploymentから同imageを一回再deployする。最新SKIPPED commitを対象にせず、受理IDを保存しGETで結果を照合する。
- owned browserの実PKCE/同意/起動→新occurrenceの完了receipt→成果download→日報→停止を行う。旧unknown occurrenceの再送・外部友人への代理DMはしない。T30 URLメール/配布とT23正式経路の順序は維持する。

### T22.1b — PostgREST startup budgetの一度の限定実験

目的は認証REST/Authが実際に応答することであり、timeout値を書き換えたことを完了としない。公開flag/Maritime capability off、既存receiptとclient deadlineを維持する。global restart・resize・新料金・新DB・catalog shadowは行わない。

旧順序=resource metrics/role catalog/公開RESTの読み取り診断を続ける。新順序=下記source受入→一度の設定実験→実API判定→必要時rollback。理由は、role readbackが成功し、global4行とglobal+currentDB scope4行の一致から追加DB-specific timeoutが無いことを確認でき、繰返すtimezone取消/REST503に対する最小の反証可能な変更が具体化したため。進行中の業務effectは中断/再送しない。限定実験は終了し、現在cursorはb.5-1。

- [x] **b.4-1 / native RED:** `apps/life-manager/test/postgres/postgrest-startup-budget.integration.js`を作る。既存native PG fixtureのinitdb/Unix socket/pg driverを再利用し、baseline auth15/service未設定/anon3/authenticated8/lock8を作る。旧migrationをforward引数にしてauth60の期待が失敗することを確認する。
- [x] **b.4-2 / forwardとrollback:** `apps/life-manager/migrations/20261021070000_lm_postgrest_startup_budget.sql`はservice_role15を先に明示、authenticator60、config+schema NOTIFYだけとする。`apps/life-manager/scripts/postgrest-startup-budget-rollback.sql`はauthenticator15、service_role RESET、両NOTIFYで元の設定状態へ戻す。native fixtureでforward再適用、新旧接続、anon/auth/lock維持、rollback再適用と新接続15を確認する。
- [x] **b.4-3 / source受入:** 最小差分をcommit/pushし、実source reviewと対象CIを確認してmainへ統合する。主仮説はcold schema/timezone queryの15s取消であり、60s以内で終わる実測はまだ無い。source acceptanceを障害復旧と呼ばない。
- [x] **b.4-4 / 一回適用:** 既存private credentialでbaseline/履歴を読み、main由来forwardを一度だけ適用して公式receiptを保存する。応答不明時はroles/historyを読む。無根拠なforward再送はしない。
- [x] **b.4-5 / 2分で判定:** 認証limit0 RESTのenrollment/funnel audience_kind、owned Auth Admin、schema-cache/role-settingsの公式ログを読む。RESTだけ200なら部分回復であり、基盤全体の復旧ではない。新しいrole-map障害/60sでもtimezone取消/2分内に必要APIが回復しなければrollbackを開始する。
- [x] **b.4-6 / catalog復帰確認（既存pool状態は未確認）:** rollback SQLを既存経路で適用し、authenticator15とservice_role未設定のreadback・REST/Auth状態を記録する。2分はrollback開始期限であり接続障害時の復帰完了保証ではない。公式確認が無ければ復帰未確認としてカーソルを保つ。

通常requestのrole map読み込み失敗時に60s fallbackとなる可能性は残る。service_role15の明示を絶対的なrequest cap保証とは説明しない。新規のビジネス処理をこの実験に使わず、既存idempotency/receipt fenceを維持する。proposalのfresh read-only reviewはCritical0/Important0、詳細は本worktreeのignored `supabase-diagnosis-bounded-experiment-review.md`を参照する。

**b.4 source観測:** 旧SQLをforward引数にしたnative REDはfresh接続15s対期待1minで失敗する。新forward/rollbackは再適用・新旧接続・role/lock・元catalog復帰の8確認がPASS。PostgREST本体のrole mapや実APIの復旧は未検証、既存接続はrollback後も起動時GUCを保持する。証拠→docs/evidence/maritime/postgrest-startup-budget-source.json。


**b.4 本番結果:** PR #8446はexact HEAD全14checks成功後、main `67b907d6ab3df3b34021ace303b528304828b22f`へ統合する。同main由来forwardを一回だけ適用し、公式successを受ける。83秒でowned Auth Adminは200/subject・email一致・confirmedになるが、97秒時点でも両RESTは503 PGRST002のため、103秒でrollbackを開始する。rollback公式successと元のglobal4設定（anon3s/authenticated8s/authenticator15s＋lock8s、service_role未設定）を読取確認する。既存poolの起動時GUC復帰とREST復旧は未確認であり、成功扱いしない。証拠→`docs/evidence/maritime/postgrest-startup-budget-production.json`。source snapshotのproduction_applied=falseは隔離検証時点の履歴として保持する。

### T22.1b.5 — 失敗した限定実験から次の修復境界へ

旧順序=b.4 source→一回適用→API判定→rollback。新順序=版/公式更新経路の読取→対象限定の修復方式決定→実API判定。理由は60s設定では必要RESTが回復せず元catalogへ戻したため。同じforward再送・追加timeout増量・全project restartはしない。現在cursor=b.5-1。

- [ ] **b.5-1 / 稼働版:** 公式Management health/service versionの返却shapeと公開API schemaを確認する。Postgres17.6をPostgREST版と取り違えず、版が取得できなければHTTP状態と不足するsessionを記録する。
- [ ] **b.5-2 / 上流修正と更新範囲:** PostgRESTの公式release/changelogでtimezone catalog依存除去の修正を照合する。Supabaseの公開upgrade DTO/eligibilityを読み、DB全体upgradeとREST単独更新を区別する。非公開endpoint401を成功扱いせず、現存PATを無根拠に入替えない。
- [ ] **b.5-3 / 修復実行と判定:** 調査で特定した最小の修復をspecへ具体化してから実行する。新たな支出/全体restart/catalog shadowを導入せず、enrollment/funnel REST200とowned Auth200を再確認する。復帰しない場合はquery/connection/公式ログの失敗境界を一段狭める。


**b.5-1/2の読取結果:** public health200はREST/Auth UNHEALTHY、DB ACTIVE_HEALTHY。PostgREST configはpool自動/acquisition10秒/max_rows1000/schema public,graphql_public。pg_stat_activityのapplication_nameはpostgrestで版なし。公開upgrade eligibilityはPostgres17.6→17.11/推定1時間なのでREST修復として使わない。v16.0以降の上流fixは確認するがmanaged版は未取得。Metricsは一回504。DashboardはGitHubログイン専用という公式メールを受信し、保存済みGitHub password拒否・旧reset失効・recovery replay fenceを確認する。本人ログイン依頼は非同期で維持し、共有profile/identityを置換しない。

### T22.1c — DB復旧と独立した配備済みfactoryの新occurrence確認

旧順序=REST/Auth復旧→owned PKCE→新cycle。新順序=REST/Authの修復・本人ログイン待ちと並行して、owned VMの新offline occurrenceを一回確認→REST復帰後にPKCE/製品経由全体を確認。理由は、既知のliteral-path修正が新main imageへ配備済みであり、その修正の実モデル受入はDBに依存せず、既存VMと無料残高内で先に証明できるため。公開flag/worker capability、旧unknown occurrenceは変更しない。運用全体cursorはb.5-1とし、独立副cursorはc-1。

- [x] **c-1 / preflight:** 私有SSOTと既存VM identity/release0c、旧factory/adoptionのterminalを読む。既存billingでfree残高を確認し、paid変更をしない。新occurrence `owned-literal-path-20261021`が未dispatchであることを専用namespaceで確認する。
- [x] **c-2 / 一回実行:** 既存`maritime-owned-factory.py`のdispatch/readbackと既存`run-cycle.js`を再利用する。dedicated namespace `owned_factory_v2_`、pending fenceを保存してから一回POSTする。新モデル呼出は既存無料残高/既存モデル設定内。provider account未接続のままoriginal offline成果物を作り、publish/commerce mutation/友人への送信はしない。
- [ ] **c-3 / receipt:** 保存したexecution IDの公式GETでterminalとcycle statusを読む。completedにはliteral artifact refsが必要。不明時は同occurrenceを再送せず、既存receipt/summaryをread-onlyで診断する。旧6ファイルのunknownは書換えない。
- [ ] **c-4 / 成果物:** 新receiptのartifact path/存在/size/hashを既存validatorの契約と照合する。内部fixtureを実利用者、ファイル作成を売上・販売・入金と呼ばない。製品経由download/日報/停止はREST復旧後の未完項目として維持する。


**c-3診断→c-5 source修正:** 新v2 executionは公式completed/exit1、cloud_cycle.py:111のreceipt.parent.mkdirでPermissionError。モデル結果/新cycle receiptは無く、completedのcycleと扱わない。非root移行前のroot-owned receipts親が固定directory準備対象から漏れる仮説をlstatで確認する。旧順序=c-3 receipt→c-4成果物、新順序=c-3権限観測→c-5固定親修正/受入/main→新image採用→同occurrenceの未着手readback→c-4、理由=実モデル前の自己所有初期化不具合を解消するため。provider dispatch fenceと旧unknown receiptは削除しない。

- [x] **c-5a / directory境界:** `apps/life-manager/maritime/runtime-env.js`の`prepareMaritimeRuntime`、`run-cycle.js`のsetpriv→`cloud_cycle.py`のreceipt mkdirを照合する。変更は固定tenant receipts親のno-follow fd初期化へ限定し、再帰chown/モデル成果物の書換えはしない。
- [x] **c-5b / source修正:** 実行済みの非root失敗と既存runtime fixtureを根拠に固定`receipts`を既存ownership対象へ加える。既存のno-follow/10001/0700契約と旧receipt内容を保つ。元のpermission境界に絞って受入を確認する。
- [x] **c-5c / mainと採用:** sourceをcommit/push→実read-only review→exact HEAD必要checks→mainへ統合する。既存builder/upload/redeployを再利用して既存owned VMだけ新mainへ反映し、health/source hashと固定親ownershipを確認する。
- [ ] **c-5d / 新実行の扱い:** v2がモデル前失敗し新cycle.jsonが存在しないことを公式readbackで確認する。保存済みv2 execution IDは保持し、修復後の別dispatch namespaceを設けて同業務occurrenceへ一回だけdispatchする。存在するunknown receiptを消したり別IDで同作用を重複させたりしない。


**c-5a/b受入:** 実VMのreceipts親はuid/gid0・0755、home/buildは10001・0700、新v2 receipt directory/cycle.jsonは未作成。旧factory execution IDの現在GET404と過去completed証拠は分離する。固定親receiptsの既存no-follow ownership対象への追加だけを実装する。receipt parent inodeが10001/10001準備対象から漏れるfocused REDを確認し、修正後runtime-env6/6を確認する。fixtureはownership syscallのみ記録し、実chownの採用は新imageで別確認する。現在副cursor=c-5c。証拠→`docs/evidence/maritime/owned-factory-v2-preflight.json`。


**c-5d evidence:** owned main4f execution terminal exit0. Runner returns `no_op` with four literal workspace files, all present, regular/single-link, UID10001; an earlier read-only observation also found a newer mtime, which is diagnostic only. The four drafts total7188bytes. `cloud_cycle.py` maps no_op directly to deferred/no_work before validating paths; no publish/sale/payout/external use is evidenced. The v3 deferred receipt remains immutable.

- [x] **c-5d / root-cause readback:** provider execution terminal+runner no_op, four current files/7188bytes, UID/link verified; durable receipt stays deferred/no_work with no artifact refs. Evidence→`docs/evidence/maritime/owned-factory-no-op.json`.
- [x] **c-5e.1 / RED:** revise the no_op fixture to write under its exact occurrence output directory and require completed offline-draft refs. A file left in the shared build root remains deferred. RED showed three expected failures on the old behavior.
- [x] **c-5e.2 / boundary checks:** empty evidence remains no_work; a preexisting occurrence dir, symlink parent/file, directory artifact, or hard-linked artifact cannot become a ref. Preserve existing receipt fences.
- [x] **c-5e.3 / minimal fix:** after exclusive receipt creation, create `build/occurrences/<occurrence_id>` with `mkdir(exist_ok=False, mode=0700)`. `lstat` the parent and occurrence dir; reject symlink/non-directory/wrong owner and never reuse a preexisting dir. Keep `LIFE_MANAGER_BUILD_WORKSPACE` at the tenant build root; set runner `--workdir` and `AGENT_RUNNER_WORKDIR` to this occurrence dir. Accept evidence for `no_op` and `success` only when it resolves strictly inside that dir and `lstat` reports a regular, current-UID, single-link file. No valid no_op refs stays deferred/no_work; success without refs stays effect_unknown. Do not use mtime.
- [x] **c-5e.4 / focused verification:** `python3 -m unittest skills/capafy-autopublish/test/test_cloud_cycle.py` passes 21/21. Evidence→`docs/evidence/maritime/no-op-occurrence-staging-fix.json`. Publish/sale/payout remain unverified.
- [x] **c-5e.5 / source acceptance:** fresh read-only review Critical0/Important0/Minor0; PR #8452 exact head `13b2910cae65ebdfaf53c7efd886f33ed5f52e0f` had all13 required checks success; admin squash merged as main `a0d217d0769db2dab68bb8a8a452bfaea916fe9d`. Preserve the old v3 receipt and original drafts.
- [x] **c-5e.6.1 / sanitized build:** from merged main a0, build secret-free ZIP at 91,658,636 bytes / 8,768 files, archive SHA-256 `678cafe1261291e0fc9606c8531b70fd64816284dd73f8d8c1fd50dc41f372ee`, mode0600; forbidden path audit0, 13 approved vendored profile-source files.
- [x] **c-5e.6.2 / source upload:** upload once through the existing official dashboard session. HTTP200/custom/100 files; archive reference stored only in credential SSOT. No new agent created.
- [x] **c-5e.6.3 / redeploy existing agent:** official API GET bound the exact existing agentId+externalId; the same agent was redeployed once at source a0; HTTP200 and deployment receipt stored privately. No new VM/agent and no retry. Evidence→`docs/evidence/maritime/image-build-source-a0d217.json`.
- [x] **c-5e.6.4 / loaded source readback:** deployment status success; `/health` reports main a0; four loaded source hashes match main, UID/GID10001, caps0, NoNewPrivs, no inherited credentials, fixed browser binary/CDP/DOM verified, fixture/process group removed. Evidence→`docs/evidence/maritime/owned-image-adoption-a0d217.json`.
- [x] **c-5e.7 / fresh occurrence:** occurrence `week1-offline-a0-20261021-01` had absent receipt before dispatch, Free/no-next-charge preflight, no Capafy provider binding, and exactly one execution dispatch. Official API receipt is completed/exit0 for main a0 with 3 literal refs; no publication/sales/payout and external users for this run0. Credit use is welcome-credit only; exact balance is kept in private billing readback.
- [x] **c-5e.8 / demo proof:** all 3 receipt refs passed `artifact-proof.py` and official files/download size+SHA-256 verification. Four additional `SKILL.md`/listing-config/icon/test files named by the factory verification document were also proof/download hash matched. Local receipt artifacts are under private mode0700 directory with file mode0600. `lint_listing.py` passes (title22/50, short128/500, overclaims0). This is an offline unpublished draft; Manager user-facing artifact handler is not yet connected, and synthetic example figures are not customer results.

### T22.1b.6 — Manager保存先を既存Runtime Postgresへ接続する

旧順序=b.5のDashboard本人ログイン→REST復旧→公開。新順序=下記b.6とc-5のimage採用を並行→owned製品受入→T30配布、T23正式経路確認。理由は、現SupabaseデータAPI503、同regionの公式障害、候補DBimageにもtimezone依存が残る一方、既存Runtime PGはDDL可・対象6表未作成・Manager job0、Supabase enrollment/execution0、公開flag/cap無効を確認するため。b.5は元provider診断として残すが製品の進行条件から外す。進行中のimage配備と旧unknown fenceを中断/重複させない。現在cursorはUnified SSOTのT22.1b.6を参照する。副cursorなし（c-5e.8完了）。

**対象tree（新規は予定、既存componentを再利用する）:**

```text
apps/life-manager/
  migrations/20261021090000_maritime_manager_runtime_state.sql  [新規]
  lib/maritime-manager-store.js
  lib/maritime-manager-store.test.js
  lib/maritime-manager-persistence.js                         [新規]
  lib/maritime-manager-usage.js
  lib/maritime-manager-usage.test.js
  server.js
  scripts/runtime-up.js
  test/postgres/maritime-manager-state.integration.js          [新規]
```

以下のチェック欄は実行手順。完了状態・現在cursorの正本はSpecの同ID範囲。各項目は記載した結果で完了とし、次の作業に無関係な完了gateを追加しない。

#### schemaと保存処理

- [x] **b.6-01:** `test/postgres/maritime-manager-state.integration.js`へ既存native initdb/Unix socket/pg driver手順を流用し、6対象relationの欠落とSQLSTATE 42P01を確認する。`PATH=/opt/homebrew/Cellar/postgresql@17/17.11/bin:$PATH node --test test/postgres/maritime-manager-state.integration.js` passes1/1。Production DSN不使用、fixture stopped/removed。Evidence→`docs/evidence/maritime/runtime-pg-manager-schema-absence.json`。
- [x] **b.6-02:** `20261021090000_maritime_manager_runtime_state.sql`に`lm_maritime_manager_identities`を定義。UID PK / verified Auth subject UNIQUE、verified_at、first_touch JSONBとtimestamp、UID/subject再割当拒否を実装。native PG17 fixtureでunique/reassignment/first-touch制約を確認し、他5 relationは未作成のまま。`maritime-manager-state.integration.js` 1/1 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-identity-schema.json`。
- [x] **b.6-03:** 同migrationにenrollmentsと既存provision claim/bind関数を移す。一般lm_users FK/専用Supabase role GRANTを持ち込まず、identity bindingを制約する。native PostgreSQL 17 fixtureでclaim一回、同一agent再bind、foreign subject拒否、別UIDへのagent重複拒否を確認。Evidence→`docs/evidence/maritime/runtime-pg-manager-enrollment-schema.json`。
- [x] **b.6-04:** 同migrationにexecutionsと既存cycle claim/bind関数を移す。同occurrenceのclaim一回・同execution IDだけの再bindを維持する。native PostgreSQL 17の2接続競合・pause・migration再適用を確認。Evidence→`docs/evidence/maritime/runtime-pg-manager-execution-schema.json`。
- [x] **b.6-05:** 同migrationにparticipantsと容量claim関数を移す。advisory lockで人数上限を直列化し、sourceは現在のnormalizerと揃えInstagramも受理する。旧SQLにないInstagramを落とさない。native PostgreSQL 17の2接続容量競合・再同意・source・上限入力を確認。Evidence→`docs/evidence/maritime/runtime-pg-manager-participant-capacity.json`。
- [x] **b.6-06:** 同migrationにfunnel表・stable source-event unique・audience制約・必要index・append-only guardを定義する。既存normalizerの出力をそのまま保存できることを確認する。native PostgreSQL 17でsource-event重複、audience拒否、UPDATE/DELETE/TRUNCATE拒否、migration再適用を確認。Evidence→`docs/evidence/maritime/runtime-pg-manager-funnel-schema.json`。
- [x] **b.6-07:** 同migrationにCFO receipt表を移す。uid/period key unique、pending/sent整合性、recipient hashを維持する。既存jobs/common receipts/FinancialRecordは再作成しない。native PostgreSQL 17でidentity FK、pending/sent整合、recipient hash、一意性、再適用を確認。Evidence→`docs/evidence/maritime/runtime-pg-manager-cfo-receipts.json`。
- [x] **b.6-08:** `maritime-manager-store.js`の`read/listPending/listPaused`をparameterized SQLへ接続する。PG timestamp→ISOを正規化し、既存input/row検証を残す。native PG integration 1/1とstore unit 16/16 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-store-reads.json`。
- [x] **b.6-09:** 同fileの`enroll`をPGへ接続する。verified subject・UID・emailが既存rowと一致しなければ拒否し、conflictで所有者を上書きしない。native PG integration 1/1/store unit 16/16 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-enrollment-write.json`。
- [x] **b.6-10:** 同fileの`claimProvision/bindAgent`を上記既存関数へ接続する。paused時のprovision claim・foreign subject/agent・異なるreleaseを拒否し、遅延bind後もpausedを保つ。native PG integration 1/1/store unit 16/16 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-provision-binding.json`。
- [x] **b.6-11:** 同fileの`pause/quarantinePendingProvision`をPGへ接続する。pauseを先に永続化し、既存receiptを削除しない。native PG integration 1/1/store unit 16/16 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-pause.json`。
- [x] **b.6-12:** 同fileの`readCycleDispatch/claimCycleDispatch/bindCycleExecution`をPGへ接続する。PG date_keyをtimezone shiftなしでYYYY-MM-DDへ正規化し、agent/release/date/occurrenceの照合とdispatch前fenceを残す。ManagerのREST transportを置換し、障害時fallback/二重writeを作らない。native PG integration 1/1/store unit 16/16 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-cycle-dispatch-store.json`。

#### verified identity・同意・日報

- [x] **b.6-13:** `maritime-manager-persistence.js`に`ensureWebUserImpl(subject)`を作る。既存`separateWebUidForSubject()`を使い、owned UIDと一致することを確認する。一般Calendar/Telegramのlm_usersは参照/移行しない。native PG integration 1/1 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-identity-resolution.json`。
- [x] **b.6-14:** 同fileに`storeFirstTouch/readFirstTouch`を作る。既存sanitizeを使い、署名cookieから得た初回流入だけを保存する。後の流入で上書きしない。native PG integration 1/1 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-first-touch.json`。
- [x] **b.6-15:** 同fileのPG event writerを既存distributionの`recordEventImpl`へ注入し、`participantId/recordManagerEvent/recordAnonymousEvent`を再利用する。internal除外・HMAC・stable event key・dedupを維持する。native PG integration 1/1 + store/distribution unit 28/28 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-events.json`。
- [x] **b.6-16:** 同fileにManager専用`getParticipant/accept`を作る。容量claim関数を呼び、同一利用者は一度だけ、並行申込でも上限を超えないことを確認する。`maritime-retention-v1`と`maritime-manager-v1`を別々に保持し、既存Telegram distributionを切り替えない。Evidence→`docs/evidence/maritime/runtime-pg-manager-participant-accept.json`。
- [x] **b.6-17:** 同fileに`revoke/isConsentActive`を作る。停止状態を永続化し、失敗や読取不明を同意済みに置換しない。旧Telegram用global distributionは切替えない。native PG integration 1/1、distribution unit 14/14、store unit 16/16 pass。Evidence→`docs/evidence/maritime/runtime-pg-manager-consent-revoke.json`。
- [x] **b.6-18:** 同fileにCFO IOの`read/claim/mark`を作り、既存`deliverCloudCfoEmail`へ渡す。pending fence・recipient hash・23時間期限・Resend idempotencyを維持する。native PostgreSQL integration 1/1と既存CFO unit 2/2 PASS。2接続raceは1 claim、2回目の配送はDB receiptからduplicateとなりsender1回。実Resend/メール送信なし、production DSN不使用。Evidence→`docs/evidence/maritime/runtime-pg-manager-cfo-receipt-io.json`。

#### 呼出経路とsource受入

- [x] **b.6-19:** `server.js`のManager page/auth/activate/stop/artifact/wakeに同じpersistence依存を渡す。既存Money Printer Runtime PG PoolからmanagerStore/persistence/distribution/CFO IO/first-touchを一度構成し共有する。email flag OFFではroute依存を初期化しない。control lock用Poolをdata queryへ渡さず待ち循環を避ける。Manager auth/artifact/wake/store関連fixture 63/63 PASS、`server.js`/dependency factory構文check PASS。実runtime/PGは起動していない。Evidence→`docs/evidence/maritime/runtime-pg-manager-http-wiring.json`。
- [x] **b.6-20:** `scripts/runtime-up.js`のHandler生成・worker生成・completion観測に同じPG store/distribution/CFO IO/first-touchを渡す。既存workerの順次awaitとmax2の既存Poolを使い、Manager向けSupabase REST receipt fallbackを除去する。`scripts/runtime-up.test.js` 48/48 PASS。既存CFO sender/Resendは変更・呼出しなし。Production worker/DBは起動していない。Evidence→`docs/evidence/maritime/runtime-pg-manager-worker-wiring.json`。
- [x] **b.6-21:** `maritime-manager-usage.js`のManager return直接REST読取を、PGの`readFirstCompletedWorkAt`へ置換する。earliest external completed-work timestamp、prefetch除外、24時間境界、internal cohort除外を維持する。usage unit 4/4とnative PostgreSQL integration 1/1 PASS。Supabase REST/production DSN不使用。Evidence→`docs/evidence/maritime/runtime-pg-manager-return-eligibility.json`。
- [x] **b.6-22:** native PostgreSQL integrationでschema再適用、identity分離、capacity並行claim、停止後拒否、dispatch一回claim、同ID bind、date/timestamp正規化、CFO一回claim、event dedup、external first-work read/internal除外を実SQLで確認する。native integration 1/1 PASS。Production DSN不使用。Evidence→`docs/evidence/maritime/runtime-pg-manager-native-contracts.json`。
- [x] **b.6-23:** Manager store/auth/handler/usageの既存関連fixtureを新transportで確認する。PKCE/CSRF/origin/他人のUID拒否を維持し、関連11 fileをまとめて170/170 PASS。Production DSN・worker・Resend不使用。Evidence→`docs/evidence/maritime/runtime-pg-manager-related-fixtures.json`。
- [x] **b.6-24:** fresh reviewで検出したRuntime PGの権限とrole実行欠落を閉じる。6つのManager tableにRLSを有効化し、PUBLIC/anon/authenticatedの全権限を剥奪。trusted `service_role`に必要なtable権限と専用RLS policyを設定（append-only funnelはSELECT/INSERTのみ）。5つの業務RPCはservice_roleのみEXECUTE、trigger guard関数は直接EXECUTE不可。native PostgreSQL integrationで全6表・5 RPC・CFO receiptの`SET ROLE service_role`実操作を確認。初回失敗を含むRED→GREEN、関連11-file suite 170/170 PASS。fresh-context review Critical/High 0、修正版source head Security Scan 12/12 + Cloud reminder 1/1 PASS。PR #8460をmain `464635e4f455a7411e441e76c3208cc188de68c2`へ統合。Evidence→`docs/evidence/maritime/runtime-pg-manager-acl.json`。production DB/migration・Resend・実メールには触れていない。

#### 本番反映と実際の製品受入

- [x] **b.6-25:** 同じRuntime PGでrole・schema owner/RLS/PK・既存履歴・対象6表absenceをreadbackする。anon/authenticated/service_roleが存在し、対象migration idが未登録で6表も未作成、source SHA256がmainと一致することを全て確認する。単一のdedicated pg.ClientでBEGIN→lock_timeout/statement_timeout→migration全文→schema_migrations insert→COMMITを順番にawaitする。成功後readbackで履歴7件/対象1件、6表0 rows、owner/RLS/policy/ACL/RPC/triggersを確認。証拠はdocs/evidence/maritime/runtime-pg-production-role-preflight.json（02:49Z readback）。
- [x] **b.6-26a:** apps/life-manager/package-lock.jsonはmain tracked (blob SHA 9b994de0daba2eac126f74c84981c9ed3a78418c)。元lockを変更せず、apps/life-manager/.npmrcにlegacy-peer-deps=trueを設定。npm config get legacy-peer-deps --prefix apps/life-manager=true、exact npm ci --ignore-scripts --prefix apps/life-manager exit 0、package.json/package-lock差分なし。PR #8469 merge。
- [x] **b.6-26b:** full main sourceをrepo rootとするGitHub auto-deployを確認（PR #8469/main 76d36e33979aa6e4b8924db6405fa8031b169782）。life-call deployment 1fd0ee51-1214-429c-bee8-2e913cd51eab SUCCESS。/health HTTP 200/build tag=main SHAをreadback。
- [x] **b.6-26c:** 同じmain SHAからmoney-printer-workerをdeploy/readback。deployment c19340af-6832-497a-86bf-793bd12a7623 SUCCESS、loaded runtime-up.js main SHA一致、既存3 capabilityのみ、Manager capabilityなし、email flag=0。
- [x] **b.6-27a / worker capability追加:** 既存3 capabilityを保ちMaritime provision/cycle/reportを追加。2026-10-21 05:49Z readbackでworker loaded SHA=27b594cd84f6e660f6ffbacabb21be8d7f25cb2c、deployment SUCCESS、capability計6件、Manager 3件、email flag=0、pilot cap=3を確認。secret valueは表示していない。Evidence→docs/evidence/maritime/current-status-20261021.json。
- [x] **b.6-27b / email入口を開く:** 2026-10-21 05:49Z readbackでlife-call loaded SHA=27b594cd84f6e660f6ffbacabb21be8d7f25cb2c、deployment SUCCESS、email flag=1、pilot cap=3を確認。06:07Zの公開GET /maritime?lang=enはHTTP 200 signup page。email flag有効化とOTP送信を区別し、activation/consentは未確認。Evidence→docs/evidence/maritime/current-status-20261021.json。
- [ ] **b.6-28:** ownedの同じブラウザでメール登録→実PKCE callbackを通す。Authのverified subjectとPG identity/CSRF cookieを照合する。
- [ ] **b.6-29:** 実同意・起動でPG enrollment/jobを確認する。既存externalIdのowned VMをrecoverし、configure receipt・relay・scheduleの公式readbackを取る。
- [ ] **b.6-30:** 製品経由の新cycleをworkerで完了させ、公式execution・共通receipt・成果物を結ぶ。ログのexit0だけで完了とせず、ブラウザから成果物をdownloadしてsize/hashを照合する。
- [ ] **b.6-31:** 実日報のjob→CFO receipt→Resend provider受付→owned inbox着信を確認する。初回予定日時を明記し、unknownを利益0や売上へ変換しない。
- [ ] **b.6-32:** 実停止でpaused永続化→新規dispatch抑止→同意revoke/schedule停止の公式readbackを確認する。過去receipt/成果物は維持する。
- [ ] **b.6-33:** 計測のverified/activated/work/report/returnをPGから読取確認する。founder/testをexternal利用者へ数えない。24時間再訪の将来観測を初週提出の待ち条件にしない。
- [ ] **b.6-34:** 初週packetの稼働URL・loaded SHA・Maritime usage・実業務・人数/費用の証拠を現在値へ更新する。T30 URLメールとT23正式経路へ渡す。

**その先の既存atomic TODO:** T30.1〜4=URLメール、T24.3〜4/T25/T26=媒体URL・配布素材・demo/公開、T23=正式提出と受付readback、T27/T28/T29=実利用と継続/1,000人への拡大、T31=課金/利益。各定義を重複作成せず既存節を実行する。友人3人・正式form公開・24時間再訪・1,000人をURL送信の待ち条件にしない。

**再利用するcomponent:** runtime-job-store、FinancialRecord、daily observations、Maritime transport、Resend/CFO delivery、PKCE/CSRF、UID helper、distribution/event normalizer。根拠→`docs/evidence/maritime/runtime-pg-state-preflight.json`。


**c-5cの本番採用:** main4fの既存VM再配備は公式success。新しいread-only executionはcompleted/exit0、health release4f・runtime-env.js hashのmain一致・receipts親10001:10001/0700・symlinkなしを確認する。v2失敗occurrenceのcycle receiptは存在しない。モデルは呼ばず、再dispatch/新業務完了は未確認。副cursor=c-5d。証拠→`docs/evidence/maritime/receipt-parent-image-adoption.json`。
