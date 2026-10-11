# 世界モデル比較：World Labs／Fei-Fei Li と LeCun／JEPA

調査基準日：2026-10-11。一次資料を直接取得した範囲に限定する。以下の2026年情報は取得した公式ページ本文に基づく。企業ブログの成果主張と独立検証済みの事実は区別する。Manager は人間の行動・社会・制度に働きかけるシステムとして扱う。

## 結論

共通する世界モデルの核は、観測の背後の状態や構造を表し、見えていない部分・将来・行動後を予測して意思決定を支えること。必ずしも明示的3D、映像生成、ロボットを要件としない。

World Labs は空間を共有文脈として、生成・再構成・シミュレーションを統合する方向。LeCun は行動に必要な抽象表現を学び、予測器と目的／コストを使って計画する方向。これは「物理対社会」の二分法ではない。JEPA の研究実装が現在主に画像・動画・ロボットを使っていることと、汎用の自律機械知能という構想の適用範囲は別である。

2026年10月時点の World Labs を Marble の静的3D生成だけで説明すると古い。Atlas と R2S2R の公式資料には時間・動力学・現実との方策比較がある。一方、これらも社会的介入の有効性の証明ではない。

## 比較

| 観点 | World Labs | LeCun／JEPA 系列 |
|---|---|---|
| 入力 | Marble: テキスト・画像・動画・空間スケッチ。Atlas: テキスト・画像・カメラ姿勢・深度、動画は画像列 | I-JEPA: 静止画像。V-JEPA: 動画。V-JEPA 2: 動画・画像で事前学習、制御向け追加学習はロボット観測と行動 |
| 状態／表現 | Marble: 探索できる永続的3D環境、Gaussian splats と collision mesh。Atlas: 入力を3Dに接地した spatial context、明示的深度／3Dと生成画像 | 学習された埋め込み空間。明示的3Dメッシュを必須とせず、課題に必要な抽象情報を保持 |
| 学習目的 | Marble の発表だけでは詳細損失・データ構成は公開されない。Atlas は自己回帰 diffusion transformer／rectified flow、条件付き多モーダル生成 | 観測文脈から隠れた領域の target embedding を予測。画素の完全再構成を目的にしない。V-JEPA 2 は actionless と action-conditioned の2段階 |
| 行動との関係 | カメラ操作／空間編集と、物体への介入は区別。R2S2R は観測・動力学を合わせ、方策訓練と検証の環境を供給 | I-JEPA は静的な欠損領域予測。V-JEPA は主に知覚。V-JEPA 2 の行動条件付き予測器は候補行動の結果を予測して制御に利用 |
| 計画 | 2026 taxonomy は renderer／simulator／planner を機能として区別。Atlas が全ての一般計画を実証済みとは言えない | V-JEPA 2 は現在画像と目標画像の埋め込みを比較し、候補行動を評価、再計画して次の行動を実行する MPC。長い課題では画像サブゴール列 |
| 評価 | Atlas: カメラ経路追従の人間選好、3D再構成。R2S2R: sim/realの挙動・成否境界・方策ランキング | I-JEPA: 視覚表現／低ショット分類など。V-JEPA: frozen encoder に小さな読出しを加えた認識評価。V-JEPA 2: 認識・行動予測・動画QA・物理推論・ロボット到達／把持／配置 |

### JEPA は動画生成の別名ではない

Meta の2024年発表は V-JEPA を明示的に “non-generative model” と呼ぶ。予測対象は映像画素ではなく抽象表現。木の葉一枚ごとの揺れなど不要で予測不能な詳細を省き、意味や動作の予測に資源を使う。その表現を別の decoder で可視化しても、JEPA 自体の学習目的が動画生成になるわけではない。Atlas も latent を使うため「latent を使う／使わない」は差ではない。違いは、生成可能な画像・幾何へ復号することを中心に据えるか、意思決定に有用な表現の予測を中心に据えるかにある。

### 世代ごとの実証範囲を混ぜない

I-JEPA（2023）は同一画像の一部から他の領域の表現を予測する制限された原始的世界モデル。V-JEPA（2024）は動画の時空間マスク予測で、Meta 自身が当時の研究を主に perception と説明し、長期計画を次の課題にした。V-JEPA 2（2025）は100万時間超の動画と100万画像で actionless 事前学習し、62時間のロボットデータによる追加学習で行動条件を導入。公式ブログの65–80%は未見の物体／環境における特定 pick-and-place 実験の成功率で、一般的な人間社会への介入能力ではない。「zero-shot」はその配備先環境などの訓練を使わない意味であり、行動データを全く使わない意味ではない。

World Labs の R2S2R（2026-07-28）は、実タスクの計測・再構成からシミュレーションを作り、その中だけで訓練した方策をハードウェアへ移す主張。従って “zero real-world training data” は方策の訓練についてであり、現実のタスクを観測せず世界モデルを作る意味ではない。方策評価では checkpoint ごとに2,000 simulated trials（ID/OOD各1,000）と100 real-world trials（各50）を報告。シミュレーションの絶対成功率一致より、方策順位・改善／停滞・失敗領域が現実と一致することを重視する。この評価思想は Manager に参考になるが、物理ロボットでの企業実験から社会へ結果を移植はできない。

