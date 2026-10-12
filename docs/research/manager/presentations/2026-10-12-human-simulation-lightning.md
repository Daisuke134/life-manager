# 人間シミュレーションとManagerの最初の実証

英語6枚、日本語発表者ノート、合計300秒。公開研究と提案する実証を区別する。

## 1. Can AI improve lives by changing shared conditions?

Human simulation → environment design → measured outcomes

**The question**: What changes when the AI acts on access, supply, and shared rules?

**The evidence**: Prediction accuracy, simulated policy gains, and actual life outcomes are separate claims.

**Manager**: Ambient AI for shared environments. Today: a research comparison and proposed first study.

日本語ノート: 人の相談へ答えるAIから、人が選べる条件を変えるAIへ進むには何が必要でしょうか。今日はAaru、Simile、AI Economistを比較します。回答予測が当たること、模型の中で制度が改善すること、現実の生活が良くなることは別々の証拠です。Managerはこの接続を目指していますが、ここで完成した社会改善を報告するわけではありません。



## 2. Aaru: construct populations, forecast responses

Population structure matters before individual answers

**Population**: Public, licensed, and customer data; preserve relevant joint traits.

**Models**: Published core: non-language-model. Hiring also names hybrid LLM/classical research.

**Customer case**: EY: 53 matched questions; median rank correlation 0.90. Research reproduction, not wealth impact.

日本語ノート: Aaruでは人口の作り方が重要です。年齢と所得を別々に一致させても、雇用や時間制約との組み合わせが間違うと反応はずれます。公開研究は中核を非言語モデルと説明し、求人は言語モデルと古典手法の組み合わせも挙げています。求人だけから内部構成を断定せず、異なる層や研究方向の可能性を残します。EYの例は調査再現の結果です。

- [Aaru methods](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)
- [Population role](https://aaru.com/careers/f718d12f-67e9-4fe9-91cc-9e3b69ff00fe)
- [EY case](https://aaru.com/case-studies/ey-wealth-research)

## 3. Simile: ground behavior and predict uncertainty

Interviews + surveys + experiments + behavior records

**Grounding**: Predict action distributions; learn from what people say and what they do.

**Confidence**: Estimate expected prediction error, then decide where more human evidence is needed.

**Customer cases**: Itaú: payment trust and comprehension. CVS: access, wait times, refill intent, and benefit design.

日本語ノート: Simileは自己報告と実際の行動を組み合わせます。さらに予測誤差を推定するモデルを持ち、不確かな問いを人間の研究へ戻すことを説明しています。Itaúの5週間から4営業日という数字は研究速度です。CVSは待ち時間や薬剤師へのアクセスなどを検討しますが、その記事から健康改善幅を確定することはできません。

- [Confidence](https://www.simile.com/blog/confidence)
- [Itaú](https://www.simile.com/blog/itau-at-esomar)
- [CVS](https://www.simile.com/blog/simile-cvs-health)

## 4. AI Economist: change rules as people adapt

A planner and economic agents learn with different objectives

**Agents**: People adjust work and trade when incentives change.

**Planner**: Changes shared rules; learns from the resulting economy.

**Value choices**: Productivity, equality, time, and wellbeing are not interchangeable objectives.

日本語ノート: AI Economistでは人々が経済活動を学び、設計者が税などの共有ルールを変えます。ルール変更後に人々が適応することを評価に含めるのが学びです。ただし社会の目的関数は人間が指定します。模型内の生産性と平等を改善しても、現実のすべての生活指標が改善したとは言えません。

- [AI Economist](https://arxiv.org/abs/2108.02755)

## 5. First proposed blessing: access to paid work

Change structural barriers and allocation in a real operator network

**Intervention**: Eligibility, task structure, timing, or allocation within operator authority.

**Primary outcome**: Realized net income per eligible person, including zero earnings.

**Study requirements**: Real demand, payment data, comparable budgets, quality, and spillover-aware evaluation.

日本語ノート: 第一候補は仕事や収入機会へのアクセスです。実在案件がある運営者と、参加条件や配分、時間条件を変えます。主要指標は対象全員の一人当たり実現純所得で、案件を得なかった人も含めます。同じ案件を奪い合うため、個人の結果を独立とは扱えません。比較の単位を考え、時間負担、費用、品質、機会を失った人も測ります。



## 6. The result must connect the model to reality

Population → response → intervention → readback → evaluation

**Public artifacts**: Reproducible code, data permissions, baselines, failures, and costs.

**Research questions**: Which constraints change policy rankings? How do we handle interference and adaptation?

**Discussion**: What evidence would convince you that a shared environment actually improved?

日本語ノート: モデルから実行、観測、独立評価までをつなぐことが成果です。公開するコードだけでなく、根拠データ、比較相手、未見条件、失敗、費用を示します。特に研究室の皆さんには、どの制約が制度の順位を変えるか、干渉と適応をどう測るかを相談したいです。最後に、何が観測されたら共有環境が改善したと納得できるかを議論したいです。
