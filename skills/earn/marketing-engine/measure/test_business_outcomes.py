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


class CloudFunnelContractTest(unittest.TestCase):
    def test_cloud_snapshot_reuses_web_report_and_preserves_unknown_cost(self):
        report = {"period": {"days": 30}, "subscription": {"grossMrrUsd": 0},
                  "costs": {"providerActualUsd": None, "netContributionUsd": None}}
        with mock.patch.object(outcomes, "collect_cloud_funnel", return_value=report) as collect:
            row = outcomes.collect_snapshot({}, "life-manager-cloud", "2026-10-11")
        collect.assert_called_once_with({})
        self.assertEqual(row["sources"]["web_funnel"]["data"], report)
        self.assertEqual(row["sources"]["web_funnel"]["status"], "available")
        self.assertNotIn("kdp", row["sources"])

    def test_cloud_report_failure_is_unavailable_not_zero_or_secret(self):
        with mock.patch.object(outcomes, "collect_cloud_funnel", side_effect=RuntimeError("secret")):
            row = outcomes.collect_snapshot({}, "life-manager-cloud", "2026-10-11")
        source = row["sources"]["web_funnel"]
        self.assertEqual(source["status"], "unavailable")
        self.assertIsNone(source["data"])
        self.assertNotIn("secret", json.dumps(row))

    def test_cloud_report_uses_existing_script_with_bounded_subprocess(self):
        report = {"period": {"days": 30}, "subscription": {"grossMrrUsd": 0}}
        with mock.patch.object(outcomes.subprocess, "run", return_value=mock.Mock(stdout=json.dumps(report))) as run:
            self.assertEqual(outcomes.collect_cloud_funnel({"STRIPE_SECRET_KEY": "test-value"}), report)
        args, kwargs = run.call_args
        self.assertEqual(args[0][0], "node")
        self.assertEqual(Path(args[0][1]), outcomes.ROOT.parents[2] / "apps/life-manager/scripts/lm-web-funnel-report.js")
        self.assertEqual(kwargs["timeout"], 120)
        self.assertTrue(kwargs["check"])
        self.assertNotIn("test-value", " ".join(args[0]))

    def test_gate_rejects_missing_cloud_readback(self):
        with mock.patch.object(outcomes, "PRODUCTS", {"life-manager-cloud": {"web_funnel": True}}):
            with self.assertRaisesRegex(ValueError, "Web funnel unavailable"):
                outcomes.verify_gate5_snapshots([{
                    "schema_version": 1, "snapshot_id": "life-manager-cloud:2026-10-11",
                    "product_id": "life-manager-cloud", "business_date": "2026-10-11",
                    "sources": {"web_funnel": outcomes.unavailable_source("provider_query_failed")},
                }], "2026-10-11")



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

    def test_collect_mrr_exports_cfo_metadata_and_utc_period_without_losing_evidence(self):
        body = {
            "yaxis_currency": "USD",
            "measures": [{"display_name": "MRR"}],
            "periods": None,
            "values": [{
                "period": 1790380800,
                "value": 20.34,
                "incomplete": False,
            }],
        }
        options = {
            "filters": [{
                "id": "app_id",
                "options": [{"id": "app-a"}],
            }],
        }
        with mock.patch.object(outcomes, "RC_CHARTS", ("mrr",)):
            with mock.patch.object(
                outcomes, "http_json", side_effect=[options, body]
            ):
                with mock.patch.object(outcomes, "revenuecat_products", return_value={}):
                    data = outcomes.collect_revenuecat(
                        {
                            "REVENUECAT_PROJECT_ID": "project-fixture",
                            "REVENUECAT_V2_SECRET_KEY": "test-token",
                        },
                        "app-a",
                        "2026-09-01",
                        "2026-09-30",
                    )

        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["revenue_definition"], {
            "metric": "mrr",
            "scope": "active_paid_subscriptions",
            "normalization": "monthly",
        })
        point = data["charts"]["mrr"]["latest_complete"]["MRR"]
        self.assertEqual(point["period"], "2026-09-26")
        self.assertEqual(point["period_index"], 1790380800)
        expected_body_hash = hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode()).hexdigest()
        self.assertEqual(data["charts"]["mrr"]["evidence_sha256"], expected_body_hash)
        iso_point = outcomes.latest_complete_chart_points({
            "measures": [{"display_name": "MRR"}],
            "periods": [{"date": "2026-09-30"}],
            "values": [{"cohort": 0, "value": 20.34, "incomplete": False}],
        }, normalize_period_utc_date=True)["MRR"]
        self.assertEqual(iso_point["period"], "2026-09-30")

    def test_cohort_only_mrr_timestamp_requires_matching_chart_range(self):
        body = {
            "start_date": 1788048000,
            "end_date": 1790380800,
            "yaxis_currency": "USD",
            "measures": [{"display_name": "MRR"}],
            "periods": None,
            "values": [{
                "cohort": 1790380800,
                "incomplete": False,
                "measure": 0,
                "value": 20.34,
            }],
        }

        point = outcomes.latest_complete_chart_points(
            body, normalize_period_utc_date=True,
        )["MRR"]
        self.assertEqual(point["period"], "2026-09-26")
        self.assertEqual(point["period_index"], 1790380800)

        unbounded = dict(body)
        unbounded.pop("start_date")
        unbounded.pop("end_date")
        unbounded_point = outcomes.latest_complete_chart_points(
            unbounded, normalize_period_utc_date=True,
        )["MRR"]
        self.assertIsNone(unbounded_point["period"])

        index_zero = dict(body)
        index_zero.update({"start_date": 0, "end_date": 86400})
        index_zero["values"] = [{
            "cohort": 0,
            "incomplete": False,
            "measure": 0,
            "value": 20.34,
        }]
        zero_point = outcomes.latest_complete_chart_points(
            index_zero, normalize_period_utc_date=True,
        )["MRR"]
        self.assertIsNone(zero_point["period"])

        out_of_range = dict(body)
        out_of_range["values"] = [{
            "cohort": 1790467200,
            "incomplete": False,
            "measure": 0,
            "value": 20.34,
        }]
        range_point = outcomes.latest_complete_chart_points(
            out_of_range, normalize_period_utc_date=True,
        )["MRR"]
        self.assertIsNone(range_point["period"])

        invalid_cohort = dict(body)
        invalid_cohort["values"] = [{
            "cohort": "invalid",
            "incomplete": False,
            "measure": 0,
            "value": 20.34,
        }]
        invalid_points = outcomes.latest_complete_chart_points(
            invalid_cohort, normalize_period_utc_date=True,
        )
        self.assertNotIn("MRR", invalid_points)

    def test_collect_mrr_does_not_default_missing_currency_or_invalid_period(self):
        body = {
            "measures": [{"display_name": "MRR"}],
            "periods": None,
            "values": [{
                "cohort": 0,
                "period": "invalid-period",
                "value": 20.34,
                "incomplete": False,
            }],
        }
        options = {
            "filters": [{
                "id": "app_id",
                "options": [{"id": "app-a"}],
            }],
        }
        with mock.patch.object(outcomes, "RC_CHARTS", ("mrr",)):
            with mock.patch.object(
                outcomes, "http_json", side_effect=[options, body]
            ):
                with mock.patch.object(outcomes, "revenuecat_products", return_value={}):
                    data = outcomes.collect_revenuecat(
                        {
                            "REVENUECAT_PROJECT_ID": "project-fixture",
                            "REVENUECAT_V2_SECRET_KEY": "test-token",
                        },
                        "app-a",
                        "2026-09-01",
                        "2026-09-30",
                    )

        self.assertIsNone(data.get("currency"))
        point = data["charts"]["mrr"]["latest_complete"]["MRR"]
        self.assertEqual(point["period"], "invalid-period")
        self.assertEqual(point["period_index"], 0)
        self.assertNotEqual(point["period"], "2026-09-30")



