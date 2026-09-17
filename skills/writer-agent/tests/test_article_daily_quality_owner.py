import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = str(ROOT / "skills/writer-agent/scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


START = load(
    "article_daily_start_control_quality_owner",
    ROOT / "skills/writer-agent/scripts/article_daily_start_control.py",
)
GENERATION = load(
    "article_generation_state_quality_owner",
    ROOT / "skills/writer-agent/scripts/article_generation_state.py",
)


class ArticleDailyQualityOwnerTest(unittest.TestCase):
    @staticmethod
    def make_adopted(root: Path):
        run_id = "daily-2026-08-21"
        run = root / "runs" / run_id
        gates = run / "gates"
        gates.mkdir(parents=True)
        prompt = run / "article-daily-prompt.txt"
        prompt.write_text("immutable prompt\n", encoding="utf-8")
        ledger = root / "articles.jsonl"
        ledger.write_text("", encoding="utf-8")
        state = GENERATION.initialize(run, run_id, prompt, ledger)
        state["status"] = "provider-failed-ambiguous"
        state["attempts"] = [{
            "attempt": 1,
            "status": "provider-failed-ambiguous",
            "return_code": 1,
            "boundary": "generated-or-staged-artifacts:article-ja.md",
        }]
        (gates / "generation-state.json").write_text(
            json.dumps(state) + "\n", encoding="utf-8"
        )
        (run / "article-ja.md").write_text("日本語 draft\n", encoding="utf-8")
        (run / "article-en.md").write_text("English draft\n", encoding="utf-8")
        GENERATION.adopt_prepublication(run, run_id, prompt, ledger)
        return run, ledger

    def test_staged_adoption_without_quality_receipt_returns_to_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, ledger = self.make_adopted(root)
            with patch.object(START, "proof", side_effect=START.QuarantineError("no proof")):
                decision = START.decide(root, "2026-08-21")
            self.assertEqual(
                decision,
                {
                    "action": "resume-generation",
                    "run_id": run.name,
                    "reason": "same-jst-day-prepublication-provider-failure",
                },
            )

            (run / "gates/prepublication-adoption.json").unlink()
            with patch.object(START, "proof", side_effect=START.QuarantineError("no proof")):
                decision = START.decide(root, "2026-08-21")
            self.assertEqual(
                decision,
                {
                    "action": "block-incomplete",
                    "run_id": run.name,
                    "reason": "same-jst-day-unclassified-run",
                },
            )

    def test_quality_receipt_keeps_quality_repair_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, ledger = self.make_adopted(root)
            state_path = run / "gates/generation-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["status"] = "provider-failed-ambiguous"
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
            (run / "gates/prepublication-adoption.json").unlink()
            (run / "gates/quality-self-heal.json").write_text(
                '{"version":2,"action":"block_freeze"}\n', encoding="utf-8"
            )
            GENERATION.adopt_prepublication(
                run, run.name, run / "article-daily-prompt.txt", ledger
            )
            with patch.object(START, "proof", side_effect=START.QuarantineError("no proof")):
                decision = START.decide(root, "2026-08-21")
            self.assertEqual(
                decision,
                {
                    "action": "skip-pending-worker",
                    "run_id": run.name,
                    "reason": "same-jst-day-owned-by-quality-repair",
                },
            )


if __name__ == "__main__":
    unittest.main()
