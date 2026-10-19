# Behavior prediction: from available inputs to probabilities of action

Behavior prediction estimates a later action from information available at a particular time. Consider someone about to depart who can choose either a bus or walking. Past travel records can reveal relationships between conditions and choices. Predictions for a new departure can then be compared with the choice actually recorded afterward.

A small calculation separates four things: records of behavior, inputs available when a prediction is made, the probabilities returned, and evaluation after the outcome is known.

![Using past behavior records to estimate probabilities and compare them with new observations](https://aniccaai.com/blog/manager/media/f95dffd7e217815a30522f164588a158316ffc7bad45e50ee6beba853095f55c.png)

The diagram and all numbers below are fictional teaching examples, not actual transport statistics or measured model accuracy. Travel makes the alternatives easy to explain; it has not been selected as Manager's field application. Diagram labels are in Japanese.

## Population composition and behavior

Population synthesis creates a roster of synthetic residents with attributes such as age, employment, and household membership. That can describe who is represented and in what numbers, but it does not yet tell us what they choose when traveling to work.

Behavior prediction combines a person's attributes with circumstances and past behavior. Available transport modes, fares, journey times, and departure-time weather are examples. Representing choices probabilistically, using the characteristics of alternatives and factors we cannot observe, is a basic idea in discrete choice modeling.[1]

Behavior includes purchases, store visits, appointment attendance, service use, and the next place someone visits, as well as transport choices. The target action must be defined specifically in each application.

The output need not be a probability for each alternative. Depending on the target, the task may predict whether someone visits, how many times they use a service, when they act, or the sequence of their movements. Classification, count, time, and sequence predictions answer different questions. Starting with two alternatives makes the input-output relationship easier to examine.

## Five decisions for one prediction

“Predict this person's behavior” is not specific enough to define a training table. For the fictional travel example, we specify:

| Decision | Definition in this example |
|---|---|
| Target and unit | One departure by someone who can choose either bus or walking |
| Prediction time | Before choosing a mode |
| Input | Weather known at departure |
| Prediction target | The mode selected for this upcoming trip |
| Outcome for evaluation | The mode actually chosen, recorded afterward |

The same two alternatives cannot be assigned to someone with no operating bus service. This example includes only occasions on which both are available. In real data, observed choices must be distinguished from the alternatives that were actually available.[1]

## One row of inputs and outcomes

A training table aligns information available before prediction with behavior observed afterward.

| Trip record | Weather known before the choice | Behavior recorded afterward |
|---|---|---|
| 001 | Rain | Bus |
| 002 | Rain | Walking |
| 003 | Clear | Walking |
| 004 | Clear | Bus |

Weather is the input feature; the behavior to be predicted is the target variable. In classification, recorded behavior is also called the label. The label corresponds to an observed choice, rather than direct access to a person's thoughts.

A new prediction receives only the weather. Before someone has chosen, it cannot use their actual choice or information that becomes known only after arrival. Using information unavailable at prediction time is data leakage.[2]

## Counting past records

Suppose 40 fictional trip records are summarized by weather. Each record is one trip, so 40 records do not necessarily mean 40 people.

| Weather at departure | Trip records | Chose bus | Chose walking |
|---|---:|---:|---:|
| Rain | 20 | 16 | 4 |
| Clear | 20 | 4 | 16 |
| Total | 40 | 20 | 20 |

Ignoring weather, the bus proportion is 20 ÷ 40 = 50%. A method returning 50% bus and 50% walking in every situation is an initial baseline. Predictions that ignore differences in input features can help establish whether a more complex model adds value.[3]

Now count only the 20 rainy trips. Sixteen used the bus, giving 16 ÷ 20 = 0.8, or 80%. In clear weather, 4 ÷ 20 = 0.2, or 20%. Calculating a proportion within a specified condition is an elementary example of conditional probability. We write `P(bus | rain)`: the expression to the right of the vertical bar specifies the condition, and the expression on the left identifies the outcome.

Here, those proportions become estimates for a new departure. A small probability table—“80% bus in rain; 20% bus in clear weather”—is already a model that maps inputs to predictions. Starting with deep learning or an LLM is unnecessary. However, these proportions come from a small historical dataset. Their performance in new situations still needs testing.

## A new input and its output

If rain is known before departure, retrieve the rainy-weather row:

```text
Input: A departure is upcoming. It is raining. Bus and walking are both available.
Calculation: In past rainy-weather records, 16 of 20 trips used the bus.
Output: Estimated probability of bus 0.8; estimated probability of walking 0.2.
```

The 80% is not a measured accuracy score. It is the estimated probability assigned to the bus for this input. Accuracy on new data has not yet been measured.

An 80% probability does not determine an individual's action. The next person may walk. Rather than judging the probabilities from a single outcome, evaluate their correspondence with observations across many records not used to construct the predictions. Scoring probabilities and scoring whether one selected answer was correct are different tasks.[4]

## Learning, prediction, and evaluation

In this example, counting past records to construct the probability table is learning. Looking up a new weather condition to return probabilities is prediction. Comparing the prediction with the choice recorded afterward is evaluation.

Fitting the same 40 records that produced the table is different from predicting a trip seen for the first time. Separate training records from evaluation records. If the task concerns future behavior, learn from the past and evaluate on later records. With repeated observations from the same people, performance for previously unseen people also needs a separate evaluation.[2][5]

Adding fares, journey times, and previous choices can produce combinations with very few matching historical records. Logistic regression, choice models, tree models, time-series models, or neural networks can estimate relationships in such settings. Whatever method is chosen, the connection between available inputs, observed actions, and evaluation on unseen data remains essential.

## Prediction and simulation

Prediction returns an action probability or another outcome estimate for an input. Simulation can use that prediction to generate a synthetic action and, when relevant, advance the situation to its next state.

Suppose 50 of 100 fictional synthetic residents are assigned rain and 50 are assigned clear weather. If this probability table applies to all of them, the expected number using the bus is 50 × 0.8 + 50 × 0.2 = 50.

Generating individual synthetic actions means sampling bus or walking according to each probability. A single simulation need not contain exactly 50 bus users. The expected count, obtained by summing probabilities, differs from one random draw. This calculation explains what connecting the components means; it is not a result obtained by attaching a validated behavior model to the Rhode Island synthetic population.

## Changing an input and estimating an intervention effect

A higher bus proportion in rainy records does not by itself establish that rain caused the change in choice. Rainy and clear days might differ in destinations, days of the week, or traveler composition.

Similarly, a fare-aware model may change its prediction when given a lower fare. That does not show the effect of an actual price reduction. Predictions under existing conditions and evaluation of a policy changing those conditions are different questions. Estimating intervention effects requires an appropriate design and separate real-world comparisons.

![Connecting population composition with a behavior model](https://aniccaai.com/blog/manager/media/0e3cb41af0ffca953ee2c234b3c932778aeb70db6917c02fa2732d815c8879ee.png)

The records, probabilities, and inputs in this diagram are also fictional teaching examples. The upper part shows learning from observed behavior. The lower part shows checking applicability to a target population before applying the model. Not every diagrammed field is included in the household-population output. Diagram labels are in Japanese.

## When a synthetic population can be reused

The Rhode Island household roster is a reusable output of a population-generation program. Household membership, integerization, IDs, and validation checks need not be discarded and rebuilt without reason.

However, the final region, target population, behavior, and required attributes for a Manager application have not been selected. A new target may require regenerating the population. Even within the same region, work locations, time information, or behavior histories may need to be added. Reusing the population-generation machinery and deciding whether a particular generated dataset is suitable are separate decisions.

Transport-choice records and records of responses to stressful experiences cannot teach every action that was never observed in them. An application needs observations and a population suited to its purpose, with differences between contexts checked before they are connected.

## Sources

1. Kenneth Train, [Discrete Choice Methods with Simulation, second edition](https://eml.berkeley.edu/books/choice2.html), 2009. [Chapter 2](https://eml.berkeley.edu/books/choice2nd/Ch02_p9-33.pdf) informs the treatment of alternatives, observed information, and probability models. The numerical examples here are original fictional examples, not copied from the book.
2. scikit-learn, [Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html): separating training from evaluation and avoiding information unavailable at prediction time.
3. scikit-learn, [DummyClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyClassifier.html): baselines that do not use input features.
4. scikit-learn, [Metrics and scoring](https://scikit-learn.org/stable/modules/model_evaluation.html): probability prediction, classification, decision making, and scoring.
5. scikit-learn, [Cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html): group-based and time-based evaluation.
