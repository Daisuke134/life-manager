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
            "skills/earn/gig/scripts/storefront_official_reconcile.py",
        ],
        "occurrence_flag": "--occurrence",
        "resolve_flag": "--resolve",
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


# A post-marker intent retired because the 応募する control was never located (the
# parent raises before Input.dispatchMouseEvent). It settles only with the official
# applicant roster of its own request, read after the retire, excluding the account
# captured before the marker in the same pass (hf-gig-apply-direct:18dea9626ade1eb8-21113).
_PASS = "gig-apply-direct-1792093310697104000-319"


def _aborted_intent(tmp_path: Path, rid: str = "5324400", reason: str | None = None,
                    account: str = "2564121") -> tuple[Path, Path]:
    import hashlib
    intents, apply_root = tmp_path / "intents", tmp_path / "apply-direct"
    intents.mkdir(parents=True, exist_ok=True)
    cas = f"{rid}:snap:prop:40000:2027-02-28"
    intent = {"request_id": rid, "state": "retired_absent", "version": 5, "cas": cas,
              "effect_phase": "irreversible_attempt_started",
              "runtime_occurrence_id": "hf-gig-apply-direct:18dea9626ade1eb8-21113",
              "runtime_run_id": "18decb5dc0974808-99454",
              "lease_fence": {"task": f"gig-apply-direct-{_PASS}-commit-{rid}"}}
    (intents / f"{rid}.json").write_text(json.dumps(intent))
    archive = intents / "recovery-history" / rid / f"{hashlib.sha256(cas.encode()).hexdigest()}.json"
    archive.parent.mkdir(parents=True)
    archive.write_text(json.dumps({
        "event": "prepared_reconciled_absent",
        "reason": reason or "pre_submit_effect_not_started:click_submit_control:ParentContractError",
        "intent": {**intent, "state": "prepared"}}))
    worker = apply_root / _PASS / "refresh-evidence" / "commit-workers" / rid
    worker.mkdir(parents=True)
    (worker / f"gig-{_PASS}-commit-{rid}-B2-{rid}-identity.json").write_text(json.dumps({
        "source": "code_owned_cdp_authenticated_identity", "provider": "coconala",
        "request_id": rid, "account_id": account}))
    return intents, apply_root


def _roster(tmp_path: Path, rid: str = "5324400", ids=("111", "222"), count=None,
            contracted=0, observed_at="2099-01-01T00:00:00+00:00", expander_remaining=False) -> Path:
    closed = tmp_path / "closed.json"
    closed.write_text(json.dumps({"source": "code_owned_cdp_readback", "requests": {rid: {
        "closed": False, "gone": False, "http_status": 200,
        "url": f"https://coconala.com/requests/{rid}", "final_url": f"https://coconala.com/requests/{rid}",
        "applicant_ids": list(ids), "applicants_count": len(ids) if count is None else count,
        "contracted_count": contracted, "observed_at": observed_at,
        "requester_ids": ["999"], "expander_remaining": expander_remaining}}}))
    return closed


def _scan(wrapper, tmp_path, intents, apply_root, closed):
    return wrapper._settled_scan(intents, roster_path=tmp_path / "none.json", closed_path=closed,
                                 apply_root=apply_root)["unresolved_irreversible"]


def test_pre_submit_aborted_intent_settles_by_account_absent_applicant_roster(tmp_path) -> None:
    wrapper = _load_wrapper()
    intents, apply_root = _aborted_intent(tmp_path)
    assert _scan(wrapper, tmp_path, intents, apply_root, _roster(tmp_path)) == 0


