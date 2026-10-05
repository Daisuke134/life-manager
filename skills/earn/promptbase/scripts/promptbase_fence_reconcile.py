#!/usr/bin/env python3
"""Close one promptbase-loop-daily effect_unknown admission fence.

promptbase-loop-daily runs skills/earn/promptbase/daily.sh, whose only
PromptBase-mutating step is publish.py --confirm (drives the CDP browser to
submit the /sell wizard). If the process dies between a real submit and the
ledger.append that records it, the host admission layer fences the
occurrence with effect_unknown (resource_admission.release_and_reserve_resource
sets it whenever effect_class != "none" and the child exited non-zero).

There is no PromptBase HTTP API: the only official readback is the seller
dashboard itself, the same account?view=prompts text readback.py already
parses with parse_dashboard_cards/status_for_title, read over the SAME
interactive:dais lease-wrapped CDP endpoint daily.sh uses -- never a fresh
login and never a second submit.

Precision: daily.sh writes one immutable, occurrence-bound snapshot before
calling publish.py --confirm. Only a well-formed schema-1 snapshot with a
matching owner, occurrence, and timestamp may prove that an explicit null
candidate was not dispatched. Missing, malformed, partial, or misbound
snapshots stay held; they never prove no effect.

Decision:
  - a valid schema-2 snapshot with explicit null slug/title -> no-effect
    immediately (the active admitted run selected no candidate).
  - missing, legacy, malformed, or unbound snapshot -> inconclusive, stays fenced.
  - the ledger already has a row for that slug recorded at/after queued_at ->
    effected via the existing local ledger row (daily.sh crashed on something
    unrelated after already recording the submission).
  - the slug's title shows Approved/Pending/Scheduled on the dashboard and the
    ledger has no such row yet -> effected: append the missing ledger row and
    close via resolve_unknown_occurrence, receipt = the dashboard status.
  - title absent from the dashboard and not enough time has passed yet ->
    inconclusive, stays fenced (never guess early).
  - title absent from the dashboard and enough time has passed -> no-effect:
    write evidence and close via resolve_pre_effect_occurrence.
  - dashboard read failure (lease busy, CDP unreachable, exception) ->
    inconclusive, stays fenced.

Usage:
    python3 promptbase_fence_reconcile.py --occurrence promptbase-loop-daily:<run_id> [--resolve]
    python3 promptbase_fence_reconcile.py --occurrence promptbase-loop-daily:<run_id> \\
        --record-snapshot [--slug <slug> --title <title>]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(HERE))
import ledger as ledger_mod  # noqa: E402
import readback as readback_mod  # noqa: E402

OWNER_ID = "promptbase-loop-daily"
# Generous ceiling for one dry-run-then-confirm wizard fill + reCAPTCHA wait.
MAX_RUN_SECONDS = 900
# PromptBase's dashboard is a synchronous read of the seller's own account,
# not an eventually-consistent public listing -- this buffer only covers
# clock skew and admission-layer release latency.
POST_PROCESSING_DELAY_SECONDS = 300
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + POST_PROCESSING_DELAY_SECONDS

SNAPSHOT_DIR = Path(
    "~/.local/state/life-manager/state/promptbase-loop-daily-snapshots"
).expanduser()
EVIDENCE_DIR = Path("~/.local/state/life-manager/reconciliation/evidence").expanduser()
BROWSER_GUARD = Path(
    os.environ.get("AI_BROWSER_GUARD", str(REPO_ROOT / "skills/browser/browser-guard.sh"))
)
BROWSER_IDENTITY = "interactive:dais"
SNAPSHOT_FIELDS = frozenset({
    "schema_version", "owner_id", "occurrence_id", "slug", "title", "captured_at",
    "capture_provenance",
})
CAPTURE_FIELDS = frozenset({
    "source", "owner_id", "occurrence_id", "run_id", "phase", "claim_pid",
    "claim_process_start", "capture_pid", "capture_process_start", "queued_at",
})
CAPTURE_SOURCE = "resource-admission-v2-active-claim"
_OCCURRENCE_SUFFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _safe_occurrence(occurrence_id: str) -> str:
    return occurrence_id.replace(":", "_").replace("/", "_")


def _valid_occurrence_id(occurrence_id: str) -> bool:
    prefix = f"{OWNER_ID}:"
    if (not isinstance(occurrence_id, str) or len(occurrence_id) > 128
            or not occurrence_id.startswith(prefix)):
        return False
    return _OCCURRENCE_SUFFIX.fullmatch(occurrence_id[len(prefix):]) is not None


def capture_active_admission(
    owner_id: str, occurrence_id: str, *,
    state_root_fn: Callable[[], Path] | None = None,
    process_start_fn: Callable[[int], str | None] | None = None,
    pid_fn: Callable[[], int] = os.getpid,
    ppid_fn: Callable[[], int] = os.getppid,
    environ: Mapping[str, str] | None = None,
) -> dict | None:
    """Read-only proof that this writer is a child of the active owner claim."""
    try:
        from runtime.host import resource_admission

        if (owner_id != OWNER_ID or not _valid_occurrence_id(occurrence_id)):
            return None
        env = os.environ if environ is None else environ
        run_id = env.get("LIFE_MANAGER_RUN_ID")
        if (env.get("LIFE_MANAGER_OCCURRENCE_ID") != occurrence_id
                or env.get("LIFE_MANAGER_LOOP_ID") not in (None, owner_id)
                or not isinstance(run_id, str) or not _SAFE_RUN_ID.fullmatch(run_id)
                or run_id in {".", ".."}):
            return None

        capture_pid = pid_fn()
        claim_pid = ppid_fn()
        if (type(capture_pid) is not int or capture_pid <= 0
                or type(claim_pid) is not int or claim_pid <= 0):
            return None
        process_start = process_start_fn or resource_admission.process_start
        capture_start = process_start(capture_pid)
        claim_start = process_start(claim_pid)
        if (not isinstance(capture_start, str) or not capture_start.strip()
                or not isinstance(claim_start, str) or not claim_start.strip()):
            return None

        root = (state_root_fn or resource_admission.state_root)()
        database = root / "admission-v2.sqlite3"
        connection = sqlite3.connect(
            f"{database.as_uri()}?mode=ro", uri=True, timeout=2.0,
        )
        try:
            connection.execute("PRAGMA query_only=ON")
            if connection.execute("PRAGMA query_only").fetchone() != (1,):
                return None
            occurrence = connection.execute(
                """SELECT owner_id,queued_at,state,effect_unknown
                     FROM occurrences WHERE occurrence_id=?""",
                (occurrence_id,),
            ).fetchone()
        finally:
            connection.close()
        if (occurrence is None or occurrence[0] != owner_id
                or occurrence[2] != "claimed" or occurrence[3] != 0
                or not isinstance(occurrence[1], (int, float))
                or isinstance(occurrence[1], bool)):
            return None
        try:
            queued_at = float(occurrence[1])
        except (OverflowError, ValueError):
            return None
        if not math.isfinite(queued_at):
            return None

        owners = root / "owners"
        if not owners.is_dir():
            return None
        owner_claims = []
        for path in owners.glob("*.json"):
            try:
                claim = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            if isinstance(claim, dict) and claim.get("owner_id") == owner_id:
                owner_claims.append(claim)
        if len(owner_claims) != 1:
            return None
        claim = owner_claims[0]
        if (claim.get("version") != 2 or claim.get("resource_class") != "browser"
                or claim.get("phase") != "running"
                or claim.get("occurrence_id") != occurrence_id
                or type(claim.get("pid")) is not int or claim["pid"] != claim_pid
                or claim.get("process_start") != claim_start):
            return None
        return {
            "source": CAPTURE_SOURCE, "owner_id": owner_id,
            "occurrence_id": occurrence_id, "run_id": run_id, "phase": "running",
            "claim_pid": claim_pid, "claim_process_start": claim_start,
            "capture_pid": capture_pid, "capture_process_start": capture_start,
            "queued_at": queued_at,
        }
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, RuntimeError, OverflowError):
        return None


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
    queued = dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)
    return str(row[0]), queued


def snapshot_path(occurrence_id: str, *, snapshot_dir: Path = SNAPSHOT_DIR) -> Path:
    if not _valid_occurrence_id(occurrence_id):
        raise ValueError("invalid_occurrence_id")
    return snapshot_dir / f"{_safe_occurrence(occurrence_id)}.json"


def _atomic_create_json(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-link creation is atomic and refuses to replace an existing proof.
        os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_write_json(path: Path, value: dict, *, mode: int = 0o600) -> None:
    """Replace an evidence record atomically; snapshots use create-only above."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)
    os.replace(temporary_path, path)


