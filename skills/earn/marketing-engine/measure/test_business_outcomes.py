from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
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
