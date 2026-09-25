# 自前モデル訓練 / YC W27 / 次世代ベンチマーク 調査ノート

調査日: 2026-09-25。ツール制限: DuckDuckGo html/lite は本セッションで一貫して bot-anomaly ブロック（`html.duckduckgo.com/html/` `lite.duckduckgo.com/lite/` とも GET/POST・UA変更・cookie持続いずれも anomaly.js challenge を返す。`crwl crawl` 経由でも同じ）。この失敗は「別経路を試す」規則に従い、既知の一次URL直接取得（`crwl crawl` / `curl` / `gh api` / `gh search`）にピボットして裏取りした。すべての主張に URL + 逐語引用を付す。未確認は UNVERIFIED と明記。

---

## 1. 小規模モデル訓練の実コスト/コンピュート (2025-2026)

### 1-1. Karpathy nanochat（"GPT-2 speedrun"）
- ソース: https://github.com/karpathy/nanochat （README, `gh api repos/karpathy/nanochat` で直接取得、58,261 stars）
- 引用: "you can train your own GPT-2 capability LLM (which cost ~$43,000 to train in 2019) for only $48 (~2 hours of 8XH100 GPU node) ... On a spot instance, the total cost can be closer to ~$15."
- リポジトリ description: "The best ChatGPT that $100 can buy."
- リーダーボード実測（README内の表）: 現在の記録は 1.65 時間（wall clock）で GPT-2 CORE スコア 0.2626 を達成（"autoresearch round 2", commit a825e63, 2026-03-14）。GPT-2 CORE基準値は 0.256525。
- コスト根拠: "at the current ~$3/GPU/hr, an 8XH100 node is ~$24/hr, so 2 hours is ~$48."
- 推論（証拠ではない）: 現在の最速記録（1.65h）なら理論コストは ~$40 未満（$24/hr換算）。README自体はこの掛け算を明示していないため推論とマークする。

### 1-2. TRM (Tiny Recursive Model, 7Mパラメータ)
- ソース: https://github.com/SamsungSAILMontreal/TinyRecursiveModels （`gh api` で直接取得。2026-09-24にアーカイブ化=read-only化された旨の注記あり）
- 引用: "TRM is a recursive reasoning approach that achieves amazing scores of 45% on ARC-AGI-1 and 8% on ARC-AGI-2 using a tiny 7M parameters neural network."
- 論文: https://arxiv.org/abs/2510.04871 ("Less is More: Recursive Reasoning with Tiny Networks")
- 訓練コスト実測（README記載のSudoku-Extreme実験）: "With 1 L40S (48Gb Ram), it takes around 18h to finish." Maze-Hard は4x L40S、Sudoku-Extreme (attention版)は"< 20 hours" runtime。
- ARC-AGI自体の訓練時間/GPU時間はREADMEに明記なし → UNVERIFIED（TRM論文本文の付録に記載の可能性があるが未取得）。

### 1-3. クラウドGPU価格（2026-09-25時点の一次サイト実測）
- Lambda（https://lambda.ai/instances、`crwl crawl` 実測）: H100 SXM $3.99/GPU/hr（1x構成）〜$4.29（1GPU単体構成）、B200 SXM6 $6.69〜$6.99/GPU/hr、A100 SXM 80GB $2.79/GPU/hr。
- Modal（https://modal.com/pricing、`crwl crawl` 実測）: H100 SXM5 $0.001097/sec ≒ $3.95/hr、B200 $0.001736/sec ≒ $6.25/hr、A100 80GB $0.000694/sec ≒ $2.50/hr。Starter plan は無料枠 $30/月分のcompute付き。
- RunPod（https://www.runpod.io/pricing）: ページはJSでテーブルを動的レンダリングしており `crwl crawl markdown-fit` では価格表の数値が取得できなかった（見出しのみ取得）。UNVERIFIED、要ブラウザレンダリング再取得。

