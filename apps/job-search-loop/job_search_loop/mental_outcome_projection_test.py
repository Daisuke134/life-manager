from __future__ import annotations

from datetime import datetime, timezone

import pytest

from job_search_loop.mental_outcome_projection import build_mental_outcome_projection
from job_search_loop.mental_outcome_projection import publish_mental_outcome
from job_search_loop.mental_outcome_projection import project_model_outcomes


BASE = {
    "outcome_id": "outcome-1",
    "application_id": "app-1",
    "company": "Example社",
    "title": "Software Engineer",
    "funnel_stage": "interview",
    "disposition": "positive",
    "evidence_source": "gmail",
    "evidence_sha256": "a" * 64,
    "occurred_at": "2026-09-17T01:00:00+00:00",
    "observed_at": "2026-09-17T01:01:00+00:00",
}


def test_projection_contains_only_verified_structured_outcome():
    result = build_mental_outcome_projection(BASE)
    assert result == {
        "source_outcome_id": "job-search:outcome-1",
        "kind": "interview",
        "company": "Example社",
        "role": "Software Engineer",
        "verified_at": "2026-09-17T01:01:00+00:00",
        "evidence_ref": "job-search-outcome://outcome-1",
    }


def test_negative_interview_is_rejection_and_offer_requires_positive_disposition():
    assert build_mental_outcome_projection({**BASE, "disposition": "negative"})["kind"] == "rejection"
    with pytest.raises(ValueError, match="offer"):
        build_mental_outcome_projection({**BASE, "funnel_stage": "offer", "disposition": "negative"})


def test_untrusted_or_invalid_outcomes_are_rejected_without_projection():
    for patch in [
        {"evidence_source": "calendar"},
        {"evidence_sha256": "bad"},
        {"funnel_stage": "recruiter_response"},
        {"observed_at": "2026-09-17T00:00:00+00:00"},
        {"outcome_id": "bad id"},
    ]:
        with pytest.raises(ValueError):
            build_mental_outcome_projection({**BASE, **patch})


def test_publish_mental_outcome_sends_signed_normalized_payload_only():
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok":true,"result":"inserted"}'

    def opener(request, timeout):
        requests.append((request, timeout))
        return Response()

    outcome = build_mental_outcome_projection(BASE)
    result = publish_mental_outcome(
        outcome,
        endpoint="https://life-call.example.test/api/internal/mental/outcomes",
        secret="s" * 40,
        now=datetime(2026, 9, 17, 1, 2, tzinfo=timezone.utc),
        opener=opener,
    )
    assert result == {"status": "inserted", "http_status": 200}
    request, timeout = requests[0]
    assert timeout == 10
    assert request.full_url.startswith("https://")
    assert request.get_header("X-lm-outcome-signature")
    assert request.get_header("X-lm-outcome-timestamp")
    assert b'"source_outcome_id":"job-search:outcome-1"' in request.data
    assert b"body" not in request.data


def test_project_model_outcome_hashes_private_candidate_and_records_funnel_receipt():
    class Cursor:
        def fetchone(self):
            return {"company": "Example社", "title": "Software Engineer"}

    class Connection:
        def execute(self, sql, params):
            assert params == ("app-1",)
            return Cursor()

    class Ledger:
        connection = Connection()

        def record_funnel_outcome(self, **kwargs):
            assert kwargs["application_id"] == "app-1"
            assert kwargs["evidence_source"] == "gmail"
            return "outcome-recorded"

    result = {
        "outcomes": [{
            "application_id": "app-1", "funnel_stage": "interview", "disposition": "positive",
            "message_id": "gmail-message-1", "occurred_at": "2026-09-17T01:00:00+00:00",
            "observation_policy_version": None,
        }]
    }
    candidates = {"messages": [{
        "message_id": "gmail-message-1", "thread_id": "thread-1", "subject": "Interview",
        "sender": "recruiter@example.test", "received_at": "2026-09-17T01:00:00+00:00",
        "body": "private body stays local",
    }]}
    projected = project_model_outcomes(result, candidates, Ledger(), observed_at="2026-09-17T01:02:00+00:00")
    assert projected[0]["kind"] == "interview"
    assert projected[0]["source_outcome_id"] == "job-search:outcome-recorded"
    assert len(projected[0]["evidence_sha256"]) == 64
    assert "private body" not in str(projected[0])
