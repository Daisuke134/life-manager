# Manager周辺の事業・一次資料・採用調査（2026-10-08 UTC）

確認方法: 公開公式サイトと、公式求人に対応する公開Ashby/Lever APIをHTTP取得。応募、問い合わせ、ログインは行っていない。生データは `jobs-oct08/` に保存。日付は閲覧日であり、掲載が今後も続く保証はない。「公開中」は取得時に公式求人一覧・個別職種・応募導線が存在したという意味で、採用枠充足・就労資格・副業可否を保証しない。

## 要点

- **直接近い**: Simile/Aaruは人間・集団の行動モデルと意思決定の反実仮想。Primitive Labs/Seldonは実際のWeb/UIを行動エージェントに使わせる事前検証。Synthetic Usersはインタビュー/概念・メッセージ研究を前倒しする合成回答者。
- **日本で具体的求人を確認**: Woven by ToyotaのTokyo Digital Twin Platform。ただし確認できた職種はCV/ML seniorで、LLM社会シミュレータを作っただけで条件を満たすわけではない。都市住民・交通・エネルギーの実データとvirtual testの接点がある。Woven Cityの現地は静岡県裾野市、会社のTokyo求人とは所在地が異なる。
- **応募先として強い証拠**: Simile (SF onsite)、Aaru (NYC中心/Singapore APAC)、Primitive Labs (SF/NY)。Seldon/Synthetic Usersは採用入口のみ確認、Notion本文が取得できず職種を列挙できない。Teneraの指定ドメインは接続403で、機構・求人とも未確認。
- **Managerで示すべきもの**: 見た目が自然な社会だけでは足りない。実データとの分布照合、holdout、漏洩防止、校正・不確実性、再現性・出典、反実仮想、速度/費用、失敗例まで実行可能な成果物として見せることが、実際の求人文に最も近い。

## 事業と仕組み: 公式説明と確認範囲

