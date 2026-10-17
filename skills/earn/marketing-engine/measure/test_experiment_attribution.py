from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("experiment_attribution.py")
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
from attribution import publication_campaign_token

SPEC = importlib.util.spec_from_file_location("experiment_attribution", MODULE_PATH)
assert SPEC and SPEC.loader
ea = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ea
SPEC.loader.exec_module(ea)


def fixture_intent():
    return {
        "schema_version": "marketing.publication-intent.v2",
        "publish_key": "publication.abc",
        "experiment_id": "experiment.one",
        "creative_id": "creative.one",
        "product_id": "ebook-ja",
        "account_id": "tiktok.obou_anicca",
        "asset_sha256": "a" * 64,
        "integration_id": "integration.ebook-ja",
        "platform": "tiktok",
        "postiz_post_id": "postiz-1",
        "native_post_id": "native-1",
        "native_post_url": "https://example.test/native-1",
        "hook_id": "hook.one",
        "renderer_id": "watercolor",
        "attribution_token": "ej_token",
        "scheduled_at": "2026-08-01T20:15:00Z",
    }


def fixture_identity(intent=None):
    intent = intent or fixture_intent()
    return {
        "publish_key": intent["publish_key"],
        "experiment_id": intent["experiment_id"],
        "creative_id": intent["creative_id"],
        "creative_sha256": intent["asset_sha256"],
        "product_id": intent["product_id"],
        "account_id": intent["account_id"],
        "integration_id": intent["integration_id"],
        "platform": intent["platform"],
        "hook_id": intent["hook_id"],
        "renderer_id": intent["renderer_id"],
        "attribution_token": intent["attribution_token"],
        "scheduled_at": intent["scheduled_at"],
        "postiz_post_id": intent["postiz_post_id"],
        "native_post_id": intent["native_post_id"],
        "native_post_url": intent["native_post_url"],
        "publish_date": intent["scheduled_at"],
        "identity_status": "resolved",
    }


def fixture_hook_lab_intent():
    intent = {
        "schema_version": "marketing.publication-intent.v2",
        "publish_key": "publication.hooklab",
        "experiment_id": "experiment.dd03",
        "creative_id": "creative.dd03",
        "product_id": "hook-lab",
        "account_id": "life-manager-capafy-ig",
        "asset_sha256": "b" * 64,
        "integration_id": "integration.hook-lab",
        "platform": "instagram",
        "postiz_post_id": "postiz-hook-lab",
        "native_post_id": "native-hook-lab",
        "native_post_url": "https://example.test/native-hook-lab",
        "hook_id": "hook.dd03",
        "renderer_id": "watercolor-monk",
        "scheduled_at": "2026-10-16T00:00:00Z",
    }
    intent["attribution_token"] = publication_campaign_token(intent)
    return intent


def fixture_hook_lab_identity():
    intent = fixture_hook_lab_intent()
    return {
        **fixture_identity(intent),
    }


