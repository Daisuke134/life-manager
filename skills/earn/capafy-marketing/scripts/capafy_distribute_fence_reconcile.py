#!/usr/bin/env python3
"""Close one capafy-distribute-daily effect_unknown admission fence.

Same decision shape as capafy_ig_fence_reconcile.py (one effected / no-effect
proof per occurrence, never a guess). capafy-distribute-daily's only external
effects are (1) a free article committed to the aniccaai.com landing repo on
GitHub and served live, and (2) an X post created through Postiz, which only
happens after (1). The official readbacks are therefore:
  - GitHub: commits "publish free article capafy-..." on the landing repo's
    remote branch for the exact slot slug inside
    [occurrence_started_at, occurrence_started_at + MAX_RUN_SECONDS];
  - the live aniccaai.com page for that slug (HTTP 200);
  - Postiz: posts on the X integration inside the same window.

  - A landing commit in the window whose live page answers 200 proves the
    effect happened: close as effected (the page URL + commit is the receipt).
  - No matching landing commit AND no Postiz X post in the window AND enough
    time has passed proves no effect: close as no-effect, citing both listings.
  - If the exact pre-effect ENOSPC marker proves the occurrence slot but the
    manifest was never written, only a Capafy article slug for that slot can
    conflict; unrelated commits in the shared landing repo do not.
  - A reel sibling's unique create receipt may exclude a preexisting scheduled
    X post only when its id/integration/slot match the official listing and the
    receipt predates this occurrence. Unknown shared-account posts stay fenced.
  - Any readback failure, or not enough time yet: stays fenced.

Usage:
    python3 capafy_distribute_fence_reconcile.py --occurrence capafy-distribute-daily:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "capafy-distribute-daily"
# model pass timeout (1800 s) + aniccaai deploy readback (<= 15 min) + X readback (<= 10 min).
MAX_RUN_SECONDS = 4200
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + 900
EVENTS_PATH = Path(
    "~/.local/state/life-manager/writer/capafy-distribute/events.jsonl"
).expanduser()
RUNS_ROOT = Path(
    "~/.local/state/life-manager/writer/capafy-distribute/capafy-distribute/runs"
).expanduser()
OCCURRENCES_ROOT = RUNS_ROOT.parent / "occurrences"
LEDGER_PATH = RUNS_ROOT.parent / "ledger.json"
LANDING_ROOT = Path(os.environ.get(
    "CAPAFY_DISTRIBUTE_LANDING_ROOT",
    "~/.local/state/life-manager/writer/checkouts/self-owned-landing")).expanduser()
BASE_URL = "https://aniccaai.com/blog/"
X_INTEGRATION_ID = os.environ.get("POSTIZ_X_INTEGRATION_ID", "cmt4l2jld031tqp0y8qtyo983")
X_VIDEO_RECEIPTS_ROOT = Path("~/.local/state/life-manager/marketing/capafy-videos").expanduser()
POSTIZ_POST_LIST_PROOF_ROW_CAP = 500
COMMIT_PREFIX = "feat(capafy-distribute): publish free article "
OCCURRENCE_SCHEMA = "capafy-distribute-occurrence.v1"
SLOT_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}-h(?:[01]\d|2[0-3])m(?:00|30)")
PRE_EFFECT_ENOSPC_RELEASE_SHA = "a299acc04573ab916fb261ad7ff94b1d3f79a119"
PRE_EFFECT_ENOSPC_DETAIL = (
    "capafy-distribute-daily.sh: line 148: cannot create temp file for here document: "
    "No space left on device"
)
PRE_EFFECT_TERMINAL_MAX_SECONDS = 120
PRE_PROVIDER_PROMPT_FAILURE_OCCURRENCE = "capafy-distribute-daily:18e077fbebd96ce8-96969"
PRE_PROVIDER_PROMPT_FAILURE_RELEASE_SHA = "70c93940bc712261f3dd01aa9556b467b1481539"
PRE_PROVIDER_PROMPT_FAILURE_SLUG = "youtube-outro-script"
PRE_PROVIDER_PROMPT_FAILURE_DETAIL = "line 237: CRAFT_GUIDANCE: unbound variable"
PRE_PROVIDER_PROMPT_FAILURE_POSTIZ_ID = "cmvhqvaid0429oh0ywbv95g8r"


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime]:
    """Read (state, queued_at) of the fenced row without mutating the ledger."""
    from runtime.host import resource_admission

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            """SELECT state, queued_at FROM occurrences
                 WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1""",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    return str(row[0]), dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)


def occurrence_queued_at(occurrence_id: str) -> dt.datetime:
    """Read the queue timestamp for a claimed or released parent occurrence."""
    from runtime.host import resource_admission

    run_id = _run_id_for_occurrence(occurrence_id)
    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT queued_at FROM occurrences WHERE owner_id=? AND occurrence_id=?",
            (OWNER_ID, f"{OWNER_ID}:{run_id}"),
        ).fetchone()
    if row is None or row[0] is None:
        raise ValueError("occurrence admission row missing")
    return dt.datetime.fromtimestamp(float(row[0]), dt.timezone.utc)


def occurrence_started_at(occurrence_id: str, events_path: Path | None = None) -> dt.datetime:
    """Read the exact execute-start timestamp for one occurrence from its event stream."""
    prefix = f"{OWNER_ID}:"
    if not occurrence_id.startswith(prefix) or not occurrence_id[len(prefix):]:
        raise ValueError("occurrence owner or run identity is invalid")
    run_id = occurrence_id[len(prefix):]
    path = events_path or EVENTS_PATH
    starts = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise ValueError("occurrence event stream contains malformed JSON") from exc
            if not isinstance(event, dict):
                raise ValueError("occurrence event stream row must be a JSON object")
            if (event.get("owner_id") != OWNER_ID
                    or event.get("run_id") != run_id
                    or event.get("occurrence_id") != occurrence_id
                    or event.get("phase") != "execute"
                    or event.get("status") != "running"):
                continue
            value = event.get("timestamp")
            if not isinstance(value, str):
                raise ValueError("occurrence execute-start timestamp missing or malformed")
            try:
                timestamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("occurrence execute-start timestamp is malformed") from exc
            if timestamp.tzinfo is None:
                raise ValueError("occurrence execute-start timestamp has no timezone")
            starts.append(timestamp.astimezone(dt.timezone.utc))
    if len(starts) != 1:
        raise ValueError("occurrence execute-start event missing or ambiguous")
    return starts[0]


def _run_id_for_occurrence(occurrence_id: str) -> str:
    prefix = f"{OWNER_ID}:"
    if not occurrence_id.startswith(prefix) or not occurrence_id[len(prefix):]:
        raise ValueError("occurrence owner or run identity is invalid")
    run_id = occurrence_id[len(prefix):]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
        raise ValueError("occurrence run identity is malformed")
    return run_id


def _validate_slot_article(slot: Any, article_slug: Any) -> tuple[str, str]:
    if not isinstance(slot, str) or not SLOT_PATTERN.fullmatch(slot):
        raise ValueError("occurrence slot is missing or malformed")
    try:
        dt.datetime.strptime(slot, "%Y-%m-%d-h%Hm%M")
    except ValueError as exc:
        raise ValueError("occurrence slot date is invalid") from exc
    if not isinstance(article_slug, str) or not (
            (article_slug.startswith("capafy-") and article_slug.endswith(f"-{slot}"))
            or article_slug in _seo_keyword_slugs()):
        raise ValueError("occurrence article slug does not match its slot")
    return slot, article_slug


def _seo_keyword_slugs() -> set[str]:
    """Seller slots publish a keyword page from seo/<skill>-keywords.json instead of a dated slug."""
    slugs: set[str] = set()
    for path in (Path(__file__).resolve().parents[1] / "seo").glob("*-keywords.json"):
        try:
            slugs |= {k["slug"] for k in json.loads(path.read_text(encoding="utf-8"))}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return slugs


def record_occurrence_manifest(path: Path, *, owner_id: str, run_id: str,
                               occurrence_id: str, slot: str, article_slug: str) -> dict[str, str]:
    """Persist the wrapper's slot outside the model-writable run directory."""
    if (owner_id != OWNER_ID or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id)
            or run_id != _run_id_for_occurrence(occurrence_id)
            or path.name != f"{run_id}.json" or path.parent.name != "occurrences"):
        raise ValueError("runtime occurrence identity mismatch")
    slot, article_slug = _validate_slot_article(slot, article_slug)
    record = {"schema": OCCURRENCE_SCHEMA, "owner_id": owner_id, "run_id": run_id,
              "occurrence_id": occurrence_id, "slot": slot, "article_slug": article_slug}
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent_info = path.parent.stat()
    if (path.parent.is_symlink() or not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != os.getuid() or stat.S_IMODE(parent_info.st_mode) != 0o700):
        raise ValueError("occurrence binding directory is not private and owner-controlled")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return record


