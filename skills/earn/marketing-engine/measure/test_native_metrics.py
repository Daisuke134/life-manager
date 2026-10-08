from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("native_metrics.py")
SPEC = importlib.util.spec_from_file_location("native_metrics", MODULE_PATH)
assert SPEC and SPEC.loader
metrics = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = metrics
SPEC.loader.exec_module(metrics)


def publication(
    postiz_id: str = "post-1",
    *,
    platform: str = "tiktok",
    identity_status: str = "resolved",
    state: str = "PUBLISHED",
    native_id: str | None = "native-1",
    release_id: str | None = "native-1",
    published_at: str = "2026-08-01T00:00:00Z",
) -> dict:
    return {
        "schema_version": 1,
        "postiz_post_id": postiz_id,
        "postiz_group_id": "group-1",
        "postiz_state": state,
        "postiz_release_id": release_id,
        "postiz_release_url": "https://example.test/profile",
        "integration_id": "integration-1",
        "account_name": "account",
        "account_id": "tiktok.obou_anicca",
        "platform": platform,
        "product_id": "ebook-ja",
        "product_id_null_reason": None,
        "product_binding_source": "account_manifest.publisher_integration_id",
        "native_post_id": native_id,
        "native_post_url": (
            f"https://www.tiktok.com/@account/video/{native_id}"
            if platform == "tiktok" and native_id
            else "https://example.test/post"
        ),
        "publish_date": published_at,
        "identity_status": identity_status,
        "experiment_id": None,
        "creative_sha256": None,
    }


