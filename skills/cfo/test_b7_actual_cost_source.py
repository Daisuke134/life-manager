"""B7 must distinguish an unconnected actual-cost source from a failed read."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import loop_pnl as m  # noqa: E402


SNAPSHOT = "2026-10-01T00:00:00.000000Z"
TRAILING_START = "2026-09-01T00:00:00.000000Z"


class ActualCostSourceStatusTest(unittest.TestCase):
    def _table(self, billing_dir: Path, actual_cost_path: str = "") -> dict:
        env = {
            "LM_CFO_ACTUAL_COST_READBACK": actual_cost_path,
            "LM_CFO_ACTUAL_COST": "",
            "LM_CFO_GOOGLE_BILLING_DIR": str(billing_dir),
        }
        projection = {"snapshot_at": SNAPSHOT, "trailing_start": TRAILING_START}
        with patch.dict(os.environ, env):
            return m._b7_table(
                date.fromisoformat("2026-10-01"), projection,
                snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            )

    def _actual_cost_gaps(self, env: dict[str, str]) -> list[dict]:
        records = m.collect_b7_records(
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
            env=env,
        )
        return [
            row for row in records
            if row.get("record_type") == "coverage"
            and row.get("source_id") == "actual-cost-readback"
        ]

    def test_unconfigured_actual_cost_source_is_unconnected(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer_db = Path(tmp) / "writer.sqlite3"
            writer_db.write_text("not a sqlite database", encoding="utf-8")
            gaps = self._actual_cost_gaps({"LM_CFO_WRITER_MONEY": str(writer_db)})

        self.assertEqual(len(gaps), 3)
        self.assertEqual({row["reason"] for row in gaps}, {"source_unconnected"})
        self.assertEqual({row["coverage_state"] for row in gaps}, {"gap"})
        self.assertEqual({row["product_loop_id"] for row in gaps}, {"cfo"})

    def test_configured_but_unreadable_actual_cost_source_is_read_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer_db = Path(tmp) / "writer.sqlite3"
            writer_db.write_text("not a sqlite database", encoding="utf-8")
            missing_payload = Path(tmp) / "official-cost-readback.json"
            gaps = self._actual_cost_gaps({
                "LM_CFO_ACTUAL_COST_READBACK": str(missing_payload),
                "LM_CFO_WRITER_MONEY": str(writer_db),
            })

        self.assertEqual(len(gaps), 3)
        self.assertEqual({row["reason"] for row in gaps}, {"read_failed"})
        self.assertEqual({row["coverage_state"] for row in gaps}, {"gap"})
        self.assertEqual({row["product_loop_id"] for row in gaps}, {"cfo"})

    def test_b7_table_keeps_billed_invoice_separate_from_settled_receipts(self):
        fixture_path = Path(__file__).parent / "fixtures/economic_attribution/actual-cost-official.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        payload["readback"]["trailing"]["window_start"] = TRAILING_START
        invoice = next(row for row in payload["documents"] if row["provider"] == "openai")
        invoice["status"] = "billed"
        invoice.pop("paid_at")
        for line in invoice["line_items"]:
            line.pop("allocations")

        with tempfile.TemporaryDirectory() as tmp:
            billing_dir = Path(tmp) / "billing"
            billing_dir.mkdir()
            readback_path = Path(tmp) / "actual-cost.json"
            readback_path.write_text(json.dumps(payload), encoding="utf-8")
            table = self._table(billing_dir, str(readback_path))

        self.assertIn("actual_billed_expenses", table)
        projection = table["actual_billed_expenses"]
        self.assertEqual(projection["status"], "verified")
        billed = next(row for row in projection["invoices"] if row["provider"] == "openai")
        self.assertEqual(billed["billed_total"], "14.34")
        self.assertEqual(billed["currency"], "USD")
        self.assertEqual(billed["cash_paid_status"], "unknown")
        self.assertEqual(billed["allocation_status"], "unattributed")

    def test_b7_table_reports_unconnected_billed_source_as_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            billing_dir = Path(tmp) / "billing"
            billing_dir.mkdir()
            table = self._table(billing_dir)

        self.assertEqual(table["actual_billed_expenses"]["status"], "unavailable")
        self.assertEqual(table["actual_billed_expenses"]["reason"], "source_unconnected")
        self.assertEqual(table["actual_billed_expenses"]["invoices"], [])


if __name__ == "__main__":
    unittest.main()
