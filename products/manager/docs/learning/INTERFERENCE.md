# L010 — 干渉（interference）と資源の移転

原著：Hernán & Robins, *Causal Inference: What If* https://miguelhernan.org/whatifbook ; donation-matching実地実験 Karlan & List https://www.aeaweb.org/articles?id=10.1257/aer.97.5.1774

通常の個人間独立の効果計算では、Aという対象への介入がBという対象の結果を変えない、という**非干渉の仮定**を置くことがある。寄付や支援資源には競合があり、他の支援先からお金が移っただけかもしれない。

**完全な架空の資金勘定**：支援先Aは+100、他団体では-90、介入運営費20 → `100 + (-90) - 20 = -10`。Aだけ見ると大成功でも、全体では純資源が-10になりうる。

`manager_core/spillover.py`は、**すでに変化量が正しく識別・観測されたと仮定した場合の単純会計**であり、実データの因果効果を推定する関数ではない。知らない他団体の影響を0と仮定して利益を捏造してはいけない。

`python3 -m examples.05_spillover`
