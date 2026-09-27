# 人間行動の基盤モデル / world models of living beings — 調査ノート (2026-09-27)

ツール制約: WebSearch/WebFetch/Firecrawl不使用。Google News RSS + arXiv API (https、httpは無応答なので注意) + 直接curlのみ。
arXiv APIは `http://export.arxiv.org` が無応答、`https://export.arxiv.org` で成功（環境依存の既知の詰まり）。

## 1. 企業: 人間行動シミュレーション

### Aaru
- TechCrunch (2025-12-05, Google News RSS経由): "Sources: AI synthetic research startup Aaru raised a Series A at a $1B 'headline' valuation" — URL: https://news.google.com/rss/articles/CBMitAFBVV95cUxOWHY0T3IybnNkRk55SmlUYXY1WTZaeEdQVEx3Z1hESkVNbm9JblZqcnd5T3lhVWIyTmVGWGM5R2tNLUhobTM5a0xMYkhkQ2s4N2VOQ0ZFdWQyUzA4QjJReDNZX2JyOHF1TzV0MFQ3V0FmYTVFLXV1cE9pZDVkd0NFc2pvMFRJcUhIbUxmVTBQSFJEdWpldHV2MTVVVThTcGljX2FiSEl1THNxWG1rNUJ6R0RRbFU (Google News リダイレクト経由、元記事techcrunch.com)
- WSJ (2026-03-11): "The Billion-Dollar AI Startup That Was Founded by Teenagers" — 見出しのみ確認、本文未取得(UNVERIFIED詳細)。
- EY (2025-10-07): "Wealth and asset management AI simulation with Aaru" — EYが企業向けにAaruの合成調査を採用している事例。本文未クロール(UNVERIFIED詳細)。
- MrWeb/Daily Research News (2025-12-08): "Further Funding for Consumer Simulation Platform Aaru" — 見出しから「消費者シミュレーションプラットフォーム」というポジショニングを確認。
- aaru.ai への直接curl(-m 25)はタイムアウト・無応答（ボットブロック濃厚）。手法の技術詳細（アーキテクチャ・精度数値）は一次資料未取得、UNVERIFIED。
- 結論: Aaruは「合成調査/消費者・有権者シミュレーション」企業として2025年末Series Aで$1Bヘッドライン評価。数字は伝聞ソース(TechCrunch/WSJ見出し経由)であり、Aaru公式の精度指標は未確認。

### Simile (Joon Sung Park)
- Google News (2026-07-30/31, 複数ソース): "Simile raises $200 million at a $2 billion valuation to replace focus groups with AI-simulated humans" (Startup Fortune); "Simile bags $200M at $2B, five months after $100M Series A" (Tech Funding News)。2026-02-13 OfficeChai: "Simile Raises $100 Million To Create Simulations Of A Society Populated By AI Agents"。
  → 資金調達系列: Series A ~$100M(2026-02) → Series B $200M @ $2B valuation(2026-07)、5ヶ月間隔。見出しベース、詳細未クロール。
- finance.biggo.com (2026-06-16): "Simile's Joon Sung Park Says AI Can Simulate Human Behavior With 85% Accuracy" — 85%という数字が2件の見出しで独立に言及されている(複数記事で同じ85%表現が出現)。ただし一次ソース(Simile公式ブログ/論文)は本セッションで未クロール — 見出しの数字は伝聞であり、下記arXiv論文(2411.10109)の"83–86% of test-retest"と混同されている可能性がある。UNVERIFIED: 「85%」が製品の宣伝数値か論文結果の要約かは未確認。
- 結論: SimileはPark(Stanford, Generative Agents論文の著者)発の会社で、フォーカスグループ代替を掲げ2026年に急速に大型資金調達(Series A→B、$2B評価)。技術的根拠は下記arXiv 2411.10109論文と重なる可能性が高いが、企業公式の精度数値は本調査では一次確認できていない。

### 「Haro」問題
- "Haro"単独、"Haro AI startup simulate humans"、"Hark AI population simulation startup" のGoogle News RSS検索は0件（タイトルのみでヒット記事なし）。
- 隣接候補の探索結果:
  - **Expected Parrot**: 検索クエリ自体しかヒットせず、記事なし。
  - **Synthetic Users**: 検索でヒットしたのは同名ジャンルの別プレイヤー(Uxia, Listen Labs)であり、"Synthetic Users"自体の記事は確認できず。
  - 意外な収穫: "Harvard and MIT built an AI model of 8.3 billion people to test products on"(Startup Fortune / eu.36kr.com, 日付不明・2026年内) — 8.3 billion「エージェント」で世界人口を模す研究/プロダクト。これは「Haro」の音とは一致しないが、owner的関心（人口レベルの合成人間）に最も近い別プロジェクトとして記録。
