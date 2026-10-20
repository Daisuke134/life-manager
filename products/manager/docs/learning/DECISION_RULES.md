# L011 — contextual bandit / MDP / off-policy evaluation

原著：Wang, Agarwal & Dudík (ICML 2017) https://proceedings.mlr.press/v70/wang17a.html ; Stanford 2021 evaluation study https://www.gsb.stanford.edu/faculty-research/publications/policy-evaluation-adaptive-weighting-data-contextual-bandits

| 手法 | 今の情報 | 未来の扱い | 初心者向けの例 |
|---|---|---|---|
| contextual bandit | 状況xで行動aを選び、その直後の報酬を観測 | 未来の状態遷移を陽にモデル化しない | 公開された二種類の支援施策の即時結果を比較 |
| MDP | 状態sで行動aを選択し、次の状態s'と報酬をモデル化 | 将来の波及や連鎖を評価 | 今支援すると後日どの資源状態が生まれるか |
| off-policy evaluation | 過去の別方針で得た行動ログを利用 | 実行前に新方針の価値を推定 | 施策Bを実行する前に、過去の正確な割付確率つきログで検討 |

**最も重要：positivity（support, overlap）**。過去の方針が行動Bを一度も選ぶ可能性がなかった状況で、Bを選ぶ新方針を過去データだけで安全に評価することは原則できない。割付確率が未知でも、自分で適当な数を与えれば計算だけは進むが、推定には根拠がない。

`manager_core/policy_basics.py`の**架空**IPS例では、`logging_propensity`と`target_propensity`を明示的に指定して `mean(reward*pi_target/pi_logging)` を計算する。作用の区別は設計仕様上でのみ検査し、真の割付メカニズムの正しさを実証したわけではない。

- 予測が不確実、倫理的リスクが高い、十分な実行権限がない場合は `no_action` を選ぶ。
- 未知の方針を自動展開しない。
- 反実仮想の評価でのバイアス、分散、観測交絡、時間依存などの問題を監査する。

`python3 -m examples.06_policy_basics`
