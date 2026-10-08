#!/usr/bin/env python3
"""Per-loop cleanup boundary followed by exact immutable entrypoint exec."""

from __future__ import annotations

import json
import hashlib
import fcntl
import os
import plistlib
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Callable, NamedTuple

from runtime.loop.lm_loop import _apply_lock, _label_apply_lock_path, _loaded_v2_release
from runtime.loop.lm_loop_apply import _loaded_arguments
from runtime.loop.loop_cleanup import remove_owned_tree
from runtime.loop.macos_loop_registry import (
    CONTROL_PLANE_SAFETY_LOOPS, admission_effect_scope, validate_registry,
)
from runtime.loop.runtime_event import (
    append_runtime_event,
    build_runtime_event,
    build_runtime_start_event,
    validate_runtime_event,
)
from runtime.host.disk_admission import disk_free_bytes
from runtime.host.memory_admission import memory_free_percent
from runtime.host.resource_admission import (
    OCCURRENCE_ID_PATTERN,
    cancel_durable as cancel_durable_resource,
    claim_durable as claim_durable_resource,
    clear_no_effect_unknown as clear_no_effect_unknown_resource,
    defer_durable as defer_durable_resource,
    durable_protocol_version,
    enqueue_durable as enqueue_durable_resource,
    heartbeat_durable as heartbeat_durable_resource,
    process_start,
    release as release_resource,
    release_and_reserve as release_and_reserve_resource,
    reserve_available as reserve_available_resource,
    transfer_durable as transfer_durable_resource,
    try_acquire as try_acquire_resource,
)


EXEC_GATE = Path(__file__).resolve().parents[1] / "host/exec_gate.py"
SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SAFE_EVENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
SAFE_RESULT_HINT = re.compile(r"[a-z][a-z0-9_:-]{1,99}\Z")
ADMISSION_CONTROL_RETRY_ATTEMPTS = 8
ADMISSION_CONTROL_RETRY_DELAY_SECONDS = 0.25
HEARTBEAT_INTERVAL_SECONDS = 30.0
# Stay under resource_admission.DEFAULT_HEARTBEAT_TIMEOUT_SECONDS (300s).
HEARTBEAT_BUSY_TOLERANCE_SECONDS = 240.0
PRE_EFFECT_HINT_ENTRYPOINTS = frozenset({
    "apps/life-manager/scripts/ebook-distribute-daily.sh",
    "apps/life-manager/scripts/mobile-app",
    "skills/affiliate/affiliate",
    "skills/earn/crowdworks/scripts/application-owner",
    "skills/earn/crowdworks/scripts/paid-owner",
    "skills/earn/crowdworks/scripts/reply-owner",
    "skills/earn/lancers/scripts/application-owner",
    "skills/earn/lancers/scripts/negotiate-owner",
    "skills/earn/lancers/scripts/paid-owner",
    "skills/earn/lancers/scripts/storefront-owner",
    "skills/earn/mercor/scripts/application-owner",
    "skills/earn/mercor/scripts/paid-owner",
    "skills/earn/mercor/scripts/reply-owner",
    "skills/writer-agent/scripts/article-resume-pending.sh",
})
EFFECT_RESULT_HINT_ENTRYPOINTS = frozenset({
    "apps/life-manager/scripts/ebook-distribute-daily.sh",
    "apps/life-manager/scripts/mobile-app",
})
NO_EFFECT_RESULT_HINT_ENTRYPOINTS = frozenset({
    "apps/life-manager/scripts/ebook-distribute-daily.sh",
    "apps/life-manager/scripts/mobile-app",
})
# Loop IDs allowed to use the pre-effect hint when their registry entrypoint is
# shared (e.g. runtime/loop/entry_dispatch.py dispatches several owners from one
# entrypoint string). Entrypoint membership above is not enough to scope trust
# in that case, since siblings dispatched from the same entrypoint may not
# implement the no-mutation-attempted tracking this hint requires. Only add a
# loop_id here once its entrypoint script provably tracks mutation attempts and
# never writes the hint after one starts.
PRE_EFFECT_HINT_LOOP_IDS = frozenset({
    "alpaca-investment-live",
    "alpaca-investment-paper",
    "ebook-en-tiktok-daily",
    "ebook-ja-instagram-daily",
    "ebook-ja-tiktok-daily",
    "hf-gig-apply-direct",
    "investment-cross-venue-report",
    "hf-gig-storefront-direct",
})
EBOOK_POSTIZ_LOOP_IDS = frozenset({
    "ebook-en-tiktok-daily",
    "ebook-ja-instagram-daily",
    "ebook-ja-tiktok-daily",
})
EBOOK_RUNTIME_TENANT_ID = "dais-local"
JAVASCRIPT_ENTRYPOINT_SUFFIXES = frozenset({".cjs", ".js", ".mjs"})


def _runtime_node() -> str:
    configured = os.environ.get("LIFE_MANAGER_RUNTIME_NODE")
    candidate = Path(configured) if configured else Path(shutil.which("node") or "")
    if (not candidate.is_absolute() or not candidate.is_file()
            or not os.access(candidate, os.X_OK)):
        raise RuntimeError("managed node executable is unavailable")
    return str(candidate)


def build_loop_command(registry: dict, loop_id: str, release_root: Path) -> list[str]:
    """Validate and build argv without doing housekeeping on the wake path."""
    validate_registry(registry)
    entry = registry["loops"].get(loop_id)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown loop id: {loop_id}")
    executable = release_root.resolve() / entry["entrypoint"]
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"entrypoint missing or not executable: {entry['entrypoint']}")
    command = [str(executable)]
    if entry.get("adapter") == "python" or executable.suffix == ".py":
        # Never let a shebang pick launchd's system python.
        command.insert(0, sys.executable)
    elif executable.suffix in JAVASCRIPT_ENTRYPOINT_SUFFIXES:
        command.insert(0, _runtime_node())
    command.extend(entry.get("command", []))
    return command


def _child_environment_for_owner(
        loop_id: str, base: dict[str, str], home: Path | None = None) -> dict[str, str]:
    """Scope the canonical data root and Postiz credential to eBook owners."""
    environment = dict(base)
    if loop_id not in EBOOK_POSTIZ_LOOP_IDS:
        return environment

    # The eBook entrypoint stores its render/object/ledger data beneath the shared
    # Life Manager data root. Do not inherit an arbitrary manager-level override.
    environment["LM_DATA_DIR"] = str(
        Path(home or Path.home()).expanduser() / ".local/state/life-manager"
    )
    environment["LM_RUNTIME_TENANT_ID"] = EBOOK_RUNTIME_TENANT_ID

    # eBook renderers discover ffmpeg, ffprobe, and fontconfig through PATH.
    # launchd's default PATH omits Homebrew binaries.
    if loop_id in EBOOK_POSTIZ_LOOP_IDS:
        inherited_path = environment.get("PATH") or os.defpath
        path_entries = inherited_path.split(os.pathsep)
        if "/opt/homebrew/bin" not in path_entries:
            environment["PATH"] = os.pathsep.join(("/opt/homebrew/bin", inherited_path))

    if loop_id == "ebook-en-tiktok-daily":
        # HeyGen's CLI telemetry must not gate the provider command on PostHog DNS.
        environment["HEYGEN_NO_ANALYTICS"] = "1"
        # The CLI lives under the user's local bin, which is intentionally not
        # added to every eBook owner's PATH.
        if not str(environment.get("LIFE_MANAGER_HEYGEN", "")).strip():
            environment["LIFE_MANAGER_HEYGEN"] = str(
                (home or Path.home()).expanduser() / ".local/bin/heygen"
            )

    # Ignore any inherited alias. The credential SSOT is the only source for eBook
    # publisher authentication. Do not even pass it to the child while publishing
    # is disabled.
    environment.pop("LM_POSTIZ_API_KEY", None)
    if environment.get("LM_EBOOK_PUBLISHING_ENABLED") != "true":
        return environment
    private = (home or Path.home()) / ".local/share/anicca"
    credentials = private / "credentials.json"
    try:
        if private.is_symlink() or credentials.is_symlink():
            return environment
        private_stat = private.stat()
        credentials_stat = credentials.stat()
        if (not stat.S_ISDIR(private_stat.st_mode)
                or not stat.S_ISREG(credentials_stat.st_mode)
                or private_stat.st_uid != os.getuid()
                or stat.S_IMODE(private_stat.st_mode) != 0o700
                or credentials_stat.st_uid != os.getuid()
                or stat.S_IMODE(credentials_stat.st_mode) != 0o600):
            return environment
        payload = json.loads(credentials.read_text(encoding="utf-8"))
        rows = [row for row in payload.get("credentials", [])
                if isinstance(row, dict) and row.get("service") == "postiz"]
        if len(rows) != 1:
            return environment
        api_key = rows[0].get("api_key")
        if not isinstance(api_key, str):
            return environment
        api_key = api_key.strip()
        if (not api_key or len(api_key) > 4096
                or any(ord(character) < 33 or ord(character) > 126 for character in api_key)):
            return environment
    except (OSError, AttributeError, TypeError, ValueError):
        return environment

    environment["LM_POSTIZ_API_KEY"] = api_key
    return environment


