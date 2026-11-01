import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import x_engage  # noqa: E402

URL = "https://x.com/someone/status/1234567890"
QUEUE = f"""# X queue
- [ ] some Postiz post item that must be ignored

## Engagement for Mac mini
- [ ] like {URL}
- [x] like {URL} → {URL} (2026-11-01 10:00 JST)
- [ ] repost {URL}

- [ ] reply {URL} :: ありがとうございます！

## Other section
- [ ] anything here is ignored
"""


def args_for(tmp, **extra):
    base = dict(queue=str(Path(tmp) / "q.md"), state=str(Path(tmp) / "s"),
                cdp_host="127.0.0.1", cdp_port=1, handle="selawmqt",
                dry_run=False, max_actions=0)
    base.update(extra)
    return SimpleNamespace(**base)


class ParseTest(unittest.TestCase):
    def test_parses_only_unchecked_lines_in_section(self):
        actions, error = x_engage.parse_section(QUEUE)
        self.assertIsNone(error)
        self.assertEqual([a[1] for a in actions], ["like", "repost", "reply"])
        self.assertEqual(actions[2][3], "ありがとうございます！")

    def test_missing_section_means_nothing(self):
        self.assertEqual(x_engage.parse_section("# q\n- [ ] like " + URL), ([], None))

    def test_unrecognized_lines_fail_closed(self):
        for bad in ("- [ ] post hello world", f"- [ ] quote {URL}", f"- [ ] like {URL} extra",
                    "- [ ] like https://evil.example/status/1", f"- [ ] reply {URL}",
                    "random note", f"- [ ] Like {URL}"):
            actions, error = x_engage.parse_section(f"## Engagement for Mac mini\n- [ ] like {URL}\n{bad}\n")
            self.assertEqual(actions, [], bad)
            self.assertIsNotNone(error, bad)

    def test_overlong_reply_fails_closed(self):
        _, error = x_engage.parse_section(f"## Engagement for Mac mini\n- [ ] reply {URL} :: {'a' * 281}\n")
        self.assertIsNotNone(error)


class RunTest(unittest.TestCase):
    def test_disabled_without_exact_flag_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "q.md").write_text(QUEUE)
            with patch.dict(os.environ, {"AFFILIATE_X_ENGAGE_ENABLED": "true"}), \
                    patch.object(x_engage, "Browser") as browser:
                self.assertEqual(x_engage.run(args_for(tmp)), 0)
            browser.assert_not_called()
            self.assertEqual(Path(tmp, "q.md").read_text(), QUEUE)

    def test_dry_run_never_opens_browser_or_edits_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "q.md").write_text(QUEUE)
            with patch.object(x_engage, "Browser") as browser:
                self.assertEqual(x_engage.run(args_for(tmp, dry_run=True)), 0)
            browser.assert_not_called()
            self.assertEqual(Path(tmp, "q.md").read_text(), QUEUE)

    def test_fail_closed_run_takes_no_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "q.md").write_text(QUEUE.replace("- [ ] repost", "- [ ] post"))
            with patch.dict(os.environ, {"AFFILIATE_X_ENGAGE_ENABLED": "1"}), \
                    patch.object(x_engage, "Browser") as browser:
                self.assertEqual(x_engage.run(args_for(tmp)), 2)
            browser.assert_not_called()

    def test_actions_mark_lines_and_respect_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "q.md").write_text(QUEUE)
            Path(tmp, "s").mkdir()
            Path(tmp, "s", "counters.json").write_text(json.dumps(
                {"day": x_engage.today(), "like": 0, "repost": 10, "reply": 0}))
            with patch.dict(os.environ, {"AFFILIATE_X_ENGAGE_ENABLED": "1"}), \
                    patch.object(x_engage, "Browser"), \
                    patch.object(x_engage, "do_like", return_value=URL) as like, \
                    patch.object(x_engage, "do_repost") as repost, \
                    patch.object(x_engage, "do_reply", return_value="https://x.com/selawmqt/status/9") as reply:
                self.assertEqual(x_engage.run(args_for(tmp)), 0)
            like.assert_called_once()
            repost.assert_not_called()  # cap reached
            reply.assert_called_once()
            self.assertEqual(reply.call_args.args[2], "ありがとうございます！")
            text = Path(tmp, "q.md").read_text()
            self.assertIn(f"- [x] like {URL} → {URL} (", text)
            self.assertIn(f"- [ ] repost {URL}", text)
            self.assertIn("→ https://x.com/selawmqt/status/9 (", text)
            self.assertIn("- [ ] some Postiz post item", text)
            counters = json.loads(Path(tmp, "s", "counters.json").read_text())
            self.assertEqual((counters["like"], counters["reply"]), (1, 1))

    def test_counters_reset_on_new_jst_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "c.json")
            path.write_text(json.dumps({"day": "2000-01-01", "like": 30, "repost": 10, "reply": 10}))
            self.assertEqual(x_engage.load_counters(path)["like"], 0)


if __name__ == "__main__":
    unittest.main()
