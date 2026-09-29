from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parents[1] / "scripts"
SCRIPT = SCRIPTS / "drive_checkpoint3.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module():
    spec = importlib.util.spec_from_file_location("drive_checkpoint3", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_short_review_url_requires_one_exact_redirect(monkeypatch) -> None:
    module = load_module()
    final = "https://capafy.ai/developer/createAgent?source=temp-link&token=123&page=review"
    monkeypatch.setattr(module, "_single_redirect_location", lambda *_args: [final])

    assert module._resolve_review_url("https://api.capafy.ai/R123") == final


def test_full_review_url_accepts_current_draft_key() -> None:
    module = load_module()
    url = "https://capafy.ai/developer/createAgent?draftKey=draft-abc&page=review"

    assert module._validate_review_url(url) == url


@pytest.mark.parametrize(
    "raw,location",
    (
        ("https://api.capafy.ai/not-review", "https://capafy.ai/developer/createAgent?token=1&page=review"),
        ("https://api.capafy.ai/R123?next=evil", "https://capafy.ai/developer/createAgent?token=1&page=review"),
    ),
)
def test_resolve_review_url_rejects_invalid_short_inputs(raw, location, monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "_single_redirect_location", lambda *_args: [location])

    with pytest.raises(RuntimeError):
        module._resolve_review_url(raw)


def test_resolve_review_url_rejects_cross_domain_location(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "_single_redirect_location", lambda *_args: ["https://evil.example/developer/createAgent?token=1&page=review"])

    with pytest.raises(RuntimeError, match="exact HTTPS Capafy"):
        module._resolve_review_url("https://api.capafy.ai/R123")


@pytest.mark.parametrize(
    "url",
    (
        "https://capafy.ai/developer/createAgent?source=temp-link&token=123&page=review&extra=1",
        "https://capafy.ai/developer/createAgent?source=temp-link&source=temp-link&token=123&page=review",
        "https://capafy.ai/developer/createAgent?source=temp-link&token=abc&page=review",
        "https://capafy.ai/developer/createAgent?draftKey=draft-abc&page=review&extra=1",
        "https://capafy.ai/developer/createAgent?draftKey=draft-abc&draftKey=second&page=review",
        "https://capafy.ai/developer/createAgent?draftKey=&page=review",
        "https://capafy.ai/developer/createAgent?draftKey=draft-abc&page=review#fragment",
    ),
)
def test_full_review_url_requires_exact_query_multimap(url) -> None:
    module = load_module()
    with pytest.raises(RuntimeError):
        module._validate_review_url(url)


def test_candidate_page_targets_scope_host_and_path(monkeypatch) -> None:
    module = load_module()
    import json

    targets = [
        {"type": "page", "url": "https://capafy.ai/developer/createAgent?old=1", "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/good"},
        {"type": "page", "url": "https://capafy.ai/other", "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/wrong-path"},
        {"type": "page", "url": "https://evil.example/developer/createAgent", "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/wrong-host"},
    ]

    class _Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(targets).encode()

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response())
    assert module._candidate_page_targets("http://localhost:9222") == [targets[0]]


def test_candidate_page_targets_fail_when_none(monkeypatch) -> None:
    module = load_module()
    import json

    class _Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps([]).encode()

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response())
    with pytest.raises(RuntimeError, match="no existing Capafy"):
        module._candidate_page_targets("http://localhost:9222")


def test_cp3_bounded_evaluate_caps_and_restores_timeout(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)

    class _Page:
        _call_timeout_s = 20.0

        def __init__(self):
            self.observed = []

        def evaluate(self, _expression):
            self.observed.append(self._call_timeout_s)
            return {"ready": "complete"}

    page = _Page()
    assert module._bounded_page_evaluate(page, "1", 105.0) == {"ready": "complete"}
    assert page.observed == [5.0]
    assert page._call_timeout_s == 20.0


class _SubmitPage:
    def __init__(self, states, click_results=None):
        self.states = iter(states)
        self.click_results = iter(click_results or [{"ok": True}])
        self.expressions = []

    def evaluate(self, expression):
        self.expressions.append(expression)
        if expression == self._module.SUBMIT_STATE_JS:
            return next(self.states)
        if "document.querySelectorAll('textarea')" in expression:
            return {"ok": True, "hydrated": True, "required": False}
        return next(self.click_results)


def test_unique_submit_without_modal_succeeds_when_button_becomes_disabled(monkeypatch) -> None:
    module = load_module()
    module.CP3_POLL_S = 0
    page = _SubmitPage([
        {"count": 1, "enabled": 1, "disabled": 0, "confirms": 0},
        {"count": 1, "enabled": 0, "disabled": 1, "confirms": 0},
    ])
    page._module = module

    module._wait_and_submit(page)

    assert module.SUBMIT_CLICK_JS in page.expressions


def test_unique_confirm_is_clicked_before_disabled_success(monkeypatch) -> None:
    module = load_module()
    module.CP3_POLL_S = 0
    page = _SubmitPage([
        {"count": 1, "enabled": 1, "disabled": 0, "confirms": 0},
        {"count": 1, "enabled": 1, "disabled": 0, "confirms": 1},
        {"count": 1, "enabled": 0, "disabled": 1, "confirms": 1},
    ], click_results=[{"ok": True}, {"ok": True}])
    page._module = module

    module._wait_and_submit(page)

    assert module.CONFIRM_CLICK_JS in page.expressions


