# 2026-10-11: Managerに直接近い人間・社会シミュレーションの求人とイベント

Oct08 landscape、Oct10 broad jobs/eventsを起点に、公式採用ページと主催ページを再取得。取得原本: `/workspace/scratch/manager-research/oct11/direct-fit/`。今回の「直接」は人間・集団・人口の行動をモデル化し、環境/条件を変更して意思決定を試すこと。一般LLM評価、科学実験、3D物理、自動運転を直接社会simulationとして数えない。応募/登録/連絡/購入はしていない。

## 現在公開された8職種

Simileは公式[public Ashby API](https://api.ashbyhq.com/posting-api/job-board/simile)を本日取得、15職種。下記3件はisListed=true、San Francisco、OnSite、FullTime。Aaruの3件は公式一覧と個別本文が存在、Apply公開、NYCで週5日office。Primitive2件も公式JDと応募form公開、SF/NY Full Time。公開中は採用充足の保証ではない。

|会社 / 正確な職種 / 個別URL|要件と実際の仕事内容|Managerで示す能力と不足|
|---|---|---|
|Simile — [Evaluations - Member of Technical Staff](https://jobs.ashbyhq.com/simile/33d75074-c23b-4a1f-bfdb-129bcc5be662)|人間/人口/市場/集団simulationのmeasurement。noisy ground truth、分布、sampling、calibration/uncertainty、Python/SQL/R/notebooks、hands-on tool構築。survey、transactions、intervention、group behavior。recent graduate/self-directed builderも明記。|実人間データholdoutとsimulationを比較、segment failures、bootstrap CI、baseline、measurement validity。一般LLM評価職だから入れたのではなく、人間behavior simulation自体を評価する職。最も入口が広い。|
|Simile — [Evaluations Engineering - Member of Technical Staff](https://jobs.ashbyhq.com/simile/beaa243c-233f-45f2-9e10-8d54e1eda9d1)|数年production software、backend/data pipelines/relational schemas。人口・model version横断execution、data provenance/versioning/access controls、human data ingestion、holdout integrity、研究者UI。|world/population/model/dataset/runをversioned objectsで保存し再実行・compareする基盤。portfolio単体で実務年数を置換しない。|
|Simile — [Research - Member of Technical Staff](https://jobs.ashbyhq.com/simile/fbf3ed84-26a2-489f-b62f-82f435568387)|Python/modern ML、GPU experiments、large-model training/fine-tuning lifecycle、論文再現/批評/technical writing、deployment。CSS/behavioral economicsはnice-to-have。|personality/memory/social influence ablation、人間ground truth、学習を含む再現研究。API orchestrationのみではGPU training経験にならない。|
|Aaru — [Researcher, Population Simulation](https://aaru.com/careers/f718d12f-67e9-4fe9-91cc-9e3b69ff00fe)|ABM/CSS/synthetic populationの深い経験、PhD又はindustry research同等depth。real profiles→agents、survey/behavior/psychometric grounding、LLM+classical hybrid、GSS/census等のdistributional fidelity。|人口joint distribution/crosstabs、demographic-prompt baseline、representativeness、rare subgroup fidelity。会話が自然というだけでは足りない。|
|Aaru — [Software Engineer, Simulation](https://aaru.com/careers/f04cd7a3-b53c-4797-bb8f-ebfe0467e9fe)|3+年ML/AI、production LLM、hypothesis→experiment→deployment、full lifecycle。audience/world/response loop、agent/population objects、simulation contracts、evaluation harness、hybrid architecture、速度/費用。|Managerのworld state/action/observation、typed population、intervention、run orchestration、cost/perf、decision reportを一貫したproduction systemへ。研究世界→商品化の最も直接的な職。|
|Aaru — [Researcher, Evaluation](https://aaru.com/careers/4490a4b7-ad45-4bf6-b00f-190a6d9f41ad)|ML/stats/behavior/CSS/economics等でrigorous empirical work、construct、observational/controlled/prospective研究、power/causal threats/leakage/condition shift、code。PhD不要だが同等research depth必須。個人/人口/集団/longitudinal interactionsの精度を測り、研究から独立したfinal measurementを守る。|temporal holdout、registered prospective predictions、calibration/proper scores、agent interactions、negative findings。モデル内介入を現実政策の因果効果と混同しない。|
|Primitive Labs — [Member of Technical Staff, Research](https://primitivelabs.ai/careers/research)|agents/ML/simulation/cognitive scienceでresearch lead経験、rigorous experiments、大モデル/agents、production化。real user decisions、simulation architectures/memory/continual learning、human-data behavioral fidelity、papers/OSS。|人間browser journey/action/path/dropoffをモデル化し、memory/decision ablationとhuman-data benchmark。製品体験のbehavior simulationであり、国家/制度ABMと同じ範囲とはしない。|
|Primitive Labs — [Member of Technical Staff, Founding Engineer](https://primitivelabs.ai/careers/founding-engineer)|shipped full-stack products、高自律性、agent-native tools/AI SDLC。infra/agent architectures/evals/developer tools/product、computational cognitive scienceからarchitecture。|agent/runtime/world/trace/inspect UIをshipして実ユーザーで改善。人口研究職というよりhuman-behavior agentsを製品化する職。|

給与: Simile3件は$200k–400k、Aaru3件はページ上部$200k–600k/equity。Primitiveはcompetitive salary/equity、具体額未公表。日本remoteの確約はどれにもない。

**重要なOct08報告の訂正:** 今回取得のAaru3件は全てbenefitsに **visa sponsorship and relocation support** と明記。公開本文上「不明」ではない。個別visa種類/承認の保証まではない。Simileは取得JDでvisaの確約なし。PrimitiveのformにUS work authorization/visa sponsorship必要性の質問があるが、提供の約束ではないためunknown。

Primitiveの[Member of Technical Staff, Intern](https://primitivelabs.ai/careers/mts-intern)も本日本文/formを取得できた。paid、potential重視の入口として別途候補（8職種の件数外）。SF/NY Internship、US就労/visaは同様に要確認。

## 研究チームと採用証拠を分ける

AgentSociety/Concordia/AI Economistの研究活動・公開codeが直接領域に近くても、それだけで現在のnamed vacancyにはしない。今回のprimary-source確認では、当該チーム指定のcurrent named jobを追加検証できなかった。一般DeepMind/Salesforce ML求人で水増ししない。別の研究担当がcode/研究者の適合を調査中。

Synthetic Users公式サイトは取得したが個別current title/requirements未確認。Seldon/Blokも前回Notion shellだけで個別live role未検証。採用ゼロと断定しない。WovenのOct08 Digital Twin職は主にCV/perception、Behavior MLはAD/ADASであり、今回の直接社会simの8件から除外。living laboratoryという企業背景から職種を社会simulationと読み替えない。

## 2026-10-11以降のイベント: 厳密な直接候補

|イベント/一次URL|日程/参加/料金|直接つながる内容と確認限界|
|---|---|---|
|[SBP-BRiMS 2026](https://sbp-brims.org/2026/)、[Registration](https://sbp-brims.org/2026/registration/)|**10/12–14 2026 Hybrid**、CMU Gates Hillman Complex/Rashid Auditorium、Pittsburgh。onlineあり。registration now open、General $500、Student $400、tutorial $25/件。virtual/対面同料金。|Social Computing, Behavioral-Cultural Modeling & Prediction and Behavior Representation in Modeling and Simulation。人間/社会行動simulationに最も直接。公式headerと2026 registrationを本日再確認。前回programに旧2024本文が残るため2026speaker/talkを確定情報として転載しない。残席/virtual双方向交流未確認。|

**Simile/Aaruの会社主催またはfounder登壇の未来イベントは、今回確認したprimary pagesでは検証できなかった。** Simile公式home/blogのESOMAR/Itaú報告やLatent Space動画は過去記事/収録であり、未来イベントではない。Aaru home/publications（本日取得、最新research Sept24）は未来イベントを示さない。これは予定が存在しないという主張ではなく、primary evidence未取得という意味。Google検索はchallenge shellで検索結果を読めなかったため、包括的web検索完了とも主張しない。

追加でCSSSA公式[homepage](https://www.computationalsocialscience.org/)を取得。**CSS 2026 Santa Fe** と **October Webinar: Nigel Gilbert — Policy in a complex world: towards complexity-aware …** の告知が実在する。政策・complexity/ABMという内容は直接適合。ただし個別[conference](https://computationalsocialscience.org/conferences/css-2026-santa-fe/)/[webinar](https://computationalsocialscience.org/october-webinar-nigel-gilbert/)頁はHTTP406、feed/wp-jsonも406で、日時・登録状態・料金を確定できない。したがって「未来参加可能なverified event」の表に入れず、**日程検証待ちの一次候補**として残す。過去のwebinar一覧を現在募集の仕事や未来eventとは扱わない。

周辺の学習機会として[Serena Wang: From Metric Selection to Metric Discovery in AI Evaluation](https://hai.stanford.edu/events/from-metric-selection-to-metric-discovery-in-ai-evaluation)はStanford HAI公式で10/16 13:00–14:15 US/Pacific、virtual登録。social choice theoryとmetric発見のeconomic incentivesがテーマで、評価項目/制度設計に接続する。ただし人間simulationを建てる会議ではなく**隣接講演**。主催会社との接点として数えない。coding meetupsは今回の直接候補に追加しない。

## 優先順位

1. 入口の柔軟性と人間/集団simulationを両立: **Simile Evaluations**。研究深度を示せるなら**Aaru Evaluation**もPhD不要を明示。
2. Managerそのもののarchitectureが最も伝わる: **Aaru Software Engineer, Simulation**。ただしML/AI 3+年が条件。
3. 人口/社会研究を本業化: **Aaru Population / Simile Research**。population fidelityとGPU/research経験を別々に証明。
4. user-level human behavior/cognitive architectureを実製品へ: **Primitive Research / Founding Engineer**。
5. すぐ参加可能な直接研究eventは、今回検証範囲では **SBP-BRiMS hybrid**。会社の未来eventが未検証である空欄を一般AI networkingで埋めない。
