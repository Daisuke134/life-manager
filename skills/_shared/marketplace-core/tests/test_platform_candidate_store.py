from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "platform_candidate_store.py"


def _module():
    spec = importlib.util.spec_from_file_location("marketplace_platform_candidate_store_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(**overrides):
    value = {
        "schema_version": 1,
        "provider": "example-market",
        "candidate_id": "listing-123",
        "observed_at": "2026-09-29T00:00:00Z",
        "source_url": "https://example.test/listing-123",
        "snapshot_sha256": "a" * 64,
        "decision": "hold",
        "gates": {
            "policy": "pass",
            "adapter": "pass",
            "funded_work": "fail",
            "canary": "fail",
            "unit_economics": "fail",
        },
        "reasons": ["funded_work_missing"],
        "evidence_refs": ["snapshot://example-market/listing-123"],
        "next_action": "obtain an official funded-work receipt",
        "idempotency_key": (
            "marketplace-candidate:v1:example-market:listing-123:" + "a" * 64
        ),
    }
    value.update(overrides)
    return value


def test_first_record_is_durable_and_latest_reads_it(tmp_path):
    module = _module()
    store = module.CandidateStateStore(tmp_path / "candidate-state")

    result = store.record(_record())

    assert result["status"] == "appended"
    assert store.latest("example-market", "listing-123") == _record()
    state_path = tmp_path / "candidate-state" / "events.jsonl"
    assert state_path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "candidate-state").stat().st_mode & 0o777 == 0o700


def test_same_snapshot_is_idempotent_and_not_appended_twice(tmp_path):
    module = _module()
    store = module.CandidateStateStore(tmp_path / "candidate-state")
    record = _record()

    first = store.record(record)
    second = store.record(dict(record))

    assert first["status"] == "appended"
    assert second == {"status": "duplicate", "record": record}
    assert (tmp_path / "candidate-state" / "events.jsonl").read_text().count("\n") == 1


def test_same_snapshot_with_different_content_is_a_conflict(tmp_path):
    module = _module()
    store = module.CandidateStateStore(tmp_path / "candidate-state")
    store.record(_record())

    conflicting = _record(next_action="do not silently change the recorded action")
    with pytest.raises(module.CandidateStoreError, match="candidate_idempotency_conflict"):
        store.record(conflicting)


def test_corrupt_or_truncated_tail_fails_closed(tmp_path):
    module = _module()
    root = tmp_path / "candidate-state"
    root.mkdir(mode=0o700)
    state_path = root / "events.jsonl"
    state_path.write_text(json.dumps(_record(), sort_keys=True) + "\ntruncated")
    state_path.chmod(0o600)
    store = module.CandidateStateStore(root)

    with pytest.raises(module.CandidateStoreError, match="candidate_state_corrupt"):
        store.latest("example-market", "listing-123")
    with pytest.raises(module.CandidateStoreError, match="candidate_state_corrupt"):
        store.record(_record(snapshot_sha256="b" * 64, idempotency_key=(
            "marketplace-candidate:v1:example-market:listing-123:" + "b" * 64
        )))


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("provider", "../escape", "provider_invalid"),
        ("candidate_id", "../escape", "candidate_id_invalid"),
        ("source_url", "http://example.test/listing-123", "source_url_invalid"),
        ("snapshot_sha256", "not-a-hash", "snapshot_sha256_invalid"),
    ],
)
def test_untrusted_candidate_fields_are_rejected(tmp_path, field, value, reason):
    module = _module()
    store = module.CandidateStateStore(tmp_path / "candidate-state")
    record = _record(**{field: value})
    if field in {"provider", "candidate_id", "snapshot_sha256"}:
        provider = record["provider"]
        candidate_id = record["candidate_id"]
        snapshot = record["snapshot_sha256"]
        record["idempotency_key"] = f"marketplace-candidate:v1:{provider}:{candidate_id}:{snapshot}"

    with pytest.raises(module.CandidateStoreError, match=reason):
        store.record(record)
