# Simile一次資料精読メモ（2026-10-11）

調査対象：Manager＝利用者だけでなく、共有環境・制度の影響を受ける非利用者のwellbeingを改善するambient AI。以下は全文ブログ7本、研究論文本文・方法・限界、CVS公開白書を分けて読んだ結果。キャッシュは `/workspace/scratch/manager-research/oct11/simile/`。製品を利用した実測や非公開資料の検証は行っていない。

## 結論

Simileの目的は、人の意思決定に関わる製品・政策・価格・制度変更を、本番前に人間行動シミュレーションで比較できるようにすること。Managerと重なるのは「制度を変えた時、どの人々がどの条件下で何をするか」の予測層である。ただし予測された購買・回答・adoptionはwellbeingそのものではなく、Simileの企業向け顧客指標をManagerの社会的目的にそのまま置き換えることはできない。

現在のSimileは「LLMに架空ペルソナを演じさせるだけ」とは異なる。2026-08-25ブログは、人間の取引、AI音声インタビュー、調査でsimulation modelを訓練することを明記し、モデル図はQwen3.5-27BのSimile fine-tuneを示す。一方、2024/2026個人再現論文の方式はGPT-4oへの実在個人の自己報告の注入であり、同論文の83%等は製品のtrained foundation modelの性能ではない。研究の公開コード・重みとSimileの現行proprietary productは区別すべきである。

## 読んだ資料（タイトル・日付・URL）

日付はブログ一覧で確認。本文ページには掲載日が表示されないものがある。

|資料|日付|URL|
|---|---|---|
|The Simulation Company|2026-02-12|https://www.simile.com/blog/the-simulation-company|
|CVS Health x Simile: Simulations for faster, safer decisions|2026-02-24|https://www.simile.com/blog/simile-cvs-health|
|Simulation: The Next Frontier for AI / Percy Liang|2026-03-10|https://www.simile.com/blog/simulation-next-frontier|
|Announcing Simile’s Series B|2026-07-30|https://www.simile.com/blog/series-b|
|Building confidence in Simile / Andrew Wesel, Sarah Chen, Percy Liang|2026-08-25|https://www.simile.com/blog/confidence|
|Building the What-If Machine / Michael Bernstein|2026-09-02|https://www.simile.com/blog/what-if-machine|
|How Itaú turned five weeks of research into four days|2026-09-11|https://www.simile.com/blog/itau-at-esomar|
|Generative Agents: Interactive Simulacra of Human Behavior|2023-04-07初稿|https://arxiv.org/abs/2304.03442 ; 全文 https://arxiv.org/html/2304.03442|
|LLM Agents Grounded in Self-Reports Enable General-Purpose Simulation of Individuals|v1 2024-11-15、v2 2026-04-22、v3 2026-06-28|https://arxiv.org/abs/2411.10109v3 ; PDF https://arxiv.org/pdf/2411.10109v3|
|Finetuning LLMs for Human Behavior Prediction in Social Science Experiments|EMNLP 2025-11-04〜09|https://aclanthology.org/2025.emnlp-main.1530/ ; PDF同URL末尾.pdf|
|The Flight Simulator for Management: Generative-Agent Simulations for Faster, Safer Decisions|2026白書、本文から正確な公開日未確定|https://www.cvshealth.com/content/dam/enterprise/cvs-enterprise/pdfs/2026/CVS_WhitepaperCVSxSimile.pdf|
|現行ホームページ|2026-10-11閲覧|https://www.simile.com/|

## 現行製品：明示されたpipelineとまだ不明な点

### 人間データから分布予測へ

`confidence` Introductionの直接記述： “we train a model that simulates how an individual or population will act in a particular situation”; 自然言語でpopulation / situation / valid actionsを入力し、action distributionを返す。例：FloridaのDoorDash利用者、August2026、tipを残すか。予測93.4%対観測87.3%、TVD=.0615。

`what-if-machine` の“What we're building at Simile”は、transactions / app usage / clickstreams / mobilityと、surveys / interviews / experimentsを一緒に訓練すると記述。データ収集、同一人物の異なる観測のlinking、実験、populationの継続更新、検証が高価なインフラであるという説明。行動ログはwhat、自己報告はwhyで、say-do gap自体もlearnableと位置づける。ただし、例示されたアイスクリーム乗り換えの「価格変更が習慣を中断し、既知の代替ブランドへ再評価」という機序は説明例で、識別された実験結果ではない。

公開されていない：データ提供者一覧、購入・取得データ量と各モダリティ割合、個人linkingの仕組み、再同意/撤回/非利用者coverage、訓練損失やモデルごとの更新周期、個人とpopulationの表現、長期動態・相互作用を現行foundation modelへ結合する具体実装。一般論として訓練していることは確認できるが、全pipelineを再現可能な仕様はない。

### confidenceは別の学習可能モジュール

同ブログ“Extracting a confidence signal”〜“From a confidence signal to trustworthy decisions”を全文確認。

