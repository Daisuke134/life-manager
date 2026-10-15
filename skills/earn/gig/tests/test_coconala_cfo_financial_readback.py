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
    gaps = [row for row in rows if row["record_type"] == "coverage"]
    # The page shows credited sales only (no itemized fee/refund), so coverage stays a gap.
    assert {row["reason"] for row in gaps} == {"missing_coverage", "missing_category"}
    assert all(row["coverage_state"] == "gap" for row in gaps)


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


def test_paid_owner_refreshes_readback_before_paid_work_without_changing_its_result() -> None:
    owner = (SCRIPTS / "paid-direct-owner").read_text(encoding="utf-8")
    assert "coconala_cfo_financial_readback.py" in owner
    assert owner.index("coconala_cfo_financial_readback.py") < owner.index('exec "$ROOT/skills/browser/with-browser.sh"')
    assert "--check-due" in owner and "|| " in owner
