import hashlib
import io
import unittest
import inspect
import json
import tempfile
import fcntl
import os
import time
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from job_search_loop.browser_agent.direct_cdp import DirectCDPPage
from job_search_loop.browser_agent.observation import ObservationBuilder
from job_search_loop.browser_agent.actions import ActionExecutor
from job_search_loop.browser_agent.contracts import (
    ActionTargetV1,
    SessionHandleV1,
    VisibleActionV1,
)
from job_search_loop.browser_agent.runtime import main as browser_runtime_main
from job_search_loop.browser_agent.runtime import auth, type_candidate, type_text
from job_search_loop.ledger import Ledger
from job_search_loop.runtime import main as compatibility_runtime_main


class DirectCDPTypeTests(unittest.IsolatedAsyncioTestCase):
    async def test_goto_waits_for_an_absolute_https_url_after_about_blank_ready_state(self):
        page = DirectCDPPage("ws://example", "target")
        page.call = AsyncMock(return_value={})
        page.evaluate = AsyncMock(
            side_effect=(
                "complete",
                "about:blank",
                "complete",
                "https://danaher.wd1.myworkdayjobs.com/DanaherJobs/job/role",
            )
        )

        with patch(
            "job_search_loop.browser_agent.direct_cdp.asyncio.sleep",
            new=AsyncMock(),
        ):
            await page.goto("https://danaher.wd1.myworkdayjobs.com/DanaherJobs/job/role")

        self.assertEqual(
            page.url,
            "https://danaher.wd1.myworkdayjobs.com/DanaherJobs/job/role",
        )
        self.assertEqual(page.evaluate.await_count, 4)

    async def test_wait_recovers_previous_https_url_after_target_returns_to_about_blank(self):
        page = DirectCDPPage("ws://example", "target")
        page.url = "https://danaher.wd1.myworkdayjobs.com/DanaherJobs/job/role"
        page.evaluate = AsyncMock(return_value="about:blank")
        page.goto = AsyncMock()

        with patch(
            "job_search_loop.browser_agent.direct_cdp.asyncio.sleep",
            new=AsyncMock(),
        ):
            await page.wait_for_timeout(6000)

        page.goto.assert_awaited_once_with(page.url)

    async def test_click_observes_after_mouse_release_response_timeout_without_retry(self):
        page = DirectCDPPage("ws://example", "target")
        page.resolve_target = AsyncMock(return_value={"x": 10.0, "y": 20.0})
        page.call = AsyncMock(side_effect=({}, {}, TimeoutError("release response")))
        page.evaluate = AsyncMock(return_value="about:blank")

        with patch(
            "job_search_loop.browser_agent.direct_cdp.asyncio.sleep",
            new=AsyncMock(),
        ):
            await page.click_target(
                {"label": "Next", "role": "button", "stable_id": "next"}
            )

        self.assertEqual(page.call.await_count, 3)
        self.assertEqual(
            page.call.await_args_list[-1].args[1]["type"], "mouseReleased"
        )
        page.evaluate.assert_awaited_once_with("() => location.href")

    async def test_close_detaches_websocket_without_closing_leased_target(self):
        page = DirectCDPPage("ws://example", "target")
        page._ws = AsyncMock()
        page.call = AsyncMock()

        await page.close()

        page.call.assert_not_awaited()
        page._ws.close.assert_awaited_once()
        self.assertTrue(page.is_closed())

    async def test_email_recovery_checkpoint_persists_tenant_recovery_state(self):
        from job_search_loop.browser_agent import runtime

        row = {
            "application_id": "application:recovery",
            "company": "Cloudera",
            "title": "Applied AI Specialist",
            "canonical_url": "https://cloudera.wd5.myworkdayjobs.com/job/role",
        }
        session = Mock(close_owned=AsyncMock())
        checkpoints = Mock()
        checkpoints.save.return_value = Mock(checkpoint_sha256="a" * 64)
        cursor = Mock(checkpoint=None)
        cursor.handle.page_marker = "page"
        cursor.handle.generation = 1
        observation = Mock(content_sha256="b" * 64, url=row["canonical_url"])
        builder = Mock(build=AsyncMock(return_value=observation))
        context = (row, session, checkpoints, Mock(), cursor, builder)
        store = Mock()
        completed = Mock()
        sender = Mock(return_value={"status": "sent", "message_id": "recovery-1"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "JOB_SEARCH_MACHINE_CREDENTIALS": root / "credentials.json",
                "JOB_SEARCH_STATE_ROOT": root / "state",
                "JOB_SEARCH_BROWSER_OWNER_EVIDENCE": root / "evidence" / "wake-1" / "browser-owner.json",
            }
            with patch.object(
                runtime, "_context", new=AsyncMock(return_value=context)
            ), patch.object(
                runtime, "_path_env", side_effect=lambda name: paths[name]
            ), patch.object(
                runtime, "MachineWorkdayCredentialStore", return_value=store
            ), patch.object(
                runtime, "send_hourly_outcomes", sender
            ), patch.object(
                runtime, "_mark_wake_completed", completed
            ):
                result = await runtime.checkpoint("email_recovery")

        self.assertEqual(result["status"], "checkpointed")
        self.assertEqual(result["application_id"], row["application_id"])
        self.assertEqual(result["report_message_id"], "recovery-1")
        sender.assert_called_once()
        completed.assert_called_once_with(row["application_id"])
        store.mark_account_status.assert_called_once_with(
            row["canonical_url"], "recovery_requested"
        )

    async def test_recovery_requested_rejects_duplicate_forgot_password_effect(self):
        from job_search_loop.browser_agent import runtime

        row = {
            "canonical_url": "https://cloudera.wd5.myworkdayjobs.com/job/role"
        }
        store = Mock(account_status=Mock(return_value="recovery_requested"))
        observation = {"status": "observed", "observation": {"controls": []}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            runtime, "_row", return_value=row
        ), patch.object(
            runtime, "_path_env", return_value=Path(directory)
        ), patch.object(
            runtime, "MachineWorkdayCredentialStore", return_value=store
        ), patch.object(
            runtime,
            "checkpoint",
            new=AsyncMock(
                return_value={
                    "status": "checkpointed",
                    "reason": "email_recovery",
                }
            ),
        ) as checkpoint, patch.object(
            runtime, "observe", new=AsyncMock(return_value=observation)
        ), patch.object(
            runtime, "act", new=AsyncMock(return_value={"status": "acted"})
        ) as act:
            result = await runtime.click(
                label="Forgot your password?",
                role="button",
                stable_id="automation:forgotPasswordLink",
            )

        self.assertEqual(result["status"], "checkpointed")
        self.assertEqual(result["reason"], "email_recovery")
        checkpoint.assert_awaited_once_with("email_recovery")
        act.assert_not_awaited()

    async def test_failed_sign_in_preserves_recovery_requested_status(self):
        from job_search_loop.browser_agent import runtime

        row = {
            "canonical_url": "https://cloudera.wd5.myworkdayjobs.com/job/role"
        }
        store = Mock(account_status=Mock(return_value="recovery_requested"))
        acted = {
            "status": "acted",
            "observation": {
                "validation": [],
                "controls": [
                    {"stable_id": "automation:signInSubmitButton"}
                ],
                "title": "Sign In",
            },
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(
            runtime, "_row", return_value=row
        ), patch.object(
            runtime, "_path_env", return_value=Path(directory)
        ), patch.object(
            runtime, "MachineWorkdayCredentialStore", return_value=store
        ), patch.object(
            runtime, "act", new=AsyncMock(return_value=acted)
        ):
            await runtime.click(
                label="Sign In",
                role="button",
                stable_id="automation:signInSubmitButton",
            )

        store.mark_account_status.assert_called_once_with(
            row["canonical_url"], "recovery_requested"
        )

    def test_command_lock_rejects_the_active_runtime_command_immediately(self):
        from job_search_loop.browser_agent import runtime

        with tempfile.TemporaryDirectory() as directory, patch.object(
            runtime, "_path_env", return_value=Path(directory)
        ):
            path = Path(directory) / "command.lock"
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            lock = os.fdopen(descriptor, "r+")
            self.addCleanup(lock.close)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            started = time.monotonic()
            with self.assertRaisesRegex(
                RuntimeError,
                "another browser runtime command is already in progress",
            ):
                with runtime._exclusive_command():
                    pass
            self.assertLess(time.monotonic() - started, 0.1)

    async def test_observe_compacts_navigation_receipt_but_keeps_normal_context(self):
        from job_search_loop.browser_agent import runtime

        row = {"application_id": "application:observe", "company": "Example", "title": "Example Role", "canonical_url": "https://jobs.ashbyhq.com/example/role"}
        cursor = Mock(handle=Mock(), checkpoint=None, needs_navigation=True, recovery_url=row["canonical_url"])
        memory = Mock(concepts=Mock(return_value=("candidate.name",)), grounding_facts=Mock(return_value=({"concept": "fact.role"},)))
        context = (row, Mock(), Mock(), Mock(), cursor, Mock(build=AsyncMock()))

        with patch.object(runtime, "_context", new=AsyncMock(return_value=context)), patch.object(runtime, "_path_env", return_value=Path("/tmp/candidate-memory.json")), patch.object(runtime.CandidateMemoryView, "load", return_value=memory), patch.object(runtime, "_safe_observation", return_value={"url": "about:blank"}), patch.object(runtime, "_wake_budget", return_value=99):
            navigation = await runtime.observe()
            self.assertEqual(set(navigation), {"status", "row", "needs_navigation", "recovery_url", "observation"})
            self.assertEqual((navigation["status"], navigation["needs_navigation"], navigation["recovery_url"]), ("observed", True, row["canonical_url"]))
            self.assertNotIn("candidate_concepts", navigation)
            self.assertNotIn("grounding_facts", navigation)

            cursor.needs_navigation = False
            normal = await runtime.observe()
            self.assertEqual(normal["candidate_concepts"], ("candidate.name", "policy.prefer_not_to_say"))
            self.assertEqual(normal["grounding_facts"], ({"concept": "fact.role"},))

    def test_terminal_marker_lifecycle_blocks_stale_wake_and_allows_next_wake(self):
        from job_search_loop.browser_agent import runtime

        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            active = scratch / "active-command.json"
            active.write_text('{"reason":"command_active","status":"active"}\n')
            active.chmod(0o600)
            finalize = AsyncMock(return_value={"status": "submitted"})
            with patch.object(runtime, "_path_env", return_value=scratch), patch.object(
                runtime, "finalize", new=finalize
            ):
                with self.assertRaisesRegex(RuntimeError, "terminal runtime failure"):
                    runtime.main(["finalize"])
                marker = scratch / "terminal-failure.json"
                self.assertTrue(active.exists())
                self.assertEqual(
                    json.loads(marker.read_text()),
                    {"reason": "runtime_failure", "status": "terminal"},
                )
                self.assertEqual(oct(marker.stat().st_mode & 0o777), "0o600")
                with self.assertRaisesRegex(RuntimeError, "terminal runtime failure"):
                    runtime.main(["finalize"])
                finalize.assert_not_called()

        with tempfile.TemporaryDirectory() as directory, patch.object(
            runtime, "_path_env", return_value=Path(directory)
        ), patch.object(
            runtime, "observe", new=AsyncMock(return_value={"status": "observed"})
        ) as observe:
            runtime.main(["observe"])
            self.assertFalse((Path(directory) / "active-command.json").exists())
            self.assertFalse((Path(directory) / "terminal-failure.json").exists())
            runtime.main(["observe"])
            self.assertEqual(observe.await_count, 2)

    async def test_auth_rejects_html_input_type_as_a_role_before_secret_action(self):
        from job_search_loop.browser_agent import runtime

        observation = {"status": "observed", "observation": {"controls": []}}
        with patch.object(
            runtime, "observe", new=AsyncMock(return_value=observation)
        ) as observe, patch.object(
            runtime, "_context", new=AsyncMock()
        ) as context:
            result = await auth(
                mode="sign_in",
                field="password",
                label="Password*",
                role="password",
                stable_id="id:input-5",
            )

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "auth_requires_textbox_role")
        observe.assert_awaited_once()
        context.assert_not_awaited()

    def test_observation_ignores_only_the_passive_recaptcha_badge(self):
        source = inspect.getsource(ObservationBuilder.build)

        self.assertIn("!el.closest('.grecaptcha-badge')", source)
        self.assertIn("iframe,[data-sitekey]", source)

    async def test_literal_type_rejects_an_expired_target_with_fresh_observation(self):
        from job_search_loop.browser_agent import runtime

        observation = {"status": "observed", "observation": {"controls": []}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            runtime,
            "_act_locked",
            new=AsyncMock(
                side_effect=RuntimeError(
                    "action target must resolve to exactly one visible enabled control (count=0)"
                )
            ),
        ), patch.object(
            runtime, "observe", new=AsyncMock(return_value=observation)
        ) as observe, patch.object(
            runtime, "_path_env", return_value=Path(directory)
        ):
            result = await type_text(
                label="Year", role="spinbutton", stable_id="id:expired", text="2020"
            )

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "observed_text_target_no_longer_visible")
        observe.assert_awaited_once()

    async def test_literal_type_rejects_focus_lost_during_controlled_rerender(self):
        from job_search_loop.browser_agent import runtime

        observation = {"status": "observed", "observation": {"controls": []}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            runtime,
            "_act_locked",
            new=AsyncMock(
                side_effect=RuntimeError(
                    "visible text target did not accept whole-value selection"
                )
            ),
        ), patch.object(
            runtime, "observe", new=AsyncMock(return_value=observation)
        ) as observe, patch.object(
            runtime, "_path_env", return_value=Path(directory)
        ):
            result = await type_text(
                label="Country*", role="combobox", stable_id="id:country", text="Japan"
            )

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "observed_text_target_lost_focus")
        observe.assert_awaited_once()

    async def test_type_rejects_non_text_control_without_browser_action(self):
        observation = {"status": "observed", "observation": {"controls": []}}
        with patch(
            "job_search_loop.browser_agent.runtime.observe",
            new=AsyncMock(return_value=observation),
        ) as observe, patch(
            "job_search_loop.browser_agent.runtime.act",
            new=AsyncMock(),
        ) as act:
            result = await type_candidate(
                label="Please Select One",
                role="button",
                stable_id="id:gender",
                candidate_concept="policy.prefer_not_to_say",
            )

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "type_requires_text_control")
        observe.assert_awaited_once()
        act.assert_not_awaited()

    async def test_candidate_type_rejects_focus_lost_during_controlled_rerender(self):
        from job_search_loop.browser_agent import runtime

        observation = {"status": "observed", "observation": {"controls": []}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            runtime,
            "act",
            new=AsyncMock(
                side_effect=RuntimeError(
                    "visible text target did not accept whole-value selection"
                )
            ),
        ), patch.object(
            runtime, "observe", new=AsyncMock(return_value=observation)
        ) as observe, patch.object(
            runtime, "_path_env", return_value=Path(directory)
        ):
            result = await type_candidate(
                label="First Name",
                role="textbox",
                stable_id="id:first_name",
                candidate_concept="candidate.name_romaji_parts.given",
            )

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "observed_text_target_lost_focus")
        observe.assert_awaited_once()

    async def test_candidate_type_rejects_a_non_scalar_concept_before_action(self):
        from job_search_loop.browser_agent import runtime

        observation = {"status": "observed", "observation": {"controls": []}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            runtime,
            "act",
            new=AsyncMock(
                side_effect=ValueError("candidate concept is not a scalar browser value")
            ),
        ), patch.object(
            runtime, "observe", new=AsyncMock(return_value=observation)
        ) as observe, patch.object(
            runtime, "_path_env", return_value=Path(directory)
        ):
            result = await type_candidate(
                label="Location (City)*",
                role="combobox",
                stable_id="id:candidate-location",
                candidate_concept="candidate.location_preferences",
            )

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "candidate_concept_requires_scalar_value")
        observe.assert_awaited_once()

    async def test_premature_finalize_returns_fresh_action_rejection_before_fence(self):
        from job_search_loop.browser_agent import runtime

        observation = unittest.mock.Mock(
            controls=(),
            url="https://jobs.ashbyhq.com/example/role/application",
            title="Role @ Example",
            visible_text="Editable application form",
            content_sha256="a" * 64,
            validation_text=(),
            visible_challenges=(),
        )
        cursor = unittest.mock.Mock(checkpoint=None)
        cursor.handle.row_run_id = "row-run"
        builder = unittest.mock.Mock()
        builder.build = AsyncMock(return_value=observation)
        context = (
            {
                "application_id": "application",
                "company": "Example",
                "title": "Role",
                "canonical_url": "https://jobs.ashbyhq.com/example/role",
            },
            unittest.mock.Mock(),
            unittest.mock.Mock(),
            unittest.mock.Mock(),
            cursor,
            builder,
        )
        verifier = unittest.mock.Mock()
        verifier.verify = AsyncMock(return_value=unittest.mock.Mock())
        with patch.object(
            runtime, "_context", new=AsyncMock(return_value=context)
        ), patch.object(
            runtime,
            "_routed_resume",
            return_value={"resume_path": "/tmp/resume.pdf", "resume_sha256": "b" * 64},
        ), patch.object(
            runtime, "ResumeVerifier", return_value=verifier
        ), patch.object(
            runtime,
            "verify_final_review",
            side_effect=RuntimeError("company or role is absent from final review"),
        ), patch.object(runtime, "_wake_budget", return_value=9), patch.object(
            runtime, "Ledger"
        ) as ledger:
            result = await runtime.finalize()

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "final_review_not_ready")
        self.assertEqual(result["observation"]["url"], observation.url)
        ledger.assert_not_called()

    async def test_arbitrary_upload_cannot_bypass_the_routed_resume(self):
        from job_search_loop.browser_agent import runtime
        row = {"application_id": "row", "title": "Role"}
        builder = unittest.mock.Mock()
        builder.build = AsyncMock(return_value=unittest.mock.Mock(visible_text="Form", content_sha256="a" * 64))
        context = (row, None, None, None, unittest.mock.Mock(), builder)
        executor = unittest.mock.Mock()
        executor.execute = AsyncMock(side_effect=AssertionError("wrong resume reached provider"))
        with patch.object(runtime, "_context", new=AsyncMock(return_value=context)), patch.object(
            runtime, "_private_action", return_value={"kind": "upload", "file_path": "/tmp/other.pdf", "target": {"role": "button", "label": "Resume"}}
        ), patch.object(runtime, "_routed_resume", return_value={"resume_path": "/tmp/company-tailored.pdf"}), patch.object(
            runtime, "ActionExecutor", return_value=executor
        ), patch.object(runtime, "_reject_repeated_decision", return_value="signature"), patch.object(runtime, "_wake_budget", return_value=8):
            result = await runtime._act_locked(Path("unused-action.json"))
        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "upload_must_use_routed_resume")
        executor.execute.assert_not_awaited()

    async def test_upload_rejects_file_textbox_before_file_chooser(self):
        from job_search_loop.browser_agent import runtime

        observation = {"status": "observed", "observation": {"controls": []}}
        with patch.object(
            runtime,
            "observe",
            new=AsyncMock(return_value=observation),
        ) as observe, patch.object(
            runtime,
            "_context",
            new=AsyncMock(),
        ) as context:
            result = await runtime.upload_resume(
                label="Resume",
                role="textbox",
                stable_id="id:_systemfield_resume",
            )

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "upload_requires_button_control")
        observe.assert_awaited_once()
        context.assert_not_awaited()

    async def test_upload_rejects_a_button_that_opens_no_file_chooser(self):
        from job_search_loop.browser_agent import runtime

        row = {"title": "Role"}
        cursor = unittest.mock.Mock()
        builder = unittest.mock.Mock()
        builder.build = AsyncMock(return_value=unittest.mock.Mock(visible_text="Form"))
        context = (row, None, None, None, cursor, builder)
        observation = {"status": "observed", "observation": {"controls": []}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            runtime, "_context", new=AsyncMock(return_value=context)
        ), patch.object(
            runtime,
            "_routed_resume",
            return_value={"resume_path": "/tmp/resume.pdf"},
        ), patch.object(
            runtime, "act", new=AsyncMock(side_effect=TimeoutError())
        ), patch.object(
            runtime, "observe", new=AsyncMock(return_value=observation)
        ) as observe, patch.object(
            runtime, "_path_env", return_value=Path(directory)
        ):
            result = await runtime.upload_resume(
                label="Attach", role="button", stable_id="ref:e23"
            )

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "upload_control_did_not_open_file_chooser")
        observe.assert_awaited_once()

    async def test_screenshot_does_not_reflow_virtualized_provider_lists(self):
        page = DirectCDPPage("ws://example", "target")
        page._ensure_viewport = AsyncMock()
        page.call = AsyncMock(return_value={"data": "eA=="})

        await page.screenshot(full_page=True)

        self.assertFalse(page.call.await_args.args[1]["captureBeyondViewport"])

    def test_short_runtime_entrypoint_is_the_same_bounded_runtime(self):
        self.assertIs(compatibility_runtime_main, browser_runtime_main)

    async def test_choose_reopens_an_expired_overlay_and_clicks_the_option_atomically(self):
        page = DirectCDPPage("ws://example", "target")
        page.click_target = AsyncMock(side_effect=[RuntimeError("expired id"), None])
        session = unittest.mock.Mock()
        session.page.return_value = page
        action = VisibleActionV1(
            "choose",
            target=ActionTargetV1("option", "Website", stable_id="id:menuItem"),
            opener=ActionTargetV1("button", "Source options", stable_id="automation:promptSearchButton"),
        )

        await ActionExecutor(session)._execute_direct(page, action)

        self.assertEqual(page.click_target.await_count, 2)

    def test_target_resolution_includes_pointer_operated_provider_controls(self):
        script = DirectCDPPage._target_script(
            {"label": "Search options", "role": "button", "stable_id": "automation:picker"}
        )
        self.assertIn("[data-automation-id]", script)
        self.assertIn("cursor==='pointer'?'button'", script)
        self.assertIn("relatedInput", script)
        self.assertIn("if (resolvedByStableId) return true", script)
        self.assertIn("closest('[role=\"option\"]')", inspect.getsource(ObservationBuilder.build))

    def test_anonymous_fieldset_textarea_uses_question_label_for_observe_and_resolve(self):
        observation_source = inspect.getsource(ObservationBuilder.build)
        target_source = DirectCDPPage._target_script(
            {"label": "Notice Period", "role": "textbox", "stable_id": "ref:e1"}
        )

        for source in (observation_source, target_source):
            self.assertIn("const fieldsetLabel", source)
            self.assertIn("fieldsetControls.length", source)
            self.assertIn("input,select,textarea,button", source)
            self.assertIn("closest('fieldset')", source)
            self.assertIn("querySelector(':scope > legend')", source)
        self.assertIn("!/^error\\\\b/i.test", observation_source)
        self.assertIn("!/^error\\b/i.test", target_source)
        self.assertIn("fieldsetLabel", observation_source)
        self.assertIn("fieldsetLabel", target_source)
        self.assertLess(
            observation_source.index("|| fieldsetLabel ||"),
            observation_source.index("el.getAttribute('placeholder')"),
        )
        self.assertLess(
            target_source.index("||fieldsetLabel||"),
            target_source.index("el.getAttribute('placeholder')"),
        )

    async def test_type_selects_the_existing_whole_value_before_inserting(self):
        page = DirectCDPPage("ws://example", "target")
        page.click_target = AsyncMock(side_effect=AssertionError("typing must focus before transition wait"))
        page.resolve_target = AsyncMock(return_value={"x": 10.0, "y": 20.0})
        page.evaluate = AsyncMock(return_value=True)
        page.call = AsyncMock(return_value={})

        await page.type_target(
            {"label": "First name", "role": "textbox", "stable_id": "ref:e1"},
            "Daisuke",
        )

        page.evaluate.assert_awaited_once()
        page.click_target.assert_not_awaited()
        page.resolve_target.assert_awaited_once()
        self.assertEqual(page.call.await_args_list[0].args[0], "Input.dispatchMouseEvent")
        self.assertIn("el.select()", page.evaluate.await_args.args[0])
        self.assertIn("el.value.length === 0", page.evaluate.await_args.args[0])
        self.assertIn("document.activeElement === el", page.evaluate.await_args.args[0])
        self.assertEqual(
            [call.args for call in page.call.await_args_list if call.args[0] == "Input.insertText"],
            [("Input.insertText", {"text": "Daisuke"})],
        )

    async def test_type_reacquires_focus_once_after_controlled_search_rerender(self):
        page = DirectCDPPage("ws://example", "target")
        page.resolve_target = AsyncMock(return_value={"x": 10.0, "y": 20.0})
        page.evaluate = AsyncMock(side_effect=[False, True])
        page.call = AsyncMock(return_value={})

        await page.type_target(
            {"label": "Type to search", "role": "textbox", "stable_id": "ref:search"},
            "Developer",
        )

        self.assertEqual(page.resolve_target.await_count, 2)
        self.assertEqual(page.evaluate.await_count, 2)
        self.assertEqual(
            [call.args for call in page.call.await_args_list if call.args[0] == "Input.insertText"],
            [("Input.insertText", {"text": "Developer"})],
        )

    async def test_scroll_target_wheels_inside_the_exact_visible_option(self):
        page = DirectCDPPage("ws://example", "target")
        target = {
            "label": "Afghanistan",
            "role": "option",
            "stable_id": "ref:e14",
        }
        page.resolve_target = AsyncMock(return_value={"x": 420.0, "y": 615.0})
        page.call = AsyncMock(return_value={})

        with patch(
            "job_search_loop.browser_agent.direct_cdp.asyncio.sleep",
            new=AsyncMock(),
        ):
            await page.scroll_target(target, delta_y=300)

        page.resolve_target.assert_awaited_once_with(target, scroll=False)
        page.call.assert_awaited_once_with(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseWheel",
                "x": 420.0,
                "y": 615.0,
                "deltaX": 0,
                "deltaY": 300,
            },
        )

    async def test_direct_scroll_action_uses_the_observed_option_as_its_anchor(self):
        page = DirectCDPPage("ws://example", "target")
        page.scroll_target = AsyncMock()
        page.scroll = AsyncMock()
        target = ActionTargetV1("option", "Afghanistan", stable_id="ref:e14")
        action = VisibleActionV1("scroll", target=target, delta_y=300)

        await ActionExecutor(unittest.mock.Mock())._execute_direct(page, action)

        page.scroll_target.assert_awaited_once_with(
            {
                "role": "option",
                "label": "Afghanistan",
                "exact": True,
                "stable_id": "ref:e14",
                "ordinal": None,
            },
            300,
        )
        page.scroll.assert_not_awaited()

    async def test_playwright_scroll_moves_to_the_observed_option_before_wheeling(self):
        page = Mock()
        page.url = "https://venaenergy.wd102.myworkdayjobs.com/careers"
        page.mouse.move = AsyncMock()
        page.mouse.wheel = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        session = Mock()
        session.page.return_value = page
        target = ActionTargetV1("option", "Afghanistan", stable_id="ref:e14")
        locator = Mock()
        locator.bounding_box = AsyncMock(
            return_value={"x": 400.0, "y": 600.0, "width": 120.0, "height": 24.0}
        )
        executor = ActionExecutor(session)
        executor._target = AsyncMock(return_value=locator)
        handle = SessionHandleV1(1, "http://localhost:9222", "wake-1", "page-1", 1)
        action = VisibleActionV1("scroll", target=target, delta_y=300)

        await executor.execute(handle, action)

        executor._target.assert_awaited_once_with(page, target)
        page.mouse.move.assert_awaited_once_with(460.0, 612.0)
        page.mouse.wheel.assert_awaited_once_with(0, 300)
        page.wait_for_timeout.assert_awaited_once_with(350)

    async def test_scroll_runtime_writes_only_the_observed_anchor_and_removes_action_file(self):
        from job_search_loop.browser_agent import runtime

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            received = {}

            async def consume(action_path):
                received["value"] = json.loads(action_path.read_text(encoding="utf-8"))
                received["mode"] = os.stat(action_path).st_mode & 0o777
                return {"status": "acted"}

            with patch.object(runtime, "_path_env", return_value=root), patch.object(
                runtime, "act", new=consume
            ):
                result = await runtime.scroll(
                    label="Afghanistan",
                    role="option",
                    stable_id="ref:e14",
                    delta_y=300,
                )

            self.assertEqual(result, {"status": "acted"})
            self.assertEqual(received["mode"], 0o600)
            self.assertEqual(
                received["value"],
                {
                    "kind": "scroll",
                    "target": {
                        "label": "Afghanistan",
                        "role": "option",
                        "stable_id": "ref:e14",
                    },
                    "delta_y": 300,
                },
            )
            self.assertFalse((root / "runtime-scroll.json").exists())

    def test_runtime_exposes_targeted_picker_scroll(self):
        from job_search_loop.browser_agent import runtime

        scroll = AsyncMock(return_value={"status": "acted"})
        stdout = io.StringIO()
        with patch.object(runtime, "_claim_active_command"), patch.object(
            runtime, "_clear_active_command"
        ), patch.object(runtime, "_check_terminal_failure_marker"), patch.object(
            runtime, "_exclusive_command", return_value=nullcontext()
        ), patch.object(runtime, "scroll", new=scroll), redirect_stdout(stdout):
            result = browser_runtime_main(
                [
                    "scroll",
                    "--label",
                    "Afghanistan",
                    "--role",
                    "option",
                    "--stable-id",
                    "ref:e14",
                    "--delta-y",
                    "300",
                ]
            )

        self.assertEqual(result, 0)
        scroll.assert_awaited_once_with(
            label="Afghanistan", role="option", stable_id="ref:e14", delta_y=300
        )

    def test_ineligible_preserves_a_claimed_submission_without_terminal_failure(self):
        from job_search_loop.browser_agent import runtime

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_root = root / "state"
            scratch = root / "scratch"
            state_root.mkdir()
            scratch.mkdir()
            url = "https://jobs.ashbyhq.com/example/role"
            ledger = Ledger(state_root / "ledger.sqlite3")
            application_id = ledger.add_application("Example", "AI Engineer", url)
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            resume = root / "resume.pdf"
            resume.write_bytes(b"%PDF-1.4\nresume\n")
            resume_sha256 = hashlib.sha256(resume.read_bytes()).hexdigest()
            snapshot = root / "ats-snapshot.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "url": url,
                        "navigation_committed": True,
                        "frames": [
                            {
                                "url": url,
                                "controls": [
                                    {"tag": "input", "type": "email"},
                                    {"tag": "input", "type": "file"},
                                    {
                                        "tag": "button",
                                        "type": "submit",
                                        "text": "Submit Application",
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            intent = ledger.claim_submission(
                application_id,
                "2026-10-11",
                "payload",
                resume_path=resume,
                resume_sha256=resume_sha256,
                ats_snapshot_path=snapshot,
                ats_snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            )
            ledger.close()

            row = {
                "application_id": application_id,
                "company": "Example",
                "title": "AI Engineer",
                "canonical_url": url,
            }
            session = Mock(close_owned=AsyncMock())
            cursor = Mock(checkpoint=None)
            cursor.handle = Mock()
            observation = Mock(content_sha256="a" * 64)
            builder = Mock(build=AsyncMock(return_value=observation))
            context = (row, session, Mock(), Mock(), cursor, builder)
            owner_evidence = root / "evidence" / "browser-owner.json"
            paths = {
                "JOB_SEARCH_BROWSER_SCRATCH": scratch,
                "JOB_SEARCH_STATE_ROOT": state_root,
                "JOB_SEARCH_BROWSER_OWNER_EVIDENCE": owner_evidence,
            }
            completed = Mock()
            sender = Mock()

            with patch.object(
                runtime, "_context", new=AsyncMock(return_value=context)
            ), patch.object(
                runtime, "_path_env", side_effect=lambda name: paths[name]
            ), patch.object(
                runtime, "_mark_wake_completed", completed
            ), patch.object(
                runtime, "send_hourly_outcomes", sender
            ), redirect_stdout(io.StringIO()):
                self.assertEqual(
                    runtime.main(["ineligible", "--reason", "hard_ineligible"]), 0
                )

            ledger = Ledger(state_root / "ledger.sqlite3")
            try:
                self.assertEqual(ledger.current_state(application_id), "submit_claimed")
                self.assertEqual(
                    ledger.connection.execute(
                        "SELECT status FROM submit_intents WHERE application_id = ?",
                        (application_id,),
                    ).fetchone()[0],
                    "submit_claimed",
                )
                self.assertEqual(
                    ledger.connection.execute(
                        "SELECT COUNT(*) FROM submission_click_phases WHERE intent_id = ? AND fence = ?",
                        (intent.intent_id, intent.fence),
                    ).fetchone()[0],
                    0,
                )
            finally:
                ledger.close()
            self.assertFalse((scratch / "terminal-failure.json").exists())
            completed.assert_called_once_with(application_id)
            session.close_owned.assert_awaited_once_with(cursor.handle)
            sender.assert_not_called()

    async def test_checkpoint_reports_and_completes_the_same_application_atomically(self):
        from types import SimpleNamespace

        from job_search_loop.browser_agent import runtime
        from job_search_loop.browser_agent.contracts import QueueRowReceiptV1

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {
                "application_id": "application-checkpoint-a",
                "company": "Example",
                "title": "Role",
                "canonical_url": "https://jobs.example.com/role",
            }
            session = Mock()
            session.close_owned = AsyncMock()
            checkpoints = Mock()
            checkpoints.save.return_value = Mock(checkpoint_sha256="c" * 64)
            cursor = Mock(checkpoint=None)
            cursor.handle = SimpleNamespace(page_marker="page-1", generation=2)
            observation = SimpleNamespace(
                content_sha256="a" * 64,
                url="https://jobs.example.com/role/application",
            )
            builder = Mock(build=AsyncMock(return_value=observation))
            context = (row, session, checkpoints, Mock(), cursor, builder)
            owner_evidence = root / "evidence" / "wake-1" / "browser-owner.json"
            paths = {
                "JOB_SEARCH_BROWSER_OWNER_EVIDENCE": owner_evidence,
                "JOB_SEARCH_STATE_ROOT": root / "state",
            }
            sender = Mock(
                return_value={"status": "sent", "message_id": "checkpoint-1"}
            )
            completed = Mock()

            with patch.object(
                runtime, "_context", new=AsyncMock(return_value=context)
            ), patch.object(
                runtime, "_path_env", side_effect=lambda name: paths[name]
            ), patch.object(
                runtime, "send_hourly_outcomes", sender
            ), patch.object(
                runtime, "_mark_wake_completed", completed
            ):
                result = await runtime.checkpoint("visible_challenge")

        self.assertEqual(result.get("application_id"), "application-checkpoint-a")
        self.assertEqual(result.get("report_message_id"), "checkpoint-1")
        sender.assert_called_once_with(
            database=root / "state" / "telegram-outbox.sqlite3",
            wake_id="wake-1",
            receipts=(
                QueueRowReceiptV1(
                    "application-checkpoint-a", "Example", "Role", "checkpointed"
                ),
            ),
            evidence_classes={},
        )
        completed.assert_called_once_with("application-checkpoint-a")
        session.close_owned.assert_awaited_once_with(cursor.handle)

    async def test_answer_memory_resolves_an_exact_private_question(self):
        from job_search_loop.browser_agent import runtime
        from job_search_loop.browser_agent.answer_memory import AnswerMemory

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answer-memory.json"
            AnswerMemory(path).remember(
                concept="job_hunter.prior_employment.circles",
                answer="No",
                kind="derived",
                provenance=("uploaded_resume_experience_absent",),
                question_variants=("Have you previously been employed by Circles?",),
            )
            resolver = getattr(runtime, "resolve_saved_answer", None)
            self.assertTrue(callable(resolver), "browser runtime must expose saved answers")
            with patch.object(runtime, "_path_env", return_value=path):
                result = await resolver("Have you previously been employed by Circles?")

        self.assertEqual(result["status"], "answer_found")
        self.assertEqual(result["answer"], "No")
        self.assertEqual(result["kind"], "derived")
        self.assertEqual(result["provenance"], ["uploaded_resume_experience_absent"])

    def test_answer_cli_resolves_saved_answer_without_browser_session(self):
        from contextlib import nullcontext

        from job_search_loop.browser_agent import runtime
        from job_search_loop.browser_agent.answer_memory import AnswerMemory

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answer-memory.json"
            AnswerMemory(path).remember(
                concept="job_hunter.prior_employment.circles",
                answer="No",
                kind="derived",
                provenance=("uploaded_resume_experience_absent",),
                question_variants=("Have you previously been employed by Circles?",),
            )
            output = io.StringIO()
            with patch.object(runtime, "_claim_active_command"), patch.object(
                runtime, "_clear_active_command"
            ), patch.object(
                runtime, "_exclusive_command", return_value=nullcontext()
            ), patch.object(
                runtime, "_check_terminal_failure_marker"
            ), patch.object(
                runtime, "_path_env", return_value=path
            ), redirect_stdout(output):
                result = runtime.main(
                    ["answer", "--question-label", "Have you previously been employed by Circles?"]
                )

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["answer"], "No")

    def test_standalone_checkpoint_report_cannot_select_a_different_row(self):
        from job_search_loop.browser_agent import runtime

        selected_row = Mock(
            return_value={
                "application_id": "next-row",
                "company": "Example",
                "title": "Another Role",
            }
        )
        sender = Mock(return_value={"status": "sent", "message_id": "message-2"})
        paths = {
            "JOB_SEARCH_BROWSER_OWNER_EVIDENCE": Path("/tmp/evidence/wake/browser-owner.json"),
            "JOB_SEARCH_STATE_ROOT": Path("/tmp/state"),
        }
        with patch.object(runtime, "_row", selected_row), patch.object(
            runtime, "send_hourly_outcomes", sender
        ), patch.object(
            runtime, "_path_env", side_effect=lambda name: paths[name]
        ), patch.object(
            runtime, "_mark_wake_completed"
        ):
            result = runtime.report("checkpointed")

        self.assertEqual(result["status"], "action_rejected")
        self.assertEqual(result["reason"], "checkpoint_outcome_is_reported_atomically")
        selected_row.assert_not_called()
        sender.assert_not_called()


if __name__ == "__main__":
    unittest.main()