class NativeMetricCheckpointTest(unittest.TestCase):
    def test_only_resolved_published_rows_are_eligible(self):
        rows = [
            publication("ok"),
            publication("ambiguous", identity_status="ambiguous", native_id=None),
            publication("error", identity_status="error", state="ERROR", native_id=None),
        ]
        eligible, counts = metrics.eligible_publications(rows)
        self.assertEqual([row["postiz_post_id"] for row in eligible], ["ok"])
        self.assertEqual(counts["excluded_ambiguous"], 1)
        self.assertEqual(counts["excluded_error"], 1)

    def test_late_checkpoint_is_still_due_with_missed_sla(self):
        plans = metrics.plan_checkpoints(
            publication(),
            existing_rows=[],
            observed_at="2026-08-02T01:00:00Z",
        )
        self.assertEqual(
            [(plan["target_age_hours"], plan["checkpoint_status"]) for plan in plans],
            [(6, "due"), (24, "due")],
        )
        self.assertEqual(plans[0]["checkpoint_sla_status"], "missed")
        self.assertEqual(plans[0]["error"], "checkpoint_missed")
        self.assertEqual(plans[1]["checkpoint_sla_status"], "in_window")
        self.assertIsNone(plans[1]["error"])

    def test_current_value_is_never_backfilled_into_missed_checkpoint(self):
        missed = metrics.make_missed_row(
            publication(),
            metrics.plan_checkpoints(
                publication(), [], "2026-08-02T01:00:00Z"
            )[0],
            "2026-08-02T01:00:00Z",
        )
        self.assertEqual(missed["checkpoint_status"], "missed")
        for field in metrics.METRIC_FIELDS:
            self.assertIsNone(missed[field])
            self.assertEqual(missed["metric_null_reasons"][field], "checkpoint_missed")

    def test_existing_checkpoint_is_idempotently_skipped(self):
        existing = [{
            "publication_id": "postiz:post-1",
            "target_age_hours": 6,
            "snapshot_id": "measured-6",
            "checkpoint_status": "measured",
        }]
        plans = metrics.plan_checkpoints(
            publication(), existing, "2026-08-02T01:00:00Z"
        )
        self.assertEqual(
            [(plan["target_age_hours"], plan["checkpoint_status"]) for plan in plans],
            [(24, "due")],
        )

    def test_very_late_run_still_plans_provider_collection(self):
        plans = metrics.plan_checkpoints(
            publication(), [], "2026-08-04T08:00:00Z"
        )
        self.assertEqual(
            [(plan["target_age_hours"], plan["checkpoint_status"]) for plan in plans],
            [(6, "due"), (24, "due"), (72, "due")],
        )
        self.assertTrue(
            all(plan["checkpoint_sla_status"] == "missed" for plan in plans)
        )

    def test_historical_missed_checkpoint_plans_one_linked_correction(self):
        missed = metrics.make_missed_row(
            publication(),
            {
                "target_age_hours": 6,
                "observed_age_hours": 25.0,
                "lateness_hours": 19.0,
                "max_lateness_hours": 3,
                "checkpoint_status": "missed",
                "error": "checkpoint_missed",
            },
            "2026-08-02T01:00:00Z",
        )
        plans = metrics.plan_checkpoints(
            publication(), [missed], "2026-08-02T02:00:00Z"
        )
        correction = next(plan for plan in plans if plan["target_age_hours"] == 6)
        self.assertEqual(correction["checkpoint_status"], "due")
        self.assertEqual(correction["checkpoint_sla_status"], "missed")
        self.assertEqual(correction["corrects_snapshot_id"], missed["snapshot_id"])

    def test_late_checkpoint_fetches_real_zero_instead_of_writing_missed(self):
        calls = []

        def fetch(postiz_id: str) -> list[dict]:
            calls.append(postiz_id)
            return [
                {"label": "Views", "data": [{"total": 0}]},
                {"label": "Likes", "data": [{"total": 0}]},
            ]

        new_rows, _raw, _report = metrics.collect_metrics(
            [publication(platform="youtube")],
            [],
            observed_at="2026-08-02T01:00:00Z",
            fetch_analytics=fetch,
        )
        six_hour = next(row for row in new_rows if row["target_age_hours"] == 6)
        self.assertEqual(calls, ["post-1", "post-1"])
        self.assertEqual(six_hour["checkpoint_status"], "measured")
        self.assertEqual(six_hour["checkpoint_sla_status"], "missed")
        self.assertEqual(six_hour["views"], 0)
        self.assertIsNone(six_hour["error"])

    def test_tiktok_checkpoint_uses_postiz_per_post_api(self):
        calls = []

        def fetch(postiz_id: str) -> list[dict]:
            calls.append(postiz_id)
            return [
                {"label": "Views", "data": [{"total": 71}]},
                {"label": "Likes", "data": [{"total": 1}]},
                {"label": "Comments", "data": [{"total": 0}]},
                {"label": "Shares", "data": [{"total": 0}]},
            ]

        new_rows, _raw, _report = metrics.collect_metrics(
            [publication()],
            [],
            observed_at="2026-08-01T07:00:00Z",
            fetch_analytics=fetch,
        )

        self.assertEqual(calls, ["post-1"])
        row = new_rows[0]
        self.assertEqual(row["source"], "postiz_tiktok_per_post_api")
        self.assertEqual(row["collector_version"], "native-metrics-v2")
        self.assertEqual(row["views"], 71)
        self.assertEqual(row["likes"], 1)
        self.assertEqual(row["comments"], 0)
        self.assertEqual(row["shares"], 0)
        self.assertIsNone(row["reach"])
        self.assertEqual(row["metric_null_reasons"]["reach"], "provider_field_missing")

    def test_product_binding_fields_propagate_to_due_and_missed_rows(self):
        plans = metrics.plan_checkpoints(
            publication(), [], "2026-08-02T01:00:00Z"
        )
        missed = metrics.make_missed_row(
            publication(), plans[0], "2026-08-02T01:00:00Z"
        )
        due = metrics.make_metric_row(
            publication(),
            plans[1],
            {field: 0 for field in metrics.METRIC_FIELDS},
            {field: None for field in metrics.METRIC_FIELDS},
            observed_at="2026-08-02T01:00:00Z",
            source="postiz_tiktok_per_post_api",
            raw_response={"native_post_id": "native-1"},
        )
        for row in (missed, due):
            self.assertEqual(row["product_id"], "ebook-ja")
            self.assertIsNone(row["product_id_null_reason"])
            self.assertEqual(row["native_post_id"], "native-1")
            self.assertEqual(
                row["native_url"],
                "https://www.tiktok.com/@account/video/native-1",
            )


