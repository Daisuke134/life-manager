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
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import cdp
import tiktok_identity_readback


HANDLE = re.compile(r"@[A-Za-z0-9._-]+\Z")
EDITOR = '[contenteditable="true"][aria-label*="メッセージ"]'
READBACK_POLL_INTERVAL_SECONDS = 0.5
READBACK_MAX_ATTEMPTS = 60


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


def _official_messages_frame(value: dict) -> bool:
    return (
        value.get("frame_present") is True
        and value.get("frame_origin") == "https://www.tiktok.com"
        and value.get("frame_path") == "/messages"
        and value.get("frame_ready_state") == "complete"
    )


def _poll_until_stable(cdp_client, target: str, expression: str, *, ready, terminal,
                       wait=time.sleep, max_attempts: int = READBACK_MAX_ATTEMPTS):
    """Poll a read-only DOM projection until it is stable or reaches a safe terminal state."""
    previous_signature = None
    stable_reads = 0
    last: dict | None = None
    for attempt in range(max_attempts):
        value = cdp_client.evaluate(target, expression)
        if not isinstance(value, dict) or "__error__" in value:
            return value, attempt + 1, False
        last = value
        if terminal(value):
            return value, attempt + 1, False
        if ready(value):
            signature = json.dumps(value, sort_keys=True, separators=(",", ":"))
            if signature == previous_signature:
                stable_reads += 1
                if stable_reads >= 1:
                    return value, attempt + 1, True
            else:
                stable_reads = 0
            previous_signature = signature
        else:
            previous_signature = None
            stable_reads = 0
        if attempt + 1 < max_attempts:
            wait(READBACK_POLL_INTERVAL_SECONDS)
    return last, max_attempts, False


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


def _contacted_recipient(path: Path, candidate: str, effect_key: str) -> dict | None:
    if not path.exists():
        return None
    effective: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        row_effect_key = str(row.get("effect_key") or "").strip()
        if row_effect_key:
            effective[row_effect_key] = row
    for row_effect_key, row in effective.items():
        if row_effect_key == effect_key:
            continue
        row_candidate = str(row.get("candidate_handle") or "").strip().casefold()
        if row_candidate == candidate and row.get("state") in {"attempting", "unknown", "sent"}:
            return row
    return None


