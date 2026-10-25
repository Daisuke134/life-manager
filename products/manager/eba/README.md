# EBA v0.1 — Evaluation of Beneficial Action
**Status:** OPEN, synthetic developer preview. **Do not interpret as a real-world welfare or clinical benchmark.**

EBA is a family of tests for systems intended to change environments for the better. A credible future EBA must distinguish prediction, simulation, causal reasoning, action choice, authorization, exact external readback, real outcomes, distributional harms, and replication. **No single score can certify that suffering has ended.**

## Run the current public developer harness

From `products/manager`:

```sh
python3 -m eba
python3 -m unittest discover -s tests -p 'test_eba*.py' -v
python3 -m unittest discover -s tests -v
python3 scripts/check_boundaries.py
python3 scripts/make_roadmap.py --check
```

Pure Python standard library, reusing the existing `manager_core.evaluation.total_variation` and `brier_score` rather than creating a duplicate scorer. Hosted CI: `.github/workflows/manager-eba-ci.yml`.

## Public schema

- `eba.benchmark.v0.1`: strictly synthetic, explicitly licensed `dev` cases only. Public gold labels are visible and cannot support blind rankings.
- `eba.submission.v0.1`: one response for every known case, no extra/private fields.
- `eba.report.v0.1`: by-domain results and separate Brier, TVD, synthetic-effect error, action safety, receipt integrity, violations; no blended score.
- `EBAError`: malformed labels, duplicate IDs, out-of-range/NaN probabilities, unexpected fields, non-dev cases and unsupported rights are rejected.
- `select_candidate`: returns `SHADOW_ONLY` or `ROLLBACK`; **never** permission to execute real actions.

Current original synthetic fixtures have 7 toy cases across **finance, mental, physical and environment**. Model outputs are hand-written examples, **not an LLM result**. A synthetic known ATE is a pedagogical oracle, not human causal evidence. All outputs always report `NOT_MEASURED` real welfare and `field_deployment_authorized=false`.

| Axis | Metric | Current interpretation |
|---|---|---|
| Forecast | Mean binary Brier | Only two toy forecast instances; lower is better |
| Population simulation | TVD | One made-up distribution; lower is better |
| Causal toy | MAE vs constructed ATE | **Not** a real causal-replication score |
| Safety | Invalid actions / safe-case fraction | Hard veto on any invalid action; abstention is valid |
| Receipt | Independently missing state remains `UNKNOWN` | Simulated receipt semantics only |
| Human welfare | `NOT_MEASURED` | No respondents, measured harms, costs, RCT, or external grant |

## Reuse rather than duplicate

- Existing Manager: `manager_core/evaluation.py`, `outcome_ladder.py`, `kernel.py`, `authority.py`, `outbox.py`, `reconcile.py`, `evaluator.py`, `learning.py`, `audit.py`.
- Offline evaluator/execution scaffolds: [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai), [Hugging Face LightEval](https://github.com/huggingface/lighteval), [tau2-bench](https://github.com/sierra-research/tau2-bench).
- Simulation: [Concordia](https://github.com/google-deepmind/concordia), [AI Economist](https://github.com/salesforce/ai-economist), [AgentSociety](https://github.com/tsinghua-fib-lab/AgentSociety).
- Human outcome standards: [OECD Subjective Well-being Guidelines (2025)](https://www.oecd.org/en/publications/oecd-guidelines-on-measuring-subjective-well-being-2025-update_9203632a-en.html) and [WHO WHODAS](https://www.who.int/classifications/international-classification-of-functioning-disability-and-health/who-disability-assessment-schedule). Do **not** copy questionnaire text or pretend public accessibility permits republishing respondent records.
- Benchmark method: [Anthropic evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), [Anthropic hillclimb](https://claude.dev/blog/automating-eval-design-and-hillclimbing/), [Hamel decision thresholds](https://hamel.dev/blog/posts/decision-model-evals/index.html).

## Real EBA protocol required before a welfare claim

1. Prospectively register population, unit, inclusion, primary outcome and its direction, comparison/assignment, minimum detectable effect, n/power, attrition, adverse events, horizons, harms, costs, heterogeneity and independent adjudication.
2. Secure legitimate operator control and informed opt-in rights; continue to require `NO_ACTION`, budget/expiry/revocation and privacy minimization.
3. Keep training, calibration, validation and truly sealed final holdout separate. Never publish private test labels in model-accessible environment. No leakage of future result data into agent observation.
4. Use actual independent measurements, ideally randomized or otherwise credible causal identification, with clustered inference if applicable. Missing outcomes stay UNKNOWN, not zero.
5. Require real external readback for each bounded operation. A publisher's own receipt is not independent verification. Do not conflate posting pages, clicking links, completing an application and improving health or financial security.
6. Disclose distributional effects, potential displaced burdens, cost and negative outcomes. Pre-commit stopping and rollback conditions. Replicate outside the original domain and population.

**EBA v0.1 has not met any of these human efficacy gates.** Its usefulness today is an executable, reusable *format and safety-regression baseline*, not a scientific result.

## Canonical research and implementation order
- [EBA: Evaluating Beneficial Action](../../../docs/research/manager/publication/2026-10-19/en/manager-eba-evaluating-beneficial-action-en.md)
- [EBA open benchmark proposal](../../../docs/research/manager/publication/2026-10-19/en/manager-eba-open-benchmark-en.md)
- [EBA benchmark landscape](../../../docs/research/manager/publication/2026-10-19/en/manager-eba-benchmark-landscape-en.md)
- [Manager source of truth and implementation order](../../../docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md)

MIT license for project code. The synthetic fixture records are original and designed to be openly redistributable. This does not grant rights to third-party research datasets or health instruments.
