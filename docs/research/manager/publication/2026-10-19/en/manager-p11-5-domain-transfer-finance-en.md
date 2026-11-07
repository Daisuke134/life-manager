# The Best Backtest Can Be the Worst Reason to Trust a Strategy

*Anicca Research · Manager Masterclass P11-5 · November 7, 2026*

A new strategy dominates a chart of historical returns. It has the highest average among hundreds of candidates and appears ready for deployment.

But the chart may be the result of searching so many alternatives that one was bound to look good by chance.

The same mistake can undermine an AI model transferred from one population or domain to another: **success on yesterday's data is not evidence of reliable success in an unseen world**.

![Original synthetic illustration of selected in-sample backtest and held-out future performance](https://aniccaai.com/blog/manager/media/4128df68cbc5266f5ad6b087eaa3635126638cff3dd6794ed88e1689acec9c17.png)

## Distribution shift is more than a technical footnote

Training and target environments can differ in who is observed, how labels are distributed, or how situations lead to outcomes.

A shift in the frequency of a feature can sometimes be addressed with reweighting. A change in the underlying conditional response mechanism cannot simply be fixed that way.

Consider a fictional behavior-support study with two groups. Group A has a treatment effect of +30 percentage points; group B has +10. In a balanced source population, the average is +20. In a target population with 20% A and 80% B, standardization gives:

Target average = 0.20 × 0.30 + 0.80 × 0.10 = 0.14.

This calculation only transports the effect under strong assumptions: all relevant effect modifiers were measured, conditional effects are stable between populations, and the target groups are represented in the source. The equation is not a guarantee of portability.

## We searched 150 strategies that had no genuine skill

In a fully synthetic lab, we generated 150 strategies with **true expected return zero**. Each had 24 artificial historical observations. We selected the strategy with the highest historical average, then evaluated that same strategy on an independently generated 24-period future.

With the seed fixed in our educational code, the historical winner averaged approximately +0.537 in arbitrary normalized units. Its held-out future mean was about −0.0365. Subtracting a hypothetical per-period transaction cost of 0.03 produced approximately −0.0665.

These are not securities, actual returns, or investment advice. The demonstration isolates one point: **searching for the maximum score creates selection bias even when every candidate has zero edge**.

Bailey and colleagues developed approaches to quantify backtest overfitting and adjust Sharpe ratios for multiple testing and non-normality. In real markets, additional problems arise from liquidity, spreads, slippage, market impact, changing regimes, data leakage, and regulation.

## The lesson is broader than finance

A researcher can overfit a behavioral benchmark by trying dozens of prompts, model checkpoints, or agent architectures against the supposedly final test set. The test set eventually becomes a training signal.

For a credible cross-domain behavioral model, preserve truly unseen groups and time periods. Report every important evaluation choice. Separate statistical prediction, identifiable causal effect, executable policy, and actual value.

The most useful claim is not "our model works everywhere." It is **"here is precisely where it generalizes, and here is what breaks when the environment changes."**

### Primary research
- [Arjovsky et al., Invariant Risk Minimization (2019)](https://arxiv.org/abs/1907.02893)
- [Bailey et al., Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- [Bailey & López de Prado, Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)

*Evidence boundary: the 150 strategies and all associated values are artificial. No trading, real returns, or Manager financial benefit was measured.*
