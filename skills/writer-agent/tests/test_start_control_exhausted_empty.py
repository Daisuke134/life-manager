import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from article_daily_start_control import decide  # noqa: E402


def _run(root: Path, run_id: str, attempts: int, extra: str | None = None) -> None:
    run = root / "runs" / run_id
    (run / "gates").mkdir(parents=True)
    (run / "article-daily-prompt.txt").write_text("prompt")
    (run / "gates" / "claimed-card.md").write_text("card")
    state = {"version": 1, "run_id": run_id, "status": "provider-failed-ambiguous",
             "maximum_attempts": 3,
             "attempts": [{"attempt": i + 1, "status": "provider-failed-ambiguous",
                           "return_code": 1, "boundary": "prepublication-empty"}
                          for i in range(attempts)]}
    (run / "gates" / "generation-state.json").write_text(json.dumps(state))
    if extra:
        (run / extra).write_text("draft")


class ExhaustedEmptyProviderFailureTest(unittest.TestCase):
    def _decide(self, attempts, extra=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "articles.jsonl").write_text("")
            _run(root, "20260928-210313", attempts, extra)
            return decide(root, "2026-09-29")

    def test_exhausted_empty_run_releases_a_new_run(self):
        result = self._decide(3)
        self.assertEqual(result["action"], "new")
        self.assertEqual(result["reason"], "same-jst-day-exhausted-empty-provider-failure")

    def test_run_with_a_draft_stays_blocked(self):
        self.assertNotEqual(self._decide(3, "article-ja.md")["action"], "new")


if __name__ == "__main__":
    unittest.main()
