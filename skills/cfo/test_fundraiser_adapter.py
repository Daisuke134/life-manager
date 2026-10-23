from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skills.cfo.adapters import fundraiser


class FundraiserAdapterTest(unittest.TestCase):
    def test_application_receipts_are_explicit_fundraising_coverage_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "application-receipts.jsonl"
            path.write_text(json.dumps({
                "status": "submitted_verified",
                "receipt_identity": "grant | cohort | 2026-10 | acct",
                "provider_readback": "official://application/1",
            }) + "\n")

            records = fundraiser.adapt_path(
                path,
                snapshot_at="2026-10-02T15:00:00Z",
                trailing_start="2026-09-02T15:00:00Z",
            )

        assert not [record for record in records if record["record_type"] == "receipt"]
        coverage = [record for record in records if record["record_type"] == "coverage"]
        assert len(coverage) == 3
        assert all(record["product_loop_id"] == "fundraiser" for record in coverage)
        assert all(record["reason"] == "missing_category" for record in coverage)

    def test_missing_application_receipts_fail_closed(self):
        records = fundraiser.adapt_path(
            Path("/tmp/does-not-exist-fundraiser-receipts.jsonl"),
            snapshot_at="2026-10-02T15:00:00Z",
            trailing_start="2026-09-02T15:00:00Z",
        )
        assert {record["reason"] for record in records} == {"read_failed", "missing_category"}

