import importlib.util
import json
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/crowdworks/scripts/reconcile_application_no_submit.py"
OWNER = "crowdworks-revenue-application"
OCC = f"{OWNER}:run-1"


def load():
    sys.path.insert(0, str(PATH.parent))
    spec = importlib.util.spec_from_file_location("crowdworks_reconcile_application_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def setup(tmp_path, receipts=(), pending=None):
    rows = [
        {"loop_id": OWNER, "run_id": "exec-9", "timestamp": "2026-09-20T03:00:00+00:00",
         "phase": "execute", "status": "running"},
        {"loop_id": OWNER, "run_id": "exec-9", "timestamp": "2026-09-20T03:04:00+00:00",
         "phase": "report", "status": "pass",
         "evidence_refs": [f"lm-occurrence://{OWNER}/run-1/claim"]},
    ]
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (tmp_path / "application-receipts.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in receipts))
    (tmp_path / "application-transaction.json").write_text(
        json.dumps({"fingerprints": [], "pending": pending or {}}))


# 12:00..12:04 JST window; proposals listed newest first with their first-message minute.
BEFORE = [(300, "2026年09月20日 11:57"), (200, "2026年09月19日 09:00")]


def test_no_proposal_in_claim_run_window_is_no_submit(tmp_path):
    module = load()
    setup(tmp_path)
    proposals = [(400, "2026年09月20日 12:07")] + BEFORE
    proof, reason = module.evaluate(tmp_path, [OCC], proposals)[OCC]
    assert reason == "ok" and proof["proof_type"] == "pre_effect"
    assert proof["evidence_ref"].startswith(f"lm-crowdworks-application-readback://{OWNER}/run-1/")


def test_proposal_in_window_or_bound_receipt_keeps_fence(tmp_path):
    module = load()
    setup(tmp_path)
    proposals = [(400, "2026年09月20日 12:02")] + BEFORE
    assert module.evaluate(tmp_path, [OCC], proposals)[OCC] == (None, "proposal_in_window:400")
    setup(tmp_path, receipts=[{"occurrence_id": OCC, "application_external_id": "1"}])
    assert module.evaluate(tmp_path, [OCC], BEFORE)[OCC] == (None, "application_receipt_bound")
    setup(tmp_path, pending={"x": {"occurrence_id": OCC}})
    assert module.evaluate(tmp_path, [OCC], BEFORE)[OCC] == (None, "application_transaction_pending")


def test_incomplete_or_unordered_readback_keeps_fence(tmp_path):
    module = load()
    setup(tmp_path)
    assert module.evaluate(tmp_path, [OCC], None)[OCC] == (None, "proposal_readback_incomplete")
    unordered = [(400, "2026年09月19日 08:00"), (300, "2026年09月20日 11:57")]
    assert module.evaluate(tmp_path, [OCC], unordered)[OCC] == (None, "proposal_order_unverified")
    # Readback stopped before reaching a proposal older than the window.
    assert module.evaluate(tmp_path, [OCC], [(400, "2026年09月20日 12:07")])[OCC] == (
        None, "proposal_readback_incomplete")


def test_unclaimed_occurrence_keeps_fence(tmp_path):
    module = load()
    setup(tmp_path)
    other = f"{OWNER}:run-2"
    assert module.evaluate(tmp_path, [other], BEFORE)[other] == (None, "claim_run_unavailable")


def test_recorded_proposals_are_read_even_when_unlisted(tmp_path):
    module = load()
    setup(tmp_path, receipts=[{"occurrence_id": "other", "application_external_id": "305"},
                              {"occurrence_id": "other", "application_external_id": "x"}])
    assert module.recorded_proposals(tmp_path) == {305}


def test_readback_defers_when_provider_browser_is_busy(monkeypatch, tmp_path):
    module = load()

    def busy(_state_root):
        raise module.ProviderBrowserBusy("crowdworks_provider_browser_busy")

    monkeypatch.setattr(module, "_provider_lease", busy)
    proposals, reason = module.read_proposals_with_lease(tmp_path, 0.0, set())
    assert proposals is None
    assert reason == "provider_browser_busy"


def test_exact_verified_receipt_reconciles_effect_only_after_opt_in(tmp_path, monkeypatch, capsys):
    module = load()
    receipt = {
        "record_type": "application_receipt", "platform": "crowdworks",
        "status": "verified", "occurrence_id": OCC,
        "application_external_id": "401",
    }
    setup(tmp_path, receipts=[receipt])
    admission_db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(admission_db) as db:
        db.execute("CREATE TABLE occurrences (occurrence_id TEXT, owner_id TEXT, state TEXT, effect_unknown INTEGER, queued_at TEXT)")
        db.execute("INSERT INTO occurrences VALUES (?, ?, 'claimed', 1, '2026-09-20T03:00:00Z')",
                   (OCC, OWNER))

    monkeypatch.setattr(module, "read_proposals_with_lease",
                        lambda *_args, **_kwargs: ([(401, "2026年09月20日 12:02")] + BEFORE, "ok"))
    from runtime.host import resource_admission
    close_calls = []

    def close(owner, occurrence, expected_state=None, proof_check=None):
        close_calls.append((owner, occurrence, expected_state, proof_check))
        return True

    monkeypatch.setattr(resource_admission, "_close_unknown_occurrence", close)
    dry_run = module.main(["--state-root", str(tmp_path), "--admission-db", str(admission_db)])
    report = json.loads(capsys.readouterr().out)
    assert dry_run == 0
    assert report["resolved"] == [{"occurrence_id": OCC, "dry_run": True,
                                   "evidence_ref": f"lm-crowdworks-application-readback://{OWNER}/run-1/401"}]
    assert close_calls == []
    assert not (tmp_path / "reconciliation").exists()

    resolved = module.main(["--state-root", str(tmp_path), "--admission-db", str(admission_db),
                            "--resolve"])
    report = json.loads(capsys.readouterr().out)
    assert resolved == 0
    assert report["resolved"] == [{"occurrence_id": OCC,
                                   "evidence_ref": f"lm-crowdworks-application-readback://{OWNER}/run-1/401"}]
    assert close_calls == [(OWNER, OCC, "claimed", None)]
    reconciliation = json.loads((tmp_path / "reconciliation" / "application-effect-run-1.json").read_text())
    assert reconciliation["provider_receipt_id"] == "proposal:401"
