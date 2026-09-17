from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/crowdworks/scripts/google_form.py"


def load():
    spec = importlib.util.spec_from_file_location("crowdworks_google_form_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_short_form_route_gets_bounded_wait_for_exact_official_viewform(tmp_path):
    module = load()
    events = []

    class Locator:
        def get_attribute(self, name):
            return "https://docs.google.com/forms/d/e/form-id/formResponse"
        def count(self): return 0

    class Page:
        url = "https://forms.gle/short"
        def goto(self, *args, **kwargs): pass
        def wait_for_timeout(self, value): pass
        def wait_for_url(self, pattern, timeout):
            events.append(timeout)
            self.url = "https://docs.google.com/forms/d/e/form-id/viewform"
        def locator(self, selector): return Locator()
        def close(self): pass

    class Context:
        def __init__(self): self.page = Page()
        def new_page(self): return self.page

    with pytest.raises(RuntimeError, match="answer-stop"):
        module.submit_once(context=Context(), state_root=tmp_path,
                           url="https://forms.gle/short",
                           url_sha256=__import__("hashlib").sha256(b"https://forms.gle/short").hexdigest(),
                           answer_fields=lambda page: (_ for _ in ()).throw(RuntimeError("answer-stop")))
    assert events == [10_000]


def test_non_google_redirect_fails_closed_with_sanitized_host(tmp_path):
    module = load()

    class Page:
        url = "https://accounts.google.com/login"
        def goto(self, *args, **kwargs): pass
        def wait_for_timeout(self, value): pass
        def close(self): pass

    class Context:
        def new_page(self): return Page()

    with pytest.raises(RuntimeError, match=r"google_form_route_invalid:accounts\.google\.com"):
        module.submit_once(context=Context(), state_root=tmp_path,
                           url="https://forms.gle/short",
                           url_sha256=__import__("hashlib").sha256(b"https://forms.gle/short").hexdigest(),
                           answer_fields=lambda page: [])


def test_pre_effect_receipt_absence_is_true_only_before_prepared_index(tmp_path):
    module = load()
    binding = {
        "provider": "crowdworks", "account_id": "7145638",
        "contract_id": "63659463", "milestone_id": "13820867",
        "form_revision_sha256": "a" * 64,
    }
    assert module.pre_effect_receipt_absent(tmp_path, binding) is True
    index = module._bound_index_path(tmp_path, binding)
    module.write_json(index, {"version": 1, "status": "prepared", "receipt_key": "x"})
    assert module.pre_effect_receipt_absent(tmp_path, binding) is False


def test_confirmed_revision_receipt_counts_for_the_original_form(tmp_path):
    module = load()
    binding = {
        "provider": "crowdworks", "account_id": "7145638",
        "contract_id": "63659463", "milestone_id": "13820867",
        "form_revision_sha256": "a" * 64,
    }
    revision = {**binding, "revision_event_id": "buyer-event-2"}
    receipt_key = module._identity({**revision, "submission_payload_sha256": "payload"})
    receipt = tmp_path / "external-actions" / f"{receipt_key}.json"
    receipt.parent.mkdir(parents=True)
    module.write_json(receipt, {"binding": revision, "status": "confirmed",
                                "confirmation_sha256": "confirmed"})
    module.write_json(tmp_path / "external-actions" / f"index-{module._identity(revision)}.json",
                      {"version": 1, "status": "confirmed", "receipt_key": receipt_key})
    assert module.has_confirmed_bound_receipt(tmp_path, binding) is True


def test_confirmed_bound_receipts_returns_revision_metadata(tmp_path):
    module = load()
    binding = {
        "provider": "crowdworks", "account_id": "7145638",
        "contract_id": "63570481", "milestone_id": "13798056",
        "form_revision_sha256": "a" * 64,
    }
    revision = {**binding, "revision_event_id": "427573234"}
    receipt_key = module._identity({**revision, "submission_payload_sha256": "payload"})
    receipt = tmp_path / "external-actions" / f"{receipt_key}.json"
    receipt.parent.mkdir(parents=True)
    module.write_json(receipt, {"binding": revision, "status": "confirmed",
                                "confirmation_sha256": "confirmed",
                                "observed_at": "2026-09-16T03:00:00Z"})
    module.write_json(tmp_path / "external-actions" / f"index-{module._identity(revision)}.json",
                      {"version": 1, "status": "confirmed", "receipt_key": receipt_key})

    receipts = module.confirmed_bound_receipts(tmp_path, binding)

    assert len(receipts) == 1
    assert receipts[0]["binding"]["revision_event_id"] == "427573234"
