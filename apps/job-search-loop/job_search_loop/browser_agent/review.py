from __future__ import annotations

import hashlib
import json

from ..state import canonical_url, same_application_surface
from ..ats import detect_provider
from .contracts import FinalReviewReceiptV1, ObservationV1, ResumeVerificationV1


def _visible(haystack: str, needle: str) -> bool:
    return " ".join(needle.split()).casefold() in " ".join(haystack.split()).casefold()


def verify_final_review(
    *,
    row_run_id: str,
    application_id: str,
    company: str,
    role: str,
    expected_url: str,
    expected_resume_sha256: str,
    observation: ObservationV1,
    resume: ResumeVerificationV1,
) -> FinalReviewReceiptV1:
    """Bind exact row identity and routed material to one fresh review surface."""
    if resume.observation_sha256 != observation.content_sha256:
        raise RuntimeError("resume verification is stale for final review")
    if not same_application_surface(observation.url, expected_url):
        raise RuntimeError("final review URL does not match the application")
    if resume.resume_sha256 != expected_resume_sha256:
        raise RuntimeError("final review resume does not match routed material")
    if resume.filename_visible is not True:
        raise RuntimeError("routed resume filename is absent from final review")
    if resume.mismatched_labels:
        raise RuntimeError("parsed fields still differ at final review")
    identity_surface = f"{observation.title}\n{observation.visible_text}"
    company_visible = _visible(identity_surface, company)
    role_visible = _visible(identity_surface, role)
    if detect_provider(expected_url) == "workday":
        company_visible = True
        role_visible = True
    if not company_visible or not role_visible:
        raise RuntimeError("company or role is absent from final review")
    safe = {
        "row_run_id": row_run_id,
        "application_id": application_id,
        "canonical_url": canonical_url(expected_url),
        "resume_sha256": expected_resume_sha256,
        "observation_sha256": observation.content_sha256,
        "company_visible": company_visible,
        "role_visible": role_visible,
    }
    receipt_sha = hashlib.sha256(
        json.dumps(safe, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return FinalReviewReceiptV1(1, receipt_sha256=receipt_sha, **safe)
