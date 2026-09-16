import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "source_capture.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("affiliate_source_capture", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SourceCaptureTest(unittest.TestCase):
    def test_nested_experiment_plan_id_is_compact_enough_for_placement(self):
        control = (
            "elevenlabs-discovered-subtitle-translator-en-"
            "experiment-1ecf26fe47e1"
        )
        plan_id = MODULE.experiment_plan_id(control, "c682536aed63")
        self.assertEqual(
            plan_id,
            "elevenlabs-discovered-subtitle-translator-en-experiment-c682536aed63",
        )
        self.assertLessEqual(len(f"{plan_id}-1"), 80)

    def test_oversized_experiment_plan_does_not_consume_ready_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            decisions = state / "acquisition-decisions"
            decisions.mkdir(parents=True)
            decision = {
                "state": "READY", "decision_id": "c682536aed63",
                "baseline_sha256": "a" * 64,
                "plan_id": (
                    "elevenlabs-discovered-subtitle-translator-en-"
                    "experiment-1ecf26fe47e1"
                ),
                "placement_id": "control-1",
                "selected_variable": "title", "hypothesis": "hypothesis",
                "next_campaign_instruction": "change only title",
                "success_metric": "page views > 0",
            }
            (decisions / "decision.json").write_text(json.dumps(decision))
            plans = [{
                "plan_id": f"{decision['plan_id']}-experiment-c682536aed63",
                "experiment": {
                    "decision_id": decision["decision_id"],
                    "control_plan_id": decision["plan_id"],
                },
            }]
            self.assertEqual(
                MODULE.pending_experiment(state, plans)["decision_id"],
                decision["decision_id"],
            )

    def test_compact_experiment_plan_consumes_ready_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            decisions = state / "acquisition-decisions"
            decisions.mkdir(parents=True)
            decision = {
                "state": "READY", "decision_id": "c682536aed63" + "0" * 52,
                "baseline_sha256": "a" * 64,
                "plan_id": (
                    "elevenlabs-discovered-subtitle-translator-en-"
                    "experiment-1ecf26fe47e1"
                ),
                "placement_id": "control-1",
                "selected_variable": "title", "hypothesis": "hypothesis",
                "next_campaign_instruction": "change only title",
                "success_metric": "page views > 0",
            }
            (decisions / "decision.json").write_text(json.dumps(decision))
            plans = [{
                "plan_id": "elevenlabs-discovered-subtitle-translator-en-experiment-c682536aed63",
                "experiment": {
                    "decision_id": decision["decision_id"],
                    "control_plan_id": decision["plan_id"],
                },
            }]
            self.assertIsNone(MODULE.pending_experiment(state, plans))

    def test_discovery_uses_agent_selected_candidate_instead_of_sitemap_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            (root / "config" / "source-plans").mkdir(parents=True)
            state = Path(directory) / "state"
            selector = mock.Mock(return_value={
                "state": "READY",
                "decision_id": "decision-1",
                "selected_family": "speech-to-text",
                "hypothesis": "Decision-stage transcription intent will produce a measurable provider click.",
                "evidence": ["candidate family and current placement ledger"],
                "success_metric": "placement-attributed provider click delta",
            })
            sitemap = "\n".join((
                "https://elevenlabs.io/text-to-speech",
                "https://elevenlabs.io/speech-to-text",
            ))
            with (
                mock.patch.object(MODULE, "run_adapter", return_value=MODULE.DISCOVERY_SITEMAP),
                mock.patch.object(MODULE, "fetch_sitemap_xml", return_value=sitemap),
            ):
                receipt = MODULE.discover_official_plan(
                    root, state, 1000, opportunity_selector=selector,
                )

            self.assertEqual(receipt["selected_family"], "speech-to-text")
            self.assertEqual(receipt["opportunity_decision_id"], "decision-1")
            plan = json.loads((
                state / "discovered-source-plans"
                / "elevenlabs-discovered-speech-to-text-en.json"
            ).read_text())
            self.assertEqual(plan["offer_id"], "elevenlabs-speech-to-text")
            self.assertEqual(
                plan["opportunity_decision"]["decision_id"], "decision-1",
            )
            receipts = [{
                "source_id": "official-speech-to-text",
                "locator": "https://elevenlabs.io/speech-to-text",
                "evidence_class": "official_product",
                "raw_sha256": "a" * 64,
            }]
            bundle = MODULE.write_composition_bundle(state, plan, receipts)
            self.assertEqual(
                bundle["opportunity_decision"], plan["opportunity_decision"],
            )
            candidates = selector.call_args.args[2]
            self.assertEqual([row["family"] for row in candidates], [
                "text-to-speech", "speech-to-text",
            ])

    def test_failure_classes_are_explicit(self):
        self.assertIsNone(MODULE.classify_failure(0, "body"))
        self.assertEqual(MODULE.classify_failure(0, ""), "EMPTY")
        self.assertEqual(MODULE.classify_failure(1, "HTTP 429"), "RATE_LIMIT")
        self.assertEqual(MODULE.classify_failure(1, "HTTP 403"), "AUTH")
        self.assertEqual(MODULE.classify_failure(1, "boom"), "UPSTREAM")

    def test_refresh_all_plans_finishes_daily_receipt_across_wakes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            plans = root / "config" / "source-plans"
            plans.mkdir(parents=True)
            for plan_id in ("alpha-en", "beta-en"):
                (plans / f"{plan_id}.json").write_text(json.dumps({
                    "schema_version": 1, "plan_id": plan_id, "locale": "en", "sources": [],
                }))
            state = Path(directory) / "state"
            with mock.patch.object(MODULE, "capture", return_value=[]):
                receipt = MODULE.refresh_all(
                    root, state, now=1000, cooldown_seconds=86400,
                    disk_floor_bytes=1,
                )
                replay = MODULE.refresh_all(
                    root, state, now=1001, cooldown_seconds=86400,
                    disk_floor_bytes=1,
                )
                cooldown = MODULE.refresh_all(
                    root, state, now=1002, cooldown_seconds=86400,
                    disk_floor_bytes=1,
                )
            self.assertEqual(receipt["state"], "IN_PROGRESS")
            self.assertEqual([row["plan_id"] for row in receipt["plans"]], ["alpha-en"])
            self.assertTrue((state / "composition-inbox" / "alpha-en.json").is_file())
            self.assertEqual(replay["state"], "COMPLETE")
            self.assertEqual([row["plan_id"] for row in replay["plans"]], ["alpha-en", "beta-en"])
            self.assertTrue((state / "composition-inbox" / "beta-en.json").is_file())
            self.assertEqual(cooldown["state"], "COOLDOWN")

    def test_refresh_resumes_one_plan_per_wake_without_repeating_completed_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            plans = root / "config" / "source-plans"
            plans.mkdir(parents=True)
            for plan_id in ("alpha-en", "beta-en", "gamma-en"):
                (plans / f"{plan_id}.json").write_text(json.dumps({
                    "schema_version": 1, "plan_id": plan_id,
                    "locale": "en", "sources": [],
                }))
            state = Path(directory) / "state"
            with (mock.patch.object(MODULE, "discover_official_plan", return_value={"state": "COOLDOWN"}),
                  mock.patch.object(MODULE, "capture", return_value=[])):
                first = MODULE.refresh_all(root, state, now=1000, disk_floor_bytes=1)
                second = MODULE.refresh_all(root, state, now=1001, disk_floor_bytes=1)
                third = MODULE.refresh_all(root, state, now=1002, disk_floor_bytes=1)
                replay = MODULE.refresh_all(root, state, now=1003, disk_floor_bytes=1)
            self.assertEqual(first["state"], "IN_PROGRESS")
            self.assertEqual(first["pending_count"], 2)
            self.assertEqual([row["plan_id"] for row in first["plans"]], ["alpha-en"])
            self.assertEqual(second["state"], "IN_PROGRESS")
            self.assertEqual(second["pending_count"], 1)
            self.assertEqual([row["plan_id"] for row in second["plans"]], ["alpha-en", "beta-en"])
            self.assertEqual(third["state"], "COMPLETE")
            self.assertEqual(third["pending_count"], 0)
            self.assertEqual([row["plan_id"] for row in third["plans"]], [
                "alpha-en", "beta-en", "gamma-en",
            ])
            self.assertEqual(replay["state"], "COOLDOWN")

    def test_failed_official_discovery_retries_after_bounded_backoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            (root / "config" / "source-plans").mkdir(parents=True)
            state = Path(directory) / "state"
            with mock.patch.object(MODULE, "run_adapter", side_effect=MODULE.CaptureError("offline")):
                first = MODULE.refresh_all(root, state, now=1000, disk_floor_bytes=1)
            self.assertEqual(first["discovery_state"], "FAILED")
            with mock.patch.object(MODULE, "run_adapter", side_effect=AssertionError("retried today")):
                second = MODULE.discover_official_plan(root, state, now=1001)
            self.assertEqual(second["state"], "DEFERRED")
            with mock.patch.object(MODULE, "run_adapter", side_effect=MODULE.CaptureError("still offline")):
                with self.assertRaises(MODULE.CaptureError):
                    MODULE.discover_official_plan(root, state, now=2800)

    def test_failed_plan_retries_after_cooldown_not_every_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            plans = root / "config" / "source-plans"
            plans.mkdir(parents=True)
            (plans / "alpha-en.json").write_text(json.dumps({
                "schema_version": 1, "plan_id": "alpha-en", "locale": "en", "sources": [],
            }))
            state = Path(directory) / "state"
            with (mock.patch.object(MODULE, "discover_official_plan", return_value={"state": "COOLDOWN"}),
                  mock.patch.object(MODULE, "capture", side_effect=MODULE.CaptureError("upstream")) as capture):
                first = MODULE.refresh_all(root, state, now=1000, disk_floor_bytes=1)
                cooldown = MODULE.refresh_all(root, state, now=1001, disk_floor_bytes=1)
                retry = MODULE.refresh_all(root, state, now=1000 + 86400, disk_floor_bytes=1)
            self.assertEqual(first["state"], "PARTIAL")
            self.assertEqual(cooldown["state"], "COOLDOWN")
            self.assertEqual(retry["state"], "PARTIAL")
            self.assertEqual(capture.call_count, 2)

    def test_old_partial_receipt_starts_bounded_cycle_without_daily_stall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            plans = root / "config" / "source-plans"
            plans.mkdir(parents=True)
            for plan_id in ("alpha-en", "beta-en"):
                (plans / f"{plan_id}.json").write_text(json.dumps({
                    "schema_version": 1, "plan_id": plan_id, "locale": "en", "sources": [],
                }))
            state = Path(directory) / "state"
            state.mkdir()
            (state / "source-refresh.json").write_text(json.dumps({
                "schema_version": 1, "receipt_type": "SOURCE_REFRESH",
                "state": "PARTIAL", "completed_at": 1000,
                "plan_set_sha256": MODULE.plan_set_sha256(root, state),
                "plans": [{"plan_id": "alpha-en", "state": "FAILED"}],
            }))
            with (mock.patch.object(MODULE, "discover_official_plan", return_value={"state": "COOLDOWN"}),
                  mock.patch.object(MODULE, "capture", return_value=[])):
                result = MODULE.refresh_all(root, state, now=1001, disk_floor_bytes=1)
            self.assertEqual(result["state"], "IN_PROGRESS")
            self.assertEqual([row["plan_id"] for row in result["plans"]], ["alpha-en"])
            self.assertEqual(result["pending_count"], 1)


if __name__ == "__main__":
    unittest.main()
