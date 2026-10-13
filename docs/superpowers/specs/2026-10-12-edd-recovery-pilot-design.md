# Life Manager EDD：Writer pilotと障害回復safety case設計

## 目的・範囲・位置付け

目的は、一つの実障害を既存の回帰試験と対応付け、修理の前後を測れるようにすること。初版の成果は調査・説明・spec・plan。2026-10-12、Daisは英語解説記事をAniccaのブログとXへ公開することを別途明示した。この編集上の配信はE02/E03実行、runtime変更、benchmark性能の主張には当たらない。

これはWriter Pilot Aの設計と実装記録であり、新しい全体TODO正本ではない。実行状態・全体順序・所有者は [統一SSOT](2026-09-25-life-manager-unified-ssot.md) に従う。Daisの現在の指示により、この作業のactive scopeはWriterの評価駆動開発とする。E01の`agent-economy-loop` release adoption/natural evaluationは別cursorとして残り、Writer graderの前提条件ではない。Writer側ではproduction runtime・外部effectを変更しない。

**実装checkpoint（2026-10-13）:** A7 W-01 deterministic code grader is merged and 9/9 focused tests pass. A3b source lineage fix PR #7878 and A3c child-to-parent summary binding PR #7881 are merged with CI pass. The current live article-daily is still on old release `3e19c846` with an unresolved publish effect fence, so no runtime adoption/natural trace is claimed. Current E02 cursor is A8 blind label set preparation; no human labels are recorded yet.

**A3bの根拠:** 現行mainの`article-daily.sh`は`git log`で`harness_git_hash`を採取するが、current immutable release `3e19c8463a1751b8c3c5a7c3a273330d4280b2f2`に`.git`はなく、loop applyが渡す`LIFE_MANAGER_RELEASE_SHA`をcapture経路は参照しない。実run `20261011-210544`は`git-hash.txt=UNKNOWN`。これはsource captureの現行欠陥を示すが、当該過去runのsourceやW-01 0-byte artifactの生成原因を確定しない。既存publish effect fenceは変更しない。
**A3cの根拠:** read-only inventoryは251 `writer-judge` child summariesを確認した。summaryには`runtime_event_id`があるがparent article run/lifecycle occurrence/source fieldsがなく、raw quality result JSONだけではjudge inputを親articleへ結べない。`shared-model-runner.py`は`ARTICLE_RUN_ID`を継承し、agent-runnerはruntime eventへchild identityを書いているため、A3cでevent identityとparent environment IDsをsummaryへcopyする。raw article textはprivate run dirに保持し、child callsを独立article taskとして数えない。
## E01 runtime checkpoint

**観測時刻:** 2026-10-12T14:52:05Z。これはローカル状態の読み取り専用checkpointであり、統一SSOTのcursorを進めない。

- `origin/main` (`af8e9a1b`) は欠測・不正netを`unknown`に保つ修正 (`b5522b5d`) を含む。main由来のcurrent release `65d1feb5` の`runtime/loop/self-eval.mjs` SHA-256は`75b050c7…`で、main sourceと一致する。既存`self-eval.test.mjs`は8/8 PASS。
- private natural earn ledgerの4,164行はすべて有限の`net_usdc`を持つ。current releaseのpure `selfEval`へ読み取り専用で渡すと、直近25行から4 groupを評価し、unknown groupは0。値やledger本文は保存・公開していない。この自然データは正常入力のbaselineであり、欠測・不正netの自然発生を示さない。
- `agent-economy-loop`はPID 3136で`loaded-running`、loaded releaseは`dd6f0ee5`。そのrelease内`self-eval.mjs` SHA-256は`e31b51c4…`で、修正済みcurrent releaseと異なる。プロセスを停止・再起動・差し替えず、E01を未完のまま保つ。

**E01受入の区別:** 欠測・不正・混在netの振る舞いは既存の8件の単体回帰testで検証する。natural ledgerに存在しない欠測値をproductionへ注入しない。実行完了には、実呼び出しownerが安全に`loaded-idle`となった後、修正済みmain由来releaseのloaded SHAと次の自然runでの採用を確認する。通常入力の自然評価は実行経路と結果を補強するが、欠測netへの耐性や経済利益を証明しない。容量/admissionが未解決なら適用せず、既存の共有資源cursorに従う。

