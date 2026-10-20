# L007 — なぜ無作為化するのか

原著：HeartSteps https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ ; Hernán & Robins https://miguelhernan.org/whatifbook

無作為割付は、介入を受ける人がもともとやる気がある、といった選択バイアスを抑えるための研究設計。`manager_core/randomization.py` では、固定seedの二値無作為割付を実装した。合成データの真のATEを2と決めておき、観測された二群平均差が試行数を増やすと近づくことを確認する。

これだけで実世界の因果が完全に解決するわけではない。干渉、途中離脱、欠測、割付不履行、測定の妥当性、十分な件数が必要。

`python3 -m examples.04_randomization`