class NativeMetricNormalizationTest(unittest.TestCase):
    def test_zero_is_preserved_and_missing_stays_null(self):
        normalized, reasons = metrics.normalize_postiz_analytics(
            "instagram",
            [
                {"label": "Views", "data": [{"total": "0"}]},
                {"label": "Likes", "data": [{"total": "0"}]},
            ],
        )
        self.assertEqual(normalized["views"], 0)
        self.assertEqual(normalized["likes"], 0)
        self.assertIsNone(normalized["reach"])
        self.assertEqual(reasons["reach"], "provider_field_missing")

    def test_empty_provider_response_is_unavailable_not_zero(self):
        normalized, reasons = metrics.normalize_postiz_analytics("tiktok", [])
        self.assertTrue(all(normalized[field] is None for field in metrics.METRIC_FIELDS))
        self.assertTrue(
            all(reasons[field] == "provider_empty_response" for field in metrics.METRIC_FIELDS)
        )

    def test_deprecated_youtube_favorites_is_not_treated_as_saves(self):
        normalized, reasons = metrics.normalize_postiz_analytics(
            "youtube",
            [
                {"label": "Views", "data": [{"total": "0"}]},
                {"label": "Favorites", "data": [{"total": "0"}]},
            ],
        )
        self.assertEqual(normalized["views"], 0)
        self.assertIsNone(normalized["saves"])
        self.assertEqual(reasons["saves"], "provider_field_missing")

    def test_instagram_actor_zero_does_not_fall_through(self):
        normalized, reasons = metrics.normalize_public_instagram(
            {
                "videoPlayCount": 0,
                "videoViewCount": 99,
                "likesCount": 0,
                "commentsCount": 0,
            }
        )
        self.assertEqual(normalized["views"], 0)
        self.assertEqual(normalized["likes"], 0)
        self.assertIsNone(normalized["shares"])
        self.assertEqual(reasons["shares"], "public_field_unavailable")

    def test_tiktok_public_response_maps_native_counts_and_preserves_zero(self):
        normalized, reasons = metrics.normalize_public_tiktok(
            {
                "playCount": 559,
                "diggCount": 32,
                "commentCount": 0,
                "shareCount": 0,
                "collectCount": 1,
            }
        )
        self.assertEqual(normalized["views"], 559)
        self.assertEqual(normalized["likes"], 32)
        self.assertEqual(normalized["comments"], 0)
        self.assertEqual(normalized["shares"], 0)
        self.assertEqual(normalized["saves"], 1)
        self.assertIsNone(reasons["comments"])

    def test_missing_tiktok_native_item_is_unavailable_not_zero(self):
        normalized, reasons = metrics.normalize_public_tiktok(None)
        self.assertTrue(all(normalized[field] is None for field in metrics.METRIC_FIELDS))
        self.assertTrue(
            all(reasons[field] == "native_item_not_visible" for field in metrics.METRIC_FIELDS)
        )

    def test_metric_row_has_stable_evidence_hash_and_validates(self):
        plan = metrics.plan_checkpoints(
            publication(), [], "2026-08-02T01:00:00Z"
        )[1]
        values, reasons = metrics.normalize_postiz_analytics(
            "instagram",
            [{"label": "Views", "data": [{"total": "12"}]}],
        )
        one = metrics.make_metric_row(
            publication(),
            plan,
            values,
            reasons,
            observed_at="2026-08-02T01:00:00Z",
            source="postiz_instagram_graph_api",
            raw_response=[{"label": "Views", "data": [{"total": "12"}]}],
        )
        two = metrics.make_metric_row(
            publication(),
            plan,
            values,
            reasons,
            observed_at="2026-08-02T01:00:00Z",
            source="postiz_instagram_graph_api",
            raw_response=[{"label": "Views", "data": [{"total": "12"}]}],
        )
        self.assertEqual(one["raw_evidence_hash"], two["raw_evidence_hash"])
        metrics.validate_metric_rows([one])

    def test_duplicate_publication_checkpoint_is_rejected(self):
        missed = metrics.make_missed_row(
            publication(),
            metrics.plan_checkpoints(
                publication(), [], "2026-08-02T01:00:00Z"
            )[0],
            "2026-08-02T01:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "duplicate metric checkpoint"):
            metrics.validate_metric_rows([missed, dict(missed)])


class TikTokReleaseRepairTest(unittest.TestCase):
    def test_repair_plan_is_allowlisted_to_resolved_numeric_native_ids(self):
        rows = [
            publication(
                "repair",
                platform="tiktok",
                native_id="7667763982932937992",
                release_id="v_pub_file~v2-token",
            ),
            publication(
                "ambiguous",
                platform="tiktok",
                identity_status="ambiguous",
                native_id=None,
                release_id="v_pub_file~other",
            ),
            publication("instagram"),
        ]
        repairs = metrics.plan_tiktok_release_repairs(rows)
        self.assertEqual(len(repairs), 1)
        self.assertEqual(repairs[0]["postiz_post_id"], "repair")
        self.assertEqual(repairs[0]["new_release_id"], "7667763982932937992")

    def test_failed_repair_verification_rolls_back(self):
        calls: list[tuple[str, str]] = []

        def update(postiz_id: str, release_id: str) -> None:
            calls.append((postiz_id, release_id))

        def analytics(postiz_id: str) -> list:
            return []

        repair = metrics.plan_tiktok_release_repairs(
            [
                publication(
                    "repair",
                    platform="tiktok",
                    native_id="7667763982932937992",
                    release_id="v_pub_file~v2-token",
                )
            ]
        )[0]
        result = metrics.execute_tiktok_release_repair(
            repair, update_release_id=update, fetch_analytics=analytics
        )
        self.assertEqual(
            calls,
            [
                ("repair", "7667763982932937992"),
                ("repair", "v_pub_file~v2-token"),
            ],
        )
        self.assertEqual(result["status"], "rolled_back")
        self.assertEqual(result["error"], "analytics_verification_empty")

    def test_source_has_no_openclaw_dependency(self):
        source = MODULE_PATH.read_text()
        self.assertNotIn(".openclaw", source)
        self.assertNotIn("openclaw ", source)


if __name__ == "__main__":
    unittest.main()
