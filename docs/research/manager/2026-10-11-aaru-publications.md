# Aaru一次資料調査 — 2026-10-11

## 結論

Aaruは「LLMに人格を演じさせる会社」と整理すると誤る。2026-09-24の方法記事では、**人口生成モデルも、個人の行動軌跡を予測する中核モデルもlanguage modelではない**と明記する。公開／ライセンス／顧客データから人口の共同分布を学び、完全なプロフィールを標本化し、個人と集計の両水準で行動予測を実世界の結果に合わせる、という公開説明がある。ただしアルゴリズム、損失関数、ネットワーク種別、モデル重み、訓練データの全容は公開されていない。Bayesian network、GNN、SCMなどの特定技術と断言できない。

Managerにとって最も有用なのは「人間を大量に会話させる実装」より、**対象人口・実在する制約・観測結果・予測誤差を結びつけた意思決定前の検査方法**である。公開成果は単変量の回答分布と購買ブランド順位に限定される。制度変更が非利用者の身体・精神・経済wellbeingを改善する因果効果、物理的供給制約、社会的相互作用の長期ダイナミクスは、この成果から立証されない。

## 取得範囲と出典

2026-10-11に各URLの本文を新規取得。最初のhttps://aaru.com/publicationsは403だったが、www版、末尾スラッシュ版、実際の記事URLでは200となった。キャッシュは `/workspace/scratch/manager-research/oct11/aaru/`。HTML・本文・PDF・JSONを保存した。過去キャッシュからの推測で補っていない。

**Publication indexには1本のみ**掲載されていた。以下のsummaryとresearchは同一研究の短縮版と方法版であり、独立した2本の研究ではない。「Aaruの複数論文を読んだ」と数を水増ししない。関連文献はAaru記事の実リンクから読んだ。

|資料|日付・種類|URL／ローカルキャッシュ|
|---|---|---|
|Publications|取得2026-10-11、一覧|https://aaru.com/publications （取得成功https://www.aaru.com/publications）、0.html/0.txt|
|Population simulation at the replication floor|2026-09-24、By Aaru、summary、9 min read|https://aaru.com/publications/population-simulation-at-the-replication-floor-summary 、summary.html/summary.txt|
|Population simulation at the replication floor|2026-09-24、By Aaru、research、24 min read|https://aaru.com/publications/population-simulation-at-the-replication-floor-research 、4.html/4.txt|
|How a simulation works. From start to finish.|公開日記載なし、製品説明|https://aaru.com/simulation 、simulation.html/simulation.txt|
|About Aaru|公開日記載なし、企業説明|https://aaru.com/about 、about.html/about.txt|
|Scenario Planning|公開日記載なし、用途説明|https://aaru.com/use-cases/scenario-planning 、scenario.html/scenario.txt|
|Aaru’s calculation and sources|日付記載なし、比較計算のJSON|https://aaru.com/data/population-simulation/confidence-comparison.json 、confidence-data.html（内容はJSON）|
|Building confidence in Simile|Andrew Wesel, Sarah Chen, Percy Liang、本文に正確な公開日を確認できず|https://www.simile.com/blog/confidence 、simile-confidence.html/simile-confidence.txt|
|SimBench: Benchmarking the Ability of Large Language Models to Simulate Human Behaviors|Huほか、arXiv v4、2026-04-13|https://arxiv.org/html/2510.17516v4 、simbench.html/simbench.txt|
|SYN-DIGITS: A Synthetic Control Framework for Calibrated Digital Twin Simulation|Fanほか、This version April 8, 2026|https://arxiv.org/html/2604.07513v1 、syndigits.html/syndigits.txt|
|Language Model Fine-Tuning on Scaled Survey Data for Predicting Distributions of Public Opinions|Suhほか、arXiv v2、2026-04-16|https://arxiv.org/html/2502.16761v2 、subpop.html/subpop.txt|
|Finetuning LLMs for Human Behavior Prediction in Social Science Experiments|Kolluriほか、EMNLP2025、2025-11-04–09会議|https://aclanthology.org/2025.emnlp-main.1530/ 、socrates.pdf/socrates-full.txt|
|Benchmarking Distributional Alignment of Large Language Models|Meister, Guestrin, Hashimoto、NAACL2025、2025-04-29–05-04会議|https://aclanthology.org/2025.naacl-long.2/ 、distributional.pdf/distributional-full.txt|

