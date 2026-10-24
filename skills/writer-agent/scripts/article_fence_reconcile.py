#!/usr/bin/env python3
"""Close Writer fences only from exact publication or no-dispatch evidence.

article-daily pairs a fence with the run start or a generation-attempt start. A resumed attempt can
pair even when its run directory predates the fence. The time window selects candidates; it never
proves no effect. Require HTTP 200 for a ledger URL or exact allowlisted pre-publication stop proof.

article-resume closes from its own pass records when the pass provably reached no publisher: the
#8260 'article-resume: pass' lines bind the occurrence to a publication-free branch sequence, its
single runtime report exited 0, and neither the ledger nor any official readback has a publication
inside the pass window.  A start->publication pass whose own segment shows the Substack verify-preview
gate refusing (PREVIEW_FATAL, exit 5 before the only publish POST) closes the same way, with any exit
code, once the touched draft reads unpublished on its publication.  Otherwise it requires age >= 7 days:
a bound Substack publication pass needs only its touched draft unpublished and no ledger row for that
run+pair at or after the fence; an unbound pass needs official Note and both Substack reads whose newest
posts predate the fence and no at-or-after row in the Writer ledger (including self-owned aniccaai.com
posts), or an exact allowlisted pass bound to its missed-schedule catch-up exec
(HISTORICAL_RESUME_CATCHUP_PROOFS).

    python3 article_fence_reconcile.py --occurrence article-daily:<run_id> [--resolve]
    python3 article_fence_reconcile.py --occurrence article-resume:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import zlib
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
    # This occurrence dispatched nothing: start control left this pre-existing run
    # with article-resume. Its exit 0 predated the typed no-effect result contract.
    "article-daily:18dfc09cffeae8b8-61102": {
        "stop_kind": "start_control_block",
        "runtime_run_id": "18dfc09cffeae8b8-61102",
        "writer_run_id": "20261018-194904",
        "writer_run_role": "pre_existing_resume_worker_owned",
        "release_sha": "bd67bc0adb238dabcb8c608309d1f3b63403b4d3",
        "entrypoint": "skills/writer-agent/article-daily.sh",
        "entrypoint_sha256": "05c5697edd6d4ada17aa2d45162e2a2509fe4501e845ec568856c52ac2402a71",
        "helper_sha256": {
            "skills/writer-agent/scripts/writer_owner_fence.py":
                "fd28146f02987fe43e1a82548a2307e302b45ad09ef43c907fd5834c6a4298e5",
        },
        "events_archive": "events-20261020T050241988389Z.jsonl.gz",
        "events_archive_sha256": "5fdb0b15d3eb0ef64e3fcaad9568b561dd78d5fb5a60e5f92afb9ad80e52c03a",
        "start_event_id": "3a581164c1fdfae737be7782",
        "terminal_event_id": "83bc68f6c71eb8479bc04dc2",
        "event_hashes": {
            "3a581164c1fdfae737be7782": "b2fe9556c1a64069a7e0005d6b6d49088130dbd110efe2df4b9509c24f32e0bc",
            "83bc68f6c71eb8479bc04dc2": "0b501ede96b8657038f2d3412a4c98b429dabfd81347f4fa5561149b9efb2079",
        },
        "log_header": "=== article-daily run 2026-10-19 07:35:58 JST ===",
        "article_log_segment_sha256": "28b1792ff2ed5595fdd59a4602552490720c01a933eefdd14bb14ab07087aa57",
        "queued_at": 1792360804.324131,
        "gate_error": "pending active-four run remains resume-worker-owned",
        "gate_terminal": "=== article-daily start control: pending active-four run remains "
                         "resume-worker-owned run=20261018-194904; no concurrent article "
                         "2026-10-19 07:36:07 JST ===",
        "pre_effect_marker_sha256": "bc68b6c09ee78331c4baf41981d2d5ce910f84432e5195fd19150f24074b3dcd",
        "evidence_ref": "writer://fence-reconciliation/article-daily-18dfc09cffeae8b8-61102.json",
    },
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
# article-resume passes whose only branch was the missed-schedule catch-up: in the pinned release every
# resume publisher (adoption/quality/priority/devto/x-post/self-owned) runs only after that `exec`, and
# reaching it requires adoption, pending-quality and priority publication all empty.  The proof binds the
# log line to the one resume execution of its JST hour, then proves the exec'd article-daily run stopped
# before publication state and that every active destination's owner listing reads it absent.
# Every resume branch that can reach a publisher records itself first (#8260), so these complete
# per-occurrence branch sequences reach none.  self-heal additionally needs the dispatcher's own
# result to say it selected no incident (no repair model ran).
RESUME_PASS_PREFIX = "article-resume: pass "
NO_PUBLICATION_PASSES = {("publication-paused",), ("lock-held",),
                         ("start", "daily-schedule-not-due"), ("start", "self-heal")}
NO_MODEL_REPAIR_STATUSES = {"NO_ACTIONABLE_INCIDENT", "NO_INCIDENT_QUEUE"}
# A start->publication pass runs one deterministic Substack publisher on one persisted draft.  The
# wrapper (_shared/publish-substack-mermaid.sh) prints PREVIEW_FATAL and exits 5 before its only
# publish POST; self_owned_article.py prints the bare {"status":"complete","run_id":...} only when it
# returned before any git delivery.
PREVIEW_FATAL = ("FATAL: verify-preview FAILED — NOT publishing (an image may be too tall on screen, "
                 "or the preview could not be opened at all -- check the message above for which).")
SUBSTACK_DRAFT_LINE = re.compile(r"== step 1/3: reuse stable Substack draft id=(\d+) ==")
SUBSTACK_TERMINAL = re.compile(r"article-resume: run=(\S+) rc=(\d+) deterministic=(substack/(?:ja|en))")
INITIALIZATION_TERMINAL = re.compile(
    r"article-resume: run=(\S+) rc=([1-9]\d*) deterministic=initialize-([a-z0-9-]+/(?:ja|en))")
INITIALIZATION_REFUSAL_PREFIX = "refuse initialization: "
SELF_OWNED_PENDING = "article-resume: self-owned worker remains pending"
# Lines a self-owned push that git rejected prints before the worker gives up; nothing else.
REJECTED_PUSH_LINES = ("Traceback (most recent call last):", "  ", "SelfOwnedInvariant: To ",
                       " ! [rejected]", "error: failed to push some refs", "hint: ")
SUBSTACK_HOST = re.compile(r"[a-z0-9-]+\.substack\.com")
TOUCHED_KEYS = ("writer_run_id", "pair", "draft_id", "host")
HISTORICAL_RESUME_CATCHUP_PROOFS = {
    # 2026-10-20 06:04 JST: catch-up exec'd article-daily.sh; run 20261019-210430 stopped in 14 s
    # with "prepublication-finish: skip reason=missing-article-ja.md" and no dispatch files.
    "article-resume:18e00a32b6c907c0-21320": {
        "writer_run_id": "20261019-210430",
        "queued_at": 1792443847.589477,
        "release_sha": "baac8c681314edd1fc430199f30da410d31a4c1c",
        "entrypoint_sha256": {
            "skills/writer-agent/scripts/article-resume-pending.sh":
                "28a40e7618173905538ca875cc59cd9a52b9ea4e9710574598f2df74fa027684",
            "skills/writer-agent/article-daily.sh":
                "05c5697edd6d4ada17aa2d45162e2a2509fe4501e845ec568856c52ac2402a71",
        },
        "events_archive": "events-20261020T050241988389Z.jsonl.gz",
        "event_hashes": [   # start, terminal
            "11447d8d5aa09d363072b54b4d8a30d8cafe21ab37624efef265d01c788b7975",
            "0bd9c01c4776a87a4a889326ddb4bea8103c2a8a8446a27bab054047e06a7b7c",
        ],
        "catchup_hour_utc": ("2026-10-19T21:00:00+00:00", "2026-10-19T22:00:00+00:00"),
        "resume_log_line": "article-resume: missed daily schedule catch-up date=2026-10-20 hour=06",
        "resume_log_previous_line": (
            'article-resume: pass {"at":"2026-10-19T21:04:25Z",'
            '"occurrence_id":"article-resume:18e00a32b6c907c0-21320","pid":21414,'
            '"branch":"start","run_ids":[]}'
        ),
        "article_log_segment": ("=== article-daily run 2026-10-20 06:04:29 JST ===",
                                "=== article-daily done rc=1 2026-10-20 06:04:43 JST ==="),
        "article_log_segment_sha256": "2960d57ecb00a8bfb34fa41f1efcb136a381d2fe87ee0449b4cef1b9771aa0c4",
        "run_artifacts": {
            "gates/generation-state.json": "214ab8df172acf90ac1a6b3726ed37c2e96ec912c02f8fecab4270bb4573002b",
            "gates/product-selection.json": "5a2b054caabe42fcec001652bc7cd182583a3aeebb4bdc3496ac57cbe97c2208",
        },
        # The run wrote no draft, so the owner listings have no title to search; the hash-bound
        # segment above ends at the pre-publication stop instead.
        "no_drafts_stop_line": ("=== article-daily: generation incomplete before publication state; "
                                "same-run generation reconciler owns run=20261019-210430 "
                                "2026-10-20 06:04:43 JST ==="),
    },
    # 2026-10-12 06:05 JST: catch-up exec'd article-daily.sh; run 20261011-210544 ended
    # provider-failed-ambiguous with publication-blocker "no staging or publishing attempted".
    "article-resume:18dd959f92920ff0-56630": {
        "writer_run_id": "20261011-210544",
        "queued_at": 1791752648.92176,
        "release_sha": "6f25bb2e95e9efbea58a0d8f04b4cc6eefbea7d2",
        "entrypoint_sha256": {
            "skills/writer-agent/scripts/article-resume-pending.sh":
                "5134fab95ab2b3056789ff7a1ed51383f5f0baf36baed81b32090c00369bf299",
            "skills/writer-agent/article-daily.sh":
                "8cad4180b62e1c4e072b98c05d3ffb3f8505011f23c9ce616e07cf43eccfcdd7",
        },
        "events_archive": "events-20261013T124916565876Z.jsonl.gz",
        "event_hashes": [   # start, terminal
            "02e82d525adbd67616a77068e99ef89a11a66613b09cd11940c41c3f09109372",
            "6ff9ff0a449c273117c23bc822eeab40de37f9c6b8cf9c0e51f5ad81421865c8",
        ],
        "catchup_hour_utc": ("2026-10-11T21:00:00+00:00", "2026-10-11T22:00:00+00:00"),
        "resume_log_line": "article-resume: missed daily schedule catch-up date=2026-10-12 hour=06",
        "resume_log_previous_line": "article-resume: daily schedule not due date=2026-10-12 hour=05",
        "article_log_segment": ("=== article-daily run 2026-10-12 06:05:42 JST ===",
                                "=== article-daily done rc=1 2026-10-12 06:17:15 JST ==="),
        "article_log_segment_sha256": "75afbdf93eb28e822973d13a4d4c44c907123d1f6217d1ba9ecec3b6a0c27b40",
        "run_artifacts": {
            "gates/generation-state.json": "128fa0373171bde3cec00fed99e7447f8c6460224b4d0ef8464d84e938d52c67",
            "gates/publication-blocker.json": "4c345382af27d7297ef50bef9ec8d80dd6f66184b06b1b772cf8cacc4ac0afea",
        },
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
    if "events_archive" in expected:
        archive_name = expected["events_archive"]
        archive = writer_root / archive_name
        if (Path(archive_name).name != archive_name
                or archive.is_symlink() or not archive.is_file()):
            return None
        try:
            archive_bytes = archive.read_bytes()
            if hashlib.sha256(archive_bytes).hexdigest() != expected["events_archive_sha256"]:
                return None
            event_lines = [line for line in gzip.decompress(archive_bytes).decode("utf-8").splitlines()
                           if line.strip()]
        except (OSError, UnicodeError, EOFError, zlib.error):
            return None
    else:
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
    try:
        for path, digest in expected.get("helper_sha256", {}).items():
            helper = subprocess.run(
                ["git", "-C", str(source_repo), "show", f"{expected['release_sha']}:{path}"],
                capture_output=True, timeout=10, check=False)
            if helper.returncode != 0 or hashlib.sha256(helper.stdout).hexdigest() != digest:
                return None
    except (OSError, subprocess.SubprocessError):
        return None
    if ("pre_effect_marker_sha256" in expected
            and _read_host_pre_effect_marker_sha256(occurrence_id, writer_root)
                != expected["pre_effect_marker_sha256"]):
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
    for key in ("events_archive", "events_archive_sha256", "helper_sha256",
                "pre_effect_marker_sha256", "writer_run_role"):
        if key in expected:
            proof[key] = expected[key]
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
                      resolve: bool, now: float, writer_root: Path, source_repo: Path = SOURCE_REPO,
                      absence_readback: Callable[..., dict | None] | None = None) -> dict:
    """Prove no article-resume publication happened after the fence from official readbacks only."""
    if occurrence_id in HISTORICAL_RESUME_CATCHUP_PROOFS:
        proof = _historical_resume_catchup_proof(
            occurrence_id, queued_at, writer_root=writer_root, source_repo=source_repo,
            articles_path=articles_path, absence_readback=absence_readback or _official_absence_readback)
        if isinstance(proof, str):
            return _inconclusive(occurrence_id, proof)
        return _resolve_resume_proof(occurrence_id, proof, state=state, resolver=resolver,
                                     resolve=resolve, writer_root=writer_root)
    pass_proof = _resume_pass_record_proof(occurrence_id, queued_at, writer_root=writer_root,
                                           articles_path=articles_path, fetch_json=fetch_json)
    if isinstance(pass_proof, dict):
        return _resolve_resume_proof(occurrence_id, pass_proof, state=state, resolver=resolver,
                                     resolve=resolve, writer_root=writer_root)
    if now - queued_at < RESUME_MIN_AGE_SECONDS:
        return {**_inconclusive(occurrence_id, "fence_too_young"), "pass_record": pass_proof}
    observed = _resume_pass(writer_root, occurrence_id, queued_at)
    touched = _substack_pass(observed, writer_root) if isinstance(observed, tuple) else None
    if isinstance(touched, dict):
        # The bound pass could publish only its one draft: later articles elsewhere are not its effect.
        rows = _jsonl_lines(articles_path)
        if rows is None:
            return _inconclusive(occurrence_id, "articles_ledger_unreadable")
        for line in rows:
            try:
                row = json.loads(line)
                stamp = _ledger_row_epoch(row)
            except (ValueError, AttributeError):
                return _inconclusive(occurrence_id, "articles_ledger_unreadable")
            if (str(row.get("run_id", "")) == touched["writer_run_id"]
                    and f"{row.get('platform')}/{row.get('lang')}" == touched["pair"]
                    and (stamp is None or stamp >= queued_at)):
                return _inconclusive(occurrence_id, "touched_pair_ledger_row_after_fence")
        readback = _touched_draft_unpublished(touched, queued_at, fetch_json)
        if isinstance(readback, str):
            return _inconclusive(occurrence_id, readback)
        runtime_run_id = occurrence_id.split(":", 1)[1]
        proof = {
            "owner_id": RESUME_OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
            "proof_type": "historical_writer_resume_no_dispatch", "provider": "writer",
            "runtime_run_id": runtime_run_id, "queued_at": _iso(queued_at),
            "touched": {**{key: touched[key] for key in TOUCHED_KEYS}, **readback},
            "report_event_id": observed[0].get("event_id"), "release_sha": observed[0].get("release_sha"),
            "evidence_ref": f"writer://fence-reconciliation/article-resume-{runtime_run_id}.json",
        }
        return _resolve_resume_proof(occurrence_id, proof, state=state, resolver=resolver,
                                     resolve=resolve, writer_root=writer_root)
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
    return _resolve_resume_proof(occurrence_id, proof, state=state, resolver=resolver,
                                 resolve=resolve, writer_root=writer_root)


def _report_event(writer_root: Path, occurrence_id: str) -> dict | None:
    """The occurrence's single runtime report event, or None."""
    reports = []
    for line in _jsonl_lines(writer_root / "events.jsonl") or []:
        if occurrence_id not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            return None
        if event.get("occurrence_id") == occurrence_id and event.get("phase") == "report":
            reports.append(event)
    return reports[0] if len(reports) == 1 else None


