import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_hosted_model.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_hosted_model", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_hosted_model"] = module
    spec.loader.exec_module(module)
    return module


LISTING_DEEPSEEK = """Primary Model: DeepSeek V4.1 Flash · category: 生産性 · tags: a, b, c

| cycle | price | cap | trial |
|---|---:|---|---|
| week | $3.99 | 40 | No Free Trial |

## Title
Some Skill
"""

LISTING_DOWNLOAD = """category: 生産性 · tags: a, b, c

| download | $19.00 |

## Title
Some Download Skill
"""


def test_listing_model_id_parses_primary_model(tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_DEEPSEEK, encoding="utf-8")
    assert module.listing_model_id(str(listing)) == "deepseek/deepseek-v4.1-flash"


def test_listing_model_id_is_none_for_download_mode(tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_DOWNLOAD, encoding="utf-8")
    assert module.listing_model_id(str(listing)) is None


def _detail_payload(required_credentials_model):
    return {
        "code": 0,
        "data": {
            "agentType": "run_online",
            "requiredCredentials": json.dumps({
                "url_proxy": [{"model": required_credentials_model}],
            }),
        },
    }


def test_confirmed_model_id_reads_required_credentials(monkeypatch):
    module = load_module()

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    payload = _detail_payload("anthropic/claude-sonnet-4.6")
    # json.load(response) is patched directly; json.loads (used afterward on
    # the requiredCredentials string) is untouched.
    monkeypatch.setattr(module.json, "load", lambda _fp: payload)
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda _request, timeout=25: _Response())
    assert module.confirmed_model_id("123", "tok") == "anthropic/claude-sonnet-4.6"


def test_main_reports_mismatch_and_exits_nonzero(monkeypatch, tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_DEEPSEEK, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(module, "confirmed_model_id", lambda *_a: "anthropic/claude-sonnet-4.6")
    monkeypatch.setattr(sys, "argv", ["check_hosted_model.py", "--agent-id", "4973250899", "--listing", str(listing)])
    assert module.main() == 1


def test_main_reports_match_and_exits_zero(monkeypatch, tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_DEEPSEEK, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(module, "confirmed_model_id", lambda *_a: "deepseek/deepseek-v4.1-flash")
    monkeypatch.setattr(sys, "argv", ["check_hosted_model.py", "--agent-id", "4973250899", "--listing", str(listing)])
    assert module.main() == 0


def test_main_treats_no_confirmed_model_yet_as_ok(monkeypatch, tmp_path):
    """A brand-new draft that never reached CP2 has no requiredCredentials
    yet -- nothing to reconcile, must not block a normal first-time publish."""
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_DEEPSEEK, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(module, "confirmed_model_id", lambda *_a: None)
    monkeypatch.setattr(sys, "argv", ["check_hosted_model.py", "--agent-id", "4973250899", "--listing", str(listing)])
    assert module.main() == 0


def test_main_treats_download_listing_as_ok(monkeypatch, tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_DOWNLOAD, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(sys, "argv", ["check_hosted_model.py", "--agent-id", "123", "--listing", str(listing)])
    assert module.main() == 0
