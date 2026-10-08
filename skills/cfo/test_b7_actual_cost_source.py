"""B7 must distinguish an unconnected actual-cost source from a failed read."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import loop_pnl as m  # noqa: E402


SNAPSHOT = "2026-10-01T00:00:00.000000Z"
TRAILING_START = "2026-09-01T00:00:00.000000Z"


class ActualCostSourceStatusTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
