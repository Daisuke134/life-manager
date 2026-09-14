#!/usr/bin/env python3
"""Read-only normalization of the Coconala retainer-application tab and its threads.

A4 (2026-07-30). A3 banned NEW retainer applications because they escalate to a
synchronous 三者面談.  The applications already submitted still have to be carried
to completion, and nothing was carrying them: the reply lane sweeps /message,
/message?fromMyPage=true, /mypage/received_orders/open and
/mypage/received_orders/requests, and has never opened
/mypage/job_matching/applied/outsource_applications.  Nine applications were
sitting there on 2026-07-30 showing 未読1 / 未返信3, one of them parked on
「三者面談の候補日時が届きました」 since 00:26 with nobody answering.

Retainer threads are a different namespace from every thread this loop already
knows: /mypage/job_matching/job_talkroom/<26-char ULID>, with the message view at
that URL plus /talkroom.  Identities are ULIDs, never digits -- the same rule the
application ledger already uses to tell a retainer from a 単発 request.

This module only reads and normalizes.  It never opens or submits an application;
A3's refusal in application_eligibility.py is untouched and stays absolute.
"""

from __future__ import annotations

import importlib.util
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _load_local(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    from connector_outbox import (
        coconala_fallback_event_key,
        normalize_outgoing_body,
    )
except ModuleNotFoundError:  # imported directly by the unit-test loader
    _outbox = _load_local("connector_outbox")
    coconala_fallback_event_key = _outbox.coconala_fallback_event_key
    normalize_outgoing_body = _outbox.normalize_outgoing_body


JST = timezone(timedelta(hours=9))

APPLICATIONS_URL = (
    "https://coconala.com/mypage/job_matching/applied/outsource_applications"
)
APPLICATIONS_TITLE = "応募・スカウト管理"
THREAD_URL_TEMPLATE = "https://coconala.com/mypage/job_matching/job_talkroom/{}"

# Crockford base32 without I, L, O and U: a ULID, which is what a retainer listing
# and its application thread are keyed by. A digits-only id is a 単発 request.
RETAINER_ID = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")

# Statuses read off the live tab on 2026-07-30. Anything terminal is not work:
# messaging a client who already passed on us is noise, not follow-through.
TERMINAL_STATUSES = frozenset({"お見送り", "辞退済み", "見送り", "終了", "キャンセル"})
SCHEDULING_STATUSES = frozenset({"面談調整中"})

# The offer arrives as a system message, not as client prose. Both the wording and
# the ◾️ bullets below are verbatim from the live thread.
_OFFER_MARKER = re.compile(r"候補日時が届きました")
_OFFER_DURATION = re.compile(r"面談時間[：:]\s*\n?\s*(\d{1,3})\s*分")
_OFFER_WINDOW = re.compile(
    r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*"
    r"(\d{1,2}):(\d{2})\s*[~〜]\s*(\d{1,2}):(\d{2})"
)

_CARD_TIMESTAMP = re.compile(r"^(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})$")

# The platform announces a settled interview with its own system message, verbatim
# from the live thread on 2026-07-31 00:48 after the booking landed:
#   「買い手F様との三者面談の日時が確定しました。…面談日時：2026年08月03日 18:00〜18:30」
_CONFIRMED_MARKER = re.compile(r"三者面談の日時が確定しました")
_CONFIRMED_AT = re.compile(
    r"面談日時[：:]\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*"
    r"(\d{1,2}):(\d{2})\s*[~〜]\s*(\d{1,2}):(\d{2})"
)

# The DOM carries no stable ids or data attributes -- every class is a Tailwind
# utility -- so rows are located by their one durable anchor, the talkroom link,
# and read positionally from the end of the card, which is the only stable order:
#   title / client / last-message-at / [body] / applied-on / 提案額 / status
APPLICATIONS_EXPRESSION = r'''(async()=>{const wait=ms=>new Promise(r=>setTimeout(r,ms));const sel="a[href*='/mypage/job_matching/job_talkroom/']";for(let i=0;i<60&&!document.querySelector(sel);i++)await wait(200);await wait(800);const stamp=/^\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}$/;const chip=t=>{const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim().startsWith(t));const m=b&&(b.innerText||'').match(/(\d+)/);return m?parseInt(m[1],10):null};const cards=[...document.querySelectorAll(sel)].map(a=>{let card=a;for(let i=0;i<8&&card.parentElement;i++){card=card.parentElement;if((card.innerText||'').includes('提案額'))break}const lines=(card.innerText||'').split('\n').map(x=>x.trim()).filter(Boolean);const at=lines.findIndex(x=>stamp.test(x));const id=(a.getAttribute('href')||'').split('/').pop();return{application_id:id,thread_url:'https://coconala.com/mypage/job_matching/job_talkroom/'+id,title:lines[0]||'',client:lines[1]||'',last_message_at:at>=0?lines[at]:null,last_message_body:at>=0?lines.slice(at+1,Math.max(at+1,lines.length-3)).join('\n'):'',applied_on:lines[lines.length-3]||'',offer_text:lines[lines.length-2]||'',status:lines[lines.length-1]||''}}).filter((x,i,a)=>a.findIndex(y=>y.application_id===x.application_id)===i);const filters={all:chip('すべて'),unread:chip('未読'),unanswered:chip('未返信')};return JSON.stringify({url:location.href,title:document.title,container_present:filters.all!==null,not_found_present:/404|ページが見つかりません|お探しのページ/.test(document.title),error_present:/エラー|error|メンテナンス/i.test(document.title),filters,cards})})()'''

# Message rows in the thread are div.tw-w-full.tw-flex.tw-flex-col.tw-gap-2 whose
# first line is the author token: 自分 for us, システムメッセージ for the platform,
# the client's display name otherwise.
THREAD_EXPRESSION = r'''(async()=>{const wait=ms=>new Promise(r=>setTimeout(r,ms));for(let i=0;i<80&&document.body.innerText.length<800;i++)await wait(200);await wait(1200);const stamp=/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;const nodes=[...document.querySelectorAll('*')].filter(x=>x.children.length===0&&stamp.test((x.innerText||'').trim()));const messages=nodes.map(s=>{let card=s;for(let i=0;i<8&&card.parentElement;i++){card=card.parentElement;if((card.innerText||'').length>60)break}const lines=(card.innerText||'').split('\n').map(x=>x.trim()).filter(Boolean);const at=lines.findIndex(x=>stamp.test(x));const author=lines.slice(0,at).filter(x=>x!=='このメッセージはあなたにのみ表示されています')[0]||'';return{author,sent_at:(s.innerText||'').trim(),body:lines.slice(at+1).join('\n')}});const btn=t=>[...document.querySelectorAll('button')].some(b=>(b.innerText||'').trim()===t);const body=document.body.innerText;return JSON.stringify({url:location.href,title:document.title,container_present:messages.length>0,not_found_present:/404|ページが見つかりません/.test(document.title),error_present:/エラー|error|メンテナンス/i.test(document.title),banner_text:(body.match(/三者面談[^\n]*/)||[''])[0],interview_select_button_present:btn('面談日時を選択する'),confirmation_text_hint:/面談日時が確定|面談予定日時/.test(body),composer_present:!!document.querySelector('#jobtalkroom-message-input'),messages})})()'''


class RetainerCollectorUnhealthy(RuntimeError):
    """A retainer page reading cannot safely be interpreted as an empty queue."""


def is_retainer_id(value: Any) -> bool:
    return bool(RETAINER_ID.fullmatch(str(value or "").strip()))


def thread_url(application_id: str) -> str:
    """Canonical thread URL. The /talkroom message view is a suffix of this one."""
    if not is_retainer_id(application_id):
        raise ValueError("not a retainer application id")
    return THREAD_URL_TEMPLATE.format(str(application_id).strip())


def _card_timestamp(value: Any) -> datetime:
    match = _CARD_TIMESTAMP.fullmatch(str(value or "").strip())
    if match is None:
        raise ValueError("invalid card timestamp")
    year, month, day, hour, minute = (int(part) for part in match.groups())
    return datetime(year, month, day, hour, minute, tzinfo=JST)


def _timestamp(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def parse_interview_offer(text: Any) -> dict[str, Any] | None:
    """Return the platform's own offer, or None when this is not an offer at all.

    Client prose asking us to suggest times ("ご都合の良い日時をいくつか
    お知らせいただけますでしょうか") is deliberately NOT an offer: there is no
    modal to drive, so it belongs to the reply path.
    """
    body = str(text or "")
    if not _OFFER_MARKER.search(body):
        return None
    duration = _OFFER_DURATION.search(body)
    windows: list[dict[str, str]] = []
    for match in _OFFER_WINDOW.finditer(body):
        year, month, day, start_h, start_m, end_h, end_m = (
            int(part) for part in match.groups()
        )
        start = datetime(year, month, day, start_h, start_m, tzinfo=JST)
        end = datetime(year, month, day, end_h, end_m, tzinfo=JST)
        if end <= start:
            continue
        windows.append({"start": start.isoformat(), "end": end.isoformat()})
    if not duration or not windows:
        return None
    return {"duration_minutes": int(duration.group(1)), "windows": windows}


def parse_interview_confirmation(text: Any) -> dict[str, str] | None:
    """The settled interview, as the platform itself states it, or None.

    Requires BOTH the announcement phrase and a concrete 面談日時 line. The 取引の流れ
    explainer talks about confirmation in the abstract (「日時が確定したら、面談日時と
    参加用URLが届きます」) and carries no date, so it cannot satisfy this; a real
    confirmation always carries the booked date and time.
    """
    body = str(text or "")
    if not _CONFIRMED_MARKER.search(body):
        return None
    match = _CONFIRMED_AT.search(body)
    if match is None:
        return None
    year, month, day, start_h, start_m, end_h, end_m = (int(part) for part in match.groups())
    start = datetime(year, month, day, start_h, start_m, tzinfo=JST)
    end = datetime(year, month, day, end_h, end_m, tzinfo=JST)
    if end <= start:
        return None
    return {"start": start.isoformat(), "end": end.isoformat()}


def messages_from_dom(dom: dict[str, Any]) -> list[dict[str, Any]]:
    """Attribute every thread message to seller, client or system."""
    rows: list[dict[str, Any]] = []
    for raw in dom.get("messages", []) or []:
        if not isinstance(raw, dict):
            continue
        author = str(raw.get("author") or "").strip()
        if author == "自分":
            side = "seller"
        elif author == "システムメッセージ" or not author:
            side = "system"
        else:
            side = "client"
        rows.append({
            "side": side,
            "author": author,
            "sent_at": str(raw.get("sent_at") or ""),
            "body": str(raw.get("body") or ""),
        })
    return rows


def thread_state(dom: dict[str, Any]) -> dict[str, Any]:
    """Summarize one retainer thread into the few facts a decision needs."""
    messages = messages_from_dom(dom)
    offer = None
    for message in reversed(messages):
        offer = parse_interview_offer(message["body"])
        if offer is not None:
            break
    non_system = [row for row in messages if row["side"] != "system"]
    select_button = dom.get("interview_select_button_present") is True
    # Confirmation is the platform's own announcement message, not the absence of a
    # control. The earlier rule here -- "an offer exists and 面談日時を選択する is
    # gone" -- was measured wrong on 2026-07-31: the interview for
    # 01KYPJ0M0ACF4DBAFSJVFN9K24 WAS booked (system message 00:48, 面談日時：2026年
    # 08月03日 18:00〜18:30) and the offer message still renders its 面談日時を選択する
    # button, so the lane read a real booking as unbooked and would have booked it
    # again. A statement the platform makes beats an inference about a widget.
    confirmation = None
    for message in reversed(messages):
        confirmation = parse_interview_confirmation(message["body"])
        if confirmation is not None:
            break
    return {
        "application_id": str(dom.get("application_id") or ""),
        "messages": messages,
        "last_side": non_system[-1]["side"] if non_system else None,
        "interview_offer": offer,
        "interview_confirmed": confirmation is not None,
        "confirmed_interview": confirmation,
        "confirmation_text_hint": dom.get("confirmation_text_hint") is True,
        "interview_select_button_present": select_button,
        "composer_present": dom.get("composer_present") is True,
    }


def applications_from_dom(dom: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the applied-retainer tab, refusing to invent an empty page."""
    if not isinstance(dom, dict):
        raise RetainerCollectorUnhealthy("invalid_dom")
    if dom.get("not_found_present") is True:
        raise RetainerCollectorUnhealthy("not_found")
    if dom.get("error_present") is True:
        raise RetainerCollectorUnhealthy("error_page")
    if dom.get("container_present") is not True:
        raise RetainerCollectorUnhealthy("missing_container")
    rows: list[dict[str, Any]] = []
    for card in dom.get("cards", []) or []:
        if not isinstance(card, dict):
            raise RetainerCollectorUnhealthy("invalid_card")
        application_id = str(card.get("application_id") or "").strip()
        if not is_retainer_id(application_id):
            raise RetainerCollectorUnhealthy("invalid_application_id")
        rows.append({
            "application_id": application_id,
            "thread_url": thread_url(application_id),
            "title": str(card.get("title") or ""),
            "client": str(card.get("client") or ""),
            "last_message_at": card.get("last_message_at"),
            "last_message_body": str(card.get("last_message_body") or ""),
            "last_message_side": card.get("last_message_side"),
            "status": str(card.get("status") or "").strip(),
        })
    return rows


def _next_action(card: dict[str, Any]) -> str | None:
    """Decide from the tab alone what this row is waiting on, or None for nothing.

    The tab does not expose message authorship, so the conservative rule is: a row
    is work when the platform says the conversation is mid-flight and our own
    application text is not the last thing on it.
    """
    if card["status"] in TERMINAL_STATUSES:
        return None
    if card.get("last_message_side") == "seller":
        return None
    if not str(card.get("last_message_body") or "").strip():
        return None
    if card["status"] in SCHEDULING_STATUSES:
        return "schedule_interview"
    return "reply"


def build_queue(
    snapshot: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    """Build a retainer follow-through queue in the shape the reply lane consumes."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    detected_at = _timestamp(snapshot["captured_at"])
    collector_error = snapshot.get("retainer_collector_error")
    if collector_error:
        # A tab we could not read is not a tab with nothing on it.
        return {
            "status": "collector_unhealthy",
            "errors": [f"retainer:collector:{collector_error}"],
            "items": [],
        }
    cards = snapshot.get("retainer_applications")
    if cards is None:
        return {"status": "queue_empty", "errors": [], "items": []}
    if not isinstance(cards, list):
        return {
            "status": "collector_unhealthy",
            "errors": ["retainer:invalid_applications"],
            "items": [],
        }
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for card in cards:
        if not isinstance(card, dict):
            errors.append("retainer:invalid_card")
            continue
        application_id = str(card.get("application_id") or "").strip()
        if not is_retainer_id(application_id):
            errors.append("retainer:invalid_application_id")
            continue
        action = _next_action(card)
        if action is None:
            continue
        try:
            origin_at = _card_timestamp(card.get("last_message_at"))
        except ValueError:
            errors.append(f"retainer:{application_id}:missing_last_message_at")
            continue
        body = normalize_outgoing_body(str(card.get("last_message_body") or ""))
        if not body:
            errors.append(f"retainer:{application_id}:missing_event_identity")
            continue
        try:
            event_key = coconala_fallback_event_key(
                thread_id=application_id,
                buyer_sent_at=int(origin_at.timestamp()),
                ordinal=0,
                raw_body=body,
            )
        except ValueError:
            errors.append(f"retainer:{application_id}:missing_event_identity")
            continue
        # Retainer selection windows run in days, not minutes: the SLA that makes
        # sense here is "answer before the offered slots expire", not the 30-minute
        # buyer-message clock the P1 inquiry lane uses.
        warning_at = origin_at + timedelta(hours=6)
        breach_at = origin_at + timedelta(hours=24)
        items.append({
            "platform": "coconala",
            "lane": "retainer",
            "priority": "P2",
            "event_type": "retainer_application_message",
            "event_key": event_key,
            "coordination_key": f"coconala:{application_id}",
            "covered_event_keys": [event_key],
            "talkroom_id": application_id,
            "talkroom_url": thread_url(application_id),
            "application_status": card["status"],
            # Carried so an after-the-fact report can name the job rather than a ULID.
            "title": str(card.get("title") or ""),
            "client": str(card.get("client") or ""),
            # The tab renders the last message body but never its author, so a row
            # here is a candidate, not a verdict. coconala_queue_snapshot already
            # treats the direct-message list badge the same way: reopen the thread
            # and ground the decision in the live last-message side. Acting on the
            # list alone would message six clients who are waiting on nobody.
            "requires_thread_confirmation": True,
            "origin_at": origin_at.astimezone(timezone.utc).isoformat(),
            "detected_at": detected_at.isoformat(),
            "reply_due_at": (detected_at + timedelta(hours=1)).isoformat(),
            "warning_at": warning_at.astimezone(timezone.utc).isoformat(),
            "breach_at": breach_at.astimezone(timezone.utc).isoformat(),
            "sla_status": (
                "breached" if current >= breach_at
                else "warning" if current >= warning_at
                else "on_time"
            ),
            "next_action": action,
        })
    if errors:
        return {"status": "collector_unhealthy", "errors": errors, "items": []}
    queued = sorted(items, key=lambda value: (value["origin_at"], value["event_key"]))
    return {
        "status": "ready" if queued else "queue_empty",
        "errors": [],
        "items": queued,
    }
