#!/usr/bin/env python3
"""Connect the Lancers natural wake to the shared read-only Meta Loop cycle."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve()
CORE = HERE.parents[3] / "_shared" / "marketplace-core" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name}_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_LANCERS = None
_CYCLE = None
_CANDIDATE_STORE = None
_RUN_STORE = None
_LIFECYCLE_STORE = None


def _modules():
    global _LANCERS, _CYCLE, _CANDIDATE_STORE, _RUN_STORE, _LIFECYCLE_STORE
    if _LANCERS is None:
        _LANCERS = _load(HERE.with_name("lancers_platform_manifest.py"), "lancers_manifest_runtime_source")
    if _CYCLE is None:
        _CYCLE = _load(CORE / "platform_manifest_cycle.py", "lancers_manifest_runtime_cycle")
    if _CANDIDATE_STORE is None:
        _CANDIDATE_STORE = _load(CORE / "platform_candidate_store.py", "lancers_manifest_runtime_candidates")
    if _RUN_STORE is None:
        _RUN_STORE = _load(CORE / "meta_loop_run_store.py", "lancers_manifest_runtime_runs")
    if _LIFECYCLE_STORE is None:
        _LIFECYCLE_STORE = _load(
            CORE / "meta_loop_lifecycle.py", "lancers_manifest_runtime_lifecycle",
        )
    return _LANCERS, _CYCLE, _CANDIDATE_STORE, _RUN_STORE, _LIFECYCLE_STORE


def default_contracts_path() -> Path:
    return Path(
        os.environ.get("GIG_LANCERS_CONTRACTS_PATH")
        or (Path.home() / ".local" / "state" / "anicca" / "lancers" / "contracts.json")
    ).expanduser()


def default_manifest_root() -> Path:
    return Path(
        os.environ.get("GIG_META_LOOP_ROOT")
        or (Path.home() / "gig" / "meta-loop")
    ).expanduser()


def _adapter_source_sha256() -> str:
    return hashlib.sha256(HERE.with_name("lancers_platform_manifest.py").read_bytes()).hexdigest()


def run_lancers_platform_manifest_wake(
    *,
    contracts_path: str | Path | None = None,
    candidate_root: str | Path | None = None,
    run_root: str | Path | None = None,
    run_id: str,
    observed_at: str | None = None,
    source_discoverers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one Lancers work-sync source through the four-platform cycle."""

    lancers, cycle, candidate_store_module, run_store_module, _ = _modules()
    contracts = Path(contracts_path).expanduser() if contracts_path is not None else default_contracts_path()
    root = default_manifest_root()
    candidates = candidate_store_module.CandidateStateStore(
        candidate_root if candidate_root is not None else root / "candidates",
    )
    runs = run_store_module.MetaLoopRunStore(
        run_root if run_root is not None else root / "runs",
    )
    seen_at = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    def load_snapshot() -> dict[str, Any]:
        return lancers.load_contracts_observation(
            contracts,
            observed_at=seen_at,
            adapter_source_sha256=_adapter_source_sha256(),
        )

    sources = dict(source_discoverers or {})
    sources["lancers"] = lancers.LancersPlatformManifestSource(load_snapshot).discover
    return cycle.run_platform_manifest_wake(
        sources,
        candidates,
        runs,
        run_id=run_id,
        observed_at=seen_at,
    )


def run_lancers_candidate_lifecycle(
    *,
    candidate_root: str | Path,
    lifecycle_root: str | Path,
    registry: Any,
    account_context: Mapping[str, Any],
    authorization: Any,
    candidate_id: str,
    run_id: str,
    observed_at: str,
) -> dict[str, Any]:
    """Promote one stored Lancers candidate through an injected registry."""

    _, cycle, candidate_store_module, _, lifecycle_store_module = _modules()
    candidates = candidate_store_module.CandidateStateStore(candidate_root)
    lifecycle = lifecycle_store_module.MetaLoopLifecycleStore(lifecycle_root)
    return cycle.run_registered_platform_candidate_lifecycle(
        candidates,
        lifecycle,
        registry,
        provider="lancers",
        candidate_id=candidate_id,
        account_context=account_context,
        authorization=authorization,
        run_id=run_id,
        observed_at=observed_at,
    )


__all__ = [
    "default_contracts_path",
    "default_manifest_root",
    "run_lancers_candidate_lifecycle",
    "run_lancers_platform_manifest_wake",
]
