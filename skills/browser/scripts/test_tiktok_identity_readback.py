from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module():
    scripts = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    try:
        path = scripts / "tiktok_identity_readback.py"
        spec = importlib.util.spec_from_file_location("tiktok_identity_readback", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(scripts))


def test_expected_identity_requires_matching_own_profile_navigation():
    module = _load_module()
    result = module.classify_readback({
        "url": "https://www.tiktok.com/@anicca.jp?lang=ja-JP",
        "profile_navigation_hrefs": [
            "https://www.tiktok.com/@anicca.jp?lang=ja-JP"
        ],
        "login_control_count": 0,
    }, "@anicca.jp")

    assert result["status"] == "authenticated_expected_identity"
    assert result["authenticated"] is True
    assert result["observed_handle"] == "@anicca.jp"


def test_readback_expression_supports_current_owned_profile_navigation():
    module = _load_module()

    assert '[data-e2e="nav-profile"] a[href*="/@"]' in module.READBACK_EXPRESSION
    assert 'a[data-e2e="nav-profile"][href*="/@"]' in module.READBACK_EXPRESSION


def test_public_profile_page_alone_is_not_authentication_proof():
    module = _load_module()
    result = module.classify_readback({
        "url": "https://www.tiktok.com/@anicca.jp",
        "profile_navigation_hrefs": [],
        "login_control_count": 1,
    }, "@anicca.jp")

    assert result["status"] == "identity_not_authenticated"
    assert result["authenticated"] is False


def test_different_authenticated_identity_fails_closed():
    module = _load_module()
    result = module.classify_readback({
        "url": "https://www.tiktok.com/@anicca.jp",
        "profile_navigation_hrefs": ["https://www.tiktok.com/@someone_else"],
        "login_control_count": 0,
    }, "@anicca.jp")

    assert result["status"] == "authenticated_identity_mismatch"
    assert result["authenticated"] is False
    assert result["observed_handle"] == "@someone_else"


def test_readback_closes_exact_owned_target_when_evaluation_fails(monkeypatch):
    module = _load_module()
    closed = []
    monkeypatch.setattr(module.cdp, "new_target", lambda _url, _owner: "owned-tab")
    monkeypatch.setattr(
        module.cdp, "evaluate", lambda _target, _source: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr(
        module.cdp, "close_target", lambda target, owner: closed.append((target, owner))
    )

    with pytest.raises(RuntimeError, match="boom"):
        module.readback("@anicca.jp", "paid-room")
    assert closed == [("owned-tab", "paid-room")]
