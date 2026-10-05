import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import writer_learning_worker  # noqa: E402


class ReadyCanaryPendingTest(unittest.TestCase):
    def test_ready_assignment_waits_without_changing_candidate_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill_dir = Path(temporary) / "skill"
            state_dir = skill_dir / "state"
            learning_dir = state_dir / "learning"
            strategy_dir = learning_dir / "strategies"
            experiment_id = "existing-canary"
            candidate = b'{"headline_style":"reader-first"}\n'
            candidate_hash = hashlib.sha256(candidate).hexdigest()
            assignment_path = learning_dir / "canary-assignment.json"
            strategy_path = strategy_dir / f"{candidate_hash}.json"
            assignment = {
                "schema_version": 2,
                "status": "READY",
                "experiment_id": experiment_id,
                "candidate_strategy_sha256": candidate_hash,
                "baseline_run_id": "baseline-run",
                "reader_job": "help readers choose a topic",
                "changed_field": "headline_style",
                "before": "generic",
                "after": "reader-first",
                "hypothesis": "A clear reader outcome improves usefulness.",
                "canary_contract": {
                    "platform": "fixture",
                    "price": 0,
                    "currency": "USD",
                    "reader_job": "help readers choose a topic",
                    "window_hours": 24,
                },
            }
            assignment_bytes = (
                json.dumps(assignment, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            assignment_path.parent.mkdir(parents=True)
            strategy_path.parent.mkdir(parents=True)
            assignment_path.write_bytes(assignment_bytes)
            strategy_path.write_bytes(candidate)
            experiment_dir = learning_dir / "experiments" / experiment_id
            manifest_bytes = b'{"experiment_id":"existing-canary","status":"REPLAYED"}\n'
            experiment_dir.mkdir(parents=True)
            (experiment_dir / "manifest.json").write_bytes(manifest_bytes)
            before = {
                path.relative_to(state_dir): path.read_bytes()
                for path in state_dir.rglob("*")
                if path.is_file()
            }

            with patch.dict(os.environ, {"ARTICLE_STATE_DIR": str(state_dir)}):
                result = writer_learning_worker.close_canary(
                    skill_dir, now=datetime(2026, 10, 5, tzinfo=timezone.utc)
                )

            self.assertEqual(
                result,
                {"status": "AWAITING_MATCHED_CANARY", "experiment_id": experiment_id},
            )
            after = {
                path.relative_to(state_dir): path.read_bytes()
                for path in state_dir.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertEqual(assignment_path.read_bytes(), assignment_bytes)
            self.assertEqual(strategy_path.read_bytes(), candidate)


if __name__ == "__main__":
    unittest.main()
