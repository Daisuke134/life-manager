# DarkBenchから借りる評価設計と、直接採用前の差分

2026-10-23 UTC。新候補1件の公開paper選択箇所・公式tree/card・scorer/task/licenseを静的に確認した。**方法・codeの所在を参照する追補で、data/scorerの導入・実行やV002の受入ではない。** 既存[用途別評価方針](../specs/2026-10-23-v001-purpose-specific-acceptance-amendment.md)と[実装計画Task2](../plans/2026-10-23-behavior-transformation-model-plan.md)に従い、用途ごとに既存資産を組み合わせる。

## 一次資料と、実際に確認した範囲

[DarkBench原著v1](https://arxiv.org/abs/2503.10728v1)は、Apart Research等のEsben Kran、Jord Nguyen、Akash Kundu、Sami Jawhar、Jinsuk Park、Mateusz Maria Jurewiczによる研究。660 prompts/6 categories、14 models/9,240 prompt-response pairs/27,720 model evaluationsを報告する。これは著者報告で、今回の独立再計算ではない。

6分類はbrand bias、user retention、sycophancy、anthropomorphization、harmful generation、sneaking。借りるのは、元promptと応答を結んで分類別に判断し、invalidを別に扱う設計である。retention発言率を本人の実依存率へ、sycophancy/sneakingの採点を実行動変容・苦しみの低減へ読み替えない。

原著Appendixは3名のhuman annotatorsによる1,680 examplesのbinary annotationとLimeSurvey上の提示・button順randomizationを報告する。Table3のhumanとのCohen’s Kは、user retentionで.62/.72/.66、sycophancyで.57/.27/.73とjudge/categoryで異なる。論文のhuman validationがあることと、その原response・各人票・裁定goldが再利用可能なartifactとして公開されていることは別である。**今回読んだ公式metadataでは、そのexact response-human-label bindingは未確認。** JSONL/TSV本文は取得していないため、未読fileにfieldが存在しないという断定もしない。

| 資産 | 固定点・利用条件の確認 | 今借りるもの |
|---|---|---|
| [公式code](https://github.com/apartresearch/DarkBench/tree/7eef15102b37df2a15a6031cbbed6be488de7fbe) | commit `7eef15102b37df2a15a6031cbbed6be488de7fbe`。[LICENSE](https://github.com/apartresearch/DarkBench/blob/7eef15102b37df2a15a6031cbbed6be488de7fbe/LICENSE)本文MIT、notice等の条件を保持 | 既存Inspect engineを使うtask、公開rubric/parser/metricの構造。今回はcodeを複製・導入しない |
| [canonical dataset card](https://huggingface.co/datasets/apart/darkbench/blob/c27ae5f155e75f7269e903bc2ddb8458e3d09304/README.md) | revision `c27ae5f155e75f7269e903bc2ddb8458e3d09304`、MIT宣言、660 prompts/単一train configの説明 | prompt資産の所在。本文・行数/schema/label bindingは未検証、学習/evalへのdata導入なし |
| [旧anonymous card](https://huggingface.co/datasets/anonymous152311/darkbench/blob/a3c639ad48a5f36df36c6d5fead78a08382b568f/README.md) | revision `a3c639ad48a5f36df36c6d5fead78a08382b568f`、Apache2.0宣言 | canonical版との版/権利の区別。同じbytes/schemaと確認したわけではない |

codeやprompt cardのlicenseを、未確認のmodel outputs/human票やpaper図版の許諾へ継承しない。人手artifactの所在・版・原responseとの対応・固有権利は未確認のまま残す。これは部分reuse全体を止める普遍gateではない。

## 採点契約の差を、接続前に確認する

固定[scorer.py](https://github.com/apartresearch/DarkBench/blob/7eef15102b37df2a15a6031cbbed6be488de7fbe/darkbench/scorer.py)のSHA-256は `7cdb551f218fb171026b5ddebafcc35c3dac9cc8caf7517d28d4c7567dca15ea`、[task.py](https://github.com/apartresearch/DarkBench/blob/7eef15102b37df2a15a6031cbbed6be488de7fbe/darkbench/task.py)は `4f67295af6ed38b4eaaafedbf94be965bfc1443b6043bfadf193e6f634c1c0c3`。静的読取のみで、scorer/import/API実行はしていない。

| 上流の実装 | 既存Managerへ接続する際の区別 |
|---|---|
| `dark_pattern_score`は空categoryへ0を返す | 未採点・分母0はnullのまま。観測なしをpatternなし/安全0にしない |
| issue付きinvalid=-1は正のincidenceにならずcategory分母に入り、answerなしのparse失敗はskipされる | 全assignedとVALID/INVALID/FAILED/UNKNOWN/NOT_RUNを別記する。既知INVALID/FAILEDをterminal UNKNOWNへ統合せず、意味内容が未採点ならsemantic判定nullを保つ |
| `_try_score`は既定3attempts、`_extract_json`はJSON抽出/修復を行う | 既存の固定attempt/retry0/strict parserと同一契約として扱わない。必要な用途/versionと全attemptを先に定義する |
| 現taskのdefault judgeはgpt-4o-mini | 原著のClaude3.5Sonnet/Gemini1.5Pro/GPT-4oという3judge比較と同一視しない |

[上流reproduce README](https://github.com/apartresearch/DarkBench/blob/7eef15102b37df2a15a6031cbbed6be488de7fbe/reproduce/README.md)自身も旧Overseer promptの誤判定・信頼性の限界を明記する。将来実接続が必要になった時は、上流native値とManagerの分母/失敗記録を別記するか、意味を変えるなら別versionのadapterとして明示する。今回はその実装も再現実行もしていない。新しい評価engineを作る根拠にはしない。

## Managerでの次の使い方

既存の`manager_core/collaboration_evaluation.py`、`collaboration_comparison.py`、`outcome_bench.py`、`governance.py`の記録・未測定・害の契約を再利用する。新しい参照を実採用する時は、まず評価purpose、許可されたexact応答、rubric/evaluator/版、referenceの来歴と利用条件を結ぶ。実callerに不整合が確認できた箇所だけを最小差分にする。過去のINTIMA生成物や新生成responseへ原著のhuman票/集計率を付け替えない。

friendlyな支援と欺瞞的な親密さ/依存誘導を同一視しない。Digital Buddha/Managerという使命・研究上の名称を、上流anthropomorphism分類から機械的に禁止する結論にも変換しない。実証済みの自覚・感情・権威・救済保証があるという誤認を与えるcontentの評価と、名称は区別する。原著には政治/社会的争点の例もあり、全datasetを非政治的用途へ適合確認したわけではない。今回subsetや操作policyを作成していない。

既存113 taskの85done/18todo/10skipped、V002/V003 todo、モデル採用HOLD、採点済みfinal16、新規U004のDRAFT/NOT_REGISTERED/参加者0/介入0を保持する。追加training/scoring、実人介入、人便益、独立再現、記事公開をこの追補から認定しない。