- 結論: 「Haro」に一致する具体的企業は本調査のツール制約下（News RSS + arXiv + 直curlのみ、ブロック多発）では特定できなかった。**UNVERIFIED — 要追加確認**。Dais本人に「Haro」の綴り・文脈（記事/Podcast/Twitterどこで見たか）を確認するのが最短。

## 2. 研究: Generative Agents系列とCentaur

### Park et al., "Generative Agents: Interactive Simulacra of Human Behavior" (arXiv 2304.03442, 2023)
- arXiv API直接取得(https): 要約より引用 — "we describe an architecture that extends a large language model to store a complete record of the agent's experiences using natural language, synthesize those memories over time into higher-level reflections, and retrieve them dynamically to plan behavior."
- 25エージェントのSimsライクな町を作り、観察・計画・振り返り(reflection)の3要素がbelievabilityに効くとアブレーションで示した論文。個人の実データに基づく精度検証ではなく、"believable"（定性評価）が主張の中心。

### Park et al., "LLM Agents Grounded in Self-Reports Enable General-Purpose Simulation of Individuals" (arXiv 2411.10109, 最新版v3 2026-06-28)
- 実際のタイトルは「Generative Agent Simulations of 1,000 People」ではなく改題されている(旧題が通称として残存)。arXiv APIより引用:
  "Using data from a diverse national sample of 1,052 Americans, we built agents from (i) two-hour, semi-structured interviews... On held-out General Social Survey items, interview-only, survey-only, and combined agents achieved accuracies equal to 83%, 82%, and 86% of participants' own two-week test-retest consistency benchmark, respectively, compared with 74% for demographics-only agents."
- **これが核心の数字**: エージェントの予測精度は「人間本人の2週間テスト再検査一致率」の83–86%相当。100%的中ではなく、"人間が自分自身に対しても完全には一貫していない"ことを基準にした相対精度。人種・イデオロギー間の予測格差もdemographics-onlyより縮小したと主張。
- 著者: Joon Sung Park, Carolyn Q. Zou, Jonne Kamphorst, Niles Egan, Aaron Shaw, Benjamin Mako Hill(Stanford/Northwestern/UW系列、Simile創業に直結する学術基盤と推定される)。

### Centaur (Binz et al., arXiv 2410.20268 → Nature 2025)
- arXiv APIより引用: "Centaur, a computational model that can predict and simulate human behavior in any experiment expressible in natural language. We derived Centaur by finetuning a state-of-the-art language model on a novel, large-scale data set called Psych-101... covering trial-by-trial data from over 60,000 participants performing over 10,000,000 choices in 160 experiments."
- 主張: (1) held-out参加者の行動を既存の認知モデルより良く予測、(2) 新しいカバーストーリー・構造変更・**全く新しい領域**への一般化、(3) fine-tuning後にモデル内部表現がヒト神経活動とより整合(neural alignment)。
- これは「なぜ人が選ぶか」の心理実験(意思決定・学習・記憶などの実験室タスク)を対象にした基盤モデルで、Delphi-2Mのような疾病軌跡や人生イベントとは対象が異なる（実験室行動 vs 実世界の健康/人生アウトカム）。2026年時点の直接後継論文は本調査では特定できず(UNVERIFIED)。

## 3. 健康・行動トラジェクトリ基盤モデル

### Delphi-2M (Nature, 2025-09)
- Google News RSS(Nature, 2025-09-17): "Learning the natural history of human disease with generative transformers"。The Guardian(2025-09-18): "New AI tool can predict a person's risk of more than 1,000 diseases, say experts"。Inside Precision Medicine: "AI Model Predicts Risk for 1,000 Diseases Decades in Advance"。
- 見出しレベルの一致した主張: 1,000種類超の疾病について**数十年先**のリスク軌跡を予測する生成トランスフォーマー。UK Biobank等の電子健康記録ベース(推定、本文未クロールでUNVERIFIED)。medRxivプレプリント版が2025-02に先行公開されていた形跡あり(News-Medical記事より逆算)。
- arXiv自体には論文が見当たらず(医学系はmedRxiv/Nature側)。本文の定量的な精度指標(C-index等)は本調査で一次確認できていない — UNVERIFIED、次の一手はNature本文かmedRxivプレプリントのPDFを直接crwlすること。

