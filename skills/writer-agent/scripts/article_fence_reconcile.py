#!/usr/bin/env python3
"""Close Writer fences only from exact publication or no-dispatch evidence.

article-daily pairs a fence with the run start or a generation-attempt start. A resumed attempt can
pair even when its run directory predates the fence. The time window selects candidates; it never
proves no effect. Require HTTP 200 for a ledger URL or exact allowlisted pre-publication stop proof.

article-resume requires age >= 7 days, official Note and both Substack reads whose newest posts
predate the fence, and no at-or-after row in the Writer ledger (including self-owned aniccaai.com posts).

    python3 article_fence_reconcile.py --occurrence article-daily:<run_id> [--resolve]
    python3 article_fence_reconcile.py --occurrence article-resume:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "article-daily"
RESUME_OWNER_ID = "article-resume"
PAIR_WINDOW_SECONDS = 1800        # a Writer run starts within 30 min after the admission claim
MIN_AGE_SECONDS = 3600            # never touch a fence whose run may still be going
RESUME_MIN_AGE_SECONDS = 7 * 86400   # measured publish lag 25 min-30 h, with margin
RESUME_READBACKS = {             # official public readbacks of every active Writer destination
    "note:anicca123": "https://note.com/api/v2/creators/anicca123/contents?kind=note&page=1",
    "substack:aniccabuddha": "https://aniccabuddha.substack.com/api/v1/posts?limit=3",
    "substack:aniccaai2026": "https://aniccaai2026.substack.com/api/v1/posts?limit=3",
}
ADMISSION_DB = Path.home() / ".local/state/life-manager/host-admission/resources/admission-v2.sqlite3"
ARTICLES = Path.home() / ".local/state/life-manager/writer/articles.jsonl"
RUNS_ROOT = Path.home() / ".local/state/life-manager/writer/runs"
PUBLICATION_STATE = "gates/publication-state.json"   # publication-guard writes it before any live effect
WRITER_STATE_ROOT = Path.home() / ".local/state/life-manager/writer"
SOURCE_REPO = Path.home() / "Projects/life-manager-main"
HISTORICAL_GATE_STOP_PROOFS = {
    # 2026-10-10 12:02 JST: start control blocked on unclassified same-day run 20261010-001933
    # and exited 0 before generation (pre-#7602 BLOCK branch); no run dir was created.
    "article-daily:18dd0bf091a5d3d0-57499": {
        "stop_kind": "start_control_block",
        "runtime_run_id": "18dd0bf091a5d3d0-57499",
        "writer_run_id": "20261010-001933",
        "release_sha": "1be8bb91b6d45010defb8790310b3c214d740555",
        "entrypoint": "skills/writer-agent/article-daily.sh",
        "entrypoint_sha256": "1e11eedb8038959bf9fcea21e24b78c9e38cc53bd7f8e9a2d84518875c3f4e96",
        "start_event_id": "65685224a361d2cd5d2c7723",
        "terminal_event_id": "9ee47bc4cfbd45fadd360281",
        "event_hashes": {
            "65685224a361d2cd5d2c7723": "62e96e9885b01762ead2cd31f4b12f34596d1cd0d1b099ff3b073d6ca5c29e20",
            "9ee47bc4cfbd45fadd360281": "feb7c20d8a32a0819d0ec7b10343f4f5c8a6519cf017abf0f46b4033a960fe21",
        },
        "log_header": "=== article-daily run 2026-10-10 12:02:35 JST ===",
        "article_log_segment_sha256": "7debc6b8776875b6c77166e94f00652cf2aecba497464d05ce19d79b0a1e7008",
        "queued_at": 1791601208.371748,
        "gate_error": "block-incomplete",
        "gate_terminal": "article-daily start control BLOCK",
        "evidence_ref": "writer://fence-reconciliation/article-daily-18dd0bf091a5d3d0-57499.json",
    },
    "article-daily:18dcb160db0ac660-67443": {
        "runtime_run_id": "18dcb160db0ac660-67443",
        "writer_run_id": "20261008-232303",
        "release_sha": "25e89f07e19db53c00fca7275543419c808e222d",
        "entrypoint": "skills/writer-agent/article-daily.sh",
        "entrypoint_sha256": "6befd8a983c17d945506761bbd727ac80e0b56b91c8cdb3b5389a31ba900b33f",
        "start_event_id": "f788745c9942592c5dda4bbe",
        "terminal_event_id": "4d8c87b93955946219a77aeb",
        "event_hashes": {
            "f788745c9942592c5dda4bbe": "b4b42e724acbde6e147af56df11210fa127f8fced67cc19ba1785fee877b3bf3",
            "4d8c87b93955946219a77aeb": "517ca5d6bb03abe911bbba504eb352c9ed4e5eda415a0dd4a11b031b09d98a90",
        },
        "run_artifacts": {
            "gates/product-selection.json": "8eb648527158bf35aea7662ef922fc7ef91253d2832af64bca07fdf08a5b925d",
            "gates/strategy-consumption.json": "7c6e4e4bb5963e755ee661e5a506a0db9dc775c07eb49203f469049e72d399c8",
            "git-hash.txt": "d594f84f59cb613b4c63ade34961972b07d0d021bb4222b4ebbfda9db655e7f7",
        },
        "article_log_segment_sha256": "af8129b5234d54e8f70b1e1b319c5ca4150b67eaa49d2b63a4d6198b19a7b9c3",
        "queued_at": 1791501539.804287,
        "gate_error": "demand topic queue contains non-paid-demand cards: "
                      "marketing-intel-48c88abc36f3.md",
        "gate_terminal": "article-daily demand authority blocked generation; "
                         "pending claim-loop supply",
    },
    "article-daily:18dcb869e78c3c38-58827": {
        "runtime_run_id": "18dcb869e78c3c38-58827",
        "writer_run_id": "20261008-232303",
        "release_sha": "d3b3a2792ce9dfa344f4edecf19b66244917d692",
        "entrypoint": "skills/writer-agent/article-daily.sh",
        "entrypoint_sha256": "33c1e70d8314847e1b010b55ef948f9b68739c74bbfeb423245b6298ed0116bf",
        "start_event_id": "5fdde4392f893a6bf3f37534",
        "terminal_event_id": "baa8f2df960fdd6dc9105e36",
        "event_hashes": {
            "5fdde4392f893a6bf3f37534": "89a6b29c0dd1d01a01543e5e18d1c8b0025c3ad9e100d02bee2f1a3438ab272c",
            "baa8f2df960fdd6dc9105e36": "8134b784e7be7cf852c7f49121d729da7d94f6cf639ca634f6c622b12f21c191",
        },
        "run_tree": [
            {"path": "article-daily-prompt.txt", "type": "file", "sha256": "422e192511ec0e1ed0774cd409b03ef2513b9f5c00c050c348f52ed64df037fc"},
            {"path": "gates", "type": "directory"},
            {"path": "gates/.generation-state.json.lock", "type": "file", "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
            {"path": "gates/judge-broker", "type": "directory"},
            {"path": "gates/judge-broker/done", "type": "directory"},
            {"path": "gates/judge-broker/heartbeat", "type": "file", "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
            {"path": "gates/judge-broker/requests", "type": "directory"},
            {"path": "gates/judge-broker/responses", "type": "directory"},
            {"path": "gates/product-selection.json", "type": "file", "sha256": "8eb648527158bf35aea7662ef922fc7ef91253d2832af64bca07fdf08a5b925d"},
            {"path": "gates/strategy-consumption.json", "type": "file", "sha256": "7c6e4e4bb5963e755ee661e5a506a0db9dc775c07eb49203f469049e72d399c8"},
            {"path": "git-hash.txt", "type": "file", "sha256": "d594f84f59cb613b4c63ade34961972b07d0d021bb4222b4ebbfda9db655e7f7"},
        ],
        "article_log_segment_sha256": "0916fde0f5448d5d2989a665da7d16b673982b9b4a7897db9ba5569ae5a01def",
        "queued_at": 1791509208.924928,
        "gate_error": "GenerationInvariant: generated-or-staged-artifacts:gates/product-selection.json",
        "gate_terminal": "GenerationInvariant: generated-or-staged-artifacts:gates/product-selection.json",
        "evidence_ref": "writer://fence-reconciliation/article-daily-18dcb869e78c3c38-58827.json",
    },
}


def _run_start_epoch(run_id: str) -> float | None:
    """Writer run ids are YYYYMMDD-HHMMSS in UTC."""
    try:
        return datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def _run_starts(run_dir: Path) -> list[float]:
    """Run start plus resumed generation attempt starts."""
    base = _run_start_epoch(run_dir.name)
    starts = [base] if base is not None else []
    gates = run_dir / "gates"
    state_path = gates / "generation-state.json"
    if run_dir.is_symlink() or not run_dir.is_dir() or gates.is_symlink() or state_path.is_symlink():
        return starts
    try:
        # Directory start may predate the fence; include retry start.
        starts.extend(
            timestamp for attempt in json.loads(state_path.read_text(encoding="utf-8")).get("attempts") or []
            if isinstance(attempt, dict)
            if (timestamp := _epoch(attempt.get("started_at"))) is not None
        )
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return starts

def _jsonl_lines(path: Path) -> list[str] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError):
        return None


def _run_tree_manifest(run_dir: Path) -> list[dict[str, str]] | None:
    if run_dir.is_symlink() or not run_dir.is_dir():
        return None
    manifest = []
    try:
        for path in sorted(run_dir.rglob("*")):
            if path.is_symlink():
                return None
            relative = path.relative_to(run_dir).as_posix()
            if path.is_dir():
                manifest.append({"path": relative, "type": "directory"})
            elif path.is_file():
                manifest.append({"path": relative, "type": "file",
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            else:
                return None
    except OSError:
        return None
    return manifest


def _historical_gate_stop_proof(
        occurrence_id: str, queued_at: float, *, writer_root: Path,
        source_repo: Path, now: float | None = None) -> dict | None:
    """Prove the allowlisted historical Writer run stopped before publish dispatch."""
    expected = HISTORICAL_GATE_STOP_PROOFS.get(occurrence_id)
    if expected is None:
        return None
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    if (now - queued_at < MIN_AGE_SECONDS
            or not math.isclose(queued_at, expected["queued_at"], abs_tol=0.001)):
        return None
    event_lines = _jsonl_lines(writer_root / "events.jsonl")
    if event_lines is None or writer_root.is_symlink():
        return None
    matching_events = [line for line in event_lines if occurrence_id in line]
    event_hashes = [hashlib.sha256(line.encode("utf-8")).hexdigest()
                    for line in matching_events]
    wanted_event_hashes = [
        expected["event_hashes"][expected["start_event_id"]],
        expected["event_hashes"][expected["terminal_event_id"]],
    ]
    if len(matching_events) != 2 or event_hashes != wanted_event_hashes:
        return None

    if source_repo.is_symlink() or not source_repo.is_dir():
        return None
    try:
        ancestry = subprocess.run(
            ["git", "-C", str(source_repo), "merge-base", "--is-ancestor",
             expected["release_sha"], "refs/remotes/origin/main"],
            capture_output=True, timeout=10, check=False,
        )
        source = subprocess.run(
            ["git", "-C", str(source_repo), "show",
             f"{expected['release_sha']}:{expected['entrypoint']}"],
            capture_output=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if ancestry.returncode != 0 or source.returncode != 0:
        return None
    entrypoint_sha = hashlib.sha256(source.stdout).hexdigest()
    if entrypoint_sha != expected["entrypoint_sha256"]:
        return None

    run_dir = writer_root / "runs" / expected["writer_run_id"]
    run_tree = None
    start_block = expected.get("stop_kind") == "start_control_block"
    if start_block:
        # Start control stopped before creating a run dir (2026-10-10 block-incomplete):
        # the log segment below is the only run evidence and is pinned by hash.
        run_artifacts = {}
    elif "run_tree" in expected:
        run_tree = _run_tree_manifest(run_dir)
        if run_tree is None or run_tree != expected["run_tree"]:
            return None
        run_artifacts = {item["path"]: item["sha256"] for item in run_tree
                         if item["type"] == "file"}
    else:
        gates = run_dir / "gates"
        if (run_dir.is_symlink() or not run_dir.is_dir()
                or {item.name for item in run_dir.iterdir()} != {"gates", "git-hash.txt"}
                or gates.is_symlink() or not gates.is_dir()
                or {item.name for item in gates.iterdir()} != {
                    "product-selection.json", "strategy-consumption.json"}):
            return None
        items = [run_dir / "git-hash.txt", *gates.iterdir()]
        if any(item.is_symlink() or not item.is_file() for item in items):
            return None
        run_artifacts = {
            item.relative_to(run_dir).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
            for item in items
        }
        if run_artifacts != expected["run_artifacts"]:
            return None

    articles_path = writer_root / "articles.jsonl"
    article_lines = _jsonl_lines(articles_path)
    if article_lines is None:
        return None
    for line in article_lines:
        try:
            row = json.loads(line)
        except ValueError:
            return None
        candidate_start = _run_start_epoch(str(row.get("run_id", "")))
        if candidate_start is not None and 0 <= candidate_start - queued_at <= PAIR_WINDOW_SECONDS:
            return None

    log_path = writer_root / "logs" / "article-daily.log"
    if log_path.is_symlink() or not log_path.is_file():
        return None
    try:
        log_lines = log_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    if start_block:
        anchors = [index for index, line in enumerate(log_lines) if line == expected["log_header"]]
        end_marker = "=== article-daily run "
    else:
        anchors = [
            index for index, line in enumerate(log_lines)
            if f"completed prior run released a new run={expected['writer_run_id']} " in line
        ]
        end_marker = "article-daily start control:"
    if len(anchors) != 1:
        return None
    start_index = anchors[0]
    end_index = next(
        (index for index in range(start_index + 1, len(log_lines))
         if end_marker in log_lines[index]),
        len(log_lines),
    )
    run_log = log_lines[start_index:end_index]
    run_log_text = "\n".join(run_log)
    if (expected["gate_error"] not in run_log_text
            or expected["gate_terminal"] not in run_log_text
            or "article-daily generation begin" in run_log_text
            or hashlib.sha256(run_log_text.encode("utf-8")).hexdigest()
               != expected["article_log_segment_sha256"]):
        return None
    proof = {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_type": "historical_writer_gate_stop_no_dispatch",
        "provider": "writer",
        "runtime_run_id": expected["runtime_run_id"],
        "writer_run_id": expected["writer_run_id"],
        "release_sha": expected["release_sha"],
        "entrypoint": expected["entrypoint"],
        "entrypoint_sha256": entrypoint_sha,
        "stop_branch": expected["gate_terminal"],
        "event_hashes": dict(zip(
            (expected["start_event_id"], expected["terminal_event_id"]), event_hashes)),
        "run_artifacts": run_artifacts,
        "article_log_segment_sha256": expected["article_log_segment_sha256"],
        "evidence_ref": expected.get(
            "evidence_ref",
            "writer://fence-reconciliation/article-daily-18dcb160db0ac660-67443.json",
        ),
    }
    if run_tree is not None:
        proof["run_tree"] = run_tree
    return proof


def _persist_historical_gate_stop_proof(writer_root: Path, proof: dict) -> bool:
    directory = writer_root / "fence-reconciliation"
    if directory.is_symlink():
        return False
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        return False
    os.chmod(directory, 0o700)
    name = proof["evidence_ref"].rsplit("/", 1)[-1]
    target = directory / name
    payload = json.dumps(proof, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if target.exists():
        return not target.is_symlink() and target.read_text(encoding="utf-8") == payload
    temporary = directory / f".{name}.{os.getpid()}.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return True
    except OSError:
        temporary.unlink(missing_ok=True)
        return False


def _http_status(url: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "lm-article-fence-reconcile"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, OSError):
        return 0


def _inconclusive(occurrence_id: str, reason: str) -> dict:
    return {"status": "inconclusive", "reason": reason, "occurrence_id": occurrence_id, "closed": False}


def _fetch_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": "lm-article-fence-reconcile"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read()) if response.status == 200 else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _epoch(value: object) -> float | None:
    """Timezone-aware ISO-8601 only; a naive or unparseable time proves nothing."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _newest_post_epoch(payload: object) -> float | None:
    """note: data.contents[].publishAt; Substack: [].post_date.  Empty or any undatable post -> None."""
    try:
        posts = payload["data"]["contents"] if isinstance(payload, dict) else payload
        if not isinstance(posts, list):
            return None
        times = [_epoch(post.get("publishAt") or post.get("post_date")) for post in posts]
    except (KeyError, TypeError, AttributeError):
        return None
    return max(times) if times and None not in times else None


