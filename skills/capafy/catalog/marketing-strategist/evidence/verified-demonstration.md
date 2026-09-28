# Verified Demonstration — Marketing Strategist

## Offline selection notes

This is a repository-owned, offline demonstration using the input and pass criteria
already stored in `test/case1.md`. No Capafy API, browser, customer account, or live
market data was used. The result is a prompt example, not a claim about a production
customer or a measured conversion lift.

## Concrete input

```text
We get 5,000 visits/mo to our landing page but only 1% sign up for the free trial.
B2B SaaS, $30/mo. We've tried changing the headline twice. What's the one thing to fix?
```

## Actual output

### Diagnosis

The supplied bottleneck is trial signup conversion: the page receives 5,000 visits per
month, but only 1% become trial signups. The two headline changes did not establish that
the headline is the limiting step. The strongest hypotheses from the supplied facts are:

- visitors may still lack enough clarity or proof to commit at the signup step;
- signup friction may be present, but the number of fields and the form experience were
  not supplied.

`[ADD: product outcome, audience, current form fields, and any customer proof]` before
claiming which hypothesis is confirmed.

### The play

Run one controlled proof-and-friction experiment: replace the current above-the-fold
signup block with one specific outcome, one verified proof point, and the shortest form
that still supports the trial.

The principle is to reduce uncertainty at the decision point instead of making another
headline-only change. This can address clarity, trust, and avoidable signup effort. It
will not diagnose traffic quality, retention, pricing, or whether the product delivers
the promised outcome.

### The asset

**Experiment:** current signup block versus a proof-led signup block.

**Variant B copy**

> **[ADD: specific outcome] for [ADD: target B2B team]**
>
> See how it works with the information you already have.  
> **Proof:** [ADD: one verified customer result, or remove this line until proof exists]
>
> **CTA:** Start the free trial

Use only the form fields required to start the trial. Do not claim “no card required,” a
time-to-value, or a result unless the product owner verifies it. Keep traffic source,
pricing, trial terms, and the rest of the page unchanged during the comparison.

### Measure

Primary metric: trial signups divided by landing-page visits, measured for the same
traffic definition and comparable time window for both variants. No success threshold was
provided, so do not invent one; set the decision threshold before the experiment starts.

## Verification notes

- The 5,000 monthly visits, 1% signup rate, B2B SaaS context, $30/month price, and two
  previous headline changes all come from the concrete input.
- The diagnosis keeps form friction and proof as hypotheses because the input does not
  confirm either one.
- The response prescribes one experiment and does not claim a benchmark, conversion lift,
  customer result, browsing, competitor research, or live measurement.
- Missing product facts remain marked `[ADD: ...]` rather than being invented.
