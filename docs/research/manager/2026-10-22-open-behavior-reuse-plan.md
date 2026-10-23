# Manager：公開研究を先に再利用する設計変更

日付：2026-10-22、実装状況追記：2026-10-23。Managerは仏教的AIエンティティ／デジタル仏陀。これは既存SSOTへ参照される設計・差分計画であり、新しいTODO状態正本ではない。E16と原Phase00–12の完了・未完了をこの記事で変更しない。

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

Slice Aは2026-10-22、Slice Bは2026-10-23に専用worktreeで実装・検証し、両方ともPR #8575として2026-10-23にmainへ統合された（merge commit `b7c9d150684d0278ec7011e2a9981cef2e3f952f`）。Aは自己完結した標準ライブラリの公開source inspector、Bはhash検証済みの非公開snapshotに対する固定study-holdout集計CLIと任意研究依存のNumPy/SciPyを使う診断であり、Manager runtimeの追加・複製・統合ではない。C–Fは下記の未実装案のままであり、runtime接続やE16/Phase受入の状態を変更しない。task状態は既存SSOTだけが所有する。

| 順 | ファイル・接続点 | 最小変更 | 完了を示す検証 |
|---|---|---|---|
| A | 実装: `products/manager/scripts/inspect_external_behavior_benchmark.py`、`products/manager/tests/test_external_behavior_benchmark.py`。旧companionは委譲entrypoint | 固定 `reuse.json` pinsを先に照合し、Fig1 panelA/Bをstrict analysis。他の取得sheetはinventory、PDFはhashのみ。原データはprivate、出力は集計のみ | 23 synthetic tests。全4ファイルfixtureで同じ長さの改変を作り、`python -O` のinternal API child processがparse前の `SOURCE_HASH_MISMATCH` を返すことを確認。CLIのsanitized error/empty stdout/exit 2は別に確認。実snapshot 70/3356/129/1678・group counts・GPT-4 summaries・4 hashes照合済。新規推論ではない |
| B (PR #8575でmain統合済) | `products/manager/manager_core/external_behavior_eval.py`、`products/manager/scripts/evaluate_external_behavior_benchmark.py`、focused test、任意依存の固定requirements | 既存inspectorのhash-first validated loaderを再利用。効果量を[-1,1] full scaleで保持し、zero/raw/train-only weighted through-origin betaを比較。NumPy/SciPyは通常runtimeの必須依存ではない | 固定SHA-256層別study split、study単位bootstrap、pair→outcome→studyのmacro平均。欠測≠0。direction coverageとtieを明示。Pearsonは対称方向を使った記述的な反対称associationのみ。選択目的未指定ならregret null。詳細と再現手順は[released-effects診断](2026-10-23-released-effects-diagnostic.md)参照。 |
| C (未実装) | 新 `scripts/twin_wave4_eval.py`、対応するfocused test | 公式QuestionID/mappingでwave1–3のみ入力。既存 `phase04_socsci_individual.py::evaluate_predictions` の分母・split設計を参考にする。まず配布出力を再採点 | wave4回答・full_persona漏洩を検出。個人/分布/subgroup/coverageを別表示。新規推論は小subsetで費用計測後 |
| D (未実装) | 新 `scripts/public_event_forecast.py` と予測記録schema | 決算説明会の公開先例を模倣。公開前入力cutoff・対象・採点法・モデル・予測hashを固定し、後日公開記録で採点 | cutoff後情報混入と後出し予測変更を検出。過去質問等の強いbaseline、欠測と失敗を報告。個人の非公開属性は不要 |
| E (未実装) | 必要時、新 `scripts/concordia_behavior_eval.py`。既存 `concordia_island_mock.py::run` は保持 | upstream engineへ薄い接続。処置対照は同一初期状態・対応seed、条件間memoryを隔離 | 実モデル実行/費用/seedと外部参照の効果誤差。mock完走を人間妥当性にしない |
| F (未実装) | 既存 `evidence.py::validate_record/load_verified_trial`、`scripts/heartsteps_phase3.py`、既存kernel/publisher | 予測→選択→実行→独立readback→行動→持続/害/費用の参照を接続。歴史研究は過去の証拠、自分の新介入は別occurrence | 実行receiptと便益の区別、比較対象、欠測、持続、group別不利益。歴史RCT再採点だけで新P4を発行しない |

### Slice A/B の統合済み検証範囲

`python -B -m unittest discover -s products/manager/tests -p 'test_external_behavior_benchmark.py' -v` は23 testsがpass。合成OOXMLでshared/inline strings、必須cell/header、hash前倒し、重複・逆方向・完全比較graph・study group、Fig3等の空panel inventoryを検査した。SHA-256照合は、同じ長さを保った合成supplement改変を含む全4ファイルfixtureで、`python -O` child processからinternal APIにfixture metadataを渡して `SOURCE_HASH_MISMATCH` を直接確認し、CLIのsanitized errorは別に検査した。実データを使った一度の照合では70 studies、3,356 directed rows、129 study×outcome blocks、1,678 unordered pairs、published/unpublished 1,572/1,784、panelB 8 rows、4つのmanifest hash、公開GPT-4 raw/adjusted correlationを確認した。canonical CLIとlegacy entrypointは別current directoryから同一JSONを出した。source-boundary guardはクラウドhostにcanonical pathがないためFAILのまま記録し、変更していない。

Bのfixed split評価を含むfocused suiteはAの23件とBの27件、計50 testsがpassし、任意のNumPy 2.2.6 / SciPy 1.15.3環境で実行した。合成fixtureは階層macro重み、study単位split/区間、方向・tie coverage、条件名再ラベル不変の対称Pearsonを含む。通常runtimeへ研究依存を追加しない境界も確認した。実snapshotの最新aggregate receiptと科学的解釈は[診断レポート](2026-10-23-released-effects-diagnostic.md)に記録した。

この結果は歴史的released aggregatesのinspectionおよび固定splitの後ろ向き診断である。3356 directed rowsを独立試験とみなさず、receipt記載の469 distinct effectsも469件の独立複製を意味しない。Bでは35/35 study splitを保持し、固定train fitに条件付けたtest-study percentile区間を算出した。原著のrandom-reference/attenuation/LOSO/megastudy top-20% protocolや全training/effect sampling uncertaintyを再現したとは主張しない。過去論文でのLLM学習 exposure はstudy単位holdoutだけでは排除できないため、歴史データ評価と、将来結果を見る前に予測を固定するD sliceは別の証拠として扱う。具体的な指標・不確実性・限界は[2026-10-23診断レポート](2026-10-23-released-effects-diagnostic.md)に記録した。

新しいbaselineを超える必要性や測定上の穴が見えてから学習・追加taskへ進む。全候補のclone/install/大規模推論を先行させない。新benchmarkの名前より、既存との互換性と追加で検証できる能力を示す。

## 研究・実装・執筆の関係

E16は有限な実行能力の工程として引き続き既存handoffで進める。今回の公開研究経路をE16のホスト待ちに従属させず、過去の合成fixtureやページ公開の成功で原Phase受入を済ませない。各研究の結果を原稿・再現記録・図・スライドへ展開し、本の「人工社会・説得・介入評価」章へ編入する。記事数、調達、採用、YC応募を、実行動や純便益の証拠として数えない。

根拠：[新しい日本語章](articles/2026-10-22-artificial-societies-open-behavior-research-ja.md)、[一次資料の取得・版・ライセンス記録](evidence/artificial-societies-20261022/README.md)。科学的不確実性は残るが、企業アクセスを待たずに進められる研究作業を具体化した。

## 追加一次資料の設計判断（2026-10-22）

- [Social Science Prediction Platform purpose](https://socialscienceprediction.org/purpose/)、[FAQ](https://socialscienceprediction.org/faq/)、[forecast guide](https://socialscienceprediction.org/ForecastingGuide)、[example research](https://socialscienceprediction.org/example_uses)から採るのは、population・endpoint・単位・予測時点・expert baselineを固定し結果前に予測をlockする方法。利用料無料でもplatform codeと収集dataは公開されていないため、必須runtime/data依存にはしない。
- [Gym megastudy paper](https://www.nature.com/articles/s41586-021-04128-4)と、論文に掲載された[OSF閲覧link](https://osf.io/9av87/?view_only=8bb9282111c24f81a19c2237e7d7eba3)、[node metadata](https://api.osf.io/v2/nodes/9av87/?view_only=8bb9282111c24f81a19c2237e7d7eba3)、[official file inventory](https://api.osf.io/v2/nodes/9av87/files/osfstorage/5f8f58d7b11ee900215a8342/?view_only=8bb9282111c24f81a19c2237e7d7eba3)を過去の実行動endpointを使う外的評価候補として採る。論文の54 armsと介入材料ZIPの53 XLSXを同数扱いせず、全trial再現や新規LLM予測も未実施。OSF node licenseはnullでCode/Dataの再配布権を確認していないため原filesを転載せず、初期は設計・source reference・自作集計だけを残す。
