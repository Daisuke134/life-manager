from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock


TESTS = Path(__file__).parent
SCRIPT = TESTS.parent / "scripts" / "storefront_official_reconcile.py"
sys.path.insert(0, str(TESTS))

from test_storefront_pre_effect_reconcile import (  # noqa: E402
    OWNER_ID, pass_line, start_terminal_events, write_admission_db, write_jsonl,
    write_stdout_log,
)


def load_module():
    spec = importlib.util.spec_from_file_location("gig_storefront_official_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SERVICES = [
    {"service_id": "4244556", "state": "公開中", "price_jpy": 5000, "sales_count": None},
    {"service_id": "4244910", "state": "公開中", "price_jpy": 7000, "sales_count": 1},
]


def setup(tmp_path: Path, monkeypatch, *, snapshot_epoch: int = 250):
    """A legacy (unbound) fenced occurrence whose claimant run started at epoch 300."""
    module = load_module()
    run_id = "legacy-run"
    occurrence_id = f"{OWNER_ID}:claimed-legacy"
    runtime = tmp_path / "runtime"
    store = tmp_path / "store"
    host = tmp_path / "host"
    host.mkdir()
    write_jsonl(runtime / "events.jsonl", start_terminal_events(
        run_id, terminal_occurrence_id=occurrence_id,
    ))
    write_stdout_log(runtime / "logs" / "launchd.out.log", [pass_line(observed_at_epoch=305)])
    write_admission_db(host / "admission-v2.sqlite3", occurrence_id)
    monkeypatch.setattr(module.pre, "admission_root", lambda: host)
    snapshot = store / "evidence" / "storefront-direct-1-1" / "official-inventory.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(json.dumps({
        "observed_at": f"1970-01-01T00:0{snapshot_epoch // 60}:{snapshot_epoch % 60:02d}+00:00",
        "services": SERVICES, "service_count": len(SERVICES),
    }), encoding="utf-8")
    later = store / "evidence" / "storefront-direct-2-2" / "official-inventory.json"
    later.parent.mkdir(parents=True)
    later.write_text(json.dumps({
        "observed_at": "1970-01-01T00:05:05+00:00", "services": [], "service_count": 0,
    }), encoding="utf-8")
    write_jsonl(store / "effects.jsonl", [{"accepted_at_epoch": 100, "status": "accepted"}])
    (store / "effect-intents").mkdir()
    (store / "effect-intents" / "a.json").write_text(
        json.dumps({"status": "prepared", "prepared_at_epoch": 90}), encoding="utf-8")
    (store / "retire-intent-1.json").write_text(
        json.dumps({"status": "attempted", "attempted_at_epoch": 80}), encoding="utf-8")
    return module, occurrence_id, runtime, store


def child(services, status="verified"):
    record = {"status": status, "observed_at": "2026-10-16T00:00:00+00:00",
              "services": services, "content_sha256": "c" * 64}
    stdout = "noise\n" + "STOREFRONT_ROSTER " + json.dumps(record) + "\n"
    return Mock(return_value=subprocess.CompletedProcess([], 0, stdout, ""))


def run(module, occurrence_id, runtime, store, runner, *extra):
    return module.main([
        "--occurrence", occurrence_id, "--state-root", str(runtime),
        "--store", str(store), *extra,
    ], runner=runner)


def test_unchanged_official_roster_resolves_through_official_readback(
        tmp_path, monkeypatch, capsys):
    module, occurrence_id, runtime, store = setup(tmp_path, monkeypatch)
    resolver = Mock(return_value=True)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)
    runner = child([dict(row, sales_count=9) for row in SERVICES])

    code = run(module, occurrence_id, runtime, store, runner, "--resolve")
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["state"] == "RECONCILED"
    assert result["owner_id"] == OWNER_ID and result["occurrence_id"] == occurrence_id
    assert result["verified"] is True
    assert result["provider_receipt_id"] == "coconala-storefront-roster:" + "c" * 64
    command = runner.call_args.args[0]
    assert command[:4] == ["bash", str(module.WITH_BROWSER), "coconala:kosuke", "--"]
    environment = runner.call_args.kwargs["env"]
    assert environment["BROWSER_WAIT_SECONDS"] == "0"
    assert environment["CLOAK_SESSION_VAULT_FILE"].endswith("gig-daily-driver/auth-state.json")
    proof = resolver.call_args.kwargs["official_readback"]()
    assert proof["provider_receipt_id"] == result["provider_receipt_id"]
    assert resolver.call_args.args == (OWNER_ID, occurrence_id)
    assert resolver.call_args.kwargs["expected_state"] == "claimed"
    receipt = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["before"]["path"].endswith("storefront-direct-1-1/official-inventory.json")