Aaru方法版／要約版、製品パイプライン、Simile confidenceは本文全体を読み、関連論文は本文の方法・評価・限界と該当表を確認した。掲載ページの会議期間は公開日と同一とは限らない。論文の将来版を勝手に仮定していない。

## Aaruの目的と製品の実像

創業の問いは「現実世界の規模・複雑さで人間行動をsimulationできるか」。目標は製品、価格、政策、メッセージを実行前に試すこと。顧客向け用途はproduct innovation、marketing/brand、audience segmentation、scenario planning、strategic communications。非利用者のwellbeingを明示的な最適化目的にするManagerとは目的関数が異なる。

Aboutでは、実人口のdemographic／behavioral／outcomes dataでAI agent人口をgroundingする、と述べる。倫理原則には「Do good」「人や制度を以前よりよくする」「善意だけでは不十分、結果と不可避なコストを検討する」がある。ただしこれが身体・精神・経済wellbeingの測定モデルや実証評価であるとは書かれていない。

### 公開された7段階

1. **Objectives**：選択肢、成功の意味、制約を定義。
2. **Audiences**：所得、子供、購買頻度などhard parameterと行動記述で対象集団を指定。
3. **Questions**：single choice、multiple select、ranking、free response、matrix、stimuli、hypothetical、branching logic等。
4. **Data**：public data（census、labor、health、prices、place等）、private/licensed data（匿名取引、POI訪問、search demand、media、hiring等）、customer context（履歴、segment、campaign、研究、製品、operating constraints等）を統合。地理粒度・更新頻度の不一致を調整し、信号の一致と不一致を評価。全情報を平滑化して欠損を隠すのではなく、coverage／bias／cadenceの制約を残すという説明。
5. **Structure**：独立列ではなく共同分布。Age×Sex×Economic activityの3次関係など、1次・2次marginだけでは守れない構造を説明。数百traitの候補相互作用からfitに影響する関係を選び、learned networkを作る。そのnetworkからconsistentな完全profileを標本化。source recordのコピーや完成済みagent表の保存とは説明されていない。
6. **Simulation／training**：individual effectsとpopulation distributionを同時に観測結果へ合わせる。新価格／政策等へ保持された関係を適用。歴史へのfitは持続性や交絡除去の証明にならない、と製品ページ自身が注意。結果はデータと仮定に条件付き。
7. **Artifacts**：question/audienceごとのinteractive結果、microdata、crosstab、sheet/deck/PDF export。図示された3 audiences×10,000 agents、30,000 agents等はUI例であり、公開評価の全問題に同じagent数が使われた根拠ではない。

公開資料はnamed personの次行動予測を否定し、人口の可能な行動分布を推定すると説明する。人口代理を実在個人のdigital twinと混同しない。

## 2026-09-24研究：何を検証したか

### Survey validation

- 186 studies、9 industries、2,993 questions、13,727 answer shares。Experiences1156、attitudes806、intentions560、expectations471。
- 質問文、選択肢、audience descriptionが入力。agentごと一行のmicrodataが出力。
- 評価問題と公表回答はsimulation／confidence predictorの開発・tuningには使わなかった、という著者申告。
- 2026年fieldedの研究を選択。Exaのみを外部retrievalに使用し、各configurationの最も早いfieldwork開始日の少なくとも前日までに保存されたページへ制限。source publisher domainとprediction-marketを検索から除外。
- productionで使うカード取引、foot traffic、social media、SKU salesなどのconfidential sourceと収集処理の一部はこの評価から除外。したがってproduction同一条件の検証ではない。非LLM中核でも、システム全体の全訓練資料と全経路の漏洩を独立監査した証明までは公開されていない。

|Metric|平均|中央値|解釈|
|---|---:|---:|---|
|Observed MAE|3.53 percentage points|2.73|回答shareの平均絶対差|
|Observed TVD|7.62 points|6.00|全分布の移動量|
|Sample-adjusted MAE|2.78|2.00|下記sampling referenceを引いた値|
|Sample-adjusted TVD|5.98|4.30|同上|
|Pooled Pearson r|0.970|—|13,727 sharesをpool|
|Pooled Spearman rho|0.963|—|share rankのpool|
|Normalized Wasserstein|0.0375|0.0259|完全なordered scaleの733問のみ|

