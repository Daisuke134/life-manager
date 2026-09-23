import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "x_post_cli.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("affiliate_x_post", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class XPostContractTest(unittest.TestCase):
    def test_disclosure_owned_url_and_stable_placement_are_required(self):
        text = "My notes on voice workflows. Affiliate link: https://aniccaai.com/blog/voice-workflows"
        self.assertEqual(MODULE.validate_content(text), text)
        self.assertEqual(MODULE.content_fingerprint(text), MODULE.content_fingerprint(text))
        with tempfile.TemporaryDirectory() as root:
            expected = Path(root) / "x-posts" / "elevenlabs-en-1.json"
            self.assertEqual(MODULE.placement_path(Path(root), "elevenlabs-en-1"), expected)
        with self.assertRaises(MODULE.XPostError):
            MODULE.validate_content("Read https://aniccaai.com/blog/voice-workflows")
        with self.assertRaises(MODULE.XPostError):
            MODULE.validate_content("#ad https://example.com/not-owned")

    def test_live_owned_article_receipt_is_required(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            with self.assertRaises(MODULE.XPostError):
                MODULE.require_live_owned_article(state, text)
            path = state / "owned-publications" / "voice-workflows.json"
            path.parent.mkdir()
            path.write_text(json.dumps({
                "state": "LIVE",
                "public_url": "https://aniccaai.com/blog/voice-workflows",
            }))
            self.assertIsNone(MODULE.require_live_owned_article(state, text))

    def test_x_short_url_is_reconciled_to_owned_article(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        rows = [{
            "text": "Affiliate link: https://\naniccaai.com/blog/voice-work…",
            "url": "https://x.com/selawmqt/status/123",
            "outbound": ["https://t.co/unit"],
        }]
        self.assertEqual(
            MODULE.find_exact(rows, text, resolver=lambda _: "https://aniccaai.com/blog/voice-workflows"),
            "https://x.com/selawmqt/status/123",
        )
        self.assertEqual(MODULE.find_exact(rows, text, resolver=lambda _: "https://example.com/wrong"), "")

    def test_exact_visible_owned_url_does_not_call_network_resolver(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        rows = [{
            "text": "Affiliate link: ",
            "url": "https://x.com/selawmqt/status/123",
            "outbound": ["https://t.co/unit"],
            "outbound_text": ["https://aniccaai.com/blog/voice-workflows"],
        }]
        resolver = Mock(side_effect=AssertionError("network resolver must stay unused"))
        self.assertEqual(
            MODULE.find_exact(rows, text, resolver=resolver),
            "https://x.com/selawmqt/status/123",
        )
        resolver.assert_not_called()

    def test_linked_disclosure_and_one_owned_cta_are_an_exact_post(self):
        text = "#ad Affiliate link: https://aniccaai.com/blog/voice-workflows"
        rows = [{
            "text": "#ad Affiliate link: ",
            "url": "https://x.com/selawmqt/status/123",
            "outbound": [
                "https://x.com/hashtag/ad",
                "https://t.co/unit",
            ],
            "outbound_text": [
                "#ad",
                "https://aniccaai.com/blog/voice-workflows",
            ],
        }]
        resolver = Mock(side_effect=AssertionError("visible owned CTA avoids resolution"))
        self.assertEqual(
            MODULE.find_exact(rows, text, resolver=resolver),
            "https://x.com/selawmqt/status/123",
        )
        resolver.assert_not_called()

    def test_non_cta_anchor_cannot_stand_in_for_owned_cta_text(self):
        text = "#ad Affiliate link: https://aniccaai.com/blog/voice-workflows"
        rows = [{
            "text": "#ad Affiliate link: @someone",
            "url": "https://x.com/selawmqt/status/123",
            "outbound": [
                "https://x.com/hashtag/ad",
                "https://x.com/someone",
                "https://t.co/unit",
            ],
            "outbound_text": [
                "#ad",
                "@someone",
                "https://aniccaai.com/blog/voice-workflows",
            ],
        }]
        self.assertEqual(MODULE.find_exact(rows, text), "")

    def test_same_cta_with_additional_copy_is_not_an_exact_post(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        rows = [{
            "text": "Affiliate link: Extra offer https://aniccaai.com/blog/voice-workflows",
            "url": "https://x.com/selawmqt/status/123",
            "outbound": ["https://aniccaai.com/blog/voice-workflows"],
            "outbound_text": ["https://aniccaai.com/blog/voice-workflows"],
        }]
        self.assertEqual(MODULE.find_exact(rows, text), "")

    def test_same_cta_with_trailing_copy_is_not_an_exact_post(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        rows = [{
            "text": "Affiliate link: https://aniccaai.com/blog/voice-workflows Extra offer",
            "url": "https://x.com/selawmqt/status/123",
            "outbound": ["https://aniccaai.com/blog/voice-workflows"],
            "outbound_text": ["https://aniccaai.com/blog/voice-workflows"],
        }]
        self.assertEqual(MODULE.find_exact(rows, text), "")

    def test_public_ssr_profile_reconciles_exact_owned_post(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        markup = '''
        <article data-tweet-id="123">
          <span>Affiliate link: </span>
          <a href="https://aniccaai.com/blog/voice-workflows">aniccaai.com/blog/voice…</a>
        </article>
        <article data-tweet-id="456">
          <span>Affiliate link: </span>
          <a href="https://aniccaai.com/blog/wrong">wrong</a>
        </article>
        '''
        self.assertEqual(
            MODULE.find_exact_public_markup(markup, text, "selawmqt"),
            "https://x.com/selawmqt/status/123",
        )

    def test_public_ssr_profile_rejects_same_cta_with_extra_copy(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        markup = '''
        <article data-tweet-id="123">
          <span>Affiliate link: </span>
          <a href="https://aniccaai.com/blog/voice-workflows">aniccaai.com/blog/voice…</a>
          <span> Extra offer</span>
        </article>
        '''
        self.assertEqual(MODULE.find_exact_public_markup(markup, text, "selawmqt"), "")

    def test_timeline_readback_waits_for_exact_pending_post(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        row = {
            "text": "Affiliate link: ",
            "url": "https://x.com/selawmqt/status/123",
            "outbound": ["https://aniccaai.com/blog/voice-workflows"],
        }
        sleeper = Mock()
        with patch.object(
            MODULE, "timeline_posts",
            side_effect=[([], 2), ([], 3), ([row], 4)],
        ) as timeline:
            public_url, rows, request_id = MODULE.wait_for_exact_timeline(
                object(), 1, text, attempts=3, delay=0.01, sleeper=sleeper,
            )
        self.assertEqual(public_url, "https://x.com/selawmqt/status/123")
        self.assertEqual(rows, [row])
        self.assertEqual(request_id, 4)
        self.assertEqual(timeline.call_count, 3)
        self.assertEqual(sleeper.call_count, 2)

    def test_timeline_readback_is_bounded_when_post_is_absent(self):
        sleeper = Mock()
        with patch.object(
            MODULE, "timeline_posts", side_effect=[([], 2), ([], 3)],
        ) as timeline:
            public_url, rows, request_id = MODULE.wait_for_exact_timeline(
                object(), 1,
                "Affiliate link: https://aniccaai.com/blog/voice-workflows",
                attempts=2, delay=0.01, sleeper=sleeper,
            )
        self.assertEqual((public_url, rows, request_id), ("", [], 3))
        self.assertEqual(timeline.call_count, 2)
        self.assertEqual(sleeper.call_count, 1)

    def test_publish_waits_for_delayed_exact_post_after_submit(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        public_url = "https://x.com/selawmqt/status/123"
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            content = state / "content.txt"
            content.write_text(text)
            receipt = state / "owned-publications" / "voice-workflows.json"
            receipt.parent.mkdir()
            receipt.write_text(json.dumps({
                "state": "LIVE",
                "public_url": "https://aniccaai.com/blog/voice-workflows",
            }))
            websocket = Mock()
            effect_job = {
                "run_id": "run-1",
                "job_id": "job-1",
                "attempt": 1,
                "action_fingerprint": "a" * 64,
                "cooldown": {"seconds": 3600, "until": None},
                "last_verified_external_object": {"state": "NOT_FOUND"},
            }
            with (
                patch.object(MODULE, "load_config", return_value={"handle": "selawmqt"}),
                patch.object(MODULE, "inspect", return_value={"handle": "selawmqt"}),
                patch.object(MODULE, "choose_x_target", return_value={}),
                patch.object(MODULE, "connect", return_value=websocket),
                patch.object(MODULE, "navigate", side_effect=lambda _ws, request_id, _url: request_id + 2),
                patch.object(
                    MODULE, "wait_for_exact_timeline",
                    side_effect=[("", [], 4), (public_url, [{"url": public_url}], 20)],
                ),
                patch.object(MODULE, "public_profile_readback", return_value=""),
                patch.object(MODULE, "unresolved_effect", return_value=None),
                patch.object(MODULE, "start_effect", return_value=effect_job),
                patch.object(MODULE, "query_node", return_value=(7, 8)),
                patch.object(MODULE, "cdp_call"),
                patch.object(MODULE, "click"),
                patch.object(MODULE.time, "sleep"),
                patch.object(MODULE, "timeline_posts", return_value=([], 20)),
                patch.object(MODULE, "live_readback", return_value=21),
                patch.object(MODULE, "verify_effect"),
            ):
                result = MODULE.publish(Namespace(
                    content=content,
                    state=state,
                    placement="voice-workflows-x",
                    cdp_host="127.0.0.1",
                    cdp_port=9326,
                ))

            self.assertEqual(result["state"], "LIVE")
            self.assertEqual(result["public_url"], public_url)
            websocket.close.assert_called_once_with()

    def test_pending_effect_never_clicks_post_again(self):
        text = "Affiliate link: https://aniccaai.com/blog/voice-workflows"
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            content = state / "content.txt"
            content.write_text(text)
            receipt = state / "owned-publications" / "voice-workflows.json"
            receipt.parent.mkdir()
            receipt.write_text(json.dumps({
                "state": "LIVE",
                "public_url": "https://aniccaai.com/blog/voice-workflows",
            }))
            websocket = Mock()
            pending = {
                "run_id": "run-1",
                "job_id": "a" * 64,
                "attempt": 1,
                "action_fingerprint": "b" * 64,
                "cooldown": {"seconds": 0, "until": None},
                "last_verified_external_object": {"state": "NOT_FOUND"},
                "updated_at": 0,
            }
            click = Mock()
            start = Mock(return_value=pending)
            with (
                patch.object(MODULE, "load_config", return_value={"handle": "selawmqt"}),
                patch.object(MODULE, "inspect", return_value={"handle": "selawmqt"}),
                patch.object(MODULE, "choose_x_target", return_value={}),
                patch.object(MODULE, "connect", return_value=websocket),
                patch.object(MODULE, "navigate", side_effect=lambda _ws, request_id, _url: request_id + 2),
                patch.object(
                    MODULE, "wait_for_exact_timeline",
                    side_effect=[("", [], 4), ("", [], 20)],
                ),
                patch.object(MODULE, "public_profile_readback", return_value=""),
                patch.object(MODULE, "unresolved_effect", return_value=pending),
                patch.object(MODULE, "start_effect", start),
                patch.object(MODULE, "atomic_write"),
                patch.object(MODULE, "query_node", return_value=(7, 8)),
                patch.object(MODULE, "cdp_call"),
                patch.object(MODULE, "click", click),
                patch.object(MODULE.time, "sleep"),
            ):
                with self.assertRaises(MODULE.XPostError):
                    MODULE.publish(Namespace(
                        content=content,
                        state=state,
                        placement="voice-workflows-x",
                        cdp_host="127.0.0.1",
                        cdp_port=9326,
                    ))

            click.assert_not_called()
            start.assert_not_called()
            websocket.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