def _resume_pass(writer_root: Path, occurrence_id: str, queued_at: float) -> tuple | str:
    """The occurrence's runtime report and its own pass records (one pid, inside the pass window)."""
    report = _report_event(writer_root, occurrence_id)
    if report is None:
        return "pass_report_missing"
    until = _epoch(report.get("timestamp"))
    if until is None:
        return "pass_report_missing"
    log = writer_root / "logs" / "article-resume.log"
    try:
        if log.is_symlink():
            return "pass_log_unreadable"
        lines = log.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return "pass_log_unreadable"
    records = []
    for index, line in enumerate(lines):
        if line.startswith(RESUME_PASS_PREFIX) and occurrence_id in line:
            try:
                record = json.loads(line[len(RESUME_PASS_PREFIX):])
            except ValueError:
                return "pass_record_unreadable"
            if isinstance(record, dict) and record.get("occurrence_id") == occurrence_id:
                records.append((index, record))
    stamps = [_epoch(record.get("at")) for _, record in records]
    if (not records or len({record.get("pid") for _, record in records}) != 1
            or None in stamps or min(stamps) < queued_at - 1 or max(stamps) > until):
        return "pass_record_unbound"
    return report, until, lines, records, tuple(str(record.get("branch")) for _, record in records)


def _resume_pass_record_proof(occurrence_id: str, queued_at: float, *, writer_root: Path,
                              articles_path: Path, fetch_json: Callable[[str], object]) -> dict | str:
    """Bind a resume fence to its own publication-free pass; return the proof or the missing binding."""
    observed = _resume_pass(writer_root, occurrence_id, queued_at)
    if isinstance(observed, str):
        return observed
    report, until, lines, records, branches = observed
    touched = None
    if branches == ("start", "publication"):
        # Accepted nonzero exits: an initialization refused before staging, or the Substack
        # preview gate refused before the publish POST.
        touched = _initialization_refused_pass(observed)
        if isinstance(touched, str):
            touched = _substack_pass(observed, writer_root)
            if isinstance(touched, str):
                return touched
            if not _preview_fatal(touched):
                return "pass_substack_may_have_published"
            readback = _touched_draft_unpublished(touched, queued_at, fetch_json)
            if isinstance(readback, str):
                return readback
            touched = {**{key: touched[key] for key in TOUCHED_KEYS}, "stop": "verify-preview-fatal", **readback}
    elif report.get("exit_code") != 0 or report.get("status") != "pass":
        return "pass_report_not_clean_exit"
    elif branches not in NO_PUBLICATION_PASSES:
        return "pass_branch_not_publication_free:" + ",".join(branches)
    elif any(record.get("run_ids") != [] for _, record in records):
        return "pass_record_unbound"
    if branches[-1] == "self-heal":
        index = records[-1][0] + 1
        try:
            status = json.loads(lines[index]).get("status") if index < len(lines) else None
        except (ValueError, AttributeError):
            status = None
        # Both the pinned and current wrappers log a nonzero dispatcher exit right after its result.
        failed = index + 1 < len(lines) and lines[index + 1] == "article-resume: repair routing failed closed"
        if status not in NO_MODEL_REPAIR_STATUSES or failed:
            return "pass_self_heal_may_have_run_model"

    rows = _jsonl_lines(articles_path)
    if rows is None:
        return "articles_ledger_unreadable"
    for line in rows:
        try:
            row = json.loads(line)
            stamp = _ledger_row_epoch(row)
        except (ValueError, AttributeError):
            return "articles_ledger_unreadable"
        if stamp is None and (row.get("published") is True or row.get("live_url")):
            return "articles_ledger_undated_publication"
        if stamp is not None and queued_at <= stamp <= until:
            return "writer_ledger_row_in_window"
    readbacks = {}
    for name, url in RESUME_READBACKS.items():
        payload = fetch_json(url)
        try:
            posts = payload["data"]["contents"] if isinstance(payload, dict) else payload
            times = [_epoch(post.get("publishAt") or post.get("post_date")) for post in posts]
        except (KeyError, TypeError, AttributeError):
            times = []
        if not times or None in times:
            return f"readback_failed:{name}"
        if any(queued_at <= t <= until for t in times):
            return f"publication_in_window:{name}"
        if min(times) >= queued_at:
            return f"readback_window_not_covered:{name}"   # older posts fell off the listed page
        readbacks[name] = _iso(max(t for t in times if t < queued_at))
    runtime_run_id = occurrence_id.split(":", 1)[1]
    proof = {
        "owner_id": RESUME_OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
        "proof_type": "historical_writer_resume_no_dispatch", "provider": "writer",
        "runtime_run_id": runtime_run_id, "branches": list(branches),
        "pass_records": [record for _, record in records],
        "report_event_id": report.get("event_id"), "release_sha": report.get("release_sha"),
        "window": {"since": _iso(queued_at), "until": _iso(until)},
        "readback_urls": dict(RESUME_READBACKS), "readback_newest_post_before_window": readbacks,
        "evidence_ref": f"writer://fence-reconciliation/article-resume-{runtime_run_id}.json",
    }
    if touched is not None:
        proof["touched"] = touched
    return proof


