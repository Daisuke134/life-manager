from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from ..ats import detect_provider
from ..ledger import Ledger
from ..resume_routing import select_resume
from ..state import provider_recovery_url
from ..workday_credentials import tenant_key
from .actions import ActionExecutor
from .candidate_memory import CandidateMemoryView
from .checkpoint import CheckpointStore, EvidenceStore
from .completion import record_completion_evidence, verify_completion_ui
from .contracts import (
    ActionTargetV1,
    QueueRowReceiptV1,
    RowCheckpointV1,
    StepEvidenceV1,
    VisibleActionV1,
)
from .observation import ObservationBuilder
from .outcome_reporting import send_hourly_outcomes
from .queue import RowQueueSupervisor
from .resume import ResumeVerifier
from .resume_cursor import RowResumer
from .review import verify_final_review
from .session import BrowserSession
from .submission_fence import SubmissionFence
from .workday_account import MachineWorkdayCredentialStore


_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
_WAKE_STEP_BUDGET = 100


def _path_env(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return Path(value)


@contextmanager
def _exclusive_terminal_effect():
    path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "terminal-effect.lock"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _terminal_failure_path() -> Path:
    return _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "terminal-failure.json"


def _active_command_path() -> Path:
    return _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "active-command.json"


def _write_terminal_failure_marker_locked() -> None:
    path = _terminal_failure_path()
    payload = b'{"reason":"runtime_failure","status":"terminal"}\n'
    try:
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
    except FileExistsError:
        return
    with os.fdopen(descriptor, "wb") as marker:
        marker.write(payload)
        marker.flush()
        os.fsync(marker.fileno())


def _write_terminal_failure_marker() -> None:
    with _exclusive_terminal_effect():
        _write_terminal_failure_marker_locked()


def _claim_active_command() -> None:
    with _exclusive_terminal_effect():
        if _terminal_failure_path().exists():
            raise RuntimeError("terminal runtime failure already recorded")
        active = _active_command_path()
        if active.exists():
            _write_terminal_failure_marker_locked()
            raise RuntimeError("terminal runtime failure already recorded")
        descriptor = os.open(
            active, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "wb") as marker:
            marker.write(b'{"reason":"command_active","status":"active"}\n')
            marker.flush()
            os.fsync(marker.fileno())


def _clear_active_command() -> None:
    with _exclusive_terminal_effect():
        if _terminal_failure_path().exists():
            return
        _active_command_path().unlink(missing_ok=True)


def _check_terminal_failure_marker() -> None:
    if _terminal_failure_path().exists():
        raise RuntimeError("terminal runtime failure already recorded")


def _redact(value: str) -> str:
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", value))


def _owner_endpoint() -> str:
    owner = json.loads(_path_env("JOB_SEARCH_BROWSER_OWNER_EVIDENCE").read_text())
    if owner.get("status") != "ready" or not owner.get("endpoint"):
        raise RuntimeError("browser owner is not ready")
    return str(owner["endpoint"])


def _wake_budget_path() -> Path:
    return _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "wake-step-budget.json"


def _decision_path() -> Path:
    return _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "last-decision.json"


@contextmanager
def _exclusive_action():
    path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "action.lock"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("another browser action is already in progress") from error
        yield


@contextmanager
def _exclusive_command():
    """Serialize model-issued runtime commands, including read observations."""
    path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "command.lock"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "another browser runtime command is already in progress"
            ) from error
        yield


def _wake_completed_path() -> Path:
    return _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "completed-rows.json"


def _wake_completed() -> set[str]:
    path = _wake_completed_path()
    if not path.exists():
        return set()
    if path.stat().st_mode & 0o077:
        raise RuntimeError("wake completed-row state must be private")
    value = json.loads(path.read_text(encoding="utf-8"))
    return {str(item) for item in value.get("application_ids", [])}


