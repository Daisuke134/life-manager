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
    tmp_path.mkdir(parents=True, exist_ok=True)
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


def test_read_proposals_rejects_redirect_to_another_proposal():
    module = load()

    class Node:
        first = None

        def __init__(self):
            self.first = self

        def locator(self, _selector):
            return self

        def text_content(self):
            return "Kaito｜AI自動化"

        def get_attribute(self, name):
            return {
                "datetime": "2026年09月20日 12:02",
                "href": "/public/employees/7145638",
            }.get(name)

    class ProposalPage:
        def __init__(self, displayed_id):
            self.displayed_id = displayed_id
            self.url = ""

        def goto(self, url, **_kwargs):
            self.url = (f"https://crowdworks.jp/proposals/{self.displayed_id}"
                        if url.endswith("/proposals/401") else url)

        def wait_for_timeout(self, _milliseconds):
            return None

        def eval_on_selector_all(self, _selector, _expression):
            return (["https://crowdworks.jp/proposals/401"]
                    if "?page=1" in self.url else [])

        def locator(self, _selector):
            return Node()

    assert module.read_proposals(ProposalPage(402), 0.0) is None
    proposals = module.read_proposals(ProposalPage(401), 0.0)
    assert proposals is not None and len(proposals) == 1
    assert {key: value for key, value in proposals[0].items() if key != "observed_at"} == {
        "proposal_id": 401,
        "proposal_url": "https://crowdworks.jp/proposals/401",
        "seller_identity": {
            "display_name": "Kaito｜AI自動化",
            "profile_url": "https://crowdworks.jp/public/employees/7145638",
        },
        "first_message_timestamp": "2026年09月20日 12:02",
        "first_message_minute": "2026-09-20T12:02+09:00",
    }
    assert proposals[0]["observed_at"].endswith("+00:00")


def test_exact_verified_receipt_reconciles_effect_only_after_opt_in(tmp_path, monkeypatch, capsys):
    module = load()
    from runtime.host import resource_admission

    state_root = tmp_path / "application-state"
    admission_root = tmp_path / "admission-root"
    admission_root.mkdir()
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    receipt = {
        "record_type": "application_receipt", "platform": "crowdworks",
        "status": "verified", "occurrence_id": OCC,
        "application_external_id": "401",
    }
    setup(state_root, receipts=[receipt])
    other = f"{OWNER}:run-2"
    admission_db = admission_root / "admission-v2.sqlite3"
    with resource_admission._database(admission_db) as db:
        for index, occurrence in enumerate((OCC, other), start=1):
            db.execute("""INSERT INTO occurrences(
                occurrence_id, owner_id, resource_class, admission_class, base_priority,
                queued_at, state, sequence, effect_unknown
            ) VALUES (?, ?, 'agent', 'revenue', 'revenue', ?, 'claimed', NULL, 1)""",
                       (occurrence, OWNER, float(index)))

    proposal = {
        "proposal_id": 401,
        "proposal_url": "https://crowdworks.jp/proposals/401",
        "seller_identity": {
            "display_name": "Kaito｜AI自動化",
            "profile_url": "https://crowdworks.jp/public/employees/7145638",
        },
        "first_message_timestamp": "2026年09月20日 12:02",
        "first_message_minute": "2026-09-20T12:02+09:00",
        "observed_at": "2026-10-08T10:00:00+00:00",
    }
    monkeypatch.setattr(module, "read_proposals_with_lease",
                        lambda *_args, **_kwargs: ([proposal] + BEFORE, "ok"))
    dry_run = module.main(["--state-root", str(state_root), "--admission-db", str(admission_db)])
    report = json.loads(capsys.readouterr().out)
    assert dry_run == 0
    assert report["resolved"] == [{"occurrence_id": OCC, "dry_run": True,
                                   "evidence_ref": f"lm-crowdworks-application-readback://{OWNER}/run-1/401"}]
    assert report["fenced"] == {other: "claim_run_unavailable"}
    assert not (state_root / "reconciliation").exists()
    with sqlite3.connect(admission_db) as db:
        assert db.execute("SELECT state, effect_unknown FROM occurrences WHERE occurrence_id=?",
                          (OCC,)).fetchone() == ("claimed", 1)

    resolved = module.main(["--state-root", str(state_root), "--admission-db", str(admission_db),
                            "--resolve"])
    report = json.loads(capsys.readouterr().out)
    assert resolved == 0
    assert report["resolved"] == [{"occurrence_id": OCC,
                                   "evidence_ref": f"lm-crowdworks-application-readback://{OWNER}/run-1/401"}]
    assert report["fenced"] == {other: "claim_run_unavailable"}
    with sqlite3.connect(admission_db) as db:
        assert db.execute("SELECT state, effect_unknown FROM occurrences WHERE occurrence_id=?",
                          (OCC,)).fetchone() == ("released", 0)
        assert db.execute("SELECT state, effect_unknown FROM occurrences WHERE occurrence_id=?",
                          (other,)).fetchone() == ("claimed", 1)
    reconciliation = json.loads((state_root / "reconciliation" / "application-effect-run-1.json").read_text())
    assert reconciliation["provider_receipt_id"] == "proposal:401"
    assert reconciliation["proposal_url"] == proposal["proposal_url"]
    assert reconciliation["seller_identity"] == proposal["seller_identity"]
    assert reconciliation["first_message_timestamp"] == proposal["first_message_timestamp"]
    assert reconciliation["first_message_minute"] == proposal["first_message_minute"]
    assert reconciliation["observed_at"] == proposal["observed_at"]


def test_resolve_rejects_admission_db_different_from_resolver_db(tmp_path, monkeypatch, capsys):
    module = load()
    state_root = tmp_path / "state"
    setup(state_root, receipts=[{
        "record_type": "application_receipt", "platform": "crowdworks",
        "status": "verified", "occurrence_id": OCC,
        "application_external_id": "401",
    }])
    resolver_root = tmp_path / "resolver-root"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(resolver_root))
    read_db = tmp_path / "read-only.sqlite3"
    with sqlite3.connect(read_db) as db:
        db.execute("CREATE TABLE occurrences (occurrence_id TEXT, owner_id TEXT, state TEXT, effect_unknown INTEGER, queued_at TEXT)")
        db.execute("INSERT INTO occurrences VALUES (?, ?, 'claimed', 1, '2026-09-20T03:00:00Z')",
                   (OCC, OWNER))
    provider_reads = []
    monkeypatch.setattr(module, "read_proposals_with_lease", lambda *_args: (
        provider_reads.append(True) or ([(401, "2026年09月20日 12:02")] + BEFORE, "ok")))

    result = module.main(["--state-root", str(state_root), "--admission-db", str(read_db),
                          "--resolve"])
    report = json.loads(capsys.readouterr().out)
    assert result == 75
    assert report["error"] == "admission_database_mismatch"
    assert provider_reads == []
    assert not (state_root / "reconciliation").exists()
    assert not (resolver_root / "admission-v2.sqlite3").exists()