def _initialization_refused_pass(observed: tuple) -> dict | str:
    """A start->publication pass that ended at an initialize-<pair> refusal before any staging.

    execute-initialization-pair.py raises its "refuse initialization:" SystemExit before
    prepare_all() or any provider call. The only other output allowed in the segment is a
    self-owned push that git rejected atomically (remote unchanged).
    """
    report, _, lines, records, branches = observed
    if branches != ("start", "publication") or records[0][1].get("run_ids") != []:
        return "pass_branch_not_publication_free:" + ",".join(branches)
    run_ids = records[1][1].get("run_ids")
    if not isinstance(run_ids, list) or len(run_ids) != 1:
        return "pass_record_unbound"
    run_id, start = str(run_ids[0]), records[1][0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("article-resume: run=")), None)
    terminal = INITIALIZATION_TERMINAL.fullmatch(lines[end]) if end is not None else None
    if not terminal or terminal[1] != run_id or int(terminal[2]) != report.get("exit_code"):
        return "pass_initialization_terminal_unbound"
    segment = lines[start:end]
    if not segment or not segment[-1].startswith(INITIALIZATION_REFUSAL_PREFIX):
        return "pass_initialization_not_refused"
    body = segment[:-1]
    if body:
        if (body[-1] != SELF_OWNED_PENDING
                or not any(line.startswith(" ! [rejected]") for line in body)
                or any(" -> " in line and not line.startswith(" ! [rejected]") for line in body)
                or not all(line.startswith(REJECTED_PUSH_LINES) for line in body[:-1])):
            return "pass_self_owned_may_have_pushed"
    return {"stop": "initialization-refused", "pair": terminal[3], "writer_run_id": run_id,
            "self_owned_push": "rejected" if body else "none"}


