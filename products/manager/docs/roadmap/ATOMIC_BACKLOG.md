# Manager — atomic learning & engineering backlog

Status: 2026-10-22 JST. Manager-only task registry in `tasks.json`; the Life Manager project SSOT is unchanged.

Total: 113 · Done: 69 · Todo: 41 · Blocked: 0 · Skipped: 3

✅ = original acceptance and dependencies verified; ⬜ = acceptance incomplete (preparation may exist); ⛔ = outside dependency; ⏭️ = scientific waiver (not success). A research task is not evidence of real-world impact.

Manager has a separate product identity, source scope and runtime, even when its source is in the same GitHub repository.

## 唯一の実装順（E01〜E16を先に、一件ずつ）

**ManagerのSSOT（状態・依存・現在位置）:** [tasks.json](tasks.json) の `F009.technical_execution_sequence` と `technical_execution_cursor`。Life Manager の別SSOTは変更しない。

**現在の次タスク:** `E16`

実装は **E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16** の順。各Eの合格条件は [Superpowers core plan](../plans/2026-10-22-manager-core-execution-plan.md)。先にF005等を実装する順序は廃止。

**実装後に検証する受け入れ条件:** **F005 → F006 → F008 → F009**。Fはタスク台帳上の製品受け入れゲートであって、Eより先に着手する工程ではない。実際のP1/P2証拠がある条件から判定し、架空試験やGitHub Actions成功だけでは完了にしない。

**対象外:** F004（第三者の資金管理者）とF007（施設所有者・屋内センサー）は `skipped`（未実施・未達成）で、実装の依存条件にしない。他者の設備・口座を操作する場合の権限は引き続き必要。

**並行する編集作業:** P01〜P07（日英記事、書籍、スライド、カルーセル、漫画、サイト）。E実装の現在位置は移動しない。

下のPhase 06表は受け入れ条件の一覧であり、時系列の作業順を示すものではない。

## Definitions of done

- Study: source-backed research note and stated verification succeeds.
- Implementation: tests and documented acceptance conditions pass.
- Real-world intervention: external proof plus harm/comparator accounting; simulation never proves beneficiary benefit.

## 00. 独立製品・再現環境

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `P001` | — | なぜLife Managerと同じDB/モジュールを使わないかを理解する | manager-independent/ を独立Gitリポジトリとして初期化する | git rev-parse --show-toplevel が /manager-independent で終わる |
| ✅ `P002` | P001 | 公開データと実行権限が別物であると説明する | README.md に目的、境界、禁止操作、Proof Levelsを書く | README.md に独立宣言・no live effectsが記載されている |
| ✅ `P003` | P001 | 依存ゼロの最小Pythonパッケージがなぜ堅牢か説明する | manager_core/, pyproject.toml, doctor CLIを作成 | python3 -m manager_core がoffline状態をJSON表示 |
| ✅ `P004` | P003 | テスト/CI/現地検証の違いを区別する | unittestとGitHub Actions定義を作り、秘密情報を.gitignore | python3 -m unittest discover -s tests; .github/workflows/ci.yml存在。GitHub CI未実行 |
| ✅ `P005` | P003 | リポジトリ境界を静的に検証する方法を理解する | scripts/check_boundaries.pyとデフォルト禁止設定を追加 | python3 scripts/check_boundaries.py、全外部書き込みが初期値false |
| ✅ `P006` | P001 | ローカルGitとGitHubリモートの違いを説明する | ユーザー許可によりDaisuke134/life-managerにManager専用ディレクトリproducts/manager/を研究ブランチで同期し、Life Manager実行環境と独立させた | GitHub研究ブランチ commit 68a2214d1edc9de4cfdd24ef75b84c8d59e5db6c からREADME/spec/tasks/R006 testを読み戻し、main SHA 060297d154d01dfa6f543b4b4c3c86de00067c60 のまま確認済み |

