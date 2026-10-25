"""The proposal send is gated on the shared APPLICATIONS ledger (origin/main), before the browser opens.

2026-10-26: this loop sent proposal 28079351 to Lancers 5620321 while another account already held
28078288. The ledger is the cross-agent claim store; the loop never read it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/application_tick.py"
HEADER = "| 日付 | 種別 | 内容 | key | owner | status | 備考 |\n|---|---|---|---|---|---|---|\n"


def _module(monkeypatch):
    spec = importlib.util.spec_from_file_location("lancers_application_ledger_gate_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def no_browser(_factory):
        raise AssertionError("the browser must not open when the ledger blocks the send")

    monkeypatch.setattr(module, "_open_owned_page", no_browser)
    return module


def _row(key, owner="参謀", status="applied"):
    return f"| 2026-10-26 | gig | Lancers x | {key} | {owner} | {status} | n |\n"


def _send(module, tmp_path, project_id):
    return module.run_live_tick(
        project_id=project_id, proposal_text="p", proposed_amount_minor=30000,
        delivery_due_on="2026-10-30", state_path=tmp_path / "application.json")


def test_another_accounts_ledger_claim_blocks_the_send_before_the_browser_opens(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    monkeypatch.setattr(module, "_read_shared_ledger", lambda: HEADER + _row("lancers:5620321"))
    result = _send(module, tmp_path, "5620321")
    assert result.ok is False and result.error == "ledger_claimed_elsewhere"


def test_an_unreadable_ledger_skips_only_this_send(monkeypatch, tmp_path):
    module = _module(monkeypatch)

    def down():
        raise OSError("offline")

    monkeypatch.setattr(module, "_read_shared_ledger", down)
    assert _send(module, tmp_path, "5620321").error == "ledger_unavailable"


def test_a_longer_id_is_not_a_substring_collision(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    monkeypatch.setattr(module, "_read_shared_ledger", lambda: HEADER + _row("lancers:56203219"))
    # free per the ledger, so the flow gets past the gate and fails later at the (refused) browser step
    result = _send(module, tmp_path, "5620321")
    assert result.error == "browser_unavailable"
