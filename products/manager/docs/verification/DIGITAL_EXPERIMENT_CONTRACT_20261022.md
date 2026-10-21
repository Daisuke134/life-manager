# Digital experiment opt-in and assignment-health contract

**Engineering preparation for F005.E06 / F008.E04.** Actual optional-engine exercise recorded **2026-10-21 17:11:52 UTC / 2026-10-22 02:11:52 JST**. Scope is **SYNTHETIC_ONLY, P0**. This implements the finite contract and refusal behavior that can be checked before a human study. It does not enable a website experiment, authenticate human consent or complete the field portions of either atomic task.

## What now runs

[manager_core/digital_experiment.py](../../manager_core/digital_experiment.py) prepares and replays assignments using the **actual GrowthBook Python SDK 3.2.2**, then evaluates assignment balance with **SciPy 1.15.3 `scipy.stats.chisquare`**. NumPy is pinned to **2.2.6**. Manager implements the surrounding evidence and refusal contract; it contains no custom allocation algorithm or chi-square implementation.

The same contract applies to the three existing routes:

| Domain | Exact candidate route | Fixed seed |
|---|---|---|
| finance | `/manager-support/finance.html` | `manager-support-finance-synthetic-v1` |
| mental | `/manager-support/mental.html` | `manager-support-mental-synthetic-v1` |
| physical | `/manager-support/physical.html` | `manager-support-physical-synthetic-v1` |

All use `hashAttribute=id`, `hashVersion=2`, `coverage=1.0`, fixed weights `(0.5, 0.5)`, and the unit type `SYNTHETIC_UNIT`. Variation zero is **NO_ACTION**. The existing `/manager-support/control.html` is retained as control-route metadata; a control decision returns no candidate route and leaves the existing state unchanged. The treatment variation is `OFFICIAL_RESOURCE_DIRECTORY`, bound to its exact domain route.

`config_hash()` uses canonical JSON and standard SHA-256 to identify the entire fixed configuration, including the route, seed, unit, engine versions and health thresholds. This hash is artifact identity, not randomization or permission. The adapter rejects changed settings rather than silently reallocating units under the same contract version. A deliberate future configuration change needs a new reviewed contract and a distinct experiment identity.

## Inputs, outputs and trust boundary

| API | Input and check | Output |
|---|---|---|
| `prepare_assignment` | Exact configuration, fictional unit, matching synthetic opt-in claim, aware clock, optional previous assignment. Calls the actual SDK twice and checks identity and stability. | An inert assignment record or a refusal. Its decision is always `NO_ACTION`. A matching previous record is reused. |
| `assignment_health` | A bounded, immutable snapshot of unique assignment records. Validates IDs/config/time, replays all rows through the SDK, recomputes counts and invokes SciPy. | `HEALTHY`, `SAMPLE_RATIO_MISMATCH` or `UNAVAILABLE`, with diagnostics where justified. |
| `evaluate_candidate` | Revalidates the current opt-in claim and assignment, computes health internally and requires the current unit to appear in the snapshot. | `NO_ACTION`, or **`SYNTHETIC_CANDIDATE`** for the existing route. Neither output permits live action. |

The positive candidate is an offline exercise result. Every public result object fixes:

```text
live_action_allowed = false
experiment_enabled = false
action_executed = false
external_authority = NOT_ESTABLISHED
human_outcome = NOT_MEASURED
causal_lift_status = NOT_ESTIMATED
proof_level = P0
```

These flags cannot be supplied as constructor overrides. The admission API has no `authorized=True`, live-activation parameter or caller-supplied “healthy” result. It recomputes health from the supplied synthetic records.

`OptInClaim` is deliberately a **self-supplied fictional claim**, not a new consent-authentication system. `SYNTHETIC_ONLY` and the `synthetic-unit-NNNNNN` syntax restrict exercise inputs; they do not independently prove data provenance. Relabeling a real person cannot create external authority because the output still forbids live action. An explicitly real-participant input is refused before SDK evaluation. This adapter does not create real identities, authenticate an operator, verify ethical approval, enroll anyone or record a real exposure.

No module path fetches GrowthBook features, supplies a client key, enables remote evaluation/streaming, attaches an exposure callback, uses sticky storage, writes a cookie or changes HTML. The [existing public-service baseline](PHASE06_DIGITAL_SERVICE_EXECUTION_20261021.md) and [public demo manifest](../demos/manager-public-no-action-20261022.json) continue to declare zero real participants and an experiment-disabled static service.

