# Artificial SocietiesとRothkoを基礎から理解する：行動基盤モデル・人工社会・11項目のベンチマーク

> **研究ノート兼公開記事草稿**｜2026-10-23｜Manager Masterclass  
> **証拠区分**：［公開一次資料］［企業の自己報告］［論文の実験結果］［教育用の架空例］［Managerへの設計提案］を区別する。  
> **重要な制限**：Rothko本体の重み・訓練コード・ネットワーク内部構成は公開確認できなかった。以下はリバースエンジニアリングや学習再現に成功したという主張ではない。

## 0. まず何を研究している会社か

[Artificial Societies](https://societies.ai/)は、人間の意見・意思決定・集団反応を推定し、戦略やメッセージ、社会的な相互作用の結果を事前検討するための人工社会モデルを提供している。製品説明では、実データに根ざしたペルソナを作り、その信念体系をモデル化し、社会的なつながり・影響関係を通じて集団反応を調べるとしている。従来の「架空の人物プロフィールを一般目的LLMに渡すだけ」と区別している［公式method］。

2026年10月に紹介された **Rothko** は同社の「人間行動の基盤モデル（foundation model of human behaviour）」である［Rothko］。「Artificial Societiesというサービス全体」「Rothkoというモデル」「公開Benchmarkという評価コード」「2024年のChirper社会ネットワーク研究」は別物として理解する。

## 1. Rothkoの公開された技術アプローチ

### なぜ通常のLLMだけでは不十分と考えるか

一般的な自己回帰言語モデルは、文脈に続くトークン確率を学習する。指示追従・選好学習は役に立つ返答や整った文章を促進するが、特定の集団に含まれる少数意見・回答のばらつき・実際の行動選択を正確に再現する目的とは必ずしも一致しない。自然な「理由の説明」と、実際の選択予測精度は別である。

### 公開資料で確認できた仕組み［企業の説明］

1. **出発点**：事前学習済みモデルを利用する。
2. **モデルの変更**：文章生成ではなく、意思決定を出力するようアーキテクチャを変更する。
3. **追加学習**：匿名化SNS情報、取引履歴、移動の軌跡、専門家インタビュー、アンケートその他の行動記録を学習に利用すると説明。
4. **条件付き予測**：個人の情報とその文脈から、その人の決定を予測する。
5. **集団集約**：回答者単位の出力を集約し、人口や属性グループの予測分布を算出する。
6. **人工社会**：同社製品では、ペルソナ同士の関係と影響をモデル化し、討論・意見の伝播なども扱う。公開methodページによると1社会あたり12〜3,500ペルソナという説明がある。

**未公開／断定しない**：Transformerのどの層や出力ヘッドを置き換えたか、損失関数、学習サイズ、個人データの照合工程、ネットワーク上の因果的な影響推定法、長期軌跡の検証、内部の推論API仕様。たとえば「分類ヘッド＋softmax」「効用関数」「模倣学習」「強化学習」は実装可能な候補だが、Rothkoでの採用事実ではない。

### 理解のための概念式［教育的な再構成・非公開実装ではない］

個人特性を \(x_i\)、状況を \(c\)、選択肢を \(a\) とすると、一般的な条件付き行動モデルは
\[
p_\theta(a\mid x_i,c)
\]
という分布を返せる。人口の重みを \(w_i\) とすると、集団全体で行動 \(a\) を選ぶ期待割合は
\[
\hat P(a\mid c)=\frac{\sum_i w_i p_\theta(a\mid x_i,c)}{\sum_i w_i}.
\]
これはRothkoの公開ソースコードから逆算された数式ではなく、考え方を理解するための標準的な数学表現である。モデルの出力が確率ではなく離散選択の場合、集約の形式は変わる。

### 意見と行動は違う

「買いたいと答えた」「買った」は別のラベル。購買行動には価格、機会、在庫、所得、時間などの制約がある。伴走論文は *intention–behaviour gap*（意図と実際の行動の乖離）を強調し、行動予測への妥当性主張には、実際の行動データを用いた基準検証が必要だとする［公平性論文］。**Rothkoが意見調査ベンチマークに強いことだけから、介入後の行動・幸福・健康への因果効果を証明したとはいえない。**

## 2. 人工社会の三層構造

公開method説明に基づく概念整理：

1. **観測データ層**：公開研究、SNS・コメント、レビュー、投票や投資などの記録、顧客が許可したデータを入力。顧客のファーストパーティーデータは個別案件で分離し、モデル学習に使わないと説明される。
2. **個人モデル層**：個人のプロフィール・信念体系・心理特性を表し、過去行動や人間の調査指標と照合して検証。
3. **社会ネットワーク／相互作用層**：属性や関係、影響パターンを使いペルソナをつなぎ、アンケート、個別インタビュー、4〜14人の人工フォーカスグループなどで反応を検討。

注意：調査質問を各ペルソナに**独立**に回答させた結果の集計と、ペルソナが相互に影響し合い時間とともに状態を更新する**動的な社会シミュレーション**は別の計算。公開Benchmarkの9個のLLM比較では、合成回答者同士は交流しない設計である［Benchmark論文Sec.4］。2024年の33,299チャットボットの社会ネットワーク研究も、Rothko本体を33,299体実行したという実証ではない。

## 3. Artificial Societies Benchmark：11の検査をどう読むか

2026年9月のarXiv論文 *Artificial Societies Benchmark: A Validation Framework for Synthetic Research* は、**20の人間データソース**と**9つの汎用LLM**、さらに統計的な対照法を使う**11の検査体系**を提案した。公開リポジトリには36タスク定義、テスト、モデル設定、結果scorecard等がある。主論文で9 LLMを比較したことと、10月に企業自身がRothko/Artificial Societiesを加えた自己比較を発表したことは分けて記録する。

| 分類 | ID | 何を検証するか | 代表的な失敗 |
|---|---|---|---|
| **Internal validity** | IV-1 | 同じ質問を繰り返したときの一致率が人間に近いか | 過剰に一致する |
|  | IV-2 | 関連する質問への回答の整合／矛盾パターン | 人間と異なる矛盾 |
|  | IV-3 | 言い換えた質問への反応 | 言い換えに過敏／鈍感 |
|  | IV-4 | 選択肢の並び等、調査形式変更への反応 | 実際の人間と異なる変化 |
| **Construct validity** | CV-1 | 一つの心理尺度の質問間の共分散・内的一貫性 | 一問ずつは自然だが関係性が壊れる |
|  | CV-2 | 質問回答と独立した外部基準との関係 | 尺度の意味が失われる |
|  | CV-3 | 異なる心理特性が区別されるか | 特性が人工的に混ざる |
| **External validity** | EV-1 | 集団の回答分布、数値分布 | 割合や分散を外す |
|  | EV-2 | 人口サブグループ・実在個人との一致 | 平均のみ合い、少数派を外す |
|  | EV-3 | 人間実験で観察された介入効果の方向と大きさ | 効果を誇張／逆転する |
|  | EV-4 | 因子構造・因子負荷・測定不変性 | 尺度の構造や選択肢が潰れる |

**注意**：ここでの「internal validity」は因果実験でいう内的妥当性と用語の使い方が完全には一致せず、著者らは回答過程を検査するカテゴリーに使っている。EV-3は因果効果の「シミュレーションによる回復度」を見る検査であり、単独で新しい実世界介入の効果を証明するものではない。

### なぜTVDだけで判断してはいけないのか

各質問の周辺分布は
\[
D_{\mathrm{TV}}(P,Q)=\frac12\sum_k |P(k)-Q(k)|
\]
で比較できる。だが、たとえば人間100人のうち50人が質問A・Bとも「はい」、50人が両方「いいえ」であっても、合成100人の半分が(A=はい,B=いいえ)、残りが(A=いいえ,B=はい)なら、**A単独もB単独もTVD=0、AとBの組み合わせはTVD=1**となる。この架空例は「同じ周辺分布でも相関・共同回答は異なる」という意味を直感的に示す。

この例の再現コードは [educational Python demo](../examples/artificial-societies-benchmark-mini-demo.py) に保存した。`python3 docs/research/manager/examples/artificial-societies-benchmark-mini-demo.py` で実行できる。公式フルベンチマークの再現ではない。

### 人間より「完璧」すぎても失敗

Benchmark論文のBainbridgeデータ例では、同じ質問の人間の回答一致率は約73%。一方、モデルによって54%から99%までばらついた。ValueConsistencyでは人間の言い換え回答一致率は約85%、多くのLLMは100%。**誤差が少なそうな完全一貫性が、むしろ人間の揺らぎを再現できていない**という逆説を学べる［Benchmark論文Sec.5.1］。

### 実験効果の誤差

人間の実験効果と合成モデルの実験効果を分ける：
\[
\tau_H=E[Y\mid T=1,H]-E[Y\mid T=0,H]
\]
\[
\tau_S=E[Y\mid T=1,S]-E[Y\mid T=0,S].
\]
両者の差 \(|\tau_S-\tau_H|\) が効果の大きさの再現誤差。これは無作為化の比較可能性などの前提で読む。たとえば実人間では30%→38%（+8ポイント）、合成モデルでは30%→50%（+20ポイント）なら誤差は12ポイント。数字は架空。

### スコアは一つにまとめない

11検査には尺度が異なるものと、データ不足で算出不能なものがある。公式リポジトリREADMEは **「単一の総合点はない」** と明記する。Managerも、予測・介入選択・実行・因果的実世界効果を一つの数字に押し込まない。

## 4. Rothkoの2026年10月・企業自己比較の結果と読み方

企業ブログは、公開Benchmarkから**7調査ソース・2,796合成回答者・68,280回答**を用い、Rothko/Artificial Societiesを9 LLMと同じ質問・採点コードで比較したと説明している。

| 指標 | Artificial Societies（企業公表） | 掲載された最良の汎用LLM | 何を測っているか |
|---|---:|---:|---|
| 集団回答分布TVD | **0.08** | **0.31** | 回答選択肢の割合 |
| サブグループ分布TVD | **約0.06** | **約0.22** | 属性別の回答分布 |
| 質問文変更の効果誤差 | **1.4ポイント** | **6.2ポイント** | 言い換えによる回答変化 |
| 意見の広がりに関する誤差 | **0.006** | **0.091** | 回答分散の人間との差 |

数値は[企業ブログ（2026年10月）](https://societies.ai/as-benchmark)にある**公開された四つの指標**の値であり、すべての11項目について同じ一律な優越性を独立検証したものと表現しない。「8%だけ外れた」「92%の個人行動が当たる」とも読まない。TVD 0.08はカテゴリ分布の移すべき確率質量の大きさに対応する。

**重要な検討点**：
- 企業自身による評価であり、独立した第三者追試とは別。
- 公開Benchmark論文の9 LLM比較と、あとで追加したRothko比較は発表主体とタイミングが異なる。
- 事前学習コーパスと評価回答の重なり、真の時系列holdout、特定分野の行動ラベルの未見性は公開資料だけでは十分監査できない。
- 汎用LLMとの比較は条件・データ・学習目的が異なり、必ずしも「同じ情報とコストを使う全手法の公平な比較」とは限らない。
- 7調査ソースの回答分布精度から、現実の政策変更・経済行動・健康・苦しみの因果的改善を直接主張しない。

## 5. 介入を扱った応用研究から学ぶこと

### 誤情報とファクトチェックの再現

2026年9月の記事では英国の**4つの既存実験**について、合成英国人の反応と、合計2万5千人超の実人間データを比較したとしている。Loombaらの実験では、誤情報による「ワクチンを確実に受ける」割合の減少は実人間 **6.6ポイント**、合成人口 **8.2ポイント**。人間の報告区間は **3.8〜9.0ポイント**であったとする。一方、対照群でも合成側がワクチン肯定方向に約4ポイント動く不一致があった。［企業の再現報告］

非常に重要な注意：後続時点のファクトチェック効果の減衰では、**外部研究の忘却率を人工的に導入し、効果減衰を一致させている**。それは時間を通じた記憶変化をモデル単独が自律予測した証拠ではない。**他研究から入力したパラメータとモデル固有の予測力は分けて評価する**。［誤情報記事］

### 決算説明会の事前登録実験

NVIDIA、Marvell、Credoの説明会について、実際の説明会より前に予測をOpen Science Frameworkで登録してから、質問内容と突き合わせた。詳しいアナリストプロフィールは質問の個人差を一部再現したと企業は報告。同時に、モデルに事前に与えた「論点」が回答を強く誘導することも認めている。モデルの予測と、研究者がプロンプトへ埋め込んだ情報の寄与を分けることが教訓。［Earnings calls記事］

### 人工フォーカスグループ

同社は、ペルソナが独立に一言ずつ答えるのではなく、相互に異議を唱え、互いの意見に反応する討論形式を実装。4〜14体程度に制約したのは、人工参加者には疲労がなくても、規模が増えると発言者偏りや議論の分裂が起こるため。Managerで再利用するなら**誰が話したか／誰を説得したか／議論前後の意見変化**を記録し、実人間のグループ討論に対する妥当性を別途確認する必要がある。［フォーカスグループ記事］

## 6. Publicationsに掲載された9本のPapersと学習上の位置付け

以下は公式[Publications一覧](https://societies.ai/publications)に掲載された順。**すべてがRothko本体の開発・評価論文ではない**。著者が関係する研究を含む。

1. **Artificial Societies Benchmark: A Validation Framework for Synthetic Research**（Chidichimoほか、2026年9月、arXiv 2609.30030）。11評価、20人間ソース、9 LLM、結果scorecard。最重要。［論文本文・GitHubコード確認］
2. **Consequential Behaviour and Representational Fairness in the Validation of Synthetic Research**（Kutznerほか、2026年9月、arXiv 2609.27690）。意図≠行動、C基準とL0–L3、実験効果E、集団ごとの代表性、公正性。Managerの介入評価設計に直結。［論文本文確認］
3. **How Artificial Societies Accurately Models Human Opinion**（2026年7月、企業内部研究ページ）。データ→個人信念→ネットワークの3段階、ベンチマーク・顧客説明。モデル内部詳細の査読済み論文ではない。［公式methodページ確認］
4. **Towards an Informational Account of Interpersonal Coordination**（Chidichimoほか、2025年11月オンライン発表／誌面2026年、Nature Reviews Neuroscience）。脳・身体・感情・言語の協調を情報理論で記述する展望論文。Managerの相互作用モデルに関連。Rothkoの実装仕様ではない。［抄録確認］
5. **Synchronized Movements and Rituals**（Chidichimo、2025年1月、Springer百科事典）。同期行動・儀礼の心理学的背景。本文の十分なアクセスが得られていないため内容の技術的細部は未確認。［書誌情報確認］
6. **Artificial Intelligence Chatbots Mimic Human Collective Behaviour**（Heほか、公式一覧では2024年12月、British Journal of Psychology掲載）。Chirper.aiの33,299ボット、312,969相互作用、28日間を分析。言語や投稿内容が似た者同士が集まりやすい**homophily（同類選好）**が見られる。ただし単一プラットフォームの観察研究であり、社会的メカニズム全般の再現やRothko本体の妥当性を確立しない。［本文確認］
7. **Unfollowing Hyperpartisan Social Media Influencers Durably Reduces Out-Party Animosity**（Rathjeほか、公式一覧2024年10月、PsyArXiv）。追跡解除の介入を含むフィールド研究。介入と実際の結果の比較例として重要。投稿時期・改訂版を区別。［要旨と公開解説確認］
8. **Computing the Performance of a New Adaptive Sampling Algorithm Based on the Gittins Index in Experiments with Exponential Rewards**（He・Villar・Mavrogonatou、2023年）。マルチアームドバンディット・Gittins指数を用い、学習の情報量と参加者への直接利益のバランスを研究。Managerの逐次介入・適応的実験に関連。［論文要旨確認］
9. **Social Media Behavior Is Associated with Vaccine Hesitancy**（Rathjeほか、2022年、PNAS Nexus）。アンケート回答とTwitter行動データの関連性を研究。観察研究の**相関**を介入による**因果効果**と取り違えない。［全文・要旨確認］

### その他の研究・商業記事

- **Introducing Rothko**：上記アーキテクチャの企業発表。
- **We Accurately Simulated Misinformation, Fact-Checking, and Prebunking Experiments**：既存実験効果の再現、対照群のズレや外部忘却率の問題。
- **AI Researchers Should Use Group Alignment to Reduce P(doom)**：個々のAIが安全でも集団相互作用が安全とは限らないという理論的主張。実世界安全性の実証とは区別。
- **Distribution Matching Is a Bad Way to Evaluate Simulations**：周辺分布だけでは測れないことを平易に解説。
- **Exploring Second-Order Effects: From Analyst Notes to Press Coverage on Nike**：一段先の反応・情報伝播という応用テーマ。企業のデモ・事例であり一般化性能は別検証。
- **How We Designed Artificial Focus Groups**：実装とUX設計の考察。
- **Artificial Societies Is More Accurate Than State-of-the-Art LLMs**：7ソース・4図の企業自己評価。
- **Testing National Resilience Against Misinformation**：国家規模の情報環境に関する応用。
- **Oversight Yes, Slowdown No: Simulating the Reaction to “We Must Pace the Frontier”**：AI政策に対する合成集団の反応デモ。予測事実と実測事実の区別が必要。
- **Testing Simulations Against Reality: Learnings from Earnings Calls**：事前登録した将来予測を実際の質問と比較。
- **News／Press**：Cambridgeの紹介、New Statesman、Forbes、資金調達発表は研究一次論文とは別の証拠レベル。

## 7. 再現可能性：何が公開され、何を動かせるか

公開GitHub: https://github.com/artificial-societies/artificial-societies-benchmark

READMEと \`benchmark_experiment/metrics.py\` のコードを直接確認。公式READMEによると：
- Python 3.12、uv、別途R 4.6等を使う。
- 36のタスク仕様、11検査、9 LLM、2統計対照法、scorecard **7,128セル**を公開。
- \`uv sync --frozen\` → \`uv run pytest -q\` → \`uv run python analysis/scorecard/build_scorecard.py\` などの再現手順が記載される。
- **実人間の個票データ、個人プロフィール、入力済みプロンプト、個人別モデル出力、API資格情報は同梱されていない**。収集元のアクセス条件を確認して別途入手する必要がある。
- コードはMIT、集計結果と図はCC BY 4.0、質問原文と採点キーには元データの利用条件が残る。

今回の調査環境では直接git cloneできず、Rothko本体の公開重みや誰でも実行できる推論APIも確認できなかったため、**公式フルベンチマーク／Rothko推論を実行したとは主張しない**。代わりに公開メトリックの計算を読み、標準Pythonだけで動く架空100人の周辺分布・同時分布・介入効果のミニ実験を作成して実行し、TVD（0、0、1）と効果誤差12ポイントを確認した。

## 8. Managerは何を再利用し、何を新規研究すべきか

| Managerの層 | 既存技術・研究から借りるもの | Managerが別途検証すべきこと |
|---|---|---|
| 人口構成 | 公的統計・PUMS・IPF／IPUなど既存方法。必要ならAaru等の公開知見 | 地域・世帯・少数派の同時分布、未指定クロス集計 |
| 行動予測 | Rothko・Aaru・Simile型の条件付き行動モデルを**比較基準**とする発想、単純な回帰・選択モデル | 時間的holdout、実行動ラベル、料金／制約の変化 |
| 社会相互作用 | network science、Concordia／AgentSociety、同社の集団討論設計 | 実人間での影響・模倣・同類選好・伝播を再現するか |
| 介入の選択 | 実験効果EV-3、因果推論、オフライン方策評価、AI Economist | 効果の過大推定、変化後の適応、波及効果、反実仮想 |
| 実行 | 権限境界、監査ログ、外部結果のreadback、ロールバック | 実際の環境変更が起こったか |
| 社会的成果 | C行動基準・実世界の因果比較・分配的公正・独立計測 | 健康、時間、アクセス、負担、財政等の**現実の改善** |

**提案する最初の実験**：1つの低リスクで許可された意思決定問題を選ぶ。まず(1)多数派予測、(2)統計的ベースライン、(3)既存ML行動モデル、(4)必要ならLLMペルソナを比較する。IPF人口合成を必須前提とせず、実人間データがある場合は直接行動予測を行う。11指標から用途に必要なものを事前登録し、実際の行動データで検証する。その後、介入選択の精度・実行・現実の成果に進む。

### 誤解してはいけない5つのポイント

1. 「RothkoはLLMではない」と単純化しない。**事前学習済みモデルを変更・追加訓練した意思決定モデル**という公表。
2. 「2024年の33,299エージェント研究がRothkoそのものの性能を示す」と言わない。
3. 「TVD=0.08は92%の個人行動正解率」と言わない。
4. 「意見・意図・購買・健康・苦しみ」は別の観測変数であり、同じモデルで代替できると仮定しない。
5. 「公開Benchmark」と「Rothkoの専有モデル」と「企業自己評価」を区別する。

## 9. これからの教材・書籍の章立て案

- **Lesson AS-01**：モデルとは何か／予測するのは文章か意思決定か（中学数学から）。
- **Lesson AS-02**：確率、条件付き確率、個人と集団の予測、重み付き集計。
- **Lesson AS-03**：周辺分布と同時分布、TVD=0でも失敗する例（実行可能Python）。
- **Lesson AS-04**：人間の心理尺度と相関、共分散、Cronbachのα、因子構造。
- **Lesson AS-05**：ネットワークと同類選好、影響伝播、動的人工社会。
- **Lesson AS-06**：意図と行動の乖離、行動データ、反実仮想、実験効果。
- **Lesson AS-07**：11項目のベンチマークをコードと一緒に読む。
- **Lesson AS-08**：Rothko・Aaru・Simileを「入力／中核モデル／目的変数／検証指標」で公正比較。
- **Lesson AS-09**：Managerのベンチマーク仕様を策定し、独立した介入実験へつなぐ。
- **Lesson AS-10**：論文の仮説、実験、限界、研究の次の一歩を口頭で守る。

## 一次資料・再現資料

1. Rothko公式: https://societies.ai/rothko
2. 公式Method & Evaluation: https://societies.ai/eval
3. 主論文（36ページ、2026-09-24提出、10月1日v2）: https://arxiv.org/abs/2609.30030
4. 公平性と行動基準（2026-09-23提出、10月6日v3）: https://arxiv.org/abs/2609.27690
5. 公式Benchmarkコード: https://github.com/artificial-societies/artificial-societies-benchmark
6. Rothko/Artificial Societiesと9 LLMの比較（2026年10月、企業自己評価）: https://societies.ai/as-benchmark
7. 周辺分布だけでは不十分: https://societies.ai/synthetic-validation
8. 誤情報実験の再現: https://societies.ai/misinformation
9. Earnings calls: https://societies.ai/earnings-calls
10. 人工フォーカスグループ: https://societies.ai/focus-group-design
11. Collective behaviour（British Journal of Psychology）: https://doi.org/10.1111/bjop.12764
12. 社会的協調の情報理論: https://doi.org/10.1038/s41583-025-00989-0
13. Gittins Index／adaptive sampling: https://arxiv.org/abs/2301.01107
14. Vaccine hesitancyとSNS行動: https://pubmed.ncbi.nlm.nih.gov/36714849/
15. Influencer unfollowing field experiments: https://stevenrathje.com/publication/unfollowing-hyperpartisan-social-media-influencers-durably-reduces-out-party-animosity/
16. Publications全件: https://societies.ai/publications

---
*編集状態：研究記事草稿。出版前に各社の2026年10月時点以降の更新、個別実験の資料、比較ベースラインの公平性、権利条件を再監査する。*
