"""Phase 11 research labs: five fully synthetic, deterministic, no-effect studies.

Educational only. No real human responses, no LLM weights trained, no real
social simulation validated, no brokerage orders, no deployment or authorization.
All reported numeric findings must be labelled SYNTHETIC, not Manager efficacy.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from random import Random
from statistics import mean
from collections import defaultdict
from typing import Mapping


def _check_probability(value: float) -> None:
    if not (isinstance(value, (int, float)) and 0 <= value <= 1):
        raise ValueError("probability must lie within [0, 1]")


@dataclass(frozen=True)
class LoggedChoice:
    context: int
    action: int
    reward: float
    logged_propensity: float


def synthetic_contextual_log(n: int = 20000, seed: int = 1101) -> list[LoggedChoice]:
    """Randomized behavioral policy; probabilities and outcome model are known."""
    if n <= 0:
        raise ValueError("positive sample size required")
    rng = Random(seed)
    result = []
    for _ in range(n):
        x = rng.randrange(2)
        behavior_p1 = 0.1 if x == 0 else 0.75
        a = int(rng.random() < behavior_p1)
        outcome = {(0, 0): 0.2, (0, 1): 0.4, (1, 0): 0.35, (1, 1): 0.75}[(x, a)]
        result.append(LoggedChoice(x, a, float(rng.random() < outcome),
                                   behavior_p1 if a else (1 - behavior_p1)))
    return result


def _target_p(context: int, action: int) -> float:
    if context not in (0, 1) or action not in (0, 1):
        raise ValueError("unsupported synthetic state/action")
    p1 = 0.2 if context == 0 else 0.7
    return p1 if action == 1 else 1 - p1


def _q(context: int, action: int) -> float:
    return {(0, 0): 0.2, (0, 1): 0.4, (1, 0): 0.35, (1, 1): 0.75}[(context, action)]


def evaluate_contextual_ope(rows: list[LoggedChoice],
                            behavior_support: Mapping[tuple[int, int], float]) -> dict:
    """IPS/SNIPS/direct-method/DR with exact known synthetic reward model.

    This is a one-step randomized bandit example, not long-horizon Offline RL.
    Real-world DR consistency needs assumptions: valid propensities/support,
    unconfounded assignment or experimental randomization and correct models.
    """
    if not rows:
        raise ValueError("rows required")
    for x in (0, 1):
        for a in (0, 1):
            if _target_p(x, a) > 0 and behavior_support.get((x, a), 0) <= 0:
                raise ValueError("positivity failure: target action not supported")
    weighted_reward = total_weight = total_squared_weight = dm = dr = 0.0
    for row in rows:
        if row.context not in (0, 1) or row.action not in (0, 1):
            raise ValueError("bad state/action")
        _check_probability(row.reward)
        if row.logged_propensity <= 0 or row.logged_propensity > 1:
            raise ValueError("bad logging propensity")
        expected_logged = behavior_support[(row.context, row.action)]
        if abs(row.logged_propensity - expected_logged) > 1e-10:
            raise ValueError("logging propensity contradicts behavior policy")
        w = _target_p(row.context, row.action) / row.logged_propensity
        target_q = sum(_target_p(row.context, a) * _q(row.context, a) for a in (0, 1))
        weighted_reward += w * row.reward
        total_weight += w
        total_squared_weight += w * w
        dm += target_q
        dr += target_q + w * (row.reward - _q(row.context, row.action))
    n = len(rows)
    return {
        "method": "SYNTHETIC_RANDOMIZED_BANDIT_NOT_HUMAN_EFFICACY",
        "ips": weighted_reward / n,
        "snips": weighted_reward / total_weight,
        "direct_method": dm / n,
        "doubly_robust": dr / n,
        "effective_sample_size": total_weight**2 / total_squared_weight,
        "n": n,
        "oracle_population_value": 0.5 * (
            0.8 * 0.2 + 0.2 * 0.4
        ) + 0.5 * (
            0.3 * 0.35 + 0.7 * 0.75
        ),
        "support_verified": True,
        "policy_deployed": False,
    }


def p11_1_demo() -> dict:
    rows = synthetic_contextual_log()
    return evaluate_contextual_ope(rows, {
        (0, 0): 0.9, (0, 1): 0.1,
        (1, 0): 0.25, (1, 1): 0.75
    })


def peer_exposure(node_id: str, ties: Mapping[str, list[str]],
                  treated: Mapping[str, int]) -> float:
    neighbors = ties.get(node_id, [])
    if not neighbors:
        return 0.0
    if any(other not in treated for other in neighbors):
        raise ValueError("neighbor treatment assignment missing")
    return sum(treated[other] for other in neighbors) / len(neighbors)


def simulated_social_outcomes(ties: Mapping[str, list[str]],
                              treated: Mapping[str, int],
                              baseline_by_person: Mapping[str, float]) -> dict:
    """Expected means under a DEFINED artificial spillover response equation.

    Edges must be exogenous here; observational neighbor associations would
    conflate homophily, common shocks and true causal influence.
    """
    if set(ties) != set(treated) or set(ties) != set(baseline_by_person):
        raise ValueError("all simulated identities must match")
    response = {}
    for person, neighbors in ties.items():
        if person in neighbors or any(other not in ties for other in neighbors):
            raise ValueError("invalid network edge")
        direct = treated[person]
        if direct not in (0, 1):
            raise ValueError("treatment must be binary")
        base = baseline_by_person[person]
        _check_probability(base)
        exposure = peer_exposure(person, ties, treated)
        response[person] = min(1.0, max(0.0, base + 0.12 * direct + 0.30 * exposure))
    return {
        "data_kind": "SYNTHETIC_STRUCTURAL_EQUATION",
        "expected_outcome_probability": response,
        "treatment_fraction": mean(treated.values()),
        "not_a_real_spillover_estimate": True,
    }


def synthetic_homophily_not_contagion() -> dict:
    """Two latent types form same-type ties and copy nothing from neighbors."""
    latent = {f"p{i}": int(i >= 6) for i in range(12)}
    ties = {i: [j for j in latent if latent[j] == latent[i] and j != i]
            for i in latent}
    neighbor_rate = {i: mean(latent[j] for j in ties[i]) for i in latent}
    matching = sum(abs(neighbor_rate[i] - latent[i]) < 1e-12 for i in latent)
    return {
        "data_kind": "SYNTHETIC_HOMOPHILY_WITH_ZERO_CAUSAL_INFLUENCE",
        "neighbor_association_accuracy": matching / len(latent),
        "structural_peer_effect": 0.0,
        "interpretation": "observed social correlation does not identify contagion",
    }


def p11_2_demo() -> dict:
    ties = {
        "a": ["b", "c"], "b": ["a", "c"],
        "c": ["a", "b", "d"], "d": ["c"]
    }
    treated = {"a": 0, "b": 1, "c": 1, "d": 0}
    output = simulated_social_outcomes(ties, treated, {p: 0.2 for p in ties})
    return {
        "network": output,
        "homophily_counterexample": synthetic_homophily_not_contagion()
    }


def compare_agent_architecture(task_count: int, parallel_fraction: float,
                               worker_error_probability: float,
                               coordination_cost_tokens: int = 120) -> dict:
    """Amdahl-style schematic, NOT a model-inference benchmark."""
    if (not isinstance(task_count, int) or task_count <= 0
            or not isinstance(coordination_cost_tokens, int)
            or coordination_cost_tokens < 0):
        raise ValueError("invalid task size/budget")
    for p in (parallel_fraction, worker_error_probability):
        _check_probability(p)
    base_duration = task_count * 10.0
    # two workers; latency overhead increases and may defeat parallelization
    multi_duration = base_duration * ((1 - parallel_fraction) +
                                      parallel_fraction / 2) + 8.0
    solo_tokens = task_count * 80
    multi_tokens = task_count * 100 + coordination_cost_tokens
    return {
        "kind": "SYNTHETIC_ARCHITECTURE_COST_MODEL",
        "single_duration_units": base_duration,
        "multi_duration_units": multi_duration,
        "single_tokens": solo_tokens,
        "multi_tokens": multi_tokens,
        "single_task_success_probability": 1 - worker_error_probability,
        "independent_two_agents_both_wrong_probability": worker_error_probability ** 2,
        "perfectly_correlated_two_agents_both_wrong_probability": worker_error_probability,
        "quality_of_real_agents_evaluated": False,
    }


def p11_3_demo() -> dict:
    return {
        "parallel": compare_agent_architecture(12, 0.90, 0.10),
        "sequential": compare_agent_architecture(12, 0.10, 0.10),
        "warning": "agreement of correlated agents is not independent validation"
    }


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + exp(-z))
    ez = exp(z)
    return ez / (1 + ez)


def fit_logistic_1d(rows: list[tuple[float, int]],
                    iterations: int = 1000, rate: float = 0.5) -> tuple[float, float]:
    """Simple deterministic teaching optimizer for intercept + slope."""
    if not rows or iterations <= 0 or not 0 < rate <= 1:
        raise ValueError("invalid optimization parameters")
    if any(y not in (0, 1) for _, y in rows):
        raise ValueError("labels must be binary")
    bias = weight = 0.0
    for _ in range(iterations):
        gb = gw = 0.0
        for x, y in rows:
            residual = _sigmoid(bias + weight * x) - y
            gb += residual
            gw += residual * x
        n = len(rows)
        bias -= rate * gb / n
        weight -= rate * gw / n
    return bias, weight


def logistic_log_loss(rows: list[tuple[float, int]],
                      parameters: tuple[float, float]) -> float:
    if not rows:
        raise ValueError("empty evaluation set")
    bias, w = parameters
    return mean(
        -(y * log(max(_sigmoid(bias + w * x), 1e-12))
          + (1 - y) * log(max(1 - _sigmoid(bias + w * x), 1e-12)))
        for x, y in rows
    )


def synthetic_two_domain_choices(n_per_domain: int = 400,
                                 seed: int = 1104) -> dict:
    rng = Random(seed)
    datasets = {}
    for domain, sign in (("A", 1), ("B", -1)):
        rows = []
        for _ in range(n_per_domain):
            x = -1 if rng.random() < 0.5 else 1
            prob = _sigmoid(2.0 * sign * x)
            y = int(rng.random() < prob)
            rows.append((x, y))
        datasets[domain] = rows
    return datasets


def p11_4_demo() -> dict:
    data = synthetic_two_domain_choices()
    train = {k: v[:300] for k, v in data.items()}
    test = {k: v[300:] for k, v in data.items()}
    pooled = fit_logistic_1d(train["A"] + train["B"])
    specific = {k: fit_logistic_1d(train[k]) for k in train}
    return {
        "data_kind": "SYNTHETIC_NEGATIVE_TRANSFER_DEMONSTRATION",
        "pooled_test_logloss": {k: logistic_log_loss(test[k], pooled) for k in test},
        "specific_test_logloss": {k: logistic_log_loss(test[k], specific[k]) for k in test},
        "pooled_weight": pooled[1],
        "task_specific_weights": {k: specific[k][1] for k in specific},
        "not_a_trained_BFM": True,
        "model_weight_release": False,
    }


def transport_stratified_ate(source_cates: Mapping[str, float],
                             target_fraction: Mapping[str, float]) -> dict:
    """Standardization ONLY under measured effect modifiers and transportability."""
    if set(source_cates) != set(target_fraction) or not source_cates:
        raise ValueError("strata must have complete overlap")
    if any(p < 0 for p in target_fraction.values()) or abs(sum(target_fraction.values())-1) > 1e-10:
        raise ValueError("valid target mass required")
    return {
        "data_kind": "SYNTHETIC_TRANSPORTABILITY_IF_ASSUMPTIONS_HOLD",
        "standardized_ate": sum(source_cates[s] * target_fraction[s] for s in source_cates),
        "not_identified_without_transport_assumptions": True,
    }


def backtest_selection_bias(seed: int = 1105, n_strategies: int = 150,
                            n_train: int = 24, n_future: int = 24) -> dict:
    """Null strategies with genuinely independent future periods."""
    if n_strategies <= 1 or n_train <= 0 or n_future <= 0:
        raise ValueError("invalid backtest shape")
    rng = Random(seed)
    candidates = []
    for _ in range(n_strategies):
        train = [rng.gauss(0, 1) for _ in range(n_train)]
        future = [rng.gauss(0, 1) for _ in range(n_future)]
        candidates.append((mean(train), mean(future)))
    selected = max(candidates, key=lambda v: v[0])
    return {
        "data_kind": "SYNTHETIC_NO_SKILL_STRATEGIES",
        "searched_strategies": n_strategies,
        "best_in_sample_mean": selected[0],
        "same_selected_future_mean": selected[1],
        "transaction_cost_per_period": 0.03,
        "future_net_mean_after_cost": selected[1] - 0.03,
        "real_market_test": False,
        "recommendation": "Never infer tradable edge from selected backtest"
    }


def p11_5_demo() -> dict:
    return {
        "transport_example": transport_stratified_ate(
            {"A": 0.30, "B": 0.10}, {"A": 0.20, "B": 0.80}),
        "backtest_multiple_search": backtest_selection_bias()
    }


def run_all() -> dict:
    return {
        "suite": "PHASE_11_FIVE_SYNTHETIC_LABS_NO_EXTERNAL_EFFECT",
        "P11-1": p11_1_demo(),
        "P11-2": p11_2_demo(),
        "P11-3": p11_3_demo(),
        "P11-4": p11_4_demo(),
        "P11-5": p11_5_demo(),
        "actual_user_outcomes": "NOT_MEASURED",
        "actual_company_revenue": "NOT_MEASURED",
        "actual_shared_BFM_training": "NOT_PERFORMED",
        "actual_autonomous_operations": "NOT_PERFORMED",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_all(), ensure_ascii=False, indent=2, sort_keys=True))
