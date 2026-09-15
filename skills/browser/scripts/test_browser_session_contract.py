import pytest

from browser_session_contract import (
    browser_mode,
    configured_endpoint,
    normalize_endpoint,
    normalize_storage_scope,
)


def test_local_and_private_endpoints_are_normalized(monkeypatch):
    assert normalize_endpoint("http://127.0.0.1:9222/") == "http://127.0.0.1:9222"
    assert normalize_endpoint("http://steel:3000/") == "http://steel:3000"
    assert normalize_endpoint("http://steel-browser.railway.internal:8080/") == (
        "http://steel-browser.railway.internal:8080"
    )
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_ENDPOINT", "http://steel:3000/")
    monkeypatch.delenv("CLOAK_CDP_BASE_URL", raising=False)
    assert configured_endpoint() == "http://steel:3000"


def test_public_endpoint_requires_explicit_https_opt_in():
    with pytest.raises(ValueError, match="private endpoint"):
        normalize_endpoint("https://steel.example.com")
    assert normalize_endpoint("https://steel.example.com/", allow_public=True) == (
        "https://steel.example.com"
    )
    with pytest.raises(ValueError, match="endpoint"):
        normalize_endpoint("https://user:secret@steel.example.com", allow_public=True)
    with pytest.raises(ValueError, match="endpoint"):
        normalize_endpoint("http://steel:invalid", allow_public=True)


def test_headless_is_default_and_headed_requires_human_boundary(monkeypatch):
    monkeypatch.delenv("CLOAK_BROWSER_MODE", raising=False)
    monkeypatch.delenv("CLOAK_BROWSER_PURPOSE", raising=False)
    assert browser_mode() == {"mode": "headless", "purpose": "autonomous", "headless": True}
    with pytest.raises(ValueError, match="headed"):
        browser_mode(mode="headed", purpose="autonomous")
    assert browser_mode(mode="headed", purpose="human_gate")["headless"] is False


def test_storage_scope_requires_https_origin_and_named_non_secret_keys():
    assert normalize_storage_scope(
        "https://mercor.com/",
        ["theme", "mercor-auth-store"],
        ["csrf"],
    ) == {
        "origin": "https://mercor.com",
        "local_storage_keys": ["mercor-auth-store", "theme"],
        "session_storage_keys": ["csrf"],
    }
    for origin in ("http://mercor.com", "https://mercor.com/path", "https://user:pw@mercor.com"):
        with pytest.raises(ValueError, match="storage origin"):
            normalize_storage_scope(origin, ["theme"], [])
    for key in ("*", "auth_token", "session-secret"):
        with pytest.raises(ValueError, match="storage key"):
            normalize_storage_scope("https://mercor.com", [key], [])
