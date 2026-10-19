# From human simulation to environment design

A bank changes a payment experience. A pharmacy changes how people reach a pharmacist. Before committing, can either test how people will respond? Human simulation companies sell technology for that decision.

Aaru, Simile, and Primitive Labs emphasize behavior grounded in evidence. Predicting a response and improving someone's life through an intervention still require different tests. The useful distinction is between population construction, response prediction, and environment design.

## Building a population and predicting a response

A population model represents who exists, in what proportions, and under which constraints. Matching age and income separately is insufficient if their relationships with employment, household structure, or available time are wrong. Those relationships form a joint distribution.

Consider a service available only during working hours. A model that represents income but ignores time constraints may miss who cannot use it. A response model then estimates choices among the options each person can actually access. Interactions add another problem: increased demand can create congestion and change other people's choices.

![Separate population, response, environment, and evaluation components](https://aniccaai.com/blog/manager/media/44e2559cf36951fd05b99b034d6c48c0bef0bfa5793bebd97d7af15bb2cfc57a.png)

*A conceptual decomposition, not a diagram of proprietary company internals.*

## Different starting points, overlapping ambitions

Aaru describes combining public, licensed, and customer data, learning population structure, and sampling synthetic profiles. Its published methods explicitly say the core population generator and individual behavioral trajectory model are not language models. The full proprietary architecture is not public.[1]

Simile describes models trained on interviews, surveys, experiments, transactions, and other behavioral records. Self-reports can provide context; traces record what happened. Its company announcement states a mission to simulate all eight billion people on Earth. It is not restricted to individual simulation.[3][4]

“Population versus individual” and “public versus personal data” are useful starting questions, but poor binary labels. Aaru makes population construction particularly visible. Simile makes human grounding and prediction-confidence research particularly visible. Both seek population-level predictions.

## What customers are using

Aaru's EY case reports a blinded reconstruction of a wealth study covering 3,600 affluent investors in more than 30 markets. Across 53 matched questions, it reports median Spearman correlation of 0.90 and an average difference of 7.1 percentage points. This is evidence about reproducing research, not increasing investor wealth.[5]

Its Breakwater case covers 71 judgments from 40,000 simulated investors. Other advertised applications include product design, pricing, market entry, segmentation, and strategic communications. Scenario descriptions include competitor and policymaker responses; illustrative scenarios should not be treated as measured customer outcomes.[6][7]

Simile's Itaú case examines trust, comprehension, control, and adoption intent for Pix Automático, Brazil's recurring-payment experience. The reported reduction from five weeks to four business days measures research speed.[8]

Its CVS case describes pharmacist access, waiting times, communication clarity, refill intent, and benefit design. Simulations help prioritize subsequent pilots and experiments. The article does not establish a measured improvement in health or medication adherence.[9]

Primitive's Instinct models navigation, hesitation, abandonment, and conversion. It also advertises turning approved recommendations into tested improvements. It would therefore be inaccurate to position every existing company as “prediction only.” The scope of execution and the evidence for outcomes need to be checked for each product.[10]

Synthetic Users focuses on synthetic interviews and concept testing. Seldon focuses on product journeys and friction before launch. Their websites establish advertised uses; headline agreement percentages do not establish comparable performance across companies.[11][12]

## Learning the rules as people adapt

Salesforce's AI Economist introduces a different loop. Economic agents learn how to gather, trade, and work; a planner changes shared rules such as taxes. People adapt to the rules, and the planner learns from the resulting economy. Its two-level reinforcement learning makes adaptation part of policy evaluation.[13]

The planner's objective is explicitly chosen. Productivity, equality, individual utility, health, and freedom are not interchangeable. A model does not discover a universally correct welfare function. Nor does improvement in a simulated economy demonstrate the same effect in a government deployment.

Separating individual objectives from shared rules makes it possible to test whether an intervention remains useful after behavioral adaptation.

## The connection to world models

World Labs models space and dynamics. JEPA research predicts useful representations and future states. These approaches are broader than a simple “robotics only” label, but social institutions require their own data and validation.[14][15]

Predicting outcomes from observed actions does not establish the effect of changing those actions. Selection, confounding, spillovers, and adaptation can break that inference.

![Keep prediction, simulation, and field evidence distinct](https://aniccaai.com/blog/manager/media/8b828c20d083053461c13a7afaa983829ecfaf22678d1d35e9b994ba84f0b64f.png)

*Claims should stop at the evidence actually obtained.*

## Choosing a field intervention

A field study should start from existing intervention evidence and an operator's actual constraints. The CVS case includes pharmacist access and waiting times. A 2011 systematic-review abstract on advanced access scheduling summarizes 24 studies and reports improvements in appointment waiting time. Every included study had a potential source of bias; satisfaction findings were mixed, and clinical outcome data was limited.[16]

That is a reason to investigate shared scheduling and supply conditions, not proof of an AI effect. An AI-guided intervention would need a separate comparison against normal operations to test whether its predictions and intervention choices improve outcomes.

A first setting needs authority to change rules, real participants, prior records, comparable conditions, and an observable outcome period. Neither paid-work access nor healthcare should become the priority before those facts are available. An operator's evidence should establish whether the study's conditions match the proposed environment.

People need not use a new app for supply and access conditions to change. A useful result connects a specific change to observed access, burden, or income, with evidence another researcher can inspect.

## Sources

- [1] [Aaru published methods](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)
- [3] [Simile What-If Machine](https://www.simile.com/blog/what-if-machine)
- [4] [Simile, The Simulation Company](https://www.simile.com/blog/the-simulation-company)
- [5] [Aaru EY case](https://aaru.com/case-studies/ey-wealth-research)
- [6] [Aaru Breakwater case](https://aaru.com/case-studies/breakwater-conviction-advantage)
- [7] [Aaru Scenario Planning](https://aaru.com/use-cases/scenario-planning)
- [8] [Simile Itaú case](https://www.simile.com/blog/itau-at-esomar)
- [9] [Simile CVS case](https://www.simile.com/blog/simile-cvs-health)
- [10] [Primitive Instinct](https://primitivelabs.ai/instinct)
- [11] [Synthetic Users](https://www.syntheticusers.com/)
- [12] [Seldon](https://seldon.com/)
- [13] [AI Economist paper](https://arxiv.org/abs/2108.02755)
- [14] [World Labs taxonomy](https://www.worldlabs.ai/blog/taxonomy-of-world-models)
- [15] [V-JEPA 2 paper](https://arxiv.org/abs/2506.09985)

- [16] [Advanced access scheduling outcomes, systematic review](https://doi.org/10.1001/archinternmed.2011.168)
