#!/usr/bin/env python3
"""Low-cost Coconala reply detector used by push and five-minute fallback."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import importlib.util
import inspect
import itertools
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from gig_paths import BROWSER_DIR, RUNNER_DIR  # noqa: E402
from gig_disk_guard import disk_headroom_ok  # noqa: E402
from no_contact_policy import load_registry, match_thread  # noqa: E402
from requested_estimate import SEMANTIC_PROMPT_VERSION  # noqa: E402
from operator_brake import status as shared_operator_brake_status  # noqa: E402

try:
    from connector_outbox import ConnectorOutbox, coconala_inbox_event_key
except ModuleNotFoundError:
    _outbox_spec = importlib.util.spec_from_file_location(
        "reply_detector_outbox", Path(__file__).with_name("connector_outbox.py"),
    )
    if _outbox_spec is None or _outbox_spec.loader is None:
        raise
    _outbox_module = importlib.util.module_from_spec(_outbox_spec)
    _outbox_spec.loader.exec_module(_outbox_module)
    ConnectorOutbox = _outbox_module.ConnectorOutbox
    coconala_inbox_event_key = _outbox_module.coconala_inbox_event_key


class StepFailure(RuntimeError):
    def __init__(
        self, step: str, returncode: int, *, attempts: list[dict[str, Any]] | None = None,
    ):
        super().__init__(f"{step} exited {returncode}")
        self.step = step
        self.returncode = returncode
        self.attempts = list(attempts or [])


class TargetedIdentityChanged(ValueError):
    """The official inbox head changed before a targeted effect could start."""

    def __init__(self, row: dict[str, Any]):
        super().__init__("targeted inbox identity changed")
        self.row = dict(row)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
        path.chmod(0o600)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _prune_continuous_evidence(evidence: Path) -> None:
    """Bound completed artifacts from one keep-alive Reply process."""
    contracts = (
        (evidence / "continuous", "probe-*", "head-snapshot.json", 8),
        (evidence / "continuous" / "workers", "*", "result.json", 16),
        (evidence / "continuous" / "reconciliation-reports", "*", "result.json", 8),
        (evidence / "reconciliation", "reconcile-*", "marketplace-snapshot.json", 8),
    )
    for root, pattern, marker_name, keep in contracts:
        completed = []
        for path in root.glob(pattern):
            marker = path / marker_name
            if path.is_symlink() or not path.is_dir() or not marker.is_file():
                continue
            try:
                completed.append((marker.stat().st_mtime_ns, path))
            except OSError:
                continue
        for _, path in sorted(completed, reverse=True)[keep:]:
            shutil.rmtree(path, ignore_errors=True)


def _run(
    step: str, arguments: list[str], *, accepted: tuple[int, ...] = (0,),
    timeout: float | None = None,
) -> None:
    completed = subprocess.run(
        arguments,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode not in accepted:
        raise StepFailure(step, completed.returncode)


def _collect_snapshot_with_retry(
    args: Any, snapshot: Path, evidence: Path,
) -> list[dict[str, Any]]:
    """Retry the read-only source collection once, preserving each attempt's evidence."""
    attempts: list[dict[str, Any]] = []
    for number in (1, 2):
        attempt_evidence = evidence / (
            "live-dom" if number == 1 else f"live-dom-retry-{number}"
        )
        snapshot.unlink(missing_ok=True)
        try:
            collect_command = [
                sys.executable, str(args.snapshot_script),
                "--output", str(snapshot),
                "--evidence-dir", str(attempt_evidence),
                "--mode", "direct-inbox-only",
                "--hidden-no-screenshot",
                "--semantic-runner", str(args.runner),
                "--semantic-schema", str(args.semantic_schema),
                "--semantic-workdir", str(Path.home()),
                "--database", str(args.database),
                "--manifest", str(args.manifest),
            ]
            if args.semantic_effects_enabled:
                collect_command.append("--semantic-effects-enabled")
            _run("collect", collect_command)
        except StepFailure as error:
            attempts.append({
                "attempt": number, "status": "failed",
                "returncode": error.returncode,
                "evidence_dir": str(attempt_evidence),
            })
            if number == 2:
                raise StepFailure(
                    "collect", error.returncode, attempts=attempts,
                ) from error
            continue
        try:
            snapshot_value = json.loads(snapshot.read_text(encoding="utf-8"))
            if not isinstance(snapshot_value, dict):
                raise ValueError("collector snapshot must be an object")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            attempts.append({
                "attempt": number, "status": "failed",
                "returncode": 1, "error": "invalid_snapshot",
                "evidence_dir": str(attempt_evidence),
            })
            if number == 2:
                raise StepFailure("collect", 1, attempts=attempts) from error
            continue
        attempts.append({
            "attempt": number, "status": "completed",
            "returncode": 0, "evidence_dir": str(attempt_evidence),
        })
        return attempts
    raise AssertionError("unreachable collector retry state")


def _collect_head_snapshot(args: Any, evidence: Path) -> dict[str, Any]:
    """Read the bounded inbox head used by the continuous producer."""
    snapshot = evidence / "head-snapshot.json"
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    command = [
        sys.executable, str(args.snapshot_script),
        "--output", str(snapshot), "--evidence-dir", str(evidence / "live-dom"),
        "--mode", "direct-inbox-head-only", "--hidden-no-screenshot",
        "--database", str(args.database), "--manifest", str(args.manifest),
    ]
    _run("head_collect", command, timeout=45)
    value = json.loads(snapshot.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("collector_mode") != "direct-inbox-head-only"
        or value.get("head_only") is not True
        or not isinstance(value.get("inquiries"), list)
    ):
        raise ValueError("head snapshot incomplete")
    _owner_only(snapshot)
    return value


def _close_no_contact_action(
    outbox: ConnectorOutbox, action: dict[str, Any], *, policy_id: str, now: int,
) -> dict[str, Any]:
    action_id = int(action["action_id"])
    if action.get("dlq_at") is not None:
        action = outbox.requeue_closed_action(
            action_id, now=now, require_no_intent=True,
        )
    owner = f"gig-no-contact-{action_id}"
    claimed = outbox.claim(owner=owner, now=now, lease_seconds=30, action_id=action_id)
    if claimed is None:
        return {"status": "ignore_policy", "policy_id": policy_id, "action_id": action_id}
    outbox.close_nothing_to_say(
        action_id, owner=owner, fencing_token=int(claimed["fencing_token"]),
        reason=f"ignore_policy:{policy_id}", now=now,
    )
    return {"status": "ignore_policy", "policy_id": policy_id, "action_id": action_id}


def partition_no_contact_rows(
    rows: list[dict[str, Any]], *, registry_path: Path,
    outbox: ConnectorOutbox, now: int,
) -> dict[str, Any]:
    """Create a durable action, then close private threads before semantic work."""
    registry = load_registry(registry_path)
    available: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for row in rows:
        thread_id = str(row.get("talkroom_id") or "")
        thread_path = f"/mypage/direct_message/{thread_id}"
        policy = match_thread(registry, thread_path=thread_path)
        if policy is None:
            available.append(row)
            continue
        identity = str(row.get("last_message_identity_sha256") or "")
        if _TARGETED_THREAD_ID.fullmatch(thread_id) is None or re.fullmatch(r"[0-9a-f]{64}", identity) is None:
            raise ValueError("no_contact_head_identity_invalid")
        event_key = coconala_inbox_event_key(thread_id, identity)
        action = outbox.enqueue(
            event_key=event_key,
            thread_id=thread_id, thread_url=f"https://coconala.com{thread_path}",
            observed_at=now,
        )
        lifecycle = outbox.action_lifecycle_for_event(event_key, thread_id)
        if (
            lifecycle is not None
            and lifecycle.get("dlq_at") is not None
            and lifecycle.get("reason") == f"nothing_to_say:ignore_policy:{policy['policy_id']}"
        ):
            ignored.append({
                "status": "ignore_policy_replay",
                "policy_id": policy["policy_id"],
                "action_id": int(action["action_id"]),
            })
            continue
        ignored.append(_close_no_contact_action(
            outbox, action, policy_id=policy["policy_id"], now=now,
        ))
    return {"available": available, "ignored": ignored}


def close_no_contact_work(
    work: dict[str, Any], *, registry_path: Path,
    outbox: ConnectorOutbox, now: int,
) -> dict[str, Any] | None:
    """Independent effect-time fence for stale or manually queued work."""
    thread_id = str(work.get("thread_id") or "")
    policy = match_thread(
        load_registry(registry_path),
        thread_path=f"/mypage/direct_message/{thread_id}",
    )
    if policy is None:
        return None
    action = outbox.get_action(int(work["action_id"]))
    return _close_no_contact_action(
        outbox, action, policy_id=policy["policy_id"], now=now,
    )


def no_contact_report(ignored: dict[str, Any], *, now: int) -> dict[str, Any]:
    """Build an owner-visible result without customer identity or message content."""
    del now
    action_id = int(ignored["action_id"])
    return {
        **ignored, "run_id": f"ignore-policy-{ignored['policy_id']}-{action_id}",
        "observed": 1, "actionable": 0,
        "replied": 0, "effect": 0, "official_readback": 0,
        "estimate_required": 0, "estimate_effect": 0, "estimate_readback": 0,
        "estimate_failed": 0, "estimate_pending": 0,
        "closed_without_send": 1, "pending": 0,
        "blocked": 0, "historical_dlq": 0, "newly_dlq": 0,
        "failed": 0, "skipped": 0, "deferred": 0,
        "officially_unrepliable_count": 0, "stop_contact_count": 0,
        "classification_failed_count": 0,
        "semantic_judgement_failed_count": 0,
        "semantic_migration_pending_count": 0,
        "thread_changed_buyer_count": 0, "thread_readback_count": 1,
        "thread_revalidated_count": 1 if ignored["status"] == "ignore_policy_replay" else 0,
        "policy_ignored_count": 1,
        "events": [], "errors": [],
    }


def _operator_brake_status(
    script: Path | None = None, *, timeout: float = 5.0,
) -> str:
    """Return free/held, or fail closed when the operator gate is unknowable."""
    brake = script or Path(__file__).with_name("gig_brake.sh")
    environment = os.environ.copy()
    environment.setdefault(
        "GIG_OPERATOR_BRAKE_FILE",
        str(Path.home() / ".openclaw/state/gig-work/reply.operator.brake"),
    )
    return shared_operator_brake_status(
        brake, timeout=timeout, environment=environment,
    )


def _telegram_report(args: Any, events: Path, command: str) -> str:
    """Publish one report through the durable Telegram outbox, never fatally.

    Shared by the verified-reply report and the dead-letter alert: reporting is
    an obligation, but a Telegram outage must not turn a completed detector run
    into a failed one. The outbox itself is what makes the send durable and
    exactly-once, so 'deferred' here means 'queued, not yet acknowledged'.
    """
    try:
        report = subprocess.run(
            [
                sys.executable, str(args.telegram_report_script), command,
                "--events", str(events),
                "--connector-database", str(args.database),
                "--telegram-database", str(args.telegram_database),
                "--runner-config", str(args.runner_config),
                "--target", str(args.telegram_target),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=240,
            check=False,
        )
    except Exception:
        return "deferred"
    if report.returncode == 2:
        return "delivery_unknown"
    try:
        lines = [line for line in report.stdout.splitlines() if line.strip()]
        dispatch = json.loads(lines[-1])
    except (IndexError, TypeError, json.JSONDecodeError):
        return "deferred"
    if not isinstance(dispatch, dict):
        return "deferred"
    if _count(dispatch.get("delivery_unknown")):
        return "delivery_unknown"
    if _count(dispatch.get("sent")):
        return "sent"
    return "deferred"


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _snapshot_terminal_counts(snapshot: Any) -> dict[str, int | None]:
    """Project only bounded terminal classifications from one fresh snapshot."""
    unknown = {
        "officially_unrepliable_count": None,
        "stop_contact_count": None,
        "classification_failed_count": None,
        "collector_unhealthy_count": None,
        "semantic_judgement_failed_count": None,
        "semantic_migration_pending_count": None,
    }
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("inquiries"), list):
        return unknown
    inquiries = snapshot["inquiries"]
    if any(
        not isinstance(item, dict) or not isinstance(item.get("next_action"), str)
        for item in inquiries
    ):
        return unknown
    actions = [item.get("next_action") for item in inquiries]
    classification_failures = [
        item for item in inquiries
        if item.get("next_action") in (
            "estimate_failed", "semantic_failed", "semantic_pending",
        )
    ]
    migration_pending = sum(
        item.get("next_action") == "semantic_pending"
        and item.get("last_message_side") == "seller"
        and item.get("semantic_failure") == "semantic_receipt_pending"
        for item in classification_failures
    )
    # classification_failed_count adds two unlike things: threads the model declined to classify
    # because the message holds no buyer intent (correct, and permanent), and threads where the
    # collector itself failed (a fault, and fixable). Measured 2026-08-17 on three threads: one was
    # a platform notice mistaken for a buyer, one was the seller having spoken last, and one was a
    # pagination ceiling. A count that mixes honesty with breakage never reaches zero and cannot be
    # alarmed on, so the fault is also published on its own.
    collector_unhealthy = sum(
        str(item.get("semantic_failure") or "").startswith("collector_unhealthy")
        for item in classification_failures
    )
    return {
        "officially_unrepliable_count": actions.count("officially_unrepliable"),
        "stop_contact_count": actions.count("stop_contact"),
        "classification_failed_count": len(classification_failures),
        "collector_unhealthy_count": collector_unhealthy,
        "semantic_judgement_failed_count": (
            len(classification_failures) - migration_pending
        ),
        "semantic_migration_pending_count": migration_pending,
    }


