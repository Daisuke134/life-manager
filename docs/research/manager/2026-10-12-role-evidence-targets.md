# 8求人とManagerの実績：内部用の対応表

2026-10-12に確認した募集本文に基づく。公開会社解説とは別資料。以下の英語文は完成後に結果を埋めるための目標文であり、現在の応募に使用する完成実績ではない。採用を保証する条件表ではない。作業順と状態は統合SSOT。

|職種・一次資料|中心となる適合/必要条件|追加の強み|Managerで示す証拠と残る不足|
|---|---|---|---|
|[Aaru Population Simulation](https://aaru.com/careers/f718d12f-67e9-4fe9-91cc-9e3b69ff00fe)|合成人口/ABM/計算社会科学の深い経験、統計検証できる構造化LLM出力、個人のもっともらしさと分布精度の区別、関連PhDまたは同等の産業研究の深さ、null結果の説明|大規模人口生成、調査/心理測定/人口統計、関連論文、研究を出荷|集計制約付き人口生成、未使用交差表と希少集団の評価、相関感度分析。修士号をPhDと書かない。同等の研究の深さは一つのrepoだけで自動的に成立しない|
|[Aaru Evaluation](https://aaru.com/careers/4490a4b7-ad45-4bf6-b00f-190a6d9f41ad)|厳密な評価実績、評価が研究/製品の判断を変えた経験、construct定義、標本・因果・power・漏洩・shift、分析コード、独立判断|因果/予測/心理測定、縦断/取引/運営結果、評価基盤、grader信頼性、隠れた失敗の発見、結果の対外説明|事前protocol、time/region holdout、強いbaseline、集団別失敗分析、結果から方針を変更した記録。PhDや以前のpopulation職は必須ではない|
|[Aaru Simulation Engineering](https://aaru.com/careers/f04cd7a3-b53c-4797-bb8f-ebfe0467e9fe)|深いML/AI、production LLM、3年以上のML/AI開発、実験から配備まで、データ/学習/評価/統合、協働出荷|主要ML論文、multi-agent/追加学習、Bayes/因果/Monte Carlo、定量分野、研究者との共同試作|人口→応答→状態遷移→実行→readbackの実装、費用/latency/failure、運用記録。3年条件は短期開発で埋められず、既存研究/職歴の実期間を確認する|
|[Simile Evaluations](https://jobs.ashbyhq.com/simile/33d75074-c23b-4a1f-bfdb-129bcc5be662)|何を測るべきかの判断、LLM学習/評価基礎、標本/校正/分布/不確実性、コード、ownership|評価基盤、人間評価/grader、survey/Bayes/因果/psychometrics、介入実験、集団行動|prediction calibration、coverage-error曲線、group holdout、独立baseline、constructとproxyの区別。GPU大規模学習の専門家という別条件を混同しない|
|[Simile Evaluations Engineering](https://jobs.ashbyhq.com/simile/beaa243c-233f-45f2-9e10-8d54e1eda9d1)|数年間のproduction-quality software、backend/data/relational models、設計から導入/adoption、version/provenance/holdout、ML理解、専門利用者のための使いやすさ|benchmark/platform、研究ツール、ラベル/人間評価、収集自動化、統計、アクセス制御、agentic engineering|schema、data/model version、protected holdout、再現runner、regression、権限と監査、外部の実利用。CLIを一度動かすだけではproduction/adoptionを証明しない|
|[Simile Research](https://jobs.ashbyhq.com/simile/fbf3ed84-26a2-489f-b62f-82f435568387)|Python/ML framework、GPU実験、大規模モデルのtraining/finetuning lifecycle、論文再現、記述、配備まで|学術背景、社会科学/行動経済、分散学習、多エージェント推論最適化|公開人間行動研究の必要部分を再現、実GPU追加学習、base対比較、ablation、inference配備。API呼出を学習経験にしない。小規模LoRAだけで大規模/分散の全経験とはしない|
|[Primitive Research](https://primitivelabs.ai/careers/research)|agent/ML/認知/シミュレーション研究を主導、厳密な実験、large models/agents、研究からproduction|本文で別のNice一覧はなし。papers/OSS/talkは職務に含む|記憶・適応・集団行動の必要な仮説、実観測とのfidelity、memory/interaction ablation、論文形式report、モデル改善とruntimeまで|
|[Primitive Founding Engineer](https://primitivelabs.ai/careers/founding-engineer)|full-stack productのproduction出荷、自律的ownership、agent-native工具、AIをSDLCに適用|本文で別のNice一覧はなし。design partner feedbackと出荷は職務に含む|Managerの端から端の出荷、データ/実行/評価基盤、design partner feedback→新release、テストと運用。受益者UI不要でも運営/研究用の技術基盤は必要|

Simileの二つの評価職は追加条件を全員が全て持つ必要はないと明記する。必要条件と追加条件は区別する。AaruはNYC週5対面とvisa/relocation支援を明記。SimileはSF対面、同じroleへの再応募90日。Simile/Primitiveのvisa支援は確認できた保証として書かない。

## 達成後の英語履歴書文の型

以下は全て内部目標。括弧を実runの値・期間・条件で置換し、本人の担当が確認できてから応募版に採用する。

- Population: “Built a weighted synthetic-population pipeline from public aggregate constraints; evaluated marginal and held-out joint-distribution fidelity across [regions/periods], with subgroup coverage and sensitivity analyses.”
- Evaluation: “Designed a preregistered evaluation of population-level behavioral forecasts; compared [models] against [baselines] on [held-out units], quantified calibration and subgroup errors, and changed [design decision] after identifying [failure].”
- Simulation engineering: “Implemented an end-to-end population/environment/policy/execution pipeline with versioned contracts, budget constraints, idempotent actions, and verified state readbacks; measured [cost/latency/failure outcomes].”
- Eval infrastructure: “Built a reproducible evaluation service with dataset provenance, protected holdouts, versioned model adapters, regression reports, and [documented adoption].”
- Research: “Reproduced [specific published experiment] and fine-tuned [actual model] on [permitted data] using [actual hardware]; reported held-out results and [ablations], including [negative finding].”
- Founding engineer: “Shipped [actual deployed system] from data ingestion through execution and evaluation; incorporated [documented partner feedback] into [released changes].”

単一の成果でも、職種ごとに先頭の焦点と証拠を変える。存在しない別成果を作らない。未完成の目標は応募版へコピーしない。既存の神経/行動研究、被験者単位holdout、企業のagent導入、Databricks分析は、実際の担当・期間・成果の範囲で残す。

## フル面接のための証明

書類: repo、再現command、比較表、本人の担当、技術report。
技術: data leakageを防ぐsplitの理由、評価指標の意味、反証例、CIの独立単位、予測と因果の違いを説明する。
実装: runnerまたは一つの主要モジュールをその場で修正でき、failure/timeout/費用を扱える。
研究: 仮説→比較→nullも含む結果→設計変更を、自分の判断として説明する。
適合: 入社後に何を改善できるか、勤務地/就労条件、独立事業との知財・利益相反を実際の条件で確認する。

すべての求人へ同時に形式応募するより、共通成果を完成させ、各roleの中心条件と証拠が揃った段階で応募する方針。特に90日待機があるroleへ未完成のまま連続応募しない。個別の採用結果は能力だけでなく募集枠、比較候補、時期、面接によるため、保証しない。
