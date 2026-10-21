# Artificial Societies / Radiant: primary-source technical due diligence (JA)

**調査日:** 2026-10-21 (JST) · **対象:** https://societies.ai/radiant · **区分:** 企業の自己申告 / 査読論文 / 2026プレプリントを別々に評価。

## 先に要約

Artificial Societiesはロンドンの企業、Radiantはその研究用製品。目的は人間に高コスト・機密・時間制約のある質問をする前に、実際の公開・匿名化情報から推定された信念体系を持つAIペルソナの集団を作り、シナリオへの反応を試し、定量調査と討論を行うこと。主な対象例はFortune 500幹部、国会議員、機関投資家、消費者。**これらの肩書きを持つ実在者がRadientの画面で回答したことを意味しない。**

**Managerとの差**は現在の公開された成果と目標であり、優劣の断言ではない。Artificial Societiesが予測・反実仮想・実測パネル比較をしていない、と主張するのは誤り。Radiantの公開主要ユースケースは**人間の意見・メッセージへの反応を予測する意思決定前リサーチ**。Managerの将来目標は、合法的な権限下で公共の環境を改善し、独立した現実世界の純便益を計測する自律ループ。**Manager自身の独立した実世界便益はまだ未実証**。両社の違いは仮説と現時点で確認できる製品の違いであって、独占的差別化が証明済みではない。

## 1. Radiantの利用者向けフロー

1. **Societies:** 事前に集めた実世界の観測、個人の信念推定、社会的ネットワークに基づく人工社会。製品の図は2D/3D、属性・セクター絞込に対応。元の製品ページでは1社会20–3,500人、技術説明/evalでは12–3,500人と不一致あり。サイトの複数ページでは1プロジェクト5社会までとの記述。
2. **Surveys:** 複数選択、単一選択、自由回答などを社会全体に提示し、回答割合、セグメントごとのcrosstab、回答理由を表示。製品ページの38%/31%/19%/12%のIT課金方式は**公開デモ画面のシミュレーション結果**であり、独立に集計された現実の人間調査結果と取り違えない。
3. **Interviews:** ひとりのペルソナの回答を追跡して「なぜ」を尋ね、続けて条件変更や購入停止理由を探る。自然言語の説明は生成された理由であって、実人間の心理機構を直接観測したことにはならない。
4. **Focus Groups:** 複数ペルソナが相互に議論し、意見を変える設定。誰が誰に話したか、発言割合、対立構造、議論後の結論を可視化。**ネットワークを組んでいるだけでは、現実の説得効果・社会的伝播速度が正しいとは言えない**。
5. **Research Assistant:** 調査・会話・討論結果を横断して可視化とレポート要約。出力の監査には元のシミュレーションログとデータ系列が必要。

出典: https://societies.ai/radiant （当日の公開ページで確認）。

## 2. 公表している技術の流れ

**A. Data sources → B. Persona Genesis → C. Society Assembly → D. Simulation Engine → E. Evaluation/UI**。

- A: オンライン発言、レビュー、公開投票情報、企業・投資家の行動情報、公開研究等。顧客固有のfirst-party dataを任意追加できると説明。独自データは案件ごとに分離しEU内保存、学習には使用しない、というプライバシー説明は**企業の主張**。実際の同意範囲・削除・再識別防止は公開ページだけから独立監査できない。
- B: Behavioral Analysis Engineとpsychometricsで信念・態度の関係を推定、過去行動とオーディエンス基準に対して妥当性評価を行う、と説明。内部モデルの重み・具体的訓練アルゴリズムは商用独自であり公開コードとして確認できず、推測して記述しない。
- C: 類似性、現実の関係、影響情報でネットワークを組成し、社会的影響をモデル化。これは独立した単一のLLM回答より複雑。ネットワークが実世界とどこまで一致するかは別の評価軸。
- D: 提案する価格・メッセージ・政治声明・製品条件を「刺激」として与え、各ペルソナ・セグメント・人口平均の反応を予測。疑似世界中のwhat-if比較は現実世界で変更が実行されたことではない。
- E: 総割合以外に参加者別説明、サブグループ、相互作用、実人間ベンチマークや不確実性を比較。ただしモデルの見かけの説明は真の内部理由の証明ではない。

