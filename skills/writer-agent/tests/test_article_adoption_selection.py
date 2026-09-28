from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).parents[1] / "scripts" / "article_adoption_selection.py"
SPEC = importlib.util.spec_from_file_location("article_adoption_selection", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _generation_run(root: Path, run_id: str, status: str = "quality-repair-ready") -> Path:
    run = root / "runs" / run_id
    (run / "gates").mkdir(parents=True)
    (run / "gates/generation-state.json").write_text(
        json.dumps({"run_id": run_id, "status": status}), encoding="utf-8"
    )
    (run / "article-daily-prompt.txt").write_text("prompt", encoding="utf-8")
    return run


class ArticleAdoptionSelectionTest(unittest.TestCase):
    def test_completed_publication_does_not_re_adopt_generation_only_marker(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _generation_run(root, "20260901-210011")
            complete = _generation_run(root, "20260917-112542")
            state = {
                "publication_contract": "active-four",
                "pairs": {
                    pair: {
                        "status": "live",
                        "receipt": {"live_url": f"https://example.test/{pair}"},
                    }
                    for pair in ("note/ja", "substack/ja", "substack/en", "x-article/ja")
                },
            }
            (complete / "gates/publication-state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            ledger = root / "articles.jsonl"
            ledger.write_text(
                json.dumps({"run_id": "20260901-210011"}) + "\n"
                + json.dumps({"run_id": "20260917-112542"}) + "\n",
                encoding="utf-8",
            )

            self.assertIsNone(MODULE.select(root, ledger, {"action": "new"}))

    def test_single_generation_candidate_remains_adoptable_without_terminal_run(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _generation_run(root, "20260901-210011")
            ledger = root / "articles.jsonl"
            ledger.write_text(
                json.dumps({"run_id": "20260901-210011"}) + "\n",
                encoding="utf-8",
            )

            self.assertEqual(
                MODULE.select(root, ledger, {"action": "new"}),
                "20260901-210011",
            )

    def test_selected_publication_state_is_left_to_publication_planner(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = _generation_run(root, "20260918-135644", "provider-failed-ambiguous")
            (run / "gates/publication-state.json").write_text(
                json.dumps(
                    {
                        "publication_contract": "active-four",
                        "run_id": run.name,
                        "pairs": {
                            "note/ja": {"status": "unavailable"},
                            "substack/ja": {"status": "intent"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            ledger = root / "articles.jsonl"
            ledger.write_text("", encoding="utf-8")

            self.assertIsNone(
                MODULE.select(root, ledger, {"run_id": run.name, "action": "resume"})
            )

    def test_permanently_unavailable_x_article_does_not_keep_run_adoptable(self) -> None:
        """Dais 2026-09-29: x-editor-unreachable on run 20260928-132912 left three
        live receipts (note/substack ja/en) plus one permanently unreachable X
        Article editor reading as an open obligation forever. A skip_receipt on
        the unavailable pair must close the run for adoption purposes exactly
        like a fully-live run does, so a brand-new day's run is never treated
        as unfinished business belonging to an old, already-published run."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _generation_run(root, "20260901-210011")
            complete = _generation_run(
                root, "20260928-132912", status="provider-failed-ambiguous"
            )
            state = {
                "publication_contract": "active-four",
                "pairs": {
                    **{
                        pair: {
                            "status": "live",
                            "receipt": {"live_url": f"https://example.test/{pair}"},
                        }
                        for pair in ("note/ja", "substack/ja", "substack/en")
                    },
                    "x-article/ja": {
                        "status": "unavailable",
                        "error": "x-editor-unreachable:no-editor",
                        "skip_receipt": {
                            "type": "permanent-unavailable",
                            "pair": "x-article/ja",
                            "reason": "x-editor-unreachable:no-editor",
                            "slo": "not-applicable",
                            "recorded_at": "2026-09-28T13:43:44Z",
                        },
                    },
                },
            }
            (complete / "gates/publication-state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            ledger = root / "articles.jsonl"
            ledger.write_text(
                json.dumps({"run_id": "20260901-210011"}) + "\n"
                + json.dumps({"run_id": "20260928-132912"}) + "\n",
                encoding="utf-8",
            )

            self.assertIsNone(MODULE.select(root, ledger, {"action": "new"}))
