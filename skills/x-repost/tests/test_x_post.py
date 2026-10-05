from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "x_post.py"
SPEC = importlib.util.spec_from_file_location("x_post", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Node:
    def __init__(self, *, text: str = "", href: str = "") -> None:
        self.text, self.href = text, href

    def inner_text(self) -> str:
        return self.text

    def get_attribute(self, name: str) -> str:
        return self.href if name == "href" else ""


class Article:
    def __init__(self, text: str, visible_url: str, article_links=None, quote_cards=None) -> None:
        self.text, self.visible_url = text, visible_url
        self.article_links = article_links or [Node(text=visible_url, href="https://t.co/example")]
        self.quote_cards = quote_cards or []

    def query_selector(self, selector: str):
        if selector == 'div[data-testid="tweetText"]':
            return Node(text=self.text)
        if 'status/' in selector:
            for link in self.article_links:
                if "/selawmqt/status/" in link.href:
                    return link
            return Node(href="/selawmqt/status/123")
        return None

    def query_selector_all(self, selector: str):
        if selector == 'div[data-testid="tweetText"] a':
            return [Node(text=self.visible_url, href="https://t.co/example")]
        if selector == "a":
            return self.article_links
        if selector == 'div[role="link"]':
            return self.quote_cards
        return []


class Page:
    def __init__(self, articles) -> None:
        self.articles = articles

    def query_selector_all(self, selector: str):
        return self.articles


class XPostTests(unittest.TestCase):
    def test_expected_browser_handle_must_match_before_publish(self) -> None:
        with patch.dict(os.environ, {"X_REPOST_EXPECTED_HANDLE": "diceai0"}, clear=False):
            MODULE.require_expected_handle("diceai0")
            with self.assertRaisesRegex(ValueError, "does not match expected handle"):
                MODULE.require_expected_handle("selawmqt")

    def test_postiz_reconcile_binds_submission_integration_and_release_url(self) -> None:
        class Response:
            content = "Useful post"
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self):
                return json.dumps({"posts": [{
                    "id": "provider-1", "state": "PUBLISHED",
                    "content": self.content,
                    "releaseURL": "https://twitter.com/selawmqt/status/123",
                    "integration": {"id": "integration-1"},
                }]}).encode()

        env = {"POSTIZ_API_KEY": "secret", "X_REPOST_POSTIZ_INTEGRATION_ID": "integration-1"}
        with patch.dict(os.environ, env, clear=False), patch.object(
            MODULE, "urlopen", return_value=Response()
        ):
            url = MODULE.postiz_published_url(
                "provider-1", "2026-08-26T16:41:28+00:00", "Useful post"
            )
        self.assertEqual(url, "https://x.com/selawmqt/status/123")
        Response.content = "Different post"
        with patch.dict(os.environ, env, clear=False), patch.object(
            MODULE, "urlopen", return_value=Response()
        ), self.assertRaisesRegex(ValueError, "content mismatch"):
            MODULE.postiz_published_url(
                "provider-1", "2026-08-26T16:41:28+00:00", "Useful post"
            )

    def test_quote_card_same_handle_wrong_status_is_not_exact(self) -> None:
        class Link:
            def __init__(self, href): self.href = href
            def get_attribute(self, _name): return self.href
        class Card:
            def __init__(self, target): self.target = target
            def inner_text(self): return "Source\n@source"
            def click(self): page.url = self.target
        class ScopedArticle:
            def __init__(self, post, card): self.post, self.card = post, card
            def query_selector_all(self, selector):
                return [Link(self.post)] if selector == "a" else [self.card]
        class QuotePage:
            url = "https://x.com/selawmqt/status/123"
            articles = [
                ScopedArticle("/selawmqt/status/123", Card("https://x.com/source/status/999")),
                ScopedArticle("/other/status/456", Card("https://x.com/source/status/456")),
            ]
            def query_selector_all(self, _selector): return self.articles
            def wait_for_url(self, expected, timeout):
                if self.url != expected: raise TimeoutError(timeout)
        page = QuotePage()
        self.assertFalse(MODULE.quote_card_opens_exact_source(
            page, "https://x.com/selawmqt/status/123", "https://x.com/source/status/456"
        ))
        page.url = "https://x.com/selawmqt/status/123"
        page.articles[0].card = Card("https://x.com/source/status/456")
        self.assertTrue(MODULE.quote_card_opens_exact_source(
            page, "https://x.com/selawmqt/status/123", "https://x.com/source/status/456"
        ))

    def test_reconcile_no_provider_match_stays_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            text_file = Path(td) / "post.txt"
            text_file.write_text("Useful https://aniccaai.com/blog/tool")
            argv = ["x_post.py", "--cdp", "http://127.0.0.1:1", "--mode", "reconcile",
                    "--text-file", str(text_file), "--provider-submission-id", "provider-1",
                    "--effect-observed-at", "2026-08-26T16:41:28+00:00"]
            output = io.StringIO()
            with patch.object(MODULE, "postiz_published_url", return_value=None), \
                    patch.object(MODULE.sys, "argv", argv), redirect_stdout(output):
                with self.assertRaisesRegex(SystemExit, "2"):
                    MODULE.main()
        self.assertEqual(json.loads(output.getvalue())["posted"], "unverified")

    def test_browser_quote_uses_historical_single_composer_effect(self) -> None:
        class Keyboard:
            def __init__(self):
                self.typed, self.pressed = [], []

            def type(self, value, delay):
                self.typed.append((value, delay))

            def press(self, value):
                self.pressed.append(value)

        class Button:
            clicked = 0

            def is_enabled(self):
                return True

            def click(self):
                self.clicked += 1

        class Compose:
            def __init__(self):
                self.keyboard, self.button, self.closed = Keyboard(), Button(), False

            def goto(self, *_args, **_kwargs): pass
            def wait_for_selector(self, *_args, **_kwargs): return True
            def click(self, *_args): pass
            def wait_for_timeout(self, *_args): pass
            def query_selector(self, selector):
                return self.button if "tweetButton" in selector else None
            def close(self): self.closed = True

        compose = Compose()

        class Context:
            pages = []
            def new_page(self): return compose

        class Browser:
            contexts = [Context()]

        class Chromium:
            def connect_over_cdp(self, _cdp): return Browser()

        class Playwright:
            chromium = Chromium()

        source = "https://x.com/source/status/123"
        with patch.object(MODULE, "ensure_logged_in", return_value="selawmqt"), \
                patch.object(MODULE, "get_page", return_value=object()):
            result = MODULE.browser_publish(
                Playwright(), "http://127.0.0.1:1", "Useful comparison", "quote", source
            )

        self.assertEqual(result, {"handle": "selawmqt", "published": True})
        self.assertEqual(compose.keyboard.typed, [("Useful comparison", 18), (source, 12)])
        self.assertEqual(compose.keyboard.pressed, ["Enter"])
        self.assertEqual(compose.button.clicked, 1)
        self.assertTrue(compose.closed)

    def test_transport_selector_never_calls_both_publishers(self) -> None:
        calls = []

        def postiz(*_args):
            calls.append("postiz")
            return "provider-1"

        def browser(*_args):
            calls.append("browser")
            return {"handle": "selawmqt", "published": True}

        browser_result = MODULE.submit_effect(
            "browser", "Useful post", "original", None, postiz, browser,
        )
        self.assertEqual(calls, ["browser"])
        self.assertEqual(browser_result["provider"], "x_browser")
        calls.clear()

        postiz_result = MODULE.submit_effect(
            "postiz", "Useful post", "original", None, postiz, browser,
        )
        self.assertEqual(calls, ["postiz"])
        self.assertEqual(postiz_result["provider_submission_id"], "provider-1")

    def test_postiz_http_error_summary_keeps_message_and_redacts_urls(self) -> None:
        error = urllib.error.HTTPError(
            "https://api.postiz.com/public/v1/posts", 400, "Bad Request", {},
            io.BytesIO(json.dumps({
                "message": "Duplicate content at https://secret.example/path",
                "apiKey": "must-not-leak",
            }).encode()),
        )
        summary = MODULE.http_error_summary(error)
        self.assertIn("Duplicate content", summary)
        self.assertNotIn("https://", summary)
        self.assertNotIn("must-not-leak", summary)

    def test_postiz_acceptance_survives_readback_session_failure_as_unverified(self) -> None:
        class BrokenPlaywright:
            def __enter__(self):
                raise SystemExit("session unavailable")

            def __exit__(self, *_args):
                return False

        with tempfile.TemporaryDirectory() as td:
            text_file = Path(td) / "post.txt"
            text_file.write_text("Useful comparison", encoding="utf-8")
            argv = ["x_post.py", "--cdp", "http://127.0.0.1:1", "--mode", "quote",
                    "--source-url", "https://x.com/source/status/123",
                    "--text-file", str(text_file)]
            output = io.StringIO()
            with patch.object(MODULE, "postiz_publish", return_value="provider-1"), \
                    patch.object(MODULE, "sync_playwright", return_value=BrokenPlaywright()), \
                    patch.object(MODULE.sys, "argv", argv), redirect_stdout(output):
                with self.assertRaisesRegex(SystemExit, "2"):
                    MODULE.main()
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["posted"], "unverified")
        self.assertEqual(receipt["provider_submission_id"], "provider-1")

    def test_postiz_quote_appends_source_once_and_returns_submission(self) -> None:
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'[{"postId":"provider-1"}]'

        def fake_open(request, timeout):
            captured["payload"] = json.loads(request.data)
            captured["timeout"] = timeout
            return Response()

        env = {"POSTIZ_API_KEY": "secret", "X_REPOST_POSTIZ_INTEGRATION_ID": "integration-1"}
        source = "https://x.com/source/status/123"
        with patch.dict(os.environ, env, clear=False), patch.object(MODULE, "urlopen", fake_open):
            submission = MODULE.postiz_publish("Useful comparison", "quote", source)
        self.assertEqual(submission, "provider-1")
        value = captured["payload"]["posts"][0]["value"][0]["content"]
        self.assertEqual(value, f"Useful comparison\n{source}")
        self.assertEqual(captured["payload"]["posts"][0]["integration"]["id"], "integration-1")
        self.assertTrue(captured["payload"]["posts"][0]["settings"]["made_with_ai"])

    def test_postiz_publish_reads_key_from_private_credentials_ssot(self) -> None:
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'[{"postId":"provider-ssot"}]'

        def fake_open(request, timeout):
            captured["authorization"] = request.get_header("Authorization")
            captured["timeout"] = timeout
            return Response()

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            private_dir = home / ".local" / "share" / "anicca"
            private_dir.mkdir(parents=True)
            credentials = private_dir / "credentials.json"
            credentials.write_text(json.dumps({"credentials": [{
                "service": "postiz", "api_key": "ssot-test-secret",
            }]}), encoding="utf-8")
            private_dir.chmod(0o700)
            credentials.chmod(0o600)
            with patch.object(Path, "home", return_value=home), \
                    patch.dict(os.environ, {
                        "X_REPOST_POSTIZ_INTEGRATION_ID": "integration-1",
                    }, clear=True), \
                    patch.object(MODULE, "urlopen", fake_open):
                submission = MODULE.postiz_publish(
                    "Useful comparison", "quote", "https://x.com/source/status/123"
                )

        self.assertEqual(submission, "provider-ssot")
        self.assertEqual(captured["authorization"], "ssot-test-secret")

    def test_postiz_publish_rejects_non_private_credentials_before_request(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            private_dir = home / ".local" / "share" / "anicca"
            private_dir.mkdir(parents=True)
            credentials = private_dir / "credentials.json"
            credentials.write_text(json.dumps({"credentials": [{
                "service": "postiz", "api_key": "ssot-test-secret",
            }]}), encoding="utf-8")
            private_dir.chmod(0o700)
            credentials.chmod(0o644)
            with patch.object(Path, "home", return_value=home), \
                    patch.dict(os.environ, {
                        "X_REPOST_POSTIZ_INTEGRATION_ID": "integration-1",
                    }, clear=True), \
                    patch.object(MODULE, "urlopen") as provider_request:
                with self.assertRaisesRegex(
                    MODULE.PostizPreSubmitError, "postiz_configuration_missing",
                ):
                    MODULE.postiz_publish(
                        "Useful comparison", "quote", "https://x.com/source/status/123"
                    )
        provider_request.assert_not_called()

    def test_postiz_response_without_submission_id_is_recorded_as_unknown(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'[{"status":"accepted"}]'

        with tempfile.TemporaryDirectory() as td:
            text_file = Path(td) / "post.txt"
            text_file.write_text("Useful comparison", encoding="utf-8")
            argv = ["x_post.py", "--cdp", "http://127.0.0.1:1", "--mode", "quote",
                    "--source-url", "https://x.com/source/status/123",
                    "--text-file", str(text_file)]
            output = io.StringIO()
            with patch.dict(os.environ, {"X_REPOST_PUBLISH_TRANSPORT": "postiz",
                                         "X_REPOST_POSTIZ_INTEGRATION_ID": "integration-1"},
                            clear=True), \
                    patch.object(MODULE, "_postiz_api_key", return_value="ssot-test-secret"), \
                    patch.object(MODULE, "urlopen", return_value=Response()), \
                    patch.object(MODULE.sys, "argv", argv), redirect_stdout(output):
                with self.assertRaisesRegex(SystemExit, "2"):
                    MODULE.main()

        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["posted"], "unverified")
        self.assertEqual(receipt["failure_phase"], "post_submit")
        self.assertEqual(receipt["reason_code"], "postiz_submission_id_missing")

    def test_postiz_refuses_automated_reply(self) -> None:
        env = {"POSTIZ_API_KEY": "secret", "X_REPOST_POSTIZ_INTEGRATION_ID": "integration-1"}
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaisesRegex(ValueError, "automated_reply_disabled"):
                MODULE.postiz_publish("No", "reply", "https://x.com/source/status/123")

    def test_public_ssr_reconciles_exact_owned_post(self) -> None:
        text = "Affiliate link: https://aniccaai.com/blog/voice-changer"
        markup = '''<article data-tweet-id="2091088320772346136">
        <span>Affiliate link: </span>
        <a href="https://aniccaai.com/blog/voice-changer">article</a></article>'''
        self.assertEqual(
            MODULE.find_exact_public_markup(
                markup, text, "https://aniccaai.com/blog/voice-changer", "selawmqt"
            ),
            "https://x.com/selawmqt/status/2091088320772346136",
        )

    def test_multiline_original_requires_exact_prefix_and_owned_url(self) -> None:
        text = "Before paying for an AI workflow: voice isolator.\n\nAffiliate link disclosure:\nhttps://aniccaai.com/blog/voice-isolator"
        found = MODULE.scan_timeline(
            Page([Article(text, "aniccaai.com/blog/voice-isolator")]), "selawmqt",
            "Before paying for an AI workflow: voice isolator.",
            "https://aniccaai.com/blog/voice-isolator", text,
        )
        self.assertEqual(found, "https://x.com/selawmqt/status/123")

    def test_original_rejects_similar_prefix_or_longer_url(self) -> None:
        text = "Before paying for an AI workflow: voice isolator.\n\nAffiliate link disclosure:\nhttps://aniccaai.com/blog/voice-isolator"
        found = MODULE.scan_timeline(
            Page([Article(
                "Before paying for an AI workflow: voice isolator. extra\n\nAffiliate link disclosure:\nhttps://aniccaai.com/blog/voice-isolator-plus",
                "aniccaai.com/blog/voice-isolator-plus",
            )]), "selawmqt", "Before paying for an AI workflow: voice isolator.",
            "https://aniccaai.com/blog/voice-isolator", text,
        )
        self.assertIsNone(found)

    def test_source_backed_original_reads_x_quote_card_outside_tweet_text(self) -> None:
        source = "https://x.com/jun_song/status/2091114049954283855"
        body = "Pair cloud orchestration with local execution, then compare one task."
        text = f"{body}\n{source}"
        article = Article(
            body, "", article_links=[
                Node(href="/selawmqt/status/456"),
                Node(href="/jun_song/status/2091114049954283855"),
            ],
        )
        self.assertEqual(
            MODULE.scan_timeline(Page([article]), "selawmqt", body, source, text),
            "https://x.com/selawmqt/status/456",
        )

    def test_source_backed_original_reads_non_anchor_x_quote_card(self) -> None:
        source = "https://x.com/jun_song/status/2091114049954283855"
        body = "Pair cloud orchestration with local execution, then compare one task."
        text = f"{body}\n{source}"
        article = Article(
            body, "", article_links=[Node(href="/selawmqt/status/789")],
            quote_cards=[Node(text="Jun Song\n@jun_song\n2h\nExact quoted source body")],
        )
        self.assertEqual(
            MODULE.scan_timeline(Page([article]), "selawmqt", body, source, text),
            "https://x.com/selawmqt/status/789",
        )

    def test_source_backed_original_reads_exact_body_when_x_omits_quote_card(self) -> None:
        source = "https://x.com/ForwardEditor/status/2091534492603220452"
        body = "Codex shines when your workspace looks like a junk drawer with an API key."
        text = f"{body}\n{source}"
        article = Article(
            body, "", article_links=[Node(href="/selawmqt/status/2091584652951879730")]
        )
        self.assertEqual(
            MODULE.scan_timeline(Page([article]), "selawmqt", body, source, text),
            "https://x.com/selawmqt/status/2091584652951879730",
        )

    def test_cardless_original_rejects_identical_status_before_submission(self) -> None:
        source = "https://x.com/ForwardEditor/status/2091534492603220452"
        body = "Codex shines when your workspace looks like a junk drawer with an API key."
        text = f"{body}\n{source}"
        old = Article(body, "", article_links=[Node(href="/selawmqt/status/100")])
        self.assertIsNone(
            MODULE.scan_timeline(
                Page([old]), "selawmqt", body, source, text, minimum_status_id=200
            )
        )

    def test_cardless_original_selects_new_status_when_old_identical_exists(self) -> None:
        source = "https://x.com/ForwardEditor/status/2091534492603220452"
        body = "Codex shines when your workspace looks like a junk drawer with an API key."
        text = f"{body}\n{source}"
        old = Article(body, "", article_links=[Node(href="/selawmqt/status/100")])
        new = Article(body, "", article_links=[Node(href="/selawmqt/status/300")])
        self.assertEqual(
            MODULE.scan_timeline(
                Page([old, new]), "selawmqt", body, source, text, minimum_status_id=200
            ),
            "https://x.com/selawmqt/status/300",
        )

    def test_source_backed_original_rejects_wrong_non_anchor_quote_card(self) -> None:
        source = "https://x.com/jun_song/status/2091114049954283855"
        body = "Pair cloud orchestration with local execution, then compare one task."
        text = f"{body}\n{source}"
        article = Article(
            body, "", article_links=[Node(href="/selawmqt/status/789")],
            quote_cards=[Node(text="Different author\n@jun_song_fan\n2h\nSimilar source body")],
        )
        self.assertIsNone(
            MODULE.scan_timeline(Page([article]), "selawmqt", body, source, text)
        )


if __name__ == "__main__":
    unittest.main()