def test_pre_submit_aborted_intent_stays_fenced_without_complete_absent_roster(tmp_path) -> None:
    wrapper = _load_wrapper()
    intents, apply_root = _aborted_intent(tmp_path)
    assert _scan(wrapper, tmp_path, intents, apply_root, _roster(tmp_path, ids=("111", "2564121"))) == 1
    assert _scan(wrapper, tmp_path, intents, apply_root, _roster(tmp_path, count=3)) == 1
    assert _scan(wrapper, tmp_path, intents, apply_root, _roster(tmp_path, contracted=1)) == 1
    assert _scan(wrapper, tmp_path, intents, apply_root,
                 _roster(tmp_path, observed_at="2000-01-01T00:00:00+00:00")) == 1
    assert _scan(wrapper, tmp_path, intents, apply_root, tmp_path / "missing.json") == 1
    # Counts can coincide before the list is fully expanded; an expander left means partial.
    assert _scan(wrapper, tmp_path, intents, apply_root, _roster(tmp_path, expander_remaining=True)) == 1
    missing_flag = json.loads((tmp_path / "closed.json").read_text())
    del missing_flag["requests"]["5324400"]["expander_remaining"]
    (tmp_path / "closed.json").write_text(json.dumps(missing_flag))
    assert _scan(wrapper, tmp_path, intents, apply_root, tmp_path / "closed.json") == 1


def test_other_retire_reasons_or_unbound_identity_stay_fenced(tmp_path) -> None:
    wrapper = _load_wrapper()
    intents, apply_root = _aborted_intent(tmp_path / "a", reason="screenshot_absent")
    assert _scan(wrapper, tmp_path / "a", intents, apply_root, _roster(tmp_path / "a")) == 1
    intents, apply_root = _aborted_intent(tmp_path / "b")
    for path in apply_root.rglob("*-identity.json"):
        path.unlink()
    assert _scan(wrapper, tmp_path / "b", intents, apply_root, _roster(tmp_path / "b")) == 1


def test_adapter_reads_roster_through_registered_browser_then_closes(tmp_path, monkeypatch, capsys) -> None:
    wrapper = _load_wrapper()
    intents, apply_root = _aborted_intent(tmp_path)
    closed = tmp_path / "closed.json"
    monkeypatch.setattr(wrapper, "CLOSED_READBACK", closed)
    monkeypatch.setattr(wrapper, "APPLY_ROOT", apply_root)
    monkeypatch.setattr(wrapper.reconciler, "discover_single_target",
                        lambda *, owner_id, intent_root: None)
    monkeypatch.setattr(wrapper, "_fenced_occurrences",
                        lambda owner_id: ["hf-gig-apply-direct:18dea9626ade1eb8-21113"])
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        _roster(tmp_path)
        return subprocess.CompletedProcess(command, 0)

    proofs = []
    monkeypatch.setattr(wrapper, "_resolve_settled",
                        lambda owner_id, occurrence_id, *, settled_proof: proofs.append(settled_proof()) or True)
    assert wrapper.main(["--intent-root", str(intents)], runner=runner) == 0
    assert commands and commands[0][:4] == ["bash", str(wrapper.WITH_BROWSER), "coconala:kosuke", "--"]
    assert commands[0][-1].endswith("coconala_request_closed_readback.py")
    assert proofs and proofs[0]["unresolved_irreversible"] == 0
    assert proofs[0]["occurrence_id"] == "hf-gig-apply-direct:18dea9626ade1eb8-21113"
    scan = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert scan["roster_readback_exit_code"] == 0


def test_roster_counts_only_dated_applicant_rows_never_the_requester() -> None:
    module = _readback_module()
    raw = {"applicants_count": 2, "contracted_count": 0, "requester_ids": ["999"], "entries": [
        {"id": "111", "row": "Yunamito 2026/10/14 12:29"},
        {"id": "999", "row": "募集者情報 nakaji7307 2026/10/14 12:29"},  # requester leak
        {"id": "333", "row": "関連する仕事 BAMGHA"},                     # no 応募日時
        {"id": "111", "row": "Yunamito 2026/10/14 12:29"}]}
    roster = module.roster_from_page(raw, expander_remaining=False)
    # Two counted but one real applicant listed: the count no longer matches by accident.
    assert roster["applicant_ids"] == ["111"]
    assert roster["requester_ids"] == ["999"] and roster["expander_remaining"] is False