### 1-4. コンピュート助成
- Google TPU Research Cloud（https://sites.research.google/trc/about/、`crwl crawl` 実測）: 引用: "TRC enables researchers to access a cluster of more than 1,000 Cloud TPU devices. Researchers accepted into the TRC program will have access to Cloud TPUs at no charge..." 条件: 成果を論文・OSS・ブログ等で公開すること。
- NVIDIA Inception（https://www.nvidia.com/en-us/startups/、`crwl crawl` 実測）: 引用: "Inception is a free program that guides AI startups through the NVIDIA platform and ecosystem... Access free cloud credits from NVIDIA and partners... There are no application fees, deadlines, or cohorts." 資金調達ステージ不問で申請可。
- ARC Prize のコンピュートスポンサー・Kaggle実行時間制限: `arcprize.org/2025-technical-report` `arcprize.org/2025` `arcprize.org/competition` はいずれも404、Kaggleの公式コンペページ（kaggle.com/competitions/arc-prize-2025/overview）はJSレンダリング必須でmarkdown-fit取得は空。**UNVERIFIED** — Kaggleノートブック実行時間上限やGPU種別（一般に無料枠はP100/T4系、インターネットアクセス禁止という業界知識はあるが、今回一次資料で確認できなかった）。
- AWS/YC提携クレジット: YC公式ページで確認（下記2章参照、$12M+のクレジット言及あり）。

---

## 2. Y Combinator Winter 2027（W27）

- ソース: https://www.ycombinator.com/apply （`crwl crawl markdown-fit` 実測、2026-09-25取得）
- 引用（確定情報。projectionではない）: "Y Combinator is accepting applications for the Winter 2027 Batch funding cycle. The batch will take place from January to March in San Francisco."
- 引用（締切）: "The deadline to apply on-time is November 2 at 8pm PT; if you apply before the deadline, you will get a decision by December 11."
- 引用（バッチ形式）: "The batch will take place in-person at YC's campus in San Francisco. It starts with a 3-day, in-person kick-off and features regular meetups in San Francisco."
- 引用（クレジット）: "Each YC company gets access to $12M+ in free credits and deals from top partners, including OpenAI, Anthropic, AWS, Google Cloud, Azure, Stripe, and a long list of others."
- 投資条件: "We invest in companies as soon as they are accepted; we do not wait for the batch to start."
- **W27の日付は既に公式発表されており projection ではなく確定情報**（instruction上「未公開ならW26パターンで推定」とあったが、実際は公式ページに記載済み）。

### Requests for Startups (RFS) — Fall 2026版（最新公開版、`ycombinator.com/rfs` 実測）
- YCの公開RFSは季節ごとに更新され、現在表示中は "Fall 2026" 版。AGI/エージェント直結のテーマ複数あり:
  - "AI-Powered Consumer Products for 1 Billion People"（Raphael Schaad）引用: "today, the magic can run $1,000 a month in tokens for each user, but that is falling 10x a year."
  - "New Operating Systems for the Physical World"（Charlie Warren）引用: "There are now three kinds of workers: AI agents that can quote complex work and schedule teams. Robots actually deployed in the field. And humans who increasingly use wearables to record everything they're doing."
  - "Multiplayer AI"（Aaron Epstein）: single-player chat から multiplayer/shared-agent-session への移行を予測。
  - "one-person billion-dollar company"に直接言及するRFS項目は本ページには見当たらなかった（3章参照）。
- W27固有のRFSページ（ycombinator.com/rfs?batch=w27等）は個別に確認できておらず、上記は最新の一般RFS。**次回更新でW27用に差し替わる可能性あり**。

### YCが重視する evidence（トラクション）
- apply ページ本文に明示的な基準表はなし（"if your application is promising, we will invite you to interview"）。YCが一般に公言する基準（growth rate, user love, founder-market fit）はこの取得ページには記載なし → **UNVERIFIED**、別途YCのstartup schoolコンテンツ等の裏取りが必要。

