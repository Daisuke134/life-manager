from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("capafy_earn_reconcile.py")


def load_module():
    spec = importlib.util.spec_from_file_location("capafy_earn_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run(monkeypatch, capsys, ledger: Path, argv: list[str]) -> dict:
    mod = load_module()
    monkeypatch.setattr(sys, "argv", ["capafy_earn_reconcile.py", "--ledger", str(ledger), *argv])
    rc = mod.main()
    out = capsys.readouterr().out.strip().splitlines()[-1]
    summary = json.loads(out)
    summary["_rc"] = rc
    return summary


def _rows(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    return [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]


SALES = '{"code":0,"data":{"data":[{"date":"2026-10-01","orders":1,"revenue":1.99}]}}'


def test_payout_api_error_writes_no_payout_row_and_reports_failed(tmp_path: Path, monkeypatch, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"
    (tmp_path / "sales.json").write_text(SALES)
    (tmp_path / "payout.json").write_text('{"code":401,"msg":"unauthorized"}')

    summary = _run(monkeypatch, capsys, ledger,
                   ["--sales-json", str(tmp_path / "sales.json"), "--payout-json", str(tmp_path / "payout.json")])

    assert summary["_rc"] == 0
    assert summary["payout_fetch_status"] == "failed"
    assert "balance_payout_usd" not in summary
    assert "total_payout_usd" not in summary
    rows = _rows(ledger)
    assert [r["source"] for r in rows] == ["capafy-sales"]


def test_payout_live_fetch_exception_writes_no_payout_row(tmp_path: Path, monkeypatch, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"
    (tmp_path / "sales.json").write_text(SALES)
    mod = load_module()

    def boom(path: str, token: str) -> dict:
        raise OSError("network down")

    monkeypatch.setattr(mod, "_get", boom)
    monkeypatch.setattr(mod, "_token", lambda: "tok")
    monkeypatch.setattr(sys, "argv", ["capafy_earn_reconcile.py", "--ledger", str(ledger),
                                      "--sales-json", str(tmp_path / "sales.json")])
    rc = mod.main()
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert rc == 0
    assert summary["payout_fetch_status"] == "failed"
    assert all(r["source"] != "capafy-payout" for r in _rows(ledger))


def test_payout_success_still_writes_official_snapshot(tmp_path: Path, monkeypatch, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"
    (tmp_path / "sales.json").write_text(SALES)
    (tmp_path / "payout.json").write_text(
        '{"code":0,"data":{"balancePayout":59.0,"totalPayout":0.0,"balancePending":15.64,'
        '"balanceConfirmed":1.54,"currency":"usd","accountNumber":"****1900"}}')

    summary = _run(monkeypatch, capsys, ledger,
                   ["--sales-json", str(tmp_path / "sales.json"), "--payout-json", str(tmp_path / "payout.json")])

    assert summary["_rc"] == 0
    assert summary["payout_fetch_status"] == "fresh"
    assert summary["balance_payout_usd"] == 59.0
    payout = [r for r in _rows(ledger) if r["source"] == "capafy-payout"]
    assert len(payout) == 1
    assert payout[0]["balance_payout_usd"] == 59.0
    assert payout[0]["account"] == "****1900"
