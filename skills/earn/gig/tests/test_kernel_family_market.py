"""`family_market` reduces a measured demand-evidence row to the public facts a proposal may
see and cite -- never the query, rationale, or seller wording the same row also carries.

Run: python3 -m pytest skills/_shared/marketplace-core/tests/test_kernel_family_market.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "storefront_kernel.py"
SPEC = importlib.util.spec_from_file_location("marketplace_storefront_kernel_family_market", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
kernel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = kernel
SPEC.loader.exec_module(kernel)


def _write_ledger(state_dir: Path, rows: list[dict]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "demand-evidence.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8",
    )


def _row(family: str, **overrides) -> dict:
    row = {
        "capability_family": family,
        "query": "some query the model proposed",
        "rationale": "why this query was chosen",
        "evidence_path": "/tmp/demand-search-example.json",
        "median_price_jpy": 7000,
        "sold_comparables": 1,
        "reviewed_comparables": 2,
        "visible_result_count": 100,
        "comparables": [
            {"display_price_jpy": 7000, "rating": 5.0, "review_count": 2,
             "title": "競合の商品タイトル", "url": "https://coconala.com/services/1"},
        ],
    }
    row.update(overrides)
    return row


# --- 1. newest row wins when several exist for the same family -----------------------------

def test_returns_newest_row_for_a_family_when_several_exist(tmp_path):
    state = tmp_path / "state"
    _write_ledger(state, [
        _row("excel_vba_gas_automation", median_price_jpy=3000, evidence_path="old.json"),
        _row("line_bot_dev", median_price_jpy=35000, evidence_path="other.json"),
        _row("excel_vba_gas_automation", median_price_jpy=29000, evidence_path="new.json"),
    ])
    market = kernel.family_market(state, "excel_vba_gas_automation")
    assert market is not None
    assert market["median_price_jpy"] == 29000
    assert market["evidence_path"] == "new.json"


# --- 2. unknown family and missing file both answer None ------------------------------------

def test_returns_none_for_an_unknown_family(tmp_path):
    state = tmp_path / "state"
    _write_ledger(state, [_row("excel_vba_gas_automation")])
    assert kernel.family_market(state, "some_other_family") is None


def test_returns_none_for_a_missing_ledger_file(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    assert kernel.family_market(state, "excel_vba_gas_automation") is None


def test_returns_none_for_a_corrupt_ledger_file(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "demand-evidence.jsonl").write_text("not json\n", encoding="utf-8")
    assert kernel.family_market(state, "excel_vba_gas_automation") is None


# --- 3. only the named fields cross; nothing else leaks --------------------------------------

def test_carries_only_the_six_named_fields_and_no_query_rationale_or_seller_title(tmp_path):
    state = tmp_path / "state"
    _write_ledger(state, [_row("excel_vba_gas_automation")])
    market = kernel.family_market(state, "excel_vba_gas_automation")
    assert set(market) == {
        "median_price_jpy", "sold_comparables", "reviewed_comparables",
        "visible_result_count", "evidence_path", "comparables",
    }
    assert market["comparables"] == [{"display_price_jpy": 7000, "rating": 5.0, "review_count": 2}]
    dumped = json.dumps(market, ensure_ascii=False)
    assert "query" not in dumped
    assert "rationale" not in dumped
    assert "some query the model proposed" not in dumped
    assert "why this query was chosen" not in dumped
    assert "競合の商品タイトル" not in dumped
    assert "coconala.com" not in dumped


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