原典: https://societies.ai/eval / https://societies.ai/knowledge/the-science-behind-artificial-societies / https://societies.ai/solutions

## 3. 学術的な関連性と方法論の証拠レベル

### 3.1 初期社会シミュレーションの査読論文（2024 online）

He, Wallis, Gvirtz & Rathje, *Artificial intelligence chatbots mimic human collective behaviour*, British Journal of Psychology; DOI https://doi.org/10.1111/bjop.12764 。

33,299のLLMチャットボットを用いた模擬オンライン社会で、言語別のコミュニティ形成（英語中心17,746におけるコンテンツの類似性によるクラスタ）を報告。**homophilyという集団レベルの一特徴**の再現であり、実社会すべてを正確に予測したわけでも商用Radiantのsurvey精度の査読証明でもない。これは「人間の回答を予測する精度」の外部検証とは異なる。

### 3.2 2026年9月プレプリント: 11テスト

Chidichimo et al., *Artificial Societies Benchmark: A Validation Framework for Synthetic Research*, arXiv:2609.30030v2 (2026-10-01) https://arxiv.org/html/2609.30030

9つのLLMと20の人間データソースを比較する11テストを整理（プレプリント、独立した査読完了とは限らない）：

- **Internal validity:** IV-1 同じ質問の再回答、IV-2 論理的に関連した質問、IV-3 言い換え、IV-4 調査の構成変更。
- **Construct validity:** CV-1 尺度項目の共分散、CV-2 別に測った外部基準、CV-3 異なる心理構成概念の弁別。
- **External validity:** EV-1 回答分布、EV-2 集団別／個人別、EV-3 原実験の処置効果、EV-4 潜在的尺度構造。

元論文は、人口平均が合うだけで実験効果・サブグループ・個人を復元したとは限らないことを強調。これはManagerのCausal Gateにとって重要。

関連プレプリント: *Consequential Behaviour and Representational Fairness in the Validation of Synthetic Research*, arXiv:2609.27690 https://arxiv.org/abs/2609.27690 。本人たちの「意図 vs 実行行動」ギャップ、脆弱集団での誤差、介入による効果差の妥当性を検討する方向はManagerに近い。元研究の有効性を自動的に証明するものではない。

### 3.3 内部パネル評価（2026年1月、企業主張）

*Artificial Societies Survey Evaluation Report (Jan 2026)*（公式/eval掲載）。

| 項目 | Artificial Societies | 対照 | 解釈 |
|---|---:|---:|---|
| 回答分布の重なり | 86% | 伝記プロンプト67%; 人間自身の再回答91% | 設定した調査の回答比率をどの程度合わせたか |
| 自己矛盾率（同社表記Hallucination） | <2% | 人間パネル約9%; generic LLM最大35% | **外部世界の事実誤認率ではない** |
| Internal coherence | 89% | 人間範囲60–95% | 構成尺度の内部一貫性の近似 |
| Open-response quality | 93% | 人間ソーシャル投稿91%; LLM61% | 語彙の多様性等であって心理的真実性の判定ではない |

独自の1,000実人間調査を参照する内部結果。会社の研究であり、独立再現した値とは主張しない。「86%の人間行動予測精度」ではなく、**回答分布重なり86%**。

### 3.4 2026年10月1日のベンチマーク評価（同社主張）

https://societies.ai/as-benchmark : 2,796のプロフィールによる68,280の回答を、7つの実人間調査ソースに突き合わせ、9つのoff-the-shelf LLMとも比較したと報告。全モデル同じ質問・プロフィール・採点コードと説明。

| 評価対象 | AS | ベスト比較モデル | 備考 |
|---|---:|---:|---|
| 全体回答分布平均TVD | 0.08 | 0.31 | 小さいほど良い |
| GSS等のグループ別TVD | 0.063 | 0.222 | 分布の部分集団差 |
| 質問言い換え効果誤差 | 1.4 percentage points | 6.2 pp | Albertson実験 |
| 意見の分散差 | 0.006 | 0.091 | 会社の指標 |

