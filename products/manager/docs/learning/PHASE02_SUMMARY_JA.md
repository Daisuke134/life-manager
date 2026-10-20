# Manager Phase02 — 理解と実装の全体像（L001–L012）

**研究目標:** 公開情報から人間・環境の予測を作ることと、実際に世界を変えたこと、その結果が原因を伴う便益であることを、数学的・実装的に区別する。

**事実と境界:** Phase02の実装はすべて架空の小規模データによる教材。Managerは人間に介入していない、自然人に関する非公開データを取得していない、金銭/機器操作/通知/ブログ投稿を実行していない。学習用コードは研究の元著者コードの独立再現ではなく、基本概念の演示にすぎない。

## 順番に何を学び、何をテストしたか

| ID | 技術概念 | 本体コード・資料 | 出した結果 / 合格条件 |
|---|---|---|---|
| L001 | 条件付き確率 P(Y\|X) | examples/01_probability.py | 朝60%, 夕方20%, 全体32%（架空） |
| L002 | TVD, Brier | manager_core/evaluation.py、examples/02_scores.py | TVD 0.20, Brier 0.01/0.81（架空） |
| L003 | 校正と異なる研究単位でのholdout | manager_core/calibration.py、examples/02_calibration.py | 10件の50%予測中5件実現、校正=50%; train/test ID重複は拒否 |
| L004 | JITAIの部品 | docs/learning/JITAI_GLOSSARY.md | Decision point/availability/intervention/tailoring/decision rule/proximalの対応、NO_ACTION |
| L005 | 交絡と因果DAG | manager_core/causal_examples.py、docs/learning/CAUSAL_DAG.md | 相関的な差.8、状況ラベル変更による因果差0の反例 |
| L006 | 潜在結果・反実仮想 | manager_core/potential_outcomes.py、examples/03_potential_outcomes.py | 真値2は完全な架空データだけ。実観測には一方の結果のみ記録 |
| L007 | 無作為化 | manager_core/randomization.py、examples/04_randomization.py | 標本25000で推定1.987、設計上の真値2（架空・固定seed） |
| L008 | MRT | manager_core/mrt_demo.py、docs/learning/MRT.md | 1日5時点、介入可能な時点のみ.4/.3/.3で割付、30分成果窓 |
| L009 | 近接と長期 | manager_core/outcome_windows.py、docs/learning/PROXIMAL_VS_LONG_TERM.md | 30分の歩数は42日後の健康成果を証明しない |
| L010 | 干渉・波及 | manager_core/spillover.py、examples/05_spillover.py | +100 -90 -20 = -10 の資源の移転例（因果推定ではない） |
| L011 | Contextual bandit / MDP / OPE | manager_core/policy_basics.py、docs/learning/DECISION_RULES.md | 既知のpropensityで架空のIPS=1; 未知/ゼロ/支持外は拒否 |
| L012 | 成果の証拠階層 | manager_core/outcome_ladder.py、docs/learning/OUTCOME_LADDER.md | P0-P5; 実行receiptだけではP1、P4には比較/害/不確実性が必要 |

## 既存の専門家・論文の方法を借りた

- Probability calibration: scikit-learn docs https://sklearn.org/stable/modules/calibration.html
- JITAI: Nahum-Shani et al., 2018 https://pmc.ncbi.nlm.nih.gov/articles/PMC5364076/
- MRT and HeartSteps: Klasnja et al. https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ ; Murphy lab FAQ https://people.seas.harvard.edu/~samurphy/JITAI_MRT/faq.html
- Causal identification: Hernán & Robins https://miguelhernan.org/whatifbook
- Off-policy evaluation: Wang, Agarwal, Dudík, 2017 https://proceedings.mlr.press/v70/wang17a.html
- Megastudies: Milkman et al., 2021 https://www.nature.com/articles/s41586-021-04128-4
- imozuru methodology / excerpt verifier: https://github.com/MaryCache/imozuru — local 6 short excerpt checks verified; original scientific validity independently unverified.

## 結果の解釈上の重要な境界

- **TVDやBrierが低い** ≠ 介入効果が当たる。
- **予測の校正** ≠ 行動を変えれば起こる結果を知っている。
- **観測群間差** ≠ 処置効果。交絡とバイアスがある。
- **無作為化** ≠ 必ず健全な実験。干渉・欠測・測定誤りが残りうる。
- **近接結果** ≠ 人の長期的便益。
- **送金/デバイス操作の成功** ≠ 人が受けた純便益。
- **計算したIPS** ≠ 未知の割付確率やサポートの欠落を解決。
- **P0-P5フラグ検査** ≠ 実証研究としての質を自動審査したということ。

## 次のフェーズへ渡すもの

Phase03 H001–H010: HeartStepsの公開生データの利用条件・列・欠測・割付を照合し、元著者の分析にできるだけ近づける。ただし生の参加者データはGitHubにアップロードしない。上記の合成コードの点数と実験論文の点数を絶対に混ぜない。

独立研究枝のタスク台帳：`docs/roadmap/tasks.json`。Managerの目的は**End suffering**だが、これらのテストが示すのは統計・数理の学習用コードの機能だけ。
