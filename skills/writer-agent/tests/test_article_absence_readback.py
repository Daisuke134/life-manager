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
