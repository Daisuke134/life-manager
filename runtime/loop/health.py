"""Bounded, read-only health projection over existing lm-loop status rows."""

from __future__ import annotations

import json
import re
import signal
from contextlib import contextmanager
from datetime import datetime, timezone
from time import monotonic


SCHEMA_VERSION = "lm-loop.health.v1"
SYSTEM_ROLES = frozenset({"platform", "control", "shared"})
HEALTH_STATES = frozenset({
    "healthy", "running", "safely_fenced", "effect_unknown",
    "telemetry_gap", "human_required", "failed",
})
FACET_STATUSES = frozenset({"ok", "degraded", "blocked", "unknown", "not_applicable"})
SUMMARY_FIELDS = frozenset({*HEALTH_STATES, "total"})
JOB_FIELDS = frozenset({
    "job_id", "label", "product_loop_id", "system_role", "state",
    "facets", "clocks", "diagnostic",
})
DIAGNOSTIC_FIELDS = frozenset({
    "release_sha", "run_id", "owner_id", "occurrence_id", "effect", "readback",
    "provider_receipt_id", "error_class", "retryable", "next_action", "release_drift",
    "receipt_missing_for_pass",
})
RFC3339_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


class HealthTimeout(TimeoutError):
    pass


class HealthAdapterTimeout(HealthTimeout):
    pass