|対象/一次URL|実際の提供物・説明される機構|公開資料/コードの状態|Managerとの距離|
|---|---|---|---|
|[Simile](https://www.simile.com/)|顧客・従業員・人口が新製品、施策、政策等にどう反応するかをシミュレーション。実人間の大規模研究/独自行動データからモデルを学習し、週次で実人間との7,000以上のevaluation、分布距離・effect size・観測行動を比較。結果毎にaccuracy confidenceを付け、ドリフト時にデータ更新。顧客のopt-in first-party dataでcustom model。|公式ホームResearchにGenerative Agents、1,000 People、human behavior fine-tuning等の系譜。企業のproduction weights/training data/source公開はこの調査で確認していない。研究論文の公開≠製品の再実装可能性。|集団の介入/行動モデルと検証の設計が直接近い。|
|[Primitive Labs](https://primitivelabs.ai/)、[Instinct](https://primitivelabs.ai/instinct)|既存research/analytics/customer dataを校正済み顧客モデルへ。価格感度、trust、intent、attention、patience等を持つagentをlive web/mobile journeysに走らせ、click/screen/decision/abandonmentを記録。segment差・friction・counterfactualを調べ、推奨から承認済み修正/テストへ。|[Insights](https://primitivelabs.ai/insights)でlaunch/資金ニュース確認。公開ベンチマーク、論文・評価データ、製品ソースは未確認。Research求人はpapers/open-source発表を業務として明記するが、これ自体は既に公開済みという証拠ではない。|社会世界より「顧客が使うUI/サービスの行動環境」側。Managerでproduct journey検証を加えると接続。|
|[Synthetic Users](https://syntheticusers.com/)|対象者をdemographics/behaviors/psychographics/professionで定義し、study設計→interview→insights。OCEAN人格を持つmulti-agent構成、個別profileとinterviewを通じたcontext/continuityを説明。problem exploration/concept/custom-script研究。公式はdiscovery co-pilotとしてorganic researchを重点領域に回す説明。|[Science](https://syntheticusers.com/science-posts/21-peer-reviewed-papers-that-support-synthetic-users)の関連研究集。ホームの85–92% parity/95% feedbackは同社の紹介・測定の主張で、一般化性能を独立再計算していない。公開製品コード/weights未確認。|定性的UXR・合成回答者。世論/政策因果や社会動態が検証されたとは読めない。|
|[Seldon.com](https://seldon.com/)|analytics/ethnographic research由来のOCEAN personaをproduct journeyに走らせ、bugs/friction/insightsをship前に得るdecision layer。ホームは1.2M real sessions、87% behavioral fidelity、SOC2 Type IIを主張。|当該accuracyの設計/データ/独立再現コード未確認。企業copyrightは**Blok Intelligence Inc.**。[Roles公式導線](https://joinblok.notion.site/Open-Roles-at-Seldon-35d5df33b37480f49bd8e7c4c3df9442?source=copy_link)。|Primitiveと同じUI/顧客journey側。Seldon.ioのMLOps会社と名前だけで混同しない。|
|Tenera (`trytenera.com`)|指定ドメインのHTTPSとwww/robotsを試したがproxy tunnel 403。製品仕様は一次本文取得できず未確認。|検索も一意に裏付けられず、似た名称の `tenera.ai` を同一企業に置き換えない。|分類保留。スクリーンショットの社名/ドメインだけから社会simulation企業と断定不可。|
|[Aaru](https://aaru.com/)、[research 2026-09-24](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)|実世界profileから人口/agentを構成し、条件を変えてpricing/product/message/strategy等の結果を試す。求人はstructured/unstructured profiles、survey、behavior traces、psychometricsにgroundingし、LLMとclassical computational social scienceを組み合わせると記述。研究記事は2,993 survey questions、TVD7.62%、MAE3.53%、sample-adjusted MAE2.78 points。別検証で実購買credit-card ground truthとの比較、予測誤差のconfidenceも評価。|論文相当の長文技術記事・評価条件/metrics/refsあり。ただし会社自身のreportであり、この調査は再計算していない。非同一test setの他社数値との比較を同条件head-to-headと思わない。公開production code/model・全評価データは未確認。|代表性/分布精度/校正を伴うpopulation simulationに直接近い。|
|[Woven by Toyota](https://woven.toyota/en/)、[Woven City](https://www.woven-city.global/about/)|Arene、AD/ADAS、Woven City、Cloud & AI。Woven Cityは住民/発明者がmobilityを試すLiving Laboratory。Digital Twin求人はphysical cityへ導入する前のvirtual product testと、住民生活/交通/energyのoperational data・simulated resultsに基づくanalyticsを明記。|公式事業/求人が実証対象とデータ接点を説明。今回、一般公開のcomplete Woven City simulation source/modelは確認しない。|純LLM synthetic interviewとは違うphysically grounded digital twin/社会インフラ側。|
|[Parallel.ai](https://parallel.ai)|Web search/extract/monitor/researchのAI向けinfra。|公式トップ/API docsリンクで確認。|同名候補として確認したが、社会/経済simulation製品の一次根拠がないため、直接競合/就職先として水増ししない。別のParallelを指すなら会社特定が必要。|

Primitiveの同一性は公式サイトfooterのLinkedIn `https://www.linkedin.com/company/primitivelabsai` がスクリーンショットのハンドルと一致する点で確認。`primitive.ai` は金融サービスAI operating systemの別会社にredirectされるため採用根拠に使わない。PrimitiveホームにTokyo表記はあるが、確認した求人勤務地はSF/NYでありTokyo募集中と読まない。

## 現在の具体的求人: 実職種を確認できたもの

### Simile: official Ashbyで15掲載、以下はManagerに関連する職種

一次採用入口 [公式→Ashby](https://jobs.ashbyhq.com/simile)、生データ [public posting API](https://api.ashbyhq.com/posting-api/job-board/simile)。下記はすべて `isListed:true`、FullTime、San Francisco、OnSiteで取得。掲載JDのbase salaryは各$200k–400kだが、個別offerは経験等次第。日本remote可/visa sponsorship/副業可の確約は確認していない。

|公開中の実職種とURL|実際の要件/仕事|Managerで示せる成果物と残る差|
|---|---|---|
|[Evaluations — Member of Technical Staff](https://jobs.ashbyhq.com/simile/33d75074-c23b-4a1f-bfdb-129bcc5be662)|Noisy human ground truth、sampling、distributions、calibration、confidence intervals、measurement validity。Python/SQL/R/notebooks/LLM APIs・Codex等で評価toolを作る。rubric/labeling/LLM judge、real purchase/intervention/群行動の評価。recent graduate/self-directed builderも記載。|最も成果物で入口を作りやすい。実人間分布対照、baseline比較、bootstrap CI、bias/failure、判断可能なevaluation dashboard。自然な会話demo単体では不十分。|
|[Evaluations Engineering — MTS](https://jobs.ashbyhq.com/simile/beaa243c-233f-45f2-9e10-8d54e1eda9d1)|数年のproduction software経験、backend/data pipelines/relational models、versioning/provenance/reproducibility/holdout integrity、deployment/adoption、研究者向けinterface。|versioned dataset/schema/run IDs、再実行、release regression gates、labeling UI、source auditを一つの小さなproduction systemとして構築。実務年数と運用実績は別途必要。|
|[Research — MTS](https://jobs.ashbyhq.com/simile/fbf3ed84-26a2-489f-b62f-82f435568387)|Python/modern ML、GPU experiments、large model training/fine-tuning lifecycle、論文再現/批評とtechnical writing、hypothesisからdeploymentまで。CSS/behavioral econ/distributed trainingはnice-to-have。|論文結果を再現し、personas/memory/learningのablationとholdout精度を書く。API orchestrationだけではGPU training経験を代替しない。|
|[Product Engineer — MTS](https://jobs.ashbyhq.com/simile/f4790964-9a97-4378-b3e9-20dfbcfdc5cf)|実務5年以上(インターン除外)、TypeScript/React＋Python/Go/Rust/Node、Postgres/MySQL、distributed systems。千単位agent orchestration/emergence/insightsをenterprise UIに。|Managerのrun/compare/inspect UI、API、queue、relational storage、ownership→deployment。5年条件はportfolioで自動消滅しない。|
|[ML Systems — MTS](https://jobs.ashbyhq.com/simile/9acc73e4-7f77-49dc-b0f6-1a9d26b33b04)|Python/PyTorch/JAX、production ML/distributed systems、GPU/NCCL/RDMA、multi-node training/serving。population-scale inferenceのbatching/scheduling/KV cache/quantization、latencyとcostを研究制約として最適化。|同一population/seedでcost per simulated decision、throughput、p95、cache/batch ablations。小型demoは有用だがmulti-node運用能力まで証明しない。|

### Aaru: official careersに31掲載（技術13、Revenue14、Product2、Recruiting2）

[一覧](https://aaru.com/careers)。NYC、SF、Singaporeを確認。日本の職種は確認していない。

|実職種/勤務地/URL|要件と仕事|Managerとの対応|
|---|---|---|
|[Researcher, Population Simulation — NYC](https://aaru.com/careers/f718d12f-67e9-4fe9-91cc-9e3b69ff00fe)|synthetic generation/ABM/CSS/population simulationの深い経験。real profileからagentを生成、GSS/census/panelとの分布精度。LLM+classical architecture、survey/psychometric grounding。「individual plausibilityとdistributional fidelityを区別」。PhD or research背景の記述あり。|代表性とjoint distribution/crosstabsを検証した人口構築、demographic-prompt baselineと比較。人口規模を増やしただけでは精度証明にならない。|
|[Software Engineer, Simulation — NYC](https://aaru.com/careers/f04cd7a3-b53c-4797-bb8f-ebfe0467e9fe)|3+年ML/AI、production LLM、rigorous experiments、data→training→evaluation→integration。agent/population objects、contracts/interfaces、eval harness、client workflows、速度/費用、decision artifactsを研究から本番に。|Managerのtyped population/world/intervention契約、run orchestration、eval/report API、性能を持つ実装。full lifecycle経験は別途必要。|
|[Researcher, Evaluation — NYC](https://aaru.com/careers/4490a4b7-ad45-4bf6-b00f-190a6d9f41ad)|ML/statistics/behavioral science/product decisionの測定研究。historical backtest、prospective forecast、population coherence、resolved outcome比較。construct/data/study/code/failure/uncertainty/限界を説明し、researchから独立した最終測定を守る。|future outcomesを登録して後から採点するbenchmark、negative resultも記録、backtestとheld-out prospectを分離。|
|[Simulation Architect, APAC — Singapore](https://aaru.com/careers/31eded26-2a69-41d4-af36-10bea19184f8)|7+年consumer insights/market research＋sampling/weighting/quant depth、senior stakeholdersへのmethodology説明。business questionをaudience/stimulus/evaluation standardに変換。POC/representativeness/calibration/confidence/limitationsを顧客と検証。|Managerの技術だけでは足りない。事業の意思決定からstudyを作り、validation record/境界を説明するcase studyが必要。|

NYCの技術3職種はJDに$200k–600k/equityを表示。勤務地・給与だけで副業可能性や日本からの応募可否は分からない。

### Primitive Labs: official本文・応募formがある4職種

[公式一覧](https://primitivelabs.ai/careers)。各個別頁にUS work authorization/visa sponsorshipを質問する公開formがあるが、スポンサーを提供するという確約ではない。

|実職種/勤務地/URL|要件と仕事|Managerとの対応|
|---|---|---|
|[Member of Technical Staff, Founding Engineer — SF/NY Full Time](https://primitivelabs.ai/careers/founding-engineer)|production full-stackをshipした経験、高自律性、agent-native tools/AI SDLC。infra/agent architecture/eval/devtool/productをdesign→production、computational cognitive scienceからarchitecture構築。|Agentを実UIで動かすtest環境、tool trace、memory/decision分離、再現evaluationとfull-stack delivery。|
|[Member of Technical Staff, Research — SF/NY Full Time](https://primitivelabs.ai/careers/research)|agents/ML/simulation/cognitive science研究lead、rigorous experiments、大モデル、production化。memory/continual learning/behavior fidelity benchmarks/human-data training eval、papers/open-source/technical talks。|人間behavior tracesとの比較、memory/personality ablation、behaviour fidelity benchmark、独立再現用研究artifact。|
|[Member of Technical Staff, Intern — SF/NY Internship](https://primitivelabs.ai/careers/mts-intern)|paid internship、potentialを重視し固定年数/skill listを掲げない。agent/eval/infra/applied researchでownership→ship。|学習中の入口候補。US/location制約は要確認。|
|[Designer — Remote / Role Type Other](https://primitivelabs.ai/careers/designer)|個別本文も確認。shipping済みdigital productsのstrong portfolio、interaction/information architecture/edge cases、typography/layout/responsive、hi-fi prototypes、data-rich technical products、engineerとのHTML/CSS連携、accessibility。|エンジニア職がRemoteであるという証拠には使えない。|

### Woven by Toyota: Tokyoで一次求人を確認

公式[careers](https://woven.toyota/en/careers/)の静的HTMLは「No matching roles found」。これは求人不存在の証拠にしない。公開[Lever API](https://api.lever.co/v0/postings/woven-by-toyota?mode=json)に145 records（英日版を含むためunique枠145とは言わない）を確認し、下記個別頁を照合。

|実職種/勤務地/URL|要件と仕事|Managerとの対応/不足|
|---|---|---|
|[Senior Computer Vision/Machine Learning Engineer, Digital Twin Platform — Tokyo / Hybrid](https://jobs.lever.co/woven-by-toyota/d59b0f20-4b3b-49bf-b9a6-600ee7050db0)|Woven City Social Infrastructures & Platforms。virtual test、physical city operational data分析。detection/tracking/classification/activity recognition、industrial perception実装。関連学士＋7年以上CV/MLまたはPhD＋5年以上、PyTorch/TensorFlow、production/technical leadership、camera calibration/3D geometry、英語。PhD/VLM/agentic/flow analysisはnice-to-have。|都市シミュレーションと観測データをつなぐ方向は近いが、今の求人中心は物流/工場CV/ML。Managerだけでは必須のperception/geometry/年数を満たさない。[日本語版](https://jobs.lever.co/woven-by-toyota/c2c2f32a-7732-4cee-a64f-5a937646fcf1)も存在。|
|[Senior Data Engineer, Behavior ML Planning & Prediction — Tokyo](https://jobs.lever.co/woven-by-toyota/ff9b4633-2035-42e0-984f-bf76741788d1)|AD/ADASでfleet/simulationのpetabyte multimodal data→canonical datasets/metrics/tools。7年以上production data pipelines、SQL/Python、BigQuery/Snowflake/Redshift、dbt/Airflow、cross-team technical leadership、英語。日本橋office週3。spatiotemporal/log/trajectory data、Spark/Ray/Parquet/Icebergはnice-to-have。|event log→trusted datasets→analysis/dashboardのarchitectureはManagerで練習可能。自動運転のbehaviorは社会/購買behaviorと同義ではない。|

Woven Cityは裾野市のphysical test course、Tokyoは会社本社/求人勤務地。都市型社会simulationへの関心だけなら組織適合の入口だが、この2職種に必要な専門経験は重い。

## 採用証拠が足りない対象

- **Synthetic Users**: 公式footer「Jobs (not many, mostly agents these days)」が `https://syntheticusers.notion.site` をリンク。ただしHTTPではJS shellのみ。current title/location/requirementを確認できず、**採用入口あり・個別live role未検証**。募集がゼロとは断定しない。
- **Seldon**: 公式Roles→上記joinblok Notion。JS shellのみで職種未検証。**採用入口あり・個別live role未検証**。
- **Tenera**: domain接続不可のため**一次根拠未取得**。採用なしとは言えない。
- **Talent pool**: 今回、named roleのない一般talent poolをlive jobとして数えない。Aaruの「Don't see your role? jobs@aaru.com」はgeneral contactであり実職種枠ではない。連絡は行っていない。

## 実装して見せるManager artifactと実際の採用条件の対応

1. **Population/eval package** — open/許諾済みの実人口調査に対し、demographic-prompt baseline、calibrated profiles、memoryあり/なしを同一holdoutで比較。TVD/MAE、joint/crosstab、bootstrap CI、segment failures、代表性をreportする。対象: Aaru Population/Evaluation、Simile Evaluations。生成の見栄えと予測精度を別々に採点。
2. **Provenance/reproducible runs** — source/license/dataset version、seed/model/prompt/world/agent config、run hash、raw outputs、evaluation split、retry/error/costを保存。CLI再実行＋compare dashboard、質問/同一sampleをsplitで跨がせない。対象: Simile Evaluations Engineering、Aaru Simulation Engineering。
3. **Intervention/world contracts** — agents/population/world/stimulus/outcomeをtyped objectsで分離し、政策/価格/UX変更を同じ条件で対比。LLM responseとbudget/inventory/transaction等のclassical rulesを分離し、モデルの都合で社会ルールを書き換えない。対象: Aaru hybrid simulation、Simile multi-agent product。
4. **Browser behavior fidelity** — controlled local web journeyをPlaywright等で操作、action/observation/decision/memory/abandonment traceを保存。人間の同意済みtask dataに対してOCEAN/memory/context等をablation、task successだけでなくhesitation/choice/path/dropoffを採点。対象: Primitive Research/Founding Engineer、Seldon product機構。公式製品コードを模倣したとの主張は不要。
5. **Scale/performance report** — 100→1,000→10,000 agentsのthroughput/cost/p95/failure、batch/cache/concurrencyの変更を同じevalで比較。精度と価格のtrade-offを記す。対象: Simile ML Systems、Aaru Simulation Engineer。ただし本番multi-GPU clusterを運用したことにはならない。
6. **Decision artifact** — business question→population/stimulus→evaluation standard→result/uncertainty→「どこまで判断できるか」を1枚reportにする。validation recordと不都合な失敗を添える。対象: Aaru APAC Simulation Architect、Simile product/customer仕事。

推薦: 最初は(1)+(2)+(3)を小規模で完走し、「社会をシミュレートできた」よりも「どの行動/分布をどのholdoutでどこまで再現でき、どこで破綻したか」を示す。現行求人ではSimile Evaluationsが学位・年数以外のbuilder入口を明示し、Primitive Internもpotential採用。上位Research/Senior/Product職の経歴条件までManager単体が満たすとは言わない。

## 公開コードの正しい位置づけ

[joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents) はApache-2.0の研究simulation moduleとgame environmentで、原論文の公開実装。memory/reflection/planningを勉強する一次コードとして強いが、**Simileの現行production platform/source/weightsではない**。Simile Research欄の論文系譜と同じ研究者の成果だからといって現在の商用accuracyを引き継ぐわけではない。Aaru/Primitive/Seldon/Synthetic Usersについて公開commercial codeを確認していないことはclosedだという最終証明ではなく、今回の公開資料調査範囲の限界。

## 知財・副業・競業について

上記求人の公開本文だけでは、個人Manager repoの持込み、就業後のside project継続、競合simulation事業、既存IPの除外、公開許可を保証できない。必要なのはoffer/契約時の発明譲渡・守秘・競業/副業条項、既存成果物の明示的schedule、使用機器/勤務時間/データの扱い、公開条件の書面確認。企業の技術領域とManagerが近いほど、独立した個人研究を許容するという推測はしない。この調査では雇用契約を見ていないため各社の許容度は**不明**。
