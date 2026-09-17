from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).parents[1] / "scripts" / "article_pending.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("article_pending_complete", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ArticlePendingCompleteTest(unittest.TestCase):
    def test_completed_run_is_not_reported_as_invalid_incomplete(self) -> None:
        import publication_resume

        with TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "state"
            run_dir = state_root / "runs" / "20260917-112542"
            gates = run_dir / "gates"
            gates.mkdir(parents=True)
            state = {
                "run_id": run_dir.name,
                "created_at": "2026-09-17T13:17:32+00:00",
                "publication_contract": "active-four",
                "run_dir": str(run_dir),
            }
            (gates / "publication-state.json").write_text(json.dumps(state), encoding="utf-8")

            class FakeStore:
                def __init__(self, *_args: object) -> None:
                    pass

                def worker_plan(self) -> dict:
                    return {"resumable": False, "reason": "all-complete"}

                def initialization_plan(self) -> dict:
                    raise AssertionError("completed runs must not enter initialization")

                def read(self) -> dict:
                    return state

            original = publication_resume.PublicationStore
            publication_resume.PublicationStore = FakeStore
            try:
                result = MODULE.plan_oldest(
                    state_root, datetime.fromisoformat("2026-09-18T00:00:00+09:00")
                )
            finally:
                publication_resume.PublicationStore = original

            self.assertEqual(result, {"status": "IDLE", "reason": "no-valid-incomplete-run"})

    def test_historical_invalid_run_is_idle_with_repair_metadata(self) -> None:
        import publication_resume

        with TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "state"
            run_dir = state_root / "runs" / "20260917-112542"
            gates = run_dir / "gates"
            gates.mkdir(parents=True)
            state = {
                "run_id": run_dir.name,
                "created_at": "2026-09-17T13:17:32+00:00",
                "publication_contract": "active-four",
                "run_dir": str(run_dir),
            }
            (gates / "publication-state.json").write_text(json.dumps(state), encoding="utf-8")

            class FakeStore:
                def __init__(self, *_args: object) -> None:
                    pass

                def worker_plan(self) -> dict:
                    return {"resumable": False, "reason": "invalid-state"}

                def initialization_plan(self) -> dict:
                    return {"initializable": False, "reason": "historical-invalid"}

                def read(self) -> dict:
                    return state

            original = publication_resume.PublicationStore
            publication_resume.PublicationStore = FakeStore
            try:
                result = MODULE.plan_oldest(
                    state_root, datetime.fromisoformat("2026-09-18T00:00:00+09:00")
                )
            finally:
                publication_resume.PublicationStore = original

            self.assertEqual(result["status"], "IDLE")
            self.assertEqual(result["reason"], "no-valid-incomplete-run")
            self.assertEqual(
                result["blocked_runs"],
                [{"run_id": "20260917-112542", "reason": "historical-invalid"}],
            )
