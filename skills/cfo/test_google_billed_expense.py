"""Public B7-table tests for official Google invoice-billed expenses."""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from adapters import google_cost_table as google_adapter  # noqa: E402
import loop_pnl as m  # noqa: E402


SNAPSHOT = "2026-10-01T00:00:00.000000Z"
TRAILING_START = "2026-09-01T00:00:00.000000Z"
HEADERS = (
    "請求先アカウント名", "請求先アカウント ID", "プロジェクト名", "プロジェクト ID",
    "プロジェクト階層", "サービスの説明", "サービス ID", "SKU の説明", "SKU ID",
    "消費モデルの説明", "クレジットの種類", "費用のタイプ", "使用開始日", "使用の終了日",
    "使用量", "使用量の単位", "四捨五入前の費用（¥）", "費用（¥）",
)


def google_cost_table_csv(
    *, metadata_total="110", summary_total="110", malformed_header=False,
    usage_amount="100.123456", credit_amount="-0.003456", tax_amount="11",
    tax_adjustment_amount="-1", rounding_amount="-0.12",
):
    headers = list(HEADERS)
    if malformed_header:
        headers[5] = "unexpected-service-column"

    def line(service, sku, credit, cost_type, exact, rounded):
        return [
            "PRIVATE-ACCOUNT-NAME", "PRIVATE-ACCOUNT-ID", "PRIVATE-PROJECT-NAME",
            "PRIVATE-PROJECT-ID", "", service, "service-id", sku, "sku-id", "",
            credit, cost_type, "2026-09-01", "2026-09-30", "1", "request", exact, rounded,
        ]

    rows = [
        ["請求書番号", "PRIVATE-INVOICE-ID", ""],
        ["発行日", "2026-10-01", ""],
        ["期限", "2026-10-31", ""],
        ["請求 ID", "PRIVATE-INVOICE-ID", ""],
        ["請求先アカウント ID", "PRIVATE-ACCOUNT-ID", ""],
        ["通貨", "JPY", ""],
        ["為替レート", "1", ""],
        ["合計お支払い額", metadata_total, ""],
        headers,
        line("Places API", "Places Text Search", "", "使用量", usage_amount, "100"),
        line("Places API", "Places Text Search", "SPENDING_BASED_DISCOUNT", "使用量", credit_amount, "0"),
        line("Google Cloud", "Tax", "", "税金", tax_amount, tax_amount),
        line("Google Cloud", "Tax adjustment", "", "税金", tax_adjustment_amount, tax_adjustment_amount),
        line("", "", "", "丸めエラー", rounding_amount, "0"),
        line("Google Cloud", "Invoice total", "", "合計", summary_total, summary_total),
    ]
    output = io.StringIO(newline="")
    csv.writer(output).writerows(rows)
    return output.getvalue()


