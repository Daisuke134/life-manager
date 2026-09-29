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


runtime = _load(
    SCRIPTS / "upwork_platform_manifest_runtime.py",
    "upwork_platform_manifest_runtime_test",
)


def _snapshot() -> dict[str, object]:
    return {
        "version": 1,
        "platform": "upwork",
        "observed_at": "2026-09-30T04:02:00Z",
        "source_url": "https://www.upwork.com/nx/wm/freelancer/home",
        "adapter_source_sha256": "a" * 64,
        "authenticated": True,
        "source_complete": True,
        "profile_readback": True,
        "account_id_sha256": "b" * 64,
        "evidence_refs": ["upwork://run/read-only-2"],
        "inventory_evidence_sha256": {
            "contracts": "c" * 64,
            "transactions": "d" * 64,
            "withdrawals": "e" * 64,
        },
    }


def test_upwork_wake_persists_one_held_platform_candidate(tmp_path):
    result = runtime.run_upwork_platform_manifest_wake(
        snapshot=_snapshot(),
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="upwork-natural-1",
        observed_at="2026-09-30T04:03:00Z",
    )

    assert result["status"] == "ok"
    assert result["sources"] == 1
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert result["promoted"] == 0
