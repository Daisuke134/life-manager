import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from article_adoption_selection import select  # noqa: E402
from article_generation_state import _failed_before_publication  # noqa: E402


def _state(boundary):
    return {"status": "provider-failed-ambiguous",
            "attempts": [{"return_code": 1, "boundary": boundary}]}


class BoundaryAllowlistTest(unittest.TestCase):
    def test_model_card_copy_and_empty_lock_stay_retryable(self):
        # run 20260928-210313: provider failed after copying its card; no draft, no effect.
        self.assertTrue(_failed_before_publication(_state(
            "generated-or-staged-artifacts:.publication-state.json.lock,gates/claimed-card.md")))
        self.assertTrue(_failed_before_publication(_state("prepublication-empty")))

    def test_drafts_still_block_retry(self):
        self.assertFalse(_failed_before_publication(_state(
            "generated-or-staged-artifacts:article-ja.md,gates/claimed-card.md")))

    def test_resume_generation_is_not_sent_to_draft_adoption(self):
        self.assertIsNone(select(Path("/nonexistent"), Path("/nonexistent"),
                                 {"action": "resume-generation", "run_id": "20260928-210313"}))


if __name__ == "__main__":
    unittest.main()
