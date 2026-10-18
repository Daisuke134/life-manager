# マネージャーの人口基盤：原子パッチ実装計画

> 実装時は `superpowers:executing-plans` を使い、パッチを順番に実行する。完了状態は統合管理文書へ記録する。この文書には手順を記す。

**目的：** 宇宙全体・すべての生命を対象とするマネージャーの最初の証拠/人口/独立評価部品を、実資料と既存の公開ライブラリから作る。

**構成：** 米国の公開人口統計を取得し、出典を記録する。初期分布、周辺集計、評価専用の交差集計を分離し、独立性を仮定する基準手法と反復比例適合を比較する。評価結果にはバージョンを付け、後続の環境モデル、反応予測、方策、実行処理へ接続できる形で保存する。

**使用技術：** Python 3.12以降。`ipfn==1.4.4`、`numpy==2.4.4`、`pandas==2.3.3`を固定し、標準ライブラリの`unittest`で検証する。

**仕様：** [宇宙規模の全体定義](../specs/2026-10-12-manager-universe-design.md)、[人口部品の厳密な仕様](../specs/2026-10-12-manager-population-v0-design.md)、[6作業の受入計画](2026-10-12-manager-population-v0.md)。

**2026-10-18 データ選定補足：** [比較と採用理由](../../research/manager/articles/2026-10-18-manager-dataset-selection-ja.md)。D01/B17001の人口v0を維持し、PUMS世帯部品は次段階の第一候補とする。P07/P09のメタデータでは対象母集団・期間・地理・推計という性質を保持し、P19では隠した交差集計の復元評価と、独立採取の観測・将来予測・実地便益を区別する。今回P01–P20の実装を完了にはしない。PUMS・ATUS・BRFSSを6セル入力へ足さない。

## 共通条件

- v0は最初の部品であり、マネージャーの製品定義を人口統計へ縮めない。
- 公式B17001は50州+DC51地域、2020–2024の推計、6セル、開発用6地域、検証用4地域、最終評価用41地域。完全な世界状態ではない。
- 計算処理は公開ipfnを利用。収束状態値と実残差を別検査。対象の人数が0の軸を除外して計算後に復元する。反復は最大1000回、正規化した残差は1e-10以下。
- 参照値は評価だけに使う。再構築処理には、対象地域の交差集計を保存したファイルのパスを渡さない。
- 実装・モデル実行・有料サービス利用の実績と、計画作成・資料の事前確認を区別する。

## 確認する点

1. ウェブページの本文、別の統計表、未知の列を人数として受け入れない（P05）。
2. 欠測・欠測を表す特別な値・地域不足を0で埋めない（P06/P07）。
3. 行順や評価用の交差集計の変更が初期分布や地域分割へ影響しない（P08/P09）。
4. ライブラリの早期停止、人数0の軸、反復回数の上限を再計算で検出（P11/P12）。
5. 出典のハッシュ値不一致と実地未測定を隠す報告書を拒否（P14/P16/P18）。

## 取得元と保存する資料

