from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


GIG_ROOT = Path(__file__).resolve().parents[1]
MODULE = GIG_ROOT / "scripts" / "providers" / "upwork_proposal_browser.py"


def _load():
    if not MODULE.is_file():
        return None
    spec = importlib.util.spec_from_file_location("upwork_proposal_browser_test", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


browser = _load()


def _payload() -> dict[str, object]:
    return {
        "attachments": [],
        "cover_letter": "Exact factual proposal.",
        "job_id": "~012345678901234",
        "job_source_sha256": "1" * 64,
        "job_url": "https://www.upwork.com/jobs/Exact-job_~012345678901234/",
        "payload_sha256": "2" * 64,
        "provider": "upwork",
        "screening_answers": [{"question": "Can you start now?", "answer": "Yes."}],
        "status": "frozen_waiting_for_connects",
        "terms": {
            "type": "fixed_price", "bid_usd": 15, "delivery_days": 1,
            "required_connects": 7, "available_connects_before": 0,
        },
        "title": "Exact job",
        "unsupported_claims": [],
    }


def _snapshot(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "job_id": "~012345678901234",
        "form_url": "https://www.upwork.com/ab/proposals/job/~012345678901234/apply/#/",
        "required_connects": 7,
        "available_connects": 7,
        "bid_usd": 15,
        "duration_label": "Less than 1 month",
        "cover_letter": "Exact factual proposal.",
        "screening_answers": [{"question": "Can you start now?", "answer": "Yes."}],
        "attachments": [],
        "submit_label": "Send for 7 Connects",
        "submit_enabled": True,
        "validation_errors": [],
    }
    value.update(overrides)
    return value


def test_exact_filled_form_returns_only_safe_preflight_receipt():
    assert browser is not None

    receipt = browser.validate_preflight(_snapshot(), _payload())

    assert receipt["ready"] is True
    assert receipt["job_id"] == "~012345678901234"
    assert receipt["required_connects"] == 7
    assert receipt["available_connects"] == 7
    assert len(receipt["evidence_sha256"]) == 64
    assert "Exact factual proposal" not in repr(receipt)


@pytest.mark.parametrize(
    "override",
    [
        {"required_connects": 8},
        {"available_connects": 6},
        {"cover_letter": "Different proposal."},
        {"screening_answers": [{"question": "Can you start now?", "answer": "Maybe."}]},
        {"submit_enabled": False},
    ],
)
def test_any_form_or_submit_mismatch_fails_before_click(override: dict[str, object]):
    assert browser is not None

    with pytest.raises(ValueError, match="upwork_proposal_preflight_mismatch"):
        browser.validate_preflight(_snapshot(**override), _payload())


def test_real_browser_fill_produces_exact_click_free_preflight():
    assert browser is not None
    html = """
      <div>When you submit this proposal <strong>7 Connects</strong>; Available Connects: 7</div>
      <label>Your bid <input data-test="bid" value=""></label>
      <div class="fe-proposal-job-estimated-duration">
        <button role="combobox">Select duration</button>
        <ul><li onclick="this.closest('div').querySelector('button').innerText=this.innerText">Less than 1 month</li><li>1 to 3 months</li></ul>
      </div>
      <div class="cover-letter-area"><textarea></textarea></div>
      <div class="fe-proposal-job-questions">
        <label>Can you start now?<textarea></textarea></label>
      </div>
      <footer><button class="air3-btn-primary">Send for 7 Connects</button></footer>
    """
    url = "https://www.upwork.com/ab/proposals/job/~012345678901234/apply/#/"
    executable = next(Path.home().glob(
        ".agent-browser/browsers/chrome-*/Google Chrome for Testing.app/Contents/"
        "MacOS/Google Chrome for Testing"
    ))
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch(
            headless=True, executable_path=str(executable),
        )
        page = chromium.new_page()
        page.route("https://www.upwork.com/**", lambda route: route.fulfill(body=html))
        page.goto(url)

        snapshot = page.evaluate(browser.fill_preflight_expression(_payload()))

        receipt = browser.validate_preflight(snapshot, _payload())
        assert receipt["ready"] is True
        assert page.locator(".cover-letter-area textarea").input_value() == "Exact factual proposal."
        assert page.locator('[data-test="bid"]').input_value() == "15"
        assert page.locator(".fe-proposal-job-questions textarea").input_value() == "Yes."
        assert page.locator("footer button").get_attribute("data-clicked") is None
        chromium.close()


def test_submit_mutation_requires_explicit_positive_fence_decision():
    assert browser is not None
    receipt = {"ready": True, "job_id": "~012345678901234"}
    calls: list[dict[str, object]] = []

    with pytest.raises(ValueError, match="upwork_proposal_effect_not_started"):
        browser.require_effect_start(receipt, lambda value: calls.append(value) or False)
    assert calls == [receipt]

    browser.require_effect_start(receipt, lambda value: calls.append(value) or True)
    assert calls == [receipt, receipt]


def test_submit_readback_requires_exact_official_proposal_id():
    assert browser is not None
    snapshot = {
        "job_id": "~012345678901234",
        "form_url": "https://www.upwork.com/ab/proposals/123456789/",
        "proposal_id": "123456789",
        "state": "submitted",
    }

    receipt = browser.validate_submit_readback(snapshot, _payload())

    assert receipt["proposal_id"] == "123456789"
    assert receipt["state"] == "submitted"
    assert len(receipt["evidence_sha256"]) == 64
    with pytest.raises(ValueError, match="upwork_proposal_submit_unconfirmed"):
        browser.validate_submit_readback({**snapshot, "proposal_id": None}, _payload())


def test_apply_path_is_not_a_proposal_receipt():
    assert browser is not None
    expression = browser.submit_readback_expression("~012345678901234")
    assert "(?!job" in expression


def test_browser_operator_prompt_uses_resolved_endpoint_not_fixed_port():
    assert browser is not None

    prompt = browser.browser_operator_prompt(
        "~012345678901234",
        "https://www.upwork.com/ab/proposals/job/~012345678901234/apply/#/",
        "http://127.0.0.1:9444",
    )

    assert "http://127.0.0.1:9444" in prompt
    assert "127.0.0.1:9233" not in prompt


def test_invitation_preflight_accepts_only_zero_cost_submit_form():
    assert browser is not None
    payload = _payload()
    payload["status"] = "frozen_waiting_for_invitation"
    payload["terms"] = {**payload["terms"], "required_connects": 0}
    snapshot = _snapshot(
        required_connects=0, available_connects=0, submit_label="Submit a proposal",
    )

    receipt = browser.validate_preflight(snapshot, payload)

    assert receipt["required_connects"] == 0
    assert receipt["available_connects"] == 0
    assert "accept and send a proposal" in browser.invitation_accept_expression().lower()
