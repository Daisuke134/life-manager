# 追加の行動評価資産 — 用途別の再利用判断

2026-10-23 UTC。公開paper・metadata・選択codeの静的読取に基づくevidence note。**新規の部分参考例2件、実行動効果・介入撤去後の持続・害/依存を包括的に置換できると確認したbenchmarkは0件**。これは今回の有限な探索結果であり、全資産の不存在や「全endpointを単一benchmarkで満たすまで何も使えない」というgateではない。既存[V001の用途別受入](../specs/2026-10-23-v001-purpose-specific-acceptance-amendment.md)に沿い、目的と軸ごとの部分reuseを判断する。

このノートはdata/scorerの採用、用途別rights受入、新しいモデル比較・学習・人研究・運用の発動、Managerの効果や便益を証明しない。既存HelpSteerの候補一致proxy、H2の固定結果・SCORED finalと選別履歴を変更しない。モデル/data/scorerをManagerへ導入・実行していない。

## 1. one sec — 実app選択の観測と、残る欠測

一次資料は[PNAS原著 DOI10.1073/pnas.2213114120](https://doi.org/10.1073/pnas.2213114120)、[公式全文XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9974409/fullTextXML)、[OSF project](https://osf.io/p4wy6/)と[node metadata](https://api.osf.io/v2/nodes/p4wy6/)。取得XML SHA-256は `01abe1d22ea693fc5e58e8541bad90fbcf22e5e3833181ce3e730fe94a085647`。DOIをimmutable Git SHAとは扱わず、取得本文hashを別に保持する。

| 軸 | 確認したこと | 再利用する考え方 / 流用しないもの |
|---|---|---|
| 本人の選択と行動 | 利用者が対象appを設定し、opening attempt後のcontinue/dismissを機器記録。会話同意率とは異なる | 本人の任意goal、試行と実行/中止を区別する測定。app自身のログを第三者の独立観測と呼ばない |
| 独立単位・脱落 | 自発参加719人、主分析は6週継続した280人。field control群なし。別の500人online実験は5条件へのrandom assignmentで短時間の動画選択を測る | 反復opening/動画を独立した人へ水増しせず、研究・人物・時点を区別。主分析からの脱落除外を隠さず、field結果を無作為化対照効果にしない |
| 持続・害 | 6週は使用中の観測。screen timeは自己報告。撤去後の維持、体系的adverse events、依存/置換のendpointは確認できない | 使用中/撤去後、行動ログ/自己申告、害の未測定を分ける。著者の倫理的議論から安全性を認定しない |
| scorer・split | OSFの確認範囲にCSV metadataはあるが分析script/scorerは未確認。モデル用train/dev/final、人物/研究/時間holdoutは未確認 | scorer file/Git SHAを創作せず `SCORER_NOT_VERIFIED`。結果を読んだ後の選択をpristine finalにしない |

論文は**CC BY-NC-ND4.0**。論文のlicenseをOSF CSVへ自動移転しない。OSF nodeはpublic:true、node_license:nullで、data/codeの商用training・evaluationへの包括許諾は未確認である。公表事実/測定方法を参照する用途と、文章/図の転載・改変、data学習、scorer実行は別に判断する。非臨床digital self-controlの測定先例であり、全参加者の非臨床性やManagerの効果を認定したものではない。

## 2. INA / IntentionBench — 本人の意図に近い分類proxy

一次資料は[arXiv2510.14513v3](https://arxiv.org/abs/2510.14513v3)、[公式project](https://intentassistant.github.io/)、[INA app](https://github.com/IntentAssistant/INA)、[IntentionBench code](https://github.com/IntentAssistant/intention-bench)、[dataset card](https://huggingface.co/datasets/juheonch/intention_bench)。方法・測定・限界に関する選択passagesと選択codeを読んだ範囲で、全論文/全repositoryの監査・動作再現ではない。

field studyは24人開始、2人離脱、22人解析。3週間のwithin-subjectsでlogging-only / simple reminder / INAを各7日、順序randomized。本人が意図を入力するが、主要なoff-task比率は**LLM推定**で、意図との整合やfocused immersionは**自己報告**。独立に確認した生活上の行動完了/便益ではなく、撤去後の長期追跡もない。通知負担・workflow disruption・privacy懸念は調べているが、長期依存や体系的adverse eventsの評価を代替しない。

公開benchは著者2人の50 focused sessionsを混ぜ、元trajectoryと現在の意図の対応でon/off labelsを作る**合成の文脈分類**。field参加者の実行動効果datasetではない。false positiveをheuristicに訂正するsimulated feedbackというupper-bound条件も含む。

| 固定artifact | exact file/function・hash | 意味と制限 |
|---|---|---|
| bench commit `e6008a5c88af85464cb47f182f12e694725967ca` | [code/utils/metric.py::calculate_metrics](https://github.com/IntentAssistant/intention-bench/blob/e6008a5c88af85464cb47f182f12e694725967ca/code/utils/metric.py)、SHA-256 `35b02e14b903da3d90126395301b30ae9d83289f9b78c696c358d8014fab3919` | frameごとのTP/TN/FP/FN、accuracy/precision/recall/F1。空入力を0へ落とす動作はManagerのUNKNOWNへ移植しない |
| 同bench commit | [code/analysis.py::inference_single / inference_parallel](https://github.com/IntentAssistant/intention-bench/blob/e6008a5c88af85464cb47f182f12e694725967ca/code/analysis.py)、SHA-256 `22439acc15eda22af2317ff0e587c997689e7eed1f5b50b868143b0f48583e81` | Gemini呼出しを含むpipeline。provider不要のoffline scorer全体とは扱わず、今回は実行していない |
| HF revision `5c229b8616c46936bcd9d336b54e98e1769fa5c2` | [README.md](https://huggingface.co/datasets/juheonch/intention_bench/raw/5c229b8616c46936bcd9d336b54e98e1769fa5c2/README.md)、SHA-256 `ba1e1b191b7c0d08d32ad28bf40657529b89d829a38c8d69c93b1329d8cc2a63` | datasetのCC BY4宣言と生成方法。card取得とdatasetのManager採用を分ける |
| 別repoのapp commit `db149cd98e817ad0b1bf6116ecd3b4406c35ecab` | [INA/LICENSE](https://github.com/IntentAssistant/INA/blob/db149cd98e817ad0b1bf6116ecd3b4406c35ecab/LICENSE) はMIT | このlicenseをbench code/dataへ継承させない |

v3論文はCC BY4、dataset cardもCC BY4を宣言する。CC BY4は帰属等の条件下で商用/派生利用を許す著作権licenseだが、screen内の第三者素材等の権利を一括保証しない。bench treeに明示LICENSEは確認できず、READMEはdataset cardを参照する。**app MIT、bench code、dataset、paperを分離**し、commercial train/evalはその用途で必要なartifactごとに判断する。

公開の標準train/dev/finalや人物・研究・時間holdoutは未確認。mixed sessionsが元trajectoryを共有し得るため、frame random splitで人物一般化を示さない。著者2人の生成軌跡とfield参加者は別の単位である。source treeとv3論文が検証済みの組合せとも確認していない。

## 3. Managerへ借りる測定設計と、採用しない接続

- 本人の任意intent、実ログ、モデル推定、自己申告を別の量として定義し、goal変更/NO_ACTION/撤回、独立性、分母/欠測/脱落を明記する。
- 単純reminder/logging baselineとfalse-positive負担、使用中/撤去後、行動/生活機能/害/依存/置換を区別する。これらは用途別に既存測定を組み合わせる設計参照であり、一つのbenchmarkへの全条件充足要求ではない。
- **one sec/INAはいずれもapp/UIを持つ。No UIの先例ではない。** BobaやiMessageもUIであるという既存の区別を保つ。これらの測定設計から、Manager専用app/chatやスクリーンショット常時監視の導入を結論しない。媒体は本人が選ぶ既存の適切な環境と、その用途で成立する観測を個別に判断する。
- `helpsteer2_*::evaluate_cases` の候補一致を実行動effectへ昇格させない。`external_behavior_eval.py::evaluate_released_effects` のstudy-level契約へ、frame/attemptを独立な人・別研究として流用しない。既存の凍結protocol/results/finalの露出・選別履歴は維持する。
- この2候補だけから新たなmodel/scorer実行の許可を自動生成しない。適合する部分reuseは目的・rights・splitごとに検討できる。公開非個人研究に提携/NDAを一律要求せず、既存V001用途別受入、D014/D015有限doneや新規研究の未成立条件を変更しない。

既知Gym megastudyは既存catalogに含まれるため新規候補へ加算しない。本ノートは[scope改訂](../specs/2026-10-23-behavior-transformation-scope-amendment.md)と[study v2草案](../../pilot/BEHAVIOR_TRANSFORMATION_STUDY_V2.md)の測定設計を補助する参照であり、本人の実行動・人の便益・安全性をManagerで測定した結果ではない。
