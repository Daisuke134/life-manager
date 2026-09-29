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
    SCRIPTS / "freelancer_platform_manifest_runtime.py",
    "freelancer_platform_manifest_runtime_test",
)


def _snapshot() -> dict[str, object]:
    return {
        "version": 1,
        "platform": "freelancer",
        "observed_at": "2026-09-30T05:02:00Z",
        "source_url": "https://www.freelancer.com/dashboard",
        "adapter_source_sha256": "a" * 64,
        "authenticated": False,
        "source_complete": False,
        "profile_readback": False,
        "account_id_sha256": None,
        "evidence_refs": ["freelancer://run/read-only-2"],
        "inventory_evidence_sha256": {
            "identity": "c" * 64,
            "projects": "d" * 64,
            "payments": "e" * 64,
            "payouts": "f" * 64,
        },
    }


def test_freelancer_wake_persists_one_held_platform_candidate(tmp_path):
    result = runtime.run_freelancer_platform_manifest_wake(
        snapshot=_snapshot(),
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="freelancer-natural-1",
        observed_at="2026-09-30T05:03:00Z",
    )

    assert result["status"] == "ok"
    assert result["sources"] == 1
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert result["promoted"] == 0
