from __future__ import annotations

from datetime import datetime, timezone

import pytest

from job_search_loop.mental_outcome_projection import build_mental_outcome_projection


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

