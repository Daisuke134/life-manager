# Manager Masterclass｜P00〜P12の全講義と製品実装（唯一のロードマップへ）

**2026-11-07 Phase11：P11-1〜5 講義・合成演習・研究公開準備。** [P11-1 OPE](P11-1_JA.md)、[P11-2社会](P11-2_JA.md)、[P11-3分散認知](P11-3_JA.md)、[P11-4行動FM](P11-4_JA.md)、[P11-5領域移植](P11-5_JA.md)、[38件の合成テスト](experiments/test_p11_1_5_research_labs.py)、[再現結果](evidence/P11-1_TO_P11-5_SYNTHETIC_RUN_20261107.json)、研究用33枚PPTX/PDFと日本語ノートを追加。公式メディア用日英10記事と図5点は正本パッケージへ登録。公開後のreadbackが済むまで未公開とみなす。次の講義はP12-1。**研究/製品/人間便益の本番実証は別Gate**。唯一の進捗正本は[ROADMAP_STATUS_JA.md](ROADMAP_STATUS_JA.md)。


**最新版：2026-11-05 America/Los_Angeles。** 先頭から読める唯一のカリキュラム・製品開発順は **[ROADMAP_STATUS_JA.md](ROADMAP_STATUS_JA.md)**。元のP07-3／P07-4／P07-5とP08〜P12は消えていない。以前の「P04〜P07-2」「次はP05-2」などは過去の作業時点に書かれた履歴で、現在の指示ではない。

**Phase 7（P07-1〜P07-6）の講義・観察専用／安全ソフトウェア実装は完了。** [P07-3 COM-B](P07-3_JA.md)、[P07-4 CBT・ACT](P07-4_JA.md)、[P07-5 ヴィパッサナー・無常・苦・無我](P07-5_JA.md)、[P07-6 生活の質・自律性・瞑想有害事象](P07-6_JA.md)の資料・FAQを保存。P07-4の15ソフトテスト、P07-5/6の25ソフトテスト、統合の10ソフトテストを実行。詳細研究用118枚の編集可能な英語スライド、118ページPDF、日本語スピーカーノートをクラウドで検証。**人間への治療・苦痛軽減の実際の効果は未実証**。P08〜P12の全講義番号も廃止せず、唯一の[ROADMAP_STATUS_JA.md](ROADMAP_STATUS_JA.md)に保持する。**『モデル開発の次』と『学習の次』を別々に置かず、唯一の現在TODOはBFM-01。**

**唯一の現在TODO BFM-01:** Qwen3-4Bの無料CPU実推論、実際のHBCP研究データのQwen vs 統計ベースライン比較、ライセンスが明確なHBCPの小型数値予測モデルの学習と読み取り専用接続は実行済み。Be.FMのLoRAはHF gatedで未実行。**さらに公式Be.FM Terms of Useに『非商用・再配布禁止・派生物の配布禁止』があり、モデルカードのApache-2.0表示と整合性を確認できていないため、書面での権利確認なく商用搭載・open-weight再配布は行わない。** 同じ一つの仕事の中で、権利が明確な既存モデルによる実測→Manager統合→公開を継続。Xへの投稿も行わない。


---

## アーカイブ：従来のREADME本文（各作成時点の進捗。現行指示は上と唯一のロードマップ）

# Manager Masterclass｜P04-1〜P07-2 因果推論・Ontology・行動と実行の接続

**更新：2026-11-05（Asia/Tokyo）。** このディレクトリは教育講義と架空実験の再現資料。**実人間への介入、実公開RCTの前向き効果予測、Manager Behavior Foundation Modelの科学的な優位性の実証ではない。**

**唯一の全ロードマップ・進捗正本：`ROADMAP_STATUS_JA.md`。** 本READMEやMANIFESTを講義の別SSOTとみなさない。P04-1〜6とP05-1〜5は講義・人工実験まで完了。P06-1〜5の教育・人工実験・実サイトのread-only成果カードまで終了、学習の次はP07-4。実会社の増分価値とP05-5のS1/S2は未完了。P05-5の実務Shadowと限定本番実行は未達。P05-2ではListen Labs Study APIの実認証GETも確認（実介入なし）。P04-5の実在公開RCTに対する未見研究効果予測、P00-3の権限・同意、実世界での方策検証は未完了。


## Managerの中核仮説と実証すべき価値