def _substack_pass(observed: tuple, writer_root: Path) -> dict | str:
    """The one Substack draft a start->publication pass touched, bound by its own log segment."""
    report, _, lines, records, branches = observed
    if branches != ("start", "publication") or records[0][1].get("run_ids") != []:
        return "pass_branch_not_publication_free:" + ",".join(branches)
    run_ids = records[1][1].get("run_ids")
    if not isinstance(run_ids, list) or len(run_ids) != 1:
        return "pass_record_unbound"
    run_id, start = str(run_ids[0]), records[1][0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("article-resume: run=")), None)
    terminal = SUBSTACK_TERMINAL.fullmatch(lines[end]) if end is not None else None
    if not terminal or terminal[1] != run_id or int(terminal[2]) != report.get("exit_code"):
        return "pass_substack_terminal_unbound"
    segment = lines[start:end]
    if any(line.startswith(RESUME_PASS_PREFIX) for line in segment):
        return "pass_record_unbound"
    if segment[:1] != [json.dumps({"status": "complete", "run_id": run_id}, separators=(",", ":"))]:
        return "pass_self_owned_may_have_published"
    pair = terminal[3]
    drafts = [match[1] for line in segment if (match := SUBSTACK_DRAFT_LINE.fullmatch(line))]
    state_path = writer_root / "runs" / run_id / PUBLICATION_STATE
    try:
        if state_path.is_symlink():
            return "pass_substack_draft_unbound"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        host, target = str(state["destination_identities"][pair]), str(state["pairs"][pair]["target"])
    except (OSError, ValueError, KeyError, TypeError):
        return "pass_substack_draft_unbound"
    if drafts != [target] or not SUBSTACK_HOST.fullmatch(host):
        return "pass_substack_draft_unbound"
    return {"writer_run_id": run_id, "pair": pair, "draft_id": target, "host": host, "segment": segment}


