from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "opportunity_observation_store.py"


def _module():
    spec = importlib.util.spec_from_file_location("marketplace_opportunity_observation_store_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(**overrides):
    value = {
        "schema_version": 1,
        "provider": "coconala",
        "opportunity_id": "request:123",
        "source_url": "https://coconala.com/requests/123",
        "title": "案件タイトル",
        "currency": "JPY",
        "source_hash": "a" * 64,
        "observed_at": "2026-09-30T00:00:00Z",
        "decision": "hold",
        "reasons": ["missing_workflow"],
        "evidence_refs": ["snapshot://coconala/pass-1"],
        "next_action": "review_shared_workflow",
        "idempotency_key": "marketplace-opportunity:v1:coconala:request:123:" + "a" * 64,
    }
    value.update(overrides)
    return value


def test_first_observation_is_private_durable_and_readable(tmp_path):
    module = _module()
    store = module.OpportunityObservationStore(tmp_path / "opportunities")

    result = store.record(_record())

    assert result == {"status": "appended", "record": _record()}
    assert store.latest("coconala", "request:123") == _record()
    assert (tmp_path / "opportunities").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "opportunities" / "events.jsonl").stat().st_mode & 0o777 == 0o600


def test_replay_is_duplicate_and_conflict_is_fail_closed(tmp_path):
    module = _module()
    store = module.OpportunityObservationStore(tmp_path / "opportunities")
    store.record(_record())

    assert store.record(dict(_record()))["status"] == "duplicate"
    with pytest.raises(module.OpportunityObservationError, match="opportunity_idempotency_conflict"):
        store.record(_record(next_action="do_not_change_same_snapshot"))


def test_corrupt_tail_is_not_ignored(tmp_path):
    module = _module()
    root = tmp_path / "opportunities"
    root.mkdir(mode=0o700)
    events = root / "events.jsonl"
    events.write_text(json.dumps(_record(), sort_keys=True) + "\npartial")
    events.chmod(0o600)

    with pytest.raises(module.OpportunityObservationError, match="opportunity_state_corrupt"):
        module.OpportunityObservationStore(root).read_all()


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("source_url", "http://coconala.com/requests/123", "source_url_invalid"),
        ("decision", "promote", "decision_invalid"),
        ("currency", "jpy", "currency_invalid"),
    ],
)
def test_untrusted_observation_fields_are_rejected(tmp_path, field, value, reason):
    module = _module()
    record = _record(**{field: value})
    with pytest.raises(module.OpportunityObservationError, match=reason):
        module.OpportunityObservationStore(tmp_path / "opportunities").record(record)