[What-if Machine × Executor：中核仮説と科学的証拠の階段](MANAGER_WHAT_IF_EXECUTOR_THESIS_JA.md) に、製品・流通・本人の便益を**結果から独立検証する**研究方針を整理した。Managerそのものを企業へ売ることを先に必須にせず、Managerが作る製品やサービスの実際の成果で価値を示す。外向きの名称は「Manager」とするが、既存リポジトリ・APIの破壊的リネームは行わない。オープンソースと将来のオープンウェイトを目指し、第三者データの権利・個人の健康情報・同意・安全性は優先して保護する。

**60分発表の最後の4枚（31〜34）** と、詳細版の対応する3枚（46〜48）をこの構想に合わせて更新した。世界最大の利益、完全自動バズ、精神疾患の治療などは実証済みの成果として扱わない。発表では反証可能な研究仮説として紹介する。

## 2026年11月5日 13:00–14:00｜神経科学ジャーナルクラブ

**本番ではこちらの厳選34枚版を使う。** 来場者は学術/業界/専門知識に関係なく理解できるように、初学者・研究者・起業家・投資家を想定する。人間行動シミュレーションの専門知識を前提とせず、歴史、モデルの種類、代表的な研究・企業、ベンチマーク、因果と限界を基礎から説明し、Managerは最後の4枚・約6.3分に留める。

| ファイル | 内容 |
| --- | --- |
| [60分発表 PowerPoint](journal_club/AI_BEHAVIOR_JOURNAL_CLUB_60MIN_JA.pptx) | **34枚**、編集可能・全ページに日本語発表者ノート |
| [60分発表 PDF](journal_club/AI_BEHAVIOR_JOURNAL_CLUB_60MIN_JA.pdf) | **34ページ**、発表画面用 |
| [全34枚日本語読み上げ原稿](journal_club/SPEAKER_SCRIPT_60MIN_JA.md) | 1ページごとの自然な読み上げ文と元スライド・時間 |
| [60分の進行表](journal_club/RUN_OF_SHOW_60MIN_JA.md) | **43.0分講演＋15分質疑＋約2分の余裕**、章別時間・重要スライド・短縮ルート |
| [発表版を再生成](journal_club/build_60min_journal_club.py) | 過去の33枚を構築した歴史的script。現在の34枚は`build_p05_phase5_decks.py`の改訂が正本。別々に管理し、元ファイルを破壊しない |

**優先順位：** ①基礎と研究史 ②どの対象にどの模型を使うか ③既存研究・企業は何を主張しているか ④何を検証して何をまだ検証していないか ⑤最後にManagerが目指すこと。数式の厳密な導出・企業の細かい数字・P04-6の全シミュレーションは本番で列挙しない。質疑用の長い資料に残す。

## 全100枚の詳細保存版（本番で一挙上映しない）

| ファイル | 内容 |
| --- | --- |
| [詳細100枚PowerPoint](journal_club/AI_BEHAVIOR_JOURNAL_CLUB_JA.pptx) | 元82枚のManager対応46〜48を研究仮説に更新し、P04-6付録3＋P05-1付録2＋P05-2付録2＋P05-3〜5/展開付録4＋P06-3〜5研究付録3＋P07-1研究付録2＝98枚。既存本文は維持 |
| [詳細100ページPDF](journal_club/AI_BEHAVIOR_JOURNAL_CLUB_JA.pdf) | 100ページ（元82＋P04-6研究3＋P05-1研究2＋P05-2研究2＋P05-3〜5/展開研究4＋P06-3〜5研究3＋P07-1研究2＋P07-2研究2）。新しい付録は画像レンダリングで統合し、元のページを維持 |
| [全100枚の日本語発表ノート](journal_club/SPEAKER_NOTES_JA.md) | 1〜96の全ページ分。PowerPoint内部にも全100枚のノートを保存 |
| `journal_club/build_p06_phase6_appendix.py` | **詳細93→96枚・研究付録94〜96**。本番34枚は不変 |
| `journal_club/build_p05_phase5_decks.py` | **研究89→93枚、本番33→34枚、一般向け用語とManager段階ロードマップ**。再実行は入力版の確認後 |
| `journal_club/build_p05_2_appendix.py` | **87枚→89枚のP05-2研究付録追加**。旧本番33枚は本アップデートで34枚に改訂 |
| `journal_club/build_p05_1_appendix.py` | **85枚→87枚の研究付録追加**。本番用33枚は不変 |
| `journal_club/build_p04_6_appendix.py` | 82枚版→85枚版への追加作成に使用。すでに85枚なら二重追加しない |
| `journal_club/build_p04_45_appendix.py` | **歴史的な74枚→82枚作成スクリプト**。現在100枚版への再実行はしない |
| `journal_club/export_p04_45_pdf.py` | **歴史的な74ページ→82ページPDF結合スクリプト** |
| `journal_club/RUN_OF_SHOW_JA.md` | 元のフル講義の履歴上の進行表。**2026-11-05本番は60MIN版の進行表を優先** |

