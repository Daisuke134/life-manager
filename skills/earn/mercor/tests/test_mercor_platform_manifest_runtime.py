from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills" / "earn" / "mercor" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = _load(
    SCRIPTS / "mercor_platform_manifest_runtime.py",
    "mercor_platform_manifest_runtime_test",
)


def _reply_snapshot() -> dict[str, object]:
    return {
        "applications": [],
        "notifications": [],
        "assessments": [],
        "contracts": [],
        "interviews": [],
        "gmail": [{"threadId": "thread-1", "messages": []}],
        "source_health": {"gmail": {"status": "fresh", "observed_at": "2026-09-30T05:00:00Z"}},
        # These opportunity fields must never cross into the platform manifest.
        "inspected_listings": [{"listing_id": "list-1"}],
        "submitted": [{"listing_id": "list-1"}],
    }


def test_build_live_snapshot_contains_only_account_source_health():
    snapshot = runtime.build_live_snapshot(
        reply_snapshot=_reply_snapshot(),
        account_id="owner@example.com",
        auth_readback={"status": "authenticated", "url": "https://work.mercor.com/home"},
        observed_at="2026-09-30T05:01:00Z",
    )

    assert set(snapshot) == {
        "version", "platform", "observed_at", "source_url", "adapter_source_sha256",
        "account_id", "source_complete", "gmail_status", "contract_readback", "evidence_refs",
    }
    assert snapshot["source_complete"] is True
    assert snapshot["contract_readback"] is True
    assert snapshot["gmail_status"] == "fresh"
    assert "inspected_listings" not in snapshot
    assert "submitted" not in snapshot


def test_build_live_snapshot_marks_stale_or_incomplete_sources_false():
    reply = _reply_snapshot()
    reply["source_health"] = {"gmail": {"status": "stale", "observed_at": "2026-09-29T05:00:00Z"}}
    reply.pop("contracts")

    snapshot = runtime.build_live_snapshot(
        reply_snapshot=reply,
        account_id="owner@example.com",
        auth_readback={"status": "authenticated"},
        observed_at="2026-09-30T05:01:00Z",
    )

    assert snapshot["source_complete"] is False
    assert snapshot["contract_readback"] is False
    assert snapshot["gmail_status"] == "stale"


def test_run_wake_persists_mercor_hold_and_typed_missing_sources(tmp_path):
    snapshot = runtime.build_live_snapshot(
        reply_snapshot=_reply_snapshot(),
        account_id="owner@example.com",
        auth_readback={"status": "authenticated"},
        observed_at="2026-09-30T05:01:00Z",
    )

    result = runtime.run_mercor_platform_manifest_wake(
        snapshot=snapshot,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="mercor-natural-test",
        observed_at="2026-09-30T05:01:00Z",
    )

    assert result["status"] == "partial"
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert result["source_errors"]
    assert any(error["source"] == "coconala" for error in result["source_errors"])


def test_reply_owner_invokes_manifest_before_reply_kernel():
    source = (SCRIPTS / "reply-owner").read_text(encoding="utf-8")

    assert "--platform-manifest-evidence-dir" in source
    assert "--auth-readback" in source
    assert source.index("--platform-manifest-evidence-dir") < source.index("reply_kernel.py")