class ProjectScopedRevenueCatTest(unittest.TestCase):
    # A wrong project/key route or a Products 403 must not erase valid app MRR.
    ROUTES = (
        ("dhamma-quotes", "86624956", "appbe1e2ee955", "revenuecat-dhamma-existing-api-v2-ani"),
        ("thankful", "7aaf9429", "app2672aee816", "revenuecat-thankful-existing-api-v2"),
        ("sleep-reset", "77301666", "appd13f39e1cf", "revenuecat-sleep-reset-metrics-read-v2"),
    )

    def credentials(self):
        return [{"product_id": product, "project_id": project, "app_id": app,
                 "service": service, "api_key": "fixture-" + product}
                for product, project, app, service in self.ROUTES]

    def snapshot(self, product, records, get):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            path.write_text(json.dumps({"credentials": records}))
            with mock.patch.object(outcomes, "CREDENTIALS_FILE", path, create=True), \
                 mock.patch.object(outcomes, "RC_CHARTS", ("mrr",)), \
                 mock.patch.object(outcomes, "http_json", side_effect=get), \
                 mock.patch.object(outcomes, "collect_asc", return_value={"downloads": 1}), \
                 mock.patch.object(outcomes, "collect_asc_sales", return_value=({}, {})), \
                 mock.patch.object(outcomes, "collect_asc_subscriptions", return_value=({}, {})):
                return outcomes.collect_snapshot({
                    "REVENUECAT_PROJECT_ID": "wrong-global-project",
                    "REVENUECAT_V2_SECRET_KEY": "wrong-global-key",
                    "ASC_KEY_ID": "asc-fixture",
                }, product, "2026-10-23")

    def chart_get(self, route, *, products_denied=False):
        product, project, app, _ = route
        def get(url, headers):
            from urllib.parse import parse_qs, urlparse
            import urllib.error
            parsed = urlparse(url)
            self.assertEqual(headers, {"Authorization": "Bearer fixture-" + product})
            self.assertTrue(parsed.path.startswith("/v2/projects/" + project + "/"))
            self.assertNotIn("fixture-", url)
            if parsed.path.endswith("/products"):
                if products_denied:
                    raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
                return {"items": []}
            if parsed.path.endswith("/options"):
                return {"filters": [{"id": "app_id", "options": [{"id": app}]}]}
            self.assertEqual(json.loads(parse_qs(parsed.query)["filters"][0]),
                             [{"name": "app_id", "values": [app]}])
            return {"resolution": "day", "yaxis_currency": "USD",
                    "measures": [{"display_name": "MRR"}],
                    "periods": [{"date": "2026-10-23"}],
                    "values": [{"cohort": 0, "measure": 0, "value": 0, "incomplete": False}]}
        return get

    def test_three_projects_use_only_their_exact_private_credentials_and_app_filters(self):
        for route in self.ROUTES:
            with self.subTest(product=route[0]):
                row = self.snapshot(route[0], self.credentials(), self.chart_get(route))
                source = row["sources"]["revenuecat"]
                self.assertEqual(source["status"], "available")
                self.assertEqual(source["data"]["app_id"], route[2])
                self.assertEqual(source["data"]["charts"]["mrr"]["latest_complete"]["MRR"]["value"], 0)
                self.assertEqual(row["sources"]["app_store_connect"]["data"], {"downloads": 1})
                self.assertNotIn("fixture-", json.dumps(row))

    def test_missing_duplicate_and_wrong_scope_never_fall_back_to_global_key(self):
        good = self.credentials()[0]
        invalid = [[], [good, good]]
        for field in ("product_id", "project_id", "app_id", "api_key"):
            invalid.append([{**good, field: ""}])
        for records in invalid:
            with self.subTest(records=records):
                get = mock.Mock(side_effect=AssertionError("must not query with a fallback key"))
                row = self.snapshot("dhamma-quotes", records, get)
                self.assertEqual(row["sources"]["revenuecat"]["reason"], "credential_unavailable")
                self.assertIsNone(row["sources"]["revenuecat"]["data"])
                self.assertEqual(row["sources"]["app_store_connect"]["status"], "available")
                get.assert_not_called()

    def test_one_project_failure_does_not_stop_the_other_projects_or_expose_credentials(self):
        for index, route in enumerate(self.ROUTES):
            def denied(url, headers):
                raise RuntimeError("fixture-dhamma-quotes")
            row = self.snapshot(route[0], self.credentials(), denied if index == 0 else self.chart_get(route))
            self.assertEqual(row["sources"]["revenuecat"]["status"], "unavailable" if index == 0 else "available")
            self.assertEqual(row["sources"]["app_store_connect"]["status"], "available")
            self.assertNotIn("fixture-", json.dumps(row))

    def test_chart_only_key_preserves_mrr_when_optional_products_is_forbidden(self):
        route = self.ROUTES[2]
        row = self.snapshot(route[0], self.credentials(), self.chart_get(route, products_denied=True))
        source = row["sources"]["revenuecat"]
        self.assertEqual(source["status"], "available")
        self.assertEqual(source["data"]["charts"]["mrr"]["latest_complete"]["MRR"]["value"], 0)
        conversion = source["data"]["charts"]["conversion_to_paying"]
        self.assertEqual(conversion["reason"], "product_query_failed")
        self.assertIsNone(conversion["data"])


