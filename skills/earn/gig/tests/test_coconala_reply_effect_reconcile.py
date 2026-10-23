from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess

import pytest


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
    marker = kernel_root / "runs" / (hashlib.sha256(occurrence.encode()).hexdigest() + ".json")
    marker.parent.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        marker.write_text(json.dumps({"version": 1, "occurrence_id": occurrence, "items": [
            {"thread_id": "12", "status": "pending", "effect": 0, "readback": 0, "failed": 0},
        ]}))
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
    assert kwargs["env"]["AI_ENSURE_BROWSER"] == "/dev/null"


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


def _verified_state(kernel_root: Path, occurrence: str = OCCURRENCE) -> Path:
    path = _state(kernel_root, occurrence)
    value = json.loads(path.read_text(encoding="utf-8"))
    value.pop("send_diagnostic")
    value.update({"status": "verified", "occurrence_id": occurrence,
                  "receipt": {"provider_receipt_id": "sha256_cached", "effect_key": value["intent"]["effect_key"]}})
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_verified_state_of_the_same_occurrence_is_a_reconcile_target(tmp_path):
    kernel_root = tmp_path / "kernel"
    path = _verified_state(kernel_root)
    target = reconcile._find_target(kernel_root, OCCURRENCE)
    assert target is not None and target[0] == path
    assert reconcile._find_target(kernel_root, "hf-gig-reply-detector:other") is None


def test_verified_state_with_tampered_payload_is_rejected(tmp_path):
    kernel_root = tmp_path / "kernel"
    path = _verified_state(kernel_root)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["intent"]["payload"]["body"] = "別の回答"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert reconcile._find_target(kernel_root, OCCURRENCE) is None


def test_child_readback_ignores_synthetic_cached_receipt(tmp_path, monkeypatch):
    kernel_root = tmp_path / "kernel"
    path = _verified_state(kernel_root)
    seen = {}

    class Adapter:
        def __init__(self, state_root):
            self._receipts = {"x": {"provider_receipt_id": "sha256_cached"}}
        def readback(self, intent):
            seen["cache"] = dict(self._receipts)
            return {"verified": True, "provider_receipt_id": "msg-123", "observed_at": "2026-10-15T00:00:00Z"}

    monkeypatch.setattr(reconcile, "_load_adapter", lambda: type("M", (), {"CoconalaReplyAdapter": Adapter}))
    result = reconcile._child_readback(path, kernel_root, OCCURRENCE)
    assert seen["cache"] == {}
    assert result == {"status": "verified", "provider_receipt_id": "msg-123", "observed_at": "2026-10-15T00:00:00Z"}


def _thread_adapter(rows):
    class Adapter:
        def __init__(self, state_root):
            self._receipts = {}
        def readback(self, intent):
            return {"authoritative_absent": False}
        def _thread_reader(self, thread_id):
            return {"conversation": rows}, {}
    return lambda: type("M", (), {"CoconalaReplyAdapter": Adapter,
                                  "reply_browser": type("RB", (), {"outgoing_sha256": staticmethod(lambda body: body.strip())})})


def test_unique_exact_seller_text_in_official_thread_verifies_reply(tmp_path, monkeypatch):
    kernel_root = tmp_path / "kernel"
    path = _verified_state(kernel_root)
    monkeypatch.setattr(reconcile, "_load_adapter", _thread_adapter([
        {"side": "buyer", "message_id": "sha256_b", "body": "依頼です"},
        {"side": "seller", "message_id": "sha256_s", "body": "回答"},
    ]))
    result = reconcile._child_readback(path, kernel_root, OCCURRENCE)
    assert result["status"] == "verified"
    assert result["provider_receipt_id"] == "coconala-dm-12-sha256_s"


