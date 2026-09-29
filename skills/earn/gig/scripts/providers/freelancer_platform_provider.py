#!/usr/bin/env python3
"""Connect authenticated Freelancer readback to the shared Meta Loop.

This module owns no login, bid, message, delivery, or launchd behavior.  It
only consumes the existing authorization-bound read-only transport, projects
secret-free evidence hashes, and records one held candidate in the shared
platform cycle.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Iterable


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from freelancer_platform_manifest import build_live_snapshot  # noqa: E402
from freelancer_platform_manifest_runtime import (  # noqa: E402
    run_freelancer_platform_manifest_wake,
)


def record_freelancer_platform_manifest_wake(
    *,
    transport: Any,
    receipts: Iterable[Any],
    account_id: str,
    project_ids: tuple[str, ...],
    fetch: Any,
    run_id: str,
    candidate_root: str | Path | None = None,
    run_root: str | Path | None = None,
    currency_minor_units: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Record one authenticated, read-only Freelancer platform observation."""
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValueError("freelancer_account_id_invalid")
    if getattr(transport, "account", None) != account_id:
        raise ValueError("freelancer_account_mismatch")
    reader = getattr(transport, "read_inventory_observation", None)
    if not callable(reader):
        raise ValueError("freelancer_manifest_reader_unavailable")
    observation = reader(
        receipts,
        account_id=account_id,
        project_ids=project_ids,
        fetch=fetch,
        currency_minor_units=currency_minor_units,
    )
    inventory = observation.inventory
    evidence = dict(observation.evidence_sha256)
    evidence["profile"] = observation.profile_sha256
    state = {
        "version": 1,
        "provider": "freelancer",
        "observed_at": inventory.observed_at,
        "source_complete": inventory.source_complete,
        "evidence_sha256": evidence,
    }
    adapter_source = SCRIPTS / "freelancer_platform_manifest.py"
    snapshot = build_live_snapshot(
        state,
        account_id=account_id,
        adapter_source_sha256=hashlib.sha256(adapter_source.read_bytes()).hexdigest(),
    )
    return run_freelancer_platform_manifest_wake(
        snapshot=snapshot,
        candidate_root=candidate_root,
        run_root=run_root,
        run_id=run_id,
        observed_at=inventory.observed_at,
    )


__all__ = ["record_freelancer_platform_manifest_wake"]
