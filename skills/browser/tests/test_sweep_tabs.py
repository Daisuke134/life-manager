import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sweep_tabs import tabs_to_close  # noqa: E402


def page(i, url):
    return {"id": str(i), "type": "page", "url": url}


def test_keeps_first_http_tab_and_closes_the_leak():
    # 2026-10-18: the lancers owner leaked one tab per run (6 tabs in 6 h, 1.5 GB).
    pages = [page(1, "about:blank"), page(2, "https://www.lancers.jp/a"), page(3, "https://www.lancers.jp/b"),
             page(4, "https://www.lancers.jp/c"), {"id": "sw", "type": "service_worker", "url": "https://x"}]
    assert tabs_to_close(pages) == ["1", "3", "4"]


def test_leaves_small_tab_counts_alone():
    assert tabs_to_close([page(1, "https://a"), page(2, "https://b"), page(3, "https://c")]) == []
