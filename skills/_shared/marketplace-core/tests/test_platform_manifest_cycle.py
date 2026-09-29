from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cycle = _load(SCRIPTS / "platform_manifest_cycle.py", "platform_manifest_cycle_test")
enrollment = _load(SCRIPTS / "platform_enrollment.py", "platform_cycle_enrollment_test")
candidate_store_module = _load(
    SCRIPTS / "platform_candidate_store.py", "platform_cycle_candidate_store_test"
)
run_store_module = _load(
    SCRIPTS / "meta_loop_run_store.py", "platform_cycle_run_store_test"
)


PROVIDERS = ("coconala", "lancers", "crowdworks", "mercor")


def _item(provider: str) -> dict[str, object]:
    return {
        "source_kind": "platform",
        "candidate": {
            "version": 1,
            "provider": provider,
            "policy": {
                "status": "unknown",
                "source_url": "https://example.test/policy",
                "observed_at": "2026-09-30T06:00:00Z",
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
                "observed_at": "2026-09-30T06:00:00Z",
            },
            "canary": {
                "status": "unknown",
                "official_receipt_ref": None,
                "replay_zero": False,
                "observed_at": "2026-09-30T06:00:00Z",
            },
            "unit_economics": {
                "status": "unknown",
                "net_amount_minor": 0,
                "currency": "USD",
                "evidence_refs": [f"platform://{provider}/observed"],
            },
        },
        "candidate_id": f"platform:{provider}",
        "observed_at": "2026-09-30T06:00:00Z",
        "source_url": "https://example.test/platform",
        "snapshot_sha256": "b" * 64,
        "evidence_refs": [f"platform://{provider}/observed"],
    }


def test_platform_manifest_cycle_runs_all_four_sources_once_and_persists_summary(tmp_path):
    calls = {provider: 0 for provider in PROVIDERS}

    def discover(provider: str):
        def _discover():
            calls[provider] += 1
            return [_item(provider)]
        return _discover

    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")
    result = cycle.run_platform_manifest_wake(
        {provider: discover(provider) for provider in PROVIDERS},
        candidates,
        runs,
        run_id="all-platforms-1",
        observed_at="2026-09-30T06:01:00Z",
    )

    assert result["status"] == "ok"
    assert result["sources"] == 4
    assert result["inspected"] == 4
    assert result["held"] == 4
    assert calls == {provider: 1 for provider in PROVIDERS}
    assert runs.latest("all-platforms-1")["held"] == 4


def test_platform_manifest_cycle_records_missing_source_as_partial(tmp_path):
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")
    result = cycle.run_platform_manifest_wake(
        {"coconala": lambda: [_item("coconala")]},
        candidates,
        runs,
        run_id="missing-lancers-1",
        observed_at="2026-09-30T06:02:00Z",
    )

    assert result["status"] == "partial"
    assert result["sources"] == 4
    assert result["inspected"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "crowdworks", "lancers", "mercor",
    }
    assert runs.latest("missing-lancers-1")["status"] == "partial"


def test_platform_manifest_cycle_rejects_unknown_source_before_discovery(tmp_path):
    called = False

    def discover():
        nonlocal called
        called = True
        return []

    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")
    try:
        cycle.run_platform_manifest_wake(
            {"unknown": discover},
            candidates,
            runs,
            run_id="unknown-source-1",
            observed_at="2026-09-30T06:03:00Z",
        )
    except cycle.PlatformManifestCycleError as error:
        assert str(error) == "source_provider_invalid"
    else:  # pragma: no cover - assertion keeps the failure explicit
        raise AssertionError("unknown source must fail closed")
    assert called is False