class AppStoreContractTest(unittest.TestCase):
    def test_download_summary_counts_only_rows_for_business_date(self):
        rows = [
            {"Date": "2026-10-08", "Download Type": "First-time download",
             "Source Type": "App Store search", "Counts": "1"},
            {"Date": "2026-10-09", "Download Type": "First-time download",
             "Source Type": "App Store search", "Counts": "1"},
        ]
        summary = outcomes.summarize_asc_downloads(
            rows, business_date="2026-10-09"
        )

        self.assertEqual(summary["first_time_downloads"], 1)

    def test_download_summary_is_unavailable_when_business_date_is_absent(self):
        rows = [
            {"Date": "2026-10-09", "Download Type": "First-time download",
             "Source Type": "App Store search", "Counts": "1"},
        ]

        summary = outcomes.summarize_asc_downloads(
            rows, business_date="2026-10-11"
        )

        self.assertIsNone(summary)

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

    def test_generic_report_scopes_rolling_rows_to_business_date(self):
        rows = [
            {"Date": "2026-10-08", "Event": "Impression", "Counts": "19"},
            {"Date": "2026-10-09", "Event": "Impression", "Counts": "2"},
        ]

        got = outcomes.summarize_asc_table(rows, business_date="2026-10-09")

        self.assertEqual(got["date_min"], "2026-10-09")
        self.assertEqual(got["date_max"], "2026-10-09")
        self.assertEqual(got["numeric_totals"]["Counts"], 2)
        self.assertIsNone(
            outcomes.summarize_asc_table(rows, business_date="2026-10-11")
        )

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

    def test_subscription_rows_count_through_the_parent_app_sku(self):
        # Shape of a real 1_1 Summary Sales row: an In-App Purchase carries its
        # own Apple Identifier and names the app only through Parent Identifier.
        rows = [
            {"Apple Identifier": "6755129214", "Parent Identifier": " ", "SKU": "anicca-ios-001",
             "Units": "3", "Developer Proceeds": "0.00", "Currency of Proceeds": " "},
            {"Apple Identifier": "6762000001", "Parent Identifier": "anicca-ios-001",
             "SKU": "ai.anicca.monthly", "Units": "2", "Developer Proceeds": "6.99",
             "Currency of Proceeds": "USD"},
            {"Apple Identifier": "6762133377", "Parent Identifier": "app.rork.hon-ne-honyaku-ai",
             "SKU": "com.daisuke.honne.premium.weekly", "Units": "-1",
             "Developer Proceeds": "1105.00", "Currency of Proceeds": "JPY"},
        ]
        summary = outcomes.summarize_asc_sales(rows, "6755129214")
        self.assertEqual(summary["units"], 3)
        self.assertEqual(summary["iap_units"], 2)
        self.assertEqual(summary["proceeds"], {"USD": 13.98})
        self.assertEqual(summary["row_count"], 2)

    def test_zero_proceeds_rows_add_no_currency_and_refunds_stay_negative(self):
        rows = [
            {"Apple Identifier": "6759667221", "Units": "1", "Developer Proceeds": "0.00",
             "Currency of Proceeds": "JPY"},
            {"Apple Identifier": "6759667221", "Units": "2", "Developer Proceeds": "0.00",
             "Currency of Proceeds": "USD"},
            {"Apple Identifier": "6762133377", "Parent Identifier": "app.rork.hon-ne-honyaku-ai",
             "Units": "-1", "Developer Proceeds": "1105.00", "Currency of Proceeds": "JPY"},
        ]
        summary = outcomes.summarize_asc_sales(rows, "6759667221")
        self.assertEqual(summary["proceeds"], {"JPY": -1105.0})
        self.assertEqual((summary["units"], summary["iap_units"]), (3, -1))
        self.assertEqual(outcomes.summarize_asc_sales(rows[:2], "6759667221")["proceeds"], {})

    def test_sales_report_with_no_activity_anywhere_is_a_successful_zero(self):
        summary = outcomes.summarize_asc_sales([], "6755129214")
        self.assertEqual(summary["units"], 0)
        self.assertEqual(summary["proceeds"], {})

    def test_sales_report_missing_required_column_is_rejected(self):
        rows = [{"Apple Identifier": "6755129214", "Units": "1"}]
        with self.assertRaisesRegex(ValueError, "Developer Proceeds"):
            outcomes.summarize_asc_sales(rows, "6755129214")