## Fail-closed behavior

The contract returns `NO_ACTION` for missing/untyped consent, a different unit/configuration/purpose, revoked/refused/unknown consent, future consent, expiry at or before the decision time, missing or invalid unit IDs, non-aware clocks, unavailable/unpinned engines, and unstable or invalid SDK assignments.

Health is unavailable when the snapshot is absent, mutable, too old, future-dated, bound to a different configuration, or contains malformed records. Duplicate units are rejected, including identical duplicates. They are not counted twice or silently discarded. Each record's assignment must replay under the actual SDK, and the current unit must exist in the valid snapshot. A self-reported count or precomputed p-value cannot bypass these checks.

The fixed exercise requires each observed and expected cell count to be at least **5** and total units to be at least **14**, following the applicability guidance in the pinned SciPy documentation. Missing or smaller samples yield `INSUFFICIENT_COUNTS`. These are conservative requirements for this diagnostic, **not a power calculation for a future human experiment**. The one-hour snapshot freshness limit is an offline contract choice, not a validated human-trial monitoring policy.

For an eligible snapshot, SciPy uses the observed unique-unit counts and the configured expected counts, with `ddof=0`. The SRM refusal condition is **p < 0.001**, matching the default warning threshold documented by GrowthBook. A p-value equal to 0.001 does not trigger this particular check. Nonfinite/invalid outputs or an unavailable statistics engine leave health unavailable and the decision at `NO_ACTION`. [GrowthBook SRM documentation](https://docs.growthbook.io/app/experiment-results#experiment-balance-srm) · [SciPy 1.15.3 reference](https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.chisquare.html)

A healthy ratio establishes only that this diagnostic did not detect a mismatch in the declared synthetic snapshot. It provides no evidence of human consent, correct real exposure logging, absence of all allocation bugs, positive treatment effects or human benefit.

## Actual optional-engine results

The [machine-readable result](DIGITAL_EXPERIMENT_CONTRACT_20261022.json) comes from [phase06_experiment_contract.py](../../scripts/phase06_experiment_contract.py). It used **Python 3.12.14**, GrowthBook **3.2.2**, SciPy **1.15.3** and NumPy **2.2.6**. The recorded wall-clock time is separate from the explicitly fictional simulation clock, `2026-10-22T00:00:00+00:00`.

The same 512 fictional ID strings are exercised separately under each domain's distinct experiment key and seed. They are not 1,536 real people or three field studies.

| Domain | NO_ACTION | Directory candidate | Total fictional assignments | Pearson chi-square | SRM p-value | Diagnostic |
|---|---:|---:|---:|---:|---:|---|
| finance | 247 | 265 | 512 | 0.6328125 | 0.426325543384408 | No SRM detected |
| mental | 253 | 259 | 512 | 0.0703125 | 0.7908823229406241 | No SRM detected |
| physical | 256 | 256 | 512 | 0.0 | 1.0 | No SRM detected |

Every assignment was reproduced with the actual SDK and an existing record. Each domain's control remained `NO_ACTION`; each eligible treatment produced only `SYNTHETIC_CANDIDATE` for its existing route. The run observed **zero network-connection attempts**, **zero external writes**, and **zero real participants**. Socket calls were blocked during the exercise and checked even if an upstream library might have caught an attempted connection.

For each domain, the script then deliberately selected a **90-control / 10-treatment** subset of the authentic synthetic assignments. This constructed refusal probe produced chi-square **64.0**, p-value **1.2441921148543578e-15**, and `NO_ACTION / SAMPLE_RATIO_MISMATCH`. It is a designed test input, not an observed field malfunction. Separate actual-engine probes also refused revoked, expired and missing opt-in claims, a real-participant claim, missing health and duplicate units.

### Configuration fingerprints

| Domain | SHA-256 |
|---|---|
| finance | `296ed81f3d07c187200b70d76e41329412391208ea5b990b63c77b98a93210dd` |
| mental | `c151d4eb1d292a4209362a27d014329b7701166b562bd8ead5052de721047c7c` |
| physical | `ddbeb743f045262ede6393c1f59574acf2ad551c56bf591cf9986b9abd356cb8` |

The JSON also includes snapshot hashes, complete fixed configurations, refusal reasons and invariant output flags. It retains only aggregate exercise results and no real participant rows.

## Tests and reproduction

The first run of the new contract tests was **RED: 32 failures because the implementation was absent**. After implementation and a test-helper parameter correction, all tests passed. Two additional adapter checks cover exact dependency-version refusal and SDK hash/participation identity. The final dedicated suite is **34 tests passed**, without requiring optional dependencies:

```bash
python -m unittest discover -s tests -p 'test_digital_experiment.py'
```

Tests cover the substantive refusal paths above, no-action control, all three route bindings, immutable configuration identity, deterministic assignment reuse, duplicate-count rejection, snapshot freshness, absent IDs, insufficient counts, the strict SRM threshold, nonfinite health results, optional-engine failure, and the invariant prohibition on live effects. A subprocess with `python -S` verifies that importing the module works without site packages and does not import GrowthBook or SciPy.

For an isolated optional-engine reproduction:

```bash
python -m venv /tmp/manager-experiment-venv
/tmp/manager-experiment-venv/bin/python -m pip install -r requirements-experiment-checks.txt
/tmp/manager-experiment-venv/bin/python scripts/phase06_experiment_contract.py
```

The actual recorded run reused separately installed dependency targets:

```bash
PYTHONPATH=/tmp/manager-growthbook-deps:/tmp/manager-causal-deps \
  python scripts/phase06_experiment_contract.py
```

[requirements-experiment-checks.txt](../../requirements-experiment-checks.txt) matches the outcome-engineering lane's SciPy/NumPy pins. Package metadata supports Python 3.11: GrowthBook requires Python >=3.9; SciPy and NumPy require >=3.10. This local machine had no Python 3.11 executable, so the recorded optional smoke is explicitly a **3.12** run rather than an asserted 3.11 execution.

An integration run at handoff discovered **450 tests**, with **5 optional skips** and one unrelated failure: `test_r006_rights.test_task_is_done_and_generator_non_destructive` reported `BACKLOG VIEW OUT OF SYNC`. The coordinating lane owns the concurrently updated task registry/backlog and will regenerate it. This lane did not modify those files and does not label that integration run as passed.

## Remaining field gates

This completes executable **offline contract preparation**, not the live owner-route trial portions of F005.E06/F008.E04. A future human integration still needs independently established operator/platform authority, authentic voluntary consent and withdrawal handling, a justified stable identity unit, prospective allocation/exposure definitions, a frozen protocol and statistical plan, appropriate data rights, real monitoring and independently observed outcomes. Those cannot be supplied by an agent-written JSON claim.

No real-cohort lift, P3 outcome or P4 causal benefit is estimated. The default static service remains experiment-disabled, and original Phase06 funding/site requirements remain unchanged. Canonical task/workflow/status updates are left to the coordinating lane.

## Primary sources and file hashes

Official sources retrieved live on 2026-10-21 UTC / 2026-10-22 JST, all HTTP 200:

- [GrowthBook Python SDK documentation](https://docs.growthbook.io/lib/python): seed, hash attribute/version, weights, and experiment results. The installed pinned 3.2.2 source was also inspected for the exact constructor and result fields used here.
- [GrowthBook experiment results](https://docs.growthbook.io/app/experiment-results): standard chi-square SRM diagnostic and default p < 0.001 threshold.
- [SciPy 1.15.3 `chisquare`](https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.chisquare.html): observed/expected counts, degrees of freedom, count applicability and matching totals.

| Artifact | SHA-256 |
|---|---|
| `manager_core/digital_experiment.py` | `06c54a8a9a00e3cd49be8445df7d09898f280b0c08893658efeca3f593b9aacd` |
| `tests/test_digital_experiment.py` | `5f441c10978e448ffb8e6ced373d40e8f3490ac6f859772f15b8fb0c5497b5cf` |
| `scripts/phase06_experiment_contract.py` | `6721d0f15f10b7347843ce4adcd4e2e4f799679a632ae7f317645a9ea4143b9e` |
| `requirements-experiment-checks.txt` | `c6749da264faaf34a002fac3997f5e23ea35ea64d5567ba89c25cd8b9ce39a2c` |
| Recorded result JSON | `1b57c2e67996b6e25c6b0678888acb6e7c841ffe862574c6b788494f59e57bed` |
