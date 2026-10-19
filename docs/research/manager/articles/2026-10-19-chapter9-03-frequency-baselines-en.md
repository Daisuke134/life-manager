# Behavior prediction starts with counting: base rates, conditional probabilities, and baselines

Draft, saved for learning. Publication on hold. All numerical examples below are fictional teaching fixtures, not findings about commuters or Manager performance.

## From records to predictions

Lesson 9.2 defined a record as a person on a decision occasion, with the conditions available at prediction time, the available alternatives, and a later observed action. Lesson 9.3 turns those records into a first predictor. Restrict this example to occasions with two available alternatives, bus and walking. Assume both exhaust the defined outcome for these records; practical studies must separately handle other modes, confirmed non-departure and missing outcomes.

Twenty historical occasions contain ten bus choices. The overall empirical probability estimate is 10/20 = 0.5. This feature-blind predictor returns the same probability for everyone. Its simplicity makes it a useful baseline, not a claim that all people are identical. scikit-learn implements this with DummyClassifier(strategy="prior"). The predict_proba result differs from strategy="most_frequent", which returns a one-hot distribution for the majority label.

## Condition on information available now

Of ten rainy occasions, eight used the bus; of ten clear occasions, two used it. Estimated bus probabilities become 8/10 = 0.8 for rain and 2/10 = 0.2 for clear weather. Formally, P(B|R)=P(B and R)/P(R), provided P(R)>0. In this example (8/20)/(10/20)=8/10. The observed fraction is an estimate of the unknown future probability, not the definition of a guaranteed future rate.

Weather is known at the prediction time. Actual later ticket payment is not an admissible input for a forecast made before that payment. A probability is also distinct from a chosen label: an 80% bus prediction can still be followed by walking. Predicting the higher-probability action and sampling an action according to probabilities are different operations. Ten similar occasions with probability .8 imply expected bus count eight under the model; they do not require exactly eight realized choices. Dependence matters for variability.

## Why not make conditions arbitrarily specific?

Rain plus Tuesday plus a particular age and neighborhood may leave only one observation. One bus choice out of one is an observed frequency of 100%, but is weak evidence of a true probability of one. More conditions can reduce bias while increasing estimation uncertainty. Repeated observations from the same person are not independent people.

A transparent teaching remedy for a binary outcome is add-one smoothing: (bus_count+1)/(total_count+2). One success out of one then yields 2/3, not one. The two additions are pseudocounts representing an assumption, not invented real observations. This corresponds to a uniform Beta(1,1) prior and a posterior predictive probability under a Bernoulli model. It is not universally optimal; choose smoothing using training/validation data, preserve final test data, and do not blindly apply a 50% prior to highly imbalanced behavior. Unseen conditions can fall back to an overall estimate, with an explicit lack-of-data flag. Hierarchical models and partial pooling are later extensions.

Jurafsky and Martin explain count estimates and smoothing in a language-modeling context. We reuse the statistical idea; their results are not a validation of transport predictions. Their chapter explicitly cautions that add-one is inadequate for modern n-gram models. Likewise, the query language-model interpolation in Manning, Raghavan and Schuetze provides another example of combining sparse local evidence with a broader distribution.

## A baseline must be evaluated on other observations

The executable companion fits twenty constructed training occasions, then evaluates eight separately constructed later occasions: rainy bus/bus/bus/walk and clear bus/walk/walk/walk. The overall predictor has accuracy .5 and binary Brier score .25. The conditional predictor has accuracy .75 and binary Brier score .19. The tie rule is fixed at p >= .5 predicting bus. These numbers only verify the mechanics on a deliberately constructed example. They are not empirical evidence that weather conditioning improves real behavior prediction. Test splits and metrics receive fuller treatment in lessons 9.5 and 9.6.

Useful comparison methods include overall frequencies, the most frequent action, conditional frequencies, and a person's last observed action when that history exists before prediction. Last-action prediction requires consistent temporal units and a cold-start fallback. Hyndman and Athanasopoulos describe last-observation forecasting for numerical time series; adapting this to categorical actions is a separate baseline design, not their exact model.

## Prediction is not an intervention estimate

P(bus|rain) is an observed association. It does not identify what a fare reduction would cause, nor prove that creating rain would change choices. Shmueli's To Explain or to Predict? distinguishes predictive and explanatory modeling goals. Manager eventually needs both credible forecasts and evidence about the effects of its actions, evaluated separately. Synthetic population records supply attributes and composition; they do not supply observed behavioral labels automatically.

## Sources and code

- Aston Zhang, Zachary C. Lipton, Mu Li and Alexander J. Smola, Dive into Deep Learning, Probability and Statistics, conditional probability equation 2.6.2: https://d2l.ai/chapter_preliminaries/probability.html
- Kenneth Train, Discrete Choice Methods with Simulation, 2nd ed. (2009), chapter 2: https://eml.berkeley.edu/books/choice2nd/Ch02_p9-33.pdf
- Galit Shmueli (2010), To Explain or to Predict?, Statistical Science 25(3), 289–310, DOI 10.1214/10-STS330: https://arxiv.org/pdf/1101.0891
- Daniel Jurafsky and James H. Martin, Speech and Language Processing, chapter 3, August 19, 2026 draft, sections 3.1 and 3.6: https://web.stanford.edu/~jurafsky/slp3/3.pdf
- Christopher D. Manning, Prabhakar Raghavan and Hinrich Schuetze (2008), Introduction to Information Retrieval, language-model smoothing: https://nlp.stanford.edu/IR-book/html/htmledition/estimating-the-query-generation-probability-1.html
- scikit-learn DummyClassifier documentation: https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyClassifier.html
- Official implementation pinned to revision afe5bcd80, predict_proba branch: https://github.com/scikit-learn/scikit-learn/blob/afe5bcd80/sklearn/dummy.py
- Rob J. Hyndman and George Athanasopoulos, Forecasting: Principles and Practice, simple forecasting methods: https://otexts.com/fpp3/simple-methods.html

Companion executable: docs/research/manager/learning/chapter9/chapter9_03_frequency_baselines.py. No external API or dependency required. Raw third-party source copies remain private; this draft contains original explanation.
