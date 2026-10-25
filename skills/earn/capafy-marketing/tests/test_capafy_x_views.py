import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import capafy_x_views as xv  # noqa: E402


def _post(when, provider="x", state="PUBLISHED", url="https://twitter.com/selawmqt/status/2114362917105828288"):
    return {"publishDate": when, "integration": {"providerIdentifier": provider}, "state": state, "releaseURL": url}


def test_status_id_comes_from_the_release_url_only():
    assert xv.status_id("https://twitter.com/selawmqt/status/2114362917105828288") == "2114362917105828288"
    assert xv.status_id("https://www.tiktok.com/@honnevideo") is None
    assert xv.status_id("") is None


def test_only_published_x_posts_with_a_status_id_are_read_newest_last():
    posts = [
        _post("2026-10-25T10:00"), _post("2026-10-25T11:00", provider="tiktok"),
        # a valid X status URL but not published: only the state can exclude these
        _post("2026-10-25T12:00", state="ERROR"), _post("2026-10-25T13:00", state="QUEUE"),
        _post("2026-10-25T14:00"), _post("2026-10-25T09:00", url="https://x.com/someone"),
    ]
    rows = xv.published_x_posts(posts, limit=10)
    assert [p["publishDate"] for p in rows] == ["2026-10-25T10:00", "2026-10-25T14:00"]
    assert [p["publishDate"] for p in xv.published_x_posts(posts, limit=1)] == ["2026-10-25T14:00"]


def test_summary_never_turns_an_unread_post_into_zero():
    assert xv.summarize([4, None, 29]) == {"posts": 3, "read": 2, "sum": 33, "mean": 16.5, "max": 29}
    assert xv.summarize([None]) == {"posts": 1, "read": 0, "sum": 0, "mean": None, "max": None}