def _preview_fatal(touched: dict) -> bool:
    """The failure circuit recorded PREVIEW_FATAL as this pair's publisher failure, after the line."""
    segment = touched["segment"]
    fatal = [index for index, line in enumerate(segment) if line == PREVIEW_FATAL]
    decided = []
    for index, line in enumerate(segment):
        try:
            decision = json.loads(line)
        except ValueError:
            continue
        if (isinstance(decision, dict) and decision.get("action") in {"retry", "open"}
                and decision.get("pair") == touched["pair"] and decision.get("signature") == PREVIEW_FATAL):
            decided.append(index)
    return (len(fatal) == 1 and bool(decided) and min(decided) > fatal[0]
            and not any(line.startswith("PUBLISHED:") for line in segment))


def _touched_draft_unpublished(touched: dict, queued_at: float,
                               fetch_json: Callable[[str], object]) -> dict | str:
    """The publication's official post listing reaches back before the fence and lacks the draft id."""
    host = touched["host"]
    url = f"https://{host}/api/v1/posts?limit=50"   # 50 is the public API maximum
    try:
        posts = {str(post["id"]): _epoch(post.get("post_date")) for post in fetch_json(url)}
    except (KeyError, TypeError, AttributeError):
        posts = {}
    if not posts or None in posts.values():
        return f"readback_failed:{host}"
    if touched["draft_id"] in posts:
        return f"touched_draft_published:{host}"
    if min(posts.values()) >= queued_at:
        return f"readback_window_not_covered:{host}"
    return {"readback_url": url, "readback_post_count": len(posts),
            "readback_oldest_post_at": _iso(min(posts.values()))}


def _resolve_resume_proof(occurrence_id: str, proof: dict, *, state: str,
                          resolver: Callable[..., bool] | None, resolve: bool, writer_root: Path) -> dict:
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


def _historical_resume_catchup_proof(occurrence_id: str, queued_at: float, *, writer_root: Path,
                                     source_repo: Path, articles_path: Path,
                                     absence_readback: Callable[..., dict | None]) -> dict | str:
    """Bind an allowlisted resume pass to its catch-up exec; return the proof or the missing binding."""
    expected = HISTORICAL_RESUME_CATCHUP_PROOFS[occurrence_id]
    if not math.isclose(queued_at, expected["queued_at"], abs_tol=0.001):
        return "catchup_queued_at_mismatch"
    archive = writer_root / expected["events_archive"]
    if writer_root.is_symlink() or archive.is_symlink() or not archive.is_file():
        return "catchup_events_unreadable"
    try:
        with gzip.open(archive, "rt", encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if line.strip()]
        events = [json.loads(line) for line in lines]
    except (OSError, ValueError, EOFError, zlib.error):
        return "catchup_events_unreadable"
    own = [line for line in lines if occurrence_id in line]
    if [hashlib.sha256(line.encode("utf-8")).hexdigest() for line in own] != expected["event_hashes"]:
        return "catchup_events_mismatch"
    until = _epoch(json.loads(own[1]).get("timestamp"))
    hour_start, hour_end = (_epoch(value) for value in expected["catchup_hour_utc"])

    def executions(loop_id: str, since: float, before: float) -> set[str]:
        """Occurrences of loop_id that started in [since, before) and were not refused by admission."""
        started = {event.get("occurrence_id") for event in events
                   if event.get("loop_id") == loop_id and event.get("phase") == "execute"
                   and since <= (_epoch(event.get("timestamp")) or -1) < before}
        deferred = {event.get("occurrence_id") for event in events
                    if event.get("phase") == "report"
                    and str(event.get("blocker") or "").startswith("host_admission_deferred:")}
        return started - deferred

    # The catch-up line names its JST date+hour, so only a resume execution of that hour can print it.
    if until is None or executions(RESUME_OWNER_ID, hour_start, hour_end) != {occurrence_id}:
        return "catchup_hour_has_other_resume_execution"
    # The exec'd article-daily.sh is the only article-daily process of the window.
    if executions(OWNER_ID, queued_at, until):
        return "catchup_overlapping_article_daily_execution"

    try:
        ancestry = subprocess.run(
            ["git", "-C", str(source_repo), "merge-base", "--is-ancestor",
             expected["release_sha"], "refs/remotes/origin/main"],
            capture_output=True, timeout=10, check=False)
        if ancestry.returncode != 0:
            return "catchup_release_not_on_main"
        for path, digest in expected["entrypoint_sha256"].items():
            source = subprocess.run(["git", "-C", str(source_repo), "show", f"{expected['release_sha']}:{path}"],
                                    capture_output=True, timeout=10, check=False)
            if source.returncode != 0 or hashlib.sha256(source.stdout).hexdigest() != digest:
                return "catchup_entrypoint_mismatch"
    except (OSError, subprocess.SubprocessError):
        return "catchup_release_unreadable"

    try:
        resume_log = (writer_root / "logs" / "article-resume.log").read_text(encoding="utf-8").splitlines()
        daily_log = (writer_root / "logs" / "article-daily.log").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return "catchup_logs_unreadable"
    anchors = [i for i, line in enumerate(resume_log) if line == expected["resume_log_line"]]
    # The previous line is the prior pass's `exit 0`: this pass logged nothing before its exec.
    if len(anchors) != 1 or anchors[0] == 0 \
            or resume_log[anchors[0] - 1] != expected["resume_log_previous_line"]:
        return "catchup_resume_log_mismatch"
    header, footer = expected["article_log_segment"]
    starts = [i for i, line in enumerate(daily_log) if line == header]
    ends = [i for i, line in enumerate(daily_log) if line == footer]
    if len(starts) != 1 or len(ends) != 1 or hashlib.sha256(
            "\n".join(daily_log[starts[0]:ends[0] + 1]).encode("utf-8")).hexdigest() \
            != expected["article_log_segment_sha256"]:
        return "catchup_article_daily_log_mismatch"

    run_dir = writer_root / "runs" / expected["writer_run_id"]
    if run_dir.is_symlink() or not run_dir.is_dir() \
            or any(os.path.lexists(run_dir / name) for name in DISPATCH_FILES):
        return "catchup_run_reached_publication"
    for name, digest in expected["run_artifacts"].items():
        path = run_dir / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return "catchup_run_artifact_mismatch"

    lines = _jsonl_lines(articles_path)
    if lines is None:
        return "articles_ledger_unreadable"
    for line in lines:
        try:
            row = json.loads(line)
            stamp = _ledger_row_epoch(row)
        except (ValueError, AttributeError):
            return "articles_ledger_unreadable"
        if str(row.get("run_id", "")) == expected["writer_run_id"]:
            return "catchup_run_has_ledger_row"
        if stamp is None and (row.get("published") is True or row.get("live_url")):
            return "articles_ledger_undated_publication"
        if stamp is not None and queued_at <= stamp <= until + PAIR_WINDOW_SECONDS:
            return "writer_ledger_row_in_window"

    stop_line = expected.get("no_drafts_stop_line")
    if stop_line is not None:
        segment = daily_log[starts[0]:ends[0] + 1]
        drafts = [name for name in ("article-ja.md", "article-en.md", "x-post-ja.txt")
                  if os.path.lexists(run_dir / name)]
        if drafts or stop_line not in segment:
            return "catchup_no_drafts_proof_mismatch"
        destinations = {pair: {"status": "absent", "reason": "run_produced_no_drafts"}
                        for pair in ABSENCE_DESTINATIONS}
    else:
        readback = absence_readback(run_dir, queued_at, until)
        destinations = (readback or {}).get("destinations") or {}
    not_absent = [pair for pair in ABSENCE_DESTINATIONS
                  if (destinations.get(pair) or {}).get("status") != "absent"]
    if not_absent:
        return "destination_not_proven_absent:" + ",".join(not_absent)
    runtime_run_id = occurrence_id.split(":", 1)[1]
    return {
        "owner_id": RESUME_OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
        "proof_type": "historical_writer_resume_no_dispatch", "provider": "writer",
        "runtime_run_id": runtime_run_id, "writer_run_id": expected["writer_run_id"],
        "branch": "missed-daily-schedule-catch-up",
        "release_sha": expected["release_sha"], "entrypoint_sha256": dict(expected["entrypoint_sha256"]),
        "event_hashes": list(expected["event_hashes"]),
        "article_log_segment_sha256": expected["article_log_segment_sha256"],
        "run_artifacts": dict(expected["run_artifacts"]),
        "window": {"since": _iso(queued_at), "until": _iso(until)},
        "destinations": {pair: destinations[pair] for pair in ABSENCE_DESTINATIONS},
        "evidence_ref": f"writer://fence-reconciliation/article-resume-{runtime_run_id}.json",
    }