**最新E01 readback:** 2026-10-12T15:22:08Z時点で`origin/main=4592b650`、current releaseは`65d1feb5`、その`self-eval.mjs` SHA-256はmain sourceと同じ`75b050c7…`です。`agent-economy-loop`は古い`dd6f0ee5`を`loaded-running`し、`brain_transport` / `reconcile_owner`状態です。停止・再起動はしていません。available diskは1,761,400 KiBで、current releaseのcapacity requirement 2,393,120,768 bytesを下回ります。E01 cursorは未完のままです。

**今回のE01 readback:** `origin/main=8cc3f0a23c96dd9c986924607239b33775633c03`、current releaseは`65d1feb577ce1158079eed79795d253049b89a25`です。mainとcurrent releaseの`self-eval.mjs` SHA-256は`75b050c7…`で一致しますが、`agent-economy-loop`はPID 3136で旧`dd6f0ee51266dda30b84b054f6c72d3771badf7b`を`loaded-running`し、`brain_transport` / `reconcile_owner`状態です。`RELEASE.json`の容量要件は2,393,120,768 bytes、readback時の`df -k /`は1,482,448 KiB availableです。直近2回のbounded watchdog passは各13候補を評価し、回収0、errors 0、protected deletions 0、capacity `unmet`でした。停止・再起動・release apply・effect fence変更は行わず、E01 cursorを未完のまま保ちます。

## Writer trace checkpoint

Writerのowner・run状態は2026-10-12T15:14:46Zにread-only確認しました。`article-daily`はloaded-idleですが`resource_effect_unknown`のfenceを持ち、`writer-craft-train`はcapacity defer、`writer-opportunity-discovery`はFIFO wait、`writer-sales-measure`はidleです。公開・再送・owner変更はしていません。

Pilot AのstageはEnglish article draftの公開前quality gateに絞ります。これはgateの再現評価で、ブログ・note・Substack等への新規公開は行いません。

**task-level inventory:** 自然なarticle run directoryは8件で、5件にEnglish draft、3件にはEnglish draftがありません。4件にquality gate receiptがあり、3件はadvisory、1件はidentity/CTA disagreementでpublication前に止まりました。8件すべての`harness_git_hash`は`UNKNOWN`です。

**child-call inventory:** 1,498のagent-runner evidence directoryのうち1,469にsummaryがあり、`article-daily`は276 child-call summariesを持ちます（251 judge、25 agent）。276件すべてに`runtime_event_id`がありますが、summaryにはparent run/occurrence/source SHAがありません。現在保持されるevent ledgerにjoinできるのは25件で、記事task件数や独立sample数へ足しません。

最初のsemantic case candidateはEnglish blog article draftのidentity `C: FAIL` / mandatory CTA `PASS` / `blocked-before-publication`の組み合わせです。人手labelはpendingで、false positiveとはまだ呼びません。A4は別軸のmachine-checkable `quality_self_heal_record_unparseable`を選び、A5/A6 case cardとoutcome vectorを[Writer EDD trace discovery](../../evals/writer-edd-trace-discovery.md)に記録しました。W-01のtask completion、quality、safety gate、effect integrity、settled net、cost coverage、latency、human interventionは別fieldで、根拠のない項目を`0`へ置換しません。これはPilot Aのcase-level schemaであり、canonical E02のCFO official receipt joinは未完です。raw traceはprivate storeに保持します。prototype review UIはrepo外のlocal artifactで、`127.0.0.1`だけにbindし、明示allowlistのGETだけを提供します。reviewerが表示ボタンを押したartifactだけを読み、POST/PUTと外部通信は拒否します。注釈はbrowserの`localStorage`に保存します。

このcheckpointはpreworkであり、統一SSOTのE01 current cursorも収益優先順も変更しません。

根拠は [一次資料比較](../../research/2026-10-12-edd-and-autonomy-benchmarks.md)。既存runnerを維持し、AutomationBenchの初期state・tool・終state検査の形を参考にする。新framework、scheduler、optimizerは追加しない。

## 18業務からのPilot A選定

