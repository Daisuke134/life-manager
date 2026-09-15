#!/usr/bin/env python3
"""Send one model-approved TikTok DM with exact provider readback.

Candidate qualification and copy are agent judgment. This module owns only the
authenticated sender check, recipient binding, single mutation and reconciliation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import cdp
import tiktok_identity_readback


HANDLE = re.compile(r"@[A-Za-z0-9._-]+\Z")
EDITOR = '[contenteditable="true"][aria-label*="メッセージ"]'


def _handle(value: object, field: str) -> str:
    result = str(value or "").strip()
    if not HANDLE.fullmatch(result):
        raise ValueError(f"{field}_invalid")
    return result.casefold()


def _tiktok_url(value: object, *, expected_path: str | None = None) -> str:
    result = str(value or "").strip()
    parsed = urlparse(result)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in {
        "tiktok.com", "www.tiktok.com"
    }:
        raise ValueError("tiktok_url_invalid")
    if expected_path is not None and unquote(parsed.path).rstrip("/").casefold() != expected_path:
        raise ValueError("profile_candidate_mismatch")
    return result


def _message_route(value: object) -> str | None:
    if not value:
        return None
    try:
        result = _tiktok_url(value)
    except ValueError:
        return None
    return result if urlparse(result).path.rstrip("/") == "/business-suite/messages" else None


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _base(payload: dict, project_root: Path) -> tuple[dict, str, str, str, str, str, Path]:
    if not isinstance(payload, dict):
        raise ValueError("payload_not_object")
    effect_key = str(payload.get("effect_key") or "").strip()
    owner = str(payload.get("owner") or "").strip()
    candidate = _handle(payload.get("candidate_handle"), "candidate_handle")
    sender = _handle(payload.get("expected_sender_handle"), "expected_sender_handle")
    profile = _tiktok_url(payload.get("profile_url"), expected_path=f"/{candidate}")
    message = str(payload.get("message") or "").strip()
    if not effect_key:
        raise ValueError("effect_key_missing")
    if not owner:
        raise ValueError("owner_missing")
    if not message or len(message) > 1000:
        raise ValueError("message_length_invalid")
    delivery = project_root.resolve() / "delivery"
    if not delivery.is_dir():
        raise ValueError("project_delivery_directory_missing")
    ledger = delivery / "tiktok-message-effects.jsonl"
    binding = hashlib.sha256(json.dumps({
        "sender": sender, "recipient": candidate,
        "message_sha256": hashlib.sha256(message.encode()).hexdigest(),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = {
        "schema_version": 1,
        "provider": "tiktok.com",
        "effect_key": effect_key,
        "candidate_handle": candidate,
        "message_sha256": hashlib.sha256(message.encode()).hexdigest(),
        "effect_binding_sha256": binding,
        "effect": 0,
        "exact_readback": False,
        "retry_safe": True,
    }
    return result, owner, candidate, sender, profile, message, ledger


def _records(path: Path, effect_key: str) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict) and row.get("effect_key") == effect_key:
            rows.append(row)
    return rows


def _append(path: Path, result: dict, state: str) -> None:
    row = {
        "schema_version": 1,
        "record_type": "tiktok_dm_effect_fence",
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "effect_key": result["effect_key"],
        "effect_binding_sha256": result["effect_binding_sha256"],
        "candidate_handle": result["candidate_handle"],
        "message_sha256": result["message_sha256"],
        "state": state,
    }
    if result.get("official_url"):
        row["official_url"] = result["official_url"]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def send_one(payload: dict, *, cdp_client=cdp, send: bool = False, wait=time.sleep,
             project_root: Path | None = None) -> dict:
    """Preflight or send once. An uncertain mutation is never retried here."""
    result, owner, candidate, sender, profile, message, ledger = _base(
        payload, (project_root or Path.cwd()).resolve()
    )
    lock = Path(str(ledger) + ".lock").open("a+", encoding="utf-8")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    prior = _records(ledger, result["effect_key"])
    if any(row.get("effect_binding_sha256") != result["effect_binding_sha256"] for row in prior):
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
        raise ValueError("effect_key_payload_conflict")
    target = None
    try:
        target = cdp_client.new_target("https://www.tiktok.com/", owner)
        wait(2)
        identity = None
        for identity_attempt in range(30):
            observed_identity = cdp_client.evaluate(
                target,
                "/* TIKTOK_IDENTITY */" + tiktok_identity_readback.READBACK_EXPRESSION,
            )
            if not isinstance(observed_identity, dict) or "__error__" in observed_identity:
                result["status"] = "sender_identity_unreadable"
                return result
            identity = tiktok_identity_readback.classify_readback(observed_identity, sender)
            if identity["authenticated"] or identity["status"] == "authenticated_identity_mismatch":
                break
            if identity_attempt < 29:
                wait(0.5)
        assert identity is not None
        result["sender_identity"] = identity
        if not identity["authenticated"]:
            result["status"] = ("sender_identity_mismatch" if identity["observed_handle"]
                                else "sender_identity_not_authenticated")
            return result

        cdp_client.navigate(target, profile)
        wait(4)
        route_readback = cdp_client.evaluate(target, r'''/* TIKTOK_PROFILE_ROUTE */ (() => {
          const link = [...document.querySelectorAll('a[href*="/business-suite/messages"][href*="u="]')][0];
          return {url: location.href, message_route: link?.href || null};
        })()''')
        route = _message_route(route_readback.get("message_route") if isinstance(route_readback, dict) else None)
        if route is None:
            result["status"] = "recipient_message_route_unavailable"
            return result

        cdp_client.navigate(target, route)
        wait(7)
        before = cdp_client.evaluate(target, f'''/* TIKTOK_COMPOSER_BEFORE */ (() => {{
          const frame = [...document.querySelectorAll('iframe')].find(x => x.src.includes('/messages?'));
          const doc = frame?.contentDocument;
          const body = doc?.body?.innerText || '';
          const editor = doc?.querySelector({json.dumps(EDITOR)});
          const heads = [...(doc?.querySelectorAll('[data-e2e*="chat-header"],[class*="ChatHeader"],[class*="ConversationHeader"]') || [])];
          const handles = heads.flatMap(node => (node.innerText || '').match(/@[A-Za-z0-9._-]+/g) || []).map(x => x.toLowerCase());
          const recipientBound = handles.includes({json.dumps(candidate)});
          return {{url: location.href, recipient_bound: recipientBound,
            editor: !!editor, editor_empty: !editor || !(editor.innerText || '').trim(),
            exact_message: body.includes({json.dumps(message)})}};
        }})()''')
        if not isinstance(before, dict) or "__error__" in before:
            result["status"] = "composer_unreadable"
            return result
        result["official_url"] = before.get("url")
        if before.get("exact_message") is True and before.get("recipient_bound") is True:
            result.update(status="deduplicated_exact_official_readback", exact_readback=True)
            if not prior or prior[-1].get("state") != "sent":
                _append(ledger, result, "sent")
            return result
        if (before.get("recipient_bound") is not True or before.get("editor") is not True
                or before.get("editor_empty") is not True):
            result["status"] = "composer_recipient_binding_failed"
            return result
        if prior and prior[-1].get("state") in {"attempting", "unknown", "sent"}:
            result.update(status="reconcile_required", retry_safe=False)
            return result
        if not send:
            result["status"] = "ready"
            return result

        focused = cdp_client.evaluate(target, f'''/* TIKTOK_FOCUS */ (() => {{
          const frame = [...document.querySelectorAll('iframe')].find(x => x.src.includes('/messages?'));
          const editor = frame?.contentDocument?.querySelector({json.dumps(EDITOR)});
          if (!editor) return false; editor.focus(); return true;
        }})()''')
        if focused is not True:
            result["status"] = "composer_focus_failed"
            return result
        cdp_client.insert(target, message)
        filled = cdp_client.evaluate(target, f'''/* TIKTOK_FILLED */ (() => {{
          const frame = [...document.querySelectorAll('iframe')].find(x => x.src.includes('/messages?'));
          const editor = frame?.contentDocument?.querySelector({json.dumps(EDITOR)});
          return {{text: editor?.innerText || ''}};
        }})()''')
        if not isinstance(filled, dict) or _text(filled.get("text")) != _text(message):
            result["status"] = "composer_fill_mismatch"
            return result

        result.update(effect=1, retry_safe=False)
        _append(ledger, result, "attempting")
        try:
            cdp_client.key(target, "Enter")
        except Exception:
            result["status"] = "send_unknown_reconcile_required"
            try:
                _append(ledger, result, "unknown")
            except Exception as error:
                result.update(ledger_terminal_write="failed", error_type=type(error).__name__)
            return result
        try:
            wait(4)
            after = cdp_client.evaluate(target, f'''/* TIKTOK_AFTER */ (() => {{
              const frame = [...document.querySelectorAll('iframe')].find(x => x.src.includes('/messages?'));
              const doc = frame?.contentDocument;
              const body = doc?.body?.innerText || '';
              const editor = doc?.querySelector({json.dumps(EDITOR)});
              const heads = [...(doc?.querySelectorAll('[data-e2e*="chat-header"],[class*="ChatHeader"],[class*="ConversationHeader"]') || [])];
              const handles = heads.flatMap(node => (node.innerText || '').match(/@[A-Za-z0-9._-]+/g) || []).map(x => x.toLowerCase());
              const recipientBound = handles.includes({json.dumps(candidate)});
              return {{url: location.href, recipient_bound: recipientBound,
                editor_empty: !editor || !(editor.innerText || '').trim(),
                exact_message: body.includes({json.dumps(message)})}};
            }})()''')
        except Exception:
            result["status"] = "send_unknown_reconcile_required"
            try:
                _append(ledger, result, "unknown")
            except Exception as error:
                result.update(ledger_terminal_write="failed", error_type=type(error).__name__)
            return result
        if isinstance(after, dict):
            result["official_url"] = after.get("url") or result.get("official_url")
        exact = (isinstance(after, dict) and after.get("recipient_bound") is True
                 and after.get("editor_empty") is True and after.get("exact_message") is True)
        result["exact_readback"] = exact
        result["status"] = ("sent_exact_official_readback" if exact
                            else "send_unknown_reconcile_required")
        try:
            _append(ledger, result, "sent" if exact else "unknown")
        except Exception as error:
            result.update(status="send_unknown_reconcile_required", exact_readback=False,
                          ledger_terminal_write="failed", error_type=type(error).__name__)
        return result
    finally:
        try:
            if target is not None:
                cdp_client.close_target(target, owner)
        except Exception as error:
            result["target_close_status"] = "failed"
            result["target_close_error_type"] = type(error).__name__
            if result.get("effect") == 1:
                result.update(status="send_unknown_reconcile_required", exact_readback=False,
                              retry_safe=False)
        finally:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            finally:
                lock.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", help="JSON file, or - for stdin")
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    raw = sys.stdin.read() if args.payload == "-" else Path(args.payload).read_text(encoding="utf-8")
    result = send_one(json.loads(raw), send=args.send)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {
        "ready", "deduplicated_exact_official_readback", "sent_exact_official_readback"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
