#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "tiktok_message_transport", SCRIPTS / "tiktok_message_transport.py"
)
transport = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(transport)


def _run_js_fixture(expression, fixture, mode):
    runner = r'''const vm = require("node:vm");
const fixture = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
const el = (text = "", attrs = {}) => ({
  innerText: text, textContent: text, className: attrs.class || "", isConnected: true,
  getAttribute: name => Object.hasOwn(attrs, name) ? attrs[name] : null,
  contains(target) { return target === this; }, closest() { return null; },
  querySelectorAll() { return this.statuses || []; }, querySelector() { return null; },
});
const editor = el(fixture.editorText ?? "本文");
const bubbles = (fixture.bubbles || []).map(b => {
  const n = el(b.text || "", b.attrs || {});
  if (b.parentAttrs) n.parentElement = el("", b.parentAttrs);
  n.statuses = (b.statuses || []).map(s => el(s.text || "", s.attrs || {}));
  n.children = (b.childrenAttrs || []).map(attrs => el("", attrs));
  n.querySelectorAll = selector => selector === "*" ? n.children : n.statuses.filter(item =>
    (selector.includes('[data-status]') && item.getAttribute("data-status") !== null)
    || (selector.includes('[data-message-status]') && item.getAttribute("data-message-status") !== null)
    || (selector.includes('[data-e2e*="status"]') && (item.getAttribute("data-e2e") || "").toLowerCase().includes("status"))
    || (selector.includes('[class*="Status"]') && item.className.includes("Status"))
    || (selector.includes('[aria-live]') && item.getAttribute("aria-live") !== null));
  return n;
});
if (fixture.messageBubbles) bubbles.push(...fixture.messageBubbles.map(text => el(text)));
const unresolved = fixture.unresolvedMessage ? [el("", {"data-e2e": "dm-message-row"})] : [];
const list = el(fixture.listText || "", {
  "aria-busy": fixture.listBusy ?? "false",
  "data-loaded": fixture.listLoaded,
  "data-hydrated": fixture.listHydrated,
});
list.querySelectorAll = selector => selector.includes('[data-e2e*="message"],')
  ? [...bubbles, ...unresolved] : selector.toLowerCase().includes("message") ? bubbles : [];
const header = el(fixture.headerText || "@candidate");
const doc = {
  URL: fixture.documentUrl || "https://www.tiktok.com/messages?u=candidate",
  readyState: fixture.readyState || "complete", activeElement: editor, body: el(fixture.bodyText || "本文"),
  querySelector: selector => selector.includes("contenteditable") ? editor
    : selector.includes("dm-new-message-list") ? list : null,
  querySelectorAll: selector => /chat-header|ChatHeader|ConversationHeader/.test(selector) ? [header] : [],
};
const frame = {src: fixture.frameSrc || "https://www.tiktok.com/messages?u=candidate",
  contentDocument: doc, contentWindow: {location: {href: doc.URL}, document: doc}, isConnected: true};
const win = {document: doc, location: new URL(doc.URL), listeners: {},
  addEventListener(type, callback, capture) { (this.listeners[type] ||= []).push({callback, capture}); }};
win.top = fixture.topIsSelf === false ? {location: new URL(fixture.topUrl)} : win;
let value;
if (fixture.mode === "guard") {
  const install = vm.runInNewContext(fixture.expression, {window: win, document: doc, location: win.location, URL});
  const event = {type: "keydown", key: "Enter", target: editor, defaultPrevented: false, stopped: false,
    preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; },
    stopImmediatePropagation() { this.stopped = true; }};
  for (const x of win.listeners.keydown || []) x.callback(event);
  let keyupPrevented = false;
  if (fixture.clearComposerBeforeKeyup) {
    editor.innerText = ""; doc.activeElement = null;
    const keyup = {...event, type: "keyup", defaultPrevented: false, stopped: false};
    for (const x of win.listeners.keyup || []) x.callback(keyup);
    keyupPrevented = keyup.defaultPrevented;
  }
  const token = JSON.parse(fixture.expression.match(/const token = ("[^"]+")/)[1]);
  value = {guard_installed: install.guard_installed, ready: install.ready,
    default_prevented: event.defaultPrevented, stopped: event.stopped, keyup_prevented: keyupPrevented,
    guard_status: win[token]?.status || null};
} else {
  value = vm.runInNewContext(fixture.expression, {
    document: {querySelectorAll: () => fixture.hasFrame === false ? [] : [frame]},
    location: {href: fixture.topUrl || "https://www.tiktok.com/business-suite/messages?u=candidate"}, URL,
  });
}
process.stdout.write(JSON.stringify(value));
'''
    completed = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps({**fixture, "expression": expression, "mode": mode}),
        text=True, capture_output=True, check=True,
    )
    return json.loads(completed.stdout)


