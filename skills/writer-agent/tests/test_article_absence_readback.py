"""Pure judgement of one destination's owner listing; readers are thin I/O around it."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "article_absence_readback.py"
spec = importlib.util.spec_from_file_location("article_absence_readback", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["article_absence_readback"] = mod
spec.loader.exec_module(mod)

SINCE, UNTIL = 1000.0, 2000.0
TITLES = ["「TikTok動画のネタがない」は、台本の前に導線を決めていないから起きる",
          "More TikTok Video Script Ideas Won’t Fix a Missing Customer Path"]
OLD = {"title": "older article", "times": [500.0]}


def test_absent_only_when_complete_and_every_item_is_older_and_untitled():
    assert mod.judge([OLD], since=SINCE, until=UNTIL, titles=TITLES, complete=True)["status"] == "absent"
    assert mod.judge([], since=SINCE, until=UNTIL, titles=TITLES, complete=True)["status"] == "absent"


def test_window_item_title_match_or_incomplete_list_is_never_absent():
    window = {"title": "something else", "times": [1500.0]}
    late = {"title": "something else", "times": [2000.0 + mod.GRACE_SECONDS - 1]}
    titled = {"title": "More TikTok Video Script Ideas Won't Fix a Missing Customer Path", "times": [100.0]}
    prefix = {"title": TITLES[0][:24] + "…", "times": [100.0]}
    for items in ([window], [late], [titled], [prefix]):
        assert mod.judge(items, since=SINCE, until=UNTIL, titles=TITLES, complete=True)["status"] == "present"
    assert mod.judge([OLD], since=SINCE, until=UNTIL, titles=TITLES, complete=False)["status"] == "unreadable"


def test_run_titles_read_frontmatter_and_heading(tmp_path):
    (tmp_path / "article-en.md").write_text('---\ntitle: "Front Title"\n---\n\n# Heading Title\n')
    (tmp_path / "article-ja.md").write_text("# 見出し\n本文\n")
    assert sorted(mod.run_titles(tmp_path)) == ["Front Title", "Heading Title", "見出し"]


import pytest

SINCE_ISO_AFTER = "2026-10-16T05:00:00Z"


def _note(key, name, status, created, publish=None, owner="anicca123", draft_name=None):
    return {"key": key, "name": name, "status": status, "createdAt": created, "publishAt": publish,
            "user": {"urlname": owner}, "noteDraft": {"name": draft_name} if draft_name else None}


def test_note_needs_last_page_and_the_ledger_anchor_and_reads_drafts():
    page1 = {"notes": [_note("ndfdf4919927a", "Claude Codeを個人編集部にする", "published",
                             "2026-10-11T18:47:00+09:00", "2026-10-12T03:59:33+09:00")],
             "isLastPage": False, "totalCount": 2}
    page2 = {"notes": [_note("n984df07e0ab5", "", "draft", "2026-09-19T12:10:36+09:00",
                             draft_name="「TikTok動画のネタがない」は、台本の前に導線を決めていないから起きる")],
             "isLastPage": True, "totalCount": 2}
    items, complete = mod.parse_note([page1, page2], "anicca123", "ndfdf4919927a")
    assert complete is True
    verdict = mod.judge(items, since=mod._epoch(SINCE_ISO_AFTER), until=mod._epoch(SINCE_ISO_AFTER),
                        titles=TITLES, complete=complete)
    assert verdict["status"] == "present" and verdict["reason"] == "title_match"   # draft title seen
    assert mod.parse_note([page1], "anicca123", "ndfdf4919927a")[1] is False        # not last page
    assert mod.parse_note([page1, page2], "anicca123", "nmissing")[1] is False      # anchor absent
    with pytest.raises(ValueError):
        mod.parse_note([{"notes": [_note("k", "x", "draft", "2026-09-19T12:10:36")], "isLastPage": True}],
                       "anicca123", "k")                                             # naive time


def _post(pid, title, updated, created, post_date=None):
    return {"id": pid, "draft_title": title, "title": title, "draft_updated_at": updated,
            "draft_created_at": created, "post_date": post_date}


def test_substack_complete_only_when_every_post_of_every_listing_was_read():
    old = _post(1, "old", "2026-10-11T19:20:03.650Z", "2026-10-11T18:47:49.468Z", "2026-10-11T19:20:03.650Z")
    full = {"drafts": [{"posts": [old], "offset": 0, "limit": 25, "total": 1, "isCapped": False}],
            "scheduled": [{"posts": [], "offset": 0, "limit": 25, "total": 0, "isCapped": False}],
            "published": [{"posts": [old], "offset": 0, "limit": 25, "total": 2, "isCapped": False},
                          {"posts": [old], "offset": 25, "limit": 25, "total": 2, "isCapped": False}]}
    items, complete = mod.parse_substack(full)
    assert complete is True and len(items) == 3
    short = {**full, "published": full["published"][:1]}
    assert mod.parse_substack(short)[1] is False
    with pytest.raises(ValueError):
        mod.parse_substack({"drafts": [{"posts": [_post(2, "t", "2026-10-11T19:20:03", None)], "total": 1}]})


X_SINCE = mod._epoch("2026-10-16T04:57:53Z")   # 13:57 JST
X_UNTIL = mod._epoch("2026-10-16T05:16:15Z")


def _xrow(tab, edit_id, date, title, saved=True):
    head = "Draft\n·\nLast saved \n" if tab == "drafts" else "Published\n·\n"
    return {"tab": tab, "href": f"/compose/articles/edit/{edit_id}",
            "text": f"{head}{date}\n{title}\n本文の抜粋がここに続く"}


X_DATA = {"url": "https://x.com/compose/articles", "identity": "diceai0", "expected": "diceai0",
          "rows": [_xrow("drafts", "2101148453665656832", "Sep 19", "「量産」が売上を増やすわけではない"),
                   _xrow("drafts", "2090757937904152576", "Aug 21", "(Needs title)"),
                   _xrow("published", "2101130889136832512", "Sep 19", "Xの投稿を売り込みにしない"),
                   _xrow("published", "2101108578518175744", "Sep 19", "Xから有料ガイドへ送るなら")]}


def _x(data, anchor="2101130889136832512"):
    return mod.parse_x(data, anchor, since=X_SINCE, until=X_UNTIL)


def test_x_rows_parse_title_and_date_and_need_both_tabs_and_the_published_anchor():
    items, complete = _x(X_DATA)
    assert complete is True
    assert [i["title"] for i in items][:2] == ["「量産」が売上を増やすわけではない", "(Needs title)"]
    assert mod.judge(items, since=X_SINCE, until=X_UNTIL, titles=TITLES, complete=complete)["status"] == "absent"
    assert _x(X_DATA, anchor="999")[1] is False
    assert _x(X_DATA, anchor="")[1] is False
    no_drafts = {**X_DATA, "rows": [r for r in X_DATA["rows"] if r["tab"] == "published"]}
    assert _x(no_drafts)[1] is False


def test_x_run_day_or_relative_date_or_title_is_present():
    for date, title in (("Oct 16", "別の記事"), ("5h", "別の記事"), ("Sep 19", TITLES[0])):
        data = {**X_DATA, "rows": [_xrow("drafts", "1", date, title)] + X_DATA["rows"]}
        items, complete = _x(data)
        assert mod.judge(items, since=X_SINCE, until=X_UNTIL, titles=TITLES, complete=complete)["status"] == "present"


def test_x_unparseable_rows_identity_or_order_are_unreadable():
    bad_rows = [
        {"tab": "drafts", "href": "/compose/articles/edit/1", "text": " \n"},
        {"tab": "drafts", "href": "/compose/articles/edit/1", "text": "Draft\n·\nLast saved \nSep 19\n"},
        {"tab": "drafts", "href": "/compose/articles/edit/1", "text": "Draft\n·\nsomeday\nTitle"},
    ]
    for row in bad_rows:
        with pytest.raises(ValueError):
            _x({**X_DATA, "rows": [row] + X_DATA["rows"]})
    with pytest.raises(ValueError):
        _x({**X_DATA, "identity": "someoneelse"})
    with pytest.raises(ValueError):
        _x({**X_DATA, "url": "https://x.com/i/jf/onboarding/web?mode=login"})
    older_first = {**X_DATA, "rows": [_xrow("drafts", "3", "Aug 1", "a"), _xrow("drafts", "4", "Sep 1", "b")]
                   + X_DATA["rows"][2:]}
    assert _x(older_first)[1] is False


def test_ledger_anchor_takes_the_newest_publication_before_the_window():
    rows = [{"platform": "note", "published": True, "published_at": "2026-09-29T02:44:15Z", "public_id": "a"},
            {"platform": "note", "published": True, "published_at": "2026-10-11T18:59:36Z", "public_id": "b"},
            {"platform": "note", "published": True, "published_at": "2026-10-17T00:00:00Z", "public_id": "late"},
            {"platform": "note", "published": False, "published_at": "2026-10-12T00:00:00Z", "public_id": "c"}]
    assert mod.ledger_anchor(rows, "note", mod._epoch(SINCE_ISO_AFTER), "public_id") == "b"


def test_collect_turns_any_reader_error_into_unreadable(tmp_path):
    (tmp_path / "article-ja.md").write_text("# 見出し\n")
    ok = lambda s, r: ([], True, {})
    def boom(s, r):
        raise ValueError("timezone-naive timestamp")
    out = mod.collect(tmp_path, SINCE, UNTIL, readers={"note/ja": ok, "substack/ja": ok,
                                                       "substack/en": ok, "x-article/ja": boom}, ledger_rows=[])
    assert out["destinations"]["note/ja"]["status"] == "absent"
    assert out["destinations"]["x-article/ja"]["status"] == "unreadable"
