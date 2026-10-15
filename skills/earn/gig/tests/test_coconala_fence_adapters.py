from __future__ import annotations

import json
import subprocess
import tempfile
import sys
import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[4]
REGISTRY = ROOT / "config" / "loop-registry.json"
SCRIPT = ROOT / "skills" / "earn" / "gig" / "scripts" / "coconala_application_effect_reconcile.py"


def _load_wrapper():
    spec = importlib.util.spec_from_file_location("coconala_application_effect_reconcile_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Never read the live ~/gig evidence from a test.
    module.EVIDENCE_DIR = Path("/nonexistent-evidence")
    module.CLOSED_READBACK = Path("/nonexistent-evidence/request-closed-readback.json")
    scratch = Path(tempfile.mkdtemp(prefix="coconala-fence-test-"))
    module._scan_result_path = lambda result: result or scratch / "scan.json"
    return module


def test_coconala_effect_fence_adapters_are_registered() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    loops = registry["loops"]

    apply_reconcile = loops["hf-gig-apply-direct"]["effect_reconcile"]
    assert apply_reconcile == {
        "argv": [
            "skills/earn/gig/scripts/coconala_application_effect_reconcile.py",
        ],
        "occurrence_flag": None,
        "resolve_flag": None,
        "timeout_seconds": 900,
    }

    storefront_reconcile = loops["hf-gig-storefront-direct"]["effect_reconcile"]
    assert storefront_reconcile == {
        "argv": [
            "skills/earn/gig/scripts/storefront_pre_effect_reconcile.py",
        ],
        "occurrence_flag": "--occurrence",
        "resolve_flag": None,
        "timeout_seconds": 900,
    }


def test_application_reconcile_leases_registered_identity_only_after_exact_target(
    tmp_path, monkeypatch, capsys
) -> None:
    wrapper = _load_wrapper()
    monkeypatch.setattr(
        wrapper.reconciler,
        "discover_single_target",
        lambda *, owner_id, intent_root: ("occ-1", "run-1", ["123", "456"])
    )
    calls = []

    class Completed:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return Completed()

    monkeypatch.setattr(wrapper.subprocess, "run", fake_run)
    assert wrapper.main(["--intent-root", str(tmp_path)]) == 0

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [
        "bash",
        str(ROOT / "skills" / "browser" / "with-browser.sh"),
        "coconala:kosuke",
        "--",
        sys.executable,
        str(ROOT / "skills" / "earn" / "gig" / "scripts" / "application_occurrence_reconcile.py"),
        "--owner-id",
        "hf-gig-apply-direct",
        "--occurrence-id",
        "occ-1",
        "--runtime-run-id",
        "run-1",
        "--intent-root",
        str(tmp_path),
        "--max-pages",
        "1000",
        "--request-id",
        "123",
        "--request-id",
        "456",
    ]
    assert kwargs["cwd"] == ROOT
    assert kwargs["env"]["BROWSER_WAIT_SECONDS"] == "0"
    assert kwargs["env"]["AI_ENSURE_PROVISION_BROWSER"] == "/dev/null"
    assert capsys.readouterr().out == ""


def test_application_reconcile_does_not_touch_browser_without_exact_target(
    tmp_path, monkeypatch, capsys
) -> None:
    wrapper = _load_wrapper()
    monkeypatch.setattr(
        wrapper.reconciler,
        "discover_single_target",
        lambda *, owner_id, intent_root: None,
    )

    def fail_run(*args, **kwargs):
        raise AssertionError("browser must not be invoked without an exact target")

    monkeypatch.setattr(wrapper.subprocess, "run", fail_run)
    assert wrapper.main(["--intent-root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "nothing_to_reconcile"


def _intent(root: Path, request_id: str, state: str, phase: str | None) -> None:
    value = {"request_id": request_id, "state": state, "version": 2}
    if phase is not None:
        value["effect_phase"] = phase
    (root / f"{request_id}.json").write_text(json.dumps(value), encoding="utf-8")


def test_settled_write_ahead_store_closes_unbound_fences(tmp_path, monkeypatch, capsys) -> None:
    wrapper = _load_wrapper()
    monkeypatch.setattr(wrapper.reconciler, "discover_single_target",
                        lambda *, owner_id, intent_root: None)
    _intent(tmp_path, "1", "confirmed", "irreversible_attempt_started")
    _intent(tmp_path, "2", "retired_absent", None)
    _intent(tmp_path, "3", "prepared", "pre_effect")
    monkeypatch.setattr(wrapper, "_fenced_occurrences",
                        lambda owner_id: ["hf-gig-apply-direct:old-1"])
    proofs = []

    def resolver(owner_id, occurrence_id, *, settled_proof):
        proofs.append(settled_proof())
        return True

    monkeypatch.setattr(wrapper, "_resolve_settled", resolver)
    assert wrapper.main(["--intent-root", str(tmp_path)]) == 0

    assert proofs[0]["unresolved_irreversible"] == 0 and proofs[0]["scanned_intents"] == 3
    closure = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert closure["owner_id"] == "hf-gig-apply-direct"
    assert closure["occurrence_id"] == "hf-gig-apply-direct:old-1"
    assert closure["verified"] is True and closure["evidence_ref"].startswith("gig-intents://sha256/")


def test_unresolved_or_unreadable_intent_keeps_every_fence(tmp_path, monkeypatch, capsys) -> None:
    wrapper = _load_wrapper()
    monkeypatch.setattr(wrapper.reconciler, "discover_single_target",
                        lambda *, owner_id, intent_root: None)
    _intent(tmp_path, "1", "confirmed", "irreversible_attempt_started")
    _intent(tmp_path, "2", "prepared", "irreversible_attempt_started")
    (tmp_path / "3.json").write_text("{broken", encoding="utf-8")

    def never(*_args, **_kwargs):
        raise AssertionError("unsettled store must not read or release fences")

    monkeypatch.setattr(wrapper, "_fenced_occurrences", never)
    monkeypatch.setattr(wrapper, "_resolve_settled", never)
    assert wrapper.main(["--intent-root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "nothing_to_reconcile"
    assert result["unresolved_irreversible"] == 2


def test_legacy_prepared_or_stateless_intent_keeps_every_fence(tmp_path, monkeypatch, capsys) -> None:
    wrapper = _load_wrapper()
    monkeypatch.setattr(wrapper.reconciler, "discover_single_target",
                        lambda *, owner_id, intent_root: None)
    _intent(tmp_path, "1", "confirmed", "irreversible_attempt_started")
    (tmp_path / "2.json").write_text(json.dumps({"request_id": "2", "state": "prepared", "version": 1}))
    (tmp_path / "3.json").write_text(json.dumps({"request_id": "3"}))

    def never(*_args, **_kwargs):
        raise AssertionError("legacy prepared intents may have crossed the boundary")

    monkeypatch.setattr(wrapper, "_fenced_occurrences", never)
    monkeypatch.setattr(wrapper, "_resolve_settled", never)
    assert wrapper.main(["--intent-root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["unresolved_irreversible"] == 2


def test_legacy_intent_is_settled_by_applied_roster_or_closed_request(tmp_path, monkeypatch) -> None:
    wrapper = _load_wrapper()
    intents = tmp_path / "intents"
    intents.mkdir()
    for rid in ("10", "11", "12"):
        (intents / f"{rid}.json").write_text(json.dumps({"request_id": rid, "state": "prepared", "version": 1}))
    roster = tmp_path / "roster.json"
    roster.write_text(json.dumps({"official_readback": {"source": "code_owned_cdp_readback",
        "observed": True, "truncated": False, "request_ids": ["10"]}}))
    closed = tmp_path / "closed.json"
    closed.write_text(json.dumps({"source": "code_owned_cdp_readback", "requests": {
        "11": {"closed": True, "http_status": 200}, "12": {"closed": False, "http_status": 200}}}))

    scan = wrapper._settled_scan(intents, roster_path=roster, closed_path=closed)
    assert scan["unresolved_irreversible"] == 1          # 12 is still open

    closed.write_text(json.dumps({"source": "code_owned_cdp_readback", "requests": {
        "11": {"closed": True, "http_status": 200}, "12": {"closed": True, "http_status": 200}}}))
    assert wrapper._settled_scan(intents, roster_path=roster, closed_path=closed)["unresolved_irreversible"] == 0


def test_unreadable_closure_evidence_settles_nothing(tmp_path) -> None:
    wrapper = _load_wrapper()
    intents = tmp_path / "intents"
    intents.mkdir()
    (intents / "11.json").write_text(json.dumps({"request_id": "11", "state": "prepared", "version": 1}))
    bad = tmp_path / "closed.json"
    bad.write_text("{broken")
    assert wrapper._settled_scan(intents, roster_path=tmp_path / "missing.json",
                                 closed_path=bad)["unresolved_irreversible"] == 1


def _readback_module():
    path = ROOT / "skills" / "earn" / "gig" / "scripts" / "coconala_request_closed_readback.py"
    spec = importlib.util.spec_from_file_location("coconala_request_closed_readback_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_request_page_closed_parser() -> None:
    module = _readback_module()
    assert module.request_closed("納品希望日 2026年9月30日 募集期限 募集終了 締切日 2026年8月10日") is True
    assert module.request_closed("募集期限\n あと3日 締切日 2026年10月20日") is False
    assert module.request_closed("ページが見つかりません") is None
    assert module.request_closed("assist.coconala.com/ 募集終了 ブックマーク 募集者情報") is True
    assert module.request_closed("応募する ブックマーク 募集者情報") is False
    assert module.request_closed("■募集内容 時間単価：2,000円 募集終了後に連絡") is None


def test_non_intent_metadata_files_are_ignored_and_gone_requests_settle(tmp_path) -> None:
    wrapper = _load_wrapper()
    intents = tmp_path / "intents"
    intents.mkdir()
    (intents / "wedge-quarantine.json").write_text("{}")
    (intents / "full-history-scan-state.json").write_text(json.dumps({"pages_walked": 20}))
    (intents / "21.json").write_text(json.dumps({"request_id": "21", "state": "prepared", "version": 1}))
    closed = tmp_path / "closed.json"
    closed.write_text(json.dumps({"source": "code_owned_cdp_readback", "requests": {
        "21": {"closed": True, "gone": True, "http_status": 404}}}))
    scan = wrapper._settled_scan(intents, roster_path=tmp_path / "none.json", closed_path=closed)
    assert (scan["scanned_intents"], scan["unresolved_irreversible"]) == (1, 0)


def test_screenshot_retired_irreversible_and_unknown_shapes_stay_unresolved(tmp_path) -> None:
    wrapper = _load_wrapper()
    _intent(tmp_path, "31", "retired_absent", "irreversible_attempt_started")
    (tmp_path / "32.json").write_text(json.dumps({"status": "prepared", "irreversible": True}))
    (tmp_path / "wedge-quarantine.json").write_text("{}")
    scan = wrapper._settled_scan(tmp_path, roster_path=tmp_path / "none", closed_path=tmp_path / "none")
    assert (scan["scanned_intents"], scan["unresolved_irreversible"]) == (2, 2)