- 真の誤差＝実人間の結果分布と予測分布のTVD（0一致、1disjoint）。ground truthなしでそのTVDを推定するconfidence modelを学ぶ。
- 評価約8,600問はsimulation modelとconfidence model双方のtraining dataからheld out。confidenceは5-fold CV。質問文と実験sample全体を同じfoldに束ねる。層・learning rate選択もtrain内部validation。
- basic features：選択肢数、entropy、max/kurtosis、prompt length、上位2選択肢gap→回帰。AUROC .566 / RMSE .0992 / Pearson r .122。
- text-embedding-3-large→回帰：.686 / .0843 / .446。
- simulation model hidden-state ridge probe、layerをvalidationで選ぶ：.730 / .0792 / .538。元のforward passを利用し追加model callなし。
- simulation modelをcontinued fine-tuning、LM headをscalar linear headへ交換、RMSE loss：.736 / .0776 / .565。AUROCはprobeとの差が有意でない。
- stock Qwen3.5-27B直接fine-tune：.720 / .0790 / .538。

上記AUROCはTVD<.16分類。confidenceモデルのAUROCをsimulationの正答率として読んではいけない。95% bootstrap CI、隣接法のpaired bootstrap10,000回、グラフ軸は切り詰めあり。

“decision-quality”基準は内部14人、約2,750ratings、410複数採点questions、Fleiss kappa .75。最良F1=.856を与えるTVD=.16をthresholdとした。外部ratersや多様な評価で更新予定と明記。High bucketは評価セットで95%がTVD<.16、Lowは38%。これは「95%の全人間行動を正しく予測」「各選択肢が誤差5%以内」「社会的に安全な政策」という意味ではない。用途ごとの損失に合わせ任意のerror metricを学習できるという最後の記述がManagerに特に重要。

現在のUI表示を支える詳細は公開されるが、8,600問の内容・population構成・個別bucket境界・データ公開・完全な外部検証は不明。特に制度変更後の長期分布shift下で同じcalibrationが維持される証拠は示されない。

## 研究系譜を混同しない

### 2023 Smallville：coherence / believabilityのarchitecture

25の架空agents、2日間のgame time。memory streamは観測・reflection・planを自然言語で保存。retrievalはrecency / importance / relevanceをmin-max正規化して加重和。importanceはLLMの整数score。reflectionは最新イベントimportance合計が150を超えた時、直近100memoryから3つの高次質問を生成し、関連memoryをretrieveして、根拠memory pointer付きinsightを保存（約日に2〜3回）。planningは高次scheduleを細かい行動へ再帰分解、環境や会話でreact/replan。

評価はagentへのinterviewを用いた人間のbelievability判断、memory/reflection/planning ablation、open-ended集団挙動。実人間の選択確率に対するcalibrationの証拠ではない。失敗はmemory retrieval漏れ、memoryの捏造的脚色、LLM由来の形式的すぎる発話など。現行ホームページは“In Simile today”でこれらのideaがstudy内context/coherent behaviorを助けると述べるが、2023公開実装＝2026製品コードという証拠はない。

### 2411.10109の現行v3：実在個人の自己報告grounding

旧タイトル“Generative Agent Simulations of 1,000 People”とhistorical85%をそのまま現行値として使わない。v3新タイトル・abstract・本文を確認。標本1,052米国成人、Bovitz募集、層化quota。英語の約2時間AI音声interview（平均6,491語、SD2,541）、American Voices Projectの既存独立protocol＋adaptive followup。GSS/BFI44/実報酬付き5経済ゲーム/5つのtext social-science experiments、2週間後再回答。

agentはGPT-4o。interview全文またはstructured surveyまたは両方をpromptへ注入。psychologist/behavioral economist/political scientist/demographerの4視点expert reflectionsを生成保存し、prediction時関連専門家reflectionを選びstep-by-step reasoning。個人別fine-tuningはしていない。survey-grounded agentのinputから評価対象GSS問を除き、BFIは対象trait同category全問を除く。さらにinterview/GSS間で意味的に重複するGSS評価問をflag/remove。評価はWave2。

GSS150問、平均3.31選択肢。normalized accuracy＝agentの個人回答一致率÷人間自身の二週間retest一致率。interview-only .83（raw65.67%, human79.53%）、survey-only .82、combined .86、demographics .74、persona .71。interview対survey差非有意p=.16、combinedの上積みは有意だが小さい。従って「interviewが唯一不可欠」「83%がabsolute accuracy」は誤り。

Big5 normalized correlation：interview .80、survey .65、combined .77。経済ゲーム：.66/.38/.49対demographic .48/persona .57、5agent群全体p=.16、pairwise有意差なし。ゲームは自己報告groundingが明確に助ける領域ではなくboundary case。survey/GSS以外へ83/86を横展開しない。

