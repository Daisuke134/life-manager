#!/usr/bin/env python3
"""Resolve one Coconala storefront host fence only from an exact pre-effect proof.

The proof is narrower than a provider readback: it shows the run never crossed
``mutation_attempted`` inside ``storefront_direct.py``. Absence or ambiguity of
any of the four evidence legs (runtime events, stdout receipt, receipt shape,
admission row) leaves the occurrence fenced.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.host.resource_admission import (  # noqa: E402
    resolve_pre_effect_occurrence,
    state_root as admission_root,
)
from runtime.loop.runtime_event import validate_runtime_event  # noqa: E402


OWNER_ID = "hf-gig-storefront-direct"
OCCURRENCE_PREFIX = f"{OWNER_ID}:"
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

# ``official_service_contract_invalid`` is set at storefront_direct.py:6316 and
# raised at :6319, both inside ``_read_official_catalog`` (called at :6321).
# ``mutation_attempted`` is not set True anywhere before that call; its first
# assignment in ``run_once`` is at :6503. ``_storefront_failure_disposition``
# (:817-823) maps this reason to status "failed" (it is not in the pending set).
ALLOWED_REASONS = frozenset({"official_service_contract_invalid"})


class EvidenceError(RuntimeError):
    pass


def _private_jsonl(path: Path, *, gz: bool = False,
                   allowed_modes: frozenset[int] = frozenset({0o600})) -> list[dict]:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) not in allowed_modes):
            raise EvidenceError("journal_not_private")
        rows: list[dict] = []
        raw = os.fdopen(descriptor, "rb")
        descriptor = -1
        stream = gzip.GzipFile(fileobj=raw) if gz else raw
        try:
            for line in stream:
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise EvidenceError("journal_row_invalid")
                rows.append(validate_runtime_event(value))
        finally:
            stream.close()
            raw.close()
        return rows
    except EvidenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, EOFError) as error:
        raise EvidenceError("journal_invalid") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_runtime_events(state_root: Path) -> list[dict]:
    rows: list[dict] = []
    plain = state_root / "events.jsonl"
    if plain.is_file():
        rows.extend(_private_jsonl(plain))
    for archive in sorted(state_root.glob("events-*.jsonl.gz")):
        rows.extend(_private_jsonl(archive, gz=True))
    return rows


def _epoch(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError as error:
            raise EvidenceError("timestamp_invalid") from error
    raise EvidenceError("timestamp_invalid")


def _find_window(rows: list[dict], run_id: str) -> tuple[dict, dict]:
    matches = [row for row in rows if row.get("run_id") == run_id]
    if len(matches) != 2:
        raise EvidenceError("runtime_event_count_invalid")
    start = next((row for row in matches if row.get("phase") == "execute"), None)
    terminal = next((row for row in matches if row.get("phase") == "report"), None)
    if start is None or terminal is None or start is terminal:
        raise EvidenceError("runtime_event_phase_invalid")
    expected_ref = f"lm-loop://{OWNER_ID}/{run_id}/summary.json"
    for event, expected_status, expected_effect_status in (
        (start, "running", "started"), (terminal, "fail", "unknown"),
    ):
        refs = event.get("evidence_refs") or []
        if (event.get("status") != expected_status
                or event.get("effect_status") != expected_effect_status
                or expected_ref not in refs
                or any(str(ref).startswith("lm-effect://") for ref in refs)):
            raise EvidenceError("runtime_event_shape_invalid")
    return start, terminal


def _stdout_pass_line(path: Path, started: float, stopped: float) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise EvidenceError("stdout_log_unreadable") from error
    matches: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        pass_id = value.get("pass_id")
        observed = value.get("observed_at_epoch")
        if (not isinstance(pass_id, str) or not pass_id.startswith("storefront-direct-")
                or not isinstance(observed, (int, float)) or isinstance(observed, bool)):
            continue
        if started <= float(observed) <= stopped:
            matches.append(value)
    if len(matches) != 1:
        raise EvidenceError("stdout_pass_count_invalid")
    return matches[0]


def _validate_pass_line(row: dict) -> None:
    if (row.get("status") != "failed" or row.get("effect") != 0
            or row.get("actionable") != 0 or row.get("readback") != 0
            or row.get("reason") not in ALLOWED_REASONS):
        raise EvidenceError("pass_line_not_pre_effect_proof")


def _admission_state(database: Path, occurrence_id: str) -> str:
    if not database.is_file():
        raise EvidenceError("admission_database_missing")
    with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT owner_id,state,effect_unknown FROM occurrences WHERE occurrence_id=?",
            (occurrence_id,),
        ).fetchone()
    if row is None:
        raise EvidenceError("admission_occurrence_missing")
    if (row["owner_id"] != OWNER_ID or row["effect_unknown"] != 1
            or row["state"] not in {"claimed", "released"}):
        raise EvidenceError("admission_occurrence_not_effect_unknown")
    return row["state"]


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _run_id_from_occurrence(occurrence: str) -> str:
    if not occurrence.startswith(OCCURRENCE_PREFIX):
        raise EvidenceError("occurrence_owner_mismatch")
    run_id = occurrence[len(OCCURRENCE_PREFIX):]
    if not RUN_ID.fullmatch(run_id):
        raise EvidenceError("occurrence_run_id_invalid")
    return run_id


def _build_evidence(state_root: Path, stdout_log: Path, database: Path,
                    run_id: str) -> tuple[str, str, dict]:
    occurrence_id = f"{OWNER_ID}:{run_id}"
    start, terminal = _find_window(_read_runtime_events(state_root), run_id)
    started = _epoch(start["timestamp"])
    stopped = _epoch(terminal["timestamp"])
    if not started <= stopped:
        raise EvidenceError("runtime_event_time_invalid")
    pass_line = _stdout_pass_line(stdout_log, started, stopped + 5)
    _validate_pass_line(pass_line)
    admission_state = _admission_state(database, occurrence_id)
    evidence = {
        "run_id": run_id,
        "start_event_id": start["event_id"],
        "terminal_event_id": terminal["event_id"],
        "pass_id": pass_line["pass_id"],
        "reason": pass_line["reason"],
        "window_started_at": start["timestamp"],
        "window_stopped_at": terminal["timestamp"],
    }
    return occurrence_id, admission_state, evidence


def reconcile(
    *,
    state_root: Path,
    stdout_log: Path,
    run_id: str,
    resolve: bool,
    database: Path | None = None,
    resolver: Callable[..., bool] = resolve_pre_effect_occurrence,
) -> dict:
    """Return exact proof, or resolve only the occurrence proven pre-effect."""
    db = database if database is not None else admission_root() / "admission-v2.sqlite3"
    try:
        occurrence_id, admission_state, evidence = _build_evidence(
            state_root, stdout_log, db, run_id,
        )
    except (EvidenceError, OSError, sqlite3.Error) as error:
        return {"state": "HELD", "reason": str(error)}
    proof_identity = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id, "evidence": evidence}
    evidence_key = hashlib.sha256(json.dumps(
        proof_identity, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    evidence_ref = f"storefront-pre-effect://{evidence_key}"
    if not resolve:
        return {
            "state": "PROOF_READY",
            "occurrence_id": occurrence_id,
            "evidence_ref": evidence_ref,
            "evidence": evidence,
        }
    receipt = {
        "schema_version": 1,
        "receipt_type": "STOREFRONT_PRE_EFFECT_RECONCILIATION",
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": evidence_ref,
        "evidence": evidence,
        "expected_state": admission_state,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "resolution_state": "PROOF_READY",
    }
    receipt_path = state_root / "reconciliation" / f"pre-effect-{run_id}.json"
    _atomic_json(receipt_path, receipt)
    proof = {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": evidence_ref,
    }
    resolved = resolver(
        OWNER_ID, occurrence_id,
        pre_effect_readback=lambda: proof,
        expected_state=admission_state,
    )
    receipt["resolution_state"] = "RESOLVED" if resolved else "HELD"
    _atomic_json(receipt_path, receipt)
    return {
        "state": "RECONCILED" if resolved else "HELD",
        "reason": None if resolved else "exact_resolution_rejected",
        "occurrence_id": occurrence_id,
        "evidence_ref": evidence_ref,
        "receipt_path": str(receipt_path),
        "evidence": evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument(
        "--state-root", type=Path,
        default=Path("~/.local/state/life-manager/coconala/storefront"),
    )
    parser.add_argument("--stdout-log", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    stdout_log = (args.stdout_log or (state_root / "logs" / "launchd.out.log")).expanduser().resolve()
    try:
        run_id = _run_id_from_occurrence(args.occurrence)
    except EvidenceError as error:
        result = {"state": "HELD", "reason": str(error)}
    else:
        result = reconcile(
            state_root=state_root, stdout_log=stdout_log, run_id=run_id,
            resolve=not args.dry_run,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["state"] in {"PROOF_READY", "RECONCILED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
