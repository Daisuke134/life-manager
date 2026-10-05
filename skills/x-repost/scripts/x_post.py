# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.40"]
# ///
"""Publish one X post through the connected Postiz API, then exact-read it from X.

A quote tweet is a normal post whose body ends with the quoted post's URL -- X renders the
embedded card itself. Browser access is readback-only: X's automation rules prohibit scripted
website posting, so the external write must go through the connected API transport.

Exit 0 ONLY after the published post has been read back from the account timeline and its
permalink captured. A compose box that accepted text is not evidence that anything shipped,
so every other outcome exits non-zero and the caller must not record a post.
"""
import argparse
import html as html_lib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

SCRIPT_DIR = str(Path(__file__).resolve().parent)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
from effect_reconcile import _postiz_key


POSTIZ_API = "https://api.postiz.com/public/v1/posts"
X_SNOWFLAKE_EPOCH_MS = 1288834974657


class PostizPreSubmitError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class PostizSubmissionOutcomeUnknown(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _postiz_api_key() -> str:
    return _postiz_key()


def http_error_summary(error: urllib.error.HTTPError) -> str:
    try:
        value = json.loads(error.read(4096).decode("utf-8", errors="replace"))
        message = value.get("message") if isinstance(value, dict) else None
        if isinstance(message, list):
            message = "; ".join(str(item) for item in message)
        text = message if isinstance(message, str) else error.reason
    except Exception:
        text = error.reason
    text = re.sub(r"https?://\S+", "[url]", str(text))
    text = re.sub(r"\b[A-Za-z0-9_-]{32,}\b", "[redacted]", text)
    return " ".join(text.split())[:300]


def snowflake_floor(observed_at: datetime) -> int:
    timestamp_ms = int(observed_at.timestamp() * 1000)
    return max(0, timestamp_ms - X_SNOWFLAKE_EPOCH_MS) << 22


def postiz_publish(text: str, mode: str, source_url: str | None) -> str:
    """Submit one API post and return its provider submission ID.

    Acceptance is not publication proof. The caller must still exact-read the X permalink.
    """
    api_key = _postiz_api_key()
    integration_id = os.environ.get("X_REPOST_POSTIZ_INTEGRATION_ID", "").strip()
    if not api_key or not integration_id:
        raise PostizPreSubmitError("postiz_configuration_missing")
    if mode == "reply":
        raise PostizPreSubmitError("automated_reply_disabled")
    content = text
    if mode == "quote" and source_url and source_url not in content:
        content = f"{content.rstrip()}\n{source_url}"
    payload = {
        "type": "now",
        "date": datetime.now(timezone.utc).isoformat(),
        "shortLink": False,
        "tags": [],
        "posts": [{
            "integration": {"id": integration_id},
            "value": [{"content": content, "image": []}],
            "settings": {
                "__type": "x", "who_can_reply_post": "everyone",
                "made_with_ai": True, "paid_partnership": False,
            },
        }],
    }
    request = Request(
        POSTIZ_API,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Authorization": api_key, "Content-Type": "application/json",
                 "User-Agent": "life-manager-x-repost/1"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise PostizSubmissionOutcomeUnknown("postiz_submission_response_unknown") from None
    row = result[0] if isinstance(result, list) and result else result
    submission_id = row.get("postId") if isinstance(row, dict) else None
    if not submission_id:
        raise PostizSubmissionOutcomeUnknown("postiz_submission_id_missing")
    return str(submission_id)


def postiz_published_url(
    submission_id: str, observed_at: str, expected_text: str
) -> str | None:
    """Resolve one accepted Postiz effect to its exact published X permalink."""
    api_key = _postiz_api_key()
    integration_id = os.environ.get("X_REPOST_POSTIZ_INTEGRATION_ID", "").strip()
    if not api_key or not integration_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", submission_id):
        raise PostizPreSubmitError("postiz_reconciliation_configuration_missing")
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("Postiz reconciliation time must be timezone-aware")
    query = urllib.parse.urlencode({
        "startDate": (observed - timedelta(hours=1)).astimezone(timezone.utc).isoformat(),
        "endDate": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    })
    request = Request(
        f"{POSTIZ_API}?{query}",
        headers={"Authorization": api_key, "User-Agent": "life-manager-x-repost/1"},
    )
    with urlopen(request, timeout=30) as response:
        value = json.load(response)
    for post in value.get("posts", []) if isinstance(value, dict) else []:
        if post.get("id") != submission_id or post.get("state") != "PUBLISHED":
            continue
        if (post.get("integration") or {}).get("id") != integration_id:
            raise ValueError("Postiz reconciliation integration mismatch")
        without_urls = lambda body: normalized(re.sub(r"https://[^\s]+", "", body or ""))
        if without_urls(post.get("content")) != without_urls(expected_text):
            raise ValueError("Postiz reconciliation content mismatch")
        release_url = str(post.get("releaseURL") or "")
        match = re.fullmatch(
            r"https://(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/([0-9]+)", release_url
        )
        if not match:
            raise ValueError("Postiz reconciliation release URL invalid")
        return f"https://x.com/{match.group(1)}/status/{match.group(2)}"
    return None


def submit_effect(transport, text, mode, source_url, postiz_submit, browser_submit):
    """Select exactly one external effect transport."""
    if transport == "postiz":
        submission_id = postiz_submit(text, mode, source_url)
        return {"provider": "postiz", "provider_submission_id": submission_id}
    if transport == "browser":
        result = browser_submit(text, mode, source_url)
        if not isinstance(result, dict) or result.get("published") is not True:
            raise ValueError("browser composer did not confirm submission")
        return {**result, "provider": "x_browser", "provider_submission_id": None}
    raise ValueError("unsupported X publish transport")


def require_expected_handle(handle: str) -> None:
    expected_handle = os.environ.get("X_REPOST_EXPECTED_HANDLE", "").strip().lstrip("@")
    if expected_handle and handle.lower() != expected_handle.lower():
        raise ValueError("leased browser account does not match expected handle")


def browser_publish(pw, cdp: str, text: str, mode: str, source_url: str | None) -> dict:
    """Historical leased-browser composer effect restored from 95d4c151e^."""
    browser = pw.chromium.connect_over_cdp(cdp)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    handle = ensure_logged_in(get_page(browser))
    require_expected_handle(handle)
    compose = ctx.new_page()
    published = False
    try:
        if mode == "reply":
            compose.goto(source_url, wait_until="domcontentloaded", timeout=60000)
            compose.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=45000)
            compose.click('[data-testid="tweetTextarea_0"]')
            compose.keyboard.type(text, delay=18)
            compose.wait_for_timeout(2000)
        elif mode == "quote":
            compose.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=60000)
            compose.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=45000)
            compose.click('[data-testid="tweetTextarea_0"]')
            compose.keyboard.type(text, delay=18)
            compose.keyboard.press("Enter")
            compose.keyboard.type(source_url, delay=12)
            compose.wait_for_timeout(6000)
        else:
            compose.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=60000)
            compose.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=45000)
            compose.click('[data-testid="tweetTextarea_0"]')
            compose.keyboard.type(text, delay=18)
            compose.wait_for_timeout(2000)

        button = (compose.query_selector('[data-testid="tweetButtonInline"]')
                  or compose.query_selector('[data-testid="tweetButton"]'))
        if button and button.is_enabled():
            button.click()
        else:
            compose.keyboard.press("Meta+Enter")
        try:
            compose.wait_for_selector(
                '[data-testid="tweetTextarea_0"]', state="detached", timeout=30000
            )
            published = True
        except Exception:
            body = compose.query_selector('[data-testid="tweetTextarea_0"]')
            published = bool(body) and not (body.inner_text() or "").strip()
    finally:
        if not published:
            try:
                compose.keyboard.press("Escape")
                compose.wait_for_timeout(1500)
                confirm = compose.query_selector('[data-testid="confirmationSheetConfirm"]')
                if confirm:
                    confirm.click(); compose.wait_for_timeout(1500)
            except Exception as exc:
                print(f"x_post: could not discard the draft: {exc}", file=sys.stderr)
        try:
            compose.close()
        except Exception as exc:
            print(f"x_post: leaving the compose tab open: {exc}", file=sys.stderr)
    return {"handle": handle, "published": published}


