"""Teaching example inspired by Artificial Societies Benchmark (2026).
NOT the original full benchmark. All data here are deliberately fictional.
Official research: https://github.com/artificial-societies/artificial-societies-benchmark
"""
from collections import Counter


def distribution(values, labels):
    if not values:
        raise ValueError("Population must not be empty")
    counts = Counter(values)
    return [counts[label] / len(values) for label in labels]


def tvd(p, q):
    """Total variation distance between two categorical distributions."""
    if len(p) != len(q):
        raise ValueError("Category lengths do not agree")
    return sum(abs(a - b) for a, b in zip(p, q)) / 2


# Both individual questions have 50% yes, 50% no in both populations.
# But the human answers are positively aligned and synthetic ones are opposite.
human = [(0, 0)] * 50 + [(1, 1)] * 50
synthetic = [(0, 1)] * 50 + [(1, 0)] * 50
labels = [0, 1]
first_h = distribution([x[0] for x in human], labels)
first_s = distribution([x[0] for x in synthetic], labels)
second_h = distribution([x[1] for x in human], labels)
second_s = distribution([x[1] for x in synthetic], labels)
pairs = [(0, 0), (0, 1), (1, 0), (1, 1)]
joint_h = distribution(human, pairs)
joint_s = distribution(synthetic, pairs)

print("Q1 marginal TVD:", tvd(first_h, first_s))
print("Q2 marginal TVD:", tvd(second_h, second_s))
print("Joint TVD:", tvd(joint_h, joint_s))

# Example: actual humans shift 30% -> 38%; model predicts 30% -> 50%.
human_effect = 0.38 - 0.30
synthetic_effect = 0.50 - 0.30
print("Human intervention effect (pp):", round(human_effect * 100, 1))
print("Synthetic intervention effect (pp):", round(synthetic_effect * 100, 1))
print("Absolute effect error (pp):", round(abs(human_effect - synthetic_effect) * 100, 1))

assert tvd(first_h, first_s) == 0
assert tvd(second_h, second_s) == 0
assert tvd(joint_h, joint_s) == 1
assert round(abs(human_effect - synthetic_effect) * 100, 8) == 12
print("All assertions passed.")
