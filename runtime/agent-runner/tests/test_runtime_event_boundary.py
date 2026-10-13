import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "runtime/agent-runner"))

from agent_runner import (  # noqa: E402
    attach_runtime_event,
    emit_runtime_event,
    runtime_event_loop_id,
    runtime_registry_path,
)


class RuntimeEventBoundaryTest(unittest.TestCase):
    def test_managed_parent_loop_id_overrides_legacy_child_alias(self):
        with mock.patch.dict(
            os.environ,
            {"LIFE_MANAGER_LOOP_ID": "hf-gig-storefront-direct"},
        ):
            self.assertEqual(
                runtime_event_loop_id("gig-storefront"),
                "hf-gig-storefront-direct",
            )

    def test_unmanaged_invocation_keeps_requested_loop_id(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runtime_event_loop_id("standalone-loop"), "standalone-loop")

    def test_staged_runner_uses_loaded_release_registry(self):
        with mock.patch.dict(os.environ, {
            "LIFE_MANAGER_REPO": "/loops/releases/current-sha",
        }, clear=True):
            self.assertEqual(
                runtime_registry_path(),
                Path("/loops/releases/current-sha/config/loop-registry.json"),
            )

    def test_final_runner_summary_emits_one_registry_grounded_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            registry = root / "registry.json"
            registry.write_text(json.dumps({"schema_version": 2, "loops": {"example": {
                "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example.sh",
                "cadence": {"run_at_load": True}, "effect_class": "application",
                "state_root": "~/state", "log_root": "~/state/logs",
                "cleanup": {"max_runs": 10, "max_age_days": 7},
                "provider_route": "shared-agent-runner",
            }}}))
            with mock.patch.dict(os.environ, {"HOME": directory}):
                event = emit_runtime_event(
                    loop_id="example", evidence_dir=root / "private evidence path",
                    selected={"provider": "codex"}, attempts=[], candidate_profile="acct2",
                    registry_path=registry, release_sha="b" * 40,
                )
            rows = (state / "events.jsonl").read_text().splitlines()
            self.assertEqual(len(rows), 1)
            self.assertEqual(event["effect_status"], "unknown")
            self.assertNotIn(str(root), rows[0])

    def test_attached_summary_binds_child_event_to_parent_article_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            registry = root / "registry.json"
            registry.write_text(json.dumps({"schema_version": 2, "loops": {"article-daily": {
                "label": "ai.anicca.article-daily", "domain": "content",
                "entrypoint": "skills/writer-agent/article-daily.sh",
                "cadence": {"run_at_load": True}, "effect_class": "publish",
                "state_root": "~/state", "log_root": "~/state/logs",
                "cleanup": {"max_runs": 10, "max_age_days": 7},
                "provider_route": "shared-agent-runner",
            }}}))
            summary = {"status": "success"}
            env = {
                "HOME": directory,
                "LIFE_MANAGER_LOOP_ID": "article-daily",
                "LIFE_MANAGER_RUN_ID": "lifecycle-run-1",
                "LIFE_MANAGER_OCCURRENCE_ID": "article-daily:lifecycle-run-1",
                "ARTICLE_RUN_ID": "20261013-121111",
            }
            with mock.patch.dict(os.environ, env, clear=True):
                attached = attach_runtime_event(
                    summary=summary,
                    loop_id="article-daily",
                    evidence_dir=root / "child-evidence",
                    selected={"provider": "codex", "profile_alias": "acct2"},
                    attempts=[],
                    registry_path=registry,
                    release_sha="b" * 40,
                )
            self.assertTrue(attached)
            event = json.loads((state / "events.jsonl").read_text().splitlines()[0])
            for field in ("owner_id", "run_id", "occurrence_id", "release_sha"):
                self.assertEqual(summary[field], event[field])
            self.assertEqual(summary["parent_lifecycle_run_id"], "lifecycle-run-1")
            self.assertEqual(
                summary["parent_lifecycle_occurrence_id"],
                "article-daily:lifecycle-run-1",
            )
            self.assertEqual(summary["parent_article_run_id"], "20261013-121111")

    def test_observability_write_failure_does_not_reverse_success(self):
        summary = {"status": "success"}
        with mock.patch("agent_runner.emit_runtime_event", side_effect=PermissionError(
            "immutable release",
        )):
            attached = attach_runtime_event(
                summary=summary,
                loop_id="example",
                evidence_dir=Path("/tmp/evidence"),
                selected={"provider": "codex", "profile_alias": "acct2"},
                attempts=[],
                registry_path=Path("/immutable/config/loop-registry.json"),
                release_sha="b" * 40,
            )
        self.assertFalse(attached)
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["runtime_event_error"], "immutable release")


if __name__ == "__main__":
    unittest.main()
