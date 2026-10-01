from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys

import pytest


MODULE = Path(__file__).parents[1] / "scripts/eligibility.py"
SPEC = importlib.util.spec_from_file_location("marketplace_eligibility_test", MODULE)
eligibility = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = eligibility
assert SPEC.loader is not None
SPEC.loader.exec_module(eligibility)


NOW = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)


def opportunity(**overrides):
    value = {
        "external_id": "job-2",
        "buyer_external_id": "buyer-1",
    }
    value.update(overrides)
    return value


def history_row(**overrides):
    value = {
        "external_id": "job-1",
        "buyer_external_id": "buyer-1",
        "submitted_at": "2026-06-01T00:00:00Z",
    }
    value.update(overrides)
    return value


def test_same_buyer_within_cooldown_is_ineligible():
    result = eligibility.evaluate_reapplication(
        opportunity(), [history_row()], history_complete=True, cooldown_days=183, now=NOW
    )

    assert result.status == "ineligible"
    assert result.reason == "provider_reapply_cooldown"
    assert result.matched_buyer_id == "buyer-1"
    assert result.eligible_at == "2026-12-01T00:00:00Z"


def test_same_project_is_duplicate_even_when_cooldown_has_elapsed():
    result = eligibility.evaluate_reapplication(
        opportunity(external_id="job-1"),
        [history_row(submitted_at="2025-01-01T00:00:00Z")],
        history_complete=True,
        cooldown_days=183,
        now=NOW,
    )

    assert result.status == "ineligible"
    assert result.reason == "duplicate_project"


def test_incomplete_history_or_missing_buyer_fails_closed():
    incomplete = eligibility.evaluate_reapplication(
        opportunity(), [history_row()], history_complete=False, now=NOW
    )
    missing_buyer = eligibility.evaluate_reapplication(
        opportunity(buyer_external_id=None), [history_row()], history_complete=True, now=NOW
    )

    assert incomplete.status == missing_buyer.status == "unknown"
    assert incomplete.reason == "eligibility_unknown"
    assert missing_buyer.reason == "buyer_identity_missing"


def test_complete_history_with_old_other_buyer_is_eligible():
    result = eligibility.evaluate_reapplication(
        opportunity(),
        [history_row(buyer_external_id="buyer-2", submitted_at="2025-01-01T00:00:00Z")],
        history_complete=True,
        cooldown_days=183,
        now=NOW,
    )

    assert result.status == "eligible"
    assert result.reason == "eligible"


def test_malformed_history_timestamp_is_unknown_not_eligible():
    with pytest.raises(eligibility.EligibilityValidationError, match="submitted_at_invalid"):
        eligibility.evaluate_reapplication(
            opportunity(), [history_row(submitted_at="2026-06-01 00:00:00+00:00")],
            history_complete=True, now=NOW,
        )