def test_pending_draft_edits_are_saved_before_submit(monkeypatch) -> None:
    # 2844813315 (2026-09-29 14:50 JST): the version-update edit left the button
    # reading 下書き保存, so 審査に提出 never appeared within the deadline.
    module = load_module()
    module.CP3_POLL_S = 0
    page = _SubmitPage([
        {"count": 0, "enabled": 0, "disabled": 0, "confirms": 0, "drafts": 1},
        {"count": 1, "enabled": 1, "disabled": 0, "confirms": 0, "drafts": 0},
        {"count": 1, "enabled": 0, "disabled": 1, "confirms": 0, "drafts": 0},
    ], click_results=[{"ok": True}, {"ok": True}])
    page._module = module

    module._wait_and_submit(page)

    assert page.expressions.index(module.DRAFT_SAVE_CLICK_JS) < page.expressions.index(module.SUBMIT_CLICK_JS)


@pytest.mark.parametrize(
    "state",
    (
        {"count": 2, "enabled": 2, "disabled": 0, "confirms": 0},
        {"count": 1, "enabled": 0, "disabled": 1, "confirms": 0},
    ),
)
def test_submit_duplicate_or_disabled_fails_closed(state) -> None:
    module = load_module()
    module.CP3_POLL_S = 0
    module.CP3_HYDRATE_TIMEOUT_S = 0.01
    page = _SubmitPage([state])
    page._module = module

    with pytest.raises(RuntimeError):
        module._wait_and_submit(page)


def test_cp3_output_contains_no_url_or_token(monkeypatch, capsys) -> None:
    module = load_module()
    monkeypatch.delenv("CP3_TRANSPORT", raising=False)

    class _Page:
        def call(self, *_args, **_kwargs):
            return {}

        def close(self):
            pass

    monkeypatch.setattr(module, "_resolve_review_url", lambda _raw: "https://capafy.ai/developer/createAgent?token=secret&page=review")
    monkeypatch.setattr(module, "_require_cdp", lambda: "http://127.0.0.1:54137")
    monkeypatch.setattr(module, "_candidate_page_targets", lambda *_args: [{"webSocketDebuggerUrl": "ws://127.0.0.1/page"}])
    monkeypatch.setattr(module, "_open_responsive_page", lambda _targets: _Page())
    monkeypatch.setattr(module, "_navigate", lambda *_args: None)
    monkeypatch.setattr(module, "_wait_and_submit", lambda *_args: None)

    assert module.main(["drive_checkpoint3.py", "https://api.capafy.ai/R123"]) == 0
    output = capsys.readouterr().out
    assert output == "RESULT: submitted\n"
    assert "secret" not in output


def test_wait_and_submit_runs_workspace_field_fix_before_waiting_for_submit(monkeypatch, tmp_path) -> None:
    """A resumed draft's Agent ワークスペース tab (welcome-message/
    input-placeholder/test-case/DPA-checkbox) must be fixed in CP3's OWN page
    session, immediately before the submit-button wait below -- the required
    DPA checkbox has no separate save action that survives a reload, so
    running the fix in a different CP2 process/navigation would lose it
    (2026-09-28, 6273179459 / 9466718786)."""
    module = load_module()
    module.CP3_POLL_S = 0
    listing = tmp_path / "LISTING.md"
    listing.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CAPAFY_LISTING_PATH", str(listing))
    calls = []
    monkeypatch.setattr(
        module, "_raw_fill_workspace_conversation_fields",
        lambda _page, path: calls.append(path) or True,
    )
    page = _SubmitPage([
        {"count": 1, "enabled": 1, "disabled": 0, "confirms": 0},
        {"count": 1, "enabled": 0, "disabled": 1, "confirms": 0},
    ])
    page._module = module

    module._wait_and_submit(page)

    assert calls == [str(listing)]


def test_wait_and_submit_skips_workspace_fix_without_a_listing_path(monkeypatch) -> None:
    module = load_module()
    module.CP3_POLL_S = 0
    monkeypatch.delenv("CAPAFY_LISTING_PATH", raising=False)
    monkeypatch.setattr(
        module, "_raw_fill_workspace_conversation_fields",
        lambda *_a: pytest.fail("must not run without a LISTING path"),
    )
    page = _SubmitPage([
        {"count": 1, "enabled": 1, "disabled": 0, "confirms": 0},
        {"count": 1, "enabled": 0, "disabled": 1, "confirms": 0},
    ])
    page._module = module

    module._wait_and_submit(page)


def test_wait_and_submit_tolerates_a_failed_best_effort_workspace_fix(monkeypatch, tmp_path) -> None:
    module = load_module()
    module.CP3_POLL_S = 0
    listing = tmp_path / "LISTING.md"
    listing.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CAPAFY_LISTING_PATH", str(listing))

    def boom(*_a):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "_raw_fill_workspace_conversation_fields", boom)
    page = _SubmitPage([
        {"count": 1, "enabled": 1, "disabled": 0, "confirms": 0},
        {"count": 1, "enabled": 0, "disabled": 1, "confirms": 0},
    ])
    page._module = module

    module._wait_and_submit(page)  # must not raise -- best-effort only


def test_version_form_opens_the_version_tab_once_before_filling() -> None:
    module = load_module()
    module.CP3_POLL_S = 0

    class _Page:
        def __init__(self):
            self.states = iter((
                {"ok": True, "hydrated": False, "required": False},  # 基本情報 tab: nothing yet
                {"ok": True},                                           # バージョン tab click
                {"ok": True, "hydrated": True, "required": False},    # form now present
            ))

        def evaluate(self, _expression):
            return next(self.states)

    page = _Page()
    module._fill_version_update_if_required(page, "Switch hosted model.")
    with pytest.raises(StopIteration):
        next(page.states)