def _mark_wake_completed(application_id: str) -> None:
    path = _wake_completed_path()
    completed = _wake_completed()
    completed.add(application_id)
    path.write_text(
        json.dumps({"application_ids": sorted(completed)}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _decision_signature(observation_sha256: str, action_bytes: bytes) -> str:
    return hashlib.sha256(
        observation_sha256.encode("ascii") + b"\0" + action_bytes
    ).hexdigest()


def _reject_repeated_decision(observation_sha256: str, action_bytes: bytes) -> str:
    signature = _decision_signature(observation_sha256, action_bytes)
    path = _decision_path()
    if path.exists():
        if path.stat().st_mode & 0o077:
            raise RuntimeError("last decision record must be private")
        prior = json.loads(path.read_text(encoding="utf-8"))
        if prior.get("signature") == signature:
            raise RuntimeError("same action on unchanged observation is prohibited")
    return signature


def _record_decision(signature: str) -> None:
    path = _decision_path()
    path.write_text(json.dumps({"signature": signature}, sort_keys=True) + "\n")
    os.chmod(path, 0o600)


def _wake_budget(*, consume: bool = False) -> int:
    """Bound one owner wake without carrying exhaustion into the next wake."""

    path = _wake_budget_path()
    if path.exists():
        if path.stat().st_mode & 0o077:
            raise RuntimeError("wake step budget must be private")
        remaining = int(json.loads(path.read_text(encoding="utf-8"))["remaining_steps"])
    else:
        remaining = _WAKE_STEP_BUDGET
    if consume:
        if remaining < 1:
            raise RuntimeError("wake step budget exhausted")
        remaining -= 1
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(
            json.dumps({"remaining_steps": remaining}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(path, 0o600)
    return remaining


def _row() -> dict[str, Any]:
    ledger = Ledger(_path_env("JOB_SEARCH_STATE_ROOT") / "ledger.sqlite3")
    try:
        completed = _wake_completed()
        rows = [
            row
            for row in RowQueueSupervisor.collect(ledger)
            if row["application_id"] not in completed
        ]
        if not rows and RowQueueSupervisor.admit_next_discovered_workday(ledger):
            rows = [
                row
                for row in RowQueueSupervisor.collect(ledger)
                if row["application_id"] not in completed
            ]
    finally:
        ledger.close()
    if not rows:
        raise RuntimeError("no eligible active-provider row")
    return rows[0]


def _role_family(title: str) -> str:
    return (
        "technical_business"
        if re.search(
            r"solutions|customer success|partnership|sales|account executive|product",
            title,
            re.IGNORECASE,
        )
        else "applied_ai"
    )


def _routed_resume(row: dict[str, Any], posting_text: str) -> dict[str, str]:
    ledger = Ledger(_path_env("JOB_SEARCH_STATE_ROOT") / "ledger.sqlite3")
    try:
        assignment = ledger.strategy_assignment(row["application_id"])
    finally:
        ledger.close()
    legacy = assignment["capture_status"] == "legacy_unavailable"
    routed = select_resume(
        posting_text=posting_text,
        role_family=(
            _role_family(str(row["title"])) if legacy else assignment["role_family"]
        ),
        materials_root=_materials_root(),
    )
    if not legacy and routed["resume_sha256"] != assignment["material_sha256"]:
        raise RuntimeError("routed resume differs from the immutable assignment")
    return routed


def _safe_observation(observation, checkpoint, remaining_steps: int) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []
    for control in observation.controls:
        if not (control.label or control.stable_id):
            continue
        if control.role in {"link", "presentation"}:
            continue
        value: dict[str, Any] = {
            "role": control.role,
            "label": _redact(control.label),
            "stable_id": control.stable_id,
        }
        if control.control_type:
            value["type"] = control.control_type
        if control.disabled:
            value["disabled"] = True
        if control.required:
            value["required"] = True
        if control.filled:
            value["filled"] = True
        if control.checked is not None:
            value["checked"] = control.checked
        if control.options:
            value["options"] = [_redact(option) for option in control.options]
        controls.append(value)
    return {
        "url": observation.url,
        "title": _redact(observation.title),
        "content_sha256": observation.content_sha256,
        "validation": [_redact(value) for value in observation.validation_text],
        "challenges": list(observation.visible_challenges),
        "remaining_steps": remaining_steps,
        "controls": controls,
    }


async def _context():
    row = _row()
    state_root = _path_env("JOB_SEARCH_BROWSER_STATE_ROOT")
    session = BrowserSession()
    checkpoints = CheckpointStore(state_root)
    evidence = EvidenceStore(state_root)
    cursor = await RowResumer(session, checkpoints, evidence).restore(
        _owner_endpoint(), row["application_id"], row["canonical_url"]
    )
    builder = ObservationBuilder(
        session, _path_env("JOB_SEARCH_BROWSER_OWNER_EVIDENCE").parent
    )
    return row, session, checkpoints, evidence, cursor, builder


async def observe() -> dict[str, Any]:
    try:
        row, _session, _checkpoints, _evidence, cursor, builder = await _context()
    except RuntimeError as error:
        if str(error) != "no eligible active-provider row":
            raise
        return {
            "status": "queue_complete",
            "remaining_rows": 0,
            "instruction": "return the accumulated typed outcomes now",
        }
    observation = await builder.build(cursor.handle)
    credential_known = False
    account_status = "not_workday"
    if detect_provider(row["canonical_url"]) == "workday":
        credential_store = MachineWorkdayCredentialStore(
            _path_env("JOB_SEARCH_MACHINE_CREDENTIALS")
        )
        credential_known = tenant_key(row["canonical_url"]) in credential_store.known_tenants()
        account_status = credential_store.account_status(row["canonical_url"])
    candidate_memory = CandidateMemoryView.load(
        _path_env("JOB_SEARCH_CANDIDATE_MEMORY")
    )
    candidate_concepts = (
        *(concept for concept in candidate_memory.concepts() if concept.startswith("candidate.")),
        "policy.prefer_not_to_say",
    )
    result = {
        "status": "observed",
        "row": {
            "application_id": row["application_id"],
            "company": row["company"],
            "role": row["title"],
            "canonical_url": row["canonical_url"],
            "workday_credential_known": credential_known,
            "workday_account_status": account_status,
        },
        "needs_navigation": cursor.needs_navigation,
        "recovery_url": cursor.recovery_url if cursor.needs_navigation else None,
        "observation": _safe_observation(observation, cursor.checkpoint, _wake_budget()),
        **({} if cursor.needs_navigation else {"candidate_concepts": candidate_concepts, "grounding_facts": candidate_memory.grounding_facts()}),
    }
    return result


def _private_action(path: Path) -> dict[str, Any]:
    scratch = _path_env("JOB_SEARCH_BROWSER_SCRATCH").resolve()
    resolved = path.resolve(strict=True)
    if path.is_symlink() or resolved.parent != scratch or not resolved.is_file():
        raise RuntimeError("action file must be a regular file in browser scratch")
    os.chmod(resolved, 0o600)
    value = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("action file must contain an object")
    return value


def _action(value: dict[str, Any]) -> VisibleActionV1:
    target_value = value.get("target")
    target = None
    if isinstance(target_value, dict):
        target = ActionTargetV1(
            role=str(target_value.get("role") or ""),
            label=str(target_value.get("label") or ""),
            exact=bool(target_value.get("exact", True)),
            stable_id=str(target_value.get("stable_id") or ""),
            ordinal=target_value.get("ordinal"),
        )
    opener_value = value.get("opener")
    opener = None
    if isinstance(opener_value, dict):
        opener = ActionTargetV1(
            role=str(opener_value.get("role") or ""),
            label=str(opener_value.get("label") or ""),
            exact=bool(opener_value.get("exact", True)),
            stable_id=str(opener_value.get("stable_id") or ""),
        )
    text = value.get("text")
    concept = value.get("candidate_concept")
    if concept:
        if concept == "policy.prefer_not_to_say":
            resolved = "Prefer not to say"
        else:
            memory = CandidateMemoryView.load(_path_env("JOB_SEARCH_CANDIDATE_MEMORY"))
            resolved = memory.get(str(concept))
        if not isinstance(resolved, (str, int, float)):
            raise ValueError("candidate concept is not a scalar browser value")
        text = str(resolved)
    file_path = Path(value["file_path"]) if value.get("file_path") else None
    kind = value.get("kind", value.get("action", value.get("type")))
    if not kind:
        if target is not None and text is not None:
            kind = "type"
        elif value.get("url"):
            kind = "navigate"
        elif target is not None and value.get("file_path"):
            kind = "upload"
        elif value.get("delta_y") is not None:
            kind = "scroll"
        elif value.get("wait_ms") is not None:
            kind = "wait"
        else:
            raise ValueError("action intent is ambiguous")
    return VisibleActionV1(
        kind=str(kind),
        target=target,
        opener=opener,
        text=str(text) if text is not None else None,
        url=str(value["url"]) if value.get("url") else None,
        file_path=file_path,
        delta_y=value.get("delta_y"),
        wait_ms=value.get("wait_ms"),
    )


async def _act_locked(action_path: Path) -> dict[str, Any]:
    row, session, checkpoints, evidence, cursor, builder = await _context()
    before = await builder.build(cursor.handle)
    action_value = _private_action(action_path)
    action = _action(action_value)
    action_bytes = json.dumps(
        action_value, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    decision_signature = (
        _decision_signature(before.content_sha256, action_bytes)
        if action.kind == "wait"
        else _reject_repeated_decision(before.content_sha256, action_bytes)
    )
    remaining = _wake_budget(consume=True)
    receipt = await ActionExecutor(session).execute(cursor.handle, action)
    after = await builder.build(cursor.handle)
    parsed_after_url = urlparse(after.url)
    valid_after_url = parsed_after_url.scheme == "https" and bool(parsed_after_url.hostname)
    chain = evidence.read_chain(row["application_id"])
    evidence_receipt = evidence.append(
        StepEvidenceV1(
            1,
            row["application_id"],
            len(chain),
            chain[-1].evidence_sha256 if chain else None,
            before.content_sha256,
            receipt.receipt_sha256,
            after.content_sha256,
        )
    )
    prior_hashes = cursor.checkpoint.action_receipt_hashes if cursor.checkpoint else ()
    checkpoint_receipt = checkpoints.save(
        RowCheckpointV1(
            1,
            row["application_id"],
            "acting" if remaining and valid_after_url else "checkpointed",
            cursor.handle.page_marker,
            cursor.handle.generation,
            after.content_sha256,
            (*prior_hashes, receipt.receipt_sha256),
            remaining if valid_after_url else 0,
            after.url if valid_after_url else "",
        )
    )
    _record_decision(decision_signature)
    if not valid_after_url:
        _write_terminal_failure_marker()
        return {
            "status": "transport_failed",
            "error_class": "post_action_context_unavailable",
            "retryable": False,
            "next_action": "preserve the action receipt and do not replay this target in the current wake",
            "action_receipt_sha256": receipt.receipt_sha256,
            "evidence_sha256": evidence_receipt.evidence_sha256,
            "checkpoint_sha256": checkpoint_receipt.checkpoint_sha256,
        }
    return {
        "status": "acted",
        "action": {
            key: value
            for key, value in asdict(receipt).items()
            if key not in {"before_url", "after_url"}
        },
        "evidence_sha256": evidence_receipt.evidence_sha256,
        "checkpoint_sha256": checkpoint_receipt.checkpoint_sha256,
        "observation": _safe_observation(
            after, checkpoints.load(row["application_id"]), remaining
        ),
    }


async def act(action_path: Path) -> dict[str, Any]:
    with _exclusive_action():
        return await _act_locked(action_path)


async def type_text(*, label: str, role: str, stable_id: str, text: str) -> dict[str, Any]:
    """Type one model-grounded visible answer without an intermediate file."""
    scratch = _path_env("JOB_SEARCH_BROWSER_SCRATCH")
    path = scratch / "literal-action.json"
    path.write_text(
        json.dumps(
            {
                "kind": "type",
                "target": {
                    "role": role,
                    "label": label,
                    "exact": True,
                    "stable_id": stable_id,
                },
                "text": text,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    try:
        try:
            with _exclusive_action():
                return await _act_locked(path)
        except RuntimeError as error:
            if "action target must resolve to exactly one visible enabled control" in str(error):
                reason = "observed_text_target_no_longer_visible"
            elif "visible text target did not accept whole-value selection" in str(error):
                reason = "observed_text_target_lost_focus"
            else:
                raise
            result = await observe()
            result["status"] = "action_rejected"
            result["reason"] = reason
            return result
    finally:
        path.unlink(missing_ok=True)


async def auth(
    *, mode: str, field: str, label: str, role: str, stable_id: str
) -> dict[str, Any]:
    """Type exactly one Workday credential field without exposing its value."""
    if mode not in {"sign_in", "create_account"}:
        raise ValueError("auth mode must be sign_in or create_account")
    if field not in {"email", "password", "verify_password"}:
        raise ValueError("auth field is invalid")
    if field == "verify_password" and mode != "create_account":
        raise ValueError("verify_password is only valid for create_account")
    if role not in {"textbox", "searchbox"}:
        result = await observe()
        result["status"] = "action_rejected"
        result["reason"] = "auth_requires_textbox_role"
        return result
    with _exclusive_action():
        row, session, checkpoints, evidence, cursor, builder = await _context()
        before = await builder.build(cursor.handle)
        store = MachineWorkdayCredentialStore(
            _path_env("JOB_SEARCH_MACHINE_CREDENTIALS")
        )
        safe = store.ensure(
            job_url=row["canonical_url"], profile_path=_path_env("JOB_SEARCH_PROFILE")
        )
        credentials = store.load(row["canonical_url"])
        value = (
            credentials["application_email"]
            if field == "email"
            else credentials["password"]
        )
        descriptor = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "runtime-auth.json"
        descriptor.write_text(
            json.dumps(
                {
                    "mode": mode,
                    "field": field,
                    "label": label,
                    "role": role,
                    "stable_id": stable_id,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(descriptor, 0o600)
        decision_signature = _reject_repeated_decision(
            before.content_sha256, descriptor.read_bytes()
        )
        remaining = _wake_budget(consume=True)
        receipt = await ActionExecutor(session).execute(
            cursor.handle,
            VisibleActionV1(
                "type",
                target=ActionTargetV1(
                    role=role,
                    label=label,
                    exact=True,
                    stable_id=stable_id,
                ),
                text=value,
            ),
        )
        after = await builder.build(cursor.handle)
        chain = evidence.read_chain(row["application_id"])
        evidence_receipt = evidence.append(
            StepEvidenceV1(
                1,
                row["application_id"],
                len(chain),
                chain[-1].evidence_sha256 if chain else None,
                before.content_sha256,
                receipt.receipt_sha256,
                after.content_sha256,
            )
        )
        prior_hashes = (
            cursor.checkpoint.action_receipt_hashes if cursor.checkpoint else ()
        )
        checkpoint_receipt = checkpoints.save(
            RowCheckpointV1(
                1,
                row["application_id"],
                "acting" if remaining else "checkpointed",
                cursor.handle.page_marker,
                cursor.handle.generation,
                after.content_sha256,
                (*prior_hashes, receipt.receipt_sha256),
                remaining,
                after.url,
            )
        )
        _record_decision(decision_signature)
        return {
            "status": "acted",
            "mode": mode,
            "field": field,
            "tenant": safe["tenant"],
            "email_sha256": safe["email_sha256"],
            "action_receipt_sha256": receipt.receipt_sha256,
            "evidence_sha256": evidence_receipt.evidence_sha256,
            "checkpoint_sha256": checkpoint_receipt.checkpoint_sha256,
            "observation": _safe_observation(
                after, checkpoints.load(row["application_id"]), remaining
            ),
        }


async def navigate(url: str) -> dict[str, Any]:
    path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "runtime-navigate.json"
    path.write_text(
        json.dumps({"kind": "navigate", "url": url}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return await act(path)


async def click(*, label: str, role: str, stable_id: str, ordinal: int | None = None) -> dict[str, Any]:
    row = _row()
    if (
        detect_provider(row["canonical_url"]) == "workday"
        and stable_id == "automation:forgotPasswordLink"
        and MachineWorkdayCredentialStore(
            _path_env("JOB_SEARCH_MACHINE_CREDENTIALS")
        ).account_status(row["canonical_url"])
        == "recovery_requested"
    ):
        return await checkpoint("email_recovery")
    if (
        detect_provider(row["canonical_url"]) == "workday"
        and stable_id
        in {"automation:createAccountLink", "automation:createAccountSubmitButton"}
        and MachineWorkdayCredentialStore(
            _path_env("JOB_SEARCH_MACHINE_CREDENTIALS")
        ).account_status(row["canonical_url"])
        in {"create_submitted", "signed_in"}
    ):
        result = await observe()
        result["status"] = "action_rejected"
        result["reason"] = "workday_account_already_create_submitted"
        return result
    normalized_label = " ".join(label.split()).casefold()
    if (
        stable_id == "automation:pageFooterNextButton"
        and normalized_label in {"submit", "submit application", "送信", "応募を送信"}
    ):
        return await finalize()
    path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "runtime-click.json"
    path.write_text(
        json.dumps(
            {
                "kind": "click",
                "target": {"label": label, "role": role, "stable_id": stable_id, "ordinal": ordinal},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    result = await act(path)
    observation = result.get("observation", {})
    validation = (
        observation.get("validation", []) if isinstance(observation, dict) else []
    )
    if detect_provider(row["canonical_url"]) == "workday" and not validation:
        store = MachineWorkdayCredentialStore(
            _path_env("JOB_SEARCH_MACHINE_CREDENTIALS")
        )
        if stable_id == "automation:createAccountSubmitButton":
            store.mark_account_status(row["canonical_url"], "create_submitted")
        elif stable_id == "automation:signInSubmitButton":
            visible_ids = {
                str(control.get("stable_id") or "")
                for control in observation.get("controls", [])
                if isinstance(control, dict)
            }
            signed_in = (
                "automation:signInSubmitButton" not in visible_ids
                and str(observation.get("title") or "").strip().casefold() != "sign in"
            )
            prior_status = store.account_status(row["canonical_url"])
            next_status = "signed_in" if signed_in else "create_submitted"
            if not signed_in and prior_status == "recovery_requested":
                next_status = "recovery_requested"
            store.mark_account_status(
                row["canonical_url"], next_status
            )
    return result


async def choose(
    *, field_label: str, field_role: str, field_stable_id: str,
    option_label: str, option_role: str, option_stable_id: str,
) -> dict[str, Any]:
    """Open one observed custom field and click one observed option atomically."""
    path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "runtime-choose.json"
    path.write_text(
        json.dumps(
            {
                "kind": "choose",
                "opener": {
                    "label": field_label,
                    "role": field_role,
                    "stable_id": field_stable_id,
                },
                "target": {
                    "label": option_label,
                    "role": option_role,
                    "stable_id": option_stable_id,
                },
            },
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    try:
        return await act(path)
    except RuntimeError as error:
        if "action target must resolve to exactly one visible enabled control" not in str(error):
            raise
        result = await observe()
        result["status"] = "action_rejected"
        result["reason"] = "observed_option_no_longer_visible"
        return result


async def type_candidate(
    *, label: str, role: str, stable_id: str, candidate_concept: str
) -> dict[str, Any]:
    if role not in {"textbox", "searchbox", "spinbutton", "combobox"}:
        result = await observe()
        result["status"] = "action_rejected"
        result["reason"] = "type_requires_text_control"
        return result
    path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "runtime-type.json"
    path.write_text(
        json.dumps(
            {
                "kind": "type",
                "target": {"label": label, "role": role, "stable_id": stable_id},
                "candidate_concept": candidate_concept,
                **({"text": ""} if not candidate_concept else {}),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    try:
        return await act(path)
    except (RuntimeError, ValueError) as error:
        if str(error) == "candidate concept is not a scalar browser value":
            reason = "candidate_concept_requires_scalar_value"
        elif "visible text target did not accept whole-value selection" in str(error):
            reason = "observed_text_target_lost_focus"
        else:
            raise
        result = await observe()
        result["status"] = "action_rejected"
        result["reason"] = reason
        return result


async def upload_resume(*, label: str, role: str, stable_id: str) -> dict[str, Any]:
    """Upload the row's immutable assigned resume without exposing its path."""
    if role != "button":
        result = await observe()
        result["status"] = "action_rejected"
        result["reason"] = "upload_requires_button_control"
        return result
    row, _session, _checkpoints, _evidence, cursor, builder = await _context()
    observation = await builder.build(cursor.handle)
    routed = _routed_resume(row, f"{row['title']}\n{observation.visible_text}")
    path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "runtime-upload.json"
    path.write_text(
        json.dumps(
            {
                "kind": "upload",
                "target": {"label": label, "role": role, "stable_id": stable_id},
                "file_path": routed["resume_path"],
            },
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    try:
        return await act(path)
    except TimeoutError:
        result = await observe()
        result["status"] = "action_rejected"
        result["reason"] = "upload_control_did_not_open_file_chooser"
        return result


async def wait(milliseconds: int) -> dict[str, Any]:
    if milliseconds < 1 or milliseconds > 10_000:
        raise ValueError("wait milliseconds must be between 1 and 10000")
    path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "runtime-wait.json"
    path.write_text(
        json.dumps({"kind": "wait", "wait_ms": milliseconds}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return await act(path)


async def checkpoint(reason: str) -> dict[str, Any]:
    row, session, checkpoints, _evidence, cursor, builder = await _context()
    observation = await builder.build(cursor.handle)
    if reason == "email_recovery" and detect_provider(row["canonical_url"]) == "workday":
        MachineWorkdayCredentialStore(
            _path_env("JOB_SEARCH_MACHINE_CREDENTIALS")
        ).mark_account_status(row["canonical_url"], "recovery_requested")
    prior_hashes = cursor.checkpoint.action_receipt_hashes if cursor.checkpoint else ()
    recovery_url = (
        provider_recovery_url(row["canonical_url"])
        if reason == "provider_unavailable"
        else observation.url
    )
    receipt = checkpoints.save(
        RowCheckpointV1(
            1,
            row["application_id"],
            "checkpointed",
            cursor.handle.page_marker,
            cursor.handle.generation,
            observation.content_sha256,
            prior_hashes,
            0,
            recovery_url,
        )
    )
    await session.close_owned(cursor.handle)
    return {
        "status": "checkpointed",
        "reason": reason,
        "row": {
            "application_id": row["application_id"],
            "company": row["company"],
            "role": row["title"],
        },
        "checkpoint_sha256": receipt.checkpoint_sha256,
        "observation_sha256": observation.content_sha256,
    }


async def ineligible(reason: str) -> dict[str, Any]:
    """Terminally reject one visibly unavailable/ineligible row and continue."""
    row, session, _checkpoints, _evidence, cursor, builder = await _context()
    observation = await builder.build(cursor.handle)
    ledger = Ledger(_path_env("JOB_SEARCH_STATE_ROOT") / "ledger.sqlite3")
    try:
        ledger.transition(
            row["application_id"],
            "rejected",
            {
                "reason": reason,
                "observation_sha256": observation.content_sha256,
            },
        )
    finally:
        ledger.close()
    wake_id = _path_env("JOB_SEARCH_BROWSER_OWNER_EVIDENCE").parent.name
    report_receipt = send_hourly_outcomes(
        database=_path_env("JOB_SEARCH_STATE_ROOT") / "telegram-outbox.sqlite3",
        wake_id=wake_id,
        receipts=(
            QueueRowReceiptV1(
                row["application_id"], row["company"], row["title"], "ineligible"
            ),
        ),
        evidence_classes={},
    )
    _mark_wake_completed(row["application_id"])
    await session.close_owned(cursor.handle)
    return {
        "status": "ineligible",
        "reason": reason,
        "application_id": row["application_id"],
        "observation_sha256": observation.content_sha256,
        "report_message_id": report_receipt.get("message_id"),
    }


def _materials_root() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return data_home / "anicca/job-search/materials"


def _claim_snapshot(observation) -> dict[str, Any]:
    controls = []
    for control in observation.controls:
        automation_id = (
            control.stable_id.removeprefix("automation:")
            if control.stable_id.startswith("automation:")
            else ""
        )
        controls.append(
            {
                "tag": control.tag,
                "type": control.control_type,
                "role": control.role,
                "automation_id": automation_id,
                "label": control.label,
                "name": "",
                "text": control.label,
            }
        )
    return {
        "version": 1,
        "url": observation.url,
        "navigation_committed": True,
        "frames": [{"url": observation.url, "controls": controls}],
    }


def _submit_action(observation) -> VisibleActionV1:
    candidates = [
        control
        for control in observation.controls
        if (
            control.stable_id == "automation:pageFooterNextButton"
            or " ".join(control.label.split()).casefold()
            in {"submit", "submit application", "送信", "応募を送信"}
        )
        and not control.disabled
    ]
    if len(candidates) != 1:
        raise RuntimeError("final review requires exactly one visible Submit control")
    control = candidates[0]
    role = control.role or ("link" if control.tag == "a" else "button")
    return VisibleActionV1(
        kind="click",
        target=ActionTargetV1(
            role=role,
            label=control.label,
            exact=True,
            stable_id=control.stable_id,
        ),
    )


async def finalize() -> dict[str, Any]:
    """Fence one final click and classify only its fresh rendered result."""
    row, session, checkpoints, evidence, cursor, builder = await _context()
    before = await builder.build(cursor.handle)
    routed = _routed_resume(row, f"{row['title']}\n{before.visible_text}")
    resume_path = Path(routed["resume_path"])
    resume = await ResumeVerifier(session).verify(
        cursor.handle, before, resume_path, {}
    )
    try:
        review = verify_final_review(
            row_run_id=cursor.handle.row_run_id,
            application_id=row["application_id"],
            company=row["company"],
            role=row["title"],
            expected_url=row["canonical_url"],
            expected_resume_sha256=routed["resume_sha256"],
            observation=before,
            resume=resume,
        )
        final_action = _submit_action(before)
    except RuntimeError as error:
        if str(error) not in {
            "company or role is absent from final review",
            "final review URL does not match the application",
            "final review requires exactly one visible Submit control",
        }:
            raise
        return {
            "status": "action_rejected",
            "reason": "final_review_not_ready",
            "observation": _safe_observation(
                before, cursor.checkpoint, _wake_budget()
            ),
        }
    snapshot_path = _path_env("JOB_SEARCH_BROWSER_SCRATCH") / "final-review-ats.json"
    snapshot_path.write_text(
        json.dumps(_claim_snapshot(before), ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(snapshot_path, 0o600)
    snapshot_sha = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    payload_hash = hashlib.sha256(
        json.dumps(
            {
                "canonical_url": row["canonical_url"],
                "resume_sha256": routed["resume_sha256"],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    ledger = Ledger(_path_env("JOB_SEARCH_STATE_ROOT") / "ledger.sqlite3")
    try:
        with _exclusive_terminal_effect():
            _check_terminal_failure_marker()
            intent = ledger.claim_submission(
                row["application_id"],
                datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d"),
                payload_hash,
                resume_path=resume_path,
                resume_sha256=routed["resume_sha256"],
                ats_snapshot_path=snapshot_path,
                ats_snapshot_sha256=snapshot_sha,
                final_review_receipt_sha256=review.receipt_sha256,
            )
            if intent is None:
                raise RuntimeError("submission intent is already claimed or row is not ready")
            fence = SubmissionFence(ledger, _path_env("JOB_SEARCH_BROWSER_STATE_ROOT"))
            lease = fence.acquire(intent.intent_id, intent.fence, review)
            try:
                action_receipt = await ActionExecutor(session).execute_final(
                    cursor.handle, final_action, fence, lease, before.content_sha256
                )
            except Exception:
                ledger.complete_submission(intent.intent_id, intent.fence, "not_submitted")
                raise
        page = session.page(cursor.handle)
        await page.wait_for_timeout(6_500)
        after = await builder.build(cursor.handle)
        completion = verify_completion_ui(
            company=row["company"],
            role=row["title"],
            review=review,
            observation=after,
            require_receipt=detect_provider(row["canonical_url"]) == "workday",
        )
        record_completion_evidence(ledger, intent.intent_id, intent.fence, completion)
    finally:
        ledger.close()
    chain = evidence.read_chain(row["application_id"])
    step = evidence.append(
        StepEvidenceV1(
            1,
            row["application_id"],
            len(chain),
            chain[-1].evidence_sha256 if chain else None,
            before.content_sha256,
            action_receipt.receipt_sha256,
            after.content_sha256,
        )
    )
    prior = cursor.checkpoint.action_receipt_hashes if cursor.checkpoint else ()
    checkpoint_receipt = checkpoints.save(
        RowCheckpointV1(
            1,
            row["application_id"],
            completion.outcome,
            cursor.handle.page_marker,
            cursor.handle.generation,
            after.content_sha256,
            (*prior, action_receipt.receipt_sha256),
            0,
            after.url,
        )
    )
    await session.close_owned(cursor.handle)
    report_status = (
        "post_submit_verification"
        if completion.evidence_class == "exact_completion_ui_pending_receipt"
        else completion.outcome
    )
    wake_id = _path_env("JOB_SEARCH_BROWSER_OWNER_EVIDENCE").parent.name
    telegram = send_hourly_outcomes(
        database=_path_env("JOB_SEARCH_STATE_ROOT") / "telegram-outbox.sqlite3",
        wake_id=wake_id,
        receipts=(
            QueueRowReceiptV1(
                row["application_id"], row["company"], row["title"], report_status
            ),
        ),
        evidence_classes={row["application_id"]: completion.evidence_class},
    )
    _mark_wake_completed(row["application_id"])
    return {
        "status": report_status,
        "application_id": row["application_id"],
        "evidence_class": completion.evidence_class,
        "evidence_sha256": completion.evidence_sha256,
        "step_evidence_sha256": step.evidence_sha256,
        "checkpoint_sha256": checkpoint_receipt.checkpoint_sha256,
        "report_message_id": telegram["message_id"],
    }


def report(status: str) -> dict[str, Any]:
    row = _row()
    wake_id = _path_env("JOB_SEARCH_BROWSER_OWNER_EVIDENCE").parent.name
    result = send_hourly_outcomes(
        database=_path_env("JOB_SEARCH_STATE_ROOT") / "telegram-outbox.sqlite3",
        wake_id=wake_id,
        receipts=(
            QueueRowReceiptV1(
                row["application_id"], row["company"], row["title"], status
            ),
        ),
        evidence_classes={},
    )
    if result.get("status") == "sent" and result.get("message_id"):
        _mark_wake_completed(row["application_id"])
    return {
        "status": result.get("status"),
        "message_id": result.get("message_id"),
        "application_id": row["application_id"],
    }


def _run_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("observe")
    subparsers.add_parser("finalize")
    navigate_parser = subparsers.add_parser("navigate")
    navigate_parser.add_argument("--url", required=True)
    click_parser = subparsers.add_parser("click")
    click_parser.add_argument("--label", required=True)
    click_parser.add_argument("--role", default="")
    click_parser.add_argument("--stable-id", default="")
    click_parser.add_argument("--ordinal", type=int)
    choose_parser = subparsers.add_parser("choose")
    choose_parser.add_argument("--field-label", required=True)
    choose_parser.add_argument("--field-role", default="")
    choose_parser.add_argument("--field-stable-id", default="")
    choose_parser.add_argument("--option-label", required=True)
    choose_parser.add_argument("--option-role", default="option")
    choose_parser.add_argument("--option-stable-id", default="")
    type_parser = subparsers.add_parser("type")
    type_parser.add_argument("--label", required=True)
    type_parser.add_argument("--role", default="")
    type_parser.add_argument("--stable-id", default="")
    type_parser.add_argument("--candidate-concept", required=True)
    type_text_parser = subparsers.add_parser("type-text")
    type_text_parser.add_argument("--label", required=True)
    type_text_parser.add_argument("--role", default="")
    type_text_parser.add_argument("--stable-id", default="")
    type_text_parser.add_argument("--text", required=True)
    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("--label", required=True)
    upload_parser.add_argument("--role", default="")
    upload_parser.add_argument("--stable-id", default="")
    wait_parser = subparsers.add_parser("wait")
    wait_parser.add_argument("--milliseconds", required=True, type=int)
    act_parser = subparsers.add_parser("act")
    act_parser.add_argument("--action-file", required=True, type=Path)
    auth_parser = subparsers.add_parser("auth")
    auth_parser.add_argument("--mode", required=True, choices=("sign_in", "create_account"))
    auth_parser.add_argument(
        "--field", required=True, choices=("email", "password", "verify_password")
    )
    auth_parser.add_argument("--label", required=True)
    auth_parser.add_argument("--role", default="")
    auth_parser.add_argument("--stable-id", default="")
    checkpoint_parser = subparsers.add_parser("checkpoint")
    checkpoint_parser.add_argument(
        "--reason",
        required=True,
        choices=("provider_unavailable", "visible_challenge", "email_recovery"),
    )
    ineligible_parser = subparsers.add_parser("ineligible")
    ineligible_parser.add_argument(
        "--reason", required=True, choices=("job_not_available", "hard_ineligible")
    )
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument(
        "--status", required=True, choices=("checkpointed", "not_submitted")
    )
    args = parser.parse_args(argv)
    if args.command == "observe":
        operation = observe
    elif args.command == "finalize":
        operation = finalize
    elif args.command == "navigate":
        operation = lambda: navigate(args.url)
    elif args.command == "click":
        operation = lambda: click(
            label=args.label, role=args.role, stable_id=args.stable_id,
            ordinal=args.ordinal,
        )
    elif args.command == "choose":
        operation = lambda: choose(
            field_label=args.field_label,
            field_role=args.field_role,
            field_stable_id=args.field_stable_id,
            option_label=args.option_label,
            option_role=args.option_role,
            option_stable_id=args.option_stable_id,
        )
    elif args.command == "type":
        operation = lambda: type_candidate(
            label=args.label,
            role=args.role,
            stable_id=args.stable_id,
            candidate_concept=args.candidate_concept,
        )
    elif args.command == "type-text":
        operation = lambda: type_text(
            label=args.label,
            role=args.role,
            stable_id=args.stable_id,
            text=args.text,
        )
    elif args.command == "upload":
        operation = lambda: upload_resume(
            label=args.label, role=args.role, stable_id=args.stable_id
        )
    elif args.command == "wait":
        operation = lambda: wait(args.milliseconds)
    elif args.command == "act":
        operation = lambda: act(args.action_file)
    elif args.command == "auth":
        operation = lambda: auth(
            mode=args.mode,
            field=args.field,
            label=args.label,
            role=args.role,
            stable_id=args.stable_id,
        )
    elif args.command == "checkpoint":
        operation = lambda: checkpoint(args.reason)
    elif args.command == "ineligible":
        operation = lambda: ineligible(args.reason)
    else:
        operation = None
    try:
        with _exclusive_command():
            _check_terminal_failure_marker()
            result = report(args.status) if operation is None else asyncio.run(operation())
    except Exception:
        _write_terminal_failure_marker()
        raise
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    active_claimed = False
    try:
        _claim_active_command()
        active_claimed = True
        result = _run_main(argv)
        _clear_active_command()
        active_claimed = False
        return result
    except BaseException:
        if active_claimed:
            _write_terminal_failure_marker()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