# hf-gig-apply-direct:18dea9ef6158f5b0-37135 (2026-10-18): the full applied-history walk
# hit 403 Forbidden on every wake, while each bound request's own official page read
# 募集終了. A closed request can take no further application, so the exact occurrence
# closes from those per-request readbacks without walking the history.
def _closed_batch_setup(tmp_path, monkeypatch, rows):
    wrapper = _load_wrapper()
    intents = tmp_path / "intents"
    intents.mkdir()
    bound = []
    for rid, state in (("5323286", "confirmed"), ("5329025", "prepared"), ("5329137", "prepared")):
        (intents / f"{rid}.json").write_text("{}")
        bound.append({"request_id": rid, "state": state})
    monkeypatch.setattr(wrapper.reconciler, "_require_complete_request_set",
                        lambda root, **kw: bound)
    evidence = tmp_path / "evidence"
    monkeypatch.setattr(wrapper.reconciler, "_default_evidence_dir", lambda occ: evidence)
    calls = []

    class Completed:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv)
        result = Path(argv[argv.index("--result") + 1])
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(json.dumps({"source": "code_owned_cdp_readback", "requests": rows}))
        return Completed()

    resolved = []

    def resolver(owner_id, occurrence_id, *, closed_proof, expected_state):
        resolved.append((owner_id, occurrence_id, closed_proof(), expected_state))
        return True

    return wrapper, intents, calls, fake_run, resolver, resolved


def _closed_row(rid, closed=True):
    url = f"https://coconala.com/requests/{rid}"
    return {"closed": closed, "gone": False, "http_status": 200, "url": url, "final_url": url,
            "observed_at": "2099-01-01T00:00:00+00:00"}


def test_closed_bound_requests_close_the_exact_occurrence(tmp_path, monkeypatch) -> None:
    rows = {rid: _closed_row(rid) for rid in ("5329025", "5329137")}
    wrapper, intents, calls, fake_run, resolver, resolved = _closed_batch_setup(tmp_path, monkeypatch, rows)
    result = wrapper._close_closed_batch(
        "hf-gig-apply-direct", "occ-1", "run-1", ["5323286", "5329025", "5329137"], intents,
        runner=fake_run, resolver=resolver)
    assert result["status"] == "reconciled"
    # The earlier click may have applied: never record the effect as 0.
    assert (result["effect"], result["reason"]) == ("unknown", "duplicate_impossible_request_closed")
    assert len(calls) == 1 and calls[0][2] == "coconala:kosuke"
    assert calls[0][calls[0].index("--request-id") + 1] == "5329025"
    assert calls[0].count("--request-id") == 2           # confirmed 5323286 is not re-read
    owner, occurrence, proof, expected = resolved[0]
    assert (owner, occurrence, expected) == ("hf-gig-apply-direct", "occ-1", "claimed")
    assert proof["verified"] is True and proof["runtime_run_id"] == "run-1"
    assert proof["proof_type"] == "provider_request_closed_exact_batch.v1"
    assert proof["request_ids"] == ["5329025", "5329137"]
    assert (proof["effect"], proof["reason"]) == ("unknown", "duplicate_impossible_request_closed")


def test_closed_batch_uses_the_dedicated_admission_resolver() -> None:
    wrapper = _load_wrapper()
    import inspect
    source = inspect.getsource(wrapper._close_closed_batch)
    assert "resolve_request_closed_occurrence" in source
    assert "resolve_unknown_occurrence" not in source


def test_one_open_or_redirected_request_keeps_the_fence(tmp_path, monkeypatch) -> None:
    for index, bad in enumerate((_closed_row("5329137", closed=False),
                                 {**_closed_row("5329137"), "final_url": "https://coconala.com/login"},
                                 {**_closed_row("5329137"), "observed_at": "2000-01-01T00:00:00+00:00"})):
        rows = {"5329025": _closed_row("5329025"), "5329137": bad}
        case = tmp_path / f"case-{index}"
        case.mkdir()
        wrapper, intents, _calls, fake_run, resolver, resolved = _closed_batch_setup(case, monkeypatch, rows)
        assert wrapper._close_closed_batch(
            "hf-gig-apply-direct", "occ-1", "run-1", ["5323286", "5329025", "5329137"], intents,
            runner=fake_run, resolver=resolver) is None
        assert resolved == []
