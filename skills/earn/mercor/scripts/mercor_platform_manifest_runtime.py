#!/usr/bin/env python3
"""Connect the Mercor reply natural wake to the shared Meta Loop cycle.

The reply snapshot contains opportunity rows, contract rows, and private Gmail
content.  This boundary projects only account/source-health facts into the
platform manifest; opportunities and applications remain in their own loops.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve()
CORE = HERE.parents[3] / "_shared" / "marketplace-core" / "scripts"
_REPLY_SOURCES = ("applications", "notifications", "assessments", "contracts", "interviews")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name}_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MERCOR = None
_CYCLE = None
_CANDIDATE_STORE = None
_RUN_STORE = None
_LIFECYCLE_STORE = None


def _modules():
    global _MERCOR, _CYCLE, _CANDIDATE_STORE, _RUN_STORE, _LIFECYCLE_STORE
    if _MERCOR is None:
        _MERCOR = _load(HERE.with_name("mercor_platform_manifest.py"), "mercor_manifest_runtime_source")
    if _CYCLE is None:
        _CYCLE = _load(CORE / "platform_manifest_cycle.py", "mercor_manifest_runtime_cycle")
    if _CANDIDATE_STORE is None:
        _CANDIDATE_STORE = _load(
            CORE / "platform_candidate_store.py", "mercor_manifest_runtime_candidates",
        )
    if _RUN_STORE is None:
        _RUN_STORE = _load(CORE / "meta_loop_run_store.py", "mercor_manifest_runtime_runs")
    if _LIFECYCLE_STORE is None:
        _LIFECYCLE_STORE = _load(
            CORE / "meta_loop_lifecycle.py", "mercor_manifest_runtime_lifecycle",
        )
    return _MERCOR, _CYCLE, _CANDIDATE_STORE, _RUN_STORE, _LIFECYCLE_STORE


def default_manifest_root() -> Path:
    return Path(
        os.environ.get("GIG_META_LOOP_ROOT")
        or (Path.home() / "gig" / "meta-loop")
    ).expanduser()


def _adapter_source_sha256() -> str:
    return hashlib.sha256(HERE.with_name("mercor_platform_manifest.py").read_bytes()).hexdigest()


def _snapshot_digest(reply_snapshot: Mapping[str, Any], *, auth_status: str, gmail_status: str) -> str:
    """Hash presence/status metadata only; never hash private message bodies into evidence."""
    material = {
        "auth_status": auth_status,
        "gmail_status": gmail_status,
        "sources": {name: name in reply_snapshot for name in _REPLY_SOURCES},
        "contracts_is_list": isinstance(reply_snapshot.get("contracts"), list),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_live_snapshot(
    *,
    reply_snapshot: Mapping[str, Any],
    account_id: str,
    auth_readback: Mapping[str, Any] | None,
    observed_at: str,
) -> dict[str, Any]:
    """Project one authenticated reply readback into source-health facts only."""
    if not isinstance(reply_snapshot, Mapping):
        raise ValueError("mercor_reply_snapshot_invalid")
    if not isinstance(account_id, str) or not account_id.strip() or len(account_id.strip()) > 256:
        raise ValueError("mercor_account_id_invalid")
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ValueError("mercor_observed_at_invalid")
    try:
        parsed = datetime.fromisoformat(observed_at.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("mercor_observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("mercor_observed_at_invalid")

    source_health = reply_snapshot.get("source_health")
    gmail_health = source_health.get("gmail") if isinstance(source_health, Mapping) else None
    gmail_status = gmail_health.get("status") if isinstance(gmail_health, Mapping) else None
    if gmail_status not in {"fresh", "stale"}:
        raise ValueError("mercor_gmail_status_invalid")

    auth_status = auth_readback.get("status") if isinstance(auth_readback, Mapping) else ""
    authenticated = auth_status == "authenticated"
    contract_readback = isinstance(reply_snapshot.get("contracts"), list)
    source_complete = bool(
        authenticated
        and gmail_status == "fresh"
        and contract_readback
        and all(name in reply_snapshot for name in _REPLY_SOURCES)
    )
    digest = _snapshot_digest(reply_snapshot, auth_status=auth_status, gmail_status=gmail_status)
    return {
        "version": 1,
        "platform": "mercor",
        "observed_at": observed_at.strip(),
        "source_url": "https://work.mercor.com/home",
        "adapter_source_sha256": _adapter_source_sha256(),
        "account_id": account_id.strip(),
        "source_complete": source_complete,
        "gmail_status": gmail_status,
        "contract_readback": contract_readback,
        "evidence_refs": [
            f"mercor://auth/status/{auth_status or 'unavailable'}",
            f"mercor://gmail/{gmail_status}",
            f"mercor://contract-readback/{str(contract_readback).lower()}",
            f"mercor://source-complete/{str(source_complete).lower()}",
            f"mercor://reply-source/sha256/{digest}",
        ],
    }


def run_mercor_platform_manifest_wake(
    *,
    snapshot: Mapping[str, Any],
    candidate_root: str | Path | None = None,
    run_root: str | Path | None = None,
    run_id: str,
    observed_at: str | None = None,
    source_discoverers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one Mercor source-health observation through the four-provider cycle."""
    mercor, cycle, candidate_store_module, run_store_module, _ = _modules()
    root = default_manifest_root()
    candidates = candidate_store_module.CandidateStateStore(
        candidate_root if candidate_root is not None else root / "candidates",
    )
    runs = run_store_module.MetaLoopRunStore(
        run_root if run_root is not None else root / "runs",
    )
    seen_at = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    def discover() -> list[dict[str, Any]]:
        source = mercor.MercorPlatformManifestSource(lambda: dict(snapshot))
        return source.discover()

    sources = dict(source_discoverers or {})
    sources["mercor"] = discover
    return cycle.run_platform_manifest_wake(
        sources,
        candidates,
        runs,
        run_id=run_id,
        observed_at=seen_at,
    )


def run_mercor_candidate_lifecycle(
    *,
    candidate_root: str | Path,
    lifecycle_root: str | Path,
    registry: Any,
    account_context: Mapping[str, Any],
    candidate_id: str,
    run_id: str,
    observed_at: str,
) -> dict[str, Any]:
    """Promote one stored Mercor candidate through an injected registry."""

    _, cycle, candidate_store_module, _, lifecycle_store_module = _modules()
    candidates = candidate_store_module.CandidateStateStore(candidate_root)
    lifecycle = lifecycle_store_module.MetaLoopLifecycleStore(lifecycle_root)
    return cycle.run_registered_platform_candidate_lifecycle(
        candidates,
        lifecycle,
        registry,
        provider="mercor",
        candidate_id=candidate_id,
        account_context=account_context,
        run_id=run_id,
        observed_at=observed_at,
    )


__all__ = [
    "build_live_snapshot",
    "default_manifest_root",
    "run_mercor_candidate_lifecycle",
    "run_mercor_platform_manifest_wake",
]
