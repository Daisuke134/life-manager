"""seo_keyword_seed.py: OpenSEO target keyword per Capafy skill, cached 30 days.

Covers the goal from #6110 follow-up: capafy-skills article runs should target a
real keyword, but never spend more than one OpenSEO call per skill per month and
never fail the article run when OpenSEO is unavailable.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "products.json"
SCRIPT_PATH = ROOT / "scripts" / "seo_keyword_seed.py"


def load_module():
    spec = importlib.util.spec_from_file_location("seo_keyword_seed", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


HOOK_CORE_TERMS = ["hook", "hooks"]

ROWS_FIXTURE = [
    {"keyword": "generic head term", "searchVolume": 500000, "keywordDifficulty": 95, "intent": "informational"},
    {"keyword": "best hook keyword", "searchVolume": 12000, "keywordDifficulty": 20, "intent": "informational"},
    {"keyword": "second choice hook keyword", "searchVolume": 9000, "keywordDifficulty": 15, "intent": "commercial"},
    {"keyword": "low volume niche hook term", "searchVolume": 300, "keywordDifficulty": 5, "intent": "informational"},
    {"keyword": "wrong intent hook keyword", "searchVolume": 999999, "keywordDifficulty": 1, "intent": "navigational"},
    {"keyword": "hooks with no kd data", "searchVolume": 5000, "keywordDifficulty": None, "intent": "commercial"},
    {"keyword": "off topic keyword with high volume", "searchVolume": 800000, "keywordDifficulty": 10, "intent": "informational"},
]


def test_pick_keywords_excludes_high_kd_head_term_and_wrong_intent():
    module = load_module()
    picked = module.pick_keywords(ROWS_FIXTURE, HOOK_CORE_TERMS)
    assert picked["primary"] == "best hook keyword"
    assert "generic head term" not in picked["secondary"]
    assert "wrong intent hook keyword" not in picked["secondary"]
    assert "hooks with no kd data" not in picked["secondary"]
    assert picked["metrics"]["primary"]["searchVolume"] == 12000


def test_pick_keywords_rejects_a_candidate_without_the_skills_core_term():
    module = load_module()
    picked = module.pick_keywords(ROWS_FIXTURE, HOOK_CORE_TERMS)
    # "off topic keyword with high volume" beats every hook candidate on volume
    # and KD alone, but it must never be picked because it has no core term.
    assert picked["primary"] != "off topic keyword with high volume"
    assert "off topic keyword with high volume" not in picked["secondary"]


def test_pick_keywords_returns_none_when_no_row_contains_a_core_term():
    module = load_module()
    rows = [{"keyword": "off topic keyword with high volume", "searchVolume": 800000, "keywordDifficulty": 10, "intent": "informational"}]
    assert module.pick_keywords(rows, HOOK_CORE_TERMS) is None


def test_pick_keywords_ignores_core_terms_when_skill_has_none():
    module = load_module()
    # A skill with no seo_core_terms configured keeps the old behavior (no
    # relevance filter) rather than rejecting everything.
    rows = [{"keyword": "off topic keyword with high volume", "searchVolume": 800000, "keywordDifficulty": 10, "intent": "informational"}]
    picked = module.pick_keywords(rows, [])
    assert picked["primary"] == "off topic keyword with high volume"


def test_pick_keywords_returns_none_when_nothing_qualifies():
    module = load_module()
    assert module.pick_keywords([{"keyword": "hook x", "searchVolume": 10, "keywordDifficulty": 90, "intent": "informational"}], HOOK_CORE_TERMS) is None


def test_resolve_uses_fresh_cache_without_any_network_call(tmp_path, monkeypatch):
    module = load_module()
    config = load_config()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cached = {
        "slug": "hook-lab", "seed": "hook for short form video", "fetched_at": 1000.0,
        "primary": "cached keyword", "secondary": ["a", "b"], "metrics": {},
    }
    (cache_dir / "hook-lab.json").write_text(json.dumps(cached), encoding="utf-8")

    def boom(*a, **k):
        raise AssertionError("must not call OpenSEO when cache is fresh")

    monkeypatch.setattr(module, "fetch_live_rows", boom)
    result = module.resolve(
        "hook-lab", config, cache_dir=cache_dir,
        credentials_file=tmp_path / "missing-credentials.json",
        now=1000.0 + 3600,  # one hour later, well inside the 30-day TTL
    )
    assert result["source"] == "cache"
    assert result["primary"] == "cached keyword"


def test_resolve_calls_live_once_and_writes_cache_when_stale(tmp_path, monkeypatch):
    module = load_module()
    config = load_config()
    cache_dir = tmp_path / "cache"
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text(json.dumps({
        "credentials": [{"service": "openseo", "api_key": "test-key"}]
    }), encoding="utf-8")

    calls = []

    def fake_fetch(api_key, project_id, seed):
        calls.append((api_key, project_id, seed))
        return ROWS_FIXTURE

    monkeypatch.setattr(module, "fetch_live_rows", fake_fetch)
    result = module.resolve(
        "hook-lab", config, cache_dir=cache_dir, credentials_file=credentials_file, now=2000.0,
    )
    assert len(calls) == 1
    assert calls[0][0] == "test-key"
    assert result["source"] == "live"
    assert result["primary"] == "best hook keyword"
    written = json.loads((cache_dir / "hook-lab.json").read_text(encoding="utf-8"))
    assert written["primary"] == "best hook keyword"
    assert written["fetched_at"] == 2000.0


def test_resolve_caches_a_no_relevant_match_outcome_without_a_second_call(tmp_path, monkeypatch):
    """The seed for hook-lab can dilute to an off-topic head term (this
    happened live 2026-09-28: seed "hook for short form video" returned zero
    rows containing "hook"). That must fall back to the static seed AND be
    cached for 30 days -- otherwise every single run would re-spend credits
    trying the same seed again."""
    module = load_module()
    config = load_config()
    cache_dir = tmp_path / "cache"
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text(json.dumps({
        "credentials": [{"service": "openseo", "api_key": "test-key"}]
    }), encoding="utf-8")

    calls = []

    def fake_fetch(api_key, project_id, seed):
        calls.append(seed)
        return [{"keyword": "generic video term", "searchVolume": 60500, "keywordDifficulty": 26, "intent": "informational"}]

    monkeypatch.setattr(module, "fetch_live_rows", fake_fetch)
    result = module.resolve(
        "hook-lab", config, cache_dir=cache_dir, credentials_file=credentials_file, now=3000.0,
    )
    assert len(calls) == 1  # exactly one call, no retry with a different seed
    assert result["source"] == "live-no-match"
    assert result["primary"] == config["products"]["capafy-skills"]["skills"]["hook-lab"]["seo_seed"]
    written = json.loads((cache_dir / "hook-lab.json").read_text(encoding="utf-8"))
    assert written["fetched_at"] == 3000.0

    # A second resolve() shortly after must hit the cache, not call live again.
    def boom(*a, **k):
        raise AssertionError("must not call OpenSEO again while the no-match cache is fresh")

    monkeypatch.setattr(module, "fetch_live_rows", boom)
    second = module.resolve(
        "hook-lab", config, cache_dir=cache_dir, credentials_file=credentials_file, now=3600.0,
    )
    assert second["source"] == "cache"


def test_resolve_falls_back_to_stale_cache_when_live_call_fails(tmp_path, monkeypatch):
    module = load_module()
    config = load_config()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    stale = {
        "slug": "hook-lab", "seed": "hook for short form video", "fetched_at": 0.0,
        "primary": "stale but usable keyword", "secondary": [], "metrics": {},
    }
    (cache_dir / "hook-lab.json").write_text(json.dumps(stale), encoding="utf-8")
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text(json.dumps({
        "credentials": [{"service": "openseo", "api_key": "test-key"}]
    }), encoding="utf-8")

    def fake_fetch(*a, **k):
        raise RuntimeError("openseo unavailable")

    monkeypatch.setattr(module, "fetch_live_rows", fake_fetch)
    far_future = 0.0 + module.CACHE_TTL_SECONDS + 3600
    result = module.resolve(
        "hook-lab", config, cache_dir=cache_dir, credentials_file=credentials_file, now=far_future,
    )
    assert result["source"] == "cache-stale"
    assert result["primary"] == "stale but usable keyword"


def test_resolve_falls_back_to_static_seed_with_no_cache_and_no_credentials(tmp_path):
    module = load_module()
    config = load_config()
    result = module.resolve(
        "hook-lab", config,
        cache_dir=tmp_path / "cache",
        credentials_file=tmp_path / "missing-credentials.json",
        now=5000.0,
    )
    assert result["source"] == "static"
    assert result["primary"] == config["products"]["capafy-skills"]["skills"]["hook-lab"]["seo_seed"]
    assert result["secondary"] == []


def test_resolve_never_raises_when_live_call_fails_and_no_cache_exists(tmp_path):
    module = load_module()
    config = load_config()
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text(json.dumps({
        "credentials": [{"service": "openseo", "api_key": "test-key"}]
    }), encoding="utf-8")

    class ExplodingModule:
        pass

    # No monkeypatch here: the real fetch_live_rows will try a real network call
    # to an unreachable host and must be swallowed by resolve()'s except clause.
    import urllib.error

    orig = module.fetch_live_rows

    def fake_unreachable(*a, **k):
        raise urllib.error.URLError("simulated network failure")

    module.fetch_live_rows = fake_unreachable
    try:
        result = module.resolve(
            "hook-lab", config, cache_dir=tmp_path / "cache",
            credentials_file=credentials_file, now=6000.0,
        )
    finally:
        module.fetch_live_rows = orig
    assert result["source"] == "static"


def test_resolve_raises_on_unknown_slug(tmp_path):
    module = load_module()
    config = load_config()
    try:
        module.resolve("not-a-real-skill", config, cache_dir=tmp_path / "cache")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for an unknown slug")


def test_every_capafy_skill_has_a_seo_seed():
    config = load_config()
    for slug, skill in config["products"]["capafy-skills"]["skills"].items():
        assert skill.get("seo_seed"), f"{slug} is missing seo_seed"


def test_every_capafy_skill_has_seo_core_terms():
    config = load_config()
    for slug, skill in config["products"]["capafy-skills"]["skills"].items():
        assert skill.get("seo_core_terms"), f"{slug} is missing seo_core_terms"


def test_cli_prints_one_json_object(tmp_path):
    import subprocess

    out = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--slug", "hook-lab", "--config", str(CONFIG_PATH),
            "--cache-dir", str(tmp_path / "cache"),
            "--credentials-file", str(tmp_path / "missing-credentials.json"),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    result = json.loads(out)
    assert result["slug"] == "hook-lab"
    assert result["source"] == "static"
