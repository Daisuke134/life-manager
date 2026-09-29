"""Shared bounded Meta Loop platform-manifest wake entrypoint.

The registry owns source completeness and ordering.  Provider modules own their
read-only snapshot collection and manifest validation; this module only routes
those discover callables through the common enrollment and durable run stores.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Mapping


_ENROLLMENT_PATH = Path(__file__).with_name("platform_enrollment.py")
try:
    from platform_enrollment import run_meta_loop_wake
except ModuleNotFoundError:  # pragma: no cover - direct module loading fallback
    _enrollment_spec = importlib.util.spec_from_file_location(
        "platform_manifest_cycle_enrollment", _ENROLLMENT_PATH,
    )
    if _enrollment_spec is None or _enrollment_spec.loader is None:
        raise
    _enrollment_module = importlib.util.module_from_spec(_enrollment_spec)
    sys.modules[_enrollment_spec.name] = _enrollment_module
    _enrollment_spec.loader.exec_module(_enrollment_module)
    run_meta_loop_wake = _enrollment_module.run_meta_loop_wake


PLATFORM_PROVIDERS = ("coconala", "lancers", "crowdworks", "mercor")
SUPPORTED_PLATFORM_PROVIDERS = PLATFORM_PROVIDERS + ("upwork", "freelancer")


class PlatformManifestCycleError(ValueError):
    """The platform source registry is malformed and must not run."""


class MissingPlatformManifestSource(RuntimeError):
    """A declared platform has no read-only source configured for this wake."""


def _missing_source(provider: str):
    def discover() -> list[dict[str, Any]]:
        raise MissingPlatformManifestSource(f"source_missing:{provider}")

    return discover


def run_platform_manifest_wake(
    source_discoverers: Mapping[str, Any],
    candidate_store: Any,
    run_store: Any,
    *,
    providers: tuple[str, ...] | None = None,
    run_id: str,
    observed_at: str,
    max_candidates_per_source: int = 50,
) -> dict[str, Any]:
    """Run an explicit bounded set of known platform sources in one wake.

    The default remains the original four marketplace sources. New providers
    must opt in with ``providers=...`` so adding an adapter cannot silently
    change the source count or status of existing natural wakes. Missing
    providers are represented as typed source failures, and provider mutation
    is never called here.
    Unknown provider keys fail before any discover callable is invoked.
    """

    if not isinstance(source_discoverers, Mapping):
        raise PlatformManifestCycleError("source_registry_invalid")
    if providers is None:
        selected = PLATFORM_PROVIDERS
    elif (
        not isinstance(providers, tuple)
        or not providers
        or len(set(providers)) != len(providers)
        or any(not isinstance(provider, str) or provider not in SUPPORTED_PLATFORM_PROVIDERS
               for provider in providers)
    ):
        raise PlatformManifestCycleError("provider_registry_invalid")
    else:
        selected = providers
    unknown = set(source_discoverers).difference(selected)
    if unknown:
        raise PlatformManifestCycleError("source_provider_invalid")
    sources: dict[str, Any] = {}
    for provider in selected:
        discover = source_discoverers.get(provider)
        if discover is None:
            discover = _missing_source(provider)
        if not callable(discover):
            raise PlatformManifestCycleError("source_discoverer_invalid")
        sources[provider] = discover
    return run_meta_loop_wake(
        sources,
        candidate_store,
        run_store,
        run_id=run_id,
        observed_at=observed_at,
        max_candidates_per_source=max_candidates_per_source,
    )


__all__ = [
    "MissingPlatformManifestSource",
    "PLATFORM_PROVIDERS",
    "SUPPORTED_PLATFORM_PROVIDERS",
    "PlatformManifestCycleError",
    "run_platform_manifest_wake",
]
