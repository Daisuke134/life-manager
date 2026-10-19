# Learning behavior probabilities with logistic and choice models

Lesson 9.4 connects observed choices to learned parameters. Manager needs forecasts it can evaluate before it uses them to compare or execute changes. Logistic regression is a transparent starting model, not a guarantee of causal intervention effects. All numerical demonstrations here use fictional data. Publication is on hold.

## From counting groups to learning a function

Lesson 9.3 estimated a separate frequency for each condition. A model instead learns a function of numerical inputs such as travel time and fare. A binary logistic model first computes z = w*x + b, then p = 1/(1+exp(-z)). Here p is the predicted probability of the outcome coded 1, w is a learned coefficient, and b is an intercept. A sigmoid maps every real score to a value between zero and one. Despite its name, logistic regression is commonly used for classification.

For a small example, let x=(walking minutes minus bus minutes)/10. Walking takes 25 minutes and the bus 15 minutes, so x=1. Code actual bus use as y=1 and walking as y=0. Initially w=b=0, giving score zero and probability .5.

A single observation with y=1 has binary cross-entropy loss -log(.5), about .693. The derivatives are dL/dw=(p-y)*x and dL/db=p-y. With learning rate .2, both coefficients move from zero to .1. The same input then has score .2, probability .549834, and loss .598139. The loss for this example decreased. This does not establish generalization or justify repeating only this one positive example.

The companion standard-library script also fits twenty fictional observations using full-batch gradient descent, without regularization. For x=1, eight of ten outcomes are bus; for x=-1, two of ten are bus. It learns w approximately 1.386294 and b approximately zero, giving probabilities .8 and .2. At x=.5 it interpolates to about .666667. That interpolation is a property of the chosen logistic function, not independently observed truth. The example has only training-fit results; no real human prediction accuracy has been measured.

Real models can include multiple predictors, with their own coefficients. Scaling and the chosen functional form matter. Regularization can discourage excessively large coefficients. A coefficient describes a conditional relationship under the fitted model; it is not automatically a causal effect or a direct measure of an individual's preference. Exact outcomes, available alternatives, timestamps and missingness still require the careful data design from lesson 9.2.

## Who developed and implements these approaches

Daniel McFadden's conditional-logit work is foundational for econometric discrete choice. Kenneth Train's Discrete Choice Methods with Simulation explains logit and its derivation from a random-utility model. In a multinomial logit model, each available alternative has a score V_j and probability exp(V_j)/sum_k exp(V_k), with the denominator restricted to available alternatives. The binary sigmoid can be obtained by taking the score difference between two alternatives. Do not interpret every raw single-alternative score as an isolated binary probability.

Train also explains the independence of irrelevant alternatives property and the limitations it creates when alternatives share unobserved factors. Repeated choices by the same individual can share such factors too. These are reasons to evaluate richer specifications, including nested or mixed logit, rather than assume the first logit specification fits every behavior.

Michel Bierlaire's official Biogeme example estimates a multinomial logit model on Swissmetro stated-preference data. It defines Train, Swissmetro and Car utilities from alternative-specific constants, travel time and travel cost. The code constructs separate dictionaries for utility and availability, passes those and CHOICE to loglogit, and calls estimate(). It uses maximum likelihood with a Newton/BFGS-style optimizer, not the simple gradient step used in this lesson's teaching script.

The published example reports 6,768 retained observations and estimates b_time about -1.278 and b_cost about -1.084 for its scaled variables and model specification. These are the author's published results, not a new reproduction by us, and they must not be reused unchanged for another population. The data record hypothetical scenario choices, not observed completed rides. Better in-sample log likelihood alone is not heldout forecast accuracy.

scikit-learn provides a general-purpose LogisticRegression implementation with regularization and several solvers. Its official documentation presents the sigmoid and cross-entropy objective. That is useful for ordinary supervised classification; Biogeme explicitly models alternative-specific attributes and choice availability. An implementation should preserve those distinctions when selecting a library.

