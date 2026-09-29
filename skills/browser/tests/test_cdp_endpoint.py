import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "cdp_endpoint.py"
SPEC = importlib.util.spec_from_file_location("cdp_endpoint_test_module", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_default_endpoint_is_kept_when_lease_environment_is_absent(monkeypatch):
    monkeypatch.delenv("CLOAK_CDP_BASE_URL", raising=False)
    assert MODULE.configured_cdp_endpoint("http://127.0.0.1:9227") == "http://127.0.0.1:9227"


@pytest.mark.parametrize("value", [
    "http://127.0.0.1:51731",
    "http://localhost:51731/",
    "http://[::1]:51731",
])
def test_lease_endpoint_overrides_static_default(monkeypatch, value):
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", value)
    assert MODULE.configured_cdp_endpoint("http://127.0.0.1:9227") == value.rstrip("/")


@pytest.mark.parametrize("value", [
    "https://127.0.0.1:51731",
    "http://192.0.2.1:51731",
    "http://127.0.0.1:51731/path",
    "http://127.0.0.1:51731?query=1",
    "http://user:pass@127.0.0.1:51731",
    "not-an-endpoint",
])
def test_untrusted_lease_endpoint_fails_closed(monkeypatch, value):
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", value)
    with pytest.raises(ValueError, match="browser_endpoint_invalid"):
        MODULE.configured_cdp_endpoint("http://127.0.0.1:9227")


def test_projected_endpoint_requires_the_identity_join_when_requested(monkeypatch):
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", "http://127.0.0.1:51731")
    monkeypatch.delenv("LIFE_MANAGER_BROWSER_IDENTITY", raising=False)
    monkeypatch.delenv("LIFE_MANAGER_BROWSER_TARGET_OWNER", raising=False)
    with pytest.raises(ValueError, match="browser_identity_join_missing"):
        MODULE.configured_cdp_endpoint("http://127.0.0.1:9227", require_identity_join=True)


def test_projected_endpoint_accepts_a_complete_identity_join(monkeypatch):
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", "http://127.0.0.1:51731")
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_IDENTITY", "lancers:dais")
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_TARGET_OWNER", "lancers-revenue-browser")
    assert MODULE.configured_cdp_endpoint(
        "http://127.0.0.1:9227", require_identity_join=True,
    ) == "http://127.0.0.1:51731"


def test_endpoint_port_is_derived_from_the_leased_url():
    assert MODULE.endpoint_port("http://[::1]:51731") == 51731
