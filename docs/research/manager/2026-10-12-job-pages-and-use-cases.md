# 個別求人から読む人間シミュレーションの仕事と用途

2026-10-12に本文再取得・読解。前日の要約だけで判断しない。Aaru3役職、Simile公式Ashby公開APIの3役職本文、Primitive2役職の全8件。取得原本とHTTP状態は `/workspace/scratch/manager-research/oct12/`。新規応募・送信はしていない。

## 各求人の仕事、条件、研究への含意

|個別ページ|本文の具体的な仕事|条件の区別|Managerで示す成果|
|---|---|---|---|
|[Aaru Population Simulation](https://aaru.com/careers/f718d12f-67e9-4fe9-91cc-9e3b69ff00fe)|structured/unstructured profile、demographic/attitudinal/behavioral distribution、survey/trace/psychometric grounding、LLM+classical hybrid、GSS/census/panel評価|PhDまたは業界研究の同等深度、synthetic/ABM/CSS経験。大規模人口構築・調査手法・論文はstrong候補条件|joint distribution・rare groups・profile coherence・予測誤差を実データで比較|
|[Aaru Evaluation](https://aaru.com/careers/4490a4b7-ad45-4bf6-b00f-190a6d9f41ad)|rails=dataset/harness/schema/report、carts=historical/prospective/longitudinal/group研究。proper score、ranking、sampling、漏洩・shift、判断損失|PhDと既存population職歴は不要と明記。ただし同等research depthと厳密な実証、code、独立判断が必要|baseline比較、未見条件、予測の事前固定、時間split、失敗から作った評価、判断が変わった証拠|
|[Aaru Simulation Engineering](https://aaru.com/careers/f04cd7a3-b53c-4797-bb8f-ebfe0467e9fe)|audience→world→responseをproduction化、population objects/contracts/evals、速度/原価、顧客向けcalculation/publication|3+年ML/AI researchまたはapplied、production LLM、実験→評価→deployment、全lifecycle。Bayes/causal/multiagent/論文はstrong候補|同じ契約の2world、run orchestration、計算台帳、再現・費用・readback|
|[Simile Evaluations](https://jobs.ashbyhq.com/simile/33d75074-c23b-4a1f-bfdb-129bcc5be662)|分布/雑音/人間ground truth、model regression、qualitative/retrieval/report評価、取引/介入/group予測|must: evaluation taste、LLM基礎、stats、実装、ownership。nice-to-have全部を一人に期待しないと明記|実測分布との誤差、calibration、bootstrap、群別失敗、モデル変更を判断するeval|
|[Simile Evaluations Engineering](https://jobs.ashbyhq.com/simile/beaa243c-233f-45f2-9e10-8d54e1eda9d1)|model/population/dataset横断実行、relational schemas、provenance/access、survey/label/review、regression調査|数年production software、backend/data systems、deployment/adoption。統計・人間データ・agentic tools等はnice|versioned run/dataset/policy、実運用、利用者feedback、漏洩防止、研究者用inspection|
|[Simile Research](https://jobs.ashbyhq.com/simile/fbf3ed84-26a2-489f-b62f-82f435568387)|独自行動データ、NVIDIA/GPU学習、論文再現/批評、evaluation→production|must: Python/ML、GPU実験、大規模training/finetune lifecycle、研究読解、全工程。CSS/behavior econ/distributedはnice|実際の学習実験・ablation。API呼出しだけでGPU訓練実績としない|
|[Primitive Research](https://primitivelabs.ai/careers/research)|memory/cognitive science/continual learning、real user decisions、human fidelity、papers/OSS/talk|research lead、厳密実験、large model/agent、productionへの接続|人間のjourney/decisionと記憶機構の比較、予測ground truth|
|[Primitive Founding Engineer](https://primitivelabs.ai/careers/founding-engineer)|fullstack→production、design partner feedback、agent architecture、AI SDLC|実際のfullstack出荷、自律性、agent tools設計と使用。年数指定は本文にない|動く製品と利用者の改善ループ、run inspection、運用の証拠|

Aaru3件はNYC週5日対面、visa sponsorship/relocation明記。Simile3件はSF OnSite。PrimitiveはSF/NY。Simileの3件には同一役職への再応募を90日待つ規定がある。無差別に未準備で全件送る前に、役職ごとの提出品質と既存応募履歴を確認する。

## 求人を技術資料として読む際の限界

Aaru求人のhybrid LLMと公開methodsのnon-LM coreは両方を記載する。求人から特定のproduction topology、loss、data ownershipを推定しない。Simileの80億人使命も達成済み人口coverageではない。求人の企業成長数値は同社の採用広報で、独立検証した経営指標として記事へ移さない。

## 用途の証拠

- Aaru [EY](https://aaru.com/case-studies/ey-wealth-research): 3,600 affluent investors、30+markets、53matched questions、median Spearman .90、平均差7.1pp。reconstructionであり資産増加の因果効果ではない。
- Aaru [Breakwater](https://aaru.com/case-studies/breakwater-conviction-advantage): 40,000synthetic investors/71judgments、capital markets decision tracker。simulated人数は実被験者数ではない。
- Aaru [Scenario Planning](https://aaru.com/use-cases/scenario-planning): 顧客・従業員・政策担当者・競合の適応と二次効果。サイトの一例はIllustrative scenarioと表示、実現効果ではない。
- Aaru公開methodsにpolitics/public affairsとelectoral/geopolitical forecastingがapplicationとして列挙される。今回のfresh顧客caseから具体的な選挙予測成果は確認していない。選挙結果予測と投票行動への介入も区別。
- Simile [Itaú](https://www.simile.com/blog/itau-at-esomar): Pix Automáticoのtrust/comprehension/control/adoption intent。5weeks→4businessdaysはresearch cycle。
- Simile [CVS](https://www.simile.com/blog/simile-cvs-health): pharmacist access/wait/communication、refill intent/benefits、downstream pilots。health effect sizeの実測をこのarticleから確定しない。
- [Primitive Instinct](https://primitivelabs.ai/instinct): customer-calibrated agents、journey/friction/conversion、approved recommendations→tested improvements。競合は全社prediction-onlyとはしない。
- [Synthetic Users](https://www.syntheticusers.com/): synthetic interviews/problem exploration/concept test。表紙の95% testimonialは比較benchmarkに使わない。
- [Seldon](https://seldon.com/): analytics/ethnography/OCEAN personas、journey friction。87%の宣伝値は方法確認なしで一般精度へ転用しない。

求人を読む利点は、モデル単体に加えて、データ、評価、運用、顧客への出力が独立の専門領域だと理解できること。Managerの成果もこれらをつなぐ必要がある。
