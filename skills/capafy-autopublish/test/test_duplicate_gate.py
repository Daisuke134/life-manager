from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "duplicate_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("duplicate_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_listing(tmp_path: Path, name: str, title: str, short_description: str) -> Path:
    path = tmp_path / f"{name}.md"
    path.write_text(f"## Title\n{title}\n\n## shortDescription\n{short_description}\n")
    return path


# ---------------------------------------------------------------------------
# judge_candidate: parses model JSON
# ---------------------------------------------------------------------------

def test_judge_candidate_parses_near_duplicate_verdict() -> None:
    module = load_module()
    candidate = {"title": "Reels Hook Lab — First 3 Seconds", "short_description": "hooks for reels"}
    live = [{"title": "Reels Hook Lab — Win the Cover Frame", "short_description": "cover frame hooks"}]

    def runner(prompt: str) -> str:
        assert "Reels Hook Lab" in prompt
        return '{"verdict": "near_duplicate", "closest": "Reels Hook Lab — Win the Cover Frame", "why": "same input/output/use case"}'

    result = module.judge_candidate(candidate, live, runner)

    assert result == {
        "verdict": "near_duplicate",
        "closest": "Reels Hook Lab — Win the Cover Frame",
        "why": "same input/output/use case",
    }


def test_judge_candidate_parses_distinct_verdict() -> None:
    module = load_module()
    candidate = {"title": "Earnings Call Brief", "short_description": "earnings brief"}
    live = [{"title": "Academic Introduction Humanizer", "short_description": "humanize intros"}]

    def runner(prompt: str) -> str:
        return '{"verdict": "distinct", "closest": "", "why": "different domain"}'

    result = module.judge_candidate(candidate, live, runner)

    assert result["verdict"] == "distinct"


def test_judge_candidate_tolerates_prose_wrapped_json() -> None:
    module = load_module()

    def runner(prompt: str) -> str:
        return 'Sure, here is my answer:\n{"verdict": "distinct", "closest": "", "why": "ok"}\nDone.'

    result = module.judge_candidate({"title": "A", "short_description": ""}, [], runner)

    assert result["verdict"] == "distinct"


# ---------------------------------------------------------------------------
# runner error / bad output => unknown, never raises
# ---------------------------------------------------------------------------

def test_judge_candidate_runner_error_returns_unknown() -> None:
    module = load_module()

    def runner(prompt: str) -> str:
        raise RuntimeError("provider down")

    result = module.judge_candidate({"title": "A", "short_description": ""}, [], runner)

    assert result["verdict"] == "unknown"


def test_judge_candidate_invalid_json_returns_unknown() -> None:
    module = load_module()

    def runner(prompt: str) -> str:
        return "not json at all"

    result = module.judge_candidate({"title": "A", "short_description": ""}, [], runner)

    assert result["verdict"] == "unknown"


def test_judge_candidate_invalid_verdict_value_returns_unknown() -> None:
    module = load_module()

    def runner(prompt: str) -> str:
        return '{"verdict": "maybe", "closest": "", "why": "waffling"}'

    result = module.judge_candidate({"title": "A", "short_description": ""}, [], runner)

    assert result["verdict"] == "unknown"


# ---------------------------------------------------------------------------
# cache: hit skips runner, content change re-judges
# ---------------------------------------------------------------------------

def test_cache_hit_skips_runner(tmp_path: Path) -> None:
    module = load_module()
    cache_path = tmp_path / "verdicts.json"
    listing = make_listing(tmp_path, "cand", "Candidate Title", "desc")
    sha = module.listing_content_sha(listing)
    calls = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return '{"verdict": "distinct", "closest": "", "why": "ok"}'

    candidate = module.read_listing_summary(listing)
    first = module.get_cached_verdict("cand", sha, candidate, [], runner, cache_path=cache_path)
    second = module.get_cached_verdict("cand", sha, candidate, [], runner, cache_path=cache_path)

    assert first == second
    assert len(calls) == 1