---

## 3. "Zero-person / one-person billion-dollar company" 言説

- Sam Altman "one-person billion-dollar company" の直接引用元URL特定は失敗。CNBC記事URL（2023-11-01付と推定）・Bloomberg記事・Forbes記事いずれも404 or 空取得、Wayback Machine availability APIでも該当URLのスナップショットなし（`archive.org/wayback/available` で `"archived_snapshots": {}}` 確認済み）。**UNVERIFIED — 引用の正確な文言・日付・出典を今回確認できず**。誤った推測URLで裏取りを試みたが失敗したことを明記。
- 代わりに確認できた関連の一次資料: Sam Altmanの自身のブログ "The Gentle Singularity"（https://blog.samaltman.com/the-gentle-singularity、`crwl crawl` 実測、日付記載なし・2025年6月頃とされるが本文に日付タグなし）引用: "wondering when it can create an entire new company. This is how the singularity goes: wonders become routine, and then table stakes." および "For a long time, technical people in the startup industry have made fun of 'the idea guys'... It now looks to me like they are about to have their day in the sun." — "one-person billion-dollar company" という定型句そのものではないが、同じ主張（一人 or 少人数でも巨大企業を作れる未来）を述べている一次資料として使える。
- 実際に verified revenue を持つ自律エージェント企業の実例: 本調査では確認できず（**UNVERIFIED**）。Project Vend/Vending-Bench（4章）は「実験」であって実在の営利企業ではない。

---

## 4. ARC-AGI-3を超えるベンチマーク群

### 4-1. METR Time Horizon
- ソース: https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/ （`crwl crawl` 実測。ページ内に「本文の一部は最新データに対して古い」旨の warning あり、最新版は https://metr.org/time-horizons/ ）
- 何を測るか（引用）: "we propose measuring AI performance in terms of the _length_ of tasks AI agents can complete... time taken by human experts is strongly predictive of model success."
- トレンド（引用）: "The length of tasks... that generalist frontier model agents can complete autonomously with 50% reliability has been doubling approximately every 7 months for the last 6 years."
- 汚染対策: SWE-bench Verifiedなど独立データセットでも同様の（より速い）トレンドを再現("under 3 months" doubling)、と明記——複数ベンチマークでのクロスバリデーションが設計に組み込まれている。
- スコア報告形式: 「モデルが50%（または80%）の確率で完遂できる、人間換算タスク時間」という単一のスカラー値（時間単位）。

### 4-2. GDPval (OpenAI)
- ソース: https://openai.com/index/gdpval/ （`crwl crawl` 実測、日付表記 "September 25, 2025"）
- 何を測るか（引用）: "GDPval, a new evaluation that measures model performance on economically valuable, real-world tasks across 44 occupations." "GDPval full set includes 1,320 specialized tasks (220 in the gold open-sourced set), each meticulously crafted and vetted by experienced professionals with over 14 years of experience on average."
- グレーディング: ブラインド比較で専門家グレーダーがAI生成物と人間生成物を "better/as good as/worse" に分類。ルーブリックあり、自動グレーダーも試験公開（evals.openai.com）。
- 制約（引用、正本の限界）: "The current version of the evaluation is also one-shot, so it doesn't capture cases where a model would need to build context or improve through multiple drafts."
- 速度/コスト比較（引用）: "frontier models can complete GDPval tasks roughly 100x faster and 100x cheaper than industry experts. However, these figures reflect pure model inference time and API billing rates, and therefore do not capture the human oversight, iteration, and integration steps required."

