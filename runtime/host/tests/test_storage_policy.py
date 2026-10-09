import json
from pathlib import Path

import pytest
from runtime.host.storage_policy import load_storage_policy


def policy_fixture(tmp_path):
    path = tmp_path / "storage-policy.json"
    source = Path(__file__).resolve().parents[3] / "config/storage-policy.json"
    path.write_bytes(source.read_bytes())
    (tmp_path / "loop-registry.json").write_text(json.dumps({"loops": {"alpha": {}}}))
    return path


def test_policy_applies_only_to_registered_owner_and_has_bounded_bytes(tmp_path):
    path = policy_fixture(tmp_path)
    value = load_storage_policy(path, "alpha")
    assert value.owner_id == "alpha"
    assert value.diagnostic_segment_bytes == 1048576
    assert value.diagnostic_backup_count == 1
    assert value.chunk_bytes == 4096
    assert value.head_bytes == 32768
    assert value.structured_record_max_bytes == 16777216
    assert load_storage_policy(path, "foreign") is None


def test_policy_rejects_bool_negative_and_unknown_fields(tmp_path):
    path = policy_fixture(tmp_path)
    original = json.loads(path.read_text())
    for key, value in [("chunk_bytes", True), ("head_bytes", -1), ("arbitrary_path", "/tmp")]:
        candidate = json.loads(json.dumps(original))
        candidate["defaults"][key] = value
        path.write_text(json.dumps(candidate))
        with pytest.raises(ValueError):
            load_storage_policy(path, "alpha")


def test_policy_owner_override_does_not_affect_other_owner(tmp_path):
    path = policy_fixture(tmp_path)
    value = json.loads(path.read_text())
    value["owners"] = {"alpha": {"diagnostic_segment_bytes": 65536}}
    path.write_text(json.dumps(value))
    assert load_storage_policy(path, "alpha").diagnostic_segment_bytes == 65536