**TVDは 0–1 の確率分布距離**であり、これらの値は「効果量」でも「85%の購入予測」でもない。数値は自己評価ページ由来で、元の評価コード・学習漏洩防止・ライセンス、様々な未知集団での第三者再現は追加検証を要する。サンプル選択、代表性、感度、処置の真の実世界影響はこれだけでは確認できない。

## 4. 公開事例の正しい読み方

- **Teneoの技術戦略ナラティブ:** 6つのメッセージ選択肢を評価し189,756件の**シミュレーション回答**を生成、エンゲージメントは3週間未満と記述。回答数=実際に面接した人間の数ではない。[原事例](https://societies.ai/case-studies/teneo)。
- **大規模企業のearnings call:** 未公開の決算文言や投資家の予想質問をシミュレーションし、実際の質疑と一定のパターンが似ていたと説明。発表後に一致したことは有用な観測だが、独立に盲検化した予測精度指標や万能性の証明とは分ける。[原事例](https://societies.ai/case-studies/hyperscaler-earnings-call)。
- **危機対応:** 1,174ペルソナ・5社会・24種類の表現をシミュレーションしたと記載。実際の評判・購買増加がその介入で生じたとの独立実験ではない。[原事例](https://societies.ai/case-studies/crisis-simulation)。
- **米国テクノロジー企業価格設定**（Radiant表示）: per ticket 38%、seat 31%、hour 19%、annual 12%は製品内デモなので、母集団を特定した現実測定ではない。

## 5. Manager研究への統合—再実装しない部分と補う部分

**Borrow the science, not the marketing.**

- 人間観測と単純なLLM人物設定を分ける
- 人口平均/サブグループ/同一人物の反応/尺度構造/因果介入効果を別々に採点
- 社会的ネットワークを物理的・制度的環境と分離し、エージェント意見と事実を混同しない
- 同じペルソナで条件A/Bを試す場合、処置順序・記憶・spillover/carryoverを監査
- 市場研究から実行の前には法的権限、NO_ACTION、予算、リスク上限、独立readbackが必要
- 「透明なBlessing」は、**Source → Model claim → Intervention protocol → Authorized external receipt → Independent outcome → Comparator, CI, harms → Public challenge**をリンクさせる。今は未構築または未検証部分が多い

再現研究候補: 本論文の11テストから、外部公開で取得と処理が許されるものを最小セットとして移植。TVDだけでない、EV-3人間の処置効果比較、IV-4測定バイアス、CV-2外部基準の反例を**別結果**で評価する。Radiantの企業報告のスコアはManagerのスコアとは区別。

## 6. 客観的に分からないこと

- 独自Persona Genesis重み、内部信念推定モデル学習スケジュール、具体プロンプトは非公開。
- 個別モデル予測を実測人口へ一般化する際の誤差、包括的なfairness/プライバシー外部監査は未確認。
- 人間の説得や購買行動の**現実の因果効果**を商用案件全体で独立に測れたかは不明。
- Radiant実製品の最小社会規模は公式資料間で12対20と異なる。
- 本文のメトリクスはさまざまな調査や尺度に由来し、他社の結果と直接比較できない。

**社外出版の注意:** 個別ペルソナ画面の人名・勤務先・顔写真を実在人の同意や実測として流用しない。画面引用は公式URLへリンクし、機密データや参加者記録を第三者へ再配布しない。

## Sources (primary)

- https://societies.ai/radiant
- https://societies.ai/eval
- https://societies.ai/solutions
- https://societies.ai/as-benchmark
- https://societies.ai/knowledge/the-science-behind-artificial-societies
- https://societies.ai/publications
- https://arxiv.org/html/2609.30030
- https://arxiv.org/abs/2609.27690
- https://doi.org/10.1111/bjop.12764
- https://societies.ai/case-studies/teneo
- https://societies.ai/case-studies/hyperscaler-earnings-call
- https://societies.ai/case-studies/crisis-simulation