個別問題の平均Spearman0.90、中央値0.99、modal accuracy87.5%。少なくとも90%の問題がobserved TVD16以下。**r=0.97は97% accuracyではない**。全問toplineの良さも、agentの正確さ、低所得などのsubgroup fit、crosstab coherenceを保証しない。

sampling adjustmentはshare pとnについて `b=100*sqrt(2*p*(1-p)/(pi*n))` のexpected absolute sampling errorを直接引く。MAEは選択肢ごとbの平均、TVDはb合計の半分。2,648問はprinted sample size、345問はmedian1441.5を補完。design effect=1、weighting/clusteringでeffective nを減らさない。負のadjusted errorも残す。これは仮定付きの解釈referenceであり、個別問題の誤差bound、latent真値の不偏推定、survey noiseの厳密な除去を立証する計算ではない。Managerではraw metricも必ず併記し、survey sourceごとのeffective nや非sampling biasを別管理すべき。

### 「Replication floor」の意味

Callegaroほかの4つの非確率US sample、約1500人／wave、2週間間隔の5 attitude questionsから計算したTVDは2.3–12.0。RedmilesほかのMTurk privacy/security、14か月間隔、26binary itemsから約2.6。Tangほかでは2019 Pewと2022 Prolific／MTurk間が13–29。Aaru平均7.62はこの幅の中に入るが、同一問題・同一population・同一時期のsurvey再測定とのhead-to-headではない。「人間と同等」の普遍的証明ではなく、異質なrepeat survey研究をreferenceにした比較。

### Baselinesと文献比較

同じrandom500問でdirect elicitation Kimi K3 TVD12.4、gpt-oss-120b21.6。Kimiの>16失敗27.6%対Aaru9.2%、>25失敗7.6%対2.6%。別の非random complex500問ではAaru7.43、Kimi16.5、gpt-oss24.7。baselineは1call、retrievalなし、toplineのみで、Aaruのdata/retrieval/system architectureとresourceを揃えた比較ではない。公開baseline結果は有用だが、LLM全般や全方法より優れるとは言えない。

SimBench19.1、Meister14.6、SYN-DIGITS17.1とAaru7.62の48–60%差、SubPOP WD0.094/0.096やSOCRATES0.151との比較は**different datasets／populations／tasks**。Aaruもこの不一致を記している。same-benchmark leaderboardでない。SOCRATESの別条件学習＋reasoning0.063も併記する誠実さはある。

### Actual purchase validation

カードpanelのpurchase records／1000active-card-daysをcategory×period内で順位化。100brand-period observations、14groups、340brand pairs。surveyはYouGov BrandIndexのconsideration。Aaruはpurchaseについて質問し、3runsの予測を平均して順位化。

- Aaru一致92.4%（individual runs91.5/91.8/92.9）、consideration77.8%。差14.6pp、95%CI7.2–23.0。
- brand-size baseline79.3%だが333pairs／99observations。
- 「66% fewer errors」は22.2%から7.6%への**順位誤り**削減。購買量、売上、個人購入、介入の効果の66%改善ではない。
- pairsは同じbrand/groupを共有し独立でない。本文のCIだけから独立pair bootstrap等の詳細を断定しない。
- surveyがintent、Aaruがpurchaseを予測するのでtaskの差も含む。card panelのcoverage／representativenessは全社会と同一ではない。現金取引や特定層の欠測、非利用者を含むManagerでは重要。
- survey評価ほど詳細なpurchase独立holdout・時間cutoff・licensed dataの入出力分離が本文から再現できない。見ていないground truthを正確に因果予測したとの追加主張を置かない。

### Error prediction／calibration

各問にpredicted TVDと10/16等閾値超過probabilityを返す。roughly半分＝1525問（51%）をretainするとmean TVD4.54、>16は1.0%。全体7.62／9.5%から減るが、同じ予測を選別したもので全予測自体を改善したわけではない。

predicted vs realized error：Pearson0.595、Spearman0.666、RMSE5.32points。AUROCは>16を区別する定義で0.848、Simile comparisonのbelow16 vs at least16で0.845（ちょうど16の19問をどちらへ入れるかが違う）。JSONの実値0.844920891566443で確認。

