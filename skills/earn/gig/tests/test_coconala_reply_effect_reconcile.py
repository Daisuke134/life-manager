from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[4]
SCRIPT = ROOT / "skills/earn/gig/scripts/coconala_reply_effect_reconcile.py"
REGISTRY = ROOT / "config/loop-registry.json"
SPEC = importlib.util.spec_from_file_location("coconala_reply_effect_reconcile_test", SCRIPT)
assert SPEC and SPEC.loader
reconcile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reconcile)

OCCURRENCE = "hf-gig-reply-detector:18dde86cdb81d360-30574"


def _state(kernel_root: Path, occurrence: str = OCCURRENCE) -> Path:
    path = kernel_root / "threads" / "thread-hash" / "state.json"
    path.parent.mkdir(parents=True)
    payload = {"body": "回答"}
    content_sha256 = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    base = {
        "version": 1,
        "provider": "coconala", "account_id": "default", "thread_id": "12",
        "latest_event_id": "buyer-1", "action": "reply",
        "payload": payload, "content_sha256": content_sha256,
    }
    effect_key = hashlib.sha256(json.dumps(
        base, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    intent = {**base, "effect_key": effect_key}
    thread_identity = "\0".join(("coconala", "default", "12"))
    path.write_text(json.dumps({
        "status": "reconcile_unknown",
        "occurrence_id": "hf-gig-reply-detector:older-intent",
        "intent": intent,
        "send_diagnostic": {
            "current_claimed_occurrence_id": occurrence,
            "effect_status": "unknown",
            "effect_key": intent["effect_key"],
            "content_sha256": content_sha256,
            "intent_sha256": hashlib.sha256(json.dumps(
                intent, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode()).hexdigest(),
            "thread_identity_sha256": hashlib.sha256(thread_identity.encode()).hexdigest(),
            "event_identity_sha256": hashlib.sha256(b"buyer-1").hexdigest(),
            "stored_intent_occurrence_id": "hf-gig-reply-detector:older-intent",
        },
    }), encoding="utf-8")
    return path


def test_registry_routes_reply_fence_to_exact_occurrence_adapter():
    loops = json.loads(REGISTRY.read_text(encoding="utf-8"))["loops"]
    assert loops["hf-gig-reply-detector"]["effect_reconcile"] == {
        "argv": ["skills/earn/gig/scripts/coconala_reply_effect_reconcile.py"],
        "occurrence_flag": "--occurrence",
        "resolve_flag": "--resolve",
        "timeout_seconds": 180,
    }


def test_no_exact_local_intent_does_not_acquire_browser_or_resolve(
    tmp_path, monkeypatch, capsys,
):
    kernel_root = tmp_path / "kernel"
    _state(kernel_root, "hf-gig-reply-detector:different-occurrence")

    def fail_run(*_args, **_kwargs):
        raise AssertionError("browser must not open without one exact intent")

    def fail_resolve(*_args, **_kwargs):
        raise AssertionError("fence must remain open without provider readback")

    monkeypatch.setattr(reconcile.subprocess, "run", fail_run)
    monkeypatch.setattr(reconcile.resource_admission, "resolve_unknown_occurrence", fail_resolve)

    assert reconcile.main([
        "--occurrence", OCCURRENCE, "--resolve", "--kernel-root", str(kernel_root),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verified"] is False
    assert result["reason"] == "exact_reply_state_not_found"


def test_positive_official_receipt_resolves_only_the_requested_occurrence(
    tmp_path, monkeypatch, capsys,
):
    kernel_root = tmp_path / "kernel"
    _state(kernel_root)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        result = {
            "status": "verified", "provider_receipt_id": "seller-message-2",
            "observed_at": "2026-10-12T23:00:00Z",
        }
        return subprocess.CompletedProcess(argv, 0, "COCONALA_READBACK " + json.dumps(result), "")

    resolutions = []

    def resolve(owner_id, occurrence_id, *, official_readback, expected_state):
        proof = official_readback()
        resolutions.append((owner_id, occurrence_id, expected_state, proof))
        return proof.get("verified") is True

    monkeypatch.setattr(reconcile.subprocess, "run", fake_run)
    monkeypatch.setattr(reconcile.resource_admission, "resolve_unknown_occurrence", resolve)

    assert reconcile.main([
        "--occurrence", OCCURRENCE, "--resolve", "--kernel-root", str(kernel_root),
    ]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["verified"] is True
    assert result["provider_receipt_id"] == "seller-message-2"
    assert result["occurrence_id"] == OCCURRENCE
    assert resolutions == [(
        "hf-gig-reply-detector", OCCURRENCE, "claimed", {
            "owner_id": "hf-gig-reply-detector", "occurrence_id": OCCURRENCE,
            "verified": True, "provider_receipt_id": "seller-message-2",
        },
    )]
    argv, kwargs = calls[0]
    assert "with-browser.sh" in argv[1]
    assert "coconala:kosuke" in argv
    assert kwargs["env"]["BROWSER_WAIT_SECONDS"] == "0"
    assert kwargs["env"]["AI_ENSURE_PROVISION_BROWSER"] == "/dev/null"


def test_missing_provider_receipt_keeps_exact_occurrence_fenced(
    tmp_path, monkeypatch, capsys,
):
    kernel_root = tmp_path / "kernel"
    _state(kernel_root)
    resolutions = []

    def fake_run(argv, **_kwargs):
        result = {"status": "unknown", "reason": "exact_provider_message_missing"}
        return subprocess.CompletedProcess(argv, 0, "COCONALA_READBACK " + json.dumps(result), "")

    monkeypatch.setattr(reconcile.subprocess, "run", fake_run)
    def resolve(_owner_id, _occurrence_id, *, official_readback, expected_state):
        assert expected_state == "claimed"
        proof = official_readback()
        resolutions.append(proof)
        return proof.get("verified") is True

    monkeypatch.setattr(reconcile.resource_admission, "resolve_unknown_occurrence", resolve)

    assert reconcile.main([
        "--occurrence", OCCURRENCE, "--resolve", "--kernel-root", str(kernel_root),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verified"] is False
    assert result["occurrence_id"] == OCCURRENCE
    assert resolutions == [{
        "owner_id": "hf-gig-reply-detector", "occurrence_id": OCCURRENCE,
        "verified": False,
    }]