class AttributionContractTest(unittest.TestCase):
    def test_complete_metric_set_and_null_reasons(self):
        snapshot = ea.build_snapshot(
            intent=fixture_intent(), identity=fixture_identity(),
            post_metric=None,
            click_query={"status": "unavailable", "reason": "query_failed",
                         "evidence_refs": ["evidence/click.json"]},
            business_snapshot=None,
            observed_at="2026-08-01T21:15:00Z",
        )
        self.assertEqual(set(ea.REQUIRED_METRICS), {
            "impressions", "views", "qualified_clicks", "first_time_downloads",
            "installs", "trials", "paid_orders", "refunds", "gross_revenue",
            "net_revenue", "actual_cost_usd", "human_interventions",
        })
        self.assertEqual({row["metric_name"] for row in snapshot["results"]},
                         set(ea.REQUIRED_METRICS))
        for row in snapshot["results"]:
            self.assertIn(row["attribution_class"], ea.ATTRIBUTION_CLASSES)
            self.assertIsNotNone(row["null_reason"])
            self.assertIsNone(row["value"])
        by_name = {row["metric_name"]: row for row in snapshot["results"]}
        self.assertEqual(by_name["actual_cost_usd"]["unit"], "usd")
        self.assertEqual(by_name["actual_cost_usd"]["null_reason"],
                         "publication_scoped_cost_evidence_unavailable")
        self.assertEqual(by_name["human_interventions"]["null_reason"],
                         "publication_scoped_intervention_evidence_unavailable")
        ea.validate_snapshot(snapshot)

    def test_exact_social_and_click_receipts_are_deterministic(self):
        post_metric = {
            "experiment_id": "experiment.one", "native_post_id": "native-1",
            "checkpoint_status": "observed", "observed_at": "2026-08-02T02:20:00Z",
            "views": 123, "impressions": 150,
            "raw_evidence_hash": "a" * 64,
        }
        click = {
            "status": "available", "product_id": "ebook-ja",
            "campaign_token": "ej_token", "count": 0,
            "observed_at": "2026-08-02T02:20:00Z",
            "evidence_refs": ["evidence/click.json"],
        }
        snapshot = ea.build_snapshot(
            intent=fixture_intent(), identity=fixture_identity(),
            post_metric=post_metric, click_query=click, business_snapshot=None,
            observed_at="2026-08-02T02:20:00Z",
        )
        by_name = {row["metric_name"]: row for row in snapshot["results"]}
        self.assertEqual((by_name["views"]["value"], by_name["views"]["attribution_class"]),
                         (123, "deterministic"))
        self.assertEqual((by_name["qualified_clicks"]["value"],
                          by_name["qualified_clicks"]["attribution_class"]),
                         (0, "deterministic"))

    def test_wrong_identity_or_click_scope_fails_closed(self):
        identity = fixture_identity()
        post_metric = {"experiment_id": "experiment.one", "native_post_id": "native-other",
                       "checkpoint_status": "observed", "views": 1, "impressions": 1,
                       "observed_at": "2026-08-02T02:20:00Z"}
        with self.assertRaisesRegex(ValueError, "native identity mismatch"):
            ea.build_snapshot(intent=fixture_intent(), identity=identity,
                              post_metric=post_metric, click_query=None,
                business_snapshot=None,
                observed_at="2026-08-02T02:20:00Z")

    def test_publish_key_and_postiz_identity_must_match_exactly(self):
        for field, value in (
            ("publish_key", "publication.other"),
            ("experiment_id", "experiment.other"),
            ("creative_id", "creative.other"),
            ("creative_sha256", "b" * 64),
            ("product_id", "ebook-en"),
            ("account_id", "account.other"),
            ("integration_id", "integration.other"),
            ("platform", "instagram"),
            ("hook_id", "hook.other"),
            ("renderer_id", "renderer.other"),
            ("attribution_token", "other-token"),
            ("scheduled_at", "2026-08-01T21:15:00Z"),
            ("postiz_post_id", "postiz-other"),
            ("native_post_id", "native-other"),
            ("native_post_url", "https://example.test/native-other"),
        ):
            with self.subTest(field=field):
                identity = {**fixture_identity(), field: value}
                with self.assertRaisesRegex(ValueError, "publication identity mismatch"):
                    ea.build_snapshot(
                        intent=fixture_intent(), identity=identity,
                        post_metric=None, click_query=None, business_snapshot=None,
                        observed_at="2026-08-02T02:20:00Z",
                    )

    def test_hook_lab_snapshot_rejects_foreign_or_shared_token(self):
        intent = fixture_hook_lab_intent()
        identity = fixture_hook_lab_identity()
        variants = [
            {**intent, "attribution_token": "capafy-distribute-hook-lab"},
            {**intent, "attribution_token": "hooklab_ig"},
            {**intent, "scheduled_at": "2026-10-16T01:00:00Z"},
        ]
        for candidate in variants:
            with self.subTest(token=candidate["attribution_token"],
                              scheduled_at=candidate["scheduled_at"]):
                click = {
                    "status": "available", "product_id": "hook-lab",
                    "campaign_token": candidate["attribution_token"], "count": 1,
                    "receipt_ids": ["click-1"],
                    "evidence_refs": ["evidence/click.json"],
                }
                with self.assertRaisesRegex(ValueError, "Hook Lab publication token mismatch"):
                    ea.build_snapshot(
                        intent=candidate, identity=identity, post_metric=None,
                        click_query=click, business_snapshot=None,
                        observed_at="2026-10-17T02:20:00Z",
                    )
        with self.assertRaisesRegex(ValueError, "click scope mismatch"):
            ea.build_snapshot(
                intent=fixture_intent(), identity=fixture_identity(), post_metric=None,
                click_query={"status": "available", "product_id": "ebook-en",
                             "campaign_token": "ej_token", "count": 0,
                             "evidence_refs": ["e"]}, business_snapshot=None,
                observed_at="2026-08-02T02:20:00Z")

    def test_apple_campaign_is_aggregate_and_unscoped_stripe_is_unknown(self):
        app_intent = {**fixture_intent(), "product_id": "anicca-ios",
                      "attribution_token": "ai_token"}
        business = {
            "product_id": "anicca-ios", "business_date": "2026-08-01",
            "sources": {"app_store_connect": {"status": "available", "data": {
                "campaigns": {"ai_token": {"first_time_downloads": 7, "installs": 7,
                                             "evidence_ref": "evidence/asc.json"}}
            }}},
        }
        snapshot = ea.build_snapshot(
            intent=app_intent, identity=fixture_identity(app_intent), post_metric=None,
            click_query=None, business_snapshot=business,
            observed_at="2026-08-03T21:15:00Z")
        by_name = {row["metric_name"]: row for row in snapshot["results"]}
        self.assertEqual(by_name["first_time_downloads"]["attribution_class"],
                         "apple_aggregate")
        self.assertEqual(by_name["first_time_downloads"]["value"], 7)

        stripe = {"product_id": "ebook-ja", "business_date": "2026-08-01",
                  "sources": {"stripe": {"status": "available", "data": {
                      "paid_orders": 2, "gross_minor": {"jpy": 3160},
                      "refunded_minor": {}, "net_minor": {"jpy": 3160},
                      "evidence_ref": "evidence/stripe.json"}}}}
        ebook = ea.build_snapshot(
            intent=fixture_intent(), identity=fixture_identity(), post_metric=None,
            click_query=None, business_snapshot=stripe,
            observed_at="2026-08-03T21:15:00Z")
        paid = next(row for row in ebook["results"] if row["metric_name"] == "paid_orders")
        self.assertIsNone(paid["value"])
        self.assertEqual((paid["status"], paid["attribution_class"], paid["null_reason"]),
                         ("unknown", "unknown", "product_aggregate_not_publication_attributed"))

    def test_exact_token_checkout_is_deterministic_and_replay_is_idempotent(self):
        business = {"product_id": "ebook-ja", "business_date": "2026-08-01",
                    "sources": {"stripe": {"status": "available", "data": {
                        "campaigns": {"ej_token": {"paid_orders": 1, "refunds": 0,
                            "gross_revenue": 1580, "net_revenue": 1580,
                            "currency": "jpy", "evidence_ref": "evidence/stripe.json"}}
                    }}}}
        snapshot = ea.build_snapshot(
            intent=fixture_intent(), identity=fixture_identity(), post_metric=None,
            click_query=None, business_snapshot=business,
            observed_at="2026-08-03T21:15:00Z")
        paid = next(row for row in snapshot["results"] if row["metric_name"] == "paid_orders")
        self.assertEqual((paid["value"], paid["attribution_class"]), (1, "deterministic"))
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "attribution.jsonl"
            self.assertTrue(ea.append_snapshot(ledger, snapshot))
            self.assertFalse(ea.append_snapshot(ledger, snapshot))
            changed = json.loads(json.dumps(snapshot))
            changed["results"][0]["confidence"] = 0.5
            with self.assertRaisesRegex(ValueError, "conflicting attribution replay"):
                ea.append_snapshot(ledger, changed)

    def test_modeled_requires_declared_method_and_interval(self):
        result = ea.empty_result("installs", "count", "2026-08-01T20:15:00Z",
                                 "2026-08-03T21:15:00Z", "model")
        result.update({"status": "observed", "value": 4, "null_reason": None,
                       "attribution_class": "modeled", "confidence": 0.7})
        with self.assertRaisesRegex(ValueError, "modeled evidence"):
            ea.validate_result(result)
        result["model"] = {"method": "staggered_holdout", "baseline": 2,
                           "sample_size": 20, "interval": [1, 7]}
        ea.validate_result(result)

    def test_exact_ledger_selectors_reject_ambiguous_identity(self):
        identity = fixture_identity()
        self.assertEqual(ea.select_identity([identity], fixture_intent(), "postiz-1"),
                         identity)
        with self.assertRaisesRegex(ValueError, "exactly one publication identity"):
            ea.select_identity([identity, identity], fixture_intent(), "postiz-1")
        social = [
            {"experiment_id": "experiment.one", "native_post_id": "native-1",
             "observed_at": "2026-08-02T01:00:00Z", "views": 1},
            {"experiment_id": "experiment.one", "native_post_id": "native-1",
             "observed_at": "2026-08-02T02:00:00Z", "views": 2},
        ]
        self.assertEqual(ea.select_latest_post_metric(
            social, identity, "2026-08-02T01:30:00Z")["views"], 1)

    def test_intent_loader_requires_postiz_and_native_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "intents.sqlite3"
            with sqlite3.connect(db_path) as db:
                db.execute(
                    "CREATE TABLE intents (publish_key TEXT, payload_json TEXT, "
                    "provider_post_id TEXT, native_post_id TEXT, native_post_url TEXT)"
                )
                db.execute(
                    "INSERT INTO intents VALUES (?, ?, ?, ?, ?)",
                    (
                        "publication.abc",
                        json.dumps(fixture_intent()),
                        "postiz-1",
                        "native-1",
                        "https://example.test/native-1",
                    ),
                )

            loaded = ea._load_intent(db_path, "publication.abc")

            self.assertEqual(loaded[1:], (
                "postiz-1", "native-1", "https://example.test/native-1"
            ))
            with sqlite3.connect(db_path) as db:
                db.execute(
                    "UPDATE intents SET native_post_id=NULL,native_post_url=NULL "
                    "WHERE publish_key=?",
                    ("publication.abc",),
                )
            with self.assertRaisesRegex(ValueError, "native post receipt missing"):
                ea._load_intent(db_path, "publication.abc")

    def test_click_query_uses_exact_scope_and_exact_count_header(self):
        calls = []

        def fetch(url, headers):
            calls.append((url, headers))
            return 200, {"content-range": "0-1/2"}, [
                {"receipt_id": "r1", "campaign_token": "ej_token",
                 "product_id": "ebook-ja", "clicked_at": "2026-08-02T00:00:00Z"},
                {"receipt_id": "r2", "campaign_token": "ej_token",
                 "product_id": "ebook-ja", "clicked_at": "2026-08-02T00:01:00Z"},
            ]

        result = ea.query_click_receipts(
            supabase_url="https://project.supabase.co", service_role_key="secret",
            product_id="ebook-ja", campaign_token="ej_token",
            observed_at="2026-08-02T02:20:00Z", fetch=fetch)
        self.assertEqual((result["status"], result["count"]), ("available", 2))
        self.assertIn("campaign_token=eq.ej_token", calls[0][0])
        self.assertIn("product_id=eq.ebook-ja", calls[0][0])
        self.assertEqual(calls[0][1]["Prefer"], "count=exact")
        self.assertNotIn("secret", json.dumps(result))

    def test_click_query_rejects_incomplete_or_duplicate_receipts(self):
        token = fixture_hook_lab_intent()["attribution_token"]
        valid_row = {
            "campaign_token": token, "product_id": "hook-lab",
            "clicked_at": "2026-10-16T01:00:00Z",
        }
        cases = [
            (
                "count exceeds returned rows",
                {"content-range": "0-0/2"},
                [{**valid_row, "receipt_id": "r1"}],
                "receipt_rows_incomplete",
            ),
            (
                "duplicate receipt IDs",
                {"content-range": "0-1/2"},
                [{**valid_row, "receipt_id": "r1"}, {**valid_row, "receipt_id": "r1"}],
                "receipt_ids_invalid",
            ),
        ]
        for label, headers, rows, reason in cases:
            with self.subTest(label=label):
                result = ea.query_click_receipts(
                    supabase_url="https://project.supabase.co",
                    service_role_key="secret",
                    product_id="hook-lab", campaign_token=token,
                    observed_at="2026-10-17T02:20:00Z",
                    fetch=lambda _url, _headers: (200, headers, rows),
                )
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["reason"], reason)

    def test_non_hook_lab_click_query_keeps_exact_header_count_when_body_is_partial(self):
        result = ea.query_click_receipts(
            supabase_url="https://project.supabase.co",
            service_role_key="secret",
            product_id="ebook-ja", campaign_token="ej_token",
            observed_at="2026-08-02T02:20:00Z",
            fetch=lambda _url, _headers: (200, {"content-range": "0-0/2"}, [
                {"receipt_id": "r1", "campaign_token": "ej_token",
                 "product_id": "ebook-ja", "clicked_at": "2026-08-02T00:00:00Z"},
            ]),
        )
        self.assertEqual((result["status"], result["count"]), ("available", 2))
        self.assertEqual(result["receipt_ids"], ["r1"])

    def test_hook_lab_click_join_rejects_incomplete_or_duplicate_receipts(self):
        intent = fixture_hook_lab_intent()
        identity = fixture_hook_lab_identity()
        cases = [
            {"count": 1, "receipt_ids": []},
            {"count": 2, "receipt_ids": ["click-1", "click-1"]},
        ]
        for click in cases:
            with self.subTest(click=click):
                query = {
                    "status": "available", "product_id": "hook-lab",
                    "campaign_token": intent["attribution_token"],
                    "evidence_refs": ["supabase:marketing_click_receipts"],
                    **click,
                }
                with self.assertRaisesRegex(ValueError, "click receipt IDs invalid"):
                    ea.build_snapshot(
                        intent=intent, identity=identity, post_metric=None,
                        click_query=query, business_snapshot=None,
                        observed_at="2026-10-17T02:20:00Z",
                    )

    def test_hook_lab_click_receipt_id_is_saved_as_creative_evidence(self):
        intent = fixture_hook_lab_intent()
        identity = fixture_hook_lab_identity()
        snapshot = ea.build_snapshot(
            intent=intent, identity=identity, post_metric=None,
            click_query={
                "status": "available", "product_id": "hook-lab",
                "campaign_token": intent["attribution_token"], "count": 1,
                "receipt_ids": ["click-hooklab-1"],
                "evidence_refs": ["supabase:marketing_click_receipts"],
            },
            business_snapshot=None, observed_at="2026-10-17T02:20:00Z",
        )
        click = next(row for row in snapshot["results"]
                     if row["metric_name"] == "qualified_clicks")
        self.assertEqual(click["value"], 1)
        self.assertIn("marketing_click_receipt:click-hooklab-1", click["evidence_refs"])
        self.assertEqual(snapshot["experiment_id"], "experiment.dd03")
        self.assertEqual(snapshot["creative_id"], "creative.dd03")
        self.assertEqual(snapshot["publish_key"], "publication.hooklab")

    def test_hook_lab_paid_revenue_stays_unknown_without_capafy_order_join(self):
        intent = fixture_hook_lab_intent()
        identity = fixture_hook_lab_identity()
        business = {
            "product_id": "hook-lab",
            "business_date": "2026-10-16",
            "sources": {
                "capafy": {"status": "available", "data": {
                    "paid_orders": 7, "sales_usd": "5.93",
                    "scope": "agent_total_not_click_joined",
                }},
                "stripe": {"status": "available", "data": {
                    "campaigns": {intent["attribution_token"]: {
                        "paid_orders": 7, "refunds": 0,
                        "gross_revenue": 593, "net_revenue": 593,
                        "currency": "usd", "evidence_ref": "evidence/stripe.json",
                    }},
                }},
            },
        }
        snapshot = ea.build_snapshot(
            intent=intent, identity=identity, post_metric=None,
            click_query=None, business_snapshot=business,
            observed_at="2026-10-17T02:20:00Z",
        )
        by_name = {row["metric_name"]: row for row in snapshot["results"]}
        for metric in ("paid_orders", "gross_revenue", "net_revenue"):
            self.assertIsNone(by_name[metric]["value"])
            self.assertEqual(by_name[metric]["status"], "unknown")
            self.assertEqual(by_name[metric]["attribution_class"], "unknown")


if __name__ == "__main__":
    unittest.main()