def ensure_logged_in(page) -> str:
    for attempt in (1, 2, 3):
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        try:
            link = page.wait_for_selector(
                '[data-testid="AppTabBar_Profile_Link"]', timeout=15000
            )
        except Exception:
            link = page.query_selector('[data-testid="AppTabBar_Profile_Link"]')
        if link:
            return (link.get_attribute("href") or "").strip("/")
        if attempt == 3:
            break
        cookies = page.context.cookies("https://x.com")
        if any(cookie.get("name") == "auth_token" and cookie.get("value") for cookie in cookies):
            # A persistent auth cookie plus a missing nav element is usually slow/transient UI.
            # Reload instead of replacing the known session with a possibly stale env fallback.
            continue
        token = os.environ.get("TWITTER_AUTH_TOKEN", "")
        if not token:
            raise SystemExit("x_post: not logged in and TWITTER_AUTH_TOKEN is unset")
        page.context.add_cookies([
            {"name": "auth_token", "value": token, "domain": ".x.com", "path": "/",
             "httpOnly": True, "secure": True, "sameSite": "None"},
        ])
    raise SystemExit("x_post: X session could not be restored from TWITTER_AUTH_TOKEN")


def get_page(browser):
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    for p in ctx.pages:
        if "x.com" in p.url and "doubleclick" not in p.url:
            return p
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def normalized(value: str) -> str:
    return " ".join(value.split())