def test_cache_content_change_re_judges(tmp_path: Path) -> None:
    module = load_module()
    cache_path = tmp_path / "verdicts.json"
    listing = make_listing(tmp_path, "cand", "Candidate Title", "desc v1")
    calls = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return '{"verdict": "distinct", "closest": "", "why": "ok"}'

    sha1 = module.listing_content_sha(listing)
    candidate1 = module.read_listing_summary(listing)
    module.get_cached_verdict("cand", sha1, candidate1, [], runner, cache_path=cache_path)

    listing.write_text("## Title\nCandidate Title\n\n## shortDescription\ndesc v2\n")
    sha2 = module.listing_content_sha(listing)
    candidate2 = module.read_listing_summary(listing)
    module.get_cached_verdict("cand", sha2, candidate2, [], runner, cache_path=cache_path)

    assert len(calls) == 2
    assert sha1 != sha2


# ---------------------------------------------------------------------------
# is_allowed: the fail-closed gate helper
# ---------------------------------------------------------------------------

def test_is_allowed_true_only_for_fresh_distinct_verdict(tmp_path: Path) -> None:
    module = load_module()
    cache_path = tmp_path / "verdicts.json"
    listing = make_listing(tmp_path, "cand", "Candidate Title", "desc")
    sha = module.listing_content_sha(listing)
    cache_path.write_text(json.dumps({
        "cand": {"content_sha256": sha, "verdict": {"verdict": "distinct", "closest": "", "why": "ok"}}
    }))

    assert module.is_allowed("cand", listing, cache_path=cache_path) is True


def test_is_allowed_false_when_near_duplicate(tmp_path: Path) -> None:
    module = load_module()
    cache_path = tmp_path / "verdicts.json"
    listing = make_listing(tmp_path, "cand", "Candidate Title", "desc")
    sha = module.listing_content_sha(listing)
    cache_path.write_text(json.dumps({
        "cand": {"content_sha256": sha, "verdict": {"verdict": "near_duplicate", "closest": "X", "why": "ok"}}
    }))

    assert module.is_allowed("cand", listing, cache_path=cache_path) is False


def test_is_allowed_false_when_no_cache_entry(tmp_path: Path) -> None:
    module = load_module()
    cache_path = tmp_path / "verdicts.json"
    listing = make_listing(tmp_path, "cand", "Candidate Title", "desc")

    assert module.is_allowed("cand", listing, cache_path=cache_path) is False


def test_is_allowed_false_when_content_changed_since_judged(tmp_path: Path) -> None:
    module = load_module()
    cache_path = tmp_path / "verdicts.json"
    listing = make_listing(tmp_path, "cand", "Candidate Title", "desc")
    stale_sha = "sha256:" + "0" * 64
    cache_path.write_text(json.dumps({
        "cand": {"content_sha256": stale_sha, "verdict": {"verdict": "distinct", "closest": "", "why": "ok"}}
    }))

    assert module.is_allowed("cand", listing, cache_path=cache_path) is False


def test_is_allowed_false_when_unknown(tmp_path: Path) -> None:
    module = load_module()
    cache_path = tmp_path / "verdicts.json"
    listing = make_listing(tmp_path, "cand", "Candidate Title", "desc")
    sha = module.listing_content_sha(listing)
    cache_path.write_text(json.dumps({
        "cand": {"content_sha256": sha, "verdict": {"verdict": "unknown", "closest": "", "why": "runner_error"}}
    }))

    assert module.is_allowed("cand", listing, cache_path=cache_path) is False


# ---------------------------------------------------------------------------
# read_listing_summary
# ---------------------------------------------------------------------------

def test_read_listing_summary_extracts_title_and_description(tmp_path: Path) -> None:
    module = load_module()
    listing = make_listing(tmp_path, "cand", "My Title", "My short description.")

    summary = module.read_listing_summary(listing)

    assert summary == {"title": "My Title", "short_description": "My short description."}


def test_read_listing_summary_missing_file_returns_empty_strings(tmp_path: Path) -> None:
    module = load_module()

    summary = module.read_listing_summary(tmp_path / "missing.md")

    assert summary == {"title": "", "short_description": ""}