## 講義の本文

| 資料 | 内容 | 学習の検証 |
| --- | --- | --- |
| `P04-1_JA.md` | 観察vs介入・DAG・潜在的結果 | 完全架空データ、14テスト |
| `P04-2_JA.md` | RCT・ATE・ITT・信頼区間 | 架空RCT、17テスト |
| `P04-3_JA.md` | 交絡・g-formula・IPW・AIPW・DiD | 架空30,000人、26テスト |
| `P04-4_JA.md` | CATE・効果異質性・方策選択・媒介 | 架空24,000人＋媒介20,000人、12テスト |
| `P04-5_JA.md` | study holdout・予測凍結・介入効果予測 | 架空180研究、11テスト。**実公開RCTの未見予測は未実施** |
| `P04-6_JA.md` | 事前登録・方策対方策RCT・意思決定価値・無計画な途中解析 | 架空40,000人＋A/A 750試行、16テスト。**実研究の事前登録・実介入は未実施** |
| `P05-1_JA.md` | Ontology・状態・時点・知識グラフ・Digital Twin・既存技術の徹底調査 | 既存Manager Coreを再利用し人工5イベントのread-only投影、26テスト成功。実行権限・実人間は未接続 |
| `P05-2_JA.md` | 既存Job/Effect/Receipt/RuntimeEventのID・証拠Trace、Listen Labs実API | 人工時点別Trace・39テスト／API安全性8テスト。TinyFish公式画面＋認証GET 2件HTTP 200。予測ID/判断ID未接続、実サービス改変なし |
| `P05-3_JA.md` | 複数エージェントの役割、権限・期限・撤回 | 既存Manager Coreで人工Grantによる6拒否条件の確認、本番は未受入 |
| `P05-4_JA.md` | 不明状態・二重実行防止・独立確認・復旧 | DurableOutboxの人工送信とUNKNOWN→PRESENT、P0のみ |
| `P05-5_JA.md` | Shadow・限定1回実行の条件と学習 | 既存Shadow41テスト成功、実務Shadow/本番S2未実施 |
| `MANAGER_MODEL_COMPANY_IMPACT_MILESTONES_JA.md` | モデル訓練・公開・会社への導入・人の便益の3本線 | **日付は条件付き仮目標であり実績・保証ではない** |
| `P06-3_JA.md` | statsmodelsでの必要標本数・SRM・逐次解析の偽陽性 | 人工A/A2,400反復・新規21テスト成功。実登録RCTなし |
| `P06-4_JA.md` | 返金・売上・費用・苦情をすべて含む増分価値 | 人工3万割当で利益が正でも苦情悪化のためDO_NOT_SHIP。新規28テスト |
| `P06-5_JA.md` | 研究凍結と独立した実公開の証拠、正直な実績カード | SHA9件・Manifest+6公開HTML確認。実利益・実人間効果はNOT_MEASURED。新規22テスト |
| `PHASE6_COMPLETION_AND_FIELD_GATES_JA.md` | Phase6の成果と未完本番ゲートの詳細 | 328レビュー済みテスト・本番のS1/S2/実効果は未完 |

基礎単体テストは **122/122件成功**（P04-1〜6：96件／P05-1：26件）。さらに比較ベンチマークの23件が成功し、**P05-1時点の合計は145/145件成功**。基礎のログは`evidence/TEST_RESULTS_P04_1_TO_P05_1.txt`、旧P04-1〜6ログも保存。教材のテスト合格を実世界への有効性の証明と混同しない。

## P05-1の調査と実装結果

**結論：巨大なOntologyを一から作らず、既存のBCIO・PROV-O・JSON-LD・JITAI・既存Manager Coreを再利用する。** [日本語講義全文](P05-1_JA.md) には一次資料、先行研究の限界、プロトコル、既存コードのマッピング、将来の評価基準を整理。

