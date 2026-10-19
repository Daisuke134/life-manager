"""Fictional lesson 9.3. Python standard library only; no real behavior claims.
Run this file to reproduce the counts and the separately constructed heldout example.
"""
from collections import Counter, defaultdict
import json

TRAIN = [("rain", 1)] * 8 + [("rain", 0)] * 2 + [("clear", 1)] * 2 + [("clear", 0)] * 8
# These are later, separate fictional occasions, not a randomized split of TRAIN.
TEST = [("rain", 1)] * 3 + [("rain", 0)] + [("clear", 1)] + [("clear", 0)] * 3

def fit(rows):
    grouped = defaultdict(Counter)
    for condition, bus in rows:
        grouped[condition][bus] += 1
    overall = sum(bus for _, bus in rows) / len(rows)
    rates = {c: counts[1] / sum(counts.values()) for c, counts in grouped.items()}
    return overall, rates

def evaluate(rows, probabilities):
    # Fixed rule: p >= .5 predicts bus, including ties.
    return {
        "n": len(rows),
        "accuracy": sum((p >= .5) == bool(y) for (_, y), p in zip(rows, probabilities)) / len(rows),
        "brier_binary": sum((p - y)**2 for (_, y), p in zip(rows, probabilities)) / len(rows),
    }

def run():
    overall, rates = fit(TRAIN)
    report = {
        "data_kind": "fictional teaching fixture, not real-world validation",
        "training_n": len(TRAIN), "overall_bus_probability": overall,
        "conditional_bus_probability": rates,
        "heldout_overall": evaluate(TEST, [overall] * len(TEST)),
        "heldout_conditional": evaluate(TEST, [rates.get(c, overall) for c, _ in TEST]),
        "laplace_binary_1_success_1_trial": (1 + 1)/(1 + 2),
        "warning": "Constructed data illustrate mechanics, not evidence that conditioning always improves prediction."
    }
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    run()