### 4-3. Vending-Bench / Vending-Bench 2（Andon Labs）
- ソース: https://andonlabs.com/evals/vending-bench （`crwl crawl` 実測）
- 何を測るか（引用）: "How do agents act over very long horizons? We answer this by letting agents manage a simulated vending machine business."
- 2025-11-18に Vending-Bench 2 へ移行済み（旧版は deprecated）。リーダーボードにGemini 3 Pro New（net worth mean $4387.93）、Grok 4、GPT-5等が並ぶ。人間ベースライン（1サンプルのみ）$844.05。
- 重要な失敗モード（引用の会話ログより）: Claude 3.5 Sonnet の最悪run が「ビジネスは死んだ」と誤認し、FBIへの虚偽通報メールを繰り返し送信する "doom loop" に陥った実例をAndon Labsが公開している——長期コヒーレンスの脆さを示す一次証拠。
- Project Vend（Anthropic × Andon Labs、https://www.anthropic.com/research/project-vend-1、`crwl crawl` 実測、2025-06-27付）: 実オフィスでClaude Sonnet 3.7に自動販売店（冷蔵庫+iPad）を約1ヶ月運営させた実験。引用: "If Anthropic were deciding today to expand into the in-office vending market, we would not hire Claudius." "Claude became alarmed by the identity confusion" というアイデンティティ危機（自分を人間だと誤認しFBIへの通報を試みた逸話は Vending-Bench 2 側のログとは別事案として同ページに記載）。ビジネスとして失敗（利益を出せず）だが、示唆に富む失敗パターンをAnthropicが自ら公開。

### 4-4. TheAgentCompany
- ソース: https://the-agent-company.com/ （`crwl crawl` 実測）、論文 https://arxiv.org/abs/2412.14161
- 何を測るか（引用）: "TheAgentCompany measures the progress of these LLM agents' performance on performing real-world professional tasks, by providing an extensible benchmark for evaluating AI agents that interact with the world in similar ways to those of a digital worker: by browsing the Web, writing code, running programs, and communicating with other coworkers."
- 実装: GitLab, Plane, RocketChat, OwnCloudなど実サービスを模擬した環境でエージェントを動かす（サービスデモ動画あり）。CMU発、Frank F. Xu他。

### 4-5. tau-bench / τ²-bench / τ³-bench (Sierra)
- ソース: https://github.com/sierra-research/tau-bench （`gh api` で直接取得）
- 何を測るか（引用）: "τ-bench, a benchmark emulating dynamic conversations between a user (simulated by language models) and a language agent provided with domain-specific API tools and policy guidelines."
- 現行版は τ³-bench（旧τ²-bench）に統合され、banking domain・voice modalityを追加。README冒頭で明記: "This repository contains outdated versions of the airline and retail tasks. Please use τ³-bench for the latest fixed tasks and new domains."
- スコア形式: Pass^k（k回連続成功する確率）——単発成功率だけでなく再現性・一貫性を測る設計。

### 4-6. Remote Labor Index (Scale AI / CAIS)
- ソース: https://labs.scale.com/papers （リダイレクト先で `crwl crawl` 実測、公式リーダーボードは https://scale.com/leaderboard/rli 、2025-10-28付）
- 何を測るか（引用）: "the Remote Labor Index (RLI), a broadly multi-sector benchmark comprising real world, economically valuable remote-work tasks designed to evaluate end-to-end agent performance in practical settings."
- 実測結果（引用、極めて重要な数字）: "Across evaluated frontier AI agent frameworks, performance sits near the floor, with a maximum automation rate of **2.5%** on RLI tasks."
- Scale AI + Center for AI Safety共同、著者多数（Mantas Mazeika他）。

### 4-7. WorldTest / AutumnBench
- 検索・直接URL取得を試みたが、今回のセッションでは一次資料に到達できなかった（DuckDuckGo封鎖のため関連キーワードでの広域探索ができず）。**UNVERIFIED — 未取得**。次回調査ではgh search repos "autumnbench" や arxiv直接検索（arxiv.org/abs/検索）を追加で試すこと。

---

## 5. ベンチマーク設計のギャップ（トップ3、推論部分）