def _pre_effect(occurrence_id: str, anchors: tuple[float, ...], state: str, rows: list, runs_root: Path,
                resolver: Callable[..., bool] | None, resolve: bool) -> dict:
    """Close a fence whose paired run stopped before any publication intent was registered.

    Positive evidence only: at least one run dir (or a resumed attempt of one) started in the pairing
    window, and none of the paired runs has a publication state or a ledger row.  Every managed
    publish adapter refuses without gates/publication-state.json, which publication-guard writes
    before the first live side effect.  No paired run -> the fence stays (absence of a run is not proof).
    """
    try:
        paired = sorted(d for d in runs_root.iterdir()
                        if d.is_dir() and any(_paired(started, anchors) for started in _run_starts(d)))
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


def _read_host_pre_effect_marker_sha256(occurrence_id: str, writer_root: Path) -> str | None:
    """Read the private original marker; a caller must separately prove the terminal boundary."""
    run_id = occurrence_id.split(":", 1)[1]
    if not run_id or not run_id.replace("-", "").isalnum():
        return None
    scratch = writer_root / "loop-tmp" / OWNER_ID / run_id
    marker = scratch / "entrypoint-result.json"
    descriptor = -1
    try:
        for directory in (writer_root, writer_root / "loop-tmp", scratch.parent, scratch):
            info = directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o022):
                return None
        descriptor = os.open(marker, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
            return None
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            data = stream.read(4097)
        if json.loads(data) != {"status": "pre_effect_failure", "effect": 0}:
            return None
        if os.path.lexists(scratch / "effect-identity.jsonl"):
            return None
    except (OSError, ValueError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return hashlib.sha256(data).hexdigest()


def _host_pre_effect_marker_sha256(occurrence_id: str, writer_root: Path) -> str | None:
    """Verify the surviving host marker and a non-zero terminal before model dispatch.

    A successful exit alone never proves no effect. Historical exit-0 stops require the
    separate exact source/event/log allowlist above as well as this original private marker.
    """
    marker_sha256 = _read_host_pre_effect_marker_sha256(occurrence_id, writer_root)
    if marker_sha256 is None:
        return None
    lines = _jsonl_lines(writer_root / "events.jsonl")
    try:
        events = [json.loads(line) for line in lines or [] if occurrence_id in line]
    except ValueError:
        return None
    terminals = [event for event in events if event.get("occurrence_id") == occurrence_id
                 and event.get("phase") == "report"]
    if (len(terminals) != 1 or type(terminals[0].get("exit_code")) is not int
            or terminals[0]["exit_code"] == 0
            or terminals[0].get("effect_identity_status") not in {None, "not_written"}
            or terminals[0].get("provider_receipt_id") is not None
            or terminals[0].get("official_readback_ref") is not None):
        return None
    return marker_sha256


DISPATCH_FILES = (PUBLICATION_STATE, "gates/platform-dispatch.jsonl", "gates/platform-dispatch-results.jsonl")
ABSENCE_DESTINATIONS = ("note/ja", "substack/ja", "substack/en", "x-article/ja")


def _official_absence_readback(run_dir: Path, since: float, until: float) -> dict | None:
    """Run the owner listings under the Writer env (credentials) with the managed Python."""
    scripts = REPO_ROOT / "skills/writer-agent/scripts"
    try:
        completed = subprocess.run(
            ["bash", "-c", 'source "$0" >/dev/null 2>&1 || exit 69; exec "$LIFE_MANAGER_PYTHON" "$@"',
             str(scripts / "writer-runtime-env.sh"), str(scripts / "article_absence_readback.py"),
             "--run-dir", str(run_dir), "--since", repr(since), "--until", repr(until)],
            capture_output=True, text=True, timeout=600, check=False,
            # Under lm-fence-reconciler LIFE_MANAGER_STATE_ROOT is the reconciler's own root, and
            # writer-runtime-env.sh falls back to it: note cookies were looked up there (2026-10-16).
            env={**os.environ, "WRITER_STATE_DIR": str(run_dir.parents[1]),
                 "ARTICLE_STATE_DIR": str(run_dir.parents[1])})
        return json.loads(completed.stdout.strip().splitlines()[-1]) if completed.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _terminal_epoch(writer_root: Path, occurrence_id: str) -> float | None:
    times = []
    for line in _jsonl_lines(writer_root / "events.jsonl") or []:
        if occurrence_id not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            return None
        if event.get("occurrence_id") == occurrence_id and event.get("phase") == "report":
            times.append(_epoch(event.get("timestamp")))
    return times[0] if len(times) == 1 else None


_KILLED_EXIT_CODES = {75, 124}   # plus 128+N signals


def _killed(code: object) -> bool:
    return type(code) is not int or code in _KILLED_EXIT_CODES or code >= 128


def _ended_naturally(writer_root: Path, occurrence_id: str, queued_at: float, runs_root: Path) -> bool:
    """The runner writes the single report event only after reaping the run's process group, so a
    reported run is over. A killed run (timeout/cancel) or a killed model pass can leave detached
    tool shells alive past the report, so those still wait out the hour (2026-10-17 review)."""
    reports = []
    for line in _jsonl_lines(writer_root / "events.jsonl") or []:
        if occurrence_id not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            return False
        if event.get("occurrence_id") == occurrence_id and event.get("phase") == "report":
            reports.append(event)
    if len(reports) != 1 or _killed(reports[0].get("exit_code")):
        return False
    try:
        paired = [d for d in runs_root.iterdir()
                  if d.is_dir() and any(0 <= s - queued_at <= PAIR_WINDOW_SECONDS for s in _run_starts(d))]
    except OSError:
        paired = []
    for run_dir in paired:
        try:
            attempts = json.loads((run_dir / "gates" / "generation-state.json").read_text(encoding="utf-8")).get("attempts")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict) \
                and "return_code" in attempts[-1] and _killed(attempts[-1]["return_code"]):
            return False
    return True


def _carry_over_absence(occurrence_id: str, queued_at: float, state: str, rows: list, runs_root: Path,
                        writer_root: Path, absence_readback: Callable[..., dict | None],
                        resolver: Callable[..., bool] | None, resolve: bool) -> dict | None:
    """A run whose only ledger trace is an unpublished carry-over row: prove absence officially.

    The model pass ran, so missing local dispatch files are not proof. Every active destination's
    authenticated owner listing must read the run's article absent; one unreadable keeps the fence.
    Returns None when this path does not apply.
    """
    try:
        paired = [d for d in runs_root.iterdir()
                  if d.is_dir() and any(0 <= s - queued_at <= PAIR_WINDOW_SECONDS for s in _run_starts(d))]
    except OSError:
        return None
    if len(paired) != 1:
        return None
    run_dir = paired[0]
    run_rows = [row for row in rows if str(row.get("run_id", "")) == run_dir.name]
    # Any unpublished row kind qualifies (2026-10-16 22:43: pending:media-renderer-unavailable rows);
    # the proof is the four official owner listings below, not the row's state name.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from article_daily_start_control import _no_effect_row  # same effect-free allowlist as start control
    if (not run_rows or not all(_no_effect_row(row) for row in run_rows)
            or any(os.path.lexists(run_dir / name) for name in DISPATCH_FILES)):
        return None
    until = _terminal_epoch(writer_root, occurrence_id)
    if until is None:
        return _inconclusive(occurrence_id, "carry_over_terminal_unreadable")
    readback = absence_readback(run_dir, queued_at, until)
    destinations = (readback or {}).get("destinations") or {}
    not_absent = [pair for pair in ABSENCE_DESTINATIONS
                  if (destinations.get(pair) or {}).get("status") != "absent"]
    if not_absent:
        held = _inconclusive(occurrence_id, "destination_not_proven_absent:" + ",".join(not_absent))
        # Keep each destination's own reason in the reconciler call log (readers never echo credentials).
        held["destinations"] = {pair: {key: (destinations.get(pair) or {}).get(key) for key in ("status", "reason")}
                                for pair in not_absent}
        return held
    runtime_run_id = occurrence_id.split(":", 1)[1]
    proof = {
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
        "proof_type": "historical_writer_gate_stop_no_dispatch", "provider": "writer",
        "runtime_run_id": runtime_run_id, "writer_run_id": run_dir.name,
        "window": {"since": _iso(queued_at), "until": _iso(until)},
        "article_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(run_dir.glob("article-*.md")) if p.is_file()},
        "destinations": {pair: destinations[pair] for pair in ABSENCE_DESTINATIONS},
        "evidence_ref": f"writer://fence-reconciliation/article-daily-{runtime_run_id}.json",
    }
    result = {"status": "no_dispatch_proven", "occurrence_id": occurrence_id, "closed": False,
              "writer_run_id": run_dir.name, "proof_ref": proof["evidence_ref"],
              "destinations": {pair: destinations[pair].get("status") for pair in ABSENCE_DESTINATIONS}}
    if not resolve:
        return result
    if not _persist_historical_gate_stop_proof(writer_root, proof):
        return _inconclusive(occurrence_id, "historical_proof_receipt_conflict")
    if resolver is None:
        from runtime.host.resource_admission import resolve_historical_no_dispatch_occurrence
        resolver = resolve_historical_no_dispatch_occurrence
    result["closed"] = bool(resolver(OWNER_ID, occurrence_id, no_dispatch_proof=lambda: proof,
                                     expected_state=state))
    return result


def _central_closure_result(owner_id: str, result: dict) -> dict:
    """Expose the exact proof contract consumed by lm-fence-reconciler."""
    if result.get("closed") is True:
        result["owner_id"] = owner_id
        result["verified"] = True
        proof_ref = result.get("proof_ref")
        if isinstance(proof_ref, str) and proof_ref.strip() and not result.get("evidence_ref"):
            result["evidence_ref"] = proof_ref
    return result


def _pair_anchors(writer_root: Path, occurrence_id: str, queued_at: float) -> tuple[float, ...]:
    """queued_at plus every runtime execute of this occurrence at or after it.

    A disk-floor or capacity defer can hold a queued occurrence for an hour, and a requeue can
    execute it more than once; a Writer run pairs with any of those starts, so every window is
    checked (an earlier execute's run that published must still be seen).
    """
    paths = [writer_root / "events.jsonl", *sorted(writer_root.glob("events-*.jsonl.gz"))]
    anchors = {queued_at}
    for path in paths:
        try:
            if path.suffix == ".gz":
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    lines = handle.read().splitlines()
            else:
                lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError, EOFError, zlib.error):
            continue
        for line in lines:
            if occurrence_id not in line:
                continue
            try:
                row = json.loads(line)
                if row.get("phase") == "execute" and row.get("occurrence_id") == occurrence_id:
                    start = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00")).timestamp()
                    if start >= queued_at:
                        anchors.add(start)
            except (ValueError, KeyError, TypeError):
                continue
    return tuple(sorted(anchors))