def expected_article_slug(occurrence_id: str, occurrences_root: Path | None = None) -> str:
    """Read the wrapper-owned occurrence binding outside the model workspace."""
    return expected_article_slot_and_slug(occurrence_id, occurrences_root)[1]


def expected_article_slot_and_slug(occurrence_id: str,
                                   occurrences_root: Path | None = None) -> tuple[str, str]:
    """Same checked read as expected_article_slug, also returning the slot."""
    run_id = _run_id_for_occurrence(occurrence_id)
    root = occurrences_root or OCCURRENCES_ROOT
    if root.is_symlink() or not root.is_dir():
        raise ValueError("canonical occurrence binding directory is unavailable")
    root_info = root.stat()
    if (root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) != 0o700):
        raise ValueError("canonical occurrence binding directory is not private")
    path = root / f"{run_id}.json"
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError("occurrence binding is missing or unsafe") from exc
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("occurrence binding file is not private and owner-controlled")
        try:
            record = json.load(stream)
        except (OSError, ValueError) as exc:
            raise ValueError("occurrence manifest is missing or malformed") from exc
    if not isinstance(record, dict):
        raise ValueError("occurrence manifest must be a JSON object")
    if (record.get("schema") != OCCURRENCE_SCHEMA
            or record.get("owner_id") != OWNER_ID
            or record.get("run_id") != run_id
            or record.get("occurrence_id") != occurrence_id):
        raise ValueError("occurrence manifest identity mismatch")
    slot, slug = _validate_slot_article(record.get("slot"), record.get("article_slug"))
    return slot, slug


