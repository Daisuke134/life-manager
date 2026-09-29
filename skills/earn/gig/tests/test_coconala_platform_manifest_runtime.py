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


def _live_collector_snapshot() -> dict[str, object]:
    return {
        "version": 1,
        "pass_id": "coconala-pass-1",
        "lease_fence": {"task": "coconala", "token": "token", "generation": 1},
        "observed_at": "2026-09-30T12:00:00Z",
        "objective": {
            "target_applications": 1,
            "max_applications": 1,
            "required_search_source_ids": ["single:new"],
        },
        "search_sources": [{
            "source_id": "single:new",
            "url": "https://coconala.com/requests?recruiting=true",
            "page_index": 1,
            "card_request_ids": ["123"],
            "has_next": False,
            "exhausted": True,
            "screenshot_sha256": "a" * 64,
            "dom_sha256": "b" * 64,
        }],
        # Opportunity data must be projected out before the platform manifest.
        "request_details": [{"request_id": "123", "visible_text": "client brief"}],
        "already_applied_ids": [],
        "snapshot_sha256": "c" * 64,
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


def test_live_coconala_wake_uses_collector_snapshot_without_onboarding_receipt(tmp_path):
    result = runtime.run_coconala_platform_manifest_wake(
        onboarding_path=tmp_path / "does-not-exist.json",
        live_snapshot=_live_collector_snapshot(),
        authenticated_state={
            "authenticated": True,
            "profile_readback": True,
            "account_id_sha256": "d" * 64,
        },
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="coconala-natural-live-1",
        observed_at="2026-09-30T12:02:00Z",
    )

    assert result["status"] == "partial"
    assert result["inspected"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "lancers", "crowdworks", "mercor",
    }