def _paired(start: float, anchors: tuple[float, ...]) -> bool:
    return any(0 <= start - anchor <= PAIR_WINDOW_SECONDS for anchor in anchors)


def reconcile(occurrence_id: str, *, queued_at: float, state: str, articles_path: Path = ARTICLES,
              fetch_status: Callable[[str], int] = _http_status, resolver: Callable[..., bool] | None = None,
              resolve: bool = False, now: float | None = None, runs_root: Path = RUNS_ROOT,
              pre_effect_resolver: Callable[..., bool] | None = None,
              writer_root: Path = WRITER_STATE_ROOT,
              source_repo: Path = SOURCE_REPO,
              fetch_json: Callable[[str], object] = _fetch_json,
              absence_readback: Callable[..., dict | None] = _official_absence_readback) -> dict:
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    if occurrence_id.startswith(f"{RESUME_OWNER_ID}:"):
        result = _reconcile_resume(occurrence_id, queued_at=queued_at, state=state,
                                   articles_path=articles_path, fetch_json=fetch_json,
                                   resolver=resolver, resolve=resolve, now=now, writer_root=writer_root,
                                   source_repo=source_repo, absence_readback=absence_readback)
        return _central_closure_result(RESUME_OWNER_ID, result)
    if not occurrence_id.startswith(f"{OWNER_ID}:"):
        return _inconclusive(occurrence_id, "owner_not_allowlisted")
    if now - queued_at < MIN_AGE_SECONDS and not _ended_naturally(writer_root, occurrence_id,
                                                                     queued_at, runs_root):
        return _inconclusive(occurrence_id, "fence_too_young")
    try:
        rows = [json.loads(line) for line in articles_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return _inconclusive(occurrence_id, "articles_ledger_unreadable")
    anchors = _pair_anchors(writer_root, occurrence_id, queued_at)
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
        if any(_paired(start, anchors) for start in starts):
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
            return _central_closure_result(OWNER_ID, result)
        marker_sha256 = None if candidates else _host_pre_effect_marker_sha256(occurrence_id, writer_root)
        if marker_sha256 is not None:
            run_id = occurrence_id.split(":", 1)[1]
            proof = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
                     "proof_type": "pre_effect",
                     "evidence_ref": f"lm-loop://{OWNER_ID}/{run_id}/entrypoint-result.json",
                     "entrypoint_result_sha256": marker_sha256}
            result = {"status": "pre_effect", "occurrence_id": occurrence_id, "closed": False,
                      "evidence_ref": proof["evidence_ref"]}
            if resolve:
                resolver_fn = pre_effect_resolver
                if resolver_fn is None:
                    from runtime.host.resource_admission import resolve_pre_effect_occurrence
                    resolver_fn = resolve_pre_effect_occurrence
                result["closed"] = bool(resolver_fn(OWNER_ID, occurrence_id,
                                                    pre_effect_readback=lambda: proof,
                                                    expected_state=state))
            return _central_closure_result(OWNER_ID, result)
        carry_over = None if candidates else _carry_over_absence(
            occurrence_id, queued_at, state, rows, runs_root, writer_root,
            absence_readback, resolver, resolve)
        if carry_over is not None:
            return _central_closure_result(OWNER_ID, carry_over)
        result = _pre_effect(occurrence_id, anchors, state, rows, runs_root,
                             pre_effect_resolver, resolve)
        return _central_closure_result(OWNER_ID, result)
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
    return _central_closure_result(OWNER_ID, result)


