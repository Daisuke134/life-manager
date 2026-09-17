from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from job_search_loop.profile_setup import (
    ProfileSetupError,
    activate_profile,
    propose_profile,
)


def _facts():
    return [
        {"id": "ai-work", "claim": "Built AI agent workflows.", "evidence": "private evidence"},
        {"id": "jp", "claim": "Native Japanese speaker in Tokyo.", "evidence": "private evidence"},
    ]


def test_proposal_contains_only_verified_fact_ids_and_resume_hash(tmp_path: Path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"resume-v1")

    proposal = propose_profile(
        facts=_facts(),
        claims=[
            {"fact_id": "ai-work", "text": "Applied AI agent engineering", "section": "summary"},
            {"fact_id": "jp", "text": "Native Japanese; Tokyo based", "section": "languages"},
        ],
        resume_path=resume,
    )

    assert proposal["version"] == 1
    assert proposal["fact_ids"] == ["ai-work", "jp"]
    assert proposal["resume_sha256"] == hashlib.sha256(b"resume-v1").hexdigest()
    assert proposal["fields"]["claims"][0]["fact_id"] == "ai-work"


def test_proposal_rejects_unverified_claims_and_placeholders(tmp_path: Path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"resume-v1")

    with pytest.raises(ProfileSetupError, match="verified fact"):
        propose_profile(
            facts=_facts(),
            claims=[{"fact_id": "senior-engineer", "text": "Senior engineer"}],
            resume_path=resume,
        )
    with pytest.raises(ProfileSetupError, match="placeholder"):
        propose_profile(
            facts=_facts(),
            claims=[{"fact_id": "ai-work", "text": "REPLACE_ME"}],
            resume_path=resume,
        )


def test_profile_activates_only_after_authenticated_exact_readback(tmp_path: Path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"resume-v1")
    proposal = propose_profile(
        facts=_facts(),
        claims=[{"fact_id": "ai-work", "text": "Applied AI agent engineering"}],
        resume_path=resume,
    )

    assert activate_profile(proposal, {"authenticated": False}) is False
    assert activate_profile(proposal, {
        "authenticated": True,
        "profile_version": "wrong",
        "resume_visible": True,
        "parser_reviewed": True,
    }) is False
    assert activate_profile(proposal, {
        "authenticated": True,
        "profile_version": proposal["profile_version"],
        "resume_visible": True,
        "parser_reviewed": True,
        "field_hashes": {"claims": "stale"},
        "resume_sha256": proposal["resume_sha256"],
    }) is False
    assert activate_profile(proposal, {
        "authenticated": True,
        "profile_version": proposal["profile_version"],
        "resume_visible": True,
        "parser_reviewed": True,
        "field_hashes": proposal["field_hashes"],
        "resume_sha256": proposal["resume_sha256"],
    }) is True
