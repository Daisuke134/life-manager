from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from ..ats import detect_provider
from ..ledger import WORKDAY_FIT_POLICY_VERSION
from ..state import canonical_url
from .contracts import QueueRowReceiptV1
from .workday_account import MachineWorkdayCredentialStore


RowProcessor = Callable[[dict[str, Any]], Awaitable[str]]
_STATUSES = frozenset(
    {
        "checkpointed",
        "ineligible",
        "post_submit_verification",
        "not_submitted",
        "submit_unknown",
        "submitted",
    }
)


def _application_limit() -> int | None:
    raw = os.environ.get("JOB_SEARCH_APPLICATION_LIMIT")
    if raw is None:
        return None
    if not raw or raw.strip() != raw or any(char not in "0123456789" for char in raw):
        return 0
    return int(raw)


class RowQueueSupervisor:
    """Run every unique queued row; one row failure never ends the wake."""

    @staticmethod
    def collect(
        ledger: Any,
        active_provider: str | None = None,
        *,
        cursor_after: tuple[str, str] | None = None,
        in_progress_application_id: str | None = None,
        resume_application_ids: Iterable[str] = (),
    ) -> tuple[dict[str, Any], ...]:
        provider = active_provider or os.environ.get(
            "JOB_SEARCH_ACTIVE_APPLICATION_PROVIDER"
        )
        ordered: Iterable[dict[str, Any]] = (
            *ledger.pending_materials_ready_applications(),
            *ledger.retryable_applications(),
        )
        credential_path = os.environ.get("JOB_SEARCH_MACHINE_CREDENTIALS")
        credentials = (
            MachineWorkdayCredentialStore(Path(credential_path))
            if credential_path
            else None
        )
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for row in ordered:
            identity = canonical_url(str(row["canonical_url"]))
            if provider and detect_provider(identity) != provider:
                continue
            if (
                credentials is not None
                and detect_provider(identity) == "workday"
                and credentials.account_status(identity) == "recovery_requested"
            ):
                continue
            if (
                detect_provider(identity) == "workday"
                and not ledger.workday_fit_qualified(
                    str(row["application_id"]), WORKDAY_FIT_POLICY_VERSION
                )
            ):
                continue
            if identity in seen:
                continue
            seen.add(identity)
            rows.append(row)
        if cursor_after is not None and rows:
            missing_keys = [
                row
                for row in rows
                if not isinstance(row.get("_queue_created_at"), str)
            ]
            if missing_keys:
                application_ids = [str(row["application_id"]) for row in missing_keys]
                placeholders = ",".join("?" for _ in application_ids)
                records = ledger.connection.execute(
                    f"SELECT id, created_at FROM applications WHERE id IN ({placeholders})",
                    application_ids,
                ).fetchall()
                created_at_by_id = {str(record[0]): str(record[1]) for record in records}
                for row in missing_keys:
                    created_at = created_at_by_id.get(str(row["application_id"]))
                    if not created_at:
                        raise RuntimeError("queued application is missing its durable order key")
                    row["_queue_created_at"] = created_at
            rows.sort(
                key=lambda row: (
                    detect_provider(str(row["canonical_url"])) != "workday",
                    str(row["_queue_created_at"]),
                    str(row["application_id"]),
                )
            )
            start = next(
                (
                    index
                    for index, row in enumerate(rows)
                    if (
                        str(row["_queue_created_at"]),
                        str(row["application_id"]),
                    )
                    > cursor_after
                ),
                0,
            )
            rows = rows[start:] + rows[:start]
        else:
            rows.sort(
                key=lambda row: detect_provider(str(row["canonical_url"])) != "workday"
            )

        priority_ids = tuple(
            dict.fromkeys(
                value
                for value in (in_progress_application_id, *resume_application_ids)
                if isinstance(value, str) and value
            )
        )
        if priority_ids:
            by_id = {str(row["application_id"]): row for row in rows}
            prioritized = [by_id[value] for value in priority_ids if value in by_id]
            prioritized_ids = {str(row["application_id"]) for row in prioritized}
            rows = prioritized + [
                row for row in rows if str(row["application_id"]) not in prioritized_ids
            ]
        preferred = os.environ.get("JOB_SEARCH_PREFERRED_APPLICATION_ID", "").strip()
        if preferred and not priority_ids:
            preferred_row = next(
                (row for row in rows if str(row["application_id"]) == preferred),
                None,
            )
            preferred_is_ahead = (
                preferred_row is not None
                and (
                    cursor_after is None
                    or (
                        str(preferred_row.get("_queue_created_at", "")),
                        str(preferred_row["application_id"]),
                    )
                    > cursor_after
                )
            )
            if preferred_is_ahead:
                rows.remove(preferred_row)
                rows.insert(0, preferred_row)
        limit = _application_limit()
        if limit == 0:
            return ()
        return tuple(rows)

    @staticmethod
    def admit_next_discovered_workday(ledger: Any) -> str | None:
        """Promote one legacy discovered Workday row into the model-owned queue."""
        candidates = ledger.connection.execute(
            """
            SELECT id, canonical_url
            FROM applications
            WHERE current_state = 'discovered'
              AND NOT EXISTS (
                SELECT 1 FROM submit_intents
                WHERE submit_intents.application_id = applications.id
              )
            ORDER BY created_at, rowid
            """
        ).fetchall()
        for candidate in candidates:
            application_id = str(candidate["id"])
            identity = canonical_url(str(candidate["canonical_url"]))
            if detect_provider(identity) != "workday":
                continue
            ledger.transition(
                application_id,
                "qualified",
                {"reason": "workday_model_lane_admission"},
            )
            ledger.transition(
                application_id,
                "materials_ready",
                {"reason": "workday_model_lane_admission"},
            )
            return application_id
        return None

    async def run(
        self, rows: Iterable[dict[str, Any]], processor: RowProcessor
    ) -> tuple[QueueRowReceiptV1, ...]:
        receipts: list[QueueRowReceiptV1] = []
        for row in rows:
            try:
                status = await processor(row)
                if status not in _STATUSES:
                    raise ValueError("row processor returned an invalid status")
                error_type = None
            except Exception as error:  # row isolation is the purpose of this boundary
                status = "checkpointed"
                error_type = type(error).__name__
            receipts.append(
                QueueRowReceiptV1(
                    application_id=str(row["application_id"]),
                    company=str(row["company"]),
                    role=str(row["title"]),
                    status=status,
                    error_type=error_type,
                )
            )
        return tuple(receipts)