- [既存のGraph Skill](https://github.com/Daisuke134/life-manager/blob/main/skills/graph-engineering/SKILL.md) はGraphを証拠のread-only projectionと位置付けているので、その方針を守った。
- `experiments/p05_1_ontology_readonly.py`は既存Manager Coreの`StateMachine`と`InterventionPlan`を再利用し、人工5イベントの知識グラフを構築する。実行・事業・個人情報とは接続しない。
- 26件の単体テスト、出典SHA、時系列、知らないことを知らないまま扱う制約、実行権限をGraphから生成しない制約を検証した。
- [実行結果](evidence/P05-1_READONLY_SYNTHETIC_PROJECTION.json)、[全122件のテストログ](evidence/TEST_RESULTS_P04_1_TO_P05_1.txt)。
- 実行・モデルの実世界の改善は未検証。**次の講義：P05-2「実験ID・行動ID・証拠の共通形式」。**

## P04-6の新規実行結果（完全架空）

- 対象40,000人。政策群への無作為割当：Manager型約19,835人／比較型約20,165人。
- 同じ事前特徴、同じ候補行動、同じ観測期間を設定。比較方策は有用な固定ヒューリスティックであり「世界最強のbaseline」とは認定しない。
- 主成果（完了マイナス通知人工費用0.02/回）は、Manager型平均0.33616／比較方策0.32003、差 **+1.613pt**（95%近似CI **+0.688〜+2.539pt**、p≈0.000635）。
- 人工の期待効果真値は**+2.00pt**。設定した世界での証拠に過ぎない。
- 効果ゼロの架空A/Aを750回反復し、最終1回の未補正検定による偽陽性**4.27%**、途中6回のいずれかで有意なら成功とした偽陽性**15.20%**。
- 結果生成前に`P04-6_PREANALYSIS_PLAN_SYNTHETIC.json`を保存し`P04-6_PLAN_FREEZE_RECEIPT.json`でSHA256を固定。**外部公開研究登録はしていない**。
- 全人工40,000人のCSVは`evidence/P04-6_POLICY_RCT_SYNTHETIC.csv`。結果は`evidence/P04-6_POLICY_RCT_SYNTHETIC_RESULTS.json`。

## ローカル再現

Python 3.11+とNumPy、PowerPoint編集はpython-pptx、PDF/追加スライド生成にはpypdf・Pillowが必要。

```bash
cd docs/research/manager/masterclass/2026-11-04-p04-causal/experiments
python3 -m unittest discover -p 'test_p0*.py' -v
python3 p04_6_preregistered_policy_value.py
python3 p05_1_ontology_readonly.py
```

本番発表版は`journal_club/build_60min_journal_club.py`で再生成。**詳細マスターを消す／発表で全100枚を使う運用はしない**。厳選34枚／詳細100枚を保持する。歴史的なManagerの対応する3枚は update_manager_thesis_slides.py で仮説に沿う内容へ同期する。

## 監査

`evidence/P04-6_JOURNAL_CLUB_QA.json` に、33枚・33ページ、85枚・85ページ、発表版33枚の全ノート、詳細版85枚の全ノート、Manager対応46〜48を除く元79枚の本文保持、凍結予測ハッシュ、人工RCT計画ハッシュ、96テストの照合を記録。ファイルのSHA256とサイズは`MANIFEST.json`に保存する。**外部の研究ベンチマーク検証や実施権限の承認を行ったとは主張しない。**


## 2026-11-04追加｜既存コードと外部OSSの実行監査・4方式比較

- [P05-1実コード徹底読取・OSSエコシステム調査](P05-1_CODE_REVIEW_ECOSYSTEM_JA.md)：BCIO・EDSL・Graphiti・MiroFish/OASIS・Palantir SDK・Listen Labs公式APIのコード/ライセンスと実行範囲。各リポジトリのソースはvendorしない。
- [Manager Ontology/Query/evidenceの統合実装仕様](https://github.com/Daisuke134/life-manager/blob/main/products/manager/docs/specs/2026-11-04-manager-ontology-query-evidence-reuse.md)：実行境界、4方式比較、採用判断、P05-2受入。会社の大きな統合SSOTは別。
- **4方式のsynthetic同条件比較**：[元データと全測定値](evidence/P05-1_QUERY_BENCHMARK_SYNTHETIC.json)、[Pythonコード](experiments/p05_1_four_way_benchmark.py)。12,252イベント・800質問でFlat scan=6,322µs／Python Dict=0.50µs／SQLite=3.29µs／Graph Projection=0.50µs（検索中央値）。すべて正解一致、索引生成コストは別計測。Graphiti本体はこの性能比較に含まれない。
- **実際の隔離実行**：EDSL 1.0.9は3架空Agent＋test modelを通信禁止で成功、Graphiti-core 0.31.2は型のオフライン生成成功、BCIO OWLに2,634クラス宣言を確認。Listen Labsの無認証GETは401で、Twinsの公開APIは未確認。MiroFish/OASIS/Palantirの本番実行は未実施。
- [完全人工のEDSL→Manager Core→Graph/Dict/SQLite/Flat E2E](evidence/P05-1_OFFLINE_END_TO_END_SYNTHETIC.json)：5人工イベントと6問で4方式一致、権限不足のため既存Manager Coreが`NO_ACTION`。ネット接続・個人情報・実通知なし。
- [外部OSSピン留め・ライセンス・正本監査](evidence/UPSTREAM_CODE_AND_LICENSE_AUDIT.json)／[BCIO検査](evidence/BCIO_REAL_OWL_SNAPSHOT_AUDIT.json)。
- **Python3.14テスト互換修正**：`products/manager/tests/test_collaboration_authority.py`の`dataclasses.replace(init=False)`例外型がPython3.12でValueError・3.14でTypeErrorとなる差を許容。許可/実行の実装そのものは未変更。両版で44 tests＋15 subtests成功。
- **採用判断**：単純なqueryはまず既存のSQLiteとPython辞書を使う。Graphitiや新Graph DBを強制導入しない。時間付き知識抽出や意味検索が必要と分かった段階で、精度と費用込みで独立比較。P05-2の実装課題と実世界検証は残る。


## P05-2実験結果（2026-11-04）

[講義全文](P05-2_JA.md)、[共通スキーマを再利用する読み取り専用Trace](experiments/p05_2_evidence_trace.py)、[人工Traceの全結果](evidence/P05-2_SYNTHETIC_TRACE_RESULTS.json)、[安全なListen Labs API GETプローブ](experiments/p05_2_listenlabs_readonly_probe.py)、[API実認証GETの匿名結果](evidence/P05-2_LISTENLABS_AUTH_READONLY_SUMMARY.json)、[193件の全テストログ](evidence/TEST_RESULTS_P04_TO_P05_2.txt)。

**P05-2新規48件、旧P04〜P05-1の145件を含む193/193件成功。** APIキー・ウォレットID/残高・調査名/ID・参加者回答はGitHub・ログに保存しない。外部へのPOST/公開/料金・実参加者への介入はゼロ。**研究保存版89枚・89ページ**、本番発表版33枚は変更なし。次はP05-3。


## 2026-11-04 Phase 5最後のP05-3〜P05-5

[役割・権限](P05-3_JA.md)、[復旧・独立証拠](P05-4_JA.md)、[Shadowと実務導入](P05-5_JA.md)を既存Manager Coreの実コードで検証した。サンドボックスで6種類の権限外操作拒否、Outboxの二重実行0、処理後TimeoutのUNKNOWN→PRESENT照合、1回の人工provider送信と独立した人工sensor確認を再現。Liveの外部操作・有料呼出・本人への介入は0。Shadow無効はモデル呼出0、既存Shadow本体のユニットテスト41件成功。

[実行コード](experiments/p05_3_5_end_to_end.py)、[テストコード](experiments/test_p05_3_5_end_to_end.py)、[結果JSON](evidence/P05-3_5_EXISTING_CORE_OFFLINE_RESULTS.json)、[テスト229件](evidence/TEST_RESULTS_P04_TO_P05_PHASE5.txt)、[既存Shadow41件](evidence/P05_3_5_EXISTING_SHADOW_TESTS.txt)。

[独自モデルの訓練・Open-weight公開・会社運営・人間の行動変容の条件付き高速ロードマップ](MANAGER_MODEL_COMPANY_IMPACT_MILESTONES_JA.md)。**P05の講義は完了。P05-5の実会社S1/S2は未達**。学習はP06-1へ進み、別の根拠/許可Gateが整うまで会社の実権限を増やさない。

**34枚の本番プレゼン**：第6枚の一般向け概念解説と第33枚の3本並行ロードマップを加え、旧33枚目の締めは第34枚へ。43分＋15分質疑＋2分余裕。**93枚の詳細保存版**：P05-3/4/5とマイルストーンの4枚（90〜93）を追加し、全93枚の日本語原稿を維持。


## 2026-11-04 P06-2とBehavior AI再利用・11/05発表更新

- [P06-2 What-ifあり/なしの人工RCT全文](P06-2_JA.md)、[実コード](experiments/p06_2_whatif_ablation.py)、[28テスト](experiments/test_p06_2_whatif_ablation.py)、[凍結方策](evidence/P06-2_POLICY_FREEZE_SYNTHETIC.json)、[結果](evidence/P06-2_SYNTHETIC_ABLATION_RESULTS.json)。学習24,000/独立検証16,000/別の方策RCT40,000でWhat-if平均効用+1.422pt（95%CI+0.492〜+2.353pt）。**完全人工世界の結果**であり、実会社や本物の人間の効果ではない。
- [最新の既存研究・企業/OSS比較メモ](BEHAVIOR_AI_REUSE_ECOSYSTEM_20261104_JA.md)：SOCRATES、SimBench、BehaviorBench/Be.FM 1.5、HumanStudy-Bench、Aaru、Listen Twins、Rehearsals等の公式資料とライセンス/比較の限界。
- [BehaviorBench公式MIT evaluatorの実動テスト記録](evidence/BEHAVIORBENCH_EVALUATOR_SOURCE_SMOKE_20261104.json)：Mac miniで41 PASS/3 SKIP、モデルの重みや実データベンチマークは動かしていない。BehaviorBenchデータのCC BY-NC-NDと評価器のMITは区別。
- [Listen Twinsの公開画面をTinyFishで試した結果](evidence/LISTEN_TWINS_PUBLIC_BROWSER_ACCESS_CHECK_20261104.json)：公開『Run a Simulation』は予約フォームに遷移。**Twinの実推論は未実行**。旧Listen Study APIのGET2件HTTP200と別。
- **全257件のMasterclass単体テスト成功**：[最新の全テストログ](evidence/TEST_RESULTS_P04_TO_P06_2.txt)。既存229件＋新規P06-2 28件。
- **明日11月5日の発表**：[準備ガイド・台本・FAQ](journal_club/PRESENTATION_READINESS_20261105_JA.md)。発表用**34枚/43分+15分質疑+2分余裕**を維持し、研究紹介第26枚のSSDataBenchをBehaviorBench/Be.FM1.5へ差替えた。詳細版第42枚も同期。両方のPPTX/PDFとページごとの日本語話者ノートを更新。**P06以降の実務・臨床・大規模モデル公開を発表の条件にしない。**
- **学習の次はP06-3**。実会社のP05-5 Shadow S1／限定Live S2、実RCTの検証、モデル実重み公開は未完了のまま保持。


## 2026-11-05：Phase 6のP06-1〜5教材・人工コード一通り完了

[Phase6統合レポート](PHASE6_COMPLETION_AND_FIELD_GATES_JA.md)／[P06-3](P06-3_JA.md)／[P06-4](P06-4_JA.md)／[P06-5](P06-5_JA.md)。Statsmodels/SciPy、Spotify Confidence/Statsig/Microsoft ExPの研究設計を再利用し、**独自A/B統計ライブラリや新しい本番Ledgerを作らない**。完全人工のP06-3標本数・A/A、P06-4返金・費用・苦情によるDO_NOT_SHIP、P06-5ハッシュ照合・実サイト配信のみの独立readbackを実装。実人間の改善や実会社の利益を主張しない。

[レビュー対象テスト328/328件成功](evidence/TEST_RESULTS_P04_TO_P06_REVIEWED_20261105.txt)（P06-2まで257＋新規P06-3〜5の71）。本番発表用34枚はそのまま、詳細保存版**96枚/96ページ**にPhase6の3枚を追加して全日本語ノートと同期する。**学習次はP07-1**、実事業価値の未達ゲートは残す。


## 2026-11-05 P07-1：実際の人間の報酬・習慣を学ぶ

[講義・数式・5研究の比較](P07-1_JA.md)を追加。Collins公式WMHのMITデータ5セット／実行有効269,603試行を読み取り、参加者分割の学習・検証・テストと別研究4件の予測を実行。報酬・習慣・短期記憶の簡略アブレーションのLog lossを検証した。別途2026年のX投稿研究の公開図用パラメータの相関を計算したが、元の投稿モデルを再学習したものではない。**P07-1新規45テスト成功。** 証拠ファイルは`evidence/P07-1_*`、教育用のPythonコードは`experiments/p07_1_*`。生の実人間行はGitHubへアップロードしない。

研究保存版に英語2枚を追加して**98枚PPTX/98ページPDF、全100枚の日本語ノート**。本番34枚は維持。次講義は**P07-2**。ただし実人間の習慣・反すうの介入の因果効果は未測定。


## 2026-11-05 P07-2｜実人間の反すう関連・感情状態を予測

[P07-2日本語講義・HMM/GLM-HMMの基礎](P07-2_JA.md)、[実際に動くPython](experiments/p07_2_real_esm_state_prediction.py)、[30件の新規テスト](experiments/test_p07_2_real_esm_state_prediction.py)、[OpenESMの実行結果](evidence/P07-2_REAL_ESM_HOEBEKE_AFFECT_RESULTS_20261105.json)。Hoebeke40人/1450有効遷移のBrooding、Dejonckheere100人/6890有効遷移のStressを**別の対象として**、強いPersistenceとRidge/RandomForest等で比較。人物単位分割、未来情報なし、推定効果は治療の因果効果ではない。P07-1＋P07-2のレビュー済み75テスト成功。

[常設ハンドオーバー](HANDOVER_LATEST.md)、[公式WebのEN/JAコピー改訂案](ANICCA_SITE_COPY_UPDATE_PROPOSAL_20261105.md)。サイト更新の直接操作は安全制御でブロックされたためドラフトのみ、**本番サイトへの更新はしていない**。研究保存版100枚・本番34枚不変。**次はP07-4**。


### P07-3 と ManagerBench（2026-11-06）の新規教材

- [COM-B・行動変容の機能と介入技法（P07-3 日本語）](P07-3_JA.md)。
- [Behavior Foundation Model / ManagerBench v0.1 仕様](BEHAVIOR_FOUNDATION_MODEL_MANAGERBENCH_SPEC_20261106.md)。
- [英語書籍章：From Persuasion to Causal Behavior Engineering](BOOK_CHAPTER_BEHAVIOR_CHANGE_AI_P07-3_EN.md)。
- [評価器](experiments/managerbench_v0.py) と [ソフトウェアunit test](experiments/test_managerbench_v0.py)。人工fixtureの13/13テストは成功。新規実人間データの検証や共通モデルの訓練ではない。
- 最新進捗は必ず[唯一の正本](ROADMAP_STATUS_JA.md)と[引継ぎ](HANDOVER_LATEST.md)へ記録。公式サイトPR #9246とデプロイPR #871はマージ済み。Netlify run 42092065987と事後money-path smoke SUCCESS。本番GET+SHA検証済み。


## 2026-11-06 JST — Verified official site release
- Canonical bilingual marketing source PR #9246 merged as 0193bac5cc29406175a1f9a44019af633e605472; deployment pin PR #871 in anicca-products merged as 4981237d0dab6c19e809f490198bfc357d5d8eb6.
- Netlify GitHub Actions run https://github.com/Daisuke134/anicca-products/actions/runs/42092065987 **SUCCESS**, including independently reported Post-deploy money-path smoke & rollback.
- Independently fetched /, /en, /ja, /blog/manager and an existing blog article: all HTTP 200. Live /en and / SHA-256 = c1eed9d468439a5cf922e171967a1408d72dded8e077d7c8ebc45a3b6be331e2 ; live /ja SHA-256 = 2ff5d801bf80df6cedc9df96e6f74d6ef8b8b7ba6efb0673c2b9139657a6550a ; both match reviewed source hashes.
- Research PR #9248 merged as fb4cf428d7d654090d5c1e2205da89716e6cde1d: P07-3, BFM / ManagerBench v0 scorer with 13/13 software-fixture tests, book chapter, 105-slide English research PPTX and Japanese speaker notes. The older research-archive PDF has **not** been regenerated; a separate 16-slide PDF/PPTX exists. No shared model checkpoint, independent real RNT RCT, or official GLM-HMM refit exists yet.
- No new separate public blog article was published in this release; existing blog index/articles were verified to remain accessible.