限界（Discussion本文）：個人回答一致はpopulation全体のattitude間covariance再現を保証しない。5実験のeffect-size相関はsuggestiveだが平均treatment-effect予測への強い結論にはunderpowered。OpenAI単一model familyでopen-weightへの移植未確認、全て英語・米国。標本は高校未卒2.3%対target10.6%、女性56.4%対50.9%、民主党35.3%対27%、Midwest過大/South過少。実在個人groundingでも「社会全体representative」の無条件保証ではない。

### 2025 Socrates：human-response trainingの公開研究

ACL最終PDFを確認（Scholarのabstractには36%/15%という別値が残るが、本レポートはACL PDF26%/13%を採用）。SocSci210＝TESS公開210研究、400,491participants、2.9M responses、1,194conditions、1,197outcomes、5,998unique stimuli。o4-mini-high data reconstruction agentが元studyをpersona(demographics)/condition/outcome/responseへ統一。ordinal/binaryに限定。

Llama3-8B-Instruct/Qwen2.5-14B-InstructをSFT、GPT-4o-mini oracle reasoning trace付きSFT、contrastive DPOで比較。oracle reasoningは実回答を与えて説明を生成したものなので、観測された心理理由ではない。SFTは分布alignmentに良く、DPOは個人回答accuracyに良い。分布評価はTVDでなく[0,1]に標準化したWasserstein distance、condition-outcome→study→studiesで平均。

unseen-study評価170train/40test研究。Socrates-Qwen14BはWasserstein errorがbaseから26.3%改善、GPT4oから13.2%改善。Llamaは30.1%/12.1%。“26%より人間っぽい”や“26point正答率改善”ではない。71%は同研究のsubset conditionsで訓練してunseen conditionsへ一般化する設定、完全な未知研究設定の値ではない。49%はunseen outcomes。10.6%demographic disparity改善も特定指標・datasetでの相対値。

data/model/fine-tuning code公開先 https://stanfordhci.github.io/socrates 。これは学術Socratesであり、現在のSimile proprietary foundation/confidence modelsの公開ではない。

## 企業事例の数字の読み方

Itaúブログ：Pix Automático、customer archetypesに基づくsimulated population、workshopで7仮説。五週間→四business days、二週間のconcept exploration→三時間未満。これは研究processの速度。独立の実測accuracyやwellbeing効果ではない。high confidenceとrepresentationを見てweightを決め、低confidenceは直接研究へ回し、質問framing/解釈/最終決定は人間researchersが担う。

CVSブログ2.9M/400k/200+は学術SocSci210の規模とほぼ同じ。全員がCVS患者として新たにinterviewされた独自患者panel、と読む根拠はない。白書p6はvalidationがpublished Simile research/academic collaborations由来、CVSの貢献はapplication/deploymentと明示。p7はfirst-party historical survey/CRM/support/A-B resultsでcalibrate、内部既知結果とのagreement“up to95%”。分母・study数・agreement定義・CIなし、最高値で一般accuracy保証ではない。白書p7の85%はhistorical個人研究、effect pattern correlation>.9は小数の実験であって全政策予測の90%accuracyではない。

白書はstatic individual→journeys→interaction→marketの段階的導入。p18confidenceはlog-probabilities+historical backtest等と述べるが、August25のlearned hidden-state/CFTモデルと同一版と断定しない。current product evolves。高stakesではlive studiesがarbiter、stageごとにgovern/validateするとの記述。

## Managerで学べる具体モジュールと条件

1. 人々の“what”と“why”を分けず、行動ログ・制約・生活史・態度・小規模実験を結び、架空personaのもっともらしさをtruthと扱わない。非利用者、介護者、少数集団、制度から脱落する人をpopulation設計に明示。
2. 結果は一点の推奨ではなくaction/outcome分布、group別影響、反実仮想候補比較へ。wellbeing、自由・負担・公平性を外部outcomeとして測り、購入や回答意図で代替しない。
3. learned error predictorを独立moduleにし、confidenceの低いqueryを実測・住民参加へroute。TVD=.16という企業内部一般thresholdをManagerへコピーせず、重い少数者損失を反映するmetricとexternal ratingsで校正。
4. memory/reflection/planningを長期coherenceのscaffoldとして使う。ただしcoherenceとreal-world fidelityを別々に評価し、reflectionは推論であって本人証言と区別。
5. validationをindividual一致、population分布、attitude covariance、treatment effect、dynamic/network effects、group disparity、長期wellbeingに分解する。static回答の良さから制度のfeedback loopを推定しない。
6. 実施前のhypothesis screeningとして使い、現場pilotで残った不確実性を潰す。制度変更の因果推論には介入識別、交絡対策、干渉・spillover、適応・distribution shiftの検証が別途必要。

Simileの“any situation, any scale”“eight billion over a year”“trillions of interacting decisions”“complete auditable trace”は方向性・研究challengeを含む記述。公開資料から全世界・任意の制度・長期非利用者wellbeingまでvalidation済みと認定できない。一方、2026confidenceブログは訓練データ・fold・metric・学習方法・限界を具体的に開示し、単なるpersona promptingから学べる技術進歩が明確にある。