|ID|取得元と固定点|取得/保管するもの|どこで何に使うか|
|---|---|---|---|
|D01|[米国の公式人口統計ファイル](https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b17001.dat)|見出し行と州等の52行。抽出データのハッシュ値 `316b602beb75129605d91ca7a9c440a37df7bc9c02271d86d3eb39cf25559a9d` を事前確認で確認|`population/acs.py`→Git外の`input/source.dat`。全生命のうち人間人口を表す最初の実観測入力|
|D02|[ACS B17001 項目定義](https://api.census.gov/data/2024/acs/acs5/groups/B17001.json)|項目名/年齢/貧困の階層。データ取得の照会はキー必須、v0では使わない|`config/population-v0.json`の項目対応・期間・対象母集団に固定。B17001E混入を拒否|
|C01|[Dirguis/ipfn](https://github.com/Dirguis/ipfn/tree/fa57b905291e4125c6e4f7ddacc8770218ad024e)、[PyPI1.4.4](https://pypi.org/project/ipfn/1.4.4/)|MIT `licence.txt`、配布ファイル SHA `a0b5f3c9c5de8c71207cc88f1e51b68135d482a50d7035c58f3e202d33a6b026`、公開`ipfn/ipfn.py`|`population/fit.py`の接続処理から数値配列の計算処理を利用。計算処理自体を再発明しない|
|C02|NumPy2.4.4/pandas2.3.3 PyPI 項目定義|Python対応と依存関係。間接依存も含むバージョンとハッシュ値の固定一覧をP02で作る|ipfnの依存。言語モデルや画像処理装置は必要としない|

元資料と実行結果の保存先は `/workspace/artifacts/manager-population/`。実行場所の変更時はコマンドの引数で指定し、中核処理へ実行先固有パスを埋めない。

## パッチの実行順

### 第8単元として見せる実装のまとまり（2026-10-18）

学習7.5はデータと方式の比較。第8単元は以下の実装・実行・検証であり、説明だけで完了としない。進捗はSSOTのみ。

|まとまり|パッチ|作るもの|確認できる結果|
|---|---|---|---|
|A 出典と実行環境|P01–P03|pyproject.toml、固定依存、THIRD_PARTY_NOTICES.md|分離環境でimportでき、依存と出典を再確認できる|
|B 観測の取込|P04–P07|population/contracts.py、population/acs.pyと対応テスト|公式ファイルから取り出し、不正・欠測・重複を拒否する|
|C 入力と答えを分離|P08–P09|population/prepare.py、config/population-v0.json|開発6/検証4/評価41、初期表と周辺集計と参照表を別々に出す|
|D 2方式を実装|P10–P12|population/fit.pyと対応テスト|単純独立法と公開ipfnを同じ契約で比較できる|
|E 評価と保存|P13–P17|benchmarks/population.py、artifacts.py、cli.pyと対応テスト|残差・TVD・群別誤差、出典と版付き結果を再生成できる|
|F 実資料の結果を公開可能にする|P18–P20|実資料の実行結果、README、解説、検証記録|良い結果も悪い結果も同じ条件で再実行できる|

この人口v0は集計表の復元まで。次のPUMS世帯部品は、pums.py/households.py/integerize.pyと世帯単位の評価を追加する別スライス。現段階でBN・拡散・LLMを全部の必須依存へしない。PUMS比較で採用する方式とインターフェースを確定してから追加する。

予定配置：

```text
apps/manager/
  pyproject.toml
  requirements-population.in
  requirements-population.lock
  THIRD_PARTY_NOTICES.md
  config/population-v0.json
  src/manager/
    population/{contracts,acs,prepare,fit}.py
    benchmarks/population.py
    artifacts.py
    cli.py
    __main__.py
  tests/test_population_*.py
  tests/test_acs.py
```

復元は初期表と周辺集計を受け取り、評価用交差集計のパスを受け取らない。採点は復元結果と参照表を別引数で受け取る。出力先はGit外のartifactsとし、記事はその実行結果から数値を引用する。

各パッチには、変更するファイルと関数、入力、確認方法を記す。実装では、先にテストを書いて失敗を確認し、最小限の変更で同じテストを成功させる。コミットは6作業の意味のある完了単位で行い、空ファイル一個ごとのコミットは要求しない。

|パッチ|一つの作業|正確な変更先/入力|検証と期待結果|
|---|---|---|---|
|P01|パッケージ境界を作る|`apps/manager/pyproject.toml` Python>=3.12、`src/manager/__init__.py`。パッケージ名は`manager`、既存実行環境依存なし|`PYTHONPATH=apps/manager/src python3 -c 'import manager'` 成功。この段階ではパッケージの入口だけを作る|
|P02|固定CPU依存をバージョンとハッシュ値の固定一覧にする|`apps/manager/requirements-population.in`: ipfn1.4.4, numpy2.4.4, pandas2.3.3。分離した `/workspace/scratch/manager-population/.venv-population`で依存解決処理の結果から`requirements-population.lock`を作りすべての間接依存のバージョンとハッシュ値を固定。ipfn 配布ファイルのSHAはC01と一致必須|`python3 -m pip download --only-binary=:all: --dest /workspace/artifacts/manager-population/wheels -r apps/manager/requirements-population.in`。確定した配布ファイルをSHA256で固定一覧へ。固定一覧から`--require-hashes`で再ダウンロードできる。互換性は後の単体テストで判定|
|P03|第三者ソースの来歴を保存|`apps/manager/THIRD_PARTY_NOTICES.md`へipfn MIT/著作権/固定コミット、NumPy/pandasの上流の利用条件。`docs/research/manager/2026-10-12-manager-upstream-lock.json`を参照|出典の固定コミット、配布物のハッシュ値、利用区分が一致。公開アクセスとデータ利用許諾を混同しない|
|P04|人口型と不正値の失敗を確認するテストを書く|`apps/manager/tests/test_population_contracts.py`。JointTable(人数 sum≠total)、Marginals(row/col totals≠total)、NaN/negativeでPopulationDataErrorをassert|`PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -p test_population_contracts.py -v` FAIL|
|P05|型と値の検証を実装して成功する|`src/manager/population/contracts.py`。仕様に定めたSourceRef/JointTable/Marginals/FitResult/PopulationScore、frozen、6cell order、finite/nonnegative/total検証|P04と同じコマンド PASS。真偽値を人数などの数値として受け入れない|
|P06|取得検証の失敗を確認するテストを書く|`tests/test_acs.py`。html、B17001E、見出し行不足、duplicate、estimate sentinel、EOF不足、ハッシュ値の改ざんをfixture/mockで検証|`PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -p test_acs.py -v` FAIL|
|P07|公式ファイルの抽出処理を実装|`population/acs.py`: `fetch_acs_extract(destination,timeout_seconds=30,max_bytes=8388608)`と`read_acs_extract(path)`。D01→`source.dat`/`source.json`、州等の52行を正確に抽出し、読み取った範囲のハッシュ値を記録|P06 コマンド PASS。通信の応答を代替データに置き換えるのはテストだけとする。本番の比較実験ではD01から実資料を取得する|
|P08|集計・地域分割・評価データの混入の失敗を確認するテストを書く|`tests/test_population_prepare.py`。末端項目の対応表、6/4/41、行順不変、評価用の交差集計を変えても初期分布不変|同じテストのunittest コマンド FAIL|
|P09|集計と参照値分離を実装|`population/prepare.py`: `aggregate_b17001`, `marginalize`, `partition_tables`, `build_seed`。`config/population-v0.json`。入力はP07の行|P08 コマンド PASS。出力はseed/marginals/split/manifest/reference-all。対象の交差集計は再構築処理向けJSONに入れない|
|P10|基準手法と反復比例適合の失敗を確認するテストを書く|`tests/test_population_fit.py`。独立人数=(6,18,6,14,42,14)、初期分布の関連性の維持、周辺集計0、有限でない値、収束失敗|同じテスト コマンド FAIL|
|P11|独立基準手法を実装|`population/fit.py`: `independent_population(target:Marginals)->FitResult`。行の人数×列の人数÷総人数、対象資料のハッシュ値を保持|`test_independent_exact_product` PASS、IPF テストはまだFAIL|
|P12|公開ipfnへの接続処理を実装|同ファイル `fit_population(seed,target,tolerance=1e-10,max_iterations=1000)`。`from ipfn import ipfn`、NumPy float64の2×3、aggregates=[poverty,age]、軸指定=[[0],[1]]。人数が正の軸へ縮小。`ipfn.ipfn(matrix, aggregates, dimensions, convergence_rate=tolerance, max_iteration=max_iterations-1, verbose=2, rate_tolerance=0.0).iteration()`、独立残差判定と配列形状復元|P10全テスト PASS。ライブラリの状態値だけでは成功にしない。収束状態値が0でも最終残差と反復回数が受入条件を満たす場合のみ採用。互換性失敗は調査し版/修正を記録、勝手に自作計算処理へ置換しない|
|P13|独立評価の失敗を確認するテストを書く|`tests/test_population_score.py`。参照値=(15,10,5,5,50,15)、prediction=(6,18,6,14,42,14)でTVD=.18/max_cell_error_pp=9、異出典のハッシュ値拒否、zero-age=None|同じテスト コマンド FAIL|
|P14|評価と結果集計を実装|`benchmarks/population.py`: `score_population`と`summarize_population`。予測値と参照値は別々に入力、分割別集計、集団ごとの比率の誤差|P13 コマンド PASS。開発用の値をテストの平均へ混ぜない|
|P15|結果保存とコマンド操作の失敗を確認するテストを書く|`tests/test_population_cli.py`。再構築処理で参照値ファイルの読み込みを失敗させても実行可能、ハッシュ値の改ざん/上書き拒否、同入力の数値再現|同じテスト コマンド FAIL|
|P16|途中で失敗しても不完全な結果を残さない保存処理とコマンド操作を実装|`artifacts.py`の`write_artifact`、`cli.py`の`main`、`__main__.py`。fetch/prepare/reconstruct/scoreの4種類のコマンドは既存6作業 計画の引数通り|P15 コマンド PASS。不完全出力に成功確認記録を残さない|
|P17|通信を使わない全テスト一式を実行|P04/P06/P08/P10/P13/P15で作ったテスト一式|`PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -v` PASS。通信やモデルの呼び出しなし|
|P18|実資料を取得し2手法を比較|D01をfetch→prepare→independent/ipf→評価。絶対パスとコマンドは6作業 計画の作業6 記述部分通り|51対象、6/4/41、2手法。人口再構築精度を示す`population_fidelity`だけを測定済みとする、残り4評価項目は未実行の状態値`not_run`。IPFが負けても結果を保存|
|P19|実結果と限界を説明する|`apps/manager/README.md`, `apps/manager/docs/population-v0.md`。P18 報告書からのみ数値引用。公開データセットの推計と真の人口を区別|再実行で同じ数値。出典のハッシュ値、参照値の分離、集団ごとの誤差の説明。画像や文章だけをマネージャー完成と扱わない|
|P20|ブランチ全体を検証する|ソース管理範囲、差分、通信を使わないテスト一式、実装・仕様・報告書の一致、第三者著作権表示。状態をSSOTへ|コードレビュー後に通常の変更提案を作る。ブランチの送信と本番公開を区別|

依存が必要なP10以降は`/workspace/scratch/manager-population/.venv-population/bin/python`で同じコマンドを実行する。PYTHONPATHは同じ。venvはGit外。上表の`python3`はこの実行ファイルを意味する。

## 次の部品に利用する公開資料

この表は採用境界と次の具体的接続先。新サブシステムの実行は別の小さな計画で行う。全リポジトリを一つの仮想環境へ入れない。

|公開出典|固定点/確認したファイル|利用する部分とマネージャー側の接続先|現在の扱い|
|---|---|---|---|
|[GBIF API](https://api.gbif.org/v1/occurrence/search?country=JP&license=CC0_1_0&limit=0&facet=kingdomKey&facetLimit=10)|当日HTTP200、CC0フィルタ、KINGDOM_KEY facet。随時更新される資料には固定版がないため、取得時点と取得内容のハッシュ値を保存|`evidence/gbif.py`の観測接続処理へ。国・ライセンス・分類群ごとの観測記録数と観測範囲を取り込む。動物/植物/菌類等の観測を人間の集団人数とは異なる単位にする|取得経路を確認。記録数を個体数/苦痛/繁栄の指標へ置き換えない|
|[Socrates / SocSci210](https://huggingface.co/datasets/socratesft/SocSci210/tree/048481111a4425ed83dc0eacf15f8431f252b21a)|データセット revision048481...、`metadata/{participant,task,condition}_mapping.json`。リポジトリ `akaashkolluri/socrates@8c9aef227ab1a5b315e797c811a122a12d8bb88a`|`datasets/socsci210.py`と`benchmarks/behavior.py`候補。既存研究の集団反応を研究・実験条件ごとへ集計し、反応の実測資料による評価へ|元資料の利用条件が継承され、包括商用ライセンスは確認できず。元データの取得/学習/製品採用は未実施。出典別利用条件を確認するタスクを先に置く|
|[Concordia](https://github.com/google-deepmind/concordia/tree/b71d202750e23444ce1bf28d9f114bcd88aa41db)|Apache2、`concordia/agents/entity_agent.py`、`environment/engines/sequential.py`|`responses/concordia_adapter.py`候補。observe/context/actの境界を接続し、typed actionを数値Environmentへ渡す。GMの文章を資源台帳の正解にしない|固定出典読解済み。モデルの呼び出しと導入は次の計画|
|[AI Economist](https://github.com/salesforce/ai-economist/tree/a84d5f3fdcabb207d9fde7754d34906903b3e184)|BSD3、`foundation/components/redistribution.py`, `foundation/scenarios/utils/social_metrics.py`, `base/base_env.py`|環境モデルと方策における資源保存・配分・住民適応を参考。`benchmarks/allocation.py`で正規化したジニ係数等を使うなら個体配分と定義を固定し、集団人口の数へ誤適用しない|旧学習環境丸ごとの移植はしない。コピーする関数を確定した次計画でBSD 著作権表示と境界テストを保存|
|[RSI-Anything](https://github.com/Gen-Verse/RSI-Anything/tree/99dbf000a424b9033651b1096c5da2b6d5fa3865)|Apache2、`src/rsi_anything/workflow/runner.py`、`tasks/code_repair/src/evaluation.py`|`learning/retention.py`, `runs/manifest.py`の参考。候補と現状維持、方策とモデルの組の採用、出典と出力のハッシュ値、途中からの再開|静的読解済み。コード修正の学習結果をマネージャーの成果へ転用しない|
|[MASS](https://github.com/SakanaAI/mass/tree/fb403581bed2c974b3f99e7236224169da643079)|`mass/ranking.py`, `training/prepare_sft_data.py`, `docs/reproduction.md`, `NOTICE.md`|処理手順最適化→実行履歴→重みの更新の研究方法を学ぶ。`learning/workflow.py`の問いを設計|独自コードの公開コードの利用ライセンス未付与。製品コードへ無許諾コピーしない|
|[MiroFish](https://github.com/666ghj/MiroFish/tree/7657031ac01184afe2cb220f5ee3545573b5e843)|AGPL3、`simulation_manager.py`, `simulation_runner.py`, `report_agent.py`|prepare/run/report、SNS反応を必要とする場合の別接続処理。文書から生成した人物像を実人口の正解値へしない|初期人口へ導入しない。目的、依存、提供条件が合う段階で個別に採否|
|[DoWhy](https://github.com/py-why/dowhy/tree/cc23521127ba21ade40514539ae7b91db27ca54a)|MIT、`dowhy/causal_model.py`等|`evaluation/field.py`候補。実運営における介入・結果・交絡要因・比較条件が揃った時に識別・推定・反証を接続|運営者の記録と因果仮定が先。シミュレーションの差を通すだけで実地効果へ昇格させない|

## 実地で必要になるデータと権限

公開ACSは人口、SocSci210は既存研究の反応、GBIFは生物の観測記録。実地の変更権限、運営状態、実際の作用の確認記録、生活結果は公開リポジトリから得たことにしない。運営者の許諾データ/操作境界が必要。そこが未接続の間は現実の恩恵を実証済みとしない。宇宙・全生命のビジョンは、その実装境界とは別に保持する。