def scan_timeline(page, handle: str, needle: str, expected_url: str | None = None,
                  expected_text: str | None = None, minimum_status_id: int | None = None):
    expected_visible = (expected_url or "").removeprefix("https://")
    exact_body_without_source = normalized(
        (expected_text or "").replace(expected_url or "", "").strip()
    )
    exact_bodies = {
        normalized(expected_text or ""),
        normalized((expected_text or "").replace(expected_url or "", expected_visible)),
        normalized(re.sub(r"https://(?:www\.)?", "", expected_text or "")),
        exact_body_without_source,
    }
    for art in page.query_selector_all('article[data-testid="tweet"]'):
        text_el = art.query_selector('div[data-testid="tweetText"]')
        body = text_el.inner_text() if text_el else ""
        body_text = normalized(body)
        if needle and (body_text in exact_bodies if expected_text else body_text.startswith(needle)):
            visible_links = []
            # X removes an x.com source URL from tweetText and renders it as a quote card. The
            # exact source anchor then lives elsewhere in the same article. Looking only inside
            # tweetText made accepted source-backed originals permanently "unverified".
            for anchor in art.query_selector_all("a"):
                visible_links.extend((anchor.get_attribute("href") or "", anchor.inner_text() or ""))
            def canonical_link(link):
                value = normalized(link).removeprefix("https://").removeprefix("www.").rstrip("/")
                return f"x.com{value}" if value.startswith("/") else value
            exact_source_link = any(canonical_link(link) == expected_visible.rstrip("/")
                                    for link in visible_links)
            if expected_visible and not exact_source_link:
                # X currently renders quote cards as a clickable DIV, not an anchor. The exact
                # source status URL is therefore absent from the DOM even though the quoted
                # account and body are visible. Accept that representation only when this is an
                # x.com status URL and the card contains the exact source @handle. The generated
                # body above must still match exactly, so a card alone can never recover a row.
                parsed = urllib.parse.urlparse(expected_url or "")
                parts = [part for part in parsed.path.split("/") if part]
                source_handle = parts[0] if (parsed.netloc.lower() in {"x.com", "www.x.com"}
                                             and len(parts) >= 3 and parts[1] == "status") else ""
                quote_cards = art.query_selector_all('div[role="link"]')
                source_identity = f"@{source_handle}" if source_handle else ""
                card_matches = bool(source_identity) and any(
                    source_identity in {
                        line.strip() for line in (card.inner_text() or "").splitlines()
                    } for card in quote_cards
                )
                if quote_cards and not card_matches:
                    continue
                if not quote_cards and body_text != exact_body_without_source:
                    continue
            link = art.query_selector(f'a[href*="/{handle}/status/"]')
            href = link.get_attribute("href") if link else ""
            if href:
                status = re.search(r"/status/([0-9]+)", href)
                if minimum_status_id is not None and (
                    not status or int(status.group(1)) < minimum_status_id
                ):
                    continue
                return "https://x.com" + href.split("/photo/")[0]
    return None


