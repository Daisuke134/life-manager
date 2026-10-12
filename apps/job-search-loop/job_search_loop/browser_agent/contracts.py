from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class SessionHandleV1:
    schema_version: int
    endpoint: str
    row_run_id: str
    page_marker: str
    generation: int

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported SessionHandleV1 schema_version")
        if not self.row_run_id:
            raise ValueError("row_run_id is required")


@dataclass(frozen=True, slots=True)
class VisibleControlV1:
    tag: str
    role: str
    control_type: str
    label: str
    disabled: bool
    stable_id: str = ""
    checked: bool | None = None
    options: tuple[str, ...] = ()
    required: bool = False
    filled: bool = False


@dataclass(frozen=True, slots=True)
class ObservationV1:
    schema_version: int
    url: str
    title: str
    visible_text: str
    controls: tuple[VisibleControlV1, ...]
    validation_text: tuple[str, ...]
    tabs: tuple[str, ...]
    screenshot_path: Path
    screenshot_sha256: str
    content_sha256: str
    visible_challenges: tuple[str, ...] = ()
    blocking_validation_text: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionTargetV1:
    role: str
    label: str
    exact: bool = True
    stable_id: str = ""
    ordinal: int | None = None


@dataclass(frozen=True, slots=True)
class VisibleActionV1:
    kind: Literal["navigate", "click", "choose", "type", "select", "upload", "scroll", "wait"]
    target: ActionTargetV1 | None = None
    opener: ActionTargetV1 | None = None
    text: str | None = None
    url: str | None = None
    file_path: Path | None = None
    delta_y: int | None = None
    wait_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ActionReceiptV1:
    schema_version: int
    kind: str
    target_role: str | None
    target_label: str | None
    target_stable_id: str | None
    before_url: str
    after_url: str
    receipt_sha256: str
    fence_receipt_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyContextV1:
    row_goal: str
    fact_refs: tuple[str, ...]
    observation_sha256: str
    action_receipt_hashes: tuple[str, ...]
    remaining_steps: int
    validation_feedback: ValidationFeedbackV1 | None = None
    challenge_assessment: ChallengeAssessmentV1 | None = None


@dataclass(frozen=True, slots=True)
class ValidationFeedbackV1:
    schema_version: int
    observation_sha256: str
    messages: tuple[str, ...]
    related_controls: tuple[VisibleControlV1, ...]
    changed: bool


@dataclass(frozen=True, slots=True)
class ChallengeAssessmentV1:
    schema_version: int
    observation_sha256: str
    visible_providers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResumeVerificationV1:
    schema_version: int
    observation_sha256: str
    resume_sha256: str
    filename_visible: bool
    checked_labels: tuple[str, ...]
    mismatched_labels: tuple[str, ...]
    receipt_sha256: str


@dataclass(frozen=True, slots=True)
class ActionPlanV1:
    based_on_observation_sha256: str
    action: VisibleActionV1 | None = None
    transition: Literal["checkpointed", "ineligible", "post_submit_verification"] | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RowCheckpointV1:
    schema_version: int
    row_run_id: str
    stage: Literal["acting", "recovering", "checkpointed", "post_submit_verification"]
    page_marker: str
    session_generation: int
    observation_sha256: str
    action_receipt_hashes: tuple[str, ...]
    remaining_steps: int
    current_url: str = ""


@dataclass(frozen=True, slots=True)
class CheckpointReceiptV1:
    path: Path
    checkpoint_sha256: str


@dataclass(frozen=True, slots=True)
class StepEvidenceV1:
    schema_version: int
    row_run_id: str
    sequence: int
    predecessor_sha256: str | None
    before_observation_sha256: str
    action_receipt_sha256: str
    after_observation_sha256: str


@dataclass(frozen=True, slots=True)
class EvidenceReceiptV1:
    sequence: int
    evidence_sha256: str
    path: Path


@dataclass(frozen=True, slots=True)
class ResumeCursorV1:
    handle: SessionHandleV1
    checkpoint: RowCheckpointV1 | None
    evidence_predecessor_sha256: str | None
    needs_navigation: bool
    recovery_url: str


@dataclass(frozen=True, slots=True)
class QueueRowReceiptV1:
    application_id: str
    company: str
    role: str
    status: str
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class FinalReviewReceiptV1:
    schema_version: int
    row_run_id: str
    application_id: str
    canonical_url: str
    resume_sha256: str
    observation_sha256: str
    company_visible: bool
    role_visible: bool
    receipt_sha256: str


@dataclass(frozen=True, slots=True)
class SubmissionFenceLeaseV1:
    intent_id: str
    fence: int
    review_receipt_sha256: str
    observation_sha256: str
    expires_at: str
    capability: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class CompletionEvidenceV1:
    schema_version: int
    outcome: Literal["submitted", "not_submitted", "submit_unknown"]
    review_receipt_sha256: str
    observation_sha256: str
    evidence_class: str
    identity_visible: bool
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class FieldQuestionV1:
    label: str
    field_type: str
    required: bool
    options: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedAnswerV1:
    concept: str
    kind: Literal["exact", "derived", "generated", "conservative"]
    value: object
    provenance: tuple[str, ...]
    answer_sha256: str
