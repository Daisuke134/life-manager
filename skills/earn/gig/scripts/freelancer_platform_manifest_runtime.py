#!/usr/bin/env python3
"""Connect one Freelancer read-only source to the shared Meta Loop."""

from __future__ import annotations

from datetime import datetime, timezone
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


_FREELANCER = None
_CYCLE = None
_CANDIDATE_STORE = None
_RUN_STORE = None


def _modules():
    global _FREELANCER, _CYCLE, _CANDIDATE_STORE, _RUN_STORE
    if _FREELANCER is None:
        _FREELANCER = _load(
            HERE.with_name("freelancer_platform_manifest.py"),
            "freelancer_manifest_runtime_source",
        )
    if _CYCLE is None:
        _CYCLE = _load(CORE / "platform_manifest_cycle.py", "freelancer_manifest_runtime_cycle")
    if _CANDIDATE_STORE is None:
        _CANDIDATE_STORE = _load(CORE / "platform_candidate_store.py", "freelancer_manifest_runtime_candidates")
    if _RUN_STORE is None:
        _RUN_STORE = _load(CORE / "meta_loop_run_store.py", "freelancer_manifest_runtime_runs")
    return _FREELANCER, _CYCLE, _CANDIDATE_STORE, _RUN_STORE


def default_manifest_root() -> Path:
    return Path(
        os.environ.get("GIG_META_LOOP_ROOT") or (Path.home() / "gig" / "meta-loop")
    ).expanduser()


def run_freelancer_platform_manifest_wake(
    *, snapshot: Mapping[str, Any], candidate_root: str | Path | None = None,
    run_root: str | Path | None = None, run_id: str,
    observed_at: str | None = None, source_discoverers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    freelancer, cycle, candidate_store_module, run_store_module = _modules()
    root = default_manifest_root()
    candidates = candidate_store_module.CandidateStateStore(
        candidate_root if candidate_root is not None else root / "candidates",
    )
    runs = run_store_module.MetaLoopRunStore(
        run_root if run_root is not None else root / "runs",
    )
    seen_at = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    def discover() -> list[dict[str, Any]]:
        return freelancer.FreelancerPlatformManifestSource(
            lambda: dict(snapshot)
        ).discover()

    sources = dict(source_discoverers or {})
    sources["freelancer"] = discover
    return cycle.run_platform_manifest_wake(
        sources, candidates, runs, providers=("freelancer",),
        run_id=run_id, observed_at=seen_at,
    )


__all__ = ["default_manifest_root", "run_freelancer_platform_manifest_wake"]