Simile best0.736との「41% lower ranking error」は1-AUROCの相対差。Aaru2993問のretrospectiveとSimile約8600問5foldを異datasetで比較。確率のcalibrationそのもの、individual outcome prediction、safety probabilityを表す数字ではない。

特に最上位2decilesはpredicted error9.6/13.0に対しobserved12.0/14.6で過小見積り。平均のmonotone関係はよいが、高誤差側では楽観的。Managerの重大な制度介入ではreliability plot、tail error、OOD、coverageと選別後populationの偏りも必要。

## リンクされた研究から実際に学べるもの

### Simile confidence

本文は訓練データをtransaction、AI voice interviews、surveysと説明。confidence modelは結果を知らずにsimulation errorを予測する。約8600production-representative questions、simulationとconfidence両方のtrainingからheld out。5foldで同じquestion textとentire experimental sampleを同じfoldへ固定し、内部train/validationでmodel selection。

basic features regression（options、entropy、max、kurtosis、prompt length、top-two gap）→embedding regression→hidden-state ridge probe→simulation model continued fine-tune→general model fine-tuneの比較。probeはfold内のvalidationでlayer選択。Aaruより方法を具体的に開示。小さなManagerでも、まず歴史holdoutの残差とcheap confidence featuresを用いた選別を学べる。Aaruのconfidence architectureがこれと同じとは言わない。

### SYN-DIGITS

model-agnosticなpost-hoc calibration。humanとdigital twinのresponse matricesのlatent structureを結び、new questionsではrow-space inclusion、new usersではcolumn-space inclusionを条件として誤差を分解。Ridge／Lasso／elastic net等のfit-and-transferとmatrix completion、constrained synthetic control等10methods、13persona constructions、複数backboneを比較。

distribution calibrationはpersona twinsのweighted ensembleにdummy twinsを加えて欠けるresponse supportを確保。OpinionQAは1498問から5option Likert489問へ限定、Twin-2K-500の2058twinsをGPT-4.1-mini temperature0で回答させる。重みはmirror descent／simplexでfit。reference latent spanから外れると劣化するためadaptive transfer diagnosticを提案。structured numerical responseのみ、free textとdomain間transferは未解決。synthetic-controlに着想を得ても、wellbeing介入の因果効果が自動で識別されるわけではない。公開code/data https://github.com/yw3453/syn-digits は学習対象になる（今回コード実行せず）。

### SubPOP

3,362questions／70K subpopulation-response pairsを用い、人間response distributionへ直接fine-tune。ATPをtrain、OpinionQAと別family GSSをtestし、unseen survey topics／waves／subpopulationsを評価。persona promptだけではvarianceやunderrepresented populationを誤ることが動機。Managerへの教訓はLLMのもっともらしいagentではなく、group outcome distributionを目的に合わせて評価すること。公開code https://github.com/JosephJeesungSuh/subpop 。日本の制度・アクセス障壁への一般化は別途評価が必要。

### SOCRATES

SocSci210はTESSの210社会科学実験、400491participants、2.9million responses、1194conditions、1197outcomes。demographic profile＋experimental condition＋question→individual responseを学習。170studies train／40unseen studies testを分け、within-studyのunseen participants／conditions／outcomesを別評価。Qwen2.5-14B SFTの完全unseen-study WD0.151、条件の一部を学ぶ別settingでreasoning付き0.063。Aaruの単変量survey比較より介入条件の表現が明確だが、実験のresponseと長期の実生活wellbeingは別。データ・models・finetuning codeを公開：https://stanfordhci.github.io/socrates 。低コストで設計と評価を読む価値がある。

### SimBench／Meister

SimBenchは20datasets、人口全体とdemographic groupでmultiple-choice single-turn分布を比較。Claude3.7SonnetのTVD0.191は表10に実在。モデルsizeとknowledge reasoningの改善はsimulation改善と関係するが、test-time reasoning増量が一律改善を生まない。instruction tuningでconsensusは改善しpluralityが縮むtradeoff。dynamic social interaction、longitudinal adaptation、embodimentは未測定。Managerでnon-user subgroupを主対象にするとaggregateだけの合格が危険。

Meister論文はquestion domain／steering／distribution expressionを切り分け、JSONでdistributionを直接述べるほうがpersona samplingやlog-probより合う場合を示す。従って「microdataを生成できる」だけでdistributionが正しいとはいえず、逆にtopline直接推定の良さだけでconsistent個人を得られるわけでもない。