class VendorAppCoverageTest(unittest.TestCase):
    # Every (Apple Identifier, SKU) with rows in the vendor's Summary Sales
    # reports, 2025-11..2026-10-17 (read-only scan 2026-10-19: monthly 1_0 +
    # October daily 1_1), cross-checked with ASC GET /v1/apps.
    VENDOR_APPS_WITH_SALES_ROWS = {
        "6755129214": "anicca-ios-001",
        "6759667221": "app.rork.hon-ne-honyaku-ai",
        "6757726663": "dailydhamma",
        "6759514159": "app.rork.thankful-gratitude-app",
        "6762143790": "app.rork.vcinrjbl3ke00f07gtlzf",
        "6766485903": "app.rork.xhozd938ie79zdqd5plem",
    }

    def test_every_vendor_app_with_sales_rows_is_tracked_by_sku(self):
        tracked = {config["asc_app_id"]: config.get("asc_sku")
                   for config in outcomes.PRODUCTS.values() if "asc_app_id" in config}
        for app_id, sku in self.VENDOR_APPS_WITH_SALES_ROWS.items():
            self.assertEqual(tracked.get(app_id), sku, app_id)

    def test_sleep_reset_subscription_row_counts_for_sleep_reset(self):
        rows = [{"Apple Identifier": "6762200000", "Parent Identifier": "app.rork.vcinrjbl3ke00f07gtlzf",
                 "SKU": "sleepreset_weekly", "Units": "1", "Developer Proceeds": "45.00",
                 "Currency of Proceeds": "CZK"}]
        summary = outcomes.summarize_asc_sales(rows, outcomes.PRODUCTS["sleep-reset"]["asc_app_id"])
        self.assertEqual((summary["iap_units"], summary["proceeds"]), (1, {"CZK": 45.0}))

    def test_app_without_revenuecat_still_collects_app_store_sales(self):
        report = [{"Apple Identifier": "6766485903", "Units": "1",
                   "Developer Proceeds": "0.00", "Currency of Proceeds": " "}]
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(outcomes, "DEFAULT_EVIDENCE", Path(directory)), \
             mock.patch.object(outcomes, "collect_revenuecat") as revenuecat, \
             mock.patch.object(outcomes, "collect_asc", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "fetch_asc_sales_rows", return_value=report):
            row = outcomes.collect_snapshot({}, "studio-cherie", "2026-10-14")
        revenuecat.assert_not_called()
        self.assertEqual(row["sources"]["revenuecat"]["reason"], "no_revenuecat_app")
        self.assertEqual(row["sources"]["app_store_sales"]["status"], "available")
        self.assertEqual(row["sources"]["app_store_sales"]["data"]["units"], 1)
        self.assertNotIn("stripe", row["sources"])