## 01. imozuruによる一次資料の掘り方

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `R001` | P001 | imozuruの問い→主張→探索→原典→抜き書き工程を説明する | MaryCache/imozuruのSKILL.md/README.mdとMITの版を確認 | 上流のSKILL.mdとreport.pyのSHAを記録 |
| ✅ `R002` | R001 | 探索バイアスを避けるため違う仮説で探索する | 実験の有効性ルートとLLM行動シミュレーションの反証ルートを別々に検索 | research/imozuru/manager-foundations/log.mdに両ルートとURLを記録 |
| ✅ `R003` | R002 | 一次資料/自社宣伝/要約の区別を説明する | 著者README/PMC/arXivの7抜き書きをsource locatorへ固定 | 上流公式report.py --checkが7件すべてPASS |
| ✅ `R004` | R003 | 抽象的な効果量が実際に何を測ったかを読む | HeartSteps論文のSample/Methods/Results/Limitationsを4ファイルの短いlocatorsに保存 | 4セクションに原著URL、対象人数、時間、統計方法、制約が埋まる |
| ✅ `R005` | R003 | よく見えるシミュレーションと因果忠実度の違いを説明する | Li & Ji(2026)の成功条件と失敗条件を一次資料で表にする | 条件×効果推定誤差×調査集団の根拠URLが埋まる |
| ✅ `R006` | R003 | 公開と自由な再配布は違うと理解する | 一次ライセンス原文と著者配布元を調べ、HeartSteps, SocSci210, Concordia, imozuruに加えモデル派生権も記録 | docs/research-rights.md と docs/research/source-rights.json の許可/保留・原出典URL・SHAを確認、tests/test_r006_rights.py合格 |
| ✅ `R007` | R004, R006 | Evidence IDと反証可能性を学ぶ | evidence/*.jsonに論文/実験/対象/効果量/限界/出典の型を作る | 少なくとも原論文5件がvalid schema; 出典なし数値はreject |
| ✅ `R008` | R007 | 研究結果の確実性を分類する | Evidence RegisterにRCT, survey, simulation, company-claimを別タグ付け | 公開企業の主張を独立RCTと表示するテストが失敗する |

## 02. 学習:確率・介入・反実仮想

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `L001` | P003 | 確率変数/分布/条件付き確率を説明する | examples/01_probability.pyで二値分布を比較 | P(Y\|X)を計算でき分布合計が1でない入力は拒否 |
| ✅ `L002` | L001 | TVDとBrier scoreの意味/限界を説明する | manager_core/evaluation.pyの関数で予測と実測を計算 | 既存test_evaluation.pyが通り、TVD=0/1を説明できる |
| ✅ `L003` | L002 | データ漏洩・過学習・校正を説明する | examples/02_calibration.pyにreliability binsとholdout検査 | 50%予測が実際50%と一致するテストを作る |
| ✅ `L004` | L001 | 状態/行動/報酬/履歴の違いを説明する | docs/learning/JITAI_GLOSSARY.mdにHeartStepsの観測変数を対応 | availability, decision_point, option, tailoring, proximalが実データに対応 |
| ✅ `L005` | L004 | 観測された行動と割付された介入の違いを説明する | docs/learning/CAUSAL_DAG.mdに交絡のDAGを作る | 観測的相関とRCTでの因果効果を別欄に記載 |
| ✅ `L006` | L005 | Y(1),Y(0),ATEと反実仮想欠損を説明する | examples/03_potential_outcomes.pyに架空の潜在結果を作る | 各対象の両方の反実仮想を現実に観測できない点を図解 |
| ✅ `L007` | L006 | 無作為化の強さと限界を説明する | examples/04_randomization.pyに固定seedで試験割付 | 繰り返しで無作為化効果平均が既知の真値へ近づくテスト |
| ✅ `L008` | L007 | MRTと通常の並行群RCTの違いを説明する | docs/learning/MRT.mdにHeartStepsの5時点/日を描く | availabilityに応じて無作為化される構造を説明 |
| ✅ `L009` | L008 | 近接効果と長期効果を区別する | 近接30分歩数vs6週間の長期評価を別列に記載 | 成果と測定窓を混同しない自動チェック |
| ✅ `L010` | L007 | 個人間干渉/スピルオーバーを説明する | docs/learning/INTERFERENCE.mdで寄付競合の例を記述 | ある寄付先の純増が他の減少だったケースを示す |
| ✅ `L011` | L008 | contextual bandit, MDP, off-policy条件の違いを説明する | docs/learning/DECISION_RULES.mdに3戦略を比較 | 過去の割付確率が不明ならoff-policy評価不能と明示 |
| ✅ `L012` | L006, L011 | 人間の苦痛へのproxyと直接測定の違いを説明する | docs/learning/OUTCOME_LADDER.mdに観測/受益/因果を分離 | クリックやTXだけでは苦しみの減少と判定しない |

## 03. HeartStepsの実測研究を再現

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `H001` | R006 | 元データの範囲と匿名性を理解する | HeartSteps公開CSVの取得条件と公開されたデータの列を確認 | ライセンス記録と必要最小列の一覧。生データは再配布しない |
| ✅ `H002` | H001 | スナップショット/再現性/ハッシュを理解する | 公開suggestions.csvをread-only取得、SHA256/コミットID保存 | data/rawはgitignore; manifestにrowcount 8,274とSHA256 **外部条件:** GitHubの公開ファイルを取得できる実行経路が必要 |
| ✅ `H003` | H002 | 実データ型・欠測を理解する | scripts/inspect_heartsteps.pyでヘッダ/行数のみ出力 | 個人データの行が表示されない; 8,274 rows照合 |
| ✅ `H004` | H003 | decision pointとavailabilityの意味を理解する | スキーマからdecision/time/availability/action列を同定 | 出典のcodebookと列名が完全一致; 不明列はunknown |
| ⏭️ `H005` | H004 | 分析単位/交絡/欠測の危険を説明する | 研究の除外規則で解析用decision pointsを抽出 | 元研究6,061件を再現できるまで「再現済み」としない **Waiver (not completed):** Founder-authorized 2026-10-21: public release cannot unambiguously reconstruct the original 2019 paper's analytic 7,540/6,061 decision population. Do not force-fit missing study-day data or treatment codes. |
| ✅ `H006` | H004, L007 | 個別データの記述統計と因果推定を分離する | 計測可能な公開CSVの6,330介入可能時点で記述統計と通知別件数を集計 | 8,274入力→6,330有効時点、平均220.42・SD436.78、欠測・割付頻度を再計算し、因果とは表示しない。 |
| ✅ `H007` | H006, L008 | 重複観測の相関と既知の割付確率を学ぶ | 公開CSVの探索的関連分析に参加者クラスタ頑健回帰と95%区間を適用 | 37人の反復測定にクラスタ頑健標準誤差を適用。単純な独立観測CIだけは使用しない。 |
| ✅ `H008` | H007 | weighted-centered least squares等の公開研究手法を理解する | 公開CSVの非同一サブセットで送信/非送信と歩行通知/非送信の調整関連比と95%区間を計算 | 送信関連比1.140 [1.001,1.297]、歩行関連比1.239 [1.056,1.454]。元2019年RCTの完全再現と表示しない。 |
| ✅ `H009` | H008 | 時間変化・減衰を評価する | 研究日ではなく公開済み決定順序インデックスの交互作用で時間的関連を評価 | 決定順序50単位の倍率0.858 [0.772,0.953]を記録。著者のstudy-day変化の再現ではない。 |
| ✅ `H010` | H009 | 外的妥当性と研究の限界を理解する | ソースの固定SHA/選別条件/統計/欠測/論文差/CIを原文リンクつきで公表可能な研究記録に保存 | CI実データ解析の再現手順があり、H005 skipped・元論文再現未達・Managerの実世界便益未測定を明記。 |

## 04. 人間行動予測とシミュレーション

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `S001` | R006 | 参加者分割と研究分割の違いを説明する | SocSci210のライセンスとmetadata/participant_mapping.jsonを取得 | 170 study train / 40 unseen study保持、splitハッシュを記録 |
| ✅ `S002` | S001, L002 | 予測ベースラインの重要性を理解する | SocSci210全17 Parquet・170学習研究から回答符号の頻度/多数派基準を求め、40未見研究の全482,642回答を実測集計 | 全210研究2,901,390件を監査、40未見研究の正答率・TVD・Brierと不確実性を実測；元研究の選択肢意味は一致しない旨明記 |
| ✅ `S003` | S001 | train/test leakageを理解する | 学習対象研究と評価対象研究のstudy_id重複を検査 | 漏洩0、偽装漏洩に対する失敗テストあり |
| ✅ `S004` | S003, L003 | 予測較正・不確実性を評価する | 同一40未見研究の実測回答でTVD/Brier・40-study bootstrap・20/20研究規模別誤差・訓練研究のみの閾値/abstentionを集計 | 40研究482,642分母と信頼区間、群別観測数、train-only TVD P90=0.60767102を保存；事後誤差をオンライン判定に使わずABSTAIN |
| ✅ `S005` | S004 | 評価へのモデル適合過ぎを説明する | 170学習/40未見研究で公開MiniLM凍結encoder＋学習側分類器を頻度/多数派と同一800個票で比較；公開SmolLM2-135Mも別の同一320個票で比較 | 実GitHub CIでMiniLM 800回答accuracy 24.5%対19.375%、TVD .3977対.4488、推論実時間とApache-2.0を記録；SmolLMは42.5%有効出力と失敗記録 |
| ✅ `S006` | R005, L005 | descriptive-vs-causalギャップを理解する | 独自の人工例で予測分布誤差と介入効果誤差を別ファイルで実証し、因果忠実度は実測していないと記録 | TVD=0でも人工の介入効果誤差0.4と別証拠。人間RCT因果精度は未測定 |
| ✅ `S007` | R006, S003 | 生成エージェントの記憶/内省/行動を学ぶ | 架空エージェントでConcordia実エンジンを独立sandbox実行し、生成と現実検証の別証拠を作成 | 実GitHub Actionsで2架空エージェント・4イベント生成、real_world_validation=0と別保存 |
| ✅ `S008` | S007 | 大規模化と一般化を区別する | 実測公開の自転車日次集計を2011年学習・2012年冬/夏の未知時間環境で評価（未知人口ではない） | UCI公式CSVバイト一致、2011年365日/2012年366日、冬91日/夏94日でTVD/Brier/MAEを記録し外挿の限界を明記 |

## 05. Manager汎用カーネル

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `K001` | R007, L004 | 観測と推論を分ける理由を学ぶ | manager_core/models/source.pyの公開URL/rights/hash型 | source不明/PII判定不明なら取り込み拒否 |
| ✅ `K002` | K001 | 測定値の時刻と単位と欠測を扱う | manager_core/models/observation.py | 同じvalueでもtimestamp/unitが違えば別状態 |
| ✅ `K003` | K002, L005 | 問題と原因仮説を区別する | manager_core/models/problem.pyにalternative_explanations | すべてのcausal_claimにevidence refsを要求 |
| ✅ `K004` | K003 | no_actionを常に含める理由を学ぶ | manager_core/models/intervention.pyにcost/risk/no_action | 根拠不明ならno_actionが残る |
| ✅ `K005` | K004, L009 | シミュレーション予測と介入効果を分離する | manager_core/forecast.pyにcalibrated distribution | 予測確信度とRCT効果推定のスコアを混在させない |
| ✅ `K006` | K004 | 形式的状態遷移を学ぶ | manager_core/state_machine.py | すべての違法な状態遷移を拒否、UNKNOWNを成功扱いしない |
| ✅ `K007` | K006 | 最小権限・予算・法的根拠を学ぶ | manager_core/authority.pyにscope/expiry/revocation | 署名/承認がないもの、期限切れ、budget超過はexecute不可 |
| ✅ `K008` | K007 | 冪等性を学ぶ | manager_core/outbox.pyにidempotency_key + durable record | 同じ効果を10回再試行しても外部実行は最大1回 |
| ✅ `K009` | K008 | 外部APIのtimeoutと二重送信の危険を学ぶ | manager_core/reconcile.pyにpresent/absent/unknown | unknownは再送せず状態確認を要求 |
| ✅ `K010` | K009 | 成功ログと独立観測の違いを説明する | manager_core/verifier.pyにsource-independent readback | executor自身のSUCCESSだけでverifiedにならない |
| ✅ `K011` | K010, L010 | 因果効果推定と介入スピルオーバーを学ぶ | manager_core/evaluator.pyの比較群/効果/CI/害 | 任意の成功数から因果効果を確定表示しない |
| ✅ `K012` | K011, S006 | Holdout評価と安全な自己改善を学ぶ | manager_core/learning.pyにversion, eval, rollback | 改善失敗時は前バージョンを自動復元 |
| ✅ `K013` | K010 | 機械可読な監査証跡を学ぶ | manager_core/audit.pyにsource/action/receipt/readback trace | 同一runの全段階を追跡可能; 証拠なし効果0扱い禁止 |
| ✅ `K014` | K011, K013 | 領域横断の再利用とは何かを定量化 | 同一kernelでfinanceとenvironmentのテストfixtureを走らせる | 新規領域追加で中核型/権限/証拠ロジック変更0 |

## 06. 現実の介入と独立した効果評価

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `F001` | K014 | 現実の行動には権限が必要と説明する | finance/environment各候補にoperator, rights, metric, feasibilityを記入 | 必須権限がなくてもpilot可能と主張しない |
| ✅ `F002` | F001, L010 | 一次アウトカムと副作用を事前固定する | pilot/PREREGISTRATION.mdにunit/comparator/n/duration/outcome | 「成功した後に指標を選ぶ」ことを禁止 |
| ✅ `F003` | F002 | 仮想テストと現実証明を分離する | finance read-only adapterと初期fixtureを実装 | 公開送金/公開台帳を第三者でreadbackできる |
| ⏭️ `F004` | F003, K007 | 資金管理者の許可待ちをManager開発の前提にしない | 旧・第三者の資金管理者承認と寄付予算取得の実地試験を必須ルートから廃止。所有サイトの情報環境改善へ移行 | 旧試験は未実施のまま履歴へ保存。実送金や外部資金確保を完了と主張せず、依存経路から除外 **Waiver (not completed):** 2026-10-22 founder-requested scope revision: external finance operators, transfers and allocated funds are not prerequisites for first-party digital Manager. Original finance field trial retired, NOT completed. |
| ⬜ `F005` | K009 | 所有する公開デジタル環境の実更新と外部readbackを区別する | Manager所有の公式情報案内ページを限定公開し、実際の提供者commitと配信中のSHA256を独立照合 | 提供者receipt P1＋公開ページ外部GET P2＋NO_ACTION replay-zeroと他のパス不変。人の便益はNOT_MEASURED |
| ⬜ `F006` | F005, K011 | 公開コンテンツの状態変化と人の苦しみの減少を混同しない | 公開ページ変化、初期状態、比較対象、欠測、費用、害を版付きで報告。人間アウトカムと因果効果の未測定を明示 | P1/P2出典・SHA・時刻を確認。利用者のP3/P4はNOT_MEASURED、標本がないのに信頼区間を捏造しない |
| ⏭️ `F007` | F001 | 屋内設備介入なしに情報アクセス環境を改善する | 旧・共有屋内施設やセンサーの取得・操作権限の確保を必須ルートから廃止。所有オンライン案内面の改善へ移行 | 旧屋内試験は未実施のまま履歴保存。屋内の曝露・疾患改善を主張せず、F008の依存を解除 **Waiver (not completed):** 2026-10-22 founder-requested scope revision: physical facilities and indoor sensors are unnecessary prerequisites to a first-party digital environmental intervention. Original indoor field trial retired, NOT completed. |
| ⬜ `F008` | F005, K010 | 対象の異なる所有オンライン環境の変化を別々に観測する | 金融案内とは別の公開情報アクセス面で改善を確認し、固有URL・SHA・独立GET・差分・復元可能性を記録 | 異なる2ページで外部読み戻しP2。室内センサーも施設許可も要求せず、人への因果効果は未測定 |
| ⬜ `F009` | F006, F008 | ひとつの共通カーネルで異なる情報アクセス面を監査する | 所有サイト上の対象2件のP2証拠、共通NO_ACTION・公開release・検証・限界を統合レポートにまとめる | 同一kernelと独立GETで対象2件を証明。人への便益はNOT_MEASURED、2ページを独立した人間試験と数えない |

## 07. 研究発表・説明責任

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `C001` | R008, H010 | 既存論文の効果とManager自身の成果を区別する | 内部英語発表資料のsource_claim_method_limitsを作る | 全数値に原著/再現結果/実世界実績のラベル |
| ⬜ `C002` | F006 | 公開可能な研究結果だけを倫理的に発信する | 英語記事/日本語要約/漫画/スライド候補を内部生成 | 投稿は別承認までdisabled。固有名/日時を創作しない |

## 08. 最初の受益者と製品市場適合の検証

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `U001` | P002 | 人の便益と操作結果を混同しない | docs/product/OPPORTUNITIES.mdに公開観測と実世界の結果を備える3候補の比較行列を作る | 候補ごとに受益者・苦しみの機構・公開データ・操作権限・比較方法を記載 |
| ⬜ `U002` | U001 | 顧客と最終受益者を分ける | 最初の領域の運営者・受益者・支援者それぞれの課題をインタビュー記録で整理 | 異なる立場の5件以上の同意ある面談と、実際に必要とする結果を記録 **外部条件:** 面談相手の承諾。回答は非公開の生データではなく必要最小限の匿名メモ |
| ⬜ `U003` | U002 | 証明可能な最小単位の選び方 | docs/product/FIRST_WEDGE.mdで、所有デジタル案内経路と運営者の保守課題を既存代替・費用・権限・結果観測と比較し、最初の利用場面を選定する | 実行主体・測定可能な結果・費用上限・代替案と断念理由を記載 **外部条件:** オペレーターの協力が得られない場合は候補変更 |
| ⬜ `U004` | U003, F002 | アウトカム事前定義と検出力 | pilot/FIRST_STUDY.mdで対象数・比較単位・期間・主要アウトカム・害・中止基準を固定 | 実行前に設定をハッシュ固定し、事後に成功定義を差し替えられない **外部条件:** 独立した実験実施協力・同意 |
| ⬜ `U005` | U003, K010 | 実行ログと成果を別表示する | 公開データだけの読み取り専用Proof Explorerを作る | 第三者が元URLから同じ観測事実を再確認し、P0/P1/P2を誤表示しない |
| ⬜ `U006` | U004, F005 | 独立読み戻しの達成を測る | 許可されたパイロットの外部receiptと観測をケースに保存 | 1件以上の実介入を第三者の公開データで確認し、未知状態を成功にしない **外部条件:** パイロット対象の明示的な権限と資源 |
| ⬜ `U007` | U006, F006 | 純便益と副作用を別集計する | 人の便益・費用・置換効果の事前登録済み比較レポートを作る | 一次指標の効果量と不確実性を示し、未測定は未測定と報告 |
| ⬜ `U008` | U007, U002 | 効果と継続需要を別に検証する | 協力者に成果レポートを提示し継続利用の意思と運用費を記録 | 実際の有料/支援コミットまたは継続利用意向の出典付き記録。収益未確認はUNKNOWN。対象期間・商品・口座の公式source coverageを照合してゼロ件と確定した場合だけ0を記録し、単発pilotをMRRにしない |

## 09. 領域横断の祝福・成果証拠

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ⬜ `D001` | F006 | 寄付者由来の純増と拠出原資を分ける | 金融介入評価に資金元・外部寄付・総費用の分類を実装 | 自分で出したマッチング予算を外部から生まれた利益として加算しない |
| ⬜ `D002` | D001, L010 | 寄付の横取り（クラウディングアウト）を理解する | 他プロジェクトへの寄付減少を検出可能な比較設計を追加 | 金融プロジェクト単体の売上増だけを社会全体の純便益としない |
| ⬜ `D003` | D002 | 家計・食料・負債の代理指標を理解する | 公表された支援先の受益報告と資金移動を別の証拠として接続 | 第三者報告がない経済的生活改善は未測定と明示する |
| ⬜ `D004` | D003, U007 | 金融における因果の再現性 | 別地域か別案件で限定的な支援効果を再確認する | 最初の成功を複数案件に外挿せず、比較可能な追試レポートを出す |
| ⬜ `D005` | F008 | センサーの誤差と時間交絡 | 屋内測定と外気・気温・湿度を時刻・単位付きで接続する | 無効・欠測・校正外の測定値を自動排除し、元データへ遡れる |
| ⬜ `D006` | D005 | 物理介入の対照条件 | 介入前後だけでなく同時期の比較領域を設計する | 時間変化と介入効果の識別条件を事前文書化 |
| ⬜ `D007` | D006 | 便益と副作用のトレードオフ | 改善量と電力・騒音・費用の独立計測を合わせる | 環境改善の純効果と副作用を別指標で開示する |
| ⬜ `D008` | D007 | 環境指標と健康改善の距離を理解する | PM2.5などの減少と直接的な健康効果を別の証拠ランクに格納 | 曝露データを病気が減ったという臨床成果と誤表示しない |
| ⬜ `D009` | D008, U007 | 領域をまたいだ効果の再現性 | 別施設で同一の環境介入証拠フローを再現する | 許可された複数施設で再現可能なP2以上の成果を報告 |
| ✅ `D010` | R008 | 有給仕事と機会改善の客観測定 | 公開OSS報奨・雇用支援の適法な公開情報アダプタを設計 | 募集・納品・承認・実入金の公開可否を別欄に保存する |
| ⬜ `D011` | D010 | 公開済み報奨と実際の受け取りの違い | 承認された成果物と独立して確認可能な受領証拠を照合 | 支払完了を証明できなければ収入増と主張しない |
| ⬜ `D012` | D011 | 生活安定への遠位アウトカム | 収入機会の純増と労働時間・費用・その他機会損失を評価 | 名目報奨額ではなく純額と分母を示す |
| ✅ `D013` | R008 | 精神的苦痛の代理尺度と倫理 | 孤立・支援アクセス等の公開集計指標と検証尺度の文献対応表を作る | 個人を特定・推定せず、対象単位と尺度妥当性を記録 |
| ⬜ `D014` | D013 | 苦痛を公共データだけで測る限界 | 支援団体/公的機関の公表集計との協働プロトコルを作る | 同意・倫理・匿名集計を守り、公開しない個票をManagerに取得しない **外部条件:** 適切な倫理審査・団体の協力・公開集計の可用性 |
| ⬜ `D015` | D014 | 精神面への介入の有害な副作用 | 当事者保護、過剰介入、誤評価、否定的影響の停止基準を定義 | 被害や不確実性がある場合はno_action・専門家による評価へ |
| ⬜ `D016` | D015, D012, D009 | 複数分野の便益を比較する限界 | 経済・身体・精神の各アウトカムを比較可能な証拠階層にまとめる | 各分野の指標を単純合算しない。合成スコアは根拠と重みを明示 |

## 10. ベンチマーク・一般化・自己改善

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ⬜ `V001` | K014, D016 | 構造上の一般性と性能上の一般性を分ける | 金融・環境・仕事/社会支援の3アダプタで同じカーネルの契約テスト | 分野固有の分岐をカーネルへ追加せず、共通の契約を満たす |
| ⬜ `V002` | V001 | 予測校正と因果推定の別評価 | OutcomeBenchでMAE/TVD・ATE error・実世界readback・harmsを独立採点 | 高い模倣精度だけで実世界P4認定しない回帰テスト |
| ⬜ `V003` | V002 | 外挿先のシフトと頑健性 | 国・所得層・領域・時間でholdoutと分布外検知を設計 | 未見集団の誤差と対象の公開範囲を明示、不確実なら実行停止 |
| ⬜ `V004` | V003 | 自己改善と人間の許可は両立する | 新しいポリシーを隔離環境→シャドー評価→限定実行へ段階昇格 | 停止/ロールバック可能。予算・権限を自己拡張できない |
| ⬜ `V005` | V004 | 第三者再現とプライバシーの両立 | 再現できるソース・評価コード・版・集計結果を権利を守って公開 | 第三者がP1-P4レベルの判定を同じ結果に再現できる **外部条件:** 公開の承認と外部資料の利用許諾 |
| ⬜ `V006` | V005 | 実装数ではなく人間への成果で学習 | 数十案件をまたぐ費用/純便益/害/失敗のポートフォリオを構築 | 正・負・不明の効果をすべて残し、虚偽の累計改善値を防ぐ |

## 11. YC・研究者ネットワーク・英語発信

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ✅ `Y001` | P002, R004 | 技術の壮大さより具体的な顧客便益を説明 | YC W27用の英語1文、誰の何を改善するか、証拠レベルを草案化 | 0件の実介入を実績として書かず、現状のプロトタイプを正確に示す |
| ✅ `Y002` | Y001 | 動く証明と構想を分ける | 公開情報→候補→根拠→無介入の安全判定を示す短いデモ動画を作る | 実在の成果を捏造せず、動いたコードと未実装部品を画面で区別 |
| ⬜ `Y003` | Y002 | YC応募の質問と時間制約を把握 | YC W27の申請文書・創業者動画・連絡先・リンクを確認して応募する | 公式サイトで申請完了を確認。採択は別の結果であり保証しない **外部条件:** 本人による応募と申請内容の承認、期限内の提出 |
| ✅ `Y004` | R002 | 研究者・創業者の知見を一次情報から学ぶ | 人物×研究×企業×公開コード×注目問題の公開ソースマップを作る | 10人以上の研究/公開活動を出典URLで確認し、私生活情報を収集しない |
| ⬜ `Y005` | Y004 | 相手の課題を聞く研究者・顧客発見 | 相手ごとに学びたい問いを作り、許可された連絡手段で面談を依頼する | 5件以上の適切な接点と送信/返信/未返信/拒否を正確に記録。公開業務窓口・公式応募経路を使い、本人が承認した対象と内容の範囲で実行し、拒否/停止要望後は追送しない。面談・研究参加の同意は初回業務連絡と別に確認 **外部条件:** 連絡先の適法な利用と送信承認 |
| ✅ `Y006` | R005 | 論文から再利用可能な価値を伝える | 英語研究解説記事の非公開草案に成功・失敗・元実験の差を記述 | 出典つき、事前査読なし/自社成果なしのラベル、著作権遵守 |
| ✅ `Y007` | Y006 | 視覚表現と因果の厳密さを両立 | 研究室・IACS・YCの聴衆別に英語スライドと日本語補助資料を作る | 数値と図の出典・観測/予測/効果区別、発表日時は未確認なら未記載 |
| ⬜ `Y008` | Y007, C002 | 発信前の校閲・個人情報・著作権 | 許可された記事/スライド/漫画をレビュー後に公開しフィードバック記録 | 公開承認、リンク先、公開日時、訂正履歴を残す。自動投稿しない **外部条件:** 公開の明示承認 |

## 12. 長期運用と統治

| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |
|---|---|---|---|---|
| ⬜ `G001` | K007, V001 | デジタル・ブッダという比喩と公的権限の違い | 公共利益憲章、権限・異議申し立て・停止条件を制定 | 管理者が監査・停止でき、AIが自分の権限を変更できない |
| ⬜ `G002` | G001 | 介入による害を監査する仕組み | 第三者監査と事故報告プロセスを設計する | 無効・悪化・未知のすべての介入の監査証拠が保全される |
| ⬜ `G003` | G002, V006 | 実績と普遍化の違い | 複数地域・人口構成の段階的検証を作る | 一つの地域の効果を無検証に世界へ外挿しない |
| ⬜ `G004` | G003 | 他組織との接続と合法性 | 監督主体・非営利・自治体・企業・研究者向け公開API契約を設計 | 接続先ごとに公開情報・許可・予算・責任を明記 |
| ⬜ `G005` | G004 | 収益と社会的便益のトレードオフ | 運営原価・資金調達・継続支援・測定コストの経済モデルを作る | 企業収益と人間への純便益を別指標で検証する |
| ⬜ `G006` | G005 | 世界規模の目的と有限の証明の違い | 人の苦しみの未測定領域・不公平・失敗・次の課題を継続棚卸し | 「世界の苦しみを終わらせた」と有限のデータから結論しない |

## Evidence and provenance

- R006 rights register: `docs/research-rights.md` and `docs/research/source-rights.json`. Unknown downstream permissions remain HOLD.
- imozuru research uses original links and local short excerpts; third-party original text is not automatically redistributable.
- No Manager field intervention or human suffering reduction has yet been proven.

- Phase06–12 implementation evidence and remaining original acceptances: `docs/verification/PHASE06_TO_12_ACCEPTANCE_20261022.md`.
