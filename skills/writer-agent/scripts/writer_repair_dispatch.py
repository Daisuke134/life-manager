#!/usr/bin/env python3
"""Claim exactly one actionable Writer incident per tick and route it.

SSOT §9.0 Order 4: known failure classes go to deterministic runbooks, unknown
ones go to Terra, and Sol is never used for routine repair.

Boundaries this script keeps:

* Exactly one incident is claimed per invocation, under the incident queue's
  own advisory lock, so two overlapping ticks cannot work the same incident.
  The claim carries a lease taken through the queue's state machine.
* A blocking `revenue-set` incident outranks a non-blocking distribution one
  regardless of age: a free-distribution failure must never delay the paid
  shipment.
* A KNOWN route ends at a durable runbook *decision* receipt.  Executing the
  runbook command and resuming the run is Order 5, so no publisher side effect
  is produced here.
* An UNKNOWN route builds the deterministic investigation receipt and then asks
  Terra through the shared runner with `ARTICLE_MODEL_ROLE=terra`. Sol is unreachable:
  `sol-audit` additionally requires an `ARTICLE_SOL_TRIGGER_RECEIPT`, which this
  script never sets and actively removes from the child environment.
* The model call is the only slow step and it runs inside the held publication
  lock, so it is spent only when there is no publication progress to protect:
  either no backlog, or the routed incident itself owns the open circuit that
  is holding its pending destination.  Deferring on backlog alone would let the
  backlog become its own cause.  The deterministic route and all its receipts
  land on every tick regardless.
* Every routed incident produces a repair-attempt receipt.  Values the runtime
  genuinely does not measure (tokens, cost) are recorded as `unknown` with a
  reason; they are never reported as zero.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Iterator


SCRIPTS = Path(__file__).resolve().parent

TERRA_ROLE = "terra"
TERRA_PROVIDER = "codex"
TERRA_MODE = "judge"
# The installed reconciler fires every 300 seconds (ai.anicca.article-resume,
# StartInterval 300) and this dispatcher runs inside the held publication lock.
# One measured Terra judge call took 84.8s, so the bound must exceed that while
# leaving most of the interval to publication.
DEFAULT_TERRA_TIMEOUT_SECONDS = 120
# §9.3.1 escalation: bounded attempts, then degrade to the safest known state
# and stop until a new occurrence retriggers the incident.
DEFAULT_MAX_INVESTIGATION_SLICES = 3
# The same rule for a failure that never reaches an investigation at all.
DEFAULT_MAX_ROUTING_FAILURES = 3
# An investigation that reached a verdict is handed to the next stage exactly
# as a KNOWN runbook decision is, so it keeps its lease and stops consuming
# ticks. Releasing it instead would let a blocking revenue-set incident win
# selection on every tick forever and starve every other incident behind it.
VERDICT_HANDOFF_STATUSES = {"COMPLETED", "ALREADY_INVESTIGATED"}

PUBLICATION_PRIORITY_REASON = (
    "publication can still advance on this tick and this dispatcher runs inside "
    "the held publication lock; Order 4 repairs nothing this tick, so the model "
    "step waits for a tick with no publication progress to protect"
)
CIRCUIT_OWNER_REASON = (
    "the routed incident owns the open resume-failure circuit that is holding "
    "its pending destination, so this tick cannot publish that pair however "
    "long the lock is held; deferring here would make the backlog its own cause"
)

TOKENS_UNKNOWN_REASON = (
    "runtime/model-runner.sh and model-runner-support.py record provider health "
    "only; no token counter exists at the model boundary"
)
COST_UNKNOWN_REASON = (
    "no price table or billing receipt is joined to a model invocation in this "
    "runtime, so a cost figure would be invented"
)


def _module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:  # pragma: no cover - import machinery guard
        raise RuntimeError(f"cannot load {name}")
    spec.loader.exec_module(module)
    return module


incidents = _module("writer_incident_queue")
router = _module("writer_repair_router")
investigation = _module("writer_unknown_investigation")
evidence = _module("writer_observability_evidence")
trace = _module("writer_observability_trace")
session = _module("writer_repair_investigation_session")


def publication_progress(
    claimed: dict[str, Any], state_root: Path, backlog: bool,
    *, defer_model_always: bool = False,
) -> dict[str, Any]:
    """Decide whether the model step may spend publication-lock time.

    A pending backlog is not the same as publication progress. When the routed
    incident owns the open resume-failure circuit that is holding its own
    pending destination, this tick cannot publish that pair no matter how long
    it holds the lock: the circuit only opens after something diagnoses the
    failure, and nothing diagnoses it until this investigation runs. Deferring
    there closes the cycle on itself -- backlog keeps the model away, and the
    absent model keeps the backlog -- so the loop reports health while doing
    zero repair. The circuit receipt is the same durable signal the trace
    projection already uses to call that destination failed.
    """
    result: dict[str, Any] = {"backlog": backlog}
    if not backlog:
        result["routed_incident_blocks_publication"] = False
        result["decision"] = "RUN_MODEL"
        result["reason"] = "no publication backlog on this tick"
        return result

    if defer_model_always:
        result["routed_incident_blocks_publication"] = False
        result["decision"] = "DEFER_MODEL"
        result["reason"] = PUBLICATION_PRIORITY_REASON
        result["circuit_receipt"] = {
            "status": "deferred",
            "reason": "foreground publication owns this tick; Terra is deferred",
        }
        return result

    run_id = str(claimed.get("run_id") or "")
    destination = str(claimed.get("destination") or "")
    if not run_id or not destination:
        result["routed_incident_blocks_publication"] = False
        result["decision"] = "DEFER_MODEL"
        result["reason"] = PUBLICATION_PRIORITY_REASON
        result["circuit_receipt"] = {
            "status": "unknown",
            "reason": "incident names no run and destination, so it owns no circuit",
        }
        return result

    gates = state_root / "runs" / run_id / "gates"
    circuit_path = gates / "resume-failure-circuit.json"
    if not circuit_path.is_file():
        result["routed_incident_blocks_publication"] = False
        result["decision"] = "DEFER_MODEL"
        result["reason"] = PUBLICATION_PRIORITY_REASON
        result["circuit_receipt"] = {
            "status": "unknown",
            "reason": f"no circuit receipt at {circuit_path}",
        }
        return result

    circuit = json.loads(circuit_path.read_text(encoding="utf-8"))
    row = (circuit.get("pairs") or {}).get(destination)
    status = None
    publication_path = gates / "publication-state.json"
    if publication_path.is_file():
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
        entry = (publication.get("pairs") or {}).get(destination)
        if isinstance(entry, dict):
            status = entry.get("status")
    blocks = (
        isinstance(row, dict)
        and row.get("open") is True
        and status not in trace.SETTLED_DESTINATION_STATUSES
    )
    result["routed_incident_blocks_publication"] = blocks
    result["destination_status"] = status
    result["circuit_receipt"] = {
        "path": str(circuit_path),
        "sha256": _sha256(circuit_path),
        "open": bool(isinstance(row, dict) and row.get("open") is True),
    }
    result["decision"] = "RUN_MODEL" if blocks else "DEFER_MODEL"
    result["reason"] = CIRCUIT_OWNER_REASON if blocks else PUBLICATION_PRIORITY_REASON
    return result


# ---------------------------------------------------------------------------
# durable helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


@contextlib.contextmanager
def _queue_lock(queue_path: Path) -> Iterator[dict[str, Any]]:
    """Hold the incident queue's own advisory lock across a read/write pair."""
    lock_path = queue_path.with_name(f".{queue_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        queue = incidents._read(queue_path)
        yield queue
        incidents._atomic(queue_path, queue)


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------

def priority(item: dict[str, Any]) -> tuple[int, str, str]:
    """Blocking revenue-set work first, then oldest first, then stable by key."""
    blocking_revenue = (
        item.get("blocking") is True and item.get("revenue_role") == "revenue-set"
    )
    return (
        0 if blocking_revenue else 1,
        str(item.get("first_seen_at") or ""),
        str(item.get("fingerprint") or ""),
    )


# A CLAIMED incident is invisible to `select()`. Before checkpoints existed, a
# model call that ended TIMEOUT returned without ever releasing its lease, so
# the incident was stranded permanently: no later tick could select it, and
# `ingest` reopens only RESOLVED, so not even a new occurrence could rescue it.
# The live `note/ja` incident sits in exactly that state. This is a one-time,
# evidence-gated recovery that the loop performs for itself.
STRANDED_TERMINAL_MODEL_STATUSES = {"TIMEOUT"}

# A completed routing/investigation receipt is a handoff, not a live lease.
# These are the only model states that can be moved to WAIT after proving the
# dispatch owner has exited.  CHECKPOINTED is intentionally absent: it must
# remain RETRYable through the normal checkpoint path, never be guessed dead.
ORPHANED_TERMINAL_MODEL_STATUSES = {
    "COMPLETED", "ALREADY_INVESTIGATED", "EXHAUSTED", "FAILED", "TIMEOUT",
}

ACTIVE_PUBLICATION_PAIRS = {"note/ja", "substack/ja", "substack/en"}


def reclaim_stranded(
    queue: dict[str, Any], self_heal: Path, state_root: Path, observed_at: str,
) -> list[dict[str, Any]]:
    """Return leases stranded by the pre-checkpoint code to the selectable set.

    Deliberately narrow, so nothing live is ever stolen. An incident is
    reclaimed only when all three hold:

    * it is CLAIMED, so it is currently unselectable;
    * it has no investigation-session checkpoint, which the current code writes
      for every model-spending slice, so the absence proves the lease was taken
      by the pre-H3 path;
    * its own repair-attempt receipt for that exact lease records a terminal,
      non-continuable model status, which proves the attempt finished and that
      no process will ever come back to release the lease.

    A CLAIMED incident failing any of these is left untouched and reported.
    Liveness is never guessed from elapsed time.
    """
    reclaimed: list[dict[str, Any]] = []
    for fingerprint, item in queue.get("items", {}).items():
        if not isinstance(item, dict) or item.get("state") != "CLAIMED":
            continue
        lease_id = str(item.get("lease_id") or "")
        if not lease_id:
            continue
        if session.checkpoint_path(state_root, fingerprint).is_file():
            continue
        receipt_path = self_heal / "repair-attempts" / f"{fingerprint}-{lease_id}.json"
        if not receipt_path.is_file():
            continue
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        model = receipt.get("model")
        status = model.get("status") if isinstance(model, dict) else None
        if status not in STRANDED_TERMINAL_MODEL_STATUSES:
            continue
        item["state"] = "RETRY"
        item["next_action"] = "CLAIM"
        item.pop("lease_id", None)
        item["reclaimed_at"] = observed_at
        item["reclaim_reason"] = (
            f"lease {lease_id} was stranded CLAIMED by a terminal {status} model "
            "attempt written before investigation checkpoints existed, so no "
            "process would ever release it and no tick could select it"
        )
        reclaimed.append({
            "fingerprint": fingerprint,
            "lease_id": lease_id,
            "model_status": status,
            "repair_attempt_receipt": str(receipt_path),
        })
    if reclaimed:
        queue["updated_at"] = observed_at
    return reclaimed


def _live_dispatch_owner_pids(state_root: Path) -> list[int]:
    """Return other Writer repair-dispatch PIDs for this exact state root.

    A lease is never reclaimed from elapsed time.  The process table is only
    used as the negative proof needed by the receipt-gated recovery below;
    failure to read it is fail-closed (an empty list is not returned).
    """
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return [-1]
    if result.returncode != 0:
        return [-1]
    state_token = str(state_root.resolve())
    owners: list[int] = []
    for line in result.stdout.splitlines():
        match = re.match(r"\s*(\d+)\s+(.*)$", line)
        if match is None:
            continue
        pid = int(match.group(1))
        command = match.group(2)
        if pid == os.getpid():
            continue
        if "writer_repair_dispatch.py" not in command:
            continue
        # A launchd shell or a developer's `zsh -lc` can contain the Python
        # command as text while the child is running.  Count only the Python
        # interpreter process, not that parent shell, as a live owner.
        executable = command.split(None, 1)[0] if command.split(None, 1) else ""
        if not Path(executable).name.startswith("python"):
            continue
        if state_token not in command:
            continue
        owners.append(pid)
    return owners


def _read_receipt(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _receipt_proof(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": _sha256(path)}


def recover_orphaned_handoffs(
    queue: dict[str, Any], self_heal: Path, state_root: Path, observed_at: str,
) -> list[dict[str, Any]]:
    """Move only ownerless, receipt-backed CLAIMED handoffs to WAIT.

    The current Writer loop previously retained leases after a process exit.
    That state is invisible to ``select()`` and can block the whole repair
    lane.  Recovery is deliberately conservative: one live dispatch process or
    one missing/mismatched receipt leaves the item CLAIMED.  No runbook,
    model, publisher, or external service is called here.
    """
    if _live_dispatch_owner_pids(state_root):
        return []
    recovered: list[dict[str, Any]] = []
    for fingerprint, item in queue.get("items", {}).items():
        if not isinstance(item, dict) or item.get("state") != "CLAIMED":
            continue
        lease_id = str(item.get("lease_id") or "")
        if not lease_id:
            continue
        attempt_path = self_heal / "repair-attempts" / f"{fingerprint}-{lease_id}.json"
        attempt = _read_receipt(attempt_path)
        if (
            attempt is None
            or attempt.get("schema") != "writer.self-heal.repair-attempt"
            or attempt.get("version") != 1
            or attempt.get("fingerprint") != fingerprint
            or attempt.get("lease_id") != lease_id
        ):
            continue
        model = attempt.get("model")
        model_status = model.get("status") if isinstance(model, dict) else None
        route = attempt.get("route")
        proof: dict[str, Any] = {"attempt_receipt": _receipt_proof(attempt_path)}
        if route == "KNOWN":
            decision_path = self_heal / "runbook-decisions" / f"{fingerprint}-{lease_id}.json"
            decision = _read_receipt(decision_path)
            if (
                decision is None
                or decision.get("schema") != "writer.self-heal.runbook-decision"
                or decision.get("version") != 1
                or decision.get("fingerprint") != fingerprint
                or decision.get("lease_id") != lease_id
                or decision.get("route") != "KNOWN"
                or decision.get("executed") is not False
                or decision.get("next_action") != "EXECUTE_BOUNDED_RUNBOOK"
            ):
                continue
            proof["decision_receipt"] = _receipt_proof(decision_path)
            handoff_kind = "known-runbook"
        elif (
            route == "UNKNOWN"
            and model_status in ORPHANED_TERMINAL_MODEL_STATUSES
        ):
            investigation_path = self_heal / "investigations" / f"{fingerprint}-{lease_id}.json"
            investigation_receipt = _read_receipt(investigation_path)
            if (
                investigation_receipt is None
                or investigation_receipt.get("schema")
                != "writer.self-heal.unknown-investigation"
                or investigation_receipt.get("version") != 1
                or investigation_receipt.get("fingerprint") != fingerprint
            ):
                continue
            proof["investigation_receipt"] = _receipt_proof(investigation_path)
            handoff_kind = "unknown-investigation"
        else:
            continue
        try:
            incidents.wait_for_owner_recovery(
                queue, fingerprint, lease_id, attempt_path, observed_at,
                handoff_kind=handoff_kind,
                handoff_status=str(model_status or "unknown"),
                proof=proof,
            )
        except (OSError, ValueError, json.JSONDecodeError):
            # A receipt that changes under us is not evidence.  Leave the
            # lease claimed and let the next owner re-read it under the lock.
            continue
        recovered.append({
            "fingerprint": fingerprint,
            "lease_id": lease_id,
            "handoff_kind": handoff_kind,
            "model_status": model_status,
            "attempt_receipt": str(attempt_path),
        })
    if recovered:
        queue["updated_at"] = observed_at
    return recovered


def _quarantine_receipt_for_run(
    state_root: Path, run_id: str,
) -> Path | None:
    """Return a proof-bound duplicate-media quarantine receipt, if valid."""
    run_dir = state_root / "runs" / run_id
    gates = run_dir / "gates"
    state_path = gates / "publication-state.json"
    receipt_path = gates / "run-quarantine.json"
    if (
        run_dir.is_symlink() or not run_dir.is_dir()
        or gates.is_symlink() or not gates.is_dir()
        or state_path.is_symlink() or not state_path.is_file()
    ):
        return None
    receipt = _read_receipt(receipt_path)
    state = _read_receipt(state_path)
    if (
        receipt is None or state is None
        or receipt.get("type") != "run-quarantine"
        or receipt.get("version") != 1
        or receipt.get("reason") != "duplicate-media"
        or receipt.get("run_id") != run_id
        or receipt.get("state_sha256") != _sha256(state_path)
        or state.get("run_id") != run_id
        or state.get("publication_contract") != "active-four"
        or state.get("state_path") != str(state_path)
    ):
        return None
    pairs = state.get("pairs")
    if not isinstance(pairs, dict) or not ACTIVE_PUBLICATION_PAIRS.issubset(pairs):
        return None
    for pair in ACTIVE_PUBLICATION_PAIRS:
        entry = pairs.get(pair)
        if not isinstance(entry, dict) or entry.get("status") not in {"unavailable", "skipped"}:
            return None
        if any(
            entry.get(key) not in (None, "", {}, [])
            for key in ("live_url", "public_id", "receipt", "published_at", "effect", "readback", "existing_publication")
        ):
            return None
    if not isinstance(receipt.get("headline_sha256"), str):
        return None
    if not isinstance(receipt.get("body_sha256"), list) or not receipt["body_sha256"]:
        return None
    return receipt_path


def quarantine_invalid_run_handoffs(
    queue: dict[str, Any], state_root: Path, observed_at: str,
) -> list[dict[str, Any]]:
    """Hide OPEN/RETRY repair items for a proof-bound quarantined run."""
    quarantined: list[dict[str, Any]] = []
    receipts: dict[str, Path | None] = {}
    for fingerprint, item in queue.get("items", {}).items():
        if not isinstance(item, dict) or item.get("state") not in {"OPEN", "RETRY"}:
            continue
        run_id = str(item.get("run_id") or "")
        if not run_id:
            continue
        if run_id not in receipts:
            receipts[run_id] = _quarantine_receipt_for_run(state_root, run_id)
        receipt_path = receipts[run_id]
        if receipt_path is None:
            continue
        try:
            incidents.wait_for_quarantined_run(
                queue, fingerprint, run_id, receipt_path, observed_at,
            )
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        quarantined.append({
            "fingerprint": fingerprint,
            "run_id": run_id,
            "quarantine_receipt": str(receipt_path),
        })
    if quarantined:
        queue["updated_at"] = observed_at
    return quarantined


def select(queue: dict[str, Any]) -> dict[str, Any] | None:
    available = [
        item for item in queue.get("items", {}).values()
        if isinstance(item, dict) and item.get("state") in {"OPEN", "RETRY"}
    ]
    if not available:
        return None
    return min(available, key=priority)


# ---------------------------------------------------------------------------
# Terra
# ---------------------------------------------------------------------------

def terra_model_name(model_runner: Path) -> dict[str, Any]:
    """Read the model the runner binds to the terra role from the runner itself."""
    if not model_runner.is_file():
        return {"status": "unknown", "reason": f"model runner is absent: {model_runner}"}
    match = re.search(
        r'^CODEX_MODEL="([^"]+)"', model_runner.read_text(encoding="utf-8", errors="replace"),
        re.MULTILINE,
    )
    if match is None:
        return {
            "status": "unknown",
            "reason": "model runner does not declare an unindented CODEX_MODEL default",
        }
    name = match.group(1)
    if "sol" in name.lower():
        return {
            "status": "unknown",
            "reason": f"runner default model {name!r} is not a terra model; refusing to name it",
        }
    return {"status": "resolved", "name": name}


def terra_prompt(receipt: dict[str, Any], item: dict[str, Any]) -> str:
    gaps = ", ".join(receipt.get("evidence_gaps") or []) or "none recorded"
    return (
        "You are Terra, investigating one unknown Writer Agent failure.\n"
        "This is a read-only investigation. Do not publish, retry, mutate state, "
        "or take any external action.\n\n"
        f"run_id: {receipt.get('run_id')}\n"
        f"destination: {item.get('destination')}\n"
        f"failure_class: {item.get('failure_class') or item.get('classification')}\n"
        f"phase: {receipt.get('phase')}\n"
        f"observed_reason: {receipt.get('observed_reason')}\n"
        f"error_signature: {item.get('error_signature')}\n"
        f"evidence_gaps: {gaps}\n"
        f"next_action: {receipt.get('next_action')}\n\n"
        "Investigation receipt:\n"
        + json.dumps(receipt, ensure_ascii=False, indent=2)
        + "\n\nName the official primary documents that decide whether this "
        "publisher response is a content contract violation, and quote the exact "
        "sentence you rely on. If you cannot verify a claim, say so; never invent "
        "a URL, a quote, or a cause.\n"
    )


def continuation_prompt(checkpoint: dict[str, Any], receipt: dict[str, Any]) -> str:
    """Ask the already-open session to carry on, never to restart the work."""
    partial = (checkpoint.get("partial_findings") or {}).get("agent_messages") or []
    return (
        "Continue the investigation you already started in this session. Do not "
        "restart it and do not repeat work you have already done.\n\n"
        f"Slices used so far: {checkpoint.get('slice_count')} of "
        f"{checkpoint.get('max_slices')}.\n"
        "What you had produced when the previous slice ran out of time:\n"
        + json.dumps(partial, ensure_ascii=False, indent=2)
        + "\n\nFinish within this slice if you can. Reply with the JSON object "
        "required by the output schema. Set \"complete\" to false and fill "
        "\"remaining_work\" if you still need another slice; never invent a "
        "cause, a URL, or a quote to appear finished.\n"
        f"\nIncident fingerprint: {receipt.get('fingerprint')}\n"
    )


def invoke_terra(
    model_runner: Path, prompt: str, out_path: Path, timeout: int,
    defer: bool = False, defer_reason: str = "", *,
    state_root: Path, fingerprint: str, lease_id: str, observed_at: str,
    claimed: dict[str, Any], receipt: dict[str, Any], max_slices: int,
    deployed_commit: str | None = None,
) -> dict[str, Any]:
    """One bounded, resumable Terra slice through the existing model boundary.

    SSOT §9.3.1 H3 with §9.4 C1 and C3.  The slice is bounded exactly as before,
    but running out of budget now checkpoints instead of truncating: the partial
    findings and the Codex session identity are persisted and a later tick
    continues the same session.  The outcome is read from the JSONL event stream
    because `codex exec` exits only 0 or 1 and cannot name a failure class.
    """
    name = terra_model_name(model_runner)
    result: dict[str, Any] = {
        "role": TERRA_ROLE,
        "provider": TERRA_PROVIDER,
        "mode": TERRA_MODE,
        "runner": str(model_runner),
        "timeout_seconds": timeout,
    }
    result["name"] = name["name"] if name.get("status") == "resolved" else name
    if defer:
        # Publication owns this tick's lock time. The deterministic route and
        # every receipt above are already durable, so a later tick with no
        # publication progress to protect performs the model step against the
        # same CLAIMED incident.
        result["status"] = "DEFERRED_PUBLICATION_PRIORITY"
        result["reason"] = defer_reason or PUBLICATION_PRIORITY_REASON
        return result
    if not model_runner.is_file():
        result["status"] = "RUNNER_MISSING"
        return result
    result["runner_sha256"] = _sha256(model_runner)

    checkpoint = session.read_checkpoint(state_root, fingerprint)
    # A new occurrence OR a new deployed code version is a new input, so either
    # one resets the bounded budget. SSOT §9.3.1's prior art is Flagger, which
    # "does not retry until a new commit arrives".
    trigger = session.trigger_token(claimed.get("occurrence_count"), deployed_commit)
    result["max_slices"] = max_slices
    result["trigger"] = trigger

    # A new occurrence of the same failure is the new trigger that §9.3.1's
    # escalation rule waits for; until one arrives the budget stays spent.
    same_trigger = checkpoint is not None and checkpoint.get("trigger") == trigger
    used = int(checkpoint.get("slice_count", 0)) if same_trigger else 0
    result["slices_used"] = used

    if same_trigger and checkpoint.get("status") == "COMPLETE":
        # One investigation per incident: a finished one is never re-run for
        # the same trigger, because that would be a second investigation.
        result["status"] = "ALREADY_INVESTIGATED"
        result["reason"] = (
            "this incident's investigation already reached a verdict for this "
            "trigger; re-running it would be duplicate model spend"
        )
        result["session"] = checkpoint.get("session")
        result["verdict"] = checkpoint.get("verdict")
        return result

    if used >= max_slices:
        # Degrade to the safest known state and stop. Nothing is published,
        # nothing is retried, and the open resume-failure circuit is left
        # exactly as it is so the blocked destination stays blocked.
        result["status"] = "EXHAUSTED"
        result["reason"] = (
            f"the investigation used its {max_slices} bounded slices without a "
            "verdict; per SSOT §9.3.1 the loop degrades to the safest known "
            "state and stops until a new occurrence retriggers it"
        )
        result["session"] = (checkpoint or {}).get("session")
        result["partial_findings"] = (checkpoint or {}).get("partial_findings")
        if checkpoint is not None:
            exhausted = dict(checkpoint)
            exhausted["status"] = "EXHAUSTED"
            exhausted["updated_at"] = observed_at
            session.save_checkpoint(state_root, fingerprint, exhausted)
        return result

    resume_session_id: str | None = None
    if same_trigger and checkpoint and checkpoint.get("status") == "CONTINUABLE":
        guard = session.liveness(checkpoint)
        result["liveness"] = guard
        if not guard.get("safe_to_resume"):
            # Never put a second turn on a session another process still holds.
            result["status"] = "RESUME_BLOCKED_SESSION_BUSY"
            result["reason"] = guard.get("reason")
            result["session"] = checkpoint.get("session")
            return result
        resume_session_id = ((checkpoint.get("session") or {}).get("id")) or None
    elif (
        checkpoint
        and checkpoint.get("status") == "CONTINUABLE"
        and checkpoint.get("session", {}).get("id")
        and not same_trigger
    ):
        # A new trigger restores the budget; continuing the open session is
        # still cheaper and is still one investigation, not a second. A session
        # marked terminal is never reopened, whatever the trigger.
        guard = session.liveness(checkpoint)
        result["liveness"] = guard
        if guard.get("safe_to_resume"):
            resume_session_id = (checkpoint.get("session") or {}).get("id")

    verdict_schema = session.write_verdict_schema(state_root, fingerprint)
    result["verdict_schema_path"] = str(verdict_schema)

    prompt_path = out_path.with_suffix(".prompt.txt")
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(
        continuation_prompt(checkpoint, receipt) if resume_session_id else prompt,
        encoding="utf-8",
    )
    result["prompt_path"] = str(prompt_path)
    result["resumed_session_id"] = resume_session_id

    environment = dict(os.environ)
    environment["ARTICLE_PROVIDER"] = TERRA_PROVIDER
    environment["ARTICLE_MODEL_ROLE"] = TERRA_ROLE
    # sol-audit is only reachable with a trigger receipt. Routine repair must
    # never carry one, so drop any inherited value rather than trusting it.
    environment.pop("ARTICLE_SOL_TRIGGER_RECEIPT", None)

    slice_index = used + 1
    workspace = session.session_dir(state_root, fingerprint)
    workspace.mkdir(parents=True, exist_ok=True)
    run = session.run_slice(
        model_runner=model_runner, mode=TERRA_MODE, prompt_path=prompt_path,
        events_path=workspace / f"slice-{slice_index}.events.jsonl",
        last_message_path=workspace / f"slice-{slice_index}.last-message.txt",
        verdict_schema=verdict_schema, budget_seconds=timeout,
        resume_session_id=resume_session_id, environment=environment,
        stdout_path=workspace / f"slice-{slice_index}.stdout.txt",
        stderr_path=workspace / f"slice-{slice_index}.stderr.txt",
    )
    result["latency_ms"] = run["latency_ms"]
    result["return_code"] = run["return_code"]
    result["killed_at_budget"] = run["killed_at_budget"]
    result["events_path"] = run["events_path"]

    stream = session.parse_events(Path(run["events_path"]))
    result["event_count"] = stream["event_count"]
    result["deciding_event"] = stream["deciding_event"]
    session_id = stream["session_id"] or resume_session_id
    result["tokens"] = session.tokens_from(stream)

    verdict: dict[str, Any] | None = None
    if stream["stream_status"] == "COMPLETED":
        verdict, problem = session.parse_verdict(
            Path(run["last_message_path"]), stream,
        )
        result["status"] = "COMPLETED"
        result["verdict"] = verdict
        if problem:
            result["verdict_problem"] = problem
        status = "COMPLETE" if (verdict or {}).get("complete") is not False else "CONTINUABLE"
    elif stream["stream_status"] == "FAILED":
        result["status"] = "FAILED"
        result["failures"] = stream["failures"]
        result["stderr_excerpt"] = run["stderr_excerpt"]
        # A turn that failed before producing any agent output carries no
        # progress, so resuming it re-sends the same request and fails
        # identically -- it would spend the whole bound to learn nothing.
        # Production slice-1 was exactly this: a 400 invalid_json_schema
        # rejected 4.4s in, before any reasoning. Terminal for the session,
        # still counted against the bound.
        made_progress = bool(stream["agent_messages"])
        result["made_progress"] = made_progress
        status = "CONTINUABLE" if (session_id and made_progress) else "FAILED"
        if not made_progress:
            result["reason"] = (
                "the turn failed before producing any agent output, so the "
                "session holds no progress to continue and resuming it would "
                "repeat the identical failing request"
            )
    elif session_id:
        # H3: the budget ended the slice, but the session and the partial
        # findings survive, so this is a checkpoint and not a dead TIMEOUT.
        result["status"] = "CHECKPOINTED"
        result["reason"] = (
            f"the slice reached its {timeout}s budget with no terminal turn "
            "event; the session and its partial findings are persisted for "
            "continuation on a later tick"
        )
        status = "CONTINUABLE"
    else:
        # Nothing was learned and no session exists to continue: the honest
        # name for that is still TIMEOUT. It still consumed a slice, so it is
        # still counted against the bound -- otherwise a slice that reliably
        # learns nothing would spend model time on every tick forever.
        result["status"] = "TIMEOUT"
        result["reason"] = (
            "the slice produced no codex session id, so there is nothing to "
            "resume and nothing was learned"
        )
        result["stderr_excerpt"] = run["stderr_excerpt"]
        status = "FAILED"

    result["continuable"] = status == "CONTINUABLE"
    result["session"] = {"id": session_id}
    result["partial_findings"] = {
        "agent_messages": stream["agent_messages"],
        "advisory_errors": stream["advisory_errors"],
    }
    session.save_checkpoint(state_root, fingerprint, session.build_checkpoint(
        previous=checkpoint if same_trigger else None, fingerprint=fingerprint,
        status=status, slice_count=slice_index, max_slices=max_slices,
        trigger=trigger, observed_at=observed_at, lease_id=lease_id,
        session_id=session_id, run=run, stream=stream, verdict=verdict,
    ))
    return result


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def dispatch(
    *, state_root: Path, scripts: Path, registry_path: Path, model_runner: Path,
    observed_at: str, lease_id: str, terra_timeout: int,
    publication_backlog: bool, max_slices: int = DEFAULT_MAX_INVESTIGATION_SLICES,
    defer_model_always: bool = False,
    max_routing_failures: int = DEFAULT_MAX_ROUTING_FAILURES,
    max_code_rearm_rounds: int = incidents.DEFAULT_MAX_CODE_REARM_ROUNDS,
) -> dict[str, Any]:
    self_heal = state_root / "self-heal"
    queue_path = self_heal / "incident-queue.json"

    quarantined_run_handoffs: list[dict[str, Any]] = []
    reclaimed: list[dict[str, Any]] = []
    recovered_orphaned: list[dict[str, Any]] = []
    rearmed: list[dict[str, Any]] = []
    deployed_commit = session.read_deployed_commit(state_root)
    with _queue_lock(queue_path) as queue:
        # A duplicate-media run may have created remote drafts before its
        # local state was quarantined.  Hide only its receipt-backed OPEN/RETRY
        # repair items so a later canary cannot retry those drafts.
        quarantined_run_handoffs = quarantine_invalid_run_handoffs(
            queue, state_root, observed_at,
        )
        # Recover leases the pre-checkpoint code stranded, under the same
        # exclusive lock that guards selection, so a reclaim and a claim can
        # never interleave.
        reclaimed = reclaim_stranded(queue, self_heal, state_root, observed_at)
        # A completed handoff can still be stranded CLAIMED if its old owner
        # died after writing the receipts. Release only with owner-aware,
        # receipt-gated proof; ambiguous claims remain fail-closed.
        recovered_orphaned = recover_orphaned_handoffs(
            queue, self_heal, state_root, observed_at,
        )
        # A deploy is a new input. Without this, every incident exhausted under
        # the old code stays dead forever and a shipped repair can never be
        # validated by the thing it repaired.
        rearmed = incidents.rearm_on_new_code(
            queue, deployed_commit, observed_at, max_code_rearm_rounds,
        )
        chosen = select(queue)
        if chosen is None:
            return {
                "status": "NO_ACTIONABLE_INCIDENT", "observed_at": observed_at,
                "quarantined_run_handoffs": quarantined_run_handoffs,
                "reclaimed_stranded_leases": reclaimed,
                "recovered_orphaned_handoffs": recovered_orphaned,
                "rearmed_on_new_code": rearmed,
                "deployed_commit": deployed_commit,
            }
        fingerprint = str(chosen["fingerprint"])
        item = incidents.claim(queue, lease_id, observed_at, fingerprint)
        if item is None:  # pragma: no cover - select() already proved it claimable
            return {"status": "NO_ACTIONABLE_INCIDENT", "observed_at": observed_at}
        claimed = json.loads(json.dumps(item))

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    started = time.monotonic()
    attempt: dict[str, Any] = {
        "schema": "writer.self-heal.repair-attempt",
        "version": 1,
        "observed_at": observed_at,
        "fingerprint": fingerprint,
        "lease_id": lease_id,
        "attempt_count": claimed.get("attempt_count"),
        "run_id": claimed.get("run_id"),
        "artifact_id": claimed.get("artifact_id"),
        "destination": claimed.get("destination"),
        "revenue_role": claimed.get("revenue_role"),
        "blocking": claimed.get("blocking"),
        "phase": claimed.get("phase"),
        "failure_class": claimed.get("failure_class") or claimed.get("classification"),
        "error_signature": claimed.get("error_signature"),
        "tokens": {"status": "unknown", "reason": TOKENS_UNKNOWN_REASON},
        "cost": {"status": "unknown", "reason": COST_UNKNOWN_REASON},
    }
    if claimed.get("previous_fingerprint"):
        attempt["previous_fingerprint"] = claimed["previous_fingerprint"]

    outcome: dict[str, Any] = {
        "status": "ROUTED",
        "observed_at": observed_at,
        "fingerprint": fingerprint,
        "lease_id": lease_id,
    }
    if reclaimed:
        outcome["reclaimed_stranded_leases"] = reclaimed
    if quarantined_run_handoffs:
        outcome["quarantined_run_handoffs"] = quarantined_run_handoffs
    if recovered_orphaned:
        outcome["recovered_orphaned_handoffs"] = recovered_orphaned
    if rearmed:
        outcome["rearmed_on_new_code"] = rearmed
    attempt["deployed_commit"] = deployed_commit

    try:
        _route_and_receipt(
            state_root=state_root, scripts=scripts, registry=registry,
            model_runner=model_runner, observed_at=observed_at, lease_id=lease_id,
            terra_timeout=terra_timeout, publication_backlog=publication_backlog,
            defer_model_always=defer_model_always,
            max_slices=max_slices, deployed_commit=deployed_commit,
            fingerprint=fingerprint, claimed=claimed,
            attempt=attempt, outcome=outcome, self_heal=self_heal,
            queue_path=queue_path, started=started,
        )
    except (ValueError, OSError, json.JSONDecodeError) as error:
        # A claimed incident that cannot be routed must not strand its lease.
        # Record why, then hand it back through the queue's own state machine
        # so a later tick can reclaim it.
        attempt["route"] = "UNRESOLVED"
        attempt["error"] = f"{type(error).__name__}: {error}"
        attempt["runbook"] = {"status": "unknown", "reason": "routing did not complete"}
        attempt.setdefault("tool", _tool(scripts / "writer_repair_router.py"))
        attempt["model"] = {
            "status": "unknown",
            "reason": "no model verdict exists because routing did not complete",
        }
        attempt["latency_ms"] = {"total": int((time.monotonic() - started) * 1000)}
        attempt["next_action"] = "RECLAIM_AFTER_ROUTING_FAILURE"
        # §9.3.1 escalation: routing failure is bounded too. Without this the
        # incident claims, fails to route, releases its lease and is re-claimed
        # on the very next tick without limit -- the live `346972de...` incident
        # produced eleven identical receipts on a strict five-minute cadence.
        # The investigation-slice budget does not cover this, because routing
        # fails before any investigation starts.
        trigger = session.trigger_token(
            claimed.get("occurrence_count"), deployed_commit,
        )
        prior = (
            int(claimed.get("routing_failure_count", 0))
            if claimed.get("routing_failure_trigger") == trigger else 0
        )
        failure_count = prior + 1
        attempt["routing_failure_count"] = failure_count
        attempt["max_routing_failures"] = max_routing_failures
        exhausted = failure_count >= max_routing_failures
        if exhausted:
            attempt["next_action"] = "ESCALATE_AFTER_ROUTING_FAILURE_BUDGET_EXHAUSTED"
        path = _atomic(
            self_heal / "repair-attempts" / f"{fingerprint}-{lease_id}.json", attempt
        )
        reason = (
            f"routing failed {failure_count} times for this trigger without ever "
            "reaching a runbook or an investigation; per SSOT 9.3.1 the loop "
            "degrades to the safest known state and stops until a new "
            "occurrence retriggers it"
        )
        with _queue_lock(queue_path) as queue:
            if exhausted:
                incidents.escalate_exhausted(
                    queue, fingerprint, lease_id, path, observed_at,
                    kind="routing-failure", failure_count=failure_count,
                    trigger=trigger, reason=reason,
                    deployed_commit=deployed_commit,
                )
            else:
                incidents.retry(queue, fingerprint, lease_id, path, observed_at)
                item = queue["items"][fingerprint]
                item["routing_failure_count"] = failure_count
                item["routing_failure_trigger"] = trigger
        result = {
            "status": "ROUTING_EXHAUSTED" if exhausted else "ROUTING_FAILED",
            "observed_at": observed_at,
            "fingerprint": fingerprint, "lease_id": lease_id, "route": "UNRESOLVED",
            "error": attempt["error"], "repair_attempt_receipt": str(path),
            "routing_failure_count": failure_count,
        }
        if exhausted:
            result["reason"] = reason
        if reclaimed:
            result["reclaimed_stranded_leases"] = reclaimed
        if quarantined_run_handoffs:
            result["quarantined_run_handoffs"] = quarantined_run_handoffs
        if recovered_orphaned:
            result["recovered_orphaned_handoffs"] = recovered_orphaned
        return result
    return outcome


def _route_and_receipt(
    *, state_root: Path, scripts: Path, registry: dict[str, Any], model_runner: Path,
    observed_at: str, lease_id: str, terra_timeout: int,
    publication_backlog: bool, max_slices: int, deployed_commit: str | None,
    defer_model_always: bool,
    fingerprint: str,
    claimed: dict[str, Any], attempt: dict[str, Any], outcome: dict[str, Any],
    self_heal: Path, queue_path: Path, started: float,
) -> None:
    decision = router.route(
        {"items": {fingerprint: claimed}}, registry, fingerprint,
        state_root.resolve(), scripts.resolve(),
    )
    attempt["route"] = decision["route"]
    outcome["route"] = decision["route"]

    if decision["route"] == "KNOWN":
        receipt = {
            "schema": "writer.self-heal.runbook-decision",
            "version": 1,
            "observed_at": observed_at,
            "fingerprint": fingerprint,
            "lease_id": lease_id,
            "run_id": claimed.get("run_id"),
            "destination": claimed.get("destination"),
            "failure_class": attempt["failure_class"],
            "route": "KNOWN",
            "runbook_id": decision["runbook_id"],
            "runbook_version": decision["runbook_version"],
            "mode": decision["mode"],
            "command": decision["command"],
            "command_sha256": decision["command_sha256"],
            # Order 4 decides. Order 5 verifies in isolation, deploys, and runs it.
            "executed": False,
            "next_action": decision["next_action"],
        }
        path = _atomic(
            self_heal / "runbook-decisions" / f"{fingerprint}-{lease_id}.json", receipt
        )
        with _queue_lock(queue_path) as queue:
            incidents.register_runbook_decision(
                queue, fingerprint, lease_id, path, observed_at
            )
        attempt["runbook"] = {
            "runbook_id": decision["runbook_id"],
            "version": decision["runbook_version"],
            "mode": decision["mode"],
            "command_sha256": decision["command_sha256"],
            "executed": False,
        }
        attempt["tool"] = _tool(scripts / "writer_repair_router.py")
        attempt["model"] = {
            "status": "unknown",
            "reason": "a deterministic runbook decision uses no model",
        }
        attempt["decision_receipt"] = {"path": str(path), "sha256": _sha256(path)}
        attempt["next_action"] = decision["next_action"]
        outcome["runbook_decision_receipt"] = str(path)
        outcome["runbook_id"] = decision["runbook_id"]
    else:
        attempt["runbook"] = {
            "status": "unknown",
            "reason": "no runbook matched this failure class; route is UNKNOWN",
        }
        attempt["tool"] = _tool(scripts / "writer_unknown_investigation.py")
        run_id = router._run_id(claimed)
        index = evidence.build_evidence_index(
            state_root / "runs" / run_id, observed_at
        )
        index_path = _atomic(self_heal / f"evidence-index-{run_id}.json", index)
        receipt = investigation.investigate(
            {"items": {fingerprint: claimed}}, fingerprint, index,
            state_root.resolve(), observed_at,
        )
        receipt_path = _atomic(
            self_heal / "investigations" / f"{fingerprint}-{lease_id}.json", receipt
        )
        with _queue_lock(queue_path) as queue:
            incidents.register_investigation(
                queue, fingerprint, lease_id, receipt_path, observed_at
            )
        progress = publication_progress(
            claimed, state_root, publication_backlog,
            defer_model_always=defer_model_always,
        )
        attempt["publication_progress"] = progress
        model = invoke_terra(
            model_runner,
            terra_prompt(receipt, claimed),
            self_heal / "terra-investigations" / f"{fingerprint}-{lease_id}.txt",
            terra_timeout,
            progress["decision"] == "DEFER_MODEL",
            progress["reason"],
            state_root=state_root, fingerprint=fingerprint, lease_id=lease_id,
            observed_at=observed_at, claimed=claimed, receipt=receipt,
            max_slices=max_slices, deployed_commit=deployed_commit,
        )
        attempt["model"] = model
        # Tokens are measured from the event stream when the turn completed and
        # stay unknown with a reason otherwise. Cost has no price table joined
        # to it in this runtime, so it stays unknown either way.
        if isinstance(model.get("tokens"), dict):
            attempt["tokens"] = model["tokens"]
        attempt["evidence_index"] = {"path": str(index_path), "sha256": _sha256(index_path)}
        attempt["investigation_receipt"] = {
            "path": str(receipt_path), "sha256": _sha256(receipt_path),
            "cause_status": receipt.get("cause_status"),
            "evidence_gaps": receipt.get("evidence_gaps"),
        }
        # The deterministic receipt names the next action, except when the
        # bounded investigation budget is spent: §9.3.1 requires the loop to
        # degrade and stop rather than keep asking for the same work.
        attempt["next_action"] = (
            "ESCALATE_AFTER_INVESTIGATION_BUDGET_EXHAUSTED"
            if model.get("status") == "EXHAUSTED" else receipt["next_action"]
        )
        outcome["investigation_receipt"] = str(receipt_path)
        outcome["evidence_index"] = str(index_path)
        outcome["model_status"] = model.get("status")

    latency: dict[str, Any] = {"total": int((time.monotonic() - started) * 1000)}
    model_latency = attempt.get("model", {}).get("latency_ms")
    if isinstance(model_latency, int):
        latency["model"] = model_latency
    else:
        latency["model"] = {
            "status": "unknown",
            "reason": "no model call completed for this attempt",
        }
    attempt["latency_ms"] = latency
    attempt_path = _atomic(
        self_heal / "repair-attempts" / f"{fingerprint}-{lease_id}.json", attempt
    )
    outcome["repair_attempt_receipt"] = str(attempt_path)
    outcome["next_action"] = attempt["next_action"]

    # A lease bounds one tick's work, and `select()` sees only OPEN and RETRY,
    # so a lease held past the end of a tick makes the incident permanently
    # unselectable. It may therefore be retained in exactly one case: a genuine
    # handoff, where a named later stage owns the lease and the incident must
    # stop consuming ticks until that stage runs. A KNOWN runbook decision is
    # one such handoff; an investigation that reached a verdict is the other.
    # Everything else -- a checkpoint to continue, a deferral, a blocked
    # resume, a provider failure -- must be released or the work is lost.
    model_status = str(attempt.get("model", {}).get("status") or "")
    handoff = decision["route"] == "KNOWN" or model_status in VERDICT_HANDOFF_STATUSES
    if not handoff:
        with _queue_lock(queue_path) as queue:
            if model_status == "EXHAUSTED":
                incidents.escalate_exhausted(
                    queue, fingerprint, lease_id, attempt_path, observed_at,
                    kind="investigation-slices",
                    failure_count=int(attempt["model"].get("slices_used") or 0),
                    trigger=attempt["model"].get("trigger"),
                    reason=str(attempt["model"].get("reason") or ""),
                    deployed_commit=deployed_commit,
                )
            else:
                # A continuable checkpoint says "continue"; anything else keeps
                # the deterministic receipt's own next action so the handoff a
                # later stage reads is unchanged.
                incidents.continue_investigation(
                    queue, fingerprint, lease_id, attempt_path, observed_at,
                    "CONTINUE_INVESTIGATION"
                    if attempt.get("model", {}).get("continuable") is True
                    else attempt["next_action"],
                )
        outcome["lease_released"] = True


def _tool(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "sha256": {"status": "unknown", "reason": "tool is absent"}}
    return {"path": str(path), "sha256": _sha256(path)}


def recover_claims_only(
    *, state_root: Path, observed_at: str,
) -> dict[str, Any]:
    """Run only local recovery gates that cannot create external effects.

    ``article-resume-pending.sh`` invokes this mode while publication is
    paused.  It cannot select an incident, invoke Codex, execute a runbook, or
    call a publisher; it only isolates receipt-backed quarantined runs and
    makes receipt-backed ownerless claims visible as WAIT so the emergency
    brake can later be lifted safely.
    """
    self_heal = state_root / "self-heal"
    queue_path = self_heal / "incident-queue.json"
    if not queue_path.is_file():
        return {"status": "NO_INCIDENT_QUEUE", "observed_at": observed_at}
    with _queue_lock(queue_path) as queue:
        quarantined = quarantine_invalid_run_handoffs(
            queue, state_root, observed_at,
        )
        recovered = recover_orphaned_handoffs(
            queue, self_heal, state_root, observed_at,
        )
    return {
        "status": (
            "CLAIMS_RECOVERED"
            if recovered or quarantined else "NO_RECOVERABLE_CLAIMS"
        ),
        "observed_at": observed_at,
        "quarantined_run_handoffs": quarantined,
        "recovered_orphaned_handoffs": recovered,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--scripts", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--model-runner", required=True, type=Path)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument(
        "--recover-claims-only", action="store_true",
        help="recover only receipt-backed ownerless claims; never select or publish",
    )
    parser.add_argument("--lease-id")
    # The reconciler's own PRIORITY_PUBLICATION_READY signal. "1" means this
    # tick still owes publication work, so no model time may be spent here.
    parser.add_argument("--publication-backlog", choices=("0", "1"), default="0")
    parser.add_argument(
        "--defer-model-always", action="store_true",
        help="defer Terra even when the routed incident owns an open circuit",
    )
    parser.add_argument(
        "--terra-timeout-seconds", type=int,
        default=int(os.environ.get(
            "ARTICLE_REPAIR_TERRA_TIMEOUT_SECONDS", DEFAULT_TERRA_TIMEOUT_SECONDS
        )),
    )
    parser.add_argument(
        "--max-investigation-slices", type=int,
        default=int(os.environ.get(
            "ARTICLE_REPAIR_MAX_INVESTIGATION_SLICES",
            DEFAULT_MAX_INVESTIGATION_SLICES,
        )),
    )
    parser.add_argument(
        "--max-routing-failures", type=int,
        default=int(os.environ.get(
            "ARTICLE_REPAIR_MAX_ROUTING_FAILURES", DEFAULT_MAX_ROUTING_FAILURES,
        )),
    )
    parser.add_argument(
        "--max-code-rearm-rounds", type=int,
        default=int(os.environ.get(
            "ARTICLE_REPAIR_MAX_CODE_REARM_ROUNDS",
            incidents.DEFAULT_MAX_CODE_REARM_ROUNDS,
        )),
    )
    args = parser.parse_args()
    if not (args.state_root / "self-heal" / "incident-queue.json").is_file():
        print(json.dumps({"status": "NO_INCIDENT_QUEUE"}, separators=(",", ":")))
        return 0
    if args.recover_claims_only:
        outcome = recover_claims_only(
            state_root=args.state_root, observed_at=args.observed_at,
        )
        print(json.dumps(outcome, ensure_ascii=False, separators=(",", ":")))
        return 0
    outcome = dispatch(
        state_root=args.state_root,
        scripts=args.scripts,
        registry_path=args.registry,
        model_runner=args.model_runner,
        observed_at=args.observed_at,
        lease_id=args.lease_id or f"repair-{uuid.uuid4().hex}",
        terra_timeout=args.terra_timeout_seconds,
        max_slices=args.max_investigation_slices,
        max_routing_failures=args.max_routing_failures,
        max_code_rearm_rounds=args.max_code_rearm_rounds,
        publication_backlog=args.publication_backlog == "1",
        defer_model_always=args.defer_model_always,
    )
    print(json.dumps(outcome, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
