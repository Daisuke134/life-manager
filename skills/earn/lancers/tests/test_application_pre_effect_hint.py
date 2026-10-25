from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/application_tick.py"
PRE_EFFECT = {"status": "pre_effect_failure", "effect": 0}


def _tick(monkeypatch, tmp_path: Path, *, account_ready: bool = True):
    spec = importlib.util.spec_from_file_location("lancers_application_pre_effect_hint_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_open_owned_page", lambda _factory: (object(), object()))
    monkeypatch.setattr(module, "_read_shared_ledger", lambda: "")  # the send gate must not need the network
    monkeypatch.setattr(module, "_production_account_ready", lambda _page: account_ready)
    monkeypatch.setattr(module, "_production_prepare", lambda *_args: None)
    monkeypatch.setattr(module, "_close_owned_page", lambda *_args: True)
    monkeypatch.setattr(module, "_stop_playwright_runtime", lambda _runtime: None)
    # lm_loop_run.py writes this marker before spawning application-owner.
    hint = tmp_path / "entrypoint-result.json"
    hint.write_text(json.dumps(PRE_EFFECT), encoding="utf-8")
    hint.chmod(0o600)
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))
    return module, hint


def _send(module, tmp_path: Path, submitter, project_id: str = "5599830"):
    return module.run_live_tick(
        project_id=project_id, proposal_text="proposal", proposed_amount_minor=30000,
        delivery_due_on="2026-10-30", state_path=tmp_path / "application.json",
        submitter_override=submitter, readback_override=lambda *_args: {},
    )


def test_proposal_send_clears_host_pre_effect_hint_first(monkeypatch, tmp_path: Path) -> None:
    module, hint = _tick(monkeypatch, tmp_path)
    seen = []

    def lost_click(*_args):
        seen.append(hint.exists())
        raise RuntimeError("final click outcome unknown")

    assert _send(module, tmp_path, lost_click).error == "submission_uncertain"
    assert seen == [False]
    assert not hint.exists()


def test_account_failure_before_send_keeps_host_pre_effect_hint(monkeypatch, tmp_path: Path) -> None:
    module, hint = _tick(monkeypatch, tmp_path, account_ready=False)

    def never_called(*_args):
        raise AssertionError("submitter must not run")

    assert _send(module, tmp_path, never_called).error == "account_unavailable"
    assert json.loads(hint.read_text(encoding="utf-8")) == PRE_EFFECT


def test_submission_not_started_restores_host_pre_effect_hint(monkeypatch, tmp_path: Path) -> None:
    module, hint = _tick(monkeypatch, tmp_path)

    def form_changed(*_args):
        raise module.SubmissionNotStarted("proposal_form_changed")

    assert _send(module, tmp_path, form_changed).error == "proposal_form_changed"
    assert json.loads(hint.read_text(encoding="utf-8")) == PRE_EFFECT
    assert stat.S_IMODE(hint.stat().st_mode) == 0o600


def test_submission_not_started_after_a_started_send_keeps_hint_cleared(monkeypatch, tmp_path: Path) -> None:
    module, hint = _tick(monkeypatch, tmp_path)

    def lost_click(*_args):
        raise RuntimeError("final click outcome unknown")

    def form_changed(*_args):
        raise module.SubmissionNotStarted("proposal_form_changed")

    assert _send(module, tmp_path, lost_click, "5599830").error == "submission_uncertain"
    assert _send(module, tmp_path, form_changed, "5599831").error == "proposal_form_changed"
    assert not hint.exists()
