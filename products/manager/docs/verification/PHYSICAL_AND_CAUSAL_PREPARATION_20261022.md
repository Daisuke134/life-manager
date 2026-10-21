# 物理測定・既存因果分析ライブラリの実装準備

**2026-10-22 JST。対象は独立製品 Manager の研究用コード。** 原タスク D005–D007 と、既存54分解の F006.E06 / F008.E08 に対応するソフトウェアを追加した。実在する施設、介入、被験者、受給、健康改善は一件も追加観測していない。全出力は **P0**、人への効果は **NOT_MEASURED**、実行判断は **NO_ACTION** のままである。

原要求は [tasks.json](../roadmap/tasks.json) と [54分解](../roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md)。この文書は証拠記録であり、別のタスク台帳ではない。D005 の依存 F008、D006/D007 の実測、F006 の実際の比較研究を完了扱いにしない。

## 1. 物理測定の契約

[physical_outcomes.py](../../manager_core/physical_outcomes.py) は外部アクセスも機器操作も行わず、既に適法に得た公開・非個人データの宣言レコードを検査する。

| 入力・処理 | 実装した内容 | 証明しないこと |
|---|---|---|
| セッション | 対象・比較領域、アクチュエーター、実行者出典、前後の期間、同期許容秒数、事前プロトコル出典を固定 | 実際の所有者許諾、対照割当、事前登録の真正性 |
| 環境チャネル | 屋内・屋外 PM2.5 を `ug/m3`、屋内・屋外気温を `degC`、屋内・屋外相対湿度を `%` で保持 | 単位の推測変換、代理値からの健康改善 |
| 校正 | 機器・チャネル・単位、数値範囲、タイムゾーン付き有効期間、校正出典を照合 | 証明書発行者の真正性、現場でのセンサー設置・精度 |
| 品質検査 | 欠測、非有限値、bool、不正な物理範囲、単位不一致、校正不明・期限外・範囲外、別セッション、範囲外時刻を計算から除外 | 欠測をゼロで補うこと、除外後の標本が代表的だと仮定すること |
| 追跡 | 元の全レコード、除外理由、Source URL/hash、校正参照を結果に残す | URL やハッシュ一致による観測の真実性認定 |
| 同期結合 | 同じ領域・前後期間内の一意な相互時刻マッチのみ採用。共変量や対照の使い回し、曖昧な複数候補を採用しない | 同期精度、クロック誤差、自然変動を自動的に解消したという主張 |
| 比較 | 同時期の対象・NO_ACTION 対照ペアで前の差、後の差、その差の変化を計算 | 無作為化、並行トレンド、交絡除去、因果効果、信頼区間 |
| 副作用・費用 | 別計測器の電力 `W`、騒音 `dBA` を領域・期間別に記録。費用は通貨付き最小単位と出典を別保持 | 瞬時電力からの `kWh`、dBA の単純平均を LAeq とみなすこと、PM2.5 と金額の加算 |

実行機器自身の読み値、既知の実行者出典だけの読み値は独立計測の入力から外す。異なる機器名・出典名が付いていても、独立性を認証したことにはならない。完全な入力でも `measurement_authentication=NOT_VERIFIED`、`harm_measurement_status=DECLARED_MEASUREMENTS_ONLY` である。電力・騒音が欠ける領域／期間は `INCOMPLETE`、費用不明は `None`。

記述的な平均差には既存 [evaluation.py](../../manager_core/evaluation.py) の `exploratory_mean_difference` を再利用した。完全な架空例で前の対象対照差 8、後の差 2、その変化 −6 `ug/m3` が計算できても、それは**架空の入力の算術結果**である。`causal_effect`、`confidence_interval`、`energy_kwh`、`net_benefit` は `None`。実在の空気改善・臨床効果は推論できない。

## 2. 既存 DoWhy を使う分析アダプター

[causal_analysis.py](../../manager_core/causal_analysis.py) は金融・身体・精神の各指標に同じ型付き契約を使い、指標と単位を別保持する。独立した公開集計単位、二値割当、介入前の同単位ベースライン一つ、線形加法モデルという限定した入力形を対象にする。現場の反復測定やクラスター依存に、そのまま適用してよいという意味ではない。

