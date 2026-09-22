import argparse
import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch
from websocket import WebSocketTimeoutException


SCRIPT = Path(__file__).parents[1] / "scripts" / "provider_cli.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("provider_cli", SCRIPT)
provider_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provider_cli)


class ProviderResumeTest(unittest.TestCase):
    def test_renderer_timeout_reloads_same_target_once_then_retries_observation(self):
        rendered = {
            "url": "https://elevenlabs.io/app/home",
            "title": "Home | ElevenLabs",
            "text": "Affiliate earnings",
        }
        with (
            patch.object(
                provider_cli, "_evaluate_once",
                side_effect=(WebSocketTimeoutException("read timeout"), rendered),
            ) as evaluate_once,
            patch.object(provider_cli, "reload_renderer") as reload_renderer,
        ):
            result = provider_cli.evaluate("127.0.0.1", 9324, "provider-tab")

        self.assertEqual(result, {**rendered, "renderer_recovered": True})
        self.assertEqual(evaluate_once.call_count, 2)
        reload_renderer.assert_called_once_with("127.0.0.1", 9324, "provider-tab")

    def test_renderer_recovery_failure_is_typed_after_one_reload(self):
        with (
            patch.object(
                provider_cli, "_evaluate_once",
                side_effect=WebSocketTimeoutException("read timeout"),
            ) as evaluate_once,
            patch.object(provider_cli, "reload_renderer") as reload_renderer,
        ):
            with self.assertRaises(provider_cli.ProviderRendererError):
                provider_cli.evaluate("127.0.0.1", 9324, "provider-tab")

        self.assertEqual(evaluate_once.call_count, 2)
        reload_renderer.assert_called_once_with("127.0.0.1", 9324, "provider-tab")

    def test_renderer_reload_targets_exact_page_and_waits_for_load(self):
        socket = MagicMock()
        socket.recv.side_effect = (
            json.dumps({"id": 1, "result": {"sessionId": "session-one"}}),
            json.dumps({"id": 2, "sessionId": "session-one", "result": {}}),
            json.dumps({
                "method": "Page.loadEventFired", "sessionId": "foreign-session",
            }),
            json.dumps({"method": "Page.loadEventFired", "sessionId": "session-one"}),
            json.dumps({"id": 3, "sessionId": "session-one", "result": {}}),
        )
        with (
            patch.object(provider_cli, "read_json", return_value={
                "webSocketDebuggerUrl":
                    "ws://127.0.0.1:9324/devtools/browser/browser-one",
            }),
            patch.object(provider_cli, "create_connection", return_value=socket),
        ):
            provider_cli.reload_renderer("127.0.0.1", 9324, "provider-tab")

        sent = [json.loads(item.args[0]) for item in socket.send.call_args_list]
        self.assertEqual(sent[0]["method"], "Target.attachToTarget")
        self.assertEqual(sent[0]["params"]["targetId"], "provider-tab")
        self.assertTrue(sent[0]["params"]["flatten"])
        self.assertEqual(sent[1]["method"], "Page.enable")
        self.assertEqual(sent[1]["sessionId"], "session-one")
        self.assertEqual(sent[2]["method"], "Page.reload")
        self.assertEqual(sent[2]["sessionId"], "session-one")
        socket.close.assert_called_once()

    def test_renderer_reload_rejects_non_object_browser_version(self):
        with patch.object(provider_cli, "read_json", return_value=[]):
            with self.assertRaises(provider_cli.ProviderRendererError):
                provider_cli.reload_renderer("127.0.0.1", 9324, "provider-tab")

    def test_renderer_reload_rejects_non_browser_websocket_endpoint(self):
        invalid_endpoints = (
            "ws://user@127.0.0.1:9324/devtools/browser/browser-one",
            "ws://127.0.0.1:9324/devtools/page/provider-tab",
            "ws://127.0.0.1:9324/devtools/browser/browser-one?token=secret",
            "ws://127.0.0.1:9324/devtools/browser/browser-one#fragment",
        )
        for endpoint in invalid_endpoints:
            with self.subTest(endpoint=endpoint):
                with patch.object(provider_cli, "read_json", return_value={
                    "webSocketDebuggerUrl": endpoint,
                }):
                    with self.assertRaises(provider_cli.ProviderRendererError):
                        provider_cli.reload_renderer(
                            "127.0.0.1", 9324, "provider-tab",
                        )

    def test_renderer_reload_types_non_object_cdp_reply(self):
        socket = MagicMock()
        socket.recv.return_value = json.dumps([])
        with (
            patch.object(provider_cli, "read_json", return_value={
                "webSocketDebuggerUrl":
                    "ws://127.0.0.1:9324/devtools/browser/browser-one",
            }),
            patch.object(provider_cli, "create_connection", return_value=socket),
        ):
            with self.assertRaises(provider_cli.ProviderRendererError):
                provider_cli.reload_renderer("127.0.0.1", 9324, "provider-tab")

        socket.close.assert_called_once()

    def test_semantic_click_activates_exact_node_directly(self):
        socket = object()
        with (
            patch.object(provider_cli, "query_node_by_text", return_value=(42, 7)),
            patch.object(provider_cli, "cdp_call", side_effect=(
                {"object": {"objectId": "button-object"}}, {},
            )) as call,
        ):
            result = provider_cli.click_text(socket, 1, "button", ["Sign in"])
        self.assertEqual(result, 9)
        self.assertEqual(call.call_args_list[1].args[3]["objectId"], "button-object")
        self.assertIn("this.click()", call.call_args_list[1].args[3]["functionDeclaration"])

    def test_extracts_one_code_without_exposing_message(self):
        self.assertEqual(
            provider_cli.extract_six_digit_codes(None, "Your code is 654321".encode()),
            {"654321"},
        )

    def test_impact_login_advances_through_email_and_password_stages(self):
        args = argparse.Namespace(
            cdp_host="127.0.0.1", cdp_port=9327,
            private_markdown=Path("/private/credentials.md"),
        )
        playbook = {"login": {
            "credential_section": "Impact",
            "username_selector": "input[type='email']",
            "username_submit_selector": "button",
            "username_submit_text_any": ["次へ", "Next"],
            "password_selector": "input[type='password']",
            "password_submit_selector": "button",
            "password_submit_text_any": ["サインイン", "Sign in"],
            "submit_selector": "button[type='submit']",
        }}
        socket = MagicMock()
        with (
            patch.object(provider_cli, "read_login_credentials", return_value=("person@example.com", "secret")),
            patch.object(provider_cli, "create_connection", return_value=socket),
            patch.object(provider_cli, "cdp_call"),
            patch.object(provider_cli, "selector_exists", side_effect=((True, 3), (False, 4))),
            patch.object(provider_cli, "focus_and_type", side_effect=(10, 20)) as typed,
            patch.object(provider_cli, "playwright_click_text") as clicked,
            patch.object(provider_cli, "wait_for_selector", return_value=18) as waited,
        ):
            provider_cli.submit_login(args, playbook, {
                "id": "impact-tab", "url": "https://app.impact.com/login.user",
            })

        self.assertEqual(typed.call_args_list, [
            call(socket, 4, "input[type='email']", "person@example.com"),
            call(socket, 18, "input[type='password']", "secret"),
        ])
        self.assertEqual(clicked.call_count, 2)
        waited.assert_called_once_with(socket, 10, "input[type='password']")
        socket.close.assert_called_once()

    def test_impact_login_resumes_from_rendered_password_stage(self):
        args = argparse.Namespace(
            cdp_host="127.0.0.1", cdp_port=9327,
            private_markdown=Path("/private/credentials.md"),
        )
        playbook = {"login": {
            "credential_section": "Impact",
            "username_selector": "input[type='email']",
            "username_submit_selector": "button",
            "username_submit_text_any": ["Continue"],
            "password_selector": "input[type='password']",
            "password_submit_selector": "button",
            "password_submit_text_any": ["Sign In"],
            "submit_selector": "button[type='submit']",
        }}
        socket = MagicMock()
        with (
            patch.object(provider_cli, "read_login_credentials", return_value=("person@example.com", "secret")),
            patch.object(provider_cli, "create_connection", return_value=socket),
            patch.object(provider_cli, "cdp_call"),
            patch.object(provider_cli, "selector_exists", side_effect=((False, 3), (True, 4))),
            patch.object(provider_cli, "focus_and_type", return_value=8) as typed,
            patch.object(provider_cli, "playwright_click_text") as clicked,
        ):
            provider_cli.submit_login(args, playbook, {
                "id": "impact-tab", "url": "https://app.impact.com/login.user",
            })
        typed.assert_called_once_with(socket, 4, "input[type='password']", "secret")
        clicked.assert_called_once_with(
            "127.0.0.1", 9327, "https://app.impact.com/login.user", ["Sign In"], None,
        )

    def test_single_page_login_fills_email_before_password(self):
        args = argparse.Namespace(
            cdp_host="127.0.0.1", cdp_port=9324,
            private_markdown=Path("/private/credentials.md"),
        )
        playbook = {"login": {
            "credential_section": "ElevenLabs",
            "username_selector": "input[name='email']",
            "password_selector": "input[name='password']",
            "submit_selector": "button:not([disabled])",
        }}
        socket = MagicMock()
        with (
            patch.object(provider_cli, "read_login_credentials", return_value=("person@example.com", "secret")),
            patch.object(provider_cli, "create_connection", return_value=socket),
            patch.object(provider_cli, "cdp_call"),
            patch.object(provider_cli, "selector_exists", side_effect=((True, 3), (True, 4))),
            patch.object(provider_cli, "focus_and_type", side_effect=(8, 12)) as typed,
            patch.object(provider_cli, "wait_for_selector", return_value=13),
            patch.object(provider_cli, "click"),
        ):
            provider_cli.submit_login(args, playbook, {
                "id": "elevenlabs-tab", "url": "https://elevenlabs.io/app/sign-in",
            })
        self.assertEqual(typed.call_args_list, [
            call(socket, 4, "input[name='email']", "person@example.com"),
            call(socket, 8, "input[name='password']", "secret"),
        ])

    def test_reads_plain_and_inconsistently_wrapped_private_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "credentials.md"
            private.write_text(
                "## ElevenLabs\n- Login: person@example.com`\n"
                "- Password: `correct horse battery staple`\n",
                encoding="utf-8",
            )
            private.chmod(0o600)
            self.assertEqual(
                provider_cli.read_login_credentials(private, "ElevenLabs"),
                ("person@example.com", "correct horse battery staple"),
            )

    def test_submits_once_and_never_receipts_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(
                provider="elevenlabs",
                cdp_host="127.0.0.1",
                cdp_port=9324,
                receipt=Path(temporary) / "receipt.json",
                private_markdown=Path(temporary) / "credentials.md",
            )
            states = [
                {"provider": "elevenlabs", "state": "SIGN_IN_REQUIRED"},
                {"provider": "elevenlabs", "state": "AUTHENTICATED"},
            ]
            with (
                patch.object(provider_cli, "observe", side_effect=states),
                patch.object(provider_cli, "read_json", return_value=[{
                    "type": "page", "url": "https://elevenlabs.io/app/sign-in",
                    "title": "Sign In | ElevenLabs", "id": "tab-1",
                }]),
                patch.object(provider_cli, "submit_login", return_value={
                    "http_status": 200,
                    "url_sha256": "b" * 64,
                    "body_sha256": "c" * 64,
                }) as submit,
                patch.object(provider_cli.time, "sleep"),
            ):
                receipt = provider_cli.resume(args)

            self.assertEqual(submit.call_count, 1)
            self.assertTrue(receipt["submitted"])
            self.assertEqual(receipt["state"], "AUTHENTICATED")
            serialized = json.dumps(receipt)
            self.assertNotIn("password", serialized.lower())
            self.assertNotIn("credential", serialized.lower())

    def test_unresolved_login_effect_observes_without_resubmitting_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            provider_cli.start_effect(
                state, "PROVIDER_LOGIN", "elevenlabs",
                {"operation": "submit_login", "provider": "elevenlabs"},
                {"state": "SIGN_IN_REQUIRED"}, 300,
            )
            args = argparse.Namespace(
                provider="elevenlabs", cdp_host="127.0.0.1", cdp_port=9324,
                receipt=Path(temporary) / "resume.json", state=state,
                private_markdown=Path(temporary) / "credentials.md",
            )
            signed_out = {
                "provider": "elevenlabs", "state": "SIGN_IN_REQUIRED",
                "next_action": "LOGIN", "url": "https://elevenlabs.io/app/sign-in",
                "rendered_text_sha256": "a" * 64,
            }
            with (
                patch.object(provider_cli, "observe", return_value=signed_out),
                patch.object(provider_cli, "read_json", return_value=[{
                    "type": "page", "url": signed_out["url"],
                    "title": "Sign In | ElevenLabs", "id": "tab-1",
                }]),
                patch.object(provider_cli, "submit_login") as submit,
            ):
                receipt = provider_cli.resume(args)
            submit.assert_not_called()
            self.assertFalse(receipt["submitted"])
            self.assertEqual(receipt["state"], "SIGN_IN_REQUIRED")


if __name__ == "__main__":
    unittest.main()
