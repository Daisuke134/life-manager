#!/usr/bin/env python3
"""duplicate_gate.py — model-judged near-duplicate gate for new Capafy listings.

WHY (Capafy review guideline, capafy.ai/developer/doc/4.2): "Do not mass-upload
large numbers of Agents with near-identical functionality or minimal variations
to dominate search results. This behavior is treated as cheating; the related
Agents will be removed and the Publisher account may be warned or suspended."
Our account already carries ~16 near-identical academic Humanizer/Voice Editor
agents and 5-6 Hook Lab variants (all $0 sales); the ready backlog queues more
near-duplicates. This module stops the factory from shipping another one.

PRINCIPLE (building-agents): the near-duplicate JUDGMENT comes from a model,
never from keyword/regex rules — two listings about "reels hooks" are not
duplicates because they share a word, and two listings with zero shared words
can still be functionally identical. This file is deliberately dumb: it builds
the prompt, calls a runner, parses + caches the verdict. It never decides
"near-duplicate" on its own via string matching.

Runner choice: skills/writer-agent/runtime/model-runner.sh is the house model
boundary, but it is scoped to the Writer article pipeline — every call requires
ARTICLE_PROVIDER/ARTICLE_RUN_ID/ARTICLE_MODEL_LOG identity plus (for judge mode)
a live judge-broker process, and no Capafy script calls it today (grepped empty).
Wiring that run-scoped identity + broker plumbing in for one classification call
is not reuse, it is importing a foreign subsystem. Per the task's documented
fallback, this uses the real `claude` CLI binary directly in print mode, run
with cwd=/tmp (house rule for a bounded, no-side-effect model call), using
--model haiku: the cheapest available Claude tier, matching the spirit of
"DeepSeek-class / cheap" for a short classification call.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable

STATE_HOME = Path(os.environ.get(
    "LIFE_MANAGER_STATE_HOME", Path.home() / ".local/state/life-manager"
)).expanduser()
DEFAULT_VERDICTS_PATH = STATE_HOME / "state/capafy-duplicate-verdicts.json"

_VALID_VERDICTS = {"distinct", "near_duplicate"}

# Two canonical few-shot examples, per the task: a real near_duplicate pair
# already live in this account's backlog, and a real distinct pair.
_FEWSHOT = """Example A:
Candidate: "Reels Hook Lab — First 3 Seconds" — Turn a pasted Instagram Reels brief, transcript, or rough opening into a first-three-seconds diagnosis, five text hooks, caption options, and a shot-list blueprint.
Live listing: "Reels Hook Lab — Win the Cover Frame" — Turn a pasted Instagram Reels brief into a cover-frame diagnosis, hook options, and caption variants for the opening seconds.
Verdict: {"verdict": "near_duplicate", "closest": "Reels Hook Lab — Win the Cover Frame", "why": "Same input (a pasted Reels brief), same output shape (hooks plus captions for the opening seconds), same use case."}

