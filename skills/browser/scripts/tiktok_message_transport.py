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


def _readback_expression(candidate: str, message: str, marker: str, sender: str = "") -> str:
    return r'''/* __MARKER__ */ (() => {
      const candidate = __CANDIDATE__;
      const expectedSender = __SENDER__.toLowerCase();
      const expected = __MESSAGE__;
      const normalize = value => String(value || '').replace(/\s+/g, ' ').trim();
      const isOfficial = (raw, top = false) => {
        try {
          const url = new URL(raw);
          const host = ['tiktok.com', 'www.tiktok.com'].includes(url.hostname.toLowerCase());
          const path = top ? /^\/business-suite\/messages\/?$/i : /^\/(?:business-suite\/)?messages\/?$/i;
          return url.protocol === 'https:' && host && path.test(url.pathname);
        } catch (_) { return false; }
      };
      const frame = [...document.querySelectorAll('iframe')].find(x => x.src.includes('/messages?'));
      const doc = frame?.contentDocument;
      const editor = doc?.querySelector('[contenteditable="true"][aria-label*="メッセージ"]');
      const messageList = doc?.querySelector('[data-e2e="dm-new-message-list"]');
      const heads = [...(doc?.querySelectorAll('[data-e2e*="chat-header"],[class*="ChatHeader"],[class*="ConversationHeader"]') || [])];
      const handles = heads.flatMap(node => (node.innerText || '').match(/@[A-Za-z0-9._-]+/g) || []).map(x => x.toLowerCase());
      const recipientBound = handles.includes(candidate.toLowerCase());
      const topUrl = location.href;
      const documentUrl = doc?.URL || '';
      const messageListText = normalize(messageList?.innerText || '');
      let frameLocationUrl = '';
      try { frameLocationUrl = frame?.contentWindow?.location?.href || ''; } catch (_) {}
      const officialDocument = isOfficial(topUrl, true) && isOfficial(documentUrl)
        && documentUrl === frameLocationUrl;
      const busy = messageList?.getAttribute('aria-busy');
      const messageListHydrated = !!messageList && doc?.readyState === 'complete'
        && busy !== 'true'
        && (busy === 'false' || messageList.getAttribute('data-loaded') === 'true'
            || messageList.getAttribute('data-hydrated') === 'true');
      const editorText = normalize(editor?.innerText || '');
      const editorEmpty = !!editor && !editorText;
      const bubbleSelector = '[data-e2e="dm-message"],[data-e2e="dm-message-text"],[data-e2e*="message-bubble"],[data-e2e*="message-content"],[class*="DivChatMessage"],[class*="DivMessageBubble"]';
      const rowBubbleSelector = '[data-e2e="dm-message"],[data-e2e*="message-bubble"],[class*="DivChatMessage"],[class*="DivMessageBubble"]';
      const messageLikeSelector = '[data-e2e*="message"],[class*="Message"]';
      const statusSelector = '[data-e2e*="status"],[class*="Status"],[aria-live],[data-status],[data-message-status],[aria-label],[title]';
      const bubbles = [...(messageList?.querySelectorAll(bubbleSelector) || [])]
        .filter(node => node && node.isConnected !== false);
      const knownBubbles = new Set(bubbles);
      const messageLikeNodes = [...(messageList?.querySelectorAll(messageLikeSelector) || [])]
        .filter(node => node && node.isConnected !== false
          && !/message[-_ ]?(list|composer)/i.test(node.getAttribute?.('data-e2e') || '')
          && !node.closest?.('[contenteditable="true"]'));
      const messageNodeResolutionComplete = messageLikeNodes.every(node => knownBubbles.has(node))
        && (!messageListText || bubbles.length > 0);
      const contextReady = officialDocument && recipientBound && !!editor && messageListHydrated
        && messageNodeResolutionComplete;
      const statusPattern = /\b(failed|error|pending|sending|queued|cancel(?:led|ed)|undelivered|not[ -]?sent)\b|失敗|エラー|送信中|未配信|保留|待機中/i;
      const statusClass = value => String(value || '').match(
        /failed|error|pending|sending|queued|cancel(?:led|ed)|undelivered|not[ -]?sent/i
      )?.[0] || '';
      const statusFor = node => {
        const row = boundedMessageRowFor(node);
        if (!row) return {value: '', owned: false};
        const values = [];
        const statusTextFor = item => {
          const rawText = String(item.innerText || '');
          if (!item.contains?.(node)) return rawText;
          const clone = item.cloneNode?.(true);
          if (!clone) return rawText;
          const path = [];
          let current = node;
          while (current && current !== item) {
            const parent = current.parentElement;
            const index = [...(parent?.children || [])].indexOf(current);
            if (index < 0) return rawText;
            path.push(index);
            current = parent;
          }
          if (current !== item) return rawText;
          let target = clone;
          for (let index = path.length - 1; index >= 0; index--) {
            target = target.children?.[path[index]];
            if (!target) return rawText;
          }
          if (target === clone) return '';
          if (typeof target.remove === 'function') target.remove();
          else if (target.parentNode?.removeChild) target.parentNode.removeChild(target);
          else return rawText;
          return String(clone.innerText ?? clone.textContent ?? '');
        };
        for (let current = node; current && current !== messageList; current = current.parentElement) {
          values.push(current.getAttribute?.('data-status'), current.getAttribute?.('data-message-status'),
            current.getAttribute?.('aria-label'), current.getAttribute?.('title'),
            statusClass(current.className));
          if (current.matches?.(statusSelector)) values.push(statusTextFor(current));
        }
        // Status descendants and siblings belong only to a scope with one canonical message root.
        for (const item of row.scope.querySelectorAll?.(statusSelector) || []) {
          values.push(item.getAttribute?.('data-status'), item.getAttribute?.('data-message-status'),
            item.getAttribute?.('aria-label'), item.getAttribute?.('title'),
            statusClass(item.className), statusTextFor(item));
        }
        return {value: values.filter(Boolean).join(' '), owned: true};
      };
      const explicitPositiveMarkers = new Set([
        'outgoing', 'outbound', 'self', 'own', 'ownmessage',
        'outgoing-message', 'outbound-message', 'self-message', 'own-message',
        'message-outgoing', 'message-outbound', 'message-self', 'message-own',
      ]);
      const senderMarkerEvidence = current => {
        let positive = false;
        let contradiction = false;
        for (const raw of [current.getAttribute?.('data-direction'),
          current.getAttribute?.('data-message-direction')]) {
          if (raw == null || !String(raw).trim()) continue;
          const direction = String(raw).trim().toLowerCase();
          if (['outgoing', 'outbound', 'self', 'own', 'me'].includes(direction)) positive = true;
          else contradiction = true;
        }
        const isOwn = current.getAttribute?.('data-is-own');
        if (isOwn != null) {
          if (['true', '1', 'yes'].includes(String(isOwn).toLowerCase())) positive = true;
          else contradiction = true;
        }
        const marker = [current.getAttribute?.('data-e2e'), current.className]
          .filter(Boolean).join(' ');
        if (/(incoming|inbound|received)/i.test(marker)
            || /(?:^|[-_ ])other(?:$|[-_ ])/i.test(marker)) contradiction = true;
        const dataE2e = String(current.getAttribute?.('data-e2e') || '').trim().toLowerCase();
        const classes = String(current.className || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
        if (explicitPositiveMarkers.has(dataE2e)
            || classes.some(token => explicitPositiveMarkers.has(token))) positive = true;
        for (const raw of [current.getAttribute?.('data-sender-handle'), current.getAttribute?.('data-sender')]) {
          if (raw == null || !String(raw).trim()) continue;
          const senderHandles = (String(raw).match(/@[A-Za-z0-9._-]+/g) || [])
            .map(handle => handle.toLowerCase());
          if (senderHandles.length) {
            if (expectedSender && senderHandles.every(handle => handle === expectedSender)) positive = true;
            else contradiction = true;
          } else if (['me', 'self', 'own', 'outgoing', 'outbound'].includes(String(raw).trim().toLowerCase())) {
            positive = true;
          } else {
            contradiction = true;
          }
        }
        return {positive, contradiction};
      };
      const boundedMessageRowFor = node => {
        let bounded = null;
        for (let scope = node.parentElement; scope && scope !== messageList; scope = scope.parentElement) {
          const messages = [...(scope.querySelectorAll?.(rowBubbleSelector) || [])]
            .filter(item => item && item.isConnected !== false);
          const roots = messages.filter(item =>
            !messages.some(other => other !== item && other.contains?.(item)));
          if (roots.length > 1) break;
          if (roots.length === 1 && (roots[0] === node || roots[0].contains?.(node))) {
            bounded = {scope, root: roots[0]};
          }
        }
        return bounded;
      };
      const isOutgoing = node => {
        const row = boundedMessageRowFor(node);
        if (!row) return false;
        let positive = false;
        let contradiction = false;
        const rowNodes = new Set([row.scope, row.root, ...(row.scope.querySelectorAll?.('*') || [])]);
        for (const current of rowNodes) {
          const evidence = senderMarkerEvidence(current);
          positive ||= evidence.positive;
          contradiction ||= evidence.contradiction;
        }
        // Outside the bounded row, ancestor markers can veto proof but cannot establish it.
        // Never inspect messageList descendants: they can belong to another conversation row.
        for (let current = row.scope.parentElement; current && current !== messageList;
             current = current.parentElement) {
          contradiction ||= senderMarkerEvidence(current).contradiction;
        }
        return positive && !contradiction;
      };
      const expectedText = normalize(expected);
      const exactBubbles = bubbles.filter(node => {
        const content = normalize(node.querySelector?.('[data-e2e="dm-message-text"],[data-e2e*="message-content"],[class*="DivMessageContent"]')?.innerText || '');
        return content === expectedText || normalize(node.innerText) === expectedText;
      });
      const possibleBubbleMatch = bubbles.some(node => normalize(node.innerText).includes(expectedText));
      const exactStatuses = exactBubbles.map(statusFor);
      const messageSenderProven = exactBubbles.length > 0 && exactBubbles.every(isOutgoing);
      const messageStatusSafe = messageSenderProven && exactStatuses.every(status => status.owned)
        && !exactStatuses.some(status => statusPattern.test(status.value));
      const exactMessage = contextReady && messageSenderProven && messageStatusSafe;
      const snapshotKey = JSON.stringify({
        documentUrl, topUrl, recipientBound, editorText, messageListText, busy,
        bubbles: bubbles.map(node => {
          const status = statusFor(node);
          return [normalize(node.innerText), status.owned, status.value];
        }),
      });
      return {
        url: topUrl, document_url: documentUrl, official_document: officialDocument,
        recipient_bound: recipientBound, editor: !!editor, editor_empty: editorEmpty,
        editor_text: editorText,
        context_ready: contextReady, message_list_hydrated: messageListHydrated,
        message_node_resolution_complete: messageNodeResolutionComplete,
        matching_bubble: exactBubbles.length > 0 || possibleBubbleMatch,
        exact_message: exactMessage,
        message_sender_proven: messageSenderProven, message_status_safe: messageStatusSafe,
        message_status: exactStatuses.map(status => status.value).join(' '),
        conversation_loaded: messageListHydrated,
        message_count: bubbles.length, snapshot_key: snapshotKey,
      };
    })()'''.replace("__MARKER__", marker).replace(
        "__CANDIDATE__", json.dumps(candidate)
    ).replace("__SENDER__", json.dumps(sender)).replace("__MESSAGE__", json.dumps(message))


