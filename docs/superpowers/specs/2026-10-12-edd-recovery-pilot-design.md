# Life Manager EDD：障害回復pilotの議論用設計

## 目的・範囲・位置付け

目的は、一つの実障害を既存の回帰試験と対応付け、修理の前後を測れるようにすること。今回の成果は調査・説明・spec・planだけ。実装・外部送信・runtime変更は実行しない。

これはE02/E03の設計候補であり、新しいTODO正本や開始済みcursorではない。実行状態・順序・所有者は [統一SSOT](2026-09-25-life-manager-unified-ssot.md) に従う。既存評価ownerの範囲と調整してから後続作業へ接続する。

根拠は [一次資料比較](../../research/2026-10-12-edd-and-autonomy-benchmarks.md)。既存runnerを維持し、AutomationBenchの初期state・tool・終state検査の形を参考にする。新framework、scheduler、optimizerは追加しない。

## 最初のtask family

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