def pre_effect_manifest_enospc(occurrence_id: str, started_at: dt.datetime, *,
                               events_path: Path | None = None,
                               runs_root: Path | None = None) -> dict[str, Any] | None:
    """Bind the one known ENOSPC failure to an empty pre-publication run directory."""
    run_id = _run_id_for_occurrence(occurrence_id)
    path = events_path or EVENTS_PATH
    matching: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise ValueError("occurrence event stream contains malformed JSON") from exc
            if not isinstance(event, dict):
                raise ValueError("occurrence event stream row must be a JSON object")
            if (event.get("owner_id") == OWNER_ID
                    and event.get("run_id") == run_id
                    and event.get("occurrence_id") == occurrence_id):
                matching.append(event)
    if len(matching) != 2:
        return None
    starts = [event for event in matching
              if event.get("phase") == "execute" and event.get("status") == "running"]
    failures = [event for event in matching
                if event.get("phase") == "report" and event.get("status") == "fail"]
    if len(starts) != 1 or len(failures) != 1:
        return None
    start_event, failure = starts[0], failures[0]
    if (start_event.get("release_sha") != PRE_EFFECT_ENOSPC_RELEASE_SHA
            or failure.get("release_sha") != PRE_EFFECT_ENOSPC_RELEASE_SHA
            or start_event.get("effect_class") != "publish"
            or start_event.get("effect_status") != "started"
            or failure.get("effect_class") != "publish"
            or failure.get("effect_status") != "unknown"
            or failure.get("effect_identity_status") != "not_written"
            or failure.get("failure_layer") != "entrypoint"
            or failure.get("error_class") != "entrypoint_exit_1"
            or failure.get("exit_code") != 1
            or failure.get("provider_receipt_id") is not None
            or failure.get("official_readback_ref") is not None
            or PRE_EFFECT_ENOSPC_DETAIL not in str(failure.get("error_detail") or "")):
        return None
    try:
        event_started = dt.datetime.fromisoformat(
            str(start_event["timestamp"]).replace("Z", "+00:00")
        ).astimezone(dt.timezone.utc)
        terminal_at = dt.datetime.fromisoformat(
            str(failure["timestamp"]).replace("Z", "+00:00")
        ).astimezone(dt.timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None
    if event_started != started_at.astimezone(dt.timezone.utc):
        return None
    elapsed = (terminal_at - event_started).total_seconds()
    if elapsed < 0 or elapsed > PRE_EFFECT_TERMINAL_MAX_SECONDS:
        return None

    local = event_started.astimezone(ZoneInfo("Asia/Tokyo"))
    half_hour = (local.minute // 30) * 30
    slot = f"{local:%Y-%m-%d}-h{local.hour:02d}m{half_hour:02d}"
    root = runs_root or RUNS_ROOT
    run_dir = root / f"capafy-distribute-{slot}"
    gates = run_dir / "gates"
    if (root.is_symlink() or run_dir.is_symlink() or gates.is_symlink()
            or not run_dir.is_dir() or not gates.is_dir()):
        return None
    try:
        if sorted(child.name for child in run_dir.iterdir()) != ["gates"]:
            return None
        if any(gates.iterdir()):
            return None
        for directory in (run_dir, gates):
            if abs(directory.stat().st_mtime - event_started.timestamp()) > PRE_EFFECT_TERMINAL_MAX_SECONDS:
                return None
    except OSError:
        return None
    return {
        "slot": slot,
        "release_sha": PRE_EFFECT_ENOSPC_RELEASE_SHA,
        "failure_event_id": failure.get("event_id"),
        "run_directory": str(run_dir),
        "started_at": event_started.isoformat(),
        "terminal_at": terminal_at.isoformat(),
    }


def read_landing_commits(start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    """Commits on the landing repo's GitHub remote branch inside the window."""
    try:
        subprocess.run(["git", "-C", str(LANDING_ROOT), "fetch", "-q", "origin"],
                       check=True, capture_output=True, timeout=120)
        out = subprocess.run(
            ["git", "-C", str(LANDING_ROOT), "log", "origin/main", "--format=%H|%cI|%s",
             f"--since={start.isoformat()}", f"--until={end.isoformat()}"],
            check=True, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "reason": f"github_readback_failed:{type(exc).__name__}"}
    hits = []
    for line in out.splitlines():
        sha, when, subject = line.split("|", 2)
        if subject.startswith(COMMIT_PREFIX):
            hits.append({"sha": sha, "at": when, "slug": subject[len(COMMIT_PREFIX):].strip()})
    return {"ok": True, "commits": hits}


def pre_provider_prompt_failure(occurrence_id: str, started_at: dt.datetime,
                                expected_slug: str, *,
                                events_path: Path | None = None) -> dict[str, Any] | None:
    """Bind one shared-Postiz collision to the exact historical pre-provider failure."""
    if (occurrence_id != PRE_PROVIDER_PROMPT_FAILURE_OCCURRENCE
            or expected_slug != PRE_PROVIDER_PROMPT_FAILURE_SLUG):
        return None
    run_id = _run_id_for_occurrence(occurrence_id)
    matching: list[dict[str, Any]] = []
    path = events_path or EVENTS_PATH
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise ValueError("occurrence event stream contains malformed JSON") from exc
            if not isinstance(event, dict):
                raise ValueError("occurrence event stream row must be a JSON object")
            if (event.get("owner_id") == OWNER_ID
                    and event.get("run_id") == run_id
                    and event.get("occurrence_id") == occurrence_id):
                matching.append(event)
    if len(matching) != 2:
        return None
    starts = [event for event in matching
              if event.get("phase") == "execute" and event.get("status") == "running"]
    failures = [event for event in matching
                if event.get("phase") == "report" and event.get("status") == "fail"]
    if len(starts) != 1 or len(failures) != 1:
        return None
    start_event, failure = starts[0], failures[0]
    start_event_id = start_event.get("event_id")
    failure_event_id = failure.get("event_id")
    if (not isinstance(start_event_id, str) or not start_event_id
            or not isinstance(failure_event_id, str) or not failure_event_id
            or start_event_id == failure_event_id):
        return None
    if (start_event.get("release_sha") != PRE_PROVIDER_PROMPT_FAILURE_RELEASE_SHA
            or failure.get("release_sha") != PRE_PROVIDER_PROMPT_FAILURE_RELEASE_SHA
            or start_event.get("effect_class") != "publish"
            or start_event.get("effect_status") != "started"
            or failure.get("effect_class") != "publish"
            or failure.get("effect_status") != "unknown"
            or failure.get("effect_identity_status") != "not_written"
            or failure.get("failure_layer") != "entrypoint"
            or failure.get("error_class") != "entrypoint_exit_1"
            or failure.get("exit_code") != 1
            or failure.get("provider_receipt_id") is not None
            or failure.get("official_readback_ref") is not None
            or PRE_PROVIDER_PROMPT_FAILURE_DETAIL not in str(failure.get("error_detail") or "")):
        return None
    try:
        event_started = dt.datetime.fromisoformat(
            str(start_event["timestamp"]).replace("Z", "+00:00")
        ).astimezone(dt.timezone.utc)
        terminal_at = dt.datetime.fromisoformat(
            str(failure["timestamp"]).replace("Z", "+00:00")
        ).astimezone(dt.timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None
    elapsed = (terminal_at - event_started).total_seconds()
    if (event_started != started_at.astimezone(dt.timezone.utc)
            or elapsed < 0 or elapsed > PRE_EFFECT_TERMINAL_MAX_SECONDS):
        return None
    return {
        "failure_event_id": failure_event_id,
        "postiz_post_ids": [PRE_PROVIDER_PROMPT_FAILURE_POSTIZ_ID],
        "started_at": event_started.isoformat(),
        "terminal_at": terminal_at.isoformat(),
    }


def page_status(slug: str) -> int:
    try:
        with urllib.request.urlopen(BASE_URL + slug, timeout=20) as response:
            return response.status
    except Exception:  # noqa: BLE001 -- any failure is "not proven live"
        return 0


def postiz_key(credentials_path: Path | None = None) -> str:
    """Resolve Postiz from runtime env, then the private credential SSOT."""
    value = os.environ.get("POSTIZ_API_KEY") or os.environ.get("LM_POSTIZ_API_KEY")
    if value:
        return value
    path = credentials_path or Path.home() / ".local/share/anicca/credentials.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("credentials")
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    if not isinstance(rows, list):
        return ""
    matches = [
        str(row.get("api_key") or "").strip()
        for row in rows
        if isinstance(row, dict) and row.get("service") == "postiz"
        and str(row.get("api_key") or "").strip()
    ]
    return matches[0] if len(matches) == 1 else ""


def preexisting_x_post(post: dict[str, Any], start: dt.datetime) -> dict[str, Any] | None:
    """Match the reel sibling's create receipt to a post that predates this run."""
    root = X_VIDEO_RECEIPTS_ROOT
    if root.is_symlink():
        return None
    matches = []
    for path in root.glob("*/x-receipts-v3.jsonl"):
        if path.is_symlink() or path.parent.is_symlink():
            continue
        try:
            raw = path.read_bytes()
            receipt = json.loads(raw)
            created = receipt["create"]
            recorded_at = dt.datetime.fromisoformat(receipt["at"].replace("Z", "+00:00"))
            if (not isinstance(created, list) or len(created) != 1
                    or not isinstance(created[0], dict)
                    or created[0].get("postId") != post["id"]
                    or created[0].get("integration") != X_INTEGRATION_ID
                    or receipt.get("integration") != X_INTEGRATION_ID
                    or recorded_at.tzinfo is None or recorded_at >= start):
                continue
            scheduled = dt.datetime.fromisoformat(receipt["scheduled_for"].replace("Z", "+00:00"))
            published = dt.datetime.fromisoformat(post["publishDate"].replace("Z", "+00:00"))
            if scheduled.tzinfo is None or published.tzinfo is None or scheduled != published:
                continue
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
        matches.append({"post_id": post["id"], "integration_id": X_INTEGRATION_ID,
                        "created_at": recorded_at.isoformat(),
                        "publish_date": published.isoformat(), "receipt_path": str(path),
                        "receipt_sha256": hashlib.sha256(raw).hexdigest()})
    return matches[0] if len(matches) == 1 else None


def read_x_posts(start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    key = postiz_key()
    if not key:
        return {"ok": False, "reason": "postiz_key_missing"}
    try:
        sys.path.insert(0, str(REPO_ROOT / "skills/earn/marketing-engine/publish"))
        from postiz_adapter import HttpPostizClient  # noqa: PLC0415
        posts = HttpPostizClient(key).list_posts(start, end)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"postiz_readback_failed:{type(exc).__name__}"}
    if not isinstance(posts, list):
        return {"ok": False, "reason": "postiz_readback_malformed"}
    if len(posts) >= POSTIZ_POST_LIST_PROOF_ROW_CAP:
        return {"ok": False, "reason": "postiz_listing_exceeds_proof_row_cap"}
    if any(not isinstance(post, dict) for post in posts):
        return {"ok": False, "reason": "postiz_readback_malformed"}
    ours = []
    preexisting = []
    integration_posts = []
    for post in posts:
        integration = post.get("integration")
        if (not isinstance(integration, dict)
                or not isinstance(integration.get("id"), str)
                or not integration["id"]):
            return {"ok": False, "reason": "postiz_readback_malformed"}
        if integration["id"] == X_INTEGRATION_ID:
            post_id = post.get("id")
            if not isinstance(post_id, str) or not post_id:
                return {"ok": False, "reason": "postiz_readback_malformed"}
            integration_posts.append(post)
            prior = preexisting_x_post(post, start)
            if prior is not None:
                preexisting.append(prior)
            else:
                ours.append(post_id)
    result = {"ok": True, "posts": ours, "integration_posts": integration_posts}
    if preexisting:
        result["preexisting_posts"] = preexisting
    return result


MODEL_NO_RESPONSE_MAX_BLOCK_START_SKEW_SECONDS = 5.0

DAILY_LOG_PATH = Path.home() / ".local/state/life-manager/writer/capafy-distribute/logs/capafy-distribute-daily.log"
_LOG_HEADING = re.compile(r"^=== capafy-distribute-daily run (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) JST ===$")
_MODEL_PASS = re.compile(r"^capafy-distribute-daily: model pass exit=(\d+) slot=(\S+) ")
# Lines that only appear once the trusted wrapper has started publishing.
_PUBLISH_MARKERS = ("wrapper publish:", "x post:", "PII-GATE PASS", "CAPAFY_DRAFT_OUTPUT=PASS")


def _ledger_has_slot_post(ledger_path: Path, slot: str) -> bool:
    try:
        entry = json.loads(ledger_path.read_text(encoding="utf-8")).get(slot)
    except (OSError, ValueError):
        return True  # unreadable ledger: assume the slot may have published
    if not entry:
        return False
    if entry.get("status") == "published":
        return True
    destinations = entry.get("destinations") or {}
    return any(isinstance(d, dict) and (d.get("post_id") or d.get("status") in {"PUBLISHED", "published"})
               for d in destinations.values())


def model_no_response_evidence(started_at: dt.datetime, slot: str, *,
                               log_path: Path | None = None,
                               ledger_path: Path | None = None) -> dict[str, Any] | None:
    """Read the run's own log block: the model pass failed and nothing after it published.

    Bound by the occurrence start time (block heading within a few seconds) and by the slot named
    on the model-pass line. None when the log is unreadable or no block matches.
    """
    try:
        lines = (log_path or DAILY_LOG_PATH).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    jst = ZoneInfo("Asia/Tokyo")
    headings = []
    for index, line in enumerate(lines):
        match = _LOG_HEADING.match(line)
        if match:
            when = dt.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=jst)
            headings.append((index, when))
    best = None
    for position, (index, when) in enumerate(headings):
        skew = abs((when - started_at.astimezone(jst)).total_seconds())
        if skew > MODEL_NO_RESPONSE_MAX_BLOCK_START_SKEW_SECONDS:
            continue
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        block = lines[index:end]
        passes = [m for m in (_MODEL_PASS.match(line) for line in block) if m]
        if len(passes) != 1 or passes[0].group(2) != slot:
            continue
        if int(passes[0].group(1)) == 0:
            continue  # the model pass succeeded: not a no-response block
        candidate = {
            "slot": passes[0].group(2), "rc": int(passes[0].group(1)),
            "published_marker_in_block": any(marker in line for line in block for marker in _PUBLISH_MARKERS),
            "ledger_has_slot_post": _ledger_has_slot_post(ledger_path or LEDGER_PATH, slot),
            "block_started_within_s": round(skew, 3),
        }
        if best is None or skew < best["block_started_within_s"]:
            best = candidate
    return best




def _model_no_response_is_exact(evidence: dict[str, Any]) -> bool:
    """Every condition must hold; any doubt keeps the occurrence fenced."""
    skew = evidence.get("block_started_within_s")
    return (
        isinstance(evidence.get("expected_slot"), str)
        and evidence.get("slot") == evidence.get("expected_slot")
        and type(evidence.get("rc")) is int and evidence["rc"] != 0
        and evidence.get("published_marker_in_block") is False
        and evidence.get("ledger_has_slot_post") is False
        and isinstance(skew, (int, float)) and not isinstance(skew, bool)
        and 0 <= skew <= MODEL_NO_RESPONSE_MAX_BLOCK_START_SKEW_SECONDS
    )


def build_proof(occurrence_id: str, queued_at: dt.datetime, *,
                started_at: dt.datetime, expected_slug: str | None, now: dt.datetime,
                commits: dict[str, Any], x_posts: dict[str, Any],
                page_status_fn: Callable[[str], int] = page_status,
                pre_effect: dict[str, Any] | None = None,
                pre_provider_failure: dict[str, Any] | None = None,
                model_no_response: dict[str, Any] | None = None) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat(),
                             "occurrence_started_at": started_at.isoformat(),
                             "expected_slug": expected_slug}
    if (queued_at.tzinfo is None or queued_at.utcoffset() is None
            or started_at.tzinfo is None or started_at.utcoffset() is None):
        proof["reason"] = "occurrence_timestamp_missing_timezone"
        return proof
    if queued_at > started_at:
        proof["reason"] = "queued_after_execute_start"
        return proof
    if expected_slug is None:
        proof["pre_effect_evidence"] = pre_effect
        if pre_effect is None:
            proof["reason"] = "occurrence_manifest_missing_without_pre_effect_proof"
            return proof
    if not commits.get("ok"):
        proof["reason"] = commits.get("reason")
        return proof
    commit_rows = commits.get("commits")
    if not isinstance(commit_rows, list):
        proof["reason"] = "github_readback_malformed"
        return proof
    if expected_slug is not None:
        matching_commits = [
            commit for commit in commit_rows if commit.get("slug") == expected_slug
        ]
    elif pre_effect is not None and pre_effect.get("proof_kind") == "legacy_manifest_gap":
        # Legacy releases stored this binding beside model-writable artifacts.
        # Without a trusted binding, this slot's dated slug or a registered SEO
        # slug keeps the occurrence fenced if it has an official commit.
        slot = pre_effect.get("slot")
        pattern = (rf"capafy-[a-z0-9]+(?:-[a-z0-9]+)*-{re.escape(slot)}"
                   if isinstance(slot, str) and SLOT_PATTERN.fullmatch(slot) else None)
        seo_slugs = _seo_keyword_slugs()
        matching_commits = [
            commit for commit in commit_rows
            if isinstance(commit, dict) and isinstance(commit.get("slug"), str)
            and ((pattern is not None and re.fullmatch(pattern, commit["slug"]))
                 or commit["slug"] in seo_slugs)
        ]
        if len(matching_commits) > 1:
            proof["reason"] = "ambiguous_legacy_capafy_commits"
            return proof
        if matching_commits:
            if not x_posts.get("ok"):
                proof["reason"] = x_posts.get("reason")
                return proof
            legacy_posts = x_posts.get("posts")
            if not isinstance(legacy_posts, list):
                proof["reason"] = "postiz_readback_malformed"
                return proof
            if legacy_posts:
                proof["reason"] = "x_post_in_window_without_occurrence_manifest"
                return proof
            commit = matching_commits[0]
            sha = commit.get("sha")
            try:
                committed_at = dt.datetime.fromisoformat(
                    str(commit["at"]).replace("Z", "+00:00")
                ).astimezone(dt.timezone.utc)
            except (KeyError, TypeError, ValueError):
                proof["reason"] = "legacy_capafy_commit_timestamp_malformed"
                return proof
            if (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
                    or committed_at < started_at.astimezone(dt.timezone.utc)
                    or committed_at > (
                        started_at + dt.timedelta(seconds=MAX_RUN_SECONDS)
                    ).astimezone(dt.timezone.utc)):
                proof["reason"] = "legacy_capafy_commit_identity_invalid"
                return proof
            if page_status_fn(commit["slug"]) != 200:
                proof["reason"] = "legacy_capafy_commit_without_live_page"
                return proof
            proof.update(
                verified=True,
                effected=True,
                provider_receipt_id=f"github:{sha}|{BASE_URL}{commit['slug']}",
                proof_kind="official_unique_capafy_commit_and_live_page_for_legacy_occurrence",
                checked_at=now.isoformat(timespec="seconds"),
            )
            return proof
    elif pre_effect is not None:
        slot = pre_effect.get("slot")
        if not isinstance(slot, str) or not SLOT_PATTERN.fullmatch(slot):
            proof["reason"] = "pre_effect_slot_missing_or_malformed"
            return proof
        pattern = rf"capafy-[a-z0-9]+(?:-[a-z0-9]+)*-{re.escape(slot)}"
        matching_commits = [
            commit for commit in commit_rows
            if isinstance(commit, dict) and isinstance(commit.get("slug"), str)
            and re.fullmatch(pattern, commit["slug"])
        ]
    else:
        matching_commits = commit_rows
    for commit in matching_commits:
        if expected_slug is not None and page_status_fn(commit["slug"]) == 200:
            proof.update(verified=True, effected=True,
                         provider_receipt_id=f"github:{commit['sha']}|{BASE_URL}{commit['slug']}",
                         proof_kind="official_github_landing_commit_and_live_page",
                         checked_at=now.isoformat(timespec="seconds"))
            return proof
    if matching_commits:
        proof["reason"] = (
            "landing_commit_in_window_without_occurrence_manifest"
            if expected_slug is None else "landing_commit_without_live_page"
        )
        return proof
    if pre_provider_failure is not None and commit_rows:
        proof["reason"] = "landing_commit_in_window_during_pre_provider_failure"
        return proof
    age = (now - started_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    if model_no_response is not None and pre_provider_failure is not None:
        proof["reason"] = "model_no_response_not_combinable_with_pre_provider_failure"
        return proof
    if model_no_response is not None and not _model_no_response_is_exact(model_no_response):
        proof["reason"] = "model_no_response_evidence_not_exact"
        return proof
    if model_no_response is not None:
        # The run's own log block shows the model pass returned nothing (rc != 0), no publish marker
        # followed, and the ledger holds no post for this slot, so it never reached any provider
        # effect. An X post by the same integration inside the window therefore belongs to someone
        # else (2026-10-24: a teammate's manual promo post). No landing commit exists (checked above).
        proof.update(
            verified=True, effected=False,
            provider_receipt_id=(f"model-no-response:{model_no_response['expected_slot']}:"
                                 f"{started_at.isoformat()}"),
            proof_kind="occurrence_bound_model_no_response",
            model_no_response=model_no_response,
            checked_at=now.isoformat(timespec="seconds"),
        )
        return proof
    if not x_posts.get("ok"):
        proof["reason"] = x_posts.get("reason")
        return proof
    post_rows = x_posts.get("posts")
    if not isinstance(post_rows, list):
        proof["reason"] = "postiz_readback_malformed"
        return proof
    if x_posts.get("preexisting_posts"):
        proof["preexisting_x_posts"] = x_posts["preexisting_posts"]
    excluded_post_ids: list[str] = []
    if pre_provider_failure is not None:
        allowed = set(pre_provider_failure.get("postiz_post_ids", []))
        preexisting_rows = x_posts.get("preexisting_posts", [])
        if (not isinstance(preexisting_rows, list)
                or any(not isinstance(row, dict)
                       or not isinstance(row.get("post_id"), str)
                       or not row["post_id"] for row in preexisting_rows)):
            proof["reason"] = "postiz_readback_malformed"
            return proof
        all_post_ids = post_rows + [row["post_id"] for row in preexisting_rows]
        if len(all_post_ids) != len(set(all_post_ids)):
            proof["reason"] = "postiz_readback_malformed"
            return proof
        unexpected_posts = [post_id for post_id in all_post_ids if post_id not in allowed]
        if unexpected_posts:
            proof["reason"] = "x_post_without_article"
            return proof
        excluded_post_ids = [post_id for post_id in all_post_ids if post_id in allowed]
        proof["excluded_postiz_post_ids"] = excluded_post_ids
        proof["pre_provider_failure_event_id"] = pre_provider_failure["failure_event_id"]
    elif post_rows:
        proof["reason"] = (
            "x_post_in_window_without_occurrence_manifest"
            if expected_slug is None else "x_post_without_article"
        )
        return proof
    if pre_provider_failure is not None:
        provider_receipt_id = (
            f"github-postiz-window:{_run_id_for_occurrence(occurrence_id)}:"
            f"{started_at.isoformat()}:{(started_at + dt.timedelta(seconds=MAX_RUN_SECONDS)).isoformat()}:"
            f"pre-provider:{pre_provider_failure['failure_event_id']}:"
            f"excluded-postiz:{','.join(excluded_post_ids) or 'none'}"
        )
        proof_kind = "official_github_postiz_window_after_pre_provider_prompt_failure"
    else:
        provider_receipt_id = (
            f"github-postiz-empty-window:{_run_id_for_occurrence(occurrence_id)}:"
            f"{started_at.isoformat()}:{(started_at + dt.timedelta(seconds=MAX_RUN_SECONDS)).isoformat()}"
            if expected_slug is None else
            f"github-landing-and-postiz-x-empty:{started_at.isoformat()}"
        )
        proof_kind = (
            "official_github_postiz_empty_after_legacy_manifest_gap"
            if expected_slug is None and pre_effect is not None
            and pre_effect.get("proof_kind") == "legacy_manifest_gap" else
            "official_github_postiz_empty_after_pre_effect_enospc"
            if expected_slug is None else "official_github_commits_and_postiz_listing"
        )
    proof.update(verified=True, effected=False,
                 provider_receipt_id=provider_receipt_id,
                 proof_kind=proof_kind,
                 checked_at=now.isoformat(timespec="seconds"))
    return proof


def prove_occurrence(occurrence_id: str, *, now: dt.datetime | None = None,
                     queued_at_fn=None, started_at_fn=None, expected_slug_fn=None,
                     commits_fn=None, x_fn=None, page_status_fn=None) -> dict[str, Any]:
    """Read official publication proof for this parent run without changing admission."""
    now = now or dt.datetime.now(dt.timezone.utc)
    queued_at_fn = queued_at_fn or occurrence_queued_at
    started_at_fn = started_at_fn or occurrence_started_at
    expected_slug_fn = expected_slug_fn or expected_article_slug
    commits_fn = commits_fn or read_landing_commits
    x_fn = x_fn or read_x_posts
    page_status_fn = page_status_fn or page_status
    queued_at = queued_at_fn(occurrence_id)
    started_at = started_at_fn(occurrence_id)
    expected_slug = expected_slug_fn(occurrence_id)
    end = started_at + dt.timedelta(seconds=MAX_RUN_SECONDS)
    return build_proof(
        occurrence_id, queued_at, started_at=started_at,
        expected_slug=expected_slug, now=now,
        commits=commits_fn(started_at, end), x_posts=x_fn(started_at, end),
        page_status_fn=page_status_fn,
    )


def _write_private_hint(path: Path, value: dict[str, Any]) -> bool:
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return True


def persist_official_readback_snapshot(occurrence_id: str, started_at: dt.datetime,
                                      expected_slug: str | None, proof: dict[str, Any],
                                      commits: dict[str, Any],
                                      x_posts: dict[str, Any]) -> tuple[Path, str]:
    root = OCCURRENCES_ROOT
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise ValueError("readback snapshot directory unavailable") from exc
    if (stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_uid != os.getuid()
            or stat.S_IMODE(root_info.st_mode) != 0o700):
        raise ValueError("readback snapshot directory is not private")

    post_ids = x_posts.get("posts")
    if not isinstance(post_ids, list) or any(not isinstance(post_id, str) for post_id in post_ids):
        raise ValueError("postiz readback snapshot is malformed")
    integration_posts = x_posts.get("integration_posts", [])
    preexisting_posts = x_posts.get("preexisting_posts", [])
    if (not isinstance(integration_posts, list)
            or any(not isinstance(post, dict)
                   or not isinstance(post.get("id"), str)
                   or not isinstance(post.get("integration"), dict)
                   or post["integration"].get("id") != X_INTEGRATION_ID
                   for post in integration_posts)):
        raise ValueError("postiz provider rows are malformed")
    if (not isinstance(preexisting_posts, list)
            or any(not isinstance(post, dict)
                   or not isinstance(post.get("post_id"), str)
                   for post in preexisting_posts)):
        raise ValueError("postiz preexisting rows are malformed")
    provider_ids = [post["id"] for post in integration_posts]
    known_ids = post_ids + [post["post_id"] for post in preexisting_posts]
    if (len(provider_ids) != len(set(provider_ids))
            or sorted(provider_ids) != sorted(known_ids)):
        raise ValueError("postiz provider rows do not match listed IDs")
    snapshot = {
        "schema_version": "capafy-distribute-official-readback.v1",
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "run_id": _run_id_for_occurrence(occurrence_id),
        "checked_at": proof.get("checked_at"),
        "window_start": started_at.isoformat(),
        "window_end": (started_at + dt.timedelta(seconds=MAX_RUN_SECONDS)).isoformat(),
        "expected_article_slug": expected_slug,
        "proof_kind": proof.get("proof_kind"),
        "provider_receipt_id": proof.get("provider_receipt_id"),
        "github": {
            "readback_ok": commits.get("ok") is True,
            "landing_commits": commits.get("commits"),
            "reason": commits.get("reason"),
        },
        "postiz": {
            "readback_ok": x_posts.get("ok") is True,
            "integration_id": X_INTEGRATION_ID,
            "matching_post_ids": post_ids,
            "integration_posts": integration_posts,
            "preexisting_posts": preexisting_posts,
            "reason": x_posts.get("reason"),
        },
        "pre_provider_failure_event_id": proof.get("pre_provider_failure_event_id"),
        "pre_provider_failure_event_ref": (
            f"{EVENTS_PATH}#event_id={proof['pre_provider_failure_event_id']}"
            if proof.get("pre_provider_failure_event_id") else None
        ),
        "excluded_postiz_post_ids": proof.get("excluded_postiz_post_ids", []),
    }
    serialized = json.dumps(snapshot, sort_keys=True) + "\n"
    snapshot_bytes = serialized.encode("utf-8")
    digest = hashlib.sha256(snapshot_bytes).hexdigest()
    path = root / f"{_run_id_for_occurrence(occurrence_id)}.readback-{digest}.json"
    if not _write_private_hint(path, snapshot):
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise ValueError("readback snapshot could not be persisted") from exc
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
                    or stream.read() != snapshot_bytes):
                raise ValueError("existing readback snapshot does not match")
    directory_descriptor = os.open(
        root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return path, digest


def _occurrence_slot(occurrence_id: str) -> str:
    started_at = occurrence_started_at(occurrence_id, events_path=EVENTS_PATH)
    local = started_at.astimezone(ZoneInfo("Asia/Tokyo"))
    half_hour = (local.minute // 30) * 30
    return f"{local:%Y-%m-%d}-h{local.hour:02d}m{half_hour:02d}"


def write_result_hint(occurrence_id: str, path: Path) -> dict[str, Any]:
    """Read official proof internally, then write only its exact occurrence receipt."""
    if (not isinstance(occurrence_id, str)
            or not re.fullmatch(rf"{re.escape(OWNER_ID)}:[A-Za-z0-9_-]{{1,128}}", occurrence_id)):
        return {"owner_id": OWNER_ID, "verified": False,
                "hint_written": False, "reason": "invalid_occurrence"}
    requested_occurrence_id = occurrence_id
    proof = prove_occurrence(
        requested_occurrence_id,
        started_at_fn=lambda value: occurrence_started_at(value, events_path=EVENTS_PATH),
        expected_slug_fn=lambda value: expected_article_slug(
            value, occurrences_root=OCCURRENCES_ROOT),
    )
    proof["hint_written"] = False
    occurrence_id = proof.get("occurrence_id")
    expected_slug = proof.get("expected_slug")
    receipt = proof.get("provider_receipt_id")
    if (proof.get("verified") is not True or proof.get("effected") is not True
            or proof.get("proof_kind") != "official_github_landing_commit_and_live_page"
            or proof.get("owner_id") != OWNER_ID
            or occurrence_id != requested_occurrence_id
            or not isinstance(occurrence_id, str)
            or not occurrence_id.startswith(f"{OWNER_ID}:")
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", occurrence_id.split(":", 1)[1])
            or not isinstance(expected_slug, str)
            or not re.fullmatch(r"[a-z0-9-]{1,160}", expected_slug)
            or not isinstance(receipt, str)):
        return proof
    match = re.fullmatch(
        r"github:([0-9a-f]{40})\|(https://aniccaai\.com/blog/([a-z0-9-]{1,160}))",
        receipt,
    )
    if match is None or match.group(3) != expected_slug:
        return proof
    proof["hint_written"] = _write_private_hint(path, {
        "schema_version": 1,
        "kind": "life_manager_effect_result",
        "status": "verified_effect",
        "effect": 1,
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "provider": "writer",
        "provider_receipt_id": match.group(1),
        "effect_status": "reconciled",
        "live_urls": [match.group(2)],
    })
    return proof


def write_no_effect_result_hint(occurrence_id: str, path: Path, reason: str,
                                slot: str) -> bool:
    """Report an existing published slot or an attested pre-provider PII block."""
    if (not isinstance(occurrence_id, str)
            or not occurrence_id.startswith(f"{OWNER_ID}:")
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", occurrence_id.split(":", 1)[1])
            or reason not in {"daily_limit_reached", "pii_gate_blocked"}
            or not isinstance(slot, str) or not SLOT_PATTERN.fullmatch(slot)):
        return False
    expected_slot = _occurrence_slot(occurrence_id)
    if slot != expected_slot:
        return False
    if LEDGER_PATH.is_symlink():
        return False
    try:
        from capafy_distribute_ledger import is_published  # noqa: PLC0415

        published = is_published(LEDGER_PATH, slot)
        if ((reason == "daily_limit_reached" and not published)
                or (reason == "pii_gate_blocked" and published)):
            return False
    except (OSError, ValueError, TypeError):
        return False
    if reason == "pii_gate_blocked":
        try:
            expected_article_slug(occurrence_id, occurrences_root=OCCURRENCES_ROOT)
        except (OSError, ValueError, TypeError):
            return False
        from runtime.loop.lm_loop_run import verify_capafy_pii_gate_attestation
        if not verify_capafy_pii_gate_attestation(path, OWNER_ID, occurrence_id, slot):
            return False
    result = {
        "schema_version": 1,
        "kind": "life_manager_no_effect_result",
        "status": "verified_no_effect",
        "effect": 0,
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "reason": reason,
    }
    if reason == "pii_gate_blocked":
        result["slot"] = slot
    return _write_private_hint(path, result)


def reconcile(occurrence_id: str, *, resolve: bool = False, now: dt.datetime | None = None,
              fenced_row_fn=fenced_row, commits_fn=read_landing_commits,
              x_fn=read_x_posts, page_status_fn=page_status, resolve_fn=None,
              started_at_fn=None, expected_slug_fn=None,
              model_no_response_fn=None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row_fn(OWNER_ID, occurrence_id)
    started_at = (started_at_fn or occurrence_started_at)(occurrence_id)
    end = started_at + dt.timedelta(seconds=MAX_RUN_SECONDS)
    pre_provider_failure = None
    try:
        expected_slug = (expected_slug_fn or expected_article_slug)(occurrence_id)
    except ValueError:
        pre_effect = pre_effect_manifest_enospc(occurrence_id, started_at)
        if pre_effect is None:
            local = started_at.astimezone(ZoneInfo("Asia/Tokyo"))
            half_hour = (local.minute // 30) * 30
            pre_effect = {
                "proof_kind": "legacy_manifest_gap",
                "slot": f"{local:%Y-%m-%d}-h{local.hour:02d}m{half_hour:02d}",
                "started_at": started_at.astimezone(dt.timezone.utc).isoformat(),
            }
        expected_slug = None
    else:
        pre_effect = None
        pre_provider_failure = pre_provider_prompt_failure(
            occurrence_id, started_at, expected_slug
        )
    commits_readback = commits_fn(started_at, end)
    postiz_readback = x_fn(started_at, end)
    model_no_response = None
    # The one hard-coded historical case keeps its own, stricter proof untouched.
    if expected_slug is not None and pre_provider_failure is None:
        try:
            slot, _slug = expected_article_slot_and_slug(occurrence_id)
        except ValueError:
            slot = None
        evidence = ((model_no_response_fn or model_no_response_evidence)(started_at, slot)
                    if slot is not None else None)
        if evidence is not None:
            model_no_response = {**evidence, "expected_slot": slot}
    proof = build_proof(
        occurrence_id, queued_at, started_at=started_at,
        expected_slug=expected_slug, now=now,
        commits=commits_readback,
        x_posts=postiz_readback, page_status_fn=page_status_fn,
        pre_effect=pre_effect, pre_provider_failure=pre_provider_failure,
        model_no_response=model_no_response,
    )
    result = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
    try:
        snapshot_path, snapshot_hash = persist_official_readback_snapshot(
            occurrence_id, started_at, expected_slug, proof,
            commits_readback, postiz_readback,
        )
    except (OSError, ValueError) as exc:
        return {
            **proof,
            "verified": False,
            "reason": "readback_snapshot_persist_failed",
            "snapshot_error_class": type(exc).__name__,
            "admission_state": state,
        }
    proof["official_readback_ref"] = str(snapshot_path)
    proof["readback_snapshot_sha256"] = snapshot_hash
    proof["evidence_refs"] = [str(snapshot_path)]
    if proof.get("pre_provider_failure_event_id"):
        proof["evidence_refs"].append(
            f"{EVENTS_PATH}#event_id={proof['pre_provider_failure_event_id']}"
        )
    result = {**proof, "admission_state": state}
    if resolve_fn is None:
        from runtime.host.resource_admission import resolve_unknown_occurrence
        resolve_fn = resolve_unknown_occurrence
    result["closed"] = resolve_fn(OWNER_ID, occurrence_id,
                                  official_readback=lambda: proof, expected_state=state)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--result-hint")
    parser.add_argument(
        "--no-effect-reason", choices=("daily_limit_reached", "pii_gate_blocked"))
    parser.add_argument("--slot")
    args = parser.parse_args(argv)
    try:
        if args.no_effect_reason and (not args.result_hint or not args.slot):
            raise ValueError("--no-effect-reason requires --result-hint and --slot")
        if args.result_hint:
            if args.resolve:
                raise ValueError("--result-hint cannot resolve an admission fence")
            if args.no_effect_reason:
                written = write_no_effect_result_hint(
                    args.occurrence, Path(args.result_hint), args.no_effect_reason, args.slot,
                )
                result = {"owner_id": OWNER_ID, "occurrence_id": args.occurrence,
                          "verified": written, "effected": False,
                          "reason": args.no_effect_reason, "hint_written": written}
            else:
                result = write_result_hint(args.occurrence, Path(args.result_hint))
                written = result.get("hint_written") is True
            print(json.dumps(result, sort_keys=True, default=str))
            if not written:
                print("CAPAFY_DISTRIBUTE_RESULT_HINT=HELD")
                return 1
            print("CAPAFY_DISTRIBUTE_RESULT_HINT=PASS")
            return 0
        result = reconcile(args.occurrence, resolve=args.resolve)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"owner_id": OWNER_ID, "occurrence_id": args.occurrence,
                          "verified": False, "error": f"{type(exc).__name__}:{exc}"}))
        print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    if not result.get("verified"):
        print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