## How this becomes a Manager component

The candidate architecture is: observed behavioral data -> feature construction -> fit a small predictor -> evaluate on heldout people/times -> apply it to an appropriate cohort or synthetic population -> aggregate forecasts -> let a separate planner compare actions -> execute through existing controls -> measure real outcomes.

The chapter 8B population-generation machinery remains reusable. Its Rhode Island household output is not a universally valid behavioral training dataset: it supplies composition and attributes, not observed choice labels, and may lack attributes or geography required by a selected task. Reuse or extend it after the task is defined rather than rebuild automatically.

This lesson adds the learning mechanism. Lesson 9.5 designs the test split, 9.6 examines scoring and calibration, and 9.7 compares model families. Manager's mission is End suffering; an accurate action forecast is one component toward that mission. An intervention's benefit still needs separate evaluation.

## Jev has a different integration role

TypeSafe Jev accepts a state and typed questions and returns bounded decisions and probabilities. TypeSafe reports a proprietary architecture, parallel sampling and Reinforcement Learning for Calibrated Decisions (RLCD). The reviewed public sources do not disclose its complete architecture, loss or training recipe. The launch FAQ explicitly says it is neither small nor an LLM. Do not invent a Transformer/QKV explanation for its internals.

As retrieved October 19, 2026, the stable alias maps to jev-1.13.0 and preview to jev-1.14.0. Customers configure state, instructions and criteria; the model is not fine-tuned per customer. This differs from fitting our own logistic coefficients against observed behavior.

For Manager, Jev could classify incoming problem reports, route to existing handlers, or select among permitted simulation actions. A generative model can write messages when needed; code should compute exact dates, amounts and constraints. A probability attached to an action choice does not become a validated probability of human behavior. Evaluate each intended use using relevant labeled cases, and distinguish decision correctness from behavioral realism and intervention benefit.

A public community fork, badgerbees/jev-oasis, already uses this architecture: Jev selects an action, an LLM is used for text-generating actions, and existing environment functions execute it. Its README reports 12 rather than 36 LLM calls for 36 agents in one round. Jev calls remain, and this does not establish total-cost savings of the same percentage or human behavioral fidelity. It is a community implementation, not evidence of adoption by official OASIS, MiroFish, Aaru or Simile.

The official input price is $0.042 per million tokens. One million requests of 1,000 input tokens each would cost $42 in input tokens; repeating that for 100 steps would cost $4,200. Launch latency of 70–500 milliseconds is a vendor measurement under its test conditions, not our benchmark. Jev is a hosted service, not a local open-weight model. No Jev inference was run for this lesson.

## Primary sources and working code

- Kenneth Train (2009), Discrete Choice Methods with Simulation, chapter 3: https://eml.berkeley.edu/books/choice2nd/Ch03_p34-75.pdf
- Daniel McFadden (1974), Conditional logit analysis of qualitative choice behavior, original chapter (OCR-assisted reading; formulas cross-checked with Train): https://eml.berkeley.edu/reprints/mcfadden/zarembka.pdf
- Michel Bierlaire, EPFL, official Biogeme example with source download and reported estimation: https://biogeme.epfl.ch/sphinx/auto_examples/swissmetro/plot_b01a_logit.html
- scikit-learn logistic regression mathematics and implementation guidance: https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression
- TypeSafe launch: https://typesafe.ai/blog/introducing-system-one-models-and-jev
- Current models: https://docs.typesafe.ai/models.md
- Independent Jev evaluation (Deusser, Sparrenberg and Sifa; 2026 preprint): https://arxiv.org/html/2609.37647v1
- Community simulation implementation: https://github.com/badgerbees/jev-oasis

Reproducible local arithmetic: docs/research/manager/learning/chapter9/chapter9_04_logistic_learning.py. Detailed Jev source review: articles/2026-10-19-typesafe-jev-system-one-en.md. Raw source copies remain private.