推定を独自実装せず、[DoWhy 0.14 の公式手順](https://www.pywhy.org/dowhy/v0.14/user_guide/causal_tasks/estimating_causal_effects/effect_estimation_with_estimators.html) にある識別・推定・反証 API を呼ぶ。モデルは `backdoor.linear_regression`、区間はライブラリの信頼区間、placebo は処置の置換、未測定交絡の感度は [`linear-partial-R2`](https://www.pywhy.org/dowhy/v0.14/_modules/dowhy/causal_refuters/add_unobserved_common_cause.html) を使う。基準共変量に対する固定 0.1 倍のライブラリ参照ベンチマークと、robustness value の閾値を記録する。これらは仮定を診断する数値であり、未測定交絡が存在しない証明ではない。

| 検査 | 振る舞い |
|---|---|
| 計画と入力の結合 | study/domain/metric/unit の完全一致。計画パラメーターと全観測を canonical JSON bytes にし、それぞれの Source SHA-256 に照合。後から閾値や値だけを差し替えると拒否 |
| 由来・時刻 | 出典やプロトコル不明、事後プロトコル、追跡終了前の結果出典は `INCONCLUSIVE`。時刻も供給者の宣言であり、外部登録の認証ではない |
| 標本・欠測 | 群別の事前最小数未達、一群のみ、欠測アウトカム／ベースラインは推定しない。欠測行の削除やゼロ補完をしない。最小数の充足を検出力充足と同一視しない |
| overlap | 割当確率不明・閾値外、ベースライン範囲が群間で完全に分離していれば停止。通過も `DECLARED_SUPPORT_ONLY` で、真の割当確率・多変量 positivity の証明ではない |
| 区間・反証 | 区間にゼロを含む、placebo が事前許容幅を超える、robustness が事前閾値を下回る場合は `INCONCLUSIVE` |
| 数値異常 | ライブラリ例外・不正な数値は停止。RuntimeWarning の内容も保存し `NUMERICAL_DIAGNOSTIC_WARNING` として `INCONCLUSIVE`。数値警告を隠して成功としない |
| 費用・害 | 量・単位・出典を別保持。未知は `UNKNOWN_COSTS` / `UNKNOWN_HARMS`。出典付き宣言も `DECLARED_ONLY` である |
| 入力の証拠レベル | 架空データは `SYNTHETIC_DIAGNOSTICS_ONLY` または `INCONCLUSIVE`。自己供給の公開集計は数値計算できても `UNAUTHENTICATED_INPUTS` / `INCONCLUSIVE`。`verified_causal_effect=None`、人への便益は `NOT_MEASURED` |
| 依存ライブラリ不在 | `DEPENDENCY_UNAVAILABLE`。代わりの自作推定器に切り替えない |

この契約は、独立した測定主体が保持する個票を取得する口実ではない。現行 FIRST_STUDY の世帯単位の研究計画と、この公開集計の限定的な分析アダプターは、そのまま同一の分析ではない。実研究では承認された分析単位、割当、欠測、干渉、クラスター構造に適合する既存手法を選び、独立側で必要な分析を行い、公開可能な集計を連結する。

## 3. 依存関係と実行記録

[requirements-causal-eval.txt](../../requirements-causal-eval.txt) は研究用の任意依存であり、通常の Manager runtime へ追加していない。DoWhy 0.14 の公式 wheel を取得し、MIT 表記と要求メタデータを確認した。wheel SHA-256 は `9c5855d80601e0feb2d0d232c19e7b660db4cd0ea04ace2ebaefcdb3599ab9db`。[公式配布ページ](https://pypi.org/project/dowhy/0.14/) に対応する。

実検証環境は Python 3.12.14、DoWhy 0.14、NumPy 2.2.6、SciPy 1.15.3、pandas 2.2.3、statsmodels 0.14.4、scikit-learn 1.6.1。`/tmp/manager-causal-deps` に隔離して実行した。これは Python 3.11 を実行済みとする記録ではない。

`products/manager` を cwd とした実行結果:

| 実行 | 結果 |
|---|---|
| `python -m unittest discover -s tests -p test_physical_outcomes.py`、モジュール作成前 | **11 tests / 11 failures**。意図した未実装アサーション |
| 同コマンド、実装後 | **11 tests / 0 failures / 0 errors** |
| `PYTHONPATH=/tmp/manager-causal-deps:. MPLCONFIGDIR=/tmp/manager-matplotlib python -m unittest discover -s tests -p test_causal_analysis.py`、モジュール作成前 | **15 tests / 15 failures**。実 DoWhy が見える環境で未実装アサーション |
| 同コマンド、初回実装検証 | 契約11件は通過、実ライブラリ4件で3 failures / 1 error。上流感度 API が列形式を要求する部分をラッパーで修正し **15件通過** |
| 数値感度警告を隠していたケースの追加回帰 | **1 test / 1 failure → 1 pass**。警告保存と `INCONCLUSIVE` を実装 |
| 上記 optional コマンドの最終実行 | **16 tests / 0 failures / 0 errors / 0 skips**。金融と身体の両単位で実 DoWhy の推定・区間・placebo・感度を実行 |

物理実装の最初の検証では2件の架空テスト出典が観測より前の日付だったため、新しい時刻検査が正しく除外した。テスト出典の取得時刻を対象観測の後へ修正し、非同時期対照の検査も「出典時刻不正」ではなく実際の同期不成立を検査するようにした。

通常テストは optional パッケージがなければ実 DoWhy の5件だけを skip する。依存欠如を隠す意図ではなく、上表の実パッケージ実行が別証拠になる。通常テスト総数は他レーンと統合時に変動するため、最終全体結果は [実行報告](COMPLETION_EXECUTION_20261022.md) を参照する。

## 4. 残る境界

機器・校正・時刻の真正性、設備権限、実際の同時期対照、公開可能な独立測定、妥当な標本と倫理・同意、登録済み主要アウトカム、適合する推定法、費用・害・脱落の把握、別施設／別人口での追試は未達である。現場の電力積算値や騒音時間積分を計測していない。効果が好ましい方向に見える架空データや、供給者が「独立」「校正済み」と述べる入力だけから、因果的または身体的改善を推論しない。

当レーンは live adapter、kernel、authority、outbox、設定、ワークフロー、タスク状態、Life Manager の実行経路を変更していない。
