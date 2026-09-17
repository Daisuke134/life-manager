from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HumanGateError(ValueError):
    pass


_KNOWN_IDENTITIES = (
    ("bilingual competency", "bilingual_competency"),
    ("project thor assessment", "project_thor_assessment"),
    ("finance interview", "finance_interview"),
    ("pharmacology lab review", "pharmacology_lab_review"),
    ("professional work survey", "professional_work_survey"),
    ("household video contributor intake form", "household_video_intake"),
)

_KNOWN_LISTING_IDENTITIES = (
    ("list_aaabn5veycy9jpdvdtdm1y-0", "project_thor_assessment"),
    ("list_aaabnmyh74ctdwnp6bjof5vx", "pharmacology_lab_review"),
    ("list_aaabn3frsqjqpfplfuheeyix", "professional_work_survey"),
    ("list_aaabnvqibotac6n9df5jsbmj", "household_video_intake"),
)


def _identity(reason: str, evidence_ref: str) -> str:
    """Return a stable logical identity despite model wording drift."""
    normalized = " ".join(reason.casefold().split())
    for marker, identity in _KNOWN_IDENTITIES:
        if marker in normalized:
            return identity
    combined = f"{normalized}\n{evidence_ref.casefold()}"
    for marker, identity in _KNOWN_LISTING_IDENTITIES:
        if marker in combined:
            return identity
    if "generalist (macbook user)" in normalized and (
        "assessment" in normalized or "interview" in normalized
    ):
        return "project_thor_assessment"
    if "mercor authentication" in normalized:
        return "mercor_authentication"
    if "resume artifact" in normalized and (
        "not present" in normalized or "missing" in normalized
    ):
        return "resume_artifact"
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    return f"{normalized}\n{evidence_ref.strip()}"


def _exact_identity(account_id: str, listing_id: str, step_id: str) -> str:
    """Bind a resumable gate to one account, listing, and provider step."""
    values = tuple(value.strip() for value in (account_id, listing_id, step_id))
    if not all(values):
        raise HumanGateError("account_id, listing_id, and step_id are required")
    digest = hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()
    return f"mercor-exact:{digest}"


def next_action(
    *, gate_status: str, official_step: str, same_account: bool,
    same_application: bool,
) -> str:
    """Choose the safe continuation for an observed provider step."""
    if gate_status != "pending":
        return "continue"
    if (
        official_step.strip().casefold() == "completed"
        and same_account is True
        and same_application is True
    ):
        return "resume_application"
    return "recheck_later"


class HumanGateStore:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        if self.path.exists():
            if self.path.is_symlink() or not self.path.is_file():
                raise HumanGateError("human gate store path must be a regular file")
            os.chmod(self.path, 0o600)

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise HumanGateError("human gate row must be an object")
            rows.append(value)
        return rows

    def record(
        self, *, run_id: str, reason: str, evidence_ref: str,
        account_id: str | None = None, listing_id: str | None = None,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        if not all(isinstance(value, str) and value.strip() for value in (run_id, reason, evidence_ref)):
            raise HumanGateError("run_id, reason, and evidence_ref are required")
        exact_values = (account_id, listing_id, step_id)
        if any(value is not None for value in exact_values) and not all(
            isinstance(value, str) and value.strip() for value in exact_values
        ):
            raise HumanGateError("account_id, listing_id, and step_id are required together")
        exact = all(isinstance(value, str) and value.strip() for value in exact_values)
        identity = (
            _exact_identity(account_id, listing_id, step_id)
            if exact else _identity(reason.strip(), evidence_ref.strip())
        )
        gate_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
        rows = self._rows()
        latest = self._latest_by_identity(rows).get(identity)
        if latest is not None and latest.get("status") == "pending":
            return latest
        row = {
            "gate_id": gate_id,
            "identity_key": identity,
            "event": "record",
            "run_id": run_id.strip(),
            "reason": reason.strip(),
            "evidence_ref": evidence_ref.strip(),
            "status": "pending",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        if exact:
            row.update({
                "account_id": account_id.strip(),
                "listing_id": listing_id.strip(),
                "step_id": step_id.strip(),
            })
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(self.path, 0o600)
        return row

    @staticmethod
    def _row_identity(row: dict[str, Any]) -> str:
        exact_values = tuple(row.get(key) for key in ("account_id", "listing_id", "step_id"))
        if all(isinstance(value, str) and value.strip() for value in exact_values):
            return _exact_identity(*exact_values)
        derived = _identity(str(row.get("reason", "")), str(row.get("evidence_ref", "")))
        if derived == "bilingual_competency":
            return derived
        value = row.get("identity_key")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return derived

    @classmethod
    def _latest_by_identity(cls, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            latest[cls._row_identity(row)] = row
        return latest

    def resolve(
        self, *, identity_key: str = "", run_id: str, evidence_ref: str,
        account_id: str | None = None, listing_id: str | None = None,
        step_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not all(isinstance(value, str) and value.strip() for value in (run_id, evidence_ref)):
            raise HumanGateError("identity_key, run_id, and evidence_ref are required")
        exact_values = (account_id, listing_id, step_id)
        if any(value is not None for value in exact_values) and not all(
            isinstance(value, str) and value.strip() for value in exact_values
        ):
            raise HumanGateError("account_id, listing_id, and step_id are required together")
        if all(isinstance(value, str) and value.strip() for value in exact_values):
            identity_key = _exact_identity(account_id, listing_id, step_id)
        elif not isinstance(identity_key, str) or not identity_key.strip():
            raise HumanGateError("identity_key or exact gate key is required")
        else:
            identity_key = identity_key.strip()
        latest = self._latest_by_identity(self._rows()).get(identity_key)
        if latest is None or latest.get("status") != "pending":
            return None
        row = {
            "gate_id": latest["gate_id"],
            "identity_key": identity_key,
            "event": "resolve",
            "run_id": run_id.strip(),
            "reason": str(latest.get("reason", "")),
            "evidence_ref": evidence_ref.strip(),
            "status": "resolved",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(self.path, 0o600)
        return row

    def pending(self) -> list[dict[str, Any]]:
        return [
            row
            for row in self._latest_by_identity(self._rows()).values()
            if row.get("status") == "pending"
        ]