class GoogleBilledExpenseTest(unittest.TestCase):
    def _table(self, directory: Path) -> dict:
        with mock.patch.dict(os.environ, {"LM_CFO_GOOGLE_BILLING_DIR": str(directory)}):
            return m._b7_table(
                date(2026, 10, 1),
                {"snapshot_at": SNAPSHOT, "trailing_start": TRAILING_START},
                snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            )

    def test_google_invoice_uses_unrounded_cost_and_reconciles_adjustments(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "2026-09-cost-table.csv").write_text(
                google_cost_table_csv(), encoding="utf-8-sig",
            )
            billing = self._table(directory).get("google_billed_expenses")

        self.assertIsInstance(billing, dict)
        invoice = billing["invoices"][0]
        self.assertEqual(billing["status"], "verified")
        self.assertEqual(invoice["invoice_period"], "2026-09")
        self.assertEqual(invoice["currency"], "JPY")
        self.assertEqual(invoice["adjustments"], {
            "usage_gross_jpy": "100.123456", "credits_jpy": "-0.003456",
            "tax_jpy": "10", "rounding_jpy": "-0.12",
        })
        self.assertEqual(invoice["billed_total_jpy"], "110")
        self.assertEqual(invoice["cash_paid_status"], "unknown")
        self.assertEqual(invoice["allocation_status"], "unattributed")

    def test_google_invoice_excludes_summary_row_from_detail_sum(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "2026-09-cost-table.csv").write_text(
                google_cost_table_csv(), encoding="utf-8-sig",
            )
            billing = self._table(directory).get("google_billed_expenses")

        self.assertIsInstance(billing, dict)
        invoice = billing["invoices"][0]
        self.assertEqual(invoice["billed_total_jpy"], "110")
        self.assertEqual(invoice["service_sku"], [{
            "service": "Places API", "sku": "Places Text Search",
            "usage_gross_jpy": "100.123456", "credits_jpy": "-0.003456",
            "net_billed_jpy": "100.12",
        }])

    def test_google_invoice_mismatch_is_unverified_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "2026-09-cost-table.csv").write_text(
                google_cost_table_csv(metadata_total="111", summary_total="111"),
                encoding="utf-8-sig",
            )
            billing = self._table(directory).get("google_billed_expenses")

        self.assertIsInstance(billing, dict)
        self.assertEqual(billing["status"], "unverified")
        self.assertIsNone(billing["invoices"][0]["billed_total_jpy"])
        self.assertEqual(billing["invoices"][0]["reason"], "invoice_total_mismatch")

    def test_google_invoice_missing_or_malformed_source_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            missing = self._table(directory).get("google_billed_expenses")
            (directory / "2026-09-cost-table.csv").write_text(
                google_cost_table_csv(malformed_header=True), encoding="utf-8-sig",
            )
            malformed = self._table(directory).get("google_billed_expenses")

        self.assertEqual(missing, {"status": "unavailable", "reason": "source_missing", "invoices": []})
        self.assertEqual(malformed["status"], "unverified")
        self.assertIsNone(malformed["invoices"][0]["billed_total_jpy"])

    def test_google_invoice_unreadable_directory_is_unknown_not_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with mock.patch.object(google_adapter.Path, "iterdir", side_effect=PermissionError("denied")):
                billing = self._table(directory).get("google_billed_expenses")

        self.assertEqual(billing, {
            "status": "unverified", "reason": "source_list_failed", "invoices": [],
        })

    def test_google_invoice_rejects_malformed_thousands_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "2026-09-cost-table.csv").write_text(
                google_cost_table_csv(metadata_total="1,10", summary_total="1,10"),
                encoding="utf-8-sig",
            )
            billing = self._table(directory).get("google_billed_expenses")

        self.assertEqual(billing["status"], "unverified")
        self.assertIsNone(billing["invoices"][0]["billed_total_jpy"])
        self.assertEqual(billing["invoices"][0]["reason"], "invoice_total_missing")

    def test_google_invoice_does_not_round_high_precision_mismatch_to_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "2026-09-cost-table.csv").write_text(
                google_cost_table_csv(
                    metadata_total="10000000010", summary_total="10000000010",
                    usage_amount="10000000000.123456789012345678",
                    credit_amount="-0.003456789012345677",
                    rounding_amount="-0.12",
                ),
                encoding="utf-8-sig",
            )
            billing = self._table(directory).get("google_billed_expenses")

        self.assertEqual(billing["status"], "unverified")
        self.assertIsNone(billing["invoices"][0]["billed_total_jpy"])
        self.assertEqual(billing["invoices"][0]["reason"], "invoice_total_mismatch")

    def test_google_invoice_preserves_high_precision_service_net(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "2026-09-cost-table.csv").write_text(
                google_cost_table_csv(
                    metadata_total="10000000010", summary_total="10000000010",
                    usage_amount="10000000000.123456789012345678",
                    credit_amount="-0.003456789012345677",
                    rounding_amount="-0.120000000000000001",
                ),
                encoding="utf-8-sig",
            )
            billing = self._table(directory).get("google_billed_expenses")

        self.assertEqual(billing["status"], "verified")
        self.assertEqual(billing["invoices"][0]["service_sku"][0]["net_billed_jpy"],
                         "10000000000.120000000000000001")

    def test_google_cost_amount_accepts_valid_grouped_yen_value(self):
        self.assertEqual(google_adapter._amount("￥1,000.123456"), Decimal("1000.123456"))

    def test_google_invoice_projection_hides_account_project_and_invoice_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "2026-09-cost-table.csv").write_text(
                google_cost_table_csv(), encoding="utf-8-sig",
            )
            billing = self._table(directory).get("google_billed_expenses")

        self.assertIsInstance(billing, dict)
        serialized = json.dumps(billing, ensure_ascii=False)
        for private_id in ("PRIVATE-ACCOUNT-NAME", "PRIVATE-ACCOUNT-ID",
                           "PRIVATE-PROJECT-NAME", "PRIVATE-PROJECT-ID", "PRIVATE-INVOICE-ID"):
            self.assertNotIn(private_id, serialized)


if __name__ == "__main__":
    unittest.main()