def _ledger_row_epoch(row: dict) -> float | None:
    for key in ("ts", "recorded_at"):
        if row.get(key):
            return _epoch(row[key])
    return _run_start_epoch(str(row.get("run_id", "")))


def _reconcile_resume(occurrence_id: str, *, queued_at: float, state: str, articles_path: Path,
                      fetch_json: Callable[[str], object], resolver: Callable[..., bool] | None,
                      resolve: bool, now: float, writer_root: Path) -> dict:
    """Prove no article-resume publication happened after the fence from official readbacks only."""
    if now - queued_at < RESUME_MIN_AGE_SECONDS:
        return _inconclusive(occurrence_id, "fence_too_young")
    lines = _jsonl_lines(articles_path)
    try:
        times = [_ledger_row_epoch(json.loads(line)) for line in lines]
    except (TypeError, ValueError, AttributeError):
        return _inconclusive(occurrence_id, "articles_ledger_unreadable")
    # ponytail: append-only ledger, so undated draft rows are bounded by the dated last row;
    # an undated tail cannot be placed in time and stays fenced.
    if not times or times[-1] is None:
        return _inconclusive(occurrence_id, "articles_ledger_tail_undated")
    if any(t is not None and t >= queued_at for t in times):
        return _inconclusive(occurrence_id, "writer_ledger_row_after_fence")
    readbacks = {}
    for name, url in RESUME_READBACKS.items():
        newest = _newest_post_epoch(fetch_json(url))
        if newest is None:
            return _inconclusive(occurrence_id, f"readback_failed:{name}")
        if newest >= queued_at:
            return _inconclusive(occurrence_id, f"publication_after_fence:{name}")
        readbacks[name] = _iso(newest)
    runtime_run_id = occurrence_id.split(":", 1)[1]
    proof = {
        "owner_id": RESUME_OWNER_ID,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_type": "historical_writer_resume_no_dispatch",
        "provider": "writer",
        "runtime_run_id": runtime_run_id,
        "queued_at": _iso(queued_at),
        "readback_urls": dict(RESUME_READBACKS),
        "readback_newest_post_at": readbacks,
        "ledger_newest_ts": _iso(max(t for t in times if t is not None)),
        "evidence_ref": f"writer://fence-reconciliation/article-resume-{runtime_run_id}.json",
    }
    result = {"status": "no_dispatch_proven", "occurrence_id": occurrence_id, "closed": False,
              "proof_ref": proof["evidence_ref"]}
    if not resolve:
        return result
    if not _persist_historical_gate_stop_proof(writer_root, proof):
        return _inconclusive(occurrence_id, "historical_proof_receipt_conflict")
    if resolver is None:
        from runtime.host.resource_admission import resolve_historical_no_dispatch_occurrence
        resolver = resolve_historical_no_dispatch_occurrence
    result["closed"] = bool(resolver(RESUME_OWNER_ID, occurrence_id,
                                     no_dispatch_proof=lambda: proof, expected_state=state))
    return result


