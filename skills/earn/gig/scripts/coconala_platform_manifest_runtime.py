#!/usr/bin/env python3
"""Connect the live Coconala natural wake to the shared Meta Loop cycle.

This boundary reads the existing secret-free onboarding receipt only.  It never
opens a provider page, submits a request, replies, delivers work, or changes a
provider account.  Other platform callers may inject their own read-only source
discoverers; absent sources remain explicit ``partial`` errors.
"""

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


_COCONALA = None
_CYCLE = None
_CANDIDATE_STORE = None
_RUN_STORE = None
_LIFECYCLE_STORE = None


def _modules():
    global _COCONALA, _CYCLE, _CANDIDATE_STORE, _RUN_STORE, _LIFECYCLE_STORE
    if _COCONALA is None:
        _COCONALA = _load(HERE.with_name("coconala_platform_manifest.py"), "coconala_manifest_runtime_source")
    if _CYCLE is None:
        _CYCLE = _load(CORE / "platform_manifest_cycle.py", "platform_manifest_runtime_cycle")
    if _CANDIDATE_STORE is None:
        _CANDIDATE_STORE = _load(CORE / "platform_candidate_store.py", "platform_manifest_runtime_candidates")
    if _RUN_STORE is None:
        _RUN_STORE = _load(CORE / "meta_loop_run_store.py", "platform_manifest_runtime_runs")
    if _LIFECYCLE_STORE is None:
        _LIFECYCLE_STORE = _load(
            CORE / "meta_loop_lifecycle.py", "platform_manifest_runtime_lifecycle",
        )
    return _COCONALA, _CYCLE, _CANDIDATE_STORE, _RUN_STORE, _LIFECYCLE_STORE


def default_onboarding_path() -> Path:
    return Path(
        os.environ.get("GIG_COCONALA_ONBOARDING_PATH")
        or (Path.home() / ".config" / "anicca" / "gig" / "coconala-onboarding.json")
    ).expanduser()


def default_manifest_root() -> Path:
    return Path(
        os.environ.get("GIG_META_LOOP_ROOT")
        or (Path.home() / "gig" / "meta-loop")
    ).expanduser()


def _adapter_source_sha256() -> str:
    return hashlib.sha256(HERE.with_name("coconala_platform_manifest.py").read_bytes()).hexdigest()


def run_coconala_platform_manifest_wake(
    *,
    onboarding_path: str | Path | None = None,
    live_snapshot: Mapping[str, Any] | None = None,
    authenticated_state: Mapping[str, Any] | None = None,
    candidate_root: str | Path | None = None,
    run_root: str | Path | None = None,
    run_id: str,
    observed_at: str | None = None,
    source_discoverers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one Coconala natural-wake source through the four-platform cycle."""

    coconala, cycle, candidate_store_module, run_store_module, _ = _modules()
    onboarding = Path(onboarding_path).expanduser() if onboarding_path is not None else default_onboarding_path()
    root = default_manifest_root()
    candidates = candidate_store_module.CandidateStateStore(
        candidate_root if candidate_root is not None else root / "candidates",
    )
    runs = run_store_module.MetaLoopRunStore(
        run_root if run_root is not None else root / "runs",
    )
    seen_at = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    if live_snapshot is not None:
        if authenticated_state is None:
            raise ValueError("coconala_live_authenticated_state_required")

        def load_snapshot() -> dict[str, Any]:
            return coconala.load_live_collector_observation(
                live_snapshot,
                authenticated_state=authenticated_state,
                observed_at=seen_at,
                adapter_source_sha256=_adapter_source_sha256(),
            )
    else:

        def load_snapshot() -> dict[str, Any]:
            return coconala.load_onboarding_observation(
                onboarding,
                observed_at=seen_at,
                adapter_source_sha256=_adapter_source_sha256(),
            )

    sources = dict(source_discoverers or {})
    sources["coconala"] = coconala.CoconalaPlatformManifestSource(load_snapshot).discover
    return cycle.run_platform_manifest_wake(
        sources,
        candidates,
        runs,
        run_id=run_id,
        observed_at=seen_at,
    )


def run_coconala_candidate_lifecycle(
    *,
    candidate_root: str | Path,
    lifecycle_root: str | Path,
    registry: Any,
    account_context: Mapping[str, Any],
    candidate_id: str,
    run_id: str,
    observed_at: str,
) -> dict[str, Any]:
    """Promote one stored Coconala candidate through an injected registry.

    The registry and account context are explicit inputs so a natural manifest
    wake cannot infer credentials or silently perform a provider effect.  A
    missing/unverified Coconala factory remains a typed registry hold.
    """

    _, cycle, candidate_store_module, _, lifecycle_store_module = _modules()
    candidates = candidate_store_module.CandidateStateStore(candidate_root)
    lifecycle = lifecycle_store_module.MetaLoopLifecycleStore(lifecycle_root)
    return cycle.run_registered_platform_candidate_lifecycle(
        candidates,
        lifecycle,
        registry,
        provider="coconala",
        candidate_id=candidate_id,
        account_context=account_context,
        run_id=run_id,
        observed_at=observed_at,
    )


__all__ = [
    "default_manifest_root",
    "default_onboarding_path",
    "run_coconala_candidate_lifecycle",
    "run_coconala_platform_manifest_wake",
]
