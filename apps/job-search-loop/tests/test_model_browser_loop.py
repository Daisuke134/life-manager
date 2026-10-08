import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jsonschema import Draft202012Validator, FormatChecker

from job_search_loop.ats import detect_provider, evaluate_snapshot


APP_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_PATH = APP_ROOT / "schemas" / "browser-row-run.v1.schema.json"


def _evidence_ref(name: str) -> dict[str, str]:
    return {"ref": f"evidence:{name}", "sha256": "a" * 64}


def _row_run(*, provider: str, canonical_url: str) -> dict[str, object]:
    return {
        "version": 1,
        "api_version": "job-hunter-browser-agent/1",
        "row": {
            "application_id": f"application:{provider}:replay",
            "company": "Recorded shape employer",
            "role": "Recorded shape role",
            "canonical_url": canonical_url,
            "provider": provider,
            "ledger_state": "materials_ready",
            "candidate_memory_ref": "candidate:memory:v1",
            "answer_memory_ref": "answer:memory:v1",
            "resume": _evidence_ref("resume"),
            "posting": _evidence_ref("posting"),
            "eligibility": {
                "decision": "eligible",
                "policy_version": "eligibility:v1",
                "evidence": _evidence_ref("eligibility"),
            },
        },
        "run": {
            "row_run_id": f"row-run:{provider}:replay",
            "wake_id": "wake:replay",
            "step_index": 0,
            "remaining_steps": 50,
            "remaining_seconds": 900,
            "observation_ref": None,
            "checkpoint_predecessor_sha256": None,
            "updated_at": "2026-08-22T00:00:00Z",
            "state": "queued",
            "effect_phase": "pre_submit",
        },
    }