def _snapshot_error(
    snapshot: Any, occurrence_id: str, *, now: dt.datetime,
    queued_at: dt.datetime | None = None,
) -> str | None:
    if not isinstance(snapshot, dict) or set(snapshot) != SNAPSHOT_FIELDS:
        return "snapshot_shape_invalid"
    if type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 2:
        return "snapshot_schema_invalid"
    if snapshot.get("owner_id") != OWNER_ID or snapshot.get("occurrence_id") != occurrence_id:
        return "snapshot_binding_mismatch"

    slug, title = snapshot.get("slug"), snapshot.get("title")
    no_candidate = slug is None and title is None
    selected = (
        isinstance(slug, str) and bool(slug.strip())
        and isinstance(title, str) and bool(title.strip())
    )
    if not (no_candidate or selected):
        return "snapshot_candidate_invalid"

    provenance = snapshot.get("capture_provenance")
    if not isinstance(provenance, dict) or set(provenance) != CAPTURE_FIELDS:
        return "capture_provenance_shape_invalid"
    if (provenance.get("source") != CAPTURE_SOURCE
            or provenance.get("owner_id") != OWNER_ID
            or provenance.get("occurrence_id") != occurrence_id
            or provenance.get("phase") != "running"):
        return "capture_provenance_binding_mismatch"
    run_id = provenance.get("run_id")
    if not isinstance(run_id, str) or not _SAFE_RUN_ID.fullmatch(run_id) or run_id in {".", ".."}:
        return "capture_run_id_invalid"
    for field in ("claim_pid", "capture_pid"):
        pid = provenance.get(field)
        if type(pid) is not int or pid <= 0:
            return "capture_process_identity_invalid"
    if provenance["claim_pid"] == provenance["capture_pid"]:
        return "capture_process_identity_invalid"
    for field in ("claim_process_start", "capture_process_start"):
        identity = provenance.get(field)
        if not isinstance(identity, str) or not identity.strip():
            return "capture_process_identity_invalid"
    capture_queued_at = provenance.get("queued_at")
    if (not isinstance(capture_queued_at, (int, float)) or isinstance(capture_queued_at, bool)):
        return "capture_queue_time_invalid"
    try:
        capture_queued_at = float(capture_queued_at)
    except (OverflowError, ValueError):
        return "capture_queue_time_invalid"
    if not math.isfinite(capture_queued_at):
        return "capture_queue_time_invalid"
    if queued_at is not None and abs(float(capture_queued_at) - queued_at.timestamp()) > 0.000001:
        return "capture_queue_binding_mismatch"

    captured_text = snapshot.get("captured_at")
    if not isinstance(captured_text, str):
        return "snapshot_timestamp_invalid"
    try:
        captured_at = dt.datetime.fromisoformat(captured_text.replace("Z", "+00:00"))
    except ValueError:
        return "snapshot_timestamp_invalid"
    if captured_at.tzinfo is None or captured_at.utcoffset() is None or captured_at.microsecond:
        return "snapshot_timestamp_invalid"
    captured_at = captured_at.astimezone(dt.timezone.utc)
    now = now.astimezone(dt.timezone.utc)
    if captured_at > now:
        return "snapshot_timestamp_in_future"
    if queued_at is not None:
        queued_at = queued_at.astimezone(dt.timezone.utc)
        # captured_at is rounded down to seconds by the producer. Its interval
        # must still overlap the queued occurrence's start time.
        if captured_at + dt.timedelta(seconds=1) <= queued_at:
            return "snapshot_before_occurrence"
    return None


