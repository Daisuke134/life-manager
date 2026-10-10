"""2026-10-10: 8 live agents sold the month plan at the week price (week $9.99 / month $10.00),
so every buyer could take a month for a week's money. The listing lint now fails that table."""
import subprocess
import sys
from pathlib import Path

LINT = Path(__file__).resolve().parents[1] / "scripts" / "lint_listing.py"
BODY = """## Title
Ad Hook Lab
## shortDescription
Angle variants and a test matrix for ad hooks.
## welcomeMessage
Paste your product.
## detailedDescription
Real output.
| cycle | price | cap | trial |
|---|---:|---:|---|
| week | $9.99 | 10 | No Free Trial |
| month | {month} | 25 | No Free Trial |
| year | $99.99 | 144 | No Free Trial |
"""


def _lint(tmp_path, month):
    listing = tmp_path / "LISTING.md"
    listing.write_text(BODY.format(month=month), encoding="utf-8")
    return subprocess.run([sys.executable, str(LINT), str(listing)], capture_output=True, text=True)


def test_month_priced_like_week_fails(tmp_path):
    result = _lint(tmp_path, "$10.00")
    assert result.returncode == 1 and "month price" in result.stdout


def test_month_at_market_band_passes_the_price_check(tmp_path):
    assert "month price" not in _lint(tmp_path, "$19.99").stdout
