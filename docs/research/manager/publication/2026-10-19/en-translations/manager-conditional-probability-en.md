# Conditional probability: which group are we counting within?

Conditional probability is a probability restricted to cases satisfying a condition. “What percentage of all students cycle to school?” and “What percentage of boys cycle to school?” use different denominators.

![A fictional school example of conditional probability](https://aniccaai.com/blog/manager/media/eb128c3864d700f6ed97817946df3eac49e5c7f28ea0a36a3b5ff1c57f1a5229.png)

Japanese labels. Consider 100 fictional students: 60 boys, of whom 18 cycle and 42 do not; 40 girls, of whom two cycle and 38 do not. These are not survey findings.

Across the school, 20/100 = 20% cycle. Among boys, 18/60 = 30%; among girls, 2/40 = 5%. Conditioning did not change anyone’s transport choice. It changed the group being counted. This association alone does not establish a causal effect.

`P(cycle | boy) = 0.30`. The right side of the bar is the condition; the left is the event of interest. In general, `P(A | B) = P(A and B)/P(B)`, requiring `P(B) > 0`. When the denominator is zero, this formula cannot supply the conditional probability; we cannot simply call it 0%.

## Generating synthetic people

Suppose we generate a school from this fictional table. Start with 60 boys and 40 girls, then assign a transport mode. Draw cycling with probability 30% for each boy and 5% for each girl. Take a uniform random number u in [0,1); assign cycling when u is below the probability. The same illustrative u = 0.20 falls below 0.30 but not 0.05. In independent sampling, draw a fresh random number for each person.

```python
probability = 0.30 if group == "male" else 0.05
bike = rng.random() < probability
```

This is a lesson in conditionally sampling one attribute, not a complete reimplementation of a research population-synthesis algorithm. Harland and colleagues assign attributes using probabilities conditional on existing attributes and also adjust against aggregates. Applying a uniform 20% to everyone would fail to reproduce the relationship in this example.

Expected cycling attendance is `60 × 0.30 + 40 × 0.05 = 20`. A draw need not produce exactly 20 cyclists. Our 100-person Python standard-random example with seed 42 produced 24 boys and two girls cycling: 26 total. Twenty is the expectation; 26 is one generated realization. A seed helps reproduce the same implementation, not guarantee real-world accuracy. Exact totals require additional allocation or adjustment.

## Connecting joint and marginal distributions

Multiply the probability of being a boy, 0.60, by the conditional cycling probability, 0.30, to get the joint probability 0.18:

```text
P(boy and cycle) = P(boy) × P(cycle | boy)
```

For girls, `0.40 × 0.05 = 0.02`; adding the two gives the overall cycling proportion 0.20. The reverse conditional, `P(boy | cycle) = 18/20 = 90%`, differs from `P(cycle | boy) = 30%`. Do not swap the event and condition.

## Separate totals do not determine unknown probabilities

We supplied all cells to make the teaching example clear. If we knew only 60 boys, 40 girls, 20 cyclists, and 80 others, we could not derive the 30% cycling probability among boys. Samples, additional evidence, or modeling are needed to estimate the combinations.

If the probability comes from another area, test whether it transfers. Adding conditions can leave few observations in each group. Matching overall totals does not establish accurate conditional probabilities.

## Connection to Manager

In population generation, this is the basis for generating attributes conditional on others. In response modeling, it expresses action probabilities given personal attributes and environmental conditions. The probability principles are shared; the training data and correct answers differ.

A Bayesian network connects conditional probabilities to represent joint distributions. Its arrows should not automatically be interpreted causally.

Sources: [Brown University, Seeing Theory](https://seeing-theory.brown.edu/compound-probability/index.html); [Harland et al. 2012, Conditional Probabilities section](https://www.jasss.org/15/1/1.html). Student counts, sampling code, and the 26-person output are our fictional teaching example, not reported research results.
