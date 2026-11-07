# Before an AI Sends Another Nudge, Ask What the Logs Can Actually Prove

*Anicca Research · Manager Masterclass P11-1 · November 7, 2026*

It is 7 a.m. Someone planned a five-minute walk yesterday, but has not started. An AI assistant could send a gentle message. It might even predict a high probability that the person will walk afterward.

But what if they would have walked anyway? What if another notification helps today but contributes to fatigue next week?

This is the gap between **predicting a response and choosing an intervention that improves an outcome**. Better language generation alone cannot close it.

![Original educational diagram separating historical behavior-policy logs from a candidate policy](https://aniccaai.com/blog/manager/media/0b583f67ed08b72f49ee8ade31300d04b0ebab4425bdb3db6343caa54021d057.png)

## From immediate reactions to longer-term value

In reinforcement learning, an action is evaluated not only by its immediate reward but also by what may happen afterward. A useful shorthand for the Bellman equation is: action value equals expected next reward plus discounted value of the next state.

For a behavior-support assistant, taking no action needs to be a legitimate option. Maximizing clicks or response rates can reward unwanted interruptions. An appropriate objective must represent the person's chosen goal, burden, and potential harm.

## Can we evaluate a new policy without running it?

**Off-Policy Evaluation (OPE)** asks how a candidate policy would perform using data collected under an earlier policy. Consider a prior service that randomized notifications and logged both the actual decision and its probability.

Inverse Propensity Scoring (IPS) reweights each observed reward by the ratio between the new policy's probability of choosing that action and the original policy's probability. Doubly Robust (DR) estimation combines such weighting with an outcome prediction model.

That sounds appealing. The qualifications matter more.

If the old policy never chose an action in a particular context, the log cannot identify that action's consequences there. If the logging probabilities are missing, invented propensities do not restore the experiment. If unmeasured differences influenced both treatment assignment and outcomes, reweighting alone does not eliminate confounding. And a model that plans several steps ahead can exploit errors in its own imagined future.

Jiang and Li extended doubly robust evaluation to sequential reinforcement learning in 2016. Work on Conservative Q-Learning (CQL) and Model-Based Offline Policy Optimization (MOPO) addresses a related challenge: a policy learning from a fixed dataset can overvalue actions absent from that dataset.

## An honest numerical experiment

We wrote a small, reproducible experiment with **entirely fictional** binary states, actions, and outcomes. The generating behavior policy and true response probabilities are known to the experimenter. Across 20,000 simulated decisions, the theoretical target-policy value is 0.435. The independently implemented IPS estimate was approximately 0.43551 and the DR estimate approximately 0.43539.

The code refuses a candidate policy when the behavioral logging policy provides no support for an action. It also rejects inconsistent logged propensities. These are checks of mathematical consistency—not proof that Manager has made any person more active.

## Why this matters for Manager

The real promise is not to send the message most likely to be answered. It is to compare appropriate options, including **NO_ACTION**, and learn whether any intervention produces an independently measured benefit without hidden costs or harm.

Before expanding a real-world policy, record actual assignment rather than confusing it with message delivery; verify the relevant data rights, consent, and safety constraints; and use properly designed comparisons. A useful algorithm does not turn observational records into causation by naming its output value.

### Primary research
- [Jiang & Li, Doubly Robust Off-policy Value Evaluation (2016)](https://proceedings.mlr.press/v48/jiang16.html)
- [Kumar et al., Conservative Q-Learning (2020)](https://arxiv.org/abs/2006.04779)
- [Yu et al., MOPO (2020)](https://arxiv.org/abs/2005.13239)
- [Kuzborskij et al., Confident Off-Policy Evaluation (2021)](https://proceedings.mlr.press/v130/kuzborskij21a.html)

*Evidence boundary: all numerical results in this article are from an explicitly synthetic example. No real intervention, user outcome, or Manager policy advantage was measured.*