## Manager に必要な追加条件

「人間・社会・制度を含む世界モデル」は概念的に両者と矛盾しない。潜在状態は位置や速度だけでなく、意図、信念、権限、資源、関係、規範、ルール、組織履歴を含み得る。しかし意味が分かること、次の言動が予測できること、変更すると何が起こるかが分かること、現実で良い結果が出ることは別の検証事項。

1. **意味理解**：何が起きたか、誰が何を求めているかを認識する。
2. **観測予測**：従来の方針・データ分布の下で次の反応を予測する。
3. **介入の妥当性**：通知、報酬、役割、制度を変えた場合の結果を、交絡・選択・他者の反応・波及・適応を考慮して比較する。
4. **現実の効果**：事前に定義した指標・対象・期間で実施し、対照比較や他の適切な因果評価、害・分配・持続性・予測誤差を測る。

JEPA の embedding に意味的特徴があることは、社会の因果構造や政策の識別可能性の証明ではない。action-conditioned 学習も、行動割当てに交絡があれば介入効果を保証しない。もっともらしい LLM エージェントの会話、見栄えのよい世界、高い予測精度も同様。Manager では信念状態・不確実性を持ち、実際に利用できる介入範囲を明確にし、予測→候補比較→限定実施→現実測定→更新のループを作る必要がある。World Labs の sim/real の方策順位照合を社会版へ翻訳するなら、複数の候補施策の予測順位が対象集団・期間で現実の効果順位と合うかを確かめる。ただし順位だけでも公平性や絶対的害は評価できない。

## 一次資料と日付／版

- World Labs, “Generating Worlds”, 2024-12-02: https://www.worldlabs.ai/blog/generating-worlds
- World Labs, “Marble: A Multimodal World Model”, 2025-11-12: https://www.worldlabs.ai/blog/marble-world-model
- World Labs, “A Functional Taxonomy of World Models”, 2026-06-03: https://www.worldlabs.ai/blog/taxonomy-of-world-models （renderer／simulator／planner は同社の機能分類であり、学界統一規格ではない）
- World Labs, “Building Worlds That Train Robots”, 2026-07-28: https://www.worldlabs.ai/blog/real-to-sim-to-real
- World Labs, “Atlas: A World Model for Spatial Intelligence”, 2026-09-01: https://www.worldlabs.ai/blog/atlas （アーキテクチャ・評価は公式記事に基づく。公開製品 availability と研究能力は同一視しない）
- World Labs, “World Labs is Joining AMD”, 2026-09-28: https://www.worldlabs.ai/blog/amd-announcement （definitive agreement を署名、2026年末までの close を予定し規制承認等が条件。10月11日で買収完了とは書かない）
- Yann LeCun, “A Path Towards Autonomous Machine Intelligence”, 2022 proposal: https://openreview.net/forum?id=BZ5a1r-kVsf / https://openreview.net/pdf?id=BZ5a1r-kVsf （今回直接取得は403／challenge。構想・JEPAの位置づけは下記 Meta の一次解説で裏づけ、原稿を読了したとは扱わない）
- Meta, “I-JEPA: The first AI model based on Yann LeCun’s vision for more human-like AI”, 2023-06-13: https://ai.meta.com/blog/yann-lecun-ai-model-i-jepa/
- Assran et al., “Self-Supervised Learning from Images with a Joint-Embedding Predictive Architecture”, arXiv original 2023-01-19, CVPR 2023: https://arxiv.org/abs/2301.08243 （取得した abstract ページは最新改訂表示。版間差を本稿で検証していない）
- Meta, “V-JEPA: The next step toward Yann LeCun’s vision of advanced machine intelligence (AMI)”, 2024-02-15: https://ai.meta.com/blog/v-jepa-yann-lecun-ai-model-video-joint-embedding-predictive-architecture/
- Bardes et al., “Revisiting Feature Prediction for Learning Visual Representations from Video”, arXiv original 2024-02-05: https://arxiv.org/abs/2402.03300
- Meta, “V-JEPA 2: Our new world model …”, 2025-06-11: https://ai.meta.com/blog/v-jepa-2-world-model-benchmarks/
- Assran et al., “V-JEPA 2: Self-Supervised Video Models Enable Understanding, Prediction and Planning”, arXiv v1, 2025-06-11: https://arxiv.org/html/2506.09985v1 （HTML本文取得）

AMI は Meta の資料では advanced machine intelligence の略であり、それだけで現行の同名会社・所属を証明しない。今回調べた amilabs.ai は一般的な Launching Soon、ami-labs.com は化粧品研究ラボ、amintelligence.ai は AM Green と表示され、LeCun企業の一次証拠として採用できなかった。現在の会社名／創業／調達／公開モデルは未確認として残す。

取得原文：`/workspace/scratch/manager-research/raw/oct11/world-models/`。HTMLと抽出txtを保存。失敗したURLと類似名サイトは未確認調査の記録であり引用証拠にしない。
