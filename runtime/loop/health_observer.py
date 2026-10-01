#!/usr/bin/env python3
"""Persist bounded fleet health without mutating providers or runtime owners."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.loop.health import validate_health_document


PROBLEM_STATES = frozenset({
    "safely_fenced", "effect_unknown", "telemetry_gap", "human_required", "failed",
})
SAFE_ID = re.compile(r"[^A-Za-z0-9._:-]")


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _encoded(value: object, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(value, indent=2, sort_keys=True)
    else:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def write_latest(path: Path, value: object) -> None:
    """Atomically replace one private JSON snapshot in its destination directory."""
    _private_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(_encoded(value, pretty=True))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        path.chmod(0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def _append_jsonl(path: Path, value: object) -> None:
    _private_directory(path.parent)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, _encoded(value))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _last_jsonl(path: Path, *, max_bytes: int = 4 * 1024 * 1024) -> dict | None:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - max_bytes))
            content = stream.read()
    except OSError:
        return None
    lines = content.splitlines()
    if not lines:
        return None
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _state_rows(document: dict) -> dict[str, dict]:
    rows = {}
    for job in document["jobs"]:
        diagnostic = job["diagnostic"]
        rows[job["job_id"]] = {
            "state": job["state"],
            "facets": {name: value["status"] for name, value in job["facets"].items()},
            "effect": diagnostic["effect"],
            "error_class": diagnostic["error_class"],
            "retryable": diagnostic["retryable"],
            "next_action": diagnostic["next_action"],
        }
    return rows


def _fingerprint(rows: dict[str, dict]) -> str:
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _safe_id(value: object, fallback: str) -> str:
    candidate = SAFE_ID.sub("_", str(value or fallback))[:128]
    return candidate if candidate and candidate[0].isalnum() else fallback


def _intent_input(job: dict, observer_run_id: str) -> dict:
    diagnostic = job["diagnostic"]
    loop_id = _safe_id(job["job_id"], "unknown-loop")
    run_id = _safe_id(diagnostic.get("run_id"), observer_run_id)
    owner_id = _safe_id(diagnostic.get("owner_id"), loop_id)
    effect = diagnostic.get("effect") or {}
    if job["state"] in {"safely_fenced", "effect_unknown"}:
        failure_layer = "effect_readback"
    elif job["state"] == "human_required":
        failure_layer = "admission"
    else:
        failure_layer = "runtime"
    return {
        "loop_id": loop_id,
        "owner_id": owner_id,
        "wake_id": observer_run_id,
        "run_id": run_id,
        "occurrence_id": f"{loop_id}:{run_id}",
        "release_sha": _safe_id(
            diagnostic.get("release_sha") or os.environ.get("LIFE_MANAGER_RELEASE_SHA"),
            "unknown-release",
        ),
        "status": "blocked" if job["state"] in {
            "safely_fenced", "effect_unknown", "human_required",
        } else "fail",
        "failure_layer": failure_layer,
        "effect_class": _safe_id(effect.get("class"), "none"),
        "effect_status": _safe_id(effect.get("status"), "unknown"),
        "blocker": _safe_id(
            diagnostic.get("error_class") or job["state"], job["state"],
        ),
        "consecutive_failure_streak": 1,
        "threshold": 3,
        "evidence_refs": [f"lm-loop://{loop_id}/{run_id}/health"],
    }


def build_recovery_intent(job: dict, observer_run_id: str) -> dict:
    """Use the canonical JavaScript classifier; do not duplicate recovery policy."""
    node = os.environ.get("LIFE_MANAGER_RUNTIME_NODE", "node")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="lm-health-intent-", suffix=".json",
    ) as source:
        json.dump(_intent_input(job, observer_run_id), source, sort_keys=True)
        source.flush()
        result = subprocess.run(
            [node, str(ROOT / "runtime/loop/recovery-intent-cli.mjs"),
             "--input", source.name],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(f"recovery intent classifier failed: {result.stderr[:200]}")
    intent = json.loads(result.stdout)
    if (not isinstance(intent, dict)
            or intent.get("mutates_external_effect") is not False
            or intent.get("loop_id") != job["job_id"]):
        raise ValueError("recovery intent classifier returned an invalid boundary")
    return intent


def observe_health(document: dict, state_root: Path, *, intent_builder=None) -> dict:
    """Persist one observation and emit at most one alert for its state transition."""
    validate_health_document(document)
    intent_builder = intent_builder or build_recovery_intent
    state_root = Path(state_root)
    current_rows = _state_rows(document)
    current_fingerprint = _fingerprint(current_rows)
    previous = _read_json(state_root / "alert-state.json") or {}
    previous_rows = previous.get("jobs") if isinstance(previous.get("jobs"), dict) else {}
    previous_fingerprint = previous.get("fingerprint")
    changed_jobs = sorted(
        job_id for job_id in set(previous_rows) | set(current_rows)
        if previous_rows.get(job_id) != current_rows.get(job_id)
    )
    first_problem = previous_fingerprint is None and any(
        job["state"] in PROBLEM_STATES for job in document["jobs"]
    )
    state_changed = (
        previous_fingerprint is not None and previous_fingerprint != current_fingerprint
    )
    last_alert = _last_jsonl(state_root / "alerts.jsonl") or {}
    already_alerted = last_alert.get("state_fingerprint") == current_fingerprint
    alert_emitted = (first_problem or state_changed) and not already_alerted
    observer_run_id = f"observer-{hashlib.sha256(document['generated_at'].encode()).hexdigest()[:16]}"
    recovery_intents = []
    if alert_emitted:
        changed = set(changed_jobs)
        recovery_intents = [
            intent_builder(job, observer_run_id)
            for job in document["jobs"]
            if job["job_id"] in changed and job["state"] in PROBLEM_STATES
        ]
        alert = {
            "schema_version": "lm-loop.health-alert.v1",
            "observed_at": document["generated_at"],
            "state_fingerprint": current_fingerprint,
            "previous_state_fingerprint": previous_fingerprint,
            "changed_jobs": changed_jobs,
            "recovery_intents": recovery_intents,
        }
        _append_jsonl(state_root / "alerts.jsonl", alert)
    write_latest(state_root / "latest.json", document)
    _append_jsonl(state_root / "history.jsonl", {
        "schema_version": "lm-loop.health-observation.v1",
        "observed_at": document["generated_at"],
        "scope": document["scope"],
        "summary": document["summary"],
        "state_fingerprint": current_fingerprint,
        "jobs": current_rows,
    })
    write_latest(state_root / "alert-state.json", {
        "schema_version": "lm-loop.health-alert-state.v1",
        "fingerprint": current_fingerprint,
        "jobs": current_rows,
    })
    return {
        "ok": True,
        "alert_emitted": alert_emitted,
        "changed_jobs": changed_jobs if alert_emitted else [],
        "recovery_intents": recovery_intents,
        "state_fingerprint": current_fingerprint,
    }


def load_health_snapshot() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "runtime.loop.lm_loop", "health", "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=40,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"health snapshot failed: {result.stderr[:200]}")
    return validate_health_document(json.loads(result.stdout))


def main() -> int:
    state_root = Path(os.environ.get(
        "LIFE_MANAGER_STATE_ROOT",
        "~/.local/state/life-manager/health-observer",
    )).expanduser()
    try:
        result = observe_health(load_health_snapshot(), state_root)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
            json.JSONDecodeError) as error:
        print(json.dumps({
            "ok": False,
            "error_class": "health_observer_failed",
            "retryable": True,
            "next_action": "inspect_health_observer",
            "detail": str(error)[:200],
        }, sort_keys=True))
        return 1
    print(json.dumps({
        key: value for key, value in result.items() if key != "recovery_intents"
    } | {"recovery_intent_count": len(result["recovery_intents"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
