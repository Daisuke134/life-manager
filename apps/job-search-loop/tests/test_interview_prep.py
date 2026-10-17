import tempfile
import unittest
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from job_search_loop.interview_prep import (
    PrepError,
    PrepStore,
    append_pending_to_prompt,
    build_prep_pack,
    deliver_due_preps,
    render_prep_message,
    save_pack_from_input,
)


class InterviewPrepTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "facts": [
                {
                    "id": f"fact-{index}",
                    "claim": f"Verified candidate claim {index}.",
                    "evidence": "private profile",
                }
                for index in range(1, 6)
            ]
        }
        self.context = {
            "company_thesis": {
                "text": "The company is expanding applied AI workflows.",
                "evidence_ids": ["company-source"],
            },
            "interviewer_interests": [
                {
                    "text": "Reliable enterprise AI delivery",
                    "evidence_ids": ["role-source"],
                }
            ],
            "public_evidence": [
                {
                    "id": "company-source",
                    "url": "https://example.com/company",
                    "source_span": "We are expanding applied AI workflows.",
                },
                {
                    "id": "role-source",
                    "url": "https://example.com/job",
                    "source_span": "Build reliable AI products with customers.",
                },
            ],
            "technical_questions": [
                "How would you evaluate an enterprise AI agent?",
                "How do you debug production agent behavior?",
                "How do you control hallucination risk?",
            ],
            "questions_to_ask": [
                "What outcome defines success in the first 90 days?",
                "How is production quality evaluated?",
                "How do product and engineering collaborate?",
            ],
            "logistics": "Video interview; join link is stored in Calendar.",
        }

    def test_registration_is_private_idempotent_and_pending_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "prep.sqlite3"
            store = PrepStore(database)
            interview_key = store.register_interview(
                thread_id="thread-1",
                event_key="event-key-1",
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                end=datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc),
                registered_at=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
            )
            duplicate = store.register_interview(
                thread_id="thread-1",
                event_key="event-key-1",
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                end=datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc),
                registered_at=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(duplicate, interview_key)
            self.assertEqual(database.stat().st_mode & 0o777, 0o600)
            pending = store.pending_generation()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["interview_key"], interview_key)
            self.assertNotIn("thread_id", pending[0])
            store.close()

    def test_pack_uses_exactly_five_approved_facts_and_cited_public_evidence(self):
        pack = build_prep_pack(
            profile=self.profile,
            company="Example AI",
            role="AI Product Manager",
            start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
            fact_ids=[f"fact-{index}" for index in range(1, 6)],
            **self.context,
        )
        self.assertEqual(len(pack["candidate_stories"]), 5)
        self.assertEqual(
            [story["claim"] for story in pack["candidate_stories"]],
            [f"Verified candidate claim {index}." for index in range(1, 6)],
        )
        self.assertEqual(len(pack["pack_sha256"]), 64)
        with self.assertRaisesRegex(PrepError, "fact"):
            build_prep_pack(
                profile=self.profile,
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                fact_ids=["fact-1", "fact-2", "fact-3", "fact-4", "invented"],
                **self.context,
            )

    def test_due_windows_are_persistent_and_do_not_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PrepStore(Path(directory) / "prep.sqlite3")
            interview_key = store.register_interview(
                thread_id="thread-1",
                event_key="event-key-1",
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                end=datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc),
                registered_at=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
            )
            pack = build_prep_pack(
                profile=self.profile,
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                fact_ids=[f"fact-{index}" for index in range(1, 6)],
                **self.context,
            )
            store.save_pack(interview_key, pack)
            self.assertEqual(
                store.due_deliveries(
                    datetime(2026, 8, 2, 0, 59, tzinfo=timezone.utc)
                ),
                [],
            )
            three_day = store.due_deliveries(
                datetime(2026, 8, 2, 1, 0, tzinfo=timezone.utc)
            )
            self.assertEqual(
                [(item["interview_key"], item["window"]) for item in three_day],
                [(interview_key, "three_day")],
            )
            store.mark_delivery(
                interview_key,
                "three_day",
                status="sent",
                message_id="telegram-1",
            )
            self.assertEqual(
                store.due_deliveries(
                    datetime(2026, 8, 2, 1, 1, tzinfo=timezone.utc)
                ),
                [],
            )
            one_day = store.due_deliveries(
                datetime(2026, 8, 4, 1, 0, tzinfo=timezone.utc)
            )
            self.assertEqual([item["window"] for item in one_day], ["one_day"])
            store.mark_delivery(
                interview_key,
                "one_day",
                status="sent",
                message_id="telegram-2",
            )
            self.assertEqual(
                store.due_deliveries(
                    datetime(2026, 8, 4, 1, 1, tzinfo=timezone.utc)
                ),
                [],
            )
            store.close()

    def test_last_minute_registration_uses_one_immediate_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PrepStore(Path(directory) / "prep.sqlite3")
            interview_key = store.register_interview(
                thread_id="thread-2",
                event_key="event-key-2",
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                end=datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc),
                registered_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
            )
            pack = build_prep_pack(
                profile=self.profile,
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                fact_ids=[f"fact-{index}" for index in range(1, 6)],
                **self.context,
            )
            store.save_pack(interview_key, pack)
            due = store.due_deliveries(
                datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
            )
            self.assertEqual([item["window"] for item in due], ["immediate"])
            store.close()

    def test_due_pack_is_rendered_and_sent_at_most_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "prep.sqlite3"
            store = PrepStore(database)
            interview_key = store.register_interview(
                thread_id="thread-1",
                event_key="event-key-1",
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                end=datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc),
                registered_at=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
            )
            pack = build_prep_pack(
                profile=self.profile,
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                fact_ids=[f"fact-{index}" for index in range(1, 6)],
                **self.context,
            )
            store.save_pack(interview_key, pack)
            store.close()
            message = render_prep_message(pack, window="three_day")
            self.assertIn("3-day interview preparation", message)
            self.assertIn("Company thesis", message)
            self.assertIn("Five grounded stories", message)
            self.assertIn("Questions to ask", message)
            self.assertLessEqual(len(message), 4_000)
            sender = Mock(return_value={"status": "sent", "message_id": "telegram-1"})
            first = deliver_due_preps(
                prep_database=database,
                outbox_database=root / "outbox.sqlite3",
                now=datetime(2026, 8, 2, 1, 0, tzinfo=timezone.utc),
                sender=sender,
            )
            second = deliver_due_preps(
                prep_database=database,
                outbox_database=root / "outbox.sqlite3",
                now=datetime(2026, 8, 2, 1, 1, tzinfo=timezone.utc),
                sender=sender,
            )
            self.assertEqual(sender.call_count, 1)
            self.assertEqual(first[0]["status"], "sent")
            self.assertEqual(second, [])
            self.assertEqual(
                sender.call_args.kwargs["event_key"],
                f"interview-prep:{interview_key}:three_day",
            )

    def test_prompt_requires_pack_generation_and_persistent_save(self):
        root = Path(__file__).parents[1]
        prompt = (root / "prompts" / "inbox-pass.md").read_text(encoding="utf-8")
        self.assertIn("build_prep_pack", prompt)
        self.assertIn("save_pack", prompt)
        self.assertIn("prep_database", prompt)
        schema = __import__("json").loads(
            (root / "schemas" / "inbox-pass-result.v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("prep_packs", schema["required"])

    def test_inbox_result_schema_requires_every_property_for_strict_output(self):
        schema_path = (
            Path(__file__).parents[1]
            / "schemas"
            / "inbox-pass-result.v1.schema.json"
        )
        schema = __import__("json").loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(set(schema["required"]), set(schema["properties"]))

    def test_pending_prompt_and_save_command_contract_complete_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "prep.sqlite3"
            store = PrepStore(database)
            interview_key = store.register_interview(
                thread_id="thread-1",
                event_key="event-key-1",
                company="Example AI",
                role="AI Product Manager",
                start=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
                end=datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc),
                registered_at=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
            )
            store.close()
            profile_path = root / "profile.json"
            profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
            os.chmod(profile_path, 0o600)
            prompt_path = root / "prompt.md"
            prompt_path.write_text("Base prompt.\n", encoding="utf-8")
            count = append_pending_to_prompt(
                database=database,
                prompt_path=prompt_path,
                profile_path=profile_path,
            )
            self.assertEqual(count, 1)
            appended = prompt_path.read_text(encoding="utf-8")
            self.assertIn('encoding="base64"', appended)
            self.assertIn("interview_prep save", appended)
            self.assertEqual(prompt_path.stat().st_mode & 0o777, 0o600)
            input_path = root / "prep-input.json"
            input_path.write_text(
                json.dumps(
                    {
                        "interview_key": interview_key,
                        "fact_ids": [f"fact-{index}" for index in range(1, 6)],
                        **self.context,
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(input_path, 0o600)
            result = save_pack_from_input(
                database=database,
                profile_path=profile_path,
                input_path=input_path,
            )
            self.assertEqual(result["status"], "generated")
            reopened = PrepStore(database)
            self.assertEqual(reopened.pending_generation(), [])
            reopened.close()


if __name__ == "__main__":
    unittest.main()
