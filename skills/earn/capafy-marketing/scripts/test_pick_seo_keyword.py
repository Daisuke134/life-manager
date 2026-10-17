import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pick_seo_keyword import pick  # noqa: E402


def test_picks_first_keyword_whose_page_is_not_published(tmp_path):
    kws = [{"query": "tiktok hook ideas", "lang": "en", "slug": "tiktok-hook-ideas"},
           {"query": "hooks for podcasts", "lang": "en", "slug": "hooks-for-podcasts"},
           {"query": "ganchos para shorts", "lang": "es", "slug": "ganchos-para-shorts"}]
    (tmp_path / "tiktok-hook-ideas.json").write_text("{}")
    assert pick(kws, tmp_path)["slug"] == "hooks-for-podcasts"


def test_returns_none_when_every_keyword_is_published(tmp_path):
    kws = [{"query": "a", "lang": "en", "slug": "a"}]
    (tmp_path / "a.json").write_text("{}")
    assert pick(kws, tmp_path) is None


def test_shipped_keyword_list_is_valid_and_unique():
    kws = json.loads((Path(__file__).resolve().parents[1] / "seo" / "hook-lab-keywords.json").read_text())
    slugs = [k["slug"] for k in kws]
    assert len(kws) >= 40 and len(set(slugs)) == len(slugs)
    assert all(k["query"] and k["lang"] in {"en", "es", "pt", "ja", "de", "fr", "id", "it"} for k in kws)
    assert all(s == s.lower() and " " not in s and not s.startswith("capafy-") for s in slugs)
