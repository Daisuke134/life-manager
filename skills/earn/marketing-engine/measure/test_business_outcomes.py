from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import datetime as dt
import contextlib
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("business_outcomes.py")
SPEC = importlib.util.spec_from_file_location("business_outcomes", MODULE_PATH)
assert SPEC and SPEC.loader
outcomes = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = outcomes
SPEC.loader.exec_module(outcomes)


class RevenueCatContractTest(unittest.TestCase):
    def test_managed_loop_storage_is_outside_the_immutable_release(self):
        state, evidence = outcomes.default_storage_paths({
            "LIFE_MANAGER_STATE_ROOT": "/tmp/marketing-metrics-daily",
        })
        self.assertEqual(
            state,
            Path("/tmp/marketing-metrics-daily/state/business-outcomes.jsonl"),
        )
        self.assertEqual(
            evidence,
            Path("/tmp/marketing-metrics-daily/evidence/business"),
        )

    def test_realtime_app_filter_uses_verified_app_id_option(self):
        options = {
            "filters": [{
                "id": "app_id",
                "options": [{"id": "app-a"}, {"id": "app-b"}],
            }]
        }
        self.assertEqual(
            outcomes.revenuecat_app_filter(options, "app-b"),
            [{"name": "app_id", "values": ["app-b"]}],
        )

    def test_legacy_schema_uses_app_config_id_only_when_discovered(self):
        options = {
            "filters": [{
                "id": "app_config_id",
                "options": [{"id": "app-a"}],
            }]
        }
        self.assertEqual(
            outcomes.revenuecat_app_filter(options, "app-a"),
            [{"name": "app_config_id", "values": ["app-a"]}],
        )

    def test_unknown_app_or_dimension_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "not offered"):
            outcomes.revenuecat_app_filter({"filters": []}, "app-a")
        with self.assertRaisesRegex(ValueError, "not listed"):
            outcomes.revenuecat_app_filter(
                {"filters": [{"id": "app_id", "options": []}]}, "app-a"
            )

    def test_latest_complete_point_skips_incomplete_final_period(self):
        body = {
            "measures": [{"id": "mrr", "display_name": "MRR"}],
            "periods": [{"date": "2026-07-30"}, {"date": "2026-07-31"}],
            "values": [
                {"cohort": 0, "measure": 0, "value": 20.73, "incomplete": False},
                {"cohort": 1, "measure": 0, "value": 99.0, "incomplete": True},
            ],
        }
        point = outcomes.latest_complete_chart_points(body)["mrr"]
        self.assertEqual(point["value"], 20.73)
        self.assertEqual(point["period"], "2026-07-30")
        self.assertFalse(point["incomplete"])

    def test_zero_is_a_real_complete_value(self):
        body = {
            "measures": [{"id": "active_subscriptions"}],
            "periods": [{"date": "2026-07-30"}],
            "values": [{"cohort": 0, "measure": 0, "value": 0, "incomplete": False}],
        }
        self.assertEqual(
            outcomes.latest_complete_chart_points(body)["active_subscriptions"]["value"],
            0,
        )

    def test_window_sum_adds_every_complete_daily_point_for_one_measure(self):
        body = {
            "measures": [{"display_name": "Revenue"}],
            "values": [
                {"cohort": 0, "measure": 0, "value": 10.0, "incomplete": False},
                {"cohort": 1, "measure": 0, "value": 15.0, "incomplete": False},
                {"cohort": 2, "measure": 0, "value": 99.0, "incomplete": True},
            ],
        }
        self.assertEqual(outcomes.sum_complete_chart_points(body, "Revenue"), 25.0)

    def test_window_sum_is_none_when_the_measure_has_no_complete_point(self):
        body = {"measures": [{"display_name": "Revenue"}], "values": []}
        self.assertIsNone(outcomes.sum_complete_chart_points(body, "Revenue"))


