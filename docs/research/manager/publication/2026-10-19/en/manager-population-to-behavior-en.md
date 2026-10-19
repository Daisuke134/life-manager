# From population construction to behavior prediction

Creating a list of synthetic residents and predicting their choices are different tasks. Numbers and resident cards here are fictional teaching examples.

![Connecting population construction and behavior prediction](https://aniccaai.com/blog/manager/media/9c26978fbafba515d22d1518336043ca1b4c13d05106d08e3ea5d876a61ff212.png)

The diagram shows one architecture that constructs a population before predicting responses, and another that predicts response distributions directly from a group description. It does not imply that both components are mandatory for every application. Illustration retains Japanese labels.

When a task calls for predicting behavior, reproducing population composition alone does not establish how people will act. A behavior model that accepts population records and circumstances needs its own training and evaluation.

The population component represents which attributes occur and how many people have them. Household synthesis also retains who lives together. A synthetic resident described as “34, employed, no car” can enter a behavior model alongside fare and service frequency. The model then estimates a bus-use probability under those conditions.

Creating attributes does not create behavioral ground truth. Behavior modeling needs observed actions or answers and evaluation evidence unused in training. Assess composition and conditional behavior separately.

For illustration, if 100 people each have a 20% use probability, expected use is `100 × 0.2 = 20`. This is not an observation that 20 people used the service. With different probabilities, sum them; with weighted profiles, sum weight times probability. Add environment and shared-resource models when interactions or capacity matter.

Predicted differences after changing conditions are not measured causal effects. Ultimately connect to an environment where changes can actually be made and test benefits using a predefined comparison and observations. Buses are an example, not our chosen first field use case.

Related: [data selection](https://aniccaai.com/blog/manager-population-dataset-selection-en), [method comparison](https://aniccaai.com/blog/manager-generative-methods-comparison-en), [separating population and responses](https://aniccaai.com/blog/manager-population-models-and-behavior-en).

## Either component can exist independently

Population synthesis represents people and composition from aggregates or samples when a target list is missing. It can support demographic or service-access analysis without a behavior model.

Behavior models do not always require synthetic populations. Predicting purchases or visits for existing users, or simulating known participants, can use their observed information directly.

Combining the components is useful when we lack a representative target-area list but want to compare group-wide responses. The population component represents composition; the behavior component predicts conditional choices. Applying behavior learned elsewhere still needs validation.

Manager’s intended loop is to proactively identify problems, predict changes, act in environments where authority and conditions permit, measure actual benefits, and feed results into the next decision. Prediction is one component. Requiring population synthesis and a behavior model for every use case would be unnecessary.

Some problems can be addressed through known rules and constraints, existing optimization methods, or operational checks when choosing a change. The design does not require a learned behavior predictor for every problem. Choose components according to the prediction question and what can be verified in reality. This is a design principle, not a claim that this full selection process has already been implemented and validated.
