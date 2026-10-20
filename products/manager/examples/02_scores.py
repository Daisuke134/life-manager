"""L002: score illustrative predictions, not people or causal effects.

Run from Manager's repository root:
    python3 -m examples.02_scores
"""
from manager_core.evaluation import brier_score, total_variation


def main() -> None:
    predicted_share = {'buy': 0.70, 'do_not_buy': 0.30}
    observed_share = {'buy': 0.50, 'do_not_buy': 0.50}
    tvd = total_variation(predicted_share, observed_share)

    individual_probabilities = [0.90, 0.10]
    aligned_brier = brier_score(individual_probabilities, [1, 0])
    reversed_brier = brier_score(individual_probabilities, [0, 1])

    print('SYNTHETIC EXAMPLES ONLY — NOT a causal effect or Manager field outcome')
    print(f'TVD = {tvd:.2f} (0 = matching distributions; 1 = disjoint)')
    print(f'Brier aligned = {aligned_brier:.2f} (lower is better)')
    print(f'Brier reversed = {reversed_brier:.2f} (same group shares; different individual matches)')
    print('These errors do NOT establish benefits from any intervention.')


if __name__ == '__main__':
    main()