class AppStoreContractTest(unittest.TestCase):
    def test_apple_finance_month_selector_matches_verified_fiscal_periods(self):
        month_for_day = getattr(outcomes, "latest_completed_apple_finance_month", lambda _day: None)
        period_dates = getattr(outcomes, "apple_finance_period_dates", lambda _month: None)
        self.assertEqual(month_for_day(dt.date(2026, 10, 2)), "2026-12")
        self.assertEqual(period_dates("2026-12"), ("2026-08-30", "2026-09-26"))
        self.assertEqual(period_dates("2026-10"), ("2026-06-28", "2026-08-01"))

    def test_download_types_are_never_collapsed_into_installs(self):
        raw = (
            "Date\tDownload Type\tSource Type\tCounts\n"
            "2026-07-30\tFirst-time download\tApp Store Search\t3\n"
            "2026-07-30\tRedownload\tApp Store Search\t7\n"
            "2026-07-30\tAuto-update\tApp Store Search\t11\n"
        ).encode()
        parsed = outcomes.parse_asc_tsv_gz(gzip.compress(raw))
        summary = outcomes.summarize_asc_downloads(parsed)
        self.assertEqual(summary["first_time_downloads"], 3)
        self.assertEqual(summary["redownloads"], 7)
        self.assertEqual(summary["auto_updates"], 11)
        self.assertNotIn("installs", summary)

    def test_missing_required_download_column_is_rejected(self):
        raw = "Date\tDownload Type\tCounts\n2026-07-30\tFirst-time download\t3\n"
        rows = outcomes.parse_asc_tsv_gz(gzip.compress(raw.encode()))
        with self.assertRaisesRegex(ValueError, "Source Type"):
            outcomes.summarize_asc_downloads(rows)

    def test_latest_instance_uses_processing_date_not_response_order(self):
        instances = [
            {"id": "old", "attributes": {
                "processingDate": "2026-07-29", "granularity": "DAILY"
            }},
            {"id": "new", "attributes": {
                "processingDate": "2026-07-31", "granularity": "DAILY"
            }},
        ]
        self.assertEqual(outcomes._latest_asc_instance(instances)["id"], "new")

    def test_generic_report_keeps_schema_dates_and_numeric_totals(self):
        rows = [
            {"Date": "2026-07-29", "Event": "Impression", "Counts": "3"},
            {"Date": "2026-07-30", "Event": "Tap", "Counts": "2"},
        ]
        got = outcomes.summarize_asc_table(rows)
        self.assertEqual(got["row_count"], 2)
        self.assertEqual(got["date_min"], "2026-07-29")
        self.assertEqual(got["date_max"], "2026-07-30")
        self.assertEqual(got["numeric_totals"]["Counts"], 5)

    def test_finance_detail_parser_skips_vendor_preamble_and_preserves_raw_row(self):
        raw = (
            "Vendor Name\tPrivate Seller\n"
            "Start Date\t08/30/2026\n"
            "End Date\t09/26/2026\n"
            "Transaction Date\tSettlement Date\tApple Identifier\tSKU\tTitle\tDeveloper Name\t"
            "Product Type Identifier\tCountry of Sale\tQuantity\tPartner Share\t"
            "Extended Partner Share\tPartner Share Currency\tCustomer Price\tCustomer Currency\t"
            "Sale or Return\tPromo Code\tOrder Type\tRegion\n"
            "09/12/2026\t09/12/2026\t6762049696\tai.anicca.app.ios.yearly.b\t"
            "Anicca Annual\tExample Seller\tIAY\tJPN\t1\t4250\t4250\tJPY\t5500\tJPY\tS\t\t\tZ1\n"
            "Country Of Sale\tPartner Share Currency\tQuantity\tExtended Partner Share\n"
            "JP\tJPY\t1\t4250.00\n"
        ).encode()
        parse = getattr(outcomes, "parse_asc_finance_detail_tsv", lambda _raw: {})
        report = parse(raw)
        self.assertEqual(
            (report.get("period_start"), report.get("period_end")),
            ("2026-08-30", "2026-09-26"),
        )
        rows = report.get("rows", [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_row_index"], 0)
        self.assertEqual(rows[0]["raw"]["Apple Identifier"], "6762049696")
        self.assertEqual(rows[0]["raw"]["SKU"], "ai.anicca.app.ios.yearly.b")
        self.assertEqual(rows[0]["raw"]["Extended Partner Share"], "4250")
        self.assertEqual(rows[0]["raw"]["Partner Share Currency"], "JPY")
        self.assertNotIn("Private Seller", json.dumps(report))

    def test_finance_detail_maps_exact_subscription_and_iap_ids_and_keeps_unmatched_rows(self):
        raw_rows = [
            {"source_row_index": 0, "raw": {
                "Apple Identifier": "6762049696", "SKU": "ai.anicca.app.ios.yearly.b",
                "Transaction Date": "09/12/2026", "Settlement Date": "09/12/2026",
                "Extended Partner Share": "4250", "Partner Share Currency": "JPY",
                "Sale or Return": "S", "Product Type Identifier": "IAY",
            }},
            {"source_row_index": 1, "raw": {
                "Apple Identifier": "1234567890", "SKU": "ai.anicca.app.ios.lifetime",
                "Transaction Date": "09/13/2026", "Settlement Date": "09/13/2026",
                "Extended Partner Share": "1000", "Partner Share Currency": "JPY",
                "Sale or Return": "S", "Product Type Identifier": "1",
            }},
            {"source_row_index": 2, "raw": {
                "Apple Identifier": "6762049696", "SKU": "ai.anicca.app.ios.wrong",
                "Transaction Date": "09/14/2026", "Settlement Date": "09/14/2026",
                "Extended Partner Share": "3000", "Partner Share Currency": "JPY",
                "Sale or Return": "S", "Product Type Identifier": "IAY",
            }},
        ]
        catalog = [
            {"app_id": "6755129214", "record_type": "subscription",
             "record_id": "6762049696", "sku": "ai.anicca.app.ios.yearly.b",
             "name": "Anicca Annual", "state": "APPROVED"},
            {"app_id": "6755129214", "record_type": "in_app_purchase",
             "record_id": "1234567890", "sku": "ai.anicca.app.ios.lifetime",
             "name": "Lifetime", "state": "APPROVED"},
        ]
        normalize = getattr(
            outcomes, "normalize_asc_finance_rows",
            lambda _rows, _catalog: {"by_product": {}, "unassigned_rows": []},
        )
        result = normalize(raw_rows, catalog)
        mapped = result["by_product"].get("anicca-ios", [])
        self.assertEqual(len(mapped), 2)
        self.assertEqual(
            [(row["apple_identifier"], row["sku"], row["parent_app_id"],
              row["catalog_record_type"], row["extended_partner_share"])
             for row in mapped],
            [
                ("6762049696", "ai.anicca.app.ios.yearly.b", "6755129214", "subscription", "4250"),
                ("1234567890", "ai.anicca.app.ios.lifetime", "6755129214", "in_app_purchase", "1000"),
            ],
        )
        self.assertEqual(result["unassigned_rows"][0]["source_row_index"], 2)
        self.assertEqual(result["unassigned_rows"][0]["reason"], "catalog_no_exact_match")

    def test_finance_source_collector_binds_raw_report_hash_and_exact_catalog_evidence(self):
        raw = (
            "Vendor Name\tPrivate Seller\n"
            "Start Date\t08/30/2026\n"
            "End Date\t09/26/2026\n"
            "Transaction Date\tSettlement Date\tApple Identifier\tSKU\tTitle\tDeveloper Name\t"
            "Product Type Identifier\tCountry of Sale\tQuantity\tPartner Share\t"
            "Extended Partner Share\tPartner Share Currency\tCustomer Price\tCustomer Currency\t"
            "Sale or Return\tPromo Code\tOrder Type\tRegion\n"
            "09/12/2026\t09/12/2026\t6762049696\tai.anicca.app.ios.yearly.b\t"
            "Anicca Annual\tExample Seller\tIAY\tJPN\t1\t4250\t4250\tJPY\t5500\tJPY\tS\t\t\tZ1\n"
        ).encode()
        calls = []

        def fake_asc(env, args, *, timeout=120):
            calls.append(args)
            if args[:2] == ["finance", "reports"]:
                output_path = Path(args[args.index("--output") + 1])
                output_path.write_bytes(raw)
                return {
                    "vendorNumber": "93486075", "reportType": "FINANCE_DETAIL",
                    "regionCode": "Z1", "reportDate": "2026-12",
                    "filePath": str(output_path), "fileSize": len(raw),
                    "decompressedSize": len(raw),
                }
            if args[:2] == ["subscriptions", "list"]:
                return {"data": [{"id": "6762049696", "attributes": {
                    "name": "Anicca Annual", "productId": "ai.anicca.app.ios.yearly.b",
                    "state": "APPROVED",
                }}]}
            if args[:2] == ["iap", "list"]:
                return {"data": []}
            raise AssertionError(f"unexpected ASC command: {args[:2]}")

        collector = getattr(outcomes, "collect_asc_financial_sources", None)
        self.assertTrue(callable(collector), "scheduled business-outcomes source collector is missing")
        with tempfile.TemporaryDirectory() as directory:
            evidence_root = Path(directory) / "evidence"
            sources = collector(
                {"ASC_VENDOR_NUMBER": "93486075"}, "2026-12", ["anicca-ios"],
                evidence_root, run_command=fake_asc,
            )
            source = sources["anicca-ios"]
            data = source["data"]
            evidence_files = list(evidence_root.rglob("*"))

        self.assertEqual(source["status"], "available")
        self.assertEqual(data["app_id"], "6755129214")
        self.assertEqual(data["report_id"], "finance-2026-12-Z1")
        self.assertEqual(data["period_start"], "2026-08-30")
        self.assertEqual(data["period_end"], "2026-09-26")
        self.assertEqual(data["report_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(data["report_sha256"], data["content_sha256"])
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(data["rows"][0]["apple_identifier"], "6762049696")
        self.assertEqual(data["rows"][0]["parent_app_id"], "6755129214")
        self.assertEqual(data["rows"][0]["extended_partner_share"], "4250")
        self.assertEqual(data["unassigned_row_count"], 0)
        self.assertTrue(data["report_evidence_ref"].startswith("appstoreconnect://financial-reports/"))
        self.assertTrue(data["unassigned_evidence_ref"].startswith("appstoreconnect://financial-report-mappings/"))
        self.assertTrue(any(path.suffix in {".tsv", ".json"} for path in evidence_files))
        self.assertTrue(any(args[:2] == ["subscriptions", "list"] for args in calls))

    def test_finance_report_no_sales_is_unavailable_not_a_fabricated_zero(self):
        collector = getattr(outcomes, "collect_asc_financial_sources", None)
        self.assertTrue(callable(collector), "scheduled business-outcomes source collector is missing")

        def no_sales(_env, args, *, timeout=120):
            raise RuntimeError("finance_report_no_sales")

        with tempfile.TemporaryDirectory() as directory:
            sources = collector(
                {"ASC_VENDOR_NUMBER": "93486075"}, "2026-11", ["anicca-ios"],
                Path(directory) / "evidence", run_command=no_sales,
            )
        self.assertEqual(sources["anicca-ios"]["status"], "unavailable")
        self.assertEqual(sources["anicca-ios"]["reason"], "finance_report_no_sales")
        self.assertIsNone(sources["anicca-ios"]["data"])

    def test_sales_report_multiplies_units_by_per_unit_proceeds(self):
        rows = [
            {"Apple Identifier": "6755129214", "Units": "3",
             "Developer Proceeds": "0.70", "Currency of Proceeds": "USD"},
            {"Apple Identifier": "6755129214", "Units": "1",
             "Developer Proceeds": "1.40", "Currency of Proceeds": "USD"},
            {"Apple Identifier": "6759667221", "Units": "5",
             "Developer Proceeds": "0.70", "Currency of Proceeds": "USD"},
        ]
        summary = outcomes.summarize_asc_sales(rows, "6755129214")
        self.assertEqual(summary["units"], 4)
        self.assertEqual(summary["proceeds"], {"USD": 3.5})
        self.assertEqual(summary["row_count"], 2)

    def test_sales_report_with_no_activity_anywhere_is_a_successful_zero(self):
        summary = outcomes.summarize_asc_sales([], "6755129214")
        self.assertEqual(summary["units"], 0)
        self.assertEqual(summary["proceeds"], {})

    def test_sales_report_missing_required_column_is_rejected(self):
        rows = [{"Apple Identifier": "6755129214", "Units": "1"}]
        with self.assertRaisesRegex(ValueError, "Developer Proceeds"):
            outcomes.summarize_asc_sales(rows, "6755129214")


class AscCollectionTest(unittest.TestCase):
    def test_one_report_with_no_instances_does_not_abort_the_others(self):
        gz_rows = gzip.compress(
            "Date\tDownload Type\tSource Type\tCounts\n"
            "2026-09-26\tFirst-time download\tApp Store search\t2\n".encode()
        )
        checksum = hashlib.md5(gz_rows).hexdigest()

        def fake_get(path_or_url, headers):
            if path_or_url.endswith("/analyticsReportRequests?limit=200"):
                return {"data": [{
                    "id": "req1",
                    "attributes": {"accessType": "ONGOING", "stoppedDueToInactivity": False},
                }]}
            if path_or_url.endswith("/analyticsReportRequests/req1/reports?limit=200"):
                return {"data": [
                    {"id": "rep-downloads", "attributes": {"name": "App Downloads Standard"}},
                    {"id": "rep-purchases", "attributes": {"name": "App Store Purchases Standard"}},
                ]}
            if path_or_url == "/analyticsReports/rep-downloads/instances?limit=200":
                return {"data": [{
                    "id": "inst1",
                    "attributes": {"processingDate": "2026-09-26", "granularity": "DAILY"},
                }]}
            if path_or_url == "/analyticsReports/rep-purchases/instances?limit=200":
                return {"data": []}
            if path_or_url == "/analyticsReportInstances/inst1/segments?limit=200":
                return {"data": [{
                    "id": "seg1",
                    "attributes": {"url": "https://x/seg1", "sizeInBytes": len(gz_rows), "checksum": checksum},
                }]}
            raise AssertionError(f"unexpected path: {path_or_url}")

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(outcomes, "_asc_headers", return_value={}), \
                 mock.patch.object(outcomes, "_asc_get", side_effect=fake_get), \
                 mock.patch.object(outcomes, "_http_bytes", return_value=gz_rows):
                result = outcomes.collect_asc({}, "app-1", Path(directory))

        self.assertEqual(result["reports"]["downloads"]["status"], "available")
        self.assertEqual(result["reports"]["downloads"]["data"]["first_time_downloads"], 2)
        self.assertEqual(result["reports"]["purchases"]["status"], "unavailable")
        self.assertEqual(result["reports"]["purchases"]["reason"], "no_instances")
        # Report types not offered for this app at all are untouched by the fix.
        self.assertEqual(result["reports"]["discovery"]["status"], "unavailable")
        self.assertEqual(result["reports"]["discovery"]["reason"], "report_not_offered")


class StripeContractTest(unittest.TestCase):
    def test_query_window_is_bounded_to_one_business_day(self):
        query = outcomes.stripe_session_query(1000, 2000)
        self.assertIn("created%5Bgte%5D=1000", query)
        self.assertIn("created%5Blt%5D=2000", query)
        self.assertIn("data.line_items", query)
        self.assertIn("data.payment_intent.latest_charge", query)

    def test_only_exact_product_allowlist_is_counted(self):
        sessions = [
            {
                "id": "cs_keep",
                "payment_status": "paid",
                "currency": "usd",
                "amount_total": 1099,
                "line_items": {"data": [{"price": {"product": "prod-en"}}]},
                "payment_intent": {"latest_charge": {"amount_refunded": 200}},
            },
            {
                "id": "cs_other",
                "payment_status": "paid",
                "currency": "usd",
                "amount_total": 99999,
                "line_items": {"data": [{"price": {"product": "prod-other"}}]},
            },
            {
                "id": "cs_unpaid",
                "payment_status": "unpaid",
                "currency": "usd",
                "amount_total": 1099,
                "line_items": {"data": [{"price": {"product": "prod-en"}}]},
            },
        ]
        got = outcomes.summarize_stripe_sessions(sessions, {"prod-en"})
        self.assertEqual(got["paid_orders"], 1)
        self.assertEqual(got["gross_minor"], {"usd": 1099})
        self.assertEqual(got["refunded_minor"], {"usd": 200})
        self.assertEqual(got["net_minor"], {"usd": 899})
        self.assertEqual(got["queried_product_ids"], ["prod-en"])
        self.assertEqual(got["matched_session_ids"], ["cs_keep"])

    def test_duplicate_checkout_session_is_rejected(self):
        session = {
            "id": "cs_dup",
            "payment_status": "paid",
            "currency": "jpy",
            "amount_total": 1580,
            "line_items": {"data": [{"price": {"product": "prod-ja"}}]},
        }
        with self.assertRaisesRegex(ValueError, "duplicate Stripe session"):
            outcomes.summarize_stripe_sessions([session, dict(session)], {"prod-ja"})


class AnalyticsAndSnapshotContractTest(unittest.TestCase):
    def test_mixpanel_counts_events_without_storing_people(self):
        lines = [
            json.dumps({"event": "Onboarding Started", "properties": {"distinct_id": "secret"}}),
            json.dumps({"event": "Onboarding Started", "properties": {"email": "x@y.test"}}),
            json.dumps({"event": "Purchase Completed", "properties": {"amount": 9.99}}),
        ]
        self.assertEqual(
            outcomes.summarize_mixpanel_export(lines),
            {"Onboarding Started": 2, "Purchase Completed": 1},
        )

    def test_unavailable_is_null_not_zero(self):
        source = outcomes.unavailable_source("missing_read_credential")
        self.assertEqual(source["status"], "unavailable")
        self.assertIsNone(source["data"])
        self.assertEqual(source["reason"], "missing_read_credential")

    def test_snapshot_validation_rejects_product_mismatch_and_duplicate(self):
        row = {
            "schema_version": 1,
            "snapshot_id": "anicca-ios:2026-07-30",
            "product_id": "anicca-ios",
            "business_date": "2026-07-30",
            "sources": {"revenuecat": outcomes.unavailable_source("fixture")},
        }
        outcomes.validate_snapshots([row], {"anicca-ios"})
        with self.assertRaisesRegex(ValueError, "unknown product"):
            outcomes.validate_snapshots([{**row, "product_id": "other"}], {"anicca-ios"})
        with self.assertRaisesRegex(ValueError, "duplicate snapshot"):
            outcomes.validate_snapshots([row, dict(row)], {"anicca-ios"})

    def test_upsert_migrates_legacy_snapshot_identity_without_duplication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "business-outcomes.jsonl"
            legacy = {
                "schema_version": 1,
                "snapshot_id": "aniccaios:2026-07-30",
                "product_id": "aniccaios",
                "business_date": "2026-07-30",
                "sources": {"revenuecat": outcomes.unavailable_source("fixture")},
            }
            current = {
                **legacy,
                "snapshot_id": "anicca-ios:2026-07-30",
                "product_id": "anicca-ios",
            }
            path.write_text(json.dumps(legacy) + "\n")
            self.assertEqual(outcomes.upsert_snapshots(path, [current]), 0)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(rows, [current])

    def test_metrics_main_attaches_finance_source_and_replays_without_duplicate_snapshot(self):
        env = {"ASC_FINANCE_REPORT_DATE": "2026-12"}
        finance_source = {
            "status": "available", "reason": None, "evidence_sha256": "a" * 64,
            "data": {"report_id": "finance-2026-12-Z1", "report_status": "final"},
        }
        snapshot = {
            "schema_version": 1, "snapshot_id": "anicca-ios:2026-10-02",
            "product_id": "anicca-ios", "business_date": "2026-10-02",
            "observed_at": "2026-10-03T00:00:00Z",
            "sources": {"revenuecat": {"status": "available", "data": {"fixture": True}}},
        }
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "business-outcomes.jsonl"

            def run_main():
                stdout = io.StringIO()
                with mock.patch.object(outcomes, "load_env", return_value=env), \
                     mock.patch.object(outcomes, "collect_snapshot", return_value=snapshot), \
                     mock.patch.object(
                         outcomes, "collect_asc_financial_sources",
                         return_value={"anicca-ios": finance_source}, create=True,
                     ), \
                     mock.patch.object(sys, "argv", [
                         "business_outcomes.py", "--date", "2026-10-02", "--state", str(state),
                         "--products", "anicca-ios",
                     ]), \
                     contextlib.redirect_stdout(stdout):
                    exit_code = outcomes.main()
                return exit_code, json.loads(stdout.getvalue())

            first_code, first = run_main()
            replay_code, replay = run_main()
            rows = [json.loads(line) for line in state.read_text().splitlines()]

        self.assertEqual(first_code, 0)
        self.assertEqual(first["added"], 1)
        self.assertEqual(replay_code, 0)
        self.assertEqual(replay["added"], 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sources"].get("app_store_financial"), finance_source)

    def test_metrics_main_uses_loaded_state_root_for_state_and_finance_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            captured = {}
            env = {
                "LIFE_MANAGER_STATE_ROOT": str(root),
                "ASC_FINANCE_REPORT_DATE": "2026-12",
            }
            snapshot = {
                "schema_version": 1, "snapshot_id": "anicca-ios:2026-10-02",
                "product_id": "anicca-ios", "business_date": "2026-10-02",
                "observed_at": "2026-10-03T00:00:00Z",
                "sources": {"revenuecat": {"status": "available", "data": {"fixture": True}}},
            }
            finance_source = {
                "status": "available", "reason": None,
                "data": {"report_id": "finance-2026-12-Z1"},
            }

            def fake_finance(_env, _month, _products, evidence_root):
                captured["evidence_root"] = Path(evidence_root)
                return {"anicca-ios": finance_source}

            def fake_upsert(state_path, _rows):
                captured["state_path"] = Path(state_path)
                return 0

            stdout = io.StringIO()
            with mock.patch.object(outcomes, "load_env", return_value=env), \
                 mock.patch.object(outcomes, "collect_snapshot", return_value=snapshot), \
                 mock.patch.object(outcomes, "collect_asc_financial_sources", side_effect=fake_finance), \
                 mock.patch.object(outcomes, "upsert_snapshots", side_effect=fake_upsert), \
                 mock.patch.object(sys, "argv", [
                     "business_outcomes.py", "--date", "2026-10-02", "--products", "anicca-ios",
                 ]), \
                 contextlib.redirect_stdout(stdout):
                self.assertEqual(outcomes.main(), 0)

        self.assertEqual(captured["state_path"], root / "state/business-outcomes.jsonl")
        self.assertEqual(captured["evidence_root"], root / "evidence/business")

    def test_gate5_verifier_requires_every_scoped_product_and_no_fake_installs(self):
        rows = []
        for product in outcomes.PRODUCTS:
            sources = {}
            if "revenuecat_app_id" in outcomes.PRODUCTS[product]:
                config = outcomes.PRODUCTS[product]
                sources = {
                    "revenuecat": outcomes.available_source({
                        "app_id": config["revenuecat_app_id"], "charts": {}
                    }),
                    "app_store_connect": outcomes.available_source({
                        "app_id": config["asc_app_id"],
                        "reports": {"downloads": outcomes.available_source({
                            "first_time_downloads": 0,
                            "redownloads": 0,
                            "auto_updates": 0,
                            "manual_updates": 0,
                            "restores": 0,
                        })},
                    }),
                }
            else:
                sources = {"stripe": outcomes.available_source({
                    "queried_product_ids": outcomes.PRODUCTS[product]["stripe_product_ids"],
                    "paid_orders": 0,
                    "gross_minor": {},
                    "refunded_minor": {},
                    "net_minor": {},
                    "matched_session_ids": [],
                })}
            rows.append({
                "schema_version": 1,
                "snapshot_id": f"{product}:2026-07-30",
                "product_id": product,
                "business_date": "2026-07-30",
                "sources": sources,
            })
        report = outcomes.verify_gate5_snapshots(rows, "2026-07-30")
        self.assertTrue(report["gate_pass"])
        self.assertEqual(report["products_verified"], len(outcomes.PRODUCTS))

        rows[0]["sources"]["app_store_connect"]["data"]["reports"]["downloads"]["data"]["installs"] = 9
        with self.assertRaisesRegex(ValueError, "ambiguous installs"):
            outcomes.verify_gate5_snapshots(rows, "2026-07-30")


if __name__ == "__main__":
    unittest.main()
