from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load(
    SCRIPTS / "crowdworks_platform_manifest_runtime.py",
    "crowdworks_platform_manifest_runtime_test",
)
application_owner = _load(
    SCRIPTS / "application_owner.py",
    "crowdworks_application_owner_manifest_runtime_test",
)


def _snapshot() -> dict[str, object]:
    return {
        "version": 1,
        "platform": "crowdworks",
        "observed_at": "2026-09-30T14:00:00Z",
        "source_url": "https://crowdworks.jp/dashboard",
        "adapter_source_sha256": "a" * 64,
        "authenticated": True,
        "source_complete": True,
        "profile_readback": True,
        "evidence_refs": ["crowdworks://account/live", "crowdworks://profile/readback/true"],
    }


def test_live_snapshot_contains_only_account_profile_state():
    snapshot = runtime.build_live_snapshot(
        authenticated=True,
        profile_readback=True,
        observed_at="2026-09-30T14:00:00Z",
    )

    assert snapshot["source_complete"] is True
    assert snapshot["profile_readback"] is True
    assert "jobs" not in snapshot
    assert "opportunities" not in snapshot


def test_crowdworks_natural_wake_persists_account_profile_only(tmp_path):
    result = runtime.run_crowdworks_platform_manifest_wake(
        snapshot=_snapshot(),
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="crowdworks-natural-1",
        observed_at="2026-09-30T14:01:00Z",
    )

    assert result["status"] == "partial"
    assert result["sources"] == 4
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "coconala", "lancers", "mercor",
    }


def test_crowdworks_application_owner_bridge_writes_read_only_summary(tmp_path):
    payload = application_owner.record_live_crowdworks_platform_manifest_wake(
        snapshot=_snapshot(),
        evidence_dir=tmp_path / "evidence",
        pass_id="crowdworks-pass-1",
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        observed_at="2026-09-30T14:02:00Z",
    )

    assert payload["status"] == "partial"
    assert payload["read_only"] is True
    assert (tmp_path / "evidence" / "platform-manifest-wake.json").is_file()
