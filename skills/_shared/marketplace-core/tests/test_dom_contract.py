"""Strict matching is kept; anonymous refusal is not.

Measured 2026-09-07, three marketplaces and three separate strict matchers, each of which threw
away the one fact needed to repair it:

    Coconala   source_not_found        discarded the observed page title
    Coconala   form_state:absent       collapsed two causes with opposite fixes
    Lancers    proposal_form_changed   81 skips in one day, naming none of ten selectors
    CrowdWorks selector_unobserved     had the selector in hand and dropped it

Run: python3 -m pytest skills/_shared/marketplace-core/tests/test_dom_contract.py
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("dom_contract_under_test",
                                                  SCRIPTS / "dom_contract.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dom = _load()


class _Locator:
    def __init__(self, count=1, visible=True, selector="form#ProposalProposeForm"):
        self._count, self._visible, self._selector = count, visible, selector

    def count(self):
        if self._count == "raise":
            raise RuntimeError("locator detached")
        return self._count

    def is_visible(self):
        if self._visible == "raise":
            raise RuntimeError("element detached")
        return self._visible

    def __str__(self):
        return f"<Locator selector='{self._selector}'>"


def _one(tmp_path, **kw):
    return dom.exactly_one(_Locator(**kw), platform="lancers", evidence_dir=tmp_path)


def test_exactly_one_match_passes_through(tmp_path):
    locator = _Locator(1)
    assert dom.exactly_one(locator, platform="lancers", evidence_dir=tmp_path) is locator
    assert dom.failures(tmp_path) == []


def test_zero_matches_names_the_selector(tmp_path):
    with pytest.raises(dom.DomContractError) as caught:
        _one(tmp_path, count=0, selector="textarea#ProposalDescription")
    assert caught.value.found == 0
    row = dom.failures(tmp_path)[0]
    assert "ProposalDescription" in row["selector"]
    assert (row["why"], row["found"], row["platform"]) == ("count_not_one", 0, "lancers")


def test_several_matches_is_a_failure_too(tmp_path):
    """An ambiguous form is worse than a missing one: the lane would submit into the wrong field."""
    with pytest.raises(dom.DomContractError):
        _one(tmp_path, count=3, selector="#FeeApp input[type=text]")
    assert dom.failures(tmp_path)[0]["found"] == 3


def test_a_locator_that_throws_while_counting_is_recorded(tmp_path):
    with pytest.raises(dom.DomContractError):
        _one(tmp_path, count="raise")
    assert dom.failures(tmp_path)[0]["why"] == "count_failed"


def test_present_but_hidden_is_distinguished_from_missing(tmp_path):
    with pytest.raises(dom.DomContractError):
        dom.visible_one(_Locator(1, visible=False, selector="#form_end"),
                        platform="lancers", evidence_dir=tmp_path)
    row = dom.failures(tmp_path)[0]
    assert (row["why"], row["found"]) == ("not_visible", 1)


def test_a_detached_node_no_longer_stays_anonymous(tmp_path):
    """Re-raising every RuntimeError before recording is exactly how this case hid."""
    with pytest.raises(dom.DomContractError):
        dom.visible_one(_Locator(1, visible="raise"), platform="lancers", evidence_dir=tmp_path)
    assert dom.failures(tmp_path)[0]["why"] == "visibility_check_failed"


def test_the_page_identity_is_captured_when_offered(tmp_path):
    """A selector alone cannot say 'you were on the login page', which is how a dead session
    reads as a markup change."""
    with pytest.raises(dom.DomContractError):
        dom.exactly_one(_Locator(0), platform="coconala", evidence_dir=tmp_path,
                        observe=lambda: {"url": "https://coconala.com/login", "title": "ログイン"})
    assert dom.failures(tmp_path)[0]["observed"]["url"].endswith("/login")


def test_a_failing_observer_does_not_mask_the_real_failure(tmp_path):
    def broken():
        raise RuntimeError("page gone")

    with pytest.raises(dom.DomContractError) as caught:
        dom.exactly_one(_Locator(0), platform="coconala", evidence_dir=tmp_path, observe=broken)
    assert caught.value.why == "count_not_one"
    assert dom.failures(tmp_path)[0]["observed"] is None


def test_an_explicit_selector_wins_over_the_repr(tmp_path):
    with pytest.raises(dom.DomContractError):
        dom.exactly_one(_Locator(0), platform="crowdworks", evidence_dir=tmp_path,
                        selector='form#new_proposal[action="/proposals"]')
    assert dom.failures(tmp_path)[0]["selector"] == 'form#new_proposal[action="/proposals"]'


def test_recording_can_never_fail_the_lane(tmp_path):
    """Diagnostics must not be able to break a submission."""
    blocked = tmp_path / "file"
    blocked.write_text("x", encoding="utf-8")
    with pytest.raises(dom.DomContractError):
        dom.exactly_one(_Locator(0), platform="lancers", evidence_dir=blocked / "nested")


def test_every_refusal_is_appended_not_overwritten(tmp_path):
    for selector in ("a", "b", "c"):
        with pytest.raises(dom.DomContractError):
            _one(tmp_path, count=0, selector=selector)
    assert [row["selector"] for row in dom.failures(tmp_path)] == [
        "<Locator selector='a'>", "<Locator selector='b'>", "<Locator selector='c'>"
    ]


def test_an_adapter_can_preserve_its_existing_evidence_path(tmp_path):
    path = tmp_path / "proposal-form-changes.jsonl"
    with pytest.raises(dom.DomContractError):
        dom.exactly_one(_Locator(0), platform="lancers", evidence_dir=tmp_path,
                        evidence_path=path)
    assert path.exists()
    assert not (tmp_path / "dom-contract-failures.jsonl").exists()
