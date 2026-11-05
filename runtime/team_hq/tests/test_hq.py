import concurrent.futures
from contextlib import contextmanager
import importlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


try:
    hq = importlib.import_module("runtime.team_hq.main")
except ModuleNotFoundError:
    hq = None


AUTOLINK_BOUNDARIES = (
    ("escaped_query", "証拠 https://example.test/?a=1&b=2", "証拠 <https://example.test/?a=1&amp;b=2>"),
    ("markdown_japanese", "[PR](https://example.test/result)でmainへ保存。",
     "[PR](<https://example.test/result>)でmainへ保存。"),
    ("json_proof", 'STATE {"proof":["https://example.test/result","/fixture/artifact","https://example.test/evidence"]}',
     'STATE {"proof":["<https://example.test/result>","/fixture/artifact","<https://example.test/evidence>"]}'),
    ("balanced_parentheses", "[資料](https://example.test/a_(b))で完了。 https://example.test/result, 次へ。",
     "[資料](<https://example.test/a_(b)>)で完了。 <https://example.test/result>, 次へ。"),
)


class Slack:
    """Only the network boundary is replaced; queue and subprocesses are real."""

    def __init__(self):
        self.history = {"": {"ok": True, "messages": []}}
        self.threads = {}
        self.posts = []
        self.lose_post_response = False
        self.hide_posts = False
        self.autolink_urls = False
        self.error = False
        self.calls = []

    def call(self, method, **parameters):
        self.calls.append((method, dict(parameters)))
        if self.error:
            return {"ok": False, "error": "not_authed"}
        if method == "auth.test":
            return {"ok": True, "user_id": "U_BOT", "bot_id": "B_BOT"}
        cursor = parameters.get("cursor", "")
        if method == "conversations.history":
            page = dict(self.history[cursor])
            if not self.hide_posts:
                page["messages"] = page.get("messages", []) + [
                    p for p in self.posts if not p.get("thread_ts")
                ]
            return page
        if method == "conversations.replies":
            page = dict(self.threads.get((parameters["ts"], cursor), {
                "ok": True, "messages": [],
            }))
            if not self.hide_posts:
                page["messages"] = page.get("messages", []) + [
                    p for p in self.posts if p.get("thread_ts") == parameters["ts"]
                ]
            return page
        if method == "chat.postMessage":
            message = dict(parameters, ts=f"9000.{len(self.posts) + 1:06d}", user="U_BOT", bot_id="B_BOT")
            if self.autolink_urls:
                parts = re.split(r"(<[^>]*>)", message["text"])
                message["text"] = "".join(
                    part if index % 2 else re.sub(r"https?://[^\s<>|]+", r"<\g<0>>", part)
                    for index, part in enumerate(parts)
                )
            self.posts.append(message)
            if self.lose_post_response:
                raise TimeoutError("private provider details must not be printed")
            return {"ok": True, "ts": message["ts"], "channel": parameters["channel"]}
        raise AssertionError(method)


class SlackEntityTests(unittest.TestCase):
    def test_observed_url_entity_matches_original_only(self):
        original = "result https://example.test/?a=1&b=2"
        observed = "result <https://example.test/?a=1&amp;b=2>"
        self.assertEqual(hq.canonical_slack_text(observed, slack_observed=True), hq.canonical_slack_text(original))
        different = "result https://example.test/?a=1&amp;b=2"
        self.assertNotEqual(hq.canonical_slack_text(observed, slack_observed=True), hq.canonical_slack_text(different))


class HQTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(hq, "HQ runtime is not implemented")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "token").write_text("private-slack-token", encoding="utf-8")
        self.config = {
            "channel_id": "C_TEST", "token_file": str(self.root / "token"),
            "state_dir": str(self.root / "state"),
            "agents": [{"id": "codex", "mention": ["@codex", "<@U_CODEX>"],
                        "command": [sys.executable, "-c", "print('worked')"],
                        "cwd": str(self.root)}],
        }
        self.slack = Slack()
        self.runtime = hq.HQ(self.config, api=self.slack)

    def tasks(self):
        with self.runtime.connect() as database:
            return [dict(row) for row in database.execute("SELECT * FROM tasks ORDER BY created, id")]

    def message(self, ts="101.000001", text="@codex fix the real work", thread=None):
        message = {"ts": ts, "text": text}
        if thread:
            message["thread_ts"] = thread
        return message

    def enqueue(self):
        self.slack.history[""]["messages"] = [self.message()]
        self.runtime.receive()

    def test_slack_sqlite_full_preserves_cursor_and_replay_creates_one_task(self):
        self.slack.history[""]["messages"] = [self.message(text="@codex " + "🟦" * 40000)]
        connect = self.runtime.connect

        @contextmanager
        def full_database():
            with connect() as database:
                pages = database.execute("PRAGMA page_count").fetchone()[0]
                database.execute(f"PRAGMA max_page_count={pages}")
                yield database

        def scan():
            return self.runtime.receive_scan(
                "conversations.history", "scan:history", "0", 1, time.monotonic() + 10)

        with mock.patch.object(self.runtime, "connect", side_effect=full_database):
            with self.assertRaises(sqlite3.OperationalError):
                scan()
        self.assertEqual(self.tasks(), [])
        with connect() as database:
            self.assertIsNone(database.execute(
                "SELECT value FROM meta WHERE key='scan:history'").fetchone())
            self.assertEqual(database.execute("SELECT count(*) FROM messages").fetchone()[0], 0)
        self.assertTrue(scan()[2])
        self.assertTrue(scan()[2])
        self.assertEqual(len(self.tasks()), 1)
        with connect() as database:
            self.assertEqual(database.execute("SELECT count(*) FROM messages").fetchone()[0], 1)

    def oauth_fixture(self, entries=None):
        private = self.root / ".local/share/anicca"
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        private.chmod(0o700)
        credentials = private / "credentials.json"
        credentials.write_text(json.dumps({"credentials": entries if entries is not None else [
            {"service": "claude-remote-control", "token": "fixture-oauth-not-a-secret"}]}))
        credentials.chmod(0o600)
        cli = self.root / "claude"
        cli.write_text(f"#!{sys.executable}\nimport os,sys\nsys.stdin.read()\n"
                       "print('auth-attached' if os.environ.get('CLAUDE_CODE_OAUTH_TOKEN') == "
                       "'fixture-oauth-not-a-secret' else 'auth-missing')\n")
        cli.chmod(0o755)
        self.config["agents"][0].update(command=[str(cli)], credential_service="claude-remote-control")
        return credentials

    def test_opted_in_claude_reads_ssot_only_into_its_child_environment(self):
        self.oauth_fixture()
        self.enqueue()
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}):
            os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
            receipt = self.runtime.execute(self.runtime.claim())
            self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", os.environ)
        self.assertIn("auth-attached", receipt["output"])
        self.assertNotIn("fixture-oauth-not-a-secret", json.dumps(receipt))
        self.assertEqual(receipt["status"], "succeeded")

    def test_injected_oauth_is_redacted_before_artifact_state_and_slack(self):
        for index, mode in enumerate(("stdout", "artifact")):
            with self.subTest(mode=mode):
                self.oauth_fixture()
                cli = self.root / "claude"
                cli.write_text(f"#!{sys.executable}\nimport os,sys,json,pathlib\nsys.stdin.read()\n"
                               "token=os.environ.get('CLAUDE_CODE_OAUTH_TOKEN','fixture-oauth-not-a-secret')\n"
                               "output=token+'\\nSTATE '+json.dumps({'proof':[token]})\n"
                               "if len(sys.argv)>1: pathlib.Path(sys.argv[1]).write_text(output)\n"
                               "else: print(output)\n")
                if mode == "artifact":
                    self.config["agents"][0]["command"].append("{artifact}")
                self.slack.history[""]["messages"] = [self.message(ts=f"12{index}.000001")]
                self.runtime.receive()
                with mock.patch.dict(os.environ, {"HOME": str(self.root)}):
                    os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
                    self.runtime.work()
                directory = self.runtime.task_directory(self.tasks()[-1])
                receipt = json.loads((directory / "result.json").read_text())
                self.assertEqual(receipt["status"], "succeeded")
                self.assertTrue(receipt["agent_state"].get("proof"))
                for name in ("artifact.txt", "result.json"):
                    self.assertNotIn("fixture-oauth-not-a-secret", (directory / name).read_text())
                self.assertNotIn("fixture-oauth-not-a-secret", json.dumps(self.slack.posts))
                self.assertNotIn("fixture-oauth-not-a-secret", json.dumps(self.tasks()))

    def test_oauth_redaction_does_not_leave_a_tail_boundary_fragment(self):
        self.oauth_fixture()
        cli = self.root / "claude"
        cli.write_text(f"#!{sys.executable}\nimport os,sys\nsys.stdin.read()\n"
                       "token=os.environ.get('CLAUDE_CODE_OAUTH_TOKEN','fixture-oauth-not-a-secret')\n"
                       "print(token+'X'*(20000-2*len(token)+5)+token,end='')\n")
        self.enqueue()
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}):
            os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
            receipt = self.runtime.execute(self.runtime.claim())
        self.assertNotIn("fixture-oauth-not-a-secret"[5:], receipt["output"])
        self.assertLessEqual(len(receipt["output"]), 20000)

    def test_unencodable_explicit_oauth_returns_typed_failure(self):
        self.oauth_fixture()
        self.enqueue()
        with mock.patch.dict(os.environ, {"HOME": str(self.root),
                                        "CLAUDE_CODE_OAUTH_TOKEN": "fixture-" + chr(0xDCFF)}):
            receipt = self.runtime.execute(self.runtime.claim())
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["checkpoint"], "credential_unavailable_handoff_required")
        self.assertEqual(receipt["output"], "")

    def test_claude_preserves_explicit_auth_environment(self):
        self.oauth_fixture(entries=[])
        self.enqueue()
        with mock.patch.dict(os.environ, {"HOME": str(self.root),
                                        "CLAUDE_CODE_OAUTH_TOKEN": "fixture-oauth-not-a-secret"}):
            receipt = self.runtime.execute(self.runtime.claim())
        self.assertIn("auth-attached", receipt["output"])

    def test_invalid_ssot_never_starts_opted_in_claude(self):
        for case in ("missing", "wrong_mode", "duplicate", "unrelated", "nul", "symlink"):
            with self.subTest(case=case):
                credentials = self.oauth_fixture()
                if case == "missing":
                    credentials.unlink()
                elif case == "wrong_mode":
                    credentials.chmod(0o644)
                elif case == "duplicate":
                    credentials.write_text(json.dumps({"credentials": [
                        {"service": "claude-remote-control", "token": "one"},
                        {"service": "claude-remote-control", "token": "two"}]}))
                elif case == "unrelated":
                    credentials.write_text(json.dumps({"credentials": [
                        {"service": "claude-remote-control-extra", "token": "fixture-oauth-not-a-secret"}]}))
                elif case == "nul":
                    credentials.write_text(json.dumps({"credentials": [
                        {"service": "claude-remote-control", "token": "bad\x00token"}]}))
                elif case == "symlink":
                    original = credentials.with_suffix(".original")
                    credentials.rename(original)
                    credentials.symlink_to(original)
                task = {"id": "oauth-" + case, "owner_id": "codex", "body": "bounded auth check", "thread_ts": "oauth-test"}
                with mock.patch.dict(os.environ, {"HOME": str(self.root)}):
                    os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
                    receipt = self.runtime.execute(task)
                self.assertEqual(receipt["checkpoint"], "credential_unavailable_handoff_required")
                self.assertEqual(receipt["status"], "failed")
                self.assertEqual(receipt["output"], "")
                if credentials.is_symlink():
                    credentials.unlink()

    def test_credential_opt_in_is_restricted_to_the_named_claude_service(self):
        for command, service in (([sys.executable], "claude-remote-control"),
                                 (["claude"], "unrelated-service")):
            with self.subTest(command=command, service=service):
                self.config["agents"][0].update(command=command, credential_service=service)
                with self.assertRaises(hq.HQError):
                    hq.HQ(self.config, api=self.slack)

    def test_start_notice_precedes_execution_and_is_not_repeated(self):
        self.config['announce_start'] = True
        self.enqueue()
        execute = self.runtime.execute
        def observed(task):
            self.assertEqual(len(self.slack.posts), 1)
            self.assertIn('受領・着手', self.slack.posts[0]['text'])
            self.assertEqual(self.slack.posts[0]['thread_ts'], task['thread_ts'])
            return execute(task)
        with mock.patch.object(self.runtime, 'execute', side_effect=observed):
            self.runtime.work()
        self.runtime.work()
        self.assertEqual(len(self.slack.posts), 2)
        notice = json.loads((self.runtime.task_directory(self.tasks()[0])/'start.json').read_text())
        self.assertEqual(notice['state'], 'posted')

    def test_lost_start_response_is_verified_without_reposting(self):
        self.config['announce_start'] = True
        self.enqueue()
        self.slack.lose_post_response = True
        self.runtime.work()
        task=self.tasks()[0]
        self.runtime.announce_start(task)
        self.assertEqual(len(self.slack.posts), 2)
        notice=json.loads((self.runtime.task_directory(task)/'start.json').read_text())
        self.assertEqual(notice['state'], 'posted')

    def test_unknown_start_notice_never_blindly_reposts(self):
        self.config['announce_start'] = True
        self.enqueue()
        self.slack.lose_post_response = True
        self.slack.hide_posts = True
        self.runtime.work()
        task=self.tasks()[0]
        self.runtime.announce_start(task)
        self.assertEqual(len(self.slack.posts), 2)
        notice=json.loads((self.runtime.task_directory(task)/'start.json').read_text())
        self.assertEqual(notice['state'], 'post_unknown')

    def test_scheduled_start_and_result_share_one_thread(self):
        self.config['announce_start'] = True
        self.config['schedules'] = [{'id':'daily','agent':'codex','interval_seconds':3600,'prompt':'bounded work'}]
        self.runtime.schedule(now=3600)
        self.runtime.work()
        self.assertEqual(len(self.slack.posts),2)
        self.assertNotIn('thread_ts', self.slack.posts[0])
        self.assertEqual(self.slack.posts[1]['thread_ts'], self.slack.posts[0]['ts'])
        self.assertEqual(self.tasks()[0]['thread_ts'], self.slack.posts[0]['ts'])

    def test_failed_work_queues_one_bounded_cross_agent_handoff(self):
        self.config['agents'].append(dict(self.config['agents'][0],id='helper',mention=['@helper']))
        self.config['handoff_agent']='helper'
        self.runtime=hq.HQ(self.config,api=self.slack)
        self.enqueue()
        task=self.runtime.claim()
        receipt={'task_id':task['id'],'owner_id':'codex','status':'failed','checkpoint':'failed_handoff_required','output':'partial evidence','agent_state':{'next':'inspect provider receipt'},'exit_code':1}
        self.runtime.finish(task,receipt)
        self.runtime.finish(task,receipt)
        cards=self.tasks()
        handoffs=[x for x in cards if x['source_key'].startswith('handoff:')]
        self.assertEqual(len(handoffs),1)
        self.assertEqual(handoffs[0]['owner_id'],'helper')
        self.assertEqual(handoffs[0]['thread_ts'],task['thread_ts'])
        self.assertIn(task['id'],handoffs[0]['body'])
        self.assertIn('照合',handoffs[0]['body'])
        self.assertIn('partial evidence',handoffs[0]['body'])
        self.assertEqual(next(x for x in cards if x['id']==task['id'])['status'],'failed')

    def test_handoff_failure_does_not_create_an_infinite_chain(self):
        self.config['handoff_agent']='codex'
        with self.runtime.connect() as db:
            self.runtime.insert_task(db,'handoff:prior','codex','inspect prior effect')
        task=self.runtime.claim()
        self.runtime.finish(task,{'task_id':task['id'],'owner_id':'codex','status':'failed','checkpoint':'failed','output':'no capacity','agent_state':{}})
        self.assertEqual(len(self.tasks()),1)

    def test_exit_zero_quota_state_preserves_artifact_and_hands_off_once(self):
        state = {"status": "blocked", "blocker": "quota_exhausted", "handoff_required": True,
                 "next": "既存receiptを照合して未完操作を継続", "proof": ["/fixture/checkpoint"]}
        output = "途中成果は保存済み\nSTATE " + json.dumps(state, ensure_ascii=False)
        command = [sys.executable, "-c", f"import sys; sys.stdin.read(); print({output!r})"]
        self.config["agents"][0].update(command=command, handoff_agent="helper")
        self.config["agents"].append(dict(self.config["agents"][0], id="helper", mention=["@helper"],
                                          handoff_agent="codex"))
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.enqueue()
        task = self.runtime.claim()
        receipt = self.runtime.execute(task)
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(receipt["execution_status"], "succeeded")
        self.assertEqual(receipt["status"], "interrupted")
        self.assertEqual(receipt["checkpoint"], "quota_exhausted_handoff_required")
        self.assertEqual(receipt["agent_state"], state)
        artifact = Path(receipt["artifact_path"])
        self.assertEqual(artifact.read_text(), output)
        self.assertEqual(json.loads((artifact.parent / "result.json").read_text()), receipt)
        self.runtime.finish(task, receipt)
        self.runtime.finish(task, receipt)
        cards = self.tasks()
        handoff = next(row for row in cards if row["source_key"].startswith("handoff:"))
        self.assertEqual(len(cards), 2)
        self.assertEqual(handoff["owner_id"], "helper")
        self.assertEqual(handoff["thread_ts"], task["thread_ts"])
        self.assertIn(state["next"], handoff["body"])
        self.assertIn(output, handoff["body"])
        self.assertIn(str(artifact.parent / "result.json"), handoff["body"])
        original = next(row for row in cards if row["id"] == task["id"])
        self.assertEqual(original["status"], "interrupted")
        self.assertEqual(json.loads(original["proof"]), state["proof"])
        delivered = self.runtime.work()
        self.assertEqual(delivered["execution_status"], "succeeded")
        self.assertEqual(delivered["reply_state"], "posted")
        helper = self.runtime.claim()
        self.assertEqual(helper["id"], handoff["id"])
        helper_receipt = self.runtime.execute(helper)
        self.assertEqual(helper_receipt["status"], "interrupted")
        self.runtime.finish(helper, helper_receipt)
        self.assertEqual(len(self.tasks()), 2)
        self.assertEqual(artifact.read_text(), output)

    def test_incomplete_or_untyped_quota_reports_do_not_handoff(self):
        self.config["agents"].append(dict(self.config["agents"][0], id="helper", mention=["@helper"]))
        self.config["handoff_agent"] = "helper"
        states = [
            {"status": "blocked", "blocker": "quota_exhausted", "handoff_required": False},
            {"status": "blocked", "blocker": "quota_exhausted", "handoff_required": "true"},
            {"status": "blocked", "blocker": "quota_exhausted", "handoff_required": 1},
            {"status": "blocked", "blocker": "quota_exhausted"},
            {"status": "blocked", "blocker": "ci_pending", "handoff_required": True},
            {"status": "reported", "blocker": "quota_exhausted", "handoff_required": True},
            {"status": "CI待ち。利用枠切れなら他担当へ引継ぎ", "next": "最新CIを確認"},
            {"status": "succeeded", "next": "公式照合"},
        ]
        for index, state in enumerate(states):
            with self.subTest(state=state):
                output = "STATE " + json.dumps(state, ensure_ascii=False)
                self.config["agents"][0]["command"] = [
                    sys.executable, "-c", f"import sys; sys.stdin.read(); print({output!r})"]
                self.runtime = hq.HQ(self.config, api=self.slack)
                self.slack.history[""]["messages"] = [self.message(ts=f"101.{index + 1:06d}")]
                self.runtime.receive()
                task = self.runtime.claim()
                receipt = self.runtime.execute(task)
                self.assertEqual(receipt["status"], "succeeded")
                self.assertEqual(receipt["execution_status"], "succeeded")
                self.assertEqual(receipt["checkpoint"], "execution_recorded")
                self.runtime.finish(task, receipt)
                self.assertFalse(any(row["source_key"].startswith("handoff:") for row in self.tasks()))

    def test_nonzero_quota_state_keeps_execution_failure(self):
        output = 'STATE {"status":"blocked","blocker":"quota_exhausted","handoff_required":true}'
        self.config["agents"][0]["command"] = [
            sys.executable, "-c", f"import sys; sys.stdin.read(); print({output!r}); sys.exit(7)"]
        self.config["agents"].append(dict(self.config["agents"][0], id="helper", mention=["@helper"]))
        self.config["handoff_agent"] = "helper"
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.enqueue()
        task = self.runtime.claim()
        receipt = self.runtime.execute(task)
        self.assertEqual(receipt["exit_code"], 7)
        self.assertEqual(receipt["execution_status"], "failed")
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["checkpoint"], "exit_failed_handoff_required")
        self.runtime.finish(task, receipt)
        self.assertEqual(len(self.tasks()), 2)

    def test_our_final_output_quoting_another_agent_is_not_a_new_assignment(self):
        self.config['agents'].append(dict(self.config['agents'][0],id='helper',mention=['@helper']))
        self.runtime=hq.HQ(self.config,api=self.slack)
        self.enqueue()
        task=self.runtime.claim()
        self.runtime.finish(task,{'task_id':task['id'],'owner_id':'codex','status':'succeeded','checkpoint':'done','output':'元依頼の引用: @helper investigate','agent_state':{}})
        reply=self.tasks()[0]['reply_text']
        self.runtime.store_messages([dict(ts='9999.000001',thread_ts=task['thread_ts'],text=reply,user='U_BOT')])
        self.assertEqual(len(self.tasks()),1)

    def test_autolinked_outbox_echo_does_not_assign_quoted_claude(self):
        self.config["agents"].append(dict(self.config["agents"][0], id="claude", mention=["@claude"]))
        self.config["agents"][0]["command"] = [
            sys.executable, "-c", "print('引用: @claude https://example.test/result')",
        ]
        self.slack.autolink_urls = True
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.enqueue()
        self.runtime.work()
        echo = dict(self.slack.posts[0], ts="9999.000001")
        self.assertEqual(self.runtime.store_messages([echo]), 0)
        self.assertEqual(len(self.tasks()), 1)

    def test_changed_outbox_body_still_assigns_quoted_claude(self):
        self.config["agents"].append(dict(self.config["agents"][0], id="claude", mention=["@claude"]))
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.enqueue()
        task = self.runtime.claim()
        self.runtime.finish(task, {
            "task_id": task["id"], "owner_id": "codex", "status": "succeeded",
            "checkpoint": "done", "output": "引用: @claude https://example.test/result", "agent_state": {},
        })
        reply = self.tasks()[0]["reply_text"]
        variants = [
            ("literal_entity", "https://example.test/?a=1&amp;b=2", "<https://example.test/?a=1&amp;b=2>"),
            reply.replace("https://example.test/result", "<https://example.test/other>"),
            reply.replace("https://example.test/result", "<https://example.test/result|https://example.test/result>"),
            reply + "\n追加本文",
            reply.replace(task["marker"], ""),
        ]
        for index, text in enumerate(variants):
            with self.subTest(index=index):
                self.assertEqual(self.runtime.store_messages([
                    dict(ts=f"9999.{index + 1:06d}", thread_ts=task["thread_ts"], text=text, user="U_BOT"),
                ]), 1)
        self.assertEqual([row["owner_id"] for row in self.tasks()[1:]], ["claude"] * len(variants))

    def test_url_token_changes_are_not_suppressed_as_outbox_echoes(self):
        self.config["agents"].append(dict(self.config["agents"][0], id="claude", mention=["@claude"]))
        variants = [
            ("split_urls", "https://example.test/resulthttps://different.test/other",
             "<https://example.test/result><https://different.test/other>"),
            ("url_suffix", "https://example.test/resultsuffix", "<https://example.test/result>suffix"),
        ]
        for name, expected, actual in variants:
            with self.subTest(name=name):
                self.runtime = hq.HQ(dict(self.config, state_dir=str(self.root / name)), api=self.slack)
                self.enqueue()
                task = self.runtime.claim()
                self.runtime.finish(task, {
                    "task_id": task["id"], "owner_id": "codex", "status": "succeeded",
                    "checkpoint": "done", "output": "引用: @claude " + expected, "agent_state": {},
                })
                reply = self.tasks()[0]["reply_text"].replace(expected, actual)
                self.assertEqual(self.runtime.store_messages([
                    dict(ts="9999.000001", thread_ts=task["thread_ts"], text=reply, user="U_BOT"),
                ]), 1)
                self.assertEqual(self.tasks()[1]["owner_id"], "claude")

    def test_autolinks_in_markdown_and_json_are_known_outbox_echoes(self):
        self.config["agents"].append(dict(self.config["agents"][0], id="claude", mention=["@claude"]))
        for name, expected, actual in AUTOLINK_BOUNDARIES:
            with self.subTest(name=name):
                self.runtime = hq.HQ(dict(self.config, state_dir=str(self.root / name)), api=self.slack)
                self.enqueue()
                task = self.runtime.claim()
                self.runtime.finish(task, {
                    "task_id": task["id"], "owner_id": "codex", "status": "succeeded",
                    "checkpoint": "done", "output": "引用: @claude " + expected, "agent_state": {},
                })
                reply = self.tasks()[0]["reply_text"].replace(expected, actual)
                self.assertEqual(self.runtime.store_messages([
                    dict(ts="9999.000001", thread_ts=task["thread_ts"], text=reply, user="U_BOT"),
                ]), 0)
                self.assertEqual(len(self.tasks()), 1)

    def test_scheduled_unknown_start_defers_only_its_final_and_reconciles_next_wake(self):
        self.config['announce_start']=True
        self.config['schedules']=[{'id':'daily','agent':'codex','interval_seconds':3600,'prompt':'work'}]
        self.runtime.schedule(now=3600)
        self.slack.lose_post_response=True
        self.slack.hide_posts=True
        first=self.runtime.work()
        self.assertFalse(first['ok'])
        self.assertEqual(len(self.slack.posts),1)
        self.assertEqual(self.tasks()[0]['status'],'succeeded')
        self.slack.hide_posts=False
        result=self.runtime.work()
        self.assertTrue(result['ok'])
        self.assertEqual(len(self.slack.posts),2)
        self.assertEqual(self.slack.posts[1]['thread_ts'],self.slack.posts[0]['ts'])
        self.runtime.work()
        self.assertEqual(len(self.slack.posts),2)

    def test_recovery_keeps_unknown_start_and_handoff_on_original_scheduled_thread(self):
        self.config['announce_start']=True
        self.config['agents'].append(dict(self.config['agents'][0],id='helper',mention=['@helper']))
        self.config['handoff_agent']='helper'
        self.config['schedules']=[{'id':'daily','agent':'codex','interval_seconds':3600,'prompt':'work'}]
        self.runtime=hq.HQ(self.config,api=self.slack)
        self.runtime.schedule(now=3600)
        task=self.runtime.claim()
        self.slack.lose_post_response=True
        self.slack.hide_posts=True
        self.runtime.announce_start(task)
        self.runtime.work()  # no execution receipt: interrupted recovery
        self.assertEqual(len(self.slack.posts),1)
        handoff=next(x for x in self.tasks() if x['source_key'].startswith('handoff:'))
        self.assertEqual(handoff['status'],'queued')
        self.slack.hide_posts=False
        self.runtime.work()
        handoff=next(x for x in self.tasks() if x['source_key'].startswith('handoff:'))
        self.assertEqual(handoff['thread_ts'],self.slack.posts[0]['ts'])
        self.assertEqual(self.slack.posts[1]['thread_ts'],self.slack.posts[0]['ts'])

    def test_foreign_echo_cannot_verify_our_post(self):
        self.enqueue()
        task=self.runtime.claim()
        self.runtime.finish(task,self.runtime.execute(task))
        with self.runtime.connect() as db:
            db.execute("UPDATE tasks SET reply_state='post_unknown' WHERE id=?",(task['id'],))
        task=self.tasks()[0]
        self.slack.threads[(task['thread_ts'],'')]={'ok':True,'messages':[
            dict(ts='9001.000001',text=task['reply_text'],user='U_FOREIGN',bot_id='B_FOREIGN')]}
        self.runtime.work()
        self.assertNotEqual(self.tasks()[0]['reply_state'],'posted')
        self.assertEqual(self.slack.posts,[])

    def test_rejected_reply_does_not_starve_independent_task(self):
        self.slack.history[""]["messages"] = [self.message(),self.message('102.000001')]
        self.runtime.receive()
        call=self.slack.call
        def reject_one(method,**parameters):
            if method=='chat.postMessage' and parameters.get('thread_ts')=='101.000001':
                return {'ok':False,'error':'thread_not_found'}
            return call(method,**parameters)
        self.slack.call=reject_one
        self.runtime.work();self.runtime.work()
        self.assertEqual(self.tasks()[0]['reply_state'],'delivery_failed')
        self.assertEqual(self.tasks()[1]['status'],'succeeded')

    def test_corrupt_receipt_isolated_without_reexecution_or_loss(self):
        self.slack.history[""]["messages"] = [self.message(),self.message('102.000001')]
        self.runtime.receive()
        task=self.runtime.claim();path=self.runtime.task_directory(task)/'result.json'
        path.write_text('broken original receipt')
        self.runtime.work();self.runtime.work()
        self.assertEqual(path.read_text(),'broken original receipt')
        self.assertEqual(self.tasks()[0]['status'],'interrupted')
        self.assertEqual(self.tasks()[0]['checkpoint'],'invalid_receipt_handoff_required')
        self.assertEqual(self.tasks()[1]['status'],'succeeded')

    def test_http_200_ok_false_is_failure_without_secret(self):
        response = io.BytesIO(b'{"ok":false,"error":"not_authed"}')
        with mock.patch.object(hq.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(hq.HQError) as caught:
                hq.SlackAPI("private-slack-token").call("conversations.history", channel="C_TEST")
        self.assertNotIn("private-slack-token", str(caught.exception))

    def test_history_pagination_and_old_thread_reply_survive_cursor(self):
        self.slack.history = {
            "": {"ok": True, "messages": [self.message("1000.000001", "ordinary root")],
                 "response_metadata": {"next_cursor": "older"}},
            "older": {"ok": True, "messages": [self.message("10.000001", "old root")]},
        }
        self.runtime.receive()
        self.slack.history = {"": {"ok": True, "messages": []}}
        self.slack.threads[("10.000001", "")] = {
            "ok": True, "messages": [self.message("1100.000001", "<@U_CODEX> real reply", "10.000001")],
            "response_metadata": {"next_cursor": "reply2"},
        }
        self.slack.threads[("10.000001", "reply2")] = {
            "ok": True, "messages": [self.message("1101.000001", "@codex second reply", "10.000001")],
        }
        self.assertEqual(self.runtime.receive()["queued"], 2)
        self.assertEqual(self.runtime.receive()["queued"], 0)
        self.assertEqual([r["source_ts"] for r in self.tasks()], ["1100.000001", "1101.000001"])

    def test_legacy_done_import_prevents_replay_and_own_prefix_is_ignored(self):
        legacy = self.root / "legacy.json"
        legacy.write_text(json.dumps({"last": "100", "done": ["101.000001"]}))
        config = dict(self.config, state_dir=str(self.root / "imported"), legacy_state_file=str(legacy))
        runtime = hq.HQ(config, api=self.slack)
        self.slack.history[""]["messages"] = [
            self.message(), self.message("102.000001", "[codex] @codex own reply"),
            self.message("103.000001", "@codex new work"),
            self.message("90.000001", "@codex old processed history"),
        ]
        self.assertEqual(runtime.receive()["queued"], 1)
        legacy.write_text(json.dumps({"last": "100", "done": ["103.000001"]}))
        self.assertEqual(hq.HQ(config, api=self.slack).receive()["queued"], 0)

    def test_receive_error_does_not_advance_poll_cursor(self):
        self.slack.error = True
        with self.assertRaises(hq.HQError):
            self.runtime.receive()
        self.assertIsNone(self.runtime.status()["last_poll"])

    def test_priority_thread_receives_before_backlog_without_extra_poll_calls(self):
        priority = "999.000001"
        self.config.update(priority_thread=priority, max_threads_per_poll=2)
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.runtime.store_messages([self.message(f"{index}.000001", "ordinary root")
                                     for index in (100, 101, 102, 999)])
        with self.runtime.connect() as database:
            database.execute("UPDATE threads SET polled=50 WHERE ts=?", (priority,))
        self.slack.threads[(priority, "")] = {
            "ok": True, "messages": [self.message("1000.000001", "@codex review", priority)],
        }
        self.assertEqual(self.runtime.receive()["queued"], 1)
        self.assertEqual(self.runtime.receive()["queued"], 0)
        self.assertEqual(self.runtime.receive()["queued"], 0)
        calls = [parameters["ts"] for method, parameters in self.slack.calls
                 if method == "conversations.replies"]
        self.assertEqual(calls, [priority, "100.000001", priority, "101.000001", priority, "102.000001"])
        self.assertEqual(len(self.tasks()), 1)
        self.assertIsNotNone(self.runtime.claim())

    def test_undiscovered_priority_thread_preserves_existing_poll_order(self):
        self.config.update(priority_thread="999.000001", max_threads_per_poll=2)
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.runtime.store_messages([self.message(f"{index}.000001", "ordinary root")
                                     for index in (100, 101)])
        self.runtime.receive()
        calls = [parameters["ts"] for method, parameters in self.slack.calls
                 if method == "conversations.replies"]
        self.assertEqual(calls, ["100.000001", "101.000001"])

    def test_priority_thread_requires_valid_timestamp_and_other_thread_capacity(self):
        for priority in (True, [], "", "NaN", "not-a-timestamp"):
            with self.subTest(priority=priority), self.assertRaises(hq.HQError):
                hq.HQ(dict(self.config, priority_thread=priority), api=self.slack)
        with self.assertRaises(hq.HQError):
            hq.HQ(dict(self.config, priority_thread="999.000001", max_threads_per_poll=1), api=self.slack)

    def test_receive_preserves_bounded_page_continuations_and_rotates_threads(self):
        self.config.update(max_history_pages=1, max_threads_per_poll=1, max_thread_pages=1)
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.slack.history = {
            "": {"ok": True, "messages": [self.message("20.000001", "first root")],
                 "response_metadata": {"next_cursor": "second"}},
            "second": {"ok": True, "messages": [self.message("10.000001", "second root")]},
        }
        self.runtime.receive()
        self.runtime.receive()
        history_calls = [parameters for method, parameters in self.slack.calls
                         if method == "conversations.history" and "latest" not in parameters]
        self.assertEqual(len(history_calls), 2)
        self.assertEqual(history_calls[1].get("cursor"), "second")
        thread_calls = [parameters["ts"] for method, parameters in self.slack.calls if method == "conversations.replies"]
        self.assertEqual(thread_calls, ["20.000001", "10.000001"])

    def test_initial_history_is_limited_to_configured_lookback(self):
        self.config["lookback_days"] = 1
        self.runtime = hq.HQ(self.config, api=self.slack)
        with mock.patch.object(hq.time, "time", return_value=2000000):
            self.runtime.receive()
        self.assertEqual(self.slack.calls[0][1]["oldest"], "1913600")

    def test_initial_backfill_finds_new_reply_on_old_root_without_replaying_old_work(self):
        self.config.update(max_history_pages=1, max_threads_per_poll=1)
        self.runtime = hq.HQ(self.config, api=self.slack)
        cutoff = 2000000 - 7 * 86400
        call = self.slack.call

        def history(method, **parameters):
            if method == "conversations.history":
                self.slack.calls.append((method, dict(parameters)))
                if "latest" not in parameters:
                    return {"ok": True, "messages": []}
                if not parameters.get("cursor"):
                    return {"ok": True, "messages": [self.message("20", "@codex old root")],
                            "response_metadata": {"next_cursor": "older"}}
                return {"ok": True, "messages": [self.message("10", "older root")]}
            if method == "conversations.replies":
                self.slack.calls.append((method, dict(parameters)))
                messages = [self.message("21", "@codex old work", parameters["ts"])]
                if parameters["ts"] == "10":
                    messages.append(self.message("22", "old clarification: preserve the agreed scope", "10"))
                    messages.append(self.message(str(cutoff + 1), "@codex new reply", "10"))
                messages = [message for message in messages if float(message["ts"]) > float(parameters["oldest"])]
                return {"ok": True, "messages": messages}
            return call(method, **parameters)

        self.slack.call = history
        with mock.patch.object(hq.time, "time", return_value=2000000):
            self.assertEqual(self.runtime.receive()["queued"], 0)
            self.assertIsNone(self.runtime.claim())
            self.runtime = hq.HQ(self.config, api=self.slack)
            self.assertEqual(self.runtime.receive()["queued"], 1)
            self.assertEqual(self.runtime.receive()["queued"], 0)
        self.assertEqual([task["source_ts"] for task in self.tasks()], [str(cutoff + 1)])
        backfill = [p for method, p in self.slack.calls if method == "conversations.history" and "latest" in p]
        self.assertEqual(len(backfill), 2)
        self.assertEqual(backfill[0]["oldest"], "0")
        self.assertEqual(backfill[0]["latest"], str(cutoff))
        self.assertEqual(backfill[1]["cursor"], "older")
        task = self.runtime.claim()
        self.assertIsNotNone(task)
        self.assertIn("old clarification: preserve the agreed scope", self.runtime.prompt(task))

    def test_task_waits_for_all_thread_pages_before_claim(self):
        self.config["max_thread_pages"] = 1
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.slack.threads[("101.000001", "")] = {
            "ok": True, "messages": [self.message("102", "first clarification", "101.000001")],
            "response_metadata": {"next_cursor": "more"},
        }
        self.slack.threads[("101.000001", "more")] = {
            "ok": True, "messages": [self.message("103", "final clarification", "101.000001")],
        }
        self.enqueue()
        self.assertIsNone(self.runtime.claim())
        self.runtime.receive()
        task = self.runtime.claim()
        self.assertIsNotNone(task)
        self.assertIn("first clarification", self.runtime.prompt(task))
        self.assertIn("final clarification", self.runtime.prompt(task))

    def test_task_waits_until_its_thread_is_selected(self):
        self.config["max_threads_per_poll"] = 1
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.slack.history[""]["messages"] = [self.message("100", "ordinary root"), self.message()]
        self.runtime.receive()
        self.assertIsNone(self.runtime.claim())
        self.runtime.receive()
        self.assertIsNotNone(self.runtime.claim())

    def test_new_reply_invalidates_previously_complete_thread_context(self):
        self.slack.history[""]["messages"] = [self.message("100", "ordinary root")]
        self.runtime.receive()
        self.slack.history[""]["messages"] = [self.message("101", "@codex new request", "100")]
        call, claims = self.slack.call, []

        def during_scan(method, **parameters):
            if method == "conversations.replies":
                claims.append(self.runtime.claim())
            return call(method, **parameters)

        self.slack.call = during_scan
        self.runtime.receive()
        self.assertEqual(claims, [None])
        self.assertIsNotNone(self.runtime.claim())

    def test_claim_waits_during_rescan_of_previously_ready_thread(self):
        self.enqueue()
        call, claims = self.slack.call, []

        def during_scan(method, **parameters):
            if method == "conversations.replies":
                claims.append(self.runtime.claim())
            return call(method, **parameters)

        self.slack.call = during_scan
        self.runtime.receive()
        self.assertEqual(claims, [None])
        self.assertIsNotNone(self.runtime.claim())

    def test_plain_mention_does_not_route_a_different_identifier(self):
        self.slack.history[""]["messages"] = [self.message(text="@codex_other is a different recipient")]
        self.assertEqual(self.runtime.receive()["queued"], 0)

    def test_duplicate_agent_ids_are_rejected_before_task_routing(self):
        self.config["agents"].append(dict(self.config["agents"][0], command=["other-agent"]))
        with self.assertRaises(hq.HQError):
            hq.HQ(self.config, api=self.slack)

    def test_receiver_does_not_wait_on_execution_lock(self):
        self.slack.history[""]["messages"] = [self.message()]
        with self.runtime.lock("work"):
            self.assertEqual(self.runtime.receive()["queued"], 1)

    def test_atomic_claim_never_assigns_one_card_twice(self):
        self.enqueue()
        barrier = threading.Barrier(2)

        def claim():
            runtime = hq.HQ(self.config, api=self.slack)
            barrier.wait()
            return runtime.claim()

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            claims = list(pool.map(lambda _: claim(), range(2)))
        self.assertEqual(sum(row is not None for row in claims), 1)
        task = self.tasks()[0]
        self.assertEqual(task["status"], "working")
        self.assertEqual(task["owner_id"], "codex")

    def test_worker_exit_failure_is_failed_not_success_and_never_reruns(self):
        script = self.root / "fail.py"
        script.write_text("import pathlib,sys\np=pathlib.Path('calls')\np.write_text(p.read_text()+'x' if p.exists() else 'x')\nprint('private-slack-token',file=sys.stderr)\nsys.exit(7)\n")
        self.config["agents"][0]["command"] = [sys.executable, str(script)]
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.enqueue()
        result = self.runtime.work()
        self.assertTrue(result["ok"])
        self.assertEqual(result.get("execution_status"), "failed")
        row = self.tasks()[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["exit_code"], 7)
        self.assertTrue(Path(row["result_path"]).is_file())
        self.runtime.work()
        self.assertEqual((self.root / "calls").read_text(), "x")
        self.assertNotIn("private-slack-token", json.dumps(self.slack.posts))

    def test_success_uses_prompt_stdin_and_artifact_without_adding_flags(self):
        script = self.root / "success.py"
        script.write_text("import pathlib,sys,json\nassert len(sys.argv)==2\nprompt=sys.stdin.read()\npathlib.Path('prompt').write_text(prompt)\npathlib.Path(sys.argv[1]).write_text('実仕事の実行結果\\nSTATE {\"status\":\"reported\",\"next\":\"公式照合\",\"proof\":[\"artifact\"]}')\n")
        self.config["agents"][0]["command"] = [sys.executable, str(script), "{artifact}"]
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.enqueue()
        self.assertTrue(self.runtime.work()["ok"])
        row = self.tasks()[0]
        self.assertEqual(row["status"], "succeeded")
        self.assertEqual(row["reply_state"], "posted")
        receipt = json.loads(Path(row["result_path"]).read_text())
        self.assertEqual(receipt["business_outcome"], "unverified")
        self.assertEqual(receipt["agent_state"]["next"], "公式照合")
        self.assertIn("BOARD", (self.root / "prompt").read_text())
        self.assertEqual(self.runtime.status()["tasks"][0].get("proof"), ["artifact"])

    def test_agent_process_does_not_inherit_trusted_runtime_hint_or_identity(self):
        script = self.root / "environment.py"
        script.write_text("import json,os,pathlib\npathlib.Path('child-env.json').write_text(json.dumps({'trusted_keys':[k for k in os.environ if k.startswith('LIFE_MANAGER_')],'context':os.environ.get('HQ_TEST_CONTEXT')}))\n")
        self.config["agents"][0]["command"] = [sys.executable, str(script)]
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.enqueue()
        environment = {"LIFE_MANAGER_RESULT_HINT_PATH": str(self.root / "hint.json"),
                       "LIFE_MANAGER_LOOP_ID": "team-hq-work", "LIFE_MANAGER_OCCURRENCE_ID": "work:one",
                       "LIFE_MANAGER_RUN_ID": "trusted-run", "LIFE_MANAGER_RELEASE_SHA": "trusted-release",
                       "HQ_TEST_CONTEXT": "keep"}
        with mock.patch.dict(os.environ, environment):
            self.runtime.work()
        child = json.loads((self.root / "child-env.json").read_text())
        self.assertEqual(child["trusted_keys"], [])
        self.assertEqual(child["context"], "keep")
        self.assertEqual(json.loads((self.root / "hint.json").read_text())["status"], "verified")

    def test_artifact_symlink_cannot_overwrite_another_file(self):
        victim = self.root / "preserve"
        victim.write_text("preserved")
        script = self.root / "symlink.py"
        script.write_text("import pathlib,sys\npathlib.Path(sys.argv[1]).symlink_to(pathlib.Path('preserve').resolve())\n")
        self.config["agents"][0]["command"] = [sys.executable, str(script), "{artifact}"]
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.enqueue()
        result = self.runtime.work()
        self.assertEqual(result.get("execution_status"), "failed")
        self.assertEqual(victim.read_text(), "preserved")

    def test_marker_only_echo_is_not_an_official_reply_receipt(self):
        self.enqueue()
        task = self.tasks()[0]
        self.slack.hide_posts = True
        self.slack.threads[(task["thread_ts"], "")] = {
            "ok": True, "messages": [self.message("102.000001", task["marker"], task["thread_ts"])],
        }
        self.assertFalse(self.runtime.work()["ok"])
        self.assertEqual(self.tasks()[0]["reply_state"], "post_unknown")

    def test_unknown_post_response_is_reconciled_without_resend_or_rerun(self):
        self.enqueue()
        self.slack.lose_post_response = True
        self.slack.hide_posts = True
        self.assertFalse(self.runtime.work()["ok"])
        self.assertEqual(self.tasks()[0]["reply_state"], "post_unknown")
        self.assertEqual(len(self.slack.posts), 1)
        self.slack.hide_posts = False
        self.assertTrue(self.runtime.work()["ok"])
        self.assertEqual(self.tasks()[0]["reply_state"], "posted")
        self.assertEqual(len(self.slack.posts), 1)

    def test_slack_autolinks_verify_one_post_and_emit_trusted_hint(self):
        output = "証拠 https://example.test/result?ct=hq_1 http://example.test/source https://example.test/log#done"
        self.config["agents"][0]["command"] = [sys.executable, "-c", f"print({output!r})"]
        self.slack.autolink_urls = True
        self.enqueue()
        hint = self.root / "hint.json"
        with mock.patch.dict(os.environ, {"LIFE_MANAGER_RESULT_HINT_PATH": str(hint)}):
            result = self.runtime.work()
        self.assertTrue(result["ok"])
        self.assertEqual(self.tasks()[0]["reply_state"], "posted")
        self.assertEqual(self.tasks()[0]["reply_ts"], "9000.000001")
        self.assertEqual(json.loads(hint.read_text())["status"], "verified")
        self.runtime.work()
        self.assertEqual(len(self.slack.posts), 1)

    def test_unknown_autolinked_reply_reconciles_without_resend_or_rerun(self):
        self.config["agents"][0]["command"] = [
            sys.executable, "-c", "print('証拠 https://example.test/result')",
        ]
        self.slack.autolink_urls = True
        self.slack.lose_post_response = True
        self.slack.hide_posts = True
        self.enqueue()
        self.assertFalse(self.runtime.work()["ok"])
        self.assertEqual(self.tasks()[0]["reply_state"], "post_unknown")
        self.slack.hide_posts = False
        with mock.patch.object(self.runtime, "execute", side_effect=AssertionError("再実行は禁止")):
            self.assertTrue(self.runtime.work()["ok"])
        self.assertEqual(self.tasks()[0]["reply_state"], "posted")
        self.assertEqual(len(self.slack.posts), 1)

    def test_autolink_readback_rejects_changed_body_and_foreign_sender(self):
        variants = [
            ("different_url", "<https://example.test/other>", "U_BOT", "B_BOT", ""),
            ("labelled_url", "<https://example.test/result|https://example.test/result>", "U_BOT", "B_BOT", ""),
            ("label_spoof", "<https://example.test/other|https://example.test/result>", "U_BOT", "B_BOT", ""),
            ("extra_body", "<https://example.test/result>", "U_BOT", "B_BOT", "\n追加本文"),
            ("foreign_sender", "<https://example.test/result>", "U_FOREIGN", "B_FOREIGN", ""),
        ]
        for name, link, user, bot, suffix in variants:
            with self.subTest(name=name):
                self.slack = Slack()
                self.runtime = hq.HQ(dict(self.config, state_dir=str(self.root / name)), api=self.slack)
                self.enqueue()
                task = self.runtime.claim()
                self.runtime.finish(task, {
                    "task_id": task["id"], "owner_id": "codex", "status": "succeeded",
                    "checkpoint": "done", "output": "証拠 https://example.test/result", "agent_state": {},
                })
                with self.runtime.connect() as database:
                    database.execute("UPDATE tasks SET reply_state='post_unknown' WHERE id=?", (task["id"],))
                reply = self.tasks()[0]["reply_text"].replace("https://example.test/result", link) + suffix
                self.slack.threads[(task["thread_ts"], "")] = {
                    "ok": True, "messages": [dict(ts="9001.000001", text=reply, user=user, bot_id=bot)],
                }
                self.assertFalse(self.runtime.work()["ok"])
                self.assertEqual(self.tasks()[0]["reply_state"], "post_unknown")
                self.assertEqual(self.slack.posts, [])

    def test_url_token_changes_cannot_verify_an_unknown_post(self):
        variants = [
            ("split_urls", "https://example.test/resulthttps://different.test/other",
             "<https://example.test/result><https://different.test/other>"),
            ("url_suffix", "https://example.test/resultsuffix", "<https://example.test/result>suffix"),
        ]
        for name, expected, actual in variants:
            with self.subTest(name=name):
                self.slack = Slack()
                self.runtime = hq.HQ(dict(self.config, state_dir=str(self.root / name)), api=self.slack)
                self.enqueue()
                task = self.runtime.claim()
                self.runtime.finish(task, {
                    "task_id": task["id"], "owner_id": "codex", "status": "succeeded",
                    "checkpoint": "done", "output": "証拠 " + expected, "agent_state": {},
                })
                with self.runtime.connect() as database:
                    database.execute("UPDATE tasks SET reply_state='post_unknown' WHERE id=?", (task["id"],))
                reply = self.tasks()[0]["reply_text"].replace(expected, actual)
                self.slack.threads[(task["thread_ts"], "")] = {
                    "ok": True, "messages": [dict(ts="9001.000001", text=reply, user="U_BOT", bot_id="B_BOT")],
                }
                hint = self.root / "hint.json"
                with mock.patch.dict(os.environ, {"LIFE_MANAGER_RESULT_HINT_PATH": str(hint)}):
                    self.assertFalse(self.runtime.work()["ok"])
                self.assertEqual(self.tasks()[0]["reply_state"], "post_unknown")
                self.assertFalse(hint.exists())
                self.assertEqual(self.slack.posts, [])

    def test_autolinks_in_markdown_and_json_reconcile_without_resend(self):
        for name, expected, actual in AUTOLINK_BOUNDARIES:
            with self.subTest(name=name):
                self.slack = Slack()
                self.runtime = hq.HQ(dict(self.config, state_dir=str(self.root / name)), api=self.slack)
                self.enqueue()
                task = self.runtime.claim()
                self.runtime.finish(task, {
                    "task_id": task["id"], "owner_id": "codex", "status": "succeeded",
                    "checkpoint": "done", "output": expected, "agent_state": {},
                })
                with self.runtime.connect() as database:
                    database.execute("UPDATE tasks SET reply_state='post_unknown' WHERE id=?", (task["id"],))
                reply = self.tasks()[0]["reply_text"].replace(expected, actual)
                self.slack.threads[(task["thread_ts"], "")] = {
                    "ok": True, "messages": [dict(ts="9001.000001", text=reply, user="U_BOT", bot_id="B_BOT")],
                }
                self.assertTrue(self.runtime.work()["ok"])
                self.assertEqual(self.tasks()[0]["reply_state"], "posted")
                self.runtime.work()
                self.assertEqual(self.slack.posts, [])

    def test_ambiguous_slack_rejection_accepts_official_marker_readback(self):
        for error in ("internal_error", "fatal_error"):
            with self.subTest(error=error):
                self.slack = Slack()
                self.runtime = hq.HQ(dict(self.config, state_dir=str(self.root / error)), api=self.slack)
                self.enqueue()
                call = self.slack.call

                def rejected(method, **parameters):
                    response = call(method, **parameters)
                    return {"ok": False, "error": error} if method == "chat.postMessage" else response

                self.slack.call = rejected
                self.assertTrue(self.runtime.work()["ok"])
                self.assertEqual(self.tasks()[0]["reply_state"], "posted")
                self.assertEqual(len(self.slack.posts), 1)

    def test_ambiguous_slack_rejection_is_reconciled_later_without_resend(self):
        for error in ("internal_error", "fatal_error"):
            with self.subTest(error=error):
                self.slack = Slack()
                self.runtime = hq.HQ(dict(self.config, state_dir=str(self.root / error)), api=self.slack)
                self.enqueue()
                call = self.slack.call

                def rejected(method, **parameters):
                    response = call(method, **parameters)
                    return {"ok": False, "error": error} if method == "chat.postMessage" else response

                self.slack.call = rejected
                self.slack.hide_posts = True
                self.assertFalse(self.runtime.work()["ok"])
                self.assertEqual(self.tasks()[0]["reply_state"], "post_unknown")
                self.slack.hide_posts = False
                self.assertTrue(self.runtime.work()["ok"])
                self.assertEqual(self.tasks()[0]["reply_state"], "posted")
                self.assertEqual(len(self.slack.posts), 1)

    def test_unknown_reply_does_not_stop_a_different_queued_task(self):
        self.enqueue()
        self.slack.lose_post_response = True
        self.slack.hide_posts = True
        self.runtime.work()
        self.slack.history[""]["messages"] = [self.message("102.000001", "@codex separate work")]
        self.runtime.receive()
        self.slack.lose_post_response = False
        self.slack.hide_posts = False
        # Keep the first marker hidden while allowing the new post's readback.
        first = self.slack.posts[0]
        self.slack.posts = []
        result = self.runtime.work()
        self.assertTrue(result["ok"])
        rows = self.tasks()
        self.assertEqual(rows[0]["reply_state"], "post_unknown")
        self.assertEqual(rows[1]["reply_state"], "posted")
        self.assertNotEqual(result["task_id"], rows[0]["id"])
        self.assertEqual(len(self.slack.posts), 1)
        self.assertNotEqual(first["text"], self.slack.posts[0]["text"])

    def test_working_crash_is_handoff_required_and_never_reassigned(self):
        self.enqueue()
        self.runtime.claim()
        self.runtime.work()
        row = self.tasks()[0]
        self.assertEqual(row["status"], "interrupted")
        self.assertIn("handoff", row["checkpoint"])
        self.assertEqual(self.runtime.status()["handoff_required"], 1)

    def test_execution_receipt_recovers_reply_after_process_completion_crash(self):
        self.enqueue()
        with mock.patch.object(self.runtime, "finish", side_effect=RuntimeError("crash after receipt")):
            with self.assertRaises(RuntimeError):
                self.runtime.work()
        self.assertEqual(self.tasks()[0]["status"], "working")
        self.assertTrue(self.runtime.work()["ok"])
        self.assertEqual(self.tasks()[0]["status"], "succeeded")
        self.assertEqual(len(self.slack.posts), 1)

    def test_schedule_slot_is_deduplicated_and_status_exposes_owner_checkpoint(self):
        self.config["schedules"] = [
            {"id": "hourly", "agent": "codex", "interval_seconds": 3600, "prompt": "収益仕事を選んで実行"},
            {"id": "manager", "agent": "codex", "hours_jst": [9, 14, 21], "prompt": "Managerの仕事"},
        ]
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.assertEqual(self.runtime.schedule(now=1793577600)["queued"], 2)  # 2026-11-02 09:00 JST
        self.assertEqual(self.runtime.schedule(now=1793577601)["queued"], 0)
        status = self.runtime.status()
        self.assertEqual(status["counts"]["queued"], 2)
        self.assertTrue(all(row["id"] and row["owner_id"] and row["updated"] and row["checkpoint"] for row in status["tasks"]))

    def test_timeout_stops_process_group_and_records_unknown_effect(self):
        script = self.root / "sleep.py"
        script.write_text("import subprocess,sys,time\np=subprocess.Popen([sys.executable,'-c',\"import time,pathlib;time.sleep(1);pathlib.Path('child-effect').write_text('bad')\"])\ntime.sleep(30)\n")
        self.config["agents"][0]["command"] = [sys.executable, str(script)]
        self.config["timeout_seconds"] = 0.1
        self.runtime = hq.HQ(self.config, api=self.slack)
        self.enqueue()
        result = self.runtime.work()
        self.assertTrue(result["ok"])
        self.assertEqual(result.get("execution_status"), "failed")
        self.assertEqual(self.tasks()[0]["checkpoint"], "timeout_handoff_required")
        # A second worker never runs the same task even after a timeout.
        self.runtime.work()
        self.assertIsNone(self.runtime.claim())
        time.sleep(1.1)
        self.assertFalse((self.root / "child-effect").exists())

    def test_cli_config_path_and_json_status_are_portable(self):
        config_file = self.root / "team.json"
        config_file.write_text(json.dumps(self.config))
        result = subprocess.run([sys.executable, "-m", "runtime.team_hq.main", "status"],
                                env=dict(os.environ, TEAM_HQ_CONFIG=str(config_file)),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["counts"], {})
        self.assertNotIn("private-slack-token", result.stdout + result.stderr)

    def test_verified_post_hint_requires_marker_readback_and_idle_is_no_effect(self):
        hint = self.root / "hint.json"
        environment = {"LIFE_MANAGER_RESULT_HINT_PATH": str(hint),
                       "LIFE_MANAGER_LOOP_ID": "team-hq-work", "LIFE_MANAGER_OCCURRENCE_ID": "work:one"}
        with mock.patch.dict(os.environ, environment):
            self.runtime.work()
            self.assertEqual(json.loads(hint.read_text())["status"], "no_effect")
            self.enqueue()
            self.runtime.work()
            receipt = json.loads(hint.read_text())
        self.assertEqual(receipt["kind"], "team_hq_result")
        self.assertEqual(receipt["status"], "verified")
        self.assertEqual(receipt["message_ts"], "9000.000001")
        self.assertEqual(hint.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()


class ReasonInboxTests(unittest.TestCase):
    setUp = HQTests.setUp
    tasks = HQTests.tasks

    def enabled(self):
        self.config["announce_start"] = True
        self.config["reason_network"] = {
            "binary": "/fixture/reason-network-hq", "name": "hq-codex", "agent": "codex",
        }
        self.reason = mock.Mock()
        self.reason.send.return_value = {"ids": ["01M6G11XSHQTVE7JPSSAEE34JA"],
                                         "recipients": [{"address": "daisuke/muse@remote", "state": "delivered"}]}
        self.message_id = "01M6G37N2HYGRZ2JAJ4KC98QBY"
        self.reason.inbox.return_value = {
            "session_key": "cli:hq-codex", "address": "daisuke/hq-codex",
            "messages": [{"id": self.message_id, "from": "daisuke/muse@remote",
                          "to": "daisuke/hq-codex", "body": "read-only canary", "reply_to": None}],
        }
        self.runtime = hq.HQ(self.config, api=self.slack, reason_api=self.reason)

    def test_reason_commits_the_single_task_before_ack(self):
        self.enabled()
        def ack(ids):
            rows = self.tasks()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_key"], "reason:" + self.message_id)
            self.assertEqual(rows[0]["owner_id"], "codex")
            self.assertIn("read-only canary", rows[0]["body"])
            self.assertEqual(ids, [self.message_id])
        self.reason.ack.side_effect = ack
        self.assertEqual(self.runtime.receive()["queued"], 1)
        self.reason.ack.assert_called_once()

    def test_reason_ack_failure_replay_does_not_duplicate_work(self):
        self.enabled()
        self.reason.ack.side_effect = hq.HQError("transport unavailable")
        self.assertFalse(self.runtime.receive()["ok"])
        self.assertEqual(len(self.tasks()), 1)
        self.reason.ack.side_effect = None
        self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(len(self.tasks()), 1)
        self.assertEqual(self.reason.ack.call_count, 2)

    def test_reason_attachment_is_durable_and_in_task_before_ack(self):
        self.enabled()
        inbox = self.root / "reason" / "inbox" / "fixture"
        inbox.mkdir(parents=True)
        attachment = inbox / "brief.txt"
        attachment.write_text("attachment evidence", encoding="utf-8")
        self.reason.inbox.return_value["messages"][0]["files"] = [
            {"name": "brief.txt", "content": "", "path": str(attachment)}]

        def ack(ids):
            self.assertEqual(ids, [self.message_id])
            self.assertIn("attachment evidence", self.tasks()[0]["body"])

        self.reason.ack.side_effect = ack
        with mock.patch.dict(os.environ, {"REASON_NETWORK_HOME": str(self.root / "reason")}):
            self.assertTrue(self.runtime.receive()["ok"])
        attachment.unlink()
        self.assertIn("attachment evidence", self.tasks()[0]["body"])

    def test_missing_reason_attachment_does_not_ack_or_starve_other_messages(self):
        self.enabled()
        first = self.reason.inbox.return_value["messages"][0]
        first["files"] = [{"name": "lost.txt", "content": "", "path": str(
            self.root / "reason" / "inbox" / "fixture" / "lost.txt")}]
        second_id = "01M6G37N2HYGRZ2JAJ4KC98QBZ"
        self.reason.inbox.return_value["messages"].append({
            "id": second_id, "from": "daisuke/muse@remote", "to": "daisuke/hq-codex",
            "body": "independent request", "wake": True})
        with mock.patch.dict(os.environ, {"REASON_NETWORK_HOME": str(self.root / "reason")}):
            self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_called_once_with([second_id])
        self.assertEqual(len(self.tasks()), 1)
        self.assertIn("independent request", self.tasks()[0]["body"])

    def test_deferred_reason_attachments_do_not_starve_later_messages(self):
        self.enabled()
        sample = self.reason.inbox.return_value["messages"][0]
        blocked = [{**sample, "id": f"blocked_{i:020d}", "files": [
            {"name": "missing.txt", "path": str(self.root / "missing.txt"), "content": ""}]}
            for i in range(20)]
        later = {**sample, "id": "later_00000000000000000001", "body": "later valid request"}
        self.reason.inbox.return_value["messages"] = blocked + [later]
        self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_called_once_with([later["id"]])
        self.assertEqual(len(self.tasks()), 1)
        self.assertIn("later valid request", self.tasks()[0]["body"])

    def test_started_attachment_tasks_do_not_starve_later_requests(self):
        self.enabled()
        inbox = self.root / "reason" / "inbox" / "fixture"
        inbox.mkdir(parents=True)
        attachment = inbox / "brief.txt"
        attachment.write_text("brief", encoding="utf-8")
        sample = self.reason.inbox.return_value["messages"][0]
        blocked = [{**sample, "id": f"working_{i:020d}", "files": [
            {"name": "brief.txt", "path": str(attachment), "content": ""}]}
            for i in range(20)]
        with self.runtime.connect() as database:
            for message in blocked:
                self.runtime.insert_task(database, "reason:" + message["id"], "codex", "old body")
            database.execute("UPDATE tasks SET status='working'")
        later = {**sample, "id": "later_00000000000000000001", "body": "later valid request"}
        self.reason.inbox.return_value["messages"] = blocked + [later]
        with mock.patch.dict(os.environ, {"REASON_NETWORK_HOME": str(self.root / "reason")}):
            self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_called_once_with([later["id"]])

    def test_reason_attachment_replay_is_idempotent_after_ack_failure(self):
        self.enabled()
        inbox = self.root / "reason" / "inbox" / "fixture"
        inbox.mkdir(parents=True)
        attachment = inbox / "brief.txt"
        attachment.write_text("keep the full brief", encoding="utf-8")
        self.reason.inbox.return_value["messages"][0]["files"] = [
            {"name": "brief.txt", "path": str(attachment), "content": ""}]
        self.reason.ack.side_effect = hq.HQError("ack unavailable")
        with mock.patch.dict(os.environ, {"REASON_NETWORK_HOME": str(self.root / "reason")}):
            self.assertFalse(self.runtime.receive()["ok"])
            attachment.unlink()
            self.reason.ack.side_effect = None
            self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(len(self.tasks()), 1)
        self.assertIn("keep the full brief", self.tasks()[0]["body"])

    def test_reason_attachment_replay_upgrades_preexisting_task_before_ack(self):
        self.enabled()
        with self.runtime.connect() as database:
            self.runtime.insert_task(database, "reason:" + self.message_id, "codex", "old body")
        inbox = self.root / "reason" / "inbox" / "fixture"
        inbox.mkdir(parents=True)
        attachment = inbox / "brief.txt"
        attachment.write_text("previously omitted attachment", encoding="utf-8")
        self.reason.inbox.return_value["messages"][0]["files"] = [
            {"name": "brief.txt", "path": str(attachment), "content": ""}]
        with mock.patch.dict(os.environ, {"REASON_NETWORK_HOME": str(self.root / "reason")}):
            self.assertTrue(self.runtime.receive()["ok"])
            self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(len(self.tasks()), 1)
        self.assertEqual(self.tasks()[0]["body"].count("previously omitted attachment"), 1)

    def test_reason_attachment_upgrades_previous_fyi_before_ack(self):
        self.enabled()
        with self.runtime.connect() as database:
            database.execute("INSERT INTO meta VALUES (?,?)", ("reason_fyi:" + self.message_id,
                             json.dumps({"sender": "daisuke/muse@remote", "body": "old body"})))
        inbox = self.root / "reason" / "inbox" / "fixture"
        inbox.mkdir(parents=True)
        attachment = inbox / "brief.txt"
        attachment.write_text("fyi attachment", encoding="utf-8")
        message = self.reason.inbox.return_value["messages"][0]
        message.update(wake=False, files=[{"name": "brief.txt", "path": str(attachment), "content": ""}])
        with mock.patch.dict(os.environ, {"REASON_NETWORK_HOME": str(self.root / "reason")}):
            self.assertTrue(self.runtime.receive()["ok"])
            self.assertTrue(self.runtime.receive()["ok"])
        with self.runtime.connect() as database:
            row = database.execute("SELECT value FROM meta WHERE key=?",
                                   ("reason_fyi:" + self.message_id,)).fetchone()
        self.assertEqual(json.loads(row[0])["body"].count("fyi attachment"), 1)

    def test_unavailable_attachment_remains_unacked_if_provider_drops_files(self):
        self.enabled()
        message = self.reason.inbox.return_value["messages"][0]
        message["files"] = [{"name": "lost.txt", "path": str(self.root / "missing.txt"), "content": ""}]
        self.assertFalse(self.runtime.receive()["ok"])
        message["files"] = []
        self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_not_called()
        self.assertEqual(self.tasks(), [])

    def test_attachment_for_existing_working_task_remains_unacked(self):
        self.enabled()
        with self.runtime.connect() as database:
            self.runtime.insert_task(database, "reason:" + self.message_id, "codex", "old body")
            database.execute("UPDATE tasks SET status='working'")
        inbox = self.root / "reason" / "inbox" / "fixture"
        inbox.mkdir(parents=True)
        attachment = inbox / "brief.txt"
        attachment.write_text("worker cannot see this", encoding="utf-8")
        self.reason.inbox.return_value["messages"][0]["files"] = [
            {"name": "brief.txt", "path": str(attachment), "content": ""}]
        with mock.patch.dict(os.environ, {"REASON_NETWORK_HOME": str(self.root / "reason")}):
            self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_not_called()

    def test_reason_rejects_attachment_outside_inbox_or_through_symlink(self):
        for kind in ("outside", "symlink"):
            with self.subTest(kind=kind):
                self.enabled()
                inbox = self.root / "reason" / "inbox" / "fixture"
                inbox.mkdir(parents=True, exist_ok=True)
                target = self.root / "private.txt"
                target.write_text("must not be read", encoding="utf-8")
                path = target
                if kind == "symlink":
                    path = inbox / "link.txt"
                    path.symlink_to(target)
                self.reason.inbox.return_value["messages"][0]["files"] = [
                    {"name": "file.txt", "path": str(path), "content": ""}]
                with mock.patch.dict(os.environ, {"REASON_NETWORK_HOME": str(self.root / "reason")}):
                    self.assertFalse(self.runtime.receive()["ok"])
                self.reason.ack.assert_not_called()
                self.assertEqual(self.tasks(), [])

    def test_paged_reason_cursor_is_committed_before_ack_and_reused(self):
        self.enabled()
        self.runtime.reason_config["page_enabled"] = True
        cursor = {"version": 1, "mailbox": "daisuke/hq-codex",
                  "after": [1, self.message_id], "through": [2, "next-message-0001"]}
        self.reason.inbox.return_value.update(next_cursor=cursor, holds=[])
        def ack(ids):
            with self.runtime.connect() as database:
                row = database.execute("SELECT value FROM meta WHERE key='reason_page_cursor'").fetchone()
            self.assertEqual(json.loads(row[0]), cursor)
        self.reason.ack.side_effect = ack
        self.assertTrue(self.runtime.receive()["ok"])
        self.reason.inbox.assert_called_with(paged=True, cursor=None)
        self.reason.ack.side_effect = None
        self.reason.inbox.return_value.update(messages=[], next_cursor=None)
        self.assertTrue(self.runtime.receive()["ok"])
        self.reason.inbox.assert_called_with(paged=True, cursor=cursor)
        with self.runtime.connect() as database:
            self.assertIsNone(database.execute("SELECT 1 FROM meta WHERE key='reason_page_cursor'").fetchone())

    def test_paged_reason_oversize_hold_is_durable_and_never_acked(self):
        self.enabled()
        self.runtime.reason_config["page_enabled"] = True
        held_id = "held_message_0000000000001"
        cursor = {"version": 1, "mailbox": "daisuke/hq-codex",
                  "after": [1, held_id], "through": [2, "next-message-0001"]}
        self.reason.inbox.return_value.update(messages=[], next_cursor=cursor,
            holds=[{"id": held_id, "sent_at": 1, "reason": "message_too_large", "has_files": False}])
        result = self.runtime.receive()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason_error"], "reason_page_hold")
        self.reason.ack.assert_not_called()
        with self.runtime.connect() as database:
            hold = database.execute("SELECT value FROM meta WHERE key=?", ("reason_page_hold:" + held_id,)).fetchone()
            saved = database.execute("SELECT value FROM meta WHERE key='reason_page_cursor'").fetchone()
        self.assertEqual(json.loads(hold[0])["reason"], "message_too_large")
        self.assertEqual(json.loads(saved[0]), cursor)

    def test_paged_reason_reports_saved_hold_until_message_is_recovered(self):
        self.enabled()
        self.runtime.reason_config["page_enabled"] = True
        held_id = self.message_id
        hold = {"id": held_id, "sent_at": 1, "reason": "message_too_large", "has_files": False}
        self.reason.inbox.return_value.update(messages=[], next_cursor=None, holds=[hold])
        self.assertFalse(self.runtime.receive()["ok"])
        self.reason.inbox.return_value.update(messages=[], holds=[])
        self.assertFalse(self.runtime.receive()["ok"])
        self.reason.inbox.return_value.update(messages=[{"id": held_id, "from": "daisuke/muse@remote",
            "body": "recovered body", "to": "daisuke/hq-codex"}], holds=[])
        self.assertTrue(self.runtime.receive()["ok"])
        with self.runtime.connect() as database:
            self.assertIsNone(database.execute("SELECT 1 FROM meta WHERE key=?", ("reason_page_hold:" + held_id,)).fetchone())
        self.reason.ack.assert_called_once_with([held_id])

    def test_paged_reason_held_attachment_disappearance_is_not_acked(self):
        self.enabled()
        self.runtime.reason_config["page_enabled"] = True
        held_id = self.message_id
        hold = {"id": held_id, "sent_at": 1, "reason": "message_too_large", "has_files": True}
        self.reason.inbox.return_value.update(messages=[], next_cursor=None, holds=[hold])
        self.assertFalse(self.runtime.receive()["ok"])
        self.reason.inbox.return_value.update(messages=[{"id": held_id, "from": "daisuke/muse@remote",
            "body": "body after attachment expiry", "to": "daisuke/hq-codex", "files": []}], holds=[])
        self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_not_called()
        with self.runtime.connect() as database:
            self.assertIsNotNone(database.execute("SELECT 1 FROM meta WHERE key=?", ("reason_page_hold:" + held_id,)).fetchone())
            self.assertIsNotNone(database.execute("SELECT 1 FROM meta WHERE key=?", ("reason_attachment_pending:" + held_id,)).fetchone())

    def test_paged_reason_failure_does_not_advance_cursor_or_ack(self):
        self.enabled()
        self.runtime.reason_config["page_enabled"] = True
        cursor = {"version": 1, "mailbox": "daisuke/hq-codex",
                  "after": [1, self.message_id], "through": [2, "next-message-0001"]}
        self.reason.inbox.return_value.update(next_cursor=cursor, holds=[])
        with mock.patch.object(self.runtime, "insert_task", side_effect=OSError("disk full")) as insert:
            self.assertFalse(self.runtime.receive()["ok"])
        insert.assert_called_once()
        self.reason.ack.assert_not_called()
        with self.runtime.connect() as database:
            self.assertIsNone(database.execute("SELECT 1 FROM meta WHERE key='reason_page_cursor'").fetchone())

    def test_reason_queue_failure_never_acknowledges(self):
        self.enabled()
        with mock.patch.object(self.runtime, "insert_task", side_effect=OSError("disk full")):
            self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_not_called()
        self.assertEqual(self.tasks(), [])

    def test_paged_reason_real_sqlite_full_rolls_back_cursor_and_replays_once(self):
        self.enabled()
        self.runtime.reason_config["page_enabled"] = True
        cursor = {"version": 1, "mailbox": "daisuke/hq-codex",
                  "after": [1, self.message_id], "through": [2, "next-message-0001"]}
        self.reason.inbox.return_value.update(next_cursor=cursor, holds=[])
        self.reason.inbox.return_value["messages"][0]["body"] = "x" * 65536
        connect = self.runtime.connect
        @contextmanager
        def full_database():
            with connect() as database:
                pages = database.execute("PRAGMA page_count").fetchone()[0]
                database.execute(f"PRAGMA max_page_count={pages}")
                yield database
        with mock.patch.object(self.runtime, "connect", side_effect=full_database):
            self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_not_called()
        self.assertEqual(self.tasks(), [])
        with connect() as database:
            self.assertIsNone(database.execute("SELECT 1 FROM meta WHERE key='reason_page_cursor'").fetchone())
        self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(len(self.tasks()), 1)
        self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(len(self.tasks()), 1)

    def test_real_sqlite_full_does_not_ack_and_replay_creates_one_task(self):
        self.enabled()
        self.reason.inbox.return_value["messages"][0]["body"] = "x" * (1024 * 1024)
        connect = self.runtime.connect
        @contextmanager
        def full_database():
            with connect() as database:
                pages = database.execute("PRAGMA page_count").fetchone()[0]
                database.execute(f"PRAGMA max_page_count={pages}")
                yield database
        with mock.patch.object(self.runtime, "connect", side_effect=full_database):
            self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_not_called()
        self.assertEqual(self.tasks(), [])
        self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(len(self.tasks()), 1)
        self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(len(self.tasks()), 1)

    def test_reason_wrong_session_never_acknowledges(self):
        self.enabled()
        self.reason.inbox.return_value["session_key"] = "cli:someone-else"
        self.assertFalse(self.runtime.receive()["ok"])
        self.reason.ack.assert_not_called()
        self.assertEqual(self.tasks(), [])

    def test_reason_failure_does_not_stop_slack_receive(self):
        self.enabled()
        self.reason.inbox.side_effect = hq.HQError("transport unavailable")
        self.slack.history[""]["messages"] = [HQTests.message(self)]
        result = self.runtime.receive()
        self.assertFalse(result["ok"])
        self.assertEqual(len(self.tasks()), 1)
        self.assertTrue(self.tasks()[0]["source_key"].startswith("slack:"))

    def test_reason_receipt_is_sent_without_starting_the_model(self):
        self.enabled()
        self.runtime.receive()
        self.assertEqual(self.tasks()[0]["status"], "queued")
        self.reason.send.assert_called_once()
        notice = self.reason.send.call_args.kwargs
        self.assertEqual(notice["to"], "daisuke/muse@remote")
        self.assertEqual(notice["reply_to"], self.message_id)
        self.assertIn("受領", notice["body"])
        self.assertIn("キューへ保存", notice["body"])
        self.assertTrue(notice["key"].endswith(":received"))

    def test_reason_receipt_timeout_reuses_the_durable_idempotency_key(self):
        self.enabled()
        self.reason.send.side_effect = hq.HQError("response lost")
        self.assertFalse(self.runtime.receive()["ok"])
        first = dict(self.reason.send.call_args.kwargs)
        self.reason.inbox.return_value["messages"] = []
        self.reason.send.side_effect = None
        self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(self.reason.send.call_args.kwargs, first)
        self.assertEqual(len(self.tasks()), 1)

    def test_reason_fyi_is_saved_without_a_reply_or_new_work(self):
        self.enabled()
        self.reason.inbox.return_value["messages"][0]["wake"] = False
        self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(self.tasks(), [])
        self.reason.send.assert_not_called()
        self.reason.ack.assert_called_once()
        with self.runtime.connect() as database:
            note = database.execute("SELECT value FROM meta WHERE key=?", ("reason_fyi:" + self.message_id,)).fetchone()
        self.assertIn("read-only canary", note[0])

    def test_reason_result_is_returned_to_its_original_sender(self):
        self.enabled()
        self.runtime.receive()
        self.assertTrue(self.runtime.work()["ok"])
        result = [x.kwargs for x in self.reason.send.call_args_list if x.kwargs["key"].endswith(":result")]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["reply_to"], self.message_id)
        self.assertIn("worked", result[0]["body"])

    def test_reason_start_notice_follows_the_actual_queue_claim(self):
        self.enabled()
        def send(**notice):
            if notice["key"].endswith(":started"):
                self.assertEqual(self.tasks()[0]["status"], "working")
            return {"ids": ["01M6G11XSHQTVE7JPSSAEE34JA"], "recipients": [{"address":"daisuke/muse@remote", "state":"queued"}]}
        self.reason.send.side_effect = send
        self.runtime.receive()
        self.runtime.work()
        self.assertTrue(any(x.kwargs["key"].endswith(":started") for x in self.reason.send.call_args_list))

    def test_reason_result_retry_does_not_execute_the_work_again(self):
        self.enabled()
        def send(**notice):
            if notice["key"].endswith(":result"):
                raise hq.HQError("lost reply receipt")
            return {"ids": ["01M6G11XSHQTVE7JPSSAEE34JA"], "recipients": [{"address":"daisuke/muse@remote", "state":"queued"}]}
        self.reason.send.side_effect = send
        self.runtime.receive()
        self.assertFalse(self.runtime.work()["ok"])
        task = self.tasks()[0]
        result_path = self.runtime.task_directory(task) / "result.json"
        original = result_path.read_bytes()
        self.reason.send.side_effect = None
        self.assertTrue(self.runtime.work()["ok"])
        self.assertEqual(result_path.read_bytes(), original)
        results = [x.kwargs for x in self.reason.send.call_args_list if x.kwargs["key"].endswith(":result")]
        self.assertEqual(results[0], results[1])

    def test_reason_pending_receipt_can_be_completed_by_the_next_receive(self):
        self.enabled()
        self.reason.send.side_effect = hq.HQError("temporarily unavailable")
        self.runtime.receive()
        self.reason.inbox.return_value["messages"] = []
        self.reason.send.side_effect = None
        self.assertTrue(self.runtime.receive()["ok"])
        self.assertEqual(self.tasks()[0]["status"], "queued")

    def test_receive_records_native_receipts_before_slack_failure(self):
        self.enabled()
        path = self.root / "receive-hint.json"
        self.slack.error = True
        with mock.patch.dict(os.environ, {"LIFE_MANAGER_RESULT_HINT_PATH":str(path),
                 "LIFE_MANAGER_LOOP_ID":"team-hq-receive", "LIFE_MANAGER_OCCURRENCE_ID":"occ-1"}):
            with self.assertRaises(hq.HQError):
                self.runtime.receive()
        value=json.loads(path.read_text())
        self.assertEqual(value["kind"], "team_hq_reason_receive_result")
        self.assertEqual(value["status"], "verified")
        self.assertEqual(value["message_ids"], self.reason.send.return_value["ids"])

    def test_receive_cannot_claim_no_effect_after_lost_reply(self):
        self.enabled()
        self.reason.send.side_effect=hq.HQError("lost response")
        path=self.root / "receive-hint.json"
        path.write_text("stale hint")
        with mock.patch.dict(os.environ, {"LIFE_MANAGER_RESULT_HINT_PATH":str(path)}):
            self.assertFalse(self.runtime.receive()["ok"])
        self.assertFalse(path.exists())

    def test_reason_refusal_or_missing_recipient_is_not_posted(self):
        self.enabled()
        for recipients in [[],
                           [{"address":"daisuke/other@remote","state":"queued"}],
                           [{"address":"daisuke/muse@remote","state":"unknown"}]]:
            with self.subTest(recipients=recipients):
                self.reason.send.return_value={"ids":["01M6G11XSHQTVE7JPSSAEE34JA"], "recipients":recipients}
                self.assertFalse(self.runtime.receive()["ok"])
                with self.runtime.connect() as db:
                    notice=json.loads(db.execute("SELECT value FROM meta WHERE key LIKE 'reason_outbox:%:received'").fetchone()[0])
                self.assertEqual(notice["state"], "pending")

    def test_reason_result_is_sent_even_if_slack_final_post_is_rejected(self):
        self.enabled();self.runtime.receive()
        original=self.slack.call
        def call(method, **parameters):
            if method == "chat.postMessage" and not parameters["text"].endswith(":start"):
                return {"ok":False,"error":"thread_not_found"}
            return original(method, **parameters)
        with mock.patch.object(self.slack,"call",side_effect=call):
            self.assertFalse(self.runtime.work()["ok"])
        result=[c.kwargs for c in self.reason.send.call_args_list if c.kwargs["key"].endswith(":result")]
        self.assertEqual(len(result),1)
        self.assertIn("worked",result[0]["body"])
        self.assertEqual(self.tasks()[0]["reply_state"],"delivery_failed")

    def test_reason_result_is_sent_even_if_slack_start_is_unknown(self):
        self.enabled();self.runtime.receive();self.slack.hide_posts=True
        self.assertFalse(self.runtime.work()["ok"])
        result=[c.kwargs for c in self.reason.send.call_args_list if c.kwargs["key"].endswith(":result")]
        self.assertEqual(len(result),1)
        self.assertIn("worked",result[0]["body"])

    def test_reason_durable_accepted_recovery_is_not_resent(self):
        self.enabled()
        self.reason.send.return_value["recipients"][0]["state"]="accepted"
        self.assertTrue(self.runtime.receive()["ok"])
        self.assertTrue(self.runtime.receive()["ok"])
        self.reason.send.assert_called_once()

    def test_one_native_refusal_does_not_starve_another_recipient(self):
        self.enabled()
        other=dict(self.reason.inbox.return_value["messages"][0],
                   id="01M6G11XSHQTVE7JPSSAEE34JA", **{"from":"daisuke/dots-one"})
        self.reason.inbox.return_value["messages"].append(other)
        def send(**notice):
            state="refused" if notice["to"]=="daisuke/muse@remote" else "queued"
            return {"ids":["01M6G11XSHQTVE7JPSSAEE34JA"],
                    "recipients":[{"address":notice["to"],"state":state}]}
        self.reason.send.side_effect=send
        self.assertFalse(self.runtime.receive()["ok"])
        with self.runtime.connect() as db:
            notices=[json.loads(row[0]) for row in db.execute("SELECT value FROM meta WHERE key LIKE 'reason_outbox:%:received'")]
        self.assertEqual({n["to"]:n["state"] for n in notices},
                         {"daisuke/muse@remote":"refused", "daisuke/dots-one":"posted"})
        self.runtime.receive()
        self.assertEqual(self.reason.send.call_count,2)

    def test_late_received_notice_does_not_claim_completed_work_is_unstarted(self):
        self.enabled()
        self.reason.ack.side_effect=lambda ids:self.runtime.work()
        self.runtime.receive()
        self.assertEqual(self.tasks()[0]["status"], "succeeded")
        received=[c.kwargs["body"] for c in self.reason.send.call_args_list if c.kwargs["key"].endswith(":received")]
        self.assertEqual(len(received),1)
        self.assertNotIn("未着手",received[0])
