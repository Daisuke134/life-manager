from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys

import pytest


MODULE = Path(__file__).parents[1] / "scripts/contract_deadline.py"
SPEC = importlib.util.spec_from_file_location("contract_deadline_test", MODULE)
deadline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = deadline
assert SPEC.loader is not None
SPEC.loader.exec_module(deadline)


def _request(**overrides):
    value = {
        "platform": "crowdworks",
        "request_id": "1427391",
        "contract_id": "63570481",
        "requested_at": "2026-09-24T11:28:00+09:00",
        "due_at": "2026-10-01T23:59:59+09:00",
        "current_state": "requested",
        "agree_url": "https://crowdworks.jp/contract_termination_requests/1427391/agree",
        "reject_flow": "official_confirmation_dialog",
        "client_reason": "previous application within six months",
    }
    value.update(overrides)
    return value


def test_normalize_requires_identity_and_keeps_external_decision_out_of_record():
    normalized = deadline.normalize_contract_termination(_request())

    assert normalized.platform == "crowdworks"
    assert normalized.request_id == "1427391"
    assert normalized.contract_id == "63570481"
    assert normalized.due_at == "2026-10-01T14:59:59Z"
    assert normalized.reject_flow == "official_confirmation_dialog"
    assert not hasattr(normalized, "decision")


def test_deadline_classification_is_deterministic_and_fails_closed_when_missing():
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    assert deadline.classify_deadline(
        deadline.normalize_contract_termination(_request(due_at="2026-10-01T11:59:59Z")),
        now=now,
    ) == "overdue"
    assert deadline.classify_deadline(
        deadline.normalize_contract_termination(_request(due_at="2026-10-01T20:00:00Z")),
        now=now,
    ) == "urgent"
    assert deadline.classify_deadline(
        deadline.normalize_contract_termination(_request(due_at="2026-10-03T12:00:00Z")),
        now=now,
    ) == "upcoming"
    assert deadline.classify_deadline(
        deadline.normalize_contract_termination(_request(due_at=None)),
        now=now,
    ) == "unknown"


def test_invalid_timestamp_and_blank_identity_are_rejected():
    with pytest.raises(deadline.ContractDeadlineValidationError, match="due_at_invalid"):
        deadline.normalize_contract_termination(_request(due_at="tomorrow"))
    with pytest.raises(deadline.ContractDeadlineValidationError, match="request_id_invalid"):
        deadline.normalize_contract_termination(_request(request_id="  "))
    with pytest.raises(deadline.ContractDeadlineValidationError, match="timestamp_invalid"):
        deadline.normalize_timestamp("2026-10-01 12:00:00+09:00")
    with pytest.raises(deadline.ContractDeadlineValidationError, match="timestamp_invalid"):
        deadline.normalize_timestamp("2026-10-01T12:00:00+0900")
