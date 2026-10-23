"""Coconala revenue history -> CFO marketplace financial readback (A8.7)."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills" / "earn" / "gig" / "scripts"
PATH = SCRIPTS / "coconala_cfo_financial_readback.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skills.cfo import economic_attribution as contract  # noqa: E402
from skills.cfo.adapters import marketplace  # noqa: E402

OBSERVED = "2026-10-12T03:36:46.968670Z"
SNAPSHOT = "2026-10-12T04:00:00Z"
TRAILING = "2026-09-12T04:00:00Z"

PAGE_1 = """売上実績
サービス
今月の売上
25,740 円
累積売上
42,198 円
ブログ
累積売上
0 円
売上履歴
2026/10/12 10:00
トークルームNo：18250352
県提出書類作成一式
buyer_a
18,720 円
2026/10/11 23:00
トークルームNo：18180857
TikTok企画
buyer_b
7,020 円
2026/09/27 03:00
トークルームNo：18211957
自動更新プログラム開発
buyer_c
申請済み
13,260 円
<1
2
>
"""

PAGE_2 = """売上履歴
2026/08/05 14:19
トークルームNo：18069473
おひねり スクリーンショットのイタリア語化（4枚）
buyer_d
振込済み
78 円
2026/08/05 14:19
トークルームNo：18069473
おひねり スクリーンショットのイタリア語化（4枚）
buyer_d
振込済み
78 円
2026/08/05 14:19
トークルームNo：18069473
スクリーンショットのイタリア語化（4枚）
buyer_d
振込済み
3,042 円
<
1
2>
"""


def load():
    spec = importlib.util.spec_from_file_location("coconala_cfo_financial_readback_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def adapt(payload: dict, snapshot: str = SNAPSHOT, trailing: str = TRAILING) -> list[dict]:
    return marketplace.adapt(
        payload, snapshot_at=snapshot, trailing_start=trailing,
        platform="coconala", product_loop_id="gig-coconala",
    )


def test_every_history_row_becomes_one_settled_receipt_the_adapter_accepts() -> None:
    payload = load().build_readback([PAGE_1, PAGE_2], OBSERVED)
    assert payload["pagination"]["complete"] is True
    assert payload["receipt_map"]["complete"] is True
    assert payload["aggregate"] == {"currency": "JPY", "sales_count": 6, "net_amount_minor": 42198}

    rows = adapt(payload)
    receipts = {row["receipt_id"]: row for row in rows if row["record_type"] == "receipt"}
    # Identical tip rows are distinct sales: their sum is what reconciles to 累積売上.
    assert sorted(receipts) == [
        "marketplace:coconala:payment:coconala-revenue-18069473-202608051419-0",
        "marketplace:coconala:payment:coconala-revenue-18069473-202608051419-1",
        "marketplace:coconala:payment:coconala-revenue-18069473-202608051419-2",
        "marketplace:coconala:payment:coconala-revenue-18180857-202610112300-0",
        "marketplace:coconala:payment:coconala-revenue-18211957-202609270300-0",
        "marketplace:coconala:payment:coconala-revenue-18250352-202610121000-0",
    ]
    first = receipts["marketplace:coconala:payment:coconala-revenue-18250352-202610121000-0"]
    assert first["verification_state"] == "verified"
    assert first["occurred_at"] == "2026-10-12T01:00:00.000000Z"  # JST page time -> UTC
    assert first["components"] == [{"category": "settled_external_revenue", "amount": "18720"}]
    coverage = {row["projection"]: row for row in rows if row["record_type"] == "coverage"}
    # The page lists every credited sale but itemizes no fee/refund: revenue only.
    assert payload["coverage"]["historical"]["complete"] is False
    for projection in ("historical", "trailing"):
        assert coverage[projection]["coverage_state"] == "complete"
        assert coverage[projection]["covered_categories"] == ["settled_external_revenue"]
    assert coverage["as_of"]["reason"] == "missing_category"

    projected = contract.project(rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING)
    jpy = projected["historical"]["loops"]["gig-coconala"]["currencies"]["JPY"]
    assert jpy["settled_external_revenue"] == "42198"
    assert jpy["refund"] is None and jpy["provider_fee"] is None and jpy["net"] is None


def test_rows_that_do_not_reconcile_to_cumulative_sales_emit_no_revenue() -> None:
    payload = load().build_readback([PAGE_1], OBSERVED)  # page 2 missing
    assert payload["pagination"]["complete"] is False
    assert payload["receipt_map"]["complete"] is False
    rows = adapt(payload)
    assert not [row for row in rows if row["record_type"] == "receipt"]
    assert {row["reason"] for row in rows} == {"missing_coverage", "missing_category"}


def test_cli_writes_owner_only_file_and_skips_until_due(tmp_path: Path) -> None:
    pages = []
    for index, text in enumerate((PAGE_1, PAGE_2)):
        page = tmp_path / f"page-{index}.txt"
        page.write_text(text, encoding="utf-8")
        pages += ["--from-text", str(page)]
    output = tmp_path / "out" / "cfo-financial-readback.json"
    command = [sys.executable, str(PATH), "--output", str(output), *pages]

    written = subprocess.run(command, capture_output=True, text=True, check=True)
    summary = json.loads(written.stdout)
    assert summary["status"] == "written" and summary["complete"] is True
    assert stat.S_IMODE(os.stat(output).st_mode) == 0o600
    payload = json.loads(output.read_text(encoding="utf-8"))
    observed = datetime.fromisoformat(payload["observed_at"].replace("Z", "+00:00"))
    snapshot = observed + timedelta(minutes=5)  # the next hourly CFO pass
    rows = adapt(payload, snapshot.isoformat(), (snapshot - timedelta(days=30)).isoformat())
    assert any(row["record_type"] == "receipt" for row in rows)
    assert "buyer_a" not in output.read_text(encoding="utf-8")

    due = [sys.executable, str(PATH), "--output", str(output), "--min-interval-seconds", "3600", "--check-due"]
    assert subprocess.run(due, capture_output=True).returncode == 3


def test_cli_writes_talkroom_titles_for_the_ab_join_without_buyers(tmp_path: Path) -> None:
    page = tmp_path / "page.txt"
    page.write_text(PAGE_1, encoding="utf-8")
    output = tmp_path / "cfo-financial-readback.json"
    subprocess.run([sys.executable, str(PATH), "--output", str(output), "--from-text", str(page)],
                   capture_output=True, text=True, check=True)

    titles = output.with_name("cfo-financial-readback-titles.json")
    payload = json.loads(titles.read_text(encoding="utf-8"))
    assert payload["titles"]["18250352"] == "県提出書類作成一式"
    assert "buyer_a" not in titles.read_text(encoding="utf-8")
    assert stat.S_IMODE(os.stat(titles).st_mode) == 0o600


def test_paid_owner_refreshes_readback_before_paid_work_without_changing_its_result() -> None:
    owner = (SCRIPTS / "paid-direct-owner").read_text(encoding="utf-8")
    assert "coconala_cfo_financial_readback.py" in owner
    assert owner.index("coconala_cfo_financial_readback.py") < owner.index('exec "$ROOT/skills/browser/with-browser.sh"')
    assert "--check-due" in owner and "|| " in owner


def test_live_read_appends_settled_sales_to_the_earnings_ledger_once(tmp_path: Path, monkeypatch) -> None:
    module = load()
    collector = sys.modules["revenue_collector"]
    earnings = tmp_path / "earnings.jsonl"
    monkeypatch.setattr(collector, "EARNINGS", earnings)
    monkeypatch.setattr(module, "read_pages", lambda cdp: [PAGE_1, PAGE_2])
    output = tmp_path / "cfo-financial-readback.json"
    monkeypatch.setattr(sys, "argv", ["x", "--output", str(output), "--cdp", "http://127.0.0.1:1"])

    assert module.main() == 0
    rows = [json.loads(line) for line in earnings.read_text(encoding="utf-8").splitlines()]
    assert {row["talkroom_id"] for row in rows} == {"18250352", "18180857", "18211957", "18069473"}
    assert len(rows) == 6 and all(row["status"] == "検収完了" and row["jpy"] > 0 for row in rows)
    assert len({row["idem_key"] for row in rows}) == 6

    assert module.main() == 0
    assert len(earnings.read_text(encoding="utf-8").splitlines()) == len(rows)