def test_without_resolve_reports_proof_and_never_closes(tmp_path, monkeypatch, capsys):
    module, occurrence_id, runtime, store = setup(tmp_path, monkeypatch)
    resolver = Mock(return_value=True)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)

    code = run(module, occurrence_id, runtime, store, child(SERVICES))
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["state"] == "PROOF_READY" and result["verified"] is True
    resolver.assert_not_called()


def test_changed_official_roster_stays_fenced(tmp_path, monkeypatch, capsys):
    module, occurrence_id, runtime, store = setup(tmp_path, monkeypatch)
    resolver = Mock(return_value=True)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)
    changed = [SERVICES[0], dict(SERVICES[1], price_jpy=9000)]

    code = run(module, occurrence_id, runtime, store, child(changed), "--resolve")
    result = json.loads(capsys.readouterr().out)

    assert code == 1
    assert result == {**result, "state": "HELD", "verified": False,
                      "reason": "official_roster_changed_since_snapshot"}
    resolver.assert_not_called()


def test_ledgered_effect_after_snapshot_stays_fenced_without_browser(
        tmp_path, monkeypatch, capsys):
    module, occurrence_id, runtime, store = setup(tmp_path, monkeypatch)
    write_jsonl(store / "effects.jsonl", [{"accepted_at_epoch": 260, "status": "accepted"}])
    runner = child(SERVICES)

    code = run(module, occurrence_id, runtime, store, runner, "--resolve")
    result = json.loads(capsys.readouterr().out)

    assert code == 1
    assert result["reason"] == "effect_ledger_after_snapshot"
    runner.assert_not_called()


def test_write_ahead_intent_after_snapshot_stays_fenced(tmp_path, monkeypatch, capsys):
    module, occurrence_id, runtime, store = setup(tmp_path, monkeypatch)
    (store / "effect-intents" / "b.json").write_text(
        json.dumps({"status": "prepared", "prepared_at_epoch": 299}), encoding="utf-8")
    runner = child(SERVICES)

    code = run(module, occurrence_id, runtime, store, runner)
    result = json.loads(capsys.readouterr().out)

    assert code == 1
    assert result["reason"] == "write_ahead_intent_after_snapshot"
    runner.assert_not_called()


def test_missing_pre_occurrence_snapshot_stays_fenced(tmp_path, monkeypatch, capsys):
    module, occurrence_id, runtime, store = setup(tmp_path, monkeypatch, snapshot_epoch=301)

    code = run(module, occurrence_id, runtime, store, child(SERVICES))
    result = json.loads(capsys.readouterr().out)

    assert code == 1
    assert result["reason"] == "pre_occurrence_snapshot_missing"


def test_unreadable_official_roster_stays_fenced(tmp_path, monkeypatch, capsys):
    module, occurrence_id, runtime, store = setup(tmp_path, monkeypatch)
    resolver = Mock(return_value=True)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)
    failed = Mock(return_value=subprocess.CompletedProcess([], 75, "", "busy"))

    code = run(module, occurrence_id, runtime, store, failed, "--resolve")
    result = json.loads(capsys.readouterr().out)

    assert code == 1
    assert result["reason"] == "official_roster_unavailable"
    resolver.assert_not_called()


def test_two_claimant_runs_bracket_from_the_earliest_start(tmp_path, monkeypatch, capsys):
    """A wake retried after an in-run defer leaves two claimant terminals (2026-10-23)."""
    module, occurrence_id, runtime, store = setup(tmp_path, monkeypatch)
    retry = [
        dict(row, timestamp=row["timestamp"].replace("00:05:", "00:06:"))
        for row in start_terminal_events("retry-run", terminal_occurrence_id=occurrence_id)
    ]
    first = json.loads((runtime / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    write_jsonl(runtime / "events.jsonl", [
        first, *start_terminal_events("legacy-run", terminal_occurrence_id=occurrence_id)[1:],
        *retry,
    ])
    resolver = Mock(return_value=True)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)

    code = run(module, occurrence_id, runtime, store, child(SERVICES), "--resolve")
    result = json.loads(capsys.readouterr().out)

    assert code == 0, result
    assert result["state"] == "RECONCILED"
    receipt = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["before"]["path"].endswith("storefront-direct-1-1/official-inventory.json")
    assert receipt["claimant_run_ids"] == ["legacy-run", "retry-run"]
