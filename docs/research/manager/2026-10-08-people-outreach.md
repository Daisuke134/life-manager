# Manager：研究者・実務家への技術フィードバック／対話候補

確認日：2026年10月8日 UTC。公式大学ページ、本人の研究ページ、公式企業サイト、著者論文、公式GitHub READMEを公開ネットワークから取得した。取得記録と原文は `people/oct08/verification*.json` と同ディレクトリの HTML/TXT。旧キャッシュを論文読解に補助使用したが、現在の所属・公開連絡先は再取得したページを優先した。メールアドレスを推測していない。ここでの「確認」は公開掲載の確認であり、配送・返信可能性の確認ではない。

Manager の説明は「受益者がログインや資格情報の提出をしなくても、供給・アクセス・ルールなど周囲の構造を改善する ambient AI の初期設計」。実装済みデモ、効果実証、AGI達成は主張しない。求めるものは技術的批判、評価設計への助言、または短い研究対話。共同創業者募集にはしない。

## 優先候補8名

順序は最初の議論で得られる具体性を重視した提案。紹介や返信を保証するものではない。

| 優先 | 人物・現時点で確認できる役割 | 実際の研究／実務と Manager の接点 | 公開された正式連絡経路 | その人への質問1つ |
|---|---|---|---|---|
| 1 | **Joel Z. Leibo**：本人サイトに Google DeepMind senior staff research scientist / King's College London visiting professor | [本人サイト](https://www.jzleibo.com/)は Concordia を明示。自然言語で相互作用するエージェントと、手書きの grounded variables を組み合わせ、協力・社会的ジレンマ・制度を研究する。構造介入の評価環境に直接近い。 | 同サイトの本文 `jzl [at] deepmind .com` と mailto に **jzl@deepmind.com**。 | “In Concordia, how would you separate changes in resource access or institutional rules from prompt-induced cooperation, and test whether the effects generalize to new populations?” |
| 2 | **Michael S. Bernstein**：Stanford、Simile co-founder & Chief Data Officer | [研究室ページ](https://hci.stanford.edu/msb/)と[Simile公式](https://www.simile.com/)で確認。HCI、社会的システム、Generative Agents、実在者に接地したシミュレーション。参加しない人も影響を受ける設計と測定の問いに適する。 | 研究室ページの本人 mailto：**msb@cs.stanford.edu**。 | “What evaluation would demonstrate benefits to people who never use Manager, while detecting unequal or unwanted effects of changes to shared access rules?” |
| 3 | **Joon Sung Park**：Simile co-founder & CEO | [本人研究サイト](https://www.joonsungpark.com/)と[Simile公式](https://www.simile.com/)で確認。memory/reflection/planning を備える生成エージェント、および実在者のインタビューに接地した個人シミュレーション。 | 現在の公開本文で本人の直接メールを確認できず。Simile公式トップの **“Run a simulation”** という企業問い合わせ導線は確認。研究対話専用窓口とは断言しない。旧HTMLコメント内の大学メールを連絡先として採用しない。 | “When an intervention changes actual access or supply rather than only wording, what held-out human study would convince you that interview-grounded agents predict the intervention effect?” |
| 4 | **Yong Li**：AgentSociety 論文の corresponding author、Tsinghua所属の著者 | [AgentSociety v1](https://arxiv.org/abs/2502.08691)と[AgentSociety 2](https://arxiv.org/abs/2607.11895)。都市環境、社会／経済相互作用、実験・分析の実行基盤。複数著者の成果であり、一人を sole founder と呼ばない。 | [v2論文本文](https://arxiv.org/html/2607.11895v2)の Email：**liyong07@tsinghua.edu.cn**。チーム窓口は[公式README](https://github.com/tsinghua-fib-lab/AgentSociety/blob/main/README.md)の **agentsociety.fiblab2025@gmail.com**。 | “Which environment variables and validation targets would you use to compare a supply/access intervention with an information-only intervention without encoding the desired outcome in agents’ prompts?” |
| 5 | **Michael Levin**：Tufts Biology、Vannevar Bush Professor / Distinguished Professor | [公式プロフィール](https://as.tufts.edu/biology/people/faculty/michael-levin)は morphological and behavioral information processing / collective intelligence of cells。[TAME](https://www.frontiersin.org/journals/systems-neuroscience/articles/10.3389/fnsys.2022.768201/full)は多様な身体・認知に対する実験的枠組み。個々のユニットの能力向上と集団環境の変化を分けて考える相手。 | 同公式ページの本人 mailto：**michael.levin@tufts.edu**。 | “What experimentally testable criterion would distinguish an environment that merely facilitates existing agents’ goals from one that supports a new level of collective agency?” |
| 6 | **David Krakauer**：SFI President / William H. Miller Professor of Complex Systems | [SFI公式プロフィール](https://www.santafe.edu/people/profile/david-krakauer)の「exbodiment」、知能を言語・人工物へ外部化する研究。[The Information Theory of Individuality](https://arxiv.org/abs/1412.2447)は情報論による個体性の枠組み。Managerを個人補助か社会的計算基盤か定義する問いに適する。 | SFI公式プロフィール Contact の `Email` リンク：**dk@santafe.edu**。 | “What measurements could distinguish improved individual performance from a more capable social system when the intervention changes shared infrastructure?” |
| 7 | **Percy Liang**：Stanford professor、Simile co-founder & Chief Scientist | [本人ページ](https://cs.stanford.edu/~pliang/)は Marin/open development、再現可能性、実験の provenance。Simile創業者役割は公式企業ページで確認。代理評価の信頼性・不確実性・外部検証に適する。 | [Stanford公式プロフィール](https://profiles.stanford.edu/percy-liang)が公開する **Contact Administrator: Suzanne Lessard, slessard@stanford.edu**。本人メールとは扱わない。取次を依頼する場合のみこの正式経路。 | “What preregistered evaluation and uncertainty reporting would make a simulation-based policy recommendation credible under population and model shift?” |
| 8 | **John Kessler**：Aaru co-founder & CTO | [Aaru公式About](https://aaru.com/about)に本人名、役職、MIT City Science Labでの simulation research、会社の technical research / simulation systems を統括する旨。大規模な人口エージェントの commercial practice から検証上の盲点を聞ける。 | [Aaru公式Contact](https://aaru.com/contact)。本人の公開メールは未確認。公式フッターの billing@aaru.com は請求用途なので研究依頼には採用しない。 | “How do you test predictions for genuinely new changes to resource availability, rather than reproducing correlations from demographic and behavioral training data?” |

### そのまま照合できるメール原文

- Levin：`https://as.tufts.edu/biology/people/faculty/michael-levin` → `michael.levin@tufts.edu`、HTMLに `href="mailto:michael.levin@tufts.edu"`。
- Bernstein：`https://hci.stanford.edu/msb/` → HTMLに `href="mailto:msb@cs.stanford.edu"`。
- Krakauer：`https://www.santafe.edu/people/profile/david-krakauer` → Contactの `Email`、HTMLに `href="mailto:dk@santafe.edu"`。
- Leibo：`https://www.jzleibo.com/` → `jzl [at] deepmind .com`、HTMLに `mailto:jzl@deepmind.com`。
- AgentSociety：`https://arxiv.org/html/2607.11895v2` → `Email: liyong07@tsinghua.edu.cn`。公式READMEの Contact → `Email: agentsociety.fiblab2025@gmail.com`。
- Liangの管理担当：`https://profiles.stanford.edu/percy-liang` → `Contact Administrator Suzanne Lessard Administrative Associate slessard@stanford.edu`。本人直接メールではない。

## 論文・サービスをどう読むか

1. **Generative Agents (2023)**：[論文](https://arxiv.org/abs/2304.03442)。25エージェントの believable behavior と構成要素の評価が中心。「自然な物語が出る」ことを現実の社会政策の因果効果や人間の将来予測の検証と同一視しない。
2. **個人シミュレーション (2024、現行題名更新あり)**：[論文](https://arxiv.org/abs/2411.10109)。実在者1,052人のインタビューと測定課題による接地。よく引用される85%は人間自身の再テスト精度を基準にした数字であり、全状況の絶対予測精度や85%の政策成功率ではない。調査課題の再現から、長期行動、希少事象、制度変更への一般化は追加検証が要る。
3. **AgentSociety / AgentSociety 2**：[v1](https://arxiv.org/abs/2502.08691)、[v2](https://arxiv.org/abs/2607.11895)。v1は1万人規模のエージェントと複数社会問題、v2は実行可能な社会科学研究の統合基盤。大規模化・既存実験の再現・分析自動化は別の成果。Managerによる介入の現実での効果や因果同定を、それだけで認証するものではない。v2のHTMLでは project-lead記号が崩れているため、先頭著者だけから正式責任者を断定せず、連絡先が明示された corresponding authorを使う。
4. **Concordia**：[公式リポジトリ](https://github.com/google-deepmind/concordia)、[Leiboの本人説明](https://www.jzleibo.com/)。game master と agents の自然言語相互作用に加えて資源量などをコードで接地できる。世界の解釈・状態遷移をLLMに任せた部分が結果を作っていないか確認する。現実意思決定の根拠に使う時の証拠水準は、探索／pilot設計に使う時より高い。
5. **Levin / Krakauer**：TAMEや個体性・exbodimentはManagerの仮説と測定を整理する理論的参照。生体の集団知能や情報論的個体性を、そのままAIのagency、意識、AGIの証明へ移し替えない。
6. **企業の性能主張**：Simileの検証数・確信度、Synthetic Usersのsynthetic-organic parity、Aaruの予測優位は公式サイト上の説明として扱う。評価データ、比較条件、外部検証を確認せずに研究論文の結果やManagerの見込みへ転用しない。

最初に送る付属資料は1ページで十分：対象領域1つ、変更可能な供給／アクセス／ルール、観測できる受益と害、介入権限、ログイン不要の意味、シミュレーション比較条件、外部検証に失敗したら中止する基準。一般的な未来論より「この評価設計は何を見落としているか」に絞る。

## 追加企業の確認結果

- **Primitive Labs**：[公式](https://primitivelabs.ai/)は「human behaviorをsoftware developmentのfirst-class primitiveにする」と説明し、Tokyo / San Francisco / São Pauloを掲載。[公式Contact](https://primitivelabs.ai/contact)を再取得し問い合わせフォーム確認。Instinctは顧客視点のjourney review、accessibility、frictionなどでManagerの構造評価に関連するが、今回の公式公開ページから創業者氏名は確定できなかった。確認済みの人物8名とは分ける。
- **Synthetic Users**：[公式](https://www.syntheticusers.com/)は探索・仮説検証のsynthetic interviews、実ユーザー調査との比較を説明。ホームの公開導線 “Book demo” は確認できるが、今回取得したページでは創業者氏名と直接メールを確認できず。顧客の “Founding Team” 表記をこの会社の創業者と誤認しない。
- **Tenera**：`https://www.tenera.ai/` は今回の応答が `/lander` へ飛ぶ短いscriptで、想定する企業・創業者・研究内容を確定できない。同名企業がある可能性もあるため保留。別URLの確認前に人物や連絡先を補完しない。

## 英文の短い依頼文6通（送信前のローカル文案）

差出人は親タスクで確認された **Daisuke Narita**。この文書自体はメールボックスに下書きを作成していない。肩書、所属、番組名、視聴者数、稼働デモは足していない。初回は短い非公開の技術フィードバック依頼が自然。録音は相手の同意後に扱う。

### 1. Michael Levin

Subject: A testable question about environment-supported collective agency

Dear Professor Levin,

I’m Daisuke Narita, exploring an early concept called Manager: ambient AI that would improve shared supply, access, or rules without requiring beneficiaries to log in or provide credentials. I’m currently working on the design and reviewing related code, rather than claiming a working system or demonstrated impact.

Your TAME framework prompted a question: what experimentally testable criterion distinguishes an environment that facilitates existing goals from one that supports a new level of collective agency?

Would you be open to a short reply or a 20-minute research conversation? I can send a one-page description and proposed evaluation.

Best,
Daisuke Narita

### 2. Michael Bernstein

Subject: Evaluating benefits for people who never use an AI system

Dear Professor Bernstein,

I’m Daisuke Narita. I’m developing the design for Manager, an ambient AI concept that would change shared supply, access, or rules without requiring beneficiaries to use an app or provide credentials. I’m reviewing simulation frameworks; I do not yet have evidence that the concept works.

Your work on generative agents and human-centered systems seems especially relevant. What evaluation would demonstrate benefits to non-users while detecting unequal or unwanted effects of a shared-rule change?

Would you be willing to give brief technical feedback on a one-page proposal, or discuss it for 20 minutes?

Best,
Daisuke Narita

### 3. David Krakauer

Subject: Measuring intelligence in shared infrastructure

Dear Professor Krakauer,

I’m Daisuke Narita, exploring an early ambient AI concept called Manager. The aim is to improve people’s surrounding supply, access, or institutional rules without requiring beneficiary accounts or credentials. The work is at the design and code-review stage, with no demonstrated real-world impact.

Your research on exbodiment raises the question I’m trying to make measurable: how could we distinguish improved individual performance from a more capable social system after changing shared infrastructure?

Would you be open to a short research conversation or brief feedback on a one-page evaluation outline?

Best,
Daisuke Narita

### 4. Joel Z. Leibo

Subject: Testing structural interventions with Concordia

Dear Dr. Leibo,

I’m Daisuke Narita. I’m reviewing Concordia while designing Manager, an early ambient AI concept intended to improve shared supply, access, or rules without beneficiary logins or credentials. I’m seeking an evaluation method, not claiming a validated system.

How would you separate an intervention’s effects on resource access or institutional rules from prompt-induced cooperation, then test generalization to new populations?

Would you be open to brief technical feedback or a 20-minute conversation? I can send one bounded scenario and its proposed baselines.

Best,
Daisuke Narita

### 5. Joon Sung Park（正式取次経路確認後／企業窓口用）

Subject: A validation question about structural changes in agent simulations

Dear Dr. Park,

I’m Daisuke Narita, exploring Manager: an early ambient AI concept that would improve shared supply, access, or rules without requiring beneficiary accounts or credentials. I’m working on the design and reviewing related code; I do not have a validated intervention.

Your interview-grounded agent research leads to a specific question: what held-out human study would establish whether agents predict effects of actual changes in supply or access, rather than only changes in wording?

Would you be open to brief feedback or a short research conversation? If this reaches the Simile team, I would appreciate guidance on the appropriate research contact.

Best,
Daisuke Narita

### 6. Yong Li / AgentSociety team

Subject: Comparing structural and information-only interventions in AgentSociety

Dear Professor Li and the AgentSociety team,

I’m Daisuke Narita. I’m reviewing AgentSociety for an early project concept, Manager: ambient AI intended to improve shared supply, access, or rules without beneficiary logins or credentials. I’m currently designing the evaluation and inspecting related code.

Which environment variables and validation targets would you use to compare a supply/access intervention with an information-only intervention, without putting the desired outcome into the agents’ prompts?

Would you be open to a short reply or a 20-minute technical discussion? I can provide a one-page scenario and comparison design.

Best,
Daisuke Narita

### ポッドキャスト向け対話の扱い

現時点では番組名・公開状況・聴衆規模が不明なので、上記は研究対話として成立する文面にした。公開インタビューを望む場合だけ最後の段落を次で置き換える（既存番組の実績を示唆しない）：

> I’m considering a recorded interview for a podcast project about AI and social systems. Would you be open to an initial 20-minute conversation? Any recording and publication would be agreed with you in advance.

## 日付を確認できた今後のイベント

- **NexTech Week 秋 / AI・人工知能EXPO**：2026年11月11–13日、**幕張メッセ（千葉）**。[主催者公式](https://www.ai-expo.jp/autumn/en-gb.html)はこの日付と会場を明示。東京圏の実装先・企業との接点にはなるが、東京開催とは書かない。理論研究の小規模会合ではなく商業展示会で、上記研究者の登壇・参加は未確認。
- **NexTech Week 春**：2027年4月21–23日、**東京ビッグサイト**。[主催者公式](https://www.nextech-week.jp/spring/ja-jp.html)。Managerの供給／運用面について企業に具体的シナリオを相談する接点。参加登録・応募はしていない。
- **オンライン**：今回確認した[SFI公式イベント一覧](https://www.santafe.edu/events)では静的取得から開催日・オンライン参加条件を確定できなかったため、確定イベントとして載せない。終了済みのCHI2025等を今後の機会に数えない。網羅的イベント検索ではない。

この調査では連絡・フォーム送信・ログイン・応募・外部アプリの下書き作成はしていない。ここにある依頼文の送信者情報や実際の発信は親タスク側の確認と処理に委ねる。


## 親タスクの処理結果

2026-10-08、Levin/Bernstein/Krakauer/Leibo宛ての個別Gmail下書き4通を作成し、宛先・件名・DRAFTラベルを公式一覧で確認した。未送信。個人メールボックスの識別子はGitへ保存しない。Park/Liang/Kessler宛ては正式な取次経路を使い、本人アドレスを推測しない。
