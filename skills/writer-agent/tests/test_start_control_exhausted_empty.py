import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from article_daily_start_control import decide  # noqa: E402


def _run(root: Path, run_id: str, attempts: int, extra: str | None = None,
         status: str = "provider-failed-ambiguous", return_code: int = 1) -> None:
    run = root / "runs" / run_id
    (run / "gates").mkdir(parents=True)
    (run / "article-daily-prompt.txt").write_text("prompt")
    (run / "gates" / "claimed-card.md").write_text("card")
    state = {"version": 1, "run_id": run_id, "status": status,
             "maximum_attempts": 3,
             "attempts": [{"attempt": i + 1, "status": status,
                           "return_code": return_code, "boundary": "prepublication-empty"}
                          for i in range(attempts)]}
    (run / "gates" / "generation-state.json").write_text(json.dumps(state))
    if extra:
        (run / extra).write_text("draft")


class ExhaustedEmptyProviderFailureTest(unittest.TestCase):
    def _decide(self, attempts, extra=None, **state):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "articles.jsonl").write_text("")
            _run(root, "20260928-210313", attempts, extra, **state)
            return decide(root, "2026-09-29")

    def test_exhausted_empty_run_releases_a_new_run(self):
        result = self._decide(3)
        self.assertEqual(result["action"], "new")
        self.assertEqual(result["reason"], "same-jst-day-exhausted-empty-provider-failure")

    def test_run_with_a_draft_but_no_dispatch_releases_a_new_run(self):
        # 2026-10-17: a draft without publication-state or dispatch never left the machine.
        self.assertEqual(self._decide(3, "article-ja.md")["action"], "new")

    def test_exhausted_empty_provider_returned_run_releases_a_new_run(self):
        # PR #8249: a completed agent pass now exits rc=0 (provider-returned)
        # instead of the old silent rc=1; an empty day must still roll over.
        result = self._decide(3, status="provider-returned", return_code=0)
        self.assertEqual(result["action"], "new")

    def test_provider_returned_with_publication_state_stays_blocked(self):
        self.assertNotEqual(self._decide(3, "gates/publication-state.json",
                                         status="provider-returned", return_code=0)["action"], "new")

    def test_run_with_publication_state_stays_blocked(self):
        self.assertNotEqual(self._decide(3, "gates/publication-state.json")["action"], "new")


if __name__ == "__main__":
    unittest.main()