**選定: Writerの一記事・一言語・一媒体の公開前品質評価。** Writer全体や18業務全体を同時に直す計画ではない。最初の目的は、自然traceの失敗を再現可能なevalにし、修正前後を同じ条件で測ること。公開や入金は独立した後段outcomeとして扱う。

比較対象の母集団は最新mainの[18業務カタログ](../../../apps/life-manager/config/product-loop-catalog.json)。候補は既存evalとrecovery artifacts、反復時の外部effect安全性、公式outcomeまでの距離、job/owner範囲で比較した。catalogの`implemented`はコード上のadapter statusで、自然runや売上receiptの存在を意味しない。

| 候補 | 選ぶ理由・外す理由 |
|---|---|
| **Writer（採用）** | quality gate、article bytesに結び付くgate receipts、bounded recoveryがあり、一記事の公開前sliceを外部effectなしで調べられる。自然runでsource commitが記録されるという意味ではない。今回の8 natural runは全て`harness_git_hash=UNKNOWN`で、source-level reproductionは未達。金融・費用adapterは部分実装なので、収益は未証明として別採点する。 |
| Agent Economy | 収益・金融・費用adapterはcatalog上実装済みで、金銭評価の有力候補。ただし19 jobと複数のx402/TaskMarket ownerを含み、最新の優先順ではTaskMarketの外部報酬証明が後段にある。最初の方法検証には広すぎる。 |
| PromptBase | 1 jobで小さく見えるが、金融・費用adapterが未実装で、seller/browser経路にも未解決境界がある。 |
| Connector | 1 jobでreceiptが明瞭だが、catalog上non-economic。仕事の完了evalには向くが、今回の収益benchmarkの初手には選ばない。 |
| Gig — Coconala | revenue/funnel/financial/cost adapterがcatalog上実装済み。ただし7 jobの応募・交渉・納品・決済を含み、Writerの公開前sliceより外部effectとprovider待ちが多い。 |

従ってWriterは「18業務で最も簡単」または「すでに最も収益がある」とは主張しない。**評価手法を安全に立ち上げるのに最も準備があるslice**として選ぶ。既存の収益業務の優先順は変更しない。品質gateのPASSを売上・利益と呼ばず、settled外部収入・refund・fee・同期間の実費が結べない場合のnetは`unknown`に保つ。

