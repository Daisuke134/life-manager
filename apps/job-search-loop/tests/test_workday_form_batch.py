from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

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


def _observation(
    controls: list[dict[str, object]], facts: list[dict[str, str]]
) -> dict[str, object]:
    return {
        "status": "observed",
        "grounding_facts": facts,
        "observation": {"controls": controls, "content_sha256": "observation"},
    }


class WorkdayFormBatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.facts = [
            {
                "concept": "fact.experience_account_management",
                "claim": "Managed enterprise accounts across Japan and the US.",
            },
            {
                "concept": "fact.education_naist",
                "claim": "Completed a master's degree at NAIST in 2024.",
            },
        ]
        self.memory = CandidateMemoryView(
            {
                "schema_version": 1,
                "concepts": [
                    {"concept": item["concept"], "value": item["claim"]}
                    for item in self.facts
                ],
            }
        )

    def test_fill_form_is_exposed_as_a_typed_runtime_command(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            runtime._run_main(["fill-form", "--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--fields-json", output.getvalue())

    async def _run(self, fields, initial, type_text, *, wake_budget=None):
        with (
            patch.object(runtime, "_path_env", return_value=Path("candidate-memory.json")),
            patch.object(runtime.CandidateMemoryView, "load", return_value=self.memory),
            patch.object(runtime, "observe", new=AsyncMock(return_value=initial)),
            patch.object(runtime, "type_text", new=type_text),
            patch.object(
                runtime,
                "_wake_budget",
                new=wake_budget or Mock(return_value=99),
            ),
        ):
            return await runtime.fill_form_fields(json.dumps(fields))

    async def test_batches_grounded_visible_workday_text_fields_as_one_step(self):
        fields = [
            {
                "label": "Experience description",
                "role": "textbox",
                "stable_id": "id:experience",
                "text": "Managed enterprise accounts",
                "fact_refs": ["fact.experience_account_management"],
            },
            {
                "label": "School",
                "role": "textbox",
                "stable_id": "id:school",
                "text": "NAIST",
                "fact_refs": ["fact.education_naist"],
            },
        ]
        initial = _observation(
            [_control("Experience description", "id:experience"), _control("School", "id:school")],
            self.facts,
        )
        after_first = _observation([_control("School", "id:school")], self.facts)
        after_second = _observation([], self.facts)
        type_text = AsyncMock(
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
        wake_budget = Mock(return_value=98)

        result = await self._run(fields, initial, type_text, wake_budget=wake_budget)

        self.assertEqual(result["status"], "batch_acted")
        self.assertEqual(result["completed_fields"], ["Experience description", "School"])
        self.assertEqual(result["receipts"], ["a" * 64, "b" * 64])
        wake_budget.assert_called_once_with(consume=True)
        self.assertEqual(type_text.await_count, 2)
        self.assertTrue(all(call.kwargs["_consume_budget"] is False for call in type_text.await_args_list))
        self.assertNotIn("Managed enterprise accounts", json.dumps(result))

    async def test_requires_fact_refs_in_the_immediately_preceding_observation(self):
        fields = [{
            "label": "School",
            "role": "textbox",
            "stable_id": "id:school",
            "text": "NAIST",
            "fact_refs": ["fact.education_naist"],
        }]
        initial = _observation(
            [_control("School", "id:school")],
            [self.facts[0]],
        )
        type_text = AsyncMock()

        result = await self._run(fields, initial, type_text)

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "form_batch_fact_not_currently_grounded")
        type_text.assert_not_awaited()

    async def test_rejects_values_not_copied_from_the_cited_candidate_fact(self):
        fields = [
            {
                "label": "School",
                "role": "textbox",
                "stable_id": "id:school",
                "text": "Invented University",
                "fact_refs": ["fact.education_naist"],
            }
        ]
        initial = _observation([_control("School", "id:school")], self.facts)
        type_text = AsyncMock()

        result = await self._run(fields, initial, type_text)

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "form_batch_value_not_grounded")
        type_text.assert_not_awaited()

    async def test_rejects_email_shape_in_a_fact_batch(self):
        email_fact = {
            "concept": "fact.example_contact",
            "claim": "Contact at someone@example.invalid.",
        }
        self.facts.append(email_fact)
        self.memory = CandidateMemoryView({
            "schema_version": 1,
            "concepts": [
                {"concept": item["concept"], "value": item["claim"]}
                for item in self.facts
            ],
        })
        fields = [{
            "label": "Experience description",
            "role": "textbox",
            "stable_id": "id:description",
            "text": "someone@example.invalid",
            "fact_refs": ["fact.example_contact"],
        }]
        initial = _observation([_control("Experience description", "id:description")], self.facts)
        type_text = AsyncMock()

        result = await self._run(fields, initial, type_text)

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "form_batch_sensitive_field")
        type_text.assert_not_awaited()

    async def test_does_not_batch_picker_controls(self):
        field = {
            "label": "School",
            "role": "textbox",
            "stable_id": "id:school",
            "text": "NAIST",
            "fact_refs": ["fact.education_naist"],
        }
        picker = _control("School", "id:school")
        picker["options"] = ["NAIST"]
        initial = _observation([picker], self.facts)
        type_text = AsyncMock()
        result = await self._run([field], initial, type_text)
        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "form_batch_control_not_plain_text")
        type_text.assert_not_awaited()

    async def test_stops_on_rerender_and_preserves_completed_field_receipt(self):
        fields = [
            {
                "label": "Experience description",
                "role": "textbox",
                "stable_id": "id:experience",
                "text": "Managed enterprise accounts",
                "fact_refs": ["fact.experience_account_management"],
            },
            {
                "label": "School",
                "role": "textbox",
                "stable_id": "id:school",
                "text": "NAIST",
                "fact_refs": ["fact.education_naist"],
            },
        ]
        initial = _observation(
            [_control("Experience description", "id:experience"), _control("School", "id:school")],
            self.facts,
        )
        after_first = _observation([_control("School", "ref:new-school")], self.facts)
        type_text = AsyncMock(
            return_value={
                "status": "acted",
                "action": {"receipt_sha256": "c" * 64},
                "observation": after_first["observation"],
            }
        )

        result = await self._run(fields, initial, type_text)

        self.assertEqual(result["status"], "batch_partial")
        self.assertEqual(result["reason"], "form_batch_target_not_fresh")
        self.assertEqual(result["completed_fields"], ["Experience description"])
        self.assertEqual(result["receipts"], ["c" * 64])
        self.assertEqual(type_text.await_count, 1)

    def test_checkpoint_cli_accepts_a_same_row_wake_budget_reason(self):
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            patch.object(runtime, "_exclusive_command", return_value=contextlib.nullcontext()),
            patch.object(runtime, "_check_terminal_failure_marker"),
            patch.object(runtime, "_write_terminal_failure_marker"),
            patch.object(
                runtime,
                "checkpoint",
                new=AsyncMock(return_value={"status": "checkpointed", "reason": "wake_budget_low"}),
            ) as checkpoint,
        ):
            code = runtime._run_main(["checkpoint", "--reason", "wake_budget_low"])

        self.assertEqual(code, 0)
        checkpoint.assert_awaited_once_with("wake_budget_low")
        self.assertIn('"status": "checkpointed"', output.getvalue())
