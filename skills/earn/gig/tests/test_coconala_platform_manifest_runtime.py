from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = _load(
    SCRIPTS / "coconala_platform_manifest_runtime.py",
    "coconala_platform_manifest_runtime_test",
)


STATES = (
    "preflight", "authenticated", "email_verified", "sms_verified",
    "seller_information", "identity_approved", "bank_registered",
    "launchd_readback", "storefront_listing_readback",
)


def _onboarding() -> dict[str, object]:
    return {
        "version": 2,
        "platform": "coconala",
        "states": {
            state: {
                "status": "complete" if state == "authenticated" else "pending",
                "evidence_sha256": "b" * 64 if state == "authenticated" else None,
            }
            for state in STATES
        },
    }


def test_live_coconala_wake_reads_onboarding_and_persists_partial_cycle(tmp_path):
    onboarding_path = tmp_path / "coconala-onboarding.json"
    onboarding_path.write_text(
        json.dumps(_onboarding(), ensure_ascii=False), encoding="utf-8",
    )

    result = runtime.run_coconala_platform_manifest_wake(
        onboarding_path=onboarding_path,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="coconala-natural-1",
        observed_at="2026-09-30T12:00:00Z",
    )

    assert result["status"] == "partial"
    assert result["sources"] == 4
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "lancers", "crowdworks", "mercor",
    }
    assert result["next_actions"][0]["next_action"] == "collect_missing_gates"


def test_live_coconala_wake_missing_onboarding_is_typed_partial_without_creating_source(
    tmp_path,
):
    result = runtime.run_coconala_platform_manifest_wake(
        onboarding_path=tmp_path / "does-not-exist.json",
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="coconala-natural-missing-1",
        observed_at="2026-09-30T12:01:00Z",
    )

    assert result["status"] == "partial"
    assert result["inspected"] == 0
    assert {row["source"] for row in result["source_errors"]} == {
        "coconala", "lancers", "crowdworks", "mercor",
    }
    assert not (tmp_path / "does-not-exist.json").exists()
