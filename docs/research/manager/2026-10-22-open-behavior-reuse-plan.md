# Manager：公開研究を先に再利用する設計変更

日付：2026-10-22。Managerは仏教的AIエンティティ／デジタル仏陀。これは既存SSOTへ参照される設計・差分計画であり、新しいTODO状態正本ではない。E16と原Phase00–12の完了・未完了をこの記事で変更しない。

## 方針変更

小さな所有サイトの変更成功は実行・復旧・公開確認の試験である。行動予測・介入効果の科学的妥当性を示す主経路にしない。研究の中心を **既存AS Benchmark → 公開人間データ／公開実験効果 → 単純baseline比較 → 公開未来イベントの事前固定予測 → 必要時のみ相互作用engine → 実環境での行動・便益測定** へ置く。

Rothko私有weights、商用provider契約、企業提携、個票NDA、巨大な新規仮想都市は初期依存にしない。MITの既存評価、CC BY4.0のTwin、公開済み予測、公開実験の集約結果から開始する。Nature Source Dataは公式download・方法参照・集計検査に使い、未確認の再配布権を推定しない。課金upgradeは行わない。既存の実行kernelと公開経路を維持する。

## 採用・保留

| 採用対象 | 役割 | 条件と現状 |
|---|---|---|
| AS Benchmark固定commit46b8ed52 | 分布、一貫性、実験効果等の既存採点 | code MIT/results CC BY4。66pass/9skip・scorecard再構築は既存記録で確認 |
| Nature DOI s41586-026-10742-x | 元実験材料→条件予測→差分→研究単位の較正／評価の方法 | 公開SI・Source Data検査済。原著全文/全code再現ではない |
| Twin HF f883165a3026fde855dfd448e0cd16443ab257b6 | wave1–3→wave4、配布LLM出力の再採点 | CC BY4.0/ungated。wave4回答を入力に混入しない |
| SMS megastudy公開集約 | 実接種の介入順位・効果予測 | 後ろ向き評価。非公開医療個票は初期依存から外す |
| DebateGPT | 訂正監査付きの意見変化評価 | code MIT/data CC BY-SA4。実行動の効果と区別 |
| 既存Concordia | 相互作用が不可欠な問いだけ | Apache2、既存adapterを拡張。必要なく全engineを追加しない |
| OASIS | social-feed固有の問いが生じた場合の比較候補 | Apache2。ConcordiaとはPython要件が異なる |
| AgentTorch/AgentSociety | 要件が生じた後の候補 | 前者current AGPL3、後者commercial例外あり。必須依存にしない |

## 実装時のatomic patch順

下記は**まだ実装完了ではない差分案**。対象は既存Manager実装ブランチの `products/manager/`。現在mainへ未統合のManager runtimeを、この調査PRへ混ぜない。task状態の更新は各受入後に既存SSOTで行う。

| 順 | ファイル・接続点 | 最小変更 | 完了を示す検証 |
|---|---|---|---|
| A | 新 `scripts/inspect_external_behavior_benchmark.py`、新 `tests/test_external_behavior_benchmark.py` | 今回の解析companionを雛形に、固定URL/revision/hash・単位・取得範囲を出す読取専用CLI。元データはprivate store、結果は集計のみ | ハッシュ不一致、欠損cell、重複対比、研究単位・対照方向の誤りを検出。70研究/3356配布対比を元receiptと照合。推論成功と呼ばない |
| B | 新 `manager_core/external_behavior_eval.py`、対応するfocused test | AS upstreamの効果採点と既存 `evaluation.py::total_variation/brier_score` を意味が適合する場合に再利用。効果量は単位を保持し、無効果・train-only平均・固定modelを比較。相関／回帰／区間は既存SciPy/statsmodels等を使う | 研究丸ごとのsplitとcluster単位の不確実性。欠測≠0、効果方向・MAE・較正・選択損失。`eba_benchmark.py::score_suite` のsynthetic契約は緩めない |
| C | 新 `scripts/twin_wave4_eval.py`、対応するfocused test | 公式QuestionID/mappingでwave1–3のみ入力。既存 `phase04_socsci_individual.py::evaluate_predictions` の分母・split設計を参考にする。まず配布出力を再採点 | wave4回答・full_persona漏洩を検出。個人/分布/subgroup/coverageを別表示。新規推論は小subsetで費用計測後 |
| D | 新 `scripts/public_event_forecast.py` と予測記録schema | 決算説明会の公開先例を模倣。公開前入力cutoff・対象・採点法・モデル・予測hashを固定し、後日公開記録で採点 | cutoff後情報混入と後出し予測変更を検出。過去質問等の強いbaseline、欠測と失敗を報告。個人の非公開属性は不要 |
| E | 必要時、新 `scripts/concordia_behavior_eval.py`。既存 `concordia_island_mock.py::run` は保持 | upstream engineへ薄い接続。処置対照は同一初期状態・対応seed、条件間memoryを隔離 | 実モデル実行/費用/seedと外部参照の効果誤差。mock完走を人間妥当性にしない |
| F | 既存 `evidence.py::validate_record/load_verified_trial`、`scripts/heartsteps_phase3.py`、既存kernel/publisher | 予測→選択→実行→独立readback→行動→持続/害/費用の参照を接続。歴史研究は過去の証拠、自分の新介入は別occurrence | 実行receiptと便益の区別、比較対象、欠測、持続、group別不利益。歴史RCT再採点だけで新P4を発行しない |

新しいbaselineを超える必要性や測定上の穴が見えてから学習・追加taskへ進む。全候補のclone/install/大規模推論を先行させない。新benchmarkの名前より、既存との互換性と追加で検証できる能力を示す。

## 研究・実装・執筆の関係

E16は有限な実行能力の工程として引き続き既存handoffで進める。今回の公開研究経路をE16のホスト待ちに従属させず、過去の合成fixtureやページ公開の成功で原Phase受入を済ませない。各研究の結果を原稿・再現記録・図・スライドへ展開し、本の「人工社会・説得・介入評価」章へ編入する。記事数、調達、採用、YC応募を、実行動や純便益の証拠として数えない。

根拠：[新しい日本語章](articles/2026-10-22-artificial-societies-open-behavior-research-ja.md)、[一次資料の取得・版・ライセンス記録](evidence/artificial-societies-20261022/README.md)。科学的不確実性は残るが、企業アクセスを待たずに進められる研究作業を具体化した。