class AscCollectionTest(unittest.TestCase):
    def test_one_report_with_no_instances_does_not_abort_the_others(self):
        gz_rows = gzip.compress(
            "Date\tDownload Type\tSource Type\tCounts\n"
            "2026-09-25\tFirst-time download\tApp Store search\t7\n"
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
                result = outcomes.collect_asc(
                    {}, "app-1", Path(directory), business_date="2026-09-26"
                )
                missing_day = outcomes.collect_asc(
                    {}, "app-1", Path(directory), business_date="2026-09-27"
                )

        self.assertEqual(result["reports"]["downloads"]["status"], "available")
        self.assertEqual(result["reports"]["downloads"]["data"]["first_time_downloads"], 2)
        self.assertEqual(
            missing_day["reports"]["downloads"]["status"], "unavailable"
        )
        self.assertEqual(
            missing_day["reports"]["downloads"]["reason"], "report_pending"
        )
        self.assertEqual(result["reports"]["purchases"]["status"], "unavailable")
        self.assertEqual(result["reports"]["purchases"]["reason"], "no_instances")
        # Report types not offered for this app at all are untouched by the fix.
        self.assertEqual(result["reports"]["discovery"]["status"], "unavailable")
        self.assertEqual(result["reports"]["discovery"]["reason"], "report_not_offered")


def _apple_404(detail: str) -> Exception:
    import io
    import urllib.error

    body = json.dumps({"errors": [{
        "status": "404", "code": "NOT_FOUND",
        "title": "The request expected results but none were found", "detail": detail,
    }]}).encode()
    return urllib.error.HTTPError("https://x/v1/salesReports", 404, "Not Found", {}, io.BytesIO(body))


NOT_YET = ("Report is not available yet. Daily reports for the Americas are available by "
           "5 am Pacific Time; Japan, Australia, and New Zealand by 5 am Japan Standard Time.")
NO_SALES = "There were no sales for the date specified."


class AscSubscriptionSourceTest(unittest.TestCase):
    def subscription_rows(self, count="2"):
        return [{"App Apple ID": "6755129214", "Subscription Apple ID": "sub-annual",
                 "Standard Subscription Duration": "1 Year", "Customer Price": "39.99",
                 "Customer Currency": "USD", "Active Standard Price Subscriptions": count,
                 "State": "private-dimension"}]

    def test_fetch_keeps_sales_default_and_uses_subscription_version_and_exact_date(self):
        raw = ("App Apple ID\tActive Standard Price Subscriptions\n6755129214\t2\n").encode()
        with mock.patch.object(outcomes, "_asc_headers", return_value={}), \
             mock.patch.object(outcomes, "_http_bytes", return_value=gzip.compress(raw)) as get:
            for kind, version in (("SALES", "1_1"), ("SUBSCRIPTION", "1_3")):
                kwargs = {} if kind == "SALES" else {"report_type": kind}
                rows = outcomes.fetch_asc_sales_rows(
                    {"ASC_VENDOR_NUMBER": "vendor"}, "2026-10-22", **kwargs
                )
                query = outcomes.urllib.parse.parse_qs(outcomes.urllib.parse.urlparse(get.call_args.args[0]).query)
                self.assertEqual(query, {"filter[frequency]": ["DAILY"],
                    "filter[reportDate]": ["2026-10-22"], "filter[reportSubType]": ["SUMMARY"],
                    "filter[reportType]": [kind], "filter[vendorNumber]": ["vendor"],
                    "filter[version]": [version]})
                self.assertEqual(rows[0]["Active Standard Price Subscriptions"], "2")

    def test_scopes_counts_and_raw_price_duration_to_app_with_evidence(self):
        rows = self.subscription_rows() + [dict(self.subscription_rows()[0], **{
            "Subscription Apple ID": "sub-jpy", "Customer Price": "4500",
            "Customer Currency": "JPY", "Active Standard Price Subscriptions": "3"}),
            dict(self.subscription_rows()[0], **{"App Apple ID": "other", "Active Standard Price Subscriptions": "99"})]
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(outcomes, "fetch_asc_sales_rows", return_value=rows) as fetch:
            data, evidence = outcomes.collect_asc_subscriptions({}, "6755129214", "2026-10-22", Path(directory))
            saved = json.loads(Path(data["evidence_path"]).read_text())
        fetch.assert_called_once_with({}, "2026-10-22", report_type="SUBSCRIPTION")
        self.assertEqual(data["active_standard_price_subscriptions"], 5)
        self.assertEqual(data["business_date"], "2026-10-22")
        self.assertEqual(data["app_id"], "6755129214")
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(data["rows"][0], {"subscription_id": "sub-annual",
            "standard_subscription_duration": "1 Year", "customer_price": "39.99",
            "customer_currency": "USD", "active_standard_price_subscriptions": 2})
        self.assertEqual(data["rows"][1]["customer_currency"], "JPY")
        self.assertEqual(saved, evidence)
        self.assertNotIn("private-dimension", json.dumps(saved))
        self.assertNotIn("other", json.dumps(saved))
        self.assertNotIn("mrr", json.dumps(data).lower())

    def test_explicit_zero_is_available_but_absent_app_is_not_zero(self):
        for rows, expected in ((self.subscription_rows("0"), 0), ([], None),
                               ([{"App Apple ID": "other"}], None)):
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as directory, \
                 mock.patch.object(outcomes, "fetch_asc_sales_rows", return_value=rows):
                data, evidence = outcomes.collect_asc_subscriptions({}, "6755129214", "2026-10-22", Path(directory))
                self.assertEqual(data["active_standard_price_subscriptions"] if data else None, expected)
                self.assertEqual(evidence["business_date"], "2026-10-22")

    def test_missing_blank_negative_or_fractional_count_is_invalid(self):
        for count in (None, "", " ", "-1", "1.5", "NaN", "True"):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory, \
                 mock.patch.object(outcomes, "fetch_asc_sales_rows", return_value=self.subscription_rows(count)):
                with self.assertRaises(ValueError):
                    outcomes.collect_asc_subscriptions({}, "6755129214", "2026-10-22", Path(directory))

    def test_unpublished_date_uses_previous_day_once_and_preserves_both_dates(self):
        pending = outcomes.AscSalesReportMissing("report_not_available_yet", NOT_YET)
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=[pending, self.subscription_rows()]) as fetch:
            data, evidence = outcomes.collect_asc_subscriptions({}, "6755129214", "2026-10-23", Path(directory))
            self.assertIn("2026-10-22", data["evidence_path"])
            self.assertEqual(json.loads(Path(data["evidence_path"]).read_text()), evidence)
        self.assertEqual(fetch.call_args_list, [mock.call({}, "2026-10-23", report_type="SUBSCRIPTION"),
                                              mock.call({}, "2026-10-22", report_type="SUBSCRIPTION")])
        self.assertEqual((data["requested_business_date"], data["business_date"]), ("2026-10-23", "2026-10-22"))
        self.assertEqual((evidence["requested_business_date"], evidence["business_date"]), ("2026-10-23", "2026-10-22"))
        self.assertEqual(data["active_standard_price_subscriptions"], 2)

    def test_pending_previous_day_stays_unknown_without_unbounded_retry(self):
        pending = outcomes.AscSalesReportMissing("report_not_available_yet", NOT_YET)
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=pending) as fetch:
            with self.assertRaises(outcomes.AscSalesReportMissing):
                outcomes.collect_asc_subscriptions({}, "6755129214", "2026-10-23", Path(directory))
        self.assertEqual(fetch.call_count, 2)

    def test_other_report_errors_never_fall_back_to_older_date(self):
        for reason in ("apple_no_sales_for_date", "report_not_found"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory, \
                 mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=outcomes.AscSalesReportMissing(reason, reason)) as fetch:
                with self.assertRaises(outcomes.AscSalesReportMissing):
                    outcomes.collect_asc_subscriptions({}, "6755129214", "2026-10-23", Path(directory))
                self.assertEqual(fetch.call_count, 1)

    def snapshot(self, directory, subscription_rows, *, analytics_fails=False):
        def fetch(env, date, **kwargs):
            if kwargs.get("report_type") == "SUBSCRIPTION":
                return subscription_rows
            return []
        with mock.patch.object(outcomes, "DEFAULT_EVIDENCE", Path(directory)), \
             mock.patch.object(outcomes, "collect_revenuecat", return_value={"mrr": 20.34}), \
             mock.patch.object(outcomes, "collect_asc", **({"side_effect": RuntimeError("analytics unavailable")} if analytics_fails else {"return_value": {"reports": {}}})), \
             mock.patch.object(outcomes, "collect_mixpanel", side_effect=RuntimeError("unavailable")), \
             mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=fetch):
            return outcomes.collect_snapshot({}, "anicca-ios", "2026-10-22")

    def test_subscription_success_survives_analytics_failure_and_hashes_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            row = self.snapshot(directory, self.subscription_rows(), analytics_fails=True)
            source = row["sources"]["app_store_subscriptions"]
            evidence = json.loads(Path(source["data"]["evidence_path"]).read_text())
        self.assertEqual(source["status"], "available")
        self.assertEqual(source["data"]["active_standard_price_subscriptions"], 2)
        self.assertEqual(source["evidence_sha256"], outcomes._json_hash(evidence))
        self.assertEqual(row["sources"]["app_store_connect"]["status"], "unavailable")
        self.assertEqual(row["sources"]["app_store_sales"]["status"], "available")
        self.assertEqual(row["sources"]["revenuecat"]["data"]["mrr"], 20.34)

    def test_subscription_absence_or_invalid_count_keeps_other_sources(self):
        for rows in ([], self.subscription_rows("")):
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as directory:
                row = self.snapshot(directory, rows)
                source = row["sources"]["app_store_subscriptions"]
                self.assertEqual(source["status"], "unavailable")
                self.assertIsNone(source["data"])
                self.assertEqual(row["sources"]["app_store_connect"]["status"], "available")
                self.assertEqual(row["sources"]["app_store_sales"]["status"], "available")

    def test_subscription_no_sales_404_is_not_a_measured_zero(self):
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(outcomes, "DEFAULT_EVIDENCE", Path(directory)), \
             mock.patch.object(outcomes, "collect_revenuecat", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "collect_asc", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "collect_mixpanel", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=outcomes.AscSalesReportMissing("apple_no_sales_for_date", NO_SALES)):
            row = outcomes.collect_snapshot({}, "anicca-ios", "2026-10-22")
        self.assertEqual(row["sources"]["app_store_sales"]["status"], "available")
        source = row["sources"]["app_store_subscriptions"]
        self.assertEqual(source["status"], "unavailable")
        self.assertEqual(source["reason"], "apple_no_sales_for_date")
        self.assertIsNone(source["data"])