def _pre_effect(occurrence_id: str, queued_at: float, state: str, rows: list, runs_root: Path,
                resolver: Callable[..., bool] | None, resolve: bool) -> dict:
    """Close a fence whose paired run stopped before any publication intent was registered.

    Positive evidence only: at least one run dir (or a resumed attempt of one) started in the pairing
    window, and none of the paired runs has a publication state or a ledger row.  Every managed
    publish adapter refuses without gates/publication-state.json, which publication-guard writes
    before the first live side effect.  No paired run -> the fence stays (absence of a run is not proof).
    """
    try:
        paired = sorted(d for d in runs_root.iterdir()
                        if d.is_dir() and any(0 <= started - queued_at <= PAIR_WINDOW_SECONDS
                                              for started in _run_starts(d)))
    except OSError:
        return _inconclusive(occurrence_id, "runs_root_unreadable")
    if not paired:
        return _inconclusive(occurrence_id, "no_run_paired_with_this_fence")
    ledger_runs = {str(row.get("run_id", "")) for row in rows}
    if any(d.name in ledger_runs or (d / PUBLICATION_STATE).exists() for d in paired):
        return _inconclusive(occurrence_id, "run_reached_publication")
    evidence = "writer-run-no-publication-state:" + ",".join(d.name for d in paired)
    result = {"status": "pre_effect", "occurrence_id": occurrence_id, "closed": False, "evidence_ref": evidence}
    if not resolve:
        return result
    if resolver is None:
        from runtime.host.resource_admission import resolve_pre_effect_occurrence
        resolver = resolve_pre_effect_occurrence
    proof = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
             "proof_type": "pre_effect", "evidence_ref": evidence}
    result["closed"] = bool(resolver(OWNER_ID, occurrence_id, pre_effect_readback=lambda: proof,
                                     expected_state=state))
    return result