class ModelBrowserLoopContractTests(unittest.TestCase):
    def test_wake_budget_covers_workday_and_one_following_ats_form(self):
        from job_search_loop.browser_agent import runtime

        self.assertGreaterEqual(runtime._WAKE_STEP_BUDGET, 100)

    def test_all_provider_queue_keeps_workday_before_ashby(self):
        from job_search_loop.browser_agent.queue import RowQueueSupervisor

        rows = [
            {
                "application_id": "ashby",
                "company": "Ashby Co",
                "title": "AI Role",
                "canonical_url": "https://jobs.ashbyhq.com/example/role",
            },
            {
                "application_id": "workday",
                "company": "Workday Co",
                "title": "AI Role",
                "canonical_url": "https://example.wd5.myworkdayjobs.com/job/role",
            },
        ]
        ledger = Mock()
        ledger.pending_materials_ready_applications.return_value = rows
        ledger.retryable_applications.return_value = []
        ledger.workday_fit_qualified.return_value = True

        collected = RowQueueSupervisor.collect(ledger, active_provider=None)

        self.assertEqual(
            [row["application_id"] for row in collected],
            ["workday", "ashby"],
        )

    def test_workday_row_without_model_fit_receipt_never_enters_browser_lane(self):
        from job_search_loop.browser_agent.queue import RowQueueSupervisor

        row = {
            "application_id": "workday-unqualified",
            "company": "Example",
            "title": "Principal Stretch Role",
            "canonical_url": "https://example.wd5.myworkdayjobs.com/job/role_JR1",
        }
        ledger = Mock()
        ledger.pending_materials_ready_applications.return_value = [row]
        ledger.retryable_applications.return_value = []
        ledger.workday_fit_qualified.return_value = False

        self.assertEqual(
            RowQueueSupervisor.collect(ledger, active_provider="workday"), ()
        )

    def test_model_selected_application_is_first_workday_row_for_this_wake(self):
        from job_search_loop.browser_agent.queue import RowQueueSupervisor

        rows = [
            {
                "application_id": value,
                "company": value,
                "title": "AI Role",
                "canonical_url": f"https://{value}.wd1.myworkdayjobs.com/job/role",
            }
            for value in ("old-rakuten", "new-company")
        ]
        ledger = Mock()
        ledger.pending_materials_ready_applications.return_value = rows
        ledger.retryable_applications.return_value = []
        ledger.workday_fit_qualified.return_value = True
        with patch.dict(
            os.environ,
            {
                "JOB_SEARCH_PREFERRED_APPLICATION_ID": "new-company",
                "JOB_SEARCH_APPLICATION_LIMIT": "2",
            },
        ):
            collected = RowQueueSupervisor.collect(ledger, active_provider="workday")
        self.assertEqual(
            [row["application_id"] for row in collected],
            ["new-company", "old-rakuten"],
        )

    def test_positive_application_limit_keeps_queued_rows_after_preferred_order(self):
        from job_search_loop.browser_agent.queue import RowQueueSupervisor

        rows = [
            {
                "application_id": value,
                "company": value,
                "title": "AI Role",
                "canonical_url": f"https://{value}.wd1.myworkdayjobs.com/job/role",
            }
            for value in ("old-rakuten", "new-company")
        ]
        ledger = Mock()
        ledger.pending_materials_ready_applications.return_value = rows
        ledger.retryable_applications.return_value = []
        ledger.workday_fit_qualified.return_value = True
        with patch.dict(
            os.environ,
            {
                "JOB_SEARCH_PREFERRED_APPLICATION_ID": "new-company",
                "JOB_SEARCH_APPLICATION_LIMIT": "1",
            },
        ):
            collected = RowQueueSupervisor.collect(ledger, active_provider="workday")
        self.assertEqual(
            [row["application_id"] for row in collected],
            ["new-company", "old-rakuten"],
        )

    def test_zero_or_malformed_application_limit_closes_queue(self):
        from job_search_loop.browser_agent.queue import RowQueueSupervisor

        row = {
            "application_id": "workday",
            "company": "Workday Co",
            "title": "AI Role",
            "canonical_url": "https://example.wd5.myworkdayjobs.com/job/role",
        }
        ledger = Mock()
        ledger.pending_materials_ready_applications.return_value = [row]
        ledger.retryable_applications.return_value = []
        ledger.workday_fit_qualified.return_value = True
        for value in ("0", "invalid", "-1", "1.5"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"JOB_SEARCH_APPLICATION_LIMIT": value}
            ):
                self.assertEqual(
                    RowQueueSupervisor.collect(ledger, active_provider="workday"), ()
                )

    def test_missing_preferred_workday_application_keeps_existing_queue(self):
        from job_search_loop.browser_agent.queue import RowQueueSupervisor

        rows = [
            {
                "application_id": value,
                "company": value,
                "title": "AI Role",
                "canonical_url": f"https://{value}.wd1.myworkdayjobs.com/job/role",
            }
            for value in ("old-rakuten", "new-company")
        ]
        ledger = Mock()
        ledger.pending_materials_ready_applications.return_value = rows
        ledger.retryable_applications.return_value = []
        ledger.workday_fit_qualified.return_value = True
        with patch.dict(
            os.environ,
            {"JOB_SEARCH_PREFERRED_APPLICATION_ID": "not-in-queue"},
        ):
            collected = RowQueueSupervisor.collect(ledger, active_provider="workday")
        self.assertEqual(
            [row["application_id"] for row in collected],
            ["old-rakuten", "new-company"],
        )

    def test_browser_queue_omits_recovery_requested_workday_tenant(self):
        from job_search_loop.browser_agent.queue import RowQueueSupervisor

        rows = [
            {
                "application_id": "cloudera-recovery",
                "company": "Cloudera",
                "title": "Applied AI Specialist",
                "canonical_url": "https://cloudera.wd5.myworkdayjobs.com/job/role",
            },
            {
                "application_id": "fresh-company",
                "company": "Fresh Company",
                "title": "Customer Success",
                "canonical_url": "https://fresh.wd5.myworkdayjobs.com/job/role",
            },
        ]
        ledger = Mock()
        ledger.pending_materials_ready_applications.return_value = rows
        ledger.retryable_applications.return_value = []
        ledger.workday_fit_qualified.return_value = True
        with tempfile.TemporaryDirectory() as directory:
            credentials = Path(directory) / "credentials.json"
            credentials.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "credentials": [
                            {
                                "service": "workday:cloudera.wd5.myworkdayjobs.com",
                                "username": "candidate@example.com",
                                "email": "candidate@example.com",
                                "password": "Strong-Workday-Password-9!",
                                "account_status": "recovery_requested",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(credentials, 0o600)
            with patch.dict(
                os.environ,
                {"JOB_SEARCH_MACHINE_CREDENTIALS": str(credentials)},
            ):
                collected = RowQueueSupervisor.collect(
                    ledger, active_provider="workday"
                )

        self.assertEqual(
            [row["application_id"] for row in collected], ["fresh-company"]
        )

    def test_transport_failed_requires_a_real_nonzero_runtime_command(self):
        from job_search_loop.browser_agent import orchestrator

        validator = getattr(orchestrator, "validate_pass_result", None)
        self.assertIsNotNone(validator)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / "result.json"
            stdout = root / "stdout.log"
            attempts = root / "attempts.jsonl"
            summary = root / "summary.json"
            result.write_text(
                json.dumps(
                    {
                        "status": "transport_failed",
                        "submitted": [],
                        "submit_unknown": [],
                        "blocked": ["Example — Role"],
                        "report_message_id": None,
                    }
                ),
                encoding="utf-8",
            )
            stdout.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "exit_code": 0,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            attempts.write_text(
                json.dumps({"stdout_path": str(stdout)}) + "\n",
                encoding="utf-8",
            )
            summary.write_text(
                json.dumps(
                    {
                        "result_path": str(result),
                        "attempts_path": str(attempts),
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                validator(root),
                "transport_failed_without_command_failure",
            )

            stdout.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "exit_code": 1,
                            "command": (
                                "/opt/homebrew/bin/python3 -m "
                                "job_search_loop.browser_agent.runtime type-text "
                                "--text job_search_loop.browser_agent.browser_agent.runtime"
                            ),
                            "aggregated_output": "ModuleNotFoundError after browser action",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertIsNone(validator(root))
            stdout.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "exit_code": 1,
                            "command": (
                                "/opt/homebrew/bin/python3 -m "
                                "job_search_loop.browser_agent.browser_agent.runtime type"
                            ),
                            "aggregated_output": (
                                "ModuleNotFoundError: No module named "
                                "'job_search_loop.browser_agent.browser_agent'"
                            ),
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                validator(root),
                "transport_failed_without_command_failure",
            )
            stdout.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "exit_code": 2,
                            "command": (
                                "/bin/zsh -lc '/opt/homebrew/bin/python3 -m "
                                "job_search_loop.runtime'"
                            ),
                            "aggregated_output": (
                                "usage: python -m job_search_loop.runtime [-h] "
                                "{observe,finalize} ...\n"
                                "error: the following arguments are required: command\n"
                            ),
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                validator(root),
                "transport_failed_without_command_failure",
            )
            stdout.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "exit_code": 7,
                            "command": (
                                "/opt/homebrew/bin/python3 -m "
                                "job_search_loop.browser_agent.runtime observe"
                            ),
                            "aggregated_output": "runtime traceback",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertIsNone(validator(root))
            stdout.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "exit_code": 1,
                            "command": (
                                "/bin/zsh -lc '/opt/homebrew/bin/python3 -m "
                                "job_search_loop.browser_agent.runtime click"
                            ),
                            "aggregated_output": 'zsh:1: unmatched "\n',
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                validator(root),
                "transport_failed_without_command_failure",
            )

    def test_in_progress_without_terminal_outcome_retries_after_successful_commands(self):
        from job_search_loop.browser_agent import orchestrator

        validator = getattr(orchestrator, "validate_pass_result", None)
        self.assertIsNotNone(validator)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / "result.json"
            stdout = root / "stdout.log"
            attempts = root / "attempts.jsonl"
            summary = root / "summary.json"
            result.write_text(
                json.dumps(
                    {
                        "status": "in_progress",
                        "submitted": [],
                        "submit_unknown": [],
                        "blocked": [],
                        "report_message_id": None,
                    }
                ),
                encoding="utf-8",
            )
            stdout.write_text(
                "".join(
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "exit_code": 0,
                                "command": "runtime observe",
                            },
                        }
                    )
                    + "\n"
                    for _ in range(37)
                ),
                encoding="utf-8",
            )
            attempts.write_text(
                json.dumps({"stdout_path": str(stdout)}) + "\n",
                encoding="utf-8",
            )
            summary.write_text(
                json.dumps(
                    {
                        "result_path": str(result),
                        "attempts_path": str(attempts),
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                validator(root),
                "in_progress_without_terminal_outcome",
            )

    def _write_queue_complete_observe_fixture(
        self, root: Path, statuses: tuple[str, ...]
    ) -> None:
        result = root / "result.json"
        stdout = root / "stdout.log"
        attempts = root / "attempts.jsonl"
        summary = root / "summary.json"
        result.write_text(
            json.dumps(
                {
                    "status": "queue_complete",
                    "submitted": [],
                    "submit_unknown": [],
                    "blocked": [],
                    "report_message_id": None,
                }
            ),
            encoding="utf-8",
        )
        stdout.write_text(
            "".join(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "exit_code": 0,
                            "command": (
                                "/bin/zsh -lc '/opt/homebrew/bin/python3 -m "
                                "job_search_loop.browser_agent.runtime observe'"
                            ),
                            "aggregated_output": json.dumps({"status": status}),
                        },
                    }
                )
                + "\n"
                for status in statuses
            ),
            encoding="utf-8",
        )
        attempts.write_text(
            json.dumps({"stdout_path": str(stdout)}) + "\n",
            encoding="utf-8",
        )
        summary.write_text(
            json.dumps(
                {
                    "result_path": str(result),
                    "attempts_path": str(attempts),
                }
            ),
            encoding="utf-8",
        )

    def test_queue_complete_after_observed_row_requires_semantic_retry(self):
        from job_search_loop.browser_agent import orchestrator

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_queue_complete_observe_fixture(root, ("observed", "observed"))

            self.assertEqual(
                orchestrator.validate_pass_result(root),
                "observed_row_without_terminal_outcome",
            )

    def test_latest_successful_queue_complete_observe_remains_accepted(self):
        from job_search_loop.browser_agent import orchestrator

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_queue_complete_observe_fixture(
                root, ("observed", "queue_complete")
            )

            self.assertIsNone(orchestrator.validate_pass_result(root))

    def test_validator_scans_runtime_causality_before_terminal_result_fields(self):
        from job_search_loop.browser_agent import orchestrator

        command = "/bin/zsh -lc '/opt/homebrew/bin/python3 -m job_search_loop.browser_agent.runtime "
        event = lambda kind, item_id, command, **fields: {"type": f"item.{kind}", "item": {"id": item_id, "type": "command_execution", "command": command, **fields}}
        events = [
            event("started", "wait-1", command + "wait --milliseconds 6000'"),
            event("started", "observe-1", command + "observe'"),
            event("completed", "wait-1", command + "wait --milliseconds 6000'", exit_code=1, aggregated_output="runtime failure"),
            event("started", "observe-2", command + "observe'"),
            event("completed", "observe-2", command + "observe'", exit_code=0, aggregated_output=json.dumps({"status": "observed"})),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_queue_complete_observe_fixture(root, ())
            (root / "stdout.log").write_text(
                "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
            )
            outcomes = []
            for terminal_field in ("submitted", "submit_unknown"):
                result = {"status": "queue_complete", "submitted": [], "submit_unknown": [], "blocked": []}
                result[terminal_field] = ["row"]
                (root / "result.json").write_text(json.dumps(result), encoding="utf-8")
                outcomes.append(orchestrator.validate_pass_result(root))
            self.assertEqual(
                outcomes,
                [
                    None,
                    "submission_outcome_unknown",
                ],
            )

    def test_validator_accepts_event_overlap_when_runtime_commands_both_succeed(self):
        from job_search_loop.browser_agent import orchestrator

        command = "/bin/zsh -lc '/opt/homebrew/bin/python3 -m job_search_loop.browser_agent.runtime "
        event = lambda kind, item_id, command, **fields: {"type": f"item.{kind}", "item": {"id": item_id, "type": "command_execution", "command": command, **fields}}
        click = command + "click --label Continue --role button --stable-id ref:e1'"
        wait = command + "wait --milliseconds 6000'"
        events = [
            event("started", "click-1", click),
            event("started", "wait-1", wait),
            event("completed", "click-1", click, exit_code=0, aggregated_output=json.dumps({"status": "acted"})),
            event("completed", "wait-1", wait, exit_code=0, aggregated_output=json.dumps({"status": "acted"})),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_queue_complete_observe_fixture(root, ())
            (root / "result.json").write_text(
                json.dumps(
                    {
                        "status": "queue_complete",
                        "submitted": [],
                        "submit_unknown": [],
                        "blocked": ["Cloudera: checkpointed for email recovery"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "stdout.log").write_text(
                "".join(json.dumps(item) + "\n" for item in events),
                encoding="utf-8",
            )

            self.assertIsNone(orchestrator.validate_pass_result(root))

    def test_validator_rejects_runtime_start_after_nonzero_completion(self):
        from job_search_loop.browser_agent import orchestrator

        command = "/bin/zsh -lc '/opt/homebrew/bin/python3 -m job_search_loop.browser_agent.runtime "
        event = lambda kind, item_id, command, **fields: {"type": f"item.{kind}", "item": {"id": item_id, "type": "command_execution", "command": command, **fields}}
        wait = command + "wait --milliseconds 6000'"
        observe = command + "observe'"
        events = [
            event("started", "wait-1", wait),
            event("completed", "wait-1", wait, exit_code=1, aggregated_output="runtime failure"),
            event("started", "observe-1", observe),
            event("completed", "observe-1", observe, exit_code=0, aggregated_output=json.dumps({"status": "observed"})),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_queue_complete_observe_fixture(root, ())
            (root / "result.json").write_text(
                json.dumps({"status": "transport_failed", "submitted": [], "submit_unknown": [], "blocked": []}),
                encoding="utf-8",
            )
            (root / "stdout.log").write_text(
                "".join(json.dumps(item) + "\n" for item in events), encoding="utf-8"
            )

            self.assertEqual(
                orchestrator.validate_pass_result(root),
                "runtime_command_after_nonzero_completion",
            )

    def test_single_terminal_nonzero_runtime_command_is_not_a_pass(self):
        from job_search_loop.browser_agent import orchestrator

        command = "/bin/zsh -lc '/opt/homebrew/bin/python3 -m job_search_loop.browser_agent.runtime "
        wait = command + "wait --milliseconds 6000'"
        events = [
            {
                "type": "item.started",
                "item": {"id": "wait-1", "type": "command_execution", "command": wait},
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "wait-1", "type": "command_execution", "command": wait,
                    "exit_code": 1, "aggregated_output": "runtime failure",
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_queue_complete_observe_fixture(root, ())
            (root / "summary.json").write_text(
                json.dumps({
                    "status": "success",
                    "result_path": str(root / "result.json"),
                    "attempts_path": str(root / "attempts.jsonl"),
                }),
                encoding="utf-8",
            )
            (root / "result.json").write_text(
                json.dumps({
                    "status": "transport_failed", "submitted": [],
                    "submit_unknown": [], "blocked": ["row-1"],
                }),
                encoding="utf-8",
            )
            (root / "stdout.log").write_text(
                "".join(json.dumps(item) + "\n" for item in events), encoding="utf-8",
            )

            self.assertEqual(
                orchestrator.validate_pass_result(root),
                "runtime_command_nonzero_completion",
            )

    @classmethod
    def setUpClass(cls) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema, format_checker=FormatChecker())

    def test_daily_prompt_requires_correction_of_duplicated_runtime_namespace(self):
        prompt = (APP_ROOT / "prompts/daily-pass.md").read_text(encoding="utf-8")
        self.assertIn("job_search_loop.browser_agent.browser_agent.runtime", prompt)
        self.assertIn("replace it with the canonical module", prompt)

    def assertValid(self, value: dict[str, object]) -> None:
        errors = sorted(self.validator.iter_errors(value), key=lambda item: list(item.path))
        self.assertEqual([], [error.message for error in errors])

    def assertInvalid(self, value: dict[str, object]) -> None:
        self.assertTrue(list(self.validator.iter_errors(value)))

    def test_recorded_workday_and_ashby_shapes_replay_through_one_row_contract(self):
        workday = json.loads(
            (FIXTURES / "browser_agent" / "workday-step1-live-shape.v1.json").read_text(
                encoding="utf-8"
            )
        )
        ashby = json.loads(
            (FIXTURES / "ats" / "ashby-application-surface.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(workday["evidence_class"], "live_cdp_sanitized_projection")
        self.assertEqual(workday["source_control_count"], 42)
        self.assertRegex(workday["source_sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(detect_provider(workday["canonical_url"]), "workday")
        self.assertEqual(evaluate_snapshot(ashby)["surface"], "ashby_application")

        self.assertValid(
            _row_run(provider="workday", canonical_url=workday["canonical_url"])
        )
        self.assertValid(_row_run(provider="ashby", canonical_url=ashby["url"]))

    def test_row_contract_rejects_secrets_raw_answers_terminal_retries_and_reclick(self):
        valid = _row_run(
            provider="workday",
            canonical_url="https://tenant.wd1.myworkdayjobs.com/job/role/apply",
        )
        cases = []
        for forbidden_key in ("password", "cookie", "email_code", "raw_answer"):
            value = copy.deepcopy(valid)
            value["row"][forbidden_key] = "must-not-cross-boundary"
            cases.append(value)
        for terminal in ("submitted", "submit_unknown"):
            value = copy.deepcopy(valid)
            value["row"]["ledger_state"] = terminal
            cases.append(value)
        reclick = copy.deepcopy(valid)
        reclick["run"].update(
            {
                "state": "acting",
                "effect_phase": "post_submit_verification",
                "intent_id": "intent:one",
                "fence": 1,
                "final_action_receipt": _evidence_ref("submit-click"),
            }
        )
        cases.append(reclick)

        for value in cases:
            with self.subTest(value=value):
                self.assertInvalid(value)

    def test_daily_owner_routes_forms_only_through_framework_orchestrator(self):
        daily = (APP_ROOT / "scripts" / "run-daily.sh").read_text(encoding="utf-8")
        prompt = (APP_ROOT / "prompts" / "daily-pass.md").read_text(encoding="utf-8")

        self.assertNotIn("job_search_loop.ashby_fast_path", daily)
        self.assertNotIn("job_search_loop.workday_fast_path", daily)
        self.assertNotIn('"$JOB_SEARCH_PYTHON" "$JOB_SEARCH_RUNNER"', daily)
        self.assertEqual(
            daily.count("-m job_search_loop.browser_agent.orchestrator"), 1
        )
        self.assertNotIn("deterministic Ashby fast path owns", prompt)
        self.assertIn("Agent loop adopted from Browser Use and career-ops", prompt)
        self.assertIn("observation-local `ref:*`", prompt)
        self.assertIn("Act on exactly one currently visible control", prompt)
        self.assertIn("Opening a dropdown is\none action", prompt)
        self.assertIn("A row-local failure never ends the queue", " ".join(prompt.split()))
        self.assertIn("job_search_loop.browser_agent.candidate_memory", daily)
        self.assertIn("grounding_facts", prompt)
        self.assertIn("JOB_SEARCH_ANSWER_MEMORY", daily)
        self.assertIn("JOB_SEARCH_MACHINE_CREDENTIALS", daily)
        self.assertIn("runtime auth --mode", prompt)
        self.assertIn("visible page determine the next action", prompt)
        self.assertIn("Canonical Review example", prompt)
        self.assertIn("enabled `Submit`", prompt)
        self.assertIn("the next action is `runtime finalize`", prompt)
        self.assertIn("shell parser rejects malformed quoting", prompt)
        self.assertIn("Correct the quoting and issue that intended command once", prompt)
        self.assertIn("For a segmented Workday month/year date", prompt)
        self.assertIn("fill Year first", prompt)
        self.assertIn("select the exact visible", prompt)
        self.assertIn("month-year matching the grounded date", prompt)
        self.assertIn("Never click Next Year or Previous Year", prompt)
        self.assertIn("Never target the\ndrop-zone wrapper", prompt)
        self.assertIn("exact `Select file` control", prompt)
        self.assertNotIn("workday_job", prompt)
        self.assertNotIn("workday-accounts.json", prompt)
        self.assertNotIn("click_filter", prompt)
        self.assertNotIn("promptOption", prompt)
        self.assertNotIn("searchBox", prompt)

    def test_orchestrator_delegates_once_to_the_existing_bounded_runner(self):
        from job_search_loop.browser_agent.orchestrator import invoke_runner

        completed = Mock(returncode=0)
        with patch(
            "job_search_loop.browser_agent.orchestrator.subprocess.run",
            return_value=completed,
        ) as run:
            returncode = invoke_runner(
                runner=Path("/runtime/agent_runner.py"),
                prompt=Path("/app/prompts/daily-pass.md"),
                schema=Path("/app/schemas/pass-result.v1.schema.json"),
                evidence_dir=Path("/state/evidence/wake"),
                workdir=Path("/repo"),
                timeout_seconds=900,
                python="/python3",
                active_provider="workday",
            )

        self.assertEqual(returncode, 0)
        run.assert_called_once()
        command = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertEqual(
            command,
            [
                "/python3",
                "/runtime/agent_runner.py",
                "--task-class",
                "job-hunter-agent",
                "--escalation-reason",
                "repeated browser form completion abandoned before provider terminal outcome",
                "--timeout-seconds",
                "900",
                "--prompt-file",
                "/app/prompts/daily-pass.md",
                "--schema",
                "/app/schemas/pass-result.v1.schema.json",
                "--evidence-dir",
                "/state/evidence/wake",
                "--task-label",
                "job-search-daily",
                "--loop",
                "job-search",
                "--workdir",
                "/repo",
            ],
        )
        self.assertIs(kwargs["check"], False)
        self.assertEqual(
            kwargs["env"]["JOB_SEARCH_ACTIVE_APPLICATION_PROVIDER"], "workday"
        )

    def test_orchestrator_retries_once_after_false_transport_failure(self):
        from job_search_loop.browser_agent import orchestrator

        completed = Mock(returncode=0)
        with tempfile.TemporaryDirectory() as directory, patch(
            "job_search_loop.browser_agent.orchestrator.subprocess.run",
            side_effect=(completed, completed),
        ) as run, patch(
            "job_search_loop.browser_agent.orchestrator.validate_pass_result",
            side_effect=("transport_failed_without_command_failure", None),
        ) as validate:
            returncode = orchestrator.invoke_runner(
                runner=Path("/runtime/agent_runner.py"),
                prompt=Path("/app/prompts/daily-pass.md"),
                schema=Path("/app/schemas/pass-result.v1.schema.json"),
                evidence_dir=Path(directory),
                workdir=Path("/repo"),
                timeout_seconds=900,
                python="/python3",
                active_provider="workday",
            )

        self.assertEqual(returncode, 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(validate.call_count, 2)

    def test_invoke_runner_does_not_pass_single_terminal_runtime_failure(self):
        from job_search_loop.browser_agent import orchestrator

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_queue_complete_observe_fixture(root, ())
            summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            summary["status"] = "success"
            (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (root / "result.json").write_text(
                json.dumps({
                    "status": "transport_failed", "submitted": [],
                    "submit_unknown": [], "blocked": ["row-1"],
                }),
                encoding="utf-8",
            )
            command = (
                "/bin/zsh -lc '/opt/homebrew/bin/python3 -m "
                "job_search_loop.browser_agent.runtime wait --milliseconds 6000'"
            )
            events = [
                {"type": "item.started", "item": {
                    "id": "wait-1", "type": "command_execution", "command": command,
                }},
                {"type": "item.completed", "item": {
                    "id": "wait-1", "type": "command_execution", "command": command,
                    "exit_code": 1, "aggregated_output": "runtime failure",
                }},
            ]
            (root / "stdout.log").write_text(
                "".join(json.dumps(item) + "\n" for item in events), encoding="utf-8",
            )
            completed = Mock(returncode=0)
            with patch(
                "job_search_loop.browser_agent.orchestrator.subprocess.run",
                return_value=completed,
            ) as run:
                returncode = orchestrator.invoke_runner(
                    runner=Path("/runtime/agent_runner.py"),
                    prompt=Path("/app/prompts/daily-pass.md"),
                    schema=Path("/app/schemas/pass-result.v1.schema.json"),
                    evidence_dir=root,
                    workdir=Path("/repo"),
                    timeout_seconds=900,
                    python="/python3",
                    active_provider="workday",
                )

            self.assertEqual(returncode, 2)
            self.assertEqual(run.call_count, 2)
            receipt = json.loads(
                (root / "semantic-validation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["reason"], "runtime_command_nonzero_completion")

    def test_invoke_runner_never_retries_submit_unknown_after_runtime_failure(self):
        from job_search_loop.browser_agent import orchestrator

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_queue_complete_observe_fixture(root, ())
            summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            summary["status"] = "success"
            (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (root / "result.json").write_text(
                json.dumps({
                    "status": "transport_failed", "submitted": [],
                    "submit_unknown": ["row-1"], "blocked": ["row-1"],
                }),
                encoding="utf-8",
            )
            command = "/bin/zsh -lc '/opt/homebrew/bin/python3 -m job_search_loop.browser_agent.runtime "
            wait = command + "wait --milliseconds 6000'"
            observe = command + "observe'"
            events = [
                {"type": "item.started", "item": {
                    "id": "wait-1", "type": "command_execution", "command": wait,
                }},
                {"type": "item.completed", "item": {
                    "id": "wait-1", "type": "command_execution", "command": wait,
                    "exit_code": 1, "aggregated_output": "runtime failure",
                }},
                {"type": "item.started", "item": {
                    "id": "observe-1", "type": "command_execution", "command": observe,
                }},
                {"type": "item.completed", "item": {
                    "id": "observe-1", "type": "command_execution", "command": observe,
                    "exit_code": 0, "aggregated_output": json.dumps({"status": "observed"}),
                }},
            ]
            (root / "stdout.log").write_text(
                "".join(json.dumps(item) + "\n" for item in events), encoding="utf-8",
            )
            completed = Mock(returncode=0)
            with patch(
                "job_search_loop.browser_agent.orchestrator.subprocess.run",
                return_value=completed,
            ) as run:
                returncode = orchestrator.invoke_runner(
                    runner=Path("/runtime/agent_runner.py"),
                    prompt=Path("/app/prompts/daily-pass.md"),
                    schema=Path("/app/schemas/pass-result.v1.schema.json"),
                    evidence_dir=root,
                    workdir=Path("/repo"),
                    timeout_seconds=900,
                    python="/python3",
                    active_provider="workday",
                )

            self.assertEqual(returncode, 2)
            run.assert_called_once()
            receipt = json.loads(
                (root / "semantic-validation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["reason"], "submission_outcome_unknown")

    def test_semantic_retry_shares_the_original_wake_timeout(self):
        from job_search_loop.browser_agent import orchestrator

        completed = Mock(returncode=0)
        clock = Mock(monotonic=Mock(side_effect=(0.0, 0.0, 600.0)))
        with tempfile.TemporaryDirectory() as directory, patch.object(
            orchestrator.subprocess,
            "run",
            side_effect=(completed, completed),
        ) as run, patch.object(
            orchestrator,
            "validate_pass_result",
            side_effect=("transport_failed_without_command_failure", None),
        ), patch.object(orchestrator, "time", clock, create=True):
            returncode = orchestrator.invoke_runner(
                runner=Path("/runtime/agent_runner.py"),
                prompt=Path("/app/prompts/daily-pass.md"),
                schema=Path("/app/schemas/pass-result.v1.schema.json"),
                evidence_dir=Path(directory),
                workdir=Path("/repo"),
                timeout_seconds=900,
                python="/python3",
                active_provider="workday",
            )

        self.assertEqual(returncode, 0)
        first_command = run.call_args_list[0].args[0]
        second_command = run.call_args_list[1].args[0]
        self.assertEqual(
            first_command[first_command.index("--timeout-seconds") + 1], "900"
        )
        self.assertEqual(
            second_command[second_command.index("--timeout-seconds") + 1], "300"
        )

    def test_every_eligible_workday_row_reaches_the_mandatory_model_lane(self):
        daily = (APP_ROOT / "scripts" / "run-daily.sh").read_text(encoding="utf-8")
        prompt = (APP_ROOT / "prompts" / "daily-pass.md").read_text(encoding="utf-8")
        normalized_prompt = " ".join(prompt.split())

        self.assertNotIn("JOB_SEARCH_ENABLE_MODEL_FALLBACK", daily)
        self.assertNotIn("-m job_search_loop.workday_fast_path", daily)
        self.assertEqual(
            daily.count("-m job_search_loop.browser_agent.orchestrator"), 1
        )
        self.assertIn('"status": "model_owned"', daily)
        self.assertIn("Process every eligible ATS row", prompt)
        self.assertIn("Workday and Ashby use this same agent loop", prompt)
        self.assertIn("A row-local failure never ends the queue", normalized_prompt)
        self.assertNotIn("do not reopen a row it advanced", prompt)
        self.assertNotIn("preserve that exact blocker", prompt)

    def test_workday_and_ashby_share_the_model_application_lane_after_10p(self):
        daily = (APP_ROOT / "scripts" / "run-daily.sh").read_text(encoding="utf-8")
        prompt = (APP_ROOT / "prompts" / "daily-pass.md").read_text(encoding="utf-8")
        normalized_prompt = " ".join(prompt.split())

        self.assertNotIn("-m job_search_loop.ashby_discovery", daily)
        self.assertNotIn("-m job_search_loop.greenhouse_discovery", daily)
        self.assertNotIn("-m job_search_loop.lever_discovery", daily)
        self.assertIn('"status": "model_owned"', daily)
        self.assertIn('"reason": "mandatory_browser_lane"', daily)
        self.assertIn("--active-provider workday", daily)
        self.assertNotIn("Never open Ashby", prompt)
        self.assertIn("Process every eligible ATS row", prompt)
        self.assertIn("Workday and Ashby use this same agent loop", prompt)

    def test_daily_exports_the_validated_rolling_deficit_to_queue(self):
        daily = (APP_ROOT / "scripts" / "run-daily.sh").read_text(encoding="utf-8")
        self.assertIn(".deficit", daily)
        self.assertIn("JOB_SEARCH_APPLICATION_LIMIT", daily)


if __name__ == "__main__":
    unittest.main()