### life2vec (Savcisens et al., Nature Computational Science, 2023)
- Google News RSS: neurosciencenews.com(2023-12-18) "AI's Leap in Predicting Life Events"; USA Today(2023-12-21) "the 'doom calculator'"。デンマークの行政データ(人口・雇用・健康・所得の全国レジストリ)を「人生を文章のように」トークン化し、死亡・転職等の人生イベントを予測するモデル、との定性紹介が複数メディアで一致。定量的な予測精度(AUCなど)は見出しのみで未確認 — UNVERIFIED、原論文(Nature Comp Sci 2023)への直接アクセスが必要。

### Apple / Google の wearable基盤モデル
- Apple: 9to5mac(見出し) "Apple AI model flags health conditions with up to 92% accuracy"、複数メディアが同じ92%を報道(macrumors, iPhone in Canada, Bhaskar English)。Apple Watchセンサーデータで健康状態を検出するモデル。独立に複数ソースが同一数値を報じているため確度は比較的高いが、Apple公式論文の一次引用は本調査では未取得(UNVERIFIED詳細)。
- Google: Google Research公式タイトルが直接ヒット — "LSM-2: Learning from incomplete wearable sensor data"、"Scaling wearable foundation models"(Google Research)。これは owner が言及した「Large Sensor Models (LSM)」系列そのもの。本文未クロール(UNVERIFIED数値)だが、タイトルからGoogleが「欠損の多いウェアラブルセンサーデータからの学習」を明示的にfoundation model路線で進めていることは一次(Google Research)ソースで確認できる。

## 4. 介入選択の方法論（行動科学 + 因果ML）

- **JITAI (Just-in-Time Adaptive Intervention)**: Nahum-Shani関連でGoogle News RSSヒット — Nature: "Effective monitoring of online AI decision-making algorithms in just-in-time adaptive interventions"、Nature: "Optimizing just-in-time adaptive interventions for interpersonal distress"、Nature RCT: "Physical activity and diet just-in-time adaptive intervention to reduce blood pressure: a randomized controlled trial"。JITAIは「個人の文脈(位置・時間・生理状態など)が介入に適したタイミングかを検知し、その瞬間だけ介入を出す」設計であり、これがownerの「個人データ無しで集団レベルで最適介入を選ぶ」という要求とは方向性が逆(JITAIは個人文脈依存が本質)である点に注意。
- **HeartSteps / contextual bandit**: 直接のGoogle News RSSヒットは0件(検索クエリのみ返る)。HeartSteps自体は文献で広く知られるmicro-randomized trial(MRT)の代表例だが、本調査のツール制約下では一次ニュース記事を特定できなかった — UNVERIFIED、次はPubMed/arXivでの直接検索が必要。
- **uplift modeling / heterogeneous treatment effects / digital twin (health)**: Google News RSSでの複合検索はほぼ無関係の1件のみ(自閉症研究のnarrative review)しかヒットせず、専用の一次資料は本調査では確保できなかった。UNVERIFIED — この領域は学術系DB(PubMed/arXiv経由の専用検索)を要する。
- 推論(証拠ではない): 集団レベルで個人データなしに介入を選ぶという要求は、JITAI/MRTの「個人文脈への適応」パラダイムと構造的に緊張する。実務的には「集団のセグメント(匿名化された行動クラスタ)ごとにuplift/CATE(条件付き平均処置効果)を推定し、集団分布に対して期待効果最大の介入を選ぶ」という設計が、個人PIIなしで最も近づける現実的な折衷案になる、というのがこの調査から導ける推論。

## 5. UBI（財務健康との関連、簡略）

- Google News RSS: NYT(2024, 見出しのみ) "The Report Card on Guaranteed Income Is Still Incomplete"; CBS News "Here's what a Sam Altman-backed basic income experiment found"; WBUR "The results are in on America's largest universal income experiment"; Business Insider "Basic-Income Recipients More Likely to Think About Starting a Business"; University of Toronto "Eva Vivalt leads landmark basic income study"。
- これらは2024年に結果公表されたOpenResearch(Sam Altman出資)の無条件給付($1,000/月, 3年間, 米国複数州)実験の報道群であり、複数の独立メディアが同一実験を報じている点で確度は高い。定量結果(労働時間・健康指標の変化など)の具体的な数字は本調査では見出しレベルのみで、本文一次引用は未取得 — UNVERIFIED詳細、次はOpenResearchの公式レポートPDFへの直接アクセスが必要。
- GiveDirectlyについては本調査で個別検索を実施していない — UNVERIFIED(未調査)。

---
# 要約（コンパクト版は別途アシスタント回答として提示）
