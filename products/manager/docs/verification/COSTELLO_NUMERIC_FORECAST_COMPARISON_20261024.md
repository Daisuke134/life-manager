# Costello numeric forecast — finite comparison closed

2026-10-24 UTC。A09の別G7評価sliceとA11の有限比較を完了した。**単一adapterの全102 contextの出力は事前値と完全一致し、persistenceを超える予測能力は確認できない。採用HOLD。** 人への介入・便益・全V002/V003の受入ではない。

## 固定した実行と実terminal

[学習receipt](COSTELLO_NUMERIC_TRAIN128_20261024.md)の単一artifactを再学習/選別せず使った。固定design SHA256は`f9010431cc7dd4a2edfda9db901fb7265986c032a125ad0f725f291f0180d6ca`。生成sourceは`f265018e2fab45262e383b0a76b5ad8be4ff0279`、[公式CI](https://github.com/Daisuke134/life-manager/actions/runs/40095519739)成功、1182 tests/skip6、新規10件実行PASS。local全1208/skip5との差26件は任意NumPy/SciPy不足によるmodule skip。fresh whole-code reviewはfinding0。通常CIはモデル性能の証明ではない。

別root G7 admission SHA256 `ed682f7be97dc086f7143653ddf34e7fdeee6bbb2162f8fbc786160d9be953bd`を生成前に0400固定。各armは1800秒/sample own-group RSS5GiBで直列に一回ずつ。throughputは事前未測定で、完走保証はしなかった。CPU2、既存ローカルQwen/PEFT/Transformersを使用し、新規有料計算契約なし。実金額はUNKNOWN。

| arm | context数 | elapsed秒 | sampled peak RSS bytes | native terminal |
|---|---:|---:|---:|---|
| frozen base | 102 | 461.704 | 1,968,340,992 | exit0、wait/reaped、PID不存在、group空 |
| frozen single adapter | 102 | 338.605 | 1,963,966,464 | exit0、wait/reaped、PID不存在、group空 |

各monitorの戻り後にconfig/monitor SHAを結ぶdurable operator terminalが残った。operator shim自身のreapはNOT_CLAIMED。旧SafetyBenchのouter-reap未成立はそのまま。記録されたretry/resume/extensionはいずれも0。

入力はpre50..100 × Control/Treatmentの102 feature context。標準greedy generation、batch1、max_new_tokens16、one-integer JSON、修復/clippingなし。生成側は個票ID/人labelを開かない。同一promptへの一つの結果を全assigned参加者へ対応付け、102 contextを102人と数えない。

両arm正常終了後、正解値と照合する前に生成結果freeze SHA256 `95d0d2f0ff2f10e999476d1d11744636836ff44edf3a00911d24fa3181730345`を0400固定した。事前のoperator解析script SHA256 `c0f4c125da6c504d4e265c0a84d2a3eb8c55654124a15f3f65ce4cc4bf5a5c31`とも結合。保存adapterの元11ファイルhashは生成後も一致した。私有comparison JSONのSHA256は`6f87fb2e06f1b067ff0a45099e3700d3420421452dfbc4328ce194cf997b0996`。

## 全分母と結果

[公開aggregate JSON](../../experiments/behavior-model/costello-numeric-forecast-results-v1.json)に全state/条件別/感度分析を保存した。devは584 assigned /568 labelled /16 missing、evaluationは762 /738 /24。単位は本人報告confidenceの0–100 slider pointsで、真偽・個人因果効果・苦しみの量ではない。

| 方法 | valid/assigned dev | dev MAE / RMSE | valid/assigned evaluation | evaluation MAE / RMSE |
|---|---:|---:|---:|---:|
| persistence | 584/584 | 14.778169 /25.551315 | 762/762 | 13.962060 /24.346249 |
| train128 mean | 584/584 | 22.202410 /27.764881 | 762/762 | 20.711255 /26.668905 |
| train128 OLS | 584/584 | 15.624753 /21.655268 | 762/762 | 14.101310 /20.907382 |
| frozen base | 0/584 | null /null | 0/762 | null /null |
| frozen adapter | 584/584 | 14.778169 /25.551315 | 762/762 | 13.962060 /24.346249 |
| NO_ACTION abstention | 0/584 | null /null | 0/762 | null /null |

baseは102/102がこの固定出力契約のINVALIDで、全participant rowsへ伝播した。UNKNOWN/NOT_RUNは0。baseの予測MAEを0や100に置き換えない。全observed-label分母へ最大100点を置く感度分析の値100は、観測されたbase MAEではない。出力契約/16-token予算内での不成立であり、モデルの一般的な予測不能・説得不能を示さない。NO_ACTIONは意図した棄権で、原著のControl群とも別。

adapterは102/102 VALIDだが、すべてのpre/conditionでoutput=preだった。persistenceとの差が0なのは同じ出力による。苦しみや治療効果の同等性ではない。既存devのR baseline値と今回の統計baseline値は1e−10以内で一致した。

paired participant bootstrapは2000/seed20261024、Python random.Random/choices、type7 percentile。adapter−persistenceのMAE差はdev/evaluationとも0、区間[0,0]。adapter−OLSはdev −0.846584、95%区間[−1.806021,0.076805]、evaluation −0.139251、区間[−0.851423,0.620064]。原著/QC曝露済みwave内の記述で、pristine一般化や同等性検定ではない。旧R bootstrapとはRNGが異なり、同じ区間の再現とは言わない。baseとの共通valid labelled pairsは0で差/区間はnull。

全point-forecast armsがcompleteという事前条件を満たさず、判定はPARTIAL_NO_SUPERIORITY_CLAIM。OLSのRMSEが小さくても、事前primary MAEを切り替えない。

## 独立検証と終了判断

別context reviewerが、元比較entryを再実行せず、保存済み新split/生成結果から全分母・全arm/条件のMAE/RMSE・bootstrapを独立算術で照合した。885 checks PASS、finding0。rootは全文reportと現在の16 evidence hashesを確認した。review JSON SHA256 `e3818753f2e28b67ebc45bdc1df5719276b77f19cb5c8b1036321253eaa8e746`。依頼model/effortはgpt-6-astra/high、actual native readbackはUNKNOWN。独立検証は新model生成・重みの再学習・旧final16再採点ではない。

この候補はHOLDとして閉じる。同じevaluationへの再学習/再採点による選別はしない。次の用途は別design/split/rightsの研究として決める。会話品質の部分eval候補は[AnnoMI現物監査](../research/2026-10-24-annomi-artifact-audit.md)、実行動/便益は既存U004以降の別研究が必要。専用利用者UIは必要条件に戻さない。

新しいManager参加者0、介入0、便益/圧力/依存/害は未測定。旧final16不使用、model採用HOLD、tasks.json85 done /18 todo /10 skippedを維持する。main統合/production適用/YC提出/収益をこのreceiptで進めない。