def _identity_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _product_loop_for_job(release_root: Path, job_id: str) -> str | None:
    """Return one catalog product identity without guessing from the job name."""
    try:
        value = json.loads((release_root / "apps/life-manager/config/product-loop-catalog.json")
                           .read_text(encoding="utf-8"))
        loops = value.get("loops")
        if not isinstance(loops, list):
            return None
        matches = [loop.get("id") for loop in loops
                   if isinstance(loop, dict) and isinstance(loop.get("job_ids"), list)
                   and job_id in loop["job_ids"]]
        if len(matches) != 1 or not isinstance(matches[0], str):
            return None
        return matches[0] if SAFE_EVENT_ID.fullmatch(matches[0]) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _wake_id(run_id: str) -> str:
    candidate = os.environ.get("WAKE_ID", "").strip()
    return candidate if SAFE_EVENT_ID.fullmatch(candidate) else run_id


def _should_enqueue_recovery_intent(entry: dict, event: dict) -> bool:
    if event.get("status") != "fail":
        return False
    entrypoint = str(entry.get("entrypoint") or "")
    if (entry.get("priority") == "critical_paid"
            or entrypoint.endswith("/paid-owner")
            or entrypoint.endswith("/paid-direct-owner")
            or entrypoint == "runtime/loop/recovery-supervisor-cli.mjs"):
        return False
    return True


def _valid_recovery_intent(value: object, event: dict) -> bool:
    return (isinstance(value, dict)
            and value.get("schema_version") == 1
            and isinstance(value.get("intent_id"), str)
            and SAFE_EVENT_ID.fullmatch(value["intent_id"]) is not None
            and value.get("loop_id") == event.get("loop_id")
            and value.get("owner_id") == event.get("owner_id")
            and value.get("wake_id") == event.get("wake_id")
            and value.get("run_id") == event.get("run_id")
            and value.get("occurrence_id") == event.get("occurrence_id")
            and value.get("release_sha") == event.get("release_sha")
            and value.get("mutates_external_effect") is False
            and type(value.get("retryable")) is bool)


