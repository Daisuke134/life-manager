"""Focused contract tests for the CFO-only current RevenueCat MRR reader."""

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import loop_pnl as m  # noqa: E402
from skills.cfo.adapters import capafy_mobile  # noqa: E402

try:
    from skills.cfo import revenuecat_readback as readback  # noqa: E402
except ImportError:
    readback = None


FIX = Path(__file__).parent / "fixtures" / "economic_attribution"
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
NOW_TEXT = NOW.isoformat(timespec="microseconds").replace("+00:00", "Z")
LIVE_FLAG = "LM_CFO_MOBILE_APPS_REVENUECAT_LIVE_READBACK"
PRODUCTS = capafy_mobile.MOBILE_PRODUCT_BINDINGS
APP_IDS = {name: binding["revenuecat_app_id"] for name, binding in PRODUCTS.items()}
MRR_DEFINITION = {
    "metric": "mrr", "scope": "active_paid_subscriptions", "normalization": "monthly",
}


def canonical_sha256(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def fake_revenuecat_get(*, fail_apps=()):
    calls = []
    bodies = {}
    end_date = NOW.date().isoformat()
    prior_date = (NOW.date() - timedelta(days=1)).isoformat()
    end_epoch = int(datetime.fromisoformat(end_date + "T00:00:00+00:00").timestamp())
    prior_epoch = int(datetime.fromisoformat(prior_date + "T00:00:00+00:00").timestamp())

    def get(url, headers):
        calls.append((url, dict(headers)))
        parsed = urlparse(url)
        if parsed.path.endswith("/charts/mrr/options"):
            return {"filters": [{
                "id": "app_id",
                "options": [{"id": app_id} for app_id in APP_IDS.values()],
            }]}
        params = parse_qs(parsed.query)
        filters = json.loads(params["filters"][0])
        app_id = filters[0]["values"][0]
        if app_id in fail_apps:
            raise TimeoutError("provider fixture failure")
        value = 100 + list(APP_IDS.values()).index(app_id)
        response_start = int(datetime.fromisoformat(
            params["start_date"][0] + "T00:00:00+00:00"
        ).timestamp())
        response_end = int(datetime.fromisoformat(
            params["end_date"][0] + "T00:00:00+00:00"
        ).timestamp())
        body = {
            "start_date": response_start,
            "end_date": response_end,
            "resolution": "day",
            "yaxis_currency": "USD",
            "measures": [{"id": "MRR"}],
            "periods": [prior_epoch, end_epoch],
            "values": [
                {"measure": 0, "cohort": 0, "value": value},
                {"measure": 0, "cohort": 1, "value": 999, "incomplete": True},
            ],
        }
        bodies[app_id] = body
        return body

    return get, calls, bodies


class RevenueCatReadbackTest(unittest.TestCase):
    def require_reader(self):
        self.assertIsNotNone(readback, "CFO live RevenueCat MRR reader is missing")
        return readback

    def fetch(self, *, api_key="fixture-key", get=None):
        reader = self.require_reader()
        if get is None:
            get, _, _ = fake_revenuecat_get()
        return reader.fetch_current_mrr(
            project_id="fixture-project",
            api_key=api_key,
            product_bindings=PRODUCTS,
            get=get,
            now=lambda: NOW,
        )

    def test_reads_exactly_six_app_scoped_mrr_charts_and_hashes_the_envelopes(self):
        get, calls, bodies = fake_revenuecat_get()
        result = self.fetch(get=get)

        self.assertEqual(len(calls), 7)
        options_url, options_headers = calls[0]
        self.assertEqual(urlparse(options_url).path,
                         "/v2/projects/fixture-project/charts/mrr/options")
        self.assertEqual(options_headers, {"Authorization": "Bearer fixture-key"})
        chart_calls = calls[1:]
        observed_filters = {}
        for url, headers in chart_calls:
            parsed = urlparse(url)
            self.assertEqual(parsed.path,
                             "/v2/projects/fixture-project/charts/mrr")
            params = parse_qs(parsed.query)
            self.assertEqual(params["resolution"], ["0"])
            filters = json.loads(params["filters"][0])
            self.assertEqual(len(filters), 1)
            self.assertEqual(filters[0]["values"], [filters[0]["values"][0]])
            app_id = filters[0]["values"][0]
            self.assertEqual(filters, [{"name": "app_id", "values": [app_id]}])
            observed_filters[app_id] = filters
            self.assertEqual(headers, {"Authorization": "Bearer fixture-key"})
            self.assertNotIn("fixture-key", url)
        self.assertEqual(set(observed_filters), set(APP_IDS.values()))
        self.assertEqual(len(result["rows"]), 6)
        self.assertEqual(result["latest_observed_at"], NOW_TEXT)
        self.assertEqual(result.get("started_at"), NOW_TEXT)
        self.assertEqual(result.get("completed_at"), NOW_TEXT)

        for row in result["rows"]:
            app_id = APP_IDS[row["product_id"]]
            source = row["sources"]["revenuecat"]
            data = source["data"]
            chart = data["charts"]["mrr"]
            self.assertEqual(data["app_id"], app_id)
            self.assertEqual(data["currency"], "USD")
            self.assertEqual(data["revenue_definition"], MRR_DEFINITION)
            self.assertEqual(data["readback"]["observed_at"], NOW_TEXT)
            self.assertEqual(data["readback"]["query"]["filters"],
                             observed_filters[app_id])
            self.assertEqual(chart["evidence_sha256"], canonical_sha256(bodies[app_id]))
            self.assertEqual(source["evidence_sha256"], canonical_sha256({
                "status": "available", "reason": None, "data": data,
            }))
            self.assertEqual(row["business_date"], (NOW.date() - timedelta(days=1)).isoformat())
        self.assertNotIn("fixture-key", json.dumps(result, sort_keys=True))

        records = capafy_mobile.adapt_mobile(
            result["rows"], snapshot_at=NOW_TEXT,
            trailing_start=(NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        )
        snapshots = [row for row in records if row["record_type"] == "subscription_snapshot"]
        self.assertEqual(len(snapshots), 6)
        self.assertEqual({row["currency"] for row in snapshots}, {"USD"})
        self.assertEqual({row["normalized_monthly_amount"] for row in snapshots},
                         {str(100 + i) for i in range(6)})
        self.assertFalse(any(row.get("provider") == "revenuecat"
                             and row["record_type"] == "receipt" for row in records))

    def test_last_app_failure_retains_started_and_completed_at_after_latest_success(self):
        reader = self.require_reader()
        get, _, _ = fake_revenuecat_get(fail_apps={list(APP_IDS.values())[-1]})
        ticks = iter(range(8))
        result = reader.fetch_current_mrr(
            project_id="fixture-project", api_key="fixture-key",
            product_bindings=PRODUCTS, get=get,
            now=lambda: NOW + timedelta(seconds=next(ticks)),
        )

        stamp = lambda seconds: (NOW + timedelta(seconds=seconds)).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
        self.assertEqual(result.get("started_at"), stamp(0))
        self.assertEqual(result.get("latest_observed_at"), stamp(5))
        self.assertEqual(result.get("completed_at"), stamp(7))

    def test_all_app_failures_retain_started_and_completed_at(self):
        reader = self.require_reader()
        get, _, _ = fake_revenuecat_get(fail_apps=set(APP_IDS.values()))
        ticks = iter(range(8))
        result = reader.fetch_current_mrr(
            project_id="fixture-project", api_key="fixture-key",
            product_bindings=PRODUCTS, get=get,
            now=lambda: NOW + timedelta(seconds=next(ticks)),
        )

        stamp = lambda seconds: (NOW + timedelta(seconds=seconds)).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
        self.assertIsNone(result.get("latest_observed_at"))
        self.assertEqual(result.get("started_at"), stamp(0))
        self.assertEqual(result.get("completed_at"), stamp(7))

    def test_implicit_snapshot_uses_completed_at_and_explicit_past_stays_fixed(self):
        completed_at = (NOW + timedelta(seconds=20)).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
        latest_observed_at = (NOW + timedelta(seconds=4)).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
        readback = {
            "rows": [], "latest_observed_at": latest_observed_at,
            "started_at": NOW_TEXT, "completed_at": completed_at,
        }
        trailing = (NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z")
        with mock.patch.object(m, "_live_mobile_revenuecat_readback", return_value=readback), \
                mock.patch.object(m, "collect_b7_records", return_value=[]) as collect:
            implicit = m.build_b7_projection(
                snapshot_at=NOW_TEXT, trailing_start=trailing, env={LIVE_FLAG: "1"},
            )
            self.assertEqual(implicit["snapshot_at"], completed_at)
            expected_trailing = datetime.fromisoformat(
                trailing.replace("Z", "+00:00")
            ) + timedelta(seconds=20)
            self.assertEqual(
                implicit["trailing_start"],
                expected_trailing.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            )

            past = "2026-10-01T00:00:00Z"
            explicit = m.build_b7_projection(
                snapshot_at=past,
                trailing_start="2026-09-01T00:00:00Z",
                snapshot_at_is_explicit=True,
                env={LIVE_FLAG: "1"},
            )
            self.assertEqual(
                datetime.fromisoformat(explicit["snapshot_at"].replace("Z", "+00:00")),
                datetime.fromisoformat(past.replace("Z", "+00:00")),
            )
            self.assertEqual(collect.call_args.kwargs["snapshot_at"], past)

    def test_missing_credential_returns_six_gaps_without_provider_calls(self):
        get, calls, _ = fake_revenuecat_get()
        result = self.fetch(api_key=None, get=get)

        self.assertEqual(calls, [])
        self.assertIsNone(result["latest_observed_at"])
        self.assertEqual(result.get("started_at"), NOW_TEXT)
        self.assertEqual(result.get("completed_at"), NOW_TEXT)
        self.assertEqual(len(result["rows"]), 6)
        for row in result["rows"]:
            source = row["sources"]["revenuecat"]
            self.assertEqual(source["status"], "unavailable")
            self.assertEqual(source["reason"], "credential_missing")
            self.assertIsNone(source["data"])
            self.assertEqual(source["evidence_sha256"], canonical_sha256({
                "status": "unavailable", "reason": "credential_missing", "data": None,
            }))

    def test_provider_errors_are_gaps_and_never_fall_back_to_static_mrr(self):
        static_path = FIX / "mobile-verified.json"
        get, calls, _ = fake_revenuecat_get(fail_apps=set(APP_IDS.values()))
        live = self.fetch(get=get)
        with tempfile.TemporaryDirectory() as tmp:
            credentials = Path(tmp) / "credentials.json"
            credentials.write_text(json.dumps({"credentials": [{
                "service": "revenuecat-mobile-existing-deployment", "api_key": "fixture-key",
            }]}))
            with mock.patch.object(m, "CREDENTIALS", credentials):
                records = m.collect_b7_records(
                    snapshot_at=NOW_TEXT,
                    trailing_start=(NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
                    env={
                        LIVE_FLAG: "1",
                        "REVENUECAT_PROJECT_ID": "fixture-project",
                        "LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES": str(static_path),
                    },
                    mobile_readback=live,
                )

        self.assertEqual(len(calls), 7)
        self.assertFalse(any(row.get("record_type") == "subscription_snapshot"
                             and row.get("provider") == "revenuecat" for row in records))
        self.assertFalse(any(row.get("record_type") == "receipt"
                             and row.get("provider") == "revenuecat" for row in records))
        mrr_coverage = [row for row in records if row.get("record_type") == "coverage"
                        and row.get("source_id") == "revenuecat-mrr"]
        self.assertEqual(len(mrr_coverage), 1)
        self.assertEqual(mrr_coverage[0]["coverage_state"], "gap")

    def test_latest_incomplete_date_is_excluded_from_mrr(self):
        result = self.fetch()
        for row in result["rows"]:
            point = row["sources"]["revenuecat"]["data"]["charts"]["mrr"][
                "latest_complete"]["MRR"]
            self.assertEqual(point["period"], (NOW.date() - timedelta(days=1)).isoformat())
            self.assertIs(point["incomplete"], False)
            self.assertNotEqual(point["value"], 999)

    def test_non_boolean_incomplete_marker_is_rejected_before_helper_normalizes_it(self):
        for marker in ("true", 1):
            with self.subTest(marker=marker):
                get, _, _ = fake_revenuecat_get()

                def malformed(url, headers):
                    body = get(url, headers)
                    if urlparse(url).path.endswith("/charts/mrr"):
                        body["values"][1]["incomplete"] = marker
                    return body

                result = self.fetch(get=malformed)

                self.assertEqual(
                    {row["sources"]["revenuecat"]["reason"] for row in result["rows"]},
                    {"provider_response_invalid"},
                )

    def test_descending_periods_are_rejected_instead_of_selecting_an_older_mrr(self):
        get, _, _ = fake_revenuecat_get()

        def descending_periods(url, headers):
            body = get(url, headers)
            if urlparse(url).path.endswith("/charts/mrr"):
                body["periods"].reverse()
                body["values"][1]["incomplete"] = False
            return body

        result = self.fetch(get=descending_periods)

        self.assertEqual(
            {row["sources"]["revenuecat"]["reason"] for row in result["rows"]},
            {"provider_response_invalid"},
        )

    def test_unoffered_app_filter_becomes_a_gap_without_an_unscoped_chart_query(self):
        get, calls, _ = fake_revenuecat_get()
        missing_app = list(APP_IDS.values())[-1]

        def omit_one_app(url, headers):
            if urlparse(url).path.endswith("/charts/mrr/options"):
                options = get(url, headers)
                options["filters"][0]["options"] = [
                    item for item in options["filters"][0]["options"]
                    if item["id"] != missing_app
                ]
                return options
            return get(url, headers)

        result = self.fetch(get=omit_one_app)
        self.assertEqual(len(calls), 6)
        missing = next(row for row in result["rows"]
                       if APP_IDS[row["product_id"]] == missing_app)
        self.assertEqual(missing["sources"]["revenuecat"]["reason"], "scope_invalid")
        attempted_app_ids = {
            json.loads(parse_qs(urlparse(url).query)["filters"][0])[0]["values"][0]
            for url, _ in calls[1:]
        }
        self.assertNotIn(missing_app, attempted_app_ids)

        records = capafy_mobile.adapt_mobile(
            result["rows"], snapshot_at=NOW_TEXT,
            trailing_start=(NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        )
        self.assertFalse(any(row.get("record_type") == "subscription_snapshot"
                             and row.get("provider") == "revenuecat" for row in records))
        mrr_coverage = [row for row in records if row.get("record_type") == "coverage"
                        and row.get("source_id") == "revenuecat-mrr"]
        self.assertEqual(len(mrr_coverage), 1)
        self.assertEqual(mrr_coverage[0]["coverage_state"], "gap")

    def test_chart_response_scope_mismatch_is_a_gap(self):
        get, _, _ = fake_revenuecat_get()

        def mismatched_scope(url, headers):
            body = get(url, headers)
            if urlparse(url).path.endswith("/charts/mrr"):
                body = dict(body)
                body["start_date"] -= 86400
                body["resolution"] = "month"
            return body

        result = self.fetch(get=mismatched_scope)

        self.assertEqual(len(result["rows"]), 6)
        self.assertEqual({row["sources"]["revenuecat"]["status"]
                          for row in result["rows"]}, {"unavailable"})
        self.assertEqual({row["sources"]["revenuecat"]["reason"]
                          for row in result["rows"]}, {"scope_invalid"})

    def test_default_off_keeps_the_existing_static_mobile_mrr_path(self):
        rows = m._read_b7_payload(FIX / "mobile-verified.json")
        self.assertEqual(len(rows), 6)
        records = m.capafy_mobile.adapt_mobile(
            rows, snapshot_at="2026-10-01T00:00:00Z",
            trailing_start="2026-09-01T00:00:00Z",
        )
        snapshots = [row for row in records if row["record_type"] == "subscription_snapshot"]
        self.assertEqual(len(snapshots), 6)
        self.assertEqual({row["currency"] for row in snapshots}, {"JPY"})

    def test_default_off_collector_keeps_static_mrr_without_calling_revenuecat(self):
        helpers = self.require_reader()._business_outcomes_helpers()
        with mock.patch.object(helpers, "http_json", side_effect=AssertionError("unexpected GET")):
            records = m.collect_b7_records(
                snapshot_at="2026-10-01T00:00:00Z",
                trailing_start="2026-09-01T00:00:00Z",
                env={"LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES": str(FIX / "mobile-verified.json")},
            )

        snapshots = [row for row in records if row.get("record_type") == "subscription_snapshot"
                     and row.get("provider") == "revenuecat"]
        self.assertEqual(len(snapshots), 6)

    def test_live_flag_reads_credential_ssot_and_advances_only_implicit_snapshot(self):
        reader = self.require_reader()
        helpers = reader._business_outcomes_helpers()
        get, calls, _ = fake_revenuecat_get()
        before = datetime.now(timezone.utc)
        requested_snapshot = (before - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        requested_trailing = (before - timedelta(days=31)).isoformat().replace("+00:00", "Z")
        with tempfile.TemporaryDirectory() as tmp:
            credentials = Path(tmp) / "credentials.json"
            credentials.write_text(json.dumps({"credentials": [{
                "service": "revenuecat-mobile-existing-deployment", "api_key": "fixture-key",
            }]}))
            with mock.patch.object(m, "CREDENTIALS", credentials), \
                    mock.patch.object(helpers, "http_json", get), \
                    mock.patch.object(m, "collect_b7_records", return_value=[]) as collect:
                projection = m.build_b7_projection(
                    snapshot_at=requested_snapshot,
                    trailing_start=requested_trailing,
                    env={LIVE_FLAG: "1", "REVENUECAT_PROJECT_ID": "fixture-project"},
                )
        after = datetime.now(timezone.utc)

        projected_at = datetime.fromisoformat(projection["snapshot_at"].replace("Z", "+00:00"))
        self.assertGreaterEqual(projected_at, before)
        self.assertLessEqual(projected_at, after)
        self.assertEqual(len(calls), 7)
        self.assertEqual(collect.call_args.kwargs["snapshot_at"], projection["snapshot_at"])
        self.assertEqual(len(collect.call_args.kwargs["mobile_readback"]["rows"]), 6)

    def test_live_flag_missing_private_credential_never_queries_or_uses_static_mrr(self):
        reader = self.require_reader()
        helpers = reader._business_outcomes_helpers()
        get = mock.Mock(side_effect=AssertionError("credential missing must prevent GET"))
        with tempfile.TemporaryDirectory() as tmp:
            credentials = Path(tmp) / "credentials.json"
            credentials.write_text(json.dumps({"credentials": []}))
            with mock.patch.object(m, "CREDENTIALS", credentials), \
                    mock.patch.object(helpers, "http_json", get), \
                    mock.patch.object(m, "collect_b7_records", return_value=[]) as collect:
                m.build_b7_projection(
                    snapshot_at=NOW_TEXT,
                    trailing_start=(NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
                    env={
                        LIVE_FLAG: "1",
                        "REVENUECAT_PROJECT_ID": "fixture-project",
                        "LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES": str(FIX / "mobile-verified.json"),
                    },
                )

        get.assert_not_called()
        mobile_readback = collect.call_args.kwargs["mobile_readback"]
        self.assertIsNone(mobile_readback["latest_observed_at"])
        self.assertEqual(len(mobile_readback["rows"]), 6)
        self.assertEqual({row["sources"]["revenuecat"]["reason"]
                          for row in mobile_readback["rows"]}, {"credential_missing"})

    def test_live_mrr_remains_separate_from_asc_receipts(self):
        get, _, _ = fake_revenuecat_get()
        live = self.fetch(get=get)
        with tempfile.TemporaryDirectory() as tmp:
            credentials = Path(tmp) / "credentials.json"
            credentials.write_text(json.dumps({"credentials": [{
                "service": "revenuecat-mobile-existing-deployment", "api_key": "fixture-key",
            }]}))
            with mock.patch.object(m, "CREDENTIALS", credentials):
                records = m.collect_b7_records(
                    snapshot_at=NOW_TEXT,
                    trailing_start=(NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
                    env={
                        LIVE_FLAG: "1",
                        "REVENUECAT_PROJECT_ID": "fixture-project",
                        "LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES": str(FIX / "mobile-verified.json"),
                    },
                    mobile_readback=live,
                )

        snapshots = [row for row in records if row.get("record_type") == "subscription_snapshot"
                     and row.get("provider") == "revenuecat"]
        asc_receipts = [row for row in records if row.get("record_type") == "receipt"
                        and row.get("provider") == "app-store-connect-financial"]
        self.assertEqual(len(snapshots), 6)
        self.assertTrue(asc_receipts)
        self.assertFalse(any(row.get("provider") == "revenuecat"
                             for row in records if row.get("record_type") == "receipt"))
        self.assertEqual({row["currency"] for row in snapshots}, {"USD"})

    def test_live_mrr_is_verified_without_asc_as_of_coverage_but_keeps_financial_gaps(self):
        live = self.fetch()
        trailing = (NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z")
        records = m.collect_b7_records(
            snapshot_at=NOW_TEXT,
            trailing_start=trailing,
            env={LIVE_FLAG: "1"},
            mobile_readback=live,
        )

        asc_coverage = [row for row in records
                        if row.get("record_type") == "coverage"
                        and row.get("source_id") == "app-store-connect-financial"
                        and row.get("product_loop_id") == "mobile-apps"]
        self.assertEqual(
            {row["projection"] for row in asc_coverage}, {"historical", "trailing"},
        )
        projection = m.project_records(
            records, snapshot_at=NOW_TEXT, trailing_start=trailing,
        )
        mobile_mrr = projection["mrr"]["loops"]["mobile-apps"]
        self.assertEqual(mobile_mrr["status"], "verified")
        self.assertEqual(mobile_mrr["currencies"], {"USD": "615"})

    def test_explicit_past_snapshot_does_not_relabel_a_current_provider_read(self):
        live = self.fetch()
        past = "2026-10-01T00:00:00Z"
        records = capafy_mobile.adapt_mobile(
            live["rows"], snapshot_at=past, trailing_start="2026-09-01T00:00:00Z",
        )

        self.assertGreater(live["latest_observed_at"], past)
        self.assertFalse(any(row.get("record_type") == "subscription_snapshot"
                             and row.get("provider") == "revenuecat" for row in records))
        mrr_coverage = [row for row in records if row.get("record_type") == "coverage"
                        and row.get("source_id") == "revenuecat-mrr"]
        self.assertEqual(len(mrr_coverage), 1)
        self.assertEqual(mrr_coverage[0]["coverage_state"], "gap")


if __name__ == "__main__":
    unittest.main()