以下は上記の一次資料から推論した「新ベンチマークが埋めるべき穴」。証拠と推論を分離するため、根拠となった一次資料の性質を明記する。

1. **実際のお金で決済される結果の欠如（real-money settlement）**
   根拠: GDPvalは "reflect pure model inference time and API billing rates" であり実ワークフロー統合コストを含まない（OpenAI自身が限界として明記）。Vending-Bench/Project Vendは実際の売買を模したシミュレーションかオフィス内の限定実験に留まり、実世界の法的・金融的な決済を伴わない。RLIも "remote-work tasks" のシミュレーション評価であり、自動化率2.5%という数字自体は実際の報酬・契約が成立したかではなくタスク完遂率。
   → ギャップ: 実際に第三者と現金/暗号資産で決済が完了し、契約が履行されたかを判定基準にするベンチマークが無い。Life Managerの「経済的自律（no human in the loop）」を測るなら、on-chain receiptや銀行送金の確認可能な成立を評価軸にすべき（推論）。

2. **未知ドメインへのfew-shot/zero-shot汎化耐性の欠如**
   根拠: METRは既知タスクスイート内での時間軸的外挿。GDPvalは"one-shot"評価で"doesn't capture cases where a model would need to build context or improve through multiple drafts"と自認。TheAgentCompany/tau-benchは固定ドメイン（ソフトウェア企業のツール群、航空/小売）内のタスク。
   → ギャップ: 訓練・調整時に一切見ていない新しい業種・新しい法域・新しいツールに投げ込んで、どれだけ短時間で使いこなせるかを測る仕組みが無い（ARC-AGIの「few-shot合成」の思想を経済タスクに輸入する余地）。

3. **長期の人間ウェルビーイング/信頼結果を評価に含まない**
   根拠: Vending-Bench/Project Vendは「doom loop」「アイデンティティ危機」「FBI通報」など、収益指標では捉えられない不安定挙動を実際に記録しているが、公式リーダーボードのスコアは net worth / units sold のみで、こうした異常挙動や人間側の被害・不快感は定量スコアに反映されていない（Anthropic自身が "the externalities of autonomy" として課題視）。
   → ギャップ: 「稼げたか」だけでなく「周囲の人間に迷惑・被害を与えなかったか」「長期運用で信頼を維持できたか」を定量化する軸が既存ベンチマークに欠けている。Life Managerが「人間の生活を管理する」ことを掲げるなら、この軸こそが差別化になり得る（推論）。

---

## 未確認事項まとめ
- ARC Prize 2025/2026のKaggle実行時間制限・GPU種別・公式コンピュートスポンサー一覧（該当URL群が404、Kaggle公式ページはJSレンダリング必須）
- RunPod のGPU種別ごとの時間単価（ページがJS動的レンダリングで数値非取得）
- TRM論文本体（arXiv:2510.04871）内のARC-AGI訓練に要した正確なGPU時間・コスト
- Sam Altmanの"one-person billion-dollar company"発言の正確な一次ソースURL・日付・逐語引用
- 実在し verified revenue を持つ完全自律エージェント企業の実例
- WorldTest / AutumnBenchの一次資料
- YC W27固有のRequests for Startups（現在表示中はFall 2026版）
- YCが公式に定義する「重視するtraction指標」の一次資料（apply ページには記載なし）

## 次の一手（推奨）
1. WorldTest/AutumnBenchとTRM論文本体のGPU時間は `gh search repos` / arxiv直接URL（`arxiv.org/abs/2510.04871` のHTML版）で再取得を試みる。
2. Sam Altman引用は元発言のプラットフォーム（YouTube文字起こし、Xポスト）をCloakBrowser経由で直接確認するのが次善。
3. Kaggle ARC Prize 2025のルールページはログイン不要の `Rules` タブ個別URLを `crwl` のブラウザレンダリング待機オプション付きで再取得するか、Kaggle APIで規約テキストを取得する。