def _append_recovery_intent(path: Path, intent: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        needle = intent["intent_id"].encode("utf-8")
        os.lseek(descriptor, 0, os.SEEK_SET)
        with os.fdopen(os.dup(descriptor), "rb") as existing:
            for line in existing:
                if needle not in line:
                    continue
                try:
                    row = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(row, dict) and row.get("intent_id") == intent["intent_id"]:
                    return
        if os.fstat(descriptor).st_size:
            os.lseek(descriptor, -1, os.SEEK_END)
            if os.read(descriptor, 1) != b"\n":
                os.write(descriptor, b"\n")
        os.write(descriptor, (json.dumps(intent, ensure_ascii=True, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _enqueue_recovery_intent(release_root: Path, event: dict, scratch: Path) -> bool:
    classifier = release_root / "runtime/loop/recovery-intent-cli.mjs"
    if not classifier.is_file():
        raise RuntimeError("recovery intent classifier unavailable")
    input_path = scratch / "recovery-intent-input.json"
    output_path = scratch / "recovery-intent-output.json"
    _atomic_json(input_path, {
        "loop_id": event["loop_id"],
        "owner_id": event["owner_id"],
        "wake_id": event["wake_id"],
        "run_id": event["run_id"],
        "occurrence_id": event["occurrence_id"],
        "release_sha": event["release_sha"],
        "status": event["status"],
        "failure_layer": event["failure_layer"],
        "effect_class": event["effect_class"],
        "effect_status": event["effect_status"],
        "blocker": event["blocker"],
        "consecutive_failure_streak": 1,
        "threshold": 3,
        "evidence_refs": event["evidence_refs"],
    })
    result = subprocess.run(
        [_runtime_node(), str(classifier), "--input", str(input_path),
         "--output", str(output_path)],
        cwd=release_root, capture_output=True, text=True, timeout=30,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )
    if result.returncode != 0:
        raise RuntimeError("recovery intent classifier failed")
    try:
        intent = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("recovery intent output invalid") from error
    if not _valid_recovery_intent(intent, event):
        raise RuntimeError("recovery intent identity invalid")
    queue = Path(os.path.expanduser(os.environ.get(
        "LIFE_MANAGER_RECOVERY_INTENTS_PATH",
        "~/.local/state/life-manager/recovery/intents.jsonl",
    )))
    _append_recovery_intent(queue, {"record_type": "recovery_intent", **intent})
    return True


def reset_loop_scratch(state_root: Path, loop_id: str, run_id: str, *,
                       effect_class: str | None = None) -> tuple[Path, int, int]:
    """Create private per-run scratch without scanning a previous wake's tree."""
    if (not SAFE_RUN_ID.fullmatch(loop_id) or loop_id in {".", ".."}
            or not SAFE_RUN_ID.fullmatch(run_id) or run_id in {".", ".."}):
        raise ValueError("unsafe run id")
    identity = process_start(os.getpid())
    if identity is None:
        raise RuntimeError("scratch owner identity unavailable")
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = state_root.resolve()
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(root, flags)
    loop_tmp_fd = parent_fd = run_fd = -1
    run_created = False
    run_verified = False
    try:
        try:
            os.mkdir("loop-tmp", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        loop_tmp_fd = os.open("loop-tmp", flags, dir_fd=root_fd)
        try:
            os.mkdir(loop_id, mode=0o700, dir_fd=loop_tmp_fd)
        except FileExistsError:
            pass
        try:
            parent_fd = os.open(loop_id, flags, dir_fd=loop_tmp_fd)
        except OSError as error:
            raise ValueError("unsafe loop scratch root") from error
        os.mkdir(run_id, mode=0o700, dir_fd=parent_fd)
        run_created = True
        created_stat = os.stat(run_id, dir_fd=parent_fd, follow_symlinks=False)
        run_fd = os.open(run_id, flags, dir_fd=parent_fd)
        opened_stat = os.fstat(run_fd)
        if ((created_stat.st_dev, created_stat.st_ino) !=
                (opened_stat.st_dev, opened_stat.st_ino)):
            raise RuntimeError("scratch inode changed during creation")
        run_verified = True
        try:
            marker_fd = os.open(
                ".terminal-unrecorded", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=run_fd)
            os.close(marker_fd)
            owner_fd = os.open(
                ".owner.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=run_fd)
            with os.fdopen(owner_fd, "w", encoding="utf-8") as handle:
                owner = {"pid": os.getpid(), "process_start": identity}
                if effect_class is not None:
                    owner["effect_class"] = effect_class
                json.dump(owner, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.fsync(run_fd)
        except Exception:
            raise
        scratch = root / "loop-tmp" / loop_id / run_id
        return scratch, parent_fd, run_fd
    except Exception:
        if run_created and run_verified and parent_fd >= 0 and run_fd >= 0:
            try:
                remove_owned_tree(parent_fd, run_fd, run_id)
            except OSError:
                pass
        if run_fd >= 0:
            os.close(run_fd)
        if parent_fd >= 0:
            os.close(parent_fd)
        raise
    finally:
        if loop_tmp_fd >= 0:
            os.close(loop_tmp_fd)
        os.close(root_fd)


def unprotect_loop_scratch(run_fd: int) -> None:
    """Allow cleanup only after the terminal receipt has been persisted."""
    os.unlink(".terminal-unrecorded", dir_fd=run_fd)
    os.fsync(run_fd)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":")); handle.write("\n")
            handle.flush(); os.fsync(handle.fileno())
        os.chmod(name, 0o600); os.replace(name, path)
    finally:
        try: os.unlink(name)
        except FileNotFoundError: pass


def _record_scratch_cleanup_diagnostic(
        state_root: Path, parent_fd: int, run_fd: int, *,
        loop_id: str, run_id: str, occurrence_id: str, release_sha: str,
        terminal_saved: bool, phase: str, cleanup_status: str,
        cleanup_operation: str, error: Exception | None,
        loaded_argv_sha256: str, loaded_env_sha256: str,
        command: str) -> None:
    if not SAFE_RUN_ID.fullmatch(loop_id) or not SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("unsafe scratch cleanup diagnostic identity")
    if not OCCURRENCE_ID_PATTERN.fullmatch(occurrence_id):
        raise ValueError("unsafe scratch cleanup diagnostic occurrence")

    opened = os.fstat(run_fd)
    try:
        named = os.stat(run_id, dir_fd=parent_fd, follow_symlinks=False)
        path_present = True
        path_matches_open = (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino)
    except FileNotFoundError:
        path_present = False
        path_matches_open = False
    except OSError:
        path_present = None
        path_matches_open = None
    try:
        os.stat(".terminal-unrecorded", dir_fd=run_fd, follow_symlinks=False)
        marker_remaining = True
    except FileNotFoundError:
        marker_remaining = False
    except OSError:
        marker_remaining = None

    diagnostic = {
        "schema_version": 1,
        "event": "scratch_cleanup_diagnostic",
        "run_id": run_id,
        "owner_id": loop_id,
        "occurrence_id": occurrence_id,
        "release_sha": release_sha,
        "terminal_saved": terminal_saved,
        "phase": phase,
        "cleanup_status": cleanup_status,
        "cleanup_operation": cleanup_operation,
        "error_class": type(error).__name__ if error is not None else None,
        "errno": getattr(error, "errno", None) if error is not None else None,
        "scratch_path": f"loop-tmp/{loop_id}/{run_id}",
        "scratch_identity": {
            "device": opened.st_dev,
            "inode": opened.st_ino,
            "mode": f"{stat.S_IMODE(opened.st_mode):04o}",
            "path_present": path_present,
            "path_matches_open": path_matches_open,
            "terminal_marker_remaining": marker_remaining,
        },
        "loaded_argv_sha256": loaded_argv_sha256,
        "loaded_env_sha256": loaded_env_sha256,
        "command": command,
    }
    _atomic_json(state_root / "scratch-cleanup-diagnostics" / f"{run_id}.json", diagnostic)


class EffectIdentityResult(NamedTuple):
    """Outcome of an effect-identity persistence attempt.

    status is one of:
      - "not_written": the sidecar was never created by the entrypoint.
      - "rejected": the sidecar existed but failed validation, or an
        OSError other than "not found" occurred while reading/moving it.
      - "persisted": the sidecar was valid and moved into state_root.
    """
    status: str
    ref: str | None


def _persist_effect_identity(sidecar: Path, state_root: Path,
                             loop_id: str, run_id: str,
                             claimed_occurrence_id: str | None = None,
                             ) -> EffectIdentityResult:
    """Move a validated run identity out of scratch before unknown-effect cleanup."""
    if (not SAFE_RUN_ID.fullmatch(loop_id) or not SAFE_RUN_ID.fullmatch(run_id)
            or loop_id in {".", ".."} or run_id in {".", ".."}):
        raise ValueError("unsafe effect identity id")
    expected_occurrence = claimed_occurrence_id or f"{loop_id}:{run_id}"
    if not OCCURRENCE_ID_PATTERN.fullmatch(expected_occurrence):
        raise ValueError("unsafe effect identity occurrence")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(sidecar, flags)
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600):
                return EffectIdentityResult("rejected", None)
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                data = handle.read(1024 * 1024 + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except FileNotFoundError:
        return EffectIdentityResult("not_written", None)
    except OSError:
        return EffectIdentityResult("rejected", None)
    home_prefix = str(Path.home()).encode()
    if not data.strip() or len(data) > 1024 * 1024 or (home_prefix and home_prefix in data):
        return EffectIdentityResult("rejected", None)

    identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
    job_identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    effect_key = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,511}$")
    integration = re.compile(
        r"^integration://postiz/([a-z]+)/([A-Za-z0-9._:-]{1,200})$", re.IGNORECASE,
    )
    account = re.compile(r"^@[A-Za-z0-9._-]{1,127}$")
    hash_value = re.compile(r"^[0-9a-f]{64}$")
    allowed = {
        "schema_version", "kind", "runtime_run_id", "occurrence_id", "loop_id",
        "job_id", "effect_key", "product_id", "format_id", "form", "locale",
        "platform", "creative_id", "slot", "integration_ref", "account_id",
        "video_sha256", "caption_sha256", "media_sha256", "pack_sha256",
        "media_order_sha256",
    }
    for raw in data.splitlines():
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return EffectIdentityResult("rejected", None)
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or value.get("kind") != "life_manager_effect_identity"
                or set(value) - allowed
                or value.get("runtime_run_id") != run_id
                or value.get("occurrence_id") != expected_occurrence
                or value.get("loop_id") != loop_id
                or not job_identifier.fullmatch(str(value.get("job_id", "")))
                or not effect_key.fullmatch(str(value.get("effect_key", "")))
                or not identifier.fullmatch(str(value.get("product_id", "")))
                or not identifier.fullmatch(str(value.get("format_id", "")))
                or not identifier.fullmatch(str(value.get("form", "")))
                or not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", str(value.get("locale", "")))
                or value.get("platform") not in {"instagram", "tiktok", "youtube"}
                or not identifier.fullmatch(str(value.get("creative_id", "")))
                or not isinstance(value.get("slot"), str) or not value["slot"].strip()
                or not integration.fullmatch(str(value.get("integration_ref", "")))
                or not account.fullmatch(str(value.get("account_id", "")))
                or (value.get("video_sha256") is not None
                    and not hash_value.fullmatch(str(value.get("video_sha256"))))
                or not hash_value.fullmatch(str(value.get("caption_sha256", "")))):
            return EffectIdentityResult("rejected", None)
        if "media_sha256" in value and (
                not isinstance(value["media_sha256"], list)
                or not value["media_sha256"]
                or any(not hash_value.fullmatch(str(item)) for item in value["media_sha256"])):
            return EffectIdentityResult("rejected", None)
        for key in ("pack_sha256", "media_order_sha256"):
            if key in value and not hash_value.fullmatch(str(value[key])):
                return EffectIdentityResult("rejected", None)
        integration_match = integration.fullmatch(str(value["integration_ref"]))
        if integration_match is None or integration_match.group(1).lower() != value["platform"]:
            return EffectIdentityResult("rejected", None)
        video_key = re.fullmatch(
            r"marketing:video:([^:]+):(instagram|tiktok|youtube):([^:]+):([0-9a-f]{64}):([0-9a-f]{64})(?::([0-9a-f]{64}))?",
            str(value["effect_key"]),
        )
        carousel_key = re.fullmatch(
            r"marketing:carousel:([^:]+):([^:]+):([0-9a-f]{64}):([0-9a-f]{64}):([0-9a-f]{64})(?::([0-9a-f]{64}))?",
            str(value["effect_key"]),
        )
        if video_key:
            if (value["product_id"] != video_key.group(1)
                    or value["platform"] != video_key.group(2)
                    or value["creative_id"] != video_key.group(3)
                    or value["video_sha256"] != video_key.group(4)
                    or value["caption_sha256"] != video_key.group(5)
                    or (video_key.group(6) is not None
                        and video_key.group(6) != hashlib.sha256(value["slot"].encode()).hexdigest())):
                return EffectIdentityResult("rejected", None)
        elif carousel_key:
            media_hashes = value.get("media_sha256")
            expected_media_order = (
                hashlib.sha256(json.dumps(
                    media_hashes, ensure_ascii=False, separators=(",", ":"),
                ).encode()).hexdigest()
                if isinstance(media_hashes, list) else None
            )
            if (value["product_id"] != carousel_key.group(1)
                    or value["creative_id"] != carousel_key.group(2)
                    or value.get("video_sha256") is not None
                    or not isinstance(media_hashes, list) or len(media_hashes) != 6
                    or any(not hash_value.fullmatch(str(item)) for item in media_hashes)
                    or value.get("pack_sha256") != carousel_key.group(3)
                    or value.get("media_order_sha256") != carousel_key.group(4)
                    or value.get("media_order_sha256") != expected_media_order
                    or value["caption_sha256"] != carousel_key.group(5)
                    or (carousel_key.group(6) is not None
                        and carousel_key.group(6) != hashlib.sha256(value["slot"].encode()).hexdigest())):
                return EffectIdentityResult("rejected", None)
        else:
            return EffectIdentityResult("rejected", None)

    root_fd = identity_fd = descriptor = -1
    temporary_name = None
    try:
        state_root = state_root.expanduser()
        state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        root_fd = os.open(state_root, root_flags)
        root_info = os.fstat(root_fd)
        if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid()
                or root_info.st_mode & 0o777 != 0o700):
            return EffectIdentityResult("rejected", None)
        try:
            os.mkdir("effect-identities", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        identity_fd = os.open("effect-identities", root_flags, dir_fd=root_fd)
        identity_info = os.fstat(identity_fd)
        if (not stat.S_ISDIR(identity_info.st_mode) or identity_info.st_uid != os.getuid()
                or identity_info.st_mode & 0o777 != 0o700):
            return EffectIdentityResult("rejected", None)
        write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        for attempt in range(8):
            temporary_name = f".{run_id}.{os.getpid()}.{time.time_ns()}.{attempt}.tmp"
            try:
                descriptor = os.open(
                    temporary_name, write_flags, 0o600, dir_fd=identity_fd,
                )
                break
            except FileExistsError:
                continue
        if descriptor < 0:
            return EffectIdentityResult("rejected", None)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name, f"{run_id}.jsonl",
            src_dir_fd=identity_fd, dst_dir_fd=identity_fd,
        )
        temporary_name = None
        os.fsync(identity_fd)
        sidecar.unlink()
    except OSError:
        return EffectIdentityResult("rejected", None)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None and identity_fd >= 0:
            try:
                os.unlink(temporary_name, dir_fd=identity_fd)
            except FileNotFoundError:
                pass
        if identity_fd >= 0:
            os.close(identity_fd)
        if root_fd >= 0:
            os.close(root_fd)
    return EffectIdentityResult(
        "persisted", f"lm-effect://{loop_id}/{run_id}/identity.jsonl")


def _runtime_limit(entry: dict) -> int | None:
    if entry.get("cadence") == {"keep_alive": True}:
        return None
    return entry.get("runtime_timeout_seconds", 3600)


def _resource_class(entry: dict) -> str:
    return entry.get("resource_class") or (
        "agent" if entry["provider_route"] == "shared-agent-runner" else "deterministic")


def _admission_class(entry: dict) -> str:
    """Revenue work owns capacity; every other finite wake borrows idle capacity."""
    return entry.get("admission_class", "borrow")


def _queue_priority(entry: dict) -> str | None:
    """Return an explicitly declared queue priority, if present."""
    value = entry.get("priority")
    return value if isinstance(value, str) and value else None


def _disk_headroom_deferred(receipt_parent: Path, *, phase: str) -> dict | None:
    """Defer only when filesystem capacity cannot be measured."""
    try:
        available = disk_free_bytes(receipt_parent)
    except Exception:
        available = None
    if isinstance(available, bool) or not isinstance(available, int) or available < 0:
        reason = "disk_headroom_unavailable"
        available_bytes = None
    else:
        return None
    return {
        "status": "deferred",
        "effect": 0,
        "reason": reason,
        "phase": phase,
        "available_bytes": available_bytes,
        "required_bytes": 0,
    }


def _sqlite_database_busy(error: sqlite3.OperationalError) -> bool:
    code = getattr(error, "sqlite_errorcode", None)
    if isinstance(code, int):
        return (code & 0xFF) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
    return str(error).lower() in {
        "database is locked",
        "database schema is locked: main",
        "database table is locked",
        "database table is locked: sqlite_master",
    }


def _admission_with_retry(
    operation: Callable[[], tuple[Path | None, str]],
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[Path | None, str]:
    result: tuple[Path | None, str] = (None, "control_busy")
    for attempt in range(ADMISSION_CONTROL_RETRY_ATTEMPTS):
        if cancelled():
            return None, "admission_interrupted"
        try:
            result = operation()
        except sqlite3.OperationalError as error:
            if not _sqlite_database_busy(error):
                raise
            result = (None, "database_busy")
        if result[0] is not None or result[1] not in {"control_busy", "database_busy"}:
            return result
        if cancelled():
            return None, "admission_interrupted"
        if attempt + 1 < ADMISSION_CONTROL_RETRY_ATTEMPTS:
            time.sleep(ADMISSION_CONTROL_RETRY_DELAY_SECONDS * (attempt + 1))
    return result


def _release_with_retry(operation: Callable[[], list[str]]) -> list[str]:
    """Retry a release only while its transaction and claim remain atomic."""
    for attempt in range(ADMISSION_CONTROL_RETRY_ATTEMPTS):
        try:
            return operation()
        except sqlite3.OperationalError as error:
            if not _sqlite_database_busy(error):
                raise
            transient: Exception = error
        except RuntimeError as error:
            if str(error) != "control_busy":
                raise
            transient = error
        if attempt + 1 < ADMISSION_CONTROL_RETRY_ATTEMPTS:
            time.sleep(ADMISSION_CONTROL_RETRY_DELAY_SECONDS * (attempt + 1))
    raise transient


def _heartbeat_loop(claim: Path, stop: threading.Event,
                    failed: threading.Event) -> None:
    last_ok = time.monotonic()
    while not stop.wait(HEARTBEAT_INTERVAL_SECONDS):
        try:
            healthy = heartbeat_durable_resource(claim)
        except RuntimeError as error:
            if (str(error) == "control_busy"
                    and time.monotonic() - last_ok < HEARTBEAT_BUSY_TOLERANCE_SECONDS):
                continue
            failed.set()
            return
        except (OSError, sqlite3.Error):
            failed.set()
            return
        if not healthy:
            failed.set()
            return
        last_ok = time.monotonic()


def _host_admission_deferred(path: Path, started_ns: int) -> str | None:
    try:
        if path.stat().st_mtime_ns < started_ns:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if value.get("status") != "deferred" or value.get("effect") != 0:
        return None
    reason = value.get("reason")
    prefix = "host_admission_deferred:"
    return (reason if isinstance(reason, str) and SAFE_RUN_ID.fullmatch(reason)
            and len(prefix) + len(reason) <= 128 else "unknown")


def _proven_pre_effect_failure(path: Path) -> bool:
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o777 != 0o600):
            return False
        return json.loads(path.read_text(encoding="utf-8")) == {
            "status": "pre_effect_failure", "effect": 0}
    except (OSError, ValueError):
        return False


def _read_private_result_hint(path: Path) -> dict | None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600
                or info.st_size > 4096):
            return None
        data = os.read(descriptor, 4097)
    except OSError:
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(data) > 4096:
        return None
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _verified_effect_result(path: Path, loop_id: str,
                            occurrence_id: str) -> tuple[str, str] | None:
    value = _read_private_result_hint(path)
    expected_fields = {
        "schema_version", "kind", "status", "effect", "owner_id",
        "occurrence_id", "provider", "provider_receipt_id", "effect_status",
    }
    if (not isinstance(value, dict) or set(value) != expected_fields
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
            or value.get("kind") != "life_manager_effect_result"
            or value.get("status") != "verified_effect"
            or type(value.get("effect")) is not int
            or value.get("effect") != 1
            or value.get("owner_id") != loop_id
            or value.get("occurrence_id") != occurrence_id
            or value.get("provider") != "postiz"
            or value.get("effect_status") not in {"verified", "reconciled"}):
        return None
    receipt_id = value.get("provider_receipt_id")
    if not isinstance(receipt_id, str) or not SAFE_RUN_ID.fullmatch(receipt_id):
        return None
    return value["effect_status"], f"postiz://posts/{receipt_id}"


def _verified_no_effect_result(path: Path, loop_id: str, occurrence_id: str,
                               entrypoint: str) -> tuple[str, str] | None:
    if entrypoint not in NO_EFFECT_RESULT_HINT_ENTRYPOINTS:
        return None
    allowed_reasons = ({"setup_required", "no_due_slot"}
                       if entrypoint == "apps/life-manager/scripts/ebook-distribute-daily.sh"
                       else {"no_due_slot", "daily_limit_reached"})
    value = _read_private_result_hint(path)
    expected_fields = {
        "schema_version", "kind", "status", "effect", "owner_id",
        "occurrence_id", "reason",
    }
    if (not isinstance(value, dict) or set(value) != expected_fields
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
            or value.get("kind") != "life_manager_no_effect_result"
            or value.get("status") != "verified_no_effect"
            or type(value.get("effect")) is not int
            or value.get("effect") != 0
            or value.get("owner_id") != loop_id
            or value.get("occurrence_id") != occurrence_id
            or not isinstance(value.get("reason"), str)
            or value.get("reason") not in allowed_reasons):
        return None
    return "not_applicable", f"lm-no-effect://{loop_id}/{occurrence_id}/{value['reason']}"


def _apply_verified_effect_result(
        event: dict, result: tuple[str, str] | None) -> dict:
    updated = dict(event)
    updated["evidence_refs"] = list(event.get("evidence_refs", []))
    if result is not None and updated.get("status") == "pass":
        if result[0] == "not_applicable":
            updated["effect_class"] = "none"
            updated["effect_status"] = "not_applicable"
        else:
            updated["effect_status"] = result[0]
            receipt_id = result[1].rsplit("/", 1)[-1]
            if "provider_receipt_id" in updated:
                updated["provider_receipt_id"] = receipt_id
                updated["official_readback_ref"] = result[1]
        if result[1] not in updated["evidence_refs"]:
            updated["evidence_refs"].append(result[1])
    return validate_runtime_event(updated)


def _terminal_outcome(return_code: int, *, host_deferred: str | None = None
                      ) -> tuple[bool, bool, str | None]:
    if return_code == 0:
        return True, False, None
    if host_deferred and return_code in {75, 124, 137, 143}:
        return False, True, f"host_admission_deferred:{host_deferred}"
    return False, False, f"entrypoint_exit_{return_code}"


# A failing entrypoint's own stderr is the only first-hand evidence of why it
# died (see the en-card-instagram investigation: hundreds of entrypoint_exit_1
# failures with nothing durable to read afterwards, because the per-run
# scratch dir is removed once the terminal event is written). Bounded so one
# noisy child cannot bloat the shared events.jsonl.
ENTRYPOINT_STDERR_TAIL_MAX_BYTES = 2048
ENTRYPOINT_STDERR_REPLAY_MAX_BYTES = 64 * 1024
ENTRYPOINT_STDERR_REPLAY_EDGE_BYTES = 32 * 1024
ENTRYPOINT_STDERR_TRUNCATION_MARKER = b"\n...[stderr truncated]...\n"


def _forward_process_group_signal(pgid: int, signum: int) -> None:
    try:
        os.killpg(pgid, signum)
    except (ProcessLookupError, PermissionError):
        pass


def _run_entrypoint(command: list[str], env: dict[str, str] | None = None, *,
                    timeout_seconds: float | None = None,
                    termination_grace_seconds: float = 15,
                    cancelled: Callable[[], bool] = lambda: False,
                    on_started: Callable[[int], None] = lambda _pid: None,
                    stderr_capture_fd: int | None = None) -> int:
    watched = (signal.SIGTERM, signal.SIGINT)
    previous = {}
    process = None
    pending = []
    stopping = False

    def forward(signum, _frame):
        nonlocal stopping
        stopping = True
        if process is None:
            pending.append(signum)
        elif process.poll() is None:
            _forward_process_group_signal(process.pid, signum)

    for signum in watched:
        previous[signum] = signal.signal(signum, forward)
    if cancelled() or pending:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        return 75
    read_fd, write_fd = os.pipe()
    try:
        process = subprocess.Popen(
            [sys.executable, str(EXEC_GATE), str(read_fd), *command],
            start_new_session=True, env=env, pass_fds=(read_fd,),
            stderr=stderr_capture_fd)
        os.close(read_fd)
        if cancelled() or pending or stopping:
            os.close(write_fd)
            for signum in pending:
                forward(signum, None)
            process.wait()
            return 75
        try:
            on_started(process.pid)
        except BaseException:
            os.close(write_fd)
            process.wait()
            raise
        if cancelled() or pending or stopping:
            os.close(write_fd)
            for signum in pending:
                forward(signum, None)
            process.wait()
            return 75
        try:
            os.write(write_fd, b"G")
        except BrokenPipeError:
            if stopping:
                process.wait()
                return 75
            raise
        os.close(write_fd)
        deadline = (None if timeout_seconds is None
                    else time.monotonic() + max(0, timeout_seconds))
        while True:
            if cancelled() or pending or stopping:
                forward(signal.SIGTERM, None)
                try:
                    process.wait(timeout=termination_grace_seconds)
                except subprocess.TimeoutExpired:
                    if process.poll() is None:
                        _forward_process_group_signal(process.pid, signal.SIGKILL)
                    process.wait()
                return 75
            wait_timeout = 0.25
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    forward(signal.SIGTERM, None)
                    try:
                        process.wait(timeout=termination_grace_seconds)
                    except subprocess.TimeoutExpired:
                        if process.poll() is None:
                            _forward_process_group_signal(process.pid, signal.SIGKILL)
                        process.wait()
                    return 124
                wait_timeout = min(wait_timeout, remaining)
            try:
                return_code = process.wait(timeout=wait_timeout)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        for descriptor in (read_fd, write_fd):
            try:
                os.close(descriptor)
            except OSError:
                pass
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return return_code if return_code >= 0 else 128 - return_code


def _run_entrypoint_with_stderr_capture(
        command: list[str], scratch_dir: Path, *,
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
        termination_grace_seconds: float = 15,
        cancelled: Callable[[], bool] = lambda: False,
        on_started: Callable[[int], None] = lambda _pid: None) -> tuple[int, bytes]:
    """Run the entrypoint, capturing its stderr via a real file, not a pipe.

    A pipe's write end is inherited by any grandchild the entrypoint detaches
    (a browser, a helper daemon) and leaves running past this run's own
    lifetime. Once this process closes its read end, that grandchild's next
    stderr write raises EPIPE/SIGPIPE and can kill it. A regular file has no
    such failure mode: even after it is unlinked here, anyone still holding
    the fd open (the detached grandchild) keeps writing to it harmlessly
    until they close it -- exactly like inherited-stderr-to-a-log-file
    worked before this capture existed. No thread is needed either: the
    child's stderr fd is duped directly onto a real file, and only after the
    run's own exit is the file read back, forwarded to this process's real
    stderr, and deleted.
    """
    capture_path = scratch_dir / "entrypoint-stderr.log"
    descriptor = os.open(
        capture_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        return_code = _run_entrypoint(
            command, env=env, timeout_seconds=timeout_seconds,
            termination_grace_seconds=termination_grace_seconds,
            cancelled=cancelled, on_started=on_started,
            stderr_capture_fd=descriptor)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
    replay = b""
    tail = b""
    try:
        with capture_path.open("rb") as captured:
            captured.seek(0, os.SEEK_END)
            size = captured.tell()
            if size <= ENTRYPOINT_STDERR_REPLAY_MAX_BYTES:
                captured.seek(0)
                replay = captured.read(size)
                tail = replay[-ENTRYPOINT_STDERR_TAIL_MAX_BYTES:]
            else:
                captured.seek(0)
                head = captured.read(ENTRYPOINT_STDERR_REPLAY_EDGE_BYTES)
                captured.seek(size - ENTRYPOINT_STDERR_REPLAY_EDGE_BYTES)
                end = captured.read(ENTRYPOINT_STDERR_REPLAY_EDGE_BYTES)
                replay = head + ENTRYPOINT_STDERR_TRUNCATION_MARKER + end
                tail = end[-ENTRYPOINT_STDERR_TAIL_MAX_BYTES:]
    except OSError:
        replay = b""
        tail = b""
    finally:
        try:
            capture_path.unlink()
        except OSError:
            pass
    if replay:
        try:
            sys.stderr.buffer.write(replay)
            sys.stderr.buffer.flush()
        except (OSError, ValueError):
            pass
    return return_code, tail


def _dispatch_arguments(arguments: object, loop_id: str, entry: dict,
                        root: Path) -> list[str] | None:
    current = [str(root / "bin/lm-loop-run"), loop_id, str(root)]
    if arguments == current:
        return current
    if (not isinstance(arguments, list) or len(arguments) != 3
            or not all(isinstance(value, str) for value in arguments)
            or not _loaded_v2_release(arguments, loop_id)):
        return None
    try:
        loaded_root = Path(arguments[2]).resolve(strict=True)
        manifest = json.loads((loaded_root / "RELEASE.json").read_text())
        loaded_registry = validate_registry(json.loads(
            (loaded_root / "config/loop-registry.json").read_text()))
        loaded_entry = loaded_registry["loops"][loop_id]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    if (not isinstance(manifest, dict)
            or loaded_root.parent != root.parent
            or manifest.get("provenance") != "ancestor-of-origin-main"
            or manifest.get("release_paths") != "ALL"
            or not isinstance(manifest.get("sha"), str)
            or re.fullmatch(r"[0-9a-f]{40}", manifest["sha"]) is None
            or loaded_entry["label"] != entry["label"]
            or _resource_class(loaded_entry) != _resource_class(entry)):
        return None
    return arguments


def _dispatch_reserved(loop_ids: list[str], *, current: Path | None = None,
                       agents_dir: Path | None = None) -> list[str]:
    """Kick only validated loaded-idle owners; reservations recover on failure."""
    root = (current or Path("~/loops/current").expanduser()).resolve()
    installed = agents_dir or Path("~/Library/LaunchAgents").expanduser()
    try:
        registry = validate_registry(json.loads(
            (root / "config/loop-registry.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    safe = root / "bin/launchctl-safe"
    started = []
    pending = list(loop_ids)
    attempted: set[str] = set()

    def cancel(loop_id: str) -> None:
        try:
            cancel_durable_resource(loop_id)
        except (OSError, RuntimeError, sqlite3.Error):
            pass

    def defer(loop_id: str) -> None:
        try:
            if defer_durable_resource(loop_id, cooldown_seconds=60) is True:
                pending.extend(reserve_available_resource())
        except (OSError, RuntimeError, sqlite3.Error):
            pass

    for loop_id in pending:
        if loop_id in attempted:
            continue
        attempted.add(loop_id)
        entry = registry["loops"].get(loop_id)
        if not isinstance(entry, dict) or entry.get("cadence", {}).get("keep_alive"):
            cancel(loop_id)
            continue
        label = entry["label"]
        plist = installed / f"{label}.plist"
        try:
            arguments = plistlib.loads(plist.read_bytes()).get("ProgramArguments")
        except (OSError, ValueError, plistlib.InvalidFileException):
            defer(loop_id)
            continue
        expected = _dispatch_arguments(arguments, loop_id, entry, root)
        if expected is None:
            defer(loop_id)
            continue
        service = f"gui/{os.getuid()}/{label}"
        try:
            observed = subprocess.run(
                [str(safe), "print", service], capture_output=True, text=True,
                check=False, timeout=10)
            if observed.returncode != 0 or _loaded_arguments(observed.stdout) != expected:
                defer(loop_id)
                continue
            if (re.search(r"\bstate\s*=\s*running\b", observed.stdout)
                    or re.search(r"\bpid\s*=\s*[1-9][0-9]*\b", observed.stdout)):
                continue
            if not re.search(r"\bstate\s*=\s*(?:not running|waiting)\b", observed.stdout):
                defer(loop_id)
                continue
            kicked = subprocess.run(
                [str(safe), "kickstart", service], capture_output=True, text=True,
                check=False, timeout=10)
            if kicked.returncode != 0:
                continue
            readback = subprocess.run(
                [str(safe), "print", service], capture_output=True, text=True,
                check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if readback.returncode == 0:
            started.append(loop_id)
    return started


def _run_admitted(command: list[str], entry: dict, loop_id: str, env: dict[str, str],
                  receipt: Path, *, occurrence_id: str | None = None,
                  on_claimed: Callable[[str], None] = lambda _value: None,
                  on_stderr_tail: Callable[[bytes], None] = lambda _tail: None) -> int:
    env = _child_environment_for_owner(loop_id, env)
    limit = _runtime_limit(entry)
    if loop_id in CONTROL_PLANE_SAFETY_LOOPS or limit is None:
        # Exempt owners have a native wake identity, but no durable claim.
        # Discard inherited occurrence/hint context before passing that identity.
        env = {key: value for key, value in env.items()
               if key not in {"LIFE_MANAGER_OCCURRENCE_ID", "LIFE_MANAGER_RESULT_HINT_PATH"}}
        if occurrence_id is not None:
            env["LIFE_MANAGER_OCCURRENCE_ID"] = occurrence_id
    if loop_id in CONTROL_PLANE_SAFETY_LOOPS:
        if entry.get("effect_class") == "none":
            try:
                clear_no_effect_unknown_resource(loop_id)
            except (OSError, RuntimeError, sqlite3.Error) as error:
                print(f"lm-loop-run: no-effect recovery deferred: {error}", file=sys.stderr)
        _atomic_json(receipt, {"status": "pass", "effect": 0,
                              "reason": "control_plane_exempt"})
        if limit is None:
            result = _run_entrypoint(command, env=env, timeout_seconds=None)
        else:
            result, tail = _run_entrypoint_with_stderr_capture(
                command, receipt.parent, env=env, timeout_seconds=limit)
            on_stderr_tail(tail)
        if result == 0 and loop_id != "capafy-loop-healthcheck":
            try:
                if durable_protocol_version() == 2:
                    reserved = reserve_available_resource()
                    if reserved:
                        _dispatch_reserved(reserved)
            except (OSError, RuntimeError, sqlite3.Error) as error:
                print(f"lm-loop-run: safety dispatch deferred: {error}", file=sys.stderr)
        return result
    if limit is None:
        _atomic_json(receipt, {"status": "pass", "effect": 0,
                              "reason": "continuous_owner_exempt"})
        # A continuous/keep-alive owner's process is meant to run indefinitely;
        # capturing its stderr to a file has no natural end and no bound. Keep
        # stderr inherited exactly as before capture existed for every other
        # owner -- no capture here.
        return _run_entrypoint(command, env=env, timeout_seconds=None)
    try:
        minimum_free = int(os.environ.get("LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT", "15"))
    except ValueError:
        return 64
    if not 1 <= minimum_free <= 100:
        return 64
    claim = None
    claim_started_child = False
    heartbeat_stop = threading.Event()
    heartbeat_failed = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    durable = False
    dispatch_after_release: list[str] = []
    interrupted = False
    return_code: int | None = None
    previous = {}
    pre_effect_hint_allowed = (entry.get("entrypoint") in PRE_EFFECT_HINT_ENTRYPOINTS
                                or loop_id in PRE_EFFECT_HINT_LOOP_IDS)
    effect_result_hint_allowed = entry.get("entrypoint") in EFFECT_RESULT_HINT_ENTRYPOINTS
    hint_allowed = pre_effect_hint_allowed or effect_result_hint_allowed

    def interrupt_wait(_signum, _frame):
        nonlocal interrupted
        interrupted = True

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, interrupt_wait)
        try:
            durable = durable_protocol_version() == 2
        except (OSError, RuntimeError, sqlite3.Error):
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_unavailable"})
            return 75
        disk_deferred = _disk_headroom_deferred(receipt.parent, phase="pre_enqueue")
        if interrupted:
            if durable:
                try:
                    defer_durable_resource(loop_id)
                except (OSError, RuntimeError, sqlite3.Error):
                    pass
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
            return 75
        if disk_deferred is not None:
            if durable:
                try:
                    defer_durable_resource(loop_id, cooldown_seconds=60)
                except (OSError, RuntimeError, sqlite3.Error):
                    pass
            _atomic_json(receipt, disk_deferred)
            return 75
        resource_class = _resource_class(entry)
        admission_class = _admission_class(entry)
        queue_priority = _queue_priority(entry)
        try:
            enqueue_kwargs = {"admission_class": admission_class}
            if queue_priority is not None:
                enqueue_kwargs["priority"] = queue_priority
            if occurrence_id is not None:
                enqueue_kwargs["occurrence_id"] = occurrence_id
            if entry.get("coalesce_queued_wakes") is True:
                enqueue_kwargs["coalesce_reserved"] = True
            if entry.get("effect_class") == "none":
                enqueue_kwargs["allow_no_effect_recovery"] = True
            if admission_effect_scope(entry) == "occurrence":
                enqueue_kwargs["effect_scope"] = "occurrence"
            ticket, admission_reason = _admission_with_retry(
                lambda: enqueue_durable_resource(resource_class, loop_id, **enqueue_kwargs)
            ) if durable else (None, "legacy")
        except (OSError, RuntimeError, sqlite3.Error):
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_unavailable"})
            return 75
        if durable and ticket is None:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": f"resource_{admission_reason}"})
            return 75
        available = memory_free_percent()
        if interrupted:
            if durable:
                try:
                    defer_durable_resource(loop_id)
                except (OSError, RuntimeError, sqlite3.Error):
                    pass
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
            return 75
        if available is None or available < minimum_free:
            if durable:
                try:
                    defer_durable_resource(loop_id)
                except (OSError, RuntimeError, sqlite3.Error):
                    pass
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                         "reason": "memory_headroom_unavailable" if available is None
                         else "memory_headroom_low"})
            return 75
        try:
            claim = None
            admission_reason = None
            claim_kwargs = {"admission_class": admission_class}
            if admission_effect_scope(entry) == "occurrence":
                claim_kwargs["effect_scope"] = "occurrence"
            if durable and entry.get("coalesce_queued_wakes") is True and occurrence_id is not None:
                claim_kwargs["coalesced_occurrence_id"] = occurrence_id
            claim, admission_reason = (
                _admission_with_retry(
                    lambda: claim_durable_resource(
                        resource_class, loop_id, **claim_kwargs),
                    cancelled=lambda: interrupted,
                ) if durable else try_acquire_resource(
                        resource_class, loop_id, admission_class=admission_class,
                        retain_ticket=False, required_protocol=1)
            )
        except (OSError, RuntimeError, sqlite3.Error):
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_unavailable"})
            return 75
        if claim is None:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": f"resource_{admission_reason}"})
            if durable and not interrupted:
                try:
                    _dispatch_reserved(reserve_available_resource())
                except (OSError, RuntimeError, sqlite3.Error) as error:
                    print(f"lm-loop-run: reservation dispatch deferred: {error}",
                          file=sys.stderr)
            return 75
        claimed_occurrence_id = occurrence_id
        if durable and occurrence_id is not None:
            try:
                claimed_occurrence_id = json.loads(claim.read_text(encoding="utf-8")).get(
                    "occurrence_id")
                if (not isinstance(claimed_occurrence_id, str)
                        or not OCCURRENCE_ID_PATTERN.fullmatch(claimed_occurrence_id)
                        or not claimed_occurrence_id.startswith(f"{loop_id}:")):
                    raise ValueError("invalid claimed occurrence")
            except (OSError, ValueError, AttributeError):
                _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                      "reason": "resource_claim_identity_invalid"})
                return 75
            on_claimed(claimed_occurrence_id)
        disk_deferred = _disk_headroom_deferred(receipt.parent, phase="post_claim")
        if interrupted:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
            return 75
        if disk_deferred is not None:
            _atomic_json(receipt, disk_deferred)
            return 75
        available = memory_free_percent()
        if interrupted:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
            return 75
        if available is None or available < minimum_free:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                         "reason": "memory_headroom_unavailable" if available is None
                         else "memory_headroom_low"})
            return 75
        _atomic_json(receipt, {"status": "pass", "effect": 0,
                              "reason": "resource_slot_acquired",
                              "resource_class": resource_class})
        if interrupted:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
            return 75

        def transfer_claim(child_pid: int) -> None:
            nonlocal claim_started_child, heartbeat_thread
            transfer_durable_resource(claim, child_pid)
            claim_started_child = True
            if durable:
                heartbeat_thread = threading.Thread(
                    target=_heartbeat_loop,
                    args=(claim, heartbeat_stop, heartbeat_failed),
                    name=f"lm-heartbeat-{loop_id}", daemon=True,
                )
                heartbeat_thread.start()

        child_env = {key: value for key, value in env.items()
                     if key not in {"LIFE_MANAGER_OCCURRENCE_ID", "LIFE_MANAGER_RESULT_HINT_PATH"}}
        if hint_allowed:
            hint_path = receipt.parent / "entrypoint-result.json"
            child_env["LIFE_MANAGER_RESULT_HINT_PATH"] = str(hint_path)
            if pre_effect_hint_allowed:
                # Establish the fail-closed pre-effect state before spawning the
                # child.  The allowlisted owner clears this marker immediately
                # before its first mutation; if it dies before then, the host
                # can safely release the claim without inventing an unknown
                # external effect.
                _atomic_json(hint_path, {"status": "pre_effect_failure", "effect": 0})
        if claimed_occurrence_id is not None:
            child_env["LIFE_MANAGER_OCCURRENCE_ID"] = claimed_occurrence_id
        if effect_result_hint_allowed:
            child_env["LIFE_MANAGER_LOOP_ID"] = loop_id
        # This branch is only reached when limit is not None (the
        # limit-is-None/continuous_owner_exempt case already returned above),
        # so capture is always safe here.
        return_code, stderr_tail = _run_entrypoint_with_stderr_capture(
            command, receipt.parent, env=child_env, timeout_seconds=limit,
            cancelled=lambda: interrupted or heartbeat_failed.is_set(),
            on_started=transfer_claim)
        on_stderr_tail(stderr_tail)
        if heartbeat_failed.is_set():
            return_code = 75
            try:
                _atomic_json(receipt, {
                    "status": "deferred", "effect": 0,
                    "reason": "resource_heartbeat_unavailable",
                })
            except OSError:
                pass
        if return_code == 75 and interrupted:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
        return return_code
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            # heartbeat_durable may wait up to five seconds for the shared
            # control lock; never let the daemon thread outlive claim release.
            heartbeat_thread.join(timeout=6)
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if claim is not None:
            try:
                if durable:
                    release_options = {"requeue": not claim_started_child,
                                       "reserve": claim_started_child}
                    if (claim_started_child and return_code != 0
                            and entry.get("effect_class") != "none"
                            and not (pre_effect_hint_allowed and _proven_pre_effect_failure(
                                receipt.parent / "entrypoint-result.json"))):
                        release_options["effect_unknown"] = True
                    dispatch_after_release = _release_with_retry(
                        lambda: release_and_reserve_resource(claim, **release_options)
                    )
                else:
                    release_resource(claim)
            except (OSError, RuntimeError, sqlite3.Error) as error:
                print(f"lm-loop-run: resource release deferred to stale recovery: {error}",
                      file=sys.stderr)
        if dispatch_after_release:
            _dispatch_reserved(dispatch_after_release)


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 2:
        print("usage: lm-loop-run <loop-id> <release-root>", file=sys.stderr); return 64
    loop_id, release_value = args
    release_root = Path(release_value).resolve()
    try:
        registry = json.loads((release_root / "config/loop-registry.json").read_text())
        manifest = json.loads((release_root / "RELEASE.json").read_text())
        if not isinstance(manifest.get("sha"), str) or len(manifest["sha"]) != 40:
            raise ValueError("invalid release manifest SHA")
        entry = registry.get("loops", {}).get(loop_id)
        if not isinstance(entry, dict):
            raise ValueError(f"unknown loop id: {loop_id}")
        loop_state_root = Path(os.path.expanduser(
            os.environ.get("LIFE_MANAGER_STATE_ROOT", entry["state_root"])))
        run_id = os.environ.get("LIFE_MANAGER_RUN_ID") or f"{time.time_ns():x}-{os.getpid()}"
        wake_id = _wake_id(run_id)
        product_loop_id = _product_loop_for_job(release_root, loop_id)
        occurrence_id = f"{loop_id}:{run_id}"
        start_env_sha256 = _identity_sha256({
            "job_id": loop_id,
            "owner_id": loop_id,
            "run_id": run_id,
            "wake_id": wake_id,
            "occurrence_id": occurrence_id,
            "release_sha": manifest["sha"],
        })
        event_path = loop_state_root / "events.jsonl"
        current = Path("~/loops/current").expanduser()
        item_lock = _label_apply_lock_path(current, entry["label"])
        with ExitStack() as apply_lock_stack:
            try:
                # The per-label apply lock is held only while that one label is being
                # re-bootstrapped (seconds, up to ~2 minutes). A wake that lands in that window used
                # to exit 78 at once, which loses a daily one-shot for the whole day
                # (article-daily 06:00). Wait for it, then fall back to the recorded deferral.
                lock_wait_deadline = time.monotonic() + float(
                    os.environ.get("LIFE_MANAGER_APPLY_LOCK_WAIT_SECONDS", "150"))
                while True:
                    try:
                        apply_lock_stack.enter_context(_apply_lock(current, item_lock))
                        break
                    except RuntimeError as busy:
                        if str(busy) != "production apply is already owned" \
                                or time.monotonic() >= lock_wait_deadline:
                            raise
                        time.sleep(5)
            except RuntimeError as error:
                if str(error) != "production apply is already owned":
                    raise
                event = build_runtime_event(
                    loop_id=loop_id, domain=entry["domain"], run_id=run_id,
                    release_sha=manifest["sha"], provider=entry["provider_route"],
                    profile_alias=None, effect_class=entry["effect_class"],
                    succeeded=False, deferred=True, blocker="apply_lock_busy",
                    evidence_scheme="lm-loop", product_loop_id=product_loop_id,
                    job_id=loop_id, owner_id=loop_id, wake_id=wake_id,
                    loaded_argv_sha256=None, loaded_env_sha256=start_env_sha256,
                    exit_code=78, failure_layer="runtime",
                    error_class="apply_lock_busy", retryable=True,
                    next_action="retry_after_eligibility",
                )
                event["effect_status"] = "not_applicable"
                validate_runtime_event(event)
                try:
                    append_runtime_event(event_path, event)
                except (OSError, ValueError) as write_error:
                    print(json.dumps({
                        "event": "runtime_event_write_failed",
                        "timestamp": event["timestamp"],
                        "event_id": event["event_id"],
                        "loop_id": loop_id,
                        "job_id": loop_id,
                        "owner_id": loop_id,
                        "wake_id": wake_id,
                        "run_id": run_id,
                        "occurrence_id": occurrence_id,
                        "product_loop_id": product_loop_id,
                        "release_sha": manifest["sha"],
                        "phase": "report",
                        "status": event["status"],
                        "blocker": event["blocker"],
                        "failure_layer": "runtime",
                        "effect_class": event["effect_class"],
                        "effect_status": event["effect_status"],
                        "error_class": event["error_class"],
                        "exit_code": event["exit_code"],
                        "retryable": event["retryable"],
                        "next_action": event["next_action"],
                        "loaded_argv_sha256": event["loaded_argv_sha256"],
                        "loaded_env_sha256": event["loaded_env_sha256"],
                        "provider_receipt_id": event["provider_receipt_id"],
                        "official_readback_ref": event["official_readback_ref"],
                        "writer_error_type": type(write_error).__name__,
                        "writer_errno": getattr(write_error, "errno", None),
                    }, sort_keys=True, separators=(",", ":")), file=sys.stderr)
                return 78
            command = build_loop_command(registry, loop_id, release_root)
            loaded_argv_sha256 = _identity_sha256(command)
            scratch, scratch_parent_fd, scratch_fd = reset_loop_scratch(
                loop_state_root, loop_id, run_id, effect_class=entry["effect_class"])
            try:
                append_runtime_event(event_path, build_runtime_start_event(
                    loop_id=loop_id, domain=entry["domain"], run_id=run_id,
                    release_sha=manifest["sha"], provider=entry["provider_route"],
                    profile_alias=None, effect_class=entry["effect_class"],
                    product_loop_id=product_loop_id, job_id=loop_id,
                    owner_id=loop_id, wake_id=wake_id,
                    occurrence_id=occurrence_id,
                    loaded_argv_sha256=loaded_argv_sha256,
                    loaded_env_sha256=start_env_sha256,
                ))
            except (OSError, ValueError) as error:
                print(f"lm-loop-run: start event failed: {error}", file=sys.stderr)
        host_receipt = scratch / "host-admission.json"
        started_ns = time.time_ns()
        claimed_occurrence_id = None
        def record_claimed(value: str) -> None:
            nonlocal claimed_occurrence_id
            claimed_occurrence_id = value
        entrypoint_stderr_tail = b""
        def record_stderr_tail(value: bytes) -> None:
            nonlocal entrypoint_stderr_tail
            entrypoint_stderr_tail = value
        return_code = _run_admitted(command, entry, loop_id, {
            **os.environ, "LIFE_MANAGER_RELEASE_ROOT": str(release_root),
            "LIFE_MANAGER_RUN_ID": run_id,
            "LIFE_MANAGER_EFFECT_IDENTITY_PATH": str(scratch / "effect-identity.jsonl"),
            "TMPDIR": f"{scratch}/", "NPM_CONFIG_CACHE": str(scratch / "npm-cache"),
        }, host_receipt, occurrence_id=occurrence_id, on_claimed=record_claimed,
           on_stderr_tail=record_stderr_tail)
        host_deferred = _host_admission_deferred(host_receipt, started_ns)
        effect_result = None
        if (return_code == 0
                and entry.get("entrypoint") in EFFECT_RESULT_HINT_ENTRYPOINTS
                and claimed_occurrence_id is not None):
            hint_path = scratch / "entrypoint-result.json"
            if entry.get("entrypoint") in NO_EFFECT_RESULT_HINT_ENTRYPOINTS:
                effect_result = _verified_no_effect_result(
                    hint_path, loop_id, claimed_occurrence_id, entry["entrypoint"])
            if effect_result is None:
                effect_result = _verified_effect_result(
                    hint_path, loop_id, claimed_occurrence_id)
        effect_identity_ref = None
        effect_identity_status = None
        if entry.get("effect_class") != "none" and return_code != 0:
            try:
                identity_result = _persist_effect_identity(
                    scratch / "effect-identity.jsonl", loop_state_root, loop_id, run_id,
                    claimed_occurrence_id,
                )
                effect_identity_status = identity_result.status
                effect_identity_ref = identity_result.ref
            except (OSError, ValueError) as error:
                print(f"lm-loop-run: effect identity preservation deferred: {error}", file=sys.stderr)
        terminal_saved = False
        event = None
        terminal_error = None
        try:
            succeeded, deferred, blocker = _terminal_outcome(
                return_code, host_deferred=host_deferred)
            error_detail = (
                entrypoint_stderr_tail.decode("utf-8", errors="replace")
                if not succeeded and entrypoint_stderr_tail else None
            )
            event = build_runtime_event(
                loop_id=loop_id, domain=entry["domain"], run_id=run_id,
                release_sha=manifest["sha"], provider=entry["provider_route"],
                profile_alias=None, effect_class=entry["effect_class"],
                succeeded=succeeded, deferred=deferred, blocker=blocker,
                evidence_scheme="lm-loop",
                claimed_occurrence_id=claimed_occurrence_id,
                effect_identity_ref=effect_identity_ref,
                effect_identity_status=effect_identity_status,
                product_loop_id=product_loop_id,
                job_id=loop_id,
                owner_id=loop_id,
                wake_id=wake_id,
                loaded_argv_sha256=loaded_argv_sha256,
                loaded_env_sha256=_identity_sha256({
                    "job_id": loop_id,
                    "owner_id": loop_id,
                    "run_id": run_id,
                    "wake_id": wake_id,
                    "occurrence_id": claimed_occurrence_id or occurrence_id,
                    "release_sha": manifest["sha"],
                }),
                exit_code=return_code,
                error_detail=error_detail,
            )
            event = _apply_verified_effect_result(event, effect_result)
            append_runtime_event(event_path, event)
            terminal_saved = True
        except (OSError, ValueError) as error:
            terminal_error = error
            print(f"lm-loop-run: terminal event failed: {error}", file=sys.stderr)
        if terminal_saved and event is not None and _should_enqueue_recovery_intent(entry, event):
            try:
                _enqueue_recovery_intent(release_root, event, scratch)
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                print(f"lm-loop-run: recovery intent append failed: {error}", file=sys.stderr)
        try:
            cleanup_status = "held_terminal_unrecorded"
            cleanup_operation = "terminal_not_saved"
            cleanup_error = terminal_error
            if terminal_saved:
                try:
                    cleanup_operation = "unprotect_marker"
                    unprotect_loop_scratch(scratch_fd)
                    cleanup_operation = "remove_owned_tree"
                    removed = remove_owned_tree(scratch_parent_fd, scratch_fd, run_id)
                    cleanup_status = "removed" if removed else "preserved"
                    cleanup_error = None
                except Exception as error:
                    cleanup_status = "error"
                    cleanup_error = error
            if cleanup_status != "removed":
                try:
                    _record_scratch_cleanup_diagnostic(
                        loop_state_root, scratch_parent_fd, scratch_fd,
                        loop_id=loop_id, run_id=run_id,
                        occurrence_id=claimed_occurrence_id or occurrence_id,
                        release_sha=manifest["sha"], terminal_saved=terminal_saved,
                        phase=("terminal_cleanup" if terminal_saved
                               else "terminal_unrecorded_hold"),
                        cleanup_status=cleanup_status,
                        cleanup_operation=cleanup_operation,
                        error=cleanup_error,
                        loaded_argv_sha256=loaded_argv_sha256,
                        loaded_env_sha256=(event.get("loaded_env_sha256")
                                           if isinstance(event, dict)
                                           else start_env_sha256),
                        command=entry["entrypoint"],
                    )
                except Exception as error:
                    print(json.dumps({
                        "event": "scratch_cleanup_diagnostic_write_failed",
                        "run_id": run_id,
                        "owner_id": loop_id,
                        "occurrence_id": claimed_occurrence_id or occurrence_id,
                        "release_sha": manifest["sha"],
                        "phase": "diagnostic_record",
                        "cleanup_status": cleanup_status,
                        "error_class": type(error).__name__,
                        "errno": getattr(error, "errno", None),
                        "command": entry["entrypoint"],
                    }, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        finally:
            os.close(scratch_fd)
            os.close(scratch_parent_fd)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"lm-loop-run: {error}", file=sys.stderr); return 78
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