def reconcile(occurrence_id: str, *, queued_at: float, state: str, articles_path: Path = ARTICLES,
              fetch_status: Callable[[str], int] = _http_status, resolver: Callable[..., bool] | None = None,
              resolve: bool = False, now: float | None = None, runs_root: Path = RUNS_ROOT,
              pre_effect_resolver: Callable[..., bool] | None = None,
              writer_root: Path = WRITER_STATE_ROOT,
              source_repo: Path = SOURCE_REPO,
              fetch_json: Callable[[str], object] = _fetch_json) -> dict:
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    if occurrence_id.startswith(f"{RESUME_OWNER_ID}:"):
        return _reconcile_resume(occurrence_id, queued_at=queued_at, state=state,
                                 articles_path=articles_path, fetch_json=fetch_json,
                                 resolver=resolver, resolve=resolve, now=now, writer_root=writer_root)
    if not occurrence_id.startswith(f"{OWNER_ID}:"):
        return _inconclusive(occurrence_id, "owner_not_allowlisted")
    if now - queued_at < MIN_AGE_SECONDS:
        return _inconclusive(occurrence_id, "fence_too_young")
    try:
        rows = [json.loads(line) for line in articles_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return _inconclusive(occurrence_id, "articles_ledger_unreadable")
    candidates = []
    for row in rows:
        run_id = str(row.get("run_id", ""))
        if (len(run_id) != 15 or not run_id.isascii() or run_id[8] != "-"
                or not (run_id[:8] + run_id[9:]).isdigit()):
            continue
        started = _run_start_epoch(run_id)
        url = str(row.get("live_url") or "")
        if started is None or not url.startswith("https://"):
            continue
        run_dir = runs_root / run_id
        starts = ([started] if runs_root.is_symlink() or run_dir.is_symlink() or not run_dir.is_dir()
                  else _run_starts(run_dir))
        if any(queued_at <= start <= queued_at + PAIR_WINDOW_SECONDS for start in starts):
            candidates.append(row)
    proven = [row for row in candidates if fetch_status(str(row["live_url"])) == 200]
    if not proven:
        if occurrence_id in HISTORICAL_GATE_STOP_PROOFS:
            no_dispatch = _historical_gate_stop_proof(
                occurrence_id, queued_at, writer_root=writer_root,
                source_repo=source_repo, now=now)
            if no_dispatch is None:
                return _inconclusive(occurrence_id, "historical_gate_stop_proof_unavailable")
            result = {"status": "no_dispatch_proven", "occurrence_id": occurrence_id,
                      "closed": False, "writer_run_id": no_dispatch["writer_run_id"],
                      "proof_ref": no_dispatch["evidence_ref"]}
            if not resolve:
                return result
            if not _persist_historical_gate_stop_proof(writer_root, no_dispatch):
                return _inconclusive(occurrence_id, "historical_proof_receipt_conflict")
            if resolver is None:
                from runtime.host.resource_admission import resolve_historical_no_dispatch_occurrence
                resolver = resolve_historical_no_dispatch_occurrence
            result["closed"] = bool(resolver(
                OWNER_ID, occurrence_id,
                no_dispatch_proof=lambda: no_dispatch,
                expected_state=state,
            ))
            return result
        return _pre_effect(occurrence_id, queued_at, state, rows, runs_root,
                           pre_effect_resolver, resolve)
    receipt = str(proven[0]["live_url"])
    result = {"status": "effected", "occurrence_id": occurrence_id, "closed": False,
              "provider_receipt_id": receipt, "run_id": proven[0].get("run_id"),
              "live_urls": [str(row["live_url"]) for row in proven]}
    if not resolve:
        return result
    if resolver is None:
        from runtime.host.resource_admission import resolve_unknown_occurrence
        resolver = resolve_unknown_occurrence
    proof = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
             "provider_receipt_id": receipt}
    result["closed"] = bool(resolver(OWNER_ID, occurrence_id, official_readback=lambda: proof,
                                     expected_state=state))
    return result


def _admission_row(occurrence_id: str) -> tuple[float, str] | None:
    owner_id = occurrence_id.split(":", 1)[0]
    if owner_id not in {OWNER_ID, RESUME_OWNER_ID}:
        return None
    try:
        with sqlite3.connect(f"file:{ADMISSION_DB}?mode=ro", uri=True, timeout=20) as connection:
            row = connection.execute(
                "SELECT queued_at, state FROM occurrences WHERE occurrence_id=? AND owner_id=? "
                "AND effect_unknown=1", (occurrence_id, owner_id)).fetchone()
    except sqlite3.Error:
        return None
    return (float(row[0]), str(row[1])) if row else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    row = _admission_row(args.occurrence)
    if row is None:
        result = _inconclusive(args.occurrence, "occurrence_not_fenced_or_unreadable")
    else:
        result = reconcile(args.occurrence, queued_at=row[0], state=row[1], resolve=args.resolve)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if (
        result["status"] in {"effected", "pre_effect", "no_dispatch_proven"}
        and (result["closed"] or not args.resolve)
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
