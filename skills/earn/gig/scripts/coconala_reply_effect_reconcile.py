#!/usr/bin/env python3
"""Reconcile one Coconala reply fence from an exact official thread receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.host import resource_admission  # noqa: E402


OWNER_ID = "hf-gig-reply-detector"
BROWSER_IDENTITY = "coconala:kosuke"
WITH_BROWSER = ROOT / "skills/browser/with-browser.sh"
REPLY_ROOT = Path.home() / ".local/state/life-manager/coconala/reply"
DEFAULT_KERNEL_ROOT = REPLY_ROOT / "kernel"
READBACK_MARKER = "COCONALA_READBACK "
GIG_VAULT = Path.home() / ".cloak/vault/gig-daily-driver/auth-state.json"


def _json_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _intent_intact(intent: dict) -> bool:
    """The reply intent still hashes to its own effect key and content digest."""
    thread_id, latest_event_id = intent.get("thread_id"), intent.get("latest_event_id")
    payload, effect_key = intent.get("payload"), intent.get("effect_key")
    content_sha256 = intent.get("content_sha256")
    return (
        intent.get("provider") == "coconala" and intent.get("version") == 1
        and intent.get("account_id") == "default" and intent.get("action") == "reply"
        and isinstance(thread_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", thread_id) is not None
        and isinstance(latest_event_id, str) and bool(latest_event_id)
        and isinstance(payload, dict) and isinstance(payload.get("body"), str)
        and isinstance(content_sha256, str) and content_sha256 == _json_sha256(payload)
        and effect_key == _json_sha256({
            "version": 1, "provider": "coconala", "account_id": "default",
            "thread_id": thread_id, "latest_event_id": latest_event_id,
            "action": "reply", "payload": payload, "content_sha256": content_sha256,
        })
    )


def _load_state(path: Path, kernel_root: Path, occurrence_id: str) -> tuple[dict, dict] | None:
    try:
        if path.is_symlink():
            return None
        root = (kernel_root / "threads").resolve(strict=True)
        resolved = path.resolve(strict=True)
        if not resolved.is_file() or not resolved.is_relative_to(root):
            return None
        state = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict):
        return None
    intent = state.get("intent")
    if (state.get("status") == "verified" and state.get("occurrence_id") == occurrence_id
            and isinstance(intent, dict) and _intent_intact(intent)):
        # The owner later recorded this exact reply as sent, but only with a local hash
        # receipt; the fence still needs a live provider message id (see _child_readback).
        return state, intent
    if state.get("status") != "reconcile_unknown":
        return None
    diagnostic = state.get("send_diagnostic")
    if not isinstance(intent, dict) or not isinstance(diagnostic, dict):
        return None
    thread_id = intent.get("thread_id")
    latest_event_id = intent.get("latest_event_id")
    payload = intent.get("payload")
    effect_key = intent.get("effect_key")
    content_sha256 = intent.get("content_sha256")
    if (
        diagnostic.get("current_claimed_occurrence_id") != occurrence_id
        or diagnostic.get("stored_intent_occurrence_id") != state.get("occurrence_id")
        or diagnostic.get("effect_status") != "unknown"
        or intent.get("provider") != "coconala"
        or intent.get("version") != 1
        or intent.get("account_id") != "default"
        or intent.get("action") != "reply"
        or not isinstance(thread_id, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", thread_id) is None
        or not isinstance(latest_event_id, str)
        or not latest_event_id
        or not isinstance(payload, dict)
        or not isinstance(payload.get("body"), str)
        or not isinstance(effect_key, str)
        or re.fullmatch(r"[0-9a-f]{64}", effect_key) is None
        or not isinstance(content_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", content_sha256) is None
        or diagnostic.get("effect_key") != effect_key
        or diagnostic.get("content_sha256") != content_sha256
        or content_sha256 != _json_sha256(payload)
        or diagnostic.get("intent_sha256") != _json_sha256(intent)
        or effect_key != _json_sha256({
            "version": 1, "provider": "coconala", "account_id": "default",
            "thread_id": thread_id, "latest_event_id": latest_event_id,
            "action": "reply", "payload": payload,
            "content_sha256": content_sha256,
        })
    ):
        return None
    thread_identity = "\0".join(("coconala", "default", thread_id))
    if (
        diagnostic.get("thread_identity_sha256") != hashlib.sha256(thread_identity.encode()).hexdigest()
        or diagnostic.get("event_identity_sha256") != hashlib.sha256(latest_event_id.encode()).hexdigest()
    ):
        return None
    return state, intent


def _find_target(kernel_root: Path, occurrence_id: str) -> tuple[Path, dict] | None:
    threads = kernel_root / "threads"
    if threads.is_symlink() or not threads.is_dir():
        return None
    matches = []
    for directory in threads.iterdir():
        if directory.is_symlink() or not directory.is_dir():
            continue
        path = directory / "state.json"
        if path.is_symlink() or not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        diagnostic = raw.get("send_diagnostic") if isinstance(raw, dict) else None
        if isinstance(diagnostic, dict) and diagnostic.get("current_claimed_occurrence_id") == occurrence_id:
            matches.append(path)
        elif (isinstance(raw, dict) and raw.get("status") == "verified"
              and raw.get("occurrence_id") == occurrence_id):
            matches.append(path)
    if len(matches) != 1:
        return None
    loaded = _load_state(matches[0], kernel_root, occurrence_id)
    return (matches[0], loaded[1]) if loaded is not None else None


def _find_targets(kernel_root: Path, occurrence_id: str) -> list[Path] | None:
    """Every reply state bound to this occurrence; one run may answer several threads.

    The fence covers all of them, so every one must load intact (None otherwise)."""
    threads = kernel_root / "threads"
    if threads.is_symlink() or not threads.is_dir():
        return None
    matches = []
    for directory in sorted(threads.iterdir()):
        path = directory / "state.json"
        if directory.is_symlink() or path.is_symlink() or not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        diagnostic = raw.get("send_diagnostic")
        bound = ((isinstance(diagnostic, dict)
                  and diagnostic.get("current_claimed_occurrence_id") == occurrence_id)
                 or (raw.get("status") == "verified" and raw.get("occurrence_id") == occurrence_id))
        if bound:
            if _load_state(path, kernel_root, occurrence_id) is None:
                return None
            matches.append(path)
    return matches or None


def _load_adapter():
    path = ROOT / "skills/earn/gig/scripts/coconala_reply_adapter.py"
    spec = importlib.util.spec_from_file_location("coconala_reply_effect_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("coconala_reply_adapter_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _child_readback(state_path: Path, kernel_root: Path, occurrence_id: str) -> dict:
    loaded = _load_state(state_path, kernel_root, occurrence_id)
    if loaded is None:
        return {"status": "unknown", "reason": "exact_reply_state_changed"}
    _state, intent = loaded
    module = _load_adapter()
    adapter = module.CoconalaReplyAdapter(state_root=REPLY_ROOT)
    adapter._receipts = {}  # a cached sha256_ receipt is local; force the live thread read
    result = adapter.readback(intent)
    receipt_id = result.get("provider_receipt_id")
    if result.get("verified") is not True or not isinstance(receipt_id, str):
        return _unique_thread_text(module, adapter, intent)
    if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", receipt_id) is None or receipt_id.startswith("sha256_"):
        return {"status": "unknown", "reason": "provider_receipt_id_invalid"}
    observed_at = result.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at.strip():
        return {"status": "unknown", "reason": "provider_readback_time_missing"}
    return {
        "status": "verified", "provider_receipt_id": receipt_id,
        "observed_at": observed_at,
    }


def _unique_thread_text(module, adapter, intent: dict) -> dict:
    """Coconala DMs carry no native message id, so the collector ids are text hashes and
    buyer ids drift when attachments change. The official thread is still authoritative:
    exactly one seller message whose body equals the intended reply proves it was sent
    once. Zero or several matches stay unknown."""
    try:
        context, _bounded = adapter._thread_reader(intent["thread_id"])
    except RuntimeError as error:
        # Same text-only fallback the owner's own readback uses when attachment ids drift.
        if str(error) != "collector_unhealthy:dm_attachment_message_identity_changed":
            return {"status": "unknown", "reason": "official_thread_unreadable"}
        try:
            context, _bounded = adapter._read_thread_text_only(intent["thread_id"])
        except Exception:
            return {"status": "unknown", "reason": "official_thread_unreadable"}
    except Exception:
        return {"status": "unknown", "reason": "official_thread_unreadable"}
    conversation = context.get("conversation") if isinstance(context, dict) else None
    if not isinstance(conversation, list):
        return {"status": "unknown", "reason": "official_thread_unreadable"}
    wanted = module.reply_browser.outgoing_sha256(intent["payload"]["body"])
    matching = [
        row for row in conversation
        if isinstance(row, dict) and row.get("side") == "seller"
        and module.reply_browser.outgoing_sha256(str(row.get("body") or "")) == wanted
    ]
    if len(matching) != 1:
        return {"status": "unknown", "reason": "exact_provider_message_missing"}
    message_id = str(matching[0].get("message_id") or "")
    if re.fullmatch(r"[A-Za-z0-9._-]{1,120}", message_id) is None:
        return {"status": "unknown", "reason": "provider_receipt_id_invalid"}
    return {"status": "verified",
            "provider_receipt_id": f"coconala-dm-{intent['thread_id']}-{message_id}",
            "observed_at": datetime.now(timezone.utc).isoformat()}


def _parse_child_output(stdout: str) -> dict | None:
    records = []
    for line in stdout.splitlines():
        if not line.startswith(READBACK_MARKER):
            continue
        try:
            value = json.loads(line[len(READBACK_MARKER):])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records[0] if len(records) == 1 else None


def _browser_readback(
    state_path: Path, kernel_root: Path, occurrence_id: str,
    *, runner=None,
) -> dict:
    command = [
        "bash", str(WITH_BROWSER), BROWSER_IDENTITY, "--", sys.executable,
        str(SCRIPT), "--readback-child", "--occurrence", occurrence_id,
        "--kernel-root", str(kernel_root), "--state-path", str(state_path),
    ]
    environment = os.environ.copy()
    environment["BROWSER_WAIT_SECONDS"] = "0"
    environment["AI_ENSURE_PROVISION_BROWSER"] = "/dev/null"
    environment["AI_ENSURE_BROWSER"] = "/dev/null"
    # The fence reconciler has no Coconala session env; without it the leased context
    # is seeded from the personal vault and lands on /login (2026-10-15).
    environment.setdefault("CLOAK_SESSION_VAULT_FILE", str(GIG_VAULT))
    environment.setdefault("CLOAK_BROWSER_OWNER", "gig-reply-reconcile")
    completed = (runner or subprocess.run)(
        command, cwd=ROOT, env=environment, capture_output=True,
        text=True, timeout=150, check=False,
    )
    if completed.returncode != 0:
        return {"status": "unknown", "reason": "browser_readback_unavailable"}
    result = _parse_child_output(completed.stdout or "")
    return result or {"status": "unknown", "reason": "provider_readback_record_missing"}


def _print(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None, *, runner=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--readback-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--state-path", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.readback_child:
        result = (
            _child_readback(args.state_path, args.kernel_root, args.occurrence)
            if args.state_path is not None
            else {"status": "unknown", "reason": "exact_reply_state_missing"}
        )
        print(READBACK_MARKER + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0

    targets = _find_targets(args.kernel_root, args.occurrence)
    if targets is None:
        _print({
            "owner_id": OWNER_ID, "occurrence_id": args.occurrence,
            "status": "unresolved", "verified": False,
            "reason": "exact_reply_state_not_found",
        })
        return 0

    readback_proof: dict = {}

    def official_readback() -> dict:
        receipts = []
        for state_path in targets:
            result = _browser_readback(
                state_path, args.kernel_root, args.occurrence, runner=runner,
            )
            if result.get("status") != "verified":
                return {
                    "owner_id": OWNER_ID, "occurrence_id": args.occurrence,
                    "verified": False,
                }
            receipts.append(result["provider_receipt_id"])
        proof = {
            "owner_id": OWNER_ID, "occurrence_id": args.occurrence,
            "verified": True, "provider_receipt_id": ",".join(receipts),
        }
        readback_proof.update(proof)
        return proof

    resolved = (
        resource_admission.resolve_unknown_occurrence(
            OWNER_ID, args.occurrence, official_readback=official_readback,
            expected_state="claimed",
        )
        if args.resolve else False
    )
    if not args.resolve:
        official_readback()
    output = {
        "owner_id": OWNER_ID, "occurrence_id": args.occurrence,
        "status": "resolved" if resolved else (
            "verified" if readback_proof.get("verified") is True else "unresolved"
        ),
        "verified": readback_proof.get("verified") is True,
        "resolved": resolved,
    }
    if readback_proof.get("verified") is True:
        output["provider_receipt_id"] = readback_proof["provider_receipt_id"]
        output["readback_kind"] = "coconala_thread_text_exact"
    else:
        output["reason"] = "official_provider_receipt_unavailable"
    _print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