def quote_card_opens_exact_source(page, post_url: str, source_url: str) -> bool:
    parsed = urllib.parse.urlparse(source_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname not in {"x.com", "www.x.com"} or len(parts) < 3:
        return False
    identity = f"@{parts[0]}"
    post_path = urllib.parse.urlparse(post_url).path.rstrip("/")
    article = next((candidate for candidate in page.query_selector_all(
        'article[data-testid="tweet"]'
    ) if any((link.get_attribute("href") or "").split("?")[0].rstrip("/") == post_path
             for link in candidate.query_selector_all("a"))), None)
    if article is None:
        return False
    for card in article.query_selector_all('div[role="link"]'):
        if identity not in {line.strip() for line in (card.inner_text() or "").splitlines()}:
            continue
        card.click()
        try:
            page.wait_for_url(source_url, timeout=15000)
        except Exception:
            return False
        return page.url.rstrip("/") == source_url.rstrip("/")
    return False


def find_exact_public_markup(markup: str, expected_text: str, expected_url: str, handle: str,
                             minimum_status_id: int | None = None):
    prefix = normalized(expected_text.replace(expected_url, "").strip())
    escaped_url = html_lib.escape(expected_url, quote=True)
    for article in re.findall(r"<article\b.*?</article>", markup, flags=re.DOTALL):
        tweet_id = re.search(r'data-tweet-id="([0-9]+)"', article)
        if not tweet_id or f'href="{escaped_url}"' not in article:
            continue
        if minimum_status_id is not None and int(tweet_id.group(1)) < minimum_status_id:
            continue
        visible = normalized(html_lib.unescape(re.sub(r"<[^>]+>", " ", article)))
        if prefix in visible:
            return f"https://x.com/{handle}/status/{tweet_id.group(1)}"
    return None


def public_profile_readback(handle: str, expected_text: str, expected_url: str,
                            minimum_status_id: int | None = None):
    request = Request(f"https://x.com/{handle}", headers={"User-Agent": "x-repost/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            markup = response.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return find_exact_public_markup(
        markup, expected_text, expected_url, handle, minimum_status_id
    )


def find_reply_permalink(pw, cdp: str, source_url: str, handle: str, needle: str,
                         minimum_status_id: int | None = None, attempts: int = 5):
    """A reply lives in the conversation, not on the profile timeline, so read it back there.

    Scanning the profile would report every reply as unverified: X files replies under a separate
    tab, and treating that absence as failure would consume sources for posts that did ship.
    """
    for attempt in range(attempts):
        try:
            browser = pw.chromium.connect_over_cdp(cdp)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
            try:
                page.goto(source_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(6000)
                found = scan_timeline(
                    page, handle, needle, minimum_status_id=minimum_status_id
                )
                if found:
                    return found
            finally:
                page.close()
        except Exception as exc:
            print(f"x_post: reply read-back attempt {attempt + 1} failed: {exc}", file=sys.stderr)
        time.sleep(6)
    return None


def find_permalink(pw, cdp: str, handle: str, needle: str, expected_url: str | None = None,
                   expected_text: str | None = None,
                   minimum_status_id: int | None = None, attempts: int = 6):
    """Read the account timeline back and return the permalink of the post we just made.

    Reconnects on every attempt instead of holding one page handle. The browser can die
    underneath this step -- it did on 2026-08-17, when navigating away from a dirty composer
    fired a beforeunload dialog and killed the Playwright driver process -- and a read-back that
    cannot survive that turns a published post into an unrecorded one.
    """
    for attempt in range(attempts):
        try:
            browser = pw.chromium.connect_over_cdp(cdp)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()   # own tab: never navigate one that might hold composer text
            try:
                page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                found = scan_timeline(
                    page, handle, needle, expected_url, expected_text, minimum_status_id
                )
                if found:
                    return found
            finally:
                page.close()
        except Exception as exc:
            print(f"x_post: read-back attempt {attempt + 1} failed: {exc}", file=sys.stderr)
        if expected_url and expected_text:
            found = public_profile_readback(
                handle, expected_text, expected_url, minimum_status_id
            )
            if found:
                return found
        time.sleep(6)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", required=True, help="leased CDP base URL from browser-guard.sh")
    ap.add_argument("--source-url", help="the post being quoted or replied to")
    ap.add_argument("--text-file", required=True, help="file holding the comment body")
    ap.add_argument("--provider-submission-id")
    ap.add_argument("--effect-observed-at")
    # A quote is a new post from an account with no followers, which asks the ranker to distribute
    # out-of-network content to nobody. A reply is rendered to the people already reading the
    # original, and "the author engaged your reply" is the single highest-weighted signal X
    # publishes (+75, against 0.5 for a like).
    ap.add_argument("--mode", choices=["quote", "reply", "original", "reconcile"], default="quote")
    args = ap.parse_args()

    if args.mode in {"quote", "reply"} and not args.source_url:
        raise SystemExit("x_post: --source-url is required for quote or reply")

    with open(args.text_file, encoding="utf-8") as stream:
        text = stream.read().strip()
    if not text:
        raise SystemExit("x_post: refusing to publish an empty comment")

    urls = re.findall(r"https://[^\s]+", text)
    expected_url = urls[0].rstrip(".,)") if args.mode in {"original", "reconcile"} and len(urls) == 1 else None
    if args.mode == "reconcile" and args.source_url:
        expected_url = args.source_url
    if args.mode in {"original", "reconcile"} and not expected_url:
        raise SystemExit("x_post: original post requires exactly one URL")
    needle = " ".join(text.split(expected_url, 1)[0].split()) if expected_url else "".join(text.split("\n")[0])[:24]
    if args.mode == "reconcile":
        if not args.provider_submission_id or not args.effect_observed_at:
            raise SystemExit("x_post: reconcile requires provider effect identity and time")
        try:
            provider_url = postiz_published_url(
                args.provider_submission_id, args.effect_observed_at, text
            )
        except (ValueError, OSError, urllib.error.HTTPError):
            provider_url = None
        if not provider_url:
            json.dump({"posted": "unverified", "mode": args.mode,
                       "provider_submission_id": args.provider_submission_id,
                       "reason": "Postiz effect is not published with an exact X URL"},
                      sys.stdout, ensure_ascii=False)
            print(); sys.exit(2)
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(args.cdp)
            handle = ensure_logged_in(get_page(browser))
            expected_handle = urllib.parse.urlparse(provider_url).path.split("/")[1]
            if handle.lower() != expected_handle.lower():
                raise SystemExit("x_post: Postiz release URL account mismatch")
            page = browser.contexts[0].new_page()
            try:
                page.goto(provider_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                permalink = scan_timeline(
                    page, handle, needle, args.source_url or expected_url,
                    text, minimum_status_id=int(provider_url.rsplit("/", 1)[1]),
                )
                exact_quote_source = (
                    not args.source_url
                    or quote_card_opens_exact_source(page, provider_url, args.source_url)
                )
            finally:
                page.close()
        if permalink != provider_url or not exact_quote_source:
            json.dump({"posted": "unverified", "mode": args.mode,
                       "provider_submission_id": args.provider_submission_id,
                       "reason": "exact Postiz permalink did not match X content"},
                      sys.stdout, ensure_ascii=False)
            print(); sys.exit(2)
        json.dump({"posted": True, "mode": args.mode, "handle": handle,
                   "post_url": permalink, "source_url": args.source_url,
                   "provider": "postiz",
                   "provider_submission_id": args.provider_submission_id},
                  sys.stdout, ensure_ascii=False)
        print(); return
    transport = os.environ.get("X_REPOST_PUBLISH_TRANSPORT", "postiz").strip().lower()
    if transport not in {"postiz", "browser"}:
        raise SystemExit("x_post: unsupported publish transport")
    minimum_status_id = snowflake_floor(datetime.now(timezone.utc))
    effect = None
    if transport == "postiz":
        try:
            effect = submit_effect(
                transport, text, args.mode, args.source_url,
                postiz_publish, lambda *_args: None,
            )
        except PostizPreSubmitError as exc:
            receipt = {"posted": False, "mode": args.mode, "source_url": args.source_url,
                       "provider": "postiz", "provider_status": None,
                       "failure_phase": "pre_submit", "reason_code": exc.reason_code}
            json.dump(receipt, sys.stdout, ensure_ascii=False)
            print(); sys.exit(1)
        except PostizSubmissionOutcomeUnknown as exc:
            receipt = {"posted": "unverified", "mode": args.mode,
                       "source_url": args.source_url, "provider": "postiz",
                       "provider_status": None, "failure_phase": "post_submit",
                       "reason_code": exc.reason_code}
            json.dump(receipt, sys.stdout, ensure_ascii=False)
            print(); sys.exit(2)
        except (ValueError, OSError, urllib.error.HTTPError) as exc:
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            receipt = {"posted": False, "mode": args.mode, "source_url": args.source_url,
                       "provider": "postiz", "provider_status": status,
                       "reason": type(exc).__name__}
            if isinstance(exc, urllib.error.HTTPError):
                receipt["provider_error"] = http_error_summary(exc)
            json.dump(receipt, sys.stdout, ensure_ascii=False)
            print(); sys.exit(1)
    browser_attempted = False
    try:
        with sync_playwright() as pw:
            if transport == "browser":
                browser_attempted = True
                effect = submit_effect(
                    transport, text, args.mode, args.source_url,
                    postiz_publish,
                    lambda body, mode, source: browser_publish(
                        pw, args.cdp, body, mode, source
                    ),
                )
                handle = effect["handle"]
            else:
                browser = pw.chromium.connect_over_cdp(args.cdp)
                handle = ensure_logged_in(get_page(browser))
            if args.mode == "reply":
                permalink = find_reply_permalink(
                    pw, args.cdp, args.source_url, handle, needle, minimum_status_id
                )
            else:
                permalink = find_permalink(
                    pw, args.cdp, handle, needle, expected_url,
                    text if expected_url else None, minimum_status_id
                )
    except (Exception, SystemExit) as exc:
        if effect is None and not browser_attempted:
            json.dump({"posted": False, "mode": args.mode,
                       "source_url": args.source_url, "provider": transport,
                       "reason": type(exc).__name__}, sys.stdout, ensure_ascii=False)
            print(); sys.exit(1)
        json.dump({"posted": "unverified", "mode": args.mode,
                   "source_url": args.source_url,
                   "provider": (effect or {}).get("provider", "x_browser"),
                   "provider_submission_id": (effect or {}).get("provider_submission_id"),
                   "reason": f"readback failed: {type(exc).__name__}"},
                  sys.stdout, ensure_ascii=False)
        print()
        sys.exit(2)
    if not permalink:
        json.dump({"posted": "unverified", "mode": args.mode, "handle": handle,
                   "needle": needle, "source_url": args.source_url,
                   "provider": effect["provider"],
                   "provider_submission_id": effect.get("provider_submission_id"),
                   "reason": "effect accepted but no matching post was found on the timeline"},
                  sys.stdout, ensure_ascii=False)
        print()
        sys.exit(2)
    json.dump({"posted": True, "mode": args.mode, "handle": handle,
               "post_url": permalink, "source_url": args.source_url,
               "provider": effect["provider"],
               "provider_submission_id": effect.get("provider_submission_id")},
              sys.stdout, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
