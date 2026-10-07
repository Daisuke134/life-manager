#!/usr/bin/env python3
"""Hourly LINE animated-sticker FACTORY owner.

One wake advances the newest open set by exactly one stage, persists a stage marker, and
exits. A new set starts only when no set is mid-pipeline and fewer than
LINE_STICKER_MAX_SETS_PER_DAY sets were started today (JST).

Stages: plan -> character -> clips -> apng -> select -> package -> submit -> submitted

``submit`` is fenced by ``creators-item.json``: once an item exists on LINE Creators Market
its product_id/url are durable there, and a later wake resumes from that item (reads the
page back) instead of creating a new one. The set only reaches the terminal "submitted"
stage once creators-item.json records state "review_requested".

All judgment (series-of-existing-character vs new flagship, theme/character/motion plan,
24-of-30 selection, listing copy, tags) is delegated to the model via ``deps.planner`` /
``deps.selector``; this module is bookkeeping, API plumbing and browser steps only. The one
exception is mechanical: when the plan names ``series_of``, the character stage copies that
prior set's reference art instead of generating a new one (zero image cost).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import seedance_set  # noqa: E402

STAGES = ("plan", "character", "clips", "apng", "select", "package", "submit", "submitted")
DEFAULT_STATE_ROOT = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", str(Path.home() / ".local/state/life-manager"))) / "line-sticker"
DEFAULT_MAX_SETS_PER_DAY = int(os.environ.get("LINE_STICKER_MAX_SETS_PER_DAY", "24"))
DEFAULT_MAX_USD_PER_SET = Decimal(os.environ.get("LINE_STICKER_MAX_USD_PER_SET", "4"))
JST = datetime.timezone(datetime.timedelta(hours=9))
EVENTS_LOG_NAME = "factory-events.jsonl"


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    tmp.replace(path)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def append_event(state_root: Path, row: dict) -> None:
    path = state_root / EVENTS_LOG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": now_utc().isoformat(), **row}
    with path.open("a") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------------------
# Set discovery and stage bookkeeping
# --------------------------------------------------------------------------------------

def list_set_dirs(state_root: Path) -> list[Path]:
    if not state_root.exists():
        return []
    return sorted(
        (p for p in state_root.iterdir() if p.is_dir() and p.name.startswith("set-") and p.name[4:].isdigit()),
        key=lambda p: int(p.name[4:]),
    )


def next_set_number(state_root: Path) -> int:
    dirs = list_set_dirs(state_root)
    if not dirs:
        return 1
    return max(int(p.name[4:]) for p in dirs) + 1


def read_stage(set_dir: Path) -> str:
    item = _read_json(set_dir / "creators-item.json")
    if item is not None and item.get("state") == "review_requested":
        return "submitted"
    stage_row = _read_json(set_dir / "stage.json")
    if stage_row is not None and stage_row.get("stage") in STAGES:
        return stage_row["stage"]
    return "plan"


def write_stage(set_dir: Path, stage: str, *, started_at: str | None = None) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    existing = _read_json(set_dir / "stage.json") or {}
    row = {
        "stage": stage,
        "started_at": started_at or existing.get("started_at") or now_utc().isoformat(),
        "updated_at": now_utc().isoformat(),
        "cost_usd": existing.get("cost_usd", "0"),
    }
    _atomic_write_json(set_dir / "stage.json", row)


def add_cost(set_dir: Path, usd: Decimal) -> Decimal:
    row = _read_json(set_dir / "stage.json") or {"stage": "plan", "started_at": now_utc().isoformat()}
    total = Decimal(str(row.get("cost_usd", "0"))) + usd
    row["cost_usd"] = str(total)
    row["updated_at"] = now_utc().isoformat()
    _atomic_write_json(set_dir / "stage.json", row)
    return total


def newest_open_set(state_root: Path) -> Path | None:
    dirs = list_set_dirs(state_root)
    if not dirs:
        return None
    latest = dirs[-1]
    return None if read_stage(latest) == "submitted" else latest


def sets_started_today(state_root: Path, *, today: datetime.date | None = None) -> int:
    today = today or now_utc().astimezone(JST).date()
    count = 0
    for set_dir in list_set_dirs(state_root):
        row = _read_json(set_dir / "stage.json")
        started_at = row.get("started_at") if row else None
        if started_at is None:
            # A set with no stage.json yet (mid-"plan") started now; count it for today.
            count += 1
            continue
        try:
            started = datetime.datetime.fromisoformat(started_at).astimezone(JST).date()
        except ValueError:
            continue
        if started == today:
            count += 1
    return count


# --------------------------------------------------------------------------------------
# Dependency bundle: production implementations, all overridable for tests.
# --------------------------------------------------------------------------------------

@dataclass
class Deps:
    planner: Callable[[Path, list[dict]], dict]
    character_image: Callable[[Path, dict], None]
    clips_runner: Callable[[Path, dict], None]
    apng_runner: Callable[[Path, dict], None]
    selector: Callable[[Path, dict], dict]
    packager: Callable[[Path, Path, list[str], str, str], None]
    validator: Callable[[Path], dict]
    submit: Callable[[Path, dict, dict, dict], dict]
    notify: Callable[[Path, dict], None] = field(default=lambda set_dir, payload: None)
    max_usd_per_set: Decimal = DEFAULT_MAX_USD_PER_SET
    max_sets_per_day: int = DEFAULT_MAX_SETS_PER_DAY


def _prior_set_facts(state_root: Path) -> list[dict]:
    """Series-planning context for the planner: one row per prior set, naming its character,
    theme and latest official LINE Creators Market status so the model can judge a sequel vs a
    new flagship (judgment stays in the prompt, not here)."""
    facts = []
    for set_dir in list_set_dirs(state_root):
        draft = _read_json(set_dir / "plan-draft.json")
        listing = _read_json(set_dir / "listing.json")
        item = _read_json(set_dir / "creators-item.json")
        if draft is None and listing is None:
            continue
        facts.append({
            "set": set_dir.name,
            "character_id": (draft or {}).get("character_id"),
            "character_description": (draft or {}).get("character_prompt"),
            "theme": (draft or {}).get("theme"),
            "title": (listing or {}).get("title"),
            "state_observed": (item or {}).get("state_observed"),
        })
    return facts


# --------------------------------------------------------------------------------------
# Stage runners (pure state transitions; each returns the next stage or raises)
# --------------------------------------------------------------------------------------

def run_plan(set_dir: Path, state_root: Path, deps: Deps) -> str:
    plan = deps.planner(set_dir, _prior_set_facts(state_root))
    _atomic_write_json(set_dir / "plan-draft.json", plan)
    _atomic_write_json(set_dir / "listing.json", plan["listing"])
    return "character"


def run_character(set_dir: Path, state_root: Path, deps: Deps) -> str:
    plan_draft = _read_json(set_dir / "plan-draft.json")
    if plan_draft is None:
        raise RuntimeError("missing plan-draft.json for character stage")
    series_of = plan_draft.get("series_of")
    source_dir = state_root / series_of if isinstance(series_of, str) and re.fullmatch(r"set-\d{3}", series_of) else None
    # A missing/unsafe/incomplete sequel source falls back to a fresh character instead of wedging this stage.
    if source_dir and (source_dir / "char-ref.png").is_file() and (source_dir / "ref-padded.png").is_file():
        # Sequel of an existing character: reuse its reference art, zero image cost.
        shutil.copy2(source_dir / "char-ref.png", set_dir / "char-ref.png")
        shutil.copy2(source_dir / "ref-padded.png", set_dir / "ref-padded.png")
        _atomic_write_json(set_dir / "char-ref.receipt.json", {"reused": True, "source_set": series_of})
    else:
        deps.character_image(set_dir, plan_draft)
    seedance_plan = {
        "reference": "ref-padded.png",
        "motions": [
            {"id": m["id"], "prompt": m["prompt"],
             "start": m.get("start") if m.get("start") is not None else 0.0,
             "seconds": m.get("seconds") if m.get("seconds") is not None else 2.0,
             "plays": m.get("plays") if m.get("plays") is not None else 2}
            for m in plan_draft["motions"]
        ],
    }
    _atomic_write_json(set_dir / "plan.json", seedance_plan)
    return "clips"


def run_clips(set_dir: Path, deps: Deps) -> str:
    plan = _read_json(set_dir / "plan.json")
    deps.clips_runner(set_dir, plan)
    receipts = [_read_json(set_dir / "clips" / f"{m['id']}.json") for m in plan["motions"]]
    spent = sum((Decimal(str(r["estimated_usd"])) for r in receipts if r and "estimated_usd" in r), Decimal("0"))
    row = _read_json(set_dir / "stage.json") or {}
    _atomic_write_json(set_dir / "stage.json", {**row, "cost_usd": str(spent)})
    missing = [m["id"] for m in plan["motions"] if not (set_dir / "clips" / f"{m['id']}.json").exists()]
    if missing:
        append_event(set_dir.parent, {"set": set_dir.name, "stage": "clips", "status": "incomplete", "missing": missing})
        return "clips"
    return "apng"


def run_apng(set_dir: Path, deps: Deps) -> str:
    plan = _read_json(set_dir / "plan.json")
    deps.apng_runner(set_dir, plan)
    return "select"


def run_select(set_dir: Path, state_root: Path, deps: Deps) -> str:
    plan = _read_json(set_dir / "plan.json")
    selection = deps.selector(set_dir, plan)
    _atomic_write_json(set_dir / "select.json", selection)
    listing = _read_json(set_dir / "listing.json") or {}
    listing.update(selection.get("listing", {}))
    draft = _read_json(set_dir / "plan-draft.json") or {}
    character_id = draft.get("character_id", "")
    listing["character_name"] = " ".join(part.capitalize() for part in character_id.split("-")[1:] if not part.isdigit())
    listing["main"] = selection["main"]
    listing["tab"] = selection["tab"]
    listing.setdefault("type", "animated_sticker")
    listing.setdefault("count", 24)
    listing.setdefault("copyright", "anicca")
    listing.setdefault("price_jpy", 250)
    listing.setdefault("regions", "all")
    _atomic_write_json(set_dir / "listing.json", listing)
    tags_by_number = {row["sticker_number"]: row["tags"] for row in selection["tags"]}
    _atomic_write_json(set_dir / "tags.json", tags_by_number)
    return "package"


def run_package(set_dir: Path, deps: Deps) -> str:
    plan_path = set_dir / "plan.json"
    selection = _read_json(set_dir / "select.json")
    deps.packager(set_dir, plan_path, selection["order"], selection["main"], selection["tab"])
    result = deps.validator(set_dir / "package")
    if result.get("status") != "ready":
        append_event(set_dir.parent, {"set": set_dir.name, "stage": "package", "status": "not_ready", "reason": result})
        return "package"
    return "submit"


def run_submit(set_dir: Path, deps: Deps) -> str:
    listing = _read_json(set_dir / "listing.json")
    tags = _read_json(set_dir / "tags.json")
    plan = _read_json(set_dir / "plan.json")
    item = _read_json(set_dir / "creators-item.json") or {}
    item = deps.submit(set_dir, item, listing, tags)
    _atomic_write_json(set_dir / "creators-item.json", item)
    if item.get("state") == "review_requested":
        # Submitted: drop intermediates that nothing reads again so sets do not fill the host disk.
        # Keep package/, the character art (sequels reuse it), candidates-sheet.png (retag) and the
        # 24 selected clips/*.mp4 (line-sticker-distribute renders posts from them).
        shutil.rmtree(set_dir / "candidates", ignore_errors=True)
        chosen = set((_read_json(set_dir / "select.json") or {}).get("order", []))
        if chosen:
            for clip in (set_dir / "clips").glob("*.mp4"):
                if clip.stem not in chosen:
                    clip.unlink(missing_ok=True)
        deps.notify(set_dir, {"product_id": item.get("product_id"), "title_ja": listing.get("title", {}).get("ja"),
                               "cost_usd": (_read_json(set_dir / "stage.json") or {}).get("cost_usd")})
        return "submitted"
    return "submit"


STAGE_RUNNERS = {
    "plan": lambda set_dir, state_root, deps: run_plan(set_dir, state_root, deps),
    "character": lambda set_dir, state_root, deps: run_character(set_dir, state_root, deps),
    "clips": lambda set_dir, state_root, deps: run_clips(set_dir, deps),
    "apng": lambda set_dir, state_root, deps: run_apng(set_dir, deps),
    "select": lambda set_dir, state_root, deps: run_select(set_dir, state_root, deps),
    "package": lambda set_dir, state_root, deps: run_package(set_dir, deps),
    "submit": lambda set_dir, state_root, deps: run_submit(set_dir, deps),
}


# --------------------------------------------------------------------------------------
# Wake entry point
# --------------------------------------------------------------------------------------

def wake(state_root: Path, deps: Deps) -> dict:
    """Advance exactly one stage of exactly one set. Returns a small report dict."""
    set_dir = newest_open_set(state_root)
    if set_dir is None:
        started = sets_started_today(state_root)
        if started >= deps.max_sets_per_day:
            return {"action": "skip", "reason": "daily_cap_reached", "started_today": started}
        number = next_set_number(state_root)
        set_dir = state_root / f"set-{number:03d}"
        set_dir.mkdir(parents=True, exist_ok=True)
        write_stage(set_dir, "plan")
        append_event(state_root, {"set": set_dir.name, "stage": "plan", "status": "started"})

    stage = read_stage(set_dir)
    if stage == "submitted":
        return {"action": "noop", "set": set_dir.name, "stage": stage}

    row = _read_json(set_dir / "stage.json")
    cost_so_far = Decimal(str((row or {}).get("cost_usd", "0")))
    if stage != "submit" and cost_so_far > deps.max_usd_per_set:
        append_event(state_root, {"set": set_dir.name, "stage": stage, "status": "cost_cap_exceeded", "cost_usd": str(cost_so_far)})
        return {"action": "halt", "set": set_dir.name, "stage": stage, "reason": "cost_cap_exceeded"}

    runner = STAGE_RUNNERS[stage]
    next_stage = runner(set_dir, state_root, deps)
    if next_stage != stage:
        write_stage(set_dir, next_stage)
    append_event(state_root, {"set": set_dir.name, "stage": stage, "next_stage": next_stage, "status": "advanced" if next_stage != stage else "retry"})
    return {"action": "advanced" if next_stage != stage else "retry", "set": set_dir.name, "stage": stage, "next_stage": next_stage}


# --------------------------------------------------------------------------------------
# Production dependency wiring (real APIs / browser). Imported lazily so tests never
# need FAL_KEY, GEMINI_API_KEY, or a browser lease.
# --------------------------------------------------------------------------------------

def production_deps() -> Deps:
    from line_sticker_planner import planner, character_image, selector  # noqa: E402 (local import keeps tests dependency-free)
    from line_sticker_submit import submit as browser_submit  # noqa: E402
    from line_sticker_notify import notify  # noqa: E402

    def clips_runner(set_dir: Path, plan: dict) -> None:
        seedance_set.clips(set_dir, plan)

    def apng_runner(set_dir: Path, plan: dict) -> None:
        seedance_set.apng(set_dir, plan)

    def packager(set_dir: Path, plan_path: Path, order: list[str], main_id: str, tab_id: str) -> None:
        seedance_set.package(set_dir, plan_path, order, main_id, tab_id)

    def validator(package_dir: Path) -> dict:
        policy = HERE / "official-policy.json"
        result = subprocess.run(
            [sys.executable, str(HERE / "line_sticker.py"), "validate", "--package", str(package_dir), "--policy", str(policy)],
            capture_output=True, text=True, check=False,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"status": "error", "errors": [result.stdout, result.stderr]}

    return Deps(
        planner=planner, character_image=character_image, clips_runner=clips_runner,
        apng_runner=apng_runner, selector=selector, packager=packager, validator=validator,
        submit=browser_submit, notify=notify,
    )


def run(state_root: Path, deps: Deps) -> dict:
    """Drive one set from wherever it is all the way to submitted in a single launch.

    Stops on submitted, on skip/noop/halt, or on a retry (an external wait such as missing clips
    or a failed package) so a stuck stage never spins.
    """
    while True:
        item_path = (newest_open_set(state_root) or state_root) / "creators-item.json"
        before = (_read_json(item_path) or {}).get("state")
        report = wake(state_root, deps)
        # The submit stage moves through several browser sub-states (metadata -> images -> tags ->
        # review request); keep going while each call makes progress.
        progressed = report.get("stage") == "submit" and (_read_json(item_path) or {}).get("state") != before
        if report.get("next_stage") == "submitted" or (report.get("action") != "advanced" and not progressed):
            return report


def main() -> int:
    state_root = DEFAULT_STATE_ROOT
    deps = production_deps()
    report = run(state_root, deps)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