def evaluate_js_expression(expression, fixture):
    return _run_js_fixture(expression, fixture, "readback")


def dispatch_js_guard(expression, fixture):
    return _run_js_fixture(expression, fixture, "guard")


class FakeCDP:
    def __init__(self, *, identity="expected", exact_before=False, before=None, after=None, route=True,
                 confirmed_empty=False, stable_empty=False, guarded_enter=None,
                 before_readback_fixture=None, after_readback_fixture=None,
                 stable_readback_fixture=None):
        self.identity = identity
        self.exact_before = exact_before
        self.before = before
        self.after = after or {
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "official_document": True,
            "context_ready": True,
            "message_list_hydrated": True,
            "message_node_resolution_complete": True,
            "recipient_bound": True,
            "editor_empty": True,
            "exact_message": True,
            "message_status_safe": True,
        }
        self.route = route
        self.confirmed_empty = confirmed_empty
        self.stable_empty = stable_empty
        self.guarded_enter = guarded_enter or {"key": "Enter", "guard_status": "allowed"}
        self.before_readback_fixture = before_readback_fixture
        self.after_readback_fixture = after_readback_fixture
        self.stable_readback_fixture = stable_readback_fixture
        self.guard_expression = None
        self.guard_status_expression = None
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
        if any(marker in expression for marker in (
            "TIKTOK_COMPOSER_BEFORE", "TIKTOK_PRE_INSERT"
        )):
            if self.before_readback_fixture is not None:
                return evaluate_js_expression(expression, self.before_readback_fixture)
            return self.before or {
                "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
                "official_document": True,
                "context_ready": True,
                "message_list_hydrated": True,
                "message_node_resolution_complete": True,
                "recipient_bound": True,
                "editor": True,
                "editor_empty": True,
                "editor_text": "",
                "exact_message": self.exact_before,
                "matching_bubble": self.exact_before,
                "message_status_safe": self.exact_before,
                "conversation_loaded": self.confirmed_empty,
                "message_count": 0 if self.confirmed_empty else None,
                "snapshot_key": "empty-snapshot" if self.confirmed_empty else "ready-snapshot",
            }
        if "TIKTOK_EMPTY_STABLE" in expression:
            if self.stable_readback_fixture is not None:
                return evaluate_js_expression(expression, self.stable_readback_fixture)
            return {
                "official_document": self.stable_empty,
                "context_ready": self.stable_empty,
                "message_list_hydrated": self.stable_empty,
                "message_node_resolution_complete": self.stable_empty,
                "recipient_bound": self.stable_empty,
                "editor_empty": self.stable_empty,
                "matching_bubble": False,
                "exact_message": False,
                "message_status_safe": False,
                "conversation_loaded": self.stable_empty,
                "message_count": 0 if self.stable_empty else None,
                "snapshot_key": "empty-snapshot" if self.stable_empty else None,
            }
        if "TIKTOK_FOCUS" in expression:
            return True
        if "TIKTOK_FILLED" in expression:
            return {
                "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
                "official_document": True,
                "context_ready": True,
                "recipient_bound": True,
                "editor": True,
                "editor_empty": False,
                "editor_text": transport._text(self.inserted_text),
                "message_list_hydrated": True,
                "message_node_resolution_complete": True,
            }
        if "TIKTOK_AFTER" in expression:
            if self.after_readback_fixture is not None:
                return evaluate_js_expression(expression, self.after_readback_fixture)
            return self.after
        raise AssertionError(expression)

    def insert(self, target, value):
        self.calls.append(("insert", target, value))
        self.inserted_text = value

    def key(self, target, value):
        self.calls.append(("key", target, value))

    def guarded_key(self, target, guard_expression, guard_status_expression, value="Enter"):
        self.calls.append(("guarded_key", target, value))
        self.guard_expression = guard_expression
        self.guard_status_expression = guard_status_expression
        return self.guarded_enter


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

    def test_sends_once_and_requires_exact_official_readback(self):
        fake = FakeCDP()
        result = self.send(self.payload(), fake)
        self.assertEqual(result["status"], "sent_exact_official_readback")
        self.assertEqual(result["effect"], 1)
        self.assertTrue(result["exact_readback"])
        self.assertEqual(sum(call[0] == "insert" for call in fake.calls), 1)
        self.assertEqual(sum(call[0] == "guarded_key" for call in fake.calls), 1)

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

    def test_unknown_is_released_only_after_official_empty_conversation_readback(self):
        payload = self.payload()
        first = FakeCDP(after={
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "recipient_bound": True,
            "editor_empty": True,
            "exact_message": False,
        })
        self.assertEqual(self.send(payload, first)["status"], "send_unknown_reconcile_required")

        reconciled_cdp = FakeCDP(confirmed_empty=True, stable_empty=True, route=False)
        reconciled = self.send(payload, reconciled_cdp, send=False)
        self.assertEqual(reconciled["status"], "not_sent_exact_official_readback")
        self.assertTrue(reconciled["retry_safe"])
        self.assertFalse(reconciled["exact_readback"])
        self.assertFalse(any(
            call[0] == "navigate" and call[2].endswith("/@candidate")
            for call in reconciled_cdp.calls
        ))

        retry = self.send(payload, FakeCDP(), send=True)
        self.assertEqual(retry["status"], "sent_exact_official_readback")

    def test_send_ack_exception_returns_unknown_and_next_run_cannot_resend(self):
        class AckLost(FakeCDP):
            def guarded_key(self, target, guard_expression, guard_status_expression, value="Enter"):
                super().guarded_key(target, guard_expression, guard_status_expression, value)
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
        self.assertEqual(sum(call[0] == "guarded_key" for call in fake.calls), 1)

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

    def test_readback_requires_resolved_bubble_and_safe_delivery_status(self):
        expression = transport._readback_expression("@candidate", "本文", "TIKTOK_TEST")
        unresolved = evaluate_js_expression(expression, {
            "bodyText": "本文", "listText": "本文", "bubbles": [],
            "unresolvedMessage": True,
        })
        self.assertFalse(unresolved["message_node_resolution_complete"])
        self.assertFalse(unresolved["context_ready"])
        self.assertFalse(unresolved["exact_message"])

        for status in ("failed", "error", "pending", "sending", "queued", "canceled", "undelivered"):
            with self.subTest(status=status):
                result = evaluate_js_expression(expression, {
                    "bodyText": "本文", "listText": "本文",
                    "bubbles": [{"text": "本文", "attrs": {"data-direction": "outgoing"},
                                 "statuses": [{"text": status, "attrs": {"data-status": status}}]}],
                })
                self.assertFalse(result["exact_message"])

        body_expression = transport._readback_expression("@candidate", "pending", "TIKTOK_TEST")
        body_word = evaluate_js_expression(body_expression, {
            "bodyText": "pending", "listText": "pending",
            "bubbles": [{"text": "pending", "attrs": {"data-direction": "outgoing"}}],
        })
        self.assertTrue(body_word["exact_message"])

    def test_identical_incoming_or_directionless_bubble_is_not_proof_of_our_sent_message(self):
        expression = transport._readback_expression("@candidate", "本文", "TIKTOK_TEST")
        result = evaluate_js_expression(expression, {
            "bubbles": [{"text": "本文"}],
        })
        self.assertTrue(result["matching_bubble"])
        self.assertFalse(result["exact_message"])

    def test_multiline_message_fill_uses_the_same_normalization_as_dom_readback(self):
        payload = self.payload()
        payload["message"] = "一行目\n  二行目"
        result = self.send(payload, FakeCDP())
        self.assertEqual(result["status"], "sent_exact_official_readback")

    def test_unready_official_context_cannot_deduplicate_exact_message(self):
        fake = FakeCDP(before={
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "official_document": False,
            "context_ready": False,
            "recipient_bound": True,
            "editor": True,
            "editor_empty": True,
            "exact_message": True,
            "message_status_safe": True,
        })
        result = self.send(self.payload(), fake)
        self.assertNotEqual(result["status"], "deduplicated_exact_official_readback")
        self.assertFalse(result["exact_readback"])

    def test_explicit_delivery_error_or_pending_state_cannot_return_sent(self):
        for status in ("failed", "error", "pending", "sending", "queued", "canceled", "undelivered"):
            with self.subTest(status=status):
                (self.project_root / "delivery/tiktok-message-effects.jsonl").unlink(missing_ok=True)
                fake = FakeCDP(after={
                    "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
                    "official_document": True,
                    "context_ready": True,
                    "recipient_bound": True,
                    "editor_empty": True,
                    "exact_message": True,
                    "message_status_safe": False,
                    "message_status": status,
                })
                result = self.send(self.payload(), fake)
                self.assertEqual(result["status"], "send_unknown_reconcile_required")
                self.assertEqual(result["effect"], 1)
                self.assertFalse(result["retry_safe"])
                self.assertFalse(result["exact_readback"])

    def test_unknown_is_released_only_after_stable_hydrated_empty_readback(self):
        payload = self.payload()
        first = FakeCDP(after={
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "recipient_bound": True,
            "editor_empty": False,
            "exact_message": False,
        })
        self.assertEqual(self.send(payload, first)["status"], "send_unknown_reconcile_required")

        shell = FakeCDP(before={
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "official_document": True,
            "context_ready": False,
            "message_list_hydrated": False,
            "recipient_bound": True,
            "editor": True,
            "editor_empty": True,
            "exact_message": False,
            "conversation_loaded": True,
            "message_count": 0,
            "snapshot_key": "empty-shell",
        })
        result = self.send(payload, shell, send=False)
        self.assertNotEqual(result["status"], "not_sent_exact_official_readback")
        self.assertFalse(result["retry_safe"])
        unstable = self.send(payload, FakeCDP(confirmed_empty=True, stable_empty=False), send=False)
        self.assertNotEqual(unstable["status"], "not_sent_exact_official_readback")
        self.assertFalse(unstable["retry_safe"])

    def test_enter_uses_native_guarded_dispatch_and_does_not_call_unconditional_key(self):
        fake = FakeCDP(guarded_enter={"guard_status": "blocked", "reason": "recipient_changed"})
        result = self.send(self.payload(), fake)
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        self.assertEqual(sum(call[0] == "guarded_key" for call in fake.calls), 1)
        self.assertFalse(any(call[0] == "key" for call in fake.calls))
        self.assertFalse(result["retry_safe"])

    def test_native_guard_allows_only_the_unchanged_document_recipient_and_composer(self):
        fake = FakeCDP()
        self.send(self.payload(), fake)
        self.assertIsNotNone(fake.guard_expression)
        for fixture in (
            {
                "documentUrl": "https://www.tiktok.com/@candidate",
                "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
                "headerText": "@candidate",
                "topIsSelf": False,
            },
            {
                "documentUrl": "https://www.tiktok.com/messages?u=candidate",
                "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
                "headerText": "@someone-else",
                "topIsSelf": False,
            },
            {
                "documentUrl": "https://www.tiktok.com/messages?u=candidate",
                "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
                "headerText": "@candidate",
                "editorText": "本文",
                "messageBubbles": ["本文"],
                "topIsSelf": False,
            },
        ):
            with self.subTest(fixture=fixture):
                result = dispatch_js_guard(fake.guard_expression, fixture)
                self.assertTrue(result["guard_installed"])
                self.assertFalse(result["ready"])
                self.assertTrue(result["default_prevented"])
                self.assertTrue(result["stopped"])
                self.assertEqual(result["guard_status"], "blocked")

        allowed = dispatch_js_guard(fake.guard_expression, {
            "documentUrl": "https://www.tiktok.com/messages?u=candidate",
            "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "headerText": "@candidate",
            "editorText": "本文",
            "clearComposerBeforeKeyup": True,
            "topIsSelf": False,
        })
        self.assertTrue(allowed["ready"])
        self.assertFalse(allowed["default_prevented"])
        self.assertTrue(allowed["keyup_prevented"])
        self.assertEqual(allowed["guard_status"], "allowed")

    def test_cdp_guarded_key_keeps_page_guard_and_native_enter_in_one_session(self):
        calls = []
        class FakeSocket:
            def close(self):
                calls.append((self, "close", None))
        socket = FakeSocket()

        def rpc(ws, _call_id, method, params=None):
            calls.append((ws, method, params))
            if method == "Page.addScriptToEvaluateOnNewDocument":
                return {"identifier": "guard-1"}
            if method == "Runtime.evaluate":
                value = ({"guard_installed": True, "ready": True}
                         if params["expression"] == "install-guard"
                         else {"guard_status": "allowed"})
                return {"result": {"value": value}}
            return {}

        with patch.object(transport.cdp, "_page", return_value=socket), \
                patch.object(transport.cdp, "_rpc", side_effect=rpc):
            result = transport.cdp.guarded_key("target", "install-guard", "read-guard")

        self.assertEqual(result, {"key": "Enter", "guard_status": "allowed", "key_dispatched": True})
        methods = [method for _, method, _ in calls if method != "close"]
        self.assertEqual(methods, [
            "Page.enable", "Page.addScriptToEvaluateOnNewDocument", "Runtime.evaluate",
            "Input.dispatchKeyEvent", "Input.dispatchKeyEvent", "Runtime.evaluate",
            "Page.removeScriptToEvaluateOnNewDocument",
        ])
        self.assertTrue(all(ws is socket for ws, _, _ in calls))

    def test_cdp_guarded_key_never_dispatches_when_current_guard_is_missing(self):
        calls = []
        class FakeSocket:
            def close(self):
                calls.append((self, "close", None))
        socket = FakeSocket()

        def rpc(ws, _call_id, method, params=None):
            calls.append((ws, method, params))
            if method == "Page.addScriptToEvaluateOnNewDocument":
                return {"identifier": "guard-1"}
            if method == "Runtime.evaluate":
                return {"result": {"value": {"guard_installed": False, "ready": False}}}
            return {}

        with patch.object(transport.cdp, "_page", return_value=socket), \
                patch.object(transport.cdp, "_rpc", side_effect=rpc):
            result = transport.cdp.guarded_key("target", "install-guard", "read-guard")

        self.assertEqual(result["__error__"], "send_guard_unavailable")
        self.assertFalse(any(method == "Input.dispatchKeyEvent" for _, method, _ in calls))
        self.assertIn("Page.removeScriptToEvaluateOnNewDocument", [method for _, method, _ in calls])

    def test_ancestor_failed_status_blocks_exact_and_keeps_send_fence(self):
        fixture = {
            "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "documentUrl": "https://www.tiktok.com/messages?u=candidate",
            "headerText": "@candidate", "editorText": "", "listText": "本文",
            "bubbles": [{"text": "本文", "parentAttrs": {
                "data-direction": "outgoing", "data-status": "failed",
            }}],
        }
        expression = transport._readback_expression("@candidate", "本文", "TIKTOK_TEST", "@anicca.jp")
        readback = evaluate_js_expression(expression, fixture)
        self.assertFalse(readback["exact_message"])
        self.assertTrue(readback["matching_bubble"])

        result = self.send(self.payload(), FakeCDP(after_readback_fixture=fixture))
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        self.assertFalse(result["retry_safe"])
        rows = [json.loads(line) for line in
                (self.project_root / "delivery/tiktok-message-effects.jsonl").read_text().splitlines()]
        self.assertEqual([row["state"] for row in rows], ["attempting", "unknown"])

    def test_child_data_message_status_failure_blocks_exact_and_keeps_send_fence(self):
        fixture = {
            "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "documentUrl": "https://www.tiktok.com/messages?u=candidate",
            "headerText": "@candidate", "editorText": "", "listText": "本文",
            "bubbles": [{"text": "本文", "attrs": {"data-direction": "outgoing"},
                         "statuses": [{"text": "送信失敗", "attrs": {"data-message-status": "failed"}}]}],
        }
        expression = transport._readback_expression("@candidate", "本文", "TIKTOK_TEST", "@anicca.jp")
        readback = evaluate_js_expression(expression, fixture)
        self.assertFalse(readback["exact_message"])
        self.assertIn("failed", readback["message_status"])

        result = self.send(self.payload(), FakeCDP(after_readback_fixture=fixture))
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        self.assertFalse(result["retry_safe"])
        rows = [json.loads(line) for line in
                (self.project_root / "delivery/tiktok-message-effects.jsonl").read_text().splitlines()]
        self.assertEqual([row["state"] for row in rows], ["attempting", "unknown"])

    def test_aria_busy_true_overrides_stale_loaded_marker_and_keeps_unknown_fenced(self):
        fixture = {
            "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "documentUrl": "https://www.tiktok.com/messages?u=candidate",
            "headerText": "@candidate", "editorText": "", "listText": "",
            "listBusy": "true", "listLoaded": "true", "bubbles": [],
        }
        expression = transport._readback_expression("@candidate", "本文", "TIKTOK_TEST", "@anicca.jp")
        self.assertFalse(evaluate_js_expression(expression, fixture)["message_list_hydrated"])

        payload = self.payload()
        first = FakeCDP(after={
            "url": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "recipient_bound": True, "editor_empty": False, "exact_message": False,
        })
        self.assertEqual(self.send(payload, first)["status"], "send_unknown_reconcile_required")
        reconciliation = FakeCDP(
            confirmed_empty=True, stable_empty=True,
            before_readback_fixture=fixture, stable_readback_fixture=fixture,
        )
        result = self.send(payload, reconciliation, send=False)
        self.assertNotEqual(result["status"], "not_sent_exact_official_readback")
        self.assertFalse(result["retry_safe"])

    def test_partial_bubble_text_is_unknown_not_exact_or_retry_safe(self):
        fixture = {
            "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "documentUrl": "https://www.tiktok.com/messages?u=candidate",
            "headerText": "@candidate", "editorText": "", "listText": "前置き\n本文",
            "bubbles": [{"text": "前置き\n本文", "attrs": {"data-direction": "outgoing"}}],
        }
        expression = transport._readback_expression("@candidate", "本文", "TIKTOK_TEST", "@anicca.jp")
        readback = evaluate_js_expression(expression, fixture)
        self.assertTrue(readback["matching_bubble"])
        self.assertFalse(readback["exact_message"])

        result = self.send(self.payload(), FakeCDP(after_readback_fixture=fixture))
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        self.assertFalse(result["retry_safe"])
        rows = [json.loads(line) for line in
                (self.project_root / "delivery/tiktok-message-effects.jsonl").read_text().splitlines()]
        self.assertEqual([row["state"] for row in rows], ["attempting", "unknown"])

    def test_guard_cleanup_failure_preserves_dispatch_result_and_sender_fence(self):
        calls = []
        class FakeSocket:
            def close(self):
                calls.append((self, "close", None))
        socket = FakeSocket()

        def rpc(ws, _call_id, method, params=None):
            calls.append((ws, method, params))
            if method == "Page.addScriptToEvaluateOnNewDocument":
                return {"identifier": "guard-1"}
            if method == "Runtime.evaluate":
                value = ({"guard_installed": True, "ready": True}
                         if params["expression"] == "install-guard"
                         else {"guard_status": "allowed"})
                return {"result": {"value": value}}
            if method == "Page.removeScriptToEvaluateOnNewDocument":
                raise RuntimeError("cleanup failed")
            return {}

        with patch.object(transport.cdp, "_page", return_value=socket), \
                patch.object(transport.cdp, "_rpc", side_effect=rpc):
            guarded = transport.cdp.guarded_key("target", "install-guard", "read-guard")

        self.assertEqual(guarded["__error__"], "send_guard_cleanup_failed")
        self.assertEqual(guarded["guard_status"], "allowed")
        self.assertTrue(guarded["key_dispatched"])
        self.assertEqual(guarded["cleanup_error_type"], "RuntimeError")

        fake = FakeCDP(guarded_enter=guarded)
        result = self.send(self.payload(), fake)
        self.assertEqual(result["status"], "send_unknown_reconcile_required")
        self.assertFalse(result["retry_safe"])
        rows = [json.loads(line) for line in
                (self.project_root / "delivery/tiktok-message-effects.jsonl").read_text().splitlines()]
        self.assertEqual([row["state"] for row in rows], ["attempting", "unknown"])

    def test_incoming_or_conflicting_sender_marker_cannot_prove_outgoing_bubble(self):
        payload = self.payload()
        incoming_child = {
            "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "documentUrl": "https://www.tiktok.com/messages?u=candidate",
            "headerText": "@candidate", "editorText": "", "listText": "本文",
            "bubbles": [{"text": "本文", "attrs": {"data-direction": "incoming"},
                         "parentAttrs": {"data-direction": "outgoing", "data-sender-handle": "@anicca.jp"}}],
        }
        expression = transport._readback_expression("@candidate", "本文", "TIKTOK_TEST", "@anicca.jp")
        incoming = self.send(payload, FakeCDP(before_readback_fixture=incoming_child), send=False)
        self.assertNotEqual(incoming["status"], "deduplicated_exact_official_readback")
        self.assertFalse(incoming["retry_safe"])
        incoming_readback = evaluate_js_expression(expression, incoming_child)
        self.assertFalse(incoming_readback["exact_message"])
        self.assertFalse(incoming_readback["message_sender_proven"])

        conflicting_sender = {
            **incoming_child,
            "bubbles": [{"text": "本文", "attrs": {
                "data-direction": "outgoing", "data-sender-handle": "@someone.else",
            }, "parentAttrs": {
                "data-direction": "outgoing", "data-sender-handle": "@anicca.jp",
            }}],
        }
        conflict_readback = evaluate_js_expression(expression, conflicting_sender)
        self.assertFalse(conflict_readback["exact_message"])
        self.assertFalse(conflict_readback["message_sender_proven"])
        conflict = self.send(payload, FakeCDP(before_readback_fixture=conflicting_sender), send=False)
        self.assertNotEqual(conflict["status"], "deduplicated_exact_official_readback")
        self.assertFalse(conflict["retry_safe"])

        not_own = {
            **incoming_child,
            "bubbles": [{"text": "本文", "attrs": {"data-is-own": "false"},
                         "parentAttrs": {"data-direction": "outgoing"}}],
        }
        not_own_readback = evaluate_js_expression(expression, not_own)
        self.assertFalse(not_own_readback["message_sender_proven"])
        not_own_result = self.send(payload, FakeCDP(before_readback_fixture=not_own), send=False)
        self.assertNotEqual(not_own_result["status"], "deduplicated_exact_official_readback")
        self.assertFalse(not_own_result["retry_safe"])

        outgoing = {
            **incoming_child,
            "bubbles": [{"text": "本文", "attrs": {
                "data-direction": "outgoing", "data-sender-handle": "@anicca.jp",
            }}],
        }
        outgoing_readback = evaluate_js_expression(expression, outgoing)
        self.assertTrue(outgoing_readback["exact_message"])
        self.assertTrue(outgoing_readback["message_sender_proven"])
        accepted = self.send(payload, FakeCDP(before_readback_fixture=outgoing), send=False)
        self.assertEqual(accepted["status"], "deduplicated_exact_official_readback")

        rows = [json.loads(line) for line in
                (self.project_root / "delivery/tiktok-message-effects.jsonl").read_text().splitlines()]
        self.assertEqual([row["state"] for row in rows], ["unknown", "sent"])

    def test_descendant_direction_and_ownership_conflicts_invalidate_outgoing_ancestor(self):
        payload = self.payload()
        expression = transport._readback_expression("@candidate", "本文", "TIKTOK_TEST", "@anicca.jp")
        base = {
            "topUrl": "https://www.tiktok.com/business-suite/messages?u=candidate",
            "documentUrl": "https://www.tiktok.com/messages?u=candidate",
            "headerText": "@candidate", "editorText": "", "listText": "本文",
            "bubbles": [{"text": "本文", "parentAttrs": {
                "data-direction": "outgoing", "data-sender-handle": "@anicca.jp",
            }}],
        }
        conflicts = (
            {"data-direction": "incoming"},
            {"data-is-own": "false"},
            {"data-sender-handle": "@candidate"},
            {"class": "incoming"},
        )
        for marker in conflicts:
            with self.subTest(marker=marker):
                fixture = {
                    **base,
                    "bubbles": [{**base["bubbles"][0], "childrenAttrs": [marker]}],
                }
                readback = evaluate_js_expression(expression, fixture)
                self.assertFalse(readback["message_sender_proven"])
                self.assertFalse(readback["exact_message"])
                result = self.send(payload, FakeCDP(before_readback_fixture=fixture), send=False)
                self.assertNotEqual(result["status"], "deduplicated_exact_official_readback")
                self.assertFalse(result["retry_safe"])


if __name__ == "__main__":
    unittest.main()