def test_absent_or_duplicated_seller_text_keeps_fence(tmp_path, monkeypatch):
    kernel_root = tmp_path / "kernel"
    path = _verified_state(kernel_root)
    for rows in ([{"side": "seller", "message_id": "sha256_x", "body": "別"}],
                 [{"side": "seller", "message_id": "sha256_1", "body": "回答"},
                  {"side": "seller", "message_id": "sha256_2", "body": "回答"}],
                 [{"side": "buyer", "message_id": "sha256_b", "body": "回答"}]):
        monkeypatch.setattr(reconcile, "_load_adapter", _thread_adapter(rows))
        assert reconcile._child_readback(path, kernel_root, OCCURRENCE)["status"] == "unknown"


def test_browser_readback_carries_the_coconala_session_env(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOAK_SESSION_VAULT_FILE", raising=False)
    monkeypatch.delenv("CLOAK_BROWSER_OWNER", raising=False)
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs["env"])
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    reconcile._browser_readback(tmp_path / "s.json", tmp_path, OCCURRENCE, runner=fake_run)
    assert seen["CLOAK_SESSION_VAULT_FILE"].endswith(".cloak/vault/gig-daily-driver/auth-state.json")
    assert seen["CLOAK_BROWSER_OWNER"] == "gig-reply-reconcile"


