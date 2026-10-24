# Costello numeric forecasting — research decisions and next implementation

**Goal:** 公開実験条件における本人報告confidenceの予測を、単純統計と一つのLoRAで有限比較する。説得文生成・個人因果効果・苦しみ低減の研究とは分ける。

**Spec:** [既存仕様§23](../MANAGER_PRODUCT_SPEC.md)、[親Task8](2026-10-23-behavior-transformation-model-plan.md)、[固定design](../../experiments/behavior-model/costello-numeric-forecast-design-v1.json)。新しい状態台帳ではない。

## A05–A08で決めたこと

- 入力は事前confidenceと割付条件の2列だけ。Controlは無関連のAI対話、Treatmentは当該beliefについてのAI対話。政治属性・demographics・個票ID・会話本文・事後情報を入力しない。
- 出力は`{"post_belief":整数0..100}`の一つのJSON。本人報告を予測し、真偽や信念の正当性を採点しない。primary MAE、secondary RMSEと条件別誤差。自己報告sliderを確率goldと見なしてBrier採点しない。
- Study1のlabelあり738人から、結果値を使わない公開participant-keyのSHA順で128人を固定。Study2aはdev584 assigned/568 labelled、Study2bはevaluation762 assigned/738 labelled。公開key上のwave間participant重複0、bridge欠落0。別releaseの人物同一性やpretraining非汚染は未証明。
- 同じ2-feature promptの重複は、異なる人が同じ事前値/割付を持つため起こり得る。人物リークと混同せず、ID非重複とfeature-pattern重複を別に扱う。
- 公開資料はQC/上流解析に曝露済み。evaluationをpristineとは呼ばない。新LLMの成績とevaluationのbaseline成績は未観測で、学習/adapter選別前に新designを固定した。
- 比較はNO_ACTION棄権、事前値維持forecast、train128平均、train128 OLS、Qwen3-0.6B base、単一LoRA。NO_ACTION棄権と原実験のControl群は異なる。
- 元学習と同じ標準PEFT/TRL、r8/q_proj+v_proj、alpha8、dropout0、seed42、batch1/accum4、1epoch、lr0.0002を使う設計。128例/32optimizer機会。NLL学習はMAEの直接最適化ではないことを報告する。
- 無改善なら不採用。dev結果を見てprimaryをRMSEへ変更したり、同じevaluationへ合うまで学習を繰り返したりしない。

## A06: 実development baseline

新LLM呼出しなし。全baselineに同じ128 training rowsを使い、Rの既存`lm`を利用した。割付とtrain平均で中心化したpreの交互作用、予測は0–100にclip。dev584件に予測し、labelあり568件で誤差を計算、残16件のhuman label欠測を保持した。

| 方法 | 予測coverage | MAE | RMSE |
|---|---:|---:|---:|
| NO_ACTION棄権 | 0/584 | null | null |
| 事前値維持 | 584/584 | 14.778169 | 25.551315 |
| train128平均 | 584/584 | 22.202410 | 27.764881 |
| train128 OLS | 584/584 | 15.624753 | 21.655268 |

OLS−事前値維持のpaired MAE差は+0.846584、participant bootstrap2000/seed20261024の95%区間[-0.128847,1.791192]。OLSはRMSE点推定では小さいが、事前固定MAEでは改善未観測。dev内の記述で、未見一般化/同等性を結論しない。evaluation762件はこのbaseline計算で採点していない。原著再現では同waveの集計/ラベルを扱っており、完全盲検の主張もしない。

## A09: 確認済みと未成立

確認済み: 現hostはcgroup8GiB/CPU2、native train用venvにtorch2.8.0+cpu、transformers4.56.2、TRL0.23.1、PEFT0.17.1等が存在。既存baseのselected asset存在をstatで確認。新しいweights/tokenizer load/forwardは0。空きdiskは観測時約8.2GBで予約ではない。

**学習開始はまだ受入していない。** 既存`helpsteer2_candidate_sft.py`は27例と元protocol/hashに固定され、新しい128例を渡せない。そこを緩めず、次の最小source作業を行う。

