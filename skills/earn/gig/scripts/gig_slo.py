#!/usr/bin/env python3
"""Pure SLO evaluation for the gig-work control plane.

The collector and repair executor intentionally live elsewhere.  Keeping this
module pure makes every alert fingerprint deterministic and independently
testable before it is allowed to trigger a repair.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PASS_SILENCE_SECONDS = 2 * 60 * 60
LANE_ATTEMPT_SILENCE_SECONDS = 2 * 60 * 60
PRODUCTIVE_SILENCE_BARREN_STREAK = 3
RECENT_FAILURE_SECONDS = 2 * 60 * 60
TELEGRAM_REPORT_SILENCE_SECONDS = 2 * 60 * 60
TELEGRAM_BACKLOG_SECONDS = 15 * 60
REVENUE_LANES = ("apply", "reply", "fulfill", "list")
HERMES_AUDIT_LANES = ("paid", "reply", "apply", "storefront")
RUNTIME_LANES = {
    "apply": ("apply", "hf-gig-apply-direct"),
    "reply": ("reply", "hf-gig-reply-detector"),
    "fulfill": ("paid", "hf-gig-paid-direct"),
    "list": ("storefront", "hf-gig-storefront-direct"),
}
TELEGRAM_HEALTH_REPORT_KINDS = (
    "pass", "hourly", "daily", "weekly", "application", "application_recovery",
    "apply-direct", "apply-decision", "reply_wake", "reply_verified", "reply_dlq",
    "paid-direct", "contract", "delivery", "payment", "storefront_direct_effect",
    "storefront_direct_failure", "storefront_direct_noop", "storefront_public_effect",
)


def _default_host_state_dir() -> Path:
    return Path(os.environ.get(
        "GIG_HOST_STATE_DIR", str(Path.home() / ".local" / "state" / "life-manager" / "state")
    ))


def _incident(
    fingerprint: str,
    *,
    repair_class: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "fingerprint": fingerprint,
        "repair_class": repair_class,
        "evidence": evidence,
    }


def browser_repair_for_parent_failure(evidence_dir) -> bool:
    """True when a B2 parent failure was a CDP call that never answered.

    gig_healer already knows how to fix a wedged browser and gig_slo already raises that
    repair — but only for browser_cdp_unavailable and live_queue_snapshot_failed. The failure
    the loop actually produces is b2_parent_boundary_failed, and since 2026-08-05 it carries a
    precise cause: cdp_Page.enable_timeout_after_30s. Page.enable is the first call after
    connecting, so a timeout on it is not a slow page, it is a target that cannot answer.
    Nothing routed that to browser_restart, so the browser stayed wedged and B2 failed every
    hour while the repair that would have fixed it was never asked for.

    Deliberately narrow. A planner contract violation or a quota failure must not restart the
    shared browser: that would hide a real defect behind an infrastructure remedy and cost a
    session every hour. Absence of a recorded error is not evidence of a wedged browser either.
    """
    path = Path(evidence_dir) / "agent-B2" / "parent-error.json"
    try:
        error = str(json.loads(path.read_text(encoding="utf-8")).get("error") or "")
    except (OSError, ValueError):
        return False
    return error.startswith("cdp_") and "timeout" in error


def _hermes_count(value: Any, *, minimum: int = 0) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = int(value)
    return number if number >= minimum else None


def _hermes_audit_incidents(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    audit = snapshot.get("hermes_audit")
    if (
        not isinstance(audit, dict)
        or audit.get("phase") != "terminal"
        or audit.get("verdict") != "RED"
        or not str(audit.get("audit_id") or "")
    ):
        return []
    since, until = audit.get("since"), audit.get("until")
    if (
        isinstance(since, bool) or isinstance(until, bool)
        or not isinstance(since, int) or not isinstance(until, int)
        or not 0 <= since < until or audit.get("audit_id") != f"{since}-{until}"
    ):
        return []
    result = audit.get("result")
    if (
        not isinstance(result, dict)
        or result.get("version") != 1
        or result.get("window_complete") is not True
        or result.get("verdict") != "RED"
        or result.get("since") != since or result.get("until") != until
    ):
        return []
    invariants = result.get("invariants")
    if not isinstance(invariants, dict):
        return []
    lanes = result.get("lanes")
    lanes = lanes if isinstance(lanes, dict) else {}
    audit_id = str(audit["audit_id"])
    baseline = {"audit_id": audit_id, "since": _hermes_count(audit.get("since")), "until": _hermes_count(audit.get("until"))}
    incidents: list[dict[str, Any]] = []
    def add(lane: str, cause: str, count: int) -> None:
        incidents.append(_incident(
            f"hermes24:{audit_id}:{lane}:{cause}", repair_class="task_diagnose",
            evidence={**baseline, "lane": lane, "cause": cause, "count": count},
        ))

    lane_causes = (
        ("no_missing_due", "missing_slots", "missing_slots"),
        ("no_bad_receipts", "nonzero_or_invalid_receipts", "invalid_receipts"),
        ("no_blocked_tasks", "blocked", "blocked_tasks"),
        ("no_stale_active", "stale_active", "stale_active"),
    )
    for lane in HERMES_AUDIT_LANES:
        metrics = lanes.get(lane) if isinstance(lanes.get(lane), dict) else {}
        for invariant, metric, cause in lane_causes:
            count = _hermes_count(metrics.get(metric), minimum=1)
            if invariants.get(invariant) is False and count is not None:
                add(lane, cause, count)
        if invariants.get("all_lanes_nonstarved") is False:
            executed = _hermes_count(metrics.get("executed"))
            expected = _hermes_count(metrics.get("expected_due"), minimum=1)
            if executed == 0 and expected is not None:
                add(lane, "nonstarved", expected)

    for invariant, section, field, lane, cause in (
        ("no_duplicate_applications", "applications", "duplicate_request_ids", "apply", "duplicate_applications"),
        ("all_applications_reported", "telegram", "unreported_application_ids", "apply", "unreported_applications"),
        ("no_excess_storefront_effects", "storefront", "effect_count", "storefront", "excess_storefront_effects"),
    ):
        if invariants.get(invariant) is not False:
            continue
        section_value = result.get(section)
        value = section_value.get(field) if isinstance(section_value, dict) else None
        count = len(value) if isinstance(value, list) else (_hermes_count(value, minimum=1) or 1)
        if cause == "excess_storefront_effects":
            storefront_metrics = lanes.get("storefront") if isinstance(lanes.get("storefront"), dict) else {}
            executed = storefront_metrics.get("executed", 0)
            count = max(1, count - (_hermes_count(executed) or 0))
        add(lane, cause, max(1, count))
    return incidents


def evaluate(snapshot: dict[str, Any], *, now: int) -> list[dict[str, Any]]:
    """Return independently actionable incidents for one bounded snapshot."""
    incidents: list[dict[str, Any]] = _hermes_audit_incidents(snapshot)

    last_pass_at = snapshot.get("last_pass_at")
    if not isinstance(last_pass_at, (int, float)) or now - last_pass_at > PASS_SILENCE_SECONDS:
        incidents.append(
            _incident(
                "scheduler:missed_hourly_pass",
                repair_class="scheduler_restart",
                evidence={"last_pass_at": last_pass_at, "now": now},
            )
        )

    lanes = snapshot.get("lanes") or {}
    for lane in REVENUE_LANES:
        state = lanes.get(lane) or {}
        last_attempt_at = state.get("last_attempt_at")
        if (
            not isinstance(last_attempt_at, (int, float))
            or now - last_attempt_at > LANE_ATTEMPT_SILENCE_SECONDS
        ):
            incidents.append(
                _incident(
                    f"lane:{lane}:attempt_silence",
                    repair_class="lane_probe",
                    evidence={
                        "lane": lane,
                        "last_attempt_at": last_attempt_at,
                        "now": now,
                    },
                )
            )
            continue

        barren_streak = state.get("barren_streak", 0)
        if (
            lane == "apply"
            and
            isinstance(barren_streak, int)
            and barren_streak >= PRODUCTIVE_SILENCE_BARREN_STREAK
        ):
            incidents.append(
                _incident(
                    "application:barren_streak",
                    repair_class="application_expand",
                    evidence={
                        "lane": lane,
                        "barren_streak": barren_streak,
                        "last_productive_at": state.get("last_productive_at"),
                    },
                )
            )

    telegram = snapshot.get("telegram") or {}
    active_unknown = telegram.get("delivery_unknown_active")
    if not isinstance(active_unknown, int):
        active_unknown = int(telegram.get("delivery_unknown", 0) or 0)
    if active_unknown > 0:
        incidents.append(
            _incident(
                "telegram:delivery_unknown",
                repair_class="telegram_reconcile",
                evidence={
                    "latest_pass_state": telegram.get("latest_pass_state"),
                    "delivery_unknown": telegram.get("delivery_unknown", 0),
                    "delivery_unknown_active": active_unknown,
                },
            )
        )
    else:
        latest_report_at = telegram.get("latest_pass_created_at")
        if (
            not isinstance(latest_report_at, (int, float))
            or now - latest_report_at > TELEGRAM_REPORT_SILENCE_SECONDS
        ):
            incidents.append(
                _incident(
                    "telegram:pass_report_silence",
                    repair_class="telegram_probe",
                    evidence={
                        "latest_pass_created_at": latest_report_at,
                        "latest_pass_state": telegram.get("latest_pass_state"),
                    },
                )
            )
        elif (
            telegram.get("latest_pass_state") in {"pending", "claimed", "send_started"}
            and now - latest_report_at > TELEGRAM_BACKLOG_SECONDS
        ):
            incidents.append(
                _incident(
                    "telegram:pass_report_backlog",
                    repair_class="telegram_probe",
                    evidence={
                        "latest_pass_created_at": latest_report_at,
                        "latest_pass_state": telegram.get("latest_pass_state"),
                    },
                )
            )

    seen_failure_fingerprints: set[str] = set()
    for failure in snapshot.get("recent_failures") or []:
        failure_at = failure.get("ts")
        if not isinstance(failure_at, (int, float)):
            continue
        if now - failure_at > RECENT_FAILURE_SECONDS:
            continue
        reason = str(failure.get("reason") or "")
        failed_step = str(failure.get("failed_step") or "unknown")
        fingerprint = ""
        repair_class = ""
        if reason == "b2_parent_boundary_failed" and browser_repair_for_parent_failure(
            str(failure.get("evidence_dir") or "")
        ):
            fingerprint = "browser:cdp_timeout"
            repair_class = "browser_restart"
        elif reason in {"browser_cdp_unavailable", "live_queue_snapshot_failed"}:
            fingerprint = (
                "browser:cdp_unavailable"
                if reason == "browser_cdp_unavailable"
                else "browser:queue_snapshot_unavailable"
            )
            repair_class = "browser_restart"
        elif "schema" in reason:
            fingerprint = f"schema:invalid_result:{failed_step}"
            repair_class = "schema_diagnose"
        elif reason == "paid_work_infra_unavailable":
            fingerprint = "sandbox:infra_unavailable"
            repair_class = "sandbox_recover"
        elif (
            reason == "b2_application_ledger_write_failed"
            and failure.get("ledger_missing_request_ids")
        ):
            fingerprint = f"ledger:application_write_failed:{failed_step}"
            repair_class = "ledger_reconcile"
        elif reason == "agent_step_failed":
            diagnosis = str(
                failure.get("diagnosis_class") or "task_failure_unclassified"
            )
            if diagnosis == "schema_invalid":
                fingerprint = f"schema:invalid_result:{failed_step}"
                repair_class = "schema_diagnose"
            elif diagnosis in {
                "provider_launch",
                "provider_timeout",
                "provider_transient",
            }:
                fingerprint = f"provider:{diagnosis}:{failed_step}"
                repair_class = "provider_diagnose"
            elif diagnosis == "budget_policy":
                # A configured budget boundary is neither a provider outage nor
                # authority to retry a possibly side-effecting browser task.
                continue
            else:
                fingerprint = f"task:unclassified:{failed_step}"
                repair_class = "task_diagnose"
        if fingerprint and fingerprint not in seen_failure_fingerprints:
            evidence = {
                "ts": failure_at,
                "failed_step": failed_step,
                "reason": reason,
            }
            if reason == "agent_step_failed":
                evidence["diagnosis_class"] = str(
                    failure.get("diagnosis_class")
                    or "task_failure_unclassified"
                )
                evidence["diagnosis_evidence"] = failure.get(
                    "diagnosis_evidence"
                ) or {}
            if repair_class == "ledger_reconcile":
                evidence["pass_id"] = str(failure.get("pass_id") or "")
                evidence["evidence_dir"] = str(
                    failure.get("evidence_dir") or ""
                )
            incidents.append(
                _incident(
                    fingerprint,
                    repair_class=repair_class,
                    evidence=evidence,
                )
            )
            seen_failure_fingerprints.add(fingerprint)

    disk = snapshot.get("disk") or {}
    free_gb = disk.get("free_gb")
    minimum_free_gb = disk.get("minimum_free_gb", 5)
    if disk.get("hard_stop") is True:
        incidents.append(
            _incident(
                "disk:hard_stop",
                repair_class="disk_recover",
                evidence={
                    "free_gb": free_gb,
                    "minimum_free_gb": minimum_free_gb,
                    "pressure_advisory": disk.get("pressure_advisory") is True,
                },
            )
        )
    elif (
        isinstance(free_gb, int)
        and isinstance(minimum_free_gb, int)
        and free_gb < minimum_free_gb
    ):
        incidents.append(
            _incident(
                "disk:space_below_minimum",
                repair_class="disk_recover",
                evidence={
                    "free_gb": free_gb,
                    "minimum_free_gb": minimum_free_gb,
                    "pressure_advisory": disk.get("pressure_advisory") is True,
                },
            )
        )

    return incidents


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_last_json_object(path: Path) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in reversed(lines[-100:]):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _event_epoch(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _runtime_lane_state(runtime_state_dir: Path) -> tuple[dict[str, dict[str, Any]], int | None]:
    lanes: dict[str, dict[str, Any]] = {}
    latest_pass: int | None = None
    for lane, (directory, loop_id) in RUNTIME_LANES.items():
        path = runtime_state_dir / directory / "events.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[-200:]
        except OSError:
            continue
        last_attempt: int | None = None
        last_success: int | None = None
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("loop_id") != loop_id:
                continue
            timestamp = _event_epoch(event.get("timestamp"))
            if timestamp is None:
                continue
            if event.get("phase") in {"execute", "report"}:
                last_attempt = max(last_attempt or timestamp, timestamp)
            if event.get("phase") == "report" and event.get("status") == "pass":
                last_success = max(last_success or timestamp, timestamp)
        if last_attempt is not None:
            lanes[lane] = {"last_attempt_at": last_attempt}
        if last_success is not None:
            latest_pass = max(latest_pass or last_success, last_success)
    return lanes, latest_pass


def _read_bounded_logs(agent_dir: Path) -> str:
    chunks: list[str] = []
    for pattern in ("attempt-*.stdout.log", "attempt-*.stderr.log"):
        paths = sorted(agent_dir.glob(pattern))
        if not paths:
            continue
        try:
            with paths[-1].open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(0, size - 65536))
                chunks.append(handle.read().decode("utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks).lower()


def _diagnose_agent_failure(row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    failed_step = str(row.get("failed_step") or "")
    evidence_dir = row.get("evidence_dir")
    if (
        not evidence_dir
        or not failed_step
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in failed_step
        )
    ):
        enriched["diagnosis_class"] = "task_failure_unclassified"
        return enriched
    agent_dir = Path(str(evidence_dir)) / f"agent-{failed_step}"
    summary = _read_json(agent_dir / "summary.json")
    attempt = _read_last_json_object(agent_dir / "attempts.jsonl")
    summary_status = str(summary.get("status") or "")
    budget = summary.get("budget") if isinstance(summary.get("budget"), dict) else {}
    if summary_status == "budget_blocked" or budget.get("status") == "blocked":
        diagnosis = "budget_policy"
    else:
        logs = _read_bounded_logs(agent_dir)
        schema_signatures = (
            "invalid_json_schema",
            "invalid schema for response_format",
            "required is required to be supplied",
        )
        provider_signatures = (
            "rate_limit",
            "rate limit",
            "overloaded",
            "service unavailable",
            "status 429",
        )
        if any(signature in logs for signature in schema_signatures):
            diagnosis = "schema_invalid"
        elif attempt.get("timed_out") is True:
            diagnosis = "provider_timeout"
        elif (
            attempt.get("launch_error")
            or attempt.get("adapter_error")
            or attempt.get("rc") in {126, 127}
        ):
            diagnosis = "provider_launch"
        elif any(signature in logs for signature in provider_signatures):
            diagnosis = "provider_transient"
        else:
            diagnosis = "task_failure_unclassified"
    enriched["diagnosis_class"] = diagnosis
    enriched["diagnosis_evidence"] = {
        "summary_status": summary_status or None,
        "attempt_rc": attempt.get("rc"),
        "attempt_timed_out": attempt.get("timed_out"),
        "attempt_error_class": attempt.get("error_class"),
        "attempt_executable": attempt.get("executable"),
    }
    return enriched


def _application_ledger_missing_ids(
    row: dict[str, Any],
    ledger_path: Path,
) -> list[str]:
    pass_id = str(row.get("pass_id") or "")
    evidence_dir = Path(str(row.get("evidence_dir") or ""))
    if not pass_id or evidence_dir.name != f"gig-pass-{pass_id}":
        return []
    candidate_ids: set[str] = set()
    for path in (evidence_dir / "agent-B2").glob("*-submitted.intent.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        request_id = str(
            payload.get("request_id") or payload.get("requestId") or ""
        )
        if request_id.isdigit() or (
            len(request_id) == 26
            and all(
                character in "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
                for character in request_id
            )
        ):
            candidate_ids.add(request_id)
    recorded: set[str] = set()
    try:
        ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        ledger_lines = []
    for line in ledger_lines[-2000:]:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, dict)
            and "action" not in payload
            and str(payload.get("status") or "") == "applied"
        ):
            recorded.add(
                str(payload.get("requestId") or payload.get("request_id") or "")
            )
    return sorted(candidate_ids - recorded)


def _recent_failures(
    path: Path,
    *,
    now: int,
    ledger_path: Path | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines[-200:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = row.get("ts") if isinstance(row, dict) else None
        if isinstance(ts, (int, float)) and 0 <= now - ts <= RECENT_FAILURE_SECONDS:
            if row.get("reason") == "agent_step_failed":
                row = _diagnose_agent_failure(row)
            elif (
                row.get("reason") == "b2_application_ledger_write_failed"
                and ledger_path is not None
            ):
                row = dict(row)
                row["ledger_missing_request_ids"] = (
                    _application_ledger_missing_ids(row, ledger_path)
                )
            rows.append(row)
    return rows


def _telegram_state(database: Path, *, now: int) -> dict[str, Any]:
    state = {
        "latest_pass_created_at": None,
        "latest_pass_state": None,
        "delivery_unknown": 0,
        "delivery_unknown_active": 0,
    }
    if not database.exists():
        return state
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            placeholders = ",".join("?" for _ in TELEGRAM_HEALTH_REPORT_KINDS)
            latest = connection.execute(
                f"""SELECT created_at,state FROM telegram_reports
                   WHERE state='sent' AND kind IN ({placeholders})
                   ORDER BY created_at DESC,report_id DESC LIMIT 1""",
                TELEGRAM_HEALTH_REPORT_KINDS,
            ).fetchone()
            unknown = connection.execute(
                "SELECT COUNT(*) FROM telegram_reports WHERE state='delivery_unknown'"
            ).fetchone()
            active_unknown = connection.execute(
                """SELECT COUNT(*) FROM telegram_reports
                   WHERE state='delivery_unknown' AND created_at>=?""",
                (now - RECENT_FAILURE_SECONDS,),
            ).fetchone()
    except sqlite3.Error:
        return state
    if latest is not None:
        state["latest_pass_created_at"] = latest[0]
        state["latest_pass_state"] = latest[1]
    state["delivery_unknown"] = int(unknown[0]) if unknown is not None else 0
    state["delivery_unknown_active"] = (
        int(active_unknown[0]) if active_unknown is not None else 0
    )
    return state


def collect_snapshot(
    *,
    state_dir: Path | str,
    telegram_database: Path | str,
    now: int,
    host_state_dir: Path | str | None = None,
    runtime_state_dir: Path | str | None = None,
    minimum_free_gb: int = 5,
) -> dict[str, Any]:
    root = Path(state_dir)
    host_state = (
        Path(host_state_dir)
        if host_state_dir is not None
        else _default_host_state_dir()
    )
    heartbeat = root / ".last-pass"
    try:
        last_pass_at: int | None = int(heartbeat.stat().st_mtime)
    except OSError:
        last_pass_at = None
    try:
        disk_free_gb: int | None = int(
            shutil.disk_usage(root).free // (1024 ** 3)
        )
    except OSError:
        disk_free_gb = None
    legacy_lanes = {
            lane: _read_json(root / "state" / "lanes" / f"{lane}.json")
            for lane in REVENUE_LANES
    }
    runtime_root = Path(runtime_state_dir) if runtime_state_dir is not None else Path(
        os.environ.get(
            "GIG_RUNTIME_COCONALA_STATE_DIR",
            str(Path.home() / ".local" / "state" / "life-manager" / "coconala"),
        )
    )
    runtime_lanes, runtime_last_pass = _runtime_lane_state(runtime_root)
    lanes = {lane: {**legacy_lanes.get(lane, {}), **runtime_lanes.get(lane, {})}
             for lane in REVENUE_LANES}
    if runtime_last_pass is not None:
        last_pass_at = max(last_pass_at or runtime_last_pass, runtime_last_pass)
    return {
        "last_pass_at": last_pass_at,
        "lanes": lanes,
        "telegram": _telegram_state(Path(telegram_database), now=now),
        "hermes_audit": _read_json(root / "hermes-canary-24h-audit.json"),
        "recent_failures": _recent_failures(
            root / "pass-failures.jsonl",
            now=now,
            ledger_path=root / "applied.jsonl",
        ),
        "disk": {
            "hard_stop": (host_state / "disk-writers.stop").is_file(),
            "pressure_advisory": (host_state / "disk-pressure.block").is_file(),
            "free_gb": disk_free_gb,
            "minimum_free_gb": minimum_free_gb,
        },
    }


def _repair_queue_module():
    path = Path(__file__).with_name("repair_queue.py")
    spec = importlib.util.spec_from_file_location("gig_repair_queue_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load repair_queue")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate_and_enqueue(
    *,
    state_dir: Path | str,
    telegram_database: Path | str,
    repair_database: Path | str,
    now: int,
    host_state_dir: Path | str | None = None,
    runtime_state_dir: Path | str | None = None,
) -> dict[str, Any]:
    snapshot = collect_snapshot(
        state_dir=state_dir,
        telegram_database=telegram_database,
        now=now,
        host_state_dir=host_state_dir,
        runtime_state_dir=runtime_state_dir,
    )
    incidents = evaluate(snapshot, now=now)
    queue = _repair_queue_module().RepairQueue(repair_database)
    for incident in incidents:
        queue.enqueue(
            fingerprint=incident["fingerprint"],
            repair_class=incident["repair_class"],
            evidence=incident["evidence"],
            detected_at=now,
        )
    return {
        "status": "ok" if not incidents else "incident",
        "incident_count": len(incidents),
        "incidents": incidents,
        "queue": queue.list_incidents(),
    }


def main() -> int:
    home = Path.home()
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=home / "gig")
    parser.add_argument(
        "--telegram-database", type=Path, default=home / "gig/telegram-outbox.sqlite3"
    )
    parser.add_argument(
        "--repair-database", type=Path, default=home / "gig/gig-control.sqlite3"
    )
    parser.add_argument(
        "--host-state-dir",
        type=Path,
        default=_default_host_state_dir(),
    )
    parser.add_argument("--runtime-state-dir", type=Path, default=None)
    parser.add_argument("--now", type=int, default=None)
    args = parser.parse_args()
    result = evaluate_and_enqueue(
        state_dir=args.state_dir,
        telegram_database=args.telegram_database,
        repair_database=args.repair_database,
        now=args.now if args.now is not None else int(time.time()),
        host_state_dir=args.host_state_dir,
        runtime_state_dir=args.runtime_state_dir,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
