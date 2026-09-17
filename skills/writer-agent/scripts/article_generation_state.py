#!/usr/bin/env python3
"""Crash-safe pre-publication generation attempt classification.

The full article prompt may be retried only while the run is mechanically empty of
publication state, ledger rows, and generated/staged artifacts.  The prompt bytes and
run identity are immutable across retries.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION = 1
MAX_GENERATION_ATTEMPTS = 3
MAX_EMPTY_INTERRUPTION_RECOVERIES = 1
ALLOWED_PREPUBLICATION_FILES = {
    "article-daily-prompt.txt",
    "git-hash.txt",
    "model-stdout.log",
    "gates/generation-state.json",
    "gates/.generation-state.json.lock",
    "gates/strategy-consumption.json",
    "gates/quality-replacement.json",
    "gates/media-create-required.json",
    # The selected demand route is a durable pre-publication receipt. Keep it
    # in place during an interrupted retry so the owner-fence can restore the
    # exact in-progress card without selecting a second topic.
    "gates/topic-route-input.json",
    "gates/topic-route.json",
    # The wrapper's resume owner-fence is also a durable pre-publication
    # receipt. It records the exact queued card before generation begins and
    # must survive a safe retry boundary without being mistaken for output.
    "gates/topic-card-resume.json",
}

# Wrapper-owned runtime infrastructure inside the run dir. These are never
# generation artifacts and never block a safe resume boundary.
# research-sources/ and research/ are ephemeral research scratch:
# sandbox-free agents npm-install / uv-venv sample repos there, leaving
# symlinks that crash archival. They are never publication artifacts, so
# they are excluded from the interruption manifest entirely.
ALLOWED_PREPUBLICATION_PREFIXES = (
    "gates/judge-broker/",
    "research-sources/",
    "research/",
)


def _is_allowed_prepublication(relative: str) -> bool:
    return relative in ALLOWED_PREPUBLICATION_FILES or relative.startswith(
        ALLOWED_PREPUBLICATION_PREFIXES
    )


class GenerationInvariant(ValueError):
    """The run is not provably safe for a full-prompt generation retry."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_sha256(manifest: list[dict[str, str]]) -> str:
    payload = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _state_path(run_dir: Path) -> Path:
    return run_dir / "gates" / "generation-state.json"


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != VERSION:
        raise GenerationInvariant("invalid generation state")
    return value


def _charged_attempt_count(state: dict[str, Any]) -> int:
    """Count generation attempts while forgiving one zero-artifact interruption.

    A terminated provider invocation that created no publication candidate must
    remain auditable, but charging the only empty interruption against the
    article budget can permanently strand an otherwise untouched daily run.
    Further empty interruptions are charged, keeping recovery bounded.
    """

    attempts = state.get("attempts", [])
    if not isinstance(attempts, list):
        raise GenerationInvariant("generation attempts are invalid")
    empty_interruptions = sum(
        1
        for attempt in attempts
        if isinstance(attempt, dict)
        and attempt.get("status") == "interrupted-safe"
        and attempt.get("archive_manifest") == []
    )
    free_recoveries = int(
        state.get(
            "maximum_empty_interruption_recoveries",
            MAX_EMPTY_INTERRUPTION_RECOVERIES,
        )
    )
    if free_recoveries < 0 or free_recoveries > MAX_EMPTY_INTERRUPTION_RECOVERIES:
        raise GenerationInvariant("empty interruption recovery budget is invalid")
    return len(attempts) - min(empty_interruptions, free_recoveries)


def _failed_before_publication(state: dict[str, Any]) -> bool:
    attempts = state.get("attempts")
    return bool(
        state.get("status") == "provider-failed-ambiguous"
        and isinstance(attempts, list)
        and attempts
        and isinstance(attempts[-1].get("return_code"), int)
        and attempts[-1]["return_code"] != 0
        and attempts[-1].get("boundary") == "prepublication-empty"
    )


def _lock(path: Path):
    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _validate_boundary(run_dir: Path, run_id: str, prompt_file: Path) -> Path:
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise GenerationInvariant("run directory is missing or symlinked")
    resolved = run_dir.resolve(strict=True)
    if resolved.name != run_id:
        raise GenerationInvariant("run identity does not match its directory")
    expected_prompt = resolved / "article-daily-prompt.txt"
    if prompt_file.is_symlink() or not prompt_file.is_file():
        raise GenerationInvariant("prompt is missing or symlinked")
    if prompt_file.resolve(strict=True) != expected_prompt:
        raise GenerationInvariant("prompt is outside the immutable run")
    return resolved


