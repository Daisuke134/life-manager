"""Regression coverage for official Capafy short review links."""
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "save_review_url.py"
SPEC = importlib.util.spec_from_file_location("save_review_url_under_test", SCRIPT)
save_review_url = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(save_review_url)


def test_accepts_numeric_official_short_review_link() -> None:
    url = "https://api.capafy.ai/21041752831257681920"

    assert save_review_url._is_edit_url(url)
