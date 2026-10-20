# imozuru R005 探索ログ / 2026-10-20

## 0周目：異なる2方向

### 路線A：著者の成功例から掘る
探索語: descriptive fit / LLM simulation / SocSci210 / model calibration / Simile。
一次資料: https://aclanthology.org/2025.emnlp-main.1530/、https://arxiv.org/abs/2411.10109、https://www.simile.com/blog/confidence。
この段階の資料は主として回答分布の再現・校正に関するもので、**介入による現実の利益の直接証明ではない**。

### 路線B：反例から掘る
探索語: Li Ji 2026 causal fidelity / climate psychology RCT / fewshot harmful ATE errors。
一次資料: https://arxiv.org/html/2604.02458v1。
結果: 介入内容の構造とアウトカム（信念/政策/行動）で精度が異なることを確認。

## 1周目：元の人間実験を参考文献からたどる
1. Li & Jiのベース実験ICCP → https://pubmed.ncbi.nlm.nih.gov/38324680/。本実験は63か国59,440人と説明。Li & Jiと不一致を保持。
2. 独立の気候偽情報実験 → https://pubmed.ncbi.nlm.nih.gov/38036655/（12か国、原研究6,816人）。
3. 科学的合意実験 → https://pubmed.ncbi.nlm.nih.gov/39187712/（27か国、原研究10,527人）。
4. 原著論文Results/Fig.2/Fig.4を詳細に再読し、モデル・介入カテゴリ・結果指標を区別。

## 終了条件と留保
R005の必須主張は原著で確認。探索飽和率は計測しておらず、網羅的ではない。
原著全文および元参加者データの再配布は行わない。著者のソースコードや実験データの直接再解析は未実施。
上流 imozuru スクリプトの fetch.py/chain.py はこのホストでインターネット接続できないため直接実行しない。公式report.pyで**短い保存抜き書きとの一致**のみ自動検査。