def _send_guard_expressions(candidate: str, message: str) -> tuple[str, str]:
    token = "__tiktok_dm_send_guard_" + hashlib.sha256(
        (candidate + "\0" + message).encode()
    ).hexdigest()[:16]
    install = r'''/* TIKTOK_DISPATCH_GUARD */ (() => {
      const token = __TOKEN__;
      const candidate = __CANDIDATE__;
      const expected = __MESSAGE__;
      const normalize = value => String(value || '').replace(/\s+/g, ' ').trim();
      const official = (raw, top = false) => {
        try {
          const url = new URL(raw);
          const host = ['tiktok.com', 'www.tiktok.com'].includes(url.hostname.toLowerCase());
          const path = top ? /^\/business-suite\/messages\/?$/i : /^\/(?:business-suite\/)?messages\/?$/i;
          return url.protocol === 'https:' && host && path.test(url.pathname);
        } catch (_) { return false; }
      };
      const contextReady = (win, event) => {
        try {
          const doc = win.document;
          const topUrl = win.top.location.href;
          const docUrl = doc.URL;
          if (!official(topUrl, true) || !official(docUrl) || docUrl !== win.location.href) return false;
          const editor = doc.querySelector('[contenteditable="true"][aria-label*="メッセージ"]');
          const list = doc.querySelector('[data-e2e="dm-new-message-list"]');
          const busy = list?.getAttribute('aria-busy');
          const hydrated = !!list && doc.readyState === 'complete' && busy !== 'true'
            && (busy === 'false' || list.getAttribute('data-loaded') === 'true'
                || list.getAttribute('data-hydrated') === 'true');
          const bubbleSelector = '[data-e2e="dm-message"],[data-e2e="dm-message-text"],[data-e2e*="message-bubble"],[data-e2e*="message-content"],[class*="DivChatMessage"],[class*="DivMessageBubble"]';
          const messageLikeSelector = '[data-e2e*="message"],[class*="Message"]';
          const bubbles = [...(list?.querySelectorAll(bubbleSelector) || [])];
          const knownBubbles = new Set(bubbles);
          const messageLikeNodes = [...(list?.querySelectorAll(messageLikeSelector) || [])]
            .filter(node => !/message[-_ ]?(list|composer)/i.test(node.getAttribute?.('data-e2e') || '')
              && !node.closest?.('[contenteditable="true"]'));
          const listText = normalize(list?.innerText || '');
          const messageNodesResolved = messageLikeNodes.every(node => knownBubbles.has(node))
            && (!listText || bubbles.length > 0);
          const expectedText = normalize(expected);
          const duplicateMessage = bubbles.some(node => normalize(node.innerText).includes(expectedText));
          const heads = [...(doc.querySelectorAll('[data-e2e*="chat-header"],[class*="ChatHeader"],[class*="ConversationHeader"]') || [])];
          const handles = heads.flatMap(node => (node.innerText || '').match(/@[A-Za-z0-9._-]+/g) || [])
            .map(value => value.toLowerCase());
          const active = doc.activeElement;
          const focused = !!editor && (active === editor || !!editor.contains?.(active));
          const targetIsEditor = !event || (!!editor && (event.target === editor || !!editor.contains?.(event.target)));
          return !!editor && editor.isConnected !== false && normalize(editor.innerText) === normalize(expected)
            && focused && targetIsEditor && hydrated && messageNodesResolved && !duplicateMessage
            && handles.includes(candidate.toLowerCase());
        } catch (_) { return false; }
      };
      const installIn = win => {
        try {
          if (!win || !win.document || typeof win.addEventListener !== 'function') return false;
          if (win[token]?.installed === true) return true;
          const state = {installed: true, seen: false, status: null, keydownAllowed: false};
          const guard = event => {
            if (event.key !== 'Enter') return;
            state.seen = true;
            const allowed = contextReady(win, event);
            if (event.type === 'keydown') {
              state.keydownAllowed = allowed;
              if (!allowed) state.status = 'blocked';
              else if (state.status !== 'blocked') state.status = 'allowed';
            } else if (event.type === 'keyup'
                && (!state.keydownAllowed || !allowed)) {
              if (state.status !== 'allowed') state.status = 'blocked';
            }
            if ((event.type === 'keydown' && !allowed)
                || (event.type === 'keyup' && (!state.keydownAllowed || !allowed))) {
              event.preventDefault();
              event.stopPropagation();
              event.stopImmediatePropagation();
            }
          };
          win[token] = state;
          win.addEventListener('keydown', guard, true);
          win.addEventListener('keyup', guard, true);
          return true;
        } catch (_) { return false; }
      };
      const windows = [window];
      if (window === window.top) {
        for (const frame of [...document.querySelectorAll('iframe')]) {
          try { if (frame.contentWindow) windows.push(frame.contentWindow); } catch (_) {}
        }
      }
      const installed = windows.map(installIn);
      return {guard_installed: installed.length > 0 && installed.every(Boolean),
        ready: windows.some(win => contextReady(win, null))};
    })()'''.replace("__TOKEN__", json.dumps(token)).replace(
        "__CANDIDATE__", json.dumps(candidate)
    ).replace("__MESSAGE__", json.dumps(message))
    read_status = r'''/* TIKTOK_DISPATCH_GUARD_STATUS */ (() => {
      const token = __TOKEN__;
      const windows = [window];
      if (window === window.top) {
        for (const frame of [...document.querySelectorAll('iframe')]) {
          try { if (frame.contentWindow) windows.push(frame.contentWindow); } catch (_) {}
        }
      }
      const statuses = windows.map(win => win[token]).filter(state => state?.seen).map(state => state.status);
      return {guard_status: statuses.includes('blocked') ? 'blocked'
        : statuses.includes('allowed') ? 'allowed' : null};
    })()'''.replace("__TOKEN__", json.dumps(token))
    return install, read_status


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
        wait(7)
        before = cdp_client.evaluate(
            target, _readback_expression(candidate, message, "TIKTOK_COMPOSER_BEFORE", sender)
        )
        if not isinstance(before, dict) or "__error__" in before:
            result["status"] = "composer_unreadable"
            return result
        uncertain_prior = bool(prior and prior[-1].get("state") in {"attempting", "unknown", "sent"})
        if before.get("official_document") is True:
            result["official_url"] = before.get("url")
        if (before.get("official_document") is not True
                or before.get("message_list_hydrated") is not True
                or before.get("message_node_resolution_complete") is not True
                or before.get("context_ready") is not True):
            result.update(
                status="reconcile_required" if uncertain_prior else "conversation_context_unready",
                retry_safe=not uncertain_prior,
            )
            return result
        if before.get("recipient_bound") is not True or before.get("editor") is not True:
            result.update(
                status="reconcile_required" if uncertain_prior else "composer_recipient_binding_failed",
                retry_safe=not uncertain_prior,
            )
            return result
        if before.get("matching_bubble") is True and before.get("message_status_safe") is not True:
            result.update(status="message_delivery_unconfirmed", effect=1, retry_safe=False)
            try:
                if not prior or prior[-1].get("state") != "unknown":
                    _append(ledger, result, "unknown")
            except Exception as error:
                result.update(ledger_terminal_write="failed", error_type=type(error).__name__)
            return result
        if before.get("exact_message") is True and before.get("message_status_safe") is True:
            result.update(status="deduplicated_exact_official_readback", exact_readback=True)
            if not prior or prior[-1].get("state") != "sent":
                _append(ledger, result, "sent")
            return result
        if before.get("editor_empty") is not True:
            result.update(
                status="reconcile_required" if uncertain_prior else "composer_recipient_binding_failed",
                retry_safe=not uncertain_prior,
            )
            return result
        if (prior and prior[-1].get("state") in {"attempting", "unknown"}
                and type(before.get("message_count")) is int
                and before.get("message_count") == 0
                and before.get("message_list_hydrated") is True
                and before.get("editor_empty") is True
                and isinstance(before.get("snapshot_key"), str)):
            wait(0.5)
            stable = cdp_client.evaluate(
                target, _readback_expression(candidate, message, "TIKTOK_EMPTY_STABLE", sender)
            )
            stable_empty = (
                isinstance(stable, dict) and "__error__" not in stable
                and stable.get("official_document") is True
                and stable.get("context_ready") is True
                and stable.get("message_list_hydrated") is True
                and stable.get("message_node_resolution_complete") is True
                and stable.get("recipient_bound") is True
                and stable.get("editor_empty") is True
                and type(stable.get("message_count")) is int
                and stable.get("message_count") == 0
                and stable.get("snapshot_key") == before.get("snapshot_key")
            )
            if stable_empty:
                _append(ledger, result, "not_sent")
                result.update(status="not_sent_exact_official_readback", retry_safe=True)
                return result
        if uncertain_prior:
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
        pre_insert = cdp_client.evaluate(
            target, _readback_expression(candidate, message, "TIKTOK_PRE_INSERT", sender)
        )
        if (not isinstance(pre_insert, dict) or "__error__" in pre_insert
                or pre_insert.get("context_ready") is not True
                or pre_insert.get("recipient_bound") is not True
                or pre_insert.get("editor_empty") is not True):
            result["status"] = "composer_guard_unavailable"
            return result

        result.update(effect=1, retry_safe=False)
        _append(ledger, result, "attempting")
        try:
            cdp_client.insert(target, message)
            filled = cdp_client.evaluate(
                target, _readback_expression(candidate, message, "TIKTOK_FILLED", sender)
            )
            if (not isinstance(filled, dict) or "__error__" in filled
                    or filled.get("context_ready") is not True
                    or filled.get("recipient_bound") is not True
                    or _text(filled.get("editor_text")) != _text(message)):
                raise RuntimeError("composer_fill_or_context_unverified")
            guard_expression, guard_status_expression = _send_guard_expressions(candidate, message)
            guarded = cdp_client.guarded_key(
                target, guard_expression, guard_status_expression, "Enter"
            )
            if (not isinstance(guarded, dict) or "__error__" in guarded
                    or guarded.get("guard_status") != "allowed"):
                result.update(
                    status="send_unknown_reconcile_required",
                    send_guard_status=(guarded.get("guard_status") if isinstance(guarded, dict) else None),
                )
                _append(ledger, result, "unknown")
                return result
        except Exception:
            result["status"] = "send_unknown_reconcile_required"
            try:
                _append(ledger, result, "unknown")
            except Exception as error:
                result.update(ledger_terminal_write="failed", error_type=type(error).__name__)
            return result
        try:
            wait(4)
            after = cdp_client.evaluate(
                target, _readback_expression(candidate, message, "TIKTOK_AFTER", sender)
            )
        except Exception:
            result["status"] = "send_unknown_reconcile_required"
            try:
                _append(ledger, result, "unknown")
            except Exception as error:
                result.update(ledger_terminal_write="failed", error_type=type(error).__name__)
            return result
        if isinstance(after, dict) and after.get("official_document") is True:
            result["official_url"] = after.get("url") or result.get("official_url")
        exact = (
            isinstance(after, dict) and "__error__" not in after
            and after.get("official_document") is True
            and after.get("context_ready") is True
            and after.get("message_list_hydrated") is True
            and after.get("message_node_resolution_complete") is True
            and after.get("recipient_bound") is True
            and after.get("editor_empty") is True
            and after.get("exact_message") is True
            and after.get("message_status_safe") is True
        )
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
