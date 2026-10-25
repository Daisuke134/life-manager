"""Offline EBA developer-benchmark CLI; prints auditable JSON, never fields a live action."""
import json
from .benchmark import evaluate, select_candidate
from .fixtures import example_suite, example_submission


def main():
    """Run the declared toy baseline and test-only improvement path."""
    suite = example_suite()
    old = example_submission()
    new = example_submission()
    new["system"] = "handwritten-toy-candidate"
    new["answers"][0]["probability"] = .95
    new["answers"][1]["probability"] = .05
    baseline = evaluate(suite, old)
    candidate = evaluate(suite, new)
    print(json.dumps({"baseline":baseline, "candidate":candidate,
                      "selection":select_candidate(baseline,candidate)},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
