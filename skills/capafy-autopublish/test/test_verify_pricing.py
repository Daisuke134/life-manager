import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_pricing.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_pricing", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_pricing"] = module
    spec.loader.exec_module(module)
    return module


LISTING_SUBSCRIPTION = """Primary Model: DeepSeek V4.1 Flash · category: マーケティング · tags: a, b, c

## Pricing
| cycle | price | cap | trial |
|---|---|---|---|
| day | $3.99 | 10 | No Free Trial |
| week | $9.99 | 30 | No Free Trial |
| month | $19.99 | 80 | No Free Trial |
| year | $99.99 | 960 | No Free Trial |

## Title
Hook Lab
"""

LISTING_DOWNLOAD = """category: 生産性 · tags: a, b, c

| download | $19.00 |

## Title
Some Download Skill
"""

LISTING_WITH_TRIAL = """Primary Model: DeepSeek V4.1 Flash · category: マーケティング · tags: a, b, c

## Pricing
| cycle | price | cap | trial |
|---|---|---|---|
| week | $9.99 | 30 | Free Trial 24h / 5 requests |

## Title
Trial Skill
"""


def _billing(cycle, price, cap, support_free_trial=0, free_trial_hours=24, free_trial_count=0):
    return {
        "billingMode": "subscription",
        "cycleType": cycle,
        "cyclePrice": price,
        "cycleMaxMessageCount": cap,
        "supportFreeTrial": support_free_trial,
        "freeTrialHours": free_trial_hours,
        "freeTrialCount": free_trial_count,
    }


OLD_HOOK_LAB_BILLINGS = [
    _billing("day", 1.99, 10),
    _billing("week", 4.99, 30),
    _billing("month", 9.99, 80),
]

TARGET_HOOK_LAB_BILLINGS = [
    _billing("day", 3.99, 10),
    _billing("week", 9.99, 30),
    _billing("month", 19.99, 80),
    _billing("year", 99.99, 960),
]


def test_listing_plans_parses_pricing_table(tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_SUBSCRIPTION, encoding="utf-8")
    plans = module.listing_plans(str(listing))
    assert plans == [
        {"cycle": "day", "price": "3.99", "cap": "10", "trial": None},
        {"cycle": "week", "price": "9.99", "cap": "30", "trial": None},
        {"cycle": "month", "price": "19.99", "cap": "80", "trial": None},
        {"cycle": "year", "price": "99.99", "cap": "960", "trial": None},
    ]


def test_listing_plans_is_none_for_download_mode(tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_DOWNLOAD, encoding="utf-8")
    assert module.listing_plans(str(listing)) is None


def test_main_reports_match_and_exits_zero(monkeypatch, tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_SUBSCRIPTION, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(module, "confirmed_billings", lambda *_a: TARGET_HOOK_LAB_BILLINGS)
    monkeypatch.setattr(sys, "argv", ["verify_pricing.py", "--agent-id", "8123079349", "--listing", str(listing)])
    assert module.main() == 0


def test_main_reports_mismatch_when_prices_are_stale_and_exits_nonzero(monkeypatch, tmp_path):
    """Reproduces the PROVEN 2026-09-29 Hook Lab incident: live billings still
    carry the OLD $1.99/$4.99/$9.99 rows (and no year row at all) while
    LISTING.md's target table already asks for $3.99/$9.99/$19.99/$99.99."""
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_SUBSCRIPTION, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(module, "confirmed_billings", lambda *_a: OLD_HOOK_LAB_BILLINGS)
    monkeypatch.setattr(sys, "argv", ["verify_pricing.py", "--agent-id", "8123079349", "--listing", str(listing)])
    assert module.main() == 1


def test_main_treats_no_billings_yet_as_ok(monkeypatch, tmp_path):
    """A brand-new draft that never reached CP1 price-save has no billings yet --
    nothing to reconcile, must not block a normal first-time publish."""
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_SUBSCRIPTION, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(module, "confirmed_billings", lambda *_a: [])
    monkeypatch.setattr(sys, "argv", ["verify_pricing.py", "--agent-id", "8123079349", "--listing", str(listing)])
    assert module.main() == 0


def test_main_treats_download_listing_as_ok(monkeypatch, tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_DOWNLOAD, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(sys, "argv", ["verify_pricing.py", "--agent-id", "123", "--listing", str(listing)])
    assert module.main() == 0


def test_main_matches_free_trial_target_against_billing_fields(monkeypatch, tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_WITH_TRIAL, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(module, "confirmed_billings", lambda *_a: [
        _billing("week", 9.99, 30, support_free_trial=1, free_trial_hours=24, free_trial_count=5),
    ])
    monkeypatch.setattr(sys, "argv", ["verify_pricing.py", "--agent-id", "8123079349", "--listing", str(listing)])
    assert module.main() == 0


def test_main_detects_missing_free_trial_as_mismatch(monkeypatch, tmp_path):
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_WITH_TRIAL, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(module, "confirmed_billings", lambda *_a: [
        _billing("week", 9.99, 30, support_free_trial=0),
    ])
    monkeypatch.setattr(sys, "argv", ["verify_pricing.py", "--agent-id", "8123079349", "--listing", str(listing)])
    assert module.main() == 1


def test_main_detects_missing_plan_row_as_mismatch(monkeypatch, tmp_path):
    """The year plan never made it into the live billings -- that is itself a
    mismatch, not something to silently ignore."""
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(LISTING_SUBSCRIPTION, encoding="utf-8")
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(module, "confirmed_billings", lambda *_a: TARGET_HOOK_LAB_BILLINGS[:3])
    monkeypatch.setattr(sys, "argv", ["verify_pricing.py", "--agent-id", "8123079349", "--listing", str(listing)])
    assert module.main() == 1
