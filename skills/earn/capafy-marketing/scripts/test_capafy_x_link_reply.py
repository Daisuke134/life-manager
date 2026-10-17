import datetime as dt

from capafy_x_link_reply import pending, reply_text

NOW = dt.datetime(2026, 10, 16, 1, 0, tzinfo=dt.timezone.utc)


def _entry(url, cta="https://capafy.ai/agent/2844813315?ct=tiktok_x", status="PUBLISHED"):
    return {"x_cta_url": cta, "destinations": {"x": {"status": status, "url": url}}}


def test_pending_picks_recent_published_posts_without_a_reply():
    ledger = {
        "2026-10-15-h22m00": _entry("https://twitter.com/selawmqt/status/2"),
        "2026-10-15-h23m00": _entry("https://twitter.com/selawmqt/status/3"),
        "2026-10-15-h21m00": _entry("https://twitter.com/selawmqt/status/1", status="ERROR"),
        "2026-10-12-h01m00": _entry("https://twitter.com/selawmqt/status/0"),
        "2026-10-15-h20m00": _entry("https://twitter.com/selawmqt/status/9", cta=""),
    }
    done = {"https://twitter.com/selawmqt/status/2"}
    assert pending(ledger, done, NOW, hours=48, limit=5) == [
        ("https://twitter.com/selawmqt/status/3", "https://capafy.ai/agent/2844813315?ct=tiktok_x"),
    ]


def test_pending_is_newest_first_and_capped():
    ledger = {f"2026-10-15-h{h:02d}m00": _entry(f"https://twitter.com/selawmqt/status/{h}") for h in range(10, 16)}
    got = pending(ledger, set(), NOW, hours=48, limit=2)
    assert [u for u, _ in got] == ["https://twitter.com/selawmqt/status/15", "https://twitter.com/selawmqt/status/14"]


def test_reply_text_carries_the_registered_ct_link():
    assert reply_text("https://capafy.ai/agent/2844813315?ct=tiktok_x") == (
        "Try it on Capafy: https://capafy.ai/agent/2844813315?ct=tiktok_x")


def test_postiz_posts_outside_the_ledger_get_the_hook_lab_link():
    # Daily Hook Lab reels and manual carousels are posted through Postiz, not the
    # distribute ledger, so they had no reply route (2026-10-16).
    from capafy_x_link_reply import HOOKLAB_X, postiz_pending

    posts = [
        {"releaseURL": "https://twitter.com/selawmqt/status/11", "state": "PUBLISHED",
         "publishDate": "2026-10-16T00:00:00.000Z", "content": "Your video is good. Hook Lab writes hooks."},
        {"releaseURL": "https://twitter.com/selawmqt/status/13", "state": "PUBLISHED",
         "publishDate": "2026-10-16T00:10:00.000Z", "content": "会議の前に最初の一文だけ決めておく。"},
        {"releaseURL": "https://twitter.com/selawmqt/status/12", "state": "PUBLISHED",
         "publishDate": "2026-10-13T00:00:00.000Z", "content": "hook"},
        {"releaseURL": None, "state": "QUEUE", "publishDate": "2026-10-16T00:30:00.000Z"},
        {"releaseURL": "https://twitter.com/selawmqt/status/2", "state": "PUBLISHED",
         "publishDate": "2026-10-15T23:00:00.000Z"},
    ]
    ledger_urls = {"https://twitter.com/selawmqt/status/2"}
    done = set()
    assert postiz_pending(posts, ledger_urls, done, NOW, hours=48) == [
        ("https://twitter.com/selawmqt/status/11", HOOKLAB_X),
    ]
