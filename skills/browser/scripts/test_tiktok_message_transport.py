#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "tiktok_message_transport", SCRIPTS / "tiktok_message_transport.py"
)
transport = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(transport)


class FakeCDP:
    def __init__(self, *, identity="expected", exact_before=False, after=None, route=True,
                 before_sequence=None, after_sequence=None):
        self.identity = identity
        self.exact_before = exact_before
        self.after = after or {
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "recipient_bound": True,
            "frame_present": True,
            "frame_origin": "https://www.tiktok.com",
            "frame_path": "/messages",
            "frame_ready_state": "complete",
            "conversation_loaded": True,
            "editor_empty": True,
            "exact_message": True,
        }
        self.route = route
        self.before_sequence = list(before_sequence or [])
        self.after_sequence = list(after_sequence or [])
        self.before_reads = 0
        self.after_reads = 0
        self.calls = []

    def new_target(self, url, owner):
        self.calls.append(("new", url, owner))
        return "target-1"

    def close_target(self, target, owner):
        self.calls.append(("close", target, owner))

    def navigate(self, target, url):
        self.calls.append(("navigate", target, url))

    def evaluate(self, target, expression):
        self.calls.append(("evaluate", target, expression))
        if "TIKTOK_IDENTITY" in expression:
            handle = "@anicca.jp" if self.identity == "expected" else "@someone.else"
            return {
                "url": "https://www.tiktok.com/",
                "profile_navigation_hrefs": [f"https://www.tiktok.com/{handle}"],
                "login_control_count": 0,
            }
        if "TIKTOK_PROFILE_ROUTE" in expression:
            return {
                "url": "https://www.tiktok.com/@candidate",
                "message_route": (
                    "https://www.tiktok.com/business-suite/messages?u=candidate"
                    if self.route else None
                ),
            }
        if "TIKTOK_COMPOSER_BEFORE" in expression:
            self.before_reads += 1
            if self.before_sequence:
                return self.before_sequence.pop(0)
            return {
                "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
                "recipient_bound": True,
                "recipient_handles": ["@candidate"],
                "frame_present": True,
                "frame_origin": "https://www.tiktok.com",
                "frame_path": "/messages",
                "frame_ready_state": "complete",
                "editor": True,
                "editor_empty": True,
                "exact_message": self.exact_before,
                "conversation_loaded": True,
                "explicit_empty_state": False,
            }
        if "TIKTOK_FOCUS" in expression:
            return True
        if "TIKTOK_FILLED" in expression:
            return {"text": "本文"}
        if "TIKTOK_AFTER" in expression:
            self.after_reads += 1
            if self.after_sequence:
                return self.after_sequence.pop(0)
            return self.after
        raise AssertionError(expression)

    def insert(self, target, value):
        self.calls.append(("insert", target, value))

    def key(self, target, value):
        self.calls.append(("key", target, value))


class TikTokMessageTransportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project_root = pathlib.Path(self.temp.name)
        (self.project_root / "delivery").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def payload(self):
        return {
            "effect_key": "18180857:@candidate:hello-v1",
            "owner": "test-owner",
            "candidate_handle": "@candidate",
            "profile_url": "https://www.tiktok.com/@candidate",
            "expected_sender_handle": "@anicca.jp",
            "message": "本文",
        }

    def send(self, payload, fake, *, send=True, dedupe_runner=None):
        return transport.send_one(payload, cdp_client=fake, send=send,
                                  wait=lambda _: None, project_root=self.project_root,
                                  dedupe_runner=dedupe_runner)

    def seed_sheet_dedupe_policy(self):
        (self.project_root / "delivery/tiktok-recipient-dedupe-policy.json").write_text(
            json.dumps({
                "schema_version": 1,
                "provider": "google_sheets",
                "spreadsheet_id": "sheet-id",
                "range": "'2026年8月'!A1:A1400",
                "account": "owner@example.com",
            }),
            encoding="utf-8",
        )

    def seed_recipient_effect(self, state):
        ledger = self.project_root / "delivery/tiktok-message-effects.jsonl"
        ledger.write_text(json.dumps({
            "schema_version": 1,
            "record_type": "tiktok_dm_effect_fence",
            "effect_key": "older-effect-key",
            "effect_binding_sha256": "older-binding",
            "candidate_handle": "@Candidate",
            "message_sha256": "older-message",
            "state": state,
        }) + "\n", encoding="utf-8")

    def test_rejects_profile_that_does_not_match_candidate(self):
        payload = self.payload()
        payload["profile_url"] = "https://www.tiktok.com/@different"
        with self.assertRaisesRegex(ValueError, "profile_candidate_mismatch"):
            self.send(payload, FakeCDP())

    def test_rejects_wrong_authenticated_sender(self):
        result = self.send(self.payload(), FakeCDP(identity="other"))
        self.assertEqual(result["status"], "sender_identity_mismatch")
        self.assertEqual(result["effect"], 0)

    def test_waits_for_delayed_authenticated_sender_navigation(self):
        class DelayedIdentity(FakeCDP):
            def __init__(self):
                super().__init__()
                self.identity_reads = 0

            def evaluate(self, target, expression):
                if "TIKTOK_IDENTITY" in expression:
                    self.identity_reads += 1
                    if self.identity_reads == 1:
                        self.calls.append(("evaluate", target, expression))
                        return {
                            "url": "https://www.tiktok.com/",
                            "profile_navigation_hrefs": [],
                            "login_control_count": 0,
                        }
                return super().evaluate(target, expression)

        fake = DelayedIdentity()
        result = self.send(self.payload(), fake, send=False)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["sender_identity"]["authenticated"])
        self.assertGreaterEqual(fake.identity_reads, 2)

    def test_deduplicates_exact_existing_message(self):
        fake = FakeCDP(exact_before=True)
        result = self.send(self.payload(), fake)
        self.assertEqual(result["status"], "deduplicated_exact_official_readback")
        self.assertTrue(result["exact_readback"])
        self.assertEqual(result["effect"], 0)
        self.assertFalse(any(call[0] == "insert" for call in fake.calls))

    def test_preflight_never_sends(self):
        fake = FakeCDP()
        result = self.send(self.payload(), fake, send=False)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["effect"], 0)
        self.assertFalse(any(call[0] == "insert" for call in fake.calls))

    def test_waits_for_delayed_business_messages_frame_before_preflight(self):
        loading = {
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "frame_present": False, "frame_origin": None, "frame_path": None,
            "frame_ready_state": "loading",
            "recipient_bound": False, "editor": False, "editor_empty": True,
            "exact_message": False, "conversation_loaded": False,
            "explicit_empty_state": False,
        }
        ready = {
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "frame_present": True, "frame_origin": "https://www.tiktok.com",
            "frame_path": "/messages", "frame_ready_state": "complete",
            "recipient_bound": True, "editor": True, "editor_empty": True,
            "exact_message": False, "conversation_loaded": True,
            "explicit_empty_state": True,
        }
        fake = FakeCDP(before_sequence=[loading, ready, ready])

        result = self.send(self.payload(), fake, send=False)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["effect"], 0)
        self.assertGreaterEqual(fake.before_reads, 3)
        self.assertFalse(any(call[0] == "insert" for call in fake.calls))

    def test_rejects_unofficial_messages_frame_before_preflight(self):
        base = {
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "frame_present": True, "frame_origin": "https://www.tiktok.com",
            "frame_path": "/messages", "frame_ready_state": "complete",
            "recipient_bound": True, "recipient_handles": ["@candidate"],
            "editor": True, "editor_empty": True, "exact_message": False,
            "conversation_loaded": True, "explicit_empty_state": False,
        }
        for field, value in (("frame_origin", "https://example.com"),
                             ("frame_path", "/not-messages")):
            with self.subTest(field=field):
                untrusted = {**base, field: value}
                fake = FakeCDP(before_sequence=[untrusted] * transport.READBACK_MAX_ATTEMPTS)

                result = self.send(self.payload(), fake, send=False)

                self.assertEqual(result["status"], "composer_hydration_timeout")
                self.assertEqual(result["effect"], 0)
                self.assertEqual(fake.before_reads, transport.READBACK_MAX_ATTEMPTS)
                self.assertFalse(any(call[0] == "insert" for call in fake.calls))

    def test_unsent_composer_draft_cannot_be_misread_as_existing_message(self):
        draft = {
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "frame_present": True, "frame_origin": "https://www.tiktok.com",
            "frame_path": "/messages", "frame_ready_state": "complete",
            "recipient_bound": True, "recipient_handles": ["@candidate"],
            "editor": True, "editor_empty": False, "exact_message": False,
            "conversation_loaded": True, "explicit_empty_state": False,
        }
        fake = FakeCDP(before_sequence=[draft] * transport.READBACK_MAX_ATTEMPTS)

        result = self.send(self.payload(), fake, send=True)

        self.assertEqual(result["status"], "composer_hydration_timeout")
        self.assertEqual(result["effect"], 0)
        self.assertFalse(any(call[0] in {"insert", "key"} for call in fake.calls))

    def test_sends_once_and_requires_exact_official_readback(self):
        fake = FakeCDP()
        result = self.send(self.payload(), fake)
        self.assertEqual(result["status"], "sent_exact_official_readback")
        self.assertEqual(result["effect"], 1)
        self.assertTrue(result["exact_readback"])
        self.assertEqual(sum(call[0] == "insert" for call in fake.calls), 1)
        self.assertEqual(sum(call[0] == "key" for call in fake.calls), 1)

    def test_waits_for_delayed_exact_post_send_readback(self):
        not_yet_visible = {
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "frame_present": True, "frame_origin": "https://www.tiktok.com",
            "frame_path": "/messages", "frame_ready_state": "complete",
            "recipient_bound": True, "conversation_loaded": False,
            "editor_empty": False, "exact_message": False,
        }
        visible = {
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "frame_present": True, "frame_origin": "https://www.tiktok.com",
            "frame_path": "/messages", "frame_ready_state": "complete",
            "recipient_bound": True, "conversation_loaded": True,
            "editor_empty": True, "exact_message": True,
        }
        fake = FakeCDP(after_sequence=[not_yet_visible, visible, visible])

        result = self.send(self.payload(), fake, send=True)

        self.assertEqual(result["status"], "sent_exact_official_readback")
        self.assertEqual(result["effect"], 1)
        self.assertGreaterEqual(fake.after_reads, 3)
        self.assertEqual(sum(call[0] == "insert" for call in fake.calls), 1)
        self.assertEqual(sum(call[0] == "key" for call in fake.calls), 1)

    def test_unknown_after_send_is_not_retried(self):
        fake = FakeCDP(after={
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "recipient_bound": True,
            "editor_empty": False,
            "exact_message": False,
        })
        result = self.send(self.payload(), fake)
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        self.assertEqual(result["effect"], 1)
        self.assertFalse(result["retry_safe"])
        self.assertEqual(sum(call[0] == "insert" for call in fake.calls), 1)

    def test_unknown_stays_fenced_when_message_list_is_empty_or_unhydrated(self):
        payload = self.payload()
        first = FakeCDP(after={
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "recipient_bound": True,
            "editor_empty": True,
            "exact_message": False,
        })
        self.assertEqual(self.send(payload, first)["status"], "send_unknown_reconcile_required")

        empty_shell = {
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "frame_present": True, "frame_origin": "https://www.tiktok.com",
            "frame_path": "/messages", "frame_ready_state": "complete",
            "recipient_bound": True, "recipient_handles": ["@candidate"],
            "editor": True, "editor_empty": True, "exact_message": False,
            "conversation_loaded": False, "explicit_empty_state": False,
        }
        reconcile = FakeCDP(before_sequence=[empty_shell] * transport.READBACK_MAX_ATTEMPTS,
                            route=False)
        result = self.send(payload, reconcile, send=False)
        self.assertEqual(result["status"], "composer_hydration_timeout")
        self.assertFalse(result["retry_safe"])
        self.assertFalse(any(call[0] in {"insert", "key"} for call in reconcile.calls))

        retry_cdp = FakeCDP()
        retry = self.send(payload, retry_cdp, send=True)
        self.assertEqual(retry["status"], "reconcile_required")
        self.assertFalse(retry["retry_safe"])
        self.assertFalse(any(call[0] in {"insert", "key"} for call in retry_cdp.calls))

    def test_send_ack_exception_returns_unknown_and_next_run_cannot_resend(self):
        class AckLost(FakeCDP):
            def key(self, target, value):
                super().key(target, value)
                raise TimeoutError("ack lost")

        payload = self.payload()
        first = AckLost()
        result = self.send(payload, first)
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        self.assertFalse(result["retry_safe"])
        second = FakeCDP()
        replay = self.send(payload, second)
        self.assertEqual(replay["status"], "reconcile_required")
        self.assertFalse(any(call[0] == "insert" for call in second.calls))

    def test_post_send_readback_exception_is_durable_unknown(self):
        class ReadbackLost(FakeCDP):
            def evaluate(self, target, expression):
                if "TIKTOK_AFTER" in expression:
                    raise TimeoutError("readback lost")
                return super().evaluate(target, expression)

        payload = self.payload()
        result = self.send(payload, ReadbackLost())
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        rows = [json.loads(line) for line in
                (self.project_root / "delivery/tiktok-message-effects.jsonl").read_text().splitlines()]
        self.assertEqual([row["state"] for row in rows], ["attempting", "unknown"])

    def test_same_effect_key_rejects_payload_drift(self):
        payload = self.payload()
        self.send(payload, FakeCDP())
        payload["message"] = "変更本文"
        with self.assertRaisesRegex(ValueError, "effect_key_payload_conflict"):
            self.send(payload, FakeCDP())

    def test_different_effect_key_cannot_resend_to_contacted_recipient(self):
        for state in ("sent", "attempting", "unknown"):
            with self.subTest(state=state):
                self.seed_recipient_effect(state)
                fake = FakeCDP()
                result = self.send(self.payload(), fake)
                self.assertEqual(result["status"], "recipient_already_contacted")
                self.assertEqual(result["effect"], 0)
                self.assertFalse(result["retry_safe"])
                self.assertEqual(result["prior_effect_key"], "older-effect-key")
                self.assertFalse(fake.calls)

    def test_live_sheet_results_only_array_blocks_recorded_recipient_before_browser(self):
        self.seed_sheet_dedupe_policy()
        calls = []

        def official_sheet(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps([["アカウント名"], ["@Candidate"]]), stderr=""
            )

        fake = FakeCDP()
        result = self.send(self.payload(), fake, dedupe_runner=official_sheet)

        self.assertEqual(result["status"], "recipient_already_recorded")
        self.assertEqual(result["effect"], 0)
        self.assertFalse(result["retry_safe"])
        self.assertEqual(fake.calls, [])
        self.assertEqual(calls[0][:3], ["gog", "sheets", "get"])

    def test_live_sheet_readback_failure_blocks_send_before_browser(self):
        self.seed_sheet_dedupe_policy()

        def failed_sheet(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="provider failed")

        fake = FakeCDP()
        result = self.send(self.payload(), fake, dedupe_runner=failed_sheet)

        self.assertEqual(result["status"], "recipient_dedupe_readback_failed")
        self.assertEqual(result["effect"], 0)
        self.assertTrue(result["retry_safe"])
        self.assertEqual(fake.calls, [])

    def test_live_sheet_object_allows_unrecorded_recipient(self):
        self.seed_sheet_dedupe_policy()

        def official_sheet(command, **kwargs):
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps({"values": [["@someone_else"]]}), stderr=""
            )

        result = self.send(self.payload(), FakeCDP(), dedupe_runner=official_sheet)

        self.assertEqual(result["status"], "sent_exact_official_readback")
        self.assertEqual(result["effect"], 1)

    def test_provider_proven_not_sent_recipient_remains_retryable(self):
        self.seed_recipient_effect("not_sent")
        fake = FakeCDP()
        result = self.send(self.payload(), fake)
        self.assertEqual(result["status"], "sent_exact_official_readback")
        self.assertEqual(result["effect"], 1)
        self.assertEqual(sum(call[0] == "key" for call in fake.calls), 1)

    def test_message_body_handle_cannot_substitute_for_recipient_header(self):
        fake = FakeCDP()
        original = fake.evaluate
        def evaluate(target, expression):
            value = original(target, expression)
            if "TIKTOK_COMPOSER_BEFORE" in expression:
                value["recipient_bound"] = False
                value["body_contains_candidate"] = True
            return value
        fake.evaluate = evaluate
        result = self.send(self.payload(), fake)
        self.assertEqual(result["status"], "composer_recipient_binding_failed")
        self.assertFalse(any(call[0] == "insert" for call in fake.calls))

    def test_recipient_binding_uses_exact_handle_tokens(self):
        fake = FakeCDP()
        self.send(self.payload(), fake, send=False)
        expression = next(call[2] for call in fake.calls
                          if call[0] == "evaluate" and "TIKTOK_COMPOSER_BEFORE" in call[2])
        self.assertIn("handles.includes", expression)
        self.assertNotIn("toLowerCase().includes", expression)

    def test_payload_cannot_choose_an_alternate_effect_ledger(self):
        payload = self.payload()
        payload["effect_ledger_path"] = str(self.project_root / "alternate.jsonl")
        self.send(payload, FakeCDP())
        self.assertTrue((self.project_root / "delivery/tiktok-message-effects.jsonl").is_file())
        self.assertFalse((self.project_root / "alternate.jsonl").exists())

    def test_close_failure_does_not_replace_machine_readable_unknown(self):
        class CloseLost(FakeCDP):
            def close_target(self, target, owner):
                super().close_target(target, owner)
                raise TimeoutError("close ack lost")

        result = self.send(self.payload(), CloseLost())
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        self.assertFalse(result["retry_safe"])
        self.assertEqual(result["target_close_status"], "failed")

    def test_terminal_ledger_failure_keeps_attempt_fence_and_returns_unknown(self):
        original = transport._append
        calls = 0
        def fail_terminal(path, result, state):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError("disk failure")
            return original(path, result, state)
        transport._append = fail_terminal
        try:
            result = self.send(self.payload(), FakeCDP())
        finally:
            transport._append = original
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        self.assertEqual(result["ledger_terminal_write"], "failed")
        rows = [json.loads(line) for line in
                (self.project_root / "delivery/tiktok-message-effects.jsonl").read_text().splitlines()]
        self.assertEqual([row["state"] for row in rows], ["attempting"])

    def test_owned_target_is_always_closed(self):
        fake = FakeCDP(route=False)
        result = self.send(self.payload(), fake)
        self.assertEqual(result["status"], "recipient_message_route_unavailable")
        self.assertEqual(fake.calls[-1], ("close", "target-1", "test-owner"))


if __name__ == "__main__":
    unittest.main()
