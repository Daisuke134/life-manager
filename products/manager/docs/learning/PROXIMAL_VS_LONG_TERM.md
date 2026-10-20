# L009 — 近接アウトカムと長期的な健康・苦しみ

出典：Nahum-Shaniら https://pmc.ncbi.nlm.nih.gov/articles/PMC5364076/ ; HeartSteps https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/

- proximal: 提案後**30分**という短い時間窓で測る「歩数」。これは行動介入の局所的効果。
- distal: 長期的な健康や生活の改善。研究の介入実施期間の**6週間（42日）**をそのまま臨床的な健康効果の証拠としない。
- 欠測: 計測不能はゼロではない。どのセンサー・どの時間窓の指標なのかを固定。

`manager_core/outcome_windows.py`は、測定対象・期間・ソース・欠測の一致を検査する。30分の歩数を42日の健康成果として問い合わせてもFalseになる。`causal_established=False`なら、たとえ値が記録されていても因果的な成果だとは認証できない。

Managerでも「資金が送れた」≠「受益者の経済状態改善」、「PM2.5が下がった」≠「臨床的な病気が減った」。