Example B:
Candidate: "Earnings Call Brief — Pasted Results to Questions" — Paste an earnings-call excerpt, shareholder letter, and your figures for each reporting period; get a source-bounded brief that separates reported facts, management statements, changes, and open questions.
Live listing: "Academic Introduction Humanizer" — Rewrite a pasted academic introduction section to read less like AI-generated text while preserving claims.
Verdict: {"verdict": "distinct", "closest": "", "why": "Different input domain (earnings transcripts vs. academic prose), different output (a results brief vs. a rewritten paragraph), different use case."}
"""


def listing_content_sha(listing_path) -> str:
    """sha256 of the LISTING.md bytes. Missing file hashes as empty content."""
    try:
        data = Path(listing_path).read_bytes()
    except OSError:
        data = b""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def read_listing_summary(listing_path) -> dict:
    """Extract {"title": ..., "short_description": ...} from a LISTING.md file.
    Missing file or missing sections => empty strings (never raises)."""
    try:
        text = Path(listing_path).read_text(encoding="utf-8")
    except OSError:
        return {"title": "", "short_description": ""}
    sections = _split_sections(text)
    return {
        "title": sections.get("title", "").strip(),
        "short_description": sections.get("shortdescription", "").strip(),
    }


def _split_sections(text: str) -> dict:
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = match.group(1).strip().lower()
            buf = []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _build_prompt(candidate: dict, live_listings: list[dict]) -> str:
    candidate_block = (
        f"Title: {candidate.get('title', '')}\n"
        f"Description: {candidate.get('short_description', '')}"
    )
    if live_listings:
        live_block = "\n\n".join(
            f"- Title: {listing.get('title', '')}\n"
            f"  Description: {listing.get('short_description', '')}"
            for listing in live_listings
        )
    else:
        live_block = "(no live listings on the account yet)"
    return (
        "You review Capafy marketplace listings for the Capafy 4.2 anti-duplication "
        "rule: \"Do not mass-upload large numbers of Agents with near-identical "
        "functionality or minimal variations to dominate search results.\"\n\n"
        f"{_FEWSHOT}\n"
        "Now judge this real case.\n\n"
        f"Candidate (not yet published):\n{candidate_block}\n\n"
        f"Live listings already on the account:\n{live_block}\n\n"
        "Would a Capafy reviewer see the candidate as near-identical functionality or "
        "a minimal variation of ANY ONE live listing above (substantially the same "
        "input, output, and use case)? Reply with ONLY one line of strict JSON, no "
        "prose, no markdown fence:\n"
        '{"verdict": "distinct"|"near_duplicate", "closest": "<exact title of the '
        'closest live listing, or empty string if none is close>", "why": "<one '
        'sentence>"}'
    )


def _parse_verdict(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        return {"verdict": "unknown", "closest": "", "why": "no_json_in_model_output"}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"verdict": "unknown", "closest": "", "why": "invalid_json_in_model_output"}
    verdict = data.get("verdict") if isinstance(data, dict) else None
    if verdict not in _VALID_VERDICTS:
        return {"verdict": "unknown", "closest": "", "why": "invalid_verdict_value"}
    closest = data.get("closest")
    why = data.get("why")
    return {
        "verdict": verdict,
        "closest": str(closest) if closest else "",
        "why": str(why)[:300] if why else "",
    }


def judge_candidate(candidate: dict, live_listings: list[dict], runner: Callable[[str], str]) -> dict:
    """Ask the model whether `candidate` is a near-duplicate of any `live_listings`
    entry. Never raises: a runner error or unparsable output becomes "unknown"."""
    prompt = _build_prompt(candidate, live_listings)
    try:
        raw = runner(prompt)
    except Exception as exc:  # noqa: BLE001 — runner failures must not propagate
        return {"verdict": "unknown", "closest": "", "why": f"runner_error: {exc}"[:300]}
    return _parse_verdict(raw)


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------

def _load_cache(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write_cache(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def get_cached_verdict(
    candidate_key: str,
    content_sha: str,
    candidate: dict,
    live_listings: list[dict],
    runner: Callable[[str], str],
    cache_path: Path | None = None,
) -> dict:
    """Return the cached verdict for `candidate_key` at `content_sha`, judging (and
    persisting) only on a cache miss or a content change."""
    cache_path = Path(cache_path) if cache_path is not None else DEFAULT_VERDICTS_PATH
    cache = _load_cache(cache_path)
    entry = cache.get(candidate_key)
    if entry and entry.get("content_sha256") == content_sha:
        return entry["verdict"]
    verdict = judge_candidate(candidate, live_listings, runner)
    cache[candidate_key] = {"content_sha256": content_sha, "verdict": verdict}
    _atomic_write_cache(cache_path, cache)
    return verdict


def is_allowed(candidate_key: str, listing_path, cache_path: Path | None = None) -> bool:
    """Fail-closed publish gate: True only when the cache holds a 'distinct' verdict
    for `candidate_key` whose stored content sha matches the listing's CURRENT
    content. A missing entry, a stale sha (content changed since judged), or a
    non-distinct verdict (near_duplicate or unknown) => False."""
    cache_path = Path(cache_path) if cache_path is not None else DEFAULT_VERDICTS_PATH
    cache = _load_cache(cache_path)
    entry = cache.get(candidate_key)
    if not entry:
        return False
    if entry.get("content_sha256") != listing_content_sha(listing_path):
        return False
    verdict = entry.get("verdict") or {}
    return verdict.get("verdict") == "distinct"


# --------------------------------------------------------------------------
# default runner — real claude CLI, print mode, cwd=/tmp, cheapest tier
# --------------------------------------------------------------------------

def runner_env(base=None) -> dict:
    """launchd omits USER; the claude CLI then reports "Not logged in". Same fix as
    runtime/agent-runner/agent_runner.py: fill USER/LOGNAME from the uid."""
    import pwd
    env = dict(os.environ if base is None else base)
    name = pwd.getpwuid(os.getuid()).pw_name
    env.setdefault("USER", name)
    env.setdefault("LOGNAME", name)
    return env


def default_runner(prompt: str) -> str:
    claude_bin = os.environ.get("CAPAFY_DUPGATE_CLAUDE_BIN") or str(Path.home() / ".local/bin/claude")
    result = subprocess.run(
        [
            claude_bin, "-p", prompt,
            "--setting-sources", "",
            "--system-prompt",
            "You are a strict Capafy listing-review classifier. Reply with exactly "
            "one line of JSON and nothing else.",
            "--model", "haiku",
        ],
        cwd="/tmp",
        capture_output=True,
        text=True,
        env=runner_env(),
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {(result.stderr or '').strip()[:300]}")
    return result.stdout


if __name__ == "__main__":
    import sys

    def _demo() -> None:
        calls = {"n": 0}

        def fake_runner(prompt: str) -> str:
            calls["n"] += 1
            return '{"verdict": "near_duplicate", "closest": "Live X", "why": "same shape"}'

        result = judge_candidate(
            {"title": "Candidate", "short_description": "desc"},
            [{"title": "Live X", "short_description": "desc2"}],
            fake_runner,
        )
        assert result["verdict"] == "near_duplicate"
        assert result["closest"] == "Live X"

        def erroring_runner(prompt: str) -> str:
            raise RuntimeError("boom")

        failed = judge_candidate({"title": "A", "short_description": ""}, [], erroring_runner)
        assert failed["verdict"] == "unknown"
        print("duplicate_gate self-check OK", file=sys.stderr)

    _demo()
