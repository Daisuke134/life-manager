from __future__ import annotations

import hashlib
import json
import re

from .contracts import CompletionEvidenceV1, FinalReviewReceiptV1, ObservationV1


_COMPLETION = re.compile(
    r"\b(?:your application has been submitted|application (?:was |has been )?submitted|"
    r"thank you for applying|we have received your application)\b|"
    r"応募(?:が|は|情報が)?(?:完了|送信されました)|応募を受け付けました|応募を受付",
    re.IGNORECASE,
)


def _contains(text: str, value: str) -> bool:
    return " ".join(value.split()).casefold() in " ".join(text.split()).casefold()


def verify_completion_ui(
    *,
    company: str,
    role: str,
    review: FinalReviewReceiptV1,
    observation: ObservationV1,
    require_receipt: bool = False,
) -> CompletionEvidenceV1:
    """Classify only freshly rendered UI; clicks, HTTP and Ledger are not inputs."""
    if observation.content_sha256 == review.observation_sha256:
        raise RuntimeError("completion verification requires a fresh observation")
    completion_visible = bool(_COMPLETION.search(observation.visible_text))
    identity_visible = _contains(observation.visible_text, company) and _contains(
        observation.visible_text, role
    )
    if completion_visible and (identity_visible or require_receipt):
        if require_receipt:
            outcome = "submit_unknown"
            evidence_class = "exact_completion_ui_pending_receipt"
        else:
            outcome = "submitted"
            evidence_class = "exact_completion_ui"
    elif observation.blocking_validation_text:
        outcome = "not_submitted"
        evidence_class = "rendered_validation_rejection"
    else:
        outcome = "submit_unknown"
        evidence_class = "no_authoritative_completion_ui"
    safe = {
        "outcome": outcome,
        "review_receipt_sha256": review.receipt_sha256,
        "observation_sha256": observation.content_sha256,
        "evidence_class": evidence_class,
        "identity_visible": identity_visible,
    }
    evidence_sha = hashlib.sha256(
        json.dumps(safe, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return CompletionEvidenceV1(1, evidence_sha256=evidence_sha, **safe)


def record_completion_evidence(ledger, intent_id: str, fence: int, evidence: CompletionEvidenceV1) -> None:
    """Write a terminal projection only through the Ledger's evidence gate."""
    ledger.complete_submission_verified(
        intent_id,
        fence,
        outcome=evidence.outcome,
        evidence_sha256=evidence.evidence_sha256,
        evidence_class=evidence.evidence_class,
    )