記事sourceと図は[PR #7798](https://github.com/Daisuke134/life-manager/pull/7798)で管理する。公開版は英語記事とし、日本語HTMLは内部説明資料とする。公開先はAniccaの既存 `/blog` と登録済み `x:anicca` identity（`@selawmqt`）。公開後に実URLと公式readbackをこの節へ記録し、E01–E06の実行cursorとは分離する。

## 英語記事の配信タスク

対象記事は “Good Agent Evals Measure Work Done, Not Answers Given”。既存のブログ記事テンプレートと標準X postの経路を再利用し、ページを別実装しない。本文には、現行LM-EABの5 fixtureは合成契約検査であること、Writer qualityは収益証拠ではないこと、AI lab採用は未達であることを明記する。

1. 英文・出典・3枚の図を確認し、この記事sourceをPR #7798に保持する。
2. Aniccaサイトへ記事recordと画像を追加し、既存build/CIとmain経由のdeployを通す。
3. blog本文と全画像のlive readbackを確認してから、そのURLをX投稿に記載する。
4. `x:anicca` のlive session identityを照合してXへ公開し、post URLと本文表示を確認する。X Articles UIが使えない時はブログ本文へ誘導する標準X postを使う。
5. X post URLをblog mirror metadataへ加え、相互リンクをlive readbackする。
6. 両URLと確認根拠をspecへ記録する。配信完了はE06 benchmark公開、第三者再現、lab採用を意味しない。

**状態:** 公開完了。英文・sourceはfresh read-only adversarial verificationでSHIP。site PR #456 (`23b2eeb`) は本文と3画像をdeployしsmoke PASS。X postは公式UIと公開readbackで確認。mirror更新PR #457 (`d86bea2`) のdeployと記事→X相互linkもlive readback済み。Life Manager文書PR #7798は全CI PASSで `575731f` にmerge済み。E01–E06 cursorは変更しない。

**公開URL:** blog `https://aniccaai.com/blog/good-agent-evals-measure-outcomes` · X `https://x.com/selawmqt/status/2109636732962668720`。X mirror labelは `X ↗`。

**X Articles調査:** [X公式Articles説明](https://help.x.com/en/using-x/articles)は公開機能をPremium/Premium+等の対象subscriberに限定している。登録済み `@selawmqt` のlive sessionで公式案内の `/compose/articles` と `/compose/articles/new` を開くと両方404となり、Articles editorと画像file inputが存在しなかった。publisher scriptはX Article draftを作る前に終了し、X Articleそのものは公開していない。その後、追加subscription購入や別identityを使わず、ブログURLへ誘導する標準X postを公開した。上記X URLはその公式readbackである。

**2026-10-13再確認:** blog URLは英語の約2,500語の記事を返し、X statusは英語の紹介投稿として公開中で、リンク先は同じblog記事である。`x:anicca` のbrowser-guard lease経由でHome/feedを確認し、`/compose/articles` は再び `Page not found`、記事title/body editorは0件だった。従って今回の依頼は既存のblog記事＋X紹介投稿で満たされている。新しい投稿・X Article・subscription購入は行わず、重複effectを作らない。X Articleを利用できるようになった場合だけ、同じ本文の長文ミラーを別途検討する。

## Pilot B: effect-unknown recovery safety case

Pilot AはWriterの公開前品質evalで、evalのtrace・grader・候補比較を安全に学ぶ。ここではE02に必要なeffect-unknown回復の安全境界を別caseとして定義する。Pilot Aのquality PASSは売上証明でもE02/E03の完了でもない。

説明用の対象は「外部送信後に応答が途切れ、ローカル成功記録が欠ける」。これは障害クラスの設計で、今回新たに本番障害を発生させない。実case採用時はownerが自然traceと公式readbackを確認し、同一occurrenceへのbindingを持つものだけを使う。採れない場合はderived syntheticと表示し、自然障害成功と称さない。

最初の成果物は一枚のcase card。初期state、目的、許可tool、制約、終条件、観測根拠、既存testとの対応、未確認を記載する。task例の目的は「対象業務を重複なく完了し、公式記録を照合する」。禁止事項は他owner変更、既存effect fence解除、公式確認なしの再送、採点器変更。永久holdでtask完了扱いにしない。

## 既存コード・testの再利用

- `apps/life-manager/eval/economic-autonomy/records.js` / `score.js`: 会計・autonomy・cost coverageの契約をそのまま使う。
- 同directoryの `run.js`: 固定fixture採点CLIとして維持。これをagent実行能力と呼ばない。
- `runtime/loop/recovery-intent.mjs` の `buildRecoveryIntent(input)` と既存 `__tests__/recovery-intent.test.mjs`: unknown effectのhold/nonretryable/requiredとknown failureのbounded recoveryは既に検査する。
- `runtime/loop/recovery-apply-plan.mjs` の `buildRecoveryApplyPlan({intent, registry})` と既存 `__tests__/recovery-apply-plan.test.mjs`: no commands、wrong owner拒否、限定reconcileを既に検査する。
- production executor・supervisor・既存ownerはpilot担当が変更/実行しない。

最初の案にあった新しいoffline wrapperは作らない。上記のassertionを再包装するだけでは業務完了を測れず、既存testと重複する。既存testが通るのに実業務が失敗した場合は、修正対象をpolicyと決めつけず、runtime入力・release・tool・state・readbackのどこが違うかを一段ずつ狭める。

## 評価を分ける

1. 契約評価: 初期stateに対するintent/planが正しいか。既存pure-function testを使う。
2. agent評価: 同じtask環境でagentを動かし、action logと終stateから業務完了・重複・費用・介入を検査する。現行fixture runnerには未接続。
3. production成果: 既存ownerの自然failure→修理→業務再開→公式outcome。offlineの結果で代替しない。

policyだけ測るcase cardは `measurement_kind=offline_policy_contract`。安全性と完了を `pass|fail|unknown` で別表示する。policyが正しくholdした場合は安全性をpassにできるが、業務完了はunknown。公式記録を入力fixtureに含めても、純関数が実業務を実行した証拠にはしない。

後続agent評価の主指標は、assigned tasksを母数とするverified completed率。failed・unknown・invalid-environmentも件数表示し、unknownを除外して成功率を膨らませない。agentが書いた「完了」は根拠にしない。graderの条件はtaskの説明と一致させ、正当な別解を落とさない。

経済taskは既存 `scoreEconomicAutonomy` へ適合bundleを渡す。settled収入・refund/fees・model/API/運営費・period/currency/receipt attributionが揃わない実利益はunknown。模擬報酬を実入金として表示しない。

## 自律性と比較条件

初回設定を許す `one_shot_onboarding` と、user credentialに依存しない `agent_native` を区別する。人のjudgment/action、外からのCodex修理・再起動を別に記録する。事前指定の構成agentと外部救済を混ぜない。欠けた介入記録を介入ゼロへ変換しない。

モデル比較は同じharness/tools/state/budgetを固定するか、system別の結果として表示する。trialは初期stateを戻して独立に行う。pilotの小標本で順位を断定せず、件数と不確かさを表示する。公開fixtureは秘密held-outではない。未見試験は別管理・変更履歴付きで扱い、候補調整に使わない。

## 修理・自己改善への接続

EDDは失敗case→修正前の失敗→原因修正→同条件の改善確認。ownerの実修理を評価担当が置き換えない。公開benchmarkが完成するまで既存修復を止めない。既存試験で覆われていない振る舞いだけを最小の失敗testにする。

自己改善は固定grader・baseline・cost/safety条件で候補を比較する。候補にgrader/held-out/credential authorityを編集させない。offlineに通っただけでproductionへ自動採用しない。既存release契約で対象限定反映と自然readbackを確認する。需要のノイズを原因未確認の自動rollback条件にしない。

## 選択肢と推奨

1. 推奨: 自然失敗一件と既存testの対応を整理し、欠けた境界だけをownerの修理atomへ追加する。新wrapperを足さない。
2. AutomationBenchをそのまま比較評価に使う: 汎用業務能力を速く測れるが、既存production障害を直接再現できるとは限らない。外部baselineの後続候補。
3. 人生全体の新frameworkを作る: 範囲が広くoutcomeの曖昧さが増す。現在は採らない。

## 文書の完了条件・後続の受入

今回は一次資料と実コードの対応、spec/plan整合、専用branchへcommit/pushとremote object確認で文書成果とする。議論用draftであり実装完了とは呼ばない。

次のpilotは一枚の匿名case card、既存test coverage対応、未測定境界、修理ownerへの接続を成果とする。実不具合を確認できなければ修正やREDを捏造しない。境界が確定した後に、exact files/interfacesと最小RED/GREENを持つ修理planをそのownerのatomで書く。

公開benchmarkにはagent実行adapter・別管理の未見task・異なるharness・独立再現が必要。lab採用・leading・AGI・全無人・収益保証は独立証拠が揃うまで成果として主張しない。

## Q&A: 調査で解消した設計上の疑問

2026-10-12のlatest main、Life Managerの既存CLI/runtime/eval/Writer、OpenTelemetry・Langfuse・Braintrust・Phoenix・Inspectの公式docs、Sentry/PagerDutyの製品説明、GEPA・OpenEvolve・SICA・DGMの公開code/papersを照合した回答である。設計判断と、自然データが必要な成果を分ける。

### Q1. Observability、traceability、trace、evalは同じか？

**回答:** 同じではない。Observabilityはlogs/metrics/tracesから未知の問題も調べられる性質。Traceは一回の実行の経路をspansの親子関係で記録する。Traceabilityはtask・実行・release・receipt・outcome・graderを相互参照できること。Evalは実結果をtaskの成功条件に照らして採点する。OpenTelemetryはtelemetry標準でありbusiness outcome graderではない。

### Q2. lm-loop status / doctor / healthは使えるか？

**回答:** 使う。status/healthは最新のread-only runtime状態を調べ、doctorはregistry・loaded label・entrypoint等を診断する。health observerは状態history・alert・recovery intentを保存する。これらはcaseのrunと失敗箇所を探す入口であり、業務成功とは数えない。

### Q3. 現在のruntime eventはdistributed traceとして十分か？

**回答:** runの失敗診断とeffect/readback参照には使えるが、distributed span traceそのものではない。現行eventはrun_id、owner_id、occurrence_id、release_sha、failure_layer、error_class、next_action、provider_receipt_id、official_readback_refを持つ。今回調べたruntime/eval pathsにはOpenTelemetry SDKやtrace_id/span_idのspan treeは見つからなかった。最初は既存JSONL/artifactを使い、eval case/runをevaluation resultで結ぶ。runtime run_idとexternal effect occurrence_idの意味を変更しない。sub-operationの因果が実caseの診断に不足すると確認された場合だけspanを追加する。

### Q4. どの製品を今入れるか？

**回答:** Pilot Aでは新backend/eval frameworkを導入しない。Life ManagerのCLI、runtime JSONL、Writer gate、既存Node LM-EAB scorerを使う。trace reviewが実際に難しいと分かった場合に限り、online/offline eval・dataset・CIをまとめ、self-host可能なLangfuseを最初のtrace/eval UI trialにする。OpenTelemetryは必要なspanの共通規格。Braintrustはhosted experiment/online scoring、PhoenixはOTel-native eval UI、Inspect AIはisolated task/solver/scorer harnessの候補。すべてを同時導入しない。

### Q5. 最初のpilotはWriterか、effect recoveryか？

**回答:** Pilot AはWriterの一記事のpre-publication quality stage。18件のcatalog metadataと既存artifactを比べ、評価・bounded recovery・候補比較が揃い、公開前に反復できるsliceとして選ぶ。金融・費用adapterは部分実装なので、Writerのquality PASSは利益の実証にならない。
このspecのeffect-unknown recovery caseはPilot Bの安全性caseとして残す。Pilot BはAの品質caseを置き換えず、外部effectを再送せずに照合する別のfailure familyを検査する。既存recovery-intent/apply-plan testsはhold/no-retry/wrong-ownerを既に検査するため、同じassertionのwrapperを作らない。自然failureと業務outcomeの紐付けで欠ける境界だけを追加する。

### Q6. Writer quality gateを通れば収益が増えるのか？

**回答:** それは未証明。Quality gateはarticle qualityを測り、売上はdistribution、audience、price、platform、refund、fee、costにも左右される。publish URL、顧客receipt、settlement、refund/fee、費用coverageが揃うまではnet unknown。quality PASSをrevenue upliftと呼ばない。経済効果はsame-channel/periodのreceipt-backed baseline/candidateで測り、trafficが少なければ標本不足と報告する。

### Q7. 何を一つのscoreにするのか？

**回答:** 初期には一つへ潰さない。identity/safety/effect-integrityはhard gate。task completion、quality、settled net、cost、latency、人の介入、recovery time、再発率を別々に表示する。費用やreadbackの欠測はunknown。採用条件はSSOT I02のfrozen baselineと事前条件で決める。

### Q8. Code grader、LLM judge、人の判定をどう分けるか？

**回答:** hash、schema、receipt ID、重複、公開状態、金銭算術はcodeで採点する。reader task fitやclaim relevanceなど意味の解釈が必要な項目のみrubric/LLM judgeを使い、expert labelsで較正する。Writerの既存80点eval-gateは品質signalであり、settled revenue scoreではない。judge failureをagent failureに付け替えない。

### Q9. Dataset・trial・held-outはいくつ必要か？

**回答:** 固定合格件数はまだ置かない。まず自然failure一件と正常/危険対照を作り、taskとgraderの矛盾を検査する。Anthropicの20–50 failure-derived tasksは初期の参考値で、収益の統計的有意性を保証しない。必要trial数はpilot varianceと検出したい差から決める。tuning/devとheld-out/challengeを分ける。公開LM-EABのheld_out labelは秘密testではない。

### Q10. Self-healingとself-improvementはどう回すか？

**回答:** Self-healingは自然failure → owner-scoped intent → 有限のsafe recoveryまたはblock → 次のnatural outcome/readback。Self-improvementは一候補 → 凍結grader/baselineで比較 → 条件を通った候補だけ小さくcanary → natural receipt確認。CIはcode/prompt変更のoffline evaluation、observerは自然runのonline outcomeを担当する。評価の都合でpublish/payment/applyを再実行しない。unknown external effectは公式readbackまでholdする。

### Q11. 既存OpenEvolveでWriterも自動改善できるか？

**回答:** 現sourceの根拠ではできると主張しない。skills/earn/self-improve/evaluator.pyとrun_evolve.shはhistorical backtest candidateをscope guard・risk-adjusted score・promotion gateで評価し、live order executionを呼ばない特定のinvestment-strategy loopである。Writerを含む全18業務のoptimizerではない。GEPAはtrace feedbackからprompt候補を提案し、SICA/DGMはcoding benchmark上でself-modifying agentを比較する。これらは機構の参考であって、Life Managerの売上証拠ではない。

### Q12. 本番利用されている自己修復製品は何をするか？

**回答:** Sentry Seerはproduction error telemetryを調べ、root causeとfixを提示・生成する製品機能を公開している。PagerDuty AI Agentsはincidentをtriageし、SRE Agentはapproved remediationを実行する製品機能を説明している。これはsoftware/SRE障害で「検知→調査→修復→再確認」を支援する例で、Life ManagerのWriter品質、顧客売上、netを評価する製品ではない。vendor docsの機能説明を、Life Managerでの効果や全顧客の無人運転の独立証拠と扱わない。

### Q13. Evalをどう自動で回し、いつ止めるか？

**回答:** code/prompt変更時はfrozen offline regression/capability suite、自然業務終了時はreceipt/evidenceに対するonline outcome scoring、定期処理はnet/cost/再発集計を行う。各cycleは固定試行数・時間・cost budgetを持つ。grader改変、safety failure、systemic error、effect_unknownは自動採用・再送を止める。候補agentにgrader、held-out、permission、spend-capを編集させない。I03本番採用はsource evaluationのみで完了としない。

### Q14. 「不確実性をなくす」は可能か？

**回答:** 用語、責任境界、計測方法の曖昧さは本Q&Aで設計判断として閉じる。市場成果やjudgeの一致率は実験前には決められない。そのempirical unknownにclosure evidenceを指定する。

| empirical unknown | closure evidence |
|---|---|
| taskからrun/receipt/netまで結べるか | Writerの実occurrence一件をsource refsから再構成し、missing/foreign occurrenceを0で確認 |
| judgeが人の判断と合うか | blinded held-out labelsでfalse-pass/false-failを別々に測る |
| Writer quality改善がsettled netを上げるか | receipt/cost-covered same-channel baseline/candidate comparison。標本不足ならunknown |
| self-healが再発・人手時間を減らすか | 同failure classのbefore/after natural recovery、official outcome、replay-zero |
| 新trace UIがCLI/artifactより役立つか | 同caseでtriage時間、root cause発見、導入/運用費を比較 |

### Q15. このspecとcanonical TODOの関係は？

**回答:** 新しいTODO正本も順序変更も作らない。Unified SSOTのE01 current cursorはrelease adoption/natural evaluation。E02は自然障害とCFO official receipt接続、E03はnatural task family、E04はcase/runner/grader/baseline/splits/calibration/trials、E05は別harness reproduction、E06は報告と限界公開。Writer Pilot AはE02/E03のcase候補で、quality PASSだけでE02/E03完了とはしない。H01–H04とI01–I04の所有者・順序もcanonical SSOTが持つ。

## Q&Aの一次資料と実装出典

- [OpenTelemetry Observability Primer](https://opentelemetry.io/docs/concepts/observability-primer/)
- [Langfuse evaluation](https://langfuse.com/docs/evaluation/overview) / [Braintrust eval cycle](https://www.braintrust.dev/docs/evaluate) / [Phoenix evals](https://arize.com/docs/phoenix/evaluation/llm-evals) / [Inspect AI](https://inspect.aisi.org.uk/)
- [Sentry Seer](https://sentry.io/product/seer/) / [PagerDuty AI Agents](https://www.pagerduty.com/platform/ai-agents/)
- [GEPA](https://github.com/gepa-ai/gepa) / [OpenEvolve](https://github.com/codelion/openevolve) / [SICA](https://github.com/MaximeRobeyns/self_improving_coding_agent) / [Darwin Gödel Machine](https://github.com/jennyzzt/dgm)
- Life Manager latest-main source: runtime event, lm-loop health/observer, Writer eval-gate/money ledger, LM-EAB guide, Unified SSOT.