from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).parents[1] / "scripts" / "publication_resume.py"
SPEC = importlib.util.spec_from_file_location("publication_resume_initialization_boundary", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _state(tmp_path: Path) -> tuple[MODULE.PublicationStore, dict]:
    run = tmp_path / "runs" / "daily-2026-09-17"
    gates = run / "gates"
    gates.mkdir(parents=True)
    state_path = gates / "publication-state.json"
    ledger_path = tmp_path / "articles.jsonl"
    pairs = {
        "substack/ja": {
            "platform": "substack",
            "lang": "ja",
            "target_kind": "substack-draft-id",
            "target": "123",
            "status": "intent",
        },
        "substack/en": {
            "platform": "substack",
            "lang": "en",
            "target_kind": "substack-draft-id",
            "target": "456",
            "status": "intent",
        },
    }
    for pair in MODULE.DORMANT_PAIRS:
        pairs[pair] = {
            "platform": pair.split("/", 1)[0],
            "lang": pair.split("/", 1)[1],
            "status": "skipped",
            "skip_receipt": {
                "type": "dormant-destination",
                "pair": pair,
                "reason": "dormant-destination",
                "slo": "not-applicable",
                "recorded_at": "2026-09-17T00:00:00Z",
            },
        }
    state = {
        "version": 1,
        "publication_contract": "active-four",
        "run_id": "20260917-112542",
        "run_dir": str(run),
        "state_path": str(state_path),
        "ledger_path": str(ledger_path),
        "topic_id": "topic-1",
        "safety_status": "ALLOW",
        "destination_identities": {
            "note/ja": "writer-note",
            "zenn-article/ja": "writer-zenn",
            "devto/en": "writer-devto",
            "substack/ja": "writer-ja.substack.com",
            "substack/en": "writer-en.substack.com",
            "x-article/ja": "writer-x",
            "x-article/en": "writer-x",
            "x-post/ja": "writer-x",
        },
        "drafts": {
            "ja": {"path": str(run / "article-ja.md"), "sha256": "0" * 64},
            "en": {"path": str(run / "article-en.md"), "sha256": "0" * 64},
        },
        "pairs": pairs,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return MODULE.PublicationStore(state_path, ledger_path), state


def _pending_row(payload: dict, **updates: object) -> dict:
    row = {
        "run_id": payload["run_id"],
        "topic_id": payload["topic_id"],
        "platform": "note",
        "lang": "ja",
        "draft_url": None,
        "state": "pending:required-headline-media-api-key-unavailable; identity-judge-no-json",
        "verified_logged_in": False,
        "published": False,
        "live_url": None,
        "public_id": None,
        "receipt": None,
        "published_at": None,
        "reality_gate": None,
        "topic": "topic",
        "topic_source": "paid-demand",
        "editorial_form": "comparison",
    }
    row.update(updates)
    return row


class PublicationInitializationBoundaryTest(unittest.TestCase):
    def test_effect_free_pending_preflight_row_does_not_block_initialization(self) -> None:
        with TemporaryDirectory() as tmp:
            store, state = _state(Path(tmp))
            store._validate_state_boundary_locked = lambda *_args, **_kwargs: None
            store._drafts_intact = lambda _state: True
            store._ledger_rows_locked = lambda: [_pending_row(state)]

            plan = store.initialization_plan()

            self.assertTrue(plan["initializable"])
            self.assertEqual(plan["initialization_pairs"], ["note/ja", "x-article/ja"])

    def test_existing_targeted_draft_row_does_not_block_initialization(self) -> None:
        with TemporaryDirectory() as tmp:
            store, state = _state(Path(tmp))
            state["pairs"]["substack/ja"]["target"] = "123"
            store._validate_state_boundary_locked = lambda *_args, **_kwargs: None
            store._drafts_intact = lambda _state: True
            store._ledger_rows_locked = lambda: [
                _pending_row(
                    state,
                    platform="substack",
                    lang="ja",
                    state="staged:authenticated-editor-own-eyes; render-verify-pass",
                    draft_url="https://writer-ja.substack.com/publish/post/123",
                    verified_logged_in=True,
                ),
                _pending_row(
                    state,
                    platform="substack",
                    lang="en",
                    state="pending:authenticated-editor-redirect-loop; render-verify-screenshot-failed",
                    draft_url="https://writer-en.substack.com/publish/post/456",
                ),
            ]

            plan = store.initialization_plan()

            self.assertTrue(plan["initializable"])

    def test_targeted_draft_row_with_conflicting_target_still_blocks(self) -> None:
        with TemporaryDirectory() as tmp:
            store, state = _state(Path(tmp))
            store._validate_state_boundary_locked = lambda *_args, **_kwargs: None
            store._drafts_intact = lambda _state: True
            store._ledger_rows_locked = lambda: [
                _pending_row(
                    state,
                    platform="substack",
                    lang="ja",
                    state="staged:authenticated-editor-own-eyes",
                    draft_url="https://writer-ja.substack.com/publish/post/999",
                    verified_logged_in=True,
                )
            ]

            plan = store.initialization_plan()

            self.assertFalse(plan["initializable"])
            self.assertEqual(plan["reason"], "run-ledger-boundary-exists")

    def test_pending_row_with_effect_signal_still_blocks_initialization(self) -> None:
        for updates in (
            {"state": "pending:published-effect-unknown"},
            {"live_url": "https://note.com/writer-note/n/abcd"},
            {"effect": "unknown"},
        ):
            with self.subTest(updates=updates), TemporaryDirectory() as tmp:
                store, state = _state(Path(tmp))
                store._validate_state_boundary_locked = lambda *_args, **_kwargs: None
                store._drafts_intact = lambda _state: True
                store._ledger_rows_locked = lambda: [_pending_row(state, **updates)]

                plan = store.initialization_plan()

                self.assertFalse(plan["initializable"])
                self.assertEqual(plan["reason"], "run-ledger-boundary-exists")
