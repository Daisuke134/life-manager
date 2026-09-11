from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import application_parent  # noqa: E402


class _Connection:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return None


def _effects(tmp_path):
    return application_parent.CdpParentEffects(
        ws_url="ws://example.invalid/devtools/page/1",
        evidence_dir=tmp_path,
        ledger_path=tmp_path / "ledger.jsonl",
        pass_id="test-pass",
    )


def test_fill_refuses_ambiguous_controls_before_set_expression(tmp_path, monkeypatch):
    effects = _effects(tmp_path)
    expressions = []

    async def connect(_url):
        return _Connection()

    async def call(_ws, _method, _params, _call_id):
        return {}

    async def evaluate(_ws, expression, call_id):
        expressions.append(expression)
        return {"ok": False, "url": "https://coconala.com/offers/add/1", "title": "提案",
                "dom_counts": {"content": 2, "price": 1, "deliver_date": 1}}, call_id + 1

    monkeypatch.setattr(application_parent, "_cdp_connect", connect)
    monkeypatch.setattr(effects, "_call", call)
    monkeypatch.setattr(effects, "_eval_json", evaluate)

    with pytest.raises(application_parent.ParentContractError,
                       match="application_form_fill_failed"):
        asyncio.run(effects._fill_async("1", "proposal", 10000, "2026-09-20"))

    expression = expressions[0]
    assert expression.index("Object.values(counts).some") < expression.index("set(content")


def test_ambiguous_submit_label_never_dispatches_mouse_event(tmp_path, monkeypatch):
    effects = _effects(tmp_path)
    methods = []

    async def connect(_url):
        return _Connection()

    async def call(_ws, method, _params, _call_id):
        methods.append(method)
        return {}

    async def evaluate(_ws, _expression, call_id):
        return {"url": "https://coconala.com/offers/add/1", "title": "提案",
                "match_count": 2, "button": None, "controls": []}, call_id + 1

    async def screenshot(_ws, call_id):
        return b"png", call_id + 1

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(application_parent, "_cdp_connect", connect)
    monkeypatch.setattr(effects, "_call", call)
    monkeypatch.setattr(effects, "_eval_json", evaluate)
    monkeypatch.setattr(effects, "_screenshot", screenshot)
    monkeypatch.setattr(application_parent.asyncio, "sleep", no_sleep)

    with pytest.raises(application_parent.ParentContractError,
                       match="application_応募する_button_missing"):
        asyncio.run(effects._click_button_async("1", "応募する"))
    assert "Input.dispatchMouseEvent" not in methods


def test_ambiguous_terms_modal_never_dispatches_mouse_event(tmp_path, monkeypatch):
    effects = _effects(tmp_path)
    methods = []

    async def evaluate(_ws, _expression, call_id):
        return {"modal": True, "title_count": 2, "button_count": None,
                "button": None, "url": "https://coconala.com/offers/add/1"}, call_id + 1

    async def call(_ws, method, _params, _call_id):
        methods.append(method)
        return {}

    monkeypatch.setattr(effects, "_eval_json", evaluate)
    monkeypatch.setattr(effects, "_call", call)

    with pytest.raises(application_parent.ParentContractError,
                       match="submit_confirm_modal_failed"):
        asyncio.run(effects._confirm_terms_modal(object(), "1", 1))
    assert "Input.dispatchMouseEvent" not in methods
