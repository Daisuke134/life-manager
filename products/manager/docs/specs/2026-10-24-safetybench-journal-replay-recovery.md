# SafetyBench保存記録の限定再生・回復scope

2026-10-24。行動変容を通じて、苦しみを終わらせることを目指すManagerのoffline研究について、失われた外側waitの証明と、保存済み選択の分析を分ける限定scope。

**この本文のGit採用は事後の公開記録である。** 実際の別枠受入は、最初のモデル正答集計より前の **2026-10-24T07:15:53.377269Z** に、Git外の新しい0400設定・root freezeで固定した。元の[実行scope](2026-10-23-safetybench-local-model-execution.md)や受理済み設定を、後から成功条件へ書き換えたものではない。

## 元の実行と未達条件

- 実推論sourceは `51b7d45b3c82a4962af16c19433c4e6c1927def6`（H）。通常統合したPR [#8801](https://github.com/Daisuke134/life-manager/pull/8801) のsquash merge `714e0041d617e579ce0c3a3c7d90e49dfe34c0db`（M）と区別する。
- 元の単一attemptは2026-10-23T23:56:49.008416Zに開始し、2026-10-24T02:56:50.137804Zに内側monitorが `RESOURCE_LIMIT / WALL` を保存した。固定予算10,800秒・6,442,450,944B、実経過10,801.129秒、sampled process-group peak RSS 2,433,519,616B。停止判定とcleanupによる1.129秒の超過を隠さず、kernelのhard reservationとは扱わない。
- 内側CLIのreturncodeは-15、実wait/reap済み、PID不存在・元process group空を元monitorが記録した。retry/resume/extensionは0。保存された706回のheartbeatと最後のterminal printは停止直前まで継続していた。会話observerの消失だけから内側monitorの空白を推測しない。
- 元の外側waiterは再接続時に利用不能となり、独立outer-wait proofとwrapper-reap receiptがない。wrapperは終了済みのZ状態・未reapで残る。waiter消失の正確な原因・時刻はUNKNOWN。kernelの終了statusを、元の `Popen.wait()` を観測した証拠へ置き換えない。
- 元v1 finalizationは **`UNFINALIZED_MISSING_OUTER_REAP`**、operational gateは **UNMET** のまま。通常finalizerは呼ばず、元producer/envelope/result/wrapper-reap receiptも作らない。古い開始markerのRUNNINGやprogressのINITIALIZEDは、現在の生存・処理件数の根拠にしない。

## 別枠の一度だけの記録再生

元の推論・tokenizer・weights・adapterを再実行せず、保存されたjournalを、既存Hの `read_journal` / `reconcile_rows` / `_summary` / `_dataset` と `safetybench_mcq.evaluate_recorded` へ渡す。既存の照合・採点実装を再利用し、別scorerや常駐engineを作らない。元のsource、科学protocol、入力、設定、freeze、journal、assignment、terminalは保全する。

新しい限定受入の条件は以下に固定した。

1. rootが、元のconfig/freeze/launch/assignment/journal/native terminal、別のdead-wrapper metadata、20 source file、helper、独立review、5 regular inputのhashと実permission、新しい出力先を事前に結ぶ。source入力が公開されていることからfilesystem modeを推測せず、現物の0600を維持する。raw質問/正解は0600、私有directoryは0700、実受入設定は0400。
2. 元child PID不存在・child group空、元wrapperの同一identity・Z状態・そのgroupに当該Z一件だけ、という範囲を確認する。他ownerを含む全workspaceのmodel不存在はUNKNOWNとし、無関係なcmdlineを走査しない。group inventoryの消滅race以外の確認不能は、空集合へ変換せず採点前に拒否する。
3. 全11,435件の元assignment・順序・membershipを保持する。開始記録だけの行はUNKNOWN、未着手はNOT_RUN、その他のstateも別に残す。subset選別、fallback、回答修復、再推論、resumeをしない。元の2 controlsも維持する。
4. 新しい0700出力directoryと排他的consumed markerで、一度の分析だけを消費する。marker後の失敗も自動retryしない。新しいproducer receipt→従来形式のrecorded envelope→既存scorer一回→新しいresultの順で保存する。元attemptの出力pathへ書かない。
5. 新receiptのschemaは `manager.safetybench-orphaned-journal-replay-receipt.v1`。statusは常に **`PARTIAL_OR_FAILED_REPLAY_ONLY`**、analysis kindは `DETERMINISTIC_RECORDED_REPLAY_ONLY`。`original_v1_finalization=UNFINALIZED_MISSING_OUTER_REAP`、`outer_wrapper_reaped=false`、`native_child_reaped=true` を分離する。元v1のCOMPLETEDを主張する経路はない。

独立reviewのR1で実terminal key、実permission、process inventoryの3不整合を検出し、原本を変えずにhelperを修正した。R2の差分reviewは0 findings、authored testsは9件PASS。これは新しい記録再生の前提確認であり、元outer-waitの回復証明ではない。通常のユーザー委任に基づくrootの技術判断で、別枠の事前受入を実施した。

## 固定した受入・成果物の識別

| 対象 | SHA256 |
|---|---|
| 元0400 execution config | `d471e87dc217332abe11b4a07b6b49a11b1e7975e3b7edd0baa4cbc7b8e70acd` |
| 元native terminal | `ffd31f21695897403510d0df0a5a752291b12edad6fd1316a44805c7f0080e9d` |
| 元journal | `88d3ad20df45d916772441c4ccca2837b0a1cc7254731b397e2410e2b8c47cfb` |
| 別枠0400 replay acceptance | `cdad857c08f9d217f38a5f30edc823106467dc9a24440a37e3d8c5bbd147938d` |
| 実root replay freeze | `f5ee2dfd8681d9547bf31124d7eb3d9418629af9231f2b60d856482bd16a36f0` |
| 修正後helper | `74dcc571e80b5507877e9107410817e2f90c3b9bb590f5ac3a9b695717a32971` |
| 事前独立R2 review | `bb838e226e7a4f1491c55d7e62d4b690840a4cc828dcb165c3b5dc6e6e928861` |
| 新producer receipt | `c5355752b6d82f78355c3adc4d01f1fd0d33d7d71320663cfaeaeb8d005b30eb` |
| 新recorded envelope | `420468f27cc365010b5a82b4d23967d1fc1c19769315d209107116101930a17d` |
| 新result | `c812487f13b6e60e7514ccf660d5a255dd33e93caa8287121344a91aac867877` |
| 事後の実結果独立検証 | `961d810fe7529b16838eaebfd5ae87d5e93307a5f8572ea189a23dfbebd92551` |

元の科学protocol `9122507cde91a8ffd9510fb5ad1227b34c5296931ffde3c1b0b888ba4aa32727`、MCQ protocol `6369fe7f5b9ead9569892acf77da9c8b60d1b4f0933cf79e55562f99041e394e`、選択rights record `07e6beea0bf5570a9b1fab8153c80306dde7a1f29159125109b6b03e16648fd4` は不変。H/mainの5件・researchの18件という既存registryを維持し、新しい権利recordを加えない。

別の実結果独立検証は2026-10-24T07:21:02.989578Zに0 findingsで終了した。標準libraryによる全割当・journal/row対応・category/state/二対照の算術・hash連鎖・保存時刻順を照合し、既存scorerやmodelを再実行していない。元v1未完了という判定も保持した。この事後検証を、最初の採点前の受入と混同しない。source採用は通常のreview・PR・CI・公式readbackで別に扱う。

## 解釈・終了境界

集計結果は[検証receipt](../verification/SAFETYBENCH_LOCAL_QWEN3_CLP_CPU_20261023.md)へ分ける。全割付分母の割合と有効選択だけの条件付き一致率を区別し、未着手・UNKNOWN・棄権・失敗・categoryごとの未測定を残す。source-orderで打ち切られたprefixは無作為標本ではなく、全件controlと条件付きprefixをそのまま比べて優位としない。CLPの有効形式は自由文応答の拒否・害・依存・臨床・便益の証明ではない。

producerの `DECLARED_NOT_AUTHENTICATED` は、hash一致だけで外部認証済みに変えない。costはUNKNOWN、proofはP0、人の便益はNOT_MEASURED、can_execute=false、モデル採用はHOLD。raw再配布・training・製品利用の許諾へ拡張せず、全row provenanceも未検証のまま。元final16はSCORED/NOT_PRISTINEで、再利用・retune・再採点しない。

この回復scopeは、元運用の未達と、別枠の記録分析を有限に報告するためのもの。全V002/V003、実行動変容・苦しみ低減、AGI/Digital Buddhaの実証を認定せず、113 IDs=85 done /18 todo /10 skippedを変更しない。次の推論・別モデル・再学習を自動許可しない。将来の新しいnative研究には、用途に合う別受入と、既存の耐久性ある実行ownerで真のouter waitを保持できる手順が必要であり、今回のjournalへ追加推論して埋めない。
