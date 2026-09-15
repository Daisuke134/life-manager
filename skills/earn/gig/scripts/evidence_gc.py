#!/usr/bin/env python3
"""Bound the evidence the gig loop writes, so a human never cleans this disk again.

WHY (measured against live ~/gig on 2026-07-30, before any policy existed)
-------------------------------------------------------------------------
    ~/gig/evidence   693 MB in 247 dirs + 114 loose files, grown in 2.1 days
                     => ~330 MB/day, unbounded.  Nothing in the loop deletes
                        anything the loop writes.  It filled the disk, a sentinel
                        raised a hard stop, and the loop was dead ~10 hours.

    PNG              3129 files, 619.5 MB = 89% of every evidence byte.
      inside pass dirs:
        PROOF  png    167 files,  27.6 MB  submitted/form/readback
        BROWSE png   2803 files, 561.4 MB  every request page the apply lane looked at

    gig-pass-*        57 dirs, 645 MB   (43 FAILED / 10 SUCCESS / 4 unknown)
    reply-detector-* 176 dirs, 1.5 MB, zero PNGs

The dominant lever is therefore the BROWSE screenshot -- 81% of all bytes, and
nothing ever reads one back.  It is NOT "failed vs successful pass": failed passes
are 75% of the corpus, so discarding only successful passes' screenshots would
reclaim 24%, not 81%.

DESIGN (copied from proven external implementations, not invented here)
----------------------------------------------------------------------
  * High/low watermark with hysteresis, not a binary stop
        kubernetes/kubernetes pkg/kubelet/images/image_gc_manager.go
        openclaw/openclaw     src/config/sessions/disk-budget.ts
    Start collecting above `high_water_bytes`, evict oldest-first by mtime, stop
    at `low_water_bytes`, resume work.  Never collect below high.
  * Dual bound: count AND bytes, and always keep at least one
        Dicklesworthstone/claude_code_agent_farm _cleanup_old_backups
  * Tiered retention expressed as data, not code branches
        restic/restic internal/data/snapshot_policy.go ExpirePolicy{Last, Daily}
    keep last N, plus the newest survivor of each of the last M days.
  * Real runs partitioned from no-op ticks so no-ops cannot evict real history
        openclaw/openclaw src/tasks/cron-history-retention.ts
    Each partition owns an independent count budget; 288 reply-detector ticks a
    day can never push out a gig-pass.
  * The sweeper lives in the runtime and self-schedules; it is not a new cron
        Arize-ai/phoenix src/phoenix/server/retention.py TraceDataSweeper
    Called once per pass from gig_pass.sh and again from the hourly auditor.

SAFETY (hard, and each one has a test)
--------------------------------------
  * Structural: this only ever walks `evidence_root`.  It REFUSES to run at all if
    that root contains `projects/` or `deliverables/`, or resolves to the state
    dir -- so a misconfigured GIG_EVIDENCE_ROOT cannot reach client deliverables.
  * Never deletes a file matching PROTECTED_GLOBS: ledgers (*.jsonl), databases
    (*.sqlite3*), archives, and every application-proof artefact.  The proof set
    is not cosmetic: normalize_applied._evidence_ids and
    application_report._proven_ids glob `*-B2-*-submitted.png` off the evidence
    ROOT to prove an application really happened and to heal the ledger.
  * Never deletes evidence pinned by an unresolved record: `.last-pass`, live
    lane locks, open rows in gig-control.sqlite3 repair_queue, or recent paths
    named by pass-failures.jsonl, report-envelopes.jsonl, and applied.jsonl.
  * Never deletes the currently running pass's own evidence dir.
  * Crash-safe: a directory is renamed into `<name>.gc-trash.<pid>` first, then
    unlinked.  A killed sweeper leaves only trash, which the next run reaps.
  * Never fatal: every failure is swallowed and reported in the result.  The CLI
    always exits 0 -- same contract as the reporting path.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

MiB = 1024 * 1024

TRASH_SUFFIX = ".gc-trash."

# ---------------------------------------------------------------------------
# Policy -- data, not code branches.  Every constant is justified inline from the
# measured distribution in the module docstring above.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    # Whole-root byte ceiling.  Measured steady state under this policy is
    # ~165 MB (48 passes of JSON/logs + 6 passes of browse screenshots + all
    # retained proof).  400 MiB leaves 2.4x headroom for a burst day while
    # capping the worst case three orders of magnitude below the 5.3 GB that
    # killed the loop.
    high_water_bytes: int = 400 * MiB
    # 250 MiB is a 150 MiB gap = ~11 passes of hysteresis at the measured
    # 13.7 MB/pass, so GC does not thrash on consecutive passes.
    low_water_bytes: int = 250 * MiB

    # gig-pass-*: real runs.  24 passes/day, so keep_last=48 is two full days of
    # complete evidence, then one survivor per day for a further week.
    gig_pass_keep_last: int = 48
    gig_pass_keep_daily: int = 7

    # gig-apply-direct-*: direct Apply wakes run every five minutes; keep one day
    # of complete run directories, plus one survivor per day for a week.
    apply_direct_keep_last: int = 288
    apply_direct_keep_daily: int = 7

    # reply-detector-*: no-op ticks every 300s = 288/day at ~8.5 KB each.  These
    # are 0.2% of bytes but 71% of directories, so they are bounded by COUNT
    # (inode pressure), in their own partition so they cannot evict real runs.
    detector_keep_last: int = 48
    detector_keep_daily: int = 1

    # Everything else (manual/ad-hoc capture dirs): conservative.
    other_keep_last: int = 20
    other_keep_daily: int = 14

    # Browse screenshots inside a RETAINED pass dir.  6 h = the 6 most recent
    # passes keep their full visual trail (~60 MB); older passes keep JSON, DOM,
    # logs and every proof image.  A FAILED pass keeps its trail 24 h because
    # that trail is what a debugging agent actually opens.
    screenshot_ttl_success_seconds: int = 6 * 3600
    screenshot_ttl_failed_seconds: int = 24 * 3600

    # Loose files sitting directly in the evidence root that match nothing
    # protected (scratch screenshots): 7 days.
    root_file_ttl_seconds: int = 7 * 86400

    # How long an append-only ledger row (pass-failures / applied /
    # report-envelopes) keeps pinning the directory it cites.  48 h matches
    # gig_pass_keep_last=48 -- inside the full-evidence window a citation is a
    # real debug handle; outside it the durable proof is the ledger row plus the
    # immortal root-level *-submitted.png.  Measured 2026-07-30: treating these
    # citations as permanent pins produced 228 pins over 249 dirs and reclaimed
    # 3% of the corpus.
    pin_horizon_seconds: int = 48 * 3600

    def keep_last_for(self, partition: str) -> int:
        return {"gig-pass": self.gig_pass_keep_last,
                "reply-detector": self.detector_keep_last,
                "apply-direct": self.apply_direct_keep_last}.get(partition, self.other_keep_last)

    def keep_daily_for(self, partition: str) -> int:
        return {"gig-pass": self.gig_pass_keep_daily,
                "reply-detector": self.detector_keep_daily,
                "apply-direct": self.apply_direct_keep_daily}.get(partition, self.other_keep_daily)


# Never deleted, anywhere, at any pressure.  Ledgers, databases, archives, and
# every artefact the loop reads back as proof that real work happened.
PROTECTED_GLOBS: tuple[str, ...] = (
    "*.jsonl", "*.sqlite3", "*.sqlite3-wal", "*.sqlite3-shm", "*.db", "*.db-wal", "*.db-shm",
    "*.zip", "*.mcaddon", "*.pdf",
    "*-submitted.png", "*-submitted.json",
    "*-submitted.intent.json", "*-submitted.eligibility.json",
    "*-form.png", "*-form.json",
    "code-applied-readback.png", "code-applied-readback.json",
)
_PROTECTED_RE = re.compile(
    "|".join(
        "(?:%s)" % g.replace(".", r"\.").replace("*", "[^/]*") for g in PROTECTED_GLOBS
    )
    + "$"
)

# Directories that must never appear under the evidence root.  Their presence
# means the root is misconfigured and GC refuses rather than guessing.
FORBIDDEN_CHILDREN = ("projects", "deliverables")

PARTITION_PREFIXES = (
    ("gig-pass", "gig-pass-"),
    ("reply-detector", "reply-detector-"),
    ("apply-direct", "gig-apply-direct-"),
)

_PASS_ID_FROM_DIR = re.compile(r"^gig-pass-(.+)$")
_LEADING_EPOCH = re.compile(r"(\d{9,})")
# Keep a just-finished pass intact for the sibling auditor's read window.
_RECENT_PASS_GRACE_SECONDS = 3600


@dataclass
class GcResult:
    refused: bool = False
    refused_reason: str = ""
    dirs_removed: int = 0
    files_removed: int = 0
    screenshots_removed: int = 0
    trash_reaped: int = 0
    bytes_reclaimed: int = 0
    total_bytes_before: int = 0
    total_bytes_after: int = 0
    errors: int = 0
    referenced_pins: list[str] = field(default_factory=list)

    def as_record(self) -> dict:
        record = asdict(self)
        record["referenced_pins"] = len(self.referenced_pins)
        return record

    def summary(self) -> str:
        if self.refused:
            return f"evidence gc refused ({self.refused_reason})"
        return (
            "evidence gc reclaimed %d items / %.1f MB "
            "(dirs=%d files=%d screenshots=%d trash=%d errors=%d) total %.1f -> %.1f MB"
            % (self.dirs_removed + self.files_removed, self.bytes_reclaimed / MiB,
               self.dirs_removed, self.files_removed, self.screenshots_removed,
               self.trash_reaped, self.errors,
               self.total_bytes_before / MiB, self.total_bytes_after / MiB)
        )


# ---------------------------------------------------------------------------
# Filesystem helpers -- every one of them is failure-tolerant by construction.
# ---------------------------------------------------------------------------


def tree_bytes(path: Path) -> int:
    """Sum of st_size below `path`, ignoring anything unreadable."""
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for current, dirs, files in os.walk(path, onerror=lambda _e: None):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(current, d))]
        for name in files:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                continue
    return total


def is_protected_name(name: str) -> bool:
    return bool(_PROTECTED_RE.match(name)) or "-B2-" in name and name.endswith(".json")


def _entry_mtime(path: Path, name: str) -> float:
    """Prefer the epoch embedded in the directory name; fall back to mtime.

    Names look like `gig-pass-1785417447-31011` / `reply-detector-1785417935-98045`.
    The embedded epoch is stable even when a later read touches the directory.
    """
    match = _LEADING_EPOCH.search(name)
    if match:
        candidate = int(match.group(1))
        if 1_000_000_000 < candidate < 4_000_000_000:
            return float(candidate)
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def partition_of(name: str) -> str:
    for label, prefix in PARTITION_PREFIXES:
        if name.startswith(prefix):
            return label
    return "other"


# ---------------------------------------------------------------------------
# What is still referenced?  Nothing pinned here is ever collected.
# ---------------------------------------------------------------------------


def _iter_jsonl(path: Path, limit: int = 5000):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except (ValueError, TypeError):
            continue


def _harvest_paths(node, root_str: str, sink: set[str]) -> None:
    if isinstance(node, str):
        if root_str in node:
            sink.add(node)
    elif isinstance(node, dict):
        for value in node.values():
            _harvest_paths(value, root_str, sink)
    elif isinstance(node, list):
        for value in node:
            _harvest_paths(value, root_str, sink)


def _process_start_signature(pid: int) -> str | None:
    """Return a stable OS process-start token, or None when it cannot be proven."""
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True, text=True, check=False, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _pid_is_live(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def register_live_evidence_pin(state_dir: Path, evidence_dir: Path, lane: str) -> Path:
    """Publish one atomic, PID-identity-bound pin for the lifetime of this process."""
    state_dir = Path(state_dir)
    evidence_dir = Path(evidence_dir).resolve(strict=True)
    pid = os.getpid()
    process_start = _process_start_signature(pid)
    if not process_start:
        raise OSError("cannot establish process-start identity for evidence pin")
    state_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".evidence-pin-", dir=state_dir))
    target = state_dir / f".gig-pass-{lane}-{pid}-{time.time_ns()}.lock.d"
    try:
        (temporary / "pid").write_text(f"{pid}\n", encoding="utf-8")
        (temporary / "meta.json").write_text(json.dumps({
            "pid": pid,
            "process_start": process_start,
            "evidence_dir": str(evidence_dir),
        }, sort_keys=True) + "\n", encoding="utf-8")
        os.rename(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    atexit.register(shutil.rmtree, target, True)
    return target


def _running_sibling_evidence(state_dir: Path, evidence_root: Path) -> set[str]:
    """Pin live lane trees from direct Hermes lock metadata, fail closed otherwise."""
    try:
        root = evidence_root.resolve()
    except OSError:
        return set()
    pins: set[str] = set()
    for lock_dir in state_dir.glob(".gig-pass-*.lock.d"):
        if lock_dir.is_symlink() or not lock_dir.is_dir():
            continue
        pid_path = lock_dir / "pid"
        metadata_path = lock_dir / "meta.json"
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(metadata, dict) or pid <= 0:
            continue
        if metadata.get("pid") != pid:
            continue
        actual_start = _process_start_signature(pid)
        if actual_start and metadata.get("process_start") != actual_start:
            continue
        # A transient `ps` timeout must retain evidence, not turn observability
        # failure into deletion. A reused PID is excluded above when `ps` works;
        # when it does not, over-retaining for a live PID is the safe outcome.
        if not actual_start and not _pid_is_live(pid):
            continue
        candidate = metadata.get("evidence_dir")
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        try:
            path = Path(candidate)
            if path.is_symlink():
                continue
            path = path.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if path.parent == root and path.is_dir() and not path.is_symlink():
            pins.add(str(evidence_root / path.relative_to(root)))
    return pins


def referenced_evidence(
    state_dir: Path,
    evidence_root: Path,
    *,
    now: float | None = None,
    horizon_seconds: int = 0,
) -> set[str]:
    """Top-level evidence entries pinned by an open or unresolved record.

    Two kinds of pin, and conflating them is what makes a GC do nothing:

      UNCONDITIONAL -- genuinely open state.  The `.last-pass` heartbeat (exactly
        one dir) and repair_queue rows still in queued/claimed/blocked (bounded by
        a unique index to one open row per fingerprint).  These really can be
        resolved, so they really can stop pinning.

      HORIZON-BOUND -- append-only history.  pass-failures.jsonl, applied.jsonl and
        report-envelopes.jsonl never resolve anything; every row they ever wrote
        cites an evidence dir forever.  Measured on live ~/gig 2026-07-30: taking
        those as "unresolved" produced 228 pins over 249 directories and reclaimed
        21 MB of 668 MB -- a GC that does nothing.  A failure from three days ago
        is closed by time, not by a writer.  So those rows only pin evidence
        younger than `horizon_seconds`; older rows keep their durable proof, which
        lives in the ledger row itself plus the root-level `*-submitted.png` /
        `*.intent.json` artefacts that PROTECTED_GLOBS makes immortal.
        (Dangling historical paths are already the status quo and already
        tolerated: 29 of applied.jsonl's 60 cited paths were absent when measured.)
    """
    root_str = str(evidence_root)
    now = time.time() if now is None else now
    raw: set[str] = set()
    horizon_raw: set[str] = set()

    heartbeat = state_dir / ".last-pass"
    try:
        _harvest_paths(json.loads(heartbeat.read_text(encoding="utf-8")), root_str, raw)
    except (OSError, ValueError):
        pass

    for name in ("pass-failures.jsonl", "report-envelopes.jsonl", "applied.jsonl"):
        for row in _iter_jsonl(state_dir / name, limit=2000):
            _harvest_paths(row, root_str, horizon_raw)

    # Open incidents in the repair queue.  Recovered/blocked-closed rows do NOT
    # pin: otherwise every incident ever raised would pin evidence forever.
    control = state_dir / "gig-control.sqlite3"
    if control.exists():
        try:
            connection = sqlite3.connect(f"file:{control}?mode=ro", uri=True, timeout=5)
            try:
                rows = connection.execute(
                    "SELECT evidence_json, last_action_json FROM repair_queue"
                    " WHERE state IN ('queued','claimed','blocked')"
                ).fetchall()
            except sqlite3.Error:
                rows = connection.execute(
                    "SELECT evidence_json FROM repair_queue"
                    " WHERE state IN ('queued','claimed','blocked')"
                ).fetchall()
            for row in rows:
                for cell in row:
                    if not cell:
                        continue
                    try:
                        _harvest_paths(json.loads(cell), root_str, raw)
                    except (ValueError, TypeError):
                        _harvest_paths(cell, root_str, raw)
            connection.close()
        except sqlite3.Error:
            pass

    # Collapse every cited path to the top-level evidence entry that contains it.
    def collapse(candidates: set[str]) -> set[str]:
        out: set[str] = set()
        try:
            resolved_root = evidence_root.resolve()
        except OSError:
            return out
        for candidate in candidates:
            try:
                relative = Path(candidate).resolve().relative_to(resolved_root)
            except (ValueError, OSError):
                continue
            parts = relative.parts
            if parts:
                out.add(str(evidence_root / parts[0]))
        return out

    pins = collapse(raw)
    pins.update(_running_sibling_evidence(state_dir, evidence_root))
    for entry in collapse(horizon_raw):
        if horizon_seconds <= 0:
            pins.add(entry)
            continue
        path = Path(entry)
        if now - _entry_mtime(path, path.name) <= horizon_seconds:
            pins.add(entry)
    return pins


def pass_outcomes(state_dir: Path) -> dict[str, str]:
    """pass_id -> 'failed' | 'success'.  Failure wins: it is the debug case."""
    outcomes: dict[str, str] = {}
    for row in _iter_jsonl(state_dir / "pass-report.jsonl"):
        pass_id = row.get("pass_id")
        if pass_id:
            outcomes[str(pass_id)] = "success"
    for row in _iter_jsonl(state_dir / "pass-failures.jsonl"):
        pass_id = row.get("pass_id")
        if pass_id:
            outcomes[str(pass_id)] = "failed"
    return outcomes


def direct_run_outcome(run_dir: Path) -> str:
    """Read the direct run's terminal result; missing or malformed means failed."""
    try:
        payload = json.loads((Path(run_dir) / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return "failed"
    return "success" if isinstance(payload, dict) and payload.get("status") == "ok" else "failed"


# ---------------------------------------------------------------------------
# Deletion primitives -- crash-safe and idempotent.
# ---------------------------------------------------------------------------


def _reap_trash(evidence_root: Path, result: GcResult) -> None:
    """Remove leftovers from a sweeper that was killed mid-run."""
    try:
        entries = list(evidence_root.iterdir())
    except OSError:
        return
    for entry in entries:
        if TRASH_SUFFIX not in entry.name:
            continue
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            result.trash_reaped += 1
        except OSError:
            result.errors += 1


def _remove_dir(path: Path, result: GcResult) -> int:
    """Rename-then-delete: a kill between the two steps leaves reapable trash."""
    size = tree_bytes(path)
    trash = path.with_name(f"{path.name}{TRASH_SUFFIX}{os.getpid()}")
    try:
        os.rename(path, trash)
    except OSError:
        # Already gone (idempotent) or unmovable (permissions) -- never fatal.
        if path.exists():
            result.errors += 1
        return 0
    shutil.rmtree(trash, ignore_errors=True)
    if trash.exists():
        # Partially removed: leave it as trash for the next run rather than
        # reporting bytes we did not actually reclaim.
        remaining = tree_bytes(trash)
        result.errors += 1
        size = max(size - remaining, 0)
    result.dirs_removed += 1
    result.bytes_reclaimed += size
    return size


def _remove_file(path: Path, result: GcResult, *, screenshot: bool = False) -> int:
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    try:
        path.unlink()
    except OSError:
        result.errors += 1
        return 0
    result.files_removed += 1
    if screenshot:
        result.screenshots_removed += 1
    result.bytes_reclaimed += size
    return size


# ---------------------------------------------------------------------------
# The sweeper.
# ---------------------------------------------------------------------------


@dataclass
class _Entry:
    path: Path
    name: str
    partition: str
    mtime: float
    size: int
    pinned: bool
    current: bool = False
    full_protected: bool = False


def _validate_root(state_dir: Path, evidence_root: Path) -> str:
    """Refuse rather than guess when the root could swallow real work."""
    try:
        resolved = evidence_root.resolve()
    except OSError as exc:
        return f"unresolvable evidence root: {exc}"
    if resolved == Path(os.path.expanduser("~")).resolve():
        return "evidence root is the home directory"
    try:
        if resolved == state_dir.resolve():
            return "evidence root equals the state dir"
    except OSError:
        pass
    for child in FORBIDDEN_CHILDREN:
        if (resolved / child).exists():
            return f"evidence root contains {child}/ (client deliverables)"
    if len(resolved.parts) < 3:
        return "evidence root is too close to the filesystem root"
    return ""


def _select_expired(entries: list[_Entry], policy: Policy, now: float) -> list[_Entry]:
    """restic-style tiers, per partition, dual-bounded, always keeping one."""
    expired: list[_Entry] = []
    by_partition: dict[str, list[_Entry]] = {}
    for entry in entries:
        by_partition.setdefault(entry.partition, []).append(entry)

    for partition, group in by_partition.items():
        group.sort(key=lambda e: e.mtime, reverse=True)
        keep_last = policy.keep_last_for(partition)
        keep_daily = policy.keep_daily_for(partition)

        keep: set[Path] = {e.path for e in group[:keep_last]}
        # ...plus the newest survivor of each of the last `keep_daily` days.
        seen_days: set[int] = set()
        for entry in group:
            day = int((now - entry.mtime) // 86400)
            if day < keep_daily and day not in seen_days:
                seen_days.add(day)
                keep.add(entry.path)
        # Dicklesworthstone: always keep at least one, whatever the limits say.
        if not keep and group:
            keep.add(group[0].path)

        for entry in group:
            if entry.path not in keep and not entry.pinned:
                expired.append(entry)
    return expired


def collect(
    *,
    state_dir: Path,
    evidence_root: Path,
    policy: Policy | None = None,
    now: float | None = None,
    current_evidence_dir: Path | None = None,
) -> GcResult:
    """Bound `evidence_root`.  Never raises; never touches anything outside it."""
    policy = policy or Policy()
    now = time.time() if now is None else now
    state_dir = Path(state_dir)
    evidence_root = Path(evidence_root)
    result = GcResult()

    if not evidence_root.is_dir():
        return result

    reason = _validate_root(state_dir, evidence_root)
    if reason:
        result.refused = True
        result.refused_reason = reason
        return result

    try:
        result.total_bytes_before = tree_bytes(evidence_root)
        _reap_trash(evidence_root, result)

        pins = referenced_evidence(
            state_dir, evidence_root, now=now,
            horizon_seconds=policy.pin_horizon_seconds,
        )
        running_pins = _running_sibling_evidence(state_dir, evidence_root)
        current_key = str(Path(current_evidence_dir)) if current_evidence_dir is not None else None
        if current_key is not None:
            pins.add(current_key)
        outcomes = pass_outcomes(state_dir)

        entries: list[_Entry] = []
        loose: list[_Entry] = []
        try:
            children = sorted(evidence_root.iterdir())
        except OSError:
            children = []
        for child in children:
            if TRASH_SUFFIX in child.name or child.is_symlink():
                continue
            child_mtime = _entry_mtime(child, child.name)
            try:
                recent_mtime = child.stat().st_mtime
            except OSError:
                recent_mtime = child_mtime
            recent = (partition_of(child.name) in {"gig-pass", "apply-direct"}
                      and now - recent_mtime <= _RECENT_PASS_GRACE_SECONDS)
            full_protected = str(child) in running_pins or recent
            if full_protected:
                pins.add(str(child))
            record = _Entry(
                path=child, name=child.name, partition=partition_of(child.name),
                mtime=child_mtime, size=tree_bytes(child),
                pinned=str(child) in pins, current=str(child) == current_key,
                full_protected=full_protected,
            )
            (entries if child.is_dir() else loose).append(record)
        result.referenced_pins = sorted(pins)

        # --- phase A: strip browse screenshots from RETAINED pass dirs ---------
        # 81% of all bytes, and nothing reads one back.  Cheapest reclaim first,
        # so eviction of whole directories is usually unnecessary.
        #
        # A PIN DELIBERATELY DOES NOT EXEMPT A DIRECTORY FROM THIS.  A pin means
        # "keep this directory", not "keep every photograph of every request page
        # the apply lane scrolled past".  Phase A can only ever delete a *.png
        # that is not in PROTECTED_GLOBS, so a pinned pass keeps 100% of its JSON,
        # DOM, logs, and every proof image either way.  Measured 2026-07-30:
        # exempting pinned dirs here left phase A reclaiming 16.8 MB of a 619.5 MB
        # PNG mass, because the whole live corpus was younger than the pin
        # horizon.  A current, actively running sibling, or just-finished pass is
        # still being written/audited, so its root and every child remain intact.
        for entry in entries:
            if entry.partition not in {"gig-pass", "apply-direct"} or entry.current or entry.full_protected:
                continue
            if entry.partition == "apply-direct":
                outcome = direct_run_outcome(entry.path)
            else:
                match = _PASS_ID_FROM_DIR.match(entry.name)
                outcome = outcomes.get(match.group(1), "failed") if match else "failed"
            ttl = (policy.screenshot_ttl_failed_seconds if outcome == "failed"
                   else policy.screenshot_ttl_success_seconds)
            if now - entry.mtime < ttl:
                continue
            freed = _strip_screenshots(entry.path, result)
            entry.size = max(entry.size - freed, 0)

        # --- phase B: tiered retention, per partition -------------------------
        for expired in _select_expired(entries, policy, now):
            _remove_dir(expired.path, result)
            expired.size = 0

        # Loose root files: protected ones are immortal, the rest age out.
        for entry in loose:
            if entry.pinned or is_protected_name(entry.name):
                continue
            if now - entry.mtime > policy.root_file_ttl_seconds:
                _remove_file(entry.path, result, screenshot=entry.name.endswith(".png"))
                entry.size = 0

        # --- phase C: watermark with hysteresis (kubelet) ----------------------
        total = result.total_bytes_before - result.bytes_reclaimed
        if total > policy.high_water_bytes:
            survivors = [e for e in entries + loose
                         if e.size > 0 and not e.pinned
                         and not (e.path.is_file() and is_protected_name(e.name))
                         and e.path.exists()]
            # openclaw disk-budget: mtime-ascending queue, break once under.
            survivors.sort(key=lambda e: e.mtime)
            for entry in survivors:
                if total <= policy.low_water_bytes:
                    break
                if len(survivors) <= 1:
                    break
                if entry.path.is_dir():
                    total -= _remove_dir(entry.path, result)
                else:
                    total -= _remove_file(entry.path, result,
                                          screenshot=entry.name.endswith(".png"))
                survivors = survivors[1:] if survivors and survivors[0] is entry else survivors

        result.total_bytes_after = result.total_bytes_before - result.bytes_reclaimed
    except Exception:  # noqa: BLE001 -- a sweeper may never break a pass
        result.errors += 1
        result.total_bytes_after = result.total_bytes_before - result.bytes_reclaimed
    return result


def _strip_screenshots(directory: Path, result: GcResult) -> int:
    """Delete non-proof PNGs inside a directory we are otherwise keeping."""
    freed = 0
    for current, dirs, files in os.walk(directory, onerror=lambda _e: None):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(current, d))]
        for name in files:
            if not name.endswith(".png") or is_protected_name(name):
                continue
            freed += _remove_file(Path(current) / name, result, screenshot=True)
    return freed


# ---------------------------------------------------------------------------
# CLI -- one line of evidence into the pass's own record.  Always exits 0.
# ---------------------------------------------------------------------------


def _record(result: GcResult, state_dir: Path, current_evidence_dir: Path | None) -> None:
    record = result.as_record()
    record["ts"] = int(time.time())
    record["driver"] = "evidence_gc.py"
    payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))

    # Per-pass: alongside every other <name>-result.json the lanes already write.
    if current_evidence_dir is not None:
        try:
            target = Path(current_evidence_dir)
            target.mkdir(parents=True, exist_ok=True)
            (target / "evidence-gc.json").write_text(payload + "\n", encoding="utf-8")
        except OSError:
            pass

    # Durable: the pass dir is itself collectable, so keep one compact row per
    # sweep next to the other ~/gig ledgers.  ~200 B x 24 passes/day = 1.7 MB/yr.
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        with (state_dir / "evidence-gc.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state-dir", type=Path, default=Path.home() / "gig")
    parser.add_argument("--evidence-root", type=Path, default=None)
    parser.add_argument("--current-evidence-dir", type=Path, default=None)
    parser.add_argument("--high-water-bytes", type=int, default=None)
    parser.add_argument("--low-water-bytes", type=int, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    state_dir = args.state_dir.expanduser()
    evidence_root = args.evidence_root.expanduser() if args.evidence_root else state_dir / "evidence"
    # `--current-evidence-dir ""` (an unset shell variable) must not become
    # Path(".") and drop evidence-gc.json into whatever cwd the caller had.
    current = args.current_evidence_dir.expanduser() if args.current_evidence_dir else None
    if current is not None and str(current) in ("", "."):
        current = None
    overrides = {}
    if args.high_water_bytes is not None:
        overrides["high_water_bytes"] = args.high_water_bytes
    if args.low_water_bytes is not None:
        overrides["low_water_bytes"] = args.low_water_bytes

    try:
        result = collect(
            state_dir=state_dir,
            evidence_root=evidence_root,
            policy=Policy(**overrides),
            current_evidence_dir=current,
        )
        _record(result, state_dir, current)
        if not args.quiet:
            print(result.summary(), file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        # A sweeper may never change a pass's exit code.
        print(f"evidence gc skipped: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
