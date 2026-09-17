from __future__ import annotations

import hashlib
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from writer_learning_worker import validate_decision_evidence, validate_winner_observation


def valid_observation() -> dict:
    excerpt = "15,000 free subscribers, 500 paid"
    return {
        "source": {
            "url": "https://example.com/report",
            "title": "Public report",
            "kind": "public_source",
        },
        "observed_at": "2026-09-17T01:02:03Z",
        "evidence": {
            "excerpt": excerpt,
            "sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
        },
        "fact_or_inference": "fact",
        "transfer_hypothesis": "A focused weekly outcome may improve paid conversion.",
        "variable": "promise",
        "baseline_reference": {"article_id": "baseline-1", "sha256": "b" * 64},
        "candidate_reference": {"article_id": "candidate-1", "sha256": "c" * 64},
        "decision": "INCONCLUSIVE",
    }


def test_valid_winner_observation_is_normalized():
    result = validate_winner_observation(valid_observation())

    assert result["observed_at"] == "2026-09-17T01:02:03+00:00"
    assert result["decision"] == "INCONCLUSIVE"


@pytest.mark.parametrize(
    "field",
    ["source", "observed_at", "evidence", "fact_or_inference", "transfer_hypothesis",
     "variable", "baseline_reference", "candidate_reference", "decision"],
)
def test_missing_contract_field_is_rejected(field):
    observation = valid_observation()
    del observation[field]

    with pytest.raises(ValueError, match=field):
        validate_winner_observation(observation)


def test_self_asserted_evidence_is_rejected():
    observation = valid_observation()
    observation["source"] = {"url": "self://writer/article", "title": "Our claim", "kind": "self_asserted"}

    with pytest.raises(ValueError, match="self.asserted"):
        validate_winner_observation(observation)


def test_excerpt_hash_mismatch_is_rejected():
    observation = valid_observation()
    observation["evidence"]["sha256"] = "d" * 64

    with pytest.raises(ValueError, match="excerpt"):
        validate_winner_observation(observation)


def test_mixed_fact_and_inference_is_rejected():
    observation = valid_observation()
    observation["fact_or_inference"] = "fact_and_inference"

    with pytest.raises(ValueError, match="fact_or_inference"):
        validate_winner_observation(observation)


def test_two_changed_variables_are_rejected():
    observation = valid_observation()
    observation["variable"] = ["promise", "price"]

    with pytest.raises(ValueError, match="variable"):
        validate_winner_observation(observation)


def test_decision_evidence_requires_and_validates_winner_observation():
    decision = {"decision": "KEEP", "reason": "supports the hypothesis", "evidence_refs": ["receipt-1"]}
    with pytest.raises(ValueError, match="winner_observation"):
        validate_decision_evidence(decision)

    observation = valid_observation()
    observation["decision"] = "KEEP"
    decision["winner_observation"] = observation
    result = validate_decision_evidence(decision)
    assert result["winner_observation"]["decision"] == "KEEP"
