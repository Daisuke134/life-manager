"""Current public portfolio contracts; synthetic provider responses, no live credentials."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
import loop_pnl
from skills.cfo import economic_attribution, revenuecat_readback
from skills.cfo.adapters import capafy_mobile

# Literal, provider-verified app scope. Studio has no RevenueCat app.
PUBLIC = {
    "anicca-ios": ("6755129214", "app511ef26659", "projbb7b9d1b", "global-fixture"),
    "honne-ai": ("6759667221", "app3bbd298d22", "projbb7b9d1b", "global-fixture"),
    "dhamma-quotes": ("6757726663", "appbe1e2ee955", "86624956", "dhamma-fixture"),
    "thankful": ("6759514159", "app2672aee816", "7aaf9429", "thankful-fixture"),
    "sleep-reset": ("6762143790", "appd13f39e1cf", "77301666", "sleep-fixture"),
    "studio-cherie": ("6766485903", None, None, None),
}
VALUES = {"app511ef26659": 20.34, "app3bbd298d22": 0,
          "appbe1e2ee955": 3, "app2672aee816": 4, "appd13f39e1cf": 5}
SERVICES = {"dhamma-quotes": "revenuecat-dhamma-existing-api-v2-ani",
            "thankful": "revenuecat-thankful-existing-api-v2",
            "sleep-reset": "revenuecat-sleep-reset-metrics-read-v2"}


class PublicMobilePortfolioTest(unittest.TestCase):
    def records(self):
        records = [{"service": "revenuecat-mobile-existing-deployment", "api_key": "global-fixture"}]
        for product, service in SERVICES.items():
            _, app, project, key = PUBLIC[product]
            records.append({"service": service, "product_id": product, "app_id": app,
                            "project_id": project, "api_key": key})
        return records

    def fetch(self, *, records=None, fail_project=None):
        helpers = revenuecat_readback._business_outcomes_helpers()
        calls = []
        def get(url, headers):
            parsed = urlparse(url)
            project = parsed.path.split("/")[3]
            scoped = [v for v in PUBLIC.values() if v[2] == project]
            self.assertTrue(scoped, "unregistered project requested")
            self.assertEqual(headers, {"Authorization": "Bearer " + scoped[0][3]})
            calls.append(url)
            if project == fail_project:
                raise PermissionError("global-fixture must not leak")
            if parsed.path.endswith("/options"):
                return {"filters": [{"id": "app_id", "options": [{"id": v[1]} for v in scoped]}]}
            query = parse_qs(parsed.query)
            filters = json.loads(query["filters"][0])
            app = filters[0]["values"][0]
            self.assertIn(app, [v[1] for v in scoped])
            self.assertEqual(filters, [{"name": "app_id", "values": [app]}])
            end = datetime.fromisoformat(query["end_date"][0] + "T00:00:00+00:00")
            start = datetime.fromisoformat(query["start_date"][0] + "T00:00:00+00:00")
            return {"start_date": int(start.timestamp()), "end_date": int(end.timestamp()),
                    "resolution": "day", "yaxis_currency": "USD", "measures": [{"id": "MRR"}],
                    "periods": [int((end-timedelta(days=1)).timestamp()), int(end.timestamp())],
                    "values": [{"measure": 0, "cohort": 0, "value": VALUES[app], "incomplete": False},
                               {"measure": 0, "cohort": 1, "value": 999, "incomplete": True}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            path.write_text(json.dumps({"credentials": self.records() if records is None else records}))
            # The production caller must pass its own SSOT path; never read a developer's file.
            with mock.patch.object(loop_pnl, "CREDENTIALS", path), \
                 mock.patch.object(helpers, "CREDENTIALS_FILE", Path(directory)/"forbidden-live-credentials"), \
                 mock.patch.object(helpers, "http_json", side_effect=get):
                result = loop_pnl._live_mobile_revenuecat_readback({"REVENUECAT_PROJECT_ID": "projbb7b9d1b"})
        return result, calls

    def test_current_six_products_use_five_app_scopes_four_projects_and_their_keys(self):
        result, calls = self.fetch()
        self.assertEqual({x["product_id"] for x in result["rows"]}, set(PUBLIC))
        rows = {x["product_id"]: x for x in result["rows"]}
        for product, (asc, app, _, _) in PUBLIC.items():
            self.assertEqual(capafy_mobile.MOBILE_PRODUCT_BINDINGS[product]["asc_app_id"], asc)
            source = rows[product]["sources"]["revenuecat"]
            if app:
                self.assertEqual(source["status"], "available")
                self.assertEqual(source["data"]["app_id"], app)
                self.assertEqual(source["data"]["charts"]["mrr"]["latest_complete"]["MRR"]["value"], VALUES[app])
            else:
                self.assertEqual(source["reason"], "no_revenuecat_app")
                self.assertIsNone(source["data"])
        self.assertEqual(len(calls), 9)  # Four options queries and five exact app queries.
        for key in [x[3] for x in PUBLIC.values() if x[3]]:
            self.assertNotIn(key, json.dumps(result))
        snapshot = result["completed_at"]
        trailing = (datetime.fromisoformat(snapshot.replace("Z", "+00:00"))-timedelta(days=30)).isoformat()
        projected = economic_attribution.project(capafy_mobile.adapt_mobile(
            result["rows"], snapshot_at=snapshot, trailing_start=trailing),
            snapshot_at=snapshot, trailing_start=trailing)
        self.assertEqual(projected["mrr"]["loops"]["mobile-apps"]["status"], "unknown")
        self.assertEqual(projected["mrr"]["loops"]["mobile-apps"]["currencies"], {})

    def test_missing_duplicate_and_wrong_scope_key_leave_other_projects_readable(self):
        good = self.records()
        broken = [good[:1]+good[2:], good+[good[1]],
                  [good[0], {**good[1], "app_id": "wrong-app"}, *good[2:]]]
        for records in broken:
            with self.subTest(records=records):
                result, calls = self.fetch(records=records)
                rows = {x["product_id"]: x["sources"]["revenuecat"] for x in result["rows"]}
                self.assertEqual(set(rows), set(PUBLIC))
                self.assertEqual(rows["dhamma-quotes"]["status"], "unavailable")
                self.assertEqual(rows["dhamma-quotes"]["reason"], "credential_unavailable")
                self.assertEqual({p for p,s in rows.items() if s["status"]=="available"},
                                 {"anicca-ios", "honne-ai", "thankful", "sleep-reset"})
                self.assertFalse(any("/86624956/" in url for url in calls))

    def test_failure_of_common_project_does_not_discard_the_three_other_projects(self):
        result, calls = self.fetch(fail_project="projbb7b9d1b")
        self.assertEqual({x["product_id"] for x in result["rows"] if x["sources"]["revenuecat"]["status"]=="available"},
                         {"dhamma-quotes", "thankful", "sleep-reset"})
        self.assertEqual(sum("/projbb7b9d1b/" in url for url in calls), 1)
        self.assertNotIn("global-fixture", json.dumps(result))

    def test_studio_missing_app_id_cannot_be_forged_into_a_verified_mrr(self):
        result, _ = self.fetch()
        self.assertEqual({x["product_id"] for x in result["rows"]}, set(PUBLIC))
        rows = copy.deepcopy(result["rows"])
        original = next(x for x in rows if x["product_id"]=="anicca-ios")
        studio = next(x for x in rows if x["product_id"]=="studio-cherie")
        studio["business_date"] = original["business_date"]
        source = copy.deepcopy(original["sources"]["revenuecat"])
        source["data"]["app_id"] = None
        source["data"]["charts"]["mrr"]["latest_complete"]["MRR"]["value"] = 999
        source["evidence_sha256"] = hashlib.sha256(json.dumps(
            {k:source[k] for k in ("status", "reason", "data")}, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        studio["sources"]["revenuecat"] = source
        snapshot=result["completed_at"]
        trailing=(datetime.fromisoformat(snapshot.replace("Z", "+00:00"))-timedelta(days=30)).isoformat()
        records=capafy_mobile.adapt_mobile(rows, snapshot_at=snapshot, trailing_start=trailing)
        self.assertFalse(any(x.get("subscription_id")=="revenuecat:studio-cherie:mrr" for x in records))


if __name__ == "__main__":
    unittest.main()
