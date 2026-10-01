from __future__ import annotations

import importlib.util
import errno
import fcntl
from pathlib import Path
import sys
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "scripts" / "application_transaction.py"


def load():
    spec = importlib.util.spec_from_file_location("shared_hourly_application_transaction_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_hourly_terms_are_receipt_backed_and_replay_zero(tmp_path):
    module = load()
    submitted = []
    receipts = []
    arguments = dict(
        platform="crowdworks",
        opportunity={"external_id": "13435160", "title": "WordPress・PHP開発"},
        proposal_text="対応できます。",
        proposed_amount_minor=2000,
        delivery_due_on=None,
        pricing_mode="hourly",
        weekly_limit_hours=30,
        state_path=tmp_path / "application.json",
        account_ready=lambda: True,
        submitter=lambda *args: submitted.append(args) or {"proposal_id": "305200001"},
        readback=lambda proposal_id, project_id: {
            "proposal_id": proposal_id,
            "project_id": project_id,
            "pricing_mode": "hourly",
            "hourly_rate_minor": 2000,
            "weekly_limit_hours": 30,
        },
        ledger_writer=receipts.append,
        now=lambda: "2026-09-09T09:00:00Z",
    )

    first = module.run_transaction(**arguments)
    second = module.run_transaction(**arguments)

    assert first.ok and first.submitted and first.application_verified
    assert second.ok and not second.submitted and second.reason == "duplicate_project"
    assert len(submitted) == 1
    assert len(receipts) == 1
    assert receipts[0]["opportunity_external_id"] == "13435160"
    assert receipts[0]["application_external_id"] == "305200001"
    assert receipts[0]["pricing_mode"] == "hourly"
    assert receipts[0]["proposed_hourly_rate_minor"] == 2000
    assert receipts[0]["weekly_limit_hours"] == 30


def test_account_lock_timeout_raises_without_waiting(tmp_path):
    module = load()
    attempts = []

    def flock(_fd, operation):
        attempts.append(operation)
        if operation & fcntl.LOCK_NB:
            raise BlockingIOError(errno.EAGAIN, "busy")

    with patch.object(module.fcntl, "flock", side_effect=flock):
        try:
            with module.account_lock(tmp_path / "work-sync.json", timeout_seconds=0):
                raise AssertionError("lock must not be acquired")
        except module._AccountLockBusy:
            pass

    assert attempts
    assert attempts[0] & fcntl.LOCK_NB


def test_ineligible_application_stops_before_claim_or_provider_submit(tmp_path):
    module = load()
    submitted = []
    result = module.run_transaction(
        platform="crowdworks",
        opportunity={"external_id": "13435160", "buyer_external_id": "buyer-1"},
        proposal_text="対応できます。",
        proposed_amount_minor=2000,
        delivery_due_on="2026-10-08",
        state_path=tmp_path / "application.json",
        account_ready=lambda: True,
        eligibility_check=lambda _opportunity: {
            "status": "ineligible", "reason": "provider_reapply_cooldown",
        },
        submitter=lambda *args: submitted.append(args) or {"proposal_id": "proposal-1"},
        readback=lambda *_args: {},
        ledger_writer=lambda _receipt: None,
        now=lambda: "2026-09-09T09:00:00Z",
    )

    assert result.ok is True
    assert result.submitted is False
    assert result.reason == "provider_reapply_cooldown"
    assert submitted == []
    assert not (tmp_path / "application.json").exists()


def test_unknown_eligibility_stops_before_provider_submit(tmp_path):
    module = load()
    submitted = []
    result = module.run_transaction(
        platform="crowdworks",
        opportunity={"external_id": "13435160", "buyer_external_id": "buyer-1"},
        proposal_text="対応できます。",
        proposed_amount_minor=2000,
        delivery_due_on="2026-10-08",
        state_path=tmp_path / "application.json",
        account_ready=lambda: True,
        eligibility_check=lambda _opportunity: {
            "status": "unknown", "reason": "eligibility_unknown",
        },
        submitter=lambda *args: submitted.append(args) or {"proposal_id": "proposal-1"},
        readback=lambda *_args: {},
        ledger_writer=lambda _receipt: None,
        now=lambda: "2026-09-09T09:00:00Z",
    )

    assert result.ok is False
    assert result.error == "eligibility_unknown"
    assert result.reason == "eligibility_unknown"
    assert submitted == []
    assert not (tmp_path / "application.json").exists()