def record_snapshot(
    occurrence_id: str, *, slug: str | None, title: str | None,
    snapshot_dir: Path = SNAPSHOT_DIR, now: dt.datetime | None = None,
    capture_provenance_fn: Callable[[str, str], dict | None] = capture_active_admission,
) -> dict:
    """Atomically create one pre-dispatch snapshot; never replace an existing one."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if not _valid_occurrence_id(occurrence_id):
        return {"write_error": "invalid_occurrence_id"}
    no_candidate = slug is None and title is None
    selected = (
        isinstance(slug, str) and bool(slug.strip())
        and isinstance(title, str) and bool(title.strip())
    )
    if not (no_candidate or selected):
        return {"write_error": "snapshot_candidate_invalid"}
    try:
        capture = capture_provenance_fn(OWNER_ID, occurrence_id)
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, RuntimeError, OverflowError):
        capture = None
    if not isinstance(capture, dict):
        return {"write_error": "capture_unverified"}

    snapshot = {
        "schema_version": 2, "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
        "slug": slug, "title": title, "captured_at": now.isoformat(timespec="seconds"),
        "capture_provenance": capture,
    }
    invalid = _snapshot_error(snapshot, occurrence_id, now=now)
    if invalid:
        reason = "capture_unverified" if invalid.startswith("capture_") else invalid
        return {**snapshot, "write_error": reason}
    try:
        capture_queued_at = dt.datetime.fromtimestamp(capture["queued_at"], dt.timezone.utc)
    except (OSError, OverflowError, ValueError):
        return {**snapshot, "write_error": "capture_queue_time_invalid"}
    invalid = _snapshot_error(snapshot, occurrence_id, now=now, queued_at=capture_queued_at)
    if invalid:
        return {**snapshot, "write_error": invalid}

    path = snapshot_path(occurrence_id, snapshot_dir=snapshot_dir)
    try:
        _atomic_create_json(path, snapshot)
        return snapshot
    except FileExistsError:
        existing = load_snapshot(occurrence_id, snapshot_dir=snapshot_dir)
        invalid_existing = _snapshot_error(
            existing, occurrence_id, now=now, queued_at=capture_queued_at,
        )
        same_capture = (
            not invalid_existing
            and all(existing["capture_provenance"][key] == capture[key] for key in (
                "source", "owner_id", "occurrence_id", "run_id", "phase", "claim_pid",
                "claim_process_start", "queued_at",
            ))
        )
        if (same_capture and existing["slug"] == slug and existing["title"] == title):
            return existing
        reason = invalid_existing or "snapshot_conflict"
        return {**snapshot, "write_error": reason}
    except OSError as exc:
        return {**snapshot, "write_error": f"{type(exc).__name__}:{exc}"}


def load_snapshot(occurrence_id: str, *, snapshot_dir: Path = SNAPSHOT_DIR) -> dict | None:
    path = snapshot_path(occurrence_id, snapshot_dir=snapshot_dir)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def read_dashboard_text(
    *, browser_guard: Path = BROWSER_GUARD, identity: str = BROWSER_IDENTITY, timeout: float = 30,
) -> dict:
    """Read-only account?view=prompts text over the leased daily-driver CDP
    endpoint. Never clicks anything, never submits. BUSY/unreachable is
    inconclusive, not a failure to escalate."""
    endpoint_result = subprocess.run(
        [str(browser_guard), "acquire", identity], capture_output=True, text=True, timeout=timeout,
    )
    if endpoint_result.returncode != 0:
        return {"ok": False, "reason": f"browser_lease_rc_{endpoint_result.returncode}"}
    endpoint = endpoint_result.stdout.strip()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint)
            ctx = browser.contexts[0]
            page = ctx.new_page()
            try:
                page.goto(readback_mod.PROMPTS_URL, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
                text = page.inner_text("body")
            finally:
                page.close()
        return {"ok": True, "text": text}
    except Exception as exc:  # fail closed -> inconclusive, never guessed
        return {"ok": False, "reason": f"dashboard_read_failed:{type(exc).__name__}:{exc}"}
    finally:
        subprocess.run(
            [str(browser_guard), "release", identity], capture_output=True, text=True, timeout=timeout,
        )


def _append_evidence(evidence_dir: Path, occurrence_id: str, payload: dict) -> Path:
    path = evidence_dir / f"{OWNER_ID}-{_safe_occurrence(occurrence_id)}.json"
    _atomic_write_json(path, payload)
    return path


def _no_effect_result(
    occurrence_id: str, state: str, reason_payload: dict, evidence_dir: Path,
    resolve: bool, resolve_pre_effect_fn: Callable[..., bool] | None, now: dt.datetime,
) -> dict:
    evidence_path = _append_evidence(evidence_dir, occurrence_id, reason_payload)
    proof = {
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
        "effected": False, "proof_type": "pre_effect", "evidence_ref": str(evidence_path),
        "checked_at": now.isoformat(timespec="seconds"),
    }
    result = {**proof, "admission_state": state}
    if not resolve:
        return result
    resolve_fn = resolve_pre_effect_fn
    if resolve_fn is None:
        from runtime.host.resource_admission import resolve_pre_effect_occurrence

        resolve_fn = resolve_pre_effect_occurrence
    result["closed"] = resolve_fn(
        OWNER_ID, occurrence_id, pre_effect_readback=lambda: proof, expected_state=state,
    )
    return result


def _effected_result(
    occurrence_id: str, state: str, receipt: str, proof_kind: str,
    resolve: bool, resolve_unknown_fn: Callable[..., bool] | None, now: dt.datetime,
) -> dict:
    proof = {
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
        "effected": True, "provider_receipt_id": receipt, "proof_kind": proof_kind,
        "checked_at": now.isoformat(timespec="seconds"),
    }
    result = {**proof, "admission_state": state}
    if not resolve:
        return result
    resolve_fn = resolve_unknown_fn
    if resolve_fn is None:
        from runtime.host.resource_admission import resolve_unknown_occurrence

        resolve_fn = resolve_unknown_occurrence
    result["closed"] = resolve_fn(
        OWNER_ID, occurrence_id, official_readback=lambda: proof, expected_state=state,
    )
    return result


def reconcile(
    occurrence_id: str, *,
    fenced_row_fn: Callable[[str, str], tuple[str, dt.datetime]] = fenced_row,
    load_snapshot_fn: Callable[[str], dict | None] = load_snapshot,
    read_dashboard_fn: Callable[[], dict] = read_dashboard_text,
    resolve_unknown_fn: Callable[..., bool] | None = None,
    resolve_pre_effect_fn: Callable[..., bool] | None = None,
    ledger_path: Path = ledger_mod.DEFAULT_LEDGER_PATH,
    evidence_dir: Path = EVIDENCE_DIR,
    now: dt.datetime | None = None,
    resolve: bool = False,
) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row_fn(OWNER_ID, occurrence_id)

    snapshot = load_snapshot_fn(occurrence_id)
    invalid_snapshot = _snapshot_error(snapshot, occurrence_id, now=now, queued_at=queued_at)
    if invalid_snapshot:
        return {
            "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
            "reason": invalid_snapshot, "error_class": "snapshot_untrusted",
            "admission_state": state,
        }
    slug, title = snapshot["slug"], snapshot["title"]

    if slug is None and title is None:
        return _no_effect_result(
            occurrence_id, state,
            {
                "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                "checked_at": now.isoformat(timespec="seconds"),
                "reason": "no_candidate_selected_for_occurrence",
                "captured_at": snapshot["captured_at"],
            },
            evidence_dir, resolve, resolve_pre_effect_fn, now,
        )

    ledger_row = ledger_mod.latest_by_slug(ledger_path).get(slug)
    if ledger_row is not None and ledger_row.get("status") not in ledger_mod.RETRYABLE_STATUSES:
        submitted_at = ledger_row.get("submitted_at")
        try:
            recorded_at = dt.datetime.strptime(submitted_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc
            )
        except (TypeError, ValueError):
            recorded_at = None
        if recorded_at is not None and recorded_at >= queued_at:
            return _effected_result(
                occurrence_id, state, f"ledger_row:{slug}:{submitted_at}",
                "local_ledger_already_recorded", resolve, resolve_unknown_fn, now,
            )

    dashboard = read_dashboard_fn()
    if not dashboard.get("ok"):
        return {
            "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
            "reason": str(dashboard.get("reason") or "dashboard_read_failed"),
            "error_class": "provider_read_failed", "admission_state": state,
        }

    dashboard_status = readback_mod.status_for_title(dashboard["text"], title)
    if dashboard_status in ("live", "pending_review", "scheduled"):
        new_status = "submitted_pending_review" if dashboard_status == "pending_review" else dashboard_status
        row = {**ledger_row, "status": new_status} if ledger_row else {
            "slug": slug, "promptbase_id": "", "url": "", "title": title,
            "status": new_status, "submitted_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        ledger_mod.append(row, ledger_path)
        return _effected_result(
            occurrence_id, state, f"promptbase:dashboard_title={title}:status={dashboard_status}",
            "official_promptbase_dashboard_readback", resolve, resolve_unknown_fn, now,
        )

    age_seconds = (now - queued_at).total_seconds()
    if age_seconds <= NO_EFFECT_MIN_AGE_SECONDS:
        return {
            "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
            "reason": f"too_recent:{int(age_seconds)}s<={NO_EFFECT_MIN_AGE_SECONDS}s",
            "admission_state": state,
        }

    return _no_effect_result(
        occurrence_id, state,
        {
            "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
            "checked_at": now.isoformat(timespec="seconds"),
            "source": "PromptBase account?view=prompts (official seller dashboard)",
            "slug": slug, "title": title, "verdict": "no_effect",
        },
        evidence_dir, resolve, resolve_pre_effect_fn, now,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--record-snapshot", action="store_true")
    parser.add_argument("--slug")
    parser.add_argument("--title")
    args = parser.parse_args(argv)
    if args.record_snapshot:
        snapshot = record_snapshot(args.occurrence, slug=args.slug, title=args.title)
        print(json.dumps(snapshot, sort_keys=True, default=str))
        return 0 if "write_error" not in snapshot else 1
    try:
        result = reconcile(args.occurrence, resolve=args.resolve)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({
            "owner_id": OWNER_ID, "occurrence_id": args.occurrence, "verified": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, sort_keys=True))
        print("PROMPTBASE_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    if not result.get("verified"):
        print("PROMPTBASE_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("PROMPTBASE_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("PROMPTBASE_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("PROMPTBASE_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