def close_officially_unrepliable_pending(
    snapshot: dict[str, Any], *, database: Path, manifest: Path, owner: str, now: int,
) -> dict[str, Any]:
    """Close old pre-click actions only when the fresh official UI forbids sending."""
    inquiries = {
        str(item.get("talkroom_id") or ""): item
        for item in snapshot.get("inquiries", []) if isinstance(item, dict)
    }
    db = ConnectorOutbox(database, manifest)
    closed: list[int] = []
    errors: list[str] = []
    for action in db.pending_actions():
        item = inquiries.get(str(action.get("thread_id") or ""))
        if not (
            isinstance(item, dict)
            and item.get("last_message_side") == "buyer"
            and item.get("sending_unavailable") is True
            and item.get("next_action") == "officially_unrepliable"
            and item.get("reply_required") is False
            and item.get("estimate_required") is False
        ):
            continue
        action_id = int(action["action_id"])
        try:
            claimed = db.claim(owner=owner, now=now, lease_seconds=30, action_id=action_id)
            if claimed is None:
                continue
            db.close_nothing_to_say(
                action_id, owner=owner, fencing_token=int(claimed["fencing_token"]),
                reason="officially_unrepliable", now=now,
            )
            closed.append(action_id)
        except Exception as error:
            errors.append(f"{action_id}:{type(error).__name__}")
    return {"closed_action_ids": closed, "errors": errors}


def _snapshot_activity_counts(snapshot: Any) -> dict[str, int | None]:
    keys = (
        "thread_changed_buyer_count", "thread_readback_count",
        "thread_revalidated_count",
    )
    receipt = snapshot.get("source_receipt") if isinstance(snapshot, dict) else None
    if not isinstance(receipt, dict):
        return {key: None for key in keys}
    return {key: _count(receipt.get(key)) for key in keys}


def _oldest_actionable(items: Any) -> str | None:
    if not isinstance(items, list) or not items:
        return None
    origins = [
        str(item.get("origin_at") or "")
        for item in items
        if isinstance(item, dict)
    ]
    if len(origins) != len(items) or any(not value for value in origins):
        return None
    try:
        return min(
            origins,
            key=lambda value: datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).astimezone(timezone.utc),
        )
    except (TypeError, ValueError):
        return None


def _verified_events(
    events: Any, expected_replied: int | None, *, expected_thread: str | None = None,
    expected_action_id: int | None = None, expected_revision: int | None = None,
) -> list[dict[str, Any]] | None:
    if not isinstance(events, list) or expected_replied is None:
        return None
    if expected_action_id is not None and (
        type(expected_revision) is not int or expected_revision <= 0
    ):
        return None
    identities: set[tuple[int, int, str]] = set()
    for event in events:
        if not isinstance(event, dict) or event.get("status") != "replied":
            return None
        action_id = _count(event.get("action_id"))
        revision = _count(event.get("revision"))
        if action_id is None or revision is None or action_id <= 0 or revision <= 0:
            return None
        if expected_action_id is not None and action_id != expected_action_id:
            return None
        if expected_revision is not None and revision != expected_revision:
            return None
        if not isinstance(event.get("talkroom_id"), str) or not event["talkroom_id"].strip():
            return None
        if expected_thread is not None and event["talkroom_id"].strip() != expected_thread:
            return None
        identity = (action_id, revision, event["talkroom_id"].strip())
        if identity in identities:
            return None
        identities.add(identity)
        for key in ("origin_at", "seller_sent_at"):
            value = event.get(key)
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None
            if parsed.tzinfo is None:
                return None
    return events if len(events) == expected_replied else None


def _wake_result(*, run_id: str, trigger: str, status: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": status,
        "trigger": trigger,
        "observed": None,
        "actionable": None,
        "oldest_actionable": None,
        "effect": None,
        "official_readback": None,
        "pending": None,
        "estimate_required": None,
        "estimate_effect": None,
        "estimate_readback": None,
        "estimate_pending": None,
        "estimate_failed": None,
        "estimate_events": [],
        "officially_unrepliable_count": None,
        "stop_contact_count": None,
        "classification_failed_count": None,
        "collector_unhealthy_count": None,
        "semantic_judgement_failed_count": None,
        "semantic_migration_pending_count": None,
        "thread_changed_buyer_count": None,
        "thread_readback_count": None,
        "thread_revalidated_count": None,
        "next_wake": None,
    }


def _persist_wake_report(args: Any, output: Path, result: dict[str, Any]) -> None:
    report_input = output
    fallback_dir: Path | None = None
    try:
        try:
            _atomic_json(output, result)
        except Exception as error:
            result["status"] = "failed"
            result.setdefault("failed_step", "output")
            result.setdefault("errors", []).append({
                "type": type(error).__name__, "message": str(error)[:300],
            })
            fallback_dir = Path(tempfile.mkdtemp(prefix="gig-reply-wake-"))
            report_input = fallback_dir / "detector-result.json"
            _atomic_json(report_input, result)
        result["telegram_report"] = _telegram_report(args, report_input, "reply-wake")
        if report_input != output:
            _atomic_json(report_input, result)
        else:
            try:
                _atomic_json(output, result)
            except Exception:
                pass
    finally:
        if fallback_dir is not None:
            try:
                (fallback_dir / "detector-result.json").unlink(missing_ok=True)
                fallback_dir.rmdir()
            except OSError:
                pass


def _persist_continuous_worker_report(
    args: Any, output: Path, result: dict[str, Any],
) -> None:
    """Report every terminal continuous worker result through the durable outbox."""
    events = result.get("events")
    if isinstance(events, list) and events:
        _atomic_json(output, result)
        result["telegram_report"] = _telegram_report(args, output, "reply")
        _atomic_json(output, result)
        return
    wake = {**_wake_result(
        run_id=str(result.get("run_id") or f"continuous-{int(time.time())}"),
        trigger="continuous", status=str(result.get("status") or "failed"),
    ), **result}
    _persist_wake_report(args, output, wake)


