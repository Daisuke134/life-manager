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

## 実装・再利用経路

Slice AはPR #8555として2026-10-22にmainへ統合された（merge commit `2fd21dbfb35d5ae4e8b99cb8c5cae8fbcef65db2`）。Slice Bは別のPR #8575として2026-10-23にmainへ統合された（merge commit `b7c9d150684d0278ec7011e2a9981cef2e3f952f`）。Aは自己完結した標準ライブラリの公開source inspector、Bはhash検証済みの公開効果集約に対する固定study-holdout診断であり、どちらもManager runtimeの追加・複製・統合ではない。Cは固定Twin wave4 snapshotの検査と既公開出力の記述的agreement監査までが実装済みで、full behavioral modeling/evaluationの完了ではない。Dは予測の事前固定方法と、1件の未来FOMC reference forecastのsource-lock/attestationまでが存在するが、イベント結果の採点は未了である。E/Fは未実装案のまま。これらの状態はruntime接続やE16/Phase受入を変更しない。task状態は既存SSOTだけが所有する。

| 順 | ファイル・接続点 | 最小変更 | 完了を示す検証 |
|---|---|---|---|
| A (PR #8555でmain統合済) | 実装: `products/manager/scripts/inspect_external_behavior_benchmark.py`、`products/manager/tests/test_external_behavior_benchmark.py`。旧companionは委譲entrypoint | 固定 `reuse.json` pinsを先に照合し、Fig1 panelA/Bをstrict analysis。他の取得sheetはinventory、PDFはhashのみ。原データはprivate、出力は集計のみ | 23 synthetic tests。全4ファイルfixtureで同じ長さの改変を作り、`python -O` のinternal API child processがparse前の `SOURCE_HASH_MISMATCH` を返すことを確認。CLIのsanitized error/empty stdout/exit 2は別に確認。実snapshot 70/3356/129/1678・group counts・GPT-4 summaries・4 hashes照合済。新規推論ではない |
| B (PR #8575でmain統合済) | `products/manager/manager_core/external_behavior_eval.py`、`products/manager/scripts/evaluate_external_behavior_benchmark.py`、focused test、任意依存の固定requirements | 既存inspectorのhash-first validated loaderを再利用。効果量を[-1,1] full scaleで保持し、zero/raw/train-only weighted through-origin betaを比較。NumPy/SciPyは通常runtimeの必須依存ではない | 固定SHA-256層別study split、study単位bootstrap、pair→outcome→studyのmacro平均。欠測≠0。direction coverageとtieを明示。Pearsonは対称方向を使った記述的な反対称associationのみ。選択目的未指定ならregret null。詳細と再現手順は[released-effects診断](2026-10-23-released-effects-diagnostic.md)参照。 |
| C (bounded released-data audit実装済、PR #8580 `e02b6e8284577f9671821fdcaef289ea9c96d6c6`、PR #8599 `d8e16607797ef218843e09cd530aa5c1c8b7465c`) | `products/manager/scripts/twin_wave4_eval.py` と `products/manager/tests/test_twin_wave4_eval.py` | `reuse.json`にpinされた5入力と公式MAD scorerをhash確認後、既存released outputとwave1–3 history／wave4 target間の集約agreementを監査する。任意依存は専用[`requirements-twin-wave4-eval.txt`](../../../products/manager/requirements-twin-wave4-eval.txt)。5入力・CLI・再現制約は下記「C: released agreement audit」を参照 | 出力はdescriptive aggregate。provenance/run binding/training exposure不明、predictive accuracy null、`scientific_pass=false`。将来モデル推論、full persona/subgroup検証、人の行動・便益評価は未完了 |
| D (事前固定方法と1件のreference forecastのみ実装済) | method PR #8585 commit `16cb856861528124e89fb0983bbe59f382eb4afc`。FOMC reference forecast PR #8593 commit `f6055f9460502cd79cba95ffadecb998439e1056`、byte attestation PR #8595 | source/cutoff/target/baselineを事前固定する手順を記録。FOMC 2026-10-27–28は公開履歴頻度による決定的な `p=0.25` referenceのみ | この確率は同じ歴史頻度baselineと等しい。model call・human probability judgment・独立性能の主張はない。会合結果はまだなくscore unavailable。一般forecasting評価、accuracy、human outcomeは未完了 |
| E (未実装) | 必要時、新 `scripts/concordia_behavior_eval.py`。既存 `concordia_island_mock.py::run` は保持 | upstream engineへ薄い接続。処置対照は同一初期状態・対応seed、条件間memoryを隔離 | 実モデル実行/費用/seedと外部参照の効果誤差。mock完走を人間妥当性にしない |
| F (未実装) | 既存 `evidence.py::validate_record/load_verified_trial`、`scripts/heartsteps_phase3.py`、既存kernel/publisher | 予測→選択→実行→独立readback→行動→持続/害/費用の参照を接続。歴史研究は過去の証拠、自分の新介入は別occurrence | 実行receiptと便益の区別、比較対象、欠測、持続、group別不利益。歴史RCT再採点だけで新P4を発行しない |

### Slice A/B/C と D の統合済み検証

A/Bの既存検証記録は維持する。Bは公開Nature集約値の後ろ向きdiagnosticであり、CのTwin結果とは異なるdataset/taskである。Cについては、構造的inspector PR #8580 (`e02b6e8284577f9671821fdcaef289ea9c96d6c6`) と公式MADを加えた集約監査 PR #8599 (`d8e16607797ef218843e09cd530aa5c1c8b7465c`) がmainに統合済み。Cのfocused suite 23 testsを含むB/C suiteは、追加したoptional scorer依存を使ったPython 3.12.14環境で73 tests passした。これはtestsと決定的集計の再現であり、科学的passではない。

#### C: released agreement audit

実行対象は`products/manager/scripts/twin_wave4_eval.py released-agreement <INPUT_DIR> <OFFICIAL_CODE_PATH>`。`<INPUT_DIR>`は私有のローカルsnapshot directoryで、次の5ファイル全てを置く。各byte countとSHA-256は repositoryの[`reuse.json`](evidence/artificial-societies-20261022/reuse.json)に固定され、CLIは一致を検査する。raw CSVはrepositoryやpublic artifactへコピーしない。

| local filename | role | SHA-256 |
|---|---|---|
| `catalog.json` | official question catalog | `e72e305f0c7c83bb990e97de4c0cf2c718ead18cc197239b7feeb354c9ac1bef` |
| `mapping.json` | official wave4-to-catalog mapping | `345f7f6645f80dc23bcb423a9bb7c5ae77dbbd17fe572472fdfeb252bdcfc2c7` |
| `history.csv` | wave1–3 human responses | `fc227b1682e2654fd4b2a8152294b68118c0e3be4d83f4a9af5f3e96df56d3f0` |
| `target.csv` | wave4 human responses | `09ec1a88bdd48fec95963da3102df0ca467378bf729cbc1c0b869b0f1e4fb942` |
| `output.csv` | released GPT-4.1-mini output (generation provenance unverified) | `22937217115db30c064489125e39ceb0539c461b678400d8b3e0827962e5436c` |

`<OFFICIAL_CODE_PATH>` must be the exact official `evaluation/mad_accuracy_evaluation.py` fetched from `tianyipeng-lab/Digital-Twin-Simulation` revision `f1eed510c9a4fb47aaa9bb46e178aaa2d9224623`; before import, the CLI requires SHA-256 `b25b7912310c14393b62dcaf5c214496189f98eb82398e86bb8004a14785ff96`. Do not vendor that upstream source into this repository. Its imports include pandas, matplotlib, and yaml in addition to B's NumPy/SciPy. The optional requirements file installs only the tested pinned scorer imports on top of the existing B requirements; it is not an ordinary Manager dependency and does not recreate the full upstream Poetry/model environment. The upstream `pyproject.toml` uses broad constraints, so these pins establish only the tested scorer-import environment.

With Python 3.12.14, NumPy 2.2.6, SciPy 1.15.3, pandas 2.2.3, matplotlib 3.10.8, and PyYAML 6.0.3, the existing C CLI reproduced the complete aggregate byte-for-byte. The checked-in aggregate is [`twin-released-agreement-20261023.json`](evidence/twin-released-agreement-20261023.json), SHA-256 `f3556911ca7be301a0481c7505ff7fbd32206d175e1a8ce94f71deed9a519bbb`; it retains the 197,580 common native-valid cells. The same B/C focused command completed 73 tests (23 Twin gate, 23 external inspector, 27 released-effects evaluator). The initial reproduction report's missing-pandas failure remains preserved; see the completed scorer follow-up at `/workspace/scratch/manager-e16-cloud-completion-20261022/pinned-scientific-reproduction-complete-scorer.md` for the follow-up environment and result.

For a repeat run, make an isolated Python 3.12 environment and install the optional pins; do not add them to the ordinary Manager environment. The private snapshot directory must contain the five filenames above, and the official scorer file must match the fixed revision and hash. Keep the output aggregate and Matplotlib cache in private temporary paths; compare the resulting aggregate with the checked-in JSON rather than overwriting it.

```bash
python3.12 -m venv "$TWIN_WAVE4_VENV"
"$TWIN_WAVE4_VENV/bin/python" -m pip install \
  -r products/manager/requirements-twin-wave4-eval.txt
curl -fsSL \
  https://raw.githubusercontent.com/tianyipeng-lab/Digital-Twin-Simulation/f1eed510c9a4fb47aaa9bb46e178aaa2d9224623/evaluation/mad_accuracy_evaluation.py \
  -o "$TWIN_WAVE4_OFFICIAL_SCORER"
printf '%s  %s\n' \
  b25b7912310c14393b62dcaf5c214496189f98eb82398e86bb8004a14785ff96 \
  "$TWIN_WAVE4_OFFICIAL_SCORER" | sha256sum -c -
MPLCONFIGDIR="$TWIN_WAVE4_MPLCONFIG" MPLBACKEND=Agg \
  "$TWIN_WAVE4_VENV/bin/python" \
  products/manager/scripts/twin_wave4_eval.py released-agreement \
  "$TWIN_WAVE4_PRIVATE_SNAPSHOT" "$TWIN_WAVE4_OFFICIAL_SCORER" \
  > "$TWIN_WAVE4_PRIVATE_AGGREGATE"
sha256sum "$TWIN_WAVE4_PRIVATE_AGGREGATE"
cmp "$TWIN_WAVE4_PRIVATE_AGGREGATE" \
  docs/research/manager/evidence/twin-released-agreement-20261023.json
```

Set each `TWIN_WAVE4_*` variable to a path outside the repository. The pinned official source declares dependencies in its upstream [pyproject.toml](https://raw.githubusercontent.com/tianyipeng-lab/Digital-Twin-Simulation/f1eed510c9a4fb47aaa9bb46e178aaa2d9224623/pyproject.toml); those broad upstream constraints and model packages are not installed by this optional file. The exact versions here are the tested import set needed by this released scorer, not a full upstream environment reproduction.

Interpret this JSON as a descriptive agreement audit only. It records `generated_cell_provenance=UNVERIFIED`, `generation_run_binding=UNKNOWN`, `model_training_exposure=UNKNOWN`, `predictive_accuracy=null`, top-level `accuracy=null`, and `scientific_pass=false`; human outcomes are `NOT_MEASURED`. Hash-valid inputs and agreement rates do not verify which process generated output.csv, exclude training exposure, establish predictive accuracy on independent future data, or demonstrate human behavior/benefit. The audit does not complete C's proposed future modeling, full-persona, subgroup, or intervention-effect evaluation.

#### D: method and one prospective reference case

The D method commit `16cb856861528124e89fb0983bbe59f382eb4afc` freezes a single public-event question, source cutoffs, deterministic reference rule, and exact payload for later read-only attestation. PR #8593 adds the [FOMC 2026-10-27–28 reference forecast](predictions/fomc-2026-10-27-28/README.md) and [deterministic procedure](predictions/fomc-2026-10-27-28/REFERENCE_PROCEDURE.md), using the historical-frequency baseline: `p=0.25`, deliberately equal to that baseline. PR #8595 (attestation commit `ef41dd2453a84140d7caf877a6ec4b1ae0853b81`) verifies the frozen payload bytes before the input cutoff; the [attestation record](predictions/fomc-2026-10-27-28/ATTESTATION.json) validates the record lock, not forecast accuracy. As of 2026-10-23 the meeting outcome is unavailable, so no score or independent performance estimate exists. No model was called and no human probability judgment was collected. General public-event forecasting evaluation remains future work.

E/F remain unimplemented proposals. The published 2026-10-22 research article and the original Slice C/D future evaluation goals should not be labeled complete based on these bounded C/D artifacts.

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