def test_every_reply_bound_to_the_occurrence_must_verify(tmp_path, monkeypatch, capsys):
    kernel_root = tmp_path / "kernel"
    first = _verified_state(kernel_root)
    second = kernel_root / "threads" / "thread-two" / "state.json"
    second.parent.mkdir(parents=True)
    value = json.loads(first.read_text())
    intent = value["intent"]
    intent["thread_id"] = "13"
    intent.pop("effect_key")
    intent["effect_key"] = hashlib.sha256(json.dumps(
        intent, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    second.write_text(json.dumps(value))
    marker_path = kernel_root / "runs" / (hashlib.sha256(OCCURRENCE.encode()).hexdigest() + ".json")
    marker = json.loads(marker_path.read_text())
    marker["items"].append({**marker["items"][0], "thread_id": "13"})
    marker_path.write_text(json.dumps(marker))
    assert reconcile._find_targets(kernel_root, OCCURRENCE) == sorted([first, second])
    answers = iter([{"status": "verified", "provider_receipt_id": "r1"}, {"status": "unknown"}])
    monkeypatch.setattr(reconcile, "_browser_readback", lambda *a, **k: next(answers))

    def resolve(owner_id, occurrence_id, *, official_readback, expected_state):
        return official_readback()["verified"]

    monkeypatch.setattr(reconcile.resource_admission, "resolve_unknown_occurrence", resolve)
    assert reconcile.main(["--occurrence", OCCURRENCE, "--resolve", "--kernel-root", str(kernel_root)]) == 0
    assert json.loads(capsys.readouterr().out)["resolved"] is False


def test_attachment_identity_drift_uses_text_only_thread(tmp_path, monkeypatch):
    kernel_root = tmp_path / "kernel"
    path = _verified_state(kernel_root)

    class Adapter:
        def __init__(self, state_root):
            self._receipts = {}
        def readback(self, intent):
            return {"authoritative_absent": False}
        def _thread_reader(self, thread_id):
            raise RuntimeError("collector_unhealthy:dm_attachment_message_identity_changed")
        def _read_thread_text_only(self, thread_id):
            return {"conversation": [{"side": "seller", "message_id": "sha256_t", "body": "回答"}]}, {}

    monkeypatch.setattr(reconcile, "_load_adapter", lambda: type("M", (), {
        "CoconalaReplyAdapter": Adapter,
        "reply_browser": type("RB", (), {"outgoing_sha256": staticmethod(lambda b: b.strip())})}))
    assert reconcile._child_readback(path, kernel_root, OCCURRENCE)["status"] == "verified"


def _run_snapshot(kernel_root, occurrence=OCCURRENCE):
    source = _state(kernel_root, occurrence)
    state = json.loads(source.read_text())
    state.pop("send_diagnostic")
    path = kernel_root / "runs" / (hashlib.sha256(occurrence.encode()).hexdigest() + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = {"version": 2, "occurrence_id": occurrence, "status": "effect_unknown", "items": [
        {"thread_id": "12", "status": "pending", "effect": 0, "readback": 0,
         "failed": 0, "reason": "reconcile_unknown", "reconcile_state": state},
        {"thread_id": "13", "status": "no_reply", "effect": 0, "readback": 1,
         "failed": 0, "reason": "replay_zero"},
    ]}
    path.write_text(json.dumps(marker))
    # A later wake no longer retains the original reply in the mutable thread state.
    source.write_text(json.dumps({"status": "no_reply", "occurrence_id": "later"}))
    return path, marker


def test_run_snapshot_reads_the_original_reply_after_thread_state_changes(tmp_path, monkeypatch):
    root = tmp_path / "kernel"
    path, _marker = _run_snapshot(root)

    class Adapter:
        def __init__(self, state_root):
            self._receipts = {}

        def readback(self, intent):
            assert intent["payload"]["body"] == "回答"
            assert intent["latest_event_id"] == "buyer-1"
            return {"verified": True, "provider_receipt_id": "official-12",
                    "observed_at": "2026-10-23T11:00:00Z"}

    monkeypatch.setattr(reconcile, "_load_adapter", lambda: type("M", (), {"CoconalaReplyAdapter": Adapter}))
    result = reconcile._child_readback(path, root, OCCURRENCE, thread_id="12")
    assert result["status"] == "verified"
    assert result["provider_receipt_id"] == "official-12"
    assert "回答" not in json.dumps(result, ensure_ascii=False)


def test_run_snapshot_uses_every_effect_target_without_exposing_reply(tmp_path, monkeypatch, capsys):
    root = tmp_path / "kernel"
    path, marker = _run_snapshot(root)
    second = json.loads(json.dumps(marker["items"][0]))
    second["thread_id"] = "14"
    intent = second["reconcile_state"]["intent"]
    intent["thread_id"] = "14"
    intent.pop("effect_key")
    intent["effect_key"] = hashlib.sha256(json.dumps(
        intent, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    marker["items"].append(second)
    path.write_text(json.dumps(marker))
    seen = []

    def run(argv, **_kwargs):
        seen.append(argv)
        thread = argv[argv.index("--thread-id") + 1]
        return subprocess.CompletedProcess(argv, 0, "COCONALA_READBACK " + json.dumps({
            "status": "verified", "provider_receipt_id": "official-" + thread,
        }), "")

    assert reconcile.main(["--occurrence", OCCURRENCE, "--kernel-root", str(root)], runner=run) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["verified"] is True
    assert len(seen) == 2
    assert {argv[argv.index("--thread-id") + 1] for argv in seen} == {"12", "14"}
    assert all(argv[argv.index("--state-path") + 1] == str(path) for argv in seen)
    assert "回答" not in output and all("回答" not in str(argv) for argv in seen)


@pytest.mark.parametrize("damage", ["payload", "missing_snapshot", "duplicate", "wrong_occurrence", "unsupported_version", "in_progress"])
def test_incomplete_run_snapshot_cannot_fall_back_to_a_remaining_thread(
    tmp_path, monkeypatch, capsys, damage,
):
    root = tmp_path / "kernel"
    path, marker = _run_snapshot(root)
    if damage == "payload":
        marker["items"][0]["reconcile_state"]["intent"]["payload"]["body"] = "改変"
    elif damage == "missing_snapshot":
        marker["items"][0].pop("reconcile_state")
    elif damage == "duplicate":
        marker["items"].append(marker["items"][0])
    elif damage == "wrong_occurrence":
        marker["occurrence_id"] = "hf-gig-reply-detector:wrong"
    elif damage == "in_progress":
        marker["status"] = "in_progress"
    else:
        marker["version"] = 3
    path.write_text(json.dumps(marker))
    # One valid mutable state must never override incomplete run evidence.
    source = root / "threads" / "thread-hash" / "state.json"
    source.unlink()
    source.parent.rmdir()
    _verified_state(root)

    def forbidden(*_args, **_kwargs):
        pytest.fail("incomplete run evidence must not reach the browser or release a fence")

    monkeypatch.setattr(reconcile.resource_admission, "resolve_unknown_occurrence", forbidden)
    reconcile.main(["--occurrence", OCCURRENCE, "--resolve", "--kernel-root", str(root)], runner=forbidden)
    assert json.loads(capsys.readouterr().out)["verified"] is False


def test_legacy_run_with_a_missing_effect_target_stays_fenced(tmp_path, capsys):
    root = tmp_path / "kernel"
    path, marker = _run_snapshot(root)
    marker["version"] = 1
    marker["items"][0].pop("reconcile_state")
    marker["items"][1].update({"status": "pending", "effect": 0, "readback": 0})
    path.write_text(json.dumps(marker))
    source = root / "threads" / "thread-hash" / "state.json"
    source.unlink()
    source.parent.rmdir()
    _verified_state(root)

    def forbidden(*_args, **_kwargs):
        pytest.fail("a missing second target cannot be represented by one remaining state")

    reconcile.main(["--occurrence", OCCURRENCE, "--kernel-root", str(root)], runner=forbidden)
    assert json.loads(capsys.readouterr().out)["verified"] is False


def test_missing_run_manifest_cannot_prove_all_effect_targets(tmp_path, capsys):
    root = tmp_path / "kernel"
    _verified_state(root)
    (root / "runs" / (hashlib.sha256(OCCURRENCE.encode()).hexdigest() + ".json")).unlink()

    def forbidden(*_args, **_kwargs):
        pytest.fail("one surviving state cannot prove that the original run had only one effect")

    reconcile.main(["--occurrence", OCCURRENCE, "--kernel-root", str(root)], runner=forbidden)
    assert json.loads(capsys.readouterr().out)["verified"] is False


def test_kernel_snapshot_reaches_official_readback_after_later_noop(tmp_path, monkeypatch):
    module_path = ROOT / "skills/_shared/marketplace-core/scripts/reply_kernel.py"
    spec = importlib.util.spec_from_file_location("reply_kernel_reconcile_integration", module_path)
    kernel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kernel)
    root = tmp_path / "kernel"

    class Adapter:
        latest = "buyer-1"
        available = False
        effects = 0

        def observe_threads(self):
            return [self.observe_one("12")]

        def observe_one(self, thread_id):
            return {"provider": "coconala", "account_id": "default", "thread_id": thread_id,
                    "latest_event_id": self.latest, "observed_at": "2026-10-23T11:00:00Z"}

        def context(self, _thread_id):
            return {"conversation": []}

        def mutate(self, _intent):
            self.effects += 1

        def readback(self, intent):
            if not self.available:
                return {"authoritative_absent": True}
            assert intent["payload"]["body"] == "保存する返信"
            return {"verified": True, "provider_receipt_id": "official-original",
                    "observed_at": "2026-10-23T11:00:00Z"}

    adapter = Adapter()
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", OCCURRENCE)
    first = kernel.run_wake(adapter=adapter, state_root=root, max_workers=1,
                            decide=lambda _: {"action": "reply", "payload": {"body": "保存する返信"}})
    assert first["pending"] == 1 and adapter.effects == 1
    adapter.available, adapter.latest = True, "buyer-2"
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "hf-gig-reply-detector:second")
    kernel.run_wake(adapter=adapter, state_root=root, max_workers=1, decide=lambda _: {})
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "hf-gig-reply-detector:third")
    kernel.run_wake(adapter=adapter, state_root=root, max_workers=1,
                    decide=lambda _: {"action": "noop", "classification": "no_reply"})
    current = json.loads(next(root.glob("threads/*/state.json")).read_text())
    assert current["status"] == "no_reply" and "intent" not in current
    monkeypatch.setattr(reconcile, "_load_adapter", lambda: type("M", (), {
        "CoconalaReplyAdapter": lambda **_kwargs: adapter}))
    path = root / "runs" / (hashlib.sha256(OCCURRENCE.encode()).hexdigest() + ".json")
    assert reconcile._child_readback(path, root, OCCURRENCE, thread_id="12")["status"] == "verified"
    assert adapter.effects == 1
