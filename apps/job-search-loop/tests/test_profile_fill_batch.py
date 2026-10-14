from __future__ import annotations

import json
import io
from pathlib import Path
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, patch

from job_search_loop.browser_agent import runtime
from job_search_loop.browser_agent.candidate_memory import CandidateMemoryView


def _control(label: str, stable_id: str, control_type: str = "text") -> dict[str, object]:
    return {
        "label": label,
        "role": "textbox",
        "stable_id": stable_id,
        "type": control_type,
        "required": True,
    }


def _observation(controls: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": "observed",
        "candidate_concepts": [
            "candidate.first_name",
            "candidate.application_email",
            "candidate.phone_number",
            "candidate.work_authorization",
        ],
        "observation": {"controls": controls, "content_sha256": "observation"},
    }


class ProfileFillBatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.memory = CandidateMemoryView(
            {
                "schema_version": 1,
                "concepts": [
                    {"concept": "candidate.first_name", "value": "Example"},
                    {
                        "concept": "candidate.application_email",
                        "value": "example@example.com",
                    },
                    {"concept": "candidate.phone_number", "value": "+1 555 555 0100"},
                    {
                        "concept": "candidate.work_authorization",
                        "value": "Not stated",
                    },
                ],
            }
        )

    def test_fill_profile_is_exposed_as_a_typed_runtime_command(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            runtime._run_main(["fill-profile", "--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--fields-json", output.getvalue())

    async def _run(self, fields: list[dict[str, str]], observation, type_candidate):
        with (
            patch.object(runtime, "_path_env", return_value=Path("candidate-memory.json")),
            patch.object(
                runtime.CandidateMemoryView, "load", return_value=self.memory
            ),
            patch.object(runtime, "observe", new=AsyncMock(return_value=observation)),
            patch.object(runtime, "type_candidate", new=type_candidate),
        ):
            return await runtime.fill_profile_fields(json.dumps(fields))

    async def test_batches_grounded_visible_profile_textboxes_and_keeps_each_receipt(self):
        fields = [
            {
                "label": "First name",
                "role": "textbox",
                "stable_id": "id:first-name",
                "candidate_concept": "candidate.first_name",
            },
            {
                "label": "Email",
                "role": "textbox",
                "stable_id": "id:email",
                "candidate_concept": "candidate.application_email",
            },
        ]
        initial = _observation(
            [_control("First name", "id:first-name"), _control("Email", "id:email", "email")]
        )
        after_first = _observation([_control("Email", "id:email", "email")])
        after_second = _observation([])
        type_candidate = AsyncMock(
            side_effect=[
                {
                    "status": "acted",
                    "action": {"receipt_sha256": "a" * 64},
                    "observation": after_first["observation"],
                },
                {
                    "status": "acted",
                    "action": {"receipt_sha256": "b" * 64},
                    "observation": after_second["observation"],
                },
            ]
        )

        result = await self._run(fields, initial, type_candidate)

        self.assertEqual(result["status"], "batch_acted")
        self.assertEqual(result["completed_fields"], ["First name", "Email"])
        self.assertEqual(result["receipts"], ["a" * 64, "b" * 64])
        self.assertEqual(type_candidate.await_count, 2)
        type_candidate.assert_any_await(
            label="First name",
            role="textbox",
            stable_id="id:first-name",
            candidate_concept="candidate.first_name",
        )
        type_candidate.assert_any_await(
            label="Email",
            role="textbox",
            stable_id="id:email",
            candidate_concept="candidate.application_email",
        )
        self.assertNotIn("Example", json.dumps(result))
        self.assertNotIn("example@example.com", json.dumps(result))

    async def test_stops_after_rerender_invalidates_the_next_target(self):
        fields = [
            {
                "label": "First name",
                "role": "textbox",
                "stable_id": "id:first-name",
                "candidate_concept": "candidate.first_name",
            },
            {
                "label": "Email",
                "role": "textbox",
                "stable_id": "id:email",
                "candidate_concept": "candidate.application_email",
            },
        ]
        initial = _observation(
            [_control("First name", "id:first-name"), _control("Email", "id:email", "email")]
        )
        after_rerender = _observation([_control("Email", "ref:new-email", "email")])
        type_candidate = AsyncMock(
            return_value={
                "status": "acted",
                "action": {"receipt_sha256": "c" * 64},
                "observation": after_rerender["observation"],
            }
        )

        result = await self._run(fields, initial, type_candidate)

        self.assertEqual(result["status"], "batch_partial")
        self.assertEqual(result["completed_fields"], ["First name"])
        self.assertEqual(result["receipts"], ["c" * 64])
        self.assertEqual(type_candidate.await_count, 1)
        self.assertEqual(result["observation"], after_rerender["observation"])

    async def test_does_not_batch_work_authorization_or_non_text_controls(self):
        fields = [
            {
                "label": "Work authorization",
                "role": "textbox",
                "stable_id": "id:authorization",
                "candidate_concept": "candidate.work_authorization",
            }
        ]
        initial = _observation([_control("Work authorization", "id:authorization")])
        type_candidate = AsyncMock()

        result = await self._run(fields, initial, type_candidate)

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "profile_batch_sensitive_field")
        type_candidate.assert_not_awaited()

    async def test_does_not_batch_picker_controls(self):
        fields = [
            {
                "label": "First name",
                "role": "textbox",
                "stable_id": "id:first-name",
                "candidate_concept": "candidate.first_name",
            }
        ]
        picker = _control("First name", "id:first-name")
        picker["options"] = ["Example"]
        initial = _observation([picker])
        type_candidate = AsyncMock()

        result = await self._run(fields, initial, type_candidate)

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "profile_batch_control_not_plain_text")
        type_candidate.assert_not_awaited()

    async def test_does_not_type_into_textbox_with_visible_related_options_button(self):
        fields = [
            {
                "label": "First name",
                "role": "textbox",
                "stable_id": "id:first-name",
                "candidate_concept": "candidate.first_name",
            }
        ]
        initial = _observation(
            [
                _control("First name", "id:first-name"),
                {"label": "First name options", "role": "button", "stable_id": "id:options"},
            ]
        )
        type_candidate = AsyncMock()

        result = await self._run(fields, initial, type_candidate)

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "profile_batch_control_is_picker")
        type_candidate.assert_not_awaited()

    async def test_does_not_batch_narrative_fields_or_mismatched_profile_facts(self):
        fields = [
            {
                "label": "Describe your experience",
                "role": "textbox",
                "stable_id": "id:experience",
                "candidate_concept": "candidate.first_name",
            }
        ]
        initial = _observation([_control("Describe your experience", "id:experience")])
        type_candidate = AsyncMock()

        result = await self._run(fields, initial, type_candidate)

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "profile_batch_not_profile_field")
        type_candidate.assert_not_awaited()

    async def test_rejects_generic_name_token_and_wrong_contact_field_kind(self):
        cases = [
            (
                "Name a recent accomplishment",
                "id:accomplishment",
                "candidate.first_name",
                "profile_batch_not_profile_field",
            ),
            (
                "Candidate email",
                "id:candidate-email",
                "candidate.phone_number",
                "profile_batch_concept_label_mismatch",
            ),
        ]
        for label, stable_id, concept, reason in cases:
            with self.subTest(label=label, concept=concept):
                fields = [
                    {
                        "label": label,
                        "role": "textbox",
                        "stable_id": stable_id,
                        "candidate_concept": concept,
                    }
                ]
                initial = _observation([_control(label, stable_id)])
                type_candidate = AsyncMock(
                    return_value={
                        "status": "acted",
                        "action": {"receipt_sha256": "d" * 64},
                        "observation": {"controls": []},
                    }
                )

                result = await self._run(fields, initial, type_candidate)

                self.assertEqual(result["status"], "action_rejected")
                self.assertEqual(result["reason"], reason)
                type_candidate.assert_not_awaited()

    async def test_profile_batch_preserves_post_action_failure_receipt_and_stops(self):
        fields = [
            {
                "label": "First name",
                "role": "textbox",
                "stable_id": "id:first-name",
                "candidate_concept": "candidate.first_name",
            },
            {
                "label": "Email",
                "role": "textbox",
                "stable_id": "id:email",
                "candidate_concept": "candidate.application_email",
            },
        ]
        initial = _observation(
            [_control("First name", "id:first-name"), _control("Email", "id:email", "email")]
        )
        after_first = _observation([_control("Email", "id:email", "email")])
        type_candidate = AsyncMock(
            side_effect=[
                {
                    "status": "acted",
                    "action": {"receipt_sha256": "a" * 64},
                    "observation": after_first["observation"],
                },
                {
                    "status": "transport_failed",
                    "error_class": "post_action_context_unavailable",
                    "retryable": False,
                    "next_action": "preserve evidence and do not replay this target",
                    "action_receipt_sha256": "b" * 64,
                    "evidence_sha256": "c" * 64,
                    "checkpoint_sha256": "d" * 64,
                },
            ]
        )

        result = await self._run(fields, initial, type_candidate)

        self.assertEqual(result["status"], "transport_failed")
        self.assertEqual(result["completed_fields"], ["First name"])
        self.assertEqual(result["receipts"], ["a" * 64])
        self.assertEqual(result["failed_field"], "Email")
        self.assertEqual(result["action_receipt_sha256"], "b" * 64)
        self.assertEqual(result["evidence_sha256"], "c" * 64)
        self.assertEqual(result["checkpoint_sha256"], "d" * 64)
        self.assertFalse(result["retryable"])
        self.assertNotIn("observation", result)
        self.assertIn("do not replay", result["next_action"])


if __name__ == "__main__":
    unittest.main()
