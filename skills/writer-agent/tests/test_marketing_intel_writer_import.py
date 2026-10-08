#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


IMPORTER = Path(__file__).resolve().parents[1] / "scripts" / "import_marketing_intel.py"


class MarketingIntelWriterImportTests(unittest.TestCase):
    def test_imports_only_open_cited_content_tactics_once_across_topic_stages(self):
        self.assertTrue(IMPORTER.is_file(), "Marketing Intel importer is not connected to Writer")
        daily = (Path(__file__).resolve().parents[1] / "article-daily.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/import_marketing_intel.py", daily)
        self.assertLess(daily.index("topic_state.py"), daily.index("scripts/import_marketing_intel.py"))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            writer_skill = root / "skills" / "writer-agent"
            intel = root / "skills" / "earn" / "marketing-engine" / "intel"
            intel.mkdir(parents=True)
            writer_skill.mkdir(parents=True)
            state = root / "writer-state"
            queue = state / "topics" / "queue"
            queue.mkdir(parents=True)
            older = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            (queue / "existing-topic.md").write_text(
                f'---\ncreated: "{older}"\n---\nExisting Writer topic.\n', encoding="utf-8"
            )

            tactics = [
                {
                    "id": "tactic.content-first-product.v1",
                    "claim": "Validate the creative promise before expanding the product.",
                    "mechanism": "This may reduce wasted build effort.",
                    "applies_to": ["app", "content"],
                    "testable": True,
                    "status": "new",
                    "source_url": None,
                    "evidence_url": None,
                },
                {
                    "id": "tactic.scene-first-copywriting.v1",
                    "claim": "Begin with the moment before the reader needs the product.",
                    "mechanism": "A recognizable scene may earn continuation.",
                    "applies_to": ["content"],
                    "testable": True,
                    "status": "queued",
                    "source_url": "https://x.com/3Imzdo3/status/2084572547761463412",
                    "evidence_url": None,
                },
                {
                    "id": "tactic.creator-outreach.v1",
                    "claim": "Use a research identity to find creators.",
                    "applies_to": ["outreach"],
                    "testable": True,
                    "status": "new",
                    "source_url": "https://x.com/example/status/2",
                    "evidence_url": None,
                },
                {
                    "id": "tactic.content-missing-source.v1",
                    "claim": "An uncited content claim.",
                    "applies_to": ["content"],
                    "testable": True,
                    "status": "new",
                    "source_url": None,
                    "evidence_url": None,
                },
                {
                    "id": "tactic.content-already-done.v1",
                    "claim": "A completed content claim.",
                    "applies_to": ["content"],
                    "testable": True,
                    "status": "done",
                    "source_url": "https://x.com/example/status/4",
                    "evidence_url": None,
                },
            ]
            (intel / "playbook.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in tactics), encoding="utf-8"
            )
            (intel / "source-enrichments.jsonl").write_text(
                json.dumps(
                    {
                        "tactic_id": "tactic.content-first-product.v1",
                        "source_url": "https://x.com/GeorgeLampro20/status/2081979523873038368",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            def run_import():
                result = subprocess.run(
                    [
                        sys.executable,
                        str(IMPORTER),
                        "--skill-dir",
                        str(writer_skill),
                        "--state-dir",
                        str(state),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return json.loads(result.stdout)

            first = run_import()
            self.assertEqual(len(first["imported"]), 1)
            card = state / "topics" / "queue" / first["imported"][0]
            content = card.read_text(encoding="utf-8")
            self.assertIn("tactic.content-first-product.v1", content)
            self.assertIn("https://x.com/GeorgeLampro20/status/2081979523873038368", content)
            self.assertIn("tactic.scene-first-copywriting.v1", content)
            self.assertIn("https://x.com/3Imzdo3/status/2084572547761463412", content)
            self.assertNotIn("tactic.creator-outreach.v1", content)
            self.assertNotIn("tactic.content-missing-source.v1", content)
            self.assertNotIn("tactic.content-already-done.v1", content)

            selector = Path(__file__).resolve().parents[1] / "scripts" / "select-next-topic.sh"
            selected = subprocess.run(
                ["bash", str(selector), str(queue)], check=True, capture_output=True, text=True
            ).stdout.strip()
            self.assertEqual(Path(selected).name, "existing-topic.md")
            self.assertEqual(run_import(), {"imported": []})

            first_stage = state / "topics" / "in-progress"
            first_stage.mkdir(parents=True)
            card.rename(first_stage / card.name)
            self.assertEqual(run_import(), {"imported": []})

            done_stage = state / "topics" / "done"
            done_stage.mkdir(parents=True)
            (first_stage / card.name).rename(done_stage / card.name)
            self.assertEqual(run_import(), {"imported": []})


if __name__ == "__main__":
    unittest.main()
