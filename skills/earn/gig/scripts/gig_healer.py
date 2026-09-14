#!/usr/bin/env python3
"""Bounded deterministic dispatch for known Gig infrastructure failures.

Dispatch is deliberately separate from recovery.  A successful launchctl call
only means the remediation was requested; the incident may be marked recovered
only after a later fresh SLO/canary no longer reproduces its fingerprint.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from gig_paths import REPO_ROOT  # noqa: E402

SHARED_LIB = REPO_ROOT / "skills" / "_shared" / "lib"
if str(SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(SHARED_LIB))
from launchd_preflight import probe as launchd_control_plane_probe  # noqa: E402


SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
DIAGNOSTIC_CLASSES = frozenset(
    {
        "schema_diagnose",
        "provider_diagnose",
        "task_diagnose",
        # A15 (2026-07-30): rung 5 of the pass-health ladder. Five consecutive
        # failures at one step is a defect in that step, not a transient, so it
        # is handed to the patch loop with the evidence already gathered.
        "pass_step_repair",
    }
)


def _patch_handoff(
    *,
    repair_class: str,
    incident: dict[str, Any] | None,
    diagnosis: dict[str, Any],
    runner: Callable[..., Any],
) -> dict[str, Any]:
    self_fix = REPO_ROOT / "skills" / "self" / "self-fix.sh"
    incident_id = (
        int(incident.get("incident_id") or 0)
        if isinstance(incident, dict)
        else 0
    )
    fingerprint = (
        str(incident.get("fingerprint") or "")
        if isinstance(incident, dict)
        else ""
    )
    blocker = (
        f"Gig D3 incident_id={incident_id} fingerprint={fingerprint} "
        f"repair_class={repair_class} diagnosis="
        f"{json.dumps(diagnosis, ensure_ascii=False, separators=(',', ':'))}. "
        "Use a clean worktree. Before editing, add the smallest failing regression test "
        "and record the RED. Then patch, run focused and affected suites GREEN, commit and "
        "push only owned files. Trigger the existing natural launchd loop for production "
        "canary; never replay a customer submission/message/delivery blindly. If the "
        "natural canary fails, revert only your own commit, push the revert, and preserve "
        "the incident evidence for the next bounded attempt."
    )
    result = runner(
        ["/bin/bash", str(self_fix), "gig", blocker],
        shell=False,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return {
            "patch_handoff": "failed",
            "patch_returncode": int(result.returncode),
            "patch_stderr_tail": str(result.stderr or "")[-500:],
        }
    return {
        "patch_handoff": "spawned",
        "patch_stdout_tail": str(result.stdout or "")[-500:],
        "patch_result_marker": str(
            Path.home() / ".openclaw/state/.self-fix-gig-loop.result"
        ),
    }


def _strict_schema_diagnosis() -> dict[str, Any]:
    errors: list[str] = []
    checked = 0

    def walk(value: Any, location: str) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                missing = sorted(set(properties) - set(value.get("required") or []))
                if missing:
                    errors.append(f"{location}:required_missing:{','.join(missing)}")
            for key, child in value.items():
                walk(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{location}[{index}]")

    for path in sorted(SCHEMAS.glob("*.schema.json")):
        checked += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}:unreadable:{type(exc).__name__}")
            continue
        walk(payload, path.name)
    return {
        "status": "diagnosed",
        "repair_class": "schema_diagnose",
        "canary_passed": checked > 0 and not errors,
        "schemas_checked": checked,
        "errors": errors,
        "side_effect_performed": False,
    }


def _diagnose(
    repair_class: str,
    incident: dict[str, Any] | None,
) -> dict[str, Any]:
    if repair_class == "schema_diagnose":
        return _strict_schema_diagnosis()
    evidence = (
        incident.get("evidence")
        if isinstance(incident, dict)
        and isinstance(incident.get("evidence"), dict)
        else {}
    )
    diagnosis_class = str(evidence.get("diagnosis_class") or "")
    if repair_class == "provider_diagnose":
        diagnosis_evidence = (
            evidence.get("diagnosis_evidence")
            if isinstance(evidence.get("diagnosis_evidence"), dict)
            else {}
        )
        executable = str(diagnosis_evidence.get("attempt_executable") or "")
        executable_available = bool(
            executable
            and Path(executable).is_file()
            and os.access(executable, os.X_OK)
        )
        return {
            "status": "diagnosed",
            "repair_class": repair_class,
            "diagnosis_class": diagnosis_class,
            "canary_passed": executable_available,
            "executable": executable or None,
            "executable_available": executable_available,
            "side_effect_performed": False,
        }
    if repair_class == "pass_step_repair":
        # Nothing to canary: a step that has failed five times running is a
        # defect to be patched, and the whole point of this row is that the
        # evidence needed to patch it is already collected.
        return {
            "status": "diagnosed",
            "repair_class": repair_class,
            "failed_step": str(evidence.get("failed_step") or "") or None,
            "reason": str(evidence.get("reason") or "") or None,
            "consecutive": int(evidence.get("consecutive") or 0),
            "evidence_dirs": [
                str(item) for item in (evidence.get("evidence_dirs") or [])
            ],
            "source_file": evidence.get("source_file"),
            "canary_passed": False,
            "side_effect_performed": False,
        }
    if repair_class == "ledger_reconcile":
        pass_id = str(evidence.get("pass_id") or "")
        evidence_dir = Path(str(evidence.get("evidence_dir") or ""))
        candidate_ids: set[str] = set()
        errors: list[str] = []
        if (
            not pass_id
            or evidence_dir.name != f"gig-pass-{pass_id}"
            or not evidence_dir.is_dir()
        ):
            errors.append("pass_evidence_identity_invalid")
        else:
            agent_dir = evidence_dir / "agent-B2"
            for path in sorted(agent_dir.glob("*-submitted.intent.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    errors.append(f"intent_unreadable:{path.name}")
                    continue
                request_id = str(
                    payload.get("request_id")
                    or payload.get("requestId")
                    or ""
                )
                if re.fullmatch(
                    r"(?:\d+|[0-7][0-9A-HJKMNP-TV-Z]{25})",
                    request_id,
                ):
                    candidate_ids.add(request_id)
                else:
                    errors.append(f"intent_identity_invalid:{path.name}")
        return {
            "status": "diagnosed",
            "repair_class": repair_class,
            "canary_passed": bool(candidate_ids) and not errors,
            "pass_id": pass_id or None,
            "candidate_request_ids": sorted(candidate_ids),
            "errors": errors,
            "side_effect_performed": False,
        }
    return {
        "status": "diagnosed",
        "repair_class": repair_class,
        "diagnosis_class": diagnosis_class or "task_failure_unclassified",
        "canary_passed": False,
        "reason": "unclassified_task_requires_test_first_patch",
        "side_effect_performed": False,
    }


def repair_command(repair_class: str, *, uid: int) -> list[str] | None:
    domain = f"gui/{uid}"
    if repair_class == "application_expand":
        # No -k: ask the direct owner for another wake without interrupting one.
        return [
            "/bin/launchctl",
            "kickstart",
            f"{domain}/ai.anicca.hf-gig-apply-direct",
        ]
    if repair_class in {"scheduler_restart", "lane_probe"}:
        # The existing healthcheck reconciles every enabled direct owner.
        return [
            "/bin/launchctl",
            "kickstart",
            f"{domain}/ai.anicca.hf-gig-core-healthcheck",
        ]
    if repair_class == "browser_restart":
        # The browser is an isolated infrastructure service. Its session vault
        # persists auth, and the SLO failure explicitly says CDP is unavailable.
        return [
            "/bin/launchctl",
            "kickstart",
            "-k",
            f"{domain}/ai.anicca.hf-gig-browser",
        ]
    if repair_class == "disk_recover":
        # The emergency guard already owns proof-based cleanup and may currently
        # be reclaiming space. Never use -k and interrupt an active cleanup.
        return [
            "/bin/launchctl",
            "kickstart",
            f"{domain}/com.anicca.emergency-disk-guard",
        ]
    if repair_class == "sandbox_recover":
        # gig-healthcheck owns the Docker/Colima/image preflight. Ask it to
        # reconcile now without killing an already running healthcheck.
        return [
            "/bin/launchctl",
            "kickstart",
            f"{domain}/ai.anicca.hf-gig-core-healthcheck",
        ]
    if repair_class in {"telegram_reconcile", "telegram_probe"}:
        # telegram_report first reconciles durable provider receipts, recovers
        # expired claims, then flushes only pending rows through the fenced
        # outbox. delivery_unknown is never blindly re-sent.
        return [
            sys.executable,
            str(Path(__file__).with_name("telegram_report.py")),
            "flush",
        ]
    return None


def dispatch(
    repair_class: str,
    *,
    uid: int,
    incident: dict[str, Any] | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    if repair_class == "ledger_reconcile":
        evidence = (
            incident.get("evidence")
            if isinstance(incident, dict)
            and isinstance(incident.get("evidence"), dict)
            else {}
        )
        pass_id = str(evidence.get("pass_id") or "")
        evidence_dir = Path(str(evidence.get("evidence_dir") or ""))
        if (
            not pass_id
            or evidence_dir.name != f"gig-pass-{pass_id}"
            or not evidence_dir.is_dir()
        ):
            return {
                "status": "dispatch_failed",
                "repair_class": repair_class,
                "error": "pass_evidence_identity_invalid",
            }
        command = [
            sys.executable,
            str(Path(__file__).with_name("application_ledger_heal.py")),
            "--evidence-dir",
            str(evidence_dir),
            "--pass-id",
            pass_id,
            "--ledger",
            str(Path.home() / "gig" / "applied.jsonl"),
            "--output",
            str(evidence_dir / "application-ledger-recovery.json"),
            "--screenshot",
            str(evidence_dir / "application-ledger-recovery.png"),
        ]
        result = runner(
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            return {
                "status": "dispatch_failed",
                "repair_class": repair_class,
                "returncode": int(result.returncode),
                "stderr_tail": str(result.stderr or "")[-500:],
            }
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {
                "status": "dispatch_failed",
                "repair_class": repair_class,
                "error": "ledger_healer_output_invalid",
            }
        return {
            **payload,
            "status": "dispatched",
            "repair_class": repair_class,
        }
    if repair_class in DIAGNOSTIC_CLASSES:
        diagnosis = _diagnose(repair_class, incident)
        if diagnosis.get("canary_passed") is not True:
            diagnosis.update(_patch_handoff(
                repair_class=repair_class,
                incident=incident,
                diagnosis=diagnosis,
                runner=runner,
            ))
        else:
            diagnosis["patch_handoff"] = "not_required"
        return diagnosis
    command = repair_command(repair_class, uid=uid)
    if command is None:
        return {
            "status": "deferred_unknown_class",
            "repair_class": repair_class,
        }
    if command[0] == "/bin/launchctl":
        control_plane = launchd_control_plane_probe(runner)
        if control_plane["mutation_allowed"] is not True:
            return {
                "status": "dispatch_failed",
                "repair_class": repair_class,
                "error": "blocked_control_plane",
                "control_plane_errors": control_plane["errors"],
                "side_effect_performed": False,
            }
    result = runner(
        command,
        shell=False,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        return {
            "status": "dispatch_failed",
            "repair_class": repair_class,
            "returncode": int(result.returncode),
            "stderr_tail": str(result.stderr or "")[-500:],
        }
    return {
        "status": "dispatched",
        "repair_class": repair_class,
        "returncode": 0,
    }
