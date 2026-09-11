from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("application_parent", SCRIPTS / "application_parent.py")
assert SPEC and SPEC.loader
application_parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(application_parent)


class _Connection:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return None


def _run_submit_click(
    tmp_path, monkeypatch, *, confirm_modal: bool, modal_present: bool = True
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    request_id = "123"
    expected_url = f"https://coconala.com/offers/add/{request_id}"
    modal_state = (
        {"modal": True, "title_count": 1, "button_count": 1,
         "button": {"x": 30, "y": 40}, "url": expected_url}
        if modal_present
        else {"modal": False, "url": expected_url, "body": ""}
    )
    states = iter([
        {"url": expected_url, "title": "提案", "match_count": 1,
         "button": {"x": 10, "y": 20}},
        *([modal_state] if confirm_modal else []),
        *(
            [
                {"url": application_parent._APPLIED_OFFERS_URL, "body": ""},
                {"url": application_parent._APPLIED_OFFERS_URL, "body": ""},
            ]
            if confirm_modal and not modal_present
            else [{"url": expected_url, "body": ""}]
        ),
    ])
    events: list[dict[str, object]] = []
    calls: list[dict[str, object]] = []
    effects = application_parent.CdpParentEffects(
        ws_url="ws://example.invalid/devtools/page/1",
        evidence_dir=tmp_path,
        ledger_path=tmp_path / "ledger.jsonl",
        pass_id="test-pass",
    )

    async def call(_ws, method, params, call_id):
        calls.append({"method": method, "params": params, "call_id": call_id})
        if method == "Input.dispatchMouseEvent":
            events.append(params)
        return {}

    async def evaluate(_ws, _expression, call_id):
        await call(_ws, "Runtime.evaluate", {}, call_id)
        return next(states), call_id + 1

    async def screenshot(_ws, call_id):
        await call(_ws, "Page.captureScreenshot", {}, call_id)
        return b"png", call_id + 1

    async def no_sleep(_seconds):
        return None

    async def connect(_url):
        return _Connection()

    monkeypatch.setattr(application_parent, "_cdp_connect", connect)
    monkeypatch.setattr(effects, "_call", call)
    monkeypatch.setattr(effects, "_eval_json", evaluate)
    monkeypatch.setattr(effects, "_screenshot", screenshot)
    monkeypatch.setattr(application_parent.asyncio, "sleep", no_sleep)

    asyncio.run(effects._click_button_async(request_id, "応募する", confirm_modal=confirm_modal))
    return events, calls


def test_submit_click_dispatches_complete_left_button_sequence(tmp_path, monkeypatch):
    events, calls = _run_submit_click(tmp_path, monkeypatch, confirm_modal=False)

    methods = [call["method"] for call in calls]
    assert [call["call_id"] for call in calls] == list(range(1, len(calls) + 1))
    enable_index = methods.index("Page.enable")
    bring_to_front_indices = [
        index for index, method in enumerate(methods) if method == "Page.bringToFront"
    ]
    input_indices = [
        index for index, method in enumerate(methods) if method == "Input.dispatchMouseEvent"
    ]
    assert len(bring_to_front_indices) == 1
    bring_to_front_index = bring_to_front_indices[0]
    first_input_index = input_indices[0]
    assert enable_index < bring_to_front_index
    assert bring_to_front_index + 1 == first_input_index
    assert calls[bring_to_front_index]["params"] == {}
    assert calls[bring_to_front_index]["call_id"] == calls[enable_index]["call_id"] + 2
    assert calls[first_input_index]["call_id"] == calls[bring_to_front_index]["call_id"] + 1

    assert events == [
        {"type": "mouseMoved", "x": 10.0, "y": 20.0, "button": "none", "buttons": 0, "clickCount": 0},
        {"type": "mousePressed", "x": 10.0, "y": 20.0, "button": "left", "buttons": 1, "clickCount": 1},
        {"type": "mouseReleased", "x": 10.0, "y": 20.0, "button": "left", "buttons": 0, "clickCount": 1},
    ]


def test_terms_modal_dispatches_the_same_complete_left_button_sequence(tmp_path, monkeypatch):
    events, calls = _run_submit_click(tmp_path, monkeypatch, confirm_modal=True)

    methods = [call["method"] for call in calls]
    assert [call["call_id"] for call in calls] == list(range(1, len(calls) + 1))
    enable_index = methods.index("Page.enable")
    bring_to_front_indices = [
        index for index, method in enumerate(methods) if method == "Page.bringToFront"
    ]
    input_indices = [
        index for index, method in enumerate(methods) if method == "Input.dispatchMouseEvent"
    ]
    assert len(bring_to_front_indices) == 2
    first_bring_to_front_index, second_bring_to_front_index = bring_to_front_indices
    first_input_index = input_indices[0]
    modal_first_input_index = input_indices[3]
    assert enable_index < first_bring_to_front_index
    assert first_bring_to_front_index + 1 == first_input_index
    assert second_bring_to_front_index + 1 == modal_first_input_index
    assert calls[first_bring_to_front_index]["params"] == {}
    assert calls[second_bring_to_front_index]["params"] == {}
    assert calls[first_bring_to_front_index]["call_id"] == calls[enable_index]["call_id"] + 2
    assert calls[first_input_index]["call_id"] == calls[first_bring_to_front_index]["call_id"] + 1
    assert calls[modal_first_input_index]["call_id"] == calls[second_bring_to_front_index]["call_id"] + 1

    assert events == [
        {"type": "mouseMoved", "x": 10.0, "y": 20.0, "button": "none", "buttons": 0, "clickCount": 0},
        {"type": "mousePressed", "x": 10.0, "y": 20.0, "button": "left", "buttons": 1, "clickCount": 1},
        {"type": "mouseReleased", "x": 10.0, "y": 20.0, "button": "left", "buttons": 0, "clickCount": 1},
        {"type": "mouseMoved", "x": 30.0, "y": 40.0, "button": "none", "buttons": 0, "clickCount": 0},
        {"type": "mousePressed", "x": 30.0, "y": 40.0, "button": "left", "buttons": 1, "clickCount": 1},
        {"type": "mouseReleased", "x": 30.0, "y": 40.0, "button": "left", "buttons": 0, "clickCount": 1},
    ]


def test_terms_modal_absent_keeps_single_primary_activation(tmp_path, monkeypatch):
    _events, calls = _run_submit_click(
        tmp_path, monkeypatch, confirm_modal=True, modal_present=False
    )

    methods = [call["method"] for call in calls]
    assert [call["call_id"] for call in calls] == list(range(1, len(calls) + 1))
    enable_index = methods.index("Page.enable")
    bring_to_front_indices = [
        index for index, method in enumerate(methods) if method == "Page.bringToFront"
    ]
    input_indices = [
        index for index, method in enumerate(methods) if method == "Input.dispatchMouseEvent"
    ]
    assert len(bring_to_front_indices) == 1
    assert len(input_indices) == 3
    bring_to_front_index = bring_to_front_indices[0]
    first_input_index = input_indices[0]
    assert enable_index < bring_to_front_index
    assert bring_to_front_index + 1 == first_input_index
    assert calls[bring_to_front_index]["params"] == {}
    assert calls[bring_to_front_index]["call_id"] == calls[enable_index]["call_id"] + 2
    assert calls[first_input_index]["call_id"] == calls[bring_to_front_index]["call_id"] + 1