def _owner_only(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            path.chmod(0o600)


def _requested_estimate_module() -> Any:
    path = Path(__file__).with_name("requested_estimate.py")
    spec = importlib.util.spec_from_file_location("gig_requested_estimate_detector", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("requested_estimate_module_missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_requested_estimate(
    snapshot: dict[str, Any], *, args: Any, owner: str, now: int,
    target_action_id: int | None = None,
) -> dict[str, Any]:
    """Run the estimate lane between collect and normal queue construction."""
    module = _requested_estimate_module()
    return module.process_snapshot(
        snapshot,
        database_path=args.database,
        manifest=args.manifest,
        runner=args.runner,
        schema=args.estimate_schema,
        workdir=Path.home(),
        helper=args.cdp_helper,
        owner=owner,
        hidden=False,
        now=now,
        target_action_id=target_action_id,
    )


def _estimate_candidate_key(item: dict[str, Any]) -> str | None:
    thread_id = str(item.get("talkroom_id") or item.get("thread_id") or "")
    identity = str(
        item.get("estimate_request_identity")
        or item.get("buyer_request_identity")
        or ""
    )
    if _TARGETED_THREAD_ID.fullmatch(thread_id) is None or not identity:
        return None
    try:
        module = _requested_estimate_module()
        key = module.coconala_estimate_event_key(thread_id, identity)
        return module.validate_estimate_event_key(key, thread_id)
    except Exception:
        return None


def _expected_estimate_bindings(
    database: Path, event_keys: set[str],
) -> dict[str, tuple[int, int]]:
    """Read the current durable action/revision for effect-capable estimates."""
    if not event_keys:
        return {}
    try:
        placeholders = ",".join("?" for _ in event_keys)
        with sqlite3.connect(f"file:{Path(database).resolve()}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                f"""SELECT e.event_key,a.action_id,a.revision
                      FROM connector_events e
                      JOIN connector_actions a ON a.action_id=e.action_id
                      WHERE e.event_key IN ({placeholders})
                        AND a.state='replied' AND a.dlq_at IS NULL
                        AND NOT EXISTS (
                          SELECT 1 FROM connector_events newer
                           WHERE newer.action_id=e.action_id
                             AND newer.event_key LIKE 'coconala:estimate:v1:%'
                             AND newer.rowid>e.rowid
                        )""",
                tuple(event_keys),
            ).fetchall()
    except (OSError, sqlite3.Error):
        return {}
    return {
        str(event_key): (int(action_id), int(revision))
        for event_key, action_id, revision in rows
        if int(action_id) > 0 and int(revision) > 0
    }


def _normalize_estimate_result(
    estimate_result: dict[str, Any], *, expected_thread: str | None = None,
    expected_event_keys: set[str] | None = None,
    expected_event_bindings: dict[str, tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Publish aggregate estimate proof only when every event is exact."""
    normalized = dict(estimate_result)
    effect = _count(normalized.get("estimate_effect"))
    readback = _count(normalized.get("estimate_readback"))
    events = normalized.get("estimate_events")
    proof_valid = (
        effect is not None and readback is not None
        and isinstance(events, list)
        and expected_event_keys is not None
        and expected_event_bindings is not None
    )
    event_effect = 0
    event_readback = 0
    event_keys: set[str] = set()
    action_bindings: set[tuple[int, int]] = set()
    try:
        validate_event_key = _requested_estimate_module().validate_estimate_event_key
    except Exception:
        validate_event_key = None
        proof_valid = False
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            proof_valid = False
            continue
        event_effect_value = _count(event.get("effect"))
        event_readback_value = _count(event.get("official_readback"))
        if event_effect_value not in {0, 1} or event_readback_value not in {0, 1}:
            proof_valid = False
            continue
        event_effect += event_effect_value
        event_readback += event_readback_value
        thread_id = str(event.get("thread_id") or "").strip()
        event_key = str(event.get("event_key") or "")
        if (
            validate_event_key is None
            or _TARGETED_THREAD_ID.fullmatch(thread_id) is None
            or expected_thread is not None and thread_id != expected_thread
        ):
            proof_valid = False
            continue
        try:
            validate_event_key(event_key, thread_id)
        except Exception:
            proof_valid = False
            continue
        if event_key not in (expected_event_keys or set()) or event_key in event_keys:
            proof_valid = False
        event_keys.add(event_key)
        action_id = _count(event.get("action_id"))
        revision = _count(event.get("revision"))
        has_action_binding = action_id is not None or revision is not None
        if has_action_binding:
            if action_id is None or revision is None or action_id <= 0 or revision <= 0:
                proof_valid = False
        if event_effect_value:
            if (action_id, revision) in action_bindings:
                proof_valid = False
            else:
                action_bindings.add((action_id, revision))
            if (
                event.get("status") != "verified"
                or event_readback_value != 1
                or not has_action_binding
                or expected_event_bindings.get(event_key) != (action_id, revision)
            ):
                proof_valid = False
        elif event_readback_value:
            if (action_id, revision) in action_bindings:
                proof_valid = False
            else:
                action_bindings.add((action_id, revision))
            if (
                event.get("status") not in {"verified", "already_delivered"}
                or not has_action_binding
                or expected_event_bindings.get(event_key) != (action_id, revision)
            ):
                proof_valid = False
        elif event.get("status") in {"reconcile_pending", "honestly_pending", "failed"}:
            if event_readback_value != 0:
                proof_valid = False
        else:
            proof_valid = False
    if event_keys != (expected_event_keys or set()):
        proof_valid = False
    if proof_valid and effect == event_effect and readback == event_readback:
        return normalized
    normalized["estimate_effect"] = 0
    normalized["estimate_readback"] = 0
    normalized["estimate_pending"] = max(
        _count(normalized.get("estimate_pending")) or 0, effect or 0, 1,
    )
    errors = list(normalized.get("errors") or [])
    if "estimate_verified_readback_missing" not in errors:
        errors.append("estimate_verified_readback_missing")
    normalized["errors"] = errors
    return normalized


def merge_estimate_metrics(
    result: dict[str, Any], estimate_result: dict[str, Any], *,
    normal_actionable: int | None, expected_thread: str | None = None,
    expected_event_keys: set[str] | None = None,
    expected_event_bindings: dict[str, tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Project estimate outcomes into the one wake truth without relabelling them."""
    estimate_result = _normalize_estimate_result(
        estimate_result, expected_thread=expected_thread,
        expected_event_keys=expected_event_keys,
        expected_event_bindings=expected_event_bindings,
    )
    estimate_required = _count(estimate_result.get("estimate_required"))
    estimate_effect = _count(estimate_result.get("estimate_effect"))
    estimate_readback = _count(estimate_result.get("estimate_readback"))
    estimate_pending = _count(estimate_result.get("estimate_pending"))
    estimate_failed = _count(estimate_result.get("estimate_failed"))
    result.update({
        key: estimate_result.get(key)
        for key in (
            "estimate_required", "estimate_effect", "estimate_readback",
            "estimate_pending", "estimate_failed", "estimate_events",
        )
    })
    if isinstance(normal_actionable, int) and estimate_required is not None:
        result["actionable"] = normal_actionable + estimate_required
    for total_key, estimate_value, normal_key in (
        ("effect", estimate_effect, "effect"),
        ("official_readback", estimate_readback, "official_readback"),
        ("pending", estimate_pending, "pending"),
        ("failed", estimate_failed, "failed"),
    ):
        normal_value = result.get(normal_key)
        if isinstance(normal_value, int) and estimate_value is not None:
            result[total_key] = normal_value + estimate_value
        elif estimate_value is not None and normal_value is None:
            result[total_key] = None
    result.setdefault("errors", []).extend(list(estimate_result.get("errors") or []))
    if estimate_failed and result.get("status") in {"completed", "reconcile_pending"}:
        result["status"] = "failed"
    elif estimate_pending and result.get("status") == "completed":
        result["status"] = "reconcile_pending"
    return result


def install_token_budget(environ: dict[str, str], *, run_id: str) -> None:
    """Keep the direct Reply owner free of inherited ANICCA token caps."""
    del run_id
    for key in (
        "ANICCA_BUDGET_SCOPE_ID", "ANICCA_PASS_TOKEN_BUDGET",
        "ANICCA_LOOP_DAILY_TOKEN_BUDGET", "ANICCA_BUDGET_DAILY_SCOPE",
        "ANICCA_BUDGET_REQUIRED",
    ):
        environ.pop(key, None)
    environ.setdefault(
        "ANICCA_TOKEN_BUDGET_LEDGER",
        environ.get(
            "GIG_TOKEN_BUDGET_LEDGER",
            str(Path.home() / ".local/state/anicca/telemetry/token-budget.jsonl"),
        ),
    )


_TARGETED_THREAD_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_TARGETED_SEND_ACTIONS = frozenset({"reply", "clarify"})
_TARGETED_ESTIMATE_ACTIONS = frozenset({"requested_estimate", "send_estimate"})
_TARGETED_INTENTIONAL_NO_SEND = frozenset({
    "wait", "stop_contact", "terminal_acknowledgement", "observe",
    "officially_unrepliable",
})
_INBOX_EVENT = re.compile(
    r"^coconala:inbox:v1:(?P<thread>[A-Za-z0-9_-]{1,128}):"
    r"sha256_v1:(?P<identity>[0-9a-f]{64})$"
)
_FRESH_PROOF_MAX_AGE_SECONDS = 300


def _targeted_arg(args: Any, name: str, default: Any) -> Any:
    """Read a worker argument while keeping the public helper testable."""
    value = getattr(args, name, None)
    return default if value is None else value


def _targeted_failure(thread_id: str, run_id: str, step: str, error: Any) -> dict[str, Any]:
    return {
        "status": "failed", "thread_id": thread_id, "run_id": run_id,
        "failed_step": step, "replied": 0, "official_readback": 0,
        "duplicate_effect": 0, "closed_without_send": 0, "pending": 0,
        "errors": [{"type": type(error).__name__, "message": str(error)[:300]}],
        "events": [],
    }


def _targeted_pending(
    thread_id: str, run_id: str, *, error: str, semantic_failure: str | None = None,
    estimate_result: dict[str, Any] | None = None, blocked: int = 0,
    current_identity_sha256: str | None = None,
    current_last_message_side: str | None = None,
    current_buyer_sent_at: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "pending", "thread_id": thread_id, "run_id": run_id,
        "replied": 0, "official_readback": 0, "duplicate_effect": 0,
        "closed_without_send": 0, "blocked": blocked, "pending": 1, "events": [],
        "errors": [error],
    }
    if semantic_failure:
        result["semantic_failure"] = semantic_failure[:160]
    if estimate_result is not None:
        result.update({
            key: estimate_result.get(key, 0)
            for key in (
                "estimate_required", "estimate_effect", "estimate_readback",
                "estimate_pending", "estimate_failed", "estimate_events",
            )
        })
    else:
        result.update({
            "estimate_required": 0, "estimate_effect": 0,
            "estimate_readback": 0, "estimate_pending": 0,
            "estimate_failed": 0, "estimate_events": [],
        })
    if re.fullmatch(r"[0-9a-f]{64}", str(current_identity_sha256 or "")):
        result.update({
            "current_identity_sha256": str(current_identity_sha256),
            "current_event_key": coconala_inbox_event_key(
                thread_id, str(current_identity_sha256),
            ),
            "current_last_message_side": str(current_last_message_side or ""),
        })
        if current_buyer_sent_at:
            result["current_buyer_sent_at"] = str(current_buyer_sent_at)
    return result


def _targeted_snapshot(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("targeted snapshot must be an object")
    return value


def _targeted_inquiry(snapshot: dict[str, Any], thread_id: str) -> dict[str, Any]:
    if (
        snapshot.get("collector_mode") != "direct-thread-only"
        or snapshot.get("semantic_ssot") is not True
        or not isinstance(snapshot.get("inquiries"), list)
        or len(snapshot["inquiries"]) != 1
    ):
        raise ValueError("targeted collector must emit one semantic inquiry")
    inquiry = snapshot["inquiries"][0]
    if not isinstance(inquiry, dict) or str(inquiry.get("talkroom_id") or "") != thread_id:
        raise ValueError("targeted inquiry thread mismatch")
    expected_url = f"https://coconala.com/mypage/direct_message/{thread_id}"
    if inquiry.get("talkroom_url") != expected_url:
        raise ValueError("targeted inquiry route mismatch")
    if inquiry.get("last_message_side") == "buyer":
        if re.fullmatch(
            r"[0-9a-f]{64}", str(inquiry.get("last_message_identity_sha256") or "")
        ) is None:
            raise ValueError("targeted inquiry missing message identity")
        if not inquiry.get("buyer_sent_at"):
            raise ValueError("targeted inquiry missing buyer timestamp")
    return inquiry


def _targeted_presemantic_snapshot(
    snapshot: dict[str, Any], inquiry: dict[str, Any], *, semantic: bool,
) -> dict[str, Any]:
    """Create the one-item queue projection without re-reading customer prose."""
    projected = dict(snapshot)
    row = dict(inquiry)
    if not semantic:
        for key in (
            "semantic_receipt", "semantic_context_sha256", "semantic_reply_body",
            "semantic_estimate_terms", "semantic_failure", "semantic_candidate_action",
            "semantic_official_context_required",
        ):
            row.pop(key, None)
        row["estimate_required"] = False
        row["reply_required"] = row.get("last_message_side") == "buyer"
        row["next_action"] = "reply" if row["reply_required"] else "observe"
    projected["inquiries"] = [row]
    projected["orders"] = []
    projected["semantic_ssot"] = semantic
    return projected


def _inbox_identity(event_key: str, thread_id: str) -> str:
    match = _INBOX_EVENT.fullmatch(str(event_key or ""))
    if match is None or match.group("thread") != thread_id:
        raise ValueError("inbox event identity does not match thread")
    identity = match.group("identity")
    # Reuse the outbox's canonical key builder; this keeps validation and
    # closure on exactly the same typed inbox identity grammar.
    if coconala_inbox_event_key(thread_id, identity) != event_key:
        raise ValueError("inbox event identity is not canonical")
    return identity


def _durable_event_action(
    database: Path, event_key: str, thread_id: str,
) -> dict[str, Any] | None:
    """Read one exact event/action binding without accepting a thread-wide candidate."""
    with sqlite3.connect(database, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT a.*,e.event_key AS bound_event_key,e.thread_id AS event_thread_id
                 FROM connector_events e
                 JOIN connector_actions a ON a.action_id=e.action_id
                WHERE e.event_key=? AND e.thread_id=?
                LIMIT 1""",
            (event_key, thread_id),
        ).fetchone()
    return dict(row) if row is not None else None


def _retry_estimate_snapshot(
    database: Path, binding: dict[str, Any], event_key: str,
    snapshot: dict[str, Any], thread_id: str,
) -> dict[str, Any] | None:
    """Reuse a pre-click estimate intent only while its source inbox head is current."""
    inquiries = snapshot.get("inquiries") if isinstance(snapshot, dict) else None
    if not isinstance(inquiries, list) or len(inquiries) != 1:
        return None
    inquiry = inquiries[0]
    if not isinstance(inquiry, dict) or inquiry.get("talkroom_id") != thread_id:
        return None
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        row = connection.execute(
            """SELECT i.outgoing_body,i.origin_at,source.event_key
                 FROM connector_events estimate
                 JOIN connector_intents i ON i.action_id=estimate.action_id
                 JOIN connector_events source ON source.rowid=(
                   SELECT prior.rowid FROM connector_events prior
                    WHERE prior.thread_id=estimate.thread_id
                      AND prior.event_key LIKE 'coconala:inbox:v1:%'
                      AND prior.observed_at<=estimate.observed_at
                    ORDER BY prior.observed_at DESC,prior.rowid DESC LIMIT 1)
                WHERE estimate.action_id=? AND estimate.event_key=?
                  AND i.outgoing_body IS NOT NULL
                ORDER BY i.revision DESC LIMIT 1""",
            (int(binding["action_id"]), event_key),
        ).fetchone()
    if row is None:
        return None
    source = _INBOX_EVENT.fullmatch(str(row[2] or ""))
    if source is None or source.group("identity") != inquiry.get("last_message_identity_sha256"):
        return None
    try:
        terms = json.loads(str(row[0]))
        module = _requested_estimate_module()
        module.canonical_offer_terms(terms)
        module.validate_estimate_event_key(event_key, thread_id)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    projected = dict(snapshot)
    item = dict(inquiry)
    item.update({
        "reply_required": False, "next_action": "requested_estimate",
        "estimate_required": True, "semantic_failure": None,
        "estimate_request_identity": event_key.rsplit(":", 1)[-1],
        "estimate_request_sent_at": int(row[1]),
        "semantic_estimate_terms": terms, "estimate_terms": terms,
        "source_inbox_identity_sha256": source.group("identity"),
    })
    projected.update({
        "collector_mode": "direct-thread-only", "semantic_ssot": True,
        "head_only": False, "inquiries": [item],
    })
    return projected


def _validate_target_binding(
    *, database: Path, manifest: Path, action_id: int, inbox_event_key: str, thread_id: str,
) -> dict[str, Any]:
    if type(action_id) is not int or action_id <= 0:
        raise ValueError("invalid action_id")
    if _TARGETED_THREAD_ID.fullmatch(thread_id or "") is None:
        raise ValueError("invalid thread id")
    identity = _inbox_identity(inbox_event_key, thread_id)
    outbox = ConnectorOutbox(database, manifest)
    action = outbox.get_action(action_id)
    bound = _durable_event_action(database, inbox_event_key, thread_id)
    if (
        action.get("platform") != "coconala"
        or str(action.get("thread_id") or "") != thread_id
        or str(action.get("thread_url") or "")
        != f"https://coconala.com/mypage/direct_message/{thread_id}"
        or bound is None
        or int(bound.get("action_id") or 0) != action_id
        or bound.get("bound_event_key") != inbox_event_key
    ):
        raise ValueError("target binding mismatch")
    expected_revision = _count(action.get("revision"))
    if expected_revision is None or expected_revision <= 0:
        raise ValueError("target action revision invalid")
    if action.get("state") == "pending" and action.get("dlq_at") is None:
        state = "pending"
    elif action.get("state") == "replied" and action.get("dlq_at") is None:
        state = "already_delivered"
    elif action.get("dlq_at") is not None:
        state = "already_closed"
    else:
        raise ValueError("target action is not pending")
    return {
        "action_id": action_id, "inbox_event_key": inbox_event_key,
        "thread_id": thread_id, "identity_sha256": identity,
        "expected_revision": expected_revision, "state": state,
    }


def _targeted_close_no_send(
    *, database: Path, manifest: Path, action_id: int, thread_id: str,
    inbox_event_key: str, expected_revision: int, reason: str, run_id: str,
) -> dict[str, Any] | None:
    """Claim and close only the exact action named by the durable inbox event."""
    if type(expected_revision) is not int or expected_revision <= 0:
        return None
    bound = _durable_event_action(database, inbox_event_key, thread_id)
    if bound is None or int(bound.get("action_id") or 0) != action_id:
        return None
    if int(bound.get("revision") or 0) != expected_revision:
        return None
    if bound.get("state") != "pending" or bound.get("dlq_at") is not None:
        return None
    now = max(int(time.time()), int(bound.get("updated_at") or 0))
    owner = f"gig-targeted-{run_id}"
    outbox = ConnectorOutbox(database, manifest)
    claimed = outbox.claim(owner=owner, now=now, lease_seconds=30, action_id=action_id)
    if claimed is None or int(claimed.get("revision") or 0) != expected_revision:
        return None
    closed = outbox.close_nothing_to_say(
        action_id, owner=owner, fencing_token=int(claimed["fencing_token"]),
        reason=reason[:120], now=now,
    )
    if int(closed.get("revision") or 0) != expected_revision:
        return None
    return {
        "action_id": int(closed["action_id"]),
        "revision": int(closed["revision"]), "status": "nothing_to_say",
    }


def _targeted_close_obsolete_estimate(
    *, database: Path, manifest: Path, action_id: int, thread_id: str,
    event_key: str, expected_revision: int, run_id: str,
) -> dict[str, Any] | None:
    """Close the exact pending estimate after fresh semantics withdraws the request."""
    try:
        _requested_estimate_module().validate_estimate_event_key(event_key, thread_id)
    except Exception:
        return None
    bound = _durable_event_action(database, event_key, thread_id)
    if (
        bound is None or int(bound.get("action_id") or 0) != action_id
        or int(bound.get("revision") or 0) != expected_revision
        or bound.get("state") != "pending" or bound.get("dlq_at") is not None
    ):
        return None
    now = max(int(time.time()), int(bound.get("updated_at") or 0))
    owner = f"gig-estimate-obsolete-{run_id}"
    outbox = ConnectorOutbox(database, manifest)
    claimed = outbox.claim(owner=owner, now=now, lease_seconds=30, action_id=action_id)
    if claimed is None or int(claimed.get("revision") or 0) != expected_revision:
        return None
    closed = outbox.close_nothing_to_say(
        action_id, owner=owner, fencing_token=int(claimed["fencing_token"]),
        reason="estimate_no_longer_required", now=now,
    )
    return {
        "action_id": int(closed["action_id"]),
        "revision": int(closed["revision"]), "status": "nothing_to_say",
    }


def _collect_targeted_head(
    args: Any, *, evidence: Path, thread_id: str, identity_sha256: str,
) -> dict[str, Any]:
    path = evidence / "targeted-head-snapshot.json"
    gig_root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable, str(_targeted_arg(args, "snapshot_script", gig_root / "scripts/coconala_queue_snapshot.py")),
        "--output", str(path), "--evidence-dir", str(evidence / "direct-head"),
        "--mode", "direct-thread-head-only", "--talkroom-id", thread_id,
        "--hidden-no-screenshot",
        "--database", str(_targeted_arg(args, "database", Path.home() / "gig/connector-outbox.sqlite3")),
        "--manifest", str(_targeted_arg(args, "manifest", gig_root / "config/connectors/coconala.json")),
    ]
    _run("head_collect", command)
    value = _targeted_snapshot(path)
    if (
        value.get("collector_mode") != "direct-thread-head-only"
        or value.get("head_only") is not True
        or value.get("read_only") is not True
        or value.get("semantic_ssot") is not False
        or not isinstance(value.get("inquiries"), list)
    ):
        raise ValueError("targeted head proof incomplete")
    rows = [
        row for row in value["inquiries"]
        if isinstance(row, dict) and str(row.get("talkroom_id") or "") == thread_id
    ]
    if len(rows) != 1:
        raise ValueError("targeted head thread missing")
    row = rows[0]
    expected_url = f"https://coconala.com/mypage/direct_message/{thread_id}"
    if str(row.get("talkroom_url") or "") != expected_url:
        raise ValueError("targeted head route mismatch")
    if row.get("last_message_identity_sha256") != identity_sha256:
        raise TargetedIdentityChanged(row)
    return row


def _targeted_identity_pending(
    thread_id: str, run_id: str, row: dict[str, Any],
) -> dict[str, Any]:
    return _targeted_pending(
        thread_id, run_id, error="targeted_inbox_identity_changed",
        current_identity_sha256=str(row.get("last_message_identity_sha256") or ""),
        current_last_message_side=str(row.get("last_message_side") or ""),
        current_buyer_sent_at=(
            str(row.get("buyer_sent_at") or "")
            if row.get("buyer_sent_at") else None
        ),
    )


def _fresh_capture_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError("orders proof timestamp invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("orders proof timestamp missing timezone")
    return parsed.astimezone(timezone.utc)


def _effect_fence_module() -> Any:
    path = Path(__file__).with_name("project_effect_fence.py")
    spec = importlib.util.spec_from_file_location("gig_project_effect_fence_detector", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("project_effect_fence_module_missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collect_fresh_orders_and_fence(
    args: Any, *, evidence: Path,
) -> tuple[dict[str, Any], Path]:
    """Collect complete orders proof, then build a fence from that same receipt."""
    gig_root = Path(__file__).resolve().parents[1]
    orders_path = evidence / "orders-snapshot.json"
    fences_path = evidence / "project-fences.json"
    database = Path(_targeted_arg(args, "database", Path.home() / "gig/connector-outbox.sqlite3"))
    manifest = Path(_targeted_arg(args, "manifest", gig_root / "config/connectors/coconala.json"))
    snapshot_script = Path(_targeted_arg(args, "snapshot_script", gig_root / "scripts/coconala_queue_snapshot.py"))
    fence_script = Path(_targeted_arg(args, "fence_script", gig_root / "scripts/project_effect_fence.py"))
    _run("orders_collect", [
        sys.executable, str(snapshot_script), "--output", str(orders_path),
        "--evidence-dir", str(evidence / "orders"), "--mode", "orders-only",
        "--hidden-no-screenshot", "--database", str(database), "--manifest", str(manifest),
    ])
    orders = _targeted_snapshot(orders_path)
    receipt = orders.get("source_receipt")
    if (
        orders.get("collector_mode") != "orders-only"
        or not isinstance(orders.get("orders"), list)
        or not isinstance(receipt, dict)
        or receipt.get("coverage_complete") is not True
    ):
        raise ValueError("orders proof incomplete")
    captured = _fresh_capture_time(orders.get("captured_at") or receipt.get("observed_at"))
    age = time.time() - captured.timestamp()
    if age > _FRESH_PROOF_MAX_AGE_SECONDS or age < -60:
        raise ValueError("orders proof stale")
    _run("fence_build", [
        sys.executable, str(fence_script), "build-paid", "--snapshot", str(orders_path),
        "--now", datetime.now(timezone.utc).isoformat(), "--output", str(fences_path),
    ])
    _owner_only(fences_path)
    try:
        registry = json.loads(fences_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("paid fence proof missing") from error
    if (
        not isinstance(registry, dict) or registry.get("version") != 1
        or not isinstance(registry.get("fences"), list)
        or fences_path.stat().st_mtime_ns < orders_path.stat().st_mtime_ns
    ):
        raise ValueError("paid fence proof stale or invalid")
    fence_module = _effect_fence_module()
    fence_module.validate_registry(registry)
    return orders, fences_path


def _paid_fence_open_for_thread(path: Path, thread_id: str) -> bool:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        raise ValueError("paid fence proof unreadable")
    module = _effect_fence_module()
    module.validate_registry(registry)
    return bool(module.active_fences_for_item(
        {"talkroom_id": thread_id}, registry,
        capability=module.CONVERSATION_WRITE, platform=module.COCONALA,
        now=datetime.now(timezone.utc),
    ))


def _close_paid_handoff(
    database: Path, manifest: Path, fences_path: Path, thread_id: str,
) -> list[dict[str, Any]]:
    if not _paid_fence_open_for_thread(fences_path, thread_id):
        return []
    return ConnectorOutbox(database, manifest).close_paid_handoff(
        thread_id, observed_at=int(time.time()),
    )


def _targeted_effect_result(
    lane: dict[str, Any], *, thread_id: str, action_id: int | None = None,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    events = lane.get("events") if isinstance(lane.get("events"), list) else []
    counts = {
        key: _count(lane.get(key)) or 0
        for key in (
            "replied", "reconciled", "requeued", "pending_verify", "reconcile_pending",
            "already_delivered", "nothing_to_say", "failed", "blocked",
            "skipped", "deferred", "dlq",
        )
    }
    verified = _verified_events(
        events, counts["replied"], expected_thread=thread_id or None,
        expected_action_id=action_id,
        expected_revision=expected_revision,
    )
    errors = list(lane.get("errors") or [])
    pending = counts["pending_verify"] + counts["reconcile_pending"]
    status = str(lane.get("status") or "failed")
    raw_replied = counts["replied"]
    if raw_replied and verified is None:
        errors.append("verified_readback_missing")
        pending = max(1, pending, raw_replied)
        status = "failed" if counts["failed"] else "reconcile_pending"
        # Do not publish an unverified positive as a successful reply count.
        counts["replied"] = 0
    return {
        "status": status, "thread_id": thread_id, **counts,
        "replied": counts["replied"],
        "official_readback": len(verified) if verified is not None else 0,
        "duplicate_effect": sum(
            1 for event in events
            if isinstance(event, dict)
            and event.get("status") in {"duplicate_effect", "duplicate_sent"}
        ),
        "closed_without_send": counts["nothing_to_say"], "pending": pending,
        "effect": max(0, counts["replied"] - counts["reconciled"]),
        "events": events, "dlq_events": list(lane.get("dlq_events") or []),
        "errors": errors,
    }


def _targeted_seller_debt_reply(inquiry: dict[str, Any]) -> bool:
    receipt = inquiry.get("semantic_receipt")
    judgement = receipt.get("judgement") if isinstance(receipt, dict) else None
    return bool(
        inquiry.get("last_message_side") == "seller"
        and inquiry.get("reply_required") is True
        and inquiry.get("next_action") == "reply"
        and isinstance(receipt, dict)
        and _requested_estimate_module().semantic_prompt_compatible(receipt)
        and isinstance(judgement, dict)
        and judgement.get("next_action") == "reply"
        and type(inquiry.get("semantic_reply_body")) is str
        and inquiry["semantic_reply_body"].strip()
    )


def _bind_targeted_seller_debt_queue(
    queue: dict[str, Any], target: dict[str, Any],
) -> dict[str, Any]:
    event_key = str(target.get("inbox_event_key") or "")
    match = _INBOX_EVENT.fullmatch(event_key)
    items = queue.get("items") if isinstance(queue.get("items"), list) else []
    if match is None or match.group("thread") != str(target.get("thread_id") or "") or len(items) != 1:
        raise ValueError("targeted seller debt queue binding invalid")
    rebound = dict(queue)
    item = dict(items[0])
    item["event_key"] = event_key
    item["covered_event_keys"] = [event_key]
    rebound["items"] = [item]
    return rebound


def _run_effect_pipeline(
    args: Any, *, snapshot: dict[str, Any], evidence: Path, run_id: str,
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shared queue, proof, estimate, normal effect and readback pipeline."""
    gig_root = Path(__file__).resolve().parents[1]
    home = Path.home()
    database = Path(_targeted_arg(args, "database", home / "gig/connector-outbox.sqlite3"))
    manifest = Path(_targeted_arg(args, "manifest", gig_root / "config/connectors/coconala.json"))
    queue_script = Path(_targeted_arg(args, "queue_script", gig_root / "scripts/reply_queue.py"))
    lane_script = Path(_targeted_arg(args, "lane_script", gig_root / "scripts/reply_lane.py"))
    runner = Path(_targeted_arg(args, "runner", RUNNER_DIR / "agent_runner.py"))
    reply_schema = Path(_targeted_arg(args, "schema", gig_root / "schemas/reply_composition.schema.json"))
    helper = Path(_targeted_arg(args, "cdp_helper", BROWSER_DIR / "scripts/cdp_default_tab.py"))
    estimate_schema = Path(_targeted_arg(args, "estimate_schema", gig_root / "schemas/estimate_category_selection.schema.json"))
    queue_path = evidence / "reply-queue.json"
    normal_path = evidence / "normal-reply-snapshot.json"
    lane_path = evidence / "reply-lane-result.json"
    estimate_path = evidence / "requested-estimate-result.json"

    inquiry: dict[str, Any] | None = None
    next_action = ""
    semantic_failure: str | None = None
    semantic_ready = False
    estimate_required = False
    no_send = False
    seller_debt_reply = False
    thread_id = str(target.get("thread_id") or "") if target else ""
    target_expected_revision = (
        _count(target.get("expected_revision")) if target else None
    )
    if target and (
        target_expected_revision is None or target_expected_revision <= 0
    ):
        return _targeted_pending(
            thread_id, run_id, error="targeted_action_revision_invalid",
        )
    if target:
        inquiry = _targeted_inquiry(snapshot, thread_id)
        observed_identity = str(inquiry.get("last_message_identity_sha256") or "")
        if (
            observed_identity != str(target.get("identity_sha256") or "")
            or coconala_inbox_event_key(thread_id, observed_identity)
            != str(target.get("inbox_event_key") or "")
        ):
            return _targeted_pending(
                thread_id, run_id, error="targeted_inbox_identity_changed",
                current_identity_sha256=observed_identity,
                current_last_message_side=str(inquiry.get("last_message_side") or ""),
                current_buyer_sent_at=(
                    str(inquiry.get("buyer_sent_at") or "")
                    if inquiry.get("buyer_sent_at") else None
                ),
            )
        next_action = str(inquiry.get("next_action") or "")
        semantic_failure = str(inquiry.get("semantic_failure") or "") or None
        semantic_receipt = inquiry.get("semantic_receipt")
        seller_debt_reply = _targeted_seller_debt_reply(inquiry)
        estimate_required = bool(
            inquiry.get("estimate_required") is True
            or next_action in _TARGETED_ESTIMATE_ACTIONS
        )
        semantic_ready = bool(
            isinstance(semantic_receipt, dict)
            and semantic_failure is None
            and (
                inquiry.get("last_message_side") == "buyer"
                or next_action in _TARGETED_ESTIMATE_ACTIONS
                or seller_debt_reply
            )
            and next_action in (_TARGETED_SEND_ACTIONS | _TARGETED_ESTIMATE_ACTIONS)
        )
        no_send = next_action in _TARGETED_INTENTIONAL_NO_SEND
        if no_send and not semantic_failure:
            closed = _targeted_close_no_send(
                database=database, manifest=manifest,
                action_id=int(target["action_id"]), thread_id=thread_id,
                inbox_event_key=str(target["inbox_event_key"]),
                expected_revision=target_expected_revision,
                reason=next_action or "intentional_no_send", run_id=run_id,
            )
            if closed is not None and int(closed.get("revision") or 0) == target_expected_revision:
                return {
                    "status": "completed", "thread_id": thread_id, "run_id": run_id,
                    "replied": 0, "official_readback": 0, "duplicate_effect": 0,
                    "closed_without_send": 1, "pending": 0, "events": [], "errors": [],
                    "estimate_required": 0, "estimate_effect": 0,
                    "estimate_readback": 0, "estimate_pending": 0,
                    "estimate_failed": 0, "estimate_events": [],
                }
        if estimate_required:
            normal_value = _targeted_presemantic_snapshot(snapshot, inquiry, semantic=False)
        else:
            normal_value = _targeted_presemantic_snapshot(
                snapshot, inquiry, semantic=semantic_ready and next_action in _TARGETED_SEND_ACTIONS,
            )
            if seller_debt_reply:
                normal_value["inquiries"][0]["semantic_seller_debt_reply"] = True
    else:
        normal_value = dict(snapshot)
        if isinstance(snapshot.get("inquiries"), list):
            normal_value["inquiries"] = [
                item for item in snapshot["inquiries"]
                if not (isinstance(item, dict) and item.get("estimate_required") is True)
            ]
    _atomic_json(normal_path, normal_value)
    _owner_only(normal_path)
    _run("queue_build", [
        sys.executable, str(queue_script), "build",
        "--snapshot", str(normal_path), "--output", str(queue_path),
    ])
    _owner_only(queue_path)
    queue_value = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(queue_value, dict):
        raise ValueError("reply queue must be an object")
    if target and seller_debt_reply:
        queue_value = _bind_targeted_seller_debt_queue(queue_value, target)
        _atomic_json(queue_path, queue_value)
        _owner_only(queue_path)
    _run("outbox_enqueue", [
        sys.executable, str(queue_script), "enqueue", "--queue", str(queue_path),
        "--database", str(database), "--manifest", str(manifest),
    ])
    if target:
        items = queue_value.get("items") if isinstance(queue_value.get("items"), list) else []
        bound = target if estimate_required else None
        if bound is None:
            for item in items:
                if not isinstance(item, dict):
                    continue
                candidate = _durable_event_action(
                    database, str(item.get("event_key") or ""), thread_id,
                )
                if (
                    candidate is not None
                    and int(candidate.get("action_id") or 0) == int(target["action_id"])
                ):
                    bound = candidate
                    break
        if bound is None:
            return _targeted_pending(thread_id, run_id, error="targeted_event_not_coalesced")
        # Re-read the durable binding after enqueue so a queue implementation
        # cannot silently redirect this collected message to another action.
        if not estimate_required:
            target_expected_revision = _count(bound.get("revision"))
            if target_expected_revision is None or target_expected_revision <= 0:
                return _targeted_pending(
                    thread_id, run_id, error="targeted_action_revision_invalid",
                )

        try:
            _collect_targeted_head(
                args, evidence=evidence, thread_id=thread_id,
                identity_sha256=str(target["identity_sha256"]),
            )
        except TargetedIdentityChanged as error:
            return _targeted_identity_pending(thread_id, run_id, error.row)
        except Exception as error:
            return _targeted_pending(thread_id, run_id, error=type(error).__name__ + ":" + str(error)[:180])
        if semantic_failure or not semantic_ready:
            return _targeted_pending(
                thread_id, run_id, error="semantic_action_not_authorized",
                semantic_failure=semantic_failure or (
                    "unknown_action:" + next_action if next_action not in _TARGETED_INTENTIONAL_NO_SEND else None
                ),
            )

    try:
        _orders, fences_path = _collect_fresh_orders_and_fence(
            args, evidence=evidence,
        )
    except Exception as error:
        if target:
            error_text = type(error).__name__ + ":" + str(error)[:180]
            return _targeted_pending(
                thread_id, run_id, error=error_text,
            )
        raise
    if target and _paid_fence_open_for_thread(fences_path, thread_id):
        closed = _close_paid_handoff(
            Path(args.database), Path(args.manifest), fences_path, thread_id,
        )
        return {
            "status": "paid_handoff", "thread_id": thread_id, "run_id": run_id,
            "replied": 0, "official_readback": 0, "duplicate_effect": 0,
            "closed_without_send": len(closed), "blocked": 0, "pending": 0,
            "events": [], "errors": [],
            "closed_action_ids": [row["action_id"] for row in closed],
        }

    estimate_result: dict[str, Any] = {
        "estimate_required": 0, "estimate_effect": 0,
        "estimate_readback": 0, "estimate_pending": 0,
        "estimate_failed": 0, "estimate_events": [], "errors": [],
    }
    estimate_candidates = [
        item for item in (snapshot.get("inquiries") or [])
        if isinstance(item, dict) and item.get("estimate_required") is True
    ]
    invalid_estimates = [
        item for item in estimate_candidates
        if not target and _estimate_candidate_key(item) is None
    ]
    valid_estimates = [item for item in estimate_candidates if item not in invalid_estimates]
    fenced_estimates = [
        item for item in valid_estimates
        if not target and _paid_fence_open_for_thread(
            fences_path, str(item.get("talkroom_id") or item.get("thread_id") or ""),
        )
    ]
    fenced_ids = {id(item) for item in fenced_estimates}
    expected_event_keys = {
        key for item in valid_estimates
        if id(item) not in fenced_ids
        and (key := _estimate_candidate_key(item)) is not None
    }
    excluded_estimates = invalid_estimates + fenced_estimates
    if estimate_required or (not target and estimate_candidates):
        estimate_args = argparse.Namespace(
            database=database, manifest=manifest, runner=runner,
            estimate_schema=estimate_schema, cdp_helper=helper,
        )
        estimate_snapshot = snapshot
        if excluded_estimates:
            estimate_snapshot = dict(snapshot)
            excluded_ids = {id(item) for item in excluded_estimates}
            estimate_snapshot["inquiries"] = [
                item for item in snapshot.get("inquiries", [])
                if id(item) not in excluded_ids
            ]
        try:
            estimate_result = run_requested_estimate(
                estimate_snapshot, args=estimate_args,
                owner=f"gig-estimate-{('targeted-' if target else 'detector-')}{run_id}",
                now=int(time.time()),
            )
        except Exception as error:
            estimate_result = {
                "estimate_required": len(estimate_candidates) or 1, "estimate_effect": 0,
                "estimate_readback": 0, "estimate_pending": 0,
                "estimate_failed": 1, "estimate_events": [],
                "errors": [{"type": type(error).__name__, "code": "estimate_lane_failed"}],
            }
        if excluded_estimates:
            estimate_result = dict(estimate_result)
            estimate_result["estimate_required"] = (
                _count(estimate_result.get("estimate_required")) or 0
            ) + len(excluded_estimates)
            estimate_result["estimate_pending"] = (
                _count(estimate_result.get("estimate_pending")) or 0
            ) + len(excluded_estimates)
            estimate_result["errors"] = list(estimate_result.get("errors") or []) + (
                ["estimate_thread_invalid" for _ in invalid_estimates]
                + ["estimate_effect_blocked_paid_fence" for _ in fenced_estimates]
            )
    _atomic_json(estimate_path, estimate_result)
    _owner_only(estimate_path)
    expected_event_bindings = _expected_estimate_bindings(
        Path(database), expected_event_keys,
    )
    if target and estimate_required:
        result = {
            "status": (
                "failed" if _count(estimate_result.get("estimate_failed")) else
                "reconcile_pending" if _count(estimate_result.get("estimate_pending")) else
                "completed"
            ),
            "thread_id": thread_id, "run_id": run_id, "replied": 0,
            "official_readback": 0, "duplicate_effect": 0,
            "closed_without_send": 0, "pending": _count(estimate_result.get("estimate_pending")) or 0,
            "events": [], "errors": list(estimate_result.get("errors") or []),
        }
        return merge_estimate_metrics(
            result, estimate_result, normal_actionable=0,
            expected_thread=thread_id,
            expected_event_keys=expected_event_keys,
            expected_event_bindings=expected_event_bindings,
        )

    _run("reply_lane", [
        sys.executable, str(lane_script), "--queue", str(queue_path),
        "--database", str(database), "--manifest", str(manifest),
        "--runner", str(runner), "--schema", str(reply_schema),
        "--cdp-helper", str(helper), "--max-model-calls", "0",
        "--output", str(lane_path), "--workdir", str(home),
        "--owner-prefix", f"gig-targeted-{run_id}" if target else f"gig-reply-detector-{run_id}",
        "--fences", str(fences_path),
    ], accepted=(0, 2))
    lane = json.loads(lane_path.read_text(encoding="utf-8"))
    if not isinstance(lane, dict):
        raise ValueError("reply lane result must be an object")
    result = _targeted_effect_result(
        lane, thread_id=thread_id if target else "",
        action_id=int(target["action_id"]) if target else None,
        expected_revision=target_expected_revision if target else None,
    )
    result["run_id"] = run_id
    result = merge_estimate_metrics(
        result, estimate_result,
        normal_actionable=(len(queue_value.get("items")) if isinstance(queue_value.get("items"), list) else None),
        expected_thread=thread_id if target else None,
        expected_event_keys=expected_event_keys,
        expected_event_bindings=expected_event_bindings,
    )
    return result


def run_targeted_thread(
    args: Any, *, action_id: int, inbox_event_key: str, thread_id: str,
    evidence: Path, run_id: str,
) -> dict[str, Any]:
    """Process one inbox-bound direct thread through the shared effect pipeline."""
    if not isinstance(thread_id, str) or _TARGETED_THREAD_ID.fullmatch(thread_id) is None:
        return _targeted_failure(thread_id, run_id, "validate_thread", ValueError("invalid thread id"))
    try:
        evidence = Path(evidence)
        evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
        evidence.chmod(0o700)
        gig_root = Path(__file__).resolve().parents[1]
        database = Path(_targeted_arg(args, "database", Path.home() / "gig/connector-outbox.sqlite3"))
        manifest = Path(_targeted_arg(args, "manifest", gig_root / "config/connectors/coconala.json"))
        binding = _validate_target_binding(
            database=database, manifest=manifest, action_id=action_id,
            inbox_event_key=inbox_event_key, thread_id=thread_id,
        )
        if binding["state"] != "pending":
            return {
                "status": binding["state"], "thread_id": thread_id, "run_id": run_id,
                "replied": 0, "official_readback": 0, "duplicate_effect": 0,
                "closed_without_send": 0, "pending": 0, "events": [], "errors": [],
            }
        try:
            # Read only the current inbox head before opening the direct thread.
            # A stale action is rebound immediately, without paying for semantic
            # judgement on obsolete customer prose.
            _collect_targeted_head(
                args, evidence=evidence, thread_id=thread_id,
                identity_sha256=str(binding["identity_sha256"]),
            )
        except TargetedIdentityChanged as error:
            return _targeted_identity_pending(thread_id, run_id, error.row)
        snapshot_script = Path(_targeted_arg(args, "snapshot_script", gig_root / "scripts/coconala_queue_snapshot.py"))
        runner = Path(_targeted_arg(args, "runner", RUNNER_DIR / "agent_runner.py"))
        semantic_schema = Path(_targeted_arg(args, "semantic_schema", gig_root / "schemas/reply_semantic_judgement.schema.json"))
        snapshot_path = evidence / "marketplace-snapshot.json"
        collect_command = [
            sys.executable, str(snapshot_script), "--output", str(snapshot_path),
            "--evidence-dir", str(evidence / "direct-thread"), "--mode", "direct-thread-only",
            "--talkroom-id", thread_id, "--hidden-no-screenshot",
            "--semantic-runner", str(runner), "--semantic-schema", str(semantic_schema),
            "--semantic-workdir", str(Path.home()), "--database", str(database),
            "--manifest", str(manifest),
        ]
        if _targeted_arg(args, "semantic_effects_enabled", True):
            collect_command.append("--semantic-effects-enabled")
        _run("collect", collect_command)
        _owner_only(snapshot_path)
        snapshot = _targeted_snapshot(snapshot_path)
        _targeted_inquiry(snapshot, thread_id)
        return _run_effect_pipeline(
            args, snapshot=snapshot, evidence=evidence, run_id=run_id, target=binding,
        )
    except StepFailure as error:
        return _targeted_failure(thread_id, run_id, error.step, error)
    except Exception as error:
        return _targeted_failure(thread_id, run_id, "targeted", error)


def run_targeted_estimate(
    args: Any, *, action_id: int, event_key: str, thread_id: str,
    expected_revision: int, evidence: Path, run_id: str,
) -> dict[str, Any]:
    """Refresh one durable estimate thread and consume only its current decision."""
    try:
        binding = _durable_event_action(Path(args.database), event_key, thread_id)
        if (
            binding is None or int(binding.get("action_id") or 0) != action_id
            or int(binding.get("revision") or 0) != expected_revision
            or binding.get("state") not in {"pending", "reconcile_pending"}
        ):
            return _targeted_pending(thread_id, run_id, error="estimate_binding_changed")
        evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
        _orders, fences_path = _collect_fresh_orders_and_fence(args, evidence=evidence)
        if _paid_fence_open_for_thread(fences_path, thread_id):
            closed = _close_paid_handoff(
                Path(args.database), Path(args.manifest), fences_path, thread_id,
            )
            return {
                "status": "paid_handoff", "thread_id": thread_id, "run_id": run_id,
                "estimate_required": 0, "estimate_effect": 0, "estimate_readback": 0,
                "estimate_pending": 0, "estimate_failed": 0, "estimate_events": [],
                "closed_without_send": len(closed), "pending": 0, "errors": [],
                "closed_action_ids": [row["action_id"] for row in closed],
            }
        snapshot_path = evidence / "marketplace-snapshot.json"
        command = [
            sys.executable, str(args.snapshot_script), "--output", str(snapshot_path),
            "--evidence-dir", str(evidence / "direct-thread"), "--mode", "direct-thread-head-only",
            "--talkroom-id", thread_id, "--hidden-no-screenshot",
        ]
        _run("collect", command)
        _owner_only(snapshot_path)
        snapshot = _targeted_snapshot(snapshot_path)
        if binding.get("state") == "reconcile_pending":
            reconcile_snapshot = dict(snapshot)
            reconcile_snapshot.update({
                "collector_mode": "direct-thread-only", "semantic_ssot": True,
                "head_only": False,
            })
            return run_requested_estimate(
                reconcile_snapshot, args=argparse.Namespace(
                    database=Path(args.database), manifest=Path(args.manifest),
                    runner=Path(args.runner), estimate_schema=Path(args.estimate_schema),
                    cdp_helper=Path(args.cdp_helper),
                ),
                owner=f"gig-estimate-targeted-{run_id}", now=int(time.time()),
                target_action_id=action_id,
            )
        retry_snapshot = _retry_estimate_snapshot(
            Path(args.database), binding, event_key, snapshot, thread_id,
        )
        if retry_snapshot is None:
            command[command.index("direct-thread-head-only")] = "direct-thread-only"
            command.extend([
                "--semantic-runner", str(args.runner), "--semantic-schema", str(args.semantic_schema),
                "--semantic-workdir", str(Path.home()), "--database", str(args.database),
                "--manifest", str(args.manifest), "--semantic-effects-enabled",
            ])
            _run("collect_semantic", command)
            snapshot = _targeted_snapshot(snapshot_path)
        else:
            snapshot = retry_snapshot
        inquiry = _targeted_inquiry(snapshot, thread_id)
        if not (
            inquiry.get("estimate_required") is True
            or str(inquiry.get("next_action") or "") in _TARGETED_ESTIMATE_ACTIONS
        ):
            closed = _targeted_close_obsolete_estimate(
                database=Path(args.database), manifest=Path(args.manifest),
                action_id=action_id, thread_id=thread_id, event_key=event_key,
                expected_revision=expected_revision, run_id=run_id,
            )
            if closed is None:
                return _targeted_pending(
                    thread_id, run_id, error="obsolete_estimate_close_raced",
                )
            return {
                "status": "completed", "thread_id": thread_id, "run_id": run_id,
                "estimate_required": 0, "estimate_effect": 0,
                "estimate_readback": 0, "estimate_pending": 0,
                "estimate_failed": 0, "estimate_events": [],
                "closed_without_send": 1, "pending": 0, "errors": [],
                "closed_action_ids": [closed["action_id"]],
            }
        return _run_effect_pipeline(
            args, snapshot=snapshot, evidence=evidence, run_id=run_id,
        )
    except StepFailure as error:
        return _targeted_failure(thread_id, run_id, error.step, error)
    except Exception as error:
        return _targeted_failure(thread_id, run_id, "targeted_estimate", error)


def run_targeted_reconcile(
    args: Any, *, action_id: int, thread_id: str, expected_revision: int,
    evidence: Path, run_id: str,
) -> dict[str, Any]:
    """Read back one delivery-unknown reply without scanning every inbox page."""
    try:
        evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
        _orders, fences_path = _collect_fresh_orders_and_fence(args, evidence=evidence)
        if _paid_fence_open_for_thread(fences_path, thread_id):
            closed = _close_paid_handoff(
                Path(args.database), Path(args.manifest), fences_path, thread_id,
            )
            return {
                "status": "paid_handoff", "thread_id": thread_id, "run_id": run_id,
                "replied": 0, "official_readback": 0, "closed_without_send": len(closed),
                "pending": 0, "events": [], "errors": [],
            }
        queue_path = evidence / "reply-queue.json"
        lane_path = evidence / "reply-lane-result.json"
        _atomic_json(queue_path, {
            "status": "queue_empty", "items": [], "semantic_ssot": True,
        })
        _run("reply_reconcile", [
            sys.executable, str(args.lane_script), "--queue", str(queue_path),
            "--database", str(args.database), "--manifest", str(args.manifest),
            "--runner", str(args.runner), "--schema", str(args.schema),
            "--cdp-helper", str(args.cdp_helper), "--max-model-calls", "0",
            "--target-action-id", str(action_id), "--output", str(lane_path),
            "--workdir", str(Path.home()), "--owner-prefix", f"gig-reconcile-{run_id}",
            "--fences", str(fences_path),
        ], accepted=(0, 2))
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        result = _targeted_effect_result(
            lane, thread_id=thread_id, action_id=action_id,
            expected_revision=expected_revision,
        )
        result["run_id"] = run_id
        if result.get("status") in {"completed", "replied"}:
            ConnectorOutbox(Path(args.database), Path(args.manifest)).revive_blocked_actions(
                now=int(time.time()),
            )
        return result
    except StepFailure as error:
        return _targeted_failure(thread_id, run_id, error.step, error)
    except Exception as error:
        return _targeted_failure(thread_id, run_id, "targeted_reconcile", error)


async def _supervisor_hook(hook: Any, *arguments: Any) -> Any:
    """Invoke a testable supervisor hook whether it is sync or async."""
    result = hook(*arguments)
    return await result if inspect.isawaitable(result) else result


def _supervisor_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("inquiries")
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _supervisor_work_from_action(action: dict[str, Any]) -> dict[str, Any] | None:
    event_key = str(action.get("event_key") or "")
    thread_id = str(action.get("thread_id") or "")
    action_id = _count(action.get("action_id"))
    expected_revision = _count(action.get("revision"))
    match = _INBOX_EVENT.fullmatch(event_key)
    if (
        match is None or match.group("thread") != thread_id
        or action_id is None or action_id <= 0
        or expected_revision is None or expected_revision <= 0
    ):
        return None
    return {
        "kind": "reply",
        "action_id": action_id,
        "event_key": event_key,
        "thread_id": thread_id,
        "identity_sha256": match.group("identity"),
        "expected_revision": expected_revision,
    }


def _supervisor_estimate_work_from_action(action: dict[str, Any]) -> dict[str, Any] | None:
    event_key = str(action.get("event_key") or "")
    thread_id = str(action.get("thread_id") or "")
    action_id = _count(action.get("action_id"))
    expected_revision = _count(action.get("revision"))
    try:
        _requested_estimate_module().validate_estimate_event_key(event_key, thread_id)
    except Exception:
        return None
    if action_id is None or action_id <= 0 or expected_revision is None or expected_revision <= 0:
        return None
    return {
        "kind": "estimate", "action_id": action_id, "event_key": event_key,
        "thread_id": thread_id, "expected_revision": expected_revision,
    }


def _supervisor_reconcile_work_from_action(action: dict[str, Any]) -> dict[str, Any] | None:
    action_id = _count(action.get("action_id"))
    thread_id = str(action.get("thread_id") or "")
    event_key = str(action.get("event_key") or "")
    if (
        action_id is None or action_id <= 0
        or _TARGETED_THREAD_ID.fullmatch(thread_id) is None
        or not event_key
    ):
        return None
    return {
        "kind": "reconcile", "action_id": action_id,
        "event_key": event_key, "thread_id": thread_id,
        "expected_revision": int(action["revision"]),
    }


def _supervisor_blocked_work_from_action(action: dict[str, Any]) -> dict[str, Any] | None:
    work = _supervisor_work_from_action(action)
    if work is not None:
        work["kind"] = "blocked"
    return work


def run_blocked_probe(args: Any, work: dict[str, Any], evidence: Path) -> dict[str, Any]:
    """Requeue a sending-unavailable reply only after a fresh official head proof."""
    row = _collect_targeted_head(
        args, evidence=evidence, thread_id=str(work["thread_id"]),
        identity_sha256=str(work["identity_sha256"]),
    )
    if row.get("sending_unavailable") is not False:
        return {"status": "blocked", "thread_id": work["thread_id"], "pending": 0}
    stored = ConnectorOutbox(Path(args.database), Path(args.manifest)).revive_sending_available(
        int(work["action_id"]), expected_revision=int(work["expected_revision"]),
        now=int(time.time()),
    )
    return {
        "status": "revived", "thread_id": work["thread_id"],
        "action_id": int(stored["action_id"]), "revision": int(stored["revision"]),
        "pending": 1,
    }


def _supervisor_rebind_targeted_work(
    outbox: ConnectorOutbox, work: dict[str, Any], result: Any, *, now: int,
) -> dict[str, Any] | None:
    """Bind a stale inbox action to the exact buyer event just read from the thread."""
    if not isinstance(result, dict) or "targeted_inbox_identity_changed" not in set(
        str(error) for error in (result.get("errors") or [])
    ):
        return None
    thread_id = str(work.get("thread_id") or "")
    identity = str(result.get("current_identity_sha256") or "")
    if (
        _TARGETED_THREAD_ID.fullmatch(thread_id) is None
        or re.fullmatch(r"[0-9a-f]{64}", identity) is None
    ):
        return None
    side = str(result.get("current_last_message_side") or "")
    event_key = coconala_inbox_event_key(thread_id, identity)
    thread_url = f"https://coconala.com/mypage/direct_message/{thread_id}"
    if side in {"buyer", ""}:
        # The cheap direct-inbox-head collector does not always expose the
        # sender side (it can be null while still returning a fresh identity).
        # Rebind that exact identity and let the authoritative direct-thread
        # read decide whether it is buyer-actionable; an unknown side is never
        # itself treated as permission to send.
        action = outbox.enqueue(
            event_key=event_key, thread_id=thread_id,
            thread_url=thread_url, observed_at=now,
        )
        if action.get("state") != "pending":
            return None
        return {
            "action_id": int(action["action_id"]),
            "event_key": event_key, "thread_id": thread_id,
            "identity_sha256": identity,
            "expected_revision": int(action["revision"]),
        }
    if side != "seller":
        return None
    try:
        action = outbox.get_action(int(work["action_id"]))
    except Exception:
        return None
    if action.get("state") != "pending" or action.get("dlq_at") is not None:
        return None
    expected_revision = _count(work.get("expected_revision"))
    if expected_revision is None or expected_revision <= 0:
        return None
    _targeted_close_no_send(
        database=outbox.database, manifest=outbox.manifest_path,
        action_id=int(work["action_id"]), thread_id=thread_id,
        inbox_event_key=str(work["event_key"]),
        expected_revision=expected_revision,
        reason="targeted_identity_superseded_seller_last", run_id=f"rebind-{now}",
    )
    return None


async def supervise_replies(
    args: Any, *, probe: Any, worker: Any, reconcile: Any, stop: Any,
    report_root: Path | None = None, report: Any | None = None,
) -> None:
    """Supervise one producer, two consumers, and idle reconciliation.

    SQLite is the durable queue.  The in-memory queue only dispatches exact
    ``action_id``/event/identity tuples and is rebuilt from pending actions on
    every producer pass, so a process restart cannot lose a claimed inquiry.
    """
    poll_seconds = float(getattr(args, "poll_seconds", 30) or 30)
    worker_count = int(getattr(args, "workers", 2) or 2)
    reconcile_seconds = float(getattr(args, "reconcile_seconds", 300) or 300)
    if not 0 < poll_seconds <= 30:
        raise ValueError("poll_seconds must be in (0, 30]")
    if worker_count != 2:
        raise ValueError("supervisor requires exactly two workers")
    if reconcile_seconds <= 0:
        raise ValueError("reconcile_seconds must be positive")
    if not hasattr(stop, "is_set") or not hasattr(stop, "wait"):
        raise TypeError("stop must be an asyncio.Event-like object")

    database = Path(getattr(args, "database"))
    manifest = Path(getattr(args, "manifest"))
    report_root = Path(report_root) if report_root is not None else database.parent
    outbox: ConnectorOutbox | None = None

    def get_outbox() -> ConnectorOutbox:
        nonlocal outbox
        if outbox is None:
            outbox = ConnectorOutbox(database, manifest)
        return outbox

    def headroom_available() -> bool:
        try:
            return bool(disk_headroom_ok())
        except Exception:
            return False

    dispatch: asyncio.PriorityQueue[tuple[int, int, dict[str, Any]]] = asyncio.PriorityQueue()
    sequence = itertools.count()
    in_flight: set[str] = set()

    async def report_policy(path: Path, result: dict[str, Any]) -> None:
        if report is None:
            _atomic_json(path, result)
            return
        await report(path, result)

    async def enqueue_work(work: dict[str, Any]) -> None:
        if stop.is_set():
            return
        event_key = work["event_key"]
        if event_key in in_flight:
            return
        lifecycle = get_outbox().action_lifecycle_for_event(event_key, work["thread_id"])
        allowed_states = (
            {"pending", "reconcile_pending"} if work.get("kind") == "estimate"
            else {"reconcile_pending"} if work.get("kind") == "reconcile"
            else {"blocked"} if work.get("kind") == "blocked"
            else {"pending"}
        )
        if lifecycle is not None and lifecycle.get("state") not in allowed_states:
            return
        in_flight.add(event_key)
        await dispatch.put((0 if work.get("kind") in {"estimate", "reconcile"} else 1, next(sequence), work))

    async def enqueue_head_rows(rows: list[dict[str, Any]]) -> None:
        outbox = get_outbox()
        policy = partition_no_contact_rows(
            rows, registry_path=Path(args.no_contact_registry),
            outbox=outbox, now=int(time.time()),
        )
        for ignored in policy["ignored"]:
            result = no_contact_report(ignored, now=int(time.time()))
            report_dir = report_root / "continuous" / "policy-reports" / result["run_id"]
            await report_policy(report_dir / "result.json", result)
        for row in policy["available"]:
            thread_id = str(row.get("talkroom_id") or "")
            identity = str(row.get("last_message_identity_sha256") or "")
            if (
                _TARGETED_THREAD_ID.fullmatch(thread_id) is None
                or not re.fullmatch(r"[0-9a-f]{64}", identity)
            ):
                continue
            event_key = coconala_inbox_event_key(thread_id, identity)
            try:
                # Persist the observation only. enqueue_pending_actions() runs
                # next and dispatches the newest durable identity for the action.
                outbox.enqueue(
                    event_key=event_key, thread_id=thread_id,
                    thread_url=str(row.get("talkroom_url") or ""),
                    observed_at=int(time.time()),
                )
            except Exception:
                continue

    async def enqueue_pending_actions() -> None:
        # The direct supervisor must consume an exact inbox identity.  A
        # fallback detector can append a later fallback event to the same
        # durable action, so use the outbox's inbox-only projection here rather
        # than allowing that fallback row to hide the target.
        estimate_actions = (
            get_outbox().estimate_reconciliation_actions()
            + get_outbox().estimate_pending_actions()
        )
        for action in estimate_actions:
            work = _supervisor_estimate_work_from_action(action)
            if work is not None:
                await enqueue_work(work)
        for action in get_outbox().reconciliation_actions():
            work = _supervisor_reconcile_work_from_action(action)
            if work is not None:
                await enqueue_work(work)
        for action in get_outbox().pending_targeted_actions():
            work = _supervisor_work_from_action(action)
            if work is not None:
                await enqueue_work(work)
        for action in get_outbox().blocked_targeted_actions():
            work = _supervisor_blocked_work_from_action(action)
            if work is not None:
                await enqueue_work(work)

    async def producer() -> None:
        next_probe_at = time.monotonic()
        immediate_after_overrun = False
        while not stop.is_set():
            remaining = next_probe_at - time.monotonic()
            if remaining > 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass
                if stop.is_set():
                    break
            if headroom_available():
                try:
                    observed = await _supervisor_hook(probe)
                    if headroom_available():
                        await enqueue_head_rows(_supervisor_rows(observed))
                except Exception:
                    # A transient probe failure leaves durable pending rows for the
                    # same pass; it must not tear down the supervised consumers.
                    pass
                if headroom_available():
                    await enqueue_pending_actions()
            now = time.monotonic()
            if immediate_after_overrun:
                # One overdue pass is allowed to start immediately.  Reset the
                # deadline after that pass so a slow probe cannot cause a
                # catch-up storm of back-to-back producer calls.
                next_probe_at = now + poll_seconds
                immediate_after_overrun = False
            else:
                next_probe_at += poll_seconds
                if next_probe_at < now:
                    next_probe_at = now
                    immediate_after_overrun = True

    async def consumer() -> None:
        # Durable work is rebuilt from SQLite after a restart.  On shutdown,
        # finish only the item already owned by this consumer; do not make a
        # release wait for the whole in-memory backlog.
        while not stop.is_set():
            try:
                _, _, work = await asyncio.wait_for(dispatch.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            try:
                if headroom_available():
                    ignored = close_no_contact_work(
                        work, registry_path=Path(args.no_contact_registry),
                        outbox=get_outbox(), now=int(time.time()),
                    )
                    if ignored is not None:
                        result = no_contact_report(ignored, now=int(time.time()))
                        report_dir = evidence / "continuous" / "policy-reports" / result["run_id"]
                        await report_policy(report_dir / "result.json", result)
                    else:
                        result = await _supervisor_hook(worker, work)
                    if headroom_available():
                        try:
                            rebound = _supervisor_rebind_targeted_work(
                                get_outbox(), work, result, now=int(time.time()),
                            )
                            if rebound is not None:
                                await enqueue_work(rebound)
                        except Exception:
                            # A failed rebind leaves the original durable action pending;
                            # the next producer pass will retry with the same exact event.
                            pass
            except Exception:
                pass
            finally:
                in_flight.discard(work["event_key"])
                dispatch.task_done()

    async def reconciler() -> None:
        delay = min(poll_seconds, reconcile_seconds)
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                if headroom_available():
                    try:
                        await _supervisor_hook(reconcile)
                        delay = reconcile_seconds
                    except Exception:
                        delay = min(poll_seconds, reconcile_seconds)

    producer_task = asyncio.create_task(producer(), name="gig-reply-producer")
    consumer_tasks = [
        asyncio.create_task(consumer(), name=f"gig-reply-consumer-{index}")
        for index in range(worker_count)
    ]
    reconcile_task = asyncio.create_task(reconciler(), name="gig-reply-reconciler")
    try:
        await producer_task
    finally:
        stop.set()
        while True:
            try:
                _, _, queued = dispatch.get_nowait()
            except asyncio.QueueEmpty:
                break
            in_flight.discard(queued["event_key"])
            dispatch.task_done()
        await dispatch.join()
        await asyncio.gather(*consumer_tasks, reconcile_task, return_exceptions=True)


def _run_reconciliation_once(args: Any, evidence: Path) -> dict[str, Any]:
    """Run the existing full four-page pass when urgent work is idle."""
    run_id = f"reconcile-{int(time.time())}-{os.getpid()}"
    run_evidence = evidence / "reconciliation" / run_id
    run_evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    snapshot = run_evidence / "marketplace-snapshot.json"
    attempts = _collect_snapshot_with_retry(args, snapshot, run_evidence)
    _owner_only(snapshot)
    snapshot_value = _targeted_snapshot(snapshot)
    terminal_cleanup = close_officially_unrepliable_pending(
        snapshot_value, database=args.database, manifest=args.manifest,
        owner=f"gig-reply-terminal-{run_id}", now=int(time.time()),
    )
    _atomic_json(run_evidence / "terminal-action-cleanup.json", terminal_cleanup)
    pipeline = _run_effect_pipeline(
        args, snapshot=snapshot_value, evidence=run_evidence, run_id=run_id,
    )
    pipeline["collect_attempts"] = len(attempts)
    return pipeline


async def _run_continuous_runtime(args: Any, evidence: Path) -> dict[str, Any]:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    probe_number = 0
    report_queue: asyncio.Queue[tuple[Path, dict[str, Any]]] = asyncio.Queue()
    reporter_done = asyncio.Event()

    async def enqueue_report(path: Path, result: dict[str, Any]) -> None:
        # A stale supervisor work item can lose its binding before the worker
        # opens it.  That is neither a buyer outcome nor a lane failure; the
        # reconciliation health report remains the owner-visible idle signal.
        if result.get("status") == "already_closed":
            _atomic_json(path, result)
            return
        await report_queue.put((path, result))

    async def reporter() -> None:
        # The shutdown signal stops new dispatch, but active workers can still
        # enqueue their terminal report.  Stay alive until the supervisor has
        # returned and every such report has been persisted.
        while not reporter_done.is_set() or not report_queue.empty():
            try:
                path, result = await asyncio.wait_for(report_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            try:
                await asyncio.to_thread(
                    _persist_continuous_worker_report, args, path, result,
                )
                await asyncio.to_thread(_prune_continuous_evidence, evidence)
            finally:
                report_queue.task_done()

    async def probe() -> dict[str, Any]:
        nonlocal probe_number
        probe_number += 1
        probe_evidence = evidence / "continuous" / f"probe-{probe_number}"
        result = await asyncio.to_thread(_collect_head_snapshot, args, probe_evidence)
        await asyncio.to_thread(_prune_continuous_evidence, evidence)
        return result

    async def worker(work: dict[str, Any]) -> dict[str, Any]:
        run_id = f"targeted-{int(time.time())}-{os.getpid()}-{work['action_id']}"
        worker_evidence = evidence / "continuous" / "workers" / run_id
        if work.get("kind") == "blocked":
            result = await asyncio.to_thread(run_blocked_probe, args, work, worker_evidence)
            await enqueue_report(worker_evidence / "result.json", result)
            return result
        if work.get("kind") == "estimate":
            result = await asyncio.to_thread(
                run_targeted_estimate, args,
                action_id=int(work["action_id"]), event_key=str(work["event_key"]),
                thread_id=str(work["thread_id"]),
                expected_revision=int(work["expected_revision"]),
                evidence=worker_evidence, run_id=run_id,
            )
            await enqueue_report(worker_evidence / "result.json", result)
            return result
        if work.get("kind") == "reconcile":
            result = await asyncio.to_thread(
                run_targeted_reconcile, args,
                action_id=int(work["action_id"]), thread_id=str(work["thread_id"]),
                expected_revision=int(work["expected_revision"]),
                evidence=worker_evidence, run_id=run_id,
            )
            await enqueue_report(worker_evidence / "result.json", result)
            return result
        result = await asyncio.to_thread(
            run_targeted_thread, args,
            action_id=int(work["action_id"]),
            inbox_event_key=str(work["event_key"]),
            thread_id=str(work["thread_id"]),
            evidence=worker_evidence,
            run_id=run_id,
        )
        await enqueue_report(worker_evidence / "result.json", result)
        return result

    async def reconcile() -> dict[str, Any]:
        result = await asyncio.to_thread(_run_reconciliation_once, args, evidence)
        run_id = str(result.get("run_id") or f"reconcile-{int(time.time())}")
        report_dir = evidence / "continuous" / "reconciliation-reports" / run_id
        report_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        await report_queue.put((report_dir / "result.json", result))
        return result

    reporter_task = asyncio.create_task(reporter(), name="gig-reply-reporter")
    try:
        await supervise_replies(
            args, probe=probe, worker=worker, reconcile=reconcile, stop=stop,
            report_root=evidence, report=enqueue_report,
        )
    finally:
        for signum in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.remove_signal_handler(signum)
            except (NotImplementedError, RuntimeError):
                pass
        stop.set()
        await report_queue.join()
        reporter_done.set()
        await reporter_task
    return {"status": "stopped", "workers": 2, "poll_seconds": args.poll_seconds}


def main() -> int:
    gig_root = Path(__file__).resolve().parents[1]
    home = Path.home()
    install_token_budget(os.environ, run_id=f"reply-detector-{int(time.time())}-{os.getpid()}")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", choices=("fallback", "gmail_push", "manual"), default="fallback")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=30)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--reconcile-seconds", type=float, default=300)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lock-file", type=Path, default=home / "gig/reply-detector.lock")
    parser.add_argument("--database", type=Path, default=home / "gig/connector-outbox.sqlite3")
    parser.add_argument("--manifest", type=Path, default=gig_root / "config/connectors/coconala.json")
    parser.add_argument(
        "--runner", type=Path,
        default=RUNNER_DIR / "agent_runner.py",
    )
    parser.add_argument("--schema", type=Path, default=gig_root / "schemas/reply_composition.schema.json")
    parser.add_argument(
        "--semantic-schema", type=Path,
        default=gig_root / "schemas/reply_semantic_judgement.schema.json",
    )
    parser.add_argument(
        "--semantic-effects-enabled", action=argparse.BooleanOptionalAction, default=True,
    )
    parser.add_argument("--estimate-schema", type=Path, default=gig_root / "schemas/estimate_category_selection.schema.json")
    parser.add_argument(
        "--cdp-helper", type=Path,
        default=BROWSER_DIR / "scripts" / "cdp_default_tab.py",
    )
    parser.add_argument("--snapshot-script", type=Path, default=gig_root / "scripts/coconala_queue_snapshot.py")
    parser.add_argument("--queue-script", type=Path, default=gig_root / "scripts/reply_queue.py")
    parser.add_argument("--lane-script", type=Path, default=gig_root / "scripts/reply_lane.py")
    parser.add_argument(
        "--fence-script", type=Path, default=gig_root / "scripts/project_effect_fence.py",
    )
    parser.add_argument(
        "--telegram-report-script", type=Path,
        default=gig_root / "scripts/telegram_report.py",
    )
    parser.add_argument(
        "--telegram-database", type=Path,
        default=home / "gig/telegram-outbox.sqlite3",
    )
    parser.add_argument(
        "--no-contact-registry", type=Path,
        default=Path(os.environ.get(
            "GIG_NO_CONTACT_REGISTRY",
            home / ".config/anicca/gig/no-contact.json",
        )),
    )
    parser.add_argument(
        "--runner-config", type=Path,
        default=RUNNER_DIR / "config.json",
    )
    parser.add_argument("--telegram-target", default=os.environ.get("GIG_REPORT_CHAT", ""))
    args = parser.parse_args()

    os.environ["CLOAK_BROWSER_OWNER"] = "gig-reply-detector"
    run_id = f"{int(time.time())}-{os.getpid()}"
    evidence = args.evidence_dir or home / f"gig/evidence/reply-detector-{run_id}"
    output = args.output or evidence / "detector-result.json"
    try:
        evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
        evidence.chmod(0o700)
    except Exception as error:
        failure = {
            **_wake_result(run_id=run_id, trigger=args.trigger, status="failed"),
            "failed_step": "evidence",
            "errors": [{"type": type(error).__name__, "message": str(error)[:300]}],
        }
        _persist_wake_report(args, output, failure)
        print(json.dumps(failure, ensure_ascii=False, separators=(",", ":")))
        return 1
    lock_fd: int | None = None
    lock_handle = None
    try:
        try:
            args.lock_file.parent.mkdir(parents=True, exist_ok=True)
            lock_fd = os.open(args.lock_file, os.O_CREAT | os.O_RDWR, 0o600)
            os.fchmod(lock_fd, 0o600)
            lock_handle = os.fdopen(lock_fd, "r+")
            lock_fd = None
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            busy = _wake_result(
                run_id=run_id, trigger=args.trigger, status="busy",
            )
            busy["errors"] = []
            _persist_wake_report(args, output, busy)
            print(json.dumps(busy, ensure_ascii=False, separators=(",", ":")))
            return 0
        except Exception as error:
            failure = {
                **_wake_result(
                    run_id=run_id, trigger=args.trigger, status="failed",
                ),
                "failed_step": "lock",
                "errors": [{"type": type(error).__name__, "message": str(error)[:300]}],
            }
            _persist_wake_report(args, output, failure)
            print(json.dumps(failure, ensure_ascii=False, separators=(",", ":")))
            return 1

        brake_status = _operator_brake_status()
        if brake_status == "held":
            operator_brake = {
                **_wake_result(
                    run_id=run_id, trigger=args.trigger, status="operator_brake",
                ),
                "errors": [],
            }
            _persist_wake_report(args, output, operator_brake)
            print(json.dumps(operator_brake, ensure_ascii=False, separators=(",", ":")))
            return 0
        if brake_status == "failed":
            failure = {
                **_wake_result(
                    run_id=run_id, trigger=args.trigger, status="failed",
                ),
                "failed_step": "operator_brake",
                "errors": [{"code": "operator_brake_check_failed"}],
            }
            _persist_wake_report(args, output, failure)
            print(json.dumps(failure, ensure_ascii=False, separators=(",", ":")))
            return 1

        if args.continuous:
            try:
                continuous = asyncio.run(_run_continuous_runtime(args, evidence))
                continuous.update({"run_id": run_id, "trigger": args.trigger})
                _atomic_json(output, continuous)
                print(json.dumps(continuous, ensure_ascii=False, separators=(",", ":")))
                return 0
            except Exception as error:
                failure = {
                    **_wake_result(
                        run_id=run_id, trigger=args.trigger, status="failed",
                    ),
                    "failed_step": "continuous",
                    "errors": [{"type": type(error).__name__, "message": str(error)[:300]}],
                }
                _persist_wake_report(args, output, failure)
                print(json.dumps(failure, ensure_ascii=False, separators=(",", ":")))
                return 1

        snapshot = evidence / "marketplace-snapshot.json"
        queue = evidence / "reply-queue.json"
        lane_result = evidence / "reply-lane-result.json"
        try:
            collect_attempts = _collect_snapshot_with_retry(args, snapshot, evidence)
            _owner_only(snapshot)
            snapshot_value = json.loads(snapshot.read_text(encoding="utf-8"))
            terminal_cleanup = close_officially_unrepliable_pending(
                snapshot_value, database=args.database, manifest=args.manifest,
                owner=f"gig-reply-terminal-{run_id}", now=int(time.time()),
            )
            _atomic_json(evidence / "terminal-action-cleanup.json", terminal_cleanup)
            pipeline = _run_effect_pipeline(
                args, snapshot=snapshot_value, evidence=evidence, run_id=run_id,
            )
            queue_value = json.loads(queue.read_text(encoding="utf-8"))
            dlq_events = pipeline.get("dlq_events")
            result = {
                **pipeline,
                "trigger": args.trigger,
                **_snapshot_terminal_counts(snapshot_value),
                **_snapshot_activity_counts(snapshot_value),
                "observed": (
                    len(snapshot_value["inquiries"])
                    if isinstance(snapshot_value, dict)
                    and isinstance(snapshot_value.get("inquiries"), list)
                    else None
                ),
                "actionable": (
                    len(queue_value["items"])
                    if isinstance(queue_value, dict)
                    and isinstance(queue_value.get("items"), list)
                    else None
                ),
                "oldest_actionable": _oldest_actionable(
                    queue_value.get("items") if isinstance(queue_value, dict) else None
                ),
                "historical_dlq": None,
                "newly_dlq": len(dlq_events) if isinstance(dlq_events, list) else None,
                "next_wake": None,
                "collect_attempts": len(collect_attempts),
                "collect_recovered": len(collect_attempts) > 1,
            }
            _persist_wake_report(args, output, result)
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
            return 0 if result["status"] == "completed" else 1
        except StepFailure as error:
            failure = {
                **_wake_result(
                    run_id=run_id, trigger=args.trigger, status="failed",
                ),
                "failed_step": error.step,
                "errors": [{"returncode": error.returncode}],
            }
            if error.step == "collect":
                failure.update({
                    "effect": 0, "official_readback": 0, "pending": 0,
                    "estimate_effect": 0, "estimate_readback": 0,
                    "estimate_pending": 0, "estimate_failed": 0,
                })
                failure["collect_attempts"] = len(error.attempts)
                failure["collect_recovered"] = False
                failure["collect_attempt_receipts"] = error.attempts
            _persist_wake_report(args, output, failure)
            print(json.dumps(failure, ensure_ascii=False, separators=(",", ":")))
            return 1
        except Exception as error:
            failure = {
                **_wake_result(
                    run_id=run_id, trigger=args.trigger, status="failed",
                ),
                "failed_step": "internal",
                "errors": [{"type": type(error).__name__, "message": str(error)[:300]}],
            }
            _persist_wake_report(args, output, failure)
            print(json.dumps(failure, ensure_ascii=False, separators=(",", ":")))
            return 1
    finally:
        if lock_handle is not None:
            lock_handle.close()
        elif lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
