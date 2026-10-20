# imozuru map: LLM behavioral simulation causal fidelity — R005

問い: 人間に似たシミュレーションは、現実の介入効果まで正確に予測できるのか。

## 要る主張
- [x] この分野の知見はどこにあるか — arXivとSci Adv/Nature Human Behaviour、Stanford SocSci210などの元論文・データの場を確認
- [x] 評価対象が実在した人間の無作為化実験か — sources/population.md
- [x] ベースラインでの記述的精度と因果誤差がどれだけ違うか — sources/baseline.md
- [x] プロンプト改善でも介入効果推定が悪化する具体的な数字があるか — sources/failure.md
- [x] どの介入機構で差が大きいか — sources/mechanism.md
- [ ] 気候以外でも同じ結果が成り立つか — 未検証、R005の限界

## 用語
- Descriptive fit（集団平均・回答パターンの記述再現性）
- Causal fidelity（実際の介入効果との一致）
- ATE, MAE, signed ATE error, absolute ATE error
- Situational simulation, deductive reasoning, cultural/group norms
- Few-shot, VBN-CoT, calibration, generalization

## 人
- Zonghan Li, Feng Ji — 本研究、Toronto
- Madalina Vlasceanuほか — ICCP元実験
- Tobia Spampattiほか — 気候偽情報への心理的接種
- Bence Većkalovほか — 科学的合意メッセージ
- Akaash Kolluri, Joon Sung Park, Michael Bernstein — SocSci210（比較領域）

## 場
- arXiv — LLM行動シミュレーション原論文
- Science Advances / Nature Human Behaviour — 元の無作為化介入実験
- ACL Anthology / GitHub — SocSci210と公開コード

## 原文の位置（短い抜き書きのみ）
| 資料 | 保存済みファイル | 原著URL | 追跡 |
|---|---|---|---|
| 〔論文〕Li & Ji sample | sources/population.md | https://arxiv.org/html/2604.02458v1 | 1周目・本文 |
| 〔論文〕Li & Ji ATE baseline | sources/baseline.md | https://arxiv.org/html/2604.02458v1 | 1周目・Fig 2 |
| 〔論文〕Li & Ji few-shot failure | sources/failure.md | https://arxiv.org/html/2604.02458v1 | 1周目・Fig 2 |
| 〔論文〕Li & Ji mechanism bias | sources/mechanism.md | https://arxiv.org/html/2604.02458v1 | 1周目・Fig 4 |
| 〔論文〕Vlasceanu original | URLのみ | https://pubmed.ncbi.nlm.nih.gov/38324680/ | 1周目・Li & Ji reference |
| 〔論文〕Spampatti original | URLのみ | https://pubmed.ncbi.nlm.nih.gov/38036655/ | 1周目・Li & Ji reference |
| 〔論文〕Većkalov original | URLのみ | https://pubmed.ncbi.nlm.nih.gov/39187712/ | 1周目・Li & Ji reference |
| 〔論文〕Kolluri SocSci210 | URLのみ | https://aclanthology.org/2025.emnlp-main.1530/ | 1周目・比較研究 |

## 次の手がかり
- Li & Jiが報告する元ICCP62か国/59,508人と、Vlasceanu原著63か国/59,440人の不一致を論文コードや正誤表で確認する
- 気候以外（金融/健康/社会支援）で「記述→因果」推定の未知領域誤差を独立検証する
- GPT-4o-mini/Gemini Flash Lite/Claude 3 Haiku以外の行動モデルとファインチューニングモデルでの比較
- 個人の非公開データ不要の集計評価設計を具体化する
