"""Regression coverage: Capafy CP1/CP2/CP3 browser attach must resolve through
a leased browser identity, never by probing a hardcoded debugging port.

Root cause (Hook Lab 8123079349, 2026-09-29 15:30 JST): cp1_agent.py's
_detect_cdp() (and drive_checkpoint2.py's copy, imported by drive_checkpoint3.py)
probed `for port in (9222, 9223)`. Port 9222 is Dais's personal, interactive
Chrome (registry: ~/.config/ai/registry/browsers.toml) -- loops must never
touch it. The fix: resolve only from an already-leased endpoint
(CP1_CDP_URL / CLOAK_CDP_BASE_URL / CDP, the env vars skills/browser/
with-browser.sh exports after leasing identity capafy:kosuke), and fail
closed (exit 75, retryable) instead of guessing a port.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_CDP_ENV_VARS = ("CP1_CDP_URL", "CLOAK_CDP_BASE_URL", "CDP")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _clear_cdp_env(monkeypatch):
    for var in _CDP_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize("module_name", ("cp1_agent", "drive_checkpoint2"))
def test_detect_cdp_never_probes_a_port_directly(module_name, monkeypatch):
    _clear_cdp_env(monkeypatch)
    module = _load(module_name)

    def urlopen(*_args, **_kwargs):
        raise AssertionError(f"{module_name}._detect_cdp must never probe a port directly")

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    assert module._detect_cdp() is None


@pytest.mark.parametrize("module_name", ("cp1_agent", "drive_checkpoint2"))
def test_detect_cdp_never_defaults_to_9222_or_9223(module_name, monkeypatch):
    _clear_cdp_env(monkeypatch)
    module = _load(module_name)
    result = module._detect_cdp()
    assert result is None
    assert result != "http://localhost:9222"
    assert result != "http://localhost:9223"


@pytest.mark.parametrize("module_name", ("cp1_agent", "drive_checkpoint2"))
def test_detect_cdp_uses_the_leased_endpoint_from_with_browser_sh(module_name, monkeypatch):
    _clear_cdp_env(monkeypatch)
    module = _load(module_name)
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", "http://127.0.0.1:54137")
    assert module._detect_cdp() == "http://127.0.0.1:54137"


@pytest.mark.parametrize("module_name", ("cp1_agent", "drive_checkpoint2"))
def test_detect_cdp_prefers_an_explicit_pre_resolved_override(module_name, monkeypatch):
    _clear_cdp_env(monkeypatch)
    module = _load(module_name)
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", "http://127.0.0.1:22222")
    monkeypatch.setenv("CP1_CDP_URL", "http://127.0.0.1:11111")
    assert module._detect_cdp() == "http://127.0.0.1:11111"


def test_cp1_agent_main_fails_closed_75_when_not_leased(monkeypatch, capsys):
    _clear_cdp_env(monkeypatch)
    module = _load("cp1_agent")
    monkeypatch.setattr(module, "CDP", None)
    monkeypatch.setattr(sys, "argv", ["cp1_agent.py", "shot"])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 75
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "capafy_browser_not_leased"
    assert payload["retryable"] is True
    assert payload["identity"] == "capafy:kosuke"


class _FakeLock:
    def fileno(self):
        return 0

    def close(self):
        pass


def test_cp1_agent_main_uses_the_leased_endpoint_not_a_bare_port(monkeypatch):
    module = _load("cp1_agent")
    monkeypatch.setattr(module, "CDP", "http://127.0.0.1:54137")
    monkeypatch.setattr(module, "_acquire_cdp_lock", lambda: _FakeLock())
    monkeypatch.setattr(module.fcntl, "flock", lambda *_a, **_k: None)
    monkeypatch.setattr(sys, "argv", ["cp1_agent.py", "shot"])
    seen = {}
    monkeypatch.setattr(module, "raw_main", lambda cmd: seen.setdefault("cmd", cmd))

    module.main()

    assert seen["cmd"] == "shot"


def test_drive_checkpoint2_require_cdp_exits_75_when_not_leased(monkeypatch, capsys):
    _clear_cdp_env(monkeypatch)
    module = _load("drive_checkpoint2")

    with pytest.raises(SystemExit) as exc:
        module._require_cdp()

    assert exc.value.code == 75
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "capafy_browser_not_leased"
    assert payload["retryable"] is True
    assert payload["identity"] == "capafy:kosuke"


def test_drive_checkpoint2_require_cdp_returns_the_leased_endpoint(monkeypatch):
    _clear_cdp_env(monkeypatch)
    module = _load("drive_checkpoint2")
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", "http://127.0.0.1:54137")
    assert module._require_cdp() == "http://127.0.0.1:54137"


def test_drive_checkpoint3_uses_the_shared_require_cdp_and_fails_closed(monkeypatch, capsys):
    _clear_cdp_env(monkeypatch)
    module = _load("drive_checkpoint3")

    with pytest.raises(SystemExit) as exc:
        module._require_cdp()

    assert exc.value.code == 75
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "capafy_browser_not_leased"
    assert payload["retryable"] is True


def test_capafy_browser_identity_defaults_to_coconala_kosuke(monkeypatch):
    for module_name in ("cp1_agent", "drive_checkpoint2"):
        monkeypatch.delenv("CAPAFY_BROWSER_IDENTITY", raising=False)
        module = _load(module_name)
        assert module.CAPAFY_BROWSER_IDENTITY == "capafy:kosuke"


def test_capafy_browser_identity_is_overridable(monkeypatch):
    monkeypatch.setenv("CAPAFY_BROWSER_IDENTITY", "coconala:other")
    for module_name in ("cp1_agent", "drive_checkpoint2"):
        module = _load(module_name)
        assert module.CAPAFY_BROWSER_IDENTITY == "coconala:other"
