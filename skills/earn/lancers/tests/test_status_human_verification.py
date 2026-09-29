"""The Lancers WAF challenge is a typed provider boundary, never an empty market."""
from __future__ import annotations

from io import BytesIO, StringIO
import importlib.util
from pathlib import Path
import sys
import urllib.error

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "skills/earn/lancers/scripts/status.py"


def _status_module():
    spec = importlib.util.spec_from_file_location("lancers_status_human_verification_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_http_error_waf_body_is_typed_without_exposing_body(monkeypatch):
    module = _status_module()
    challenge = b"<title>Human Verification</title><script src=challenge.js></script>"
    error = urllib.error.HTTPError(
        "https://www.lancers.jp/work/search", 405, "method not allowed", {}, BytesIO(challenge)
    )
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))

    with pytest.raises(module.LancersProviderError) as excinfo:
        module.fetch_public_html(query="業務自動化", limit=1, timeout=1)

    assert excinfo.value.code == "lancers_human_verification_required"
    assert challenge not in str(excinfo.value).encode()


def test_success_status_waf_body_is_not_parsed_as_an_empty_market(monkeypatch):
    module = _status_module()
    challenge = b"<title>Human Verification</title>"

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return "https://www.lancers.jp/work/search?open=1"

        def read(self, _size):
            value, self._body = getattr(self, "_body", challenge), b""
            return value

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(module.LancersProviderError) as excinfo:
        module.fetch_public_html(query="業務自動化", limit=1, timeout=1)

    assert excinfo.value.code == "lancers_human_verification_required"


def test_discovery_returns_typed_provider_boundary(monkeypatch):
    module = _status_module()
    monkeypatch.setattr(
        module,
        "fetch_public_html",
        lambda **_kwargs: (_ for _ in ()).throw(module.LancersProviderError("lancers_human_verification_required")),
    )

    result = module.run_discovery(query="業務自動化", limit=1, timeout=1)

    assert result == {
        "ok": False,
        "platform": "lancers",
        "source": "public_html",
        "error": "lancers_human_verification_required",
    }


def test_application_loop_maps_provider_boundary_to_retryable_exit_75(tmp_path):
    path = REPO_ROOT / "skills/earn/lancers/scripts/application_loop.py"
    spec = importlib.util.spec_from_file_location("lancers_application_loop_human_verification_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def discovery(**_kwargs):
        return {
            "ok": False,
            "platform": "lancers",
            "source": "public_html",
            "error": "lancers_human_verification_required",
        }

    output = StringIO()
    result = module.run_loop(
        state_path=tmp_path / "application.json",
        evidence_root=tmp_path / "evidence",
        discovery=discovery,
        output_stream=output,
    )

    assert result["ok"] is False
    assert result["error"] == "human_verification_required"
    assert module.main(
        ["--json", "--state-path", str(tmp_path / "application-main.json")],
        discovery=discovery,
        stdout=StringIO(),
    ) == 75