## 商用claimと公開証拠を分ける

|商用ページの説明|公開研究で確認できる範囲|残るギャップ|
|---|---|---|
|全世界の難アクセス人口をground-truth trainingで表現|9industryのsurvey distributions|地域別・niche別のjoint／OOD accuracy|
|高次trait jointをlearned networkで保持|architecture narrative|network algorithm、heldout joint tables、個人coherence scores|
|顧客・employee・policymaker・competitorのsecond-order effects|scenario planningの製品説明とillustrative scenario|interaction mechanism、real intervention validation、equilibrium stability|
|intervention evidenceがあればdirection/sizeを検証|internal／engagement validation手続の説明|その介入dataset・effect error・結果の公開|
|EY2025Global Wealth Studyのblind replication、3600富裕層・30以上markets、median Spearman0.90、1day|simulationページ掲載のcase claim|元case studyを本調査で取得・精査していない。独立検証とは扱わない|
|preferences／microdata／crosstabsを提供|出力formatは説明あり|研究本文はhigher-order accuracy／logical row coherenceをfuture postsに明確に延期|

## Managerへ持ち帰る設計 — Aaru模倣ではなく測定可能な改善へ

1. **Decision specification**：供給・アクセス・制度の選択肢、対象人口、時間horizon、hard constraint、成功基準を明示。利用登録者だけでなく非利用者、現金生活者、交通弱者、介護者、低所得等をsampling frameへ入れる。
2. **Evidence registry**：人口・所得・健康・訪問・施設capacity等にsource/time/geography/coverage/bias/permissionを付ける。欠損をagentの物語で埋めず、不確実性として出力する。
3. **Joint population generator**：個人、世帯、雇用、移動、ケアの相関を保持。1way、2way、重要3wayのheldout tablesを検証。Aaruが使う特定algorithmは取得できないので、Managerは公開の人口合成と統計モデルから選ぶ。
4. **Physical institutional layer**：営業時間、在庫、交通距離、待ち行列、staff、capacity、予算、eligibilityを明示モデルにする。需要の反応だけでは不十分。制度を変えた結果のsupply responseとspilloverを区別。
5. **Behavioral kernelとcalibration**：initialは解釈可能なdiscrete-choice／transition／queue modelと実測値で十分。LLMは文書から条件を抽出・説明できるが、unvalidated personaを数値ground truthにしない。SYN-DIGITS等からheldout校正・OOD検査を借りる。
6. **Separate confidence**：予測値と予測誤差を別学習し、coverage-risk curve、subgroup residual、tail、driftを可視化。低confidenceは候補案の優先検証や追加データ収集に回す。棄却により脆弱集団が消えるなら公平な改善判断ではない。
7. **Wellbeing objective**：購買／click／stated preferenceを代理として終えない。身体＝健康・安全・睡眠・治療アクセス、精神＝validated distress／loneliness等、経済＝可処分資金・所得変動・債務・アクセス費。関係者と尺度を定義し、同意とprivacyの範囲で行政／施設aggregate、実測行動、少量human validationを組み合わせる。観測できないnon-user outcomeを「改善した」と表示しない。
8. **Causal verification loop**：simulationで候補をscreenし、pilot／natural experiment／randomized or staggered rollout等でreal outcomesを測る。confounding、interference、time lag、selectionを扱い、推定effectとCI・副作用を記録し更新する。wellbeing改善の証拠はこの段階で得る。

### 再利用可能性

Aaru本体は商用proprietary serviceとしてlogin/contact経由。閲覧したページに公開weights、SDK／API仕様、self-host implementation、full dataset、公開価格を確認していない。存在しないと全世界について断言するのでなく「今回の公開資料では未確認」と扱う。公開HTMLにinteractive chart dataはあるが、それを原システムの再現コードと呼べない。顧客licensed evidenceも自由再配布可能とは限らない。

Managerの初期投資はAaru導入／巨大LLM人口より、**限定された一地域・一制度の、人口合成＋物理制約＋historical holdout＋real intervention outcome**を通すほうが学習が濃い。Aaruは候補の反応を測る強い参考例であり、wellbeingを実現する供給設計・因果検証・持続的実行の全体像を代替しない。