class AscSalesAvailabilityTest(unittest.TestCase):
    """Apple answers 404 both for 'not generated yet' and 'no sales that day'."""

    def test_404_not_available_yet_is_typed_unknown_and_body_closed(self):
        error = _apple_404(NOT_YET)
        with mock.patch.object(outcomes, "_asc_headers", return_value={}), \
             mock.patch.object(outcomes, "_http_bytes", side_effect=error):
            with self.assertRaises(outcomes.AscSalesReportMissing) as caught:
                outcomes.fetch_asc_sales_rows({"ASC_VENDOR_NUMBER": "1"}, "2026-10-18")
        self.assertEqual(caught.exception.reason, "report_not_available_yet")
        self.assertTrue(error.fp.closed)

    def test_404_no_sales_is_typed_as_apple_readback(self):
        error = _apple_404(NO_SALES)
        with mock.patch.object(outcomes, "_asc_headers", return_value={}), \
             mock.patch.object(outcomes, "_http_bytes", side_effect=error):
            with self.assertRaises(outcomes.AscSalesReportMissing) as caught:
                outcomes.fetch_asc_sales_rows({"ASC_VENDOR_NUMBER": "1"}, "2026-10-12")
        self.assertEqual(caught.exception.reason, "apple_no_sales_for_date")

    def test_other_404_details_are_unknown_not_no_sales(self):
        for detail in ("The specified resource does not exist.",
                       "There were no sales reports generated due to an outage."):
            with mock.patch.object(outcomes, "_asc_headers", return_value={}), \
                 mock.patch.object(outcomes, "_http_bytes", side_effect=_apple_404(detail)):
                with self.assertRaises(outcomes.AscSalesReportMissing) as caught:
                    outcomes.fetch_asc_sales_rows({"ASC_VENDOR_NUMBER": "1"}, "2026-10-12")
            self.assertEqual(caught.exception.reason, "report_not_found", detail)

    def test_snapshot_records_apple_no_sales_as_measured_zero(self):
        missing = outcomes.AscSalesReportMissing("apple_no_sales_for_date", NO_SALES)
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(outcomes, "DEFAULT_EVIDENCE", Path(directory)), \
             mock.patch.object(outcomes, "collect_revenuecat", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "collect_asc", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "collect_mixpanel", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=missing):
            row = outcomes.collect_snapshot({}, "anicca-ios", "2026-10-12")
        sales = row["sources"]["app_store_sales"]
        self.assertEqual(sales["status"], "available")
        data = sales["data"]
        self.assertEqual((data["units"], data["iap_units"], data["proceeds"]), (0, 0, {}))
        self.assertEqual(data["evidence_reason"], "apple_no_sales_for_date")
        self.assertEqual(data["apple_detail"], NO_SALES)
        self.assertTrue(sales["evidence_sha256"])

    def test_snapshot_records_missing_report_as_unknown_not_zero(self):
        missing = outcomes.AscSalesReportMissing("report_not_available_yet", NOT_YET)
        with mock.patch.object(outcomes, "collect_revenuecat", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "collect_asc", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "collect_mixpanel", side_effect=RuntimeError("x")), \
             mock.patch.object(outcomes, "_asc_headers", return_value={}), \
             mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=missing):
            row = outcomes.collect_snapshot({}, "anicca-ios", "2026-10-18")
        sales = row["sources"]["app_store_sales"]
        self.assertEqual(sales["status"], "unavailable")
        self.assertEqual(sales["reason"], "report_not_available_yet")
        self.assertIsNone(sales["data"])

    def test_backfill_fills_latest_available_dates_into_their_own_rows(self):
        def row(date, product, sales):
            return {"schema_version": 1, "snapshot_id": f"{product}:{date}", "product_id": product,
                    "business_date": date, "observed_at": f"{date}T22:00:00+00:00",
                    "sources": {} if sales is None else {"app_store_sales": sales}}

        done = outcomes.available_source({"units": 9, "iap_units": 0, "proceeds": {}})
        legacy = outcomes.available_source({"units": 9, "proceeds": {"JPY": 0.0}})
        no_sales = outcomes.available_source({"units": 0, "iap_units": 0, "proceeds": {},
                                              "evidence_reason": "apple_no_sales_for_date"})
        rows = [
            row("2026-10-14", "anicca-ios", legacy),
            row("2026-10-15", "anicca-ios", done),
            row("2026-10-16", "anicca-ios", no_sales),
            row("2026-10-17", "anicca-ios", outcomes.unavailable_source("provider_query_failed")),
            row("2026-10-17", "ebook-en", None),
            row("2026-10-18", "anicca-ios", outcomes.unavailable_source("report_not_available_yet")),
        ]
        report = [{"Apple Identifier": "6755129214", "Units": "2",
                   "Developer Proceeds": "0.00", "Currency of Proceeds": " "}]
        calls: list[str] = []

        def fetch(env, report_date):
            calls.append(report_date)
            return report

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "business-outcomes.jsonl"
            state.write_text("".join(json.dumps(item) + "\n" for item in rows))
            with mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=fetch):
                filled = outcomes.backfill_asc_sales(
                    {}, state, "2026-10-18", evidence_root=Path(directory) / "evidence"
                )
            saved = {(item["product_id"], item["business_date"]): item
                     for item in map(json.loads, state.read_text().splitlines())}

        # A row summarized before subscription rows were attributed is re-read.
        self.assertEqual(calls, ["2026-10-17", "2026-10-14"])
        self.assertEqual(filled, ["2026-10-17", "2026-10-14"])
        self.assertEqual(saved[("anicca-ios", "2026-10-14")]["sources"]["app_store_sales"]["data"]["iap_units"], 0)
        sales = saved[("anicca-ios", "2026-10-17")]["sources"]["app_store_sales"]
        self.assertEqual(sales["status"], "available")
        self.assertEqual(sales["data"]["units"], 2)
        self.assertEqual(sales["data"]["business_date"], "2026-10-17")
        # The requested date stays unknown; definitive and finished days are untouched.
        self.assertEqual(saved[("anicca-ios", "2026-10-18")]["sources"]["app_store_sales"]["reason"],
                         "report_not_available_yet")
        self.assertEqual(saved[("anicca-ios", "2026-10-15")]["sources"]["app_store_sales"]["data"]["units"], 9)
        self.assertNotIn("app_store_sales", saved[("ebook-en", "2026-10-17")]["sources"])

    def _backfill_one(self, missing):
        row = {"schema_version": 1, "snapshot_id": "anicca-ios:2026-10-17", "product_id": "anicca-ios",
               "business_date": "2026-10-17", "observed_at": "2026-10-17T22:00:00+00:00",
               "sources": {"app_store_sales": outcomes.unavailable_source("provider_query_failed")}}
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "business-outcomes.jsonl"
            state.write_text(json.dumps(row) + "\n")
            with mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=missing):
                filled = outcomes.backfill_asc_sales(
                    {}, state, "2026-10-18", evidence_root=Path(directory)
                )
            return filled, json.loads(state.read_text())["sources"]["app_store_sales"]

    def test_backfill_never_downgrades_a_measured_row(self):
        measured = outcomes.available_source({"units": 4, "proceeds": {"JPY": 5100.0}})
        row = {"schema_version": 1, "snapshot_id": "honne-ai:2026-10-17", "product_id": "honne-ai",
               "business_date": "2026-10-17", "observed_at": "2026-10-17T22:00:00+00:00",
               "sources": {"app_store_sales": measured}}
        for failure in (outcomes.AscSalesReportMissing("report_not_found", "gone"),
                        RuntimeError("HTTP 500")):
            with tempfile.TemporaryDirectory() as directory:
                state = Path(directory) / "business-outcomes.jsonl"
                state.write_text(json.dumps(row) + "\n")
                with mock.patch.object(outcomes, "fetch_asc_sales_rows", side_effect=failure):
                    filled = outcomes.backfill_asc_sales(
                        {}, state, "2026-10-18", evidence_root=Path(directory)
                    )
                saved = json.loads(state.read_text())["sources"]["app_store_sales"]
            self.assertEqual(filled, [])
            self.assertEqual(saved, measured)

    def test_backfill_keeps_row_unknown_while_report_is_not_published(self):
        filled, sales = self._backfill_one(
            outcomes.AscSalesReportMissing("report_not_available_yet", NOT_YET)
        )
        self.assertEqual(filled, [])
        self.assertEqual((sales["status"], sales["reason"], sales["data"]),
                         ("unavailable", "report_not_available_yet", None))

    def test_backfill_records_apple_no_sales_as_final_measured_zero(self):
        filled, sales = self._backfill_one(
            outcomes.AscSalesReportMissing("apple_no_sales_for_date", NO_SALES)
        )
        self.assertEqual(filled, ["2026-10-17"])
        self.assertEqual(sales["status"], "available")
        self.assertEqual((sales["data"]["units"], sales["data"]["iap_units"], sales["data"]["proceeds"]),
                         (0, 0, {}))
        self.assertEqual(sales["data"]["evidence_reason"], "apple_no_sales_for_date")


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
            if outcomes.PRODUCTS[product].get("web_funnel"):
                sources = {"web_funnel": outcomes.available_source({
                    "period": {"days": 30},
                    "subscription": {"activeTrials": 0, "activePaidUsers": 0, "grossMrrUsd": 0},
                })}
            elif "asc_app_id" in outcomes.PRODUCTS[product]:
                config = outcomes.PRODUCTS[product]
                sources = {
                    "revenuecat": outcomes.available_source({
                        "app_id": config["revenuecat_app_id"], "charts": {}
                    }) if "revenuecat_app_id" in config
                    else outcomes.unavailable_source("no_revenuecat_app"),
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

        next(row for row in rows if row["product_id"] == "anicca-ios")["sources"]["app_store_connect"]["data"]["reports"]["downloads"]["data"]["installs"] = 9
        with self.assertRaisesRegex(ValueError, "ambiguous installs"):
            outcomes.verify_gate5_snapshots(rows, "2026-07-30")


if __name__ == "__main__":
    unittest.main()
