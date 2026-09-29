from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load(SCRIPTS / "platform_manifest_source.py", "platform_manifest_source_test")
enrollment = _load(SCRIPTS / "platform_enrollment.py", "platform_manifest_enrollment_test")
candidate_store_module = _load(
    SCRIPTS / "platform_candidate_store.py", "platform_manifest_candidate_store_test"
)


def _candidate(provider: str = "example-market") -> dict[str, object]:
    return {
        "version": 1,
        "provider": provider,
        "policy": {
            "status": "unknown",
            "source_url": "https://example.test/policy",
            "observed_at": "2026-09-30T01:00:00Z",
        },
        "adapter": {
            "contract": "marketplace-core-v1",
            "actions": [
                "discover", "inspect", "propose", "message", "accept_offer",
                "deliver", "read_payments", "read_payouts",
            ],
            "source_sha256": "a" * 64,
        },
        "funded_work": {
            "status": "unknown",
            "receipt_ref": f"provider-receipt://{provider}/unverified",
            "observed_at": "2026-09-30T01:00:00Z",
        },
        "canary": {
            "status": "unknown",
            "official_receipt_ref": None,
            "replay_zero": False,
            "observed_at": "2026-09-30T01:00:00Z",
        },
        "unit_economics": {
            "status": "unknown",
            "net_amount_minor": 0,
            "currency": "USD",
            "evidence_refs": [f"platform://{provider}/unverified"],
        },
    }


def _manifest(provider: str = "example-market") -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_kind": "platform",
        "provider": provider,
        "candidate_id": f"platform:{provider}",
        "candidate": _candidate(provider),
        "observed_at": "2026-09-30T01:01:00Z",
        "source_url": "https://example.test/",
        "snapshot_sha256": "b" * 64,
        "evidence_refs": [f"platform://{provider}/manifest-1"],
    }


def test_platform_manifest_source_emits_one_platform_candidate_and_caches_snapshot():
    calls = 0

    def load():
        nonlocal calls
        calls += 1
        return _manifest()

    source = module.PlatformManifestSource(load)
    [item] = source.discover()
    [same_item] = source.discover()

    assert calls == 1
    assert item == same_item
    assert item["source_kind"] == "platform"
    assert item["candidate_id"] == "platform:example-market"
    assert "opportunities" not in item


def test_platform_manifest_source_rejects_opportunity_snapshot():
    source = module.PlatformManifestSource(
        lambda: {**_manifest(), "opportunities": [{"id": "listing-1"}]}
    )

    with pytest.raises(module.PlatformManifestError, match="opportunity_snapshot_rejected"):
        source.discover()


def test_platform_manifest_source_rejects_candidate_provider_mismatch():
    source = module.PlatformManifestSource(
        lambda: {**_manifest("lancers"), "candidate": _candidate("coconala")}
    )

    with pytest.raises(module.PlatformManifestError, match="provider_mismatch"):
        source.discover()


def test_platform_manifest_source_is_accepted_by_platform_candidate_cycle(tmp_path):
    source = module.PlatformManifestSource(_manifest)
    store = candidate_store_module.CandidateStateStore(tmp_path / "candidates")

    summary = enrollment.run_discovery_cycle(
        {"example-platform": source.discover},
        store,
    )

    assert summary["status"] == "ok"
    assert summary["inspected"] == 1
    assert summary["held"] == 1
    assert store.latest("example-market", "platform:example-market")["decision"] == "hold"
