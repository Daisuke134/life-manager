# Ampersand: a reproducible recalculation of public aggregates

This record accompanies the English and Japanese explanatory articles. It checks
the arithmetic of the **company-published simulation chart**, using a frozen
snapshot of public numeric aggregates. It is not an independent model benchmark,
a new simulation, an API inference trial, or an observed effect on people.

## What was actually done

1. The parent research task retrieved the two public JavaScript files below.
2. `recompute.py` verifies their exact byte counts and SHA-256 hashes.
3. It parses only the public model-aggregate array as data and extracts the
   displayed default weight. It does not execute JavaScript.
4. It recomputes the score and reported standard-error formula, then changes only
   the cost weight to show how the numerical ordering depends on that choice.
5. It produces `observations.json` and four original explanatory PNGs. Source
   comments, internal links, individual records, and conversation traces are not
   retained in these outputs.

The parent task also made an unauthenticated public `GET /v1/models` request,
which returned **HTTP 401**. No model inference was performed. This access check
does not show whether an authenticated account could use the model.

## Frozen sources

| File | Public URL | Retrieval time, UTC | Bytes | SHA-256 |
|---|---|---|---:|---|
| Aggregate data | [life-combined-data.js](https://ampersand.humansand.ai/blog/life-combined-data.js?v=no-note-1) | 2026-10-21 23:33:45.463593 | 2,046 | `196aff6d814a702058528c8d158e32d00340dde40e0096b9553f364dd4f917f1` |
| Chart configuration | [evaluations.js](https://ampersand.humansand.ai/blog/evaluations.js) | 2026-10-21 23:33:45.633121 | 63,968 | `f5160c6d396acb368a52f2358b16c112b645f7551a61c1de1cfac166f70bbc89` |

The retrieval timestamps are fixed provenance. Running the calculation again does
not replace them with the current time. If the upstream file changes, the script
rejects it rather than silently treating it as the same observation. The full
upstream JavaScript is not redistributed in this directory.

## Calculation and results

For a model's published mean goal progress `g`, interaction cost `c`, and selected
weight `w`, the displayed score is:

```text
score(w) = g - w * c
```

The display configuration sets the default to `w = 0.2`. The script uses exact
decimal arithmetic on the published decimal inputs. These quantities use the
publisher's scoring convention; `cost` here is not API expenditure or dollars.

| Model | Published goal progress | Published cost | Recomputed score at 0.2 |
|---|---:|---:|---:|
| Fable 5.1 | 13.4456 | 2.5019 | 12.94522 |
| Ampersand | 13.8157 | 4.3651 | 12.94268 |
| Gemini 3.8 Flash | 13.2943 | 1.8528 | 12.92374 |
| Muse Spark 1.3 | 13.0179 | 1.9217 | 12.63356 |
| Kimi K3 | 12.5893 | 4.2691 | 11.73548 |
| Opus 5.5 | 10.8288 | 1.3279 | 10.56322 |
| GLM 5.3 | 10.9667 | 5.4016 | 9.88638 |
| GPT-6 Astra | 9.9567 | 0.7631 | 9.80408 |
| GPT-6.1 Sol | 9.1987 | 0.9806 | 9.00258 |

The numerical leaders change when the weight changes:

| Cost weight | First | Second | Third |
|---|---|---|---|
| 0.0 | Ampersand — 13.81570 | Fable 5.1 — 13.44560 | Gemini 3.8 Flash — 13.29430 |
| 0.2 | Fable 5.1 — 12.94522 | Ampersand — 12.94268 | Gemini 3.8 Flash — 12.92374 |
| 0.3 | Gemini 3.8 Flash — 12.73846 | Fable 5.1 — 12.69503 | Ampersand — 12.50617 |

At the published setting, the Fable–Ampersand difference is **0.00254**. This is
an arithmetic ordering of published means. We did not test whether the difference
is statistically significant or practically meaningful.

The reported standard-error terms also permit the calculation
`SE(w) = sqrt(A - 2*w*B + w*w*C)`. They represent variation within the published
simulation setup. They do not quantify whether results generalize to real people,
and they do not supply the paired cross-model data needed to test the difference
between two models. The score-weight figure therefore shows point estimates and
explicitly labels its limited interpretation.

Changing the weight here does **not** retrain a model or generate new behavior.
It revalues fixed outcomes under different preferences about interaction cost.
The example shows why reporting only the highest bar can hide a consequential
evaluation choice.

## Reproduce the arithmetic

Python 3.10+ and the standard library are sufficient. Supply locally downloaded
copies of the two pinned public files:

```bash
python products/manager/docs/research/ampersand-20261022/recompute.py \
  --life-js /path/to/life-combined-data.js \
  --evaluations-js /path/to/evaluations.js
```

Use `--output /path/to/observations.json` to write elsewhere. An optional
`--reference-json` can compare the parsed model goals, costs, and scores with a
separately prepared numeric extract. That check does not change the output.

## Reproduce the original figures

The optional plotting path uses Matplotlib, with a Japanese-capable font supplied
by the caller. Numerical analysis remains usable without Matplotlib.

```bash
python products/manager/docs/research/ampersand-20261022/recompute.py \
  --life-js /path/to/life-combined-data.js \
  --evaluations-js /path/to/evaluations.js \
  --figures \
  --japanese-font /path/to/NotoSansCJKjp-Regular.otf
```

The figures were generated with Matplotlib 3.10.8. The Japanese font was obtained
from the [official Noto CJK repository](https://github.com/notofonts/noto-cjk),
`Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf`. The font file is not redistributed
here. Its SHA-256 was
`68a3fc98800b2a27b371f2fb79991daf3633bd89309d4ffaa6946fd587f375b5`.
`--figure-dir` can select another output directory.

- `ampersand-training-loop-en.png` and `ampersand-training-loop-ja.png` explain
  a general conceptual loop: assistant chooses, user/world model predicts,
  evaluation rule scores, learning changes choices. Real-world evaluation is
  shown separately. This is **not a claim about undisclosed Ampersand internals**.
- `ampersand-score-weight-en.png` and `ampersand-score-weight-ja.png` plot four
  of the nine public model aggregates and list the numerical top three at each
  selected weight. The plot does not claim a causal or significant winner.

## Verification performed

- Both raw source hashes and byte counts matched the frozen record.
- Nine models were parsed, with a unique expected model set and finite numeric
  values. The published default weight was independently extracted from the
  display file.
- Goals, costs, and default scores agreed with the parent's separate numeric
  extract. Direct checks verified the three numerical leaders and the 0.00254
  default-score difference.
- The output was regenerated without changing its bytes. A changed source was
  rejected by the hash check.
- All four PNGs were visually inspected, including Japanese glyphs and labels.

Only the analysis script, aggregate record, this explanation, and the four
original figures belong to this research task. No product runtime, external
account, experiment participant, or publishing configuration was changed here.

## Future article and book library (2026-10-22; GitHub storage only)

The user requested that newly researched material be saved as **files** and **not published** to the blog automatically. The following additive materials extend this independently reproducible recalculation without replacing the frozen source record:

- [Japanese long-form book chapter](BOOK_CHAPTER_DEEP_DIVE_JA.md) — fundamentals, Persimmon, CORO math, honest evaluation, Simile/Aaru/Andon comparison, Manager implications.
- [English long-form book chapter](BOOK_CHAPTER_DEEP_DIVE_EN.md) — chapter-length bilingual companion for later adaptation into published content.
- [Read-only Ampersand API protocol probe](ampersand_readonly_probe.py) with [12 offline contract tests](test_ampersand_readonly_probe.py). In the current runtime, authenticated inference is **BLOCKED_NO_API_KEY**; the mock's 12 passing tests only establish safe request/validation behavior.
- [Prioritized implementation backlog and actual experiment record](IMPLEMENTATION_ORDER_AND_PROBE_RECORD.md) — detailed observation/planning/evaluation architecture, dependency gates and next actions.

Publication manifest, generated blog artifact hashes, payment workflows, and the original 113-task Manager roadmap are deliberately unchanged by this extension. Keep study provenance, simulated data, model-provider claims, mathematical reanalysis, API trial evidence and independently measured human effects as separate classes. If future vendor evidence changes, add dated errata rather than silently rewriting this frozen public snapshot.

## Follow-up: simulation, reality and suffering (2026-10-22)

[Simulation and Reality: Reactions, Suffering, and Human Agency](SIMULATION_REALITY_SUFFERING.md) adds English/Japanese material, ten proposed synthetic tests, and ordered integration tasks. Distinguish reaction, self-report, material conditions, autonomy, and longer-term causal outcomes. Compare communication with removing environmental barriers; do not optimize agreement alone.

A credential was subsequently supplied by the user. The earlier `BLOCKED_NO_API_KEY` entry above is a historical observation, **not the present blocker**. The current execution environment could not complete the external API preflight, and a browser execution check was blocked. The credential was not sent to any provider or stored in files. Authenticated requests, model inference, Persimmon simulations, and human interventions in this follow-up are all **0**. Credential validity and model availability remain unverified, not rejected.

Code review also established that the existing `--smoke` path ends after session creation; it does not retrieve the completed answer. Extend and verify that readback before reporting a successful inference test. The proposed ten cases are NOT RUN, and the earlier mock-test report has not been rerun in this follow-up.

No article publication or deployment was initiated. This repository is public: a manuscript stored here is not confidential. Credentials, actual participant profiles, and private conversations must remain outside Git.
