# How AI Economist learns rules that people adapt to

A shared rule changes people's incentives. People adapt, and their adaptations change what the rule achieves. Salesforce's AI Economist makes this loop explicit through two-level reinforcement learning.

It is not a language model answering economics questions. Its economic agents learn how to gather resources, trade, and build. A separate social planner learns a tax schedule. Agents pursue their own utility; the planner pursues a specified social objective.

## A world with resources and transactions

In the main simulation, agents move through a grid, gather wood and stone, place market orders, and build houses that generate coins. Skills and access differ. Lower-skill builders can earn by supplying resources to higher-skill builders. Actions carry labor costs.

The world updates inventory, orders, escrow, labor, and taxes in code. Agents cannot declare a trade or invent money through text. The planner changes seven marginal tax rates at the beginning of each tax period. Taxes are collected at the end and redistributed equally. Observations and action masks determine what each actor knows and can do.

The shared rule affects more than the taxed person. If a high-skill builder reduces activity, demand for resources falls; suppliers can lose income too. This is why optimizing a rule while holding behavior fixed can produce the wrong conclusion.

## Different goals at two levels

Agent utility is a concave function of coin holdings minus labor disutility. Coins are a wealth proxy inside the model, not measured consumption or real financial wellbeing. Per-step rewards are changes in utility.

One planner objective combines equality and productivity: the complement of normalized Gini multiplied by total wealth. Another weights individual utility toward lower-endowment agents. Choosing either objective is a value decision made by the designer. The system does not discover what society ought to value.

Agents share policy parameters but have their own observations and recurrent states. The planner has a separate policy. PPO updates both using simulated experience. This is joint adaptation, not an exact solver that proves agents reached an equilibrium before optimizing the planner.

Training is difficult because both sides keep changing. The research starts with agent learning in a no-tax economy, then gradually expands allowable tax rates and changes exploration. Otherwise, early high taxation can suppress the behavior the planner needs to learn about.

## Evidence and limits

The papers compare learned policies with no-tax, a scaled US schedule, and Saez-style policies in particular modeled economies. Results depend on the world and social objective. The 2020 headline and the extended 2021 results are different experiments.

A small human experiment transferred a fixed learned schedule to a modified game. Trading and other conditions changed, and brackets were recalibrated. This is useful evidence about transfer into that game, not proof that a learned planner improved an actual national tax system.

The final journal paper appeared in *Science Advances* in 2022. The public repository is archived and uses an old training stack. Its simulation components and accounting boundaries remain useful to study; copying its full billion-sample training pipeline is unnecessary for a first Manager prototype.

Manager can borrow the separation of resident goals, shared rules, resource transitions, and social evaluation. It should test adaptation and spillovers, preserve group-level outcomes, and validate against reality. Health, time, agency, and the effects on other living beings need their own measures. They do not appear just because a planner maximizes a scalar reward.

Sources: [2020 paper](https://arxiv.org/abs/2004.13332), [extended paper](https://arxiv.org/abs/2108.02755), [Science Advances DOI](https://doi.org/10.1126/sciadv.abk2607), [fixed source](https://github.com/salesforce/ai-economist/tree/a84d5f3fdcabb207d9fde7754d34906903b3e184). Old official blogs were inaccessible in this review; methodological claims here use the papers and code.
