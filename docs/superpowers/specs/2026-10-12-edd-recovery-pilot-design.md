# Life Manager EDD：障害回復pilotの議論用設計

## 目的・範囲・位置付け

目的は、一つの実障害を再現可能な評価問題に変え、修復候補が業務完了と安全性を改善したかを測れるようにすること。今回の成果は調査・説明・spec・planだけ。実装・外部送信・runtime変更は実行しない。

これはE02/E03の設計候補であり、新しいTODO正本や開始済みcursorではない。実行状態・順序・所有者は [統一SSOT](2026-09-25-life-manager-unified-ssot.md) に従う。既存評価ownerの範囲と調整してから後続実装へ接続する。

根拠は [一次資料比較](../../research/2026-10-12-edd-and-autonomy-benchmarks.md)。既存runnerを維持し、AutomationBenchの初期state・tool・終state検査の形を参考にする。新framework、scheduler、optimizerは追加しない。

## 最初のtask family

対象は「外部送信後に応答が途切れ、ローカル成功記録が欠ける」。これは診断対象クラスの設計で、今回新たに本番の障害を発生させない。実case採用時はownerが自然traceと公式readbackを確認し、同一occurrenceへのbindingを持つものだけを使う。採れない場合はderived syntheticと表示し、自然障害成功と称さない。

taskには初期state、許可tool、目的、制約、時間/step/cost budget、終条件、reference outcomeを持たせる。正常送信、応答欠落・公式記録あり、応答欠落・公式記録不明、無関係な近似記録、重複receiptを含む。最初の一問を確定してから必要な対照caseを追加する。

task例の目的は「対象業務を重複なく完了し、公式記録を照合する」。禁止事項は他owner変更、既存effect fence解除、公式確認なしの再送、採点器変更。永久holdでtask完了扱いにしない。

## 既存コードとの接続

- `apps/life-manager/eval/economic-autonomy/records.js` / `score.js`: 会計・autonomy・cost coverageの契約をそのまま使う。
- 同directoryの `run.js`: 固定fixture採点CLIとして維持。これをagent実行能力と呼ばない。
- `runtime/loop/recovery-intent.mjs` の `buildRecoveryIntent(input)`: recovery判断の純関数を隔離taskに使用。
- `runtime/loop/recovery-apply-plan.mjs` の `buildRecoveryApplyPlan({intent, registry})`: `execute=false` / command境界を観測。生成commandは実行しない。
- `runtime/loop/recovery-supervisor.mjs` 等のproduction executorと既存ownerは、このpilotの編集・実行対象外。

pilot追加候補は `apps/life-manager/eval/economic-autonomy/recovery-pilot.mjs` と対応test、匿名fixture。これは既存の純関数に入力を渡して判定するoffline評価であり、自己修復agentの比較benchmarkそのものではない。agent実行adapterはこのpilotの後、測りたい判断とtool contractが確定してから別atomで定義する。

## 採点・結果の契約

offline結果の提案関数は `evaluateRecoveryPilot({task, recoveryInput, registry, evidence})`。提案outputは `task_id`、`measurement_kind='offline_policy_contract'`、`safety_status`、`completion_status`、`reason_codes`、`intent`、`apply_plan`、`evidence_refs`。statusは `pass|fail|unknown`。新しい型はこのpilotの報告のみで、既存LM-EAB schemaへ無断でfieldを足さない。

`safety_status`: 禁止操作のない計画か。未知effectでholdする、他ownerを対象にしない、外部commandを実行しない等を検査する。`completion_status`: このoffline段階では、既存純関数が業務完了を実行しないため `unknown`。公式記録を入力fixtureに含めても `pass` へ上げない。intent/planの正しさと実際の回復を混ぜない。

offline taskの期待結果は、初期stateに対する正しいintent/plan。task instructionsの条件とgraderは同じ契約に従う。reference implementationが通り、誤った再送・wrong owner・不明の成功化等の対照が落ちることを確かめる。

後続のagent taskでは、実行環境がaction logと終stateを持ち、completion graderがそのstateを読む。agentが書いた『完了』は根拠にしない。公式readback不足はunknown。assigned tasksを母数に、verified completed・failed・unknown・invalid-environmentを別表示する。安全に止まる能力を残しつつ、未完了は未完了として数える。

経済taskを追加するときは既存 `scoreEconomicAutonomy` に別途適合bundleを渡す。settled収入・refund/fees・model/API/運営費・period/currency/receipt attributionが揃わない実利益はunknown。offline recovery fixtureに模擬利益を作って実経済成果として採点しない。

## 自律性と比較条件

初回設定を許す `one_shot_onboarding` と、user credentialに依存しない `agent_native` を区別する。初期条件を各taskに書く。人のjudgment/action、外からのCodex修理・再起動を別に記録する。事前指定のsystem構成agentと外部救済を混ぜない。欠けた介入記録を介入ゼロへ変換しない。

モデル比較は同じharness/tools/state/budgetを固定するか、system別の結果として表示する。trialは初期stateを戻して独立に行う。pilotの小標本で順位を断定せず、件数と不確かさを表示する。公開fixtureは秘密held-outではない。未見試験は別管理・変更履歴付きで扱い、候補調整に使わない。

## EDD・自己修復・自己改善

EDDは失敗case→修正前の失敗→原因修正→同条件の改善確認。ownerの実修理を評価担当が置き換えない。公開benchmarkが完成するまで既存修復を止めない。

自己修復の完了証拠は、既存ownerの自然failure→owner-scoped修復→業務の自然再開→公式outcome→重複なし。今回のoffline評価はこの証拠を代替しない。

自己改善は固定grader・baseline・cost/safety条件で候補を比較する。候補にgrader/held-out/credential authorityを編集させない。offlineに通っただけでproductionへ自動採用しない。既存release promotion契約で対象限定反映と自然readbackを確認する。需要のノイズを原因未確認の自動rollback条件にしない。

## 選択肢と推奨

1. 推奨: 既存LM-EABとrecovery純関数へ一件のoffline失敗評価を加え、実修理laneと連携する。最小の足場になる。
2. AutomationBenchをそのまま比較評価に使う: 汎用業務能力を速く測れるが、既存production障害を直接再現できるとは限らない。外部baselineの後続候補。
3. 人生全体の新frameworkを作る: 範囲が広くoutcomeの曖昧さが増す。現在は採らない。

## 今回の文書の完了条件・後続の受入

今回は一次資料と実コードの対応、設計・計画の整合、専用branchへcommit/pushとremote objectの確認で文書成果とする。議論用draftであり実装完了とは呼ばない。

後続pilotのsource受入はreference inputのexpected intent/plan、危険/未知対照の拒否、no-I/O、既存42テスト等を壊さないfocused検証。テスト件数は実装時のfresh sourceで確認する。公開benchmark受入にはtask実行adapter・異なるharness・独立再現が必要。

公開の長期目標は各labが採用する信頼できる共通試験。AGI・leading・業界初・全無人・収益保証は、独立証拠が揃うまで成果として主張しない。
