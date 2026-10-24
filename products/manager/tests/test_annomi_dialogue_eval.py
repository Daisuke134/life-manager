"""Synthetic contract tests for the aggregate-only AnnoMI research evaluator."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "products/manager/manager_core"))

import annomi_dialogue_eval as evaluation  # noqa: E402


def synthetic_rows(video_count: int = 30) -> list[dict[str, str]]:
    therapist_labels = ["question", "reflection", "therapist_input", "other"]
    client_labels = ["change", "neutral", "sustain"]
    rows: list[dict[str, str]] = []
    for video in range(video_count):
        video_id = f"private_video_{video:03d}"
        for utterance, label in enumerate(therapist_labels):
            rows.append({
                "transcript_id": f"private_transcript_{video:03d}",
                "utterance_id": f"t_{utterance}",
                "video_url": f"https://www.youtube.com/watch?v={video_id}&t={utterance}",
                "interlocutor": "therapist",
                "utterance_text": f"SYNTHETIC_PRIVATE_THERAPIST_TOKEN_{label} example {video} {utterance}",
                "main_therapist_behaviour": label,
                "client_talk_type": "n/a",
            })
        for utterance, label in enumerate(client_labels):
            rows.append({
                "transcript_id": f"private_transcript_{video:03d}",
                "utterance_id": f"c_{utterance}",
                "video_url": f"https://www.youtube.com/watch?v={video_id}&t={utterance + 10}",
                "interlocutor": "client",
                "utterance_text": f"SYNTHETIC_PRIVATE_CLIENT_TOKEN_{label} example {video} {utterance}",
                "main_therapist_behaviour": "n/a",
                "client_talk_type": label,
            })
    return rows


class AnnoMIDialogueEvaluationTests(unittest.TestCase):
    def test_video_group_key_ignores_timestamp_query(self):
        key_a = evaluation._video_group_key("https://www.youtube.com/watch?v=abc123&t=10")
        key_b = evaluation._video_group_key("https://www.youtube.com/watch?v=abc123&t=999")
        self.assertEqual(key_a, key_b)

    def test_vimeo_group_key_ignores_query_and_is_platform_scoped(self):
        key_a = evaluation._video_group_key("https://vimeo.com/12345678")
        key_b = evaluation._video_group_key("https://www.vimeo.com/12345678?h=private")
        youtube_key = evaluation._video_group_key("https://www.youtube.com/watch?v=12345678")
        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, youtube_key)

    def test_rejects_unsupported_video_reference_without_echoing_input(self):
        with self.assertRaises(evaluation.AnnoMIEvaluationError) as caught:
            evaluation._video_group_key("private://secret-video-identifier")
        self.assertEqual(str(caught.exception), "INVALID_VIDEO_REFERENCE")

    def test_csv_digest_mismatch_fails_before_parsing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source.csv"
            path.write_text("not,a,valid,source\n", encoding="utf-8")
            with self.assertRaises(evaluation.AnnoMIEvaluationError) as caught:
                evaluation.evaluate_csv(path, expected_sha256="0" * 64)
        self.assertEqual(str(caught.exception), "SOURCE_HASH_MISMATCH")

    def test_cli_does_not_echo_private_input_path(self):
        private_path = "/private/path/ANNOMI_SECRET_INPUT.csv"
        cli = REPO_ROOT / "products/manager/scripts/evaluate_annomi_dialogue.py"
        completed = subprocess.run(
            [sys.executable, "-S", str(cli), "--input", private_path],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "ERROR SOURCE_UNAVAILABLE\n")
        self.assertNotIn(private_path, completed.stdout + completed.stderr)

    @unittest.skipUnless(
        importlib.util.find_spec("numpy") is not None
        and importlib.util.find_spec("sklearn") is not None,
        "optional NumPy/scikit-learn research dependencies are unavailable",
    )
    def test_grouped_evaluation_is_aggregate_only_and_covers_each_row_once(self):
        rows = synthetic_rows()
        result = evaluation.evaluate_rows(rows, n_splits=5, bootstrap_resamples=100, seed=17)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["split"]["n_folds"], 5)
        self.assertEqual(result["split"]["grouping_unit"], "normalized_source_video")
        self.assertEqual(result["split"]["cross_fold_group_leaks"], 0)
        self.assertEqual(result["tasks"]["therapist"]["assigned"], 120)
        self.assertEqual(result["tasks"]["client"]["assigned"], 90)
        for task in result["tasks"].values():
            self.assertEqual(task["attempted"], task["assigned"])
            self.assertEqual(task["valid"], task["assigned"])
            self.assertEqual(task["invalid"], 0)
            self.assertEqual(task["not_run"], 0)
        serialized = json.dumps(result, sort_keys=True)
        self.assertNotIn("SYNTHETIC_PRIVATE", serialized)
        self.assertNotIn("private_video_", serialized)
        self.assertNotIn("private_transcript_", serialized)


if __name__ == "__main__":
    unittest.main()