1. 新しいsource専用の薄いloader/parser/callerを追加する前に、2-feature以外の漏洩、participant重複、NA→0、範囲外/余分fieldの予測、partial→full扱いを拒否するREDを定義する。
2. 標準SFTTrainerを呼び、既存のasset/save/receipt検証の形を再利用する。新trainer・optimizer・agent runtimeは作らない。旧entry・旧final16は変更/再利用しない。
3. CPU2・train900秒/sampleRSS5GiBは提案上限。新code/実資源とgeneration throughputの事前確認後に、評価上限を別固定する。現時点で当該上限内完了や全評価coverageを保証しない。
4. 元MCQのouter-wait消失を踏まえ、既存durable実行ownerの再接続耐性と実wait/終了記録を確認する。code review/正確なsourceの通常CI/外部freezeがそろってからA10を開始する。

A05–A08は研究設計/私有入力準備として成立し、学習code実装済みではない。A09はresource/software確認済み・上記source/CI/実行owner未成立。全V002/V003、model採用、実人便益は受入していない。

## A09実装の具体的な接続（後続作業）

新規sourceは`manager_core/costello_forecast.py`（strict入力/予測JSON、人物分離、固定私有splitの読取、全分母/欠測/部分結果の採点）、`manager_core/costello_forecast_train.py`（外部0400設定から標準SFTTrainerへ一度だけ接続）、`scripts/train_costello_forecast.py`（薄いCLI）。旧train27 entryと科学定義は変更しない。

- `parse_case(row: dict) -> ForecastCase`は固定promptの2feature以外を拒否し、`target=None`を維持する。ID/値はreprへ出さない。
- `read_prepared(directory) -> dict[str, tuple[ForecastCase,...]]`はdesignと私有manifest/各splitのbytesを固定hashで検証し、operator側でselection/人物非重複を確認する。
- `read_training(directory) -> tuple[ForecastCase,...]`はnative用。manifestとtrain_selected.jsonlだけを開き、dev/evaluation fileは開かない。実audit hookで128例とこの2fileだけのopenを確認済み。
- `parse_prediction(raw) -> int`は一つの整数fieldだけを受理し、duplicate key、bool、float、範囲外、code fence、修復を拒否する。
- `score_predictions(cases, predictions) -> dict`はVALID/INVALID/UNKNOWN/NOT_RUN/ABSTAINとhuman label欠測を別に数える。conditional MAE/RMSE、全label分母のworst-case bound、coverageを別表示し、部分結果をcompleteへ変えない。実evaluationの採点はまだ行わない。
- `build_training_example(case, tokenizer)`は既存completion_maskを使い、user promptをlossから外し、native assistant completionとEOSだけを学習する。
- `training_kwargs(output_dir)`は1epoch/batch1/accum4/seed42/lr0.0002と標準NLLを固定。`run_train(config_path)`はsource/版/実monitor/基底asset/evidence/private ACL検証後にのみMLをimportし、旧save/有限tensor/optimizer-member検証を再利用する。

外部設定kindは`manager.costello-numeric-train128.v1`、accepted_actionsは`train128_private_once`のみ。全sourceは実Git commit bytesと照合する。base/tokenizerは旧科学定義の固定8asset pinsだけを借り、旧データ/学習許可/評価を借りない。空asset表や別weightsのcaller再宣言は拒否する。review/official CI/data-purposeはrootが実確認したGit外の別evidenceを結び、hashを権限の暗号学的証明とは呼ばない。

テストは`tests/test_costello_forecast.py`と`tests/test_costello_forecast_train.py`。未実装状態のREDを観測し、入力漏洩/型/重複人物/欠測/部分分母/マスク/保存前の未観測gradient/CLI静音/基底再宣言を検証する。実native学習、A09の全受入、A10開始は、独立review・正確なsourceの公式CI・durable実行ownerと別外部freezeが成立した後。

### 終了監視の有限な事前確認

既存のprivate `helpsteer2_watchdog.monitor`の固定sourceを再利用する。新しい常駐ownerや第二のmonitorは作らず、privateの薄いdurable shimがその関数を呼び、戻った後にconfig/monitor-terminalのSHAと実child wait/reap/PID不存在/group空をfsyncして記録する。外側の起動元shellの終了後にもshimが動くことを、標準Pythonのsleepだけのcanaryで確認した。native子はexit0、reaped/PID不存在/group空、elapsed2.440秒。新LLM/学習は0。

新研究のterminal契約は、固定monitorが実際にnative子をwait/reapした記録と、戻り後のdurable operator terminal、正常save/inventoryを結ぶ。shim自身のreapを観測済みとはしない。旧SafetyBench v1の別outer-reap条件を事後変更せず、UNFINALIZEDを保持する。この新しい有限契約は、モデル学習開始前の独立review/外部freezeで別受入する。通常CIや事前の資源検査だけで実nativeの成功を推定しない。