def _admission_row(occurrence_id: str) -> tuple[float, str, bool] | None:
    owner_id = occurrence_id.split(":", 1)[0]
    if owner_id not in {OWNER_ID, RESUME_OWNER_ID}:
        return None
    try:
        with sqlite3.connect(f"file:{ADMISSION_DB}?mode=ro", uri=True, timeout=20) as connection:
            row = connection.execute(
                "SELECT queued_at, state, effect_unknown FROM occurrences WHERE occurrence_id=? AND owner_id=?",
                (occurrence_id, owner_id)).fetchone()
    except sqlite3.Error:
        return None
    if row is None or type(row[2]) is not int or row[2] not in (0, 1):
        return None
    return (float(row[0]), str(row[1]), bool(row[2]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    row = _admission_row(args.occurrence)
    if row is None:
        result = _inconclusive(args.occurrence, "occurrence_not_fenced_or_unreadable")
    else:
        queued_at, state, effect_unknown = row
        already_released = state == "released" and not effect_unknown
        if effect_unknown or already_released:
            result = reconcile(
                args.occurrence, queued_at=queued_at, state=state,
                resolve=args.resolve and not already_released,
                articles_path=ARTICLES, runs_root=RUNS_ROOT,
                writer_root=WRITER_STATE_ROOT, source_repo=SOURCE_REPO,
            )
            if already_released and result.get("status") in {
                    "effected", "pre_effect", "no_dispatch_proven"}:
                # Revalidate an already-released occurrence without mutating admission state.
                result["closed"] = True
                result = _central_closure_result(args.occurrence.split(":", 1)[0], result)
        else:
            result = _inconclusive(args.occurrence, "occurrence_not_fenced_or_unreadable")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if (
        result["status"] in {"effected", "pre_effect", "no_dispatch_proven"}
        and (result["closed"] or not args.resolve)
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