@contextmanager
def health_deadline(seconds: float, *, timeout_error=HealthTimeout):
    if seconds <= 0:
        raise ValueError("health deadline must be positive")
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expired(_signum, _frame):
        raise timeout_error("health deadline exceeded")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def health_json_schema() -> dict:
    nullable_string = {"type": ["string", "null"]}
    nonnegative_integer = {"type": "integer", "minimum": 0}
    facet = {
        "type": "object",
        "required": ["status", "reason"],
        "properties": {
            "status": {"type": "string", "enum": sorted(FACET_STATUSES)},
            "reason": nullable_string,
        },
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/Daisuke134/life-manager/runtime/loop/health.schema.json",
        "title": SCHEMA_VERSION,
        "type": "object",
        "required": ["schema_version", "generated_at", "scope", "summary", "jobs"],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "generated_at": {
                "type": "string",
                "format": "date-time",
                "pattern": RFC3339_PATTERN,
            },
            "scope": {
                "type": "object",
                "required": ["kind", "target"],
                "properties": {
                    "kind": {"type": "string", "enum": ["fleet", "loop"]},
                    "target": nullable_string,
                },
                "oneOf": [
                    {
                        "properties": {
                            "kind": {"const": "fleet"},
                            "target": {"type": "null"},
                        },
                    },
                    {
                        "properties": {
                            "kind": {"const": "loop"},
                            "target": {"type": "string", "minLength": 1},
                        },
                    },
                ],
                "additionalProperties": False,
            },
            "summary": {
                "type": "object",
                "required": sorted(SUMMARY_FIELDS),
                "properties": {
                    name: nonnegative_integer for name in sorted(SUMMARY_FIELDS)
                },
                "additionalProperties": False,
            },
            "jobs": {"type": "array", "items": {"$ref": "#/$defs/job"}},
        },
        "$defs": {
            "facet": facet,
            "diagnostic": {
                "type": "object",
                "required": sorted(DIAGNOSTIC_FIELDS),
                "properties": {
                    "release_sha": nullable_string,
                    "run_id": nullable_string,
                    "owner_id": nullable_string,
                    "occurrence_id": nullable_string,
                    "effect": {
                        "type": "object",
                        "required": ["class", "status"],
                        "properties": {
                            "class": nullable_string,
                            "status": nullable_string,
                        },
                        "additionalProperties": False,
                    },
                    "readback": nullable_string,
                    "provider_receipt_id": nullable_string,
                    "error_class": nullable_string,
                    "retryable": {"type": ["boolean", "null"]},
                    "next_action": nullable_string,
                    "release_drift": {"type": "boolean"},
                    "receipt_missing_for_pass": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            "job": {
                "type": "object",
                "required": sorted(JOB_FIELDS),
                "properties": {
                    "job_id": {"type": "string", "minLength": 1},
                    "label": {"type": "string", "minLength": 1},
                    "product_loop_id": nullable_string,
                    "system_role": {
                        "type": ["string", "null"],
                        "enum": [None, *sorted(SYSTEM_ROLES)],
                    },
                    "state": {"type": "string", "enum": sorted(HEALTH_STATES)},
                    "facets": {
                        "type": "object",
                        "required": [
                            "runtime", "productivity", "effect_safety", "business", "recovery",
                        ],
                        "properties": {
                            name: {"$ref": "#/$defs/facet"}
                            for name in (
                                "runtime", "productivity", "effect_safety", "business", "recovery",
                            )
                        },
                        "additionalProperties": False,
                    },
                    "clocks": {
                        "type": "object",
                        "required": [
                            "last_attempt", "last_success", "last_effect", "last_receipt",
                        ],
                        "properties": {
                            name: nullable_string for name in (
                                "last_attempt", "last_success", "last_effect", "last_receipt",
                            )
                        },
                        "additionalProperties": False,
                    },
                    "diagnostic": {"$ref": "#/$defs/diagnostic"},
                },
                "oneOf": [
                    {
                        "properties": {
                            "product_loop_id": {"type": "string", "minLength": 1},
                            "system_role": {"type": "null"},
                        },
                    },
                    {
                        "properties": {
                            "product_loop_id": {"type": "null"},
                            "system_role": {"type": "string", "enum": sorted(SYSTEM_ROLES)},
                        },
                    },
                ],
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def render_health_json_schema() -> bytes:
    return (json.dumps(health_json_schema(), indent=2, sort_keys=True) + "\n").encode()


def _clock(row: dict, name: str, *, statuses: set[str] | None = None,
           require_receipt: bool = False) -> str | None:
    historical = (row.get("health_clocks") or {}).get(name)
    if isinstance(historical, str):
        return historical
    timestamp = row.get("last_pass")
    if not isinstance(timestamp, str):
        return None
    if statuses is not None and row.get("last_terminal_result") not in statuses:
        return None
    if require_receipt and not (
        row.get("provider_receipt_id") or row.get("official_readback_ref")
    ):
        return None
    return timestamp


def _health_state(row: dict) -> str:
    adapter_status = row.get("health_adapter_status")
    if adapter_status in {"timeout", "error"}:
        return "telemetry_gap"
    if row.get("release_drift") is True:
        # The event was emitted by a different immutable release than the one
        # currently installed. Do not treat that event as current health.
        return "telemetry_gap"
    if row.get("receipt_missing_for_pass") is True:
        # A terminal pass cannot prove an external effect without one of the
        # two official receipt forms. Keep the lane fenced for readback.
        return "telemetry_gap"
    diagnostic_text = " ".join(str(row.get(key) or "") for key in (
        "blocker", "error_class", "next_action", "error_detail",
    )).lower()
    if "human_required" in diagnostic_text:
        return "human_required"
    if "pre_effect_" in diagnostic_text or "lm_pre_effect_reason:" in diagnostic_text:
        return "safely_fenced"
    if row.get("admission_effect_unknown") is True or "resource_effect_unknown" in diagnostic_text:
        return "safely_fenced"
    if row.get("diagnostic_complete") is not True or not isinstance(row.get("last_pass"), str):
        return "telemetry_gap"
    if (row.get("effect_class") != "none"
            and row.get("effect_status") in {None, "unknown", "planned", "started"}):
        return "effect_unknown"
    if (row.get("last_terminal_result") in {"fail", "blocked"}
            or row.get("launchd_state") in {"disabled", "unloaded"}
            or row.get("blocker")):
        return "failed"
    if row.get("last_terminal_result") == "running":
        return "running"
    return "healthy"


def _facets(row: dict, state: str) -> dict[str, dict[str, str | None]]:
    runtime = "ok" if row.get("launchd_state") in {"loaded-idle", "loaded-running"} else "degraded"
    productivity = {
        "pass": "ok", "running": "ok", "fail": "degraded", "blocked": "blocked",
    }.get(row.get("last_terminal_result"), "unknown")
    if row.get("effect_class") == "none":
        effect_safety = "not_applicable"
    elif state in {"safely_fenced", "effect_unknown", "human_required"}:
        effect_safety = "blocked"
    elif row.get("effect_status") in {"verified", "reconciled"}:
        effect_safety = "ok"
    elif row.get("effect_status") == "failed":
        effect_safety = "degraded"
    else:
        effect_safety = "unknown"
    if row.get("effect_class") == "none":
        business = "not_applicable"
    elif row.get("provider_receipt_id") or row.get("official_readback_ref"):
        business = "ok"
    else:
        business = "unknown"
    if state == "human_required":
        recovery = "blocked"
    elif row.get("retryable") is True:
        recovery = "degraded"
    elif row.get("next_action") in {None, "none", "monitor_running"}:
        recovery = "ok"
    else:
        recovery = "unknown"
    reason = row.get("blocker") or row.get("error_class")
    return {
        "runtime": {"status": runtime, "reason": reason},
        "productivity": {"status": productivity, "reason": reason},
        "effect_safety": {"status": effect_safety, "reason": reason},
        "business": {"status": business, "reason": None},
        "recovery": {"status": recovery, "reason": row.get("next_action")},
    }


def project_health(rows: list[dict], *, scope: str = "fleet",
                   target: str | None = None, adapter=None,
                   adapter_timeout_seconds: float = 0.25,
                   deadline_monotonic: float | None = None) -> dict:
    jobs = []
    adapted_rows = []
    for original in rows:
        if original.get("classification") not in {None, "managed"}:
            continue
        row = dict(original)
        remaining = (
            deadline_monotonic - monotonic()
            if deadline_monotonic is not None else None
        )
        if remaining is not None and remaining <= 0:
            row.update({
                "health_adapter_status": "timeout",
                "error_class": "health_projection_timeout",
                "retryable": True,
                "next_action": "retry_health_snapshot",
            })
            adapted_rows.append(row)
            continue
        if adapter is not None:
            adapter_deadline = (
                min(adapter_timeout_seconds, remaining)
                if remaining is not None else adapter_timeout_seconds
            )
            fleet_deadline_is_tighter = (
                remaining is not None and remaining <= adapter_timeout_seconds
            )
            try:
                with health_deadline(
                    adapter_deadline,
                    timeout_error=HealthAdapterTimeout,
                ):
                    adapted = adapter(row)
                if not isinstance(adapted, dict):
                    raise ValueError("health adapter must return an object")
                row = adapted
            except HealthAdapterTimeout:
                row.update({
                    "health_adapter_status": "timeout",
                    "error_class": (
                        "health_projection_timeout" if fleet_deadline_is_tighter
                        else "health_adapter_timeout"
                    ),
                    "retryable": True,
                    "next_action": (
                        "retry_health_snapshot" if fleet_deadline_is_tighter
                        else "inspect_health_adapter"
                    ),
                })
            except HealthTimeout:
                raise
            except Exception:
                row.update({
                    "health_adapter_status": "error",
                    "error_class": "health_adapter_error",
                    "retryable": True,
                    "next_action": "inspect_health_adapter",
                })
        adapted_rows.append(row)
    for row in adapted_rows:
        release_drift = (
            isinstance(row.get("installed_release_sha"), str)
            and isinstance(row.get("event_release_sha"), str)
            and row["installed_release_sha"] != row["event_release_sha"]
        )
        receipt_missing_for_pass = (
            row.get("effect_class") != "none"
            and row.get("last_terminal_result") == "pass"
            and row.get("effect_status") in {"verified", "reconciled"}
            and not (row.get("provider_receipt_id") or row.get("official_readback_ref"))
        )
        row["release_drift"] = release_drift
        row["receipt_missing_for_pass"] = receipt_missing_for_pass
        if release_drift:
            # Reconcile provenance before retrying the provider action. This
            # is a read-only projection; it does not reload or restart a loop.
            row["next_action"] = "reconcile_current_release"
            row["retryable"] = True
        elif receipt_missing_for_pass:
            row["error_class"] = row.get("error_class") or "receipt_missing_for_pass"
            row["next_action"] = "official_readback_required"
            row["retryable"] = False
        state = _health_state(row)
        effect_status = row.get("effect_status")
        jobs.append({
            "job_id": row.get("loop_id"),
            "label": row.get("label"),
            "product_loop_id": row.get("product_loop_id"),
            "system_role": row.get("system_role"),
            "state": state,
            "facets": _facets(row, state),
            "clocks": {
                "last_attempt": _clock(row, "last_attempt"),
                "last_success": _clock(row, "last_success", statuses={"pass"}),
                "last_effect": (
                    _clock(row, "last_effect") if row.get("effect_class") != "none"
                    and effect_status in {"started", "verified", "failed", "reconciled"}
                    else (row.get("health_clocks") or {}).get("last_effect")
                ),
                "last_receipt": _clock(
                    row, "last_receipt", require_receipt=True,
                ),
            },
            "diagnostic": {
                "release_sha": row.get("event_release_sha") or row.get("installed_release_sha"),
                "run_id": row.get("run_id"),
                "owner_id": row.get("owner_id"),
                "occurrence_id": row.get("occurrence_id"),
                "effect": {
                    "class": row.get("effect_class"),
                    "status": effect_status,
                },
                "readback": row.get("official_readback_ref"),
                "provider_receipt_id": row.get("provider_receipt_id"),
                "error_class": row.get("error_class"),
                "retryable": row.get("retryable"),
                "next_action": row.get("next_action"),
                "release_drift": release_drift,
                "receipt_missing_for_pass": receipt_missing_for_pass,
            },
        })
    summary = {state: 0 for state in sorted(HEALTH_STATES)}
    for job in jobs:
        summary[job["state"]] += 1
    summary["total"] = len(jobs)
    value = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"kind": scope, "target": target},
        "summary": summary,
        "jobs": jobs,
    }
    return validate_health_document(value)


def validate_health_document(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "generated_at", "scope", "summary", "jobs",
    }:
        raise ValueError("health document must contain only v1 top-level fields")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError("invalid health schema_version")
    generated_at_text = value["generated_at"]
    if (not isinstance(generated_at_text, str)
            or re.fullmatch(RFC3339_PATTERN, generated_at_text) is None):
        raise ValueError("invalid health generated_at")
    try:
        generated_at = datetime.fromisoformat(generated_at_text.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("invalid health generated_at") from exc
    if generated_at.tzinfo is None:
        raise ValueError("invalid health generated_at")
    scope = value["scope"]
    if (not isinstance(scope, dict) or set(scope) != {"kind", "target"}
            or scope.get("kind") not in {"fleet", "loop"}):
        raise ValueError("invalid health scope")
    if ((scope["kind"] == "fleet" and scope.get("target") is not None)
            or (scope["kind"] == "loop"
                and (not isinstance(scope.get("target"), str) or not scope["target"]))):
        raise ValueError("invalid health scope target")
    summary = value["summary"]
    if (not isinstance(summary, dict) or set(summary) != SUMMARY_FIELDS
            or any(type(count) is not int or count < 0 for count in summary.values())):
        raise ValueError("invalid health summary")
    if not isinstance(value["jobs"], list):
        raise ValueError("health jobs must be an array")
    for job in value["jobs"]:
        if not isinstance(job, dict) or set(job) != JOB_FIELDS:
            raise ValueError("invalid health job fields")
        if (not isinstance(job["job_id"], str) or not job["job_id"]
                or not isinstance(job["label"], str) or not job["label"]):
            raise ValueError("invalid health job identity")
        if job.get("state") not in HEALTH_STATES:
            raise ValueError("invalid health job state")
        product_loop_id, system_role = job.get("product_loop_id"), job.get("system_role")
        if (product_loop_id is None) == (system_role is None):
            raise ValueError("health job requires exactly one classification")
        if (product_loop_id is not None
                and (not isinstance(product_loop_id, str) or not product_loop_id)):
            raise ValueError("invalid health product_loop_id")
        if system_role is not None and system_role not in SYSTEM_ROLES:
            raise ValueError("invalid health system_role")
        if set(job.get("clocks", {})) != {
            "last_attempt", "last_success", "last_effect", "last_receipt",
        } or any(value is not None and not isinstance(value, str)
                 for value in job["clocks"].values()):
            raise ValueError("invalid health clocks")
        facets = job.get("facets", {})
        if set(facets) != {"runtime", "productivity", "effect_safety", "business", "recovery"}:
            raise ValueError("invalid health facets")
        if any(not isinstance(facet, dict) or set(facet) != {"status", "reason"}
               or facet.get("status") not in FACET_STATUSES
               or (facet.get("reason") is not None
                   and not isinstance(facet.get("reason"), str))
               for facet in facets.values()):
            raise ValueError("invalid health facet status")
        diagnostic = job["diagnostic"]
        if not isinstance(diagnostic, dict) or set(diagnostic) != DIAGNOSTIC_FIELDS:
            raise ValueError("invalid health diagnostic")
        effect = diagnostic["effect"]
        if (not isinstance(effect, dict) or set(effect) != {"class", "status"}
                or any(item is not None and not isinstance(item, str)
                       for item in effect.values())):
            raise ValueError("invalid health diagnostic effect")
        nullable_diagnostic_strings = DIAGNOSTIC_FIELDS - {
            "effect", "retryable", "release_drift", "receipt_missing_for_pass",
        }
        if any(diagnostic[name] is not None and not isinstance(diagnostic[name], str)
               for name in nullable_diagnostic_strings):
            raise ValueError("invalid health diagnostic value")
        if diagnostic["retryable"] is not None and type(diagnostic["retryable"]) is not bool:
            raise ValueError("invalid health diagnostic retryable")
        if type(diagnostic["release_drift"]) is not bool:
            raise ValueError("invalid health diagnostic release_drift")
        if type(diagnostic["receipt_missing_for_pass"]) is not bool:
            raise ValueError("invalid health diagnostic receipt_missing_for_pass")
    expected_summary = {state: 0 for state in sorted(HEALTH_STATES)}
    for job in value["jobs"]:
        expected_summary[job["state"]] += 1
    expected_summary["total"] = len(value["jobs"])
    if summary != expected_summary:
        raise ValueError("health summary does not match jobs")
    return value


def health_exit_code(value: dict) -> int:
    summary = value["summary"]
    unsafe = (
        "safely_fenced", "effect_unknown", "telemetry_gap", "human_required", "failed",
    )
    return 1 if any(summary[name] for name in unsafe) else 0


def render_human(value: dict) -> str:
    summary = value["summary"]
    line = (
        f"health total={summary['total']} healthy={summary['healthy']} "
        f"running={summary['running']} safely_fenced={summary['safely_fenced']} "
        f"effect_unknown={summary['effect_unknown']} telemetry_gap={summary['telemetry_gap']} "
        f"human_required={summary['human_required']} failed={summary['failed']}"
    )
    problems = [
        f"{job['job_id']}: {job['state']} next={job['diagnostic']['next_action'] or 'none'}"
        for job in value["jobs"] if job["state"] != "healthy"
    ]
    return "\n".join([line, *problems])


def render_skill(value: dict) -> str:
    return "\n".join(
        json.dumps({
            "job_id": job["job_id"],
            "classification": job["product_loop_id"] or job["system_role"],
            "state": job["state"],
            "next_action": job["diagnostic"]["next_action"],
        }, sort_keys=True, separators=(",", ":"))
        for job in value["jobs"]
    )