def _sheet_recipient_status(project_root: Path, candidate: str, run) -> str | None:
    policy_path = project_root / "delivery/tiktok-recipient-dedupe-policy.json"
    if not policy_path.exists():
        return None
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise ValueError("recipient_dedupe_policy_invalid")
    if policy.get("provider") != "google_sheets":
        raise ValueError("recipient_dedupe_policy_invalid")
    spreadsheet_id = str(policy.get("spreadsheet_id") or "").strip()
    sheet_range = str(policy.get("range") or "").strip()
    account = str(policy.get("account") or "").strip()
    if not spreadsheet_id or not sheet_range or not account:
        raise ValueError("recipient_dedupe_policy_invalid")
    completed = run(
        ["gog", "sheets", "get", spreadsheet_id, sheet_range,
         "--account", account, "--json", "--results-only", "--no-input"],
        check=False, capture_output=True, text=True,
    )
    if completed.returncode != 0:
        return "recipient_dedupe_readback_failed"
    try:
        decoded = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return "recipient_dedupe_readback_failed"
    values = decoded.get("values") if isinstance(decoded, dict) else decoded
    if not isinstance(values, list):
        return "recipient_dedupe_readback_failed"
    recorded = {
        str(row[0]).strip().casefold()
        for row in values
        if isinstance(row, list) and row and isinstance(row[0], str)
    }
    return "recipient_already_recorded" if candidate in recorded else None


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
             project_root: Path | None = None, dedupe_runner=subprocess.run) -> dict:
    """Preflight or send once. An uncertain mutation is never retried here."""
    resolved_root = (project_root or Path.cwd()).resolve()
    result, owner, candidate, sender, profile, message, ledger = _base(payload, resolved_root)
    lock = Path(str(ledger) + ".lock").open("a+", encoding="utf-8")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    prior = _records(ledger, result["effect_key"])
    if any(row.get("effect_binding_sha256") != result["effect_binding_sha256"] for row in prior):
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
        raise ValueError("effect_key_payload_conflict")
    if prior and prior[-1].get("state") in {"attempting", "unknown", "sent"}:
        result["retry_safe"] = False
    contacted = _contacted_recipient(ledger, candidate, result["effect_key"])
    if contacted is not None:
        result.update(
            status="recipient_already_contacted",
            retry_safe=False,
            prior_effect_key=contacted["effect_key"],
            prior_state=contacted["state"],
        )
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
        return result
    sheet_status = _sheet_recipient_status(resolved_root, candidate, dedupe_runner)
    if sheet_status is not None:
        result.update(status=sheet_status, retry_safe=sheet_status != "recipient_already_recorded")
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
        return result
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

        route = None
        if prior and prior[-1].get("state") in {"attempting", "unknown"}:
            route = _message_route(prior[-1].get("official_url"))
        if route is None:
            cdp_client.navigate(target, profile)
            wait(4)
            route_readback = cdp_client.evaluate(target, r'''/* TIKTOK_PROFILE_ROUTE */ (() => {
              const link = [...document.querySelectorAll('a[href*="/business-suite/messages"][href*="u="]')][0];
              return {url: location.href, message_route: link?.href || null};
            })()''')
            route = _message_route(
                route_readback.get("message_route") if isinstance(route_readback, dict) else None
            )
        if route is None:
            result["status"] = "recipient_message_route_unavailable"
            return result

        cdp_client.navigate(target, route)
        before_expression = f'''/* TIKTOK_COMPOSER_BEFORE */ (() => {{
          const frame = [...document.querySelectorAll('iframe')].find(x => x.src.includes('/messages?'));
          const doc = frame?.contentDocument;
          const editor = doc?.querySelector({json.dumps(EDITOR)});
          const messageList = doc?.querySelector('[data-e2e="dm-new-message-list"]');
          const listText = (messageList?.innerText || '').trim();
          const listBusy = !!messageList?.matches('[aria-busy="true"]')
            || !!messageList?.querySelector('[aria-busy="true"],[role="progressbar"],[data-e2e*="loading"],[class*="Loading"]')
            || /loading|読み込み中/i.test(listText);
          const explicitEmpty = /no messages|メッセージはありません/i.test(listText);
          const conversationLoaded = !!messageList && !listBusy && (!!listText || explicitEmpty);
          const normalise = value => (value || '').replace(/\\s+/g, ' ').trim();
          const messageNodes = messageList
            ? [messageList, ...messageList.querySelectorAll('*')].filter(node => !editor || !node.contains(editor))
            : [];
          const exactMessage = messageNodes.some(node => normalise(node.innerText) === normalise({json.dumps(message)}));
          const heads = [...(doc?.querySelectorAll('[data-e2e*="chat-header"],[class*="ChatHeader"],[class*="ConversationHeader"]') || [])];
          const handles = heads.flatMap(node => (node.innerText || '').match(/@[A-Za-z0-9._-]+/g) || []).map(x => x.toLowerCase());
          const recipientBound = handles.includes({json.dumps(candidate)});
          let frameUrl = null;
          try {{ frameUrl = doc?.location?.href ? new URL(doc.location.href) : null; }} catch (_) {{}}
          return {{url: location.href, recipient_bound: recipientBound, recipient_handles: handles,
            frame_present: !!frame, frame_origin: frameUrl?.origin || null,
            frame_path: frameUrl?.pathname || null, frame_ready_state: doc?.readyState || null,
            editor: !!editor, editor_empty: !editor || !(editor.innerText || '').trim(),
            exact_message: exactMessage,
            conversation_loaded: conversationLoaded,
            explicit_empty_state: explicitEmpty}};
        }})()'''
        before, before_attempts, before_ready = _poll_until_stable(
            cdp_client, target, before_expression,
            ready=lambda row: (
                _official_messages_frame(row)
                and row.get("recipient_bound") is True
                and row.get("editor") is True
                and row.get("editor_empty") is True
                and row.get("conversation_loaded") is True
            ),
            terminal=lambda row: (
                _official_messages_frame(row)
                and row.get("conversation_loaded") is True
                and bool(row.get("recipient_handles"))
                and row.get("recipient_bound") is not True
            ),
            wait=wait,
        )
        result["pre_send_readback_attempts"] = before_attempts
        if not isinstance(before, dict) or "__error__" in before:
            result["status"] = "composer_unreadable"
            return result
        result["official_url"] = before.get("url")
        if not before_ready:
            result["status"] = (
                "composer_recipient_binding_failed"
                if before.get("recipient_handles") and before.get("recipient_bound") is not True
                else "composer_hydration_timeout"
            )
            return result
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
            after_expression = f'''/* TIKTOK_AFTER */ (() => {{
              const frame = [...document.querySelectorAll('iframe')].find(x => x.src.includes('/messages?'));
              const doc = frame?.contentDocument;
              const editor = doc?.querySelector({json.dumps(EDITOR)});
              const messageList = doc?.querySelector('[data-e2e="dm-new-message-list"]');
              const listText = (messageList?.innerText || '').trim();
              const listBusy = !!messageList?.matches('[aria-busy="true"]')
                || !!messageList?.querySelector('[aria-busy="true"],[role="progressbar"],[data-e2e*="loading"],[class*="Loading"]')
                || /loading|読み込み中/i.test(listText);
              const explicitEmpty = /no messages|メッセージはありません/i.test(listText);
              const conversationLoaded = !!messageList && !listBusy && (!!listText || explicitEmpty);
              const normalise = value => (value || '').replace(/\\s+/g, ' ').trim();
              const messageNodes = messageList
                ? [messageList, ...messageList.querySelectorAll('*')].filter(node => !editor || !node.contains(editor))
                : [];
              const exactMessage = messageNodes.some(node => normalise(node.innerText) === normalise({json.dumps(message)}));
              const heads = [...(doc?.querySelectorAll('[data-e2e*="chat-header"],[class*="ChatHeader"],[class*="ConversationHeader"]') || [])];
              const handles = heads.flatMap(node => (node.innerText || '').match(/@[A-Za-z0-9._-]+/g) || []).map(x => x.toLowerCase());
              const recipientBound = handles.includes({json.dumps(candidate)});
              let frameUrl = null;
              try {{ frameUrl = doc?.location?.href ? new URL(doc.location.href) : null; }} catch (_) {{}}
              return {{url: location.href, recipient_bound: recipientBound,
                frame_present: !!frame, frame_origin: frameUrl?.origin || null,
                frame_path: frameUrl?.pathname || null, frame_ready_state: doc?.readyState || null,
                conversation_loaded: conversationLoaded,
                explicit_empty_state: explicitEmpty,
                editor_empty: !editor || !(editor.innerText || '').trim(),
                exact_message: exactMessage}};
            }})()'''
            after, after_attempts, after_ready = _poll_until_stable(
                cdp_client, target, after_expression,
                ready=lambda row: (
                    _official_messages_frame(row)
                    and row.get("recipient_bound") is True
                    and row.get("conversation_loaded") is True
                    and row.get("editor_empty") is True
                    and row.get("exact_message") is True
                ),
                terminal=lambda row: False,
                wait=wait,
            )
            result["post_send_readback_attempts"] = after_attempts
        except Exception:
            result["status"] = "send_unknown_reconcile_required"
            try:
                _append(ledger, result, "unknown")
            except Exception as error:
                result.update(ledger_terminal_write="failed", error_type=type(error).__name__)
            return result
        if isinstance(after, dict):
            result["official_url"] = after.get("url") or result.get("official_url")
        exact = (isinstance(after, dict) and after_ready
                 and _official_messages_frame(after)
                 and after.get("recipient_bound") is True
                 and after.get("editor_empty") is True
                 and after.get("exact_message") is True)
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
        "ready", "not_sent_exact_official_readback",
        "deduplicated_exact_official_readback", "sent_exact_official_readback"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