def _ledger_has_run(ledger: Path, run_id: str) -> bool:
    if not ledger.exists():
        return False
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(row, dict) and row.get("run_id") == run_id:
            return True
    return False


def ledger_has_public_effect(ledger: Path, run_id: str) -> bool:
    """A draft-stage bookkeeping row (published false, no live URL) is not a
    public side effect; only published/live rows block a same-prompt resume."""
    if not ledger.exists():
        return False
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or row.get("run_id") != run_id:
            continue
        live_url = row.get("live_url")
        if (
            row.get("published") is True
            or (isinstance(live_url, str) and bool(live_url.strip()))
            or row.get("state") == "live"
            or row.get("reality_gate") == "PASS"
        ):
            return True
    return False


def _adoption_manifests(run_dir: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    drafts: list[dict[str, str]] = []
    for lang in ("ja", "en"):
        path = run_dir / f"article-{lang}.md"
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise GenerationInvariant(f"article-{lang}.md is not a current regular draft")
        drafts.append({"path": path.name, "sha256": file_sha256(path)})

    excluded = {
        "gates/.generation-state.json.lock",
        "gates/generation-state.json",
        "gates/prepublication-adoption.json",
    }
    artifacts: list[dict[str, str]] = []
    for path in sorted(run_dir.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(run_dir).as_posix()
        selected = (
            relative.startswith("gates/")
            and not relative.startswith("gates/judge-broker/")
            and relative not in excluded
        ) or (
            "/" not in relative
            and relative
            not in {
                "article-daily-prompt.txt",
                "article-ja.md",
                "article-en.md",
                "git-hash.txt",
                "model-stdout.log",
            }
        )
        if not selected:
            continue
        if path.is_symlink() or not path.is_file():
            raise GenerationInvariant(f"adoption artifact is not regular: {relative}")
        artifacts.append({"path": relative, "sha256": file_sha256(path)})
    return drafts, artifacts


def _adoption_receipt_hash(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "receipt_sha256"}
    return hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _adoption_receipt_matches(
    receipt: Any,
    run_id: str,
    prompt_sha256: str,
    drafts: list[dict[str, str]],
    artifacts: list[dict[str, str]],
    state_before_sha256: str | None = None,
) -> bool:
    return bool(
        isinstance(receipt, dict)
        and receipt.get("schema") == "writer.prepublication-adoption"
        and receipt.get("version") == 1
        and receipt.get("from_status") == "provider-failed-ambiguous"
        and receipt.get("to_status") == "quality-repair-ready"
        and receipt.get("publication_state_absent") is True
        and receipt.get("public_ledger_rows") == 0
        and receipt.get("receipt_sha256") == _adoption_receipt_hash(receipt)
        and receipt.get("artifact_manifest_sha256") == manifest_sha256(artifacts)
        and receipt.get("run_id") == run_id
        and receipt.get("prompt_sha256") == prompt_sha256
        and receipt.get("draft_manifest") == drafts
        and receipt.get("artifact_manifest") == artifacts
        and (
            state_before_sha256 is None
            or receipt.get("generation_state_before_sha256") == state_before_sha256
        )
    )


def _adopted_staged_prepublication(
    run_dir: Path,
    run_id: str,
    prompt_file: Path,
    ledger: Path,
    state: dict[str, Any],
) -> bool:
    """Allow one same-prompt retry for a staged provider failure with no quality receipt.

    A provider can return nonzero after writing drafts and before any quality or
    publication gate exists.  Adoption preserves those bytes, but there is no
    quality-repair owner to run in that shape.  Resume is safe only when the
    adoption receipt still binds every staged byte and no external/publication
    marker has appeared.
    """
    if state.get("status") != "quality-repair-ready":
        return False
    gates = run_dir / "gates"
    if any(
        (gates / name).exists() or (gates / name).is_symlink()
        for name in (
            "quality-repair-state.json",
            "quality-self-heal.json",
            "quality-self-heal-final.json",
            "terminal-quality-blocked.json",
            "publication-state.json",
        )
    ):
        return False
    if ledger_has_public_effect(ledger, run_id):
        return False
    receipt_path = gates / "prepublication-adoption.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        return False
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        drafts, artifacts = _adoption_manifests(run_dir)
    except (OSError, TypeError, ValueError, json.JSONDecodeError, GenerationInvariant):
        return False
    if _adoption_receipt_matches(
        receipt,
        run_id,
        str(state.get("prompt_sha256", "")),
        drafts,
        artifacts,
    ):
        return True
    # Resume bookkeeping may add one of the explicitly allowed pre-publication
    # receipts after adoption (for example topic-card-resume.json).  Preserve
    # the original manifest as an immutable subset and accept only regular,
    # allowlisted additions; any changed or unexpected byte remains fenced.
    if not isinstance(receipt, dict):
        return False
    recorded_drafts = receipt.get("draft_manifest")
    recorded_artifacts = receipt.get("artifact_manifest")
    if not isinstance(recorded_drafts, list) or not isinstance(recorded_artifacts, list):
        return False
    current_by_path = {
        item["path"]: item["sha256"] for item in [*drafts, *artifacts]
    }
    for item in [*recorded_drafts, *recorded_artifacts]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("sha256"), str)
            or item["path"] not in current_by_path
            or current_by_path[item["path"]] != item["sha256"]
        ):
            return False
    recorded_paths = {
        item["path"]
        for item in [*recorded_drafts, *recorded_artifacts]
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    added = set(current_by_path) - recorded_paths
    if any(not _is_allowed_prepublication(path) for path in added):
        return False
    return (
        receipt.get("schema") == "writer.prepublication-adoption"
        and receipt.get("version") == 1
        and receipt.get("run_id") == run_id
        and receipt.get("prompt_sha256") == state.get("prompt_sha256")
        and receipt.get("artifact_manifest_sha256") == manifest_sha256(recorded_artifacts)
        and receipt.get("receipt_sha256") == _adoption_receipt_hash(receipt)
        and receipt.get("publication_state_absent") is True
        and receipt.get("public_ledger_rows") == 0
    )


def _adopted_current_prepublication(
    run_dir: Path,
    run_id: str,
    prompt_file: Path,
    ledger: Path,
    state: dict[str, Any],
) -> bool:
    """Recognize an exact adoption receipt after quality artifacts were added.

    Once a provider has produced quality receipts, the staged-resume predicate
    intentionally no longer applies.  The run is still safely movable when its
    adoption receipt binds the complete current manifest and no public effect
    exists; this lets a pruned immutable release be replaced without copying
    prompt references by hand.
    """
    if state.get("status") != "quality-repair-ready":
        return False
    if (run_dir / "gates/publication-state.json").exists() or ledger_has_public_effect(
        ledger, run_id
    ):
        return False
    receipt_path = run_dir / "gates/prepublication-adoption.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        return False
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        drafts, artifacts = _adoption_manifests(run_dir)
    except (OSError, TypeError, ValueError, json.JSONDecodeError, GenerationInvariant):
        return False
    return _adoption_receipt_matches(
        receipt,
        run_id,
        str(state.get("prompt_sha256", "")),
        drafts,
        artifacts,
    )


def adopt_prepublication(
    run_dir: Path, run_id: str, prompt_file: Path, ledger: Path
) -> dict[str, Any]:
    resolved = _validate_boundary(run_dir, run_id, prompt_file)
    state_path = _state_path(resolved)
    receipt_path = resolved / "gates/prepublication-adoption.json"
    with _lock(state_path):
        state = _load(state_path)
        if (
            state.get("run_id") != run_id
            or state.get("run_dir") != str(resolved)
            or state.get("prompt_path") != str(prompt_file.resolve(strict=True))
            or state.get("prompt_sha256") != file_sha256(prompt_file)
        ):
            raise GenerationInvariant("prompt or run identity changed")
        publication_state = resolved / "gates/publication-state.json"
        if publication_state.exists() or publication_state.is_symlink():
            raise GenerationInvariant("publication-state-exists")
        if ledger_has_public_effect(ledger, run_id):
            raise GenerationInvariant("ledger-public-effect-exists")
        drafts, artifacts = _adoption_manifests(resolved)

        if state.get("status") == "quality-repair-ready":
            if _adopted_staged_prepublication(
                resolved, run_id, prompt_file, ledger, state
            ):
                return {"action": "unchanged", "status": "quality-repair-ready"}
            if receipt_path.is_symlink() or not receipt_path.is_file():
                raise GenerationInvariant("adoption receipt is missing")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            transitions = state.get("transitions")
            transition = transitions[-1] if isinstance(transitions, list) and transitions else {}
            if (
                not _adoption_receipt_matches(
                    receipt, run_id, state["prompt_sha256"], drafts, artifacts
                )
                or transition.get("action") != "adopt-prepublication"
                or transition.get("receipt_sha256") != receipt.get("receipt_sha256")
            ):
                raise GenerationInvariant("adoption receipt does not match current evidence")
            return {"action": "unchanged", "status": "quality-repair-ready"}

        if state.get("status") != "provider-failed-ambiguous":
            raise GenerationInvariant("generation state is not adoptable")
        attempts = state.get("attempts")
        if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
            raise GenerationInvariant("generation attempts are invalid")
        maximum = int(state.get("maximum_attempts", MAX_GENERATION_ATTEMPTS))
        last = attempts[-1]
        boundary = last.get("boundary")
        non_resumable = bool(
            last.get("status") == "provider-failed-ambiguous"
            and isinstance(last.get("return_code"), int)
            and last["return_code"] != 0
            and isinstance(boundary, str)
            and boundary.startswith("generated-or-staged-artifacts:")
        )
        if _charged_attempt_count(state) < maximum and not non_resumable:
            raise GenerationInvariant("generation attempt remains safely resumable")
        state_before_sha256 = file_sha256(state_path)
        if receipt_path.exists() or receipt_path.is_symlink():
            if receipt_path.is_symlink() or not receipt_path.is_file():
                raise GenerationInvariant("adoption receipt is not regular")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if not _adoption_receipt_matches(
                receipt,
                run_id,
                state["prompt_sha256"],
                drafts,
                artifacts,
                state_before_sha256,
            ):
                raise GenerationInvariant("orphan adoption receipt does not match current evidence")
            action = "recovered"
        else:
            receipt = {
                "schema": "writer.prepublication-adoption",
                "version": 1,
                "run_id": run_id,
                "adopted_at": utc_now(),
                "from_status": "provider-failed-ambiguous",
                "to_status": "quality-repair-ready",
                "generation_state_before_sha256": state_before_sha256,
                "prompt_sha256": state["prompt_sha256"],
                "draft_manifest": drafts,
                "artifact_manifest": artifacts,
                "artifact_manifest_sha256": manifest_sha256(artifacts),
                "publication_state_absent": True,
                "public_ledger_rows": 0,
            }
            receipt["receipt_sha256"] = _adoption_receipt_hash(receipt)
            _atomic_write(receipt_path, receipt)
            action = "adopted"
        state["status"] = "quality-repair-ready"
        state["updated_at"] = receipt["adopted_at"]
        state.setdefault("transitions", []).append(
            {
                "action": "adopt-prepublication",
                "at": receipt["adopted_at"],
                "from_status": receipt["from_status"],
                "to_status": receipt["to_status"],
                "receipt_sha256": receipt["receipt_sha256"],
            }
        )
        _atomic_write(state_path, state)
        return {"action": action, "status": "quality-repair-ready"}


def prepublication_empty(run_dir: Path, run_id: str, ledger: Path) -> tuple[bool, str]:
    if (run_dir / "gates" / "publication-state.json").exists():
        return False, "publication-state-exists"
    if ledger_has_public_effect(ledger, run_id):
        return False, "ledger-row-exists"
    observed = {
        str(path.relative_to(run_dir))
        for path in run_dir.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    unexpected = sorted(
        path for path in observed if not _is_allowed_prepublication(path)
    )
    if unexpected:
        return False, f"generated-or-staged-artifacts:{','.join(unexpected)}"
    return True, "prepublication-empty"


def initialize(run_dir: Path, run_id: str, prompt_file: Path, ledger: Path) -> dict[str, Any]:
    resolved = _validate_boundary(run_dir, run_id, prompt_file)
    state_path = _state_path(resolved)
    prompt_hash = file_sha256(prompt_file)
    with _lock(state_path):
        if state_path.exists():
            state = _load(state_path)
            if (
                state.get("run_id") != run_id
                or state.get("prompt_sha256") != prompt_hash
            ):
                raise GenerationInvariant("generation identity is immutable")
            return state
        safe, reason = prepublication_empty(resolved, run_id, ledger)
        if not safe:
            raise GenerationInvariant(reason)
        state = {
            "version": VERSION,
            "run_id": run_id,
            "run_dir": str(resolved),
            "prompt_path": str(prompt_file.resolve(strict=True)),
            "prompt_sha256": prompt_hash,
            "status": "prepared",
            "maximum_attempts": MAX_GENERATION_ATTEMPTS,
            "maximum_empty_interruption_recoveries": (
                MAX_EMPTY_INTERRUPTION_RECOVERIES
            ),
            "attempts": [],
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        _atomic_write(state_path, state)
        return state


def rebind_release(
    run_dir: Path,
    run_id: str,
    prompt_file: Path,
    ledger: Path,
    current_root: Path,
) -> dict[str, Any]:
    """Move a safely resumable prompt from a pruned release to this release."""
    resolved = _validate_boundary(run_dir, run_id, prompt_file)
    state_path = _state_path(resolved)
    current_root = current_root.resolve(strict=True)
    releases_dir = current_root.parents[2]
    if Path(*current_root.parts[-2:]) != Path("skills/writer-agent"):
        raise GenerationInvariant("current root is not a writer-agent release path")
    with _lock(state_path):
        state = _load(state_path)
        staged_resume = _adopted_staged_prepublication(
            resolved, run_id, prompt_file, ledger, state
        )
        adopted_resume = staged_resume or _adopted_current_prepublication(
            resolved, run_id, prompt_file, ledger, state
        )
        allowed_statuses = {
            "provider-failed-safe",
            "provider-failed-ambiguous",
            "interrupted-safe",
        }
        if adopted_resume:
            allowed_statuses.add("quality-repair-ready")
        if state.get("run_id") != run_id or state.get("status") not in allowed_statuses:
            raise GenerationInvariant("generation state is not safely resumable")
        safe, reason = prepublication_empty(resolved, run_id, ledger)
        if adopted_resume:
            safe, reason = True, "adopted-staged-prepublication"
        if not safe:
            raise GenerationInvariant(reason)
        original = prompt_file.read_bytes()
        if state.get("prompt_sha256") != hashlib.sha256(original).hexdigest():
            raise GenerationInvariant("prompt hash does not match generation state")
        patterns = [
            re.compile(
                re.escape(str(releases_dir)).encode()
                + rb"/[^/\s`\"']+/skills/writer-agent"
            ),
            re.compile(
                re.escape(
                    str(Path(os.environ.get("LOOPS_ROOT", "~/loops")).expanduser() / "current")
                ).encode()
                + rb"/skills/writer-agent"
            ),
        ]
        roots = {
            match
            for pattern in patterns
            for match in pattern.findall(original)
        }
        if not roots:
            raise GenerationInvariant("prompt contains no writer release root")
        updated = original
        for pattern in patterns:
            updated = pattern.sub(str(current_root).encode(), updated)
        if updated == original:
            return {"action": "unchanged", "prompt_sha256": state["prompt_sha256"]}
        _atomic_write_bytes(prompt_file, updated)
        previous_sha = state["prompt_sha256"]
        state["prompt_sha256"] = hashlib.sha256(updated).hexdigest()
        state["updated_at"] = utc_now()
        state.setdefault("release_rebindings", []).append(
            {
                "at": state["updated_at"],
                "from": sorted(root.decode() for root in roots),
                "to": str(current_root),
                "previous_prompt_sha256": previous_sha,
            }
        )
        _atomic_write(state_path, state)
        if adopted_resume:
            adoption_path = resolved / "gates/prepublication-adoption.json"
            adoption = json.loads(adoption_path.read_text(encoding="utf-8"))
            adoption["prompt_sha256"] = state["prompt_sha256"]
            adoption["receipt_sha256"] = _adoption_receipt_hash(adoption)
            _atomic_write(adoption_path, adoption)
        return {"action": "rebound", "prompt_sha256": state["prompt_sha256"]}


def begin(
    run_dir: Path,
    run_id: str,
    prompt_file: Path,
    ledger: Path,
    owner_pid: int | None = None,
) -> dict[str, Any]:
    resolved = _validate_boundary(run_dir, run_id, prompt_file)
    state_path = _state_path(resolved)
    if not state_path.exists():
        initialize(resolved, run_id, prompt_file, ledger)
    with _lock(state_path):
        state = _load(state_path)
        if state.get("run_id") != run_id or state.get("prompt_sha256") != file_sha256(prompt_file):
            raise GenerationInvariant("prompt or run identity changed")
        staged_resume = _adopted_staged_prepublication(
            resolved, run_id, prompt_file, ledger, state
        )
        safe, reason = prepublication_empty(resolved, run_id, ledger)
        if staged_resume:
            safe, reason = True, "adopted-staged-prepublication"
        quality_reroute = _quality_reroute_pending(resolved, run_id, ledger)
        if not safe and not quality_reroute:
            raise GenerationInvariant(reason)
        allowed_statuses = {
            "prepared",
            "provider-failed-safe",
            "interrupted-safe",
        }
        if _failed_before_publication(state):
            allowed_statuses.add("provider-failed-ambiguous")
        if staged_resume:
            allowed_statuses.add("quality-repair-ready")
        if quality_reroute:
            allowed_statuses.add("provider-returned")
        if state.get("status") not in allowed_statuses:
            raise GenerationInvariant("generation attempt is not safely resumable")
        if _charged_attempt_count(state) >= int(
            state.get("maximum_attempts", MAX_GENERATION_ATTEMPTS)
        ):
            raise GenerationInvariant("generation attempt limit exhausted")
        attempt = len(state.get("attempts", [])) + 1
        state.setdefault("attempts", []).append(
            {
                "attempt": attempt,
                "started_at": utc_now(),
                "status": "invoking",
                "owner_pid": owner_pid,
            }
        )
        state["status"] = "invoking"
        state["updated_at"] = utc_now()
        _atomic_write(state_path, state)
        return state


def _quality_reroute_pending(
    run_dir: Path, run_id: str, ledger: Path
) -> bool:
    if (run_dir / "gates" / "publication-state.json").exists():
        return False
    if ledger_has_public_effect(ledger, run_id):
        return False
    quality_path = run_dir / "gates" / "quality-self-heal.json"
    try:
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    if not (
        quality
        and quality.get("version") == 2
        and quality.get("attempt") == 1
        and quality.get("action") == "reroute"
    ):
        return False
    records = quality.get("quality")
    if not isinstance(records, dict):
        return False
    for lang in ("ja", "en"):
        article = run_dir / f"article-{lang}.md"
        if (
            not article.is_file()
            or article.is_symlink()
            or records.get(lang, {}).get("article_sha256")
            != file_sha256(article)
        ):
            return False
    return True


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def recover_orphan(
    run_dir: Path,
    run_id: str,
    prompt_file: Path,
    ledger: Path,
    minimum_age_seconds: int = 60,
) -> dict[str, Any]:
    """Archive an invoking attempt only after its recorded owner disappeared."""

    resolved = _validate_boundary(run_dir, run_id, prompt_file)
    state_path = _state_path(resolved)
    with _lock(state_path):
        state = _load(state_path)
        attempts = state.get("attempts", [])
        if (
            state.get("status") != "invoking"
            or not isinstance(attempts, list)
            or not attempts
            or attempts[-1].get("status") != "invoking"
        ):
            raise GenerationInvariant("generation attempt is not invoking")
        owner_pid = attempts[-1].get("owner_pid")
        if isinstance(owner_pid, int) and _pid_is_alive(owner_pid):
            raise GenerationInvariant("generation owner is still alive")
        updated = datetime.fromisoformat(
            str(state.get("updated_at", "")).replace("Z", "+00:00")
        )
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        if age < minimum_age_seconds:
            raise GenerationInvariant("generation orphan lease is not stale")
    return archive_interrupted(
        resolved, run_id, prompt_file, ledger, 143
    )


def record_result(
    run_dir: Path, run_id: str, prompt_file: Path, ledger: Path, return_code: int
) -> dict[str, Any]:
    resolved = _validate_boundary(run_dir, run_id, prompt_file)
    state_path = _state_path(resolved)
    with _lock(state_path):
        state = _load(state_path)
        attempts = state.get("attempts", [])
        if (
            state.get("run_id") != run_id
            or state.get("prompt_sha256") != file_sha256(prompt_file)
            or state.get("status") != "invoking"
            or not isinstance(attempts, list)
            or not attempts
            or attempts[-1].get("status") != "invoking"
        ):
            raise GenerationInvariant("generation result has no matching active attempt")
        safe, reason = prepublication_empty(resolved, run_id, ledger)
        if return_code == 75 and safe:
            status = "provider-failed-safe"
        elif return_code == 0:
            status = "provider-returned"
        else:
            status = "provider-failed-ambiguous"
        attempts[-1].update(
            {
                "finished_at": utc_now(),
                "return_code": return_code,
                "status": status,
                "boundary": reason,
            }
        )
        state["status"] = status
        state["updated_at"] = utc_now()
        _atomic_write(state_path, state)
        return state


def archive_interrupted(
    run_dir: Path,
    run_id: str,
    prompt_file: Path,
    ledger: Path,
    return_code: int,
) -> dict[str, Any]:
    """Archive a terminated prepublication attempt and make the same prompt resumable."""
    # A bounded timeout or SIGINT/SIGTERM archives a still-active attempt; a classified retryable
    # provider failure (75) that only staged artifacts may also archive, so
    # the same immutable prompt can resume instead of stranding the run.
    if return_code in {124, 130, 143}:
        allowed_statuses = {"invoking", "interruption-archiving"}
    elif return_code == 75:
        # provider-failed-ambiguous: retryable failure that staged artifacts.
        # provider-returned: the agent finished without publication (e.g. a
        # fail-closed carry-over); with no public side effect its staged
        # artifacts may archive so the same immutable prompt can re-run.
        allowed_statuses = {
            "provider-failed-ambiguous",
            "provider-returned",
            "interruption-archiving",
        }
    else:
        raise GenerationInvariant(
            "only bounded timeout/SIGINT/SIGTERM interruption or an "
            "ambiguous retryable provider failure can be archived"
        )
    resolved = _validate_boundary(run_dir, run_id, prompt_file)
    state_path = _state_path(resolved)
    with _lock(state_path):
        state = _load(state_path)
        attempts = state.get("attempts", [])
        if (
            state.get("run_id") != run_id
            or state.get("prompt_sha256") != file_sha256(prompt_file)
            or not isinstance(attempts, list)
            or not attempts
            or attempts[-1].get("status") not in allowed_statuses
            or state.get("status") not in allowed_statuses
        ):
            raise GenerationInvariant("generation interruption has no active attempt")
        if (resolved / "gates/publication-state.json").exists():
            raise GenerationInvariant("publication-state-exists")
        if ledger_has_public_effect(ledger, run_id):
            raise GenerationInvariant("ledger-row-exists")

        attempt = attempts[-1]
        archive_root = (
            resolved.parents[1]
            / "interrupted-generation"
            / run_id
            / f"attempt-{attempt['attempt']}"
        )
        if state.get("status") in {
            "invoking",
            "provider-failed-ambiguous",
            "provider-returned",
        }:
            observed = sorted(
                (
                    path
                    for path in resolved.rglob("*")
                    if (path.is_file() or path.is_symlink())
                    and not _is_allowed_prepublication(
                        str(path.relative_to(resolved))
                    )
                ),
                key=lambda path: str(path.relative_to(resolved)),
            )
            manifest: list[dict[str, str]] = []
            for path in observed:
                if path.is_symlink() or not path.is_file():
                    raise GenerationInvariant("interrupted artifact is not a regular file")
                manifest.append(
                    {
                        "path": str(path.relative_to(resolved)),
                        "sha256": file_sha256(path),
                    }
                )
            if state.get("status") == "provider-failed-ambiguous" and return_code == 75:
                attempt["provider_return_code"] = attempt.get("return_code")
            attempt.update(
                {
                    "status": "interruption-archiving",
                    "return_code": return_code,
                    "archive_root": str(archive_root),
                    "archive_manifest": manifest,
                }
            )
            state["status"] = "interruption-archiving"
            state["updated_at"] = utc_now()
            _atomic_write(state_path, state)
        else:
            if attempt.get("return_code") != return_code:
                raise GenerationInvariant("interruption return code changed")
            manifest = attempt.get("archive_manifest")
            if (
                not isinstance(manifest, list)
                or attempt.get("archive_root") != str(archive_root)
            ):
                raise GenerationInvariant("interruption archive journal is invalid")

        archive_root.mkdir(parents=True, exist_ok=True)
        for item in manifest:
            relative = Path(str(item.get("path", "")))
            if (
                not str(relative)
                or relative.is_absolute()
                or ".." in relative.parts
                or not isinstance(item.get("sha256"), str)
            ):
                raise GenerationInvariant("interruption archive entry is invalid")
            source = resolved / relative
            destination = archive_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                if source.is_symlink() or not source.is_file():
                    raise GenerationInvariant("interrupted source changed type")
                if file_sha256(source) != item["sha256"]:
                    raise GenerationInvariant("interrupted source bytes changed")
                if destination.exists():
                    raise GenerationInvariant("interruption archive destination conflicts")
                os.replace(source, destination)
            if (
                not destination.is_file()
                or destination.is_symlink()
                or file_sha256(destination) != item["sha256"]
            ):
                raise GenerationInvariant("interruption archive verification failed")

        safe, reason = prepublication_empty(resolved, run_id, ledger)
        if not safe:
            raise GenerationInvariant(reason)
        finished = utc_now()
        attempt.update(
            {
                "finished_at": finished,
                "status": "interrupted-safe",
                "boundary": "archived-prepublication-artifacts",
            }
        )
        state["status"] = "interrupted-safe"
        state["updated_at"] = finished
        _atomic_write(state_path, state)
        # Keep a durable, hash-bound proof outside the prunable run directory.
        # The run state itself is useful during the next tick, but a retention
        # pass may remove it after the archive is complete; the archive proof
        # is what permits a safe new identity without guessing publication.
        _atomic_write(archive_root / "generation-state.json", state)
        _atomic_write(
            archive_root / "generation-exhaustion-receipt.json",
            {
                "schema": "writer.generation-exhaustion-receipt",
                "version": 1,
                "run_id": run_id,
                "attempt": attempt.get("attempt"),
                "status": "interrupted-safe",
                "return_code": return_code,
                "charged_attempts": _charged_attempt_count(state),
                "maximum_attempts": int(
                    state.get("maximum_attempts", MAX_GENERATION_ATTEMPTS)
                ),
                "state_sha256": file_sha256(archive_root / "generation-state.json"),
                "archive_manifest_sha256": manifest_sha256(manifest),
                "publication_state_absent": True,
                "public_ledger_rows": 0,
            },
        )
        return state


def resume_decision(
    run_dir: Path, run_id: str, prompt_file: Path, ledger: Path
) -> dict[str, Any]:
    try:
        resolved = _validate_boundary(run_dir, run_id, prompt_file)
        state_path = _state_path(resolved)
        if not state_path.exists():
            if _ledger_has_run(ledger, run_id):
                return {
                    "resumable": False,
                    "reason": "generation-ledger-row-exists",
                }
            safe, reason = prepublication_empty(resolved, run_id, ledger)
            return {
                "resumable": safe,
                "reason": reason,
                "status": "uninitialized-safe",
            }
        state = _load(state_path)
        if (
            state.get("run_id") != run_id
            or state.get("run_dir") != str(resolved)
            or state.get("prompt_path") != str(prompt_file.resolve(strict=True))
            or state.get("prompt_sha256") != file_sha256(prompt_file)
        ):
            return {"resumable": False, "reason": "generation-state-not-safe"}
        if state.get("status") == "quality-repair-ready":
            if _adopted_staged_prepublication(
                resolved, run_id, prompt_file, ledger, state
            ):
                attempts = state.get("attempts", [])
                maximum = int(
                    state.get("maximum_attempts", MAX_GENERATION_ATTEMPTS)
                )
                if isinstance(attempts, list) and _charged_attempt_count(state) < maximum:
                    return {
                        "resumable": True,
                        "reason": "adopted-staged-prepublication",
                        "status": "quality-repair-ready",
                    }
            return {
                "resumable": False,
                "reason": "quality-repair-ready",
                "status": "quality-repair-ready",
            }
        if (
            state.get("status")
            not in {"provider-failed-safe", "interrupted-safe"}
            and not _failed_before_publication(state)
        ):
            return {"resumable": False, "reason": "generation-state-not-safe"}
        attempts = state.get("attempts", [])
        maximum = int(
            state.get("maximum_attempts", MAX_GENERATION_ATTEMPTS)
        )
        if not isinstance(attempts, list) or _charged_attempt_count(state) >= maximum:
            return {
                "resumable": False,
                "reason": "generation-attempt-limit-exhausted",
            }
        safe, reason = prepublication_empty(resolved, run_id, ledger)
        return {
            "resumable": safe,
            "reason": reason,
            "status": state.get("status"),
        }
    except (OSError, ValueError, json.JSONDecodeError, GenerationInvariant) as error:
        return {"resumable": False, "reason": f"generation-state-invalid:{error}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    begin_parser = subparsers.add_parser("begin")
    begin_parser.add_argument("--owner-pid", type=int)
    result_parser = subparsers.add_parser("result")
    result_parser.add_argument("--return-code", required=True, type=int)
    interrupted_parser = subparsers.add_parser("archive-interrupted")
    interrupted_parser.add_argument("--return-code", required=True, type=int)
    orphan_parser = subparsers.add_parser("recover-orphan")
    orphan_parser.add_argument(
        "--minimum-age-seconds", type=int, default=60
    )
    rebind_parser = subparsers.add_parser("rebind-release")
    rebind_parser.add_argument("--current-root", required=True, type=Path)
    subparsers.add_parser("adopt-prepublication")
    subparsers.add_parser("resume-check")
    args = parser.parse_args()
    common = (args.run_dir, args.run_id, args.prompt_file, args.ledger)
    if args.command == "init":
        value = initialize(*common)
    elif args.command == "begin":
        value = begin(*common, owner_pid=args.owner_pid)
    elif args.command == "result":
        value = record_result(*common, args.return_code)
    elif args.command == "archive-interrupted":
        value = archive_interrupted(*common, args.return_code)
    elif args.command == "recover-orphan":
        value = recover_orphan(
            *common,
            minimum_age_seconds=args.minimum_age_seconds,
        )
    elif args.command == "rebind-release":
        value = rebind_release(*common, current_root=args.current_root)
    elif args.command == "adopt-prepublication":
        value = adopt_prepublication(*common)
    else:
        value = resume_decision(*common)
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return 0 if args.command != "resume-check" or value["resumable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